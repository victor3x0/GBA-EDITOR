"""Contrat minimal du conteneur de contextes Canvas."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QWidget

from ui.scene_manager.canvas.canvas_workspace import CanvasWorkspace


def test_le_workspace_monte_la_vue_scene_par_defaut(qapp):
    scene = QWidget()
    workspace = CanvasWorkspace(scene)

    assert workspace.scene_editor is scene
    assert workspace.active_view == CanvasWorkspace.SCENE_VIEW
    assert workspace.view("scene") is scene
    # La vue Graphe est possédée par le workspace, prête sans branchement externe.
    assert workspace.view("graph") is workspace.graph_view


def test_le_workspace_bascule_vers_le_graphe(qapp):
    workspace = CanvasWorkspace(QWidget())
    seen = []
    workspace.view_changed.connect(seen.append)

    workspace.activate_view(CanvasWorkspace.GRAPH_VIEW)

    assert workspace.active_view == "graph"
    assert seen == ["graph"]
    # Le bandeau reflète la vue active dans les deux sens.
    assert workspace._buttons["graph"].isChecked()


def test_le_bouton_de_bandeau_bascule_la_vue(qapp):
    workspace = CanvasWorkspace(QWidget())
    seen = []
    workspace.view_changed.connect(seen.append)

    workspace._buttons["graph"].click()

    assert workspace.active_view == "graph"
    assert seen == ["graph"]


def test_le_workspace_refuse_un_nom_de_vue_duplique(qapp):
    workspace = CanvasWorkspace(QWidget())

    with pytest.raises(ValueError, match="existe déjà"):
        workspace.register_view("scene", QWidget())


class _CountingScene(QWidget):
    """Faux SceneEditor qui compte ses rechargements."""

    def __init__(self):
        super().__init__()
        self.loads = 0

    def load_project(self, project):
        self.loads += 1


class _FakeProject:
    active_scene = object()
    scenes = ()

    class settings:
        start_scene = ""


def test_basculer_puis_revenir_ne_recharge_pas_lediteur_de_scene(qapp):
    scene = _CountingScene()
    workspace = CanvasWorkspace(scene)

    workspace.activate_view(CanvasWorkspace.GRAPH_VIEW)
    workspace.activate_view(CanvasWorkspace.SCENE_VIEW)

    # Changer de vue est un simple échange de widget : l'éditeur 2D reste intact.
    assert scene.loads == 0


def test_load_project_attache_le_projet_au_graphe_sans_le_projeter(qapp):
    scene = _CountingScene()
    workspace = CanvasWorkspace(scene)

    workspace.load_project(_FakeProject())

    # La scène se charge ; le graphe reçoit le projet mais ne projette qu'à
    # l'affichage (pull mémoïsé) — aucun script n'est lu ici.
    assert scene.loads == 1
    assert workspace.graph_view.graph is None
