"""Resynchro du canvas après undo/redo — le 4ᵉ invariant A1.

Les trois `*_undo` prouvent que le MODÈLE revient après un undo. Ferme la boucle
côté VUE : après un undo, la fenêtre appelle `_flush_after_undo_redo`, dont
l'action sur le canvas est `SceneEditor.reload_scene_items()` — les items sont
reposés depuis le modèle (« le modèle en mémoire = vérité après undo »), pour
TOUTES les familles.

Ces tests gardent aussi un CORRECTIF : `_flush` ne reposait que les SPRITES, si
bien qu'un item de caméra ou de zone déplacé puis annulé restait à sa position
draggée alors que le modèle était revenu. `reload_scene_items` (sprites + caméras
+ zones) referme ce trou ; le test zone ci-dessous tomberait si on l'ouvrait à
nouveau.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.project import Project
from core.history import get_history, MoveActorCmd, MoveUIRegionCmd

REPO_DIR = Path(__file__).resolve().parent.parent.parent
ORBIT = REPO_DIR / "Project Demo" / "OrbitTest"
MYGAME = REPO_DIR / "Project Demo" / "MyGame"


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _editor(project_dir: Path):
    if not project_dir.exists():
        pytest.skip(f"démo absente : {project_dir}")
    from ui.scene_manager.scene_canvas import SceneEditor
    ed = SceneEditor()
    ed.load_project(Project.open(project_dir))
    return ed


def _first_actor(ed):
    actor = next((a for a in ed._project.active_scene.actors if a.active), None)
    if actor is None:
        pytest.skip("la scène de démo n'a pas d'acteur actif")
    return actor


def _first_region(ed):
    from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
    p = ed._project
    for i, s in enumerate(p.scenes):
        if any(lay.elements for lay in p.scene_ui_layouts(s)):
            p.set_active_scene(i)
            ed.load_project(p)
            break
    items = [it for it in ed._gba_scene.items() if isinstance(it, UIRegionItem)]
    if not items:
        pytest.skip("aucune zone d'interface dans la démo")
    return items[0]._region


def _region_pos(ed, el):
    from ui.scene_manager.canvas.canvas_region_item import UIRegionItem
    it = next(it for it in ed._gba_scene.items()
              if isinstance(it, UIRegionItem) and it._region is el)
    return (it.pos().x(), it.pos().y())


def _actor_pos(ed, actor):
    it = ed._find_item(actor)
    return (it.x(), it.y())


def test_le_canvas_ne_suit_pas_le_modele_sans_resynchro(qapp, history):
    """Le point fin : muter le modèle (via un `MoveActorCmd`) ne bouge PAS l'item
    tant qu'on ne resynchronise pas. Sans ça, les tests suivants passeraient même
    si `reload_scene_items` ne servait à rien."""
    ed = _editor(ORBIT)
    actor = _first_actor(ed)
    p0 = _actor_pos(ed, actor)
    x0, y0 = actor.x, actor.y

    history.push(MoveActorCmd(actor, actor.x, actor.y, actor.x + 40, actor.y + 24))

    assert (actor.x, actor.y) == (x0 + 40, y0 + 24)
    assert _actor_pos(ed, actor) == p0


def test_resync_ramene_le_sprite(qapp, history):
    ed = _editor(ORBIT)
    actor = _first_actor(ed)
    p0 = _actor_pos(ed, actor)

    history.push(MoveActorCmd(actor, actor.x, actor.y, actor.x + 40, actor.y + 24))
    ed.reload_scene_items()
    assert _actor_pos(ed, actor) != p0          # l'item a suivi

    history.undo()
    ed.reload_scene_items()
    assert _actor_pos(ed, actor) == p0          # et il revient exactement


def test_resync_ramene_la_zone_dinterface(qapp, history):
    """Le correctif : un item de ZONE annulé revient à la position du modèle.
    Avant `reload_scene_items`, `_flush` ne reposait que les sprites — la zone
    restait à sa position draggée."""
    ed = _editor(MYGAME)
    el = _first_region(ed)
    p0 = _region_pos(ed, el)

    history.push(MoveUIRegionCmd(el, el.x, el.y, el.x + 16, el.y))
    ed.reload_scene_items()
    assert _region_pos(ed, el) != p0            # la zone a suivi (résolu)

    history.undo()
    ed.reload_scene_items()
    assert _region_pos(ed, el) == p0            # et revient exactement
