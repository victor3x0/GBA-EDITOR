"""
editor/core/models/field_value.py — valeur d'un champ numérique de composant
qui peut être, au choix :

  • un littéral en PIXELS      → stocké tel quel en `int`   (forme historique)
  • un littéral en TILES       → stocké `{"unit": "t", "n": <int>}`
  • une RÉFÉRENCE de variable   → stocké `{"var": "<nom>", "src": "global"|"const"}`

Rétro-compatibilité : un champ historique (`x: int = 0`) reste un `int` pur ;
il est simplement interprété comme un littéral pixel. Aucune migration de
projet n'est nécessaire — seule la sérialisation des formes tile/ref introduit
un dict.

Ce module ne dépend pas de Qt : il est partagé par l'UI (aperçu pixel),
le canvas (rendu) et le codegen (expression C). Les noms de symboles C
DOIVENT rester alignés sur scripting/globals.py (`g_<nom>`) et
scripting/constants.py (`CONST_<NOM en MAJUSCULES>`).
"""

from __future__ import annotations
from typing import Callable, Optional, Union

TILE_SIZE = 8   # px par tile (GBA)

Raw = Union[int, dict]                    # forme sérialisée telle qu'en JSON
Resolver = Callable[[str, str], Optional[int]]   # (src, name) -> valeur ou None


class FieldValue:
    """Wrapper léger autour de la forme sérialisée (`int` ou `dict`).

    On ne stocke JAMAIS une instance de FieldValue dans le modèle : le champ
    du composant garde sa forme sérialisable (`int`/`dict`). On enveloppe à la
    volée via `FieldValue.parse(raw)` puis on relit `to_raw()` pour ré-stocker.
    """

    __slots__ = ("mode", "n", "var_name", "var_src")

    def __init__(self, mode: str, n: int = 0, var_name: str = "", var_src: str = "global"):
        self.mode = mode            # "px" | "tile" | "ref"
        self.n = n                  # nombre (px ou tiles) pour px/tile
        self.var_name = var_name    # nom de la variable pour ref
        self.var_src = var_src      # "global" | "const"

    # ── Construction ──────────────────────────────────────────────
    @classmethod
    def parse(cls, raw: Raw) -> "FieldValue":
        if isinstance(raw, bool):           # bool est un int en Python — normaliser
            return cls("px", int(raw))
        if isinstance(raw, int):
            return cls("px", raw)
        if isinstance(raw, dict):
            if "var" in raw:
                src = raw.get("src", "global")
                return cls("ref", var_name=str(raw.get("var", "")),
                           var_src=src if src in ("global", "const") else "global")
            if raw.get("unit") == "t":
                try:
                    return cls("tile", int(raw.get("n", 0)))
                except (TypeError, ValueError):
                    return cls("tile", 0)
        return cls("px", 0)             # forme inconnue → repli neutre

    @classmethod
    def pixels(cls, n: int) -> "FieldValue":
        return cls("px", int(n))

    @classmethod
    def tiles(cls, n: int) -> "FieldValue":
        return cls("tile", int(n))

    @classmethod
    def ref(cls, name: str, src: str) -> "FieldValue":
        return cls("ref", var_name=name, var_src=src if src in ("global", "const") else "global")

    # ── Sérialisation ─────────────────────────────────────────────
    def to_raw(self) -> Raw:
        if self.mode == "tile":
            return {"unit": "t", "n": int(self.n)}
        if self.mode == "ref":
            return {"var": self.var_name, "src": self.var_src}
        return int(self.n)          # px → int nu (fichiers propres, rétro-compat)

    # ── Interrogation ─────────────────────────────────────────────
    @property
    def is_ref(self) -> bool:
        return self.mode == "ref"

    @property
    def is_tile(self) -> bool:
        return self.mode == "tile"

    # ── Aperçu pixel (UI / canvas) ────────────────────────────────
    def px(self, resolver: Optional[Resolver] = None, fallback: int = 0) -> int:
        """Valeur en pixels pour l'affichage.
        - px   : la valeur telle quelle
        - tile : n * TILE_SIZE
        - ref  : valeur fournie par `resolver(src, name)` (ex : défaut de la
                 variable) ; `fallback` si non résolue."""
        if self.mode == "tile":
            return int(self.n) * TILE_SIZE
        if self.mode == "ref":
            if resolver is not None:
                v = resolver(self.var_src, self.var_name)
                if v is not None:
                    return int(v)
            return fallback
        return int(self.n)

    # ── Expression C (codegen) ────────────────────────────────────
    def c_expr(self) -> str:
        """Rvalue C. px→littéral, tile→n*8, ref→symbole (g_<nom> / CONST_<NOM>)."""
        if self.mode == "tile":
            return str(int(self.n) * TILE_SIZE)
        if self.mode == "ref":
            if not self.var_name:
                return "0"
            if self.var_src == "const":
                return f"CONST_{self.var_name.upper()}"
            return f"g_{self.var_name}"
        return str(int(self.n))

    # ── Libellé court (puce UI) ───────────────────────────────────
    def label(self) -> str:
        if self.mode == "tile":
            return f"{self.n}t"
        if self.mode == "ref":
            return self.var_name or "?"
        return str(self.n)


# ── Helpers projet ─────────────────────────────────────────────────
# Les variables référençables d'un projet = ses globals + constantes. Ces
# trois fonctions évitent de recopier la même dérivation à chaque point
# d'usage (éditeurs de composant → liste ; canvas → résolveur). `project`
# est duck-typé (.globals / .constants) pour garder ce module sans import.

def variables_from_project(project) -> list[tuple[str, str]]:
    """Liste ordonnée `(src, name)` prête pour `ValueField(variables=…)`."""
    if not project:
        return []
    return ([("global", g.name) for g in project.globals]
            + [("const", c.name) for c in project.constants])


def var_defaults_from_project(project) -> dict:
    """Map `(src, name) -> valeur par défaut` (global.default / const.value),
    pour résoudre une référence à sa valeur représentative (aperçu canvas)."""
    if not project:
        return {}
    d: dict = {}
    for g in project.globals:
        d[("global", g.name)] = g.default
    for c in project.constants:
        d[("const", c.name)] = c.value
    return d


def make_resolver(project) -> Resolver:
    """Résolveur `(src, name) -> valeur|None` prêt pour `FieldValue.px(resolver)`."""
    defaults = var_defaults_from_project(project)
    return lambda src, name: defaults.get((src, name))
