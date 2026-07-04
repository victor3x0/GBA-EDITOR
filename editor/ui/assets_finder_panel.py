"""Panneau gauche — arbre projet style GB Studio."""

import os
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QToolButton, QInputDialog, QMessageBox,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QMenu, QAbstractItemView,
    QApplication, QSizePolicy, QComboBox,
)
from PyQt6.QtGui import QFont, QColor, QDrag, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QSize, QByteArray

from ui.theme import T
from ui.widgets import W, FinderSection

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import (
    Project, Actor, Prefab, Scene, GlobalVar, Constant,
    MIME_PREFAB_TEMPLATE, MIME_SCRIPT,
)
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from core.history import get_history, DeleteResourceCmd, RemoveListItemCmd
from ui.icons import (
    get as _ico, COLOR_ACTOR, COLOR_PREFAB, COLOR_SCRIPT, COLOR_FOLDER,
    COLOR_SCENE, COLOR_GLOBAL, COLOR_CONST,
)

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# ── Rôles QTreeWidgetItem ─────────────────────────────────────────
_ROLE_TYPE = Qt.ItemDataRole.UserRole
_ROLE_OBJ  = Qt.ItemDataRole.UserRole + 1
_ROLE_PATH = Qt.ItemDataRole.UserRole + 2

T_SCENE  = "scene"
T_ACTOR  = "actor"
T_PREFAB = "prefab"
T_SCRIPT = "script"
T_FOLDER = "folder"

# ── Thème ─────────────────────────────────────────────────────────
_BG      = "#141414"
_HEADER  = "#1a1a1a"
_HOVER   = "#1e1e1e"
_SEL_BG  = "#1e3a2a"
_SEL_FG  = "#4caf78"
_TEXT    = "#999999"
_DIM     = "#555555"
# Couleurs de type d'objet — centralisées dans ui/icons.py (même source
# que les icônes _ico(...) ci-dessous, pour éviter tout écart icône/texte).
_C_SCENE  = COLOR_SCENE
_C_PREFAB = COLOR_PREFAB
_C_SCRIPT = COLOR_SCRIPT
_C_FOLDER = COLOR_FOLDER

_TREE_QSS = f"""
QTreeWidget {{
    background: {_BG};
    color: {_TEXT};
    border: none;
    font-family: monospace;
    font-size: {T.MD}px;
    outline: none;
    show-decoration-selected: 1;
}}
QTreeWidget::item {{
    height: 22px;
    padding-left: 2px;
    border: none;
}}
QTreeWidget::item:selected {{
    background: {_SEL_BG};
    color: {_SEL_FG};
    border-left: 2px solid {_SEL_FG};
}}
QTreeWidget::item:hover:!selected {{
    background: {_HOVER};
}}
QTreeWidget::branch {{
    background: {_BG};
}}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    border-image: none;
    image: none;
}}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {{
    border-image: none;
    image: none;
}}
"""




# ──────────────────────────────────────────────────────────────────
#  QTreeWidget commun
# ──────────────────────────────────────────────────────────────────

class _Tree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setAnimated(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Renommage en place : clic sur un item déjà sélectionné (pas de dialogue modal)
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self.setStyleSheet(_TREE_QSS)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Ajuster la hauteur au contenu
        self.model().rowsInserted.connect(self._fit)
        self.model().rowsRemoved.connect(self._fit)
        self.itemExpanded.connect(self._fit)
        self.itemCollapsed.connect(self._fit)

    def _fit(self):
        h = self.sizeHintForRow(0) if self.topLevelItemCount() else 0
        total = 0
        it = QTreeWidgetItem.__new__(QTreeWidgetItem)
        i = self.invisibleRootItem()
        stack = [i.child(n) for n in range(i.childCount())]
        while stack:
            item = stack.pop()
            total += 1
            if item.isExpanded():
                stack.extend(item.child(n) for n in range(item.childCount()))
        self.setFixedHeight(max(total * 22, 4))

    def sizeHint(self):
        return QSize(self.width(), self.minimumHeight())


# ──────────────────────────────────────────────────────────────────
#  Arbre SCENES  (scènes → acteurs, drag interne pour réordonner)
# ──────────────────────────────────────────────────────────────────

class _SceneTree(_Tree):
    def __init__(self, panel: "AssetsFinderPanel"):
        super().__init__()
        self._panel = panel
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.itemClicked.connect(self._on_click)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.itemChanged.connect(self._on_item_changed)

    # ── Peuplement ────────────────────────────────────────────────

    def populate(self, project: Project):
        self.blockSignals(True)
        self.clear()
        active = project.active_scene
        for i, scene in enumerate(project.scenes):
            s_item = QTreeWidgetItem(self)
            is_active = scene is active
            s_item.setText(0, scene.name)
            s_item.setFlags(s_item.flags() | Qt.ItemFlag.ItemIsEditable)
            s_item.setData(0, _ROLE_TYPE, T_SCENE)
            s_item.setData(0, _ROLE_OBJ, scene)
            s_item.setData(0, _ROLE_PATH, i)
            fg = QColor(_SEL_FG if is_active else _C_SCENE)
            s_item.setForeground(0, fg)
            s_item.setFont(0, QFont(T.MONO, T.MD,
                                    QFont.Weight.Bold if is_active else QFont.Weight.Normal))

            for actor in scene.actors:
                a_item = QTreeWidgetItem(s_item)
                a_item.setData(0, _ROLE_TYPE, T_ACTOR)
                a_item.setData(0, _ROLE_OBJ, actor)
                self._update_actor_item(a_item, actor)

            if is_active:
                s_item.setExpanded(True)

        self.blockSignals(False)
        self._fit()

    def _update_actor_item(self, item: QTreeWidgetItem, actor: Actor):
        if actor.prefab_name:
            item.setIcon(0, _ico("prefab", COLOR_PREFAB))
            item.setToolTip(0, f"Instance de prefab : {actor.prefab_name}")
        else:
            item.setIcon(0, _ico("actor", COLOR_ACTOR))
            item.setToolTip(0, "")

        # Le texte de l'item EST le texte édité en place (QTreeWidgetItem ne
        # permet pas de distinguer DisplayRole/EditRole) : on n'y met donc que
        # le nom, l'origine prefab passe par l'icône + le tooltip ci-dessus.
        item.setText(0, actor.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setForeground(0, QColor(_TEXT))

    def highlight_actor(self, actor: Actor):
        """Met en évidence l'actor correspondant dans l'arbre."""
        self.blockSignals(True)
        self.clearSelection()
        it = QTreeWidgetItemIterator(self)
        while it.value():
            node = it.value()
            if node.data(0, _ROLE_TYPE) == T_ACTOR and node.data(0, _ROLE_OBJ) is actor:
                node.setSelected(True)
                self.scrollToItem(node)
                break
            it += 1
        self.blockSignals(False)

    # ── Clic ──────────────────────────────────────────────────────

    def _on_click(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_SCENE:
            idx = item.data(0, _ROLE_PATH)
            self._panel.scene_selected.emit(idx)
        elif typ == T_ACTOR:
            get_bus().select(item.data(0, _ROLE_OBJ))

    # ── Drag & drop réordonnancement acteurs ──────────────────────

    def dropEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        dragged = self.currentItem()
        if (not dragged or not target
                or dragged.data(0, _ROLE_TYPE) != T_ACTOR):
            event.ignore()
            return

        # Accepter seulement si on reste dans la même scène
        src_parent = dragged.parent()
        dst_parent = target.parent() or target
        if dst_parent.data(0, _ROLE_TYPE) == T_ACTOR:
            dst_parent = dst_parent.parent()
        if src_parent is not dst_parent:
            event.ignore()
            return

        super().dropEvent(event)  # Qt réordonne visuellement

        # Synchroniser scene.actors avec l'ordre visuel
        scene: Scene = src_parent.data(0, _ROLE_OBJ)
        new_order = [
            src_parent.child(i).data(0, _ROLE_OBJ)
            for i in range(src_parent.childCount())
        ]
        scene.actors[:] = new_order
        get_dispatcher().save_scene()
        self._panel.project_panel_actors_reordered()

    # ── Menu contextuel ───────────────────────────────────────────

    def _ctx_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        typ = item.data(0, _ROLE_TYPE)
        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))

        if typ == T_SCENE:
            scene: Scene = item.data(0, _ROLE_OBJ)
            menu.addAction("Ajouter un actor").triggered.connect(
                self._panel.actor_add_requested)
            menu.addSeparator()
            menu.addAction("Supprimer la scène").triggered.connect(
                lambda: self._delete_scene(scene))

        elif typ == T_ACTOR:
            actor: Actor = item.data(0, _ROLE_OBJ)
            parent = item.parent()
            scene: Scene = parent.data(0, _ROLE_OBJ)
            menu.addAction("Monter tout en haut").triggered.connect(
                lambda: self._move_actor(scene, actor, "top"))
            menu.addAction("Monter").triggered.connect(
                lambda: self._move_actor(scene, actor, "up"))
            menu.addAction("Descendre").triggered.connect(
                lambda: self._move_actor(scene, actor, "down"))
            menu.addAction("Descendre tout en bas").triggered.connect(
                lambda: self._move_actor(scene, actor, "bottom"))
            menu.addSeparator()
            menu.addAction("Supprimer l'actor").triggered.connect(
                lambda: get_dispatcher().delete_actor(actor))

        menu.exec(self.viewport().mapToGlobal(pos))

    # ── Actions ───────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_SCENE:
            self._commit_rename_scene(item)
        elif typ == T_ACTOR:
            self._commit_rename_actor(item)

    def _commit_rename_scene(self, item: QTreeWidgetItem):
        scene: Scene = item.data(0, _ROLE_OBJ)
        new_name = item.text(0).strip()
        if not new_name or new_name == scene.name:
            self.blockSignals(True)
            item.setText(0, scene.name)
            self.blockSignals(False)
            return
        scene.name = new_name
        self.blockSignals(True)
        item.setText(0, scene.name)
        self.blockSignals(False)
        get_dispatcher().save_scene()

    def _commit_rename_actor(self, item: QTreeWidgetItem):
        actor: Actor = item.data(0, _ROLE_OBJ)
        new_name = item.text(0).strip()
        if not new_name or new_name == actor.name:
            self.blockSignals(True)
            self._update_actor_item(item, actor)
            self.blockSignals(False)
            return
        actor.name = new_name
        self.blockSignals(True)
        self._update_actor_item(item, actor)
        self.blockSignals(False)
        get_dispatcher().save_scene()
        get_dispatcher()._emit("actors_list_changed")

    def _delete_scene(self, scene: Scene):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer la scène '{scene.name}' ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        proj = self._panel._project
        was_active = proj.active_scene is scene

        def _refresh():
            if was_active:
                proj.set_active_scene(0)
            get_dispatcher().save_all()
            self._panel.refresh()

        get_history().push(DeleteResourceCmd(proj.scenes, scene, _refresh))

    def _move_actor(self, scene: Scene, actor: Actor, direction: str):
        actors = scene.actors
        idx = actors.index(actor)
        if direction == "top":
            actors.insert(0, actors.pop(idx))
        elif direction == "up" and idx > 0:
            actors[idx], actors[idx - 1] = actors[idx - 1], actors[idx]
        elif direction == "down" and idx < len(actors) - 1:
            actors[idx], actors[idx + 1] = actors[idx + 1], actors[idx]
        elif direction == "bottom":
            actors.append(actors.pop(idx))
        get_dispatcher().save_scene()
        self._panel.refresh()


# Import tardif pour QTreeWidgetItemIterator
try:
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
except ImportError:
    QTreeWidgetItemIterator = None


# ──────────────────────────────────────────────────────────────────
#  Arbre ASSETS (prefabs ou scripts) avec hiérarchie de dossiers
# ──────────────────────────────────────────────────────────────────

class _AssetTree(_Tree):
    def __init__(self, panel: "AssetsFinderPanel", asset_type: str):
        super().__init__()
        self._panel = panel
        self._type  = asset_type   # T_PREFAB ou T_SCRIPT
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.itemChanged.connect(self._on_item_changed)

    # ── Peuplement depuis le disque ───────────────────────────────

    def populate_dir(self, directory: Path, project: Project):
        self.blockSignals(True)
        self.clear()
        if directory and directory.exists():
            self._fill(self.invisibleRootItem(), directory, project)
        self.blockSignals(False)
        self._fit()
        self.expandAll()
        self._fit()

    def _fill(self, parent, directory: Path, project: Project):
        suffixes = {T_PREFAB: {".json"}, T_SCRIPT: {".lua", ".c"}}.get(self._type, set())
        entries = sorted(directory.iterdir(),
                         key=lambda p: (not p.is_dir(), p.name.lower()))
        for entry in entries:
            if entry.is_dir():
                folder = QTreeWidgetItem(parent)
                folder.setIcon(0, _ico("folder", COLOR_FOLDER))
                folder.setText(0, entry.name)
                folder.setData(0, _ROLE_TYPE, T_FOLDER)
                folder.setData(0, _ROLE_PATH, entry)
                folder.setForeground(0, QColor(_C_FOLDER))
                folder.setFont(0, QFont(T.MONO, T.MD))
                self._fill(folder, entry, project)
                folder.setExpanded(True)
            elif entry.suffix in suffixes:
                item = QTreeWidgetItem(parent)
                item.setData(0, _ROLE_PATH, entry)
                if self._type == T_PREFAB:
                    obj = project.get_prefab(entry.stem)
                    if not obj:
                        continue
                    item.setIcon(0, _ico("prefab", COLOR_PREFAB))
                    item.setText(0, entry.stem)
                    item.setData(0, _ROLE_TYPE, T_PREFAB)
                    item.setData(0, _ROLE_OBJ, obj)
                    item.setForeground(0, QColor(_C_PREFAB))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    icon_key = "script_lua" if entry.suffix == ".lua" else "script_file"
                    item.setIcon(0, _ico(icon_key, COLOR_SCRIPT))
                    item.setText(0, entry.name)
                    item.setData(0, _ROLE_TYPE, T_SCRIPT)
                    item.setData(0, _ROLE_OBJ, entry)
                    item.setForeground(0, QColor(_C_SCRIPT))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setFont(0, QFont(T.MONO, T.MD))

    # ── Drag MIME ─────────────────────────────────────────────────

    def startDrag(self, actions):
        item = self.currentItem()
        if not item:
            return
        typ = item.data(0, _ROLE_TYPE)
        mime = QMimeData()
        if typ == T_PREFAB:
            prefab = item.data(0, _ROLE_OBJ)
            mime.setData(MIME_PREFAB_TEMPLATE,
                         QByteArray(prefab.name.encode()))
        elif typ == T_SCRIPT:
            path: Path = item.data(0, _ROLE_OBJ)
            rel = self._panel._project.asset_rel(path) if self._panel._project else str(path)
            mime.setData(MIME_SCRIPT, QByteArray(str(rel).encode()))
        else:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    # ── Double-clic ───────────────────────────────────────────────

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_SCRIPT:
            path: Path = item.data(0, _ROLE_OBJ)
            self._panel.script_opened.emit(str(path))
        elif typ == T_PREFAB:
            prefab = item.data(0, _ROLE_OBJ)
            get_bus().select(prefab)

    # ── Menu contextuel ───────────────────────────────────────────

    def _ctx_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        typ  = item.data(0, _ROLE_TYPE)
        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))

        if typ == T_PREFAB:
            prefab: Prefab = item.data(0, _ROLE_OBJ)
            a_inst = menu.addAction("Instancier le prefab")
            a_inst.triggered.connect(
                lambda: get_dispatcher().instantiate_prefab(prefab.name, 60, 60))
            menu.addAction("Éditer le prefab").triggered.connect(
                lambda: get_bus().select(prefab))
            menu.addAction("Voir les instances").triggered.connect(
                lambda: self._panel.prefab_uses_requested.emit(prefab))
            menu.addSeparator()
            menu.addAction("Supprimer le prefab").triggered.connect(
                lambda: self._delete_prefab(prefab))

        elif typ == T_SCRIPT:
            path: Path = item.data(0, _ROLE_OBJ)
            menu.addAction("Éditer le script").triggered.connect(
                lambda: self._panel.script_opened.emit(str(path)))
            menu.addAction("Voir les utilisations").triggered.connect(
                lambda: self._panel.script_uses_requested.emit(str(path)))
            menu.addSeparator()
            menu.addAction("Supprimer le script").triggered.connect(
                lambda: self._delete_script(path))

        elif typ == T_FOLDER:
            folder: Path = item.data(0, _ROLE_PATH)
            menu.addAction("Nouveau sous-dossier").triggered.connect(
                lambda: self._new_subfolder(item, folder))

        menu.exec(self.viewport().mapToGlobal(pos))

    # ── Actions ───────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_PREFAB:
            self._commit_rename_prefab(item)
        elif typ == T_SCRIPT:
            self._commit_rename_script(item)

    def _commit_rename_prefab(self, item: QTreeWidgetItem):
        prefab: Prefab = item.data(0, _ROLE_OBJ)
        new_name = item.text(0).strip()
        if not new_name or new_name == prefab.name:
            self.blockSignals(True)
            item.setText(0, prefab.name)
            self.blockSignals(False)
            return
        proj = self._panel._project
        proj.prefabs.rename(prefab, new_name)
        new_path = proj.prefabs._path(prefab.name)
        self.blockSignals(True)
        item.setIcon(0, _ico("prefab", COLOR_PREFAB))
        item.setText(0, prefab.name)
        item.setData(0, _ROLE_PATH, new_path)
        self.blockSignals(False)
        get_dispatcher().save_all()

    def _commit_rename_script(self, item: QTreeWidgetItem):
        path: Path = item.data(0, _ROLE_OBJ)
        new_text = item.text(0).strip()
        if not new_text or new_text == path.name:
            self.blockSignals(True)
            item.setText(0, path.name)
            self.blockSignals(False)
            return
        # QTreeWidgetItem affiche le nom complet (avec extension) et c'est ce
        # texte qui est édité en place : si l'utilisateur n'a pas tapé une
        # extension de script reconnue, on conserve l'extension d'origine
        # plutôt que de la perdre silencieusement.
        if Path(new_text).suffix in (".lua", ".c"):
            new_path = path.parent / new_text
        else:
            new_path = path.parent / f"{new_text}{path.suffix}"
        if new_path == path:
            return
        path.rename(new_path)
        icon_key = "script_lua" if new_path.suffix == ".lua" else "script_file"
        self.blockSignals(True)
        item.setIcon(0, _ico(icon_key, COLOR_SCRIPT))
        item.setText(0, new_path.name)
        item.setData(0, _ROLE_OBJ, new_path)
        item.setData(0, _ROLE_PATH, new_path)
        self.blockSignals(False)

    def _delete_prefab(self, prefab: Prefab):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer le prefab '{prefab.name}' ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        proj = self._panel._project
        get_history().push(DeleteResourceCmd(
            proj.prefabs, prefab,
            lambda: self._panel.refresh(),
        ))

    def _delete_script(self, path: Path):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer '{path.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        path.unlink(missing_ok=True)
        self._panel.refresh()

    def _new_subfolder(self, parent_item, parent_dir: Path):
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom :")
        if ok and name.strip():
            new_dir = parent_dir / name.strip()
            new_dir.mkdir(exist_ok=True)
            self._panel.refresh()


# ──────────────────────────────────────────────────────────────────
#  Table GLOBALS / CONSTANTS (nom / type / valeur)
# ──────────────────────────────────────────────────────────────────

class _ValuesTable(QWidget):
    """
    Table nom/type/valeur partagée par les sections GLOBALS et CONSTANTS de
    l'Assets finder. kind="global" -> project.globals (GlobalVar, valeur
    mutable = "default") ; kind="const" -> project.constants (Constant,
    valeur figée). Renommage en place (clic sur le nom déjà sélectionné,
    même mécanisme que les autres finders), clic droit : Supprimer / Voir
    les utilisations.
    """

    _TYPES = ["int", "bool", "u8", "u16", "s8", "s16"]

    def __init__(self, panel: "AssetsFinderPanel", kind: str, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._kind = kind   # "global" | "const"
        self._project: Optional[Project] = None
        self._color = COLOR_GLOBAL if kind == "global" else COLOR_CONST

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["nom", "type", "valeur"])
        self._tree.setColumnWidth(0, 110)
        self._tree.setColumnWidth(1, 50)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(0)
        self._tree.setStyleSheet(_TREE_QSS)
        self._tree.setFrameShape(QFrame.Shape.NoFrame)
        self._tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.customContextMenuRequested.connect(self._ctx_menu)
        layout.addWidget(self._tree)

    def set_project(self, project: Project):
        self._project = project

    def _entries(self) -> list:
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def _value_of(self, entry) -> int:
        return entry.value if self._kind == "const" else entry.default

    def _set_value(self, entry, value: int):
        if self._kind == "const":
            entry.value = value
        else:
            entry.default = value

    def reload(self):
        self._tree.blockSignals(True)
        self._tree.clear()
        for entry in self._entries():
            self._add_row(entry)
        self._tree.blockSignals(False)
        h = self._tree.sizeHintForRow(0) if self._tree.topLevelItemCount() else 0
        self._tree.setFixedHeight(max(self._tree.topLevelItemCount() * 22 + 24, 24))

    def _add_row(self, entry):
        item = QTreeWidgetItem([entry.name, "", str(self._value_of(entry))])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, Qt.ItemDataRole.UserRole, entry)
        item.setForeground(0, QColor(self._color))
        self._tree.addTopLevelItem(item)
        combo = QComboBox()
        combo.addItems(self._TYPES)
        combo.setCurrentText(entry.type)
        combo.currentTextChanged.connect(lambda t, e=entry: self._on_type_changed(e, t))
        self._tree.setItemWidget(item, 1, combo)

    def _on_type_changed(self, entry, new_type: str):
        entry.type = new_type
        self._persist()

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        if col == 0:
            self._commit_rename(item, entry)
        elif col == 2:
            self._commit_value(item, entry)

    def _commit_rename(self, item: QTreeWidgetItem, entry):
        new_name = item.text(0).strip()
        if not new_name or new_name == entry.name:
            self._tree.blockSignals(True)
            item.setText(0, entry.name)
            self._tree.blockSignals(False)
            return
        if any(e is not entry and e.name == new_name for e in self._entries()):
            QMessageBox.warning(self, "Nom déjà utilisé", f"« {new_name} » existe déjà.")
            self._tree.blockSignals(True)
            item.setText(0, entry.name)
            self._tree.blockSignals(False)
            return
        entry.name = new_name
        self._persist()

    def _commit_value(self, item: QTreeWidgetItem, entry):
        try:
            value = int(item.text(2).strip())
        except ValueError:
            value = self._value_of(entry)
        self._set_value(entry, value)
        self._tree.blockSignals(True)
        item.setText(2, str(value))
        self._tree.blockSignals(False)
        self._persist()

    def _persist(self):
        if self._project:
            self._project.save_settings()

    def _ctx_menu(self, pos: QPoint):
        item = self._tree.itemAt(pos)
        if not item:
            return
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))
        a_uses = menu.addAction("Voir les utilisations")
        menu.addSeparator()
        a_del = menu.addAction("Supprimer")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == a_del:
            self._delete(entry)
        elif action == a_uses:
            self._panel.variable_uses_requested.emit(self._kind, entry.name)

    def _delete(self, entry):
        if not self._project:
            return
        get_history().push(RemoveListItemCmd(
            self._entries(), entry, persist_fn=self._persist,
            label=f"Supprimer {entry.name}",
        ))
        self.reload()

    def add_new(self):
        if not self._project:
            return
        title = "Nouvelle constante" if self._kind == "const" else "Nouvelle variable globale"
        name, ok = QInputDialog.getText(self, title, "Nom :")
        name = name.strip() if ok else ""
        if not name:
            return
        if any(e.name == name for e in self._entries()):
            QMessageBox.warning(self, "Nom déjà utilisé", f"« {name} » existe déjà.")
            return
        if self._kind == "const":
            self._project.constants.append(Constant(name=name))
        else:
            self._project.globals.append(GlobalVar(name=name))
        self._persist()
        self.reload()


# ──────────────────────────────────────────────────────────────────
#  Panneau principal
# ──────────────────────────────────────────────────────────────────

class AssetsFinderPanel(QWidget):
    scene_selected        = pyqtSignal(int)
    actor_add_requested   = pyqtSignal()
    prefab_add_requested  = pyqtSignal()
    scene_add_requested   = pyqtSignal()
    script_opened         = pyqtSignal(str)
    project_created       = pyqtSignal(str, str)   # (name, path)
    project_opened        = pyqtSignal(str)         # (path)
    prefab_uses_requested = pyqtSignal(object)   # Prefab
    script_uses_requested = pyqtSignal(str)      # chemin absolu du script
    variable_uses_requested = pyqtSignal(str, str)   # (kind: "global"|"const", name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Project = None
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{_BG};")
        self._setup_ui()
        get_bus().changed.connect(self.on_selection)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header projet ──────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"background:{_HEADER}; border-bottom:1px solid #2a2a2a;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 8, 0)
        self._project_lbl = QLabel("Aucun projet")
        self._project_lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        self._project_lbl.setStyleSheet("color:#ccc;")
        hl.addWidget(self._project_lbl, 1)
        _btn_qss = (
            "QPushButton{color:#777;background:#222;border:1px solid #333;"
            f"border-radius:3px;padding:0 7px;font-family:{T.MONO};font-size:{T.SM}px;}}"
            "QPushButton:hover{color:#ccc;background:#2a2a2a;}"
        )
        btn_new  = QPushButton("Nouveau"); btn_new.setFixedHeight(22)
        btn_open = QPushButton("Ouvrir");  btn_open.setFixedHeight(22)
        for b in (btn_new, btn_open):
            b.setStyleSheet(_btn_qss)
        btn_new.clicked.connect(self._prompt_new)
        btn_open.clicked.connect(self._prompt_open)
        hl.addWidget(btn_new); hl.addWidget(btn_open)
        layout.addWidget(hdr)

        # ── Bandeau "finder" (identité du panneau, cohérent avec les
        #    autres écrans : Sprite finder / Script finder / Sound finder) ──
        finder_hdr = QFrame()
        finder_hdr.setFixedHeight(20)
        finder_hdr.setStyleSheet(f"background:{_BG}; border-bottom:1px solid #232323;")
        fl = QHBoxLayout(finder_hdr)
        fl.setContentsMargins(8, 0, 0, 0)
        finder_lbl = QLabel("ASSETS FINDER")
        finder_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        finder_lbl.setStyleSheet(f"color:{_DIM}; letter-spacing:1px;")
        fl.addWidget(finder_lbl)
        layout.addWidget(finder_hdr)

        # ── Scroll area ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG}; border:none;")
        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Sections
        self._sec_scenes  = FinderSection("SCENES",    _C_SCENE)
        self._sec_prefabs = FinderSection("PREFABS",   _C_PREFAB)
        self._sec_scripts = FinderSection("SCRIPTS",   _C_SCRIPT)
        self._sec_const   = FinderSection("CONSTANTS", COLOR_CONST)
        self._sec_globals = FinderSection("GLOBALS",   COLOR_GLOBAL)

        self._sec_scenes.add_clicked.connect(self.scene_add_requested)
        self._sec_prefabs.add_clicked.connect(self._add_prefab)
        self._sec_scripts.add_clicked.connect(self._show_add_script_menu)

        # Trees
        self._tree_scenes    = _SceneTree(self)
        self._tree_prefabs   = _AssetTree(self, T_PREFAB)
        self._tree_scripts_a = _AssetTree(self, T_SCRIPT)  # actors
        self._tree_scripts_s = _AssetTree(self, T_SCRIPT)  # scenes
        self._tree_scripts_b = _AssetTree(self, T_SCRIPT)  # behaviors

        self._sec_scenes.set_widget(self._tree_scenes)
        self._sec_prefabs.set_widget(self._tree_prefabs)

        # Body SCRIPTS : trois sous-sections actors / scenes / behaviors
        scripts_body = QWidget()
        scripts_body.setStyleSheet(f"background:{_BG};")
        sb_layout = QVBoxLayout(scripts_body)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        def _sub_label(text):
            lbl = QLabel(f"  {text}")
            lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color:{_DIM}; background:{_HEADER};"
                              f"border-bottom:1px solid #232323; padding:3px 0;")
            lbl.setFixedHeight(18)
            return lbl

        sb_layout.addWidget(_sub_label("ACTORS"))
        sb_layout.addWidget(self._tree_scripts_a)
        sb_layout.addWidget(_sub_label("SCENES"))
        sb_layout.addWidget(self._tree_scripts_s)
        sb_layout.addWidget(_sub_label("BEHAVIORS"))
        sb_layout.addWidget(self._tree_scripts_b)
        self._sec_scripts.set_widget(scripts_body)

        # CONSTANTS / GLOBALS : table nom/type/valeur
        self._tbl_const   = _ValuesTable(self, "const")
        self._tbl_globals = _ValuesTable(self, "global")
        self._sec_const.set_widget(self._tbl_const)
        self._sec_globals.set_widget(self._tbl_globals)
        self._sec_const.add_clicked.connect(self._tbl_const.add_new)
        self._sec_globals.add_clicked.connect(self._tbl_globals.add_new)
        self._sec_const._toggle()    # fermé par défaut
        self._sec_globals._toggle()  # fermé par défaut

        for sec in (self._sec_scenes, self._sec_prefabs, self._sec_scripts,
                    self._sec_const, self._sec_globals):
            cl.addWidget(sec)

        cl.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._project_lbl.setText(project.settings.name)
        self._tbl_const.set_project(project)
        self._tbl_globals.set_project(project)
        self.refresh()

    def refresh(self):
        if not self._project:
            return
        self._refresh_scenes()
        self._refresh_prefabs()
        self._refresh_scripts()
        self._tbl_const.reload()
        self._tbl_globals.reload()

    def _refresh_scenes(self):
        self._tree_scenes.populate(self._project)

    def _refresh_prefabs(self):
        prefab_dir = self._project.root / "project" / "prefab"
        self._tree_prefabs.populate_dir(prefab_dir, self._project)

    def _refresh_scripts(self):
        self._tree_scripts_a.populate_dir(self._project.scripts_actors_dir, self._project)
        self._tree_scripts_s.populate_dir(self._project.scripts_scenes_dir, self._project)
        self._tree_scripts_b.populate_dir(self._project.scripts_behaviors_dir, self._project)

    # ── Sélection bus ─────────────────────────────────────────────

    def on_selection(self, obj):
        if isinstance(obj, Actor) and QTreeWidgetItemIterator:
            self._tree_scenes.highlight_actor(obj)

    def project_panel_actors_reordered(self):
        self._refresh_scenes()

    # ── Projets ───────────────────────────────────────────────────

    def _prompt_new(self):
        name, ok = QInputDialog.getText(self, "Nouveau projet", "Nom :")
        if ok and name.strip():
            path = PROJECTS_DIR / name.strip()
            if path.exists():
                QMessageBox.warning(self, "Erreur", f"'{name}' existe déjà.")
                return
            self.project_created.emit(name.strip(), str(path))

    def _prompt_open(self):
        path = QFileDialog.getExistingDirectory(
            self, "Ouvrir un projet", str(PROJECTS_DIR))
        if path:
            self.project_opened.emit(path)

    def _add_prefab(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(self, "Nouveau prefab", "Nom :")
        if ok and name.strip():
            get_dispatcher().add_prefab(name.strip())
            self.refresh()

    def _show_add_script_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1e1e1e;color:#ccc;border:1px solid #333;border-radius:4px;padding:4px;}"
            "QMenu::item{padding:5px 16px 5px 10px;border-radius:3px;}"
            "QMenu::item:selected{background:#2a3a2a;color:#4caf78;}"
        )
        menu.addAction("Behavior Script", self._new_behavior_script)
        btn = self._sec_scripts._btn_add
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))

    def _new_actor_script(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(
            self, "Nouveau script actor", "Nom (sans .lua) :")
        if ok and name.strip():
            d = self._project.scripts_actors_dir
            d.mkdir(parents=True, exist_ok=True)
            sp = d / f"{name.strip()}.lua"
            if not sp.exists():
                sp.write_text(
                    f"-- Actor script : {name.strip()}\n"
                    f"-- Attache ce script via ScriptComponent dans l'inspector.\n\n"
                    f"function onSpawn()\nend\n\n"
                    f"function onUpdate()\nend\n",
                    encoding="utf-8"
                )
            self._refresh_scripts()
            self.script_opened.emit(str(sp))
            if os.name == "nt":
                os.startfile(str(sp))

    def _new_behavior_script(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(
            self, "Nouveau script behavior", "Nom (sans .lua) :")
        if ok and name.strip():
            d = self._project.scripts_behaviors_dir
            d.mkdir(parents=True, exist_ok=True)
            sp = d / f"{name.strip()}.lua"
            if not sp.exists():
                sp.write_text(
                    f"-- Behavior : {name.strip()}\n"
                    f"-- Module réutilisable. Usage : local M = require('behaviors/{name.strip()}')\n\n"
                    f"local M = {{}}\n\n"
                    f"function M.update(actor)\nend\n\n"
                    f"return M\n",
                    encoding="utf-8"
                )
            self._refresh_scripts()
            self.script_opened.emit(str(sp))
            if os.name == "nt":
                os.startfile(str(sp))

    @property
    def project(self) -> Project:
        return self._project
