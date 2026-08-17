"""Le sous-ensemble Lua : ce qu'il refuse, et le fait qu'il le DISE.

Chacun de ces cas produisait auparavant l'un des deux silences que la v0.7.5
supprime :

  - un statement non géré rendait `None` — le bloc disparaissait du jeu, sans
    erreur de checker ni avertissement gcc ;
  - une expression non gérée rendait `ExprName("__unsupported_<Type>")`, ou un
    appel inconnu partait tel quel — donc un échec au `make`, sur la ligne
    générée et jamais sur sa cause.

C'est la définition d'un test ici (cf. `tests/` dans ARCHITECTURE) : une erreur
silencieuse, pas une exception.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parent.parent


def _errors(src: str, **ctx_kw) -> list[str]:
    """Les messages d'ERREUR d'un script, sans passer par le codegen."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    body = ctx_kw.pop("check_event_names", True)
    errs = check(parse(src), BuildContext(actor_name="Ball", **ctx_kw),
                 check_event_names=body)
    return [e.message for e in errs if e.level == "error"]


def _in_handler(body: str) -> str:
    return f"function on_update()\n{body}\nend\n"


# ── 1. Les constructions du langage qui disparaissaient ────────────
# Le corps de boucle n'arrivait pas jusqu'au C, et rien ne le disait : un jeu
# où la logique manque, sans une ligne de log pour le soupçonner.

@pytest.mark.parametrize("body, attendu", [
    ("for k, v in pairs(t) do n = n + v end", "for … in"),
    ("repeat n = n - 1 until n == 0",         "repeat … until"),
    ("goto fin\n::fin::",                     "goto"),
    ("do n = 1 end",                          "do … end"),
    ("local function f() return 1 end",       "fonction"),
    ("function f() return 1 end",             "fonction"),
])
def test_statement_refuse_avec_sa_ligne(body, attendu):
    errs = _errors(_in_handler(body))
    assert errs, f"« {body} » ne produit aucune erreur — il disparaît en silence"
    assert any(attendu in e for e in errs), errs
    assert any("ligne" in e for e in errs), \
        f"le refus de « {body} » ne situe pas la faute : {errs}"


# ── 2. Les expressions qui partaient en C invalide ─────────────────

@pytest.mark.parametrize("expr, attendu", [
    ('local s = "a" .. "b"',            ".."),
    ("local f = function() return 1 end", "fonction"),
    ("local p = 2 ^ 8",                 "^"),
    ("local q = 5 // 2",                "//"),
    ("local r = 1 << 3",                "binaires"),
    ("local r = 1 & 3",                 "binaires"),
    ("local r = ~1",                    "binaires"),
])
def test_expression_refusee(expr, attendu):
    errs = _errors(_in_handler(expr))
    assert any(attendu in e for e in errs), errs


def test_aucun_identifiant_unsupported_dans_le_c():
    """L'ancien marqueur ne doit plus exister nulle part : il n'était pas un
    diagnostic, c'était un identifiant C inexistant qui voyageait jusqu'à gcc."""
    from scripting.parser import parse
    from scripting.codegen import generate, CodegenContext

    script = parse(_in_handler('local s = "a" .. "b"'))
    code, _, _ = generate(script, CodegenContext(
        actor_name="Ball", actor_sym="Ball", anim_names=[], sfx_names=[],
        music_names=[], global_names=set(), const_names=set(),
        all_actor_syms=["Ball"]))
    assert "__unsupported" not in code
    assert "non traduit" in code       # le trou est écrit, pas caché


# ── 3. La bibliothèque standard de Lua ─────────────────────────────
# Elle n'existe pas, et le nom est pourtant JUSTE — d'où un message par nom
# plutôt qu'un « fonction inconnue » qui ferait chercher une faute de frappe.

@pytest.mark.parametrize("appel, attendu", [
    ("print(1)",              "console"),
    ("table.insert(t, 1)",    "taille fixe"),
    ("string.format(\"%d\")", "chaîne manipulable"),
    ("os.time()",             "horloge"),
    ("io.open(\"a\")",        "système de fichiers"),
    ("coroutine.create(f)",   "coroutine"),
    ("pairs(t)",              "index"),
    ("tostring(1)",           "marqueur de valeur"),
    ("pcall(f)",              "exception"),
    ("setmetatable(t, t)",    "métatable"),
    ("collectgarbage()",      "alloué"),
])
def test_bibliotheque_standard_refusee(appel, attendu):
    errs = _errors(_in_handler(f"    {appel}"))
    assert any(attendu in e for e in errs), errs


@pytest.mark.parametrize("appel, attendu", [
    ("math.floor(1)",   "entièrement entier"),
    ("math.random(1, 2)", "math.rand"),
    ("math.pow(2, 3)",  "multipliant"),
    ("math.fmod(5, 2)", "%"),
    # Sans entrée dédiée : le message LISTE ce que le module offre vraiment.
    ("math.tan(1)",     "abs, atan2, clamp"),
])
def test_math_est_un_faux_ami(appel, attendu):
    errs = _errors(_in_handler(f"    local x = {appel}"))
    assert any(attendu in e for e in errs), errs


# ── 4. Les appels inconnus, tolérés jusqu'ici ──────────────────────

def test_fonction_inconnue_refusee():
    errs = _errors(_in_handler("    aide(3)"))
    assert any("fonction inconnue" in e.lower() for e in errs), errs


def test_module_inconnu_refuse():
    errs = _errors(_in_handler("    machin.truc()"))
    assert any("machin" in e for e in errs), errs


def test_propriete_appelee_comme_une_fonction():
    """`self.position()` : la v0.7.4 a fait des états des propriétés, et le
    point suivi de parenthèses est l'erreur que cette migration provoque."""
    errs = _errors(_in_handler("    local p = self.position()"))
    assert any("PROPRIÉTÉ" in e for e in errs), errs


def test_methode_appelee_avec_un_point():
    errs = _errors(_in_handler('    self.play_anim("idle")'))
    assert any("DEUX POINTS" in e for e in errs), errs


def test_handler_inconnu_refuse():
    """Le C émis pour un nom inconnu est une fonction qu'aucun appel Lua ne peut
    atteindre — avertissement jusqu'ici, donc un build vert pour du code mort."""
    errs = _errors("function aide()\nend\n")
    assert any("behavior" in e for e in errs), errs


# ── 5. Ce qui doit continuer de passer ─────────────────────────────
# Le refus des appels inconnus ne doit pas emporter les deux espaces de noms
# légitimes hors catalogue : l'alias d'un behavior, et la table de module d'un
# behavior lui-même.

def test_alias_de_behavior_accepte():
    src = ('local IA = require("behaviors/ia")\n'
           'function on_update()\n    IA.update(self, 3)\nend\n')
    assert _errors(src) == []


def test_table_de_module_de_behavior_acceptee():
    """Le template de behavior qu'écrit l'éditeur lui-même (`local M = {}` …
    `return M`) récoltait « un tableau vide n'a pas de taille » : la forme de
    module était lue comme un tableau raté."""
    src = ("local M = {}\n\nfunction M.update(actor)\n    M.aide(actor)\nend\n\n"
           "function M.aide(actor)\nend\n\nreturn M\n")
    assert _errors(src, check_event_names=False) == []


def test_fonction_absente_du_module_refusee():
    src = ("local M = {}\n\nfunction M.update(actor)\n    M.aid(actor)\nend\n\n"
           "function M.aide(actor)\nend\n\nreturn M\n")
    errs = _errors(src, check_event_names=False)
    assert any("aide" in e for e in errs), errs


def test_les_scripts_de_la_demo_restent_valides():
    """Le filet le plus large : un projet réel, complet, qui doit rester vert.

    Ce filet juge le LANGAGE, pas l'authoring : le contexte de build réel est
    construit par owner dans `lua_compiler.transpile_all`, et le refaire ici en
    fouillant les JSON de la démo en ferait une seconde source qui dériverait au
    premier champ ajouté. Les garde-fous qui dépendent d'une case cochée dans
    l'éditeur sont donc ouverts — `Ball` a bien « Affine transform » coché
    (`project/prefab/Ball.json`), et c'est le build qui le vérifie. Le refus,
    lui, est scellé juste en dessous."""
    from scripting.parser import parse
    from scripting.checker import check, BuildContext

    racine = REPO_DIR / "Project Demo" / "Pong" / "assets" / "scripts"
    if not racine.exists():
        pytest.skip("projet de démo absent")
    for chemin in racine.rglob("*.lua"):
        errs = [e.message for e in check(
            parse(chemin.read_text(encoding="utf-8")),
            BuildContext(affine_transform=True),
            check_event_names=(chemin.parent.name != "behaviors"))
            if e.level == "error"]
        assert errs == [], f"{chemin.name} : {errs}"


def test_transform_affine_refuse_sans_la_case_cochee():
    """Le pendant du filet ci-dessus : sans « Affine transform », aucun slot de
    matrice n'est réservé au build, et self.rotation/scale n'ont nulle part où
    écrire. Le refus nomme la case à cocher, pas le matériel."""
    for prop in ("rotation", "scale", "sprite_rotation", "sprite_scale",
                 "sprite_offset"):
        errs = _errors(_in_handler(f"local v = self.{prop}"))
        assert any("Affine transform" in e for e in errs), (prop, errs)
        assert _errors(_in_handler(f"local v = self.{prop}"),
                       affine_transform=True) == []


# ── 6. Les deux listes qui ne doivent pas diverger ─────────────────

def test_tout_noeud_de_luaparser_est_classe():
    """Le contrôle de couverture, joué hors du validateur de projet : une mise à
    jour de luaparser qui ajoute un nœud doit se voir ici aussi, et pas
    seulement au moment d'ouvrir un projet."""
    import inspect
    from luaparser import astnodes
    from scripting import lua_subset

    abstraites = {"Expression", "Statement", "Op", "BinaryOp", "AriOp",
                  "BitOp", "RelOp", "LoOp", "UnaryOp", "Lhs"}
    univers = {name for name, cls in vars(astnodes).items()
               if inspect.isclass(cls) and issubclass(cls, astnodes.Expression)
               and name not in abstraites}
    assert univers - lua_subset.covered_nodes() == set()
    assert lua_subset.covered_nodes() - univers == set()


def test_chaque_refus_est_documente():
    """La documentation ne peut pas prendre de retard sur la table : un refus
    que `SCRIPTING.md` ne montre pas est un utilisateur bloqué par un message
    dont le document ne parle pas."""
    from scripting import lua_subset

    doc = (REPO_DIR / "SCRIPTING.md").read_text(encoding="utf-8")
    refus = [*lua_subset.REFUSED.values(), lua_subset.NESTED_FUNCTION,
             *lua_subset.STDLIB_MODULES.values(), *lua_subset.STDLIB.values()]
    absents = sorted({r.lua for r in refus if r.lua not in doc})
    assert absents == [], (
        f"Refus non documentés dans SCRIPTING.md : {absents}")
