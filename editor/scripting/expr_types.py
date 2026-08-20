"""editor/scripting/expr_types.py — de quel TYPE est une expression Lua.

Le sous-ensemble ne connaît que des scalaires (cf. ARCHITECTURE.md), à deux
exceptions près, et ce module répond pour les deux : les VALEURS COMPOSÉES
(`vec2`, `vec3`, `rect`) et les RÉFÉRENCES rendues par un appel (`sfx.play`).
Il s'appelait `vec_types.py` tant qu'il n'y en avait qu'une.

Une valeur composée se COPIE, une référence DÉSIGNE un slot pris dans un pool
du matériel : les deux ne se confondent pas, mais checker.py et codegen.py se
posent la même question sur les deux — « quel type porte ce nom ? » — et deux
modules auraient fini par y répondre différemment.

── Les valeurs composées ────────────────────────────────────────────────

`vec2(x, y)`, `vec3(x, y, z)` et `rect(x, y, w, h)` sont des CONSTRUCTEURS DE
LANGAGE, pas des entrées `RUNTIME_API` : ils ne traduisent pas un appel C, ils
déclarent une valeur composée (des entiers, jamais de virgule flottante — cf.
runtime/include/actor_types_static.h). checker.py (valider) et codegen.py
(émettre) ont chacun besoin de savoir si une expression EST un vec2/vec3/rect —
ce module est le seul endroit qui répond, pour que les deux ne divergent jamais
sur ce qu'est le type d'une expression.

Le module répond aussi à la deuxième famille de valeurs composées : les
PROPRIÉTÉS (`self.position`, `camera.bound`, `scene.size`…). Un accès pointé
`self.position` a bien un type, lu dans `RUNTIME_PROPS` (api.py) — c'est lui
qui fait que `local pos = self.position` donne une variable vec2, et que
`self.position.x` est un accès de champ valide.

Chaque consommateur garde sa propre table nom → type (`self._vec_types`),
remplie au fil de son propre parcours (une seule passe, de haut en bas —
même approximation, volontairement grossière, que `self._arrays` dans les
deux fichiers : un nom réutilisé avec deux types différents n'est pas
démêlé, il retombe sur `None`)."""

from __future__ import annotations
from typing import Optional

from .parser import ExprName, ExprIndex, ExprCall, ExprInvoke, ExprBinop
from .api import RUNTIME_API, RUNTIME_PROPS, REF_TYPES, ApiProp

# Champs valides par type — l'ordre est celui du constructeur.
VEC_FIELDS: dict[str, tuple[str, ...]] = {
    "vec2": ("x", "y"),
    "vec3": ("x", "y", "z"),
    "rect": ("x", "y", "w", "h"),
}

# Les types qui portent de l'ARITHMÉTIQUE (+ - *) : le C n'a pas d'opérateur
# sur les structs, et le checker/codegen traduisent ces opérateurs par les
# fonctions vec2_*/vec3_*. Un rect n'a rien à faire dans un calcul.
ARITH_TYPES: frozenset[str] = frozenset({"vec2", "vec3"})

# Constructeur → nombre d'arguments attendus. Dérivé de VEC_FIELDS : un seul
# endroit à tenir à jour pour ajouter un jour un autre type composé.
VEC_CONSTRUCTORS: dict[str, int] = {name: len(fields) for name, fields in VEC_FIELDS.items()}

# Constructeur → type C émis (littéral composé, pas un appel de fonction).
C_TYPES: dict[str, str] = {
    "vec2": "Vec2",
    "vec3": "Vec3",
    "rect": "Rect",
}


def _call_key(func_expr) -> Optional[str]:
    """Même règle que Checker._call_key / CodeGen._call_key : nom nu
    (`vec2`) ou `module.func` (`math.abs`). Ne rejoue pas la
    résolution complète (behaviors, cas spéciaux) — seul le nom compte ici,
    pour retrouver un `ret` dans RUNTIME_API ou un nom de constructeur."""
    if isinstance(func_expr, ExprName):
        return func_expr.name
    if isinstance(func_expr, ExprIndex) and isinstance(func_expr.obj, ExprName):
        return f"{func_expr.obj.name}.{func_expr.field}"
    return None


def resolve_prop(expr) -> Optional[tuple[str, ApiProp]]:
    """`self.position`, `camera.bound`, `scene.size`, ou une propriété d'ACTOR
    sur un récepteur quelconque (`other.velocity`, `paddle.position`) →
    `(récepteur, ApiProp)`. None si `expr` n'est pas un accès de propriété connu.

    Les propriétés d'actor vivent sous la clé `self.<champ>` dans
    RUNTIME_PROPS, mais s'accèdent sur n'importe quel `Actor*` nommé : un
    `other.velocity` est le même champ, avec un autre récepteur. Les propriétés
    de caméra/scène, elles, n'existent que sur `camera`/`scene`."""
    if not isinstance(expr, ExprIndex) or not isinstance(expr.obj, ExprName):
        return None
    receiver, field = expr.obj.name, expr.field
    prop = RUNTIME_PROPS.get(f"{receiver}.{field}")
    if prop is not None:
        return receiver, prop
    if receiver not in ("self", "camera", "scene"):
        prop = _ACTOR_PROP_FIELDS.get(field)
        if prop is not None:
            return receiver, prop
    return None


def _actor_prop_fields() -> dict[str, ApiProp]:
    """Champ (`position`, `velocity`, `rotation`, `scale`) → ApiProp, pour les
    propriétés d'actor consultées sur un récepteur autre que self."""
    out: dict[str, ApiProp] = {}
    for name, prop in RUNTIME_PROPS.items():
        if name.startswith("self."):
            out[name.rsplit(".", 1)[1]] = prop
    return out


_ACTOR_PROP_FIELDS = _actor_prop_fields()


def infer_vec_type(expr, local_types: dict[str, Optional[str]]) -> Optional[str]:
    """Rend "vec2" / "vec3" / "rect" si `expr` est de ce type, None sinon
    (scalaire, ou type que ce sous-ensemble ne suit pas — le défaut reste
    toujours scalaire, jamais composite par supposition)."""
    if expr is None:
        return None

    if isinstance(expr, ExprName):
        return local_types.get(expr.name)

    if isinstance(expr, ExprCall):
        key = _call_key(expr.func)
        if key in VEC_CONSTRUCTORS:
            return key
        api = RUNTIME_API.get(key) if key else None
        return api.ret if (api and api.ret in VEC_CONSTRUCTORS) else None

    if isinstance(expr, ExprInvoke):
        api = RUNTIME_API.get(f"self:{expr.method}")
        return api.ret if (api and api.ret in VEC_CONSTRUCTORS) else None

    if isinstance(expr, ExprBinop) and expr.op in ("+", "-", "*"):
        lt = infer_vec_type(expr.left, local_types)
        rt = infer_vec_type(expr.right, local_types)
        if lt and rt:
            return lt if (lt == rt and expr.op != "*") else None
        return lt or rt   # un seul côté composite (l'autre un scalaire, cf. * ) : ce type-là

    if isinstance(expr, ExprIndex):
        prop = resolve_prop(expr)
        if prop is not None:
            _, p = prop
            return p.ptype if (p.ptype in VEC_CONSTRUCTORS) else None

    return None


# ─── Les références ───────────────────────────────────────────────
# Ce qu'un appel REND et sur quoi s'écrivent des méthodes : un slot pris dans
# un pool dimensionné par le matériel. Le catalogue déclare le type (`ret`), ce
# module dit si une expression en porte un, et la table ci-dessous ce que le C
# écrit pour le tenir.

C_REF_TYPES: dict[str, str] = {
    "sfx": "mm_sfxhand",     # une référence d'effet — cf. headers.py
}


def infer_ref_type(expr) -> Optional[str]:
    """Le type de référence que rend `expr`, ou None.

    Un seul producteur possible : un appel du catalogue dont le `ret` est un
    type de référence. Une référence ne se calcule pas — on ne l'additionne
    pas, on n'en prend pas de champ —, donc il n'y a rien d'autre à parcourir,
    contrairement aux valeurs composées.
    """
    if not isinstance(expr, ExprCall):
        return None
    api = RUNTIME_API.get(_call_key(expr.func) or "")
    return api.ret if (api and api.ret in REF_TYPES) else None
