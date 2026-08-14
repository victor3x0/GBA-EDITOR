"""ui/data_editor/data_finder_panel.py — panneau gauche : les tables du projet."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QMessageBox, QMenu,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T, QSS
from ui.common.widgets import W

from core.models.data_table import DataTable, DataColumn
from core.history import get_history, AddResourceCmd, DeleteResourceCmd
from core.project import Project


class DataFinderPanel(QWidget):
    """Liste des tables de données du projet — créer, renommer, dupliquer,
    supprimer.

    Le « + » crée directement une table nommée d'office et ouvre l'édition du
    nom EN PLACE : pas de dialogue qui demande un nom avant que quoi que ce
    soit existe. Le renommage passe par `Project.rename_data_table`, seul
    chemin qui réécrive aussi les scripts citant `data.<nom>`."""

    table_selected = pyqtSignal(str)
    table_deleted  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(W.finder_bar("Data finder"))
        root.addWidget(self._make_section())

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setFont(QFont(T.UI, T.MD))
        self._tree.setStyleSheet(QSS.tree_widget)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.currentItemChanged.connect(self._on_selected)
        self._tree.itemChanged.connect(self._on_item_text_changed)
        self._tree.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._tree, 1)

    def _make_section(self) -> QFrame:
        f = W.section_bar("Tables", C.ACCENT)
        hl = f.layout()
        btn_add = W.btn_add("New table")
        btn_add.clicked.connect(self._add)
        hl.addWidget(btn_add)
        btn_del = W.btn_danger("Delete selected table")
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
        for table in self._project.data_tables:
            item = QTreeWidgetItem()
            # « nom  (12 × 3) » : lignes × colonnes. Le nom NU vit en UserRole —
            # c'est lui qu'on édite et qu'on cherche, jamais le libellé.
            item.setText(0, f"{table.name}  ({len(table.rows)} × {len(table.columns)})")
            item.setData(0, Qt.ItemDataRole.UserRole, table.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)

    def select_table(self, name: str):
        for i in range(self._tree.topLevelItemCount()):
            it = self._tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == name:
                self._tree.setCurrentItem(it)
                return

    @property
    def current_name(self) -> str:
        item = self._tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else ""

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, current: Optional[QTreeWidgetItem], _prev):
        if current:
            self.table_selected.emit(current.data(0, Qt.ItemDataRole.UserRole))

    # ── Renommage en place ────────────────────────────────────────

    def _on_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        old_name = item.data(0, Qt.ItemDataRole.UserRole)
        table = self._project.data_tables.get(old_name) if self._project else None
        if not table:
            return
        new_name = item.text(0).strip()
        if self._project.rename_data_table(table, new_name):
            self.refresh()
            self.select_table(new_name)
            return
        # Refusé (vide, déjà pris, ou pas un identifiant) : la ligne doit
        # revenir au nom réel, sinon la liste affiche une table qui n'existe
        # sous ce nom nulle part.
        self.refresh()
        self.select_table(old_name)
        if new_name and new_name != old_name:
            QMessageBox.warning(
                self, "Rename",
                f"« {new_name} » is not usable: a table name is written as code "
                f"in scripts (data.{old_name}), so it must be a plain identifier "
                f"— letters, digits and _, not starting with a digit — and unique.")

    # ── Menu contextuel ───────────────────────────────────────────

    def _on_ctx_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        self._tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        dup_a = menu.addAction("Duplicate")
        menu.addSeparator()
        del_a = menu.addAction("Delete")
        act = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if act == dup_a:
            self._duplicate()
        elif act == del_a:
            self._del()

    # ── Création / duplication / suppression ──────────────────────

    def _unique_name(self, base: str) -> str:
        if not self._project.data_tables.get(base):
            return base
        i = 2
        while self._project.data_tables.get(f"{base}_{i}"):
            i += 1
        return f"{base}_{i}"

    def _add(self):
        """Crée une table d'une colonne et d'aucune ligne, et ouvre l'édition
        du nom. Une colonne d'office plutôt qu'une table vide : une grille sans
        colonne n'a nulle part où poser une ligne."""
        if not self._project:
            return
        table = DataTable(name=self._unique_name("Table"),
                          columns=[DataColumn(name="valeur", type="int")],
                          rows=[])

        def _refresh():
            self.refresh()
            if self._project.data_tables.get(table.name):
                self.select_table(table.name)
            else:
                self.table_deleted.emit()

        get_history().push(AddResourceCmd(self._project.data_tables, table, _refresh))
        item = self._tree.currentItem()
        if item:
            self._tree.editItem(item, 0)

    def _duplicate(self):
        src = self._project.data_tables.get(self.current_name) if self._project else None
        if not src:
            return
        copy = DataTable(
            name    = self._unique_name(f"{src.name}_copy"),
            columns = [DataColumn(name=c.name, type=c.type) for c in src.columns],
            rows    = [dict(r) for r in src.rows],
        )

        def _refresh():
            self.refresh()
            if self._project.data_tables.get(copy.name):
                self.select_table(copy.name)
            else:
                self.table_deleted.emit()

        get_history().push(AddResourceCmd(self._project.data_tables, copy, _refresh))

    def _del(self):
        table = self._project.data_tables.get(self.current_name) if self._project else None
        if not table:
            return
        if QMessageBox.question(
            self, "Delete",
            f"Delete table “{table.name}”?\n(Ctrl+Z to undo)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _refresh():
            self.refresh()
            self.table_deleted.emit()

        get_history().push(DeleteResourceCmd(self._project.data_tables, table, _refresh))
