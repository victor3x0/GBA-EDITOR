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
