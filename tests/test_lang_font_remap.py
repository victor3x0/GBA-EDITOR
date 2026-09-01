"""`g_lang_font` — le remap de police par langue (ROADMAP v0.9, phase 3.2).

Le projet démo Fonts&Texts n'exerce PAS le chemin de substitution : sa seule
police (`ark-pixel-10px-monospaced-ja`) couvre nativement le latin et le
japonais, donc `Language.fonts` y reste vide pour les deux langues — c'est le
cas COURANT (identité), pas le cas qui a besoin d'être prouvé ici. Ces tests
couvrent l'autre chemin : une langue qui déclare une VRAIE police de
remplacement.
"""
from __future__ import annotations

import re

from types import SimpleNamespace


def _lang(code: str, fonts: dict | None = None):
    return SimpleNamespace(code=code, fonts=fonts or {})


def _idxs(src: str, table: str) -> list[int]:
    m = re.search(re.escape(table) + r"\[\d+\] = \{([^}]*)\}", src)
    assert m, f"{table} introuvable dans :\n{src}"
    return [int(x) for x in m.group(1).split(",")]


def test_aucune_langue_declaree_est_identite():
    from codegen.font_emit import emit_lang_fonts_c
    src = "\n".join(emit_lang_fonts_c(["dialog"], []))
    assert "g_lang_font[1]" in src
    assert _idxs(src, "g_lang_font_0") == [0]


def test_langue_sans_remplacement_declare_est_identite():
    """Le cas courant EN/FR/DE/ES du modèle : `Language.fonts` vide, la même
    planche latine sert toutes les langues sans qu'aucune entrée existe."""
    from codegen.font_emit import emit_lang_fonts_c
    fr = _lang("fr")   # fonts={} — rien déclaré
    src = "\n".join(emit_lang_fonts_c(["dialog", "title"], [_lang("en"), fr]))
    assert _idxs(src, "g_lang_font_0") == [0, 1]   # source : toujours identité
    assert _idxs(src, "g_lang_font_1") == [0, 1]   # fr : identité aussi, rien à remplacer


def test_langue_avec_remplacement_pointe_l_autre_police():
    """Le cas d'un système d'écriture qui A BESOIN d'une autre planche —
    celui que le projet démo Fonts&Texts, lui, n'a pas besoin de déclarer."""
    from codegen.font_emit import emit_lang_fonts_c
    ja = _lang("ja", fonts={"dialog": "dialog_ja"})
    src = "\n".join(emit_lang_fonts_c(["dialog", "dialog_ja", "title"], [_lang("en"), ja]))
    # source : identité partout
    assert _idxs(src, "g_lang_font_0") == [0, 1, 2]
    # ja : "dialog" (index 0) résout vers "dialog_ja" (index 1) ; "title" (non
    # remplacé) reste lui-même.
    assert _idxs(src, "g_lang_font_1") == [1, 1, 2]


def test_remplacement_vers_une_police_absente_retombe_sur_l_identite():
    """Un nom mal tapé ou un asset supprimé ne doit pas produire un index hors
    bornes — au validateur de le signaler, pas à ce module de deviner."""
    from codegen.font_emit import emit_lang_fonts_c
    de = _lang("de", fonts={"dialog": "police_qui_n_existe_plus"})
    src = "\n".join(emit_lang_fonts_c(["dialog"], [_lang("en"), de]))
    assert _idxs(src, "g_lang_font_1") == [0]
