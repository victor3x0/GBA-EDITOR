"""
editor/scripting/refactor.py — références d'assets dans les scripts Lua.

Renommer une scène, un sfx, un prefab… dans l'éditeur doit mettre à jour les
scripts qui citent l'ancien nom. `Project.rename_*` répare déjà les références
côté DONNÉES (composants, layers de scène) ; ce module fait la même chose côté
SCRIPTS.

Le repérage est **structurel**, jamais textuel : on relit l'AST luaparser et on
ne retient que les arguments dont `RUNTIME_API` déclare le domaine (cf.
api.Param.domain). Conséquence directe : un commentaire qui mentionne "PONG",
ou un `local titre = "PONG"` sans rapport, ne sont pas touchés — seul
`scene.switch("PONG")` l'est. C'est la même table que celle qui pilote le
checker et le codegen : ajouter un domaine profite aux trois.

La réécriture remplace les littéraux par leur position exacte dans le texte
source (offsets luaparser), de droite à gauche — le reste du fichier, y compris
la mise en forme et les commentaires, est préservé octet pour octet.

Usage :
    refs = find_refs_in_project(project, DOMAIN_SCENE, "Arène")
    n    = rename_in_project(project, DOMAIN_SCENE, "Arène", "PONG")
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .api import RUNTIME_API, PARAM_STR

try:
    from luaparser import ast as _lua_ast, astnodes as _nodes
    _LUAPARSER_OK = True
except ImportError:                       # même repli que scripting/parser.py
    _LUAPARSER_OK = False


# ── Table domaine → sites d'appel ─────────────────────────────────
# Construite une fois depuis RUNTIME_API : {clé API: {index arg: domaine}}.
# Aucune liste de fonctions codée en dur ici — déclarer un `domain` sur un
# paramètre suffit à le rendre renommable.

def _reference_sites() -> dict[str, dict[int, str]]:
    sites: dict[str, dict[int, str]] = {}
    for key, fn in RUNTIME_API.items():
        for i, p in enumerate(fn.params):
            if p.ptype == PARAM_STR and p.domain:
                sites.setdefault(key, {})[i] = p.domain
    return sites


_SITES = _reference_sites()


@dataclass(frozen=True)
class LuaRef:
    """Un littéral de script qui référence un asset nommé."""
    path:    Path
    domain:  str
    value:   str
    line:    int
    start:   int   # offset du littéral dans le texte source, guillemets INCLUS
    stop:    int   # offset du dernier caractère (inclusif, convention luaparser)
    api_key: str   # "scene.switch", "sfx.play"… — pour l'affichage


# ── Repérage ──────────────────────────────────────────────────────

def _call_key(node) -> Optional[str]:
    """Clé RUNTIME_API d'un noeud d'appel luaparser, ou None.

    Reproduit la résolution du checker (`Checker._call_key`) sur l'AST brut :
    `Name` → "get_actor", `Index(Name, field)` → "sfx.play", `Invoke` →
    "self:play_anim"."""
    if isinstance(node, _nodes.Invoke):
        method = getattr(node.func, "id", None)
        return f"self:{method}" if method else None
    if isinstance(node, _nodes.Call):
        func = node.func
        if isinstance(func, _nodes.Name):
            return func.id
        if isinstance(func, _nodes.Index) and isinstance(func.value, _nodes.Name):
            field = getattr(func.idx, "id", None)
            return f"{func.value.id}.{field}" if field else None
    return None


def iter_refs(text: str, path: Path | None = None,
              domain: str | None = None,
              value: str | None = None) -> Iterator[LuaRef]:
    """Parcourt les références d'un script. `domain`/`value` filtrent ;
    sans filtre, retourne toute la surface de référence du fichier (c'est
    la base d'un futur graphe de dépendances)."""
    if not _LUAPARSER_OK:
        return
    try:
        tree = _lua_ast.parse(text)
    except Exception:
        return   # script non parsable : aucune réécriture (cf. rename_in_text)

    for node in _lua_ast.walk(tree):
        if not isinstance(node, (_nodes.Call, _nodes.Invoke)):
            continue
        key = _call_key(node)
        arg_domains = _SITES.get(key or "")
        if not arg_domains:
            continue
        for i, arg in enumerate(node.args or []):
            dom = arg_domains.get(i)
            if dom is None or not isinstance(arg, _nodes.String):
                continue
            if domain is not None and dom != domain:
                continue
            if value is not None and arg.raw != value:
                continue
            # Ligne recalculée depuis l'offset : `String.line` de luaparser
            # lève dès que le noeud n'a pas conservé ses tokens.
            yield LuaRef(
                path=path or Path(""), domain=dom, value=arg.raw,
                line=text.count("\n", 0, arg.start_char) + 1,
                start=arg.start_char, stop=arg.stop_char,
                api_key=key or "",
            )


# ── Réécriture ────────────────────────────────────────────────────

def rename_in_text(text: str, domain: str, old: str, new: str) -> tuple[str, int]:
    """(texte réécrit, nombre de remplacements). Texte inchangé si le script
    ne parse pas — mieux vaut une référence non mise à jour, signalée par le
    checker au build, qu'un fichier corrompu par une substitution à l'aveugle."""
    refs = sorted(iter_refs(text, domain=domain, value=old),
                  key=lambda r: r.start, reverse=True)
    if not refs:
        return text, 0
    out = text
    for r in refs:
        # On ne réécrit que le CONTENU : les guillemets d'origine (" ou ')
        # et l'échappement restent ceux de l'auteur.
        literal = out[r.start:r.stop + 1]
        quote   = literal[0]
        out = out[:r.start] + f"{quote}{new}{quote}" + out[r.stop + 1:]
    return out, len(refs)


# ── Portée projet ─────────────────────────────────────────────────

def script_paths(project) -> list[Path]:
    """Tous les .lua du projet (actors, scènes, behaviors)."""
    dirs = [getattr(project, attr, None) for attr in
            ("scripts_actors_dir", "scripts_scenes_dir", "scripts_behaviors_dir")]
    out: list[Path] = []
    for d in dirs:
        if d and Path(d).exists():
            out += sorted(Path(d).rglob("*.lua"))
    return out


def find_refs_in_project(project, domain: str, name: str) -> dict[Path, list[LuaRef]]:
    """{script: références} — pour une vue « utilisations » ou un aperçu de
    renommage. N'écrit rien."""
    found: dict[Path, list[LuaRef]] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        refs = list(iter_refs(text, path=p, domain=domain, value=name))
        if refs:
            found[p] = refs
    return found


def index_refs_in_project(project, domain: str) -> dict[str, dict[Path, int]]:
    """{valeur référencée: {script: nombre d'occurrences}} pour tout un domaine.

    Un SEUL parcours des scripts couvre toutes les valeurs du domaine, là où
    `find_refs_in_project` reparse tout pour un seul nom. C'est ce qu'il faut à
    une vue « utilisé par » posée sur une table entière : l'utilisateur passe
    d'une entrée à l'autre sans relancer luaparser à chaque sélection."""
    index: dict[str, dict[Path, int]] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for ref in iter_refs(text, path=p, domain=domain):
            index.setdefault(ref.value, {}).setdefault(p, 0)
            index[ref.value][p] += 1
    return index


# ── Migration display.* → text.* ──────────────────────────────────
# `display.print` / `display.clear` (libtonc TTE) ont été retirés. Leur chaîne
# de format vivait dans le script, donc hors de la table de textes :
# intraduisible (cf. api.REMOVED_API).
#
# Ce qui se migre TOUT SEUL : un littéral sans marqueur de format. Le texte
# part dans la table, l'appel devient `text.draw("clé", col, row)`. Ce qui ne
# se migre pas : dès qu'il y a un `%` ou des arguments variadiques, il faut
# décider ce qui devient un libellé traduisible et ce qui devient un
# `text.draw_num` — une décision d'auteur, que le checker signale plutôt que
# de la prendre à sa place.

def _print_calls(text: str):
    """[(node, key)] des appels display.* d'un script, dans l'ordre du source."""
    if not _LUAPARSER_OK:
        return []
    try:
        tree = _lua_ast.parse(text)
    except Exception:
        return []
    out = []
    for node in _lua_ast.walk(tree):
        if not isinstance(node, _nodes.Call):
            continue
        key = _call_key(node)
        if key in ("display.print", "display.clear"):
            out.append((node, key))
    out.sort(key=lambda t: t[0].start_char)
    return out


def _string_value(node) -> str:
    """Contenu d'un noeud String, sans guillemets. Selon la version de
    luaparser, `.s` sort en bytes et `.raw` en str — on prend ce qui vient."""
    for attr in ("raw", "s"):
        v = getattr(node, attr, None)
        if isinstance(v, str):
            return v
        if isinstance(v, (bytes, bytearray)):
            return v.decode("utf-8", "replace")
    return ""


def _src(text: str, node) -> str:
    """Texte source exact d'un noeud — préserve les expressions d'argument
    telles que l'auteur les a écrites (`col + 2`, `const.get("X")`…)."""
    return text[node.start_char:node.stop_char + 1]


def _call_span(text: str, node) -> tuple[int, int]:
    """Bornes source d'un appel, préfixe d'objet INCLUS.

    Sur `display.print(…)`, luaparser fait commencer le Call ET son Index AU
    POINT (mesuré : start_char == 7 pour « display.print(…) »), et le noeud
    `Name('display')` ne porte aucun offset. Remplacer cette étendue laisserait
    donc un « display » orphelin collé au remplacement.

    On remonte depuis le point : espaces éventuels (`display . print` est du Lua
    valide), puis les caractères d'identifiant. Le point de départ vient de
    l'AST, l'extension est mécanique — aucune recherche textuelle à l'aveugle."""
    start, stop = node.start_char, node.stop_char
    if start < len(text) and text[start] == ".":
        i = start
        while i > 0 and text[i - 1] in " \t":
            i -= 1
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            i -= 1
        start = i
    return start, stop


def _skipped_src(text: str, node) -> str:
    """Appel non migré, tel qu'il apparaît dans le source — c'est ce qu'on
    montre à l'utilisateur, il doit donc inclure le préfixe d'objet."""
    st, sp = _call_span(text, node)
    return text[st:sp + 1]


def migrate_display_in_text(text: str, new_text_fn) -> tuple[str, int, list[str]]:
    """(source réécrit, nombre de migrations, appels laissés en place).

    `new_text_fn(content) -> clé` crée l'entrée de table et rend sa clé ;
    l'appelant décide du rangement. Réécriture de DROITE À GAUCHE par offsets,
    donc la mise en forme et les commentaires du reste du fichier sont
    préservés octet pour octet (même règle que rename_in_text)."""
    calls = _print_calls(text)
    if not calls:
        return text, 0, []

    edits: list[tuple[int, int, str]] = []
    skipped: list[str] = []
    for node, key in calls:
        args = node.args or []
        if key == "display.clear":
            # display.clear(col, row, len) -> text.clear(col, row, len, 1)
            # Équivalence exacte : `len` était une longueur de ligne en tuiles,
            # text.clear prend une largeur ET une hauteur.
            if len(args) != 3:
                skipped.append(_skipped_src(text, node))
                continue
            a = [_src(text, x) for x in args]
            st, sp = _call_span(text, node)
            edits.append((st, sp, f"text.clear({a[0]}, {a[1]}, {a[2]}, 1)"))
            continue
        # display.print(col, row, "littéral")
        if len(args) != 3 or not isinstance(args[2], _nodes.String):
            skipped.append(_skipped_src(text, node))
            continue
        content = _string_value(args[2])
        if "%" in content:
            skipped.append(_skipped_src(text, node))
            continue
        text_key = new_text_fn(content)
        a = [_src(text, x) for x in args]
        st, sp = _call_span(text, node)
        # Grammaire position → contenu (cf. api.py, section Texte).
        edits.append((st, sp, f'text.draw({a[0]}, {a[1]}, "{text_key}")'))

    out = text
    for start, stop, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[stop + 1:]
    return out, len(edits), skipped


# ── Réordonnancement des arguments de text.* (2026-07-27) ─────────
# La famille est passée à « position/conteneur → contenu ». Le piège : l'ancien
# ordre reste du Lua VALIDE — mêmes noms, mêmes arités — donc ni le checker ni
# le compilateur C ne le voient. `text.draw("clé", 2, 16)` résoudrait « clé »
# comme une coordonnée et 16 comme une clé de texte : un projet non migré
# rendrait n'importe quoi, en silence.
#
# La détection ne peut donc pas se faire sur la signature, seulement sur la
# FORME des arguments — et pour draw_in, sur le NAMESPACE auquel appartient
# chaque chaîne (l'une nomme une zone, l'autre une clé de texte). Ce qui reste
# indécidable est SIGNALÉ, jamais deviné.
#
# Corollaire gratuit : la migration est idempotente. Après passage, `draw_in` a
# sa zone en premier, donc elle se reconnaît comme déjà migrée. Pas de marqueur
# de version à poser — un marqueur peut mentir, une forme non.


def _is_str(node) -> bool:
    return _LUAPARSER_OK and isinstance(node, _nodes.String)


def _is_num(node) -> bool:
    return _LUAPARSER_OK and isinstance(node, _nodes.Number)


def _text_calls(text: str, keys: set[str]):
    """[(node, clé API)] des appels aux fonctions à réordonner."""
    if not _LUAPARSER_OK:
        return []
    try:
        tree = _lua_ast.parse(text)
    except Exception:
        return []
    out = [(n, _call_key(n)) for n in _lua_ast.walk(tree)
           if isinstance(n, _nodes.Call) and _call_key(n) in keys]
    out.sort(key=lambda t: t[0].start_char)
    return out


def _needs_reorder(key: str, args: list, is_region, is_text_key) -> Optional[bool]:
    """True = ancien ordre (à permuter), False = déjà migré, None = indécidable.

    `is_region` / `is_text_key` disent à quel namespace appartient une chaîne :
    c'est la seule information qui départage `draw_in("a", "b")`, dont les deux
    arguments sont des chaînes dans les deux ordres."""
    if key in ("text.draw", "text.draw_upto"):
        # ancien (id, tx, ty[, n]) ; nouveau (tx, ty, id[, n])
        if _is_str(args[0]) and not _is_str(args[2]):
            return True
        if _is_str(args[2]) and not _is_str(args[0]):
            return False
        return None
    if key in ("text.draw_in", "text.draw_in_upto"):
        # ancien (id, region[, n]) ; nouveau (region, id[, n]) — deux chaînes
        # dans les deux cas, donc on interroge les namespaces.
        if not (_is_str(args[0]) and _is_str(args[1])):
            return None
        a, b = _string_value(args[0]), _string_value(args[1])
        old = is_text_key(a) and is_region(b)
        new = is_region(a) and is_text_key(b)
        if old and not new:
            return True
        if new and not old:
            return False
        return None            # un nom qui vit dans les deux namespaces
    if key == "text.draw_num_in":
        # ancien (value, region) ; nouveau (region, value)
        if _is_str(args[1]) and not _is_str(args[0]):
            return True
        if _is_str(args[0]) and not _is_str(args[1]):
            return False
        return None
    if key == "text.draw_num":
        # ancien (value, tx, ty) ; nouveau (tx, ty, value). Trois entiers : on
        # ne tranche que si UN SEUL des bouts n'est pas un littéral numérique
        # (`global.get("score")`, une variable…). Trois littéraux sont
        # indécidables, et deviner y serait irréparable.
        if not _is_num(args[0]) and _is_num(args[1]) and _is_num(args[2]):
            return True
        if _is_num(args[0]) and _is_num(args[1]) and not _is_num(args[2]):
            return False
        return None
    return None


def migrate_text_arg_order_in_text(text: str, is_region, is_text_key
                                   ) -> tuple[str, int, list[str]]:
    """(source réécrit, nombre de permutations, appels laissés en place).

    Réécriture de DROITE À GAUCHE par offsets : la mise en forme et les
    commentaires du reste du fichier sont préservés octet pour octet (même
    règle que `rename_in_text` et `migrate_display_in_text`)."""
    from .api import TEXT_ARG_REORDER_2026_07 as PERM

    calls = _text_calls(text, set(PERM))
    if not calls:
        return text, 0, []

    edits: list[tuple[int, int, str]] = []
    skipped: list[str] = []
    for node, key in calls:
        args = node.args or []
        perm = PERM[key]
        if len(args) != len(perm):
            skipped.append(_skipped_src(text, node))
            continue
        verdict = _needs_reorder(key, args, is_region, is_text_key)
        if verdict is None:
            skipped.append(_skipped_src(text, node))
            continue
        if verdict is False:
            continue                       # déjà dans le nouvel ordre
        src = [_src(text, a) for a in args]
        st, sp = _call_span(text, node)
        edits.append((st, sp, f"{key}({', '.join(src[i] for i in perm)})"))

    out = text
    for start, stop, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[stop + 1:]
    return out, len(edits), skipped


def migrate_text_arg_order_in_project(project) -> dict:
    """Migre tous les scripts du projet. Retourne
    {"migrated": {script: n}, "skipped": {script: [appels]}}."""
    regions = set(project.region_names())
    keys = {t.key for t in getattr(project, "texts", [])}
    migrated: dict[Path, int] = {}
    skipped: dict[Path, list[str]] = {}
    for p in script_paths(project):
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "text." not in src:             # filtre bon marché avant de parser
            continue
        out, n, left = migrate_text_arg_order_in_text(
            src, regions.__contains__, keys.__contains__)
        if n:
            p.write_text(out, encoding="utf-8")
            migrated[p] = n
        if left:
            skipped[p] = left
    return {"migrated": migrated, "skipped": skipped}


def migrate_display_in_project(project) -> dict:
    """Migre tous les scripts du projet. Retourne
    {"migrated": {script: n}, "skipped": {script: [appels]}}.

    Les entrées de table sont rangées sous le nom du script d'origine : c'est le
    contexte de création, donc ce que la clé doit situer (cf. models/text.py,
    « la clé situe, elle ne résume pas »)."""
    migrated: dict[Path, int] = {}
    skipped: dict[Path, list[str]] = {}
    for p in script_paths(project):
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "display." not in src:          # filtre bon marché avant de parser
            continue

        def _new(content: str, _stem=p.stem) -> str:
            return project.new_text(content=content, path=[_stem]).key

        out, n, left = migrate_display_in_text(src, _new)
        if n:
            p.write_text(out, encoding="utf-8")
            migrated[p] = n
        if left:
            skipped[p] = left
    return {"migrated": migrated, "skipped": skipped}


def rename_in_project(project, domain: str, old: str, new: str) -> dict[Path, int]:
    """Réécrit toutes les références `old` → `new` du domaine donné dans les
    scripts du projet. Retourne {script: nombre de remplacements} (vide si
    rien n'a bougé). Sans effet si old == new."""
    if not old or not new or old == new:
        return {}
    changed: dict[Path, int] = {}
    for p in script_paths(project):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, n = rename_in_text(text, domain, old, new)
        if n:
            p.write_text(new_text, encoding="utf-8")
            changed[p] = n
    return changed


# ── Retrait de draw_upto / draw_num / draw_num_in (2026-07-31) ────
# Le tempo et l'interpolation vivaient dans le SCRIPT ; ils vivent désormais
# dans le TEXTE (`[speed=4]`, `$score`). Retour à l'auteur du texte, là où ça se
# relit et se traduit.
#
# Contrairement au réordonnancement d'arguments, l'absence de migration se VOIT
# ici : les fonctions n'existent plus, le checker les signale et le C ne
# compilerait pas. On peut donc se permettre de ne migrer que le mécanique et de
# laisser le reste à l'auteur — c'est la règle déjà suivie pour `display.print`.

_REMOVED_TEXT_CALLS = ("text.draw_upto", "text.draw_in_upto",
                       "text.draw_num", "text.draw_num_in")


def _removed_text_calls(text: str):
    """[(node, key)] des appels aux primitives retirées, dans l'ordre source."""
    if not _LUAPARSER_OK:
        return []
    try:
        tree = _lua_ast.parse(text)
    except Exception:
        return []
    out = [(n, _call_key(n)) for n in _lua_ast.walk(tree)
           if isinstance(n, _nodes.Call) and _call_key(n) in _REMOVED_TEXT_CALLS]
    out.sort(key=lambda t: t[0].start_char)
    return out


def _var_ref(node) -> Optional[str]:
    """`global.get("x")` ou `const.get("x")` → "x". None sinon.

    C'est la SEULE forme qu'une valeur interpolée sait exprimer : `$nom` désigne
    un global ou une constante, pas une expression. Un calcul reste donc à
    reprendre à la main — le porte-fenêtre était déjà celui de la décision
    « pas de valeur calculée » (cf. ROADMAP v0.3.2)."""
    if not isinstance(node, _nodes.Call):
        return None
    if _call_key(node) not in ("global.get", "const.get"):
        return None
    args = node.args or []
    if len(args) != 1 or not isinstance(args[0], _nodes.String):
        return None
    return _string_value(args[0]) or None


def _frame_divisor(text: str, node) -> Optional[int]:
    """`scene.frame() / K` → K (entier littéral). None sinon.

    C'est l'idiome que la documentation de `draw_in_upto` enseignait elle-même,
    et K y est exactement le nombre de frames par caractère — donc `[speed=K]`.
    Toute autre expression est laissée à l'auteur : deviner un tempo à partir
    d'un calcul inconnu produirait un texte qui défile faux."""
    # Le nom du noeud de division varie selon la version de luaparser : on
    # interroge donc le type par son nom plutôt que par une classe importée,
    # qui n'existe pas partout.
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)
    if left is None or right is None:
        return None
    if type(node).__name__ not in ("FloatDivOp", "FloorDivOp", "DivOp"):
        return None
    if not (isinstance(left, _nodes.Call) and _call_key(left) == "scene.frame"):
        return None
    if not isinstance(right, _nodes.Number):
        return None
    k = right.n
    return int(k) if float(k) == int(k) and int(k) > 0 else None


def migrate_removed_text_in_text(text: str, new_value_text_fn,
                                 set_speed_fn) -> tuple[str, int, list[str]]:
    """(source réécrit, migrations, appels laissés en place).

    `new_value_text_fn(var_name) -> clé` crée une entrée de contenu `$var` ;
    `set_speed_fn(text_key, k) -> bool` pose `[speed=k]` en tête d'une entrée
    existante et dit si elle a pu. Réécriture de DROITE À GAUCHE par offsets :
    le reste du fichier est préservé octet pour octet."""
    calls = _removed_text_calls(text)
    if not calls:
        return text, 0, []

    edits: list[tuple[int, int, str]] = []
    skipped: list[str] = []
    for node, key in calls:
        args = node.args or []
        a = [_src(text, x) for x in args]
        st, sp = _call_span(text, node)

        if key in ("text.draw_num", "text.draw_num_in"):
            # La valeur devient le contenu de l'entrée : "$mon_global".
            n_pos = 2 if key == "text.draw_num" else 1
            if len(args) != n_pos + 1:
                skipped.append(_skipped_src(text, node))
                continue
            var = _var_ref(args[n_pos])
            if not var:
                skipped.append(_skipped_src(text, node))
                continue
            k = new_value_text_fn(var)
            if key == "text.draw_num":
                edits.append((st, sp, f'text.draw({a[0]}, {a[1]}, "{k}")'))
            else:
                edits.append((st, sp, f'text.draw_in({a[0]}, "{k}")'))
            continue

        if key == "text.draw_in_upto":
            # Le tempo passe DANS le texte ; l'appel devient un draw_in, qui est
            # idempotent tant que la lecture court (cf. gba_engine.h).
            if len(args) != 3 or not isinstance(args[1], _nodes.String):
                skipped.append(_skipped_src(text, node))
                continue
            k = _frame_divisor(text, args[2])
            if k is None or not set_speed_fn(_string_value(args[1]), k):
                skipped.append(_skipped_src(text, node))
                continue
            edits.append((st, sp, f'text.draw_in({a[0]}, {a[1]})'))
            continue

        # text.draw_upto : sans zone, pas de tête de lecture. Aucun équivalent
        # mécanique — c'est précisément la décision « dessine une zone ».
        skipped.append(_skipped_src(text, node))

    out = text
    for start, stop, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[stop + 1:]
    return out, len(edits), skipped


def migrate_removed_text_in_project(project) -> dict:
    """Migre tous les scripts. {"migrated": {script: n}, "skipped": {script: [...]}}"""
    from core.text_markup import parse

    migrated: dict[Path, int] = {}
    skipped: dict[Path, list[str]] = {}
    by_var: dict[str, str] = {}          # un global cité deux fois = une entrée

    def _new_value(var: str, _stem="") -> str:
        if var not in by_var:
            by_var[var] = project.new_text(content=f"${var}",
                                           path=[_stem] if _stem else []).key
        return by_var[var]

    def _set_speed(text_key: str, k: int) -> bool:
        """Pose `[speed=k]` en tête. Refuse si l'entrée porte déjà du tempo :
        deux appels de rythmes différents sur la même entrée n'ont pas de
        réponse, et en inventer une changerait un texte sans le dire."""
        t = next((x for x in project.texts if x.key == text_key), None)
        if t is None:
            return False
        if parse(t.content).of_kind("speed", "pause"):
            return False
        t.content = f"[speed={k}]" + t.content
        return True

    for p in script_paths(project):
        try:
            src = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if not any(n.split(".")[-1] in src for n in _REMOVED_TEXT_CALLS):
            continue        # filtre bon marché avant de parser

        def _new(var: str, _stem=p.stem) -> str:
            return _new_value(var, _stem)

        out, n, left = migrate_removed_text_in_text(src, _new, _set_speed)
        if n:
            p.write_text(out, encoding="utf-8")
            migrated[p] = n
        if left:
            skipped[p] = left
    return {"migrated": migrated, "skipped": skipped}
