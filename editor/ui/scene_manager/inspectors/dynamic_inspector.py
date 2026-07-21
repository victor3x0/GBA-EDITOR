"""DynamicInspector — remplace le QTabWidget Scene/Actor, route vers le bon panneau."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T
from .actor_inspector import ActorInspector
from .scene_inspector import SceneInspector
from .camera_inspector import CameraInspector
from .project_inspector import ProjectInspector
from .script_inspector import ScriptInspector
from .uses_inspectors import PrefabUsesInspector, ScriptUsesInspector, VariableUsesInspector


class DynamicInspector(QWidget):
    """
    Inspector contextuel sans onglets.
    Affiche automatiquement le bon panneau selon la selection :
      - rien        → message d'aide
      - scene       → SceneInspector (nom + BG slots)
      - actor       → ActorInspector (transform + components)
      - prefab      → ActorInspector (components seulement)
      - prefab uses → PrefabUsesInspector
    """
    changed       = pyqtSignal()
    actor_changed = pyqtSignal(object)   # Actor | None — payload propre pour window.py
    slot_assigned = pyqtSignal(int, str)

    _MODE_EMPTY       = 0
    _MODE_SCENE       = 1
    _MODE_ACTOR       = 2
    _MODE_CAMERA      = 3
    _MODE_PREFAB_USES = 4
    _MODE_SCRIPT_USES = 5
    _MODE_VARIABLE_USES = 6
    _MODE_PROJECT     = 7
    _MODE_SCRIPT      = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None   # mis à jour via set_project()
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self.setMinimumWidth(200)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Bandeau contextuel coloré — composant partagé (voir ui/common/widgets.py),
        # même template/couleurs/renommage que Sprite Editor, Sound Mixer, Script Editor.
        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_header_rename)
        self._header_mode = "empty"
        main.addWidget(self._header)

        self._stack = QStackedWidget()
        main.addWidget(self._stack, 1)

        # 0 — vide
        empty_w = QWidget()
        empty_w.setStyleSheet(f"background:{C.BG_PANEL};")
        el = QVBoxLayout(empty_w)
        hint = QLabel("Selectionnez une scene\nou un actor pour\nafficher ses proprietes")
        hint.setFont(QFont(T.MONO, T.MD))
        hint.setStyleSheet(f"color:{C.BORDER_MID};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addStretch(); el.addWidget(hint); el.addStretch()
        self._stack.addWidget(empty_w)

        # 1 — scene
        self._scene_insp = SceneInspector()
        self._scene_insp.changed.connect(self.changed)
        self._scene_insp.slot_assigned.connect(self.slot_assigned)
        self._stack.addWidget(self._scene_insp)

        # 2 — actor / prefab
        self._actor_insp = ActorInspector()
        self._actor_insp.changed.connect(self._on_actor_insp_changed)
        self._stack.addWidget(self._actor_insp)

        # 3 — caméra
        self._camera_insp = CameraInspector()
        self._camera_insp.changed.connect(self.changed)
        self._stack.addWidget(self._camera_insp)

        # 4 — prefab uses
        self._uses_insp = PrefabUsesInspector()
        self._uses_insp.edit_requested.connect(
            lambda p: self.show_prefab(p, self._project))
        self._stack.addWidget(self._uses_insp)

        # 5 — script uses
        self._script_uses_insp = ScriptUsesInspector()
        self._script_uses_insp.edit_requested.connect(self._on_script_edit_requested)
        self._stack.addWidget(self._script_uses_insp)

        # 6 — global/constant uses
        self._variable_uses_insp = VariableUsesInspector()
        self._variable_uses_insp.edit_requested.connect(self._on_script_edit_requested)
        self._stack.addWidget(self._variable_uses_insp)

        # 7 — projet (mode par défaut : aucune sélection)
        self._project_insp = ProjectInspector()
        self._stack.addWidget(self._project_insp)

        # 8 — script (asset .lua sélectionné dans le Project Viewer)
        self._script_insp = ScriptInspector()
        self._stack.addWidget(self._script_insp)
        self._current_script_path = None   # utilisé par _on_header_rename

        self._stack.setCurrentIndex(self._MODE_EMPTY)

        from core.selection_bus import get_bus
        get_bus().changed.connect(self.on_selection)

    def _on_actor_insp_changed(self):
        """Relaye changed ET émet actor_changed(actor) avec le payload explicite."""
        self.changed.emit()
        self.actor_changed.emit(self._actor_insp._actor)

    # ── Helpers header ───────────────────────────────────────────

    def _set_header(self, kind: str, type_text: str, name_text: str):
        editable = kind in ("scene", "actor", "prefab", "script_asset")
        self._header.set_header(kind, type_text, name_text, editable=editable)
        self._header_mode = kind

    def _on_header_rename(self, new_name: str):
        if self._header_mode == "scene":
            scene = self._scene_insp._scene
            project = self._scene_insp._project
            if scene and project and new_name != scene.name:
                project.rename_scene(scene, new_name)
                self._header.set_name(scene.name)
                self._scene_insp.changed.emit()
        elif self._header_mode in ("actor", "prefab"):
            actor = self._actor_insp._actor
            project = self._actor_insp._project
            if actor and new_name != actor.name:
                if self._actor_insp._is_prefab_template:
                    project.prefabs.rename(actor, new_name)
                else:
                    actor.name = new_name
                    self._actor_insp._persist()
                    from core.command_dispatcher import get_dispatcher
                    get_dispatcher()._emit("actors_list_changed")
                self._header.set_name(actor.name)
        elif self._header_mode == "script_asset":
            path = self._current_script_path
            if not path or not path.exists():
                return
            new_stem = new_name.strip()
            if not new_stem or new_stem == path.stem:
                self._header.set_name(path.name)
                return
            new_path = path.parent / f"{new_stem}{path.suffix}"
            if new_path.exists():
                self._header.set_name(path.name)
                return
            from core.history import get_history, RenameFileCmd
            from core.command_dispatcher import get_dispatcher

            def _refresh():
                current = new_path if new_path.exists() else path
                self._current_script_path = current
                self._header.set_name(current.name)
                self._script_insp.load(current)
                get_dispatcher().notify_scripts_changed()

            get_history().push(RenameFileCmd(path, new_path, _refresh))

    # ── API publique ─────────────────────────────────────────────

    def set_project(self, project):
        """Appelé par MainWindow à chaque ouverture/changement de projet."""
        self._project = project

    def on_selection(self, obj):
        """Reçu du bus — afficher le bon panneau selon le type de l'objet."""
        from pathlib import Path as _P
        from core.project import Actor, Scene, Prefab
        from core.selection_bus import CameraSelection
        if obj is None:
            # Mode par défaut : aperçu du projet (pas le message d'aide vide) —
            # cf. clic hors de la zone active du canvas.
            self.show_project()
        elif isinstance(obj, CameraSelection):
            # Clic sur l'ICÔNE caméra spécifiquement (cf. CameraItem.shape() —
            # le rectangle de vue 240×160 n'est qu'un retour visuel, il ne
            # déclenche jamais ce marqueur) → inspecteur caméra.
            self.show_camera(obj.scene, self._project)
        elif isinstance(obj, Actor):
            scene = self._project.active_scene if self._project else None
            self.show_actor(obj, self._project, scene)
        elif isinstance(obj, Scene):
            # Sélection générique de la scène (clic vide dans la zone active du
            # canvas) → son propre inspecteur, comme Actor/Prefab.
            self.show_scene(obj, self._project)
        elif isinstance(obj, Prefab):
            self.show_prefab(obj, self._project)
        elif isinstance(obj, _P):
            # Un script (.lua) sélectionné dans le Project Viewer — pas de
            # Resource dédiée, un simple chemin de fichier sur le bus.
            self.show_script(obj, self._project)

    def refresh_current(self):
        """Recharge le panneau courant depuis les données projet — capte les
        assets modifiés dans un autre écran (ex. palettes d'un fond recompressé
        → grisées de la carte PALETTES). Ne change pas le mode affiché
        ni ne rebranche de signaux."""
        if self._stack.currentIndex() == self._MODE_SCENE:
            sc, pr = self._scene_insp._scene, self._scene_insp._project
            if sc and pr:
                self._scene_insp.load(sc, pr)

    def show_empty(self):
        self._set_header("empty", "", "")
        self._stack.setCurrentIndex(self._MODE_EMPTY)

    def show_project(self):
        """Mode par défaut de l'inspecteur — aucune sélection (clic hors
        canvas, Échap, suppression du dernier actor sélectionné…)."""
        self._project_insp.load(self._project)
        name = self._project.settings.name if self._project else ""
        self._set_header("project", "PROJET", name)
        self._stack.setCurrentIndex(self._MODE_PROJECT)

    def show_scene(self, scene, project):
        self._scene_insp.load(scene, project)
        self._set_header("scene", "SCÈNE", scene.name if scene else "")
        self._stack.setCurrentIndex(self._MODE_SCENE)
        # Sync si l'inspector SceneInspector émet changed après un rename interne
        self._scene_insp.changed.connect(
            lambda: self._header.set_name(
                self._scene_insp._scene.name if self._scene_insp._scene else ""
            )
        )

    def show_actor(self, actor, project, scene=None):
        self._actor_insp.load(actor, project, scene)
        self._set_header("actor", "ACTOR", actor.name if actor else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_prefab(self, prefab, project):
        scene = project.active_scene if project else None
        self._actor_insp.load_prefab(prefab, project, scene)
        self._set_header("prefab", "PREFAB", prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_camera(self, scene, project):
        self._camera_insp.load(scene, project)
        self._set_header("camera", "CAMÉRA", "240 × 160")
        self._stack.setCurrentIndex(self._MODE_CAMERA)

    def show_script(self, path, project=None):
        """Script .lua sélectionné dans le Project Viewer — note libre +
        variables exposées (ScriptInspector)."""
        from pathlib import Path as _P
        path = _P(path)
        self._current_script_path = path
        self._script_insp.load(path)
        self._set_header("script_asset", "SCRIPT", path.name)
        self._stack.setCurrentIndex(self._MODE_SCRIPT)

    def show_prefab_uses(self, prefab, project=None):
        proj = project or self._project
        if not proj:
            return
        self._uses_insp.load(prefab, proj)
        self._set_header("uses", "INSTANCES", prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_PREFAB_USES)

    def show_script_uses(self, script_path: str, project=None):
        proj = project or self._project
        if not proj:
            return
        from pathlib import Path as _P
        self._script_uses_insp.load(script_path, proj)
        self._set_header("script", "SCRIPT", _P(script_path).name)
        self._stack.setCurrentIndex(self._MODE_SCRIPT_USES)

    def show_variable_uses(self, kind: str, name: str, project=None):
        proj = project or self._project
        if not proj:
            return
        self._variable_uses_insp.load(kind, name, proj)
        type_text = "CONSTANT" if kind == "const" else "GLOBAL"
        self._set_header("uses", type_text, name)
        self._stack.setCurrentIndex(self._MODE_VARIABLE_USES)

    def _on_script_edit_requested(self, path: str):
        """Ouvre le script dans l'éditeur — relayé par window.py via script_opened."""
        # On émet via un signal dédié ou on passe par le bus.
        # Ici on utilise directement l'import window pour éviter une dépendance circulaire :
        # c'est window.py qui connecte script_opened → open_script().
        # On stocke un callback optionnel.
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(path)

    def set_script_open_fn(self, fn):
        """Injecté par window.py pour ouvrir un script depuis la vue ScriptUses."""
        self._script_open_fn = fn
        self._actor_insp._script_open_fn = fn

    def update_actor_position(self, x: int, y: int):
        self._actor_insp.update_position(x, y)

    @property
    def actor_inspector(self) -> ActorInspector:
        return self._actor_insp
