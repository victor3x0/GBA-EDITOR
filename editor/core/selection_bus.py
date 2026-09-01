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


class CameraSelection:
    """Marqueur de sélection : l'ICÔNE caméra a été cliquée dans le canvas (ou
    une caméra choisie dans le scene tree) — distinct d'une sélection de Scene
    « nue » (qui affiche le SceneInspector, comme Actor/Prefab affichent leur
    propre inspecteur). Le rectangle de vue 240×160 de la caméra n'est qu'un
    retour visuel, non cliquable ; seule l'icône déclenche ce marqueur (cf.
    CameraItem.shape() dans scene_canvas.py). Sans lui, impossible de
    distinguer les deux intentions une fois passées par le bus.

    `camera` désigne PRÉCISÉMENT la caméra visée (la scène peut en posséder
    plusieurs) ; `None` = état implicite (scène sans caméra encore créée, cf.
    `Project.ensure_scene_camera`)."""
    __slots__ = ("scene", "camera")

    def __init__(self, scene, camera=None):
        self.scene = scene
        self.camera = camera


class UIElementSelection:
    """Marqueur de sélection : un ÉLÉMENT d'UI (zone, panel, texte…) a été
    sélectionné dans le canvas ou l'arbre.

    Porte la mise en page en plus de l'élément, parce qu'un élément ne connaît
    pas son `UILayout` — et que l'inspecteur en a besoin pour dire « partagée
    par N scènes » comme pour le supprimer de la bonne liste. Même raison d'être
    que `CameraSelection` : le bus transporte une intention, pas seulement un
    objet.

    `region` est un alias rétro-compat de `element` : le bus portait autrefois
    des zones seules, et de nombreux sites lisent encore `.region`."""
    __slots__ = ("layout", "element")

    def __init__(self, layout, element):
        self.layout = layout
        self.element = element

    @property
    def region(self):
        return self.element


# Alias historique : `UIRegionSelection(layout, region)` construit toujours, et
# `isinstance(obj, UIRegionSelection)` reste vrai pour tout élément.
UIRegionSelection = UIElementSelection


class SelectionBus(QObject):
    """
    Singleton de sélection. Émet changed(obj) à chaque changement.
    obj : Actor | Scene | Prefab | CameraSelection | UIRegionSelection | None
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
