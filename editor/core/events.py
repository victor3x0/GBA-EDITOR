"""
events.py — Bus d'événements Python pur, sans dépendance framework.

Usage :
    class MonEngine(EventEmitter):
        def do_something(self):
            self._emit("data_changed", payload)

    engine = MonEngine()
    engine.on("data_changed", lambda data: print(data))
    engine.off("data_changed", handler)
"""
from __future__ import annotations
from typing import Callable


class EventEmitter:
    """Mixin léger pour publier/souscrire à des événements nommés."""

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}

    def on(self, event: str, fn: Callable) -> None:
        """Abonne fn à event."""
        self._listeners.setdefault(event, []).append(fn)

    def off(self, event: str, fn: Callable) -> None:
        """Désabonne fn de event (silencieux si absent)."""
        listeners = self._listeners.get(event, [])
        if fn in listeners:
            listeners.remove(fn)

    def _emit(self, event: str, *args) -> None:
        """Notifie tous les abonnés de event."""
        for fn in list(self._listeners.get(event, [])):
            fn(*args)
