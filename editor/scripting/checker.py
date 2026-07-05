"""
editor/scripting/checker.py — Vérification sémantique d'un LuaScript.

Reçoit le LuaScript produit par parser.py et une description du contexte
de build (nom de l'actor, sprites disponibles, sfx disponibles…).
Retourne une liste de CheckError ; si vide, le script peut être compilé.

Vérifications en v1 :
  - Toutes les fonctions top-level sont des handlers connus (KNOWN_EVENTS)
  - Les appels self:method correspondent à l'API (RUNTIME_API)
  - Les appels module.func correspondent à l'API
  - Les noms d'animation passés à play_anim existent dans le SpriteAsset
  - Les noms de sfx existent dans le projet
  - Les noms de music existent dans le projet
  - Les boutons passés à input.held / input.pressed sont valides
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .parser import (
    LuaScript, LuaFunction,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile, StmtForNum,
    ExprInvoke, ExprCall, ExprIndex, ExprName, ExprString,
    ExprNumber, ExprUnop, ExprBool,
)
from .api import RUNTIME_API, KNOWN_EVENTS, DOMAIN_ANIM, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_SCENE


# ─── Résultat ─────────────────────────────────────────────────────

@dataclass
class CheckError:
    level:   str   # "error" | "warning"
    message: str


@dataclass
class BuildContext:
    """
    Informations fournies par build.py pour la validation contextuelle.
    Tous les champs sont optionnels ; si absent, la vérification est relâchée.
    """
    actor_name:   str        = ""
    anim_names:   list[str]  = None    # noms d'anim définis dans le SpriteAsset lié
    sfx_names:    list[str]  = None    # noms de Sfx dans le projet
    music_names:  list[str]  = None    # noms de Music dans le projet
    scene_names:  list[str]  = None    # noms de scènes du projet
    actor_names:  list[str]  = None    # noms des actors de la scène (pour get_actor)
    global_names: list[str]  = None    # noms de GlobalVar déclarées dans le projet
    global_types: dict[str, str] = None  # nom -> type ("int"/"bool"/"u8"/"u16"/"s8"/"s16")
    const_names:  list[str]  = None    # noms de Constant déclarées dans le projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)

    VALID_KEYS = {"a", "b", "l", "r", "start", "select", "up", "down", "left", "right"}


# Plage valide par type C généré (cf. scripting/globals.py) — "int" n'a pas
# de plage restreinte (entier natif ARM 32 bits), donc absent de la table.
_TYPE_RANGES = {
    "bool": (0, 1),
    "u8":   (0, 255),
    "s8":   (-128, 127),
    "u16":  (0, 65535),
    "s16":  (-32768, 32767),
}


# ─── Checker ──────────────────────────────────────────────────────

class Checker:

    def __init__(self, ctx: BuildContext):
        self.ctx    = ctx
        self.errors: list[CheckError] = []

    def check(self, script: LuaScript, check_event_names: bool = True) -> list[CheckError]:
        for fn in script.functions:
            self._check_function(fn, check_event_names)
        return self.errors

    # ── Fonctions ─────────────────────────────────────────────────

    def _check_function(self, fn: LuaFunction, check_event_names: bool = True):
        # check_event_names=False pour les modules de behavior : leurs
        # fonctions top-level sont des noms de méthode arbitraires (M.update),
        # pas des handlers d'événement actor/scène — seul le corps est validé.
        if check_event_names and fn.name not in KNOWN_EVENTS:
            self.errors.append(CheckError(
                "warning",
                f"Fonction '{fn.name}' inconnue — les fonctions top-level doivent être "
                f"des handlers d'événement ({', '.join(KNOWN_EVENTS[:5])}…).",
            ))
        self._check_block(fn.body)

    # ── Statements ────────────────────────────────────────────────

    def _check_block(self, stmts: list):
        for s in stmts:
            self._check_stmt(s)

    def _check_stmt(self, s):
        if isinstance(s, StmtCall):
            self._check_call_expr(s.call)
        elif isinstance(s, (StmtAssign, StmtLocalAssign)):
            self._check_expr(getattr(s, "value", None))
        elif isinstance(s, StmtIf):
            self._check_expr(s.cond)
            self._check_block(s.then)
            for _, b in s.elseifs:
                self._check_block(b)
            self._check_block(s.else_)
        elif isinstance(s, (StmtWhile, StmtForNum)):
            self._check_block(s.body)

    def _check_expr(self, e):
        if e is None:
            return
        if isinstance(e, (ExprInvoke, ExprCall)):
            self._check_call_expr(e)

    # ── Appels ────────────────────────────────────────────────────

    def _check_call_expr(self, e):
        if isinstance(e, ExprInvoke):
            # self:method(args)
            if isinstance(e.obj, ExprName) and e.obj.name == "self":
                key = f"self:{e.method}"
                api = RUNTIME_API.get(key)
                if api is None:
                    self.errors.append(CheckError(
                        "warning",
                        f"Méthode inconnue : self:{e.method}() — "
                        f"vérifiez l'orthographe ou consultez l'API.",
                    ))
                else:
                    self._check_args(key, api, e.args)
                    if key == "self:play_sfx" and not self.ctx.sfx_component_name:
                        self.errors.append(CheckError(
                            "warning",
                            "self:play_sfx() : cet actor n'a pas de component SoundFX "
                            "(ou son champ Sfx est vide) — l'appel ne jouera rien.",
                        ))

        elif isinstance(e, ExprCall):
            # module.func(args) ou func(args)
            key = self._call_key(e.func)
            if key is None:
                return
            if key == "scene.switch":
                self._check_scene_switch(e.args)
                return
            if key in ("global.set", "global.get"):
                self._check_global_name(key, e.args)
                return
            if key == "const.get":
                self._check_const_name(key, e.args)
                return
            if key == "get_actor":
                self._check_get_actor(e.args)
                return
            api = RUNTIME_API.get(key)
            if api is None:
                # Pas une erreur : peut être une fonction helper définie par l'user
                pass
            else:
                self._check_args(key, api, e.args)

    def _call_key(self, func_expr) -> Optional[str]:
        """Reconstruit la clé API depuis l'expression de la fonction appelée."""
        if isinstance(func_expr, ExprName):
            return func_expr.name                    # ex: "get_actor", fonction helper user
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"   # ex: "sfx.play"
        return None

    def _check_args(self, key: str, api, args: list):
        """Vérifie le nombre d'arguments et les valeurs string si possible."""
        expected = len(api.params)
        got      = len(args)
        if api.variadic:
            if got < expected:
                self.errors.append(CheckError(
                    "error",
                    f"{key}() : au moins {expected} argument(s) attendu(s), {got} fourni(s).",
                ))
                return
        elif got != expected:
            self.errors.append(CheckError(
                "error",
                f"{key}() : {expected} argument(s) attendu(s), {got} fourni(s).",
            ))
            return

        for i, (param, arg) in enumerate(zip(api.params, args)):
            if not isinstance(arg, ExprString):
                continue   # on ne valide les strings que si elles sont littérales

            val = arg.value
            if param.domain == DOMAIN_ANIM:
                self._check_anim(key, val)
            elif param.domain == DOMAIN_SFX:
                self._check_sfx(key, val)
            elif param.domain == DOMAIN_MUSIC:
                self._check_music(key, val)
            elif param.domain == DOMAIN_KEY:
                self._check_key(key, val)

    def _check_anim(self, call_key: str, name: str):
        if self.ctx.anim_names is not None and name not in self.ctx.anim_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : animation '{name}' introuvable dans le "
                f"sprite lié ({', '.join(self.ctx.anim_names) or 'aucune'}).",
            ))

    def _check_sfx(self, call_key: str, name: str):
        if self.ctx.sfx_names is not None and name not in self.ctx.sfx_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : sfx '{name}' introuvable dans le projet.",
            ))

    def _check_music(self, call_key: str, name: str):
        if self.ctx.music_names is not None and name not in self.ctx.music_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : music '{name}' introuvable dans le projet.",
            ))

    def _check_global_name(self, call_key: str, args: list):
        if not args or not isinstance(args[0], ExprString):
            return
        name = args[0].value
        if self.ctx.global_names is not None and name not in self.ctx.global_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : variable globale '{name}' non déclarée dans le projet. "
                f"Ajoutez-la dans le panneau Globals de l'éditeur.",
            ))
            return
        if call_key == "global.set" and len(args) >= 2 and self.ctx.global_types is not None:
            self._check_global_range(name, self.ctx.global_types.get(name), args[1])

    @staticmethod
    def _literal_int(expr) -> Optional[int]:
        """Valeur entière d'un littéral connu à la compilation, sinon None
        (variable, expression calculée, etc. — pas de vérif possible)."""
        if isinstance(expr, ExprNumber):
            return expr.value
        if isinstance(expr, ExprUnop) and expr.op == "-" and isinstance(expr.operand, ExprNumber):
            return -expr.operand.value
        if isinstance(expr, ExprBool):
            return 1 if expr.value else 0
        return None

    def _check_global_range(self, name: str, typ: Optional[str], value_expr):
        rng = _TYPE_RANGES.get(typ)
        if rng is None:
            return
        val = self._literal_int(value_expr)
        if val is None:
            return
        lo, hi = rng
        if not (lo <= val <= hi):
            self.errors.append(CheckError(
                "warning",
                f"global.set('{name}', {val}) : valeur hors plage pour le type '{typ}' "
                f"({lo} à {hi}) — sera tronquée/wrap au build (comportement natif GBA/C), "
                f"pas d'erreur mais probablement pas ce que tu voulais.",
            ))

    def _check_const_name(self, call_key: str, args: list):
        if not args or not isinstance(args[0], ExprString):
            return
        name = args[0].value
        if self.ctx.const_names is not None and name not in self.ctx.const_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : constante '{name}' non déclarée dans le projet. "
                f"Ajoutez-la dans le panneau Constants de l'éditeur.",
            ))

    def _check_scene_switch(self, args: list):
        if not args or not isinstance(args[0], ExprString):
            return
        name = args[0].value
        if self.ctx.scene_names is not None and name not in self.ctx.scene_names:
            self.errors.append(CheckError(
                "warning",
                f"scene.switch('{name}') : scène '{name}' introuvable dans le projet "
                f"({', '.join(self.ctx.scene_names) or 'aucune'}).",
            ))

    def _check_get_actor(self, args: list):
        if not args or not isinstance(args[0], ExprString):
            return
        name = args[0].value
        if self.ctx.actor_names is not None and name not in self.ctx.actor_names:
            self.errors.append(CheckError(
                "warning",
                f"get_actor('{name}') : aucun actor nommé '{name}' dans la scène "
                f"({', '.join(self.ctx.actor_names) or 'aucun'}).",
            ))

    def _check_key(self, call_key: str, name: str):
        if name.lower() not in BuildContext.VALID_KEYS:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : bouton '{name}' invalide. "
                f"Valeurs valides : {', '.join(sorted(BuildContext.VALID_KEYS))}.",
            ))


# ─── Point d'entrée public ────────────────────────────────────────

def check(script: LuaScript, ctx: BuildContext, check_event_names: bool = True) -> list[CheckError]:
    return Checker(ctx).check(script, check_event_names)
