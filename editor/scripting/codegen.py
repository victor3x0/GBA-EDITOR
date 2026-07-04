"""
editor/scripting/codegen.py — Transpileur AST normalisé → C.

Reçoit un LuaScript (parser.py) et un CodegenContext (informations de
build) et produit le source C d'un fichier actor_<Name>.c.

Règles de génération :
  - Variables locales top-level  → static <type> g_<name>; (scope fichier)
  - Variables globales (globals.h) → accès direct par nom
  - self:method(args)  → actor_method(self, args) via RUNTIME_API
  - module.func(args)  → func_c(args) via RUNTIME_API
  - Opérateurs Lua     → opérateurs C (and→&&, or→||, ~=→!=, not→!)
  - Strings d'args API → constantes entières (ANIM_*, SFX_*, BTN_*, TAG_*)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .parser import (
    LuaScript, LuaFunction, LuaLocal,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile,
    StmtForNum, StmtReturn, StmtBreak,
    ExprNumber, ExprBool, ExprNil, ExprString, ExprName,
    ExprIndex, ExprInvoke, ExprCall, ExprBinop, ExprUnop,
)
from .api import (
    RUNTIME_API, EVENT_C_SIGNATURES, KNOWN_EVENTS, ApiFunc,
    KNOWN_SCENE_EVENTS, SCENE_EVENT_C_SIGNATURES, scene_event_sig,
    DOMAIN_ANIM, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_TAG, DOMAIN_SCENE,
    anim_constant, sfx_constant, music_constant, key_constant, tag_constant,
    SCREEN_CONSTANTS,
)


# ─── Contexte de génération ───────────────────────────────────────

@dataclass
class CodegenContext:
    """
    Informations fournies par build.py pour la génération du C.
    Permet de résoudre les constantes (ANIM_*, SFX_*…) à la compilation.
    """
    actor_name:   str            # "Hero" — utilisé comme préfixe C
    actor_sym:    str            # "Hero" nettoyé pour C (ex: "Mon_Hero")
    anim_names:   list[str]      # ["idle", "walk", "attack"] — depuis SpriteAsset
    sfx_names:    list[str]      # noms des Sfx du projet
    music_names:  list[str]      # noms des Music du projet
    global_names: set[str]       # noms des variables globales (depuis globals.h)
    const_names:  set[str]       # noms des constantes (depuis constants.h)
    all_actor_syms: list[str]    # tous les acteurs de la scène
    is_scene: bool = False       # True → script de scène (pas de self, signatures différentes)
    scripts_dir: Path | None = None  # racine project/scripts/ pour résoudre les require()
    is_pooled: bool = False      # True → locals → self->data[N] (prefab poolé)
    scene_names: list[str] = field(default_factory=list)  # noms de scènes du projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    sfx_autoplay: bool = False   # True → SoundFxComponent.trigger == "on_spawn"
    sfx_volumes: dict = field(default_factory=dict)  # {nom Sfx: volume 0-255} — sfx_play(id, volume)
    music_info: dict = field(default_factory=dict)  # {nom Music: (loop, volume)} — music_play(id, loop, volume)


# ─── Générateur ───────────────────────────────────────────────────

class CodeGen:

    def __init__(self, ctx: CodegenContext):
        self.ctx   = ctx
        self._lines: list[str] = []
        self._indent = 0
        self._required_behaviors: dict[str, str] = {}  # alias Lua → sym C
        self._pool_locals: dict[str, tuple[int, any]] = {}  # name → (data_index, init_value)

    # ── API publique ──────────────────────────────────────────────

    def generate(self, script: LuaScript) -> str:
        """Retourne le source C complet pour ce script."""
        self._emit_header()
        self._emit_locals(script.locals)
        # Inline des behaviors requis (collectés pendant _emit_locals via StmtLocalAssign)
        self._emit_inlined_behaviors(script)
        # Fonction d'init des data[] pour les prefabs poolés (avant les handlers)
        if self.ctx.is_pooled:
            self._emit_pool_init()
        defined = set()
        for fn in script.functions:
            self._emit_function(fn)
            defined.add(fn.name)
        # Stubs vides pour les events non définis (évite les erreurs de linker)
        known = KNOWN_SCENE_EVENTS if self.ctx.is_scene else KNOWN_EVENTS
        for event in known:
            if event not in defined:
                self._emit_stub(event)
        return "\n".join(self._lines) + "\n"

    def _emit_pool_init(self):
        """Génère void SYM_pool_init(Actor* self) — appelée par spawn avant on_start."""
        sym = self.ctx.actor_sym
        self._w(f"void {sym}_pool_init(Actor* self) {{")
        self._indent += 1
        if self._pool_locals:
            for name, (idx, init_val) in self._pool_locals.items():
                self._w(f"self->data[{idx}] = {init_val};  /* {name} */")
        else:
            self._w("(void)self;")
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_inlined_behaviors(self, script: LuaScript):
        """Parse et transpile les behaviors requis en fonctions C statiques inline."""
        from .parser import parse as lua_parse
        if not self._required_behaviors or not self.ctx.scripts_dir:
            return
        self._w("/* ── Behaviors inlinés ── */")
        for alias, sym in self._required_behaviors.items():
            stem = sym[len("beh_"):]          # "paddle_ai"
            beh_path = self.ctx.scripts_dir / "behaviors" / f"{stem}.lua"
            if not beh_path.exists():
                self._w(f"/* behavior '{stem}' introuvable : {beh_path} */")
                continue
            beh_src  = beh_path.read_text(encoding="utf-8")
            beh_ast  = lua_parse(beh_src)
            # Émettre chaque fonction du module comme helper C statique préfixé
            for fn in beh_ast.functions:
                # Ignore le nom de module (M.update → beh_paddle_ai_update)
                func_name = fn.name.split(".")[-1] if "." in fn.name else fn.name
                c_name    = f"{sym}_{func_name}"
                # Signature : premier param est l'actor receveur (conventionnellement "actor" ou "self")
                params_c  = ", ".join(
                    f"Actor* {p}" if i == 0 else f"int {p}"
                    for i, p in enumerate(fn.params)
                )
                self._w(f"static void {c_name}({params_c}) {{")
                self._indent += 1
                self._emit_block(fn.body)
                self._indent -= 1
                self._w("}")
                self._w("")

    def _scan_requires(self, stmts):
        """Pré-scan récursif pour enregistrer les require() avant la génération."""
        from .parser import StmtLocalAssign, ExprCall, ExprName, ExprString
        for s in stmts:
            if (isinstance(s, StmtLocalAssign)
                    and s.value is not None
                    and isinstance(s.value, ExprCall)
                    and isinstance(s.value.func, ExprName)
                    and s.value.func.name == "require"
                    and s.value.args
                    and isinstance(s.value.args[0], ExprString)):
                path_str = s.value.args[0].value
                stem     = Path(path_str).stem
                sym      = f"beh_{stem}"
                self._required_behaviors[s.name] = sym

    # ── En-tête ───────────────────────────────────────────────────

    def _emit_header(self):
        sym = self.ctx.actor_sym
        if self.ctx.is_scene:
            self._w(f"/* scene_{sym}.c — script de scène, généré par GBA Editor (ne pas éditer) */")
        else:
            self._w(f"/* actor_{sym}.c — généré par GBA Editor (ne pas éditer) */")
        self._w('#include "runtime.h"')
        self._w('#include "globals.h"')
        self._w('#include "constants.h"')
        # Forward declarations pour éviter les erreurs d'ordre (ex: destroy appelle on_destroy)
        if not self.ctx.is_scene:
            self._w("")
            known = KNOWN_EVENTS
            for event in known:
                sig_tpl = EVENT_C_SIGNATURES.get(event)
                if sig_tpl:
                    self._w(sig_tpl.format(prefix=sym) + ";")
        # Constantes d'animation pour cet acteur
        if self.ctx.anim_names:
            self._w("")
            self._w(f"/* Animations de {self.ctx.actor_name} */")
            for i, name in enumerate(self.ctx.anim_names):
                self._w(f"#define {anim_constant(sym, name)} {i}")
        # Constantes SFX
        if self.ctx.sfx_names:
            self._w("")
            self._w("/* SFX */")
            for i, name in enumerate(self.ctx.sfx_names):
                self._w(f"#define {sfx_constant(name)} {i}")
        # Constantes Music
        if self.ctx.music_names:
            self._w("")
            self._w("/* Music */")
            for i, name in enumerate(self.ctx.music_names):
                self._w(f"#define {music_constant(name)} {i}")
        self._w("")

    # ── Variables locales top-level (static = scope fichier) ──────

    def _emit_locals(self, locals_: list[LuaLocal]):
        # Pré-enregistrer les require() et les exclure des déclarations C
        for loc in locals_:
            if (loc.value is not None
                    and isinstance(loc.value, ExprCall)
                    and isinstance(loc.value.func, ExprName)
                    and loc.value.func.name == "require"
                    and loc.value.args
                    and isinstance(loc.value.args[0], ExprString)):
                path_str = loc.value.args[0].value
                stem     = Path(path_str).stem
                self._required_behaviors[loc.name] = f"beh_{stem}"

        non_require = [
            loc for loc in locals_
            if not (loc.value is not None
                    and isinstance(loc.value, ExprCall)
                    and isinstance(loc.value.func, ExprName)
                    and loc.value.func.name == "require")
        ]
        if not non_require:
            return
        if self.ctx.is_pooled:
            # Prefab poolé : locals → self->data[N] (état par instance)
            self._w("/* Variables locales — stockées dans Actor.data[] (une par instance) */")
            for i, loc in enumerate(non_require):
                init_val = self._expr(loc.value) if loc.value is not None else "0"
                self._pool_locals[loc.name] = (i, init_val)
                self._w(f"/* data[{i}] = {loc.name} (init={init_val}) */")
        else:
            # Actor statique : locals → variables C statiques (partagées, OK car une seule instance)
            self._w("/* Variables locales à cet acteur */")
            for loc in non_require:
                init = f" = {self._expr(loc.value)}" if loc.value is not None else " = 0"
                self._w(f"static int {loc.name}{init};")
        self._w("")

    # ── Fonctions / handlers ──────────────────────────────────────

    def _emit_function(self, fn: LuaFunction):
        if self.ctx.is_scene:
            sym = self.ctx.actor_sym
            if fn.name in KNOWN_SCENE_EVENTS:
                sig = scene_event_sig(sym, fn.name)   # "void PONG_scene_on_start(void)"
            else:
                sig = f"static void {sym}_scene_{fn.name}(void)"
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(fn.name)
            if sig_tpl is None:
                sig = f"static void {self.ctx.actor_sym}_{fn.name}(Actor* self)"
            else:
                sig = sig_tpl.format(prefix=self.ctx.actor_sym)
        self._w(sig + " {")
        self._indent += 1
        if not self.ctx.is_scene and fn.name == "on_start":
            self._emit_sfx_autoplay()
        self._emit_block(fn.body)
        self._indent -= 1
        self._w("}")
        self._w("")

    def _emit_sfx_autoplay(self):
        """Injecte l'appel sfx_play() auto au début de on_start si trigger == 'on_spawn'."""
        if self.ctx.sfx_autoplay and self.ctx.sfx_component_name:
            self._w(f"sfx_play({sfx_constant(self.ctx.sfx_component_name)});")

    # ── Blocs et statements ───────────────────────────────────────

    def _emit_block(self, stmts: list):
        for s in stmts:
            self._emit_stmt(s)

    def _emit_stmt(self, s):
        if isinstance(s, StmtCall):
            self._w(self._call_expr(s.call) + ";")

        elif isinstance(s, StmtAssign):
            tgt = self._expr(s.target)
            val = self._expr(s.value)
            self._w(f"{tgt} = {val};")

        elif isinstance(s, StmtLocalAssign):
            # Détecte local M = require("behaviors/foo") → enregistre l'alias, pas de décl C
            if (s.value is not None
                    and isinstance(s.value, ExprCall)
                    and isinstance(s.value.func, ExprName)
                    and s.value.func.name == "require"
                    and s.value.args
                    and isinstance(s.value.args[0], ExprString)):
                path_str = s.value.args[0].value          # "behaviors/paddle_ai"
                stem     = Path(path_str).stem             # "paddle_ai"
                sym      = f"beh_{stem}"                   # "beh_paddle_ai"
                self._required_behaviors[s.name] = sym
                # Pas de déclaration C — le behavior est inclus dans l'en-tête
                return
            val = self._expr(s.value) if s.value is not None else "0"
            # Détecte local var = get_actor("...") → Actor* au lieu de int
            is_actor_ref = (
                s.value is not None
                and isinstance(s.value, ExprCall)
                and isinstance(s.value.func, ExprName)
                and s.value.func.name == "get_actor"
            )
            ctype = "Actor*" if is_actor_ref else "int"
            self._w(f"{ctype} {s.name} = {val};")

        elif isinstance(s, StmtIf):
            cond = self._expr(s.cond)
            self._w(f"if ({cond}) {{")
            self._indent += 1
            self._emit_block(s.then)
            self._indent -= 1
            for elif_cond, elif_body in s.elseifs:
                self._w(f"}} else if ({self._expr(elif_cond)}) {{")
                self._indent += 1
                self._emit_block(elif_body)
                self._indent -= 1
            if s.else_:
                self._w("} else {")
                self._indent += 1
                self._emit_block(s.else_)
                self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtWhile):
            self._w(f"while ({self._expr(s.cond)}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtForNum):
            # for i = start, stop[, step] do
            start = self._expr(s.start)
            stop  = self._expr(s.stop) if s.stop else "0"
            step  = self._expr(s.step) if s.step else "1"
            v     = s.var
            self._w(f"for (int {v} = {start}; {v} <= {stop}; {v} += {step}) {{")
            self._indent += 1
            self._emit_block(s.body)
            self._indent -= 1
            self._w("}")

        elif isinstance(s, StmtReturn):
            if s.values:
                self._w(f"return {self._expr(s.values[0])};")
            else:
                self._w("return;")

        elif isinstance(s, StmtBreak):
            self._w("break;")

    # ── Expressions ───────────────────────────────────────────────

    def _expr(self, e) -> str:
        if e is None:
            return "0"
        if isinstance(e, ExprNumber):
            return str(e.value)
        if isinstance(e, ExprBool):
            return "1" if e.value else "0"
        if isinstance(e, ExprNil):
            return "0"
        if isinstance(e, ExprString):
            # String littérale en dehors d'un appel API → chaîne C (rare en v1)
            return f'"{e.value}"'
        if isinstance(e, ExprName):
            # Prefab poolé : locals → self->data[N]
            if self.ctx.is_pooled and e.name in self._pool_locals:
                idx, _ = self._pool_locals[e.name]
                return f"self->data[{idx}]"
            return e.name
        if isinstance(e, ExprIndex):
            # screen.width / screen.height / etc. → littéral C
            if isinstance(e.obj, ExprName) and e.obj.name == "screen":
                val = SCREEN_CONSTANTS.get(e.field)
                if val is not None:
                    return str(val)
            # module.field — retourne le nom composé pour la résolution ultérieure
            return f"{self._expr(e.obj)}.{e.field}"
        if isinstance(e, (ExprInvoke, ExprCall)):
            return self._call_expr(e)
        if isinstance(e, ExprBinop):
            return f"({self._expr(e.left)} {e.op} {self._expr(e.right)})"
        if isinstance(e, ExprUnop):
            op = "!" if e.op == "not" else e.op
            return f"({op}{self._expr(e.operand)})"
        return "0"

    # ── Résolution des appels API ──────────────────────────────────

    def _call_expr(self, e) -> str:
        """Génère le C pour un appel de fonction/méthode."""
        if isinstance(e, ExprInvoke):
            return self._invoke(e)
        if isinstance(e, ExprCall):
            return self._call(e)
        return "/* appel non géré */"

    def _invoke(self, e: ExprInvoke) -> str:
        """var:method(args) — var peut être self ou toute variable Actor*."""
        if not isinstance(e.obj, ExprName):
            return f"/* invoke sur expression complexe ignoré */"
        receiver = e.obj.name          # "self", "other", "paddle", ...
        key = f"self:{e.method}"       # les méthodes sont toujours indexées sous "self:"
        # destroy : appelle on_destroy puis désactive
        if e.method == "destroy":
            sym = self.ctx.actor_sym
            return f"{sym}_on_destroy({receiver}); actor_destroy_internal({receiver})"
        # play_sfx : résolu au build depuis le SoundFxComponent de cet actor
        if e.method == "play_sfx":
            return self._emit_play_sfx()
        api = RUNTIME_API.get(key)
        if api is None:
            args = ", ".join(self._expr(a) for a in e.args)
            return f"actor_{e.method}({receiver}, {args})"
        return self._emit_api_call(api, e.args, receiver=receiver)

    def _call(self, e: ExprCall) -> str:
        """func(args) ou module.func(args)"""
        key = self._call_key(e.func)

        # Appel sur un behavior requis : AI.update(self, x) → beh_foo_update(self, x)
        if (isinstance(e.func, ExprIndex)
                and isinstance(e.func.obj, ExprName)
                and e.func.obj.name in self._required_behaviors):
            sym  = self._required_behaviors[e.func.obj.name]
            func = f"{sym}_{e.func.field}"
            args = ", ".join(self._expr(a) for a in e.args)
            return f"{func}({args})"

        # Cas spéciaux résolus directement par le codegen
        if key == "get_actor":
            return self._emit_get_actor(e.args)
        if key == "global.get":
            return self._emit_global_get(e.args)
        if key == "global.set":
            return self._emit_global_set(e.args)
        if key == "const.get":
            return self._emit_const_get(e.args)
        if key == "actor.spawn":
            return self._emit_actor_spawn(e.args)
        if key == "scene.switch":
            return self._emit_scene_switch(e.args)
        if key == "sfx.play":
            return self._emit_sfx_play(e.args)
        if key == "music.play":
            return self._emit_music_play(e.args)

        api = RUNTIME_API.get(key) if key else None
        if api is None:
            # Appel à une fonction helper interne ou inconnue
            func_c = key or self._expr(e.func)
            args   = ", ".join(self._expr(a) for a in e.args)
            return f"{func_c}({args})"
        return self._emit_api_call(api, e.args, with_self=False)

    def _call_key(self, func_expr) -> Optional[str]:
        if isinstance(func_expr, ExprName):
            return func_expr.name
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"
        return None

    def _emit_api_call(self, api: ApiFunc, lua_args: list,
                       with_self: bool = False, receiver: str | None = None) -> str:
        """Génère l'appel C en résolvant les args string → constantes."""
        c_args = []
        if receiver is not None:
            c_args.append(receiver)
        elif with_self:
            c_args.append("self")
        for param, arg in zip(api.params, lua_args):
            c_args.append(self._resolve_arg(param, arg))
        # Args variadiques : tous ceux qui dépassent les params déclarés
        if api.variadic:
            for extra in lua_args[len(api.params):]:
                c_args.append(self._expr(extra))
        return f"{api.c_func}({', '.join(c_args)})"

    def _resolve_arg(self, param, arg) -> str:
        """Convertit un arg Lua en expression C, résolvant les strings → constantes."""
        from .api import PARAM_STR_LITERAL
        if param.ptype == PARAM_STR_LITERAL:
            # Chaîne littérale → guillemets C, sans résolution de constante
            val = arg.value if isinstance(arg, ExprString) else self._expr(arg)
            return f'"{val}"' if isinstance(arg, ExprString) else val
        if not isinstance(arg, ExprString) or param.domain is None:
            return self._expr(arg)
        name = arg.value
        sym  = self.ctx.actor_sym
        match param.domain:
            case d if d == DOMAIN_ANIM:   return anim_constant(sym, name)
            case d if d == DOMAIN_SFX:    return sfx_constant(name)
            case d if d == DOMAIN_MUSIC:  return music_constant(name)
            case d if d == DOMAIN_KEY:    return key_constant(name)
            case d if d == DOMAIN_TAG:    return tag_constant(name)
            case _:                        return f'"{name}"'

    # ── Cas spéciaux ──────────────────────────────────────────────

    def _emit_play_sfx(self) -> str:
        """self:play_sfx() → sfx_play(SFX_X, volume) où X/volume viennent du SoundFxComponent."""
        if not self.ctx.sfx_component_name:
            return "(void)0 /* self:play_sfx() : aucun SoundFX configuré sur cet actor */"
        name   = self.ctx.sfx_component_name
        volume = self.ctx.sfx_volumes.get(name, 255)
        return f"sfx_play({sfx_constant(name)}, {volume})"

    def _emit_sfx_play(self, args: list) -> str:
        """sfx.play("Name") → sfx_play(SFX_NAME, volume) — volume lu depuis la ressource Sfx."""
        if not args or not isinstance(args[0], ExprString):
            return "/* sfx.play() : argument invalide */"
        name   = args[0].value
        volume = self.ctx.sfx_volumes.get(name, 255)
        return f"sfx_play({sfx_constant(name)}, {volume})"

    def _emit_music_play(self, args: list) -> str:
        """music.play("Name") → music_play(MUSIC_NAME, loop, volume) — loop/volume lus depuis la ressource Music."""
        if not args or not isinstance(args[0], ExprString):
            return "/* music.play() : argument invalide */"
        name = args[0].value
        loop, volume = self.ctx.music_info.get(name, (True, 255))
        return f"music_play({music_constant(name)}, {1 if loop else 0}, {volume})"

    def _emit_get_actor(self, args: list) -> str:
        """
        get_actor("PADDLE_AUTO")  →  &g_actors[TAG_PADDLE_AUTO]
        Résolu à la compilation, zéro overhead runtime.
        """
        if not args or not isinstance(args[0], ExprString):
            return "/* get_actor() : argument invalide */"
        sym = args[0].value.replace(" ", "_")
        return f"&g_actors[TAG_{sym.upper()}]"

    def _emit_send(self, args: list) -> str:
        """
        send("Enemy", "on_take_damage", 1)
        →  Enemy_on_take_damage(&g_actors[TAG_ENEMY], 1)
        (appel direct — résolu à la compilation, zéro overhead runtime)
        """
        if len(args) < 2:
            return "/* send() : arguments manquants */"
        target = args[0].value if isinstance(args[0], ExprString) else self._expr(args[0])
        event  = args[1].value if isinstance(args[1], ExprString) else self._expr(args[1])
        value  = self._expr(args[2]) if len(args) > 2 else "0"
        target_sym = target.replace(" ", "_")
        return f"{target_sym}_{event}(&g_actors[TAG_{target_sym.upper()}], {value})"

    def _emit_broadcast(self, args: list) -> str:
        """
        broadcast("on_receive", 42)
        → do { if(g_actors[i].active) SYM_on_receive(&g_actors[i], 0, 42); ... } while(0)
        Expansion statique à la compilation, zéro overhead runtime.
        """
        if len(args) < 2:
            return "/* broadcast() : arguments manquants */"
        event = args[0].value if isinstance(args[0], ExprString) else self._expr(args[0])
        value = self._expr(args[1]) if len(args) > 1 else "0"
        calls = []
        for i, sym in enumerate(self.ctx.all_actor_syms):
            calls.append(f"if(g_actors[{i}].active) {sym}_{event}(&g_actors[{i}], 0, {value})")
        inner = "; ".join(calls)
        return f"do {{ {inner}; }} while(0)"

    def _emit_scene_switch(self, args: list) -> str:
        """scene.switch("VICTORY") → scene_switch(SCENE_IDX_VICTORY)"""
        if not args or not isinstance(args[0], ExprString):
            return "/* scene.switch : nom de scène non littéral */"
        name = args[0].value
        sym  = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
        return f"scene_switch(SCENE_IDX_{sym.upper()})"

    def _emit_actor_spawn(self, args: list) -> str:
        """actor.spawn("PrefabName", x, y) → spawn_PrefabName(x, y)"""
        if not args or not isinstance(args[0], ExprString):
            return "/* actor.spawn : nom de prefab non littéral */"
        prefab_name = args[0].value
        sym = prefab_name.replace(" ", "_")
        rest = ", ".join(self._expr(a) for a in args[1:])
        return f"spawn_{sym}({rest})"

    def _emit_global_get(self, args: list) -> str:
        if args and isinstance(args[0], ExprString):
            return f"g_{args[0].value}"
        return "/* global.get : nom non littéral */"

    def _emit_global_set(self, args: list) -> str:
        if len(args) >= 2 and isinstance(args[0], ExprString):
            val = self._expr(args[1])
            return f"g_{args[0].value} = {val}"
        return "/* global.set : nom non littéral */"

    def _emit_const_get(self, args: list) -> str:
        if args and isinstance(args[0], ExprString):
            return f"CONST_{args[0].value.upper()}"
        return "/* const.get : nom non littéral */"

    def _emit_stub(self, event_name: str):
        """Stub vide pour un event non défini dans le script."""
        if self.ctx.is_scene:
            if event_name not in KNOWN_SCENE_EVENTS:
                return
            sig = scene_event_sig(self.ctx.actor_sym, event_name)
            self._w(sig + " {}")
        else:
            sig_tpl = EVENT_C_SIGNATURES.get(event_name)
            if sig_tpl is None:
                return
            sig = sig_tpl.format(prefix=self.ctx.actor_sym)
            sig = sig.replace("Actor* self", "Actor* self __attribute__((unused))")
            sig = sig.replace("Actor* other", "Actor* other __attribute__((unused))")
            sig = sig.replace("int event_id", "int event_id __attribute__((unused))")
            sig = sig.replace("int value", "int value __attribute__((unused))")
            sig = sig.replace("u8 my_box", "u8 my_box __attribute__((unused))")
            sig = sig.replace("u8 other_box", "u8 other_box __attribute__((unused))")
            sig = sig.replace("int normal_x", "int normal_x __attribute__((unused))")
            sig = sig.replace("int normal_y", "int normal_y __attribute__((unused))")
            if event_name == "on_start" and self.ctx.sfx_autoplay and self.ctx.sfx_component_name:
                self._w(sig + " {")
                self._indent += 1
                self._emit_sfx_autoplay()
                self._indent -= 1
                self._w("}")
            else:
                self._w(sig + " {}")
        self._w("")

    # ── Émission de lignes ────────────────────────────────────────

    def _w(self, line: str):
        self._lines.append("    " * self._indent + line)


# ─── Point d'entrée public ────────────────────────────────────────

def generate(script: LuaScript, ctx: CodegenContext) -> str:
    return CodeGen(ctx).generate(script)
