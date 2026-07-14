"""ui/background_editor/background_editor_screen.py — écran Background Editor.

3 colonnes : finder (backgrounds) · canvas d'inpainting (BackgroundInpainting :
repeindre la palette par tuile 8×8, partagé entre scènes, cf. bg_inpaint_canvas) ·
inspecteur (dimensions, budget tuiles, liste des palettes éditables, algo de
compression). La compression est non-destructive (cf. core/bg_compress) — le PNG
n'est jamais modifié, tout vit en métadonnées dans le .json du BackgroundAsset.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QListWidget,
    QListWidgetItem, QComboBox, QFileDialog, QFrame,
    QMenu, QMessageBox, QAbstractItemView, QPushButton, QGridLayout, QCheckBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, QObject, QRunnable, QThreadPool, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W, FinderSection, AssetHeaderBar, ScriptPickerPopup
from ui.common.icons import COLOR_BACKGROUND
from ui.common.palette_swatch import bank_icon
from core.project import PaletteBank
from core.command_dispatcher import get_dispatcher
from core.history import get_history, DeleteResourceCmd
from core.color_utils import COMPRESSION_METHODS
from core.bg_compress import bg_fits_vram
from .bg_inpaint_canvas import BgInpaintCanvas

_BG_COLOR = COLOR_BACKGROUND

_CTX_MENU_QSS = (
    f"QMenu{{background:{C.BG_RAISED}; color:{C.TEXT_NORM};"
    f"border:1px solid {C.BORDER_MID}; font-family:{T.MONO};"
    f"font-size:{T.MD}px; padding:2px;}}"
    f"QMenu::item{{padding:4px 20px 4px 12px; border-radius:2px;}}"
    f"QMenu::item:selected{{background:{C.BG_SEL}; color:{C.ACCENT_GRN};}}"
)


# ── Compression hors-thread ─────────────────────────────────────────────────
# La compression (bg_compress) peut prendre plusieurs secondes sur un grand fond
# ou une photo : on la lance dans un worker du QThreadPool pour ne JAMAIS geler
# l'éditeur. Le worker calcule le dict de compression ; le thread UI l'applique
# à l'asset (Project.apply_bg_compression) puis rafraîchit.

class _CompressSignals(QObject):
    done   = pyqtSignal(int, str, dict)   # token, source_name, résultat
    failed = pyqtSignal(int, str)          # token, message


class _CompressTask(QRunnable):
    def __init__(self, token: int, png_path: Path, mode: str, method: str, dither: bool):
        super().__init__()
        self._token = token
        self._png = str(png_path)
        self._name = Path(png_path).name
        self._mode = mode           # "tiled4" | "tiled8" | "bitmap"
        self._method = method
        self._dither = dither
        self.signals = _CompressSignals()

    def run(self):
        try:
            from core.bg_compress import (
                compress_background, compress_background_8bpp, compress_background_bitmap,
            )
            if self._mode == "bitmap":
                c = compress_background_bitmap(self._png, dither=self._dither)
            elif self._mode == "tiled8":
                c = compress_background_8bpp(self._png, dither=self._dither)
            else:
                c = compress_background(self._png, method=self._method)
            self.signals.done.emit(self._token, self._name, c)
        except Exception as e:  # noqa: BLE001 — remonté à l'UI, pas avalé
            self.signals.failed.emit(self._token, str(e))


# ── Finder (gauche) ─────────────────────────────────────────────────────────

class BgFinderPanel(QWidget):
    bg_selected  = pyqtSignal(object)   # BackgroundAsset | None
    import_asked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180); self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._blocking = False
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        hdr = QFrame(); hdr.setFixedHeight(20)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(8, 0, 0, 0)
        lbl = QLabel("BACKGROUND FINDER")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        hl.addWidget(lbl); root.addWidget(hdr)

        sec = FinderSection("BACKGROUNDS", _BG_COLOR)
        sec.set_add_tooltip("Importer un PNG")
        sec.add_clicked.connect(self.import_asked)
        root.addWidget(sec, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
            f"QListWidget::item{{padding:4px 6px;}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL}; color:{_BG_COLOR};"
            f"border-left:2px solid {_BG_COLOR};}}"
            # Éditeur de renommage en place : mêmes police/taille que la ligne,
            # sinon le QLineEdit s'ouvre avec la police par défaut (plus grande)
            # et le texte est rogné verticalement.
            f"QListWidget QLineEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
            f"border:1px solid {_BG_COLOR}; padding:0 4px; margin:0;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
        )
        self._list.currentItemChanged.connect(self._on_sel)
        # Renommage en place : clic sur un item déjà sélectionné (même mécanisme
        # que les autres finders — sprite/scene/prefab).
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._list.itemChanged.connect(self._on_item_renamed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._ctx_menu)
        sec.set_widget(self._list)

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self, select: str = None):
        self._blocking = True
        self._list.blockSignals(True)
        self._list.clear()
        for ba in (list(self._project.backgrounds) if self._project else []):
            it = QListWidgetItem(ba.name)
            it.setFont(QFont(T.MONO, T.SM))
            it.setData(Qt.ItemDataRole.UserRole, ba)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(it)
        self._list.blockSignals(False)
        self._blocking = False
        target = select or (self._list.item(0).text() if self._list.count() else None)
        for i in range(self._list.count()):
            if self._list.item(i).text() == target:
                self._list.setCurrentRow(i)
                return
        # Plus rien à sélectionner (liste vide ou cible introuvable) : notifier
        # pour que la preview / l'inspecteur se vident.
        self.bg_selected.emit(None)

    def _on_sel(self, cur, _prev):
        if self._blocking:
            return
        self.bg_selected.emit(cur.data(Qt.ItemDataRole.UserRole) if cur else None)

    # ── Renommage en place ────────────────────────────────────────

    def _reset_item_text(self, item: QListWidgetItem, ba):
        self._blocking = True
        item.setText(ba.name if ba else "")
        self._blocking = False

    def _on_item_renamed(self, item: QListWidgetItem):
        if self._blocking or not self._project:
            return
        ba = item.data(Qt.ItemDataRole.UserRole)
        new_name = item.text().strip()
        if not ba or not new_name or new_name == ba.name:
            self._reset_item_text(item, ba)
            return
        if self._project.get_background(new_name):
            QMessageBox.warning(self, "Nom déjà utilisé",
                                f"Un fond nommé « {new_name} » existe déjà.")
            self._reset_item_text(item, ba)
            return
        with get_dispatcher().suspended():
            self._project.rename_background(ba, new_name)
        self._reset_item_text(item, ba)
        # setCurrentRow ne réémet pas la sélection si l'item était déjà courant :
        # forcer le rafraîchissement de l'inspecteur pour refléter le nouveau nom.
        self.bg_selected.emit(ba)

    # ── Menu contextuel ───────────────────────────────────────────

    def _ctx_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        ba = item.data(Qt.ItemDataRole.UserRole)
        if not ba:
            return
        menu = QMenu(self)
        menu.setStyleSheet(_CTX_MENU_QSS)
        act_rename = menu.addAction("Renommer")
        menu.addSeparator()
        act_del = menu.addAction("Supprimer le fond")
        chosen = menu.exec(self._list.viewport().mapToGlobal(pos))
        if chosen == act_rename:
            self._list.editItem(item)
        elif chosen == act_del:
            self._delete_bg(ba)

    def _delete_bg(self, ba):
        if not self._project:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer le fond « {ba.name} » ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        # Le PNG source doit partir avec l'asset : sinon _reconcile_backgrounds
        # recrée le fond au prochain chargement du projet. Les métadonnées de
        # compression vivent dans le JSON, qu'un Ctrl+Z (restore) ramène intact.
        png = (self._project.background_images_dir / ba.source) if ba.source else None
        with get_dispatcher().suspended():
            if png and png.exists():
                png.unlink()
        get_history().push(DeleteResourceCmd(
            self._project.backgrounds, ba, lambda: self.refresh()))


# ── Liste dynamique de palettes (swatches) ──────────────────────────────────

class _BgPaletteBar(QWidget):
    """Liste dynamique des sous-palettes d'un fond, rendue en swatches (même
    style que le _PaletteSlotGrid du Scene Inspector). Ce n'est PAS une grille
    fixe de 16 : autant de cases que de palettes, plus un « + » (jusqu'à 16) pour
    en ajouter une. Clic = palette active de peinture ; clic droit = remplacer /
    vider / supprimer."""

    selected         = pyqtSignal(int)
    add_requested    = pyqtSignal()
    replace_requested = pyqtSignal(int)
    clear_requested  = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    _COLS = 8
    _ICON = 28

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._active = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        self._pal_btns: list[QPushButton] = []
        self._add_btn: Optional[QPushButton] = None
        self._read_only = False

    def load(self, palettes: list, active: int = 0, read_only: bool = False):
        self._read_only = read_only
        for b in self._pal_btns:
            self._grid.removeWidget(b); b.deleteLater()
        self._pal_btns.clear()
        if self._add_btn is not None:
            self._grid.removeWidget(self._add_btn); self._add_btn.deleteLater()
            self._add_btn = None

        n = len(palettes)
        self._active = max(0, min(active, n - 1)) if n else -1
        for i, pal in enumerate(palettes):
            btn = QPushButton()
            btn.setFixedSize(self._ICON + 10, self._ICON + 10)
            bank = PaletteBank(name=f"Palette {i}", colors=list(pal))
            btn.setIcon(bank_icon(bank, size=self._ICON))
            btn.setIconSize(QSize(self._ICON, self._ICON))
            if read_only:
                btn.setToolTip("Palette 256 couleurs (8bpp) — lecture seule")
            else:
                btn.setToolTip(f"Palette {i} — clic : peindre avec · clic droit : remplacer/vider/supprimer")
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, i=i, b=btn: self._ctx(b, pos, i))
            self._style(btn, i == self._active)
            btn.clicked.connect(lambda _c=False, i=i: self._select(i))
            self._grid.addWidget(btn, *divmod(i, self._COLS))
            self._pal_btns.append(btn)

        if n < 16 and not read_only:
            add = QPushButton("＋")
            add.setFixedSize(self._ICON + 10, self._ICON + 10)
            add.setFont(QFont(T.MONO, T.LG, QFont.Weight.Bold))
            add.setCursor(Qt.CursorShape.PointingHandCursor)
            add.setToolTip("Ajouter une palette (depuis le catalogue projet)")
            add.setStyleSheet(
                f"QPushButton{{color:{self._accent}; background:{C.BG_INPUT};"
                f"border:1px dashed {C.BORDER_MID}; border-radius:4px;}}"
                f"QPushButton:hover{{border-color:{self._accent}; color:{C.TEXT_HI};}}"
            )
            add.clicked.connect(lambda: self.add_requested.emit())
            self._grid.addWidget(add, *divmod(n, self._COLS))
            self._add_btn = add

    def _style(self, btn: QPushButton, active: bool):
        border = self._accent if active else C.BORDER_MID
        width = 2 if active else 1
        btn.setStyleSheet(
            f"QPushButton{{background:{C.BG_INPUT}; border:{width}px solid {border};"
            f"border-radius:4px;}}"
            f"QPushButton:hover{{border-color:{self._accent};}}"
        )

    def _select(self, i: int):
        self._active = i
        for j, b in enumerate(self._pal_btns):
            self._style(b, j == i)
        self.selected.emit(i)

    def _ctx(self, btn: QPushButton, pos, i: int):
        menu = QMenu(self)
        menu.setStyleSheet(_CTX_MENU_QSS)
        a_rep = menu.addAction("Remplacer (catalogue)…")
        a_clr = menu.addAction("Vider la palette")
        menu.addSeparator()
        a_del = menu.addAction("Supprimer la palette")
        a_del.setEnabled(len(self._pal_btns) > 1)
        act = menu.exec(btn.mapToGlobal(pos))
        if act == a_rep:
            self.replace_requested.emit(i)
        elif act == a_clr:
            self.clear_requested.emit(i)
        elif act == a_del:
            self.remove_requested.emit(i)

    def anchor(self) -> QWidget:
        """Widget d'ancrage pour les popups (le bouton +, sinon la barre)."""
        return self._add_btn or self


# ── Propriétés (droite) ─────────────────────────────────────────────────────

class BgPropertiesPanel(QWidget):
    changed = pyqtSignal()          # compression recalculée → re-render du canvas
    renamed = pyqtSignal()          # fond renommé depuis l'en-tête → rafraîchir le finder
    palette_selected = pyqtSignal(int)  # palette active pour la peinture (index)
    palettes_changed = pyqtSignal()     # liste des palettes mutée → re-render du canvas
    recompress_requested = pyqtSignal(object, object, str, bool)  # (ba, png, mode_token, dither) → hors-thread

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220); self.setMaximumWidth(440)
        self.setStyleSheet(f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};")
        self._project = None
        self._ba = None
        self._blocking = False

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # ── En-tête : nom du fond — composant partagé (même template/couleurs/
        # renommage que Scene Manager, Sprite Editor, Sound Mixer, Script Editor).
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_rename)
        outer.addWidget(self._header)

        body = QWidget(); body.setStyleSheet(f"background:{C.BG_PANEL};")
        outer.addWidget(body, 1)
        root = QVBoxLayout(body); root.setContentsMargins(10, 8, 10, 8); root.setSpacing(2)

        # ── Bandeau MODE COULEUR : [4bpp] [8bpp] + dithering (8bpp seulement).
        #    Changer de mode recompresse le fond (hors-thread).
        mode_row = QHBoxLayout(); mode_row.setContentsMargins(0, 2, 0, 2); mode_row.setSpacing(6)
        self._btn_4bpp = self._mode_btn("4bpp", "Tuilé · 16 couleurs × 16 palettes · inpainting (pixel-art)")
        self._btn_8bpp = self._mode_btn("8bpp", "Tuilé · 256 couleurs, une seule palette (pixel-art riche)")
        self._btn_bitmap = self._mode_btn("Bitmap", "Mode 4 · plein écran 240×160, 256 couleurs, sans tuiles (photos / écrans-titre)")
        self._btn_4bpp.clicked.connect(lambda: self._set_mode("tiled4"))
        self._btn_8bpp.clicked.connect(lambda: self._set_mode("tiled8"))
        self._btn_bitmap.clicked.connect(lambda: self._set_mode("bitmap"))
        mode_row.addWidget(self._btn_4bpp, 1); mode_row.addWidget(self._btn_8bpp, 1)
        mode_row.addWidget(self._btn_bitmap, 1)
        root.addLayout(mode_row)
        self._chk_dither = QCheckBox("Dithering")
        self._chk_dither.setFont(QFont(T.MONO, T.SM))
        self._chk_dither.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_dither.toggled.connect(self._on_dither_toggled)
        root.addWidget(self._chk_dither)

        W.separator(root); W.section("IMAGE", root)
        self._dims = self._info_label(); root.addWidget(self._dims)

        W.separator(root); W.section("COMPRESSION", root)
        self._tiles = self._info_label(); root.addWidget(self._tiles)
        self._pals = self._info_label(); root.addWidget(self._pals)

        # Validation NON-BLOQUANTE : alertes sur ce que la compression a dû faire
        # (dimensions, couleurs/tuile, palettes fusionnées, budget VRAM). Le PNG
        # source n'est jamais modifié — ces messages décrivent la représentation.
        self._valid = QLabel("—")
        self._valid.setFont(QFont(T.MONO, T.SM))
        self._valid.setWordWrap(True)
        self._valid.setTextFormat(Qt.TextFormat.RichText)
        self._valid.setStyleSheet("padding-top:2px;")
        root.addWidget(self._valid)

        # ── PALETTES : liste dynamique de swatches (clic = palette peinte,
        #    « + » pour ajouter depuis le catalogue, clic droit = remplacer/vider/
        #    supprimer). Réutilise bank_icon et le style du Scene Inspector.
        W.separator(root); W.section("PALETTES", root)
        self._pal_bar = _BgPaletteBar(_BG_COLOR)
        self._pal_bar.selected.connect(self.palette_selected)
        self._pal_bar.add_requested.connect(self._on_pal_add)
        self._pal_bar.replace_requested.connect(self._on_pal_replace)
        self._pal_bar.clear_requested.connect(self._on_pal_clear)
        self._pal_bar.remove_requested.connect(self._on_pal_remove)
        root.addWidget(self._pal_bar)

        # COMPRESSION AVANCÉE (choix d'algo) — 4bpp uniquement (masqué en 8bpp,
        # où la quantification 256 couleurs a un seul algo).
        self._adv_box = QWidget()
        adv_l = QVBoxLayout(self._adv_box)
        adv_l.setContentsMargins(0, 0, 0, 0); adv_l.setSpacing(2)
        W.separator(adv_l); W.section("COMPRESSION AVANCÉE", adv_l)
        self._cb = QComboBox(); self._cb.setFont(QFont(T.MONO, T.SM))
        for tok, label in COMPRESSION_METHODS:
            self._cb.addItem(label, tok)
        self._cb.currentIndexChanged.connect(self._on_method)
        W.row("Algo", self._cb, adv_l)
        root.addWidget(self._adv_box)

        self._btn = W.btn_accent("⟐  Importer / remplacer l'image…")
        self._btn.clicked.connect(self._on_replace)
        root.addWidget(self._btn)

        self._btn_restore = self._mini_btn(
            "↺  Restaurer l'original…",
            "Réinitialise le fond comme au premier import (recompression du PNG) — "
            "les palettes ajoutées et la peinture seront perdues.")
        self._btn_restore.clicked.connect(self._on_restore)
        root.addWidget(self._btn_restore)
        root.addStretch()

    def _info_label(self):
        l = QLabel("—"); l.setFont(QFont(T.MONO, T.SM)); l.setWordWrap(True)
        l.setStyleSheet(f"color:{C.TEXT_NORM};")
        return l

    def _mini_btn(self, text: str, tip: str = "") -> QPushButton:
        b = QPushButton(text); b.setToolTip(tip)
        b.setFont(QFont(T.MONO, T.SM))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:3px 8px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; background:{C.BG_HOVER};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};}}"
        )
        return b

    def _mode_btn(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text); b.setToolTip(tip)
        b.setCheckable(True)
        b.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:4px; padding:2px 10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            f"QPushButton:checked{{color:{_BG_COLOR}; border:2px solid {_BG_COLOR};"
            f"background:{C.BG_SEL};}}"
        )
        return b

    # ── Mode couleur (4bpp / 8bpp) ────────────────────────────────

    def _cur_mode_token(self) -> str:
        if not self._ba:
            return "tiled4"
        if self._ba.mode == "bitmap":
            return "bitmap"
        return "tiled8" if self._ba.bpp == 8 else "tiled4"

    def _refresh_mode_buttons(self):
        tok = self._cur_mode_token()
        self._blocking = True
        self._btn_4bpp.setChecked(tok == "tiled4")
        self._btn_8bpp.setChecked(tok == "tiled8")
        self._btn_bitmap.setChecked(tok == "bitmap")
        self._chk_dither.setVisible(tok in ("tiled8", "bitmap"))
        self._chk_dither.setChecked(bool(self._ba and self._ba.dither))
        self._adv_box.setVisible(tok == "tiled4")
        enabled = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        for b in (self._btn_4bpp, self._btn_8bpp, self._btn_bitmap):
            b.setEnabled(enabled)
        self._blocking = False

    def _set_mode(self, token: str):
        if self._blocking or not self._ba or not self._project:
            self._refresh_mode_buttons(); return
        if self._cur_mode_token() == token:
            self._refresh_mode_buttons(); return
        ap = self._png_path()
        if not ap or not ap.exists():
            self._refresh_mode_buttons(); return
        self.recompress_requested.emit(self._ba, ap, token, self._ba.dither)

    def _on_dither_toggled(self, on: bool):
        tok = self._cur_mode_token()
        if self._blocking or not self._ba or tok not in ("tiled8", "bitmap"):
            return
        ap = self._png_path()
        if not ap or not ap.exists():
            return
        self._ba.dither = on
        self.recompress_requested.emit(self._ba, ap, tok, on)

    def load(self, ba, project):
        self._project, self._ba = project, ba
        self._blocking = True
        if ba:
            self._header.set_header("background", "BACKGROUND", ba.name)
        else:
            self._header.set_header("empty", "", "")
        if ba and ba.mode == "bitmap" and ba.bitmap:
            self._dims.setText(f"{ba.out_w}×{ba.out_h} px  (bitmap, ajusté à ≤240×160)")
            self._tiles.setStyleSheet(f"color:{C.TEXT_NORM};")
            self._tiles.setText("Mode 4 — plein écran, sans tuiles")
            self._pals.setText("Palette : 256 couleurs (1)")
        elif ba and ba.tileset:
            self._dims.setText(f"{ba.tiles_w*8}×{ba.tiles_h*8} px  ({ba.tiles_w}×{ba.tiles_h} tuiles)")
            # Budget VRAM : 512 tuiles/charblock en 4bpp, 256 en 8bpp (2× la taille).
            budget_max = 256 if ba.bpp == 8 else 512
            n = len(ba.tileset); fits, budget = bg_fits_vram(ba.tileset, budget=budget_max)
            col = C.TEXT_NORM if fits else "#e06060"
            self._tiles.setStyleSheet(f"color:{col};")
            self._tiles.setText(f"Tuiles uniques : {n} / {budget}  ({ba.bpp}bpp)"
                                + ("" if fits else "  ⚠ dépasse la VRAM"))
            if ba.bpp == 8:
                self._pals.setText("Palette : 256 couleurs (1)")
            else:
                self._pals.setText(f"Palettes : {len(ba.palettes)} / 16")
            mi = self._cb.findData(getattr(ba, "compress_method", "median_cut"))
            self._cb.setCurrentIndex(mi if mi >= 0 else 0)
        else:
            for l in (self._dims, self._tiles, self._pals):
                l.setText("—")
        self._blocking = False
        self._refresh_mode_buttons()
        self._reload_palettes()

    # ── Validation (non-bloquante) ────────────────────────────────

    def _diag_for(self, ba) -> dict:
        """Diagnostics de compression : depuis l'asset, sinon calculés à la volée
        pour les fonds importés avant le validateur (mémorisés sur l'asset)."""
        if not ba:
            return {}
        if ba.diagnostics:
            return ba.diagnostics
        ap = self._png_path()
        if ap and ap.exists():
            try:
                from core.bg_compress import analyze_background_source
                ba.diagnostics = analyze_background_source(ap, method=ba.compress_method)
            except Exception:
                ba.diagnostics = {}
        return ba.diagnostics or {}

    def _validation_lines(self, ba) -> list:
        if not ba or not (ba.tileset or ba.bitmap):
            return [("⚠ Compression impossible — image illisible ou vide.", C.ACCENT_RED)]
        warn, err, ok = C.ACCENT_YLW, C.ACCENT_RED, C.ACCENT_GRN
        if ba.mode == "bitmap":
            diag = self._diag_for(ba)
            lines: list = []
            if diag.get("scaled"):
                lines.append((f"⚠ Image mise à l'échelle → {ba.out_w}×{ba.out_h} (≤ 240×160).", warn))
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append(("⚠ &gt; 256 couleurs — réduites à 256 (perte).", warn))
            if not lines:
                lines.append(("✓ Bitmap GBA (Mode 4) — plein écran, sans perte de tuiles.", ok))
            return lines
        diag = self._diag_for(ba)
        lines: list = []
        if diag and not diag.get("multiple_of_8", True):
            w, h = diag.get("src_w"), diag.get("src_h")
            lines.append((f"⚠ {w}×{h} px non multiple de 8 — complété par transparence "
                          f"({ba.tiles_w*8}×{ba.tiles_h*8}).", warn))
        if ba.bpp == 8:
            # 8bpp : une seule palette de 256 ; perte si le source en avait plus.
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append(("⚠ &gt; 256 couleurs — réduites à 256 (perte, mode 8bpp).", warn))
            budget = 256
        else:
            mtc = diag.get("max_tile_colors", 0)
            if mtc > 15:
                n = diag.get("tiles_reduced", 0)
                lines.append((f"⚠ {n} tuile(s) &gt; 15 couleurs (max {mtc}) — couleurs réduites (perte).", warn))
            pre = diag.get("pre_merge_palettes")
            if pre and pre > 16:
                lines.append((f"⚠ {pre} palettes nécessaires &gt; 16 — fusionnées en {len(ba.palettes)} (perte).", warn))
            budget = 512
        fits, bud = bg_fits_vram(ba.tileset, budget=budget)
        if not fits:
            lines.append((f"⚠ {len(ba.tileset)} tuiles uniques &gt; {bud} — dépasse la VRAM ({ba.bpp}bpp).", err))
        if not lines:
            lines.append((f"✓ Compatible GBA ({ba.bpp}bpp) — compressé sans perte.", ok))
        return lines

    def _set_validation(self):
        if not self._ba:
            self._valid.setText("—")
            return
        html = "<br>".join(
            f"<span style='color:{col};'>{txt}</span>"
            for txt, col in self._validation_lines(self._ba))
        self._valid.setText(html)

    # ── Section PALETTES ──────────────────────────────────────────

    def _reload_palettes(self, select: int = 0):
        has_data = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        pals = self._ba.palettes if has_data else []
        # Palette non éditable en 8bpp (256) et en bitmap (256).
        read_only = bool(self._ba and (self._ba.mode == "bitmap" or self._ba.bpp == 8))
        self._pal_bar.load(pals, select, read_only=read_only)
        if pals and not read_only:
            self.palette_selected.emit(self._pal_bar._active)
        self._set_validation()

    def _refresh_pal_count(self):
        if self._ba:
            self._pals.setText(f"Palettes : {len(self._ba.palettes)} / 16")

    def _persist_bg(self):
        if self._project and self._ba:
            with get_dispatcher().suspended():
                self._project.backgrounds.save(self._ba)

    def _open_catalog_popup(self, anchor, on_pick):
        if not self._project:
            return
        banks = list(self._project.palettes)
        if not banks:
            QMessageBox.information(self, "Catalogue vide",
                                    "Aucune palette dans le catalogue du projet.")
            return
        entries = [(b.name, b.name, bank_icon(b)) for b in banks]
        popup = ScriptPickerPopup(entries, _BG_COLOR, parent=self, new_label=None)

        def _picked(name: str):
            b = next((x for x in banks if x.name == name), None)
            if b:
                on_pick(b)

        popup.picked.connect(_picked)
        popup.show_below(anchor)

    def _on_pal_add(self):
        if not self._ba:
            return
        def _pick(bank):
            idx = self._ba.add_palette_colors(bank.colors)
            if idx < 0:
                QMessageBox.warning(self, "Limite atteinte",
                                    "Un fond ne peut avoir que 16 palettes.")
                return
            self._persist_bg()
            self._reload_palettes(select=idx)
            self._refresh_pal_count()
            self.palettes_changed.emit()
        self._open_catalog_popup(self._pal_bar.anchor(), _pick)

    def _on_pal_replace(self, idx: int):
        if not self._ba or not (0 <= idx < len(self._ba.palettes)):
            return
        def _pick(bank):
            self._ba.replace_palette(idx, bank.colors)
            self._persist_bg()
            self._reload_palettes(select=idx)
            self.palettes_changed.emit()
        self._open_catalog_popup(self._pal_bar.anchor(), _pick)

    def _on_pal_clear(self, idx: int):
        if not self._ba or not (0 <= idx < len(self._ba.palettes)):
            return
        self._ba.clear_palette(idx)
        self._persist_bg()
        self._reload_palettes(select=idx)
        self.palettes_changed.emit()

    def _on_pal_remove(self, idx: int):
        if not self._ba or not (0 <= idx < len(self._ba.palettes)) or len(self._ba.palettes) <= 1:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la palette {idx} ?\n"
            "Les tuiles qui l'utilisent repasseront sur la palette 0.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._ba.remove_palette(idx)
        self._persist_bg()
        self._reload_palettes(select=min(idx, len(self._ba.palettes) - 1))
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_restore(self):
        if not self._project or not self._ba:
            return
        if QMessageBox.question(
            self, "Restaurer l'original",
            "Réinitialiser ce fond comme au tout premier import ?\n"
            "Les palettes ajoutées et la peinture (inpainting) seront perdues.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        png = self._png_path()
        if not png or not png.exists():
            QMessageBox.warning(self, "Impossible",
                                "PNG source introuvable — restauration impossible.")
            return
        # Purge l'inpainting ; palettes/tileset/tilemap sont régénérés par la
        # recompression (hors-thread) depuis le PNG, dans le mode courant.
        self._ba.tile_palette_overrides = {}
        self.recompress_requested.emit(self._ba, png, self._cur_mode_token(), self._ba.dither)

    def _on_rename(self, new_name: str):
        if self._blocking or not self._ba or not self._project:
            return
        new_name = new_name.strip()
        if not new_name or new_name == self._ba.name:
            return
        if self._project.get_background(new_name):
            QMessageBox.warning(self, "Nom déjà utilisé",
                                f"Un fond nommé « {new_name} » existe déjà.")
            self._header.set_name(self._ba.name)
            return
        with get_dispatcher().suspended():
            self._project.rename_background(self._ba, new_name)
        self._header.set_name(self._ba.name)
        self.renamed.emit()

    def _png_path(self):
        img = self._ba.image_name() if self._ba else ""
        return (self._project.background_images_dir / img) if (self._project and img) else None

    def _on_method(self, _):
        if self._blocking or not self._ba or not self._project:
            return
        ap = self._png_path()
        if not ap or not ap.exists():
            return
        self._ba.compress_method = self._cb.currentData()
        self.recompress_requested.emit(self._ba, ap, self._cur_mode_token(), self._ba.dither)

    def _on_replace(self):
        if not self._project or not self._ba:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", "Images (*.png *.bmp)")
        if not path:
            return
        import shutil
        dst = self._project.background_images_dir / f"{self._ba.name}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        self._ba.source = dst.name
        # Ré-auto-détecter le mode pour la nouvelle image.
        from core.bg_compress import detect_bg_mode, detect_bpp
        try:
            if detect_bg_mode(dst) == "bitmap":
                token = "bitmap"
            else:
                token = "tiled8" if detect_bpp(dst) == 8 else "tiled4"
        except Exception:
            token = self._cur_mode_token()
        self.recompress_requested.emit(self._ba, dst, token, self._ba.dither)


# ── Écran ───────────────────────────────────────────────────────────────────

class BackgroundEditorScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project = None
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{_BG_COLOR};}}"
        )
        self._finder = BgFinderPanel()
        self._canvas = BgInpaintCanvas()
        self._props = BgPropertiesPanel()
        split.addWidget(self._finder); split.addWidget(self._canvas); split.addWidget(self._props)
        split.setSizes([240, 800, 300])
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setStretchFactor(2, 0)
        root.addWidget(split)

        self._finder.bg_selected.connect(self._on_selected)
        self._finder.import_asked.connect(self._on_import)
        self._props.changed.connect(self._canvas.reload)
        self._props.renamed.connect(self._on_renamed)
        # Peinture : palette active choisie dans l'inspecteur → canvas ;
        # mutation de la liste des palettes → re-render du canvas.
        self._props.palette_selected.connect(self._canvas.set_active_palette)
        self._props.palettes_changed.connect(self._canvas.reload)
        # (Re)compression demandée par l'inspecteur (algo / remplacer / restaurer)
        # → exécutée hors-thread par l'écran.
        self._props.recompress_requested.connect(self._on_recompress)

        # Compression hors-thread : jeton pour ignorer les résultats périmés
        # (l'utilisateur peut relancer avant la fin), + refs pour éviter le GC.
        self._compress_token = 0
        self._compress_tasks: set = set()

    def load_project(self, project):
        self._project = project
        self._finder.load_project(project)

    # ── Compression hors-thread ───────────────────────────────────

    def _compress_async(self, ba, png_path, mode, method, dither, then=None):
        """Compresse `png_path` dans un worker (mode token tiled4/tiled8/bitmap)
        puis applique le résultat à `ba` sur le thread UI. Non-bloquant."""
        if not self._project or not png_path or not Path(png_path).exists():
            return
        self._compress_token += 1
        token = self._compress_token
        self._canvas.set_busy(True)

        task = _CompressTask(token, Path(png_path), mode, method or ba.compress_method, dither)

        def _done(tok, name, c):
            self._compress_tasks.discard(task)
            if tok != self._compress_token:
                return  # résultat périmé (une compression plus récente a été lancée)
            from core.project import Project
            Project.apply_bg_compression(ba, name, c)
            with get_dispatcher().suspended():
                self._project.backgrounds.save(ba)
            self._canvas.set_busy(False)
            if then:
                then()

        def _failed(tok, msg):
            self._compress_tasks.discard(task)
            if tok != self._compress_token:
                return
            self._canvas.set_busy(False)
            QMessageBox.warning(self, "Compression échouée",
                                f"Impossible de compresser le fond :\n{msg}")

        task.signals.done.connect(_done)
        task.signals.failed.connect(_failed)
        self._compress_tasks.add(task)
        QThreadPool.globalInstance().start(task)

    def _on_recompress(self, ba, png_path, mode, dither):
        self._compress_async(
            ba, png_path, mode, ba.compress_method, dither,
            then=lambda: (self._props.load(ba, self._project), self._canvas.reload()))

    def _on_selected(self, ba):
        # Charger le canvas AVANT l'inspecteur : `props.load` émet palette_selected
        # (sélection de la palette active) que le canvas doit déjà connaître.
        self._canvas.load(self._project, ba)
        self._props.load(ba, self._project)

    def _on_renamed(self):
        # Renommage validé depuis l'en-tête de l'inspecteur : réaligner le finder
        # sur le nouveau nom (il émettra bg_selected → recharge preview + props).
        ba = self._props._ba
        if ba:
            self._finder.refresh(select=ba.name)

    def _on_import(self):
        if not self._project:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer un fond", "", "Images (*.png *.bmp)")
        if not path:
            return
        dst = self._project.import_asset(Path(path), "backgrounds")
        name = dst.stem
        ba = self._project.get_background(name)
        if ba is None:
            from core.project import BackgroundAsset
            ba = BackgroundAsset(name=name, source=dst.name)
            self._project.backgrounds.append(ba)
        # Auto-détection du mode : trop de tuiles (photo) → bitmap ; sinon
        # tuilé 4bpp/8bpp selon le nombre de couleurs.
        from core.bg_compress import detect_bg_mode, detect_bpp
        try:
            if detect_bg_mode(dst) == "bitmap":
                token = "bitmap"
            else:
                token = "tiled8" if detect_bpp(dst) == 8 else "tiled4"
        except Exception:
            token = "tiled4"
        # Sélectionner immédiatement (canvas vide + « Compression… ») puis
        # compresser hors-thread — l'éditeur n'est jamais bloqué.
        self._finder.refresh(select=ba.name)
        self._compress_async(
            ba, dst, token, ba.compress_method, ba.dither,
            then=lambda: self._on_selected(ba))
