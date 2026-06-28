"""
ui.inspectors — package principal.

Import de compat :
    from ui.inspectors import DynamicInspector, BackgroundInspector
"""

# Charger les éditeurs built-in dans le registre
from ui.inspectors.component_editors import sprite    # noqa: F401
from ui.inspectors.component_editors import collision  # noqa: F401
from ui.inspectors.component_editors import sfx        # noqa: F401
from ui.inspectors.component_editors import script     # noqa: F401

# Ré-exporter les classes publiques depuis l'ancien module (compat)
from ui.inspectors_module import (   # type: ignore[import]
    DynamicInspector,
    BackgroundInspector,
    ActorInspector,
    SceneInspector,
    CameraInspector,
    PrefabUsesInspector,
    ScriptUsesInspector,
    ComponentListWidget,
)

__all__ = [
    "DynamicInspector",
    "BackgroundInspector",
    "ActorInspector",
    "SceneInspector",
    "CameraInspector",
    "PrefabUsesInspector",
    "ScriptUsesInspector",
    "ComponentListWidget",
]
