"""
history.py — Système undo/redo par pattern Command.

Usage :
    from core.history import get_history, SetFieldCmd, MoveActorCmd, ...
    get_history().push(SetFieldCmd(actor, "x", old, new, "Move X"))

Règles :
  - L'historique est par scène : clear() doit être appelé lors d'un
    changement de scène ou d'écran.
  - Les commandes sur un même (objet, champ) consécutives sont fusionnées
    (évite 100 entrées pour un drag de SpinBox).
  - Le stack redo est vidé dès qu'une nouvelle commande est poussée.
  - Max 200 commandes gardées (mémoire bornée).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from core.project import Actor, Scene

_MAX_HISTORY = 200


# ── Commande abstraite ─────────────────────────────────────────────

class Command(ABC):
    label: str = ""

    @abstractmethod
    def execute(self): ...

    @abstractmethod
    def undo(self): ...

    def merge(self, newer: "Command") -> bool:
        """Retourne True si `newer` peut être absorbée dans self (fusion)."""
        return False


# ── Commandes concrètes ────────────────────────────────────────────

class SetFieldCmd(Command):
    """
    Modification d'un champ d'un objet (actor ou component).
    Les commandes consécutives sur le même (obj, field) sont fusionnées.
    """

    def __init__(self, obj: Any, field: str, old_val: Any, new_val: Any,
                 label: str = "", persist_fn=None):
        self._obj = obj
        self._field = field
        self._old = old_val
        self._new = new_val
        self.label = label or f"Set {field}"
        self._persist = persist_fn   # callable() pour sauvegarder après apply

    def execute(self):
        setattr(self._obj, self._field, self._new)
        if self._persist:
            self._persist()

    def undo(self):
        setattr(self._obj, self._field, self._old)
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if not isinstance(newer, SetFieldCmd):
            return False
        if self._obj is newer._obj and self._field == newer._field:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class MoveActorCmd(Command):
    """Déplacement d'un actor dans le canvas (drag souris)."""

    def __init__(self, actor: "Actor", old_x: int, old_y: int,
                 new_x: int, new_y: int, persist_fn=None):
        self._actor = actor
        self._old = (old_x, old_y)
        self._new = (new_x, new_y)
        self.label = f"Déplacer {actor.name}"
        self._persist = persist_fn

    def execute(self):
        self._actor.x, self._actor.y = self._new
        if self._persist:
            self._persist()

    def undo(self):
        self._actor.x, self._actor.y = self._old
        if self._persist:
            self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, MoveActorCmd) and self._actor is newer._actor:
            self._new = newer._new
            self._persist = newer._persist
            return True
        return False


class AddActorCmd(Command):
    def __init__(self, scene: "Scene", actor: "Actor", persist_fn=None):
        self._scene = scene
        self._actor = actor
        self.label = f"Ajouter {actor.name}"
        self._persist = persist_fn

    def execute(self):
        if self._actor not in self._scene.actors:
            self._scene.actors.append(self._actor)
        if self._persist:
            self._persist()

    def undo(self):
        if self._actor in self._scene.actors:
            self._scene.actors.remove(self._actor)
        if self._persist:
            self._persist()


class RemoveActorCmd(Command):
    def __init__(self, scene: "Scene", actor: "Actor", index: int, persist_fn=None):
        self._scene = scene
        self._actor = actor
        self._index = index
        self.label = f"Supprimer {actor.name}"
        self._persist = persist_fn

    def execute(self):
        if self._actor in self._scene.actors:
            self._scene.actors.remove(self._actor)
        if self._persist:
            self._persist()

    def undo(self):
        idx = min(self._index, len(self._scene.actors))
        self._scene.actors.insert(idx, self._actor)
        if self._persist:
            self._persist()


class PaintFrameCmd(Command):
    """
    Peinture / effacement de tuiles sur un AnimFrame (canvas sprite editor).
    Coups de pinceau consécutifs sur la même frame fusionnés en un seul undo.
    Utiliser avec record() (action déjà appliquée avant l'enregistrement).
    """

    def __init__(self, frame: Any, old_tiles: list, new_tiles: list, persist_fn=None):
        self._frame   = frame
        self._old     = old_tiles
        self._new     = new_tiles
        self.label    = "Peindre frame"
        self._persist = persist_fn

    def execute(self):
        self._frame.tiles = list(self._new)
        if self._persist: self._persist()

    def undo(self):
        self._frame.tiles = list(self._old)
        if self._persist: self._persist()

    def merge(self, newer: "Command") -> bool:
        if isinstance(newer, PaintFrameCmd) and self._frame is newer._frame:
            self._new     = newer._new
            self._persist = newer._persist
            return True
        return False


class DeleteResourceCmd(Command):
    """
    Suppression d'une Resource (scène, prefab…) depuis l'UI.
    execute : soft_delete (retire de la liste, JSON différé)
    undo    : restore (remet dans la liste et resauvegarde le JSON)
    """

    def __init__(self, manager: Any, item: Any, refresh_fn=None):
        self._mgr     = manager
        self._item    = item
        self.label    = f"Supprimer {getattr(item, 'name', str(item))}"
        self._refresh = refresh_fn

    def execute(self):
        self._mgr.soft_delete(self._item)
        if self._refresh:
            self._refresh()

    def undo(self):
        self._mgr.restore(self._item)
        if self._refresh:
            self._refresh()


class CollisionPaintCmd(Command):
    """
    Stroke de peinture collision (pinceau ou slope). Un stroke = press → release.
    delta : {(col, row): (old_tile, new_tile)}
    Les tiles sont déjà appliquées au moment du push — on bypasse execute().
    """

    def __init__(self, overlay, delta: dict, persist_fn=None):
        self._overlay = overlay
        self._delta   = delta
        self.label    = "Peinture collision"
        self._persist = persist_fn

    def execute(self):
        for (col, row), (_, new) in self._delta.items():
            self._overlay.set_tile(col, row, new)
        if self._persist:
            self._persist()

    def undo(self):
        for (col, row), (old, _) in self._delta.items():
            self._overlay.set_tile(col, row, old)
        if self._persist:
            self._persist()


class AddComponentCmd(Command):
    def __init__(self, actor: "Actor", comp: Any, persist_fn=None):
        self._actor = actor
        self._comp = comp
        self.label = f"Ajouter component {getattr(comp, 'id', '')}"
        self._persist = persist_fn

    def execute(self):
        if self._comp not in self._actor.components:
            self._actor.components.append(self._comp)
        if self._persist:
            self._persist()

    def undo(self):
        if self._comp in self._actor.components:
            self._actor.components.remove(self._comp)
        if self._persist:
            self._persist()


class RemoveComponentCmd(Command):
    def __init__(self, actor: "Actor", comp: Any, index: int, persist_fn=None):
        self._actor = actor
        self._comp = comp
        self._index = index
        self.label = f"Supprimer component {getattr(comp, 'id', '')}"
        self._persist = persist_fn

    def execute(self):
        if self._comp in self._actor.components:
            self._actor.components.remove(self._comp)
        if self._persist:
            self._persist()

    def undo(self):
        idx = min(self._index, len(self._actor.components))
        self._actor.components.insert(idx, self._comp)
        if self._persist:
            self._persist()


class RemoveListItemCmd(Command):
    """
    Suppression d'un élément d'une liste arbitraire (ex: AnimState d'un
    sprite). Générique pour éviter une Command dédiée par type de liste.
    """

    def __init__(self, container: list, item: Any, persist_fn=None, label: str = "Supprimer"):
        self._container = container
        self._item = item
        self._index = container.index(item)
        self.label = label
        self._persist = persist_fn

    def execute(self):
        if self._item in self._container:
            self._container.remove(self._item)
        if self._persist:
            self._persist()

    def undo(self):
        idx = min(self._index, len(self._container))
        self._container.insert(idx, self._item)
        if self._persist:
            self._persist()


class AddListItemCmd(Command):
    """
    Ajout d'un élément à une liste arbitraire (ex: BackgroundLayer d'un
    BackgroundAsset). Symétrique de RemoveListItemCmd — construire l'item
    AVANT de le pousser (contrairement à AddComponentCmd, pas besoin de le
    retirer manuellement pour laisser execute() faire son travail).
    """

    def __init__(self, container: list, item: Any, persist_fn=None, label: str = "Ajouter"):
        self._container = container
        self._item = item
        self.label = label
        self._persist = persist_fn

    def execute(self):
        if self._item not in self._container:
            self._container.append(self._item)
        if self._persist:
            self._persist()

    def undo(self):
        if self._item in self._container:
            self._container.remove(self._item)
        if self._persist:
            self._persist()


class RenameFileCmd(Command):
    """
    Renommage d'un fichier arbitraire sur disque (scripts assets/ — pas un
    Resource géré par ResourceManager, donc pas de rename() disponible).
    execute/undo renomment réellement le fichier dans les deux sens.
    """

    def __init__(self, old_path: Path, new_path: Path, refresh_fn=None):
        self._old = old_path
        self._new = new_path
        self.label = f"Renommer {old_path.name} → {new_path.name}"
        self._refresh = refresh_fn

    def execute(self):
        if self._old.exists():
            self._old.rename(self._new)
        if self._refresh:
            self._refresh()

    def undo(self):
        if self._new.exists():
            self._new.rename(self._old)
        if self._refresh:
            self._refresh()


class DeleteFileCmd(Command):
    """
    Suppression d'un fichier arbitraire sur disque (scripts assets/). Le
    contenu est gardé en mémoire le temps de la commande pour permettre un
    undo réel (contrairement à DeleteResourceCmd, il n'y a pas de
    soft_delete/restore disponible pour un fichier hors ResourceManager).
    """

    def __init__(self, path: Path, refresh_fn=None):
        self._path = path
        self._bytes: Optional[bytes] = None
        self.label = f"Supprimer {path.name}"
        self._refresh = refresh_fn

    def execute(self):
        if self._path.exists():
            self._bytes = self._path.read_bytes()
            self._path.unlink()
        if self._refresh:
            self._refresh()

    def undo(self):
        if self._bytes is not None:
            self._path.write_bytes(self._bytes)
        if self._refresh:
            self._refresh()


# ── Historique ────────────────────────────────────────────────────

class CommandHistory(QObject):
    """
    Stack undo/redo avec fusion de commandes consécutives identiques.
    Émis changed() à chaque mutation du stack pour mettre à jour l'UI.
    """

    changed = pyqtSignal()   # undo/redo dispo a changé

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    # ── API ──────────────────────────────────────────────────────

    def record(self, cmd: Command):
        """Enregistre une commande SANS l'exécuter (déjà exécutée par l'appelant)."""
        if self._undo and self._undo[-1].merge(cmd):
            self.changed.emit()
            return
        self._undo.append(cmd)
        self._redo.clear()
        if len(self._undo) > _MAX_HISTORY:
            self._undo = self._undo[-_MAX_HISTORY:]
        self.changed.emit()

    def push(self, cmd: Command):
        """Exécute la commande et l'enregistre dans le stack undo."""
        # Tenter la fusion avec la dernière commande
        if self._undo and self._undo[-1].merge(cmd):
            # Fusion réussie : on réexécute la commande mergée (nouvelle valeur)
            cmd.execute()
            self.changed.emit()
            return

        cmd.execute()
        self._undo.append(cmd)
        self._redo.clear()

        # Borner la mémoire
        if len(self._undo) > _MAX_HISTORY:
            self._undo = self._undo[-_MAX_HISTORY:]

        self.changed.emit()

    def undo(self) -> Optional[str]:
        """Annule la dernière commande. Retourne son label ou None."""
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self.changed.emit()
        return cmd.label

    def redo(self) -> Optional[str]:
        """Rejoue la dernière commande annulée. Retourne son label ou None."""
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.execute()
        self._undo.append(cmd)
        self.changed.emit()
        return cmd.label

    def clear(self):
        """Vide l'historique (changement de scène / d'écran)."""
        self._undo.clear()
        self._redo.clear()
        self.changed.emit()

    # ── État ─────────────────────────────────────────────────────

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""


# ── Singleton global ──────────────────────────────────────────────
# Accessible par tous les modules sans passer de référence.

_history = CommandHistory()


def get_history() -> CommandHistory:
    return _history
