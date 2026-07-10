"""Palette Editor screen — catalogue illimité et unifié de palettes nommées.

Plus de distinction OBJ/BG dans le catalogue (2026-07-08) — une palette est
juste 16 couleurs, réutilisable pour les deux pools. C'est la scène qui
choisit jusqu'à 16 palettes actives par pool parmi ce catalogue (voir Scene
Inspector, carte "Palettes actives").
"""
import colorsys
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSplitter,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QSlider, QSpinBox,
    QInputDialog, QMessageBox, QMenu, QLineEdit,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W

from core.project import Project, PaletteBank
from core.color_utils import (
    bgr555_to_rgb888, bgr555_components, components_to_bgr555, rgb888_to_bgr555,
)
from core.palette_presets import hsb_ramp_bgr555
from core.history import get_history, DeleteResourceCmd
from ui.common.palette_swatch import bank_icon as _bank_icon

SPLITTER_STYLE = (
    f"QSplitter::handle{{background:{C.BORDER};}}"
    "QSplitter::handle:horizontal{width:3px;}"
    f"QSplitter::handle:hover{{background:{C.ACCENT_GRN};}}"
)


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

        btn_add = W.btn_add("Ajouter une palette")
        btn_add.clicked.connect(self._add)
        hl.addWidget(btn_add)

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
            item = QTreeWidgetItem([bank.name])
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
        new_name = item.text(0).strip()
        if not new_name or new_name == old_name or self._project.palettes.get(new_name):
            self._tree.blockSignals(True)
            item.setText(0, old_name)
            self._tree.blockSignals(False)
            return
        self._project.palettes.rename(bank, new_name)
        item.setData(0, Qt.ItemDataRole.UserRole, new_name)
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

    # ── Ajout / suppression ───────────────────────────────────────

    def _add(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(self, "Nouvelle palette", "Nom :")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if self._project.palettes.get(name):
            return
        bank = PaletteBank(name=name, colors=hsb_ramp_bgr555(0, 0))
        self._project.palettes.append(bank)
        self._project.palettes.save(bank)
        self.refresh()
        last = self._tree.topLevelItem(self._tree.topLevelItemCount() - 1)
        if last:
            self._tree.setCurrentItem(last)

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
        self._active_index: Optional[int] = None
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

        self._center = QWidget()
        self._center.setStyleSheet(f"background:{C.BG_PANEL};")
        cl = QVBoxLayout(self._center)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(14)

        self._empty_lbl = QLabel("Sélectionne une palette dans le panneau de gauche")
        self._empty_lbl.setFont(QFont(T.MONO, T.MD))
        self._empty_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self._empty_lbl)

        _CENTER = Qt.AlignmentFlag.AlignHCenter

        self._title = QLabel("")
        self._title.setFont(QFont(T.MONO, T.XL, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};")
        self._title.setVisible(False)
        cl.addWidget(self._title, alignment=_CENTER)

        self._swatch_row = QHBoxLayout()
        self._swatch_row.setSpacing(4)
        cl.addLayout(self._swatch_row)
        self._swatch_btns: list[QPushButton] = []

        # ── Éditeur de couleur (centré, largeur bornée) ────────────────
        self._editor = QWidget()
        self._editor.setMaximumWidth(460)
        el = QVBoxLayout(self._editor)
        el.setContentsMargins(0, 10, 0, 0)
        el.setSpacing(10)

        self._preview = QLabel()
        self._preview.setFixedSize(96, 96)
        self._preview.setStyleSheet(f"border:1px solid {C.BORDER_MID}; border-radius:6px;")
        el.addWidget(self._preview, alignment=_CENTER)

        # Champ hexadécimal (#RRGGBB, quantifié 5 bits/canal)
        hex_row = QHBoxLayout()
        hex_row.setAlignment(_CENTER)
        hex_lab = QLabel("HEX")
        hex_lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        hex_lab.setStyleSheet(f"color:{C.TEXT_DIM};")
        hex_row.addWidget(hex_lab)
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
        hex_row.addWidget(self._hex)
        el.addLayout(hex_row)

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

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER_DARK};")
        el.addWidget(sep)

        for ch, label, maxv, chan_color in (
            ("h", "H", 359, C.TEXT_DIM), ("s", "S", 100, C.TEXT_DIM), ("v", "L", 100, C.TEXT_DIM),
        ):
            sl, sp = self._make_channel_row(
                el, label, chan_color, 0, maxv,
                lambda v, ch=ch: self._on_hsb_changed(ch, v),
            )
            self._hsb_sliders[ch] = sl
            self._hsb_spins[ch] = sp

        cl.addWidget(self._editor, alignment=_CENTER)
        cl.addStretch()
        self._editor.setVisible(False)

        split.addWidget(self._center)
        split.setSizes([240, 560])

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
        sl.setMinimumWidth(240)
        sl.valueChanged.connect(on_change)
        row.addWidget(sl, 1)
        sp = QSpinBox()
        sp.setRange(min_v, max_v)
        sp.setFixedWidth(56)
        sp.valueChanged.connect(on_change)
        row.addWidget(sp)
        parent_layout.addLayout(row)
        return sl, sp

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
        self._title.setText(bank.name)
        self._title.setVisible(True)

        self._active_index = 1 if len(bank.colors) > 1 else None
        self._render_swatches(bank, selectable=True)
        self._editor.setVisible(bool(bank.colors))
        if self._active_index is not None:
            self._load_channels(bank.colors[self._active_index])

    def _on_bank_deleted(self):
        if self._bank_name is None or not self._current_bank():
            self._show_empty()

    def _show_empty(self):
        self._empty_lbl.setVisible(True)
        self._title.setVisible(False)
        self._editor.setVisible(False)
        self._clear_swatches()

    # ── Swatches ──────────────────────────────────────────────────

    def _clear_swatches(self):
        # Vide tout le layout (boutons ET le stretch final) — sinon les
        # stretches s'accumulent d'un appel a l'autre et poussent les
        # swatches progressivement vers la droite.
        while self._swatch_row.count():
            item = self._swatch_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._swatch_btns.clear()

    def _render_swatches(self, bank: PaletteBank, selectable: bool):
        self._clear_swatches()
        self._swatch_row.addStretch(1)   # centrage (stretch avant + après)
        for i, c in enumerate(bank.colors):
            btn = QPushButton()
            btn.setFixedSize(32, 40)
            r, g, b = bgr555_to_rgb888(c)
            swatch_selectable = selectable and i != 0
            selected = swatch_selectable and i == self._active_index
            border = C.ACCENT_GRN if selected else C.BORDER_MID
            width = 3 if selected else 1
            btn.setStyleSheet(
                f"QPushButton{{background:rgb({r},{g},{b});"
                f"border:{width}px solid {border};border-radius:2px;}}"
            )
            if swatch_selectable:
                btn.clicked.connect(lambda _checked, i=i: self._select_color(i))
            else:
                btn.setEnabled(False)
            if i == 0:
                btn.setToolTip("Réservé — toujours transparent (hardware GBA)")
            self._swatch_row.addWidget(btn)
            self._swatch_btns.append(btn)
        self._swatch_row.addStretch(1)

    def _select_color(self, index: int):
        """Sélectionne le slot `index` (l'index EST le slot hardware visible
        in-game — on suit l'index, pas la valeur, pour ne jamais réordonner
        les couleurs sous les pieds de l'utilisateur)."""
        bank = self._current_bank()
        if not bank or not (0 <= index < len(bank.colors)):
            return
        self._active_index = index
        self._load_channels(bank.colors[index])
        self._render_swatches(bank, selectable=True)

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
        self._update_preview(value)
        self._update_gradients(value)
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
        self._render_swatches(bank, selectable=True)
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
        self._apply_color(rgb888_to_bgr555(R, G, B))
