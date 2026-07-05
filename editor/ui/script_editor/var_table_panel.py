"""ui/script_editor/var_table_panel.py — table GLOBALS/CONSTANTS de la sidebar Script Editor."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QAbstractItemView, QMenu, QInputDialog, QMessageBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import C, T
from core.project import GlobalVar, Constant
from .colors import _C_GLOBAL, _C_CONST


_TBL_SS = f"""
QTableWidget {{
    background:{C.BG_PANEL}; color:{C.TEXT_HI};
    border:none; gridline-color:{C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
    selection-background-color:#264f78; selection-color:#ffffff;
}}
QHeaderView::section {{
    background:{C.BG_PANEL}; color:{C.TEXT_DIM};
    border:none; border-bottom:1px solid {C.BORDER};
    font-family:{T.MONO}; font-size:{T.XS}px;
    padding:2px 4px;
}}
QTableWidget::item {{ padding:1px 4px; }}
QComboBox {{
    background:{C.BG_PANEL}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
}}
QComboBox QAbstractItemView {{
    background:{C.BG_RAISED}; color:{C.TEXT_HI};
    selection-background-color:#264f78;
}}
"""


class VarTablePanel(QWidget):
    """
    Tableau nom/type/valeur pour GLOBALS ou CONSTANTS, déclarées dans le
    projet. Double-clic sur une ligne → insère un snippet get (et set pour
    les globals) au curseur. Clic droit → même menu + Supprimer.

    Pas de header propre : posé via FinderSection.set_widget() pour la même
    apparence (flèche + titre coloré + boutons +/recherche) que les autres
    finders — le bouton "+" de la section appelle add_var() directement.
    """
    snippet_requested = pyqtSignal(str)
    changed           = pyqtSignal()   # pour notifier le projet de sauvegarder

    def __init__(self, kind: str = "global", parent=None):
        super().__init__(parent)
        self._kind = kind   # "global" | "const"
        self._project = None
        self._updating = False
        self._label = "GLOBALS" if kind == "global" else "CONSTANTS"
        self._color = _C_GLOBAL if kind == "global" else _C_CONST
        value_col = "défaut" if kind == "global" else "valeur"
        self._cols = ["nom", "type", value_col]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Table (3 colonnes : nom / type / défaut ou valeur)
        self._tbl = QTableWidget(0, 3)
        self._tbl.setStyleSheet(_TBL_SS)
        self._tbl.setHorizontalHeaderLabels(self._cols)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tbl.setColumnWidth(1, 46)
        self._tbl.setColumnWidth(2, 46)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._ctx_menu)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.cellDoubleClicked.connect(self._on_double_click)
        self._tbl.setMinimumHeight(80)
        self._tbl.setMaximumHeight(240)
        root.addWidget(self._tbl)

    def _entries(self):
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def set_project(self, project):
        self._project = project
        self._reload()

    def _reload(self):
        self._updating = True
        self._tbl.setRowCount(0)
        for e in self._entries():
            value = e.value if self._kind == "const" else e.default
            self._append_row(e.name, e.type, str(value))
        self._updating = False

    def _append_row(self, name="var", typ="int", default="0"):
        from PyQt6.QtWidgets import QComboBox
        row = self._tbl.rowCount()
        self._tbl.insertRow(row)
        self._tbl.setRowHeight(row, 20)

        name_item = QTableWidgetItem(name)
        name_item.setForeground(QColor(self._color))
        self._tbl.setItem(row, 0, name_item)

        combo = QComboBox()
        combo.addItems(["int", "bool", "u8", "u16", "s8", "s16"])
        combo.setCurrentText(typ)
        combo.setStyleSheet(_TBL_SS)
        combo.currentTextChanged.connect(lambda _, r=row: self._sync_to_project())
        self._tbl.setCellWidget(row, 1, combo)

        default_item = QTableWidgetItem(str(default))
        default_item.setForeground(QColor("#b5cea8"))
        self._tbl.setItem(row, 2, default_item)

    def _add_var(self):
        if not self._project:
            return
        title = "Nouvelle variable globale" if self._kind == "global" else "Nouvelle constante"
        name, ok = QInputDialog.getText(self, title, "Nom :")
        if not ok or not name.strip():
            return
        if self._project.add_variable(self._kind, name) is None:
            QMessageBox.warning(self, "Doublon", f"« {name.strip()} » existe déjà.")
            return
        self._updating = True
        self._append_row(name.strip())
        self._updating = False
        self.changed.emit()

    def _on_item_changed(self, item):
        if self._updating:
            return
        self._sync_to_project()

    def _sync_to_project(self):
        if not self._project or self._updating:
            return
        from core.project import GlobalVar, Constant
        entries = []
        for row in range(self._tbl.rowCount()):
            name_item = self._tbl.item(row, 0)
            combo     = self._tbl.cellWidget(row, 1)
            val_item  = self._tbl.item(row, 2)
            if name_item is None:
                continue
            name  = name_item.text().strip()
            typ   = combo.currentText() if combo else "int"
            value = int(val_item.text() or "0") if val_item else 0
            if not name:
                continue
            if self._kind == "const":
                entries.append(Constant(name=name, type=typ, value=value))
            else:
                entries.append(GlobalVar(name=name, type=typ, default=value))
        if self._kind == "const":
            self._project.constants = entries
        else:
            self._project.globals = entries
        self._project.save_variables()
        self.changed.emit()

    def _snippet_get(self, name: str) -> str:
        return f'const.get("{name}")' if self._kind == "const" else f'global.get("{name}")'

    def _on_double_click(self, row, col):
        name_item = self._tbl.item(row, 0)
        if name_item:
            self.snippet_requested.emit(self._snippet_get(name_item.text()))

    def _ctx_menu(self, pos: QPoint):
        row = self._tbl.rowAt(pos.y())
        if row < 0:
            return
        name_item = self._tbl.item(row, 0)
        if not name_item:
            return
        name = name_item.text()
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_HI};border:1px solid {C.BORDER};}}"
            f"QMenu::item:selected{{background:{C.BG_SEL};}}"
        )
        a_get = menu.addAction(self._snippet_get(name))
        a_set = menu.addAction(f'global.set("{name}", ...)') if self._kind == "global" else None
        menu.addSeparator()
        a_del = menu.addAction("Supprimer")
        action = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if action == a_get:
            self.snippet_requested.emit(self._snippet_get(name))
        elif a_set is not None and action == a_set:
            self.snippet_requested.emit(f'global.set("{name}", )')
        elif action == a_del:
            self._delete_row(row)

    def _delete_row(self, row):
        self._tbl.removeRow(row)
        self._sync_to_project()
