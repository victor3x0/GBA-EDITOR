"""
runtime_codegen/lua_compiler.py — Transpilation Lua -> C pour acteurs, prefabs et scènes.

Entrées  : Project, Scene, liste (Actor, SpriteAsset)
Sorties  : fichiers actor_*.c et scene.c écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from core.project import Project, Scene, Actor, SpriteAsset, ScriptComponent
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals
from scripting.constants import write_constants
from codegen.build_utils import sym as _sym


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def _sfx_component_info(owner) -> tuple[Optional[str], bool]:
    """Retourne (sfx_name, autoplay) depuis le SoundFxComponent d'un actor/prefab, si présent."""
    comp = owner.get_component("sound_fx")
    if not comp or not comp.active or not comp.sfx_name:
        return None, False
    return comp.sfx_name, comp.trigger == "on_spawn"


def transpile_all(
    p: Project,
    scene: Scene,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    emit,
    scene_names: list[str] | None = None,
    precomputed_global_names: list[str] | None = None,
    precomputed_const_names: list[str] | None = None,
    compiled_prefabs: set[str] | None = None,
) -> bool:
    """
    Compile tous les scripts Lua de la scène en C.

    Retourne False si une erreur bloquante est trouvée.
    """
    sfx_names   = [s.name for s in p.sfx]   if hasattr(p, "sfx")   else []
    sfx_volumes = {s.name: getattr(s, "volume", 255) for s in p.sfx} if hasattr(p, "sfx") else {}
    music_names = [m.name for m in p.music] if hasattr(p, "music") else []
    music_info  = ({m.name: (getattr(m, "loop", True), getattr(m, "volume", 255)) for m in p.music}
                   if hasattr(p, "music") else {})
    all_syms    = [_sym(a.name) for a, _ in scene_actors]
    _scene_names = scene_names or []

    # Globals résolus en avance (nécessaire pour le BuildContext du checker)
    if precomputed_global_names is not None:
        global_names = precomputed_global_names
    else:
        global_names = write_globals(p.src_dir, p.globals)
        if global_names:
            emit("log_line", f"[lua] globals: {', '.join('g_'+n for n in global_names)}")

    # Constants résolues en avance, même principe que les globals
    if precomputed_const_names is not None:
        const_names = precomputed_const_names
    else:
        const_names = write_constants(p.src_dir, p.constants)
        if const_names:
            emit("log_line", f"[lua] constants: {', '.join('CONST_'+n.upper() for n in const_names)}")

    parsed_scripts = []

    for actor, sprite in scene_actors:
        script_path = _actor_script(actor)
        if not script_path:
            continue
        sp = p.asset_abs(script_path)
        if not sp or not sp.exists():
            continue

        if sp.suffix.lower() == ".c":
            shutil.copy2(sp, p.src_dir / sp.name)
            emit("log_line", f"[script] {sp.name} copié (C natif)")
            continue

        if sp.suffix.lower() != ".lua":
            continue

        source = sp.read_text(encoding="utf-8")
        try:
            script = lua_parse(source)
        except LuaParseError as e:
            emit("error_line", f"[error] {sp.name} — parse: {e}")
            return False

        anim_names = [st.name for st in sprite.states] if sprite and sprite.states else []
        sfx_comp_name, _ = _sfx_component_info(actor)
        ctx_check = BuildContext(
            actor_name   = actor.name,
            anim_names   = anim_names,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            global_names = list(global_names) if global_names else None,
            const_names  = list(const_names) if const_names else None,
            sfx_component_name = sfx_comp_name,
        )
        errors = lua_check(script, ctx_check)
        for err in errors:
            prefix = "[error]" if err.level == "error" else "[warn] "
            emit("log_line", f"{prefix} {sp.name}: {err.message}")
        if any(e.level == "error" for e in errors):
            return False

        parsed_scripts.append((actor, sprite, script, sp))

    # Script de scène — parse
    scene_script_ast  = None
    scene_script_file = None
    scene_script_path = getattr(scene, "script", "")
    if scene_script_path:
        sp = p.asset_abs(scene_script_path)
        if sp and sp.exists() and sp.suffix.lower() == ".lua":
            try:
                scene_script_ast  = lua_parse(sp.read_text(encoding="utf-8"))
                scene_script_file = sp
            except LuaParseError as e:
                emit("error_line", f"[scene script] parse: {e}")
                return False

    # Génération C — actors de scène
    for actor, sprite, script, sp in parsed_scripts:
        s    = _sym(actor.name)
        anims = [st.name for st in sprite.states] if sprite and sprite.states else []
        sfx_comp_name, sfx_autoplay = _sfx_component_info(actor)
        ctx  = CodegenContext(
            actor_name    = actor.name,
            actor_sym     = s,
            anim_names    = anims,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            scripts_dir   = p.scripts_dir,
            scene_names   = _scene_names,
            sfx_component_name = sfx_comp_name,
            sfx_autoplay  = sfx_autoplay,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
        )
        c_code = lua_generate(script, ctx).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out = p.src_dir / f"actor_{s}.c"
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua->c] {sp.name} -> {out.name}")

    # Génération C — prefabs poolés (compilés une seule fois grâce à compiled_prefabs)
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) <= 0:
            continue
        pf_sym = _sym(pf.name)
        if compiled_prefabs is not None:
            if pf_sym in compiled_prefabs:
                continue
            compiled_prefabs.add(pf_sym)
        sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
        if not sc or not sc.script:
            continue
        sp_path = p.asset_abs(sc.script)
        if not sp_path or not sp_path.exists() or sp_path.suffix.lower() != ".lua":
            continue
        try:
            pf_ast = lua_parse(sp_path.read_text(encoding="utf-8"))
        except Exception as ex:
            emit("log_line", f"[warn] prefab {pf.name}: parse error: {ex}")
            continue
        pf_spr  = next((c for c in pf.components if hasattr(c, "states")), None)
        pf_anim = [st.name for st in pf_spr.states] if pf_spr and hasattr(pf_spr, "states") else []
        pf_sfx_comp_name, pf_sfx_autoplay = _sfx_component_info(pf)
        ctx_pf  = CodegenContext(
            actor_name    = pf.name,
            actor_sym     = pf_sym,
            anim_names    = pf_anim,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            scripts_dir   = p.scripts_dir,
            is_pooled     = True,
            scene_names   = _scene_names,
            sfx_component_name = pf_sfx_comp_name,
            sfx_autoplay  = pf_sfx_autoplay,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
        )
        pf_c = lua_generate(pf_ast, ctx_pf).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out_pf = p.src_dir / f"actor_{pf_sym}.c"
        out_pf.write_text(pf_c, encoding="utf-8")
        emit("log_line", f"[lua->c] prefab {pf.name} -> {out_pf.name}")

    # Génération C — script de scène
    if scene_script_ast and scene_script_file:
        scene_s = _sym(scene.name)
        ctx_sc  = CodegenContext(
            actor_name    = scene.name,
            actor_sym     = scene_s,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            is_scene      = True,
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
        )
        c_code = lua_generate(scene_script_ast, ctx_sc).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out_name = f"{scene_s}_scene.c"
        out = p.src_dir / out_name
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua->c] {scene_script_file.name} -> {out_name}")

    return True
