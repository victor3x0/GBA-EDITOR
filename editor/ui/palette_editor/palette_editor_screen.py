"""Palette Editor screen — catalogue illimité et unifié de palettes nommées.

Plus de distinction OBJ/BG dans le catalogue (2026-07-08) — une palette est
juste 16 couleurs, réutilisable pour les deux pools. C'est la scène qui
choisit jusqu'à 16 palettes actives par pool parmi ce catalogue (voir Scene
Inspector, carte "Palettes actives").
"""
import colorsys
import re
from typing import Optional

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QSplitter, QTreeWidget, QTreeWidgetItem, QAbstractItemView, QSlider, QSpinBox,
    QInputDialog, QMessageBox, QMenu, QLineEdit, QStyledItemDelegate,
    QFileDialog, QDialog, QComboBox, QDialogButtonBox, QToolButton,
)
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon, QGuiApplication
from PyQt6.QtCore import Qt, QSize, QEvent, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W

from core.project import Project, PaletteBank
from core.color_utils import (
    bgr555_to_rgb888, bgr555_components, components_to_bgr555, rgb888_to_bgr555,
)
from core.palette_presets import hsb_ramp_bgr555
from core.history import get_history, DeleteResourceCmd
from ui.common.palette_swatch import bank_icon as _bank_icon
from ui.palette_editor.color_wheel import ColorTriangleWheel

SPLITTER_STYLE = (
    f"QSplitter::handle{{background:{C.BORDER};}}"
    "QSplitter::handle:horizontal{width:3px;}"
    f"QSplitter::handle:hover{{background:{C.ACCENT_GRN};}}"
)

# Taille de cellule des swatches : grandes cases en 16 (4×4 qui remplit l'espace),
# compactes en 256 (16×16 = carte lisible).
SWATCH_CELL_16 = 56
SWATCH_CELL_256 = 32
SWATCH_GAP = 3


def _checker_icon(size: int, a: str = "#3a3a3a", b: str = "#262626", cells: int = 4) -> QIcon:
    """Icône damier (transparence) — même pixmap en mode Normal et Disabled pour
    que le slot index 0 (désactivé) ne soit pas grisé par Qt."""
    pm = QPixmap(size, size)
    p = QPainter(pm)
    step = max(2, size // cells)
    for yy in range(0, size, step):
        for xx in range(0, size, step):
            on = ((xx // step) + (yy // step)) % 2 == 0
            p.fillRect(xx, yy, step, step, QColor(a if on else b))
    p.end()
    ic = QIcon()
    ic.addPixmap(pm, QIcon.Mode.Normal)
    ic.addPixmap(pm, QIcon.Mode.Disabled)
    return ic


_HEX6 = re.compile(r"#?([0-9a-fA-F]{6})")


def _parse_palette_file(path: Path) -> list[tuple[int, int, int]]:
    """Extrait une liste de couleurs RGB888 depuis un .gpl (GIMP), .pal (JASC)
    ou une liste hexadécimale/RVB. Tolérant : ignore entêtes et commentaires."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    head = lines[0].strip().lower() if lines else ""
    out: list[tuple[int, int, int]] = []
    if head.startswith("jasc-pal"):
        for ln in lines[3:]:
            nums = ln.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    elif head.startswith("gimp palette"):
        for ln in lines[1:]:
            s = ln.strip()
            if not s or s.startswith("#") or ":" in s:   # commentaires / Name:/Columns:
                continue
            nums = s.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    else:                                                # liste hex ou "R G B"
        for ln in lines:
            m = _HEX6.findall(ln)
            if m:
                out += [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in m]
                continue
            nums = ln.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    return out


def _serialize_palette(name: str, rgb: list[tuple[int, int, int]], fmt: str) -> str:
    """Sérialise `rgb` (RGB888) au format 'gpl', 'pal' (JASC) ou 'hex'."""
    if fmt == "pal":
        return "\n".join(["JASC-PAL", "0100", str(len(rgb))]
                         + [f"{r} {g} {b}" for r, g, b in rgb]) + "\n"
    if fmt == "hex":
        return "\n".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in rgb) + "\n"
    return "\n".join(["GIMP Palette", f"Name: {name}", "Columns: 16", "#"]
                     + [f"{r:>3} {g:>3} {b:>3}\tindex {i}"
                        for i, (r, g, b) in enumerate(rgb)]) + "\n"


def _rgb01(rgb01) -> str:
    """(r,g,b) 0-1 -> 'rgb(R,G,B)' 0-255 pour un stop de gradient QSS."""
    r, g, b = rgb01
    return f"rgb({round(r * 255)},{round(g * 255)},{round(b * 255)})"


def _grad_slider_qss(stops: list[str]) -> str:
    """Feuille de style d'un QSlider dont la rainure affiche le gradient
    `stops` (chaînes 'rgb(...)') — simule la couleur résultante le long du
    slider. Poignée sobre lisible sur n'importe quel fond."""
    n = len(stops)
    grad_stops = ", ".join(
        f"stop:{(i / (n - 1)):.4f} {c}" for i, c in enumerate(stops)
    )
    return (
        "QSlider::groove:horizontal{height:12px;border-radius:6px;"
        f"border:1px solid {C.BORDER_MID};"
        f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,{grad_stops});}}"
        "QSlider::handle:horizontal{width:8px;height:20px;margin:-5px 0;"
        "border-radius:3px;background:#f0f0f0;border:1px solid #101010;}"
        "QSlider::handle:horizontal:hover{background:#ffffff;}"
    )


class _PaletteNameDelegate(QStyledItemDelegate):
    """Le libellé du finder affiche « nom  (16/256) », mais l'édition en place ne
    porte que sur le nom NU (stocké en UserRole) — le suffixe de taille ne pollue
    jamais le champ de renommage."""

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.UserRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


# ──────────────────────────────────────────────────────────────────
#  PaletteFinderPanel
# ──────────────────────────────────────────────────────────────────
class PaletteFinderPanel(QWidget):
    """Panneau gauche : liste unique du catalogue projet (ajout/suppression/
    renommage), même modèle que SoundFinderPanel — partagé OBJ/BG."""

    bank_selected = pyqtSignal(str)   # nom
    bank_deleted  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        finder_hdr = QFrame()
        finder_hdr.setFixedHeight(20)
        finder_hdr.setStyleSheet(f"background:{C.BG_BASE}; border-bottom:1px solid {C.BORDER_DARK};")
        fl = QHBoxLayout(finder_hdr)
        fl.setContentsMargins(8, 0, 0, 0)
        finder_lbl = QLabel("PALETTE FINDER")
        finder_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        finder_lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; letter-spacing:1px;")
        fl.addWidget(finder_lbl)
        root.addWidget(finder_hdr)

        root.addWidget(self._make_section("PALETTES", C.ACCENT_GRN))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFont(QFont(T.MONO, T.MD))
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:#161616;color:{C.TEXT_NORM};border:none;}}"
            "QTreeWidget::item:selected{background:#1a2a3a;}"
            "QTreeWidget::item:hover{background:#202020;}"
        )
        self._tree.setItemDelegate(_PaletteNameDelegate(self._tree))
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.currentItemChanged.connect(self._on_selected)
        self._tree.itemChanged.connect(self._on_item_text_changed)
        self._tree.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._tree, 1)

    def _make_section(self, title: str, color: str) -> QFrame:
        f = QFrame()
        f.setFixedHeight(28)
        f.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(f)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(2)
        lbl = QLabel(title)
        lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{color};")
        hl.addWidget(lbl, 1)

        self._btn_add = W.btn_add("Ajouter une palette (créer / importer)")
        self._btn_add.clicked.connect(self._on_add_menu)
        hl.addWidget(self._btn_add)

        btn_del = W.btn_danger("Supprimer la palette sélectionnée")
        btn_del.clicked.connect(self._del)
        hl.addWidget(btn_del)

        return f

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self.refresh()

    def refresh(self):
        if not self._project:
            return
        self._tree.blockSignals(True)
        self._tree.clear()
        for bank in self._project.palettes:
            item = QTreeWidgetItem()
            # Libellé « nom  (16/256) » ; le nom NU vit en UserRole (clé de lookup
            # + source de l'édition via _PaletteNameDelegate).
            item.setText(0, f"{bank.name}  ({bank.size})")
            item.setIcon(0, _bank_icon(bank))
            item.setData(0, Qt.ItemDataRole.UserRole, bank.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)

    def select_bank(self, name: str):
        """Sélectionne la banque `name` dans l'arbre si elle existe (émet
        bank_selected via currentItemChanged)."""
        for i in range(self._tree.topLevelItemCount()):
            it = self._tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == name:
                self._tree.setCurrentItem(it)
                return

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, current: Optional[QTreeWidgetItem], _prev):
        if not current:
            return
        self.bank_selected.emit(current.data(0, Qt.ItemDataRole.UserRole))

    # ── Renommage en place ────────────────────────────────────────

    def _on_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        old_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_name:
            return
        bank = self._project.palettes.get(old_name)
        if not bank:
            return

        def _set_display(name: str):
            self._tree.blockSignals(True)
            item.setText(0, f"{name}  ({bank.size})")
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            self._tree.blockSignals(False)

        # Le délégué a écrit le nom nu ; on retire défensivement un suffixe
        # « (16)/(256) » résiduel au cas où l'édition l'aurait laissé.
        raw = item.text(0).strip()
        new_name = re.sub(r"\s*\(\s*(?:16|256)\s*\)\s*$", "", raw).strip()
        if not new_name or new_name == old_name or self._project.palettes.get(new_name):
            _set_display(old_name)   # invalide -> restaure nom + suffixe
            return
        self._project.palettes.rename(bank, new_name)
        _set_display(new_name)
        self.bank_selected.emit(new_name)

    # ── Menu contextuel ──────────────────────────────────────────────

    def _on_ctx_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        self._tree.setCurrentItem(item)
        menu = QMenu(self)
        delete_a = menu.addAction("Supprimer")
        if menu.exec(self._tree.viewport().mapToGlobal(pos)) == delete_a:
            self._del()

    # ── Ajout (créer / importer) / suppression ────────────────────

    def _on_add_menu(self):
        """Le « + » propose deux entrées : créer une palette vide, ou en importer
        une depuis un fichier (.gpl / .pal / liste hex)."""
        menu = QMenu(self)
        a_new = menu.addAction("Créer une palette vide")
        a_imp = menu.addAction("Importer…")
        act = menu.exec(self._btn_add.mapToGlobal(self._btn_add.rect().bottomLeft()))
        if act == a_new:
            self._add()
        elif act == a_imp:
            self._import()

    def _unique_name(self, base: str) -> str:
        base = base.strip() or "Palette"
        if not self._project.palettes.get(base):
            return base
        i = 2
        while self._project.palettes.get(f"{base} {i}"):
            i += 1
        return f"{base} {i}"

    def _add(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(self, "Nouvelle palette", "Nom :")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if self._project.palettes.get(name):
            return
        kind, ok = QInputDialog.getItem(
            self, "Type de palette", "Taille :",
            ["16 couleurs (4bpp)", "256 couleurs (8bpp)"], 0, False)
        if not ok:
            return
        size = 256 if kind.startswith("256") else 16
        bank = PaletteBank(name=name, colors=hsb_ramp_bgr555(0, 0, steps=size), size=size)
        self._project.palettes.append(bank)
        self._project.palettes.save(bank)
        self.refresh()
        last = self._tree.topLevelItem(self._tree.topLevelItemCount() - 1)
        if last:
            self._tree.setCurrentItem(last)

    def _import(self):
        """Crée une NOUVELLE palette depuis un fichier (nom = nom de fichier,
        taille déduite du nombre de couleurs : ≤16 → 16, sinon 256)."""
        if not self._project:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer une palette", "",
            "Palettes (*.gpl *.pal *.txt *.hex);;Tous les fichiers (*)")
        if not path:
            return
        try:
            colors = _parse_palette_file(Path(path))
        except OSError as e:
            QMessageBox.warning(self, "Importer", f"Fichier illisible : {e}")
            return
        if not colors:
            QMessageBox.warning(self, "Importer", "Aucune couleur reconnue dans ce fichier.")
            return
        size = 256 if len(colors) > 16 else 16
        bgr = [rgb888_to_bgr555(*c) for c in colors[:size]]
        bgr += [0] * (size - len(bgr))                # complète si le fichier est court
        name = self._unique_name(Path(path).stem)
        bank = PaletteBank(name=name, colors=bgr, size=size)
        self._project.palettes.append(bank)
        self._project.palettes.save(bank)
        self.refresh()
        self.select_bank(name)

    def _del(self):
        item = self._tree.currentItem()
        if not item:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        bank = self._project.palettes.get(name)
        if not bank:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la palette « {bank.name} » ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _refresh():
            self.refresh()
            self.bank_deleted.emit()

        get_history().push(DeleteResourceCmd(self._project.palettes, bank, _refresh))


# ──────────────────────────────────────────────────────────────────
#  PaletteEditorScreen
# ──────────────────────────────────────────────────────────────────
class PaletteEditorScreen(QWidget):
    """Écran complet Palette Editor : finder unifié + édition RGB de la banque active."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._bank_name: Optional[str] = None
        self._active_index: Optional[int] = None    # slot édité (curseur)
        self._anchor_index: Optional[int] = None     # ancre pour la plage shift+clic
        self._sel_range: Optional[tuple[int, int]] = None   # (lo, hi) inclus, ou None
        self._selected_set: set[int] = set()         # indices actuellement surlignés
        self._active_drawn: Optional[int] = None      # case au marqueur blanc actuel
        self._dragging = False                       # sélection au cliqué-glissé en cours
        self._drag_grab: Optional[QPushButton] = None
        self._blocking = False
        self.setStyleSheet("background:#181818;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel("PALETTE EDITOR")
        lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.ACCENT_GRN};")
        hl.addWidget(lbl)
        hl.addStretch()
        root.addWidget(hdr)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(SPLITTER_STYLE)
        root.addWidget(split, 1)

        self._finder = PaletteFinderPanel()
        self._finder.bank_selected.connect(self._on_bank_selected)
        self._finder.bank_deleted.connect(self._on_bank_deleted)
        split.addWidget(self._finder)

        # Zone centrale = UN seul agencement, identique en 16 et 256 couleurs :
        # colonne centrale (entête + grille de swatches + zone aperçu) et carte
        # « inspecteur de couleur » ancrée à droite. Plus de double _relayout.
        self._center = QWidget()
        self._center.setStyleSheet(f"background:{C.BG_PANEL};")
        cl = QHBoxLayout(self._center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        _CENTER = Qt.AlignmentFlag.AlignHCenter

        # ── Colonne centrale ──────────────────────────────────────────
        swatch_col = QWidget()
        scl = QVBoxLayout(swatch_col)
        scl.setContentsMargins(0, 0, 0, 0)
        scl.setSpacing(0)

        center_hdr = QFrame()
        center_hdr.setFixedHeight(32)
        center_hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        chl = QHBoxLayout(center_hdr)
        chl.setContentsMargins(14, 0, 8, 0)
        chl.setSpacing(10)
        self._title = QLabel("")
        self._title.setFont(QFont(T.MONO, T.LG, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};")
        chl.addWidget(self._title)
        self._size_lbl = QLabel("")
        self._size_lbl.setFont(QFont(T.MONO, T.SM))
        self._size_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        chl.addWidget(self._size_lbl)
        chl.addStretch()

        # Barre d'actions sur la palette (point D) : import/export interop +
        # génération de rampe (reste dans les index existants, ne réordonne pas).
        self._tools = QWidget()
        tl = QHBoxLayout(self._tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        self._btn_export = W.btn_ghost("Exporter")
        self._btn_export.setToolTip("Exporter en .gpl (GIMP) / .pal (JASC) / liste hex")
        self._btn_export.clicked.connect(self._export_palette)
        tl.addWidget(self._btn_export)
        chl.addWidget(self._tools)
        scl.addWidget(center_hdr)

        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 16, 16, 16)
        il.setSpacing(14)

        self._empty_lbl = QLabel("Sélectionne une palette dans le panneau de gauche")
        self._empty_lbl.setFont(QFont(T.MONO, T.MD))
        self._empty_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Grille de swatches CENTRÉE verticalement (ressorts haut/bas). Conteneur
        # focusable pour la navigation clavier (flèches, Ctrl+C/V).
        self._swatch_container = QWidget()
        self._swatch_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._swatch_container.installEventFilter(self)
        self._swatch_grid = QGridLayout(self._swatch_container)
        self._swatch_grid.setContentsMargins(0, 0, 0, 0)
        self._swatch_grid.setSpacing(SWATCH_GAP)
        self._swatch_btns: list[QPushButton] = []

        il.addStretch(1)
        il.addWidget(self._empty_lbl, 0, _CENTER)
        il.addWidget(self._swatch_container, 0, _CENTER)
        il.addStretch(1)

        scl.addWidget(inner, 1)
        cl.addWidget(swatch_col, 1)

        # ── Colonne droite : carte « inspecteur de couleur » ancrée ──
        self._editor_card = QWidget()
        self._editor_card.setFixedWidth(300)
        self._editor_card.setStyleSheet(f"background:{C.BG_RAISED}; border-left:1px solid {C.BORDER};")
        ecl = QVBoxLayout(self._editor_card)
        ecl.setContentsMargins(0, 0, 0, 0)
        ecl.setSpacing(0)

        card_hdr = QFrame()
        card_hdr.setFixedHeight(32)
        card_hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        chl2 = QHBoxLayout(card_hdr)
        chl2.setContentsMargins(12, 0, 12, 0)
        self._color_hdr = QLabel("COULEUR")
        self._color_hdr.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._color_hdr.setStyleSheet(f"color:{C.ACCENT_GRN}; letter-spacing:1px;")
        chl2.addWidget(self._color_hdr)
        ecl.addWidget(card_hdr)

        self._editor = QWidget()
        el = QVBoxLayout(self._editor)
        el.setContentsMargins(12, 12, 12, 12)
        el.setSpacing(10)

        self._preview = QLabel()
        self._preview.setFixedSize(96, 96)
        self._preview.setStyleSheet(f"border:1px solid {C.BORDER_MID}; border-radius:6px;")
        el.addWidget(self._preview, alignment=_CENTER)

        # Formulaire HEX (#RRGGBB, quantifié 5 bits/canal) + valeur BGR555 native
        # GBA (ce qui finit réellement en ROM). Le point « snap » signale qu'un
        # hex saisi a dû être ajusté à la grille 15 bits.
        info = QGridLayout()
        info.setHorizontalSpacing(8)
        info.setVerticalSpacing(6)
        info.setContentsMargins(0, 0, 0, 0)

        hex_lab = QLabel("HEX")
        hex_lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        hex_lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        info.addWidget(hex_lab, 0, 0)
        self._hex = QLineEdit()
        self._hex.setFixedWidth(100)
        self._hex.setMaxLength(7)
        self._hex.setFont(QFont(T.MONO, T.MD))
        self._hex.setStyleSheet(
            f"QLineEdit{{background:{C.BG_INPUT};color:{C.TEXT_HI};"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;padding:3px 6px;}}"
            f"QLineEdit:focus{{border-color:{C.ACCENT_GRN};}}"
        )
        self._hex.editingFinished.connect(self._on_hex_changed)
        info.addWidget(self._hex, 0, 1)

        btn_copy = QToolButton()
        btn_copy.setText("⧉")
        btn_copy.setFixedSize(24, 24)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setToolTip("Copier le HEX (Ctrl+C)")
        btn_copy.setStyleSheet(
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;}}"
            f"QToolButton:hover{{color:{C.ACCENT_GRN};}}"
        )
        btn_copy.clicked.connect(self._copy_color)
        info.addWidget(btn_copy, 0, 2)

        bgr_lab = QLabel("BGR555")
        bgr_lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        bgr_lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        info.addWidget(bgr_lab, 1, 0)
        self._bgr = QLabel("—")
        self._bgr.setFont(QFont(T.MONO, T.MD))
        self._bgr.setStyleSheet(f"color:{C.TEXT_NORM};")
        info.addWidget(self._bgr, 1, 1)
        self._snap = QLabel("")
        self._snap.setFont(QFont(T.MONO, T.SM))
        self._snap.setStyleSheet(f"color:{C.AXIS_X};")
        self._snap.setToolTip("Couleur ajustée à la grille 15 bits du GBA (5 bits/canal)")
        info.addWidget(self._snap, 1, 2)
        info.setColumnStretch(2, 1)
        el.addLayout(info)

        # Roue chromatique (anneau teinte + triangle S/L) — dans la carte, sous
        # le preview/hex. Synchronisée avec sliders/hex via _load_channels.
        self._wheel = ColorTriangleWheel()
        self._wheel.color_changed.connect(self._on_wheel_changed)
        el.addWidget(self._wheel, alignment=_CENTER)

        # Sliders RGB (0-31, natif GBA) + HSB (dérivé), rainure colorée
        self._sliders: dict[str, QSlider] = {}
        self._spins: dict[str, QSpinBox] = {}
        self._hsb_sliders: dict[str, QSlider] = {}
        self._hsb_spins: dict[str, QSpinBox] = {}

        for ch, chan_color in (("r", C.AXIS_X), ("g", C.ACCENT_GRN), ("b", C.AXIS_Y)):
            sl, sp = self._make_channel_row(
                el, ch.upper(), chan_color, 0, 31,
                lambda v, ch=ch: self._on_rgb_changed(ch, v),
            )
            self._sliders[ch] = sl
            self._spins[ch] = sp

        # ── TSL (dérivé) — repliable : HEX + RGB suffisent le plus souvent ──
        self._hsb_toggle = QPushButton("▸  TSL")
        self._hsb_toggle.setCheckable(True)
        self._hsb_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hsb_toggle.setStyleSheet(
            f"QPushButton{{text-align:left;color:{C.TEXT_DIM};background:transparent;"
            f"border:none;border-top:1px solid {C.BORDER_DARK};padding:6px 0 2px 0;}}"
            f"QPushButton:hover{{color:{C.TEXT_NORM};}}"
            f"QPushButton:checked{{color:{C.ACCENT_GRN};}}"
        )
        self._hsb_toggle.clicked.connect(self._toggle_hsb)
        el.addWidget(self._hsb_toggle)

        self._hsb_box = QWidget()
        hb = QVBoxLayout(self._hsb_box)
        hb.setContentsMargins(0, 4, 0, 0)
        hb.setSpacing(10)
        for ch, label, maxv, chan_color in (
            ("h", "H", 359, C.TEXT_DIM), ("s", "S", 100, C.TEXT_DIM), ("v", "L", 100, C.TEXT_DIM),
        ):
            sl, sp = self._make_channel_row(
                hb, label, chan_color, 0, maxv,
                lambda v, ch=ch: self._on_hsb_changed(ch, v),
            )
            self._hsb_sliders[ch] = sl
            self._hsb_spins[ch] = sp
        self._hsb_box.setVisible(False)
        el.addWidget(self._hsb_box)

        ecl.addWidget(self._editor)
        ecl.addStretch(1)
        cl.addWidget(self._editor_card)
        self._editor_card.setVisible(False)

        split.addWidget(self._center)
        split.setSizes([240, 620])

        self._show_empty()

    # ── Construction d'une ligne slider coloré + spinbox ───────────

    def _make_channel_row(self, parent_layout, label, color, min_v, max_v, on_change):
        row = QHBoxLayout()
        lab = QLabel(label)
        lab.setFixedWidth(20)
        lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lab.setStyleSheet(f"color:{color};")
        row.addWidget(lab)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(min_v, max_v)
        sl.setMinimumWidth(170)
        sl.valueChanged.connect(on_change)
        row.addWidget(sl, 1)
        sp = QSpinBox()
        sp.setRange(min_v, max_v)
        sp.setFixedWidth(56)
        sp.valueChanged.connect(on_change)
        row.addWidget(sp)
        parent_layout.addLayout(row)
        return sl, sp

    def _toggle_hsb(self):
        on = self._hsb_toggle.isChecked()
        self._hsb_box.setVisible(on)
        self._hsb_toggle.setText(("▾  TSL" if on else "▸  TSL"))

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)
        self._bank_name = None
        self._show_empty()

    def refresh(self):
        """Reconstruit le finder depuis project.palettes — abonné à
        l'événement dispatcher "palettes_changed" (ex. palette extraite depuis
        le Sprite Editor). Re-sélectionne la banque en cours d'édition si elle
        existe toujours."""
        if not self._project:
            return
        self._finder.refresh()
        if self._bank_name and self._project.palettes.get(self._bank_name):
            self._finder.select_bank(self._bank_name)

    # ── Sélection banque ─────────────────────────────────────────

    def _current_bank(self) -> Optional[PaletteBank]:
        if not self._project or self._bank_name is None:
            return None
        return self._project.palettes.get(self._bank_name)

    def _on_bank_selected(self, name: str):
        self._bank_name = name
        bank = self._current_bank()
        if bank is None:
            self._show_empty()
            return

        self._empty_lbl.setVisible(False)
        self._tools.setVisible(True)
        size = getattr(bank, "size", 16)
        self._title.setText(bank.name)
        self._size_lbl.setText(f"{size} couleurs · {'8bpp' if size == 256 else '4bpp'}")

        self._active_index = 1 if len(bank.colors) > 1 else None
        self._anchor_index = self._active_index
        self._sel_range = None
        self._render_swatches(bank, selectable=True)
        has = bool(bank.colors)
        self._editor_card.setVisible(has)
        self._wheel.setVisible(has)
        if self._active_index is not None:
            self._load_channels(bank.colors[self._active_index])
            self._set_color_hdr(self._active_index)

    def _set_color_hdr(self, index: int):
        self._color_hdr.setText(f"COULEUR · index {index} · 0x{index:02X}")

    def _on_wheel_changed(self, value: int):
        if self._blocking or self._active_value() is None:
            return
        self._apply_color(value)

    def _on_bank_deleted(self):
        if self._bank_name is None or not self._current_bank():
            self._show_empty()

    # ── Actions palette : import / export / rampe (point D) ──────────

    def _reload_after_bulk(self, bank: PaletteBank):
        """Après une modif en masse (rampe) : sauve, re-render la grille, restaure
        le surlignage de sélection, recharge le slot actif et l'icône du finder."""
        self._project.palettes.save(bank)
        self._render_swatches(bank, selectable=True)
        self._refresh_selection_styles(bank)
        if self._active_index is not None and self._active_index < len(bank.colors):
            self._load_channels(bank.colors[self._active_index])
        self._finder.refresh()

    def _export_palette(self):
        bank = self._current_bank()
        if not bank:
            return
        path, sel = QFileDialog.getSaveFileName(
            self, "Exporter la palette", bank.name,
            "Palette GIMP (*.gpl);;Palette JASC (*.pal);;Liste hexadécimale (*.txt)")
        if not path:
            return
        low = path.lower()
        fmt = ("pal" if low.endswith(".pal") or "JASC" in sel else
               "hex" if low.endswith(".txt") or "hexad" in sel else "gpl")
        rgb = [bgr555_to_rgb888(c) for c in bank.colors]
        try:
            Path(path).write_text(_serialize_palette(bank.name, rgb, fmt), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Exporter", f"Échec de l'écriture : {e}")

    def _make_ramp(self):
        """Interpole un dégradé entre deux index (inclus) — les extrémités
        gardent leur couleur, on ne remplit que l'intervalle. Bornes = plage
        sélectionnée (shift+clic). Reste dans les index existants (ne réordonne
        rien)."""
        bank = self._current_bank()
        if not bank or not self._sel_range:
            return
        n = len(bank.colors)
        lo, hi = self._sel_range
        dlg = QDialog(self)
        dlg.setWindowTitle("Générer une rampe")
        v = QVBoxLayout(dlg)
        row = QHBoxLayout()
        sa = QSpinBox(); sa.setRange(1, n - 1); sa.setValue(lo)
        sb = QSpinBox(); sb.setRange(1, n - 1); sb.setValue(hi)
        row.addWidget(QLabel("De l'index")); row.addWidget(sa)
        row.addWidget(QLabel("à")); row.addWidget(sb)
        v.addLayout(row)
        space = QComboBox(); space.addItems(["RVB (linéaire)", "TSL (teinte)"])
        v.addWidget(space)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        a, b = sorted((sa.value(), sb.value()))
        if a == b:
            return
        ca = bgr555_to_rgb888(bank.colors[a])
        cb = bgr555_to_rgb888(bank.colors[b])
        use_hsl = space.currentIndex() == 1
        for i in range(a, b + 1):
            t = (i - a) / (b - a)
            if use_hsl:
                ha, la, sa_ = colorsys.rgb_to_hls(*[x / 255 for x in ca])
                hb, lb, sb_ = colorsys.rgb_to_hls(*[x / 255 for x in cb])
                dh = ((hb - ha + 0.5) % 1.0) - 0.5      # teinte : plus court chemin
                r, g, bl = colorsys.hls_to_rgb((ha + dh * t) % 1.0,
                                               la + (lb - la) * t, sa_ + (sb_ - sa_) * t)
                rgb = (round(r * 255), round(g * 255), round(bl * 255))
            else:
                rgb = tuple(round(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
            bank.colors[i] = rgb888_to_bgr555(*rgb)
        self._reload_after_bulk(bank)

    def _show_empty(self):
        self._empty_lbl.setVisible(True)
        self._tools.setVisible(False)
        self._title.setText("")
        self._size_lbl.setText("")
        self._editor_card.setVisible(False)
        self._wheel.setVisible(False)
        self._clear_swatches()

    # ── Swatches ──────────────────────────────────────────────────

    def _clear_swatches(self):
        while self._swatch_grid.count():
            item = self._swatch_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._swatch_btns.clear()
        self._selected_set = set()

    def _style_swatch(self, btn: QPushButton, index: int, color: int,
                      selected: bool, active: bool = False):
        r, g, b = bgr555_to_rgb888(color)
        # Sans bordure au repos (débruitage de la carte 256) : la géométrie ne
        # bouge pas car les boutons ont une taille fixe — la bordure se dessine EN
        # DEDANS. `active` = liseré blanc (curseur / bord meneur d'une plage),
        # `selected` = liseré accent, sinon rien + liseré discret au survol.
        if active:
            style = (f"QPushButton{{background:rgb({r},{g},{b});"
                     f"border:2px solid {C.TEXT_HI};border-radius:2px;}}")
        elif selected:
            style = (f"QPushButton{{background:rgb({r},{g},{b});"
                     f"border:2px solid {C.ACCENT_GRN};border-radius:2px;}}")
        else:
            style = (f"QPushButton{{background:rgb({r},{g},{b});"
                     f"border:none;border-radius:2px;}}"
                     f"QPushButton:hover{{border:2px solid {C.TEXT_DIM};}}")
        btn.setStyleSheet(style)

    def _coord_label(self, text: str, width: int) -> QLabel:
        lab = QLabel(text)
        lab.setFixedWidth(width)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFont(QFont(T.MONO, T.XS))
        lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        return lab

    def _render_swatches(self, bank: PaletteBank, selectable: bool):
        self._clear_swatches()
        # Grille carrée harmonisée : cellules de MÊME taille en 16 (4×4) et 256
        # (16×16). En 256, la rangée/colonne 0 porte des coordonnées hexa (carte
        # lisible plutôt que mur). Swatches sans bordure (débruitage) ; index 0 =
        # transparent (hardware GBA) → damier, jamais cliquable.
        size = getattr(bank, "size", 16)
        cols = 16 if size == 256 else 4
        cw = ch = SWATCH_CELL_256 if size == 256 else SWATCH_CELL_16
        off = 1 if size == 256 else 0
        if size == 256:
            hexd = "0123456789ABCDEF"
            for c in range(16):
                self._swatch_grid.addWidget(self._coord_label(hexd[c], cw), 0, c + 1)
            for r in range(16):
                self._swatch_grid.addWidget(self._coord_label(f"{r * 16:02X}", 22), r + 1, 0)
        for i, c in enumerate(bank.colors):
            btn = QPushButton()
            btn.setFixedSize(cw, ch)
            if i == 0:
                btn.setIcon(_checker_icon(min(cw, ch) - 6))
                btn.setIconSize(QSize(cw - 6, ch - 6))
                btn.setStyleSheet(
                    f"QPushButton{{background:{C.BG_INPUT};border:none;border-radius:2px;}}"
                )
                btn.setEnabled(False)
                btn.setToolTip("Réservé — toujours transparent (hardware GBA)")
            else:
                self._style_swatch(btn, i, c, selected=selectable and i == self._active_index)
                if selectable:
                    btn.installEventFilter(self)   # sélection au cliqué-glissé
                else:
                    btn.setEnabled(False)
            self._swatch_grid.addWidget(btn, i // cols + off, i % cols + off)
            self._swatch_btns.append(btn)
        self._selected_set = ({self._active_index}
                              if selectable and self._active_index else set())
        self._active_drawn = None

    # ── Sélection au cliqué-glissé (drag) ────────────────────────────

    def eventFilter(self, obj, event):
        """Souris déléguée par les swatches : clic-gauche = début de sélection,
        glisser = extension de la plage, relâcher = fin, clic-droit = menu.
        Clavier délégué par le conteneur : flèches (navigation), Ctrl+C/V."""
        et = event.type()
        if et == QEvent.Type.KeyPress and obj is self._swatch_container:
            if self._handle_grid_key(event):
                return True
        elif et == QEvent.Type.MouseButtonPress and obj in self._swatch_btns:
            idx = self._swatch_btns.index(obj)
            if event.button() == Qt.MouseButton.RightButton:
                if self._selected_set:
                    self._show_swatch_menu(event.globalPosition().toPoint())
                    return True
                return False
            if event.button() == Qt.MouseButton.LeftButton and idx >= 1:
                self._begin_drag(idx)
                return True
        elif et == QEvent.Type.MouseMove and self._dragging:
            self._drag_to(event.globalPosition().toPoint())
            return True
        elif (et == QEvent.Type.MouseButtonRelease and self._dragging
              and event.button() == Qt.MouseButton.LeftButton):
            self._end_drag()
            return True
        return super().eventFilter(obj, event)

    def _handle_grid_key(self, event) -> bool:
        """Navigation clavier dans la grille : flèches (+ shift pour étendre la
        plage), Ctrl+C / Ctrl+V pour copier/coller la couleur active."""
        key, mod = event.key(), event.modifiers()
        if mod & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self._copy_color(); return True
            if key == Qt.Key.Key_V:
                self._paste_color(); return True
            return False
        bank = self._current_bank()
        if not bank or self._active_index is None:
            return False
        size = getattr(bank, "size", 16)
        cols = 16 if size == 256 else 4
        delta = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1,
                 Qt.Key.Key_Up: -cols, Qt.Key.Key_Down: cols}.get(key)
        if delta is None:
            return False
        ni = self._active_index + delta
        if not (1 <= ni < len(bank.colors)):      # ne franchit ni l'index 0 ni les bornes
            return True
        if (mod & Qt.KeyboardModifier.ShiftModifier) and self._anchor_index is not None:
            lo, hi = sorted((self._anchor_index, ni))
            self._sel_range = (lo, hi) if lo != hi else None
        else:
            self._anchor_index = ni
            self._sel_range = None
        self._active_index = ni
        self._refresh_selection_styles(bank)
        self._load_channels(bank.colors[ni])
        self._set_color_hdr(ni)
        return True

    def _copy_color(self):
        v = self._active_value()
        if v is None:
            return
        r, g, b = bgr555_to_rgb888(v)
        QGuiApplication.clipboard().setText(f"#{r:02X}{g:02X}{b:02X}")

    def _paste_color(self):
        if self._active_index is None:
            return
        t = QGuiApplication.clipboard().text().strip().lstrip("#")
        if len(t) != 6:
            return
        try:
            r, g, b = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        except ValueError:
            return
        self._apply_color(rgb888_to_bgr555(r, g, b))

    def _cell_at_global(self, gpos) -> Optional[int]:
        """Index du swatch sous le curseur (coord. écran) — hit-test géométrique
        sur les boutons (ignore les labels de coordonnées)."""
        local = self._swatch_container.mapFromGlobal(gpos)
        for i, b in enumerate(self._swatch_btns):
            if b.geometry().contains(local):
                return i
        return None

    def _begin_drag(self, index: int):
        bank = self._current_bank()
        if not bank or not (1 <= index < len(bank.colors)):
            return
        self._dragging = True
        self._swatch_container.setFocus()      # active la navigation clavier
        self._anchor_index = index
        self._sel_range = None
        self._active_index = index
        self._refresh_selection_styles(bank)
        self._load_channels(bank.colors[index])
        self._set_color_hdr(index)
        self._drag_grab = self._swatch_btns[index]
        self._drag_grab.grabMouse()

    def _drag_to(self, gpos):
        bank = self._current_bank()
        if not bank:
            return
        idx = self._cell_at_global(gpos)
        if idx is None or not (1 <= idx < len(bank.colors)) or idx == self._active_index:
            return
        lo, hi = sorted((self._anchor_index, idx))
        self._sel_range = (lo, hi) if lo != hi else None
        self._active_index = idx
        self._refresh_selection_styles(bank)
        self._load_channels(bank.colors[idx])
        self._set_color_hdr(idx)

    def _end_drag(self):
        if self._drag_grab is not None:
            self._drag_grab.releaseMouse()
            self._drag_grab = None
        self._dragging = False

    # ── Menu contextuel (clic-droit sur la sélection) ────────────────

    def _show_swatch_menu(self, gpos):
        if not self._selected_set:
            return
        lo, hi = min(self._selected_set), max(self._selected_set)
        menu = QMenu(self)
        a_ramp = menu.addAction("Créer une rampe")
        a_ramp.setEnabled(hi - lo >= 2)
        menu.addSeparator()
        a_clear = menu.addAction("Vider")
        a_del = menu.addAction("Supprimer (décale les swatchs)")
        act = menu.exec(gpos)
        if act == a_ramp:
            self._make_ramp()
        elif act == a_clear:
            self._clear_selected()
        elif act == a_del:
            self._delete_selected()

    def _clear_selected(self):
        """Remet les slots sélectionnés à noir (0x0000) — la palette garde sa
        taille et ses index."""
        bank = self._current_bank()
        if not bank or not self._selected_set:
            return
        for i in self._selected_set:
            if 1 <= i < len(bank.colors):
                bank.colors[i] = 0
        self._reload_after_bulk(bank)

    def _delete_selected(self):
        """Supprime les slots sélectionnés et DÉCALE les suivants vers la gauche ;
        complète la fin en noir pour préserver la taille (16/256) et l'index 0."""
        bank = self._current_bank()
        if not bank or not self._selected_set:
            return
        lo, hi = min(self._selected_set), max(self._selected_set)
        size = getattr(bank, "size", len(bank.colors))
        del bank.colors[lo:hi + 1]
        bank.colors += [0] * (size - len(bank.colors))
        self._sel_range = None
        self._active_index = min(lo, len(bank.colors) - 1)
        self._anchor_index = self._active_index
        self._project.palettes.save(bank)
        self._render_swatches(bank, selectable=True)
        self._refresh_selection_styles(bank)
        if self._active_index is not None and self._active_index < len(bank.colors):
            self._load_channels(bank.colors[self._active_index])
            self._set_color_hdr(self._active_index)
        self._finder.refresh()

    def _refresh_selection_styles(self, bank: PaletteBank):
        """Re-stylise uniquement les cases dont l'état de sélection change
        (diff avec la sélection précédente) — crucial en 256 couleurs. Dans une
        PLAGE, la case active (bord meneur) porte un liseré blanc distinct."""
        if self._sel_range:
            new = set(range(self._sel_range[0], self._sel_range[1] + 1))
        elif self._active_index is not None:
            new = {self._active_index}
        else:
            new = set()
        act = self._active_index if self._sel_range else None    # marqueur blanc si plage

        def _style(idx):
            self._style_swatch(self._swatch_btns[idx], idx, bank.colors[idx],
                               selected=True, active=(idx == act))

        for idx in self._selected_set - new:
            if 0 < idx < len(self._swatch_btns):
                self._style_swatch(self._swatch_btns[idx], idx, bank.colors[idx], selected=False)
        for idx in new - self._selected_set:
            if 0 < idx < len(self._swatch_btns):
                _style(idx)
        # Le marqueur actif a bougé à l'intérieur de la plage : re-stylise l'ancien
        # (rétrogradé en vert) et le nouveau (promu blanc).
        if self._active_drawn != act:
            for idx in {self._active_drawn, act} & new:
                if idx is not None and 0 < idx < len(self._swatch_btns):
                    _style(idx)
        self._selected_set = new
        self._active_drawn = act

    def _active_value(self) -> Optional[int]:
        bank = self._current_bank()
        if bank and self._active_index is not None and self._active_index < len(bank.colors):
            return bank.colors[self._active_index]
        return None

    # ── Éditeur de couleur (RGB 0-31 natif GBA + HSB dérivé + hex) ────

    def _load_channels(self, value: int):
        """Synchronise tous les contrôles (RGB, HSB, hex, preview, gradients)
        depuis une valeur BGR555, sans re-déclencher les handlers."""
        self._blocking = True
        r, g, b = bgr555_components(value)                 # 0-31
        for ch, v in (("r", r), ("g", g), ("b", b)):
            self._sliders[ch].setValue(v)
            self._spins[ch].setValue(v)
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        for ch, v in (("h", round(h * 359)), ("s", round(s * 100)), ("v", round(l * 100))):
            self._hsb_sliders[ch].setValue(v)
            self._hsb_spins[ch].setValue(v)
        R, G, B = bgr555_to_rgb888(value)
        self._hex.setText(f"#{R:02X}{G:02X}{B:02X}")
        self._bgr.setText(f"0x{value & 0x7FFF:04X}")
        self._snap.setText("")            # valeur exacte : pas de snap par défaut
        self._update_preview(value)
        self._update_gradients(value)
        self._wheel.set_value(value)   # no-op pendant un drag de la roue
        self._blocking = False

    def _update_preview(self, value: int):
        r, g, b = bgr555_to_rgb888(value)
        self._preview.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID}; border-radius:6px;"
        )

    def _update_gradients(self, value: int):
        """Recolore chaque rainure de slider pour simuler la couleur obtenue
        le long du slider (les autres canaux fixés à la valeur courante)."""
        r, g, b = bgr555_components(value)
        R, G, B = bgr555_to_rgb888(value)
        self._sliders["r"].setStyleSheet(_grad_slider_qss([f"rgb(0,{G},{B})", f"rgb(255,{G},{B})"]))
        self._sliders["g"].setStyleSheet(_grad_slider_qss([f"rgb({R},0,{B})", f"rgb({R},255,{B})"]))
        self._sliders["b"].setStyleSheet(_grad_slider_qss([f"rgb({R},{G},0)", f"rgb({R},{G},255)"]))
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        self._hsb_sliders["h"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(i / 6, s, l)) for i in range(7)]))
        self._hsb_sliders["s"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(h, 0, l)), _rgb01(colorsys.hsv_to_rgb(h, 1, l))]))
        self._hsb_sliders["v"].setStyleSheet(_grad_slider_qss(
            [_rgb01(colorsys.hsv_to_rgb(h, s, 0)), _rgb01(colorsys.hsv_to_rgb(h, s, 1))]))

    def _apply_color(self, new_value: int):
        """Écrit `new_value` DANS LE SLOT ÉDITÉ (à son index, sans réordonner),
        sauvegarde et resynchronise l'UI. Point de passage unique des trois
        modes d'édition (RGB, HSB, hex). L'ordre des couleurs = l'ordre des
        index hardware, laissé tel quel : c'est à l'utilisateur d'organiser
        ses couleurs (l'index est ce qui est réellement visible in-game)."""
        if self._active_index is None:
            return
        bank = self._current_bank()
        if not bank or not (1 <= self._active_index < len(bank.colors)):
            return
        bank.colors[self._active_index] = new_value
        self._project.palettes.save(bank)
        self._load_channels(new_value)
        # Met à jour uniquement le swatch édité (pas de re-render complet).
        idx = self._active_index
        if 0 <= idx < len(self._swatch_btns):
            self._style_swatch(self._swatch_btns[idx], idx, new_value, selected=True)
        self._finder.refresh()

    def _on_rgb_changed(self, ch: str, v: int):
        cur = self._active_value()
        if self._blocking or cur is None:
            return
        r, g, b = bgr555_components(cur)
        r, g, b = {"r": (v, g, b), "g": (r, v, b), "b": (r, g, v)}[ch]
        self._apply_color(components_to_bgr555(r, g, b))

    def _on_hsb_changed(self, ch: str, v: int):
        cur = self._active_value()
        if self._blocking or cur is None:
            return
        r, g, b = bgr555_components(cur)
        h, s, l = colorsys.rgb_to_hsv(r / 31, g / 31, b / 31)
        hsb = {"h": h * 359, "s": s * 100, "v": l * 100}
        hsb[ch] = v
        rr, gg, bb = colorsys.hsv_to_rgb(hsb["h"] / 359, hsb["s"] / 100, hsb["v"] / 100)
        self._apply_color(components_to_bgr555(round(rr * 31), round(gg * 31), round(bb * 31)))

    def _on_hex_changed(self):
        cur = self._active_value()
        if self._blocking or cur is None:
            return
        t = self._hex.text().strip().lstrip("#")
        if len(t) != 6:
            self._load_channels(cur)   # entrée invalide -> restaure
            return
        try:
            R, G, B = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
        except ValueError:
            self._load_channels(cur)
            return
        new = rgb888_to_bgr555(R, G, B)
        self._apply_color(new)
        # _apply_color a resynchronisé (snap remis à ""). Si l'hex 24 bits saisi
        # ne retombe pas exactement sur la grille 15 bits, on le signale.
        if bgr555_to_rgb888(new) != (R, G, B):
            self._snap.setText("≈ snap")
