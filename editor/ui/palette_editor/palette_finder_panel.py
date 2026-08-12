"""ui/palette_editor/palette_finder_panel.py — panneau gauche : catalogue des palettes du projet."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QInputDialog, QMessageBox, QMenu, QStyledItemDelegate,
    QFileDialog,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.widgets import W
from ui.common.palette_swatch import bank_icon as _bank_icon

from core.models.palette import PaletteBank
from core.project import Project
from core.gba_color import rgb888_to_bgr555
from core.palette_presets import hsb_ramp_bgr555
from core.history import get_history, AddResourceCmd, DeleteResourceCmd

from .palette_file_io import parse_palette_file


class _PaletteNameDelegate(QStyledItemDelegate):
    """Le libellé du finder affiche « nom  (16/256) », mais l'édition en place ne
    porte que sur le nom NU (stocké en UserRole) — le suffixe de taille ne pollue
    jamais le champ de renommage."""

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.UserRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


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

        root.addWidget(W.finder_bar("PALETTE FINDER"))

        root.addWidget(self._make_section("PALETTES", C.ACCENT))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFont(QFont(T.UI, T.MD))
        self._tree.setIconSize(QSize(16, 16))
        self._tree.setStyleSheet(QSS.tree_widget)
        self._tree.setItemDelegate(_PaletteNameDelegate(self._tree))
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.currentItemChanged.connect(self._on_selected)
        self._tree.itemChanged.connect(self._on_item_text_changed)
        self._tree.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._tree, 1)

    def _make_section(self, title: str, color: str) -> QFrame:
        # Même en-tête que les sections repliables des autres viewers
        # (W.section_bar) : titre sur la gouttière, pas de bandeau.
        f = W.section_bar(title, color)
        hl = f.layout()

        self._btn_add = W.btn_add("Add a palette (create / import)")
        self._btn_add.clicked.connect(self._on_add_menu)
        hl.addWidget(self._btn_add)

        btn_del = W.btn_danger("Delete selected palette")
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
        # Project.rename_palette (et pas palettes.rename) : il répare aussi les
        # scènes et les overrides d'assets qui citent la banque par son nom.
        self._project.rename_palette(bank, new_name)
        _set_display(new_name)
        self.bank_selected.emit(new_name)

    # ── Menu contextuel ──────────────────────────────────────────────

    def _on_ctx_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        self._tree.setCurrentItem(item)
        menu = QMenu(self)
        dup_a = menu.addAction("Duplicate")
        menu.addSeparator()
        delete_a = menu.addAction("Delete")
        act = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if act == dup_a:
            self._duplicate()
        elif act == delete_a:
            self._del()

    # ── Ajout (créer / importer) / suppression ────────────────────

    def _on_add_menu(self):
        """Le « + » propose deux entrées : créer une palette vide, ou en importer
        une depuis un fichier (.gpl / .pal / liste hex)."""
        menu = QMenu(self)
        a_new = menu.addAction("Create an empty palette")
        a_imp = menu.addAction("Import…")
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
        name, ok = QInputDialog.getText(self, "New palette", "Name:")
        if not (ok and name.strip()):
            return
        name = name.strip()
        if self._project.palettes.get(name):
            return
        kind, ok = QInputDialog.getItem(
            self, "Palette type", "Size:",
            ["16 colors (4bpp)", "256 colors (8bpp)"], 0, False)
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
            self, "Import a palette", "",
            "Palettes (*.gpl *.pal *.txt *.hex);;All files (*)")
        if not path:
            return
        try:
            colors = parse_palette_file(Path(path))
        except OSError as e:
            QMessageBox.warning(self, "Import", f"Unreadable file: {e}")
            return
        if not colors:
            QMessageBox.warning(self, "Import", "No color recognized in this file.")
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

    def _duplicate(self):
        """Copie la palette sélectionnée sous un nom libre (« X copie », « X copie 2 »…)
        et l'affiche — geste de composition le plus courant : partir d'une palette
        existante pour en dériver une variante sans toucher à l'originale (ni aux
        scènes qui la référencent par nom). Annulable (Ctrl+Z)."""
        item = self._tree.currentItem()
        if not (item and self._project):
            return
        src = self._project.palettes.get(item.data(0, Qt.ItemDataRole.UserRole))
        if not src:
            return
        copy = PaletteBank(name=self._unique_name(f"{src.name} copy"),
                           colors=list(src.colors), size=src.size)

        def _refresh():
            self.refresh()
            if self._project.palettes.get(copy.name):
                self.select_bank(copy.name)     # execute / redo : afficher la copie
            else:
                self.bank_deleted.emit()        # undo : la copie n'existe plus

        get_history().push(AddResourceCmd(self._project.palettes, copy, _refresh))

    def _del(self):
        item = self._tree.currentItem()
        if not item:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        bank = self._project.palettes.get(name)
        if not bank:
            return
        if QMessageBox.question(
            self, "Delete",
            f"Delete palette “{bank.name}”?\n(Ctrl+Z to undo)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _refresh():
            self.refresh()
            self.bank_deleted.emit()

        get_history().push(DeleteResourceCmd(self._project.palettes, bank, _refresh))
