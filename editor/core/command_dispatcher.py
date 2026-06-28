"""
CommandDispatcher — point unique pour toutes les mutations du projet.

Règle absolue :
  - TOUT appel à save_scene/save/save_prefab passe par ici.
  - Le watcher est toujours suspendu pendant une mutation.
  - Les panels appellent get_dispatcher().xxx() pour muter.
  - window.py s'abonne via .on() aux événements du dispatcher.

Usage :
    from core.command_dispatcher import get_dispatcher
    get_dispatcher().delete_actor(actor)
    get_dispatcher().on("actors_list_changed", panel.refresh)

Événements émis :
    "scene_sprites_changed"        — recréer les sprites canvas
    "actors_list_changed"          — rafraîchir la liste actors
    "bg_slot_changed"  (int slot)  — rafraîchir un BG slot précis
    "status_message"   (str msg)   — afficher dans la barre de statut
    "scripts_changed"              — rafraîchir la liste des scripts
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import copy

from core.events import EventEmitter
from core.project import Actor, Scene, Prefab, Background, Tileset
from core.history import get_history, AddActorCmd, RemoveActorCmd
from core.selection_bus import get_bus

if TYPE_CHECKING:
    from core.project import Project
    from core.project_watcher import ProjectWatcher


class CommandDispatcher(EventEmitter):
    """
    Dispatcher centralisé — singleton, initialiser via setup() après chaque chargement projet.
    """

    def __init__(self):
        super().__init__()
        self._project: Optional["Project"] = None
        self._watcher: Optional["ProjectWatcher"] = None

    @property
    def project(self) -> Optional["Project"]:
        return self._project

    def setup(self, project, watcher):
        """Appelé par MainWindow à chaque chargement/création de projet."""
        self._project = project
        self._watcher = watcher

    # ── Helpers ───────────────────────────────────────────────────

    def _save_scene(self):
        if not self._project or not self._project.active_scene:
            return
        with self._watcher.suspended():
            self._project.save_scene(self._project.active_scene)

    def _save_all(self):
        if not self._project:
            return
        with self._watcher.suspended():
            self._project.save()

    # ── Actor ─────────────────────────────────────────────────────

    def add_actor(self, name: str, x: int = 0, y: int = 0) -> Optional[Actor]:
        """Ajoute un actor vide à la scène active aux coordonnées données (avec historique)."""
        if not self._project or not self._project.active_scene:
            return None
        scene = self._project.active_scene
        actor = Actor(name=name, x=x, y=y)

        def persist():
            self._save_scene()
            self._emit("actors_list_changed")
            self._emit("scene_sprites_changed")

        get_history().push(AddActorCmd(scene, actor, persist_fn=persist))
        get_bus().select(actor)
        self._emit("status_message", f"Actor créé : {name}")
        return actor

    def delete_actor(self, actor: Actor):
        """Supprime un actor de la scène active (avec historique)."""
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        if actor not in scene.actors:
            return
        index = scene.actors.index(actor)

        def persist():
            get_bus().clear()
            self._save_scene()
            self._emit("actors_list_changed")
            self._emit("scene_sprites_changed")

        get_history().push(RemoveActorCmd(scene, actor, index, persist_fn=persist))
        self._emit("status_message", f"Actor supprimé : {actor.name}")

    def instantiate_prefab(self, prefab_name: str, x: int, y: int) -> Optional[Actor]:
        """Instancie un prefab dans la scène active aux coordonnées données."""
        if not self._project or not self._project.active_scene:
            return None
        prefab = self._project.get_prefab(prefab_name)
        if not prefab:
            return None
        existing = {a.name for a in self._project.active_scene.actors}
        name = prefab.name
        counter = 1
        while name in existing:
            name = f"{prefab.name}_{counter}"
            counter += 1
        actor = self._project.instantiate_actor_from_prefab(prefab, name, x=x, y=y)
        self._project.active_scene.actors.append(actor)
        self._save_scene()
        self._emit("scene_sprites_changed")
        get_bus().select(actor)
        return actor

    # ── Scene ─────────────────────────────────────────────────────

    def add_scene(self, name: str) -> Optional[Scene]:
        """Crée une nouvelle scène vide et la persiste."""
        if not self._project:
            return None
        scene = Scene(name=name)
        self._project.scenes.append(scene)
        with self._watcher.suspended():
            self._project.save_scene(scene)
        self._emit("status_message",f"Scène créée : {name}")
        return scene

    # ── Prefab ────────────────────────────────────────────────────

    def add_prefab(self, name: str) -> Optional[Prefab]:
        """Crée un nouveau prefab vide et le persiste."""
        if not self._project:
            return None
        prefab = Prefab(name=name)
        self._project.prefabs.append(prefab)
        with self._watcher.suspended():
            self._project.save_prefab(prefab)
        self._emit("status_message",f"Prefab créé : {name}")
        return prefab

    # ── BG slots ──────────────────────────────────────────────────

    def assign_bg_slot(self, slot: int, path_str: str):
        """Assigne (ou vide) un slot BG de la scène active."""
        if not self._project or not self._project.active_scene or slot > 3:
            return
        scene = self._project.active_scene

        if path_str:
            ap = Path(path_str)
            dst = self._project.import_asset(ap, "backgrounds")
            bg_name = dst.stem

            tileset = self._project.get_tileset(bg_name)
            if not tileset:
                tileset = Tileset(name=bg_name, asset=self._project.asset_rel(dst))
                self._project.tilesets.append(tileset)
                with self._watcher.suspended():
                    self._project.save_tileset(tileset)

            bg = self._project.get_background(bg_name)
            if not bg:
                bg = Background(name=bg_name, tileset_name=bg_name)
                self._project.backgrounds.append(bg)
                with self._watcher.suspended():
                    self._project.save_background(bg)

            scene.bg_layers[slot].background_name = bg_name
            self._emit("status_message",f"BG{slot} : {bg_name}")
        else:
            scene.bg_layers[slot].background_name = ""

        self._save_scene()
        self._emit("bg_slot_changed", slot)
        self._emit("actors_list_changed")

    # ── Prefab avec propagation ───────────────────────────────────

    def save_prefab(self, prefab: Prefab):
        """
        Sauvegarde le prefab ET propage ses components à toutes les instances
        liées (actor.prefab_name == prefab.name) dans toutes les scènes.
        La position/transform de chaque instance reste inchangée.
        """
        if not self._project:
            return
        with self._watcher.suspended():
            self._project.save_prefab(prefab)

        # Propagation cross-scène
        scenes_updated: list[Scene] = []
        for scene in self._project.scenes:
            changed = False
            for actor in scene.actors:
                if actor.prefab_name == prefab.name:
                    actor.components = copy.deepcopy(prefab.components)
                    changed = True
            if changed:
                with self._watcher.suspended():
                    self._project.save_scene(scene)
                scenes_updated.append(scene)

        if scenes_updated:
            self._emit("scene_sprites_changed")
            self._emit("actors_list_changed")

        n = len(scenes_updated)
        msg = f"Prefab '{prefab.name}' sauvegardé"
        if n:
            msg += f" — {n} scène{'s' if n > 1 else ''} mise{'s' if n > 1 else ''} à jour"
        self._emit("status_message",msg)

    # ── Saves ─────────────────────────────────────────────────────

    def save_scene(self):
        """Sauvegarde la scène active (après drag actor, déplacement caméra)."""
        self._save_scene()

    def save_all(self):
        """Sauvegarde globale différée (après changements inspector)."""
        self._save_all()

    def notify_scripts_changed(self):
        """Notifie que la liste des scripts a changé (création, suppression)."""
        self._emit("scripts_changed")


_dispatcher = CommandDispatcher()


def get_dispatcher() -> CommandDispatcher:
    return _dispatcher

