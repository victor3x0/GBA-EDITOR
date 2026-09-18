"""L'inspecteur d'acteur du `DynamicInspector` démarre paresseux : None tant
qu'aucun acteur n'a été inspecté.

Régression : `window._on_lua_changed` (et `_on_asset_changed`) appelaient
`self._inspector.actor_inspector.notify_lua_changed(...)` sans garde. Sauver un
script de scène sans avoir jamais ouvert d'acteur crashait alors sur
`AttributeError: 'NoneType' object has no attribute 'notify_lua_changed'`. Ce
test verrouille le contrat sur lequel repose la garde des appelants."""
from __future__ import annotations


def test_actor_inspector_est_none_avant_toute_inspection(qapp):
    from ui.scene_manager.inspectors.dynamic_inspector import DynamicInspector

    inspector = DynamicInspector()
    assert inspector.actor_inspector is None
