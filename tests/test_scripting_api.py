"""Les trois défauts de l'API scriptée qui ne se voyaient qu'au `make`, ou pas
du tout.

Ils ont en commun de ne produire AUCUN message à l'endroit de la faute : une
API retirée qui continuait de marcher, une constante émise mais introuvable
dans l'unité de compilation, un réglage nommé retombé sur un entier nu. C'est
la définition d'un test ici (cf. `tests/` dans ARCHITECTURE) — une erreur
silencieuse, pas une exception.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent


def _lua(src: str, **ctx_kw):
    """Parse + check + génère, avec un contexte de build minimal."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball", anim_names=["idle"], **ctx_kw))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=["idle"], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(), all_actor_syms=["Ball"]))
    return errors, code


def _errors(src: str, **ctx_kw) -> list[str]:
    return [e.message for e in _lua(src, **ctx_kw)[0] if e.level == "error"]


# ── 1. Une API retirée doit être RETIRÉE, sur tous les récepteurs ──


def _setter_spellings() -> list[tuple[str, str]]:
    """(propriété, orthographe en méthode qui tomberait sur sa fonction C).

    `codegen._invoke` traduit une méthode inconnue en `actor_<méthode>(récepteur,
    ...)`. Pour toute propriété dont le setter C s'appelle `actor_set_<champ>`,
    l'orthographe `self:set_<champ>(v)` produit donc du C qui compile et qui
    MARCHE. Dérivé du catalogue, ce cas de test suit chaque propriété ajoutée."""
    from scripting.api import RUNTIME_PROPS

    out = []
    for name, p in RUNTIME_PROPS.items():
        if p.c_setter and p.c_setter.startswith("actor_set_"):
            out.append((name, "set_" + p.c_setter[len("actor_set_"):]))
    return out


@pytest.mark.parametrize("prop,method", _setter_spellings(),
                         ids=[m for _, m in _setter_spellings()])
def test_aucune_orthographe_en_methode_ne_double_une_propriete(prop, method):
    """Un état s'écrit d'UNE façon. `self:set_frame(0)` doit être refusé à la
    ligne fautive — sinon il traverse en simple avertissement, le repli du
    codegen tombe sur `actor_set_frame`, et l'ancienne API survit sans
    documentation à côté de `self.frame = 0`."""
    errs = _errors(f"function on_update(self)\n self:{method}(0)\nend\n")
    assert errs, (f"self:{method}() n'est pas refusé : il double {prop} "
                  f"et le C émis compile.")


def test_api_retiree_bloque_sur_self():
    errs = _errors("function on_update(self)\n self:set_frame(0)\nend\n")
    assert errs and "self.frame" in errs[0]


def test_api_retiree_bloque_aussi_sur_un_autre_recepteur():
    """`other:set_position(p)` émettait `actor_set_position(other, p)` — du C qui
    compile et marche. L'API retirée survivait tant qu'on ne l'écrivait pas sur
    `self`."""
    errs = _errors("function on_collide(self, other)\n"
                   " other:set_position(vec2(1, 2))\nend\n")
    assert errs and "other.<champ>" in errs[0]


def test_methode_inconnue_signalee_sur_tout_recepteur():
    """Un `:` ne peut désigner qu'une méthode du catalogue : hors de lui, il n'y
    a rien à traduire, et `_invoke` inventerait un `actor_nawak(other, 1)`."""
    errs = _errors("function on_collide(self, other)\n other:nawak(1)\nend\n")
    assert errs and "other:nawak" in errs[0]


def test_methode_valide_sur_un_autre_recepteur_reste_valide():
    """La validation ne doit pas devenir un refus : une méthode du catalogue
    s'appelle sur n'importe quel Actor* nommé."""
    errs, code = _lua("function on_collide(self, other)\n"
                      " other:move(vec2(1, 0), 2)\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_move(other," in code


def test_nom_de_ressource_du_recepteur_refuse():
    """`other:play_anim("idle")` : le nom est résolu contre le SpriteAsset de
    l'acteur qui EXÉCUTE (`anim_constant(ctx.actor_sym, ...)`), donc le C émis
    citerait l'animation d'un autre acteur — crédible et faux."""
    errs = _errors("function on_collide(self, other)\n"
                   " other:play_anim('idle')\nend\n")
    assert errs and "self" in errs[0]


# ── 2. Les constantes vivent dans les DEUX en-têtes ────────────────


def test_constantes_denumeration_declarees_dans_la_facade():
    """`actor_api_static.h` est le seul en-tête que voient les unités de scène et
    d'acteur. Une constante émise par le codegen mais définie seulement dans
    `gba_engine.h` échoue au `make`, sur la ligne générée et jamais sur sa
    cause."""
    from scripting.api import HARDWARE_ENUMS

    facade = (REPO_DIR / "runtime" / "include" / "actor_api_static.h").read_text(
        encoding="utf-8", errors="ignore")
    missing = sorted({
        c for table in HARDWARE_ENUMS.values() for c in table.values()
        if not re.search(r"^\s*#\s*define\s+" + re.escape(c) + r"\b", facade, re.M)
    })
    assert missing == [], f"constantes absentes de actor_api_static.h : {missing}"


def test_les_deux_entetes_saccordent_sur_les_valeurs():
    """main.c inclut les deux : une valeur divergente serait une redéfinition,
    donc bruyante — ce test la nomme avant le compilateur."""
    from scripting.api import HARDWARE_ENUMS

    inc = REPO_DIR / "runtime" / "include"
    facade = (inc / "actor_api_static.h").read_text(encoding="utf-8", errors="ignore")
    engine = (inc / "gba_engine.h").read_text(encoding="utf-8", errors="ignore")

    def value(src: str, name: str):
        m = re.search(r"^\s*#\s*define\s+" + re.escape(name) + r"\s+(\S+)", src, re.M)
        return m.group(1) if m else None

    for table in HARDWARE_ENUMS.values():
        for c in table.values():
            a, b = value(facade, c), value(engine, c)
            if a is not None and b is not None:
                assert a == b, f"{c} vaut {a} dans la façade et {b} dans le moteur"


def test_le_c_emis_cite_la_constante_pas_le_nombre():
    _, code = _lua("function on_update(self)\n"
                   " window.set_layer('win0', 1, true)\n"
                   " blend.set_layer('top', 2, true)\nend\n")
    assert "window_set_layer(WINR_0," in code
    assert "blend_set_layer(BLD_SIDE_TOP," in code


# ── 3. Une propriété d'énumération s'écrit et se compare par son NOM ─


def test_propriete_denumeration_ecrite_par_son_nom():
    errs, code = _lua("function on_update(self)\n"
                      " self.obj_mode = 'window'\n"
                      " blend.mode = 'alpha'\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_set_obj_mode(self, OBJ_MODE_WINDOW)" in code
    assert "blend_set_mode(BLD_MODE_ALPHA)" in code


def test_propriete_denumeration_comparee_par_son_nom():
    """Sans traduction, la comparaison partirait sur une chaîne C là où le getter
    rend un entier : gcc accepte, et le test est toujours faux."""
    errs, code = _lua("function on_update(self)\n"
                      " if blend.mode == 'alpha' then blend.mode = 'none' end\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "blend_get_mode() == BLD_MODE_ALPHA" in code


def test_entier_nu_refuse_sur_une_propriete_denumeration():
    errs = _errors("function on_update(self)\n self.obj_mode = 2\nend\n")
    assert errs and "nom" in errs[0]


def test_valeur_inconnue_refusee():
    errs = _errors("function on_update(self)\n blend.mode = 'alfa'\nend\n")
    assert errs and "alfa" in errs[0]


def test_aucune_enumeration_materielle_nest_orpheline():
    """Une table de `HARDWARE_ENUMS` que plus aucun paramètre ni propriété ne cite
    est du vocabulaire mort — et son domaine oblige quand même checker et codegen
    à garder une entrée. C'est ce qui est arrivé à OBJ_MODES et BLEND_MODES le
    jour où leurs réglages sont devenus des propriétés."""
    from scripting.api import RUNTIME_API, RUNTIME_PROPS, HARDWARE_ENUMS

    cites = {p.domain for f in RUNTIME_API.values() for p in f.params}
    cites |= {p.domain for p in RUNTIME_PROPS.values()}
    orphelins = sorted(set(HARDWARE_ENUMS) - cites)
    assert orphelins == [], f"énumérations citées par personne : {orphelins}"


# ── 4. Un état, une orthographe ────────────────────────────────────
# La direction s'écrivait trois fois pour un seul couple `dir_x`/`dir_y` : un
# vec2, une boussole nommée, et un entier 0-8 en lecture — qu'on POSAIT par un
# nom et qu'on RELISAIT en nombre.


def test_la_direction_secrit_des_deux_facons_sur_une_seule_propriete():
    errs, code = _lua("function on_update(self)\n"
                      " self.direction = \"north_east\"\n"
                      " self.direction = vec2(1, -1)\n"
                      " self.flip_h = self.direction.x < 0\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    # Deux portes C pour un seul état : l'index de boussole, et le vecteur.
    assert "actor_set_dir(self, DIR_NORTH_EAST)" in code
    assert "actor_set_direction(self, (Vec2){1, (-1)})" in code
    assert "actor_get_direction(self).x" in code


def test_la_direction_se_compare_par_son_nom():
    """Le getter ordinaire rend un `Vec2`, que le C ne sait pas comparer : sans
    la porte nommée, `self.direction == "west"` produirait du C invalide."""
    errs, code = _lua('function on_update(self)\n'
                      ' if self.direction == "west" then self.frame = 0 end\nend\n')
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_get_dir(self) == DIR_WEST" in code


@pytest.mark.parametrize("old,prop", [
    ('self:set_dir("north")',  "self.direction"),
    ("self:get_dir()",         "self.direction"),
    ("self:set_auto_dir(true)", "self.auto_dir"),
    ("self:on_ground()",       "self.grounded"),
])
def test_les_anciennes_orthographes_guident_vers_la_propriete(old, prop):
    errs = _errors(f"function on_update(self)\n local x = {old}\nend\n")
    assert errs and prop in errs[0]


def test_auto_dir_se_lit_maintenant():
    """L'ancien `set_auto_dir` n'avait pas de getter : un script qui voulait le
    basculer devait tenir son propre drapeau à côté de celui du moteur."""
    errs, code = _lua("function on_update(self)\n"
                      " if self.auto_dir then self.auto_dir = false end\nend\n")
    assert [e for e in errs if e.level == "error"] == []
    assert "actor_get_auto_dir(self)" in code and "actor_set_auto_dir(self, 0)" in code


def test_grounded_est_en_lecture_seule():
    errs = _errors("function on_update(self)\n self.grounded = true\nend\n")
    assert errs and "lecture seule" in errs[0]


def test_le_getter_dauto_dir_existe_en_c():
    """Une propriété sans lecture n'en est pas une — et le garde-fou des
    prototypes ne voit que ce qui est déjà dans `gba_engine.h`, donc il n'aurait
    pas signalé l'absence de celle-ci."""
    from scripting.api import RUNTIME_PROPS

    facade = (REPO_DIR / "runtime" / "include" / "actor_api_static.h").read_text(
        encoding="utf-8", errors="ignore")
    for name, p in RUNTIME_PROPS.items():
        for fn in (p.c_getter, p.c_setter, p.c_getter_named, p.c_setter_named):
            if fn and fn.startswith("actor_"):
                assert re.search(r"\b" + re.escape(fn) + r"\s*\(", facade), (
                    f"{name} : {fn}() n'existe pas dans actor_api_static.h")


# ── 5. L'état d'une image se vérifie DANS son sprite ───────────────


def _ui_errors(src: str) -> list[str]:
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    ctx = BuildContext(actor_name="HUD", image_names=["coeur_1", "curseur"],
                       image_states={"coeur_1": ["plein", "vide"],
                                     "curseur": ["on", "off"]})
    return [e.message for e in check(parse(src), ctx) if e.level == "error"]


def test_etat_dimage_valide():
    assert _ui_errors('function on_update(self)\n'
                      ' ui.image_set("coeur_1", "vide")\nend\n') == []


def test_etat_dimage_inconnu_refuse_avec_les_etats_du_bon_sprite():
    """« vide » est valide sur coeur_1 et pas sur curseur : l'ensemble valide se
    lit sur l'IMAGE citée, jamais sur le projet entier."""
    errs = _ui_errors('function on_update(self)\n'
                      ' ui.image_set("curseur", "vide")\nend\n')
    assert errs and "on, off" in errs[0]


def test_image_inconnue_ne_produit_quune_seule_erreur():
    errs = _ui_errors('function on_update(self)\n'
                      ' ui.image_set("nawak", "vide")\nend\n')
    assert len(errs) == 1 and "introuvable" in errs[0]


# ── 6. L'écran de référence décrit l'API qui existe ────────────────


def test_le_json_de_reference_ne_decrit_que_lapi_vivante():
    """`api_reference.json` a décrit pendant des mois `display.print` et
    `text.draw_box`. La réconciliation les cachait ; le fichier mentait quand
    même, et personne ne le relisait."""
    from scripting import api_reference

    api_reference.get_categories()
    assert sorted(set(api_reference.STALE)) == []


def test_toute_entree_du_catalogue_est_rangee_et_aucune_ne_finit_en_vrac():
    from scripting import api_reference
    from scripting.api import RUNTIME_API, RUNTIME_PROPS

    cats = api_reference.get_categories()
    labels = {e["label"].split("(")[0].split(" =")[0].strip()
              for c in cats for e in c["entries"]}
    manquants = (set(RUNTIME_API) | set(RUNTIME_PROPS)) - labels
    assert manquants == set(), f"absents de l'écran : {sorted(manquants)}"
    assert not any(c["name"] == "Autres" for c in cats), (
        "une entrée est tombée dans le fourre-tout : donne-lui une catégorie "
        "dans api_reference.json ou dans _PROP_HOME")
    assert all(c["entries"] for c in cats), "catégorie sans entrée"


def test_lordre_du_json_gouverne_lecran():
    """Une catégorie vidée par le filtre gardait son en-tête mais perdait sa
    place : « Transform », première du fichier, se recréait en dernier une fois
    ses cinq entrées retirées."""
    import json

    from scripting import api_reference

    brut = json.loads((REPO_DIR / "editor" / "scripting" / "api_reference.json")
                      .read_text(encoding="utf-8"))
    attendu = [c["name"] for c in brut["categories"]]
    rendu   = [c["name"] for c in api_reference.get_categories()]
    assert rendu == [n for n in attendu if n in rendu]
    assert rendu[0] == "Transform"


# ── 7. L'identité d'un acteur se cite par son nom ──────────────────
# `self.tag` rendait un entier opaque qu'aucune écriture Lua ne permettait de
# nommer : sa doc disait « utile pour identifier other » sans dire comment.


def _tag_lua(src: str):
    from scripting.parser import parse
    from scripting.checker import check, BuildContext
    from scripting.codegen import generate, CodegenContext

    script = parse(src)
    errors = check(script, BuildContext(actor_name="Ball",
                                        actor_names=["PADDLE_PL"],
                                        prefab_names=["Bullet"]))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball", "PADDLE_PL"]))
    return [e.message for e in errors if e.level == "error"], code


def test_le_tag_se_compare_par_le_nom_de_lacteur():
    errs, code = _tag_lua('function on_collide(self, other)\n'
                          ' if other.tag == "PADDLE_PL" then self:destroy() end\nend\n')
    assert errs == []
    assert "actor_get_tag(other) == TAG_PADDLE_PL" in code


def test_le_tag_accepte_aussi_un_prefab():
    """`headers.py` émet un TAG_* par acteur de scène ET par prefab poolé."""
    errs, code = _tag_lua('function on_collide(self, other)\n'
                          ' if other.tag == "Bullet" then self:destroy() end\nend\n')
    assert errs == []
    assert "TAG_BULLET" in code


def test_identite_inconnue_refusee():
    """Sans `#define`, le C généré cite un identifiant qui n'existe pas — même
    sévérité que pour une scène ou un prefab inconnus."""
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.tag == "Nawak" then end\nend\n')
    assert errs and "aucun acteur ni prefab" in errs[0]


def test_le_tag_ne_se_compare_pas_a_un_nombre():
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' if other.tag == 0 then end\nend\n')
    assert errs and "par son nom" in errs[0]


def test_les_messages_nomment_le_recepteur_ecrit():
    """Le catalogue range les propriétés d'actor sous `self.<champ>` : une clé,
    pas une restriction. Un message qui reprendrait la clé citerait à l'auteur
    une ligne qu'il n'a pas écrite."""
    errs, _ = _tag_lua('function on_collide(self, other)\n'
                       ' other.tag = "Bullet"\nend\n')
    assert errs and errs[0].startswith("other.tag")


def test_aucun_domaine_declare_nest_orphelin():
    """Un `DOMAIN_*` que ni un paramètre ni une propriété ne cite est du
    vocabulaire mort — et il oblige quand même checker et codegen à garder une
    entrée pour satisfaire `validator._check_api_domains`. C'était le cas de
    `tag`, gardé au motif faux que `TAG_*` serait un espace ouvert (c'est
    `BOXTAG_*` qui l'est)."""
    from scripting.api import ALL_DOMAINS, RUNTIME_API, RUNTIME_PROPS

    cites = {p.domain for f in RUNTIME_API.values() for p in f.params if p.domain}
    cites |= {p.domain for p in RUNTIME_PROPS.values() if p.domain}
    assert sorted(ALL_DOMAINS - cites) == []


def test_les_deux_consommateurs_couvrent_tous_les_domaines():
    """Pendant Python de `validator._check_api_domains`, qui ne tourne qu'au
    build d'un projet : un domaine inconnu du checker n'est pas vérifié, et
    inconnu du codegen il part en littéral C."""
    from scripting.api import ALL_DOMAINS
    from scripting import checker, codegen

    assert sorted(ALL_DOMAINS - checker.covered_domains()) == []
    assert sorted(ALL_DOMAINS - codegen.covered_domains()) == []
    assert sorted(checker.covered_domains() - ALL_DOMAINS) == []
    assert sorted(codegen.covered_domains() - ALL_DOMAINS) == []


# ── 8. Les helpers de « juiciness » ne composent que l'API existante ──
# squash/stretch/bounce/shake/flash/blink/pulse/pop/wobble : neuf `self:`
# stateless (t, duration, amount) qui n'écrivent que sprite_scale/
# sprite_offset/sprite_rotation/pal/visible — donc reproductibles à la main.

JUICE_METHODS = [
    "squash", "stretch", "bounce", "shake",
    "flash", "blink", "pulse", "pop", "wobble",
]


def test_les_neuf_helpers_de_juiciness_compilent():
    errs, code = _lua(
        "function on_update(self)\n"
        + "\n".join(f" self:{m}(3, 8, 10)" for m in JUICE_METHODS)
        + "\nend\n",
        affine_transform=True,
    )
    assert errs == []
    for m in JUICE_METHODS:
        assert f"actor_{m}(self, 3, 8, 10)" in code


def test_les_neuf_helpers_existent_en_c():
    """Même garde-fou que `test_le_getter_dauto_dir_existe_en_c` : le checker
    ne voit que le catalogue Python, jamais l'en-tête C — un `c_func` sans
    implémentation compilerait en `undefined reference` seulement au `make`."""
    from scripting.api import RUNTIME_API

    facade = (REPO_DIR / "runtime" / "include" / "actor_api_static.h").read_text(
        encoding="utf-8", errors="ignore")
    for m in JUICE_METHODS:
        fn = RUNTIME_API[f"self:{m}"].c_func
        assert re.search(r"\b" + re.escape(fn) + r"\s*\(", facade), (
            f"self:{m} : {fn}() n'existe pas dans actor_api_static.h")
