"""
runtime_codegen/headers.py — Génération de actor_types.h et actor_api.h.

Entrées  : Project, liste (Actor, SpriteAsset), présence audio
Sorties  : fichiers écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from core.project import Project, Actor, SpriteAsset, CollisionBoxComponent, AnimState
from codegen.build_utils import sym as _sym


RUNTIME_DIR = Path(__file__).resolve().parents[3] / "runtime"


def generate_actor_types(
    p: Project,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,      # iterable de Prefab
) -> None:
    """Écrit actor_types_static.h (copie) et actor_types.h (généré)."""
    _types_static = RUNTIME_DIR / "include" / "actor_types_static.h"
    if _types_static.exists():
        shutil.copy2(_types_static, p.src_dir / "actor_types_static.h")

    h = [
        "/* actor_types.h — struct Actor partagée entre main.c et les scripts */",
        "/* Généré par GBA Editor */",
        "#ifndef ACTOR_TYPES_H",
        "#define ACTOR_TYPES_H",
        "#include <gba_types.h>",
        "",
    ]

    # Tags de boxes de collision
    box_tags: list[str] = []
    for actor, _ in scene_actors:
        for comp in actor.components:
            if isinstance(comp, CollisionBoxComponent) and comp.active:
                tag = comp.tag or "body"
                if tag not in box_tags:
                    box_tags.append(tag)
    if not box_tags:
        box_tags = ["body"]

    for ti, tag in enumerate(box_tags):
        h.append(f"#define BOXTAG_{_sym(tag).upper()} {ti}")
    h.append("")
    h.append('#include "actor_types_static.h"')
    h.append("")

    # TAG_* pour les actors de scène
    for i, (actor, _) in enumerate(scene_actors):
        h.append(f"#define TAG_{_sym(actor.name).upper()} {i}")

    # TAG_* pour les prefabs poolés (offset après les actors de scène)
    pool_offset = len(scene_actors)
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) > 0:
            pf_s = _sym(pf.name)
            h.append(f"#define TAG_{pf_s.upper()} {pool_offset}  /* prefab pool début */")
            pool_offset += pf.max_instances

    h += ["", "#endif /* ACTOR_TYPES_H */", ""]
    (p.src_dir / "actor_types.h").write_text("\n".join(h), encoding="utf-8")


def generate_actor_api(
    p: Project,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    has_sound: bool,
    all_scenes=None,   # liste de Scene — pour SCENE_IDX_* et scene_switch()
    max_actors: int | None = None,  # taille réelle du tableau g_actors
) -> None:
    """Écrit actor_api_static.h (copie) et actor_api.h (généré)."""
    for static_h in ("actor_api_static.h", "gba_engine.h", "gba_font.h", "runtime.h"):
        src_h = RUNTIME_DIR / "include" / static_h
        if src_h.exists():
            shutil.copy2(src_h, p.src_dir / static_h)
    _api_static = RUNTIME_DIR / "include" / "actor_api_static.h"

    prefab_slots = sum(pf.max_instances for pf in prefabs if getattr(pf, "max_instances", 0) > 0)
    total_actors = max_actors if max_actors is not None else (len(scene_actors) + prefab_slots)

    a = [
        "/* actor_api.h — API runtime pour les scripts acteur */",
        "/* Généré par GBA Editor */",
        "#ifndef ACTOR_API_H",
        "#define ACTOR_API_H",
        '#include "actor_types.h"',
        "",
        f"#define G_ACTOR_COUNT {total_actors}",
        "",
        '#include "actor_api_static.h"',
        "",
    ]

    if has_sound:
        a += [
            "#include <maxmod.h>",
            "/* API audio — miroir direct des fonctions maxmod (mm_sound_effect, mmEffectEx,",
            "   mmEffectVolume/Panning/Cancel, mmStart/Pause/Resume/Stop/Active, mmSet*Volume). */",
            "static inline mm_sfxhand sfx_play(int id, int volume){",
            "    mm_sound_effect ex;",
            "    ex.id = (mm_word)id; ex.rate = (mm_hword)1024; ex.handle = 0;",
            "    ex.volume = (mm_byte)volume; ex.panning = (mm_byte)128;",
            "    return mmEffectEx(&ex);",
            "}",
            "static inline void sfx_set_volume(mm_sfxhand h, int volume){mmEffectVolume(h,(mm_word)volume);}",
            "static inline void sfx_set_panning(mm_sfxhand h, int panning){mmEffectPanning(h,(mm_byte)panning);}",
            "static inline void sfx_stop(mm_sfxhand h){mmEffectCancel(h);}",
            "static inline void sfx_set_effects_volume(int volume){mmSetEffectsVolume((mm_word)volume);}",
            "static inline void music_play(int id, int loop, int volume){",
            "    mmStart((mm_word)id, loop ? MM_PLAY_LOOP : MM_PLAY_ONCE);",
            "    mmSetModuleVolume((mm_word)volume);",
            "}",
            "static inline void music_stop(void){mmStop();}",
            "static inline void music_pause(void){mmPause();}",
            "static inline void music_resume(void){mmResume();}",
            "static inline int  music_is_playing(void){return mmActive();}",
            "static inline void music_set_volume(int volume){mmSetModuleVolume((mm_word)volume);}",
        ]
    else:
        a += [
            "static inline int  sfx_play(int id, int volume){(void)id;(void)volume;return 0;}",
            "static inline void sfx_set_volume(int h, int volume){(void)h;(void)volume;}",
            "static inline void sfx_set_panning(int h, int panning){(void)h;(void)panning;}",
            "static inline void sfx_stop(int h){(void)h;}",
            "static inline void sfx_set_effects_volume(int volume){(void)volume;}",
            "static inline void music_play(int id, int loop, int volume){(void)id;(void)loop;(void)volume;}",
            "static inline void music_stop(void){}",
            "static inline void music_pause(void){}",
            "static inline void music_resume(void){}",
            "static inline int  music_is_playing(void){return 0;}",
            "static inline void music_set_volume(int volume){(void)volume;}",
        ]

    spawnable = [pf for pf in prefabs if getattr(pf, "max_instances", 0) > 0]
    if spawnable:
        a.append("")
        a.append("/* spawn_X() — défini dans main.c, visible par tous les scripts */")
        for pf in spawnable:
            a.append(f"extern int spawn_{_sym(pf.name)}(int x, int y);")

    # Constantes ANIM_* par SpriteAsset — résolues à la compile par le transpileur
    done_sprites: set[str] = set()
    for _, sprite in scene_actors:
        if sprite and sprite.states and sprite.name not in done_sprites:
            done_sprites.add(sprite.name)
            a.append("")
            a.append(f"/* Animations : {sprite.name} */")
            for i, st in enumerate(sprite.states):
                a.append(f"#define ANIM_{_sym(st.name).upper()} {i}")

    if all_scenes:
        a.append("")
        a.append("/* Indices de scènes — utilisés par scene.switch() */")
        for i, sc in enumerate(all_scenes):
            a.append(f"#define SCENE_IDX_{_sym(sc.name).upper()} {i}")
        a += [
            "",
            "extern int g_next_scene;",
            "static inline void scene_switch(int idx){ g_next_scene = idx; }",
        ]

    a += ["", "#endif /* ACTOR_API_H */", ""]
    (p.src_dir / "actor_api.h").write_text("\n".join(a), encoding="utf-8")
