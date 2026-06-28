"""
runtime_codegen/lua_compiler.py — Transpilation Lua → C pour acteurs, prefabs et scènes.

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
from codegen.build_utils import sym as _sym


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def transpile_all(
    p: Project,
    scene: Scene,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    emit,
    scene_names: list[str] | None = None,
) -> bool:
    """
    Compile tous les scripts Lua de la scène en C.

    Retourne False si une erreur bloquante est trouvée.
    """
    sfx_names   = [s.name for s in p.sfx]   if hasattr(p, "sfx")   else []
    music_names = [m.name for m in p.music] if hasattr(p, "music") else []
    all_syms    = [_sym(a.name) for a, _ in scene_actors]
    _scene_names = scene_names or []

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
        ctx_check = BuildContext(
            actor_name  = actor.name,
            anim_names  = anim_names,
            sfx_names   = sfx_names,
            music_names = music_names,
            scene_names = _scene_names,
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

    # Globals
    all_lua = [s for _, _, s, _ in parsed_scripts]
    if scene_script_ast:
        all_lua.append(scene_script_ast)
    global_names = write_globals(p.src_dir, all_lua)
    if global_names:
        emit("log_line", f"[lua] globals: {', '.join('g_'+n for n in global_names)}")
    else:
        write_globals(p.src_dir, [])

    # Génération C — actors de scène
    for actor, sprite, script, sp in parsed_scripts:
        s    = _sym(actor.name)
        anims = [st.name for st in sprite.states] if sprite and sprite.states else []
        ctx  = CodegenContext(
            actor_name    = actor.name,
            actor_sym     = s,
            anim_names    = anims,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            all_actor_syms= all_syms,
            scripts_dir   = p.scripts_dir,
            scene_names   = _scene_names,
        )
        c_code = lua_generate(script, ctx).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out = p.src_dir / f"actor_{s}.c"
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua→c] {sp.name} → {out.name}")

    # Génération C — prefabs poolés
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) <= 0:
            continue
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
        pf_sym  = _sym(pf.name)
        pf_spr  = next((c for c in pf.components if hasattr(c, "states")), None)
        pf_anim = [st.name for st in pf_spr.states] if pf_spr and hasattr(pf_spr, "states") else []
        ctx_pf  = CodegenContext(
            actor_name    = pf.name,
            actor_sym     = pf_sym,
            anim_names    = pf_anim,
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            all_actor_syms= all_syms,
            scripts_dir   = p.scripts_dir,
            is_pooled     = True,
            scene_names   = _scene_names,
        )
        pf_c = lua_generate(pf_ast, ctx_pf).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out_pf = p.src_dir / f"actor_{pf_sym}.c"
        out_pf.write_text(pf_c, encoding="utf-8")
        emit("log_line", f"[lua→c] prefab {pf.name} → {out_pf.name}")

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
            all_actor_syms= all_syms,
            is_scene      = True,
            scene_names   = _scene_names,
        )
        c_code = lua_generate(scene_script_ast, ctx_sc).replace(
            '#include "runtime.h"', '#include "actor_api.h"')
        out = p.src_dir / "scene.c"
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua→c] {scene_script_file.name} → scene.c")

    return True
