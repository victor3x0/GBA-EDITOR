"""Conteneur des contextes du Canvas du Scene Manager.

`CanvasWorkspace` possède les VUES du Canvas, pas leur logique métier. La vue
de scène existante reste un `SceneEditor` autonome ; une future vue Graphe sera
enregistrée ici sans lui ajouter des nœuds, des arêtes ou des dépendances Qt.

La fenêtre conserve une référence à `scene_editor` pendant la transition : les
connexions existantes (inspecteur, bus de sélection, dispatcher) restent donc
identiques. Les nouveaux branchements qui concernent le choix de vue passent
par ce conteneur.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QStackedLayout, QWidget


class CanvasWorkspace(QWidget):
    """Héberge les vues exclusives du Canvas.

    La clé ``scene`` est réservée à la vue de scène éditable. Une vue ajoutée
    ultérieurement doit seulement être un QWidget : elle reçoit son propre
    contrat de chargement de données, plutôt que de devenir une extension de
    `SceneEditor`.
    """

    view_changed = pyqtSignal(str)
    SCENE_VIEW = "scene"

    def __init__(self, scene_editor: QWidget, parent=None):
        super().__init__(parent)
        if scene_editor is None:
            raise ValueError("CanvasWorkspace requiert la vue de scène")

        self._views: dict[str, QWidget] = {}
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)
        self._active_view = ""
        self.scene_editor = scene_editor
        self.register_view(self.SCENE_VIEW, scene_editor)
        self.activate_view(self.SCENE_VIEW, emit=False)

    @property
    def active_view(self) -> str:
        return self._active_view

    def view(self, name: str) -> QWidget | None:
        """Renvoie une vue enregistrée, sans exposer le QStackedLayout."""
        return self._views.get(name)

    def register_view(self, name: str, widget: QWidget) -> None:
        """Ajoute une vue sous un nom stable."""
        if not name:
            raise ValueError("Une vue Canvas doit avoir un nom")
        if name in self._views:
            raise ValueError(f"La vue Canvas '{name}' existe déjà")
        if widget is None:
            raise ValueError("Une vue Canvas ne peut pas être vide")
        self._views[name] = widget
        self._stack.addWidget(widget)

    def activate_view(self, name: str, *, emit: bool = True) -> None:
        """Affiche une vue déjà enregistrée."""
        widget = self._views.get(name)
        if widget is None:
            raise KeyError(f"Vue Canvas inconnue : {name}")
        if name == self._active_view:
            return
        self._stack.setCurrentWidget(widget)
        self._active_view = name
        if emit:
            self.view_changed.emit(name)

    def load_project(self, project) -> None:
        """Conserve le contrat actuel : seul le Canvas de scène charge ici.

        Les vues futures recevront une projection dédiée (par exemple le
        graphe dérivé des scripts), et non le projet brut par défaut.
        """
        if project and project.active_scene:
            self.scene_editor.load_project(project)
