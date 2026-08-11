"""ui/script_editor/var_table_panel.py — table GLOBALS/CONSTANTS de la sidebar Script Editor."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QAbstractItemView, QMenu, QInputDialog, QMessageBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import C, T, S, QSS
from core.project import GlobalVar, Constant
from .colors import _C_GLOBAL, _C_CONST


# Même grammaire que les autres viewers : fond du panneau, retrait de contenu,
# sélection périwinkle, en-tête de colonnes en intertitre discret.
_TBL_SS = f"""
QTableWidget {{
    background:{C.BG_BASE}; color:{C.TEXT_HI};
    border:none; gridline-color:transparent;
    font-family:{T.CODE}; font-size:{T.MD}px;
    outline:none;
    padding-left:{S.LG}px; padding-right:{S.SM}px;
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
}}
QHeaderView::section {{
    background:transparent; color:{C.TEXT_MUTED};
    border:none; border-bottom:1px solid {C.BORDER_DARK};
    font-family:{T.UI_STACK}; font-size:{T.XS}px;
    font-weight:700; letter-spacing:1px;
    padding:3px 4px;
}}
QTableWidget::item {{ padding:1px 4px; }}
QTableWidget::item:hover {{ background:{C.BG_PANEL}; }}
QComboBox {{
    background:{C.BG_INPUT}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
}}
QComboBox QAbstractItemView {{
    background:{C.BG_RAISED}; color:{C.TEXT_HI};
    selection-background-color:{C.BG_SEL}; selection-color:{C.ACCENT};
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
        value_col = "default" if kind == "global" else "value"
        # Colonne « persist » aux globals seulement : une constante ne change
        # jamais, rien n'a donc à en survivre à l'extinction de la console.
        self._cols = ["name", "type", value_col]
        if kind == "global":
            self._cols.append("persist")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Table : nom / type / défaut ou valeur (+ persist pour les globals)
        self._tbl = QTableWidget(0, len(self._cols))
        self._tbl.setStyleSheet(_TBL_SS)
        self._tbl.setHorizontalHeaderLabels(self._cols)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(self._cols)):
            self._tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self._tbl.setColumnWidth(1, 46)
        self._tbl.setColumnWidth(2, 46)
        if kind == "global":
            self._tbl.setColumnWidth(3, 52)
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
            self._append_row(e.name, e.type, str(value),
                             persist=getattr(e, "persist", False), entry=e)
        self._updating = False

    def _append_row(self, name="var", typ="int", default="0", persist=False,
                    entry=None):
        from PyQt6.QtWidgets import QComboBox
        row = self._tbl.rowCount()
        self._tbl.insertRow(row)
        self._tbl.setRowHeight(row, S.ROW)

        name_item = QTableWidgetItem(name)
        name_item.setForeground(QColor(self._color))
        # La ligne retient l'entrée dont elle vient, et non son rang : supprimer
        # une ligne décale toutes les suivantes, et un rang décalé ferait écrire
        # les valeurs d'une variable dans une autre.
        name_item.setData(Qt.ItemDataRole.UserRole, entry)
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

        # Persistance : la variable est-elle écrite en SRAM par save.write() ?
        # Une case à cocher sans texte — la colonne dit déjà ce qu'elle coche.
        if self._kind == "global":
            p_item = QTableWidgetItem()
            p_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                            | Qt.ItemFlag.ItemIsSelectable)
            p_item.setCheckState(Qt.CheckState.Checked if persist
                                 else Qt.CheckState.Unchecked)
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tbl.setItem(row, 3, p_item)

    def _add_var(self):
        if not self._project:
            return
        title = "New global variable" if self._kind == "global" else "New constant"
        name, ok = QInputDialog.getText(self, title, "Name:")
        if not ok or not name.strip():
            return
        entry = self._project.add_variable(self._kind, name)
        if entry is None:
            QMessageBox.warning(self, "Duplicate", f"“{name.strip()}” already exists.")
            return
        self._updating = True
        self._append_row(name.strip(), entry=entry)
        self._updating = False
        self.changed.emit()

    def _on_item_changed(self, item):
        if self._updating:
            return
        # Le NOM ne se recopie pas, il se renomme : c'est la seule colonne dont
        # la valeur est citée ailleurs (appels Lua, `$nom` dans un texte).
        if item.column() == 0:
            self._rename_from_cell(item)
            return
        self._sync_to_project()

    def _rename_from_cell(self, item):
        """Renomme via le projet, seul chemin qui suit les CITATIONS du nom.

        Écrire `entry.name` directement laisserait derrière chaque appel
        `global.get("ancien")` et chaque `$ancien` d'un texte — le build
        échouerait bien plus tard sur un `g_ancien` indéfini, sans rien qui
        ramène au renommage. `Project.rename_variable` réécrit les deux, refuse
        un doublon et dit combien de références il a touchées.

        (L'id, lui, ne bouge pas : les fichiers de DONNÉES citent la variable
        par id justement pour ne pas dépendre de son nom, cf. `_sync_to_project`.)"""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            # Ligne neuve, pas encore adossée à une entrée : rien à renommer.
            self._sync_to_project()
            return
        old, new = entry.name, item.text().strip()
        if new == old:
            return
        if self._project and self._project.rename_variable(self._kind, entry, new):
            self._updating = True
            item.setText(entry.name)   # normalisé par le projet (espaces retirés)
            self._updating = False
            self.changed.emit()
            return
        # Refusé : la cellule doit revenir au nom réel, sinon la table affiche
        # une variable qui n'existe sous ce nom nulle part.
        self._updating = True
        item.setText(old)
        self._updating = False
        if new and self._project and self._project.variable_name_taken(
                self._kind, new, exclude=entry):
            QMessageBox.warning(self, "Duplicate", f"“{new}” already exists.")

    def _sync_to_project(self):
        """Reporte la table dans le projet, en MODIFIANT les entrées existantes.

        Reconstruire des `GlobalVar` neufs à chaque édition perdrait tout ce que
        la table n'affiche pas — `id` en tête. Or l'id est l'identité opaque que
        citent les références de champ et les fichiers de sauvegarde : le
        régénérer à la volée casserait le lien de chaque référence stockée, sans
        rien qui le signale. Chaque ligne porte l'entrée dont elle vient ; une
        ligne qui n'en a pas est une ligne neuve."""
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
            entry = name_item.data(Qt.ItemDataRole.UserRole)
            if entry is None:
                entry = (Constant(name=name) if self._kind == "const"
                         else GlobalVar(name=name))
                name_item.setData(Qt.ItemDataRole.UserRole, entry)
            # Le nom n'est PAS recopié ici : il appartient à `_rename_from_cell`,
            # qui seul sait réécrire ce qui le cite. Une entrée neuve, elle, l'a
            # déjà reçu de son constructeur.
            entry.type = typ
            if self._kind == "const":
                entry.value = value
            else:
                entry.default = value
                p_item = self._tbl.item(row, 3)
                entry.persist = (p_item is not None
                                 and p_item.checkState() == Qt.CheckState.Checked)
            entries.append(entry)
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
        menu.setStyleSheet(QSS.menu)
        a_get = menu.addAction(self._snippet_get(name))
        a_set = menu.addAction(f'global.set("{name}", ...)') if self._kind == "global" else None
        menu.addSeparator()
        a_del = menu.addAction("Delete")
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
