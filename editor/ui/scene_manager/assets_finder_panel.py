
"""Panneau gauche — arbre projet avec sections collapsibles"""

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QToolButton, QInputDialog, QMessageBox,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QMenu, QAbstractItemView,
    QApplication, QSizePolicy, QLineEdit, QSpinBox,
)
from PyQt6.QtGui import QFont, QColor, QDrag, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QSize, QByteArray, QTimer

from ui.common.theme import T, C, QSS
from ui.common.widgets import W, FinderSection

from core.project import (
    Project, Actor, Prefab, Scene,
    MIME_PREFAB_TEMPLATE, MIME_SCRIPT,
)
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from core.history import get_history, DeleteResourceCmd, RemoveListItemCmd, RenameFileCmd, DeleteFileCmd
from ui.common.icons import get as _ico, COLOR_DEFAULT

PROJECTS_DIR = Path(__file__).parent.parent.parent.parent / "projects"

# ── Rôles QTreeWidgetItem ─────────────────────────────────────────
_ROLE_TYPE = Qt.ItemDataRole.UserRole
_ROLE_OBJ  = Qt.ItemDataRole.UserRole + 1
_ROLE_PATH = Qt.ItemDataRole.UserRole + 2

T_SCENE  = "scene"
T_ACTOR  = "actor"
T_PREFAB = "prefab"
T_SCRIPT = "script"
T_FOLDER = "folder"

# ── Thème ─── surfaces indigo centralisées (cf. project_theme_gba_redesign) ──
_BG      = C.BG_BASE      # fond de l'arbre / panneaux (indigo profond)
_HEADER  = C.BG_PANEL     # bandeaux de section (SCENES, PREFABS…)
_HOVER   = C.BG_HOVER     # survol de ligne
_SEL_BG  = C.BG_SEL       # fond sélection périwinkle
_SEL_FG  = C.ACCENT       # texte/liseré sélection
_TEXT    = C.TEXT_NORM
_DIM     = C.TEXT_DIM
# Plus de code couleur par type d'asset dans le finder : texte en tons de
# thème, icônes en neutre (COLOR_DEFAULT), distinction par forme d'icône.
# Le code couleur ne subsiste qu'aux niveaux locaux (scene canvas) et dans
# l'en-tête d'inspecteur (AssetHeaderBar).
_C_SCENE  = _TEXT
_C_PREFAB = _TEXT
_C_SCRIPT = _TEXT
_C_FOLDER = _DIM

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
            s_item.setForeground(0, QColor(_C_SCENE))
            s_item.setFont(0, QFont(T.MONO, T.MD, QFont.Weight.Normal))
            if is_active:
                s_item.setBackground(0, QColor(C.BG_SEL))

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
            item.setIcon(0, _ico("prefab", COLOR_DEFAULT))
            item.setToolTip(0, f"Instance de prefab : {actor.prefab_name}")
        else:
            item.setIcon(0, _ico("actor", COLOR_DEFAULT))
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
        self.itemClicked.connect(self._on_click)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.itemChanged.connect(self._on_item_changed)

    # ── Clic ────────────────────────────────────────────────────────

    def _on_click(self, item: QTreeWidgetItem, _col: int):
        """Simple clic sur un script → ScriptInspector (note + variables
        exposées). Les prefabs restent sur leur route existante (double-clic /
        menu contextuel « Éditer le prefab »)."""
        if item.data(0, _ROLE_TYPE) == T_SCRIPT:
            get_bus().select(item.data(0, _ROLE_OBJ))

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
                folder.setIcon(0, _ico("folder", COLOR_DEFAULT))
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
                    item.setIcon(0, _ico("prefab", COLOR_DEFAULT))
                    item.setText(0, entry.stem)
                    item.setData(0, _ROLE_TYPE, T_PREFAB)
                    item.setData(0, _ROLE_OBJ, obj)
                    item.setForeground(0, QColor(_C_PREFAB))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    icon_key = "script_lua" if entry.suffix == ".lua" else "script_file"
                    item.setIcon(0, _ico(icon_key, COLOR_DEFAULT))
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
        item.setIcon(0, _ico("prefab", COLOR_DEFAULT))
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

        def _refresh():
            current = new_path if new_path.exists() else path
            self.blockSignals(True)
            icon_key = "script_lua" if current.suffix == ".lua" else "script_file"
            item.setIcon(0, _ico(icon_key, COLOR_DEFAULT))
            item.setText(0, current.name)
            item.setData(0, _ROLE_OBJ, current)
            item.setData(0, _ROLE_PATH, current)
            self.blockSignals(False)

        get_history().push(RenameFileCmd(path, new_path, _refresh))

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
            self, "Supprimer", f"Supprimer '{path.name}' ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        get_history().push(DeleteFileCmd(path, lambda: self._panel.refresh()))

    def _new_subfolder(self, parent_item, parent_dir: Path):
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom :")
        if ok and name.strip():
            new_dir = parent_dir / name.strip()
            new_dir.mkdir(exist_ok=True)
            self._panel.refresh()


# ──────────────────────────────────────────────────────────────────
#  Liste GLOBALS / CONSTANTS — une ligne par variable
#  [ nom éditable ] [ bouton type ▾ ] [ champ valeur réactif au type ]
# ──────────────────────────────────────────────────────────────────

# Types déclarables + plage de valeur numérique associée (le champ valeur se
# règle dessus). "bool" est traité à part (toggle true/false, valeur 0/1).
_VAR_TYPES  = ["int", "bool", "u8", "u16", "s8", "s16"]
_VAR_RANGES = {
    "int": (-2147483648, 2147483647),
    "u8":  (0, 255),
    "u16": (0, 65535),
    "s8":  (-128, 127),
    "s16": (-32768, 32767),
}


def _clamp_to_type(value: int, type_: str) -> int:
    """Ramène `value` dans la plage du type (bool → 0/1)."""
    if type_ == "bool":
        return 1 if value else 0
    lo, hi = _VAR_RANGES.get(type_, _VAR_RANGES["int"])
    return max(lo, min(hi, value))


class _ValueSpin(QSpinBox):
    """Spinbox qui n'attrape la molette que s'il a déjà le focus — sinon la
    molette scrolle le panneau (les lignes vivent dans une QScrollArea)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class _VarRow(QWidget):
    """Une variable = une ligne. Le champ valeur est reconstruit quand le type
    change (bool ↔ numérique), d'où l'aspect « réactif »."""

    _ROW_H = 26

    def __init__(self, owner: "_ValuesList", entry):
        super().__init__()
        self._owner = owner
        self._entry = entry
        self.setFixedHeight(self._ROW_H)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 1, 6, 1)
        row.setSpacing(4)

        # Nom — édition en place, sans cadre (pas d'aspect champ de formulaire)
        self._name = QLineEdit(entry.name)
        self._name.setFont(QFont(T.MONO, T.MD))
        self._name.setFrame(False)
        self._name.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._name.setStyleSheet(
            f"QLineEdit{{background:transparent;border:none;color:{_TEXT};padding:0;}}"
            f"QLineEdit:focus{{border-bottom:1px solid {C.ACCENT};}}"
        )
        self._name.editingFinished.connect(self._commit_name)
        row.addWidget(self._name, 1)

        # Bouton type — menu déroulant des types déclarables
        self._type_btn = QToolButton()
        self._type_btn.setText(entry.type)
        self._type_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._type_btn.setFixedWidth(48)
        self._type_btn.setStyleSheet(
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;padding:1px 4px;"
            f"font-family:{T.MONO};font-size:{T.SM}px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};border-color:{C.ACCENT};}}"
            f"QToolButton::menu-indicator{{image:none;width:0;}}"
        )
        menu = QMenu(self._type_btn)
        menu.setFont(QFont(T.MONO, T.MD))
        for t in _VAR_TYPES:
            menu.addAction(t, lambda tt=t: self._on_type_selected(tt))
        self._type_btn.setMenu(menu)
        row.addWidget(self._type_btn)

        # Champ valeur — construit selon le type courant
        self._value_w: QWidget | None = None
        self._build_value()

    # ── Valeur : construction réactive ────────────────────────────
    def _build_value(self):
        if self._value_w is not None:
            self._layout_row().removeWidget(self._value_w)
            self._value_w.deleteLater()
            self._value_w = None

        val = self._owner.value_of(self._entry)
        if self._entry.type == "bool":
            w = QToolButton()
            w.setCheckable(True)
            w.setChecked(bool(val))
            w.setText("true" if val else "false")
            w.setFixedWidth(76)
            w.setStyleSheet(self._bool_qss())
            w.toggled.connect(self._on_bool_toggled)
        else:
            w = _ValueSpin()
            lo, hi = _VAR_RANGES.get(self._entry.type, _VAR_RANGES["int"])
            w.setRange(lo, hi)
            w.setValue(_clamp_to_type(val, self._entry.type))
            w.setFixedWidth(76)
            w.setAlignment(Qt.AlignmentFlag.AlignRight)
            w.setStyleSheet(
                f"QSpinBox{{color:{_TEXT};background:{C.BG_INPUT};"
                f"border:1px solid {C.BORDER};border-radius:3px;padding:1px 4px;"
                f"font-family:{T.MONO};font-size:{T.SM}px;}}"
                f"QSpinBox:focus{{border-color:{C.ACCENT};}}"
            )
            w.valueChanged.connect(self._commit_value)  # après setValue : pas de faux commit
        self._value_w = w
        self._layout_row().addWidget(w)

    def _bool_qss(self) -> str:
        # true = accent périwinkle (chrome), false = neutre discret
        return (
            f"QToolButton{{background:{C.BG_INPUT};border:1px solid {C.BORDER};"
            f"border-radius:3px;color:{C.TEXT_DIM};font-family:{T.MONO};"
            f"font-size:{T.SM}px;padding:1px 4px;}}"
            f"QToolButton:checked{{color:{C.ACCENT};border-color:{C.ACCENT};}}"
        )

    def _layout_row(self) -> QHBoxLayout:
        return self.layout()  # type: ignore[return-value]

    # ── Handlers ──────────────────────────────────────────────────
    def _on_type_selected(self, new_type: str):
        if new_type == self._entry.type:
            return
        self._entry.type = new_type
        # Recadrer la valeur dans la nouvelle plage puis reconstruire le champ.
        self._owner.set_value(self._entry, _clamp_to_type(
            self._owner.value_of(self._entry), new_type))
        self._type_btn.setText(new_type)
        self._build_value()
        self._owner.persist()

    def _on_bool_toggled(self, checked: bool):
        self._value_w.setText("true" if checked else "false")  # type: ignore[union-attr]
        self._owner.set_value(self._entry, 1 if checked else 0)
        self._owner.persist()

    def _commit_value(self, value: int):
        self._owner.set_value(self._entry, value)
        self._owner.persist()

    def _commit_name(self):
        new_name = self._name.text().strip()
        if new_name == self._entry.name:
            return
        if not self._owner.rename(self._entry, new_name):
            QMessageBox.warning(self, "Nom déjà utilisé", f"« {new_name} » existe déjà.")
            self._name.setText(self._entry.name)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))
        a_uses = menu.addAction("Voir les utilisations")
        menu.addSeparator()
        a_del = menu.addAction("Supprimer")
        action = menu.exec(e.globalPos())
        if action == a_del:
            self._owner.delete(self._entry)
        elif action == a_uses:
            self._owner.request_uses(self._entry)


class _ValuesList(QWidget):
    """
    Liste des variables partagée par les sections GLOBALS et CONSTANTS de
    l'Assets finder. kind="global" -> project.globals (GlobalVar, valeur
    mutable = "default") ; kind="const" -> project.constants (Constant,
    valeur figée). Une ligne = un `_VarRow`. Renommage en place, clic droit :
    Voir les utilisations / Supprimer.
    """

    def __init__(self, panel: "AssetsFinderPanel", kind: str, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._kind = kind   # "global" | "const"
        self._project: Optional[Project] = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 2, 0, 4)
        self._root.setSpacing(0)

        self._empty = QLabel("  aucune variable")
        self._empty.setFont(QFont(T.MONO, T.SM))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        self._root.addWidget(self._empty)

    def set_project(self, project: Project):
        self._project = project

    # ── Accès modèle (const=value / global=default) ───────────────
    def _entries(self) -> list:
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def value_of(self, entry) -> int:
        return entry.value if self._kind == "const" else entry.default

    def set_value(self, entry, value: int):
        if self._kind == "const":
            entry.value = value
        else:
            entry.default = value

    def rename(self, entry, new_name: str) -> bool:
        if not new_name or not self._project:
            return False
        return self._project.rename_variable(self._kind, entry, new_name)

    def request_uses(self, entry):
        self._panel.variable_uses_requested.emit(self._kind, entry.name)

    def persist(self):
        if self._project:
            self._project.save_variables()

    def delete(self, entry):
        if not self._project:
            return
        get_history().push(RemoveListItemCmd(
            self._entries(), entry, persist_fn=self.persist,
            label=f"Supprimer {entry.name}",
        ))
        self.reload()

    # ── Peuplement ────────────────────────────────────────────────
    def reload(self):
        while self._root.count() > 1:  # garde le label vide en position 0
            item = self._root.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        entries = self._entries()
        self._empty.setVisible(not entries)
        for entry in entries:
            self._root.addWidget(_VarRow(self, entry))
        n = max(len(entries), 1)
        self.setFixedHeight(n * _VarRow._ROW_H + 6)

    def add_new(self):
        if not self._project:
            return
        from core.command_dispatcher import unique_name
        base = "constante" if self._kind == "const" else "variable"
        name = unique_name(base, {e.name for e in self._entries()})
        if self._project.add_variable(self._kind, name) is None:
            return
        self.reload()
        # Focus + sélection du nom de la nouvelle ligne pour renommage immédiat
        last = self._root.itemAt(self._root.count() - 1)
        row = last.widget() if last else None
        if isinstance(row, _VarRow):
            QTimer.singleShot(0, lambda w=row._name: (w.setFocus(), w.selectAll()))


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
            f"background:{_HEADER}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 8, 0)
        self._project_lbl = QLabel("Aucun projet")
        self._project_lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        self._project_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        hl.addWidget(self._project_lbl, 1)
        _btn_qss = (
            f"QPushButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};"
            f"border-radius:3px;padding:0 7px;font-family:{T.MONO};font-size:{T.SM}px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
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
        finder_hdr.setStyleSheet(f"background:{_BG}; border-bottom:1px solid {C.BORDER_DARK};")
        fl = QHBoxLayout(finder_hdr)
        fl.setContentsMargins(8, 0, 0, 0)
        finder_lbl = QLabel("Project Viewer")
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
        self._sec_scenes  = FinderSection("SCENES")
        self._sec_prefabs = FinderSection("PREFABS")
        self._sec_scripts = FinderSection("SCRIPTS")
        self._sec_const   = FinderSection("CONSTANTS")
        self._sec_globals = FinderSection("GLOBALS")

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
                              f"border-bottom:1px solid {C.BORDER_DARK}; padding:3px 0;")
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
        self._tbl_const   = _ValuesList(self, "const")
        self._tbl_globals = _ValuesList(self, "global")
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
        from core.command_dispatcher import unique_name
        name = unique_name("Prefab", {p.name for p in self._project.prefabs})
        get_dispatcher().add_prefab(name)
        self.refresh()
        self.begin_rename_prefab(name)

    # ── Renommage inline d'un asset fraîchement créé (pas de pop-up) ──
    def _begin_rename(self, tree, name: str):
        """Sélectionne l'item nommé `name` dans `tree` et entre en édition
        (renommage en place), une fois le refresh terminé."""
        if QTreeWidgetItemIterator is None:
            return
        def go():
            it = QTreeWidgetItemIterator(tree)
            while it.value():
                item = it.value()
                if item.text(0) == name and bool(item.flags() & Qt.ItemFlag.ItemIsEditable):
                    tree.setCurrentItem(item)
                    tree.editItem(item, 0)
                    return
                it += 1
        QTimer.singleShot(0, go)

    def begin_rename_scene(self, name: str):
        self._begin_rename(self._tree_scenes, name)

    def begin_rename_prefab(self, name: str):
        self._begin_rename(self._tree_prefabs, name)

    def _show_add_script_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.addAction("Behavior Script", self._new_behavior_script)
        btn = self._sec_scripts._btn_add
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height())))

    def _new_actor_script(self):
        self._create_script("actor", self._project.scripts_actors_dir if self._project else None, "Actor")

    def _new_behavior_script(self):
        self._create_script("behavior", self._project.scripts_behaviors_dir if self._project else None, "Behavior")

    def _create_script(self, kind: str, directory, base: str):
        """Crée un script au nommage automatique (pas de pop-up) et l'ouvre."""
        if not self._project or directory is None:
            return
        from core.command_dispatcher import unique_name
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        directory.mkdir(parents=True, exist_ok=True)
        existing = {f.stem for f in directory.glob("*.lua")}
        name = unique_name(base, existing)
        sp = directory / f"{name}.lua"
        # Pas d'actor précis à ce stade (créé depuis l'Assets finder) — contexte
        # de composants vide, même template que component_editors/script.py.
        ctx = ScriptTemplateContext(kind=kind, name=name)
        sp.write_text(generate_script_template(ctx), encoding="utf-8")
        self._refresh_scripts()
        self.script_opened.emit(str(sp))
        if os.name == "nt":
            os.startfile(str(sp))

    @property
    def project(self) -> Project:
        return self._project
