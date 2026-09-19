"""Commandes annulables partagées par le Graphe des scènes.

`EdgePresentationCmd` écrit la présentation éditoriale d'une transition (tracé,
note) dans le sidecar `SceneGraphState`. Elle est poussée depuis DEUX endroits —
l'inspecteur d'arête et la vue du graphe (clic droit droite/courbe) — donc elle
vit ici plutôt que privée à l'un des deux : un import du privé `_…` d'un module
frère par un autre est justement ce que le contrôle d'architecture refuse.
"""
from __future__ import annotations

from core.history import Command
from ui.common.labels import label


class EdgePresentationCmd(Command):
    """Métadonnée d'une ou plusieurs transitions, persistée et annulable."""

    def __init__(self, state, edges, field: str, before, after, applied):
        self._state = state
        self._edges = tuple(edges)
        self._field = field
        self._before, self._after = tuple(before), tuple(after)
        self._applied = applied
        self.label = label("edgeinsp.undo_path" if field == "style" else "edgeinsp.undo_note")

    def _apply(self, values) -> None:
        setter = self._state.set_edge_style if self._field == "style" else self._state.set_edge_note
        for edge, value in zip(self._edges, values):
            setter(edge.source, edge.target, value)
        self._applied(self._edges, self._field)

    def execute(self):
        self._apply(self._after)

    def undo(self):
        self._apply(self._before)

    def merge(self, newer: Command) -> bool:
        if (isinstance(newer, EdgePresentationCmd)
                and self._state is newer._state
                and self._edges == newer._edges
                and self._field == newer._field):
            self._after = newer._after
            self._applied = newer._applied
            return True
        return False
