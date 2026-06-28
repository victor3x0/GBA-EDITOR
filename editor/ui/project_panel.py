"""Panneau gauche — arbre projet style GB Studio."""

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QToolButton, QInputDialog, QMessageBox,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QMenu, QAbstractItemView,
    QApplication, QSizePolicy,
)
from PyQt6.QtGui import QFont, QColor, QDrag, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QSize, QByteArray

from ui.theme import T
from ui.widgets import W

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import Project, Actor, Prefab, Scene, MIME_PREFAB_TEMPLATE, MIME_SCRIPT
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from ui.icons import get as _ico, COLOR_ACTOR, COLOR_PREFAB, COLOR_SCRIPT, COLOR_FOLDER

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
_C_SCENE  = "#b48aff"   # violet  — scènes
_C_ACTOR  = "#4caf78"   # vert    — actors dans les scènes
_C_PREFAB = "#7ecfff"   # bleu    — prefabs
_C_SCRIPT = "#c48b3c"   # orange  — scripts
_C_FOLDER = "#666666"

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
#  Section collapsible
# ──────────────────────────────────────────────────────────────────

class _Section(QFrame):
    add_clicked = pyqtSignal()

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — le clic sur la zone texte/flèche toggle, les boutons sont indépendants
        hdr = QFrame()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background:{_HEADER}; border-top:1px solid #232323;"
            f"border-bottom:1px solid #232323;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 6, 0)

        # Zone cliquable pour toggle (flèche fixe + titre)
        toggle_area = QWidget()
        toggle_area.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ta_layout = QHBoxLayout(toggle_area)
        ta_layout.setContentsMargins(6, 0, 0, 0)
        ta_layout.setSpacing(6)

        self._arrow_lbl = QLabel("▾")
        self._arrow_lbl.setFixedWidth(12)
        self._arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow_lbl.setStyleSheet(f"color:{color}; font-size:{T.SM}pt; font-weight:bold; background:transparent;")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{color}; font-family:{T.MONO}; font-size:{T.SM}pt;"
            f"font-weight:bold; letter-spacing:1px; background:transparent;"
        )

        ta_layout.addWidget(self._arrow_lbl)
        ta_layout.addWidget(title_lbl, 1)

        toggle_area.mousePressEvent = lambda e: self._toggle()
        self._color = color
        self._title = title

        self._btn_add = W.btn_add("Ajouter un élément")
        self._btn_add.clicked.connect(self.add_clicked)

        btn_search = W.btn_search("Rechercher")

        hl.addWidget(toggle_area, 1)
        hl.addWidget(self._btn_add)
        hl.addWidget(btn_search)
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._arrow_lbl.setText("▾" if self._expanded else "▸")

    def set_widget(self, w: QWidget):
        """Remplace le contenu de la section par w."""
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._body_layout.addWidget(w)


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
    def __init__(self, panel: "ProjectPanel"):
        super().__init__()
        self._panel = panel
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.itemClicked.connect(self._on_click)
        self.customContextMenuRequested.connect(self._ctx_menu)

    # ── Peuplement ────────────────────────────────────────────────

    def populate(self, project: Project):
        self.blockSignals(True)
        self.clear()
        active = project.active_scene
        for i, scene in enumerate(project.scenes):
            s_item = QTreeWidgetItem(self)
            is_active = scene is active
            s_item.setText(0, f"  {scene.name}")
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
        else:
            item.setIcon(0, _ico("actor", COLOR_ACTOR))

        label = actor.name
        if actor.prefab_name:
            label += f"  ← {actor.prefab_name}"
        item.setText(0, label)
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
            menu.addAction("Renommer").triggered.connect(
                lambda: self._rename_scene(item, scene))
            menu.addSeparator()
            menu.addAction("Ajouter un actor").triggered.connect(
                self._panel.actor_add_requested)
            menu.addSeparator()
            menu.addAction("Supprimer la scène").triggered.connect(
                lambda: self._delete_scene(scene))

        elif typ == T_ACTOR:
            actor: Actor = item.data(0, _ROLE_OBJ)
            parent = item.parent()
            scene: Scene = parent.data(0, _ROLE_OBJ)
            menu.addAction("Renommer").triggered.connect(
                lambda: self._rename_actor(item, actor))
            menu.addSeparator()
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

    def _rename_scene(self, item, scene: Scene):
        name, ok = QInputDialog.getText(self, "Renommer la scène",
                                        "Nouveau nom :", text=scene.name)
        if ok and name.strip() and name.strip() != scene.name:
            scene.name = name.strip()
            item.setText(0, f"  {scene.name}")
            get_dispatcher().save_scene()

    def _delete_scene(self, scene: Scene):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer la scène '{scene.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        proj = self._panel._project
        was_active = proj.active_scene is scene
        proj.scenes.delete(scene)
        if was_active:
            proj.set_active_scene(0)
        get_dispatcher().save_all()
        self._panel.refresh()

    def _rename_actor(self, item, actor: Actor):
        name, ok = QInputDialog.getText(self, "Renommer l'actor",
                                        "Nouveau nom :", text=actor.name)
        if ok and name.strip() and name.strip() != actor.name:
            actor.name = name.strip()
            self._update_actor_item(item, actor)
            get_dispatcher().save_scene()
            get_dispatcher()._emit("actors_list_changed")

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
    def __init__(self, panel: "ProjectPanel", asset_type: str):
        super().__init__()
        self._panel = panel
        self._type  = asset_type   # T_PREFAB ou T_SCRIPT
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.customContextMenuRequested.connect(self._ctx_menu)

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
                else:
                    icon_key = "script_lua" if entry.suffix == ".lua" else "script_file"
                    item.setIcon(0, _ico(icon_key, COLOR_SCRIPT))
                    item.setText(0, entry.name)
                    item.setData(0, _ROLE_TYPE, T_SCRIPT)
                    item.setData(0, _ROLE_OBJ, entry)
                    item.setForeground(0, QColor(_C_SCRIPT))
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
            menu.addAction("Renommer").triggered.connect(
                lambda: self._rename_prefab(item, prefab))
            menu.addSeparator()
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
            menu.addAction("Renommer").triggered.connect(
                lambda: self._rename_script(item, path))
            menu.addSeparator()
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

    def _rename_prefab(self, item, prefab: Prefab):
        name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=prefab.name)
        if ok and name.strip() and name.strip() != prefab.name:
            proj = self._panel._project
            proj.prefabs.rename(prefab, name.strip())
            new_path = proj.prefabs._path(prefab.name)
            item.setIcon(0, _ico("prefab", COLOR_PREFAB))
            item.setText(0, prefab.name)
            item.setData(0, _ROLE_PATH, new_path)
            get_dispatcher().save_all()

    def _delete_prefab(self, prefab: Prefab):
        if QMessageBox.question(
            self, "Supprimer", f"Supprimer le prefab '{prefab.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        proj = self._panel._project
        proj.prefabs.delete(prefab)
        self._panel.refresh()

    def _rename_script(self, item, path: Path):
        name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom (sans extension) :",
                                        text=path.stem)
        if ok and name.strip():
            new_path = path.parent / f"{name.strip()}{path.suffix}"
            path.rename(new_path)
            icon_key = "script_lua" if new_path.suffix == ".lua" else "script_file"
            item.setIcon(0, _ico(icon_key, COLOR_SCRIPT))
            item.setText(0, new_path.name)
            item.setData(0, _ROLE_OBJ, new_path)
            item.setData(0, _ROLE_PATH, new_path)

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
#  Panneau principal
# ──────────────────────────────────────────────────────────────────

class ProjectPanel(QWidget):
    scene_selected        = pyqtSignal(int)
    actor_add_requested   = pyqtSignal()
    prefab_add_requested  = pyqtSignal()
    scene_add_requested   = pyqtSignal()
    script_opened         = pyqtSignal(str)
    project_created       = pyqtSignal(str, str)   # (name, path)
    project_opened        = pyqtSignal(str)         # (path)
    prefab_uses_requested = pyqtSignal(object)   # Prefab
    script_uses_requested = pyqtSignal(str)      # chemin absolu du script

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
        self._sec_scenes  = _Section("SCENES",    _C_SCENE)
        self._sec_prefabs = _Section("PREFABS",   _C_PREFAB)
        self._sec_scripts = _Section("SCRIPTS",   _C_SCRIPT)
        self._sec_const   = _Section("CONSTANTS", "#888888")
        self._sec_vars    = _Section("VARIABLES", "#888888")

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

        # Placeholders CONSTANTS / VARIABLES
        for sec in (self._sec_const, self._sec_vars):
            ph = QLabel("  (bientôt disponible)")
            ph.setFont(QFont(T.MONO, T.SM))
            ph.setStyleSheet(f"color:{_DIM}; padding:6px 8px;")
            sec.set_widget(ph)
            sec._toggle()  # fermé par défaut

        for sec in (self._sec_scenes, self._sec_prefabs, self._sec_scripts,
                    self._sec_const, self._sec_vars):
            cl.addWidget(sec)

        cl.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._project_lbl.setText(project.settings.name)
        self.refresh()

    def refresh(self):
        if not self._project:
            return
        self._refresh_scenes()
        self._refresh_prefabs()
        self._refresh_scripts()

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
