"""Loader pour api_reference.json — la PRÉSENTATION de l'API (groupes, ordre,
descriptions rédigées, exemples choisis).

`api.py` reste la source de vérité de ce qui EXISTE ; ce fichier ne décide que
de la mise en rayon. Les deux ont divergé en silence : le JSON proposait encore
`display.print`, `display.clear` et `text.draw_box`, retirées de l'API, tout en
ignorant `scene.switch`, `text.draw_in` et douze autres. Un utilisateur cherchant
comment écrire du texte y trouvait donc trois fonctions mortes et pas la vivante.

D'où la réconciliation ci-dessous, faite à chaque chargement : le JSON est
FILTRÉ par le catalogue (une fonction retirée disparaît de l'écran) puis COMPLÉTÉ
par lui (une fonction ajoutée apparaît sans qu'on ait à toucher au JSON). Le
fichier peut donc rester incomplet ou en retard sans jamais mentir.
"""
from __future__ import annotations
import json
from pathlib import Path

from scripting.api import RUNTIME_API, REMOVED_API
from scripting import api_snippets

_JSON_PATH = Path(__file__).parent / "api_reference.json"
_cache: list[dict] | None = None

# Renseignés par la réconciliation, à fin de diagnostic. Vides en régime normal.
STALE: list[str] = []      # décrit par le JSON, inconnu du catalogue
RELABELED: list[str] = []  # libellé du JSON permuté par rapport au catalogue

# Catégorie d'accueil des méthodes d'actor ajoutées au catalogue sans avoir été
# rangées à la main. Les `self:*` sont répartis entre plusieurs catégories
# (Mouvement, Animation, Position…), donc leur module ne suffit pas à déduire
# laquelle : on ne devine pas, on les regroupe visiblement.
_ACTOR_FALLBACK = "Actor"
_MISC_FALLBACK  = "Autres"


def _module_of(name: str) -> str:
    """`text.draw_in` → `text` ; `self:move` → `self` ; `get_actor` → ``."""
    if name.startswith("self:"):
        return "self"
    return name.split(".")[0] if "." in name else ""


def _label_params(label: str) -> list[str]:
    """Noms de paramètres lus dans un libellé, guillemets retirés —
    `get_actor("name")` → `["name"]`."""
    inner = label[label.find("(") + 1:label.rfind(")")]
    return [a.strip().strip('"').strip() for a in inner.split(",")] if inner.strip() else []


def _fix_permuted(entry: dict, name: str) -> dict:
    """Regénère libellé et snippet quand le JSON décrit les MÊMES paramètres
    dans un AUTRE ORDRE que le catalogue.

    Restreint aux permutations, volontairement. Un réordonnancement rend le
    libellé faux — il enseignerait une signature que le compilateur rejette. Un
    simple renommage de paramètre (`n` devenu `frame`) reste juste sur le fond,
    et écraser à cette occasion un libellé rédigé à la main coûterait ses
    exemples choisis (`self:set_frame(0)` valant mieux que `self:set_frame(frame)`).

    Description et tableau de paramètres sont conservés : c'est la prose de ce
    fichier, elle n'est pas concernée par l'ordre."""
    f = RUNTIME_API.get(name)
    if f is None:
        return entry
    cat = [p.name for p in f.params] + (["..."] if f.variadic else [])
    lab = _label_params(entry.get("label", ""))
    if lab == cat or sorted(lab) != sorted(cat):
        return entry
    RELABELED.append(name)
    gen = api_snippets.entry_dict(name)
    return {**entry, "label": gen["label"], "snippet": gen["snippet"]}


def _reconcile(cats: list[dict]) -> list[dict]:
    STALE.clear()
    RELABELED.clear()
    out: list[dict] = []
    described: set[str] = set()
    # Où vit déjà chaque module — c'est ce qui range une fonction ajoutée sans
    # table de correspondance à maintenir. Un module présent dans plusieurs
    # catégories est ambigu : on ne tranche pas à sa place.
    homes: dict[str, set[str]] = {}

    for cat in cats:
        kept = []
        for entry in cat.get("entries", []):
            name = entry.get("label", "").split("(")[0].strip()
            if name in REMOVED_API or name not in RUNTIME_API:
                STALE.append(name)
                continue
            kept.append(_fix_permuted(entry, name))
            described.add(name)
            homes.setdefault(_module_of(name), set()).add(cat["name"])
        # Une catégorie vidée par le filtre ne doit pas laisser un en-tête creux.
        if kept:
            out.append({**cat, "entries": kept})

    by_name = {c["name"]: c for c in out}
    for name in RUNTIME_API:
        if name in described:
            continue
        candidates = homes.get(_module_of(name), set())
        target = (next(iter(candidates)) if len(candidates) == 1
                  else _ACTOR_FALLBACK if name.startswith("self:")
                  else _MISC_FALLBACK)
        cat = by_name.get(target)
        if cat is None:
            cat = {"name": target, "entries": []}
            by_name[target] = cat
            out.append(cat)
        cat["entries"].append(api_snippets.entry_dict(name))

    return out


def get_categories() -> list[dict]:
    """Catégories de la section API, réconciliées avec `RUNTIME_API` (en cache)."""
    global _cache
    if _cache is None:
        raw = json.loads(_JSON_PATH.read_text(encoding="utf-8")).get("categories", [])
        _cache = _reconcile(raw)
    return _cache


def make_tooltip(entry: dict) -> str:
    """Génère un tooltip HTML riche pour une entrée API."""
    sig   = entry.get("label", "")
    desc  = entry.get("description", "")
    params = entry.get("params", [])
    ret   = entry.get("returns", "")

    lines = [
        f"<b style='font-family:Consolas,monospace;color:#4ec9b0'>{sig}</b>",
        f"<p style='color:#aaaaaa;margin:4px 0'>{desc}</p>",
    ]

    if params:
        lines.append("<table cellspacing='2' style='margin-top:4px'>")
        for p in params:
            name = p.get("name", "")
            typ  = p.get("type", "")
            pdesc = p.get("description", "")
            lines.append(
                f"<tr>"
                f"<td style='font-family:Consolas,monospace;color:#c48b3c'>{name}</td>"
                f"<td style='color:#555;padding:0 6px'>{typ}</td>"
                f"<td style='color:#888'>{pdesc}</td>"
                f"</tr>"
            )
        lines.append("</table>")

    if ret:
        lines.append(
            f"<p style='color:#555;margin-top:4px;font-style:italic'>→ {ret}</p>"
        )

    lines.append(
        "<p style='color:#383838;margin-top:6px;font-size:9px'>? doc (bientôt disponible)</p>"
    )

    return "".join(lines)
