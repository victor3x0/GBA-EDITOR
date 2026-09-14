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


def test_le_workspace_bascule_vers_une_vue_enregistree(qapp):
    workspace = CanvasWorkspace(QWidget())
    graph = QWidget()
    seen = []
    workspace.view_changed.connect(seen.append)

    workspace.register_view("graph", graph)
    workspace.activate_view("graph")

    assert workspace.active_view == "graph"
    assert seen == ["graph"]


def test_le_workspace_refuse_un_nom_de_vue_duplique(qapp):
    workspace = CanvasWorkspace(QWidget())

    with pytest.raises(ValueError, match="existe déjà"):
        workspace.register_view("scene", QWidget())
