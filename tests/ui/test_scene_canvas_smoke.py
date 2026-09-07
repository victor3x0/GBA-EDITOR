"""Filet de sécurité de `scene_canvas` avant sa découpe (ARCHI A1 + A3).

`scene_canvas.py` (5 227 lignes) part en sous-package `ui/scene_manager/canvas/`.
Contrairement au découpage de `main_gen` — prouvé neutre par « C généré identique
+ md5 ROM » —, la couche UI n'a AUCUN oracle : un `paint()` ou un `itemChange()`
cassé par un déplacement passe inaperçu jusqu'à l'usage manuel. Ces smoke tests
sont ce filet : ils chargent une VRAIE scène de démo dans un `SceneEditor`
headless et vérifient que le canvas reflète le modèle. L'attendu est DÉRIVÉ du
modèle (nombre d'acteurs, éléments d'interface), jamais figé sur le contenu d'une
démo — ils tiennent donc même si la démo évolue, et n'attrapent que ce que la
découpe pourrait casser : les items ne se créent plus, la sélection ne se propage
plus, la façade ne réexporte plus son API.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.project import Project

REPO_DIR = Path(__file__).resolve().parent.parent.parent
MYGAME = REPO_DIR / "Project Demo" / "MyGame"
ORBIT = REPO_DIR / "Project Demo" / "OrbitTest"


def _editor(project_dir: Path):
    """Un `SceneEditor` ayant chargé la démo — ou skip si la démo manque."""
    if not project_dir.exists():
        pytest.skip(f"démo absente : {project_dir}")
    from ui.scene_manager.scene_canvas import SceneEditor
    ed = SceneEditor()
    ed.load_project(Project.open(project_dir))
    return ed


def _use_scene(ed, predicate, why: str):
    """Rend active la première scène qui satisfait `predicate` et recharge le
    canvas dessus. La scène active PERSISTÉE (`last_scene`) n'est pas fiable pour
    un test — on choisit la scène par ce qu'elle contient, via le modèle."""
    p = ed._project
    for i, scene in enumerate(p.scenes):
        if predicate(scene):
            p.set_active_scene(i)
            ed.load_project(p)
            return scene
    pytest.skip(f"aucune scène de démo ne satisfait : {why}")


def _counts(ed):
    from ui.scene_manager.scene_canvas import SpriteItem, UIRegionItem, CameraItem
    items = ed._gba_scene.items()
    return (
        sum(1 for i in items if isinstance(i, SpriteItem)),
        sum(1 for i in items if isinstance(i, UIRegionItem)),
        sum(1 for i in items if isinstance(i, CameraItem)),
    )


def test_la_facade_reexporte_son_api_publique(qapp):
    """Les trois seuls noms qui sortent du fichier — `window.py` importe
    `SceneEditor`, `canvas_tools` importe `GBAView`+`SpriteItem`. La découpe doit
    les garder importables depuis `scene_canvas`, sinon elle casse l'extérieur."""
    from ui.scene_manager.scene_canvas import SceneEditor, GBAView, SpriteItem
    assert all(x is not None for x in (SceneEditor, GBAView, SpriteItem))


def test_un_sprite_item_par_acteur(qapp):
    """`_reload_sprites` pose un `SpriteItem` par acteur de la scène (placeholder
    compris) : le canvas montre autant d'items que le modèle a d'acteurs."""
    ed = _editor(MYGAME)
    scene = _use_scene(ed, lambda s: len(s.actors) > 0, "au moins un acteur")
    n_sprite, _, _ = _counts(ed)
    assert n_sprite == len(scene.actors)


def test_un_item_par_element_dinterface(qapp):
    """`set_ui_regions` pose un `UIRegionItem` par élément de CHAQUE nœud
    Interface de la scène. L'attendu vient de `scene_ui_layouts`, la même source
    que l'éditeur — donc c'est bien « tout élément authoré a son item »."""
    ed = _editor(MYGAME)
    p = ed._project
    scene = _use_scene(
        ed, lambda s: sum(len(l.elements) for l in p.scene_ui_layouts(s)) > 0,
        "au moins un élément d'interface")
    expected = sum(len(lay.elements) for lay in p.scene_ui_layouts(scene))
    _, n_ui, _ = _counts(ed)
    assert n_ui == expected


def test_au_moins_une_camera(qapp):
    """Toute scène a sa caméra principale — au moins un `CameraItem` posé."""
    ed = _editor(ORBIT)
    _, _, n_cam = _counts(ed)
    assert n_cam >= 1


def test_la_selection_dun_acteur_se_propage_au_canvas(qapp):
    """Chemin bus → canvas (`on_selection`) : sélectionner un acteur doit
    sélectionner SON item et le rendre actif. C'est l'invariant de fiabilité que
    la revue a relevé (l'inspecteur reflète la sélection) ; un `_find_item` ou un
    `set_active_item` cassé par la découpe tombe ici."""
    ed = _editor(MYGAME)
    scene = _use_scene(ed, lambda s: any(a.active for a in s.actors),
                       "au moins un acteur actif")
    actor = next(a for a in scene.actors if a.active)

    ed.on_selection(actor)

    item = ed._find_item(actor)
    assert item is not None and item.isSelected()
    assert ed._gba_scene.active_item is item


def test_changer_de_scene_reconstruit_les_items(qapp):
    """Changer de scène active puis recharger reconstruit les items d'interface
    pour la NOUVELLE scène — le compte suit son modèle, pas celui d'avant."""
    ed = _editor(MYGAME)
    p = ed._project
    if len(p.scenes) < 2:
        pytest.skip("démo mono-scène")
    for i, scene in enumerate(p.scenes):
        p.set_active_scene(i)
        ed.load_project(p)
        expected = sum(len(lay.elements) for lay in p.scene_ui_layouts(scene))
        _, n_ui, _ = _counts(ed)
        assert n_ui == expected, f"scène {scene.name}"
