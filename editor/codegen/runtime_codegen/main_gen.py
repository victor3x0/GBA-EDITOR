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
    Project, Scene, Actor, SpriteAsset, CollisionBoxComponent, SpriteComponent, OWN_PAL_BANK,
)
from codegen.palette_alloc import scene_bank_layout
from codegen.asset_pipeline import (
    count_frames, sprite_unique_frames, _seq_key,
    bg_layer_sym, bg_layer_sym_for, bg_map_geometry, bg_map_sbb_count,
)
from codegen.build_utils import sym as _sym


RUNTIME_DIR = Path(__file__).resolve().parents[3] / "runtime"


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


def _bg_info(p: Project, scene) -> list[dict]:
    """Un CBB (16 Ko) par layer = bg_slot ; sa map occupe les derniers SBB de ce
    CBB. Chaque layer de la scène référence une image ; sa compression vient du
    BackgroundAsset (sidecar) keyé par ce nom. cf. pipeline._check_bg_tile_budget."""
    result = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.image:
            continue
        ba = p.get_background(layer.image)
        # Fond bitmap (Mode 4) : non supporté au build (increment 2) — ignoré ici
        # (sinon il serait traité comme un fond tuilé legacy → symbole manquant).
        if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
            continue
        bg_slot = layer.bg_slot
        speed = int(layer.scroll_speed * 256)
        sym = bg_layer_sym(layer.image, bg_slot)
        if ba and ba.tileset:
            # Fond COMPRESSÉ (métadonnées) — 16 palettes via g_pal_bg, tuiles/map
            # depuis le C émis par pipeline._emit_compressed_bg. Un axe >64 tuiles
            # dépasse la fenêtre hardware -> streaming (map résidente 64 sur cet axe).
            # Symbole PROPRE À LA SCÈNE si le layer est peint (map d'overrides,
            # cf. bg_layer_sym_for / pipeline._emit_compressed_bg).
            sym = bg_layer_sym_for(scene, layer)
            tw, th = ba.tiles_w, ba.tiles_h
            stream_h = tw > 64
            stream_v = th > 64
            win_w = 64 if stream_h else tw
            win_h = 64 if stream_v else th
            ms = (1 if win_w > 32 else 0) | (2 if win_h > 32 else 0)
            map_sbb_count = bg_map_sbb_count(ms)
            result.append({
                "bg": bg_slot, "stem": ba.name, "sym": sym,
                "tw": tw, "th": th, "sbb": bg_slot * 8 + (8 - map_sbb_count),
                "map_size": ms, "map_sbb_count": map_sbb_count,
                "speed": speed, "pal_bank": layer.pal_bank, "compressed": True,
                "stream": stream_h or stream_v, "stream_h": stream_h, "stream_v": stream_v,
                "win_w": win_w, "win_h": win_h,
                "bpp8": getattr(ba, "bpp", 4) == 8,   # BGxCNT bit 7 (256/1)
            })
        else:
            # Image non compressée -> taille depuis le PNG (chemin legacy).
            ap = p.background_images_dir / (ba.source if ba and ba.source else f"{layer.image}.png")
            try:
                from PIL import Image
                with Image.open(ap) as img:
                    w, h = img.size
            except Exception:
                w, h = 240, 160
            tw, th, ms = bg_map_geometry(w, h)
            map_sbb_count = bg_map_sbb_count(ms)
            result.append({
                "bg": bg_slot, "stem": ap.stem, "sym": sym,
                "tw": tw, "th": th, "sbb": bg_slot * 8 + (8 - map_sbb_count),
                "map_size": ms, "map_sbb_count": map_sbb_count,
                "speed": speed, "pal_bank": layer.pal_bank,
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


def _section_spawn(pool_info: list[dict], p: Project, obj_layout,
                   actor_defined_events: dict[str, set[str]] | None = None) -> list[str]:
    """`obj_layout` : layout OBJ de la scène d'ancrage (1ère scène) — spawn_X
    étant global, l'index de banque d'un prefab poolé est fixé depuis cette
    scène (cohérent avec la résolution prefab par 1ère scène ; les incohérences
    inter-scènes sont signalées par le validateur)."""
    if not pool_info:
        return []

    def _def(sym, ev):
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    L = ["/* ── Spawn helpers (prefabs poolés) ────────────────────── */"]
    for pi in pool_info:
        s, start, size, pf = pi["sym"], pi["start"], pi["size"], pi["prefab"]
        sp = next((c for c in pf.components
                   if isinstance(c, SpriteComponent) and c.sprite_name), None)
        sprite = p.get_sprite(sp.sprite_name) if sp else None
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(pf, "pal_bank", OWN_PAL_BANK), own) if obj_layout else 0
        if pal is None:
            pal = 0
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


def _anim_tables_for(p: Project, sprite: SpriteAsset) -> list[str]:
    """Génère les tables C d'animation pour un SpriteAsset.

    Produit :
      {sym}_anim_dirs[]   — {dir, frame_start, frame_count} par état+direction
      {sym}_state_start[] — index dans anim_dirs où commence chaque état
      {sym}_state_speed[] — speed (ticks) par état
      {sym}_state_loop[]  — loop (0/1) par état
    """
    sym = f"sprite_{_sym(sprite.name)}"
    entries: list[str] = []          # "{dir,start,count}"
    state_starts: list[int] = []
    state_speeds: list[int] = []
    state_loops: list[int] = []

    # seq_starts fait autorité sur le layout du sheet : chaque direction occupe
    # un bloc contigu [start, start+count) — le runtime joue frame=start+k.
    seq_starts, _ = sprite_unique_frames(sprite)

    for state in sprite.states:
        state_starts.append(len(entries))
        state_speeds.append(state.speed)
        state_loops.append(1 if state.loop else 0)
        dir_map = {sd.dir: sd for sd in state.directions}
        for sd in state.directions:
            src_sd = dir_map.get(sd.mirror_of, sd) if sd.mirror_of is not None else sd
            start = seq_starts[_seq_key(src_sd, sd.flip_h, sd.flip_v)]
            count = len(src_sd.frames)
            entries.append(f"{{{sd.dir},{start},{count}}}")
        entries.append("{255,0,0}")   # sentinel de fin d'état

    L: list[str] = [
        f"static const u8 __attribute__((unused)) {sym}_anim_dirs[][3] = {{",
        "    " + ",".join(entries),
        "};",
        f"static const u8 __attribute__((unused)) {sym}_state_start[] = {{{','.join(str(x) for x in state_starts)}}};",
        f"static const u8 __attribute__((unused)) {sym}_state_speed[] = {{{','.join(str(x) for x in state_speeds)}}};",
        f"static const u8 __attribute__((unused)) {sym}_state_loop[]  = {{{','.join(str(x) for x in state_loops)}}};",
    ]
    return L


def _anim_tick_lines(idx: int, sym: str) -> list[str]:
    """Génère le bloc C de tick d'animation pour un acteur (dans scene_tick)."""
    return [
        f"    if(g_actors[{idx}].auto_dir&&(g_actors[{idx}].vx||g_actors[{idx}].vy)){{",
        f"        g_actors[{idx}].dir_x=(g_actors[{idx}].vx>0)-(g_actors[{idx}].vx<0);",
        f"        g_actors[{idx}].dir_y=(g_actors[{idx}].vy>0)-(g_actors[{idx}].vy<0);",
        f"    }}",
        # dir_x/dir_y → indice 1-8 (NW=8,N=1,NE=2,W=7,0=0,E=3,SW=6,S=5,SE=4)
        f"    {{",
        f"        static const s8 _dlut[3][3]={{{{8,1,2}},{{7,0,3}},{{6,5,4}}}};",
        f"        int _ad=_dlut[g_actors[{idx}].dir_y+1][g_actors[{idx}].dir_x+1];",
        f"        int _st=g_actors[{idx}].anim_state;",
        f"        int _b={sym}_state_start[_st];",
        f"        int _fs=0,_fc=1,_fb=-1,_fbc=1;",
        f"        for(int _e=_b;{sym}_anim_dirs[_e][0]!=255;_e++){{",
        f"            if({sym}_anim_dirs[_e][0]==_ad){{_fs={sym}_anim_dirs[_e][1];_fc={sym}_anim_dirs[_e][2];goto _af{idx};}}",
        f"            if({sym}_anim_dirs[_e][0]==0){{_fb={sym}_anim_dirs[_e][1];_fbc={sym}_anim_dirs[_e][2];}}",
        f"        }}",
        f"        if(_fb>=0){{_fs=_fb;_fc=_fbc;}}",
        f"        _af{idx}:;",
        f"        g_actors[{idx}].timer++;",
        f"        if(g_actors[{idx}].timer>={sym}_state_speed[_st]){{",
        f"            g_actors[{idx}].timer=0;",
        f"            int _fi=g_actors[{idx}].frame-_fs;",
        f"            if({sym}_state_loop[_st]) g_actors[{idx}].frame=_fs+(_fc>1?(_fi+1)%_fc:0);",
        f"            else if(_fi<_fc-1) g_actors[{idx}].frame=_fs+_fi+1;",
        f"        }}",
        f"    }}",
    ]


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


# ─── Helpers affine / origine ─────────────────────────────────────────────────

def _get_sprite_comp(actor) -> "SpriteComponent | None":
    """Retourne le SpriteComponent d'un Actor/Prefab, ou None."""
    for c in getattr(actor, "components", []):
        if isinstance(c, SpriteComponent):
            return c
    return None


def _affine_entry(sc, slot: int) -> dict | None:
    """
    Calcule les valeurs affines GBA pour un SpriteComponent.

    Retourne None si aucune transformation affine n'est requise.

    Matrice GBA (8.8 fp, ×256) :
        PA = cos/sx   PB = sin/sx
        PC = -sin/sy  PD = cos/sy
    Flip encodé dans le signe (runtime) : flip_h → -(PA,PB), flip_v → -(PC,PD).

    Position OAM ajustée pour que le pixel à (ox,oy) atterrisse sur (actor.x, actor.y) :
        oam_x = actor.x - cam_x + oam_x_const  (4 variantes selon flip runtime)
    """
    sx      = getattr(sc, "scale_x",  1.0)
    sy      = getattr(sc, "scale_y",  1.0)
    angle   = getattr(sc, "rotation", 0.0)
    ox      = getattr(sc, "origin_x", 0)
    oy      = getattr(sc, "origin_y", 0)

    needs_affine = (
        abs(sx - 1.0) > 1e-4 or abs(sy - 1.0) > 1e-4 or abs(angle) > 1e-4
    )
    if not needs_affine:
        return None

    theta  = math.radians(angle)
    cos_a  = math.cos(theta)
    sin_a  = math.sin(theta)

    # PA, PB, PC, PD en 8.8 fp (base, sans flip)
    pa = round(cos_a / sx * 256) if sx != 0 else 0
    pb = round(sin_a / sx * 256) if sx != 0 else 0
    pc = round(-sin_a / sy * 256) if sy != 0 else 0
    pd = round(cos_a / sy * 256) if sy != 0 else 0

    # Éviter PA=PD=0 quand scale est gigantesque
    if pa == 0 and pb == 0:
        pa = 1
    if pc == 0 and pd == 0:
        pd = 1

    def _oam_adj(fh: bool, fv: bool, W: int, H: int) -> tuple[int, int]:
        """OAM constant (oam_x_adj, oam_y_adj) pour un état flip donné.
        En double-size mode le centre de référence écran est W,H (pas W/2,H/2)
        mais le centre texture reste toujours W/2,H/2."""
        sx_eff = -sx if fh else sx
        sy_eff = -sy if fv else sy
        dx = ox - W / 2   # origine relative au centre texture
        dy = oy - H / 2
        u = cos_a * sx_eff * dx - sin_a * sy_eff * dy
        v = sin_a * sx_eff * dx + cos_a * sy_eff * dy
        return round(-W - u), round(-H - v)  # -W/-H car double-size (centre = W,H)

    return {
        "slot": slot,
        "pa": pa, "pb": pb, "pc": pc, "pd": pd,
        "_oam_adj": _oam_adj,   # callable(fh, fv, W, H) → (x_adj, y_adj)
    }


def _compute_affine_info(actor_offset: int, scene_actors: list, pi: list) -> dict:
    """
    Retourne {oam_idx: entry} pour tout actor nécessitant un sprite affine.
    Limité à 32 slots (contrainte hardware GBA OAM).
    """
    result: dict = {}
    slot = 0

    for j, (actor, _) in enumerate(scene_actors):
        if slot >= 32:
            break
        sc = _get_sprite_comp(actor)
        if not sc:
            continue
        entry = _affine_entry(sc, slot)
        if entry:
            result[actor_offset + j] = entry
            slot += 1

    for p2 in pi:
        pf = p2["prefab"]
        sc = _get_sprite_comp(pf)
        if not sc:
            continue
        for oam_idx in range(p2["start"], p2["start"] + p2["size"]):
            if slot >= 32:
                break
            entry = _affine_entry(sc, slot)
            if entry:
                result[oam_idx] = entry
                slot += 1

    return result


def _layout_palette_words(layout) -> list[int]:
    """256 valeurs BGR555 (16 banques x 16 couleurs) depuis un SceneBankLayout
    — inclut les palettes référencées ET les palettes propres auto-allouées
    (cf. codegen/palette_alloc.py)."""
    words = [0] * 256
    for i, colors in enumerate(layout.slot_colors):
        if not colors:
            continue
        for j, c in enumerate(colors[:16]):
            words[i * 16 + j] = c
    return words


def _resolve_backdrop_color(p: Project, scene: Scene) -> int:
    """Scene.backdrop_color surcharge ProjectSettings.backdrop_color si
    défini (None = hérite du projet)."""
    v = getattr(scene, "backdrop_color", None)
    return v if v is not None else p.settings.backdrop_color


def _scene_obj_palette_words(p: Project, scene: Scene) -> list[int]:
    """PAL_OBJ_RAM de la scène — layout OBJ (référencées + propres allouées)."""
    return _layout_palette_words(scene_bank_layout(p, scene, "obj"))


def _scene_bg_palette_words(p: Project, scene: Scene) -> list[int]:
    """PAL_BG_RAM de la scène — layout BG (référencées + propres, y compris
    les blocs de banques des fonds compressés, cf. palette_alloc). words[0]
    forcé à la couleur de backdrop."""
    words = _layout_palette_words(scene_bank_layout(p, scene, "bg"))
    words[0] = _resolve_backdrop_color(p, scene)
    return words


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
    obj_layout = scene_bank_layout(p, scene, "obj")
    bg_layout  = scene_bank_layout(p, scene, "bg")
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
    # BG layers — chaque layer a son propre CBB (= bg_slot) pour ses tuiles,
    # sa map vit dans les derniers SBB de ce même CBB (cf. _bg_info).
    if bgi:
        for bi in bgi:
            L.append(f"    copy16(TILE_RAM({bi['bg']}), {bi['sym']}Tiles, {bi['sym']}TilesLen);")
        for bi in bgi:
            if bi.get("stream"):
                # Streaming : charger la fenêtre résidente initiale depuis la map
                # complète en ROM ; les bords se rechargent au scroll (tick).
                L.append(f"    bg_stream_init(MAP_RAM({bi['sbb']}), {bi['sym']}Map, "
                         f"{bi['tw']}, {bi['th']}, {bi['win_w']}, {bi['win_h']});")
            else:
                ms = bi["map_size"]
                gcols = 64 if (ms & 1) else 32
                grows = 64 if (ms & 2) else 32
                L.append(f"    load_map(MAP_RAM({bi['sbb']}), {bi['sym']}Map, {bi['tw']}, {bi['th']}, {gcols}, {grows});")
        for bi in bgi:
            # Priorité GBA = bg_slot directement (bg_slot 0 = priorité 0 =
            # premier plan). Même convention que l'éditeur (scene_editor.py
            # GbaScene.set_bg : z = 3 - bg_index, donc bg_slot 0 = zValue le
            # plus HAUT = dessiné devant dans le canvas Qt) — bg_slot 0 doit
            # rester devant sur les deux. Or en registre BGxCNT, priorité 0 =
            # dessiné DEVANT (l'inverse d'un zValue Qt) : `pri = bg` (pas
            # `3 - bg`) est donc la formule qui fait correspondre les deux.
            bg = bi["bg"]; sbb = bi["sbb"]; pri = bg; ms = bi["map_size"]
            val = (pri & 3) | (bg & 3) << 2 | (sbb & 0x1F) << 8 | ms << 14
            if bi.get("bpp8"):
                val |= 0x0080   # bit 7 : couleurs 256/1 (8bpp) au lieu de 16/16
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
    # Palettes OBJ — chaque banque occupée du layout (référencée OU palette
    # propre auto-allouée, cf. palette_alloc) est copiée dans PAL_OBJ_RAM.
    for i, colors in enumerate(obj_layout.slot_colors):
        if colors:
            L.append(f"    copy16(PAL_OBJ_RAM+{i}*16, g_pal_obj_{sym}+{i}*16, 32);")
    # Palette BG — chaque banque occupée du layout (référencée, bloc de fond
    # compressé, ou palette propre auto-allouée, cf. palette_alloc) est copiée
    # dans PAL_BG_RAM.
    for i, colors in enumerate(bg_layout.slot_colors):
        if colors:
            L.append(f"    copy16(PAL_BG_RAM+{i}*16, g_pal_bg_{sym}+{i}*16, 32);")
    # Backdrop — écrit inconditionnellement (indépendant de bgi/de
    # l'occupation du slot 0 ci-dessus, qui ne copie que les slots occupés :
    # une scène sans aucune palette BG active doit quand même pouvoir
    # afficher une couleur de fond).
    L.append(f"    PAL_BG_RAM[0] = 0x{_resolve_backdrop_color(p, scene):04X};")
    # TTE — CBB/SBB du charblock DU LAYER UI choisi (pas figé sur CBB3) : les
    # glyphes de police vivent dans le charblock text_bg (bg_slot == text_bg,
    # cf. per-layer redesign CBB=bg_slot), dernier SBB de ce même charblock.
    # Le layer UI ne doit porter aucune image (cf. _check_bg_text_cbb_conflict,
    # devenu bloquant) : ce charblock est donc entièrement libre pour la police.
    text_bg = getattr(scene, "text_bg", -1)
    if text_bg in {0, 1, 2, 3}:
        text_sbb = text_bg * 8 + 7
        L.append(f"    tte_init_se({text_bg}, BG_CBB({text_bg})|BG_SBB({text_sbb}), SE_PALBANK(15), 0x7FFF, 0, &fwf_default, NULL);")
    # DISPCNT
    L.append(f"    REG_DISPCNT = 0x{dispcnt:04X};")
    # Init actors
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        s = _sym(actor.name)
        boxes = [c for c in actor.components if isinstance(c, CollisionBoxComponent) and c.active][:4]
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(actor, "pal_bank", OWN_PAL_BANK), own)
        L += [
            f"    g_actors[{idx}].x       = {actor.x};",
            f"    g_actors[{idx}].y       = {actor.y};",
            f"    g_actors[{idx}].active  = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].visible = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].flip_h  = {1 if getattr(_get_sprite_comp(actor),'flip_h',False) else 0};",
            f"    g_actors[{idx}].flip_v  = {1 if getattr(_get_sprite_comp(actor),'flip_v',False) else 0};",
            f"    g_actors[{idx}].dir_x   = {getattr(actor,'dir_x',0)};",
            f"    g_actors[{idx}].dir_y   = {getattr(actor,'dir_y',0)};",
            f"    g_actors[{idx}].pal_bank= {pal if pal is not None else 0};",
            f"    g_actors[{idx}].auto_dir= {1 if getattr(_get_sprite_comp(actor),'auto_dir',True) else 0};",
            f"    g_actors[{idx}].anim_state=0;",
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


def _signed(n: int) -> str:
    """Formate un entier en chaîne C signée : +3, -8, '' si zéro."""
    if n == 0:
        return ""
    return f"+{n}" if n > 0 else str(n)


def _affine_oam_lines(idx: int, aff: dict, sprite, bt: int, priority_expr: str) -> list[str]:
    """Lignes C (intérieur du if actif) pour un sprite affine : rotation+scale+flip runtime."""
    aslot = aff["slot"]
    pa, pb, pc, pd = aff["pa"], aff["pb"], aff["pc"], aff["pd"]
    adj_fn = aff["_oam_adj"]
    W, H   = sprite.frame_w, sprite.frame_h
    sh, sz = sprite.oam_shape, sprite.oam_size
    tpf    = sprite.tiles_per_frame

    x00, y00 = adj_fn(False, False, W, H)
    xfh, yfh = adj_fn(True,  False, W, H)
    xfv, yfv = adj_fn(False, True,  W, H)
    xhv, yhv = adj_fn(True,  True,  W, H)

    def _pos(base: str, n0, nfh, nfv, nhv) -> str:
        if n0 == nfh == nfv == nhv:
            return f"{base}{_signed(n0)}"
        return (
            f"{base}+(g_actors[{idx}].flip_h"
            f"?(g_actors[{idx}].flip_v?({nhv}):({nfh}))"
            f":(g_actors[{idx}].flip_v?({nfv}):({n0})))"
        )

    sx_expr = _pos(f"g_actors[{idx}].x-cam_x", x00, xfh, xfv, xhv)
    sy_expr = _pos(f"g_actors[{idx}].y-cam_y", y00, yfh, yfv, yhv)

    return [
        f"        int sx={sx_expr}; int sy={sy_expr};",
        f"        u16 ti=(u16)({bt}+g_actors[{idx}].frame*{tpf});",
        f"        shadow_oam[{aslot*4+0}].dummy=(u16)(s16)(g_actors[{idx}].flip_h?{-pa}:{pa});",
        f"        shadow_oam[{aslot*4+1}].dummy=(u16)(s16)(g_actors[{idx}].flip_h?{-pb}:{pb});",
        f"        shadow_oam[{aslot*4+2}].dummy=(u16)(s16)(g_actors[{idx}].flip_v?{-pc}:{pc});",
        f"        shadow_oam[{aslot*4+3}].dummy=(u16)(s16)(g_actors[{idx}].flip_v?{-pd}:{pd});",
        f"        shadow_oam[{idx}].attr0=(sy&0xFF)|(1<<8)|(1<<9)|({sh}<<14);",
        f"        shadow_oam[{idx}].attr1=(sx&0x1FF)|({aslot}<<9)|({sz}<<14);",
        f"        shadow_oam[{idx}].attr2=(ti&0x3FF)|({priority_expr}<<10)|(g_actors[{idx}].pal_bank<<12);",
    ]


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
    affine_info: dict | None = None,
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

    # BG scroll offset H+V (+ streaming des bords pour un grand niveau)
    if bgi:
        for bi in bgi:
            if bi.get("stream"):
                L.append(f"    bg_stream_update(MAP_RAM({bi['sbb']}), {bi['sym']}Map, "
                         f"{bi['tw']}, {bi['th']}, {bi['win_w']}, {bi['win_h']}, "
                         f"{int(bi['stream_h'])}, {int(bi['stream_v'])}, cam_x, cam_y);")
            L.append(f"    BGOFS({bi['bg']})=(u16)((cam_x*{bi['speed']})>>8);")
            L.append(f"    BGVOFS({bi['bg']})=(u16)((cam_y*{bi['speed']})>>8);")
            if scene.scroll_v:
                L.append(f"    *((vu16*)(0x04000012+{bi['bg']}*4))=(u16)((cam_y*{bi['speed']})>>8);")

    # Animation (state machine + direction)
    anim_actors = [(actor_offset + j, a, s2) for j, (a, s2) in enumerate(scene_actors) if s2 and s2.asset and s2.states]
    for idx, actor, sprite in anim_actors:
        L += _anim_tick_lines(idx, f"sprite_{_sym(sprite.name)}")

    _aff = affine_info or {}

    # OAM actors scène
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        if not actor.visible:
            continue
        if sprite and sprite.asset:
            sh = sprite.oam_shape; sz = sprite.oam_size
            bt = sprite_offsets.get(sprite.name, 0)
            sc  = _get_sprite_comp(actor)
            ox  = getattr(sc, "origin_x", 0) if sc else 0
            oy  = getattr(sc, "origin_y", 0) if sc else 0
            ox_s = (f"-{ox}" if ox > 0 else f"+{-ox}") if ox else ""
            oy_s = (f"-{oy}" if oy > 0 else f"+{-oy}") if oy else ""
            if idx in _aff:
                inner = _affine_oam_lines(idx, _aff[idx], sprite, bt, str(actor.priority))
                L += [
                    f"    if(g_actors[{idx}].active && g_actors[{idx}].visible){{",
                    *inner,
                    f"    }}else{{ shadow_oam[{idx}].attr0=0x0200; }}",
                ]
            else:
                L += [
                    f"    if(g_actors[{idx}].active && g_actors[{idx}].visible){{",
                    f"        int sx=g_actors[{idx}].x-cam_x{ox_s}; int sy=g_actors[{idx}].y-cam_y{oy_s};",
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
            for oam_slot in range(p2["start"], p2["start"] + p2["size"]):
                L.append(f"    shadow_oam[{oam_slot}].attr0=0x0200;")
            continue
        sh = pf_spr.oam_shape; sz = pf_spr.oam_size
        bt = sprite_offsets.get(pf_spr.name, 0)
        pf_sc2 = _get_sprite_comp(pf)
        ox = getattr(pf_sc2, "origin_x", 0) if pf_sc2 else 0
        oy = getattr(pf_sc2, "origin_y", 0) if pf_sc2 else 0
        ox_s = (f"-{ox}" if ox > 0 else f"+{-ox}") if ox else ""
        oy_s = (f"-{oy}" if oy > 0 else f"+{-oy}") if oy else ""
        for oam_slot in range(p2["start"], p2["start"] + p2["size"]):
            if oam_slot in _aff:
                inner = _affine_oam_lines(oam_slot, _aff[oam_slot], pf_spr, bt, "0")
                L += [
                    f"    if(g_actors[{oam_slot}].active && g_actors[{oam_slot}].visible){{",
                    *inner,
                    f"    }}else{{ shadow_oam[{oam_slot}].attr0=0x0200; }}",
                ]
            else:
                L += [
                    f"    if(g_actors[{oam_slot}].active && g_actors[{oam_slot}].visible){{",
                    f"        int sx=g_actors[{oam_slot}].x-cam_x{ox_s}; int sy=g_actors[{oam_slot}].y-cam_y{oy_s};",
                    f"        u16 ti=(u16)({bt}+g_actors[{oam_slot}].frame*{pf_spr.tiles_per_frame});",
                    f"        int fh=g_actors[{oam_slot}].flip_h; int fv=g_actors[{oam_slot}].flip_v;",
                    f"        shadow_oam[{oam_slot}].attr0=(sy&0xFF)|({sh}<<14);",
                    f"        shadow_oam[{oam_slot}].attr1=(sx&0x1FF)|(fh<<12)|(fv<<13)|({sz}<<14);",
                    f"        shadow_oam[{oam_slot}].attr2=(ti&0x3FF)|(0<<10)|(g_actors[{oam_slot}].pal_bank<<12);",
                    f"    }}else{{ shadow_oam[{oam_slot}].attr0=0x0200; }}",
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
    _add_inc('#include "constants.h"')
    if has_sound and soundbank_h.exists():
        _add_inc('#include <maxmod.h>')
        _add_inc(f'#include "{soundbank_h.name}"')
        _add_inc('#include "soundbank.bin.h"')

    for d in all_scene_data:
        bgi_d = _bg_info(p, d["scene"])
        for bi in bgi_d:
            _add_inc(f'#include "{bi["sym"]}.h"')
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

    # ── Tables d'animation par SpriteAsset (dédupliquées) ────────
    _all_sprites_flat = [
        pair
        for d in all_scene_data
        for pair in d["scene_actors"]
    ] + (prefab_actor_sprites or [])
    done_anim: set[str] = set()
    for _, sprite in _all_sprites_flat:
        if sprite and sprite.asset and sprite.name not in done_anim:
            done_anim.add(sprite.name)
            L += _anim_tables_for(p, sprite)
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

    # ── Palettes OBJ actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_obj_palettes -> project.palettes) ────────────
    # Émis uniquement si au moins un slot est réellement occupé — sinon la
    # boucle copy16 correspondante dans _gen_scene_init ne référence jamais
    # ce tableau ("defined but not used", en plus de gaspiller 512 octets
    # de ROM par scène sans palette OBJ active, ex. INTRO/VICTORY).
    for d in all_scene_data:
        sc = d["scene"]
        sym = _sym(sc.name)
        if scene_bank_layout(p, sc, "obj").bank_count() > 0:
            words = _scene_obj_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_obj_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
                "};",
                "",
            ]

    # ── Palettes BG actives par scène (16 banques x 16 couleurs, résolues
    #    depuis Scene.active_bg_palettes -> project.palettes) ──────────────
    # Même garde qu'OBJ ci-dessus — le backdrop (PAL_BG_RAM[0]) est écrit à
    # part comme constante littérale (_resolve_backdrop_color), pas depuis
    # ce tableau, donc rien ne le référence si aucun slot BG n'est occupé.
    for d in all_scene_data:
        sc = d["scene"]
        sym = _sym(sc.name)
        # Émis si un slot BG est occupé (référencé, bloc de fond compressé, ou
        # palette propre) ; le backdrop (PAL_BG_RAM[0]) est écrit séparément.
        if scene_bank_layout(p, sc, "bg").bank_count() > 0:
            words = _scene_bg_palette_words(p, sc)
            L += [
                f"static const unsigned short g_pal_bg_{sym}[256] __attribute__((aligned(4))) = {{",
                "    " + ", ".join(f"0x{v:04X}" for v in words),
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

    # Spawn helpers — index de banque des prefabs poolés résolu via la
    # 1ère scène (spawn_X est global).
    _anchor_obj_layout = scene_bank_layout(p, all_scenes[0], "obj") if all_scenes else None
    L += _section_spawn(pi, p, _anchor_obj_layout, actor_defined_events=actor_defined_events)

    # ── scene_init_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc         = d["scene"]
        act_off    = scene_offsets[i]
        bgi_d      = _bg_info(p, d["scene"])
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
        bgi_d   = _bg_info(p, d["scene"])
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

        affine_d = _compute_affine_info(act_off, sa, pi)
        L += _gen_scene_tick(
            p, sc, act_off, bgi_d, sa, lua_idx_d, pi,
            sprite_offsets, sprite_nframes, col_pairs_d,
            actor_defined_events=actor_defined_events,
            affine_info=affine_d,
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
        # mmVBlank() DOIT être lié à l'IRQ vblank (doc maxmod.h) — sans ça le
        # mixeur n'avance jamais et le son ne sort qu'en grésillement/silence.
        L.append("    irqSet(IRQ_VBLANK, mmVBlank);")
        # 8 canaux logiciels — valeur standard des exemples maxmod
        # (MM_SIZEOF_MODLIST n'existe pas dans maxmod.h : mmInitDefault()
        # attend un nombre de canaux, pas une taille).
        L.append("    mmInitDefault((mm_addr)soundbank_bin, 8);")
        if sound_assets and sound_assets.get("music"):
            music_item, _ = sound_assets["music"][0]
            loop = "MM_PLAY_LOOP" if getattr(music_item, "loop", True) else "MM_PLAY_ONCE"
            L.append(f"    mmStart(MOD_{_sym(music_item.name).upper()}, {loop});")

    # Sprites VRAM (une seule fois au démarrage — toutes scènes). Les
    # palettes OBJ ne sont PLUS copiées ici : chaque scene_init_X() charge
    # déjà la sienne (g_pal_obj_{sym}) au bon moment, y compris pour la
    # scène de départ (appelée juste après, cf. boucle principale ci-dessous).
    if sprite_offsets:
        L.append("    /* Tiles sprites → OBJ VRAM (toutes scènes) */")
        for name, base in sprite_offsets.items():
            ss = f"sprite_{_sym(name)}"
            L.append(f"    copy16(OBJ_VRAM+{base}*16, {ss}Tiles, {ss}TilesLen);")

    L += [
        f"    g_next_scene = {start_idx};   /* {start_scene} */",
        "    while(1){",
        "        if(g_next_scene != g_current_scene){",
        "            g_current_scene = g_next_scene;",
        f"            if(g_current_scene>=0 && g_current_scene<{len(all_scene_data)})",
        "                g_scene_vtable[g_current_scene].init();",
        "        }",
        "        VBlankIntrWait();",
    ] + ([
        "        mmFrame();   /* doc maxmod.h : _doit_ être appelée chaque frame */",
    ] if has_sound and soundbank_h.exists() else []) + [
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
