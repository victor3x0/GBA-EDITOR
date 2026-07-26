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
        edits.append((st, sp, f'text.draw("{text_key}", {a[0]}, {a[1]})'))

    out = text
    for start, stop, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[stop + 1:]
    return out, len(edits), skipped


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
