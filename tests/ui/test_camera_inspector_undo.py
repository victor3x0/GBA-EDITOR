"""CameraInspector ↔ historique — le round-trip édition → undo/redo (ARCHI A1).

Ces tests gardent un CORRECTIF, pas seulement un invariant : jusqu'au 2026-09-07,
l'édition de caméra mutait l'objet en direct puis sauvait — **sans passer par
l'historique**. Ctrl+Z ne défaisait aucune modification de caméra, ni depuis
l'inspecteur ni depuis le drag canvas. Les handlers passent désormais par `_edit`
(→ `SetFieldCmd`/`MacroCmd`), comme l'actor et l'UIRegion ; le drag canvas pousse
un `MoveCameraCmd`. On verrouille ici le comportement annulable, pour qu'une
régression qui recâblerait l'édition « en direct » retombe.
"""
from __future__ import annotations

import pytest

from core.history import get_history
from core.models.camera import Camera
from core.models.scene import Scene
from ui.scene_manager.inspectors.camera_inspector import CameraInspector


@pytest.fixture
def history():
    h = get_history()
    h.clear()
    yield h
    h.clear()


def _loaded():
    """Un `CameraInspector` chargé sur une caméra RÉELLE d'une scène (édition
    sans projet : seule la matérialisation en aurait besoin, cf. `_mutable`).
    Retourne (inspecteur, caméra, scène)."""
    scene = Scene(name="S1")
    cam = Camera(name="Cam", x=0, y=0, margin_x=10, margin_y=10)
    scene.cameras.append(cam)
    scene.camera = "Cam"
    insp = CameraInspector()
    insp.load(scene, cam, project=None)
    return insp, cam, scene


def test_une_edition_cree_une_entree_annulable(qapp, history):
    insp, cam, _ = _loaded()

    insp._margin_x.setValue(50)

    assert cam.margin_x == 50
    assert history.can_undo
    assert history.undo_label == "Camera margins"


def test_undo_restaure_et_linspecteur_le_reflete(qapp, history):
    insp, cam, scene = _loaded()

    insp._margin_x.setValue(50)
    insp._pos_x.setValue(64)             # champ + label DIFFÉRENTS → 2e entrée
    assert (cam.margin_x, cam.x) == (50, 64)

    history.undo()                        # défait la position
    assert (cam.margin_x, cam.x) == (50, 0)
    history.undo()                        # défait la marge
    assert (cam.margin_x, cam.x) == (10, 0)

    insp.load(scene, cam, project=None)
    assert insp._margin_x.value() == 10
    assert insp._pos_x.value() == 0


def test_redo_rejoue(qapp, history):
    insp, cam, _ = _loaded()

    insp._margin_x.setValue(50)
    history.undo()
    assert cam.margin_x == 10
    assert history.can_redo

    history.redo()
    assert cam.margin_x == 50


def test_un_no_op_ne_cree_aucune_commande(qapp, history):
    insp, cam, _ = _loaded()

    insp._edit([(cam, "margin_x", cam.margin_x)], "Camera margins")   # déjà 10

    assert not history.can_undo


def test_frappes_fusionnees_une_seule_entree(qapp, history):
    """Tirer une marge est UN geste : la salve sur le même champ fusionne, un
    seul undo revient à l'origine (`SetFieldCmd.merge`)."""
    insp, cam, _ = _loaded()

    insp._margin_x.setValue(20)
    insp._margin_x.setValue(35)
    insp._margin_x.setValue(50)
    assert cam.margin_x == 50

    history.undo()
    assert cam.margin_x == 10             # l'origine, pas 35 ni 20
    assert not history.can_undo


def test_recalc_bounds_est_une_seule_entree(qapp, history):
    """Le bouton « recalc » pose QUATRE bornes d'un coup : une seule entrée
    d'historique (`MacroCmd`), pas quatre annulations pour un clic."""
    insp, cam, _ = _loaded()

    # Poser des bornes via le groupe, comme le bouton (signaux bloqués + commit).
    for sp, v in ((insp._bounds_x, 0), (insp._bounds_y, 0),
                  (insp._bounds_w, 256), (insp._bounds_h, 128)):
        sp.blockSignals(True)
        sp.setValue(v)
        sp.blockSignals(False)
    insp._on_bounds_changed()

    assert (cam.bounds_w, cam.bounds_h) == (256, 128)
    assert history.can_undo

    history.undo()
    assert cam.bounds_w is None and cam.bounds_h is None
    assert not history.can_undo           # UNE entrée pour les quatre bornes
