"""
selection_bus.py — Point central de sélection pour tous les panels.

Règle absolue :
  - Les panels appellent bus.select(obj) quand l'utilisateur interagit.
  - Les panels écoutent bus.changed pour se mettre à jour (on_selection).
  - Les panels ne se parlent JAMAIS directement.
  - on_selection() ne rappelle JAMAIS bus.select() — sens unique.

Usage :
    from core.selection_bus import get_bus
    bus = get_bus()
    bus.select(actor)          # émet changed(actor)
    bus.changed.connect(panel.on_selection)
"""

from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal


class SelectionBus(QObject):
    """
    Singleton de sélection. Émet changed(obj) à chaque changement.
    obj peut être : Actor | Scene | Prefab | None
    """

    changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = None

    def select(self, obj):
        """Sélectionner un objet. No-op si déjà sélectionné (évite les boucles)."""
        if obj is self._current:
            return
        self._current = obj
        self.changed.emit(obj)

    def clear(self):
        self.select(None)

    @property
    def current(self):
        return self._current


_bus = SelectionBus()


def get_bus() -> SelectionBus:
    return _bus
