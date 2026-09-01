"""`lang.set`/`lang.get` (ROADMAP v0.9, phase 4).

Rien de plus que ces deux appels côté script : la police effective
(`g_lang_font`, phase 3.2) et le sous-ensemble de glyphes ÉMIS (union de
toutes les langues, phase 3.3) sont déjà prêts pour n'importe quelle langue.
Ce que ces tests protègent :

- une langue non déclarée refuse de compiler, comme une scène inconnue ;
- un projet monolingue (`lang_codes = []`) refuse TOUT code, sans cas
  spécial à écrire ;
- `lang.set("fr")` résout au CODE C `LANG_FR`, jamais une chaîne au runtime —
  même mécanique que `TEXT_*`/`SCENE_IDX_*` ;
- l'ordre des `#define LANG_*` suit `lang_codes` (source en 0).
"""
from __future__ import annotations

import pytest


def _errors(src: str, **ctx_kw) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    errs = check(parse(src), BuildContext(actor_name="Scene", **ctx_kw))
    return [e.message for e in errs if e.level == "error"]


_CALL_LANG = 'function on_update()\n    lang.set("fr")\nend\n'
_CALL_GET  = 'function on_update()\n    if lang.get() == 0 then end\nend\n'


def test_langue_declaree_compile():
    assert _errors(_CALL_LANG, lang_codes=["en", "fr"]) == []


def test_langue_non_declaree_refuse():
    errs = _errors(_CALL_LANG, lang_codes=["en", "de"])
    assert errs and "fr" in errs[0] and "introuvable" in errs[0]


def test_projet_monolingue_refuse_tout_code():
    """`lang_codes = []` (jamais None ici) : aucun code n'est valide, il n'y
    a rien à choisir."""
    errs = _errors(_CALL_LANG, lang_codes=[])
    assert errs and "fr" in errs[0]


def test_lang_get_ne_cite_aucun_domaine():
    """`lang.get()` ne prend pas d'argument — rien à valider, aucun message."""
    assert _errors(_CALL_GET, lang_codes=[]) == []


def test_contexte_absent_relache_la_verification():
    """`lang_codes=None` (info absente, pas déclarée par l'appelant) : même
    contrat que tout le reste de `BuildContext` — pas de faux négatif."""
    assert _errors(_CALL_LANG) == []


def _gen(src: str, lang_codes):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = [e.message for e in check(script, BuildContext(
        actor_name="Scene", lang_codes=lang_codes)) if e.level == "error"]
    code, _warnings, _state = generate(script, CodegenContext(
        actor_name="Scene", actor_sym="Scene", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=[], is_scene=True, lang_codes=lang_codes))
    return errors, code


def test_lang_set_resout_en_constante_c():
    errors, code = _gen(_CALL_LANG, ["en", "fr"])
    assert errors == []
    assert "lang_set(LANG_FR)" in code
    assert '"fr"' not in code   # jamais une chaîne au runtime


def test_defines_langue_dans_l_ordre_source_puis_declarees():
    _errors_, code = _gen(_CALL_LANG, ["en", "jap", "fr"])
    assert "#define LANG_EN 0" in code
    assert "#define LANG_JAP 1" in code
    assert "#define LANG_FR 2" in code


def test_aucune_langue_declaree_n_emet_aucun_define():
    """Projet monolingue : pas de bloc `/* Langues */` du tout — rien à
    choisir, rien à nommer."""
    _errors_, code = _gen(_CALL_GET, [])
    assert "LANG_" not in code
