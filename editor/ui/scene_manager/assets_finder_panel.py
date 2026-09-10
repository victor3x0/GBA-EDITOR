"""Panneau gauche (bas) du Scene Manager — ce que le PROJET contient.

Scènes, prefabs et scripts, rendus par le composant partagé
(`ui/common/asset_finder.py`) comme dans tous les autres écrans. Ce module ne
garde que ce qui est propre à CET écran : traduire une sélection en geste
(activer une scène, inspecter un prefab), et les entrées de menu qui supposent
un inspecteur en face (« Voir les instances », « Voir les utilisations »).

Le contenu de la scène active — acteurs et mise en page UI — vit dans
`scene_tree_panel.py`, au-dessus dans la même colonne.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenu, QFileDialog, QDialog
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.common.theme import QSS
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import SCENES, PREFABS, SCRIPTS
from ui.common.labels import label

from core.project import Project
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher, unique_name
# Source unique du dossier de projets par défaut (~/GBAProjects) — ce module et
# window.py en avaient chacun une copie pointant vers le projects/ du repo :
# inexistant chez quelqu'un qui lance l'exe, et dans le dossier temporaire une
# fois figé.
from ui.home.project_picker import PROJECTS_DIR


class AssetsFinderPanel(QWidget):
    scene_selected        = pyqtSignal(int)      # INDEX dans project.scenes
    prefab_add_requested  = pyqtSignal()
    scene_add_requested   = pyqtSignal()
    script_opened         = pyqtSignal(str)
    project_created       = pyqtSignal(str, str)   # (name, path)
    project_opened        = pyqtSignal(str)        # (path)
    prefab_uses_requested = pyqtSignal(object)     # Prefab
    script_uses_requested = pyqtSignal(str)        # chemin absolu du script

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._finder = AssetFinder(label('assf.project_viewer'), [SCENES, PREFABS, SCRIPTS],
                                   min_width=180, max_width=420)
        root.addWidget(self._finder, 1)

        self._finder.selected.connect(self._on_selected)
        self._finder.activated.connect(self._on_activated)
        self._finder.add_requested.connect(self._on_add_requested)

        # Entrées de menu propres à cet écran : elles supposent un inspecteur
        # capable de les afficher, que seul le Scene Manager possède.
        self._finder.add_action(PREFABS.label, label("assf.instantiate_prefab"),
                                lambda pf: get_dispatcher().instantiate_prefab(pf.name, 60, 60))
        self._finder.add_action(PREFABS.label, label("assf.edit_prefab"),
                                lambda pf: get_bus().select(pf))
        self._finder.add_action(PREFABS.label, label("assf.view_instances"),
                                self.prefab_uses_requested.emit)
        self._finder.add_action(SCRIPTS.label, label("assf.edit_script"),
                                lambda p: self.script_opened.emit(str(p)))
        self._finder.add_action(SCRIPTS.label, label("assf.view_uses"),
                                lambda p: self.script_uses_requested.emit(str(p)))

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selected(self, kind_label: str, obj):
        """Traduit « un asset a été choisi » dans le geste attendu de sa famille.

        Une scène s'ACTIVE (elle devient celle qu'on édite) et window.py la
        désigne par son index ; un prefab ou un script se posent simplement sur
        le bus, où l'inspecteur les prend."""
        if kind_label == SCENES.label:
            if self._project is not None and obj in self._project.scenes:
                self.scene_selected.emit(list(self._project.scenes).index(obj))
        elif kind_label == PREFABS.label:
            get_bus().select(obj)
        elif kind_label == SCRIPTS.label:
            get_bus().select(obj)     # -> ScriptInspector (note + exports)

    def _on_activated(self, kind_label: str, obj):
        """Double-clic. Un script s'ouvre dans l'éditeur ; un prefab s'édite."""
        if kind_label == SCRIPTS.label:
            self.script_opened.emit(str(obj))
        elif kind_label == PREFABS.label:
            get_bus().select(obj)

    # ── Création ──────────────────────────────────────────────────

    def _on_add_requested(self, kind_label: str):
        if kind_label == SCENES.label:
            self.scene_add_requested.emit()     # window.py : reporte la scène active
        elif kind_label == PREFABS.label:
            self._add_prefab()
        elif kind_label == SCRIPTS.label:
            self._show_add_script_menu()

    def _add_prefab(self):
        if not self._project:
            return
        name = unique_name("Prefab", {p.name for p in self._project.prefabs})
        get_dispatcher().add_prefab(name)
        self.refresh()
        self.begin_rename_prefab(name)

    def _show_add_script_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.addAction(label("assf.behavior_script"), self._new_behavior_script)
        menu.exec(self.mapToGlobal(QPoint(0, 0)))

    def _new_behavior_script(self):
        self._create_script("behavior",
                            self._project.scripts_behaviors_dir if self._project else None,
                            "Behavior")

    def _create_script(self, kind: str, directory, base: str):
        """Crée un script au nommage automatique (pas de pop-up) et l'ouvre."""
        if not self._project or directory is None:
            return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        directory.mkdir(parents=True, exist_ok=True)
        name = unique_name(base, {f.stem for f in directory.glob("*.lua")})
        sp = directory / f"{name}.lua"
        # Pas d'actor précis à ce stade (créé depuis l'Assets finder) — contexte
        # de composants vide, même template que component_editors/script.py.
        sp.write_text(generate_script_template(ScriptTemplateContext(kind=kind, name=name)),
                      encoding="utf-8")
        self.refresh()
        # Ouvre le script dans le Script Editor interne (window.open_script), sur
        # les trois OS. Un os.startfile Windows-only l'ouvrait EN PLUS dans
        # l'éditeur externe du système — redondant avec l'éditeur interne et
        # incohérent hors Windows ; retiré.
        self.script_opened.emit(str(sp))

    # ── Renommage inline d'un asset fraîchement créé (pas de pop-up) ──

    def begin_rename_scene(self, name: str):
        self._begin_rename(SCENES.label, self._project.scenes.get(name) if self._project else None)

    def begin_rename_prefab(self, name: str):
        self._begin_rename(PREFABS.label, self._project.prefabs.get(name) if self._project else None)

    def _begin_rename(self, kind_label: str, obj):
        if obj is not None:
            self._finder.begin_rename(kind_label, obj)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)

    def refresh(self):
        self._finder.refresh()

    def _refresh_scripts(self):
        # Une seule famille a bougé, mais tout repeupler coûte un parcours de
        # listes déjà en mémoire : pas de quoi se doter d'un chemin à part.
        self._finder.refresh()

    # ── Projets ───────────────────────────────────────────────────

    def _prompt_new(self):
        from ui.home.project_picker import NewProjectDialog
        dlg = NewProjectDialog(PROJECTS_DIR, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.project_created.emit(dlg.result_name, str(dlg.result_path))

    def _prompt_open(self):
        path = QFileDialog.getExistingDirectory(self, label("assf.open_project"), str(PROJECTS_DIR))
        if path:
            self.project_opened.emit(path)

    @property
    def project(self) -> Project:
        return self._project
