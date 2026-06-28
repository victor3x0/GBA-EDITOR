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


class SetBgLayerCmd(Command):
    """
    Assignation ou effacement d'un background sur un calque BG de scène.
    execute/undo manipulent uniquement background_name + sauvegarde.
    La création du tileset/background est déjà faite par le dispatcher
    avant le push — record() est utilisé pour ne pas ré-exécuter.
    """

    def __init__(self, layer: Any, old_bg: str, new_bg: str,
                 slot: int, save_fn, refresh_fn=None):
        self._layer = layer
        self._old = old_bg
        self._new = new_bg
        self.label = f"BG{slot} ← {new_bg or 'vide'}"
        self._save = save_fn       # callable() → save_scene
        self._refresh = refresh_fn # callable() → recharger UI

    def execute(self):
        self._layer.background_name = self._new
        self._save()
        if self._refresh: self._refresh()

    def undo(self):
        self._layer.background_name = self._old
        self._save()
        if self._refresh: self._refresh()


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
