"""
runtime_codegen/main_gen.py — Génération de main.c.

Entrées  : Project, Scene, bg_pairs, scene_actors, sound_assets, prefab_sprites
Sortie   : p.src_dir/main.c
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Optional

from core.project import (
    Project, Scene, BackgroundLayer,
    Actor, SpriteAsset, CollisionBoxComponent, SpriteComponent,
)
from codegen.asset_pipeline import count_frames
from codegen.build_utils import sym as _sym


RUNTIME_DIR = Path(__file__).resolve().parents[3] / "runtime"

_EV_SIGS = {
    "on_start":           "void {s}_on_start(Actor* self);",
    "on_update":          "void {s}_on_update(Actor* self);",
    "on_late_update":     "void {s}_on_late_update(Actor* self);",
    "on_collide":         "void {s}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box);",
    "on_collision_enter": "void {s}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box);",
    "on_collision_exit":  "void {s}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box);",
    "on_button_a":        "void {s}_on_button_a(Actor* self);",
    "on_button_b":        "void {s}_on_button_b(Actor* self);",
    "on_button_l":        "void {s}_on_button_l(Actor* self);",
    "on_button_r":        "void {s}_on_button_r(Actor* self);",
    "on_button_start":    "void {s}_on_button_start(Actor* self);",
    "on_button_select":   "void {s}_on_button_select(Actor* self);",
    "on_button_up":       "void {s}_on_button_up(Actor* self);",
    "on_button_down":     "void {s}_on_button_down(Actor* self);",
    "on_button_left":     "void {s}_on_button_left(Actor* self);",
    "on_button_right":    "void {s}_on_button_right(Actor* self);",
    "on_tile_collide":    "void {s}_on_tile_collide(Actor* self, int normal_x, int normal_y);",
    "on_receive":         "void {s}_on_receive(Actor* self, int event_id, int value);",
}

_BTN_MAP = [
    ("BTN_A",      "on_button_a"),
    ("BTN_B",      "on_button_b"),
    ("BTN_L",      "on_button_l"),
    ("BTN_R",      "on_button_r"),
    ("BTN_START",  "on_button_start"),
    ("BTN_SELECT", "on_button_select"),
    ("BTN_UP",     "on_button_up"),
    ("BTN_DOWN",   "on_button_down"),
    ("BTN_LEFT",   "on_button_left"),
    ("BTN_RIGHT",  "on_button_right"),
]


def _actor_script(actor: Actor) -> Optional[str]:
    comp = actor.get_component("script")
    return comp.script if comp and comp.active else None


def _bg_info(p: Project, bg_pairs: list[BackgroundLayer]) -> list[dict]:
    sbb_map = {0: 8, 1: 12, 2: 20, 3: 28}
    result  = []
    for layer in bg_pairs:
        if not layer.image:
            continue
        ap = p.background_images_dir / layer.image
        try:
            from PIL import Image
            with Image.open(ap) as img:
                w, h = img.size
        except Exception:
            w, h = 240, 160
        tw = min(max(math.ceil(w / 8), 1), 64)
        th = min(max(math.ceil(h / 8), 1), 64)
        ms = (1 if tw > 32 else 0) | (2 if th > 32 else 0)
        stem = ap.stem
        result.append({
            "bg": layer.bg_slot, "stem": stem, "sym": _sym(stem),
            "tw": tw, "th": th, "sbb": sbb_map.get(layer.bg_slot, 8),
            "map_size": ms, "speed": int(layer.scroll_speed * 256),
        })
    return result


def _pool_info(prefabs, pool_start: int) -> list[dict]:
    info, offset = [], pool_start
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) > 0:
            s = _sym(pf.name)
            info.append({"prefab": pf, "sym": s, "start": offset, "size": pf.max_instances})
            offset += pf.max_instances
    return info


# ─── sections du main.c ───────────────────────────────────────────────────────

def _section_includes(
    scene: Scene,
    bg_info: list[dict],
    scene_actors: list,
    prefab_sprites: list,
    has_sound: bool,
    soundbank_h: Path,
) -> list[str]:
    L = [
        f"/* main.c - scene: {scene.name} - genere par GBA Editor */",
        "#define GBA_ENGINE_IMPL",
        "#include <gba_interrupt.h>",
        "#include <gba_systemcalls.h>",
        "#include <gba_input.h>",
        '#include "gba_engine.h"',
    ]
    if has_sound and soundbank_h.exists():
        L += ["#include <maxmod.h>", '#include "soundbank.h"']
    L += ['#include "actor_api.h"', '#include "globals.h"']
    if bg_info:
        L.append('#include "tileset.h"')
    done: set[str] = set()
    for _, sprite in (scene_actors + prefab_sprites):
        if sprite and sprite.asset and sprite.name not in done:
            L.append(f'#include "sprite_{_sym(sprite.name)}.h"')
            done.add(sprite.name)
    return L


def _section_externs(
    scene: Scene,
    lua_actors: list,
) -> list[str]:
    L: list[str] = []
    if getattr(scene, "script", ""):
        L += [
            "", "/* Script de scène */",
            "void scene_on_start(void);",
            "void scene_on_update(void);",
            "void scene_on_late_update(void);",
        ]
    if lua_actors:
        L += ["", "/* Handlers générés depuis les scripts Lua */"]
        for _, actor, _ in lua_actors:
            s = _sym(actor.name)
            L.append(f"/* {actor.name} */")
            for sig in _EV_SIGS.values():
                L.append(sig.format(s=s))
    return L


def _section_cmap(scene: Scene) -> list[str]:
    cmap = scene.collision_map
    if not cmap:
        scene.ensure_collision_map()
        cmap = scene.collision_map
    rows, cols = len(cmap), len(cmap[0]) if cmap else 1
    L = [
        f"#define CMAP_W {cols}", f"#define CMAP_H {rows}",
        "#define TILE_SIZE 8",
        f"static const u8 g_cmap[{rows}][{cols}]={{",
    ]
    for row in cmap:
        L.append("    {" + ",".join(str(v) for v in row) + "},")
    L += [
        "};",
        "int tile_solid_at(int px,int py){",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=CMAP_W||ty>=CMAP_H) return 1;",
        "    return g_cmap[ty][tx]!=0;",
        "}",
        "int tile_get(int px,int py){",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=CMAP_W||ty>=CMAP_H) return 0;",
        "    return (int)g_cmap[ty][tx];",
        "}",
        # resolve_actor_tiles — résolution Y→X
        "typedef void (*TileCollideCb)(Actor*,int,int);",
        "static void __attribute__((unused)) resolve_actor_tiles(Actor*a, TileCollideCb cb){",
        "    for(int i=0;i<a->box_count;i++){",
        "        CollisionBox*b=&a->boxes[i];",
        "        if(!b->solid) continue;",
        "        if(a->vy!=0){",
        "            int left =a->x+(int)b->x; int right=left+(int)b->w-1;",
        "            int top  =a->y+(int)b->y; int bot  =top +(int)b->h-1;",
        "            if(a->vy>0){",
        "                int hit=0;",
        "                for(int px=left;px<=right&&!hit;px+=TILE_SIZE) hit=tile_solid_at(px,bot);",
        "                if(!hit) hit=tile_solid_at(right,bot);",
        "                if(hit){a->y=(bot/TILE_SIZE)*TILE_SIZE-(int)b->y-(int)b->h;",
        "                    if(cb)cb(a,0,1);else a->vy=0;}",
        "            }else{",
        "                int hit=0;",
        "                for(int px=left;px<=right&&!hit;px+=TILE_SIZE) hit=tile_solid_at(px,top);",
        "                if(!hit) hit=tile_solid_at(right,top);",
        "                if(hit){a->y=(top/TILE_SIZE+1)*TILE_SIZE-(int)b->y;",
        "                    if(cb)cb(a,0,-1);else a->vy=0;}",
        "            }",
        "        }",
        "        if(a->vx!=0){",
        "            int left =a->x+(int)b->x; int right=left+(int)b->w-1;",
        "            int top  =a->y+(int)b->y; int bot  =top +(int)b->h-1;",
        "            if(a->vx>0){",
        "                int hit=0;",
        "                for(int px=top;px<=bot&&!hit;px+=TILE_SIZE) hit=tile_solid_at(right,px);",
        "                if(!hit) hit=tile_solid_at(right,bot);",
        "                if(hit){a->x=(right/TILE_SIZE)*TILE_SIZE-(int)b->x-(int)b->w;",
        "                    if(cb)cb(a,1,0);else a->vx=0;}",
        "            }else{",
        "                int hit=0;",
        "                for(int px=top;px<=bot&&!hit;px+=TILE_SIZE) hit=tile_solid_at(left,px);",
        "                if(!hit) hit=tile_solid_at(left,bot);",
        "                if(hit){a->x=(left/TILE_SIZE+1)*TILE_SIZE-(int)b->x;",
        "                    if(cb)cb(a,-1,0);else a->vx=0;}",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]
    return L


def _section_spawn(pool_info: list[dict],
                   actor_defined_events: dict[str, set[str]] | None = None) -> list[str]:
    if not pool_info:
        return []

    def _def(sym, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    L = ["/* ── Spawn helpers (prefabs poolés) ────────────────────── */"]
    for pi in pool_info:
        s, start, size, pf = pi["sym"], pi["start"], pi["size"], pi["prefab"]
        pal = getattr(pf, "pal_bank", 0)
        boxes = [c for c in pf.components if isinstance(c, CollisionBoxComponent) and c.active][:4]

        # pool_init est toujours généré par le transpileur, extern inconditionnel
        L.append(f"extern void {s}_pool_init(Actor* self);")
        for ev, sig in [
            ("on_start",           f"extern void {s}_on_start(Actor* self);"),
            ("on_update",          f"extern void {s}_on_update(Actor* self);"),
            ("on_late_update",     f"extern void {s}_on_late_update(Actor* self);"),
            ("on_collide",         f"extern void {s}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_enter", f"extern void {s}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_collision_exit",  f"extern void {s}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box);"),
            ("on_tile_collide",    f"extern void {s}_on_tile_collide(Actor* self, int normal_x, int normal_y);"),
        ]:
            if _def(s, ev):
                L.append(sig)

        L += [
            f"int spawn_{s}(int x, int y) {{",
            f"    for(int _i={start}; _i<{start+size}; _i++) {{",
            f"        if(!g_actors[_i].active) {{",
            f"            g_actors[_i] = (Actor){{0}};",
            f"            g_actors[_i].x = x; g_actors[_i].y = y;",
            f"            g_actors[_i].active   = 1; g_actors[_i].visible = 1;",
            f"            g_actors[_i].pal_bank = {pal};",
            f"            g_actors[_i].tag      = TAG_{s.upper()};",
            f"            g_actors[_i].box_count = {len(boxes)};",
        ]
        for bi, cb in enumerate(boxes):
            tag_s = "BOXTAG_" + _sym(cb.tag or "body").upper()
            L += [
                f"            g_actors[_i].boxes[{bi}].x=(s8){cb.x}; g_actors[_i].boxes[{bi}].y=(s8){cb.y};",
                f"            g_actors[_i].boxes[{bi}].w=(u8){cb.w};  g_actors[_i].boxes[{bi}].h=(u8){cb.h};",
                f"            g_actors[_i].boxes[{bi}].solid={1 if cb.solid else 0}; g_actors[_i].boxes[{bi}].tag={tag_s};",
            ]
        L.append(f"            {s}_pool_init(&g_actors[_i]);")
        if _def(s, "on_start"):
            L.append(f"            {s}_on_start(&g_actors[_i]);")
        L += [
            f"            return _i;",
            f"        }}",
            f"    }}",
            f"    return -1;",
            f"}}",
            "",
        ]
    return L


# ─── helpers multi-scène ──────────────────────────────────────────────────────

def _sprite_offsets_for(p: Project, sprites: list) -> tuple[dict, dict]:
    """Calcule tile_offset et nframes pour une liste (actor, sprite), sans doublons."""
    offsets, nframes = {}, {}
    tile_offset = 0
    for _, sprite in sprites:
        if not sprite or not sprite.asset or sprite.name in offsets:
            continue
        nf = count_frames(p, sprite)
        offsets[sprite.name] = tile_offset
        nframes[sprite.name] = nf
        tile_offset += sprite.tiles_per_frame * nf
    return offsets, nframes


def _gen_tile_helpers() -> list[str]:
    """Fonctions tile_solid_at/tile_get avec dispatch via pointeur (multi-scène)."""
    return [
        "static const u8 *g_active_cmap = NULL;",
        "static int g_cmap_w = 0, g_cmap_h = 0;",
        "#define TILE_SIZE 8",
        "int tile_solid_at(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 1;",
        "    return g_active_cmap[ty*g_cmap_w+tx]!=0;",
        "}",
        "int tile_get(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 0;",
        "    return (int)g_active_cmap[ty*g_cmap_w+tx];",
        "}",
        "typedef void (*TileCollideCb)(Actor*,int,int);",
        "static void __attribute__((unused)) resolve_actor_tiles(Actor*a, TileCollideCb cb){",
        "    for(int i=0;i<a->box_count;i++){",
        "        CollisionBox*b=&a->boxes[i];",
        "        if(!b->solid) continue;",
        "        if(a->vy!=0){",
        "            int left =a->x+(int)b->x; int right=left+(int)b->w-1;",
        "            int top  =a->y+(int)b->y; int bot  =top +(int)b->h-1;",
        "            if(a->vy>0){",
        "                int hit=0;",
        "                for(int px=left;px<=right&&!hit;px+=TILE_SIZE) hit=tile_solid_at(px,bot);",
        "                if(!hit) hit=tile_solid_at(right,bot);",
        "                if(hit){a->y=(bot/TILE_SIZE)*TILE_SIZE-(int)b->y-(int)b->h;",
        "                    if(cb)cb(a,0,1);else a->vy=0;}",
        "            }else{",
        "                int hit=0;",
        "                for(int px=left;px<=right&&!hit;px+=TILE_SIZE) hit=tile_solid_at(px,top);",
        "                if(!hit) hit=tile_solid_at(right,top);",
        "                if(hit){a->y=(top/TILE_SIZE+1)*TILE_SIZE-(int)b->y;",
        "                    if(cb)cb(a,0,-1);else a->vy=0;}",
        "            }",
        "        }",
        "        if(a->vx!=0){",
        "            int left =a->x+(int)b->x; int right=left+(int)b->w-1;",
        "            int top  =a->y+(int)b->y; int bot  =top +(int)b->h-1;",
        "            if(a->vx>0){",
        "                int hit=0;",
        "                for(int px=top;px<=bot&&!hit;px+=TILE_SIZE) hit=tile_solid_at(right,px);",
        "                if(!hit) hit=tile_solid_at(right,bot);",
        "                if(hit){a->x=(right/TILE_SIZE)*TILE_SIZE-(int)b->x-(int)b->w;",
        "                    if(cb)cb(a,1,0);else a->vx=0;}",
        "            }else{",
        "                int hit=0;",
        "                for(int px=top;px<=bot&&!hit;px+=TILE_SIZE) hit=tile_solid_at(left,px);",
        "                if(!hit) hit=tile_solid_at(left,bot);",
        "                if(hit){a->x=(left/TILE_SIZE+1)*TILE_SIZE-(int)b->x;",
        "                    if(cb)cb(a,-1,0);else a->vx=0;}",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]


def _gen_scene_init(
    p: Project,
    scene: Scene,
    actor_offset: int,
    bgi: list[dict],
    scene_actors: list,
    lua_idx: set,
    pi: list[dict],
    sprite_offsets: dict,
    dispcnt: int,
    has_sound: bool,
    sound_assets: dict | None,
    actor_defined_events: dict[str, set[str]] | None = None,
) -> list[str]:
    """Génère void scene_init_{sym}(void) { ... }"""
    sym = _sym(scene.name)
    L = [f"static void scene_init_{sym}(void) {{"]
    L.append("    for(int _i=0; _i<G_ACTOR_COUNT; _i++) g_actors[_i]=(Actor){0};")
    L.append("    oam_hide_all();")
    L.append("    bg_maps_clear();")
    # Cmap dispatch
    if scene.collision_map and any(v != 0 for row in scene.collision_map for v in row):
        L.append(f"    g_active_cmap = g_cmap_{sym};")
        L.append(f"    g_cmap_w = CMAP_W_{sym.upper()};")
        L.append(f"    g_cmap_h = CMAP_H_{sym.upper()};")
    else:
        L.append("    g_active_cmap = NULL; g_cmap_w = 0; g_cmap_h = 0;")
    # BG layers
    ts_sym = f"{sym}_tileset"  # préfixe grit : ex. PONG_tileset
    if bgi:
        L.append(f"    copy16(TILE_RAM(0), {ts_sym}Tiles, {ts_sym}TilesLen);")
        for bi in bgi:
            ms = bi["map_size"]
            gcols = 64 if (ms & 1) else 32
            grows = 64 if (ms & 2) else 32
            L.append(f"    load_map(MAP_RAM({bi['sbb']}), {bi['sym']}Map, {bi['tw']}, {bi['th']}, {gcols}, {grows});")
        for bi in bgi:
            bg = bi["bg"]; sbb = bi["sbb"]; pri = 3 - bg; ms = bi["map_size"]
            val = (pri & 3) | (sbb & 0x1F) << 8 | ms << 14
            L.append(f"    *((vu16*)(0x04000008+{bg}*2))=0x{val:04X};")
    # Sprites VRAM
    all_sprites = scene_actors + (p._prefab_sprites_cache if hasattr(p, "_prefab_sprites_cache") else [])
    done_vram: set[str] = set()
    for _, sprite in all_sprites:
        if not sprite or not sprite.asset or sprite.name in done_vram:
            continue
        done_vram.add(sprite.name)
        bt = sprite_offsets.get(sprite.name, 0)
        ss = f"sprite_{_sym(sprite.name)}"
        L.append(f"    copy16(OBJ_VRAM+{bt}*16, {ss}Tiles, {ss}TilesLen);")
    # Palettes OBJ
    done_pal: set[int] = set()
    for actor, sprite in scene_actors:
        if sprite and sprite.asset:
            pal = getattr(actor, "pal_bank", 0)
            if pal not in done_pal:
                done_pal.add(pal)
                ss = f"sprite_{_sym(sprite.name)}"
                L.append(f"    copy16(PAL_OBJ_RAM+{pal}*16, {ss}Pal, {ss}PalLen);")
    # Palettes BG
    if bgi:
        L.append(f"    copy16(PAL_BG_RAM, {ts_sym}Pal, {ts_sym}PalLen);")
    # TTE
    text_bg = getattr(scene, "text_bg", -1)
    if text_bg in {0, 1, 2, 3}:
        L.append(f"    tte_init_se({text_bg}, BG_CBB(3)|BG_SBB(31), SE_PALBANK(15), 0x7FFF, 0, &fwf_default, NULL);")
    # DISPCNT
    L.append(f"    REG_DISPCNT = 0x{dispcnt:04X};")
    # Init actors
    for j, (actor, _) in enumerate(scene_actors):
        idx = actor_offset + j
        s = _sym(actor.name)
        boxes = [c for c in actor.components if isinstance(c, CollisionBoxComponent) and c.active][:4]
        L += [
            f"    g_actors[{idx}].x       = {actor.x};",
            f"    g_actors[{idx}].y       = {actor.y};",
            f"    g_actors[{idx}].active  = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].visible = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].flip_h  = {1 if getattr(actor,'flip_h',False) else 0};",
            f"    g_actors[{idx}].flip_v  = {1 if getattr(actor,'flip_v',False) else 0};",
            f"    g_actors[{idx}].pal_bank= {getattr(actor,'pal_bank',0)};",
            f"    g_actors[{idx}].tag     = TAG_{s.upper()};",
            f"    g_actors[{idx}].box_count = {len(boxes)};",
        ]
        for bi2, cb in enumerate(boxes):
            tag_s = "BOXTAG_" + _sym(cb.tag or "body").upper()
            L += [
                f"    g_actors[{idx}].boxes[{bi2}].x=(s8){cb.x}; g_actors[{idx}].boxes[{bi2}].y=(s8){cb.y};",
                f"    g_actors[{idx}].boxes[{bi2}].w=(u8){cb.w};  g_actors[{idx}].boxes[{bi2}].h=(u8){cb.h};",
                f"    g_actors[{idx}].boxes[{bi2}].solid={1 if cb.solid else 0}; g_actors[{idx}].boxes[{bi2}].tag={tag_s};",
            ]
    # Pool init
    for p2 in pi:
        for slot in range(p2["start"], p2["start"] + p2["size"]):
            L.append(f"    g_actors[{slot}].tag = TAG_{p2['sym'].upper()};")
            L.append(f"    g_actors[{slot}].active = 0;")
    # on_start actors (seulement si défini dans le script Lua)
    def _def_init(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    for j in sorted(lua_idx):
        actor, _ = scene_actors[j - actor_offset]
        s = _sym(actor.name)
        if _def_init(s, "on_start"):
            L.append(f"    {s}_on_start(&g_actors[{j}]);")
    # on_start scene
    if getattr(scene, "script", ""):
        L.append(f"    {sym}_scene_on_start();")
    L.append("}")
    L.append("")
    return L


def _gen_scene_tick(
    p: Project,
    scene: Scene,
    actor_offset: int,
    bgi: list[dict],
    scene_actors: list,
    lua_idx: set,
    pi: list[dict],
    sprite_offsets: dict,
    sprite_nframes: dict,
    col_pairs: list,
    actor_defined_events: dict[str, set[str]] | None = None,
) -> list[str]:
    """Génère void scene_tick_{sym}(void) { ... }"""
    sym = _sym(scene.name)
    L = [f"static void scene_tick_{sym}(void) {{"]

    def _def(s, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(s, set())

    # on_update scène
    if getattr(scene, "script", ""):
        L += [f"    {sym}_scene_on_update();"]

    # on_update actors
    if lua_idx:
        for j in sorted(lua_idx):
            actor, _ = scene_actors[j - actor_offset]
            s = _sym(actor.name)
            if _def(s, "on_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_update(&g_actors[{j}]);")

    # on_update prefabs poolés
    for p2 in pi:
        if _def(p2["sym"], "on_update"):
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi++)")
            L.append(f"        if(g_actors[_pi].active) {p2['sym']}_on_update(&g_actors[_pi]);")

    # Tile resolution actors scène (seulement si on_tile_collide défini)
    for j in sorted(lua_idx):
        actor, _ = scene_actors[j - actor_offset]
        s = _sym(actor.name)
        if _def(s, "on_tile_collide"):
            L.append(f"    if(g_actors[{j}].active) resolve_actor_tiles(&g_actors[{j}],{s}_on_tile_collide);")

    # Tile resolution prefabs
    for p2 in pi:
        if _def(p2["sym"], "on_tile_collide"):
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi++)")
            L.append(f"        if(g_actors[_pi].active) resolve_actor_tiles(&g_actors[_pi], {p2['sym']}_on_tile_collide);")

    # Pool→scene collisions
    col_scene = [
        (actor_offset + j, scene_actors[j][0])
        for j in range(len(scene_actors))
        if any(hasattr(c, "w") for c in scene_actors[j][0].components)
    ]
    if pi and col_scene:
        for p2 in pi:
            s, start, size = p2["sym"], p2["start"], p2["size"]
            np = len(col_scene)
            L += [
                f"    {{",
                f"        static u8 _pcol_{s}[{size}][{np}]={{{{0}}}};",
                f"        for(int _pi={start}; _pi<{start+size}; _pi++){{",
                f"            if(!g_actors[_pi].active) continue;",
                f"            int _sl=_pi-{start};",
            ]
            has_col = (_def(s, "on_collision_enter") or _def(s, "on_collide")
                       or _def(s, "on_collision_exit"))
            for ci, (sidx, sactor) in enumerate(col_scene):
                if not has_col:
                    continue
                L += [
                    f"            {{ u8 _bx=0,_bo=0;",
                    f"              u8 _c=(g_actors[{sidx}].active&&actors_overlap_boxes(&g_actors[_pi],&g_actors[{sidx}],&_bx,&_bo))?1:0;",
                    f"              u8 _p=_pcol_{s}[_sl][{ci}];",
                ]
                if _def(s, "on_collision_enter"):
                    L.append(f"              if(_c&&!_p) {s}_on_collision_enter(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                if _def(s, "on_collide"):
                    L.append(f"              if(_c&&_p)  {s}_on_collide(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                if _def(s, "on_collision_exit"):
                    L.append(f"              if(!_c&&_p) {s}_on_collision_exit(&g_actors[_pi],&g_actors[{sidx}],_bx,_bo);")
                L.append(f"              _pcol_{s}[_sl][{ci}]=_c; }}")
            L += [f"        }}", f"    }}"]

    # AABB collisions scène
    if col_pairs:
        L.append(f"    static u8 _col_prev[{len(col_pairs)}]={{0}};")
        for pair_idx, (i, j) in enumerate(col_pairs):
            i_lua = i in lua_idx; j_lua = j in lua_idx
            si = _sym(scene_actors[i - actor_offset][0].name)
            sj = _sym(scene_actors[j - actor_offset][0].name)
            L += [
                f"    {{ u8 _bx_i=0,_bx_j=0;",
                f"        u8 _cur=(g_actors[{i}].active&&g_actors[{j}].active&&"
                f"actors_overlap_boxes(&g_actors[{i}],&g_actors[{j}],&_bx_i,&_bx_j))?1:0;",
                f"        if(_cur&&!_col_prev[{pair_idx}]){{",
            ]
            if i_lua and _def(si, "on_collision_enter"): L.append(f"            {si}_on_collision_enter(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collision_enter"): L.append(f"            {sj}_on_collision_enter(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L.append(f"        }}")
            L.append(f"        if(_cur&&_col_prev[{pair_idx}]){{")
            if i_lua and _def(si, "on_collide"): L.append(f"            {si}_on_collide(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collide"): L.append(f"            {sj}_on_collide(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L.append(f"        }}")
            L.append(f"        if(!_cur&&_col_prev[{pair_idx}]){{")
            if i_lua and _def(si, "on_collision_exit"): L.append(f"            {si}_on_collision_exit(&g_actors[{i}],&g_actors[{j}],_bx_i,_bx_j);")
            if j_lua and _def(sj, "on_collision_exit"): L.append(f"            {sj}_on_collision_exit(&g_actors[{j}],&g_actors[{i}],_bx_j,_bx_i);")
            L += [f"        }}", f"        _col_prev[{pair_idx}]=_cur; }}"]

    # Boutons
    if lua_idx:
        for btn, ev in _BTN_MAP:
            actors_b = [
                (j, _sym(scene_actors[j - actor_offset][0].name))
                for j in sorted(lua_idx)
                if _def(_sym(scene_actors[j - actor_offset][0].name), ev)
            ]
            if actors_b:
                L.append(f"    if(_g_keys_pressed&{btn}){{")
                for j, s in actors_b:
                    L.append(f"        if(g_actors[{j}].active) {s}_{ev}(&g_actors[{j}]);")
                L.append("    }")

    # on_late_update actors
    if lua_idx:
        for j in sorted(lua_idx):
            actor, _ = scene_actors[j - actor_offset]
            s = _sym(actor.name)
            if _def(s, "on_late_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_late_update(&g_actors[{j}]);")

    # on_late_update prefabs
    for p2 in pi:
        if _def(p2["sym"], "on_late_update"):
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi++)")
            L.append(f"        if(g_actors[_pi].active) {p2['sym']}_on_late_update(&g_actors[_pi]);")

    # on_late_update scène
    if getattr(scene, "script", ""):
        L.append(f"    {sym}_scene_on_late_update();")

    # Camera follow
    world_bi = min(bgi, key=lambda b: abs(b["speed"] - 256)) if bgi else None
    if scene.cam_follow and bgi:
        follow_local = next((j for j, (a, _) in enumerate(scene_actors) if a.name == scene.cam_follow), None)
        if follow_local is not None:
            follow_idx = actor_offset + follow_local
            L += [
                f"    cam_x = g_actors[{follow_idx}].x - 120;",
                f"    cam_y = g_actors[{follow_idx}].y - 80;",
            ]
            if scene.scroll_h and world_bi:
                ww = world_bi["tw"] * 8
                L += ["    if(cam_x<0) cam_x=0;", f"    if(cam_x>{ww}-240) cam_x={ww}-240;"]
            if scene.scroll_v and world_bi:
                wh = world_bi["th"] * 8
                L += ["    if(cam_y<0) cam_y=0;", f"    if(cam_y>{wh}-160) cam_y={wh}-160;"]

    # Scroll caméra manuel
    if bgi and not scene.cam_follow:
        if scene.scroll_h:
            L += ["    if(_g_keys_held&KEY_RIGHT) cam_x++;", "    if(_g_keys_held&KEY_LEFT)  cam_x--;"]
        if scene.scroll_v:
            L += ["    if(_g_keys_held&KEY_DOWN)  cam_y++;", "    if(_g_keys_held&KEY_UP)    cam_y--;"]

    # BG scroll offset
    if bgi:
        for bi in bgi:
            L.append(f"    BGOFS({bi['bg']})=(u16)((cam_x*{bi['speed']})>>8);")
            if scene.scroll_v:
                L.append(f"    *((vu16*)(0x04000012+{bi['bg']}*4))=(u16)((cam_y*{bi['speed']})>>8);")

    # Animation
    anim_actors = [(actor_offset + j, a, s2) for j, (a, s2) in enumerate(scene_actors) if s2 and s2.asset and s2.states]
    for idx, actor, sprite in anim_actors:
        nf = sprite_nframes.get(sprite.name, 1)
        spd = sprite.states[0].speed if sprite.states else 8
        L += [
            f"    g_actors[{idx}].timer++;",
            f"    if(g_actors[{idx}].timer>={spd}){{",
            f"        g_actors[{idx}].timer=0;",
            f"        g_actors[{idx}].frame=(g_actors[{idx}].frame+1)%{nf};",
            f"    }}",
        ]

    # OAM actors scène
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        if not actor.visible:
            continue
        if sprite and sprite.asset:
            sh = sprite.oam_shape; sz = sprite.oam_size
            bt = sprite_offsets.get(sprite.name, 0)
            L += [
                f"    if(g_actors[{idx}].active && g_actors[{idx}].visible){{",
                f"        int sx=g_actors[{idx}].x-cam_x; int sy=g_actors[{idx}].y-cam_y;",
                f"        u16 ti=(u16)({bt}+g_actors[{idx}].frame*{sprite.tiles_per_frame});",
                f"        int fh=g_actors[{idx}].flip_h; int fv=g_actors[{idx}].flip_v;",
                f"        shadow_oam[{idx}].attr0=(sy&0xFF)|({sh}<<14);",
                f"        shadow_oam[{idx}].attr1=(sx&0x1FF)|(fh<<12)|(fv<<13)|({sz}<<14);",
                f"        shadow_oam[{idx}].attr2=(ti&0x3FF)|({actor.priority}<<10)|(g_actors[{idx}].pal_bank<<12);",
                f"    }}else{{ shadow_oam[{idx}].attr0=0x0200; }}",
            ]

    # OAM prefab pool
    for p2 in pi:
        pf = p2["prefab"]
        _pf_sc = next((c for c in pf.components if isinstance(c, SpriteComponent) and c.sprite_name), None)
        pf_spr = p.get_sprite(_pf_sc.sprite_name) if _pf_sc else None
        if not pf_spr:
            for slot in range(p2["start"], p2["start"] + p2["size"]):
                L.append(f"    shadow_oam[{slot}].attr0=0x0200;")
            continue
        sh = pf_spr.oam_shape; sz = pf_spr.oam_size
        bt = sprite_offsets.get(pf_spr.name, 0)
        for slot in range(p2["start"], p2["start"] + p2["size"]):
            L += [
                f"    if(g_actors[{slot}].active && g_actors[{slot}].visible){{",
                f"        int sx=g_actors[{slot}].x-cam_x; int sy=g_actors[{slot}].y-cam_y;",
                f"        u16 ti=(u16)({bt}+g_actors[{slot}].frame*{pf_spr.tiles_per_frame});",
                f"        int fh=g_actors[{slot}].flip_h; int fv=g_actors[{slot}].flip_v;",
                f"        shadow_oam[{slot}].attr0=(sy&0xFF)|({sh}<<14);",
                f"        shadow_oam[{slot}].attr1=(sx&0x1FF)|(fh<<12)|(fv<<13)|({sz}<<14);",
                f"        shadow_oam[{slot}].attr2=(ti&0x3FF)|(0<<10)|(g_actors[{slot}].pal_bank<<12);",
                f"    }}else{{ shadow_oam[{slot}].attr0=0x0200; }}",
            ]

    L.append("    oam_update();")
    L.append("}")
    L.append("")
    return L


# ─── point d'entrée ───────────────────────────────────────────────────────────

def generate_main(
    p: Project,
    all_scene_data: list[dict],   # list of {scene, bg_pairs, scene_actors, prefab_sprites}
    sound_assets: dict | None,
    prefab_actor_sprites: list,
    prefabs,
    emit,
    actor_defined_events: dict[str, set[str]] | None = None,
) -> bool:
    """Génère main.c multi-scène et le copie dans p.src_dir/."""
    prefab_actor_sprites = prefab_actor_sprites or []
    has_sound   = bool(sound_assets and (sound_assets.get("sfx") or sound_assets.get("music")))
    soundbank_h = p.build_dir / "soundbank.h"
    all_scenes  = [d["scene"] for d in all_scene_data]
    scene_names = [s.name for s in all_scenes]
    start_scene = (getattr(p.settings, "start_scene", None) or
                   (scene_names[0] if scene_names else ""))
    start_idx   = next((i for i, n in enumerate(scene_names) if n == start_scene), 0)

    # Copier gba_engine.h
    _src = RUNTIME_DIR / "include" / "gba_engine.h"
    if _src.exists():
        shutil.copy2(_src, p.src_dir / "gba_engine.h")

    # ── Calcul des offsets globaux des actors ─────────────────────
    # Chaque scène reçoit une tranche de g_actors[].
    # La pool de prefabs commence après tous les actors de scène.
    total_scene_actors = sum(len(d["scene_actors"]) for d in all_scene_data)
    pi = _pool_info(prefabs, total_scene_actors)
    n_actors = max(total_scene_actors + sum(p2["size"] for p2 in pi), 1)

    # Offsets par scène
    scene_offsets: list[int] = []
    offset = 0
    for d in all_scene_data:
        scene_offsets.append(offset)
        offset += len(d["scene_actors"])

    # ── Sprites : union de toutes les scènes ──────────────────────
    all_sprite_pairs: list = []
    for d in all_scene_data:
        all_sprite_pairs += d["scene_actors"]
    all_sprite_pairs += prefab_actor_sprites

    sprite_offsets, sprite_nframes = _sprite_offsets_for(p, all_sprite_pairs)

    # ── Génération des includes (union de toutes les scènes) ──────
    L: list[str] = []
    seen_incs: set[str] = set()

    def _add_inc(line: str):
        if line not in seen_incs:
            seen_incs.add(line)
            L.append(line)

    _add_inc('#define GBA_ENGINE_IMPL')
    _add_inc('#include "gba_engine.h"')
    _add_inc('#include "actor_api.h"')
    _add_inc('#include "globals.h"')
    if has_sound and soundbank_h.exists():
        _add_inc('#include <maxmod.h>')
        _add_inc(f'#include "{soundbank_h.name}"')
        _add_inc('#include "soundbank.bin.h"')

    for d in all_scene_data:
        bgi_d = _bg_info(p, d["bg_pairs"])
        if bgi_d:
            _add_inc(f'#include "{_sym(d["scene"].name)}_tileset.h"')
        for _, sprite in d["scene_actors"]:
            if sprite and sprite.asset:
                _add_inc(f'#include "sprite_{_sym(sprite.name)}.h"')

    for _, sprite in prefab_actor_sprites:
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{_sym(sprite.name)}.h"')

    # Externs actors + scènes (filtrés sur les events réellement implémentés)
    def _def(sym, ev):
        """True si l'event est défini dans le script Lua de cet actor."""
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    for d in all_scene_data:
        sc = d["scene"]
        sc_sym = _sym(sc.name)
        for actor, _ in d["scene_actors"]:
            s = _sym(actor.name)
            script_path = _actor_script(actor)
            if script_path:
                abs_sp = p.asset_abs(script_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    for ev in ("on_start", "on_update", "on_late_update", "on_tile_collide",
                               "on_collision_enter", "on_collide", "on_collision_exit"):
                        if _def(s, ev):
                            if ev == "on_tile_collide":
                                L.append(f"extern void {s}_{ev}(Actor*,int,int);")
                            elif ev in ("on_collision_enter", "on_collide", "on_collision_exit"):
                                L.append(f"extern void {s}_{ev}(Actor*,Actor*,u8,u8);")
                            else:
                                L.append(f"extern void {s}_{ev}(Actor*);")
                    for btn, ev in _BTN_MAP:
                        if _def(s, ev):
                            L.append(f"extern void {s}_{ev}(Actor*);")
        if getattr(sc, "script", ""):
            L += [
                f"extern void {sc_sym}_scene_on_start(void);",
                f"extern void {sc_sym}_scene_on_update(void);",
                f"extern void {sc_sym}_scene_on_late_update(void);",
            ]
    L.append("")

    # ── Tile helpers (dispatch via pointeur) ──────────────────────
    L += _gen_tile_helpers()

    # ── Cmap flat arrays par scène ────────────────────────────────
    for d in all_scene_data:
        sc = d["scene"]
        sym = _sym(sc.name)
        cmap = sc.collision_map or []
        if cmap and any(v != 0 for row in cmap for v in row):
            rows = len(cmap)
            cols = max(len(row) for row in cmap)
            flat = []
            for row in cmap:
                flat += list(row) + [0] * (cols - len(row))
            L += [
                f"#define CMAP_W_{sym.upper()} {cols}",
                f"#define CMAP_H_{sym.upper()} {rows}",
                f"static const u8 g_cmap_{sym}[{rows*cols}] = {{",
                "    " + ", ".join(str(v) for v in flat),
                "};",
                "",
            ]

    # ── Globals ───────────────────────────────────────────────────
    L += [
        f"Actor g_actors[{n_actors}];",
        "u32   _g_keys_held    = 0;",
        "u32   _g_keys_pressed = 0;",
        "int   cam_x = 0, cam_y = 0;",
        "int   _g_frame = 0;",
        "int   g_current_scene = -1;",
        "int   g_next_scene    = -1;",
        "",
    ]

    # Spawn helpers
    L += _section_spawn(pi, actor_defined_events=actor_defined_events)

    # ── scene_init_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc         = d["scene"]
        act_off    = scene_offsets[i]
        bgi_d      = _bg_info(p, d["bg_pairs"])
        sa         = d["scene_actors"]

        # lua_idx local (indices GLOBAUX)
        lua_idx_d: set[int] = set()
        for j, (actor, _) in enumerate(sa):
            sp_path = _actor_script(actor)
            if sp_path:
                abs_sp = p.asset_abs(sp_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    lua_idx_d.add(act_off + j)

        # DISPCNT
        text_bg = getattr(sc, "text_bg", -1)
        bg_bits = {0: 0x0100, 1: 0x0200, 2: 0x0400, 3: 0x0800}
        dispcnt = bg_bits.get(text_bg, 0)
        if bgi_d:
            for bi in bgi_d:
                dispcnt |= bg_bits.get(bi["bg"], 0)
        if sprite_offsets:
            dispcnt |= 0x1040

        L += _gen_scene_init(
            p, sc, act_off, bgi_d, sa, lua_idx_d, pi,
            sprite_offsets, dispcnt, has_sound, sound_assets,
            actor_defined_events=actor_defined_events,
        )

    # ── scene_tick_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc      = d["scene"]
        act_off = scene_offsets[i]
        bgi_d   = _bg_info(p, d["bg_pairs"])
        sa      = d["scene_actors"]

        lua_idx_d: set[int] = set()
        for j, (actor, _) in enumerate(sa):
            sp_path = _actor_script(actor)
            if sp_path:
                abs_sp = p.asset_abs(sp_path)
                if abs_sp and abs_sp.suffix.lower() == ".lua":
                    lua_idx_d.add(act_off + j)

        col_pairs_d = [
            (act_off + ii, act_off + jj)
            for ii in range(len(sa))
            for jj in range(ii + 1, len(sa))
            if (act_off + ii) in lua_idx_d or (act_off + jj) in lua_idx_d
        ]

        L += _gen_scene_tick(
            p, sc, act_off, bgi_d, sa, lua_idx_d, pi,
            sprite_offsets, sprite_nframes, col_pairs_d,
            actor_defined_events=actor_defined_events,
        )

    # ── Dispatch table ────────────────────────────────────────────
    L += [
        "typedef struct { void(*init)(void); void(*tick)(void); } _SceneVtable;",
        f"static const _SceneVtable g_scene_vtable[{len(all_scene_data)}] = {{",
    ]
    for d in all_scene_data:
        sym = _sym(d["scene"].name)
        L.append(f"    {{ scene_init_{sym}, scene_tick_{sym} }},")
    L += ["};", ""]

    # ── main() ────────────────────────────────────────────────────
    L.append("int main(void){")
    L.append("    irqInit(); irqEnable(IRQ_VBLANK);")

    if has_sound and soundbank_h.exists():
        L.append("    mmInitDefault((mm_addr)soundbank_bin, MM_SIZEOF_MODLIST);")
        if sound_assets and sound_assets.get("music"):
            music_item, _ = sound_assets["music"][0]
            loop = "MM_PLAY_LOOP" if getattr(music_item, "loop", True) else "MM_PLAY_ONCE"
            L.append(f"    mmStart(MOD_{_sym(music_item.name).upper()}, {loop});")

    # Sprites VRAM (une seule fois au démarrage — toutes scènes)
    if sprite_offsets:
        L.append("    /* Tiles sprites → OBJ VRAM (toutes scènes) */")
        for name, base in sprite_offsets.items():
            ss = f"sprite_{_sym(name)}"
            L.append(f"    copy16(OBJ_VRAM+{base}*16, {ss}Tiles, {ss}TilesLen);")
        L.append("    /* Palettes OBJ */")
        done_pal: set[int] = set()
        for d in all_scene_data:
            for actor, sprite in d["scene_actors"]:
                if sprite and sprite.asset:
                    pal = getattr(actor, "pal_bank", 0)
                    if pal not in done_pal:
                        done_pal.add(pal)
                        ss = f"sprite_{_sym(sprite.name)}"
                        L.append(f"    copy16(PAL_OBJ_RAM+{pal}*16, {ss}Pal, {ss}PalLen);")
        for pf, sprite in prefab_actor_sprites:
            if sprite and sprite.asset:
                pal = getattr(pf, "pal_bank", 0)
                if pal not in done_pal:
                    done_pal.add(pal)
                    ss = f"sprite_{_sym(sprite.name)}"
                    L.append(f"    copy16(PAL_OBJ_RAM+{pal}*16, {ss}Pal, {ss}PalLen);")

    L += [
        f"    g_next_scene = {start_idx};   /* {start_scene} */",
        "    while(1){",
        "        if(g_next_scene != g_current_scene){",
        "            g_current_scene = g_next_scene;",
        f"            if(g_current_scene>=0 && g_current_scene<{len(all_scene_data)})",
        "                g_scene_vtable[g_current_scene].init();",
        "        }",
        "        VBlankIntrWait();",
        "        _g_frame++;",
        "        scanKeys();",
        "        _g_keys_held    = keysHeld();",
        "        _g_keys_pressed = keysDown();",
        f"        if(g_current_scene>=0 && g_current_scene<{len(all_scene_data)})",
        "            g_scene_vtable[g_current_scene].tick();",
        "    }",
        "    return 0;",
        "}",
    ]

    out = p.src_dir / "main.c"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    emit("log_line", f"[gen] {out.relative_to(p.root)}")
    return True
