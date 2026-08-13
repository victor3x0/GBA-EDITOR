"""scripting/api_snippets.py — fabrique le Lua que l'éditeur INSÈRE, depuis `RUNTIME_API`.

Point unique de fabrication des snippets. Tant qu'ils étaient écrits en dur dans
la sidebar, ils pourrissaient à chaque changement de signature sans que rien ne
le signale : la sidebar proposait encore `scene_goto("X")` et
`instantiate("X", x, y)`, deux noms qui n'ont **jamais** existé dans le
catalogue — donc, au clic, du code que le checker refuse. Et l'utilisateur, lui,
conclut que l'API est cassée, pas que le bouton est périmé.

Dériver du catalogue rend cette dérive impossible : une signature qui change
change le snippet, une fonction qui disparaît fait disparaître son bouton.
C'est aussi ce qui fait que le réordonnancement d'arguments à venir
(`text.draw(x, y, contenu)`) n'aura à toucher que `api.py`.

Deux entrées distinctes, parce que les deux usages ne veulent pas la même chose :

  `example()` — section API : montre la fonction, donc préfère l'exemple écrit
                à la main dans le `doc` (« Ex: … »), qui vaut mieux qu'un
                gabarit générique.
  `call()`    — section RÉFÉRENCES : l'utilisateur a cliqué sur UN asset précis,
                donc le nom vient de lui et l'exemple du `doc` serait un
                contresens (il citerait un autre asset).
"""
from __future__ import annotations

from scripting.api import (
    RUNTIME_API, PARAM_STR, PARAM_STR_LITERAL, PARAM_ACTOR, ApiFunc,
    HARDWARE_ENUMS,
)

# Marqueur d'exemple dans les `doc` d'api.py. Convention déjà en place là-bas ;
# la nommer ici évite qu'un troisième lecteur la redevine.
_EX = "Ex:"


def _fn(name: str) -> ApiFunc | None:
    return RUNTIME_API.get(name)


def _lua_str(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def signature(name: str) -> str:
    """`text.draw_in(id, region)` — la forme, pour un libellé de bouton."""
    f = _fn(name)
    if f is None:
        return name
    parts = [p.name for p in f.params]
    if f.variadic:
        parts.append("...")
    return f"{name}({', '.join(parts)})"


def call(name: str, **by_domain: str) -> str:
    """Appel Lua prêt à insérer, les arguments NOMMÉS remplis par domaine.

    Les clés de `by_domain` sont des `DOMAIN_*` : c'est le domaine, et non la
    position, qui dit où va le nom d'un asset — donc réordonner les paramètres
    dans `api.py` n'invalide aucun appelant. Un paramètre non fourni devient un
    gabarit : son propre nom, entre guillemets s'il attend une chaîne, pour que
    le snippet reste du Lua valide et visiblement à compléter."""
    f = _fn(name)
    if f is None:
        return name
    args: list[str] = []
    for p in f.params:
        if p.domain and p.domain in by_domain:
            args.append(_lua_str(by_domain[p.domain]))
        elif p.domain in HARDWARE_ENUMS:
            # Énumération matérielle : l'ensemble est FIXE et connu ici, donc on
            # propose une vraie valeur plutôt qu'un gabarit. Un gabarit
            # (`blend.set_mode("mode")`) serait refusé par le checker à la
            # seconde même où l'utilisateur vient de cliquer pour l'insérer.
            args.append(_lua_str(next(iter(HARDWARE_ENUMS[p.domain]))))
        elif p.ptype in (PARAM_STR, PARAM_STR_LITERAL):
            args.append(_lua_str(p.name))
        elif p.ptype == PARAM_ACTOR:
            args.append(p.name)
        else:
            args.append(p.name)
    if f.variadic:
        args.append("...")
    return f"{name}({', '.join(args)})"


def description(name: str) -> str:
    """Le `doc` sans sa queue d'exemple — celle-ci se montre à part."""
    f = _fn(name)
    if f is None:
        return ""
    return (f.doc or "").split(_EX)[0].strip()


def example(name: str) -> str:
    """Exemple écrit à la main s'il existe, sinon le gabarit de `call()`."""
    f = _fn(name)
    if f is None:
        return name
    doc = f.doc or ""
    if _EX in doc:
        ex = doc.split(_EX, 1)[1].strip()
        if ex:
            return ex
    return call(name)


def entry_dict(name: str) -> dict:
    """Entrée au format d'`api_reference.json`, pour une fonction que le JSON
    ne décrit pas. Même forme exactement : c'est ce qui permet à `make_tooltip`
    de ne pas savoir d'où vient l'entrée qu'il affiche."""
    f = _fn(name)
    ret = "" if f is None or f.ret == "void" else f.ret
    return {
        "label":       signature(name),
        "snippet":     example(name),
        "description": description(name),
        "params": [
            {"name": p.name,
             "type": "string" if p.ptype in (PARAM_STR, PARAM_STR_LITERAL) else "number",
             "description": ""}
            for p in (f.params if f else [])
        ],
        "returns":     ret,
        "doc_anchor":  name.replace(":", "-").replace(".", "-"),
    }
