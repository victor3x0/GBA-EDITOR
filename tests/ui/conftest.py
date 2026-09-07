"""Harnais des tests de la couche UI (ARCHI A1) — un `QApplication` headless.

La couche UI était jusqu'ici sans test (cf. TodoTechnique, A1) : le code le plus
gros et le plus mouvant, sans filet. Ces tests-là ont besoin d'instancier de
vrais widgets Qt, donc d'un `QApplication` — mais sans écran. La plateforme
`offscreen` (livrée avec PyQt6) le permet, et c'est elle qui rend ces tests
exécutables en CI comme en local.

`sys.path` est déjà posé par `tests/conftest.py` (racine) : ce conftest-ci
n'ajoute que le `QApplication`. Il doit être choisi AVANT tout import de PyQt6,
d'où le `os.environ` en tête de module.
"""
from __future__ import annotations

import os

# Avant le premier import de PyQt6 : pas d'écran requis.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """L'unique `QApplication` de la session — un widget Qt ne peut exister sans
    lui. Réutilisé s'il existe déjà (un autre test UI a pu le créer)."""
    app = QApplication.instance() or QApplication([])
    yield app
