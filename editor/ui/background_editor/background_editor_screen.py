"""ui/background_editor/background_editor_screen.py — écran Background Editor.

3 colonnes : finder (backgrounds) · canvas d'inpainting (BackgroundInpainting :
repeindre la palette par tuile 8×8, partagé entre scènes, cf. bg_inpaint_canvas) ·
inspecteur (dimensions, budget tuiles, liste des palettes éditables, algo de
compression). La compression est non-destructive (cf. core/bg_import) — le PNG
n'est jamais modifié, tout vit en métadonnées dans le .json du BackgroundAsset.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QListWidget,
    QListWidgetItem, QFileDialog, QFrame,
    QMenu, QMessageBox, QAbstractItemView, QPushButton, QGridLayout, QCheckBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, QObject, QRunnable, QThreadPool, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W, FinderSection, AssetHeaderBar
from ui.common.icons import COLOR_BACKGROUND
from ui.common.palette_slot_grid import PaletteSlotGridAsset
from ui.common.asset_palette_view import background_palette_view
from core.project import PaletteBank
from core.command_dispatcher import get_dispatcher
from core.history import get_history, DeleteResourceCmd
from core.bg_import import bg_fits_vram
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
# La compression (bg_import) peut prendre plusieurs secondes sur un grand fond
# ou une photo : on la lance dans un worker du QThreadPool pour ne JAMAIS geler
# l'éditeur. Le worker calcule le dict de compression ; le thread UI l'applique
# à l'asset (Project.apply_bg_encoding) puis rafraîchit.

class _CompressSignals(QObject):
    done   = pyqtSignal(int, str, dict)   # token, source_name, résultat
    failed = pyqtSignal(int, str)          # token, message


class _EncodeTask(QRunnable):
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
            from core.bg_import import (
                encode_background, encode_background_8bpp, encode_background_bitmap,
            )
            if self._mode in ("bitmap", "bitmap16"):
                # bitmap16 = vrai 16bpp direct (détecté), pas encore implémenté :
                # repli interim sur le Mode 4 paletté (quantif 256). cf. detect_import_mode.
                c = encode_background_bitmap(self._png, dither=self._dither)
            elif self._mode == "tiled8":
                c = encode_background_8bpp(self._png, dither=self._dither)
            else:
                c = encode_background(self._png, method=self._method)
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
        png = (self._project.background_images_dir / ba.asset) if ba.asset else None
        with get_dispatcher().suspended():
            if png and png.exists():
                png.unlink()
        get_history().push(DeleteResourceCmd(
            self._project.backgrounds, ba, lambda: self.refresh()))


# ── Propriétés (droite) ─────────────────────────────────────────────────────

class BgPropertiesPanel(QWidget):
    changed = pyqtSignal()          # compression recalculée → re-render du canvas
    renamed = pyqtSignal()          # fond renommé depuis l'en-tête → rafraîchir le finder
    palettes_changed = pyqtSignal()     # liste des palettes mutée → re-render du canvas
    recompress_requested = pyqtSignal(object, object, str, bool)  # (ba, png, mode_token, dither) → hors-thread
    overlays_changed = pyqtSignal(list, list)  # (info_lines, warning_lines) → overlays du canvas

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

        # ── MODE COULEUR : deux axes ORTHOGONAUX. Layout (tuilé/bitmap) ×
        #    profondeur (4/8/16 bpp) ; certaines combinaisons n'existent pas sur
        #    GBA → boutons profondeur filtrés selon le layout (cf. _refresh_mode_buttons).
        #    Changer d'axe recompresse le fond (hors-thread).
        lay_row = QHBoxLayout(); lay_row.setContentsMargins(0, 2, 0, 0); lay_row.setSpacing(6)
        lay_row.addWidget(self._axis_label("LAYOUT"))
        self._btn_tiled = self._mode_btn("Tuilé", "Fond tuilé (Mode 0) — tileset + tilemap, scroll, inpainting")
        self._btn_bitmap = self._mode_btn("Bitmap", "Bitmap plein écran ≤240×160, sans tuiles (photos / écrans-titre)")
        self._btn_tiled.clicked.connect(lambda: self._set_layout("tiled"))
        self._btn_bitmap.clicked.connect(lambda: self._set_layout("bitmap"))
        lay_row.addWidget(self._btn_tiled, 1); lay_row.addWidget(self._btn_bitmap, 1)
        root.addLayout(lay_row)

        dep_row = QHBoxLayout(); dep_row.setContentsMargins(0, 2, 0, 2); dep_row.setSpacing(6)
        dep_row.addWidget(self._axis_label("PROFONDEUR"))
        self._d4 = self._mode_btn("4bpp", "16 couleurs × 16 palettes · inpainting (pixel-art) — tuilé uniquement")
        self._d8 = self._mode_btn("8bpp", "256 couleurs, une palette (pixel-art riche / bitmap Mode 4)")
        self._d16 = self._mode_btn("16bpp", "Couleur directe 15-bit (photos true-color) — à venir, repli Mode 4")
        self._d4.clicked.connect(lambda: self._set_depth(4))
        self._d8.clicked.connect(lambda: self._set_depth(8))
        self._d16.clicked.connect(lambda: self._set_depth(16))
        dep_row.addWidget(self._d4, 1); dep_row.addWidget(self._d8, 1); dep_row.addWidget(self._d16, 1)
        root.addLayout(dep_row)
        self._chk_dither = QCheckBox("Dithering")
        self._chk_dither.setFont(QFont(T.MONO, T.SM))
        self._chk_dither.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_dither.toggled.connect(self._on_dither_toggled)
        root.addWidget(self._chk_dither)

        # NB : les infos read-only (dimensions, origine palette, tuiles/palettes) et
        # les alertes de validation NON-BLOQUANTES ne vivent plus dans l'inspecteur —
        # elles sont poussées via `overlays_changed` sur des overlays du canvas
        # (infos bas-gauche, warnings haut-droite). cf. _emit_overlays / _info_lines /
        # _validation_lines. Le PNG source n'est jamais modifié : ces messages
        # décrivent seulement la représentation GBA.
        W.separator(root)

        # ── PALETTES : grille unifiée (modèle Scene Inspector). Palettes dérivées
        #    du PNG grisées + overridables (clic = pointer une banque du catalogue,
        #    clic droit = restaurer l'origine) ; « + » ajoute une palette du
        #    catalogue (éditable, clic = remplacer, clic droit = retirer). La
        #    palette active de PEINTURE se choisit dans la bande en haut du canvas.
        W.separator(root); W.section("PALETTES", root)
        self._pal_grid = PaletteSlotGridAsset(_BG_COLOR, override_catalog=True)
        self._pal_grid.scene_add.connect(self._on_pal_add)
        self._pal_grid.scene_replace.connect(self._on_pal_replace)
        self._pal_grid.scene_remove.connect(self._on_pal_remove)
        self._pal_grid.asset_override.connect(self._on_pal_override)
        self._pal_grid.asset_restore.connect(self._on_pal_restore)
        root.addWidget(self._pal_grid)

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

        # ── EXTRACT PALETTE — ferré en bas de l'inspecteur. Promeut les
        #    sous-palettes déduites du PNG en PaletteBank partagées du catalogue
        #    (visibles/éditables depuis le Palette Editor) et les assigne à ce fond.
        self._btn_extract = QPushButton("⤓  EXTRACT PALETTE")
        self._btn_extract.setToolTip(
            "Promeut les palettes déduites du PNG en palettes partagées du "
            "catalogue (visibles et éditables depuis le Palette Editor). Les "
            "palettes créées sont assignées à ce fond.")
        self._btn_extract.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        self._btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_extract.setFixedHeight(38)
        self._btn_extract.setStyleSheet(
            f"QPushButton{{color:{_BG_COLOR}; background:transparent;"
            f"border:2px solid {_BG_COLOR}; border-radius:5px; letter-spacing:1px;"
            f"padding:4px 10px;}}"
            f"QPushButton:hover{{color:{C.BG_DEEP}; background:{_BG_COLOR};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:transparent;}}"
        )
        self._btn_extract.clicked.connect(self._on_extract_palette)
        root.addWidget(self._btn_extract)

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

    def _axis_label(self, text: str) -> QLabel:
        l = QLabel(text); l.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        l.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        l.setFixedWidth(72)
        return l

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
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:{C.BG_INPUT};}}"
        )
        return b

    # ── Mode couleur : 2 axes (layout × profondeur) ───────────────
    #    Combinaisons valides GBA : tuilé→{4,8}, bitmap→{8,16}. Le 16bpp direct
    #    n'est pas encore implémenté (repli Mode 4) → bouton visible mais désactivé.

    def _cur_axes(self) -> tuple[str, int]:
        """(layout, profondeur) courant de l'asset. Le bitmap est du Mode 4 (8bpp) :
        le 16bpp direct n'étant pas persisté, on le lit toujours comme 8."""
        if not self._ba:
            return ("tiled", 4)
        if self._ba.mode == "bitmap":
            return ("bitmap", 8)
        return ("tiled", 8 if self._ba.bpp == 8 else 4)

    @staticmethod
    def _axes_token(layout: str, depth: int) -> str:
        if layout == "tiled":
            return "tiled8" if depth == 8 else "tiled4"
        return "bitmap16" if depth == 16 else "bitmap"

    def _cur_mode_token(self) -> str:
        return self._axes_token(*self._cur_axes())

    def _refresh_mode_buttons(self):
        layout, depth = self._cur_axes()
        tok = self._axes_token(layout, depth)
        tiled = layout == "tiled"
        base = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        self._blocking = True
        self._btn_tiled.setChecked(tiled)
        self._btn_bitmap.setChecked(not tiled)
        self._d4.setChecked(tiled and depth == 4)
        self._d8.setChecked(depth == 8)
        self._d16.setChecked(not tiled and depth == 16)
        # Filtre des profondeurs valides selon le layout.
        self._btn_tiled.setEnabled(base); self._btn_bitmap.setEnabled(base)
        self._d4.setEnabled(base and tiled)          # 4bpp : tuilé uniquement
        self._d8.setEnabled(base)                    # 8bpp : toujours
        self._d16.setEnabled(False)                  # 16bpp direct : à venir
        self._chk_dither.setVisible(tok != "tiled4")
        self._chk_dither.setChecked(bool(self._ba and self._ba.dither))
        self._blocking = False

    def _apply_axes(self, layout: str, depth: int):
        """Recompresse vers (layout, depth) si le token change ; sinon réaligne l'UI."""
        if self._blocking or not self._ba or not self._project:
            self._refresh_mode_buttons(); return
        token = self._axes_token(layout, depth)
        if token == self._cur_mode_token():
            self._refresh_mode_buttons(); return
        ap = self._png_path()
        if not ap or not ap.exists():
            self._refresh_mode_buttons(); return
        self.recompress_requested.emit(self._ba, ap, token, self._ba.dither)

    def _set_layout(self, layout: str):
        # Bascule d'axe : on snappe la profondeur sur une valeur valide du layout
        # cible (tuilé→{4,8}, bitmap→{8,16}), en gardant l'actuelle si possible.
        _, depth = self._cur_axes()
        valid = (4, 8) if layout == "tiled" else (8, 16)
        self._apply_axes(layout, depth if depth in valid else 8)

    def _set_depth(self, depth: int):
        layout, _ = self._cur_axes()
        self._apply_axes(layout, depth)

    def _on_dither_toggled(self, on: bool):
        tok = self._cur_mode_token()
        if self._blocking or not self._ba or tok == "tiled4":
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
        self._blocking = False
        self._refresh_mode_buttons()
        self._reload_palettes()   # émet aussi les overlays (infos + warnings)

    def _emit_overlays(self):
        """Pousse les infos read-only + les warnings vers les overlays du canvas."""
        ba = self._ba
        info = self._info_lines(ba) if ba else []
        warns = self._validation_lines(ba) if ba else []
        self.overlays_changed.emit(info, warns)

    def _info_lines(self, ba) -> list:
        """Lignes descriptives read-only (dims, origine palette, tuiles, palettes)
        pour l'overlay bas-gauche du canvas."""
        if not ba or not (ba.tileset or ba.bitmap):
            return []
        lines: list = []
        if ba.mode == "bitmap" and ba.bitmap:
            lines.append(f"{ba.out_w}×{ba.out_h} px  ·  bitmap ≤240×160")
        elif ba.tileset:
            lines.append(f"{ba.tiles_w*8}×{ba.tiles_h*8} px  ·  {ba.tiles_w}×{ba.tiles_h} tuiles")
        indexed, ncol, capped = self._source_info(ba)
        origin = "indexé (palette d'origine)" if indexed else "déduit"
        ncol_s = "256+" if capped else str(ncol)
        lines.append(f"Source : {origin} · {ncol_s} couleurs")
        if ba.mode == "bitmap":
            lines.append("Mode 4 — plein écran, sans tuiles")
            lines.append("Palette : 256 couleurs (1)")
        else:
            budget = 256 if ba.bpp == 8 else 512
            lines.append(f"Tuiles uniques : {len(ba.tileset)} / {budget}  ({ba.bpp}bpp)")
            lines.append("Palette : 256 couleurs (1)" if ba.bpp == 8
                         else f"Palettes : {len(ba.palettes)} / 16")
        return lines

    def _source_info(self, ba) -> tuple[bool, int, bool]:
        """(indexed, n_colors, capped) du PNG source — mis en cache dans
        `ba.diagnostics` pour ne pas relire l'image à chaque sélection."""
        d = ba.diagnostics if isinstance(ba.diagnostics, dict) else {}
        if "src_indexed" in d and "src_colors" in d:
            return d["src_indexed"], d["src_colors"], bool(d.get("src_capped"))
        ap = self._png_path()
        if not ap or not ap.exists():
            return False, 0, False
        try:
            from core.bg_import import source_palette_info
            indexed, ncol, capped = source_palette_info(ap)
        except Exception:
            return False, 0, False
        if not isinstance(ba.diagnostics, dict):
            ba.diagnostics = {}
        ba.diagnostics.update(src_indexed=indexed, src_colors=ncol, src_capped=capped)
        return indexed, ncol, capped

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
                from core.bg_import import analyze_background_source
                ba.diagnostics = analyze_background_source(ap, method=ba.quantize_method)
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

    # ── Section PALETTES ──────────────────────────────────────────

    def _reload_palettes(self, select: int = 0):
        # Grille unifiée : palettes dérivées grisées/overridables + palettes
        # ajoutées du catalogue. La palette de PEINTURE active vit désormais dans
        # la bande en haut du canvas (rebâtie via palettes_changed → canvas.reload).
        # `select` est conservé pour la compat d'appel mais n'est plus consommé ici.
        read_only = bool(self._ba and (self._ba.mode == "bitmap" or self._ba.bpp == 8))
        view = background_palette_view(self._ba, read_only=read_only)
        catalog = list(self._project.palettes) if self._project else []
        self._pal_grid.load(view, catalog)
        self._btn_extract.setEnabled(bool(self._ba and self._ba.palettes))
        self._emit_overlays()

    def _refresh_pal_count(self):
        self._emit_overlays()

    def _persist_bg(self):
        if self._project and self._ba:
            with get_dispatcher().suspended():
                self._project.backgrounds.save(self._ba)

    def _on_pal_add(self, name: str):
        """« + » : ajoute une palette du catalogue (banque `name`)."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        idx = self._ba.add_palette_colors(bank.colors)
        if idx < 0:
            QMessageBox.warning(self, "Limite atteinte",
                                "Un fond ne peut avoir que 16 palettes.")
            return
        self._persist_bg()
        self._reload_palettes()
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_pal_replace(self, idx: int, name: str):
        """Remplace une palette AJOUTÉE (index réel `idx`) par la banque `name`."""
        if not self._ba or not self._project or not (0 <= idx < len(self._ba.palettes)):
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        self._ba.replace_palette(idx, bank.colors)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_override(self, entry, name: str):
        """Override une palette DÉRIVÉE (grisée) par la banque catalogue `name` :
        ses couleurs effectives sont remplacées, l'origine PNG reste restaurable."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        self._ba.override_palette(entry.idx, name, bank.colors)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_restore(self, entry):
        """Restaure une palette dérivée overridée à ses couleurs PNG d'origine."""
        if not self._ba:
            return
        self._ba.restore_palette(entry.idx)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_remove(self, idx: int):
        """Retire une palette AJOUTÉE (index réel `idx`). Les tuiles qui la
        référencent retombent sur la palette 0."""
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
        self._reload_palettes()
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

    def _on_extract_palette(self):
        """Promeut les sous-palettes déduites (`ba.palettes`) en PaletteBank
        partagées du catalogue projet, sous un nom stable dérivé du fond. Les
        palettes créées deviennent visibles/éditables depuis le Palette Editor
        et restent celles utilisées par ce fond (elles EN sont l'origine — le
        rendu du fond est inchangé). Une ré-extraction (après recompression)
        met à jour les mêmes banques."""
        if not self._project or not self._ba:
            return
        ba = self._ba
        pals = [list(p) for p in ba.palettes]
        if not pals:
            QMessageBox.information(
                self, "Extraction impossible",
                "Ce fond n'a pas encore de palette à extraire "
                "(image non compressée ou illisible).")
            return
        # 256 couleurs (une banque unique) en 8bpp / bitmap ; 16 en 4bpp tuilé.
        size = 256 if (ba.mode == "bitmap" or ba.bpp == 8) else 16
        single = len(pals) == 1
        created: list[str] = []
        for i, cols in enumerate(pals):
            name = f"pal_{ba.name}" if single else f"pal_{ba.name}_{i}"
            existing = self._project.palettes.get(name)
            if existing:
                # Ré-extraction : on écrase les couleurs de la banque déjà générée
                # (action explicite, régénération attendue — cf. Sprite Editor).
                existing.colors = list(cols)
                existing.size = size
                bank = existing
            else:
                bank = PaletteBank(name=name, colors=list(cols), size=size)
            # Passe par le dispatcher : persistance (watcher suspendu) + événement
            # « palettes_changed » pour rafraîchir le Palette Editor / les finders.
            get_dispatcher().save_palette(bank)
            created.append(bank.name)
        noun = "palette" if single else "palettes"
        QMessageBox.information(
            self, "Palette extraite",
            f"{len(created)} {noun} ajoutée(s) au catalogue et assignée(s) à "
            f"« {ba.name} » :\n  " + "\n  ".join(created) + "\n\n"
            "Elles sont maintenant visibles et éditables depuis le Palette Editor.")

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
        self._ba.asset = dst.name
        # Ré-auto-détecter le mode pour la nouvelle image (pivot indexé/non-indexé).
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, "Import", d["warning"])
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
        # Mutation de la liste des palettes → re-render du canvas (sa bande de
        # peinture en tête se reconstruit alors depuis ba.palettes).
        self._props.palettes_changed.connect(self._canvas.reload)
        # Infos read-only + warnings → overlays du canvas (bas-gauche / haut-droite).
        self._props.overlays_changed.connect(self._canvas.set_overlays)
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

        task = _EncodeTask(token, Path(png_path), mode, method or ba.quantize_method, dither)

        def _done(tok, name, c):
            self._compress_tasks.discard(task)
            if tok != self._compress_token:
                return  # résultat périmé (une compression plus récente a été lancée)
            from core.project import Project
            Project.apply_bg_encoding(ba, name, c)
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
            ba, png_path, mode, ba.quantize_method, dither,
            then=lambda: (self._props.load(ba, self._project), self._canvas.reload()))

    def _on_selected(self, ba):
        # Charger le canvas AVANT l'inspecteur : le canvas bâtit sa bande de
        # peinture depuis `ba` (palette active de peinture) ; l'inspecteur suit.
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
            ba = BackgroundAsset(name=name, asset=dst.name)
            self._project.backgrounds.append(ba)
        # Auto-détection unifiée (pivot indexé/non-indexé) : profondeur ← couleurs,
        # layout tuilé/bitmap ← unicité des tuiles.
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, "Import", d["warning"])
        except Exception:
            token = "tiled4"
        # Sélectionner immédiatement (canvas vide + « Compression… ») puis
        # compresser hors-thread — l'éditeur n'est jamais bloqué.
        self._finder.refresh(select=ba.name)
        self._compress_async(
            ba, dst, token, ba.quantize_method, ba.dither,
            then=lambda: self._on_selected(ba))
