"""
runtime_codegen/lua_compiler.py — Transpilation Lua -> C pour acteurs, prefabs et scènes.

Entrées  : Project, Scene, liste (Actor, SpriteAsset)
Sorties  : fichiers actor_*.c et scene.c écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from core.models.components import ScriptComponent
from core.models.sprite import SpriteAsset
from core.models.scene import Actor, Scene
from core.project import Project
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals
from scripting.constants import write_constants
from codegen.c_names import sym as c_sym


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def _sfx_component_info(owner) -> tuple[Optional[str], bool]:
    """Retourne (sfx_name, autoplay) depuis le SoundFxComponent d'un actor/prefab, si présent."""
    comp = owner.get_component("sound_fx")
    if not comp or not comp.active or not comp.sfx_name:
        return None, False
    return comp.sfx_name, comp.trigger == "on_spawn"


def _compile_script(sp: Path, ctx_check: "BuildContext", emit, label: str):
    """
    Parse + valide un script Lua (actor, scène ou prefab — même traitement
    pour les trois, contrairement à avant où seuls les actors étaient
    validés). Retourne (ast, ok) : ast est None si le parse échoue ; ok est
    False sur erreur bloquante (parse ou check), quel que soit le type de
    script — un prefab avec une faute de syntaxe bloque désormais le build
    au lieu d'être silencieusement sauté.
    """
    try:
        script = lua_parse(sp.read_text(encoding="utf-8"))
    except LuaParseError as e:
        emit("error_line", f"[error] {label} — parse: {e}")
        return None, False
    errors = lua_check(script, ctx_check)
    for err in errors:
        prefix = "[error]" if err.level == "error" else "[warn] "
        emit("log_line", f"{prefix} {label}: {err.message}")
    if any(e.level == "error" for e in errors):
        return script, False
    return script, True


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
    compiled_cameras: set[str] | None = None,
    sound_assets: dict | None = None,
) -> bool:
    """
    Compile tous les scripts Lua de la scène en C.

    Retourne False si une erreur bloquante est trouvée.
    """
    # L'ORDRE fait foi ici aussi, mais il ne nous appartient PAS : c'est mmutil
    # qui numérote les sons, dans l'ordre où le build les lui passe. `SFX_X` et
    # `MUSIC_X` doivent donc être des rangs dans les listes RÉELLEMENT émises
    # (`sound_assets`), jamais dans le catalogue du projet.
    #
    # Le piège s'est refermé le jour où le build a cessé de tout émettre : tant
    # que les 105 musiques partaient dans l'ordre du projet, les deux
    # numérotations coïncidaient par accident et `music.play` fonctionnait.
    # Filtrer sur ce qui est référencé a désaligné les deux, sans qu'aucun
    # symbole ne manque — la ROM compilait et jouait le mauvais module.
    if sound_assets is not None:
        sfx_items   = [s for s, _ in sound_assets.get("sfx", [])]
        music_items = [m for m, _ in sound_assets.get("music", [])]
    else:
        sfx_items   = list(getattr(p, "sfx", []))
        music_items = list(getattr(p, "music", []))
    sfx_names   = [s.name for s in sfx_items]
    sfx_volumes = {s.name: getattr(s, "volume", 100) for s in sfx_items}
    music_names = [m.name for m in music_items]
    music_info  = ({m.name: (getattr(m, "loop", True), getattr(m, "volume", 100)) for m in p.music}
                   if hasattr(p, "music") else {})
    # Textes et polices : l'ORDRE fait foi (il devient l'index dans les tables C
    # émises par main_gen). project_fonts() est la source unique côté polices.
    from codegen.runtime_codegen.main_gen import project_fonts
    # `build_texts()` et non `texts` : les littéraux de `text.draw` deviennent
    # des entrées anonymes, et leurs `#define TEXT_*` doivent exister aussi.
    text_keys   = ([t.key for t in p.build_texts()] if hasattr(p, "build_texts")
                   else [t.key for t in getattr(p, "texts", [])])
    font_names  = [f.name for f in project_fonts(p)]
    # Palettes : le catalogue ENTIER, dans son ordre. L'ordre devient
    # l'index dans g_palettes (main_gen), comme pour les textes et les
    # polices. Pas de dérivation depuis les scripts : la ROM est assez
    # large pour toutes les porter (32 octets pièce).
    palette_names = [b.name for b in getattr(p, "palettes", [])]
    # Zones de texte : l'ordre de `all_regions()` devient l'index dans
    # g_ui_regions, comme pour les textes et les polices.
    region_names = (p.region_names() if hasattr(p, "region_names") else [])
    image_names  = (p.image_names()  if hasattr(p, "image_names")  else [])
    # TOUS les éléments d'UI, tous types confondus — l'index de la table de
    # visibilité plate (UIELEM_*), pour ui.get().
    element_names = (p.ui_element_names() if hasattr(p, "ui_element_names") else [])
    # Les états que chaque image peut prendre, lus dans SON sprite : c'est le
    # seul endroit du build qui tienne les deux bouts (l'élément et l'asset).
    image_states = {}
    for _lay, _im in (p.all_images() if hasattr(p, "all_images") else []):
        _spr = p.get_sprite(getattr(_im, "sprite_name", "") or "")
        image_states[_im.name] = [st.name for st in (getattr(_spr, "states", []) or [])]
    all_syms    = [c_sym(a.name) for a, _ in scene_actors]
    _actor_names = [a.name for a, _ in scene_actors]
    _scene_names = scene_names or []
    _camera_names = [c.name for c in getattr(p, "cameras", [])]
    # Une famille, un espace de noms — depuis que les trois boîtes sont trois
    # assets, rien n'oblige leurs états à se distinguer entre familles.
    from core.models.sound_box import KIND_SOUND, KIND_JINGLE
    _snd_names = (p.sound_state_names(KIND_SOUND)
                  if hasattr(p, "sound_state_names") else [])
    _jgl_names = (p.sound_state_names(KIND_JINGLE)
                  if hasattr(p, "sound_state_names") else [])
    _snd_triggers = p.sound_trigger_names() if hasattr(p, "sound_trigger_names") else []
    # Le rang d'un état est celui qu'il occupe DANS SA boîte — c'est ce que les
    # tables C indexent.
    _trigger_index = {n: i for i, n in enumerate(_snd_triggers)}
    _snd_index: dict = {}
    _jgl_index: dict = {}
    for _store, _index in ((getattr(p, "sound_boxes", []), _snd_index),
                           (getattr(p, "jingle_boxes", []), _jgl_index)):
        for _b in sorted(_store, key=lambda b: b.name):
            for _i, _st in enumerate(_b.states):
                _index.setdefault(_st.name, _i)
    # Les prefabs sont poolés au niveau PROJET : `actor.spawn("X")` vise la
    # liste entière, pas ce que la scène courante contient.
    _prefab_names = [pf.name for pf in prefabs]
    # Tables de données : {nom: (colonnes, nombre de lignes)}. Le checker en
    # tire ses refus (table ou colonne inconnue, index hors bornes, écriture sur
    # une const) et le codegen la taille pour `#data.X`. Une seule lecture du
    # registre pour tous les scripts de la scène.
    _data_tables = {t.name: ([c.name for c in t.columns], len(t.rows))
                    for t in getattr(p, "data_tables", [])}

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

    # Sauvegarde — deux faits du PROJET, les mêmes pour tous les scripts : le
    # nombre d'emplacements déclaré, et s'il y a seulement quelque chose à
    # sauver. Le checker s'en sert pour refuser un emplacement inexistant et
    # signaler un save.write() qui ne sauverait rien.
    _save_slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    _has_persist = any(getattr(g, "persist", False) for g in p.globals)

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

        anim_names = [st.name for st in sprite.states] if sprite and sprite.states else []
        sfx_comp_name, _ = _sfx_component_info(actor)
        _rt_transform = bool(getattr(actor, "affine_transform", False))
        ctx_check = BuildContext(
            actor_name   = actor.name,
            anim_names   = anim_names,
            affine_transform = _rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            const_names  = list(const_names) if const_names else None,
            sfx_component_name = sfx_comp_name,
            text_keys    = text_keys,
            font_names   = font_names,
            palette_names = palette_names,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
        )
        script, ok = _compile_script(sp, ctx_check, emit, sp.name)
        if not ok:
            return False

        parsed_scripts.append((actor, sprite, script, sp))

    # Script de scène — parse
    scene_script_ast  = None
    scene_script_file = None
    scene_script_path = getattr(scene, "script", "")
    if scene_script_path:
        sp = p.asset_abs(scene_script_path)
        if sp and sp.exists() and sp.suffix.lower() == ".lua":
            ctx_check = BuildContext(
                actor_name   = scene.name,
                sfx_names    = sfx_names,
                music_names  = music_names,
                scene_names  = _scene_names,
                camera_names = _camera_names,
                sound_box_state_names   = _snd_names,
                jingle_box_state_names  = _jgl_names,
                music_box_trigger_names = _snd_triggers,
                actor_names  = _actor_names,
            prefab_names = _prefab_names,
                global_names = list(global_names) if global_names else None,
                global_types = {g.name: g.type for g in p.globals},
                const_names  = list(const_names) if const_names else None,
                # Un script de SCÈNE cite textes et polices autant qu'un script
                # d'actor : sans ces deux-là le checker se tait, et une clé
                # inconnue n'échoue qu'au `make`, sur un `TEXT_*` indéfini.
                text_keys    = text_keys,
                font_names   = font_names,
                palette_names = palette_names,
                region_names = region_names,
                image_names  = image_names,
                element_names = element_names,
                image_states = image_states,
                save_slots   = _save_slots,
                has_persistent = _has_persist,
                data_tables  = _data_tables,
            )
            scene_script_ast, ok = _compile_script(sp, ctx_check, emit, sp.name)
            if not ok:
                return False
            scene_script_file = sp

    # Génération C — actors de scène
    for actor, sprite, script, sp in parsed_scripts:
        s    = c_sym(actor.name)
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
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            palette_names = palette_names,
            region_names  = region_names,
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
        )
        c_code, gen_warnings, _ = lua_generate(script, ctx)
        for w in gen_warnings:
            emit("log_line", f"[warn] {sp.name}: {w}")
        out = p.src_dir / f"actor_{s}.c"
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua->c] {sp.name} -> {out.name}")

    # Génération C — prefabs poolés (compilés une seule fois grâce à compiled_prefabs)
    # `prefabs` est la liste du PROJET : la première scène les compile tous, les
    # suivantes n'en recompilent aucun. Le total ci-dessous est donc bien celui
    # du projet, et il n'est dit que là où il a été calculé.
    pool_state_total = 0
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) <= 0:
            continue
        pf_sym = c_sym(pf.name)
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
        pf_spr  = next((c for c in pf.components if hasattr(c, "states")), None)
        pf_anim = [st.name for st in pf_spr.states] if pf_spr and hasattr(pf_spr, "states") else []
        pf_sfx_comp_name, pf_sfx_autoplay = _sfx_component_info(pf)
        _pf_rt_transform = bool(getattr(pf, "affine_transform", False))
        ctx_check = BuildContext(
            actor_name   = pf.name,
            anim_names   = pf_anim,
            affine_transform = _pf_rt_transform,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            actor_names  = _actor_names,
            prefab_names = _prefab_names,
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            const_names  = list(const_names) if const_names else None,
            sfx_component_name = pf_sfx_comp_name,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
        )
        pf_ast, ok = _compile_script(sp_path, ctx_check, emit, f"prefab {pf.name} ({sp_path.name})")
        if not ok:
            return False
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
            pool_size     = pf.max_instances,
            scene_names   = _scene_names,
            sfx_component_name = pf_sfx_comp_name,
            sfx_autoplay  = pf_sfx_autoplay,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            palette_names = palette_names,
            region_names  = region_names,
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
        )
        pf_c, pf_warnings, pf_state_bytes = lua_generate(pf_ast, ctx_pf)
        for w in pf_warnings:
            emit("log_line", f"[warn] prefab {pf.name}: {w}")
        out_pf = p.src_dir / f"actor_{pf_sym}.c"
        out_pf.write_text(pf_c, encoding="utf-8")
        emit("log_line", f"[lua->c] prefab {pf.name} -> {out_pf.name}")
        # Ce que l'état de script de ce prefab occupe en EWRAM. Le chiffre est
        # dit et non plafonné (cf. ROADMAP v0.7.6) : le plafond de huit entiers
        # qu'il remplace était arbitraire, et la ressource ici est arbitrable.
        pool_state_total += pf_state_bytes * pf.max_instances
        if pf_state_bytes:
            emit("log_line",
                 f"[ewram] prefab {pf.name} : état de script {pf_state_bytes} "
                 f"octets × {pf.max_instances} instance(s) = "
                 f"{pf_state_bytes * pf.max_instances} octets")

    if pool_state_total:
        emit("log_line",
             f"[ewram] état de script des prefabs poolés : {pool_state_total} octets")

    # Génération C — script de scène
    if scene_script_ast and scene_script_file:
        scene_s = c_sym(scene.name)
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
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            palette_names = palette_names,
            region_names  = region_names,
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
        )
        c_code, sc_warnings, _ = lua_generate(scene_script_ast, ctx_sc)
        for w in sc_warnings:
            emit("log_line", f"[warn] {scene_script_file.name}: {w}")
        out_name = f"{scene_s}_scene.c"
        out = p.src_dir / out_name
        out.write_text(c_code, encoding="utf-8")
        emit("log_line", f"[lua->c] {scene_script_file.name} -> {out_name}")

    # Génération C — scripts de CAMÉRA
    #
    # Compilés une fois pour le PROJET et non par scène (`compiled_cameras`,
    # même mécanique que les prefabs poolés) : une caméra est un asset partagé,
    # et n'importe quelle scène peut activer n'importe laquelle par script.
    # Mêmes points d'entrée qu'un script de scène — `hook_kind="camera"` ne
    # change que le mot dans le symbole C émis.
    for cam in getattr(p, "cameras", []):
        if not getattr(cam, "script", ""):
            continue
        cam_sym = f"camera_{c_sym(cam.name)}"
        if compiled_cameras is not None:
            if cam_sym in compiled_cameras:
                continue
            compiled_cameras.add(cam_sym)
        sp = p.asset_abs(cam.script)
        if not sp or not sp.exists() or sp.suffix.lower() != ".lua":
            continue
        ctx_check = BuildContext(
            actor_name   = cam.name,
            sfx_names    = sfx_names,
            music_names  = music_names,
            scene_names  = _scene_names,
            camera_names = _camera_names,
            sound_box_state_names   = _snd_names,
            jingle_box_state_names  = _jgl_names,
            music_box_trigger_names = _snd_triggers,
            # Aucun `actor_names` : une caméra est réutilisable entre scènes et
            # les noms d'acteurs y sont locaux. Citer un acteur depuis une
            # caméra marcherait dans une scène et pas dans la suivante — le
            # checker doit le dire, pas le laisser passer.
            global_names = list(global_names) if global_names else None,
            global_types = {g.name: g.type for g in p.globals},
            const_names  = list(const_names) if const_names else None,
            text_keys    = text_keys,
            font_names   = font_names,
            palette_names = palette_names,
            region_names = region_names,
            image_names  = image_names,
            element_names = element_names,
            image_states = image_states,
            save_slots   = _save_slots,
            has_persistent = _has_persist,
            data_tables  = _data_tables,
        )
        cam_ast, ok = _compile_script(sp, ctx_check, emit, f"camera {cam.name} ({sp.name})")
        if not ok:
            return False
        ctx_cam = CodegenContext(
            actor_name    = cam.name,
            actor_sym     = cam_sym,
            anim_names    = [],
            sfx_names     = sfx_names,
            music_names   = music_names,
            global_names  = set(global_names),
            const_names   = set(const_names),
            all_actor_syms= all_syms,
            is_scene      = True,
            hook_kind     = "camera",
            scene_names   = _scene_names,
            sfx_volumes   = sfx_volumes,
            music_info    = music_info,
            sound_box_states   = _snd_index,
            jingle_box_states  = _jgl_index,
            music_box_triggers = _trigger_index,
            text_keys     = text_keys,
            font_names    = font_names,
            palette_names = palette_names,
            region_names  = region_names,
            image_names   = image_names,
            element_names = element_names,
            image_states  = image_states,
            save_slots    = _save_slots,
            has_persistent = _has_persist,
            data_tables   = _data_tables,
        )
        cam_c, cam_warnings, _ = lua_generate(cam_ast, ctx_cam)
        for w in cam_warnings:
            emit("log_line", f"[warn] camera {cam.name}: {w}")
        out_cam = p.src_dir / f"{cam_sym}.c"
        out_cam.write_text(cam_c, encoding="utf-8")
        emit("log_line", f"[lua->c] {sp.name} -> {out_cam.name}")

    return True
