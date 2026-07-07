"""Palette Editor screen — catalogue illimité de palettes nommées (OBJ + BG).

Le catalogue projet n'a plus de limite (contrairement aux 16 banques
hardware) — c'est la scène qui choisit jusqu'à 16 palettes actives par pool
parmi ce catalogue (voir Scene Inspector, carte "Palettes actives").
"""
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSplitter,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QSlider, QSpinBox,
    QInputDialog, QMessageBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W

from core.project import Project, PaletteBank
from core.color_utils import bgr555_to_rgb888, bgr555_components, components_to_bgr555
from core.palette_presets import hsb_ramp_bgr555
from core.history import get_history, DeleteResourceCmd
from ui.common.palette_swatch import bank_icon as _bank_icon

POOL_LABELS = {"bg": "BACKGROUND", "obj": "OBJ"}

SPLITTER_STYLE = (
    f"QSplitter::handle{{background:{C.BORDER};}}"
    "QSplitter::handle:horizontal{width:3px;}"
    f"QSplitter::handle:hover{{background:{C.ACCENT_GRN};}}"
)


# ──────────────────────────────────────────────────────────────────
#  PaletteFinderPanel
# ──────────────────────────────────────────────────────────────────
class PaletteFinderPanel(QWidget):
    """Panneau gauche : deux sections BACKGROUND / OBJ, catalogue illimité
    (ajout/suppression/renommage), même modèle que SoundFinderPanel."""

    bank_selected = pyqtSignal(str, str)   # pool ("bg"/"obj"), nom
    bank_deleted  = pyqtSignal(str)        # pool

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

        self._trees: dict[str, QTreeWidget] = {}
        for pool, color in (("bg", C.ACCENT_BLU), ("obj", C.ACCENT_ORG)):
            root.addWidget(self._make_section(pool, POOL_LABELS[pool], color))
            tree = QTreeWidget()
            tree.setHeaderHidden(True)
            tree.setFont(QFont(T.MONO, T.MD))
            tree.setIconSize(QSize(16, 16))
            tree.setStyleSheet(
                f"QTreeWidget{{background:#161616;color:{C.TEXT_NORM};border:none;}}"
                "QTreeWidget::item:selected{background:#1a2a3a;}"
                "QTreeWidget::item:hover{background:#202020;}"
            )
            tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.currentItemChanged.connect(
                lambda cur, prev, pool=pool: self._on_selected(pool, cur))
            tree.itemChanged.connect(
                lambda item, col, pool=pool: self._on_item_text_changed(pool, item, col))
            tree.customContextMenuRequested.connect(
                lambda pos, pool=pool: self._on_ctx_menu(pool, pos))
            root.addWidget(tree, 1)
            self._trees[pool] = tree

    def _make_section(self, pool: str, title: str, color: str) -> QFrame:
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

        btn_add = W.btn_add(f"Ajouter une palette {title}")
        btn_add.clicked.connect(lambda: self._add(pool))
        hl.addWidget(btn_add)

        btn_del = W.btn_danger("Supprimer la palette sélectionnée")
        btn_del.clicked.connect(lambda: self._del(pool))
        hl.addWidget(btn_del)

        return f

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self.refresh()

    def refresh(self):
        for pool in ("bg", "obj"):
            self._refresh_pool(pool)

    def _manager(self, pool: str):
        return self._project.obj_palettes if pool == "obj" else self._project.bg_palettes

    def _refresh_pool(self, pool: str):
        if not self._project:
            return
        tree = self._trees[pool]
        tree.blockSignals(True)
        tree.clear()
        for bank in self._manager(pool):
            item = QTreeWidgetItem([bank.name])
            item.setIcon(0, _bank_icon(bank))
            item.setData(0, Qt.ItemDataRole.UserRole, (pool, bank.name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            tree.addTopLevelItem(item)
        tree.blockSignals(False)

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, pool: str, current: Optional[QTreeWidgetItem]):
        if not current:
            return
        self._trees["obj" if pool == "bg" else "bg"].clearSelection()
        _, name = current.data(0, Qt.ItemDataRole.UserRole)
        self.bank_selected.emit(pool, name)

    # ── Renommage en place ────────────────────────────────────────

    def _on_item_text_changed(self, pool: str, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        _, old_name = data
        manager = self._manager(pool)
        bank = manager.get(old_name)
        tree = self._trees[pool]
        if not bank:
            return
        new_name = item.text(0).strip()
        if not new_name or new_name == old_name or manager.get(new_name):
            tree.blockSignals(True)
            item.setText(0, old_name)
            tree.blockSignals(False)
            return
        manager.rename(bank, new_name)
        item.setData(0, Qt.ItemDataRole.UserRole, (pool, new_name))
        self.bank_selected.emit(pool, new_name)

    # ── Menu contextuel ──────────────────────────────────────────────

    def _on_ctx_menu(self, pool: str, pos):
        from PyQt6.QtWidgets import QMenu
        tree = self._trees[pool]
        item = tree.itemAt(pos)
        if not item:
            return
        tree.setCurrentItem(item)
        menu = QMenu(self)
        delete_a = menu.addAction("Supprimer")
        if menu.exec(tree.viewport().mapToGlobal(pos)) == delete_a:
            self._del(pool)

    # ── Ajout / suppression ───────────────────────────────────────

    def _add(self, pool: str):
        if not self._project:
            return
        name, ok = QInputDialog.getText(self, f"Nouvelle palette {POOL_LABELS[pool]}", "Nom :")
        if not (ok and name.strip()):
            return
        name = name.strip()
        manager = self._manager(pool)
        if manager.get(name):
            return
        bank = PaletteBank(name=name, colors=hsb_ramp_bgr555(0, 0))
        manager.append(bank)
        manager.save(bank)
        self._refresh_pool(pool)
        tree = self._trees[pool]
        last = tree.topLevelItem(tree.topLevelItemCount() - 1)
        if last:
            tree.setCurrentItem(last)

    def _del(self, pool: str):
        tree = self._trees[pool]
        item = tree.currentItem()
        if not item:
            return
        _, name = item.data(0, Qt.ItemDataRole.UserRole)
        manager = self._manager(pool)
        bank = manager.get(name)
        if not bank:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la palette « {bank.name} » ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _refresh():
            self._refresh_pool(pool)
            self.bank_deleted.emit(pool)

        get_history().push(DeleteResourceCmd(manager, bank, _refresh))


# ──────────────────────────────────────────────────────────────────
#  PaletteEditorScreen
# ──────────────────────────────────────────────────────────────────
class PaletteEditorScreen(QWidget):
    """Écran complet Palette Editor : finder (BG/OBJ) + édition RGB de la banque active."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._pool: Optional[str] = None
        self._bank_name: Optional[str] = None
        self._active_color: Optional[int] = None
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

        self._title = QLabel("")
        self._title.setFont(QFont(T.MONO, T.XL, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color:{C.TEXT_HI};")
        self._title.setVisible(False)
        cl.addWidget(self._title)

        self._swatch_row = QHBoxLayout()
        self._swatch_row.setSpacing(4)
        cl.addLayout(self._swatch_row)
        self._swatch_btns: list[QPushButton] = []

        self._editor = QWidget()
        el = QVBoxLayout(self._editor)
        el.setContentsMargins(0, 10, 0, 0)
        el.setSpacing(8)

        self._preview = QLabel()
        self._preview.setFixedSize(60, 60)
        self._preview.setStyleSheet(f"border:1px solid {C.BORDER_MID}; border-radius:4px;")
        el.addWidget(self._preview)

        self._sliders: dict[str, QSlider] = {}
        self._spins: dict[str, QSpinBox] = {}
        for ch, chan_color in (("r", C.AXIS_X), ("g", C.ACCENT_GRN), ("b", C.AXIS_Y)):
            row = QHBoxLayout()
            lab = QLabel(ch.upper())
            lab.setFixedWidth(16)
            lab.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            lab.setStyleSheet(f"color:{chan_color};")
            row.addWidget(lab)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 31)
            sl.valueChanged.connect(lambda v, ch=ch: self._on_channel_changed(ch, v))
            row.addWidget(sl, 1)
            sp = QSpinBox()
            sp.setRange(0, 31)
            sp.setFixedWidth(50)
            sp.valueChanged.connect(lambda v, ch=ch: self._on_channel_changed(ch, v))
            row.addWidget(sp)
            self._sliders[ch] = sl
            self._spins[ch] = sp
            el.addLayout(row)

        cl.addWidget(self._editor)
        cl.addStretch()
        self._editor.setVisible(False)

        split.addWidget(self._center)
        split.setSizes([240, 560])

        self._show_empty()

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)
        self._pool = None
        self._bank_name = None
        self._show_empty()

    # ── Sélection banque ─────────────────────────────────────────

    def _current_bank(self) -> Optional[PaletteBank]:
        if not self._project or self._pool is None or self._bank_name is None:
            return None
        manager = self._project.obj_palettes if self._pool == "obj" else self._project.bg_palettes
        return manager.get(self._bank_name)

    def _on_bank_selected(self, pool: str, name: str):
        self._pool = pool
        self._bank_name = name
        bank = self._current_bank()
        if bank is None:
            self._show_empty()
            return

        self._empty_lbl.setVisible(False)
        self._title.setText(bank.name)
        self._title.setVisible(True)

        self._active_color = bank.colors[0] if bank.colors else None
        self._render_swatches(bank, selectable=True)
        self._editor.setVisible(bool(bank.colors))
        if self._active_color is not None:
            self._load_channels(self._active_color)

    def _on_bank_deleted(self, pool: str):
        if self._pool == pool and (self._bank_name is None or not self._current_bank()):
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
        for c in bank.colors:
            btn = QPushButton()
            btn.setFixedSize(32, 40)
            r, g, b = bgr555_to_rgb888(c)
            selected = selectable and c == self._active_color
            border = C.ACCENT_GRN if selected else C.BORDER_MID
            width = 3 if selected else 1
            btn.setStyleSheet(
                f"QPushButton{{background:rgb({r},{g},{b});"
                f"border:{width}px solid {border};border-radius:2px;}}"
            )
            if selectable:
                btn.clicked.connect(lambda _checked, c=c: self._select_color(c))
            else:
                btn.setEnabled(False)
            self._swatch_row.addWidget(btn)
            self._swatch_btns.append(btn)
        self._swatch_row.addStretch(1)

    def _select_color(self, value: int):
        self._active_color = value
        self._load_channels(value)
        bank = self._current_bank()
        if bank:
            self._render_swatches(bank, selectable=True)

    # ── Éditeur RGB (0-31, profondeur native GBA) ───────────────────

    def _load_channels(self, value: int):
        self._blocking = True
        r, g, b = bgr555_components(value)
        for ch, v in (("r", r), ("g", g), ("b", b)):
            self._sliders[ch].setValue(v)
            self._spins[ch].setValue(v)
        self._update_preview(value)
        self._blocking = False

    def _update_preview(self, value: int):
        r, g, b = bgr555_to_rgb888(value)
        self._preview.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID}; border-radius:4px;"
        )

    def _on_channel_changed(self, ch: str, v: int):
        if self._blocking or self._active_color is None:
            return
        bank = self._current_bank()
        if not bank:
            return

        self._blocking = True
        self._sliders[ch].setValue(v)
        self._spins[ch].setValue(v)
        self._blocking = False

        r, g, b = bgr555_components(self._active_color)
        r, g, b = {"r": (v, g, b), "g": (r, v, b), "b": (r, g, v)}[ch]
        new_value = components_to_bgr555(r, g, b)

        idx = bank.colors.index(self._active_color)
        bank.colors[idx] = new_value
        bank.colors.sort(key=lambda c: sum(bgr555_components(c)), reverse=True)
        self._active_color = new_value

        manager = self._project.obj_palettes if self._pool == "obj" else self._project.bg_palettes
        manager.save(bank)
        self._update_preview(new_value)
        self._render_swatches(bank, selectable=True)
        self._finder.refresh()
