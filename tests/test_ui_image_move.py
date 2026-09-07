"""Déplacer une image d'interface depuis un script (ROADMAP v0.22, 2026-09-02).

Le jalon s'appelle « Menus, listes et CURSEUR » et ne savait pas déplacer un
curseur : la navigation livrée surligne la rangée choisie, mais aucune API ne
donnait accès à la position d'une image. Écrit d'instinct,
`ui.get("Cursor").y = 40` traversait le checker sans un mot et produisait
`UIELEM_CURSOR.y` — `.y` sur un entier, refusé par gcc sur un fichier que
l'auteur n'a pas écrit.

Ce que ces tests protègent :

- la forme retenue est un APPEL DE MODULE à nom vérifié par domaine, pas une
  propriété — donc elle se valide et s'émet par les chemins GÉNÉRIQUES, sans
  une ligne de checker ni de codegen écrite pour l'occasion. C'est justement ce
  qu'un test doit surveiller : si quelqu'un ajoute plus tard un chemin dédié,
  c'est que la forme a dérivé ;
- le nom résout en `IMAGE_*` (index dans `g_ui_images`) et jamais en `UIELEM_*`
  (index dans `g_ui_elements`, la table de VISIBILITÉ qui couvre les trois
  types) — la confusion qui rendait le premier réflexe incompilable ;
- un nom d'image inconnu est refusé au build, en nommant les images du projet ;
- la fonction est vue des DEUX contextes de compilation — `gba_engine.h` pour
  `main.c`, et le prototype GÉNÉRÉ dans `runtime_api.h` pour les unités de scène/
  acteur (A2, « 4e lecteur »). Le piège d'antan — une redéclaration oubliée à la
  main — est fermé : ce qui est exposé et présent dans le moteur est extrait
  automatiquement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent


def _lua(src: str, images=("Curseur",), lists=("Menu",)):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = [e.message for e in check(script, BuildContext(
        actor_name="Sc", image_names=list(images), ui_list_names=list(lists),
    )) if e.level == "error"]
    code, _w, _s = generate(script, CodegenContext(
        actor_name="Sc", actor_sym="Sc", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=[],
        is_scene=True, image_names=list(images), ui_list_names=list(lists)))
    return errors, code


def _body(*lines: str) -> str:
    return "function on_update()\n" + "".join(f"    {l}\n" for l in lines) + "end\n"


# ── La forme, et ce en quoi elle compile ──────────────────────────


def test_le_deplacement_compile_en_appel_direct():
    errors, code = _lua(_body('ui.image_move("Curseur", 0, 16)'))
    assert errors == []
    assert "ui_image_move(IMAGE_CURSEUR, 0, 16)" in code


def test_le_nom_resout_en_index_dimage_pas_en_index_delement():
    """`UIELEM_*` indexe `g_ui_elements` (la VISIBILITÉ, trois types confondus),
    `IMAGE_*` indexe `g_ui_images`. Confondre les deux est ce qui rendait
    `ui.get("Cursor").y` incompilable ; le domaine évite la question."""
    _errors, code = _lua(_body('ui.image_move("Curseur", 4, 8)'))
    assert "IMAGE_CURSEUR" in code
    assert "UIELEM_CURSEUR" not in code


def test_la_lecture_est_symetrique_de_lecriture():
    errors, code = _lua(_body('local x = ui.image_dx("Curseur")',
                              'local y = ui.image_dy("Curseur")'))
    assert errors == []
    assert "ui_image_dx(IMAGE_CURSEUR)" in code
    assert "ui_image_dy(IMAGE_CURSEUR)" in code


def test_le_decalage_se_compose_avec_une_expression():
    """Le cas qui a motivé le chantier : un curseur qui suit l'item choisi."""
    errors, code = _lua(_body(
        'ui.image_move("Curseur", 0, 16 * list.index("Menu"))'))
    assert errors == []
    assert "ui_image_move(IMAGE_CURSEUR, 0, (16 * ui_list_index(UILIST_MENU)))" in code


# ── Ce que le domaine refuse tout seul ────────────────────────────


def test_une_image_inconnue_est_refusee_en_nommant_les_autres():
    errors, _code = _lua(_body('ui.image_move("Cusor", 0, 8)'))
    assert len(errors) == 1
    assert "Cusor" in errors[0] and "Curseur" in errors[0]


def test_le_nombre_darguments_est_verifie():
    errors, _code = _lua(_body('ui.image_move("Curseur", 8)'))
    assert errors and "argument" in errors[0]


# ── La forme n'a demandé aucun chemin dédié ───────────────────────


def test_aucun_emetteur_dedie_pour_ces_trois_appels():
    """Un appel de module dont l'argument porte un domaine déjà couvert se
    traduit par `_emit_api_call`. Si l'un des trois apparaît un jour dans
    `_CALL_CUSTOM`, c'est que la forme a dérivé vers un cas particulier — et
    c'est le moment de se demander pourquoi, pas de l'y laisser."""
    from scripting import codegen
    for nom in ("ui.image_move", "ui.image_dx", "ui.image_dy"):
        assert nom not in codegen._CALL_CUSTOM


def test_le_domaine_porte_le_renommage():
    """Porter `DOMAIN_IMAGE` n'est pas décoratif : c'est ce qui fait suivre un
    renommage d'image dans les scripts (`refactor.iter_refs`), sans liste de
    fonctions codée en dur."""
    from scripting.refactor import iter_refs
    from scripting.api import DOMAIN_IMAGE
    src = _body('ui.image_move("Curseur", 0, 8)')
    refs = list(iter_refs(src, domain=DOMAIN_IMAGE))
    assert [r.value for r in refs] == ["Curseur"]


# ── Le piège des deux prototypes, désormais fermé par génération ───


@pytest.mark.parametrize("fn", ["ui_image_move", "ui_image_dx", "ui_image_dy"])
def test_la_fonction_est_vue_des_deux_contextes(fn):
    """`main.c` voit `gba_engine.h` ; une unité d'acteur ou de scène voit le
    prototype GÉNÉRÉ dans `runtime_api.h` (A2, « 4e lecteur »). Le piège d'antan —
    une redéclaration oubliée à la main dans `runtime_api_inline.h` — n'existe plus :
    ce qui est dans le moteur et exposé est extrait et émis automatiquement. Le
    test protège donc l'invariant sous sa forme actuelle : présent dans le moteur,
    et repris par la génération."""
    from codegen.runtime_codegen.api_prototypes import (
        build_prototype_block, exposed_engine_names,
    )
    moteur = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(encoding="utf-8")
    assert fn in moteur
    decls, _ = build_prototype_block(moteur, exposed_engine_names())
    assert any(f"extern " in d and f" {fn}(" in d for d in decls), \
        f"{fn} n'est pas repris par la génération de prototypes"


def test_le_decalage_est_remis_a_zero_entre_deux_scenes():
    """`ui_images_reset` ferme les images de la scène précédente. Sans les deux
    champs, revenir dans un menu retrouverait le curseur là où on l'avait
    laissé, alors que tout le reste de la scène repart de sa mise en page."""
    moteur = (REPO_DIR / "runtime" / "include" / "gba_engine.h").read_text(encoding="utf-8")
    debut = moteur.index("void ui_images_reset(void)")
    corps = moteur[debut: moteur.index("\n}", debut)]
    assert "dx" in corps and "dy" in corps
