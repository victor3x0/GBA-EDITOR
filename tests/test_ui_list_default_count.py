"""`g_ui_list_total` démarre au compte de RANGÉES authorées, pas à 0.

Avant ce correctif, un panneau « Liste » restait figé tant que le script
n'appelait pas `list.set_count` — même avec des rangées visibles et posées
dans le canvas. Un menu STATIQUE (un sélecteur de langue, un menu principal :
autant d'items que de rangées, jamais de défilement) n'a aucune raison de
répéter en script une information que l'éditeur connaît déjà. `list.set_count`
garde son rôle : dire un total plus grand que les rangées visibles (un
inventaire qui défile), auquel cas il écrase le défaut.

Bug réel signalé en relisant l'inspecteur de scène : son propre texte
(« place text zones INSIDE this panel — ceux-là sont ce que la liste
parcourt ») ne correspondait pas au comportement runtime.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def projet(tmp_path):
    from core.project import Project
    from core.models.ui_region import UILayout, UIPanel, UIText

    p = Project(tmp_path / "jeu")
    p.project_dir.mkdir(parents=True, exist_ok=True)

    panel = UIPanel(name="Selection_box", is_list=True)
    rows = [UIText(name=n, parent="Selection_box") for n in ("English", "Japanese", "French")]
    layout = UILayout(name="hud")
    layout.elements.append(panel)
    layout.elements += rows
    p.ui_layouts.append(layout)
    return p, panel


def _totals(src: str) -> list[int]:
    m = re.search(r"g_ui_list_total\[\] = \{([^}]*)\}", src)
    assert m, f"g_ui_list_total introuvable :\n{src}"
    return [int(x) for x in m.group(1).split(",")]


def test_le_total_par_defaut_est_le_compte_de_rangees(projet):
    from codegen.runtime_codegen.main_gen import emit_ui_lists_c
    p, _panel = projet
    src = "\n".join(emit_ui_lists_c(p))
    assert _totals(src) == [3]


def test_une_liste_sans_rangee_reste_a_zero(projet):
    """Aucune rangée posée : le défaut retombe sur 0, exactement comme avant
    — rien à parcourir tant que l'auteur n'a rien posé dans le panneau."""
    from core.models.ui_region import UILayout, UIPanel
    from core.project import Project
    p2 = Project(projet[0].root.parent / "vide")
    p2.project_dir.mkdir(parents=True, exist_ok=True)
    panel = UIPanel(name="Vide", is_list=True)
    layout = UILayout(name="hud")
    layout.elements.append(panel)
    p2.ui_layouts.append(layout)

    from codegen.runtime_codegen.main_gen import emit_ui_lists_c
    src = "\n".join(emit_ui_lists_c(p2))
    assert _totals(src) == [0]


def test_plusieurs_listes_gardent_chacune_leur_propre_compte(projet):
    from core.models.ui_region import UIPanel, UIText
    from codegen.runtime_codegen.main_gen import emit_ui_lists_c
    p, _panel = projet
    lay = p.ui_layouts[0]
    autre = UIPanel(name="Autre", is_list=True)
    lay.elements.append(autre)
    lay.elements += [UIText(name=f"row{i}", parent="Autre") for i in range(5)]

    src = "\n".join(emit_ui_lists_c(p))
    assert _totals(src) == [3, 5]
