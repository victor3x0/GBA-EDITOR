"""
runtime_codegen/main_gen.py — Génération de main.c.

Entrées  : Project, Scene, bg_pairs, scene_actors, sound_assets, prefab_sprites
Sortie   : p.src_dir/main.c
"""
from __future__ import annotations

import math
import shutil
from typing import Optional

from core.models.palette import OWN_PAL_BANK
from core.models.components import CollisionBoxComponent, SpriteComponent
from core.models.sprite import SpriteAsset
from core.models.scene import Actor, Scene
from core.project import Project
from core.models.field_value import (FieldValue as _FV,
                                     var_names_from_project as _var_names)
from codegen.palette_alloc import scene_bank_layout
from codegen.grit_conversion import (
    count_frames, sprite_unique_frames, seq_key,
    bg_layer_sym, bg_layer_sym_for, bg_map_geometry, bg_map_sbb_count,
)
from codegen.c_names import sym as c_sym
from core.app_paths import RUNTIME_DIR


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


def bg_info(p: Project, scene) -> list[dict]:
    """Un CBB (16 Ko) par layer = bg_slot ; sa map occupe les derniers SBB de ce
    CBB. Chaque layer de la scène référence une image ; sa compression vient du
    BackgroundAsset (sidecar) keyé par ce nom. cf. pipeline._check_bg_tile_budget."""
    result = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name:
            continue
        ba = p.get_background(layer.background_name)
        # Fond bitmap (Mode 4) : non supporté au build (increment 2) — ignoré ici
        # (sinon il serait traité comme un fond tuilé legacy → symbole manquant).
        if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
            continue
        bg_slot = layer.bg_slot
        speed = int(layer.scroll_speed * 256)
        sym = bg_layer_sym(layer.background_name, bg_slot)
        if ba and ba.tileset:
            # Fond COMPRESSÉ (métadonnées) — 16 palettes via g_pal_bg, tuiles/map
            # depuis le C émis par pipeline._emit_encoded_bg. Un axe >64 tuiles
            # dépasse la fenêtre hardware -> streaming (map résidente 64 sur cet axe).
            # Symbole PROPRE À LA SCÈNE si le layer est peint (map d'overrides,
            # cf. bg_layer_sym_for / pipeline._emit_encoded_bg).
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
            ap = p.background_images_dir / (ba.asset if ba and ba.asset else f"{layer.background_name}.png")
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
    _apply_vram_layout(p, scene, result)
    return result


def scene_anim_descriptors(p, scene, bgi: list[dict]) -> list[dict]:
    """Placements de fonds animés de la scène, enrichis de ce que seul le codegen
    connaît : le screenblock et la taille de la carte du calque hôte.

    L'ordre est celui de `bg_anim.scene_animations`, le même que `pipeline` a
    utilisé pour nommer les tables — les deux le recalculent séparément, ils
    doivent tomber d'accord (cf. bg_anim.anim_table_sym)."""
    from codegen.bg_anim import scene_animations, anim_table_sym, shared_table_sym
    by_slot = {bi["bg"]: bi for bi in bgi}
    out = []
    seen_shared: set[int] = set()
    for a in scene_animations(p, scene):
        bi = by_slot.get(a["layer"].bg_slot)
        if bi is None:
            continue    # calque non émis (bitmap, image manquante) : rien à animer
        g = a["geom"]
        if a["shared"]:
            # UN descripteur par fusion, pas par copie : le bloc de pixels est
            # partagé, deux descripteurs y écriraient la même chose deux fois.
            if a["table_index"] in seen_shared:
                continue
            seen_shared.add(a["table_index"])
            out.append({
                "shared": True,
                "table": shared_table_sym(scene, a["table_index"]),
                # 8 mots de 32 bits par tuile 4bpp = 16 u16.
                "cbb": bi["bg"], "vram_ofs": a["block"].tile_base * 16,
                "words": g.cells * 8,
                "frames": g.frames, "speed": g.speed, "loop": 1 if g.loop else 0,
            })
            continue
        f0, t0 = g.start_state()
        out.append({
            "shared": False,
            "table": anim_table_sym(scene, a["table_index"]),
            "sbb": bi["sbb"], "ms": bi["map_size"],
            "col": g.col, "row": g.row, "cols": g.cols, "rows": g.rows,
            "frames": g.frames, "speed": g.speed, "loop": 1 if g.loop else 0,
            "f0": f0, "t0": t0,
        })
    return out


def _layer_tiles_used(p, bi: dict) -> int:
    """Tuiles réellement générées pour un layer. Deux sources selon le chemin :
    le sidecar pour un fond compressé (connu sans grit), l'en-tête grit sinon."""
    ba = p.get_background(bi["stem"]) if bi.get("stem") else None
    if bi.get("compressed") and ba is not None and ba.tileset:
        # Les animés posés partagent le charblock de leur hôte : leurs tuiles
        # comptent dans ce que le calque charge (cf. codegen/bg_anim).
        from codegen.bg_anim import layer_tile_count
        return layer_tile_count(p, ba)
    header = p.grit_out_dir / f"{bi['sym']}.h"
    if header.exists():
        import re
        m = re.search(rf"{bi['sym']}TilesLen\s+(\d+)", header.read_text())
        if m:
            return int(m.group(1)) // 32
    # Inconnu (grit pas encore passé) : on suppose le pire pour ne pas
    # sur-promettre de la place à un voisin.
    return 512


def scene_text_colors(p, scene, font_name: str) -> list:
    """Couleurs à charger pour cette police dans cette scène, variante 0 d'abord.

    La variante 0 est l'encre d'ORIGINE : une police à plusieurs teintes garde
    les siennes tant qu'aucun slot ne demande de couleur. Les autres sont les
    index réclamés par les slots, chacun coûtant une copie des glyphes — d'où le
    tri, pour que l'ordre ne dépende pas de l'itération.

    Un slot qui ne DÉCLARE pas de police écrit avec la police courante, que le
    build ne connaît pas : sa couleur compte alors pour toutes les polices de la
    scène. Une copie de trop coûte des tuiles ; une de moins ferait tomber la
    couleur en silence."""
    from core.models.ui_region import KIND_SLOTS
    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    colors: set = set()
    for el in (lay.elements if lay is not None else []):
        if getattr(el, "kind", "") not in KIND_SLOTS:
            continue
        c = int(getattr(el, "text_color", 0) or 0)
        if not 1 <= c <= 15:
            continue
        declared = getattr(el, "font_name", "")
        if not declared or declared == font_name:
            colors.add(c)
    return [0] + sorted(colors)


def scene_text_reservation(p, scene) -> dict:
    """Tuiles à réserver au texte dans le charblock d'UI de CETTE scène.

    Un seul calcul pour deux lecteurs : le placement (`_apply_vram_layout`) et
    le garde-fou de budget (`pipeline._scene_tile_budgets`). Les laisser diverger
    validerait un budget que le placement ne tient pas.

    Quatre postes, dans l'ordre où ils occupent le charblock :
    - les fonds COULEUR puis les fonds IMAGE (nine-slice, background) — ils
      précèdent les glyphes, qui se décalent d'autant ;
    - les GLYPHES, restreints aux polices que cette scène peut charger
      (`font_emit.scene_font_names`) ;
    - la SURFACE composée quand une zone a un fond : bloc propre de 240 tuiles,
      jamais à l'adresse des glyphes (cf. runtime `g_surf_tile_base`) ;
    - les SPRITES des images en cible BG, TOUTES frames comprises : un script
      peut changer d'état à n'importe quelle frame, et recopier depuis la ROM à
      cet instant-là ferait clignoter l'image. En dernier parce que c'est le
      poste le plus récent, donc celui dont l'absence ne doit rien décaler dans
      un projet qui n'emploie pas d'image."""
    from codegen.font_emit import (scene_text_tiles, scene_font_names,
                                   scene_codepoints, mono_vram_tiles,
                                   scene_default_font, TEXT_SURF_TILES)
    fonts = project_fonts(p)
    # `scene_init` émet toujours un `text_set_font` : la police par défaut de la
    # scène est en VRAM même si la scène n'écrit pas une lettre.
    _, default_font = scene_default_font(p, scene)
    names = scene_font_names(p, scene, default_font)

    fills, fill_indices = scene_color_fills(p, scene)
    img_fills, img_assets = scene_image_fills(p, scene)
    by_name, _ = _region_bg_fills(p)
    lay_ui = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    needs_surface = any(r.name in by_name for r in (lay_ui.slots if lay_ui else []))

    # Ce que la scène AFFICHE borne ce qu'elle charge. `None` = indécidable,
    # donc la police entière (et pas de sous-ensemble émis non plus).
    cps = scene_codepoints(p, scene)

    # ── Où chaque police se charge ────────────────────────────────
    # Chacune a SA base : un titre et un corps de texte coexistent à l'écran, et
    # la réservation devient une SOMME (abordable grâce au sous-ensemble).
    #
    # Si l'ensemble des polices est indécidable, on ne sait pas lesquelles
    # coexistent et sommer tout le projet réserverait un charblock pour rien :
    # repli sur le modèle « une seule résidente, base 0 », donc le MAXIMUM.
    from codegen.font_emit import render_composited
    scene_fonts = [(i, f) for i, f in enumerate(fonts)
                   if names is None or f.name in names]
    font_layout: list[dict] = []
    if names is not None:
        base = 0
        for i, f in scene_fonts:
            if render_composited(f):
                continue          # ne charge aucun glyphe : c'est la surface qui coûte
            n = mono_vram_tiles(f, cps)
            colors = scene_text_colors(p, scene, f.name)
            font_layout.append({"index": i, "name": f.name, "base": base,
                                "tiles": n * len(colors), "colors": colors})
            base += n * len(colors)
        mono_tiles = base
    else:
        mono_tiles = scene_text_tiles(fonts, names, cps)

    # Une police COMPOSÉE range ses pixels dans la surface, comme une zone à
    # fond : sans ça `blit_use_bg_surface` retombe sur la base des glyphes et
    # écrase la police mono voisine.
    needs_surface = needs_surface or any(render_composited(f) for _i, f in scene_fonts)

    img_tiles  = sum(a["tiles"] for a in img_assets)
    surf_tiles = TEXT_SURF_TILES if needs_surface else 0

    # Images en cible BG : chacune sa base RELATIVE au bloc, dans l'ordre de la
    # mise en page. Relative comme le reste (glyphes, surface) — la base absolue
    # est celle que l'allocateur donne à la scène, et une même mise en page sert
    # plusieurs scènes qui ne l'ont pas au même endroit.
    ui_images = scene_ui_images(p, scene)
    img_layout: list[dict] = []
    base = 0
    for info in ui_images:
        if not info["bg"]:
            continue
        img_layout.append({"index": info["index"], "name": info["el"].name,
                           "base": base, "tiles": info["tiles"],
                           "sprite": info["sprite"].name,
                           "tiles_per_frame": info["tiles_per_frame"]})
        base += info["tiles"]
    sprite_tiles = base

    return {
        "fills": fills, "fill_indices": fill_indices,
        "img_fills": img_fills, "img_assets": img_assets,
        "mono_tiles": mono_tiles, "needs_surface": needs_surface,
        "font_names": names, "codepoints": cps, "font_layout": font_layout,
        "default_font": default_font,
        "ui_images": ui_images, "img_layout": img_layout,
        "sprite_tiles": sprite_tiles,
        "total": (len(fill_indices) + img_tiles + mono_tiles + surf_tiles
                  + sprite_tiles),
    }


def _apply_vram_layout(p, scene, bgi: list[dict]) -> None:
    """Remplace le placement historique des maps par celui de l'allocateur.

    Écrit `sbb` sur place, et mémorise le placement du texte sur la scène pour
    que `_gen_scene_init` le retrouve — les deux doivent voir EXACTEMENT la même
    allocation, sinon les tuiles et la map du texte partent à des adresses qui
    ne se correspondent plus."""
    from codegen.vram_alloc import scene_layout
    slots = {bi["bg"]: _layer_tiles_used(p, bi) for bi in bgi}
    maps  = {bi["bg"]: bi["map_sbb_count"] for bi in bgi}
    res = scene_text_reservation(p, scene)
    lay = scene_layout(slots, maps, getattr(scene, "text_bg", -1), res["total"])
    for bi in bgi:
        bi["sbb"] = lay.map_sbb[bi["bg"]]
    scene._vram_layout = lay   # consommé par _gen_scene_init
    scene._ui_fills = res["fills"]
    scene._ui_fill_indices = res["fill_indices"]
    scene._ui_mono_tiles = res["mono_tiles"]
    scene._ui_needs_surface = res["needs_surface"]
    scene._ui_img_fills = res["img_fills"]
    scene._ui_img_assets = res["img_assets"]
    scene._ui_images = res["ui_images"]
    scene._ui_image_layout = res["img_layout"]
    scene._ui_reservation = res   # relu par le log de build


def _log_vram_layout(scene, emit) -> None:
    """Dit où l'allocateur a posé le bloc du texte, et pourquoi le cas échéant.

    Émis à CHAQUE build et pas seulement en repli : c'est la première chose
    qu'on cherche quand un fond ne rentre plus."""
    lay = getattr(scene, "_vram_layout", None)
    if lay is None or emit is None:
        return
    budget = ", ".join(f"BG{s}:{n}" for s, n in sorted(lay.budget.items()))
    emit("log_line",
         f"[vram] scène '{scene.name}' : texte en CBB{lay.text_cbb} "
         f"base {lay.text_base}, map SBB{lay.text_sbb} — {lay.note}"
         + (f" — budget tuiles {budget}" if budget else ""))

    # Sur quelle base la place a été réservée : un repli sur tout le projet est
    # un choix de l'outil, sinon on cherche pourquoi le décor a moins de tuiles.
    res = getattr(scene, "_ui_reservation", None)
    if not res:
        return
    names = res.get("font_names")
    if names is None:
        why = ("toutes les polices du projet — une police est choisie au "
               "runtime (text.set_font non littéral) ou un script n'a pas pu "
               "être analysé")
    else:
        why = "polices " + (", ".join(sorted(names)) if names else "(aucune)")
    # Nommer la police par défaut : c'est elle qui est chargée même dans une
    # scène sans une ligne de texte, et un `Scene.font_name` introuvable retombe
    # en silence sur la première du projet. Relue depuis la réservation, pas
    # recalculée — le log doit dire ce qui a RÉELLEMENT servi à réserver.
    _dn = res.get("default_font") or ""
    emit("log_line",
         f"[vram] scène '{scene.name}' : {res['total']} tuile(s) réservée(s) au "
         f"texte ({res['mono_tiles']} de glyphes — {why}"
         + (f" — défaut {_dn}" if _dn else "") + ")")


def _pool_info(prefabs, pool_start: int) -> list[dict]:
    info, offset = [], pool_start
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) > 0:
            s = c_sym(pf.name)
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
            tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
            _vn = _var_names(p)
            bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
            bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
            L += [
                f"            g_actors[_i].boxes[{bi}].x=(s8){bx}; g_actors[_i].boxes[{bi}].y=(s8){by};",
                f"            g_actors[_i].boxes[{bi}].w=(u8){bw};  g_actors[_i].boxes[{bi}].h=(u8){bh};",
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


def _obj_tiles_used(p: Project, sprites: list) -> int:
    """Tuiles de VRAM OBJ occupées par les sprites — donc la 1re tuile libre.

    Recalcule l'accumulation de `_sprite_offsets_for` plutôt que de lui faire
    rendre un total de plus : les deux doivent packer à l'identique, et un
    second compteur à tenir à jour finirait par diverger."""
    seen, total = set(), 0
    for _, sprite in sprites:
        if not sprite or not sprite.asset or sprite.name in seen:
            continue
        seen.add(sprite.name)
        total += sprite.tiles_per_frame * count_frames(p, sprite)
    return total


def ui_image_sprites(p: Project) -> list:
    """[(None, SpriteAsset)] des sprites que les IMAGES d'UI réclament.

    Rendu sous la forme de paires `(actor, sprite)` pour se verser tel quel dans
    `all_sprite_pairs` : les tuiles d'un sprite d'interface arrivent alors en
    VRAM OBJ par le même chemin que celles d'un acteur, et `_sprite_offsets_for`
    lui donne une base dans la même numérotation. Un chemin de chargement à part
    aurait dupliqué le packing — donc, tôt ou tard, l'aurait fait diverger.

    Vaut aussi pour une image en cible BG : ses tuiles sont recopiées dans le
    charblock d'UI, mais le sprite reste résident en OBJ. Le doublon est assumé
    — il n'y a pas de « désallouer une plage OBJ » dans ce packing, et une image
    de HUD partage presque toujours son sprite avec un acteur."""
    out, seen = [], set()
    for _lay, im in (p.all_images() if hasattr(p, "all_images") else []):
        name = getattr(im, "sprite_name", "") or ""
        if not name or name in seen:
            continue
        sprite = p.get_sprite(name)
        if sprite is None or not sprite.asset:
            continue
        seen.add(name)
        out.append((None, sprite))
    return out


def scene_ui_images(p: Project, scene) -> list[dict]:
    """Ce que chaque image de la mise en page d'une scène demande au build.

    Un dict par image RÉSOLUE (sprite existant) : index global dans
    `g_ui_images`, sprite, nombre de frames, cible, et le nombre de tuiles à
    réserver dans le charblock d'UI si elle s'écrit dans la tilemap.

    Les images NON résolues (aucun sprite, ou nom cassé) sont omises et non pas
    réservées à zéro : elles n'existent pas à l'écran, et le validateur le dit
    déjà. Réserver pour elles décalerait la base des suivantes à chaque frappe
    dans le champ « Sprite »."""
    from core.models.ui_region import TARGET_BG
    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    if lay is None:
        return []
    rm = int(getattr(scene, "render_mode", 0) or 0)
    index = {im.name: i for i, (_l, im) in enumerate(p.all_images())}
    out: list[dict] = []
    for im in lay.images:
        sprite = p.get_sprite(getattr(im, "sprite_name", "") or "")
        if sprite is None or not sprite.asset or im.name not in index:
            continue
        frames = count_frames(p, sprite)
        g = ui_item_geometry(im, sprite, frames)
        out.append({
            "el": im, "index": index[im.name], "sprite": sprite,
            "frames": frames, "tiles": g["tiles"],
            "tiles_per_frame": sprite.tiles_per_frame,
            "map_tiles": g["map_tiles"],
            "cols": g["cols"], "rows": g["rows"],
            "frame_w": g["frame_w"], "frame_h": g["frame_h"],
            "bg": lay.resolved_target(im, rm) == TARGET_BG,
        })
    return out


def ui_item_geometry(el, sprite, frames: int = 1) -> dict:
    """Géométrie d'un élément qui pose un sprite, image ou fond de panneau.

    Le modèle ne résout pas les noms d'asset : c'est ici qu'on lui donne la
    taille de frame, seule inconnue qui sépare un `UIImage` (dont le rectangle
    EST la frame) d'un `UIPanel` à fond sprite (dont le rectangle se pave)."""
    from core.models.ui_region import image_geometry
    return image_geometry(el, frames,
                          int(getattr(sprite, "frame_w", 0) or 0),
                          int(getattr(sprite, "frame_h", 0) or 0))


def _obj_text_alloc(p: Project) -> dict:
    """Placement OBJ de chaque zone : {nom: {oam_rel, tile_rel, ...}}.

    Relatif à sa MISE EN PAGE, pas au projet : deux mises en page se partagent
    la même plage réservée puisqu'une seule est active par scène. Sans ça, cinq
    boîtes de dialogue dans cinq mises en page réserveraient cinq fois la place
    alors qu'on n'en voit jamais qu'une."""
    from core.models.ui_region import layout_obj_budget
    out = {}
    for lay in getattr(p, "ui_layouts", []):
        # Les frames ET la taille de frame par image : `layout_obj_budget` ne
        # résout pas les noms d'asset, et sous-réserver ferait écrire une image
        # dans les tuiles de la suivante. La taille de frame commande en plus le
        # PAVAGE d'un fond de panneau, donc son nombre de slots OAM.
        frames, sizes = {}, {}
        for im in lay.images:
            sprite = p.get_sprite(getattr(im, "sprite_name", "") or "")
            if sprite is not None and sprite.asset:
                frames[im.name] = count_frames(p, sprite)
                sizes[im.name] = (int(getattr(sprite, "frame_w", 0) or 0),
                                  int(getattr(sprite, "frame_h", 0) or 0))
        bud = layout_obj_budget(lay, image_frames=frames, image_frame_size=sizes)
        for name, place in bud["place"].items():
            out[name] = place
    return out


def _anim_tables_for(p: Project, sprite: SpriteAsset) -> list[str]:
    """Génère les tables C d'animation pour un SpriteAsset.

    Produit :
      {sym}_anim_dirs[]   — {dir, frame_start, frame_count} par état+direction
      {sym}_state_start[] — index dans anim_dirs où commence chaque état
      {sym}_state_speed[] — speed (ticks) par état
      {sym}_state_loop[]  — loop (0/1) par état
    """
    sym = f"sprite_{c_sym(sprite.name)}"
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
            start = seq_starts[seq_key(src_sd, sd.flip_h, sd.flip_v)]
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
    """Lecture de la carte de collision, et résolution d'un acteur contre elle.

    La table de profils est ÉMISE depuis `core.models.collision_tiles`, la même
    géométrie que celle dont le canvas tire ses polygones : la physique du jeu
    et le dessin de l'éditeur ne peuvent pas diverger."""
    from core.models.collision_tiles import (
        TILE_COUNT, kind_of, column_surfaces, speed_scale,
    )
    L = [
        "static const u8 *g_active_cmap = NULL;",
        "static int g_cmap_w = 0, g_cmap_h = 0;",
        "#define TILE_SIZE 8",
        "",
        "/* Profil des types de tuiles — ÉMIS depuis core/models/collision_tiles.py,",
        "   jamais écrit à la main ici : c'est la même géométrie que celle que",
        "   l'éditeur dessine. `surface` porte l'ordonnée de la surface dans",
        "   chacune des 8 colonnes de pixels ; pour un SOL la matière va de là au",
        "   bas de la tuile (8 = colonne vide), pour un PLAFOND du haut jusque-là",
        "   (0 = colonne vide). */",
        "#define TK_EMPTY 0",
        "#define TK_SOLID 1",
        "#define TK_FLOOR 2",
        "#define TK_CEIL  3",
    ]
    kinds = ", ".join(str(kind_of(t)) for t in range(TILE_COUNT))
    L.append(f"static const u8 g_tile_kind[{TILE_COUNT}] = {{ {kinds} }};")
    # Cosinus de la pente en virgule fixe 8 bits — 256 à plat. Un pas horizontal
    # sur une pente parcourt √(1+p²) fois plus de distance qu'à plat ; c'est ce
    # facteur qui le ramène à la distance demandée. Précalculé ici : pas de
    # racine carrée à l'exécution, et la table est la même géométrie que le reste.
    # u16 et non u8 : « plat » vaut 256, qui ne tient pas dans un octet.
    scales = ", ".join(str(speed_scale(t)) for t in range(TILE_COUNT))
    L.append(f"static const u16 g_tile_scale[{TILE_COUNT}] = {{ {scales} }};")
    L.append(f"static const u8 g_tile_surface[{TILE_COUNT}][TILE_SIZE] = {{")
    for t in range(TILE_COUNT):
        row = ", ".join(f"{v}" for v in column_surfaces(t))
        L.append(f"    {{ {row} }},")
    L += [
        "};",
        "",
        "int tile_get(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 0;",
        "    return (int)g_active_cmap[ty*g_cmap_w+tx];",
        "}",
        "/* Le seul type qui REPOUSSE horizontalement. Une pente n'est pas un mur,",
        "   sinon personne ne la gravirait : on y monte par la surface. */",
        "static int tile_wall_at(int px,int py){",
        "    if(!g_active_cmap) return 0;",
        "    int tx=px/TILE_SIZE, ty=py/TILE_SIZE;",
        "    if(tx<0||ty<0||tx>=g_cmap_w||ty>=g_cmap_h) return 1;",
        "    return g_active_cmap[ty*g_cmap_w+tx]==TK_SOLID;",
        "}",
        "/* Ordonnée monde du DESSUS de la matière portant la colonne px.",
        "",
        "   Trois tuiles balayées de haut en bas, la PREMIÈRE trouvée gagnant : celle",
        "   au-dessus des pieds, celle des pieds, celle du dessous. La tuile du DESSUS",
        "   est indispensable — sur une pente, la matière de la colonne suivante vit",
        "   dans la tuile d'au-dessus, et s'arrêter aux pieds fait décrocher l'acteur",
        "   en pleine montée. Une surface plus haute que la box est écartée (`>=top`) :",
        "   elle ne touche pas l'acteur, et l'y hisser le téléporterait sur une",
        "   plateforme qu'il passait dessous.",
        "",
        "   Hors carte par le bas = plein : le monde est une boîte close, comme avant",
        "   que la résolution ne connaisse les pentes. Sans ça un acteur qui rate une",
        "   plateforme tombe indéfiniment — et son sprite reboucle en haut de l'écran,",
        "   l'OAM ne codant Y que sur 8 bits. -1 = rien à portée. */",
        "/* Type de la tuile qui a fourni la dernière surface rendue par",
        "   tile_floor_at — c'est elle qui porte l'acteur, donc elle qui dit à",
        "   quelle pente il marche. Rendu à côté plutôt qu'en valeur de retour :",
        "   un seul appelant s'en sert, et le balayage n'est pas fait deux fois. */",
        "static u8 g_floor_tile = 0;",
        "static int tile_floor_at(int px,int top,int bot){",
        "    g_floor_tile=0;",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=-1;i<2;i++){",
        "        int ty=bot/TILE_SIZE+i;",
        "        if(ty<0) continue;",
        "        if(ty>=g_cmap_h) return g_cmap_h*TILE_SIZE;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID){ if(ty*TILE_SIZE>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE;} continue; }",
        "        if(g_tile_kind[t]==TK_FLOOR){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s<TILE_SIZE && ty*TILE_SIZE+s>=top){g_floor_tile=(u8)t; return ty*TILE_SIZE+s;}",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "/* Symétrique : ordonnée du DESSOUS de la matière au-dessus de la tête.",
        "   Le balayage part de la tête et MONTE — jamais vers le bas, sinon le sol",
        "   sur lequel l'acteur repose serait pris pour un plafond et le pousserait",
        "   dedans. Hors carte par le haut = plein, même boîte close. */",
        "static int tile_ceil_at(int px,int py){",
        "    if(!g_active_cmap) return -1;",
        "    int tx=px/TILE_SIZE;",
        "    if(tx<0||tx>=g_cmap_w) return -1;",
        "    for(int i=0;i<2;i++){",
        "        int ty=py/TILE_SIZE-i;",
        "        if(ty>=g_cmap_h) continue;",
        "        if(ty<0) return 0;",
        "        int t=g_active_cmap[ty*g_cmap_w+tx];",
        "        if(t==TK_SOLID) return ty*TILE_SIZE+TILE_SIZE;",
        "        if(g_tile_kind[t]==TK_CEIL){",
        "            int s=g_tile_surface[t][px&(TILE_SIZE-1)];",
        "            if(s>0) return ty*TILE_SIZE+s;",
        "        }",
        "    }",
        "    return -1;",
        "}",
        "typedef void (*TileCollideCb)(Actor*,int,int);",
        "/* Résolution d'un acteur contre la carte (cf. ROADMAP v0.6.3).",
        "   L'ordre est la règle : X d'abord — les pentes n'y font pas obstacle —",
        "   puis Y, où la surface est cherchée en TROIS points (les deux coins bas",
        "   et le centre), la plus haute l'emportant : un acteur large ne s'enfonce",
        "   pas dans la pente et franchit une arête proprement.",
        "   `cb` ne fait que PRÉVENIR : la vitesse est annulée dans tous les cas,",
        "   écrire le hook ne désactive donc pas la physique. */",
        "static void __attribute__((unused)) resolve_actor_tiles(Actor*a, TileCollideCb cb){",
        "    if(!g_active_cmap) return;",
        "    int was_grounded=a->grounded, dx=a->x-a->last_x;",
        "    int moved=dx<0?-dx:dx;",
        "    /* ── Vitesse constante LE LONG du sol ─────────────────────",
        "       Un pas horizontal sur une pente parcourt √(1+p²) fois plus de",
        "       distance qu'à plat : 114 % à 26°, 141 % à 45°, 224 % à 63°. Sans",
        "       correction, plus la pente est raide plus le personnage paraît",
        "       rapide. On ramène donc le pas au cosinus de la pente qu'il",
        "       gravit, lu dans g_tile_scale.",
        "",
        "       Deux garde-fous, parce que le moteur DÉFAIT ici une partie de ce",
        "       que le script a demandé :",
        "         - il faut être au sol à la frame précédente — un saut, une",
        "           chute ou un vol ne sont pas une marche ;",
        "         - le pas doit tenir dans une tuile. Au-delà, la résolution ne",
        "           prétend déjà plus rien (la sonde ne porte qu'à une tuile), et",
        "           c'est là qu'un script téléporte plutôt qu'il ne marche.",
        "       Le reste (1/256 de pixel) est REPORTÉ : sans lui, un pas de 2 px",
        "       à 45° tomberait toujours sur 1 px, et le personnage ramperait au",
        "       lieu d'aller 1,41 fois moins vite. */",
        "    if(was_grounded && dx && moved<=TILE_SIZE){",
        "        for(int i=0;i<a->box_count;i++){",
        "            CollisionBox*b=&a->boxes[i];",
        "            if(!b->solid) continue;",
        "            int l=a->last_x+(int)b->x, r=l+(int)b->w-1;",
        "            int t=a->y+(int)b->y;",
        "            tile_floor_at((l+r)>>1, t, t+(int)b->h-1);",
        "            int sc=g_tile_scale[g_floor_tile];",
        "            if(sc<256){",
        "                int want=dx*sc+a->slope_acc;",
        "                int step=want/256;",
        "                a->slope_acc=want-step*256;",
        "                a->x=a->last_x+step;",
        "            }",
        "            break;",
        "        }",
        "    }else a->slope_acc=0;",
        "    a->grounded=0;",
        "    for(int i=0;i<a->box_count;i++){",
        "        CollisionBox*b=&a->boxes[i];",
        "        if(!b->solid) continue;",
        "        int left,right,top,bot;",
        "        /* ── X : seuls les blocs pleins repoussent ───────────── */",
        "        if(a->vx!=0){",
        "            left=a->x+(int)b->x; right=left+(int)b->w-1;",
        "            top =a->y+(int)b->y; bot  =top +(int)b->h-1;",
        "            int hit=0;",
        "            if(a->vx>0){",
        "                for(int py=top;py<=bot&&!hit;py+=TILE_SIZE) hit=tile_wall_at(right,py);",
        "                if(!hit) hit=tile_wall_at(right,bot);",
        "                if(hit){a->x=(right/TILE_SIZE)*TILE_SIZE-(int)b->x-(int)b->w;",
        "                    a->vx=0; if(cb)cb(a,1,0);}",
        "            }else{",
        "                for(int py=top;py<=bot&&!hit;py+=TILE_SIZE) hit=tile_wall_at(left,py);",
        "                if(!hit) hit=tile_wall_at(left,bot);",
        "                if(hit){a->x=(left/TILE_SIZE+1)*TILE_SIZE-(int)b->x;",
        "                    a->vx=0; if(cb)cb(a,-1,0);}",
        "            }",
        "        }",
        "        /* ── Plafond : la surface la plus BASSE arrête la tête ─ */",
        "        left=a->x+(int)b->x; right=left+(int)b->w-1;",
        "        top =a->y+(int)b->y; bot  =top +(int)b->h-1;",
        "        if(a->vy<0){",
        "            int c=-1;",
        "            for(int k=0;k<3;k++){",
        "                int px=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "                int cy=tile_ceil_at(px,top);",
        "                if(cy>c) c=cy;",
        "            }",
        "            if(c>=0&&top<c){a->y=c-(int)b->y; a->vy=0; if(cb)cb(a,0,-1);}",
        "        }",
        "        /* ── Sol : la surface la plus HAUTE porte l'acteur ───── */",
        "        top=a->y+(int)b->y; bot=top+(int)b->h-1;",
        "        int g=-1;",
        "        for(int k=0;k<3;k++){",
        "            int px=(k==0)?left:((k==1)?((left+right)>>1):right);",
        "            int gy=tile_floor_at(px,top,bot);",
        "            if(gy>=0&&(g<0||gy<g)) g=gy;",
        "        }",
        "        if(g>=0){",
        "            int feet=bot+1;",
        "            if(feet>g){",
        "                /* Pénétration : on remonte sur la surface. Aucun plafond",
        "                   de marche — l'auteur a peint une pente, on la gravit. */",
        "                a->y=g-(int)b->y-(int)b->h;",
        "                if(a->vy>0) a->vy=0;",
        "                a->grounded=1; if(cb)cb(a,0,1);",
        "            }else if(feet==g){",
        "                /* Pile sur la surface : au sol, et une vitesse vers le",
        "                   bas n'a plus de sens — sans ça elle survit une frame",
        "                   de plus et l'acteur retraverse le sol avant d'être",
        "                   repoussé. */",
        "                if(a->vy>0) a->vy=0;",
        "                a->grounded=1;",
        "            }else if(was_grounded&&a->vy>=0&&g-feet<=moved*2+1){",
        "                /* Collage en descente : l'écart maximal qu'une pente à",
        "                   63° peut creuser pour ce déplacement. Sans lui, toute",
        "                   descente décolle et retombe, donc tressaute. */",
        "                a->y=g-(int)b->y-(int)b->h;",
        "                a->grounded=1;",
        "            }",
        "        }",
        "    }",
        "    a->last_x=a->x;",
        "}",
        "",
    ]
    return L


# ─── Helpers affine / origine ─────────────────────────────────────────────────

def _has_solid_box(owner) -> bool:
    """Cet acteur (ou prefab) a-t-il une box PHYSIQUE ?

    C'est ce qui lui donne droit à la résolution contre la carte de collision —
    la définition que le modèle donne déjà de `solid` (cf. components.py)."""
    return any(getattr(c, "solid", False) and getattr(c, "active", True)
               and hasattr(c, "w") for c in getattr(owner, "components", []))


def _scene_has_cmap(scene) -> bool:
    """Carte de collision réellement peuplée — une grille de zéros n'est pas une
    carte, et n'a rien à faire heurter."""
    cmap = getattr(scene, "collision_map", None) or []
    return any(v != 0 for row in cmap for v in row)


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


def camera_sym(name: str) -> str:
    """Symbole C d'une caméra — préfixé, les caméras et les acteurs partageant
    le même espace de noms C."""
    return f"camera_{c_sym(name)}"


def project_cameras(p) -> list:
    """Les caméras du projet dans l'ordre de la TABLE runtime, `None` en tête.

    Ce `None` est la caméra par défaut : fixe à l'origine, sans bornes ni
    suivi, et sans fichier sur le disque — une scène qui n'en désigne aucune
    tombe dessus. La donner comme entrée 0 plutôt que comme cas particulier
    évite un `if` à chaque endroit qui active une caméra.

    Source de vérité partagée : `main_gen` émet la table dans cet ordre et
    `headers` en dérive les `#define CAM_*`, sinon `camera.switch` viserait la
    mauvaise caméra."""
    return [None] + list(getattr(p, "cameras", []))


def scene_camera_index(p, scene) -> int:
    """Index de la caméra de démarrage d'une scène dans la table runtime.

    Un nom qui ne résout pas retombe sur 0 (la caméra par défaut) plutôt que de
    faire échouer le build : le validateur signale la référence cassée, et un
    jeu qui compile encore reste débuggable."""
    name = getattr(scene, "camera", "")
    if not name:
        return 0
    cams = project_cameras(p)
    return next((i for i, c in enumerate(cams) if c is not None and c.name == name), 0)


def camera_target_index(p, camera, scene_actors: list, actor_offset: int) -> int:
    """Index dans `g_actors` de l'acteur suivi par cette caméra DANS CETTE
    SCÈNE, ou -1.

    Une caméra est réutilisable et cite sa cible par nom ; les noms d'acteurs
    sont locaux à une scène. La résolution est donc faite par couple
    (scène, caméra), et une scène sans acteur de ce nom laisse simplement la
    caméra immobile."""
    if camera is None or camera.mode != "follow" or not camera.follow_target:
        return -1
    local = next((j for j, (a, _) in enumerate(scene_actors)
                  if a.name == camera.follow_target), None)
    return -1 if local is None else actor_offset + local


def _camera_follow_lines(p, scene, scene_actors: list, actor_offset: int) -> list[str]:
    """Le suivi déclaratif de la frame, pour la caméra ACTIVE.

    Un `switch` plutôt qu'une table de cibles lue au runtime : la cible et la
    zone morte deviennent des constantes, et seules les caméras qui peuvent
    réellement suivre quelqu'un DANS CETTE SCÈNE ont un cas. Une scène où
    aucune caméra n'a de cible n'émet rien du tout."""
    cases: list[str] = []
    for i, cam in enumerate(project_cameras(p)):
        t = camera_target_index(p, cam, scene_actors, actor_offset)
        if t < 0:
            continue
        # Axe désactivé (scroll_h/scroll_v) : la cible sur cet axe devient
        # cam_x/cam_y lui-même → écart nul → camera_follow ne le bouge pas.
        tx = f"g_actors[{t}].x" if scene.scroll_h else "cam_x"
        ty = f"g_actors[{t}].y" if scene.scroll_v else "cam_y"
        cases.append(f"        case {i}: camera_follow({tx}, {ty}, "
                     f"{int(cam.margin_x)}, {int(cam.margin_y)}); break;"
                     f"   /* {cam.name} → {cam.follow_target} */")
    if not cases:
        return []
    return ["    switch(g_cam_active){"] + cases + ["        default: break;", "    }"]


def project_fonts(p) -> list:
    """Polices réellement encodables (planche présente sur disque).

    Source de vérité partagée : `main_gen` émet les tables dans cet ordre et
    `lua_compiler` en dérive les `#define FONT_*` — les deux doivent voir la
    même liste, sinon un script pointerait sur la mauvaise police."""
    out = []
    for f in getattr(p, "fonts", []):
        if f.asset and f.glyphs and p.asset_abs(f.asset) and p.asset_abs(f.asset).exists():
            out.append(f)
    return out


def _emit_font_subsets(p, encoded: list, emit=None) -> list[str]:
    """Tableaux C des sous-ensembles de glyphes, une entrée par (scène, police).

    Émis ici parce que c'est le seul endroit qui tient les polices ENCODÉES : un
    sous-ensemble parle en index de glyphe encodé, pas en glyphe de la planche.
    Le nom des descripteurs est mémorisé sur la scène, relu par
    `_gen_scene_init` pour poser les `text_set_subset`.

    Pas de sous-ensemble pour une police composée (elle ne charge aucun glyphe)
    ni pour une scène indécidable (police entière, déjà réservée)."""
    from codegen.font_emit import (build_font_subset, scene_codepoints,
                                   scene_font_names, scene_default_font)
    from codegen.c_names import c_ident
    fonts = project_fonts(p)
    if not fonts or not encoded:
        return []
    by_name = {name: (i, e) for i, (name, e) in enumerate(encoded)}

    L: list[str] = ["/* ── Sous-ensembles de glyphes (par scène) ───────── */"]
    any_line = False
    for scene in p.scenes:
        scene._ui_font_subsets = {}
        cps = scene_codepoints(p, scene)
        if cps is None:
            if emit:
                emit("log_line",
                     f"[font] scène '{scene.name}' : polices chargées ENTIÈRES "
                     f"— ce qu'elle affiche n'est pas déterminable au build")
            continue
        names = scene_font_names(p, scene, scene_default_font(p, scene)[1])
        for fname in sorted(names or [f.name for f in fonts]):
            if fname not in by_name:
                continue
            fi, e = by_name[fname]
            sub = build_font_subset(e, cps)
            if sub is None or not sub["load"]:
                continue
            colors = scene_text_colors(p, scene, fname)
            sym = f"g_fsub_{c_ident(scene.name)}_{c_ident(fname)}"
            L.append(f"static const unsigned short {sym}_slot[{len(sub['slot'])}] = {{"
                     + ",".join(str(v) for v in sub["slot"]) + "};")
            L.append(f"static const unsigned short {sym}_load[{len(sub['load'])}] = {{"
                     + ",".join(str(v) for v in sub["load"]) + "};")
            L.append(f"static const unsigned char {sym}_var[{len(colors)}] = {{"
                     + ",".join(str(c) for c in colors) + "};")
            L.append(f"static const FontSubset {sym} = {{ {sym}_slot, {sym}_load, "
                     f"{len(sub['load'])}, {len(colors)}, {sym}_var }};")
            scene._ui_font_subsets[fi] = sym
            any_line = True
            if emit:
                extra = ("" if len(colors) == 1 else
                         f", ×{len(colors)} couleurs {colors[1:]}")
                emit("log_line",
                     f"[font] scène '{scene.name}' : '{fname}' réduite à "
                     f"{len(sub['load'])} tuile(s) sur {e['n_tiles']}{extra}")
    return L + [""] if any_line else []


def _fonts_and_texts_lines(p, emit=None) -> list[str]:
    """Tables C des polices, des textes et des zones (cf. codegen/font_emit)."""
    from codegen.font_emit import (encode_font, emit_fonts_c, emit_texts_c,
                                   emit_ui_regions_c)

    encoded = []
    for f in project_fonts(p):
        try:
            e = encode_font(f, p.asset_abs(f.asset))
        except Exception as exc:
            if emit:
                emit("error_line", f"[font] {f.name} : encodage impossible ({exc})")
            continue
        if e.get("warning") and emit:
            emit("log_line", f"[font] {e['warning']}")
        if emit:
            # Le CHEMIN de rendu autant que le coût VRAM : une police composée
            # ne charge aucune tuile, c'est la surface qui coûte. Sans ça un
            # basculement automatique (police trop grosse) passe inaperçu.
            from codegen.font_emit import render_composited, font_vram_tiles
            mode = "composition" if render_composited(f) else "tilemap"
            emit("log_line", f"[font] {f.name} -> {e['n_tiles']} tuiles, "
                             f"{len(e['codepoints'])} glyphes, rendu {mode}, "
                             f"{font_vram_tiles(f)} tuiles VRAM")
        encoded.append((f.name, e))

    # Même liste que celle dont `lua_compiler` dérive les `#define` : l'ordre
    # fait l'index.
    texts = list(p.build_texts() if hasattr(p, "build_texts")
                 else getattr(p, "texts", []))
    if emit and texts:
        emit("log_line", f"[text] {len(texts)} entrée(s) de texte")

    regions = p.all_regions() if hasattr(p, "all_regions") else []
    if emit and regions:
        from core.models.ui_region import KIND_TEXT
        n_auth = sum(1 for _l, r in regions if getattr(r, "kind", "") == KIND_TEXT)
        detail = f", dont {n_auth} texte(s) authoré(s)" if n_auth else ""
        emit("log_line", f"[text] {len(regions)} slot(s) de texte{detail} "
                         f"({len(p.ui_layouts)} mise(s) en page)")
    font_names = [f.name for f in project_fonts(p)]
    subset_lines = _emit_font_subsets(p, encoded, emit)
    return (emit_fonts_c(encoded) + subset_lines
            + emit_texts_c(texts, p.globals, p.constants, emit,
                           fonts=project_fonts(p))
            + emit_ui_regions_c(regions, font_names, emit,
                                obj_place=_obj_text_alloc(p),
                                actor_index=_region_actor_index(p),
                                bg_fill=_region_bg_fills(p)[0])
            + _palettes_lines(p, emit))


def _palettes_lines(p, emit=None) -> list[str]:
    """Table `g_palettes` — le catalogue de couleurs, pour `palette.set_bg/obj`.

    Le catalogue ENTIER, dans son ordre, celui-là même dont `lua_compiler` dérive
    les `#define PAL_*` : les deux doivent voir la même liste ou l'index désigne
    une autre palette.

    Émis en entier plutôt que dérivé des scripts — contrairement aux polices, où
    la réservation doit être calculée parce qu'elle coûte de la mémoire vidéo.
    Une palette pèse 32 octets en ROM ; réserver pour tout le catalogue est moins
    cher que le risque de réserver trop peu, qui ferait basculer vers une palette
    absente sans erreur avant l'exécution."""
    banks = list(getattr(p, "palettes", []))
    L = ["", "/* Palettes du catalogue — palette.set_bg / palette.set_obj */"]
    L.append(f"const unsigned short g_palettes[{max(1, len(banks))}][16] = {{")
    for b in banks:
        cols = list(b.colors or [])[:16]
        cols += [0] * (16 - len(cols))
        L.append("    {" + ",".join(f"0x{c & 0xFFFF:04X}" for c in cols) + "},")
    if not banks:
        L.append("    {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0},")
    L.append("};")
    L.append(f"const int g_palette_count = {max(1, len(banks))};")
    L.append("")
    if emit and banks:
        emit("log_line", f"[palette] {len(banks)} palette(s) du catalogue en ROM "
                         f"({len(banks) * 32} octets)")
    return L


# ── Sauvegarde (SRAM) ─────────────────────────────────────────────
# Trois tableaux parallèles, une entrée par variable globale marquée
# persistante : son id (l'identité qui traverse les versions du jeu), son index
# GLOBAL_* (par où le moteur la lit et l'écrit) et son défaut (ce qu'elle vaut
# si le fichier chargé ne la contient pas).

SAVE_HEADER_BYTES = 12
SAVE_RECORD_BYTES = 8
SRAM_BYTES        = 32768


def save_vars(p) -> list[tuple[int, object]]:
    """Les globales persistantes, avec leur INDEX dans `p.globals` — celui-là
    même dont `globals.h` tire `GLOBAL_<NOM>`. Les deux listes doivent voir le
    même ordre ou l'index désigne une autre variable."""
    return [(i, g) for i, g in enumerate(getattr(p, "globals", []))
            if getattr(g, "persist", False)]


def save_id32(vid: int) -> int:
    """L'id opaque replié sur 32 bits. Il en fait 12 chiffres (jusqu'à ~2^40) et
    la SRAM se lit par mots de 32 bits : c'est un repli DÉTERMINISTE, pas un
    hachage — deux builds du même projet donnent le même. Une collision entre
    deux variables persistantes bloque le build (cf. `save_fatal`), sinon elle
    ne se verrait qu'en jeu, sous la forme d'une variable qui prend la valeur
    d'une autre."""
    return int(vid) & 0xFFFFFFFF


def save_slot_size(p) -> int:
    return SAVE_HEADER_BYTES + SAVE_RECORD_BYTES * len(save_vars(p))


def save_fatal(p) -> list[str]:
    """Ce qui rend la sauvegarde impossible à émettre. Bloquant, comme le budget
    de tuiles : une sauvegarde qui déborde de la SRAM n'échouerait qu'à
    l'exécution, chez le joueur."""
    out: list[str] = []
    vars_ = save_vars(p)
    if not vars_:
        return out
    seen: dict[int, str] = {}
    for _i, g in vars_:
        k = save_id32(g.id)
        if k in seen:
            out.append(
                f"[error] les variables persistantes « {seen[k]} » et "
                f"« {g.name} » retombent sur le même identifiant de sauvegarde. "
                f"Renommer n'y changera rien — recréer l'une des deux lui donne "
                f"un nouvel identifiant.")
        seen[k] = g.name
    slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    total = slots * save_slot_size(p)
    if total > SRAM_BYTES:
        out.append(
            f"[error] {slots} emplacement(s) de sauvegarde × {len(vars_)} "
            f"variable(s) demandent {total} octets, soit plus que les "
            f"{SRAM_BYTES} de la SRAM. Réduire le nombre d'emplacements ou de "
            f"variables persistantes.")
    return out


def _save_lines(p, emit=None) -> list[str]:
    """Tables de sauvegarde + chaîne de détection du support.

    Les tableaux sont émis MÊME VIDES (une entrée neutre) : le pilote de
    `gba_engine.h` les déclare `extern` sans condition, et un projet sans
    variable persistante doit tout de même se lier. C'est `g_save_count == 0`
    qui dit au moteur de ne pas toucher la SRAM."""
    vars_ = save_vars(p)
    slots = max(1, int(getattr(p.settings, "save_slots", 1)))
    L = ["", "/* Sauvegarde — variables globales marquées persistantes */"]
    if vars_:
        # La chaîne que cherchent émulateurs et linkers pour savoir de quel type
        # de sauvegarde la cartouche dispose. Émise SEULEMENT si le projet sauve
        # quelque chose : un jeu sans sauvegarde ne doit pas faire naître un
        # fichier .sav vide chez le joueur. `used` parce que rien ne la
        # référence — sans ça l'éditeur de liens la retire et la détection
        # échoue silencieusement.
        L += ['static const char __attribute__((used, aligned(4)))',
              '    g_save_type[] = "SRAM_V113";', ""]
        L.append("const unsigned int g_save_id[] = {"
                 + ", ".join(f"0x{save_id32(g.id):08X}" for _i, g in vars_) + "};")
        L.append("const unsigned short g_save_idx[] = {"
                 + ", ".join(str(i) for i, _g in vars_) + "};")
        L.append("const int g_save_def[] = {"
                 + ", ".join(str(int(g.default)) for _i, g in vars_) + "};")
    else:
        L += ["const unsigned int   g_save_id[]  = {0};",
              "const unsigned short g_save_idx[] = {0};",
              "const int            g_save_def[] = {0};"]
    L.append(f"const int g_save_count = {len(vars_)};")
    L.append(f"const int g_save_slots = {slots if vars_ else 0};")
    L.append(f"const int g_save_slot_size = {save_slot_size(p) if vars_ else 0};")
    L.append("")
    if emit and vars_:
        emit("log_line",
             f"[save] {len(vars_)} variable(s) persistante(s), {slots} "
             f"emplacement(s) de {save_slot_size(p)} octets "
             f"({slots * save_slot_size(p)} sur {SRAM_BYTES} de SRAM)")
    return L


def _ui_images_lines(p, sprite_offsets: dict, emit=None) -> list[str]:
    """Table des images + leurs constantes. Séparée de `_fonts_and_texts_lines`
    parce qu'elle a besoin de `sprite_offsets`, qui n'est connu qu'une fois
    l'union des sprites faite — donc bien plus tard dans le pipeline."""
    images = p.all_images() if hasattr(p, "all_images") else []
    if emit and images:
        from core.models.ui_region import KIND_PANEL
        n_bound = sum(1 for _l, im in images if getattr(im, "sprite_name", ""))
        n_fill = sum(1 for _l, im in images
                     if getattr(im, "kind", "") == KIND_PANEL)
        emit("log_line", f"[ui] {len(images)} sprite(s) d'interface "
                         f"(dont {n_fill} fond(s) de conteneur), "
                         f"{n_bound} relié(s) à un sprite")
    return emit_ui_images_c(p, sprite_offsets, _obj_text_alloc(p),
                            actor_index=_region_actor_index(p), emit=emit)


def emit_ui_images_c(p: Project, sprite_offsets: dict, obj_place: dict,
                     actor_index: dict | None = None, emit=None) -> list[str]:
    """Table `g_ui_images` — une entrée par image du projet, dans l'ordre de
    `Project.all_images()`, qui fait l'index (donc la constante `IMAGE_*`).

    Ce que l'entrée porte, et ce qu'elle NE porte pas : la géométrie, la cible,
    l'état de départ, et des POINTEURS vers les tables d'animation du sprite —
    les mêmes que celles des acteurs (`sprite_X_anim_dirs`, `_state_start`,
    `_state_speed`, `_state_loop`). Ni vitesse ni liste de frames recopiées :
    l'image désigne un sprite, elle ne le redéfinit pas.

    La base de tuiles est celle de l'OBJ VRAM (`sprite_offsets`), valable pour
    une image en cible OBJ. Une image BG lit une AUTRE base, posée par
    `scene_init` (`ui_image_set_bg_base`) : elle dépend du charblock alloué à la
    scène, et la table, elle, est partagée par toutes les scènes.

    Une image sans sprite résoluble sort une entrée NEUTRE plutôt que d'être
    omise : l'index doit rester celui de `all_images()`, sinon `IMAGE_*` désigne
    l'élément d'à côté. Le runtime la voit `n_states == 0` et ne dessine rien."""
    rows: list[str] = []
    images = p.all_images() if hasattr(p, "all_images") else []
    for lay, im in images:
        sprite = p.get_sprite(getattr(im, "sprite_name", "") or "")
        eff_anchor, eff_actor = lay.effective_anchor(im)
        from core.models.ui_region import ANCHORS, TARGET_OBJ
        target_obj = lay.resolved_target(im) == TARGET_OBJ
        x, y = im.x, im.y
        if not target_obj:
            x, y, _res = lay.absolute_origin(im, None)
            x -= x % 8
            y -= y % 8
        if sprite is None or not sprite.asset:
            rows.append(f"    {{ {x}, {y}, {im.w}, {im.h}, 0, 0, -1, "
                        f"0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0 }},"
                        f"  /* {im.name} — aucun sprite */")
            if emit:
                emit("log_line", f"[ui] image '{im.name}' : aucun sprite — "
                                 f"rien ne sera dessiné à cet endroit.")
            continue
        ss = f"sprite_{c_sym(sprite.name)}"
        n_states = max(1, len(getattr(sprite, "states", []) or []))
        st0 = im.state_index(sprite)
        base = sprite_offsets.get(sprite.name, 0)
        pl = obj_place.get(im.name) if target_obj else None
        oam_rel = pl["oam_rel"] if pl else 0
        # `w`/`h` de la table sont ceux de la FRAME, pas du rectangle : c'est ce
        # que le matériel dessine, et le pavage se dit en `cols`/`rows`. Pour un
        # UIImage les deux coïncident (cf. sync_size_from) ; pour un panneau non.
        g = ui_item_geometry(im, sprite, 1)
        rows.append(
            f"    {{ {x}, {y}, {g['frame_w']}, {g['frame_h']}, "
            f"{1 if target_obj else 0}, "
            f"{ANCHORS.index(eff_anchor)}, {(actor_index or {}).get(im.name, -1)}, "
            f"{ss}_anim_dirs, {ss}_state_start, {ss}_state_speed, {ss}_state_loop, "
            f"{n_states}, {st0}, {1 if im.playing else 0}, "
            f"{base}, {sprite.tiles_per_frame}, {oam_rel}, {im.priority}, "
            f"{g['cols']}, {g['rows']}, {int(getattr(im, 'anim_speed', 0) or 0)} }},"
            f"  /* {im.name} — {sprite.name}"
            + (f", pavage {g['cols']}×{g['rows']}"
               if g['cols'] * g['rows'] > 1 else "") + " */")
        if emit and eff_anchor == "actor" and (actor_index or {}).get(im.name, -1) < 0:
            # Même angle mort que pour une zone de texte : sans acteur résolu,
            # l'image se pose à l'origine de l'écran, ce qui ressemble à un bug
            # de placement plutôt qu'à une référence introuvable.
            emit("log_line",
                 f"[warn] image '{im.name}' : ancrée sur l'actor "
                 f"'{eff_actor or '(aucun)'}', introuvable dans la scène — elle "
                 f"se posera à l'origine de l'écran.")
    L = ["/* ── Images d'interface (UILayout) ─────────────── */"]
    L.append(f"const UIImageInfo g_ui_images[{max(1, len(rows))}] = {{")
    L += rows or ["    { 0, 0, 8, 8, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,"
                  " 1, 1, 0 },   /* aucune image */"]
    L.append("};")
    L.append(f"const int g_ui_image_count = {len(rows)};")
    L.append("")
    return L


def _region_actor_index(p: Project) -> dict:
    """{nom de zone: index global dans g_actors} pour les zones ancrées actor.

    Résolu contre la PREMIÈRE scène qui référence la mise en page. Une mise en
    page partagée par deux scènes où l'acteur n'a pas le même index global
    donnerait deux réponses ; on prend la première et on le signale, plutôt que
    d'ajouter une indirection par scène pour un cas qui n'existe pas encore
    (une bulle est en pratique dans la mise en page de sa scène)."""
    out: dict = {}
    offset = 0
    for scene in p.scenes:
        lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
        actors = [a for a in getattr(scene, "actors", [])]
        if lay is not None:
            names = {a.name: offset + i for i, a in enumerate(actors)}
            # Textes ET images : toutes deux se posent au pixel quand elles
            # suivent un acteur, et un second index les ferait diverger.
            for r in lay.slots + lay.images:
                # L'ancrage vient du ROOT (un enfant en hérite), plus de
                # l'élément lui-même — cohérent avec l'éditeur.
                eff_anchor, eff_actor = lay.effective_anchor(r)
                if eff_anchor == "actor" and r.name not in out:
                    out[r.name] = names.get(eff_actor, -1)
        offset += len(actors)
    return out


def _region_bg_fills(p: Project) -> tuple[dict, dict]:
    """({nom de zone: index dans FONT_PAL_BANK}, {index: couleur BGR555}) pour
    les zones de texte dont un panel ANCÊTRE porte un fond couleur.

    Le texte se compose alors sur cette couleur (cf. runtime g_ui_fill_bg). Les
    index sont réservés PROJET-GLOBAL, depuis le haut de la banque de police (15,
    14, …) : `g_ui_regions` est une table partagée entre scènes, donc l'index
    d'une zone doit être le même partout. La couleur, elle, est réécrite par
    chaque scène à l'init."""
    from core.models.ui_region import KIND_PANEL, FILL_COLOR
    by_name: dict = {}
    color_index: dict = {}      # couleur BGR555 -> index
    nxt = 15
    for lay, r in (p.all_regions() if hasattr(p, "all_regions") else []):
        col = None
        for anc_name in lay.ancestors(r.name):
            anc = lay.get(anc_name)
            if (getattr(anc, "kind", "") == KIND_PANEL
                    and getattr(anc, "fill_kind", "") == FILL_COLOR):
                bank = p.get_palette(getattr(anc, "fill_palette", ""))
                idx = int(getattr(anc, "fill_index", 0) or 0)
                if bank and 0 <= idx < len(bank.colors):
                    col = bank.colors[idx]
                break
        if col is None:
            continue
        if col not in color_index:
            if nxt < 1:            # banque de police pleine : on ne réserve plus
                continue
            color_index[col] = nxt
            nxt -= 1
        by_name[r.name] = color_index[col]
    return by_name, {i: c for c, i in color_index.items()}


def _gen_ui_texts(p: Project, scene, text_bg: int, emit=None) -> list[str]:
    """Appels `text_draw_in` des textes AUTHORÉS de la mise en page d'une scène.

    Le build émet exactement l'appel que l'auteur aurait tapé — même fonction,
    même table, même index. Pas de chemin de rendu « statique » séparé : un
    script peut réécrire le même slot ensuite (`text.draw_in`), dernier
    écrivain gagne.

    Posé une seule fois, à l'init : un texte qui doit CHANGER est le travail
    d'un script.
    """
    from core.models.ui_region import KIND_TEXT, ANCHOR_ACTOR, TARGET_OBJ

    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    if lay is None:
        return []
    # Index PROJET-GLOBAUX : `g_ui_regions` suit l'ordre de `all_regions()`,
    # `g_texts` celui de `build_texts()`. Recalculés ici plutôt que reçus, pour
    # lire les mêmes listes que les émetteurs de tables — deux vues divergentes
    # écriraient le bon texte dans la mauvaise zone, sans casser le link.
    slot_idx = {el.name: i for i, (_l, el) in enumerate(p.all_regions())}
    text_idx = {t.key: i for i, t in enumerate(
        p.build_texts() if hasattr(p, "build_texts") else getattr(p, "texts", []))}
    rm = int(getattr(scene, "render_mode", 0) or 0)

    L: list[str] = []
    for el in lay.slots:
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        key = getattr(el, "text_key", "") or ""
        if not key:
            continue          # le validateur le signale déjà, et mieux
        if key not in text_idx or el.name not in slot_idx:
            if emit:
                emit("log_line", f"[warn] texte '{el.name}' : clé '{key}' "
                                 f"introuvable dans la table — rien ne sera écrit.")
            continue
        target = lay.resolved_target(el, rm)
        # Cible BG sans layer de texte : `text_set_layer(-1)` fait sortir le
        # rendu sans un mot, et l'élément disparaît entre le canvas et la ROM.
        if target != TARGET_OBJ and text_bg not in (0, 1, 2, 3):
            if emit:
                emit("log_line",
                     f"[warn] texte '{el.name}' : la scène '{scene.name}' n'a "
                     f"aucun layer de texte (Text BG), il ne s'affichera pas.")
            continue
        if lay.effective_anchor(el)[0] == ANCHOR_ACTOR:
            if emit:
                emit("log_line",
                     f"[warn] texte '{el.name}' : ancré sur un acteur mais posé "
                     f"une seule fois à l'init — il ne suivra pas l'acteur. "
                     f"Utilise une zone et un script pour ça.")
        L.append(f"    text_draw_in({slot_idx[el.name]}, {text_idx[key]});"
                 f"   /* texte authoré '{el.name}' = '{key}' */")
    if L and emit:
        emit("log_line", f"[text] scène '{scene.name}' : {len(L)} texte(s) "
                         f"authoré(s) écrit(s) à l'init")
    return L


def _gen_scene_blend(scene, emit=None) -> list[str]:
    """Configuration du mélange de couleurs d'une scène.

    Les mêmes fonctions que l'API Lua `blend.*` : un script peut reconfigurer
    ensuite, dernier écrivain gagne — pas de second mécanisme.

    L'ordre suit le matériel : les CIBLES d'abord (BLDCNT bits 0-5 et 8-13),
    le MODE ensuite (bits 6-7), les coefficients en dernier. `blend_set_mode`
    n'écrase que son champ, donc l'ordre n'est pas critique — mais le lire dans
    l'ordre du registre évite de se demander s'il l'est.

    Rien n'est émis en mode « aucun » : `display_reset()` a déjà tout remis à
    zéro. Une scène sans mélange ne paie donc pas une instruction."""
    from core.models.scene import (BLEND_NONE, BLEND_ALPHA, BLEND_TOP,
                                   BLEND_BOTTOM, BLEND_NEEDS_BOTTOM,
                                   blend_role_of)
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    if mode == BLEND_NONE:
        return []
    L: list[str] = []
    sides = {BLEND_TOP: 0, BLEND_BOTTOM: 1}
    for layer in getattr(scene, "background_layers", []):
        role = blend_role_of(layer)
        if role:
            L.append(f"    blend_set_layer({sides[role]}, {layer.bg_slot}, 1);"
                     f"   /* BG{layer.bg_slot} — {'dessus' if role == BLEND_TOP else 'dessous'} */")
    for attr, fn in (("blend_obj_role", "blend_set_obj"),
                     ("blend_backdrop_role", "blend_set_backdrop")):
        role = getattr(scene, attr, "")
        if role in sides:
            L.append(f"    {fn}({sides[role]}, 1);")
    L.append(f"    blend_set_mode({mode});")
    if mode == BLEND_ALPHA:
        L.append(f"    blend_set_alpha({int(scene.blend_eva)}, {int(scene.blend_evb)});")
    else:
        # Les modes 2 et 3 n'emploient QUE le dessus, et leur intensité vient de
        # BLDY — écrire BLDALPHA ici ne ferait rien du tout.
        L.append(f"    blend_set_fade({int(scene.blend_evy)});")
    if emit:
        names = {1: "alpha", 2: "éclaircir", 3: "assombrir"}
        tops = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_TOP)]
        bots = [f"BG{l.bg_slot}" for l in scene.blend_layers(BLEND_BOTTOM)]
        if getattr(scene, "blend_obj_role", "") == BLEND_TOP: tops.append("OBJ")
        if getattr(scene, "blend_obj_role", "") == BLEND_BOTTOM: bots.append("OBJ")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_TOP: tops.append("backdrop")
        if getattr(scene, "blend_backdrop_role", "") == BLEND_BOTTOM: bots.append("backdrop")
        detail = f"dessus {', '.join(tops) or '(aucun)'}"
        if mode in BLEND_NEEDS_BOTTOM:
            detail += f", dessous {', '.join(bots) or '(aucun)'}"
        emit("log_line", f"[blend] scène '{scene.name}' : {names.get(mode, mode)} "
                         f"— {detail}")
    return L


def _gen_ui_images(p: Project, scene, text_cbb: int, sprite_offsets: dict,
                   emit=None) -> list[str]:
    """Init des images d'interface d'une scène.

    Trois choses, et rien de plus : remettre l'état des images à leur état
    DÉCLARÉ (une scène quittée laisse ses animations où elles en étaient),
    désigner la banque de palette de chacune, et — pour les images en cible BG
    seulement — recopier les tuiles du sprite dans le charblock d'UI.

    La recopie est ici et pas au démarrage parce que la base dépend du charblock
    alloué à CETTE scène : la même mise en page servie par deux scènes n'a pas
    la même adresse. C'est le raisonnement de `text_set_font_base`, appliqué à
    des tuiles de sprite.

    TOUTES les frames sont copiées, pas seulement celles de l'état déclaré : un
    script peut basculer d'état à n'importe quelle frame, et recopier depuis la
    ROM à cet instant-là ferait clignoter l'image."""
    images = getattr(scene, "_ui_images", None)
    if images is None:
        images = scene_ui_images(p, scene)
    L: list[str] = ["    ui_images_reset();"]
    # Banques : la même que le texte côté BG (les images d'UI partagent la
    # palette de l'interface), et le slot OBJ de la scène côté sprites.
    layout = {d["index"]: d for d in (getattr(scene, "_ui_image_layout", []) or [])}
    text_base = getattr(scene, "_vram_layout", None)
    base0 = getattr(text_base, "text_base", 0) if text_base is not None else 0
    res = getattr(scene, "_ui_reservation", {}) or {}
    # Les images viennent APRÈS tous les autres postes du bloc de texte — cf.
    # `scene_text_reservation`, dont l'ordre fait foi.
    from codegen.font_emit import TEXT_SURF_TILES
    head = (len(res.get("fill_indices", []))
            + sum(a["tiles"] for a in res.get("img_assets", []))
            + res.get("mono_tiles", 0)
            + (TEXT_SURF_TILES if res.get("needs_surface") else 0))
    # Banque de palette par image, résolue par l'allocateur du POOL de sa cible
    # — les deux pools sont disjoints sur GBA. Sans ça l'image lisait la banque
    # d'interface, celle de la POLICE : une silhouette aux couleurs du texte.
    from codegen.palette_alloc import scene_bank_layout
    from core.models.palette import OWN_PAL_BANK
    bg_layout = obj_layout = None
    for info in images:
        sprite = info["sprite"]
        if info["bg"]:
            bg_layout = bg_layout or scene_bank_layout(p, scene, "bg")
            bank_layout = bg_layout
        else:
            obj_layout = obj_layout or scene_bank_layout(p, scene, "obj")
            bank_layout = obj_layout
        bank = bank_layout.bank_index(
            int(getattr(sprite, "pal_bank", OWN_PAL_BANK)),
            list(getattr(sprite, "own_palette", None) or []))
        L.append(f"    ui_image_set_bank({info['index']}, {bank if bank is not None else 0});"
                 f"   /* '{info['el'].name}' : palette de {sprite.name} */")
        if bank is None and emit:
            emit("log_line",
                 f"[warn] image '{info['el'].name}' : aucune banque libre pour la "
                 f"palette de '{sprite.name}' — elle s'affichera avec les "
                 f"couleurs de la banque 0.")
        if not info["bg"]:
            continue
        pl = layout.get(info["index"])
        if pl is None:
            continue
        base = base0 + head + pl["base"]
        ss = f"sprite_{c_sym(sprite.name)}"
        L.append(f"    ui_image_set_bg_base({info['index']}, {base});")
        L.append(f"    copy16(TILE_RAM({text_cbb}) + {base} * 16, "
                 f"{ss}Tiles, {ss}TilesLen);"
                 f"   /* image '{info['el'].name}' : {info['frames']} frame(s) */")
    return L


def scene_color_fills(p: Project, scene) -> tuple[list[dict], list[int]]:
    """Fonds COULEUR des conteneurs d'une scène → (fills, indices).

    1re tranche : uniquement les panels à fond `color`, cible BG, root ancré
    ÉCRAN (position fixe — le monde défile, l'OBJ n'a pas de tilemap). Chaque
    fond : rectangle en TUILES (résolu écran), index de couleur, banque de
    palette (= sa place dans `scene.active_bg_palettes`). `indices` = index
    distincts, un par tuile pleine à graver dans le charblock UI."""
    from core.models.ui_region import (
        KIND_PANEL, FILL_COLOR, ANCHOR_SCREEN, TARGET_BG)
    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    if lay is None or getattr(scene, "text_bg", -1) not in (0, 1, 2, 3):
        return [], []
    rm = int(getattr(scene, "render_mode", 0) or 0)
    active = list(getattr(scene, "active_bg_palettes", []) or [])
    fills: list[dict] = []
    indices: list[int] = []
    for el in lay.elements:
        if getattr(el, "kind", "") != KIND_PANEL:            continue
        if getattr(el, "fill_kind", "") != FILL_COLOR:       continue
        if lay.resolved_target(el, rm) != TARGET_BG:         continue
        if lay.effective_anchor(el)[0] != ANCHOR_SCREEN:     continue
        pal = getattr(el, "fill_palette", "")
        if pal not in active:                                continue  # non active
        x, y, _ = lay.absolute_origin(el, lambda _n: None)
        tx, ty = x // 8, y // 8
        tw = max(1, (x - tx * 8 + el.w + 7) // 8)
        th = max(1, (y - ty * 8 + el.h + 7) // 8)
        idx = int(getattr(el, "fill_index", 0) or 0) & 0xF
        if idx not in indices:
            indices.append(idx)
        fills.append({"name": el.name, "tx": tx, "ty": ty, "w": tw, "h": th,
                      "index": idx, "bank": active.index(pal)})
    return fills, indices


# Cellule « rien à dessiner » d'un fond image. Doit rester égale à UI_SE_EMPTY
# de gba_engine.h : le runtime y reconnaît la sentinelle AVANT d'ajouter la base
# de tuiles, et pose une case vide.
UI_SE_EMPTY = 0xFFFF


def scene_image_fills(p: Project, scene) -> tuple[list[dict], list[dict]]:
    """Fonds IMAGE (nine-slice, background) des conteneurs d'une scène.

    Renvoie (fills, assets) :
      fills  — un par panneau : rectangle en TUILES + la liste des screen
               entries à écrire (palette déjà rebasée sur les banques HW).
      assets — les BackgroundAsset sources, dédupliqués et ORDONNÉS ; le codegen
               leur attribue une base de tuiles dans le charblock d'UI, dans cet
               ordre, et les `se` citent des index LOCAUX que le runtime décale
               de cette base.

    Même périmètre que `scene_color_fills` (cible BG, root écran) : le monde
    défile et l'OBJ n'a pas de tilemap. Les marges d'un nine-slice sont ramenées
    à la TUILE — une tilemap ne sait pas couper un cadre à 3 px."""
    from core.models.ui_region import (
        KIND_PANEL, FILL_NINE, FILL_BG, ANCHOR_SCREEN, TARGET_BG)
    from core.nine_slice import nine_slice_rects
    from core.models.tile_codec import unpack_se, pack_se
    from codegen.palette_alloc import scene_bank_layout

    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    if lay is None or getattr(scene, "text_bg", -1) not in (0, 1, 2, 3):
        return [], []
    rm = int(getattr(scene, "render_mode", 0) or 0)
    bank_layout = scene_bank_layout(p, scene, "bg")
    fills: list[dict] = []
    assets: list[dict] = []
    by_name: dict[str, int] = {}      # nom d'asset -> index dans `assets`

    for el in lay.elements:
        if getattr(el, "kind", "") != KIND_PANEL:            continue
        fk = getattr(el, "fill_kind", "")
        if fk not in (FILL_NINE, FILL_BG):                   continue
        if lay.resolved_target(el, rm) != TARGET_BG:         continue
        if lay.effective_anchor(el)[0] != ANCHOR_SCREEN:     continue

        # Source : le fond cité, dans les deux modes. Un cadre étirable est un
        # BackgroundAsset de kind `ui` qui porte ses propres marges de découpe —
        # il n'y a plus d'asset de cadre à déréférencer entre les deux.
        src_name = getattr(el, "fill_asset", "")
        ba = p.get_background(src_name) if src_name else None
        if ba is None or not getattr(ba, "tileset", None):    continue
        if getattr(ba, "bpp", 4) == 8:                        continue  # cf. layers 8bpp
        pal_offset = bank_layout.bg_block_offset(ba)
        if pal_offset is None:                                continue  # pas de banques

        x, y, _ = lay.absolute_origin(el, lambda _n: None)
        tx, ty = x // 8, y // 8
        w = max(1, (x - tx * 8 + el.w + 7) // 8)
        h = max(1, (y - ty * 8 + el.h + 7) // 8)
        sw, sh = max(1, ba.tiles_w), max(1, ba.tiles_h)
        src_map = ba.effective_tilemap()

        def src_se(sc: int, sr: int) -> int:
            """SE source rebasée sur les banques HW, ou UI_SE_EMPTY hors image.

            Sentinelle plutôt que 0 : le runtime AJOUTE la base de tuiles de
            l'asset, donc un 0 y désignerait sa PREMIÈRE tuile au lieu de
            « rien à dessiner »."""
            if not (0 <= sc < sw and 0 <= sr < sh):
                return UI_SE_EMPTY
            cell = sr * sw + sc
            if cell >= len(src_map):
                return UI_SE_EMPTY
            tid, pb, fh, fv = unpack_se(src_map[cell])
            return pack_se(tid, pb + pal_offset, fh, fv)

        se = [UI_SE_EMPTY] * (w * h)
        if fk == FILL_BG:
            # Image posée en haut-gauche, ROGNÉE bas/droite — une fenêtre sur le
            # fond, jamais un étirement (même règle que l'aperçu éditeur).
            for r in range(h):
                for c in range(w):
                    se[r * w + c] = src_se(c, r)
        else:
            # Coins fixes, bords/centre RÉPÉTÉS. La géométrie est celle de
            # `core.nine_slice`, en unités de TUILE plutôt qu'en pixels.
            ml, mr, mt, mb = ba.slice_margins_tiles()
            for z in nine_slice_rects(sw, sh, ml, mr, mt, mb, w, h):
                sx, sy, s_w, s_h = z["src"]
                dx, dy, d_w, d_h = z["dst"]
                for r in range(d_h):
                    for c in range(d_w):
                        cc = (c % s_w) if z["tile"] else min(c, s_w - 1)
                        rr = (r % s_h) if z["tile"] else min(r, s_h - 1)
                        se[(dy + r) * w + (dx + c)] = src_se(sx + cc, sy + rr)

        if ba.name not in by_name:
            from codegen.bg_emit import tileset_words
            words = tileset_words(ba.tileset, 4)   # 8 mots u32 = 1 tuile 4bpp
            by_name[ba.name] = len(assets)
            assets.append({"name": ba.name, "sym": f"ui_bg_{c_sym(ba.name)}",
                           "words": words, "tiles": len(words) // 8})
        fills.append({"name": el.name, "tx": tx, "ty": ty, "w": w, "h": h,
                      "asset": by_name[ba.name], "se": se})
    return fills, assets


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
    obj_text_oam: int = -1,
    obj_text_tile: int = 0,
    emit=None,
) -> list[str]:
    """Génère void scene_init_{sym}(void) { ... }"""
    sym = c_sym(scene.name)
    obj_layout = scene_bank_layout(p, scene, "obj")
    bg_layout  = scene_bank_layout(p, scene, "bg")
    L: list[str] = []
    # ── Données des fonds IMAGE, en amont de la fonction ───────────
    # Les tuiles de l'asset source et la carte de screen entries de chaque
    # panneau sont des CONSTANTES : calculées par l'éditeur (cf.
    # `scene_image_fills`), elles n'ont aucune raison d'être reconstruites au
    # runtime. `scene_init` ne fait plus qu'une copie et une écriture de map.
    for _a in (getattr(scene, "_ui_img_assets", []) or []):
        _w = _a["words"]
        L.append(f"static const unsigned int {sym}_{_a['sym']}[] = {{"
                 f"   /* fond '{_a['name']}' : {_a['tiles']} tuiles */")
        for i in range(0, len(_w), 8):
            L.append("    " + " ".join(f"0x{v:08X}," for v in _w[i:i + 8]))
        L.append("};")
    for _f in (getattr(scene, "_ui_img_fills", []) or []):
        _se = _f["se"]
        L.append(f"static const unsigned short {sym}_uimap_{c_sym(_f['name'])}[] = {{"
                 f"   /* {_f['w']}x{_f['h']} cases */")
        for i in range(0, len(_se), 12):
            L.append("    " + " ".join(f"0x{v:04X}," for v in _se[i:i + 12]))
        L.append("};")
    # Fonds animés posés sur les calques : un descripteur par placement, avec son
    # propre compteur — c'est ce qui permet à deux copies du même animé d'être à
    # des moments différents de leur boucle (mode `instance`).
    anims = [a for a in scene_anim_descriptors(p, scene, bgi) if not a["shared"]]
    tanims = [a for a in scene_anim_descriptors(p, scene, bgi) if a["shared"]]
    if anims:
        L.append(f"static BgAnim g_bganim_{sym}[{len(anims)}] = {{")
        for a in anims:
            L.append(f"    {{ {a['table']}, {a['sbb']}, {a['ms']}, "
                     f"{a['col']}, {a['row']}, {a['cols']}, {a['rows']}, "
                     f"{a['frames']}, {a['speed']}, {a['loop']}, "
                     f"{a['f0']}, {a['t0']}, {a['f0']}, {a['t0']} }},")
        L.append("};")
    if tanims:
        L.append(f"static BgTileAnim g_bgtileanim_{sym}[{len(tanims)}] = {{")
        for a in tanims:
            L.append(f"    {{ {a['table']}, {a['cbb']}, {a['vram_ofs']}, {a['words']}, "
                     f"{a['frames']}, {a['speed']}, {a['loop']}, 0, 0 }},")
        L.append("};")
    if L:
        L.append("")
    L.append(f"static void scene_init_{sym}(void) {{")
    L.append("    for(int _i=0; _i<G_ACTOR_COUNT; _i++) g_actors[_i]=(Actor){0};")
    L.append("    oam_hide_all();")
    L.append("    bg_maps_clear();")
    L.append("    display_reset();")
    # Ferme les lectures de la scène PRÉCÉDENTE. `g_reads` est global et ses
    # index sont projet-globaux : sans ce reset, `text_update` continue de
    # rendre — chaque frame — une zone appartenant à la mise en page d'une
    # autre scène (son texte réapparaît, son tempo se rejoue).
    L.append("    text_read_reset_all();")
    # Caméra de démarrage. L'activation pose cadrage ET bornes, et rejoue le
    # on_start de la caméra : une scène n'hérite donc jamais du cadrage de la
    # précédente, et un script peut basculer ailleurs ensuite (camera.switch).
    _cam_idx = scene_camera_index(p, scene)
    _cam_name = getattr(scene, "camera", "") or "(default)"
    L.append(f"    camera_switch({_cam_idx});   /* {_cam_name} */")
    # Cmap dispatch
    if _scene_has_cmap(scene):
        L.append(f"    g_active_cmap = g_cmap_{sym};")
        L.append(f"    g_cmap_w = CMAP_W_{sym.upper()};")
        L.append(f"    g_cmap_h = CMAP_H_{sym.upper()};")
    else:
        L.append("    g_active_cmap = NULL; g_cmap_w = 0; g_cmap_h = 0;")
    # BG layers — chaque layer a son propre CBB (= bg_slot) pour ses tuiles,
    # sa map vit dans les derniers SBB de ce même CBB (cf. bg_info).
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
            # bg_cnt_set plutôt qu'une écriture directe : le registre est
            # write-only, la shadow permet ensuite de changer priorité /
            # screenblock au runtime sans perdre les autres bits.
            L.append(f"    bg_cnt_set({bg}, 0x{val:04X});")
    # APRÈS le chargement des cartes, qu'ils recouvrent : un animé n'existe pas
    # dans la carte en ROM, il est toujours posé par-dessus.
    if anims:
        L.append(f"    bg_anim_init(g_bganim_{sym}, {len(anims)});")
    if tanims:
        L.append(f"    bg_tileanim_init(g_bgtileanim_{sym}, {len(tanims)});")
    # Sprites VRAM
    all_sprites = scene_actors + (p._prefab_sprites_cache if hasattr(p, "_prefab_sprites_cache") else [])
    done_vram: set[str] = set()
    for _, sprite in all_sprites:
        if not sprite or not sprite.asset or sprite.name in done_vram:
            continue
        done_vram.add(sprite.name)
        bt = sprite_offsets.get(sprite.name, 0)
        ss = f"sprite_{c_sym(sprite.name)}"
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
    # Texte (text.*) — le layer d'UI porte les glyphes ; la 1ère police du
    # projet est chargée par défaut, `text.set_font()` en change.
    #
    # Plus d'init TTE ici : libtonc est sorti du workflow. TTE chargeait SA
    # police à partir de la tuile 1 de ce même charblock, là où text_set_font
    # pose la nôtre — les deux s'écrasaient. Un seul système de texte, donc un
    # seul occupant du charblock (cf. gba_engine.h, section TTE retiré).
    text_bg = getattr(scene, "text_bg", -1)
    lay = getattr(scene, "_vram_layout", None)
    text_cbb = (lay.text_cbb if lay else text_bg) if text_bg in {0, 1, 2, 3} else -1
    text_base = lay.text_base if lay else 1
    fills = getattr(scene, "_ui_fills", []) or []
    fill_indices = getattr(scene, "_ui_fill_indices", []) or []
    if text_bg in {0, 1, 2, 3}:
        # BGxCNT du layer d'UI. Il n'a pas d'image, donc la boucle des fonds
        # ci-dessus ne l'a pas configuré — et c'est `tte_init_se` qui s'en
        # chargeait avant, en effet de bord. Sans cette ligne le registre reste
        # à 0 (display_reset) : CBB 0 ET SBB 0, donc les screen entries du texte
        # atterrissent PILE sur ses propres tuiles de glyphes.
        #
        # CBB et SBB viennent de l'allocateur : le charblock du texte n'est plus
        # forcément le sien, c'est tout l'intérêt (cf. codegen/vram_alloc.py).
        text_sbb = lay.text_sbb if lay else text_bg * 8 + 7
        text_cnt = (text_bg & 3) | (text_cbb & 3) << 2 | (text_sbb & 0x1F) << 8
        L.append(f"    bg_cnt_set({text_bg}, 0x{text_cnt:04X});"
                 f"   /* layer UI BG{text_bg} : CBB{text_cbb}, SBB{text_sbb} */")
        # PAS besoin de purger le screenblock ici : `bg_maps_clear()`, tout en
        # haut de `scene_init` (avant même les fonds), vide déjà les 32
        # screenblocks en entier — donc CE SBB aussi, quelle que soit la scène
        # précédente qui l'occupait. Une tentative de purge locale à cet
        # endroit serait redondante (et, historiquement, n'était PAS la cause
        # d'un texte qui persiste d'une scène à l'autre).
    L.append(f"    text_set_layer({text_bg if text_bg in {0,1,2,3} else -1});")
    # Remis à 0 (= pas de surface dédiée) à CHAQUE scène : `g_surf_tile_base`
    # est un global qui, sans ce reset, garderait la valeur de la scène
    # précédente pour une scène qui n'a elle-même aucune zone à fond.
    L.append("    text_set_surf_base(0);")
    # Fonds COULEUR des conteneurs : les tuiles pleines occupent le DÉBUT du
    # bloc UI (le texte se décale de `len(indices)`), puis on les repose sur le
    # rectangle de chaque panel. Statique : posé une fois, avant le texte.
    for i, idx in enumerate(fill_indices):
        L.append(f"    ui_fill_load_solid({text_cbb}, {text_base + i}, {idx});"
                 f"   /* tuile pleine, index {idx} */")
    # Fonds IMAGE (nine-slice, background) : les tuiles de chaque asset source
    # sont copiées dans le charblock d'UI, JUSTE APRÈS les tuiles pleines et
    # AVANT les glyphes — chaque bloc a son adresse propre, aucun ne recouvre
    # l'autre. `ui_fill_map` recale ensuite les index de la carte sur cette base.
    img_fills = getattr(scene, "_ui_img_fills", []) or []
    img_assets = getattr(scene, "_ui_img_assets", []) or []
    img_base = text_base + len(fill_indices)
    asset_base: list[int] = []
    _cur = img_base
    for a in img_assets:
        asset_base.append(_cur)
        L.append(f"    copy16(TILE_RAM({text_cbb}) + {_cur} * 16, "
                 f"{sym}_{a['sym']}, {a['tiles'] * 32});"
                 f"   /* tuiles du fond '{a['name']}' */")
        _cur += a["tiles"]
    glyph_base = _cur
    if project_fonts(p):
        # APRÈS text_set_layer (qui repose le charblock par défaut) et AVANT
        # text_set_font (qui copie les glyphes à cette adresse) ; décalé après
        # les tuiles pleines des fonds.
        L.append(f"    text_set_charblock({text_cbb if text_cbb >= 0 else text_bg});")
        L.append(f"    text_set_tile_base({glyph_base});")
        # Chaque police à SA base : charger la seconde n'écrase plus la
        # première. Rien d'émis = tout à la base 0, une seule résidente.
        for _fl in getattr(scene, "_ui_reservation", {}).get("font_layout", []):
            L.append(f"    text_set_font_base({_fl['index']}, {_fl['base']});"
                     f"   /* {_fl['name']} : {_fl['tiles']} tuile(s) */")
        # Banque de couleurs de l'UI. -1 = automatique (la police impose sa
        # palette dans FONT_PAL_BANK) ; sinon un slot de la sélection de la
        # scène, et deux polices ne se repeignent plus l'une l'autre.
        _uib = int(getattr(scene, "ui_pal_bank", -1))
        _uib_obj = _uib if _uib < 0 or _uib < len(
            getattr(scene, "active_obj_palettes", []) or []) else -1
        L.append(f"    text_set_pal_bank({_uib}, {_uib_obj});")
        # Sous-ensembles AVANT text_set_font : c'est lui qui copie les glyphes,
        # il doit déjà savoir lesquels. Une police sans sous-ensemble déclaré se
        # charge entière.
        L.append("    text_clear_subsets();")
        for _fi, _sub_sym in sorted(getattr(scene, "_ui_font_subsets", {}).items()):
            L.append(f"    text_set_subset({_fi}, &{_sub_sym});")
        # Police par défaut de la SCÈNE — le même calcul que la réservation
        # VRAM et les sous-ensembles (cf. font_emit.scene_default_font).
        # Réserver pour une police et en charger une autre écrirait le texte
        # dans le décor sans une erreur avant l'exécution.
        from codegen.font_emit import scene_default_font as _sdf
        _fi_def, _fn_def = _sdf(p, scene)
        L.append(f"    text_set_font({max(0, _fi_def)});"
                 + (f"   /* {_fn_def} */" if _fn_def else ""))
    for f in fills:
        L.append(
            f"    ui_fill_rect({text_bg}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, "
            f"{text_base + fill_indices.index(f['index'])}, {f['bank']});"
            f"   /* fond couleur '{f['name']}' */")
    for f in img_fills:
        L.append(
            f"    ui_fill_map({text_bg}, {f['tx']}, {f['ty']}, {f['w']}, {f['h']}, "
            f"{sym}_uimap_{c_sym(f['name'])}, {asset_base[f['asset']]});"
            f"   /* fond image '{f['name']}' */")
    # Texte SUR un fond couleur : les zones enfants d'un panel couleur se
    # composent sur cette couleur (décision PAR ZONE au runtime, cf.
    # UIRegionInfo.bg_fill). La surface composée a son PROPRE bloc de tuiles,
    # APRÈS les glyphes mono — à la même adresse, composer une zone écraserait
    # les glyphes que ses voisines mono lisent encore. Les couleurs de fond sont
    # réécrites dans la palette de police, donc après text_set_font.
    from codegen.font_emit import FONT_PAL_BANK
    by_name, idx_color = _region_bg_fills(p)
    lay_ui = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    scene_bg_idx = sorted({by_name[r.name] for r in (lay_ui.slots if lay_ui else [])
                           if r.name in by_name})
    if scene_bg_idx and text_bg in {0, 1, 2, 3}:
        mono_tiles = getattr(scene, "_ui_mono_tiles", 0)
        surf_base = glyph_base + mono_tiles
        L.append(f"    text_set_surf_base({surf_base});"
                 f"   /* surface composée, bloc dédié après les glyphes mono */")
        if int(getattr(scene, "ui_pal_bank", -1)) < 0:
            # Mode automatique : la banque de police n'appartient qu'au texte,
            # on peut y graver les couleurs de fond des zones.
            for idx in scene_bg_idx:
                L.append(f"    PAL_BG_RAM[{FONT_PAL_BANK} * 16 + {idx}] = "
                         f"0x{idx_color[idx]:04X};   /* couleur de fond de zone */")
        # Banque DÉSIGNÉE : on n'y écrit rien, ce serait remplacer en douce les
        # couleurs choisies par la scène. Un fond de zone doit alors prendre une
        # couleur qui s'y trouve déjà.
    # Bande de sprites du texte : après les sprites d'acteurs (tuiles) et après
    # tous les slots d'acteurs et de pools (OAM). -1 = aucune zone en cible OBJ.
    if obj_text_oam >= 0:
        L.append(f"    text_obj_set_actor_fn(_txt_actor_x, _txt_actor_y);")
        L.append(f"    text_obj_set_base({obj_text_oam}, {obj_text_tile});")
    # Textes AUTHORÉS de la mise en page. En DERNIER des postes de texte : le
    # rendu lit la police, la base de tuiles, la surface composée, les couleurs
    # de fond et la base OBJ — tout ce qui précède. Avant dispcnt_set, qui
    # n'écrit que des registres d'affichage.
    L += _gen_ui_texts(p, scene, text_bg, emit)
    # Images de l'interface, APRÈS les postes de texte : elles réutilisent la
    # même base OAM (`text_obj_set_base`, dont l'allocation chaîne les deux) et
    # se logent après les glyphes dans le charblock d'UI.
    L += _gen_ui_images(p, scene, text_cbb, sprite_offsets, emit)
    # DISPCNT
    L.append(f"    dispcnt_set(0x{dispcnt:04X});")
    # Mélange de couleurs (BLDCNT/BLDALPHA/BLDY) — rien d'émis en mode « aucun » :
    # `display_reset()` a déjà remis les trois registres à zéro, et le défaut
    # doit rester littéralement gratuit.
    L += _gen_scene_blend(scene, emit)
    # Windows (WIN0/WIN1/fenêtre-objet) — mêmes fonctions runtime que l'API Lua
    # window.* : un script peut reconfigurer/désactiver ensuite (dernier écrivain
    # gagne, pas de mécanisme séparé). Rien n'est émis si la scène n'a aucune
    # window authorée (display_reset() a déjà tout remis à « aucune window active »).
    #
    # IMPÉRATIVEMENT APRÈS dispcnt_set : window_show() pose un bit DISPCNT
    # (13=WIN0, 14=WIN1, 15=OBJWIN) dans la shadow, alors que dispcnt_set()
    # REMPLACE la shadow entière (g_dispcnt_sh = val). Émis avant, l'activation
    # des windows serait silencieusement effacée — la window resterait invisible
    # en jeu alors que tous ses autres registres sont corrects.
    for ws in getattr(scene, "windows", []):
        region = int(ws.region)
        # Région 2 (fenêtre-objet) n'a pas de rectangle : sa forme vient des
        # pixels opaques des sprites en obj_mode=2. Surtout, window_set() fait
        # `n &= 1` — l'appeler avec 2 écraserait le rectangle de WIN0.
        if region in (0, 1):
            L.append(f"    window_set({region}, {int(ws.x)}, {int(ws.y)}, {int(ws.w)}, {int(ws.h)});")
        layers = list(getattr(ws, "layers_shown", [True, True, True, True]))
        for bg in range(4):
            on = 1 if (bg < len(layers) and layers[bg]) else 0
            L.append(f"    window_set_layer({region}, {bg}, {on});")
        L.append(f"    window_set_obj({region}, {1 if ws.obj_shown else 0});")
        L.append(f"    window_show({region}, {1 if ws.visible else 0});")
    # Init actors
    for j, (actor, sprite) in enumerate(scene_actors):
        idx = actor_offset + j
        s = c_sym(actor.name)
        boxes = [c for c in actor.components if isinstance(c, CollisionBoxComponent) and c.active][:4]
        own = list(sprite.own_palette) if (sprite and getattr(sprite, "own_palette", None)) else []
        pal = obj_layout.bank_index(getattr(actor, "pal_bank", OWN_PAL_BANK), own)
        L += [
            f"    g_actors[{idx}].x       = {_FV.parse(actor.x, _var_names(p)).c_expr()};",
            f"    g_actors[{idx}].y       = {_FV.parse(actor.y, _var_names(p)).c_expr()};",
            f"    g_actors[{idx}].active  = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].visible = {1 if actor.visible else 0};",
            f"    g_actors[{idx}].flip_h  = {1 if getattr(_get_sprite_comp(actor),'flip_h',False) else 0};",
            f"    g_actors[{idx}].flip_v  = {1 if getattr(_get_sprite_comp(actor),'flip_v',False) else 0};",
            f"    g_actors[{idx}].dir_x   = {getattr(actor,'dir_x',0)};",
            f"    g_actors[{idx}].dir_y   = {getattr(actor,'dir_y',0)};",
            f"    g_actors[{idx}].pal_bank= {pal if pal is not None else 0};",
            f"    g_actors[{idx}].obj_mode= {int(getattr(actor, 'obj_mode', 0)) & 3};",
            f"    g_actors[{idx}].auto_dir= {1 if getattr(_get_sprite_comp(actor),'auto_dir',True) else 0};",
            f"    g_actors[{idx}].anim_state=0;",
            f"    g_actors[{idx}].tag     = TAG_{s.upper()};",
            f"    g_actors[{idx}].box_count = {len(boxes)};",
        ]
        for bi2, cb in enumerate(boxes):
            tag_s = "BOXTAG_" + c_sym(cb.tag or "body").upper()
            _vn = _var_names(p)
            bx, by = _FV.parse(cb.x, _vn).c_expr(), _FV.parse(cb.y, _vn).c_expr()
            bw, bh = _FV.parse(cb.w, _vn).c_expr(), _FV.parse(cb.h, _vn).c_expr()
            L += [
                f"    g_actors[{idx}].boxes[{bi2}].x=(s8){bx}; g_actors[{idx}].boxes[{bi2}].y=(s8){by};",
                f"    g_actors[{idx}].boxes[{bi2}].w=(u8){bw};  g_actors[{idx}].boxes[{bi2}].h=(u8){bh};",
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
        s = c_sym(actor.name)
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


def _affine_oam_lines(idx: int, aff: dict, sprite, bt: int, priority_expr: str,
                      screen_space: bool = False) -> list[str]:
    """Lignes C (intérieur du if actif) pour un sprite affine : rotation+scale+flip runtime.

    `screen_space` retire la soustraction de caméra (cf. Actor.screen_space) :
    x/y sont alors des pixels d'écran. Le reste du calcul est identique — les
    ajustements affines sont relatifs à l'ancrage, pas à l'espace."""
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

    sx_expr = _pos(f"g_actors[{idx}].x" + ("" if screen_space else "-cam_x"),
                   x00, xfh, xfv, xhv)
    sy_expr = _pos(f"g_actors[{idx}].y" + ("" if screen_space else "-cam_y"),
                   y00, yfh, yfv, yhv)

    return [
        f"        int sx={sx_expr}; int sy={sy_expr};",
        f"        u16 ti=(u16)({bt}+g_actors[{idx}].frame*{tpf});",
        f"        shadow_oam[{aslot*4+0}].dummy=(u16)(s16)(g_actors[{idx}].flip_h?{-pa}:{pa});",
        f"        shadow_oam[{aslot*4+1}].dummy=(u16)(s16)(g_actors[{idx}].flip_h?{-pb}:{pb});",
        f"        shadow_oam[{aslot*4+2}].dummy=(u16)(s16)(g_actors[{idx}].flip_v?{-pc}:{pc});",
        f"        shadow_oam[{aslot*4+3}].dummy=(u16)(s16)(g_actors[{idx}].flip_v?{-pd}:{pd});",
        f"        shadow_oam[{idx}].attr0=(sy&0xFF)|(1<<8)|(1<<9)|(g_actors[{idx}].obj_mode<<10)|({sh}<<14);",
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
    sym = c_sym(scene.name)
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
            s = c_sym(actor.name)
            if _def(s, "on_update"):
                L.append(f"    if(g_actors[{j}].active) {s}_on_update(&g_actors[{j}]);")

    # on_update prefabs poolés
    for p2 in pi:
        if _def(p2["sym"], "on_update"):
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi++)")
            L.append(f"        if(g_actors[_pi].active) {p2['sym']}_on_update(&g_actors[_pi]);")

    # Résolution contre la carte de collision — pour TOUTE box solide, et non
    # plus seulement pour les acteurs qui définissent `on_tile_collide` : la
    # résolution DÉPLACE l'acteur, le hook ne fait que prévenir. C'est aussi ce
    # que le modèle promet depuis toujours (« solid=True → résolution physique »).
    # Rien n'est émis si la scène n'a pas de carte : il n'y aurait rien à heurter.
    if _scene_has_cmap(scene):
        for j in range(len(scene_actors)):
            actor, _ = scene_actors[j]
            if not _has_solid_box(actor):
                continue
            idx = actor_offset + j
            s = c_sym(actor.name)
            cb = f"{s}_on_tile_collide" if (idx in lua_idx and _def(s, "on_tile_collide")) else "NULL"
            L.append(f"    if(g_actors[{idx}].active) resolve_actor_tiles(&g_actors[{idx}], {cb});")

        for p2 in pi:
            if not _has_solid_box(p2["prefab"]):
                continue
            cb = f"{p2['sym']}_on_tile_collide" if _def(p2["sym"], "on_tile_collide") else "NULL"
            L.append(f"    for(int _pi={p2['start']}; _pi<{p2['start']+p2['size']}; _pi++)")
            L.append(f"        if(g_actors[_pi].active) resolve_actor_tiles(&g_actors[_pi], {cb});")

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
            si = c_sym(scene_actors[i - actor_offset][0].name)
            sj = c_sym(scene_actors[j - actor_offset][0].name)
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
                (j, c_sym(scene_actors[j - actor_offset][0].name))
                for j in sorted(lua_idx)
                if _def(c_sym(scene_actors[j - actor_offset][0].name), ev)
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
            s = c_sym(actor.name)
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

    # Caméra — l'ordre est la règle, et il tient en quatre lignes :
    #   1. la secousse de la frame précédente est retirée, pour que le suivi
    #      raisonne sur la vraie position et non sur une position tremblée ;
    #   2. le DÉCLARATIF est calculé (suivi par zone morte, si la caméra active
    #      est en mode suivi et que sa cible existe dans cette scène) ;
    #   3. le SCRIPT de la caméra s'exécute ensuite — il peut donc ajuster ce
    #      que le déclaratif vient de poser, ce qui rend l'usage purement
    #      déclaratif, purement scripté ou hybride sans réglage de bascule ;
    #   4. les bornes clampent en dernier, peu importe qui a écrit cam_x/cam_y,
    #      puis la secousse se pose PAR-DESSUS le clamp — trembler au bord du
    #      monde doit se voir.
    # Le tout lit `g_cam_active` : c'est ce qui permet à un script de changer de
    # caméra en cours de partie (camera.switch) sans que le tick soit regénéré.
    L.append("    camera_shake_undo();")
    L += _camera_follow_lines(p, scene, scene_actors, actor_offset)
    L.append("    if(g_cam_table[g_cam_active].on_update) g_cam_table[g_cam_active].on_update();")
    L.append("    camera_apply_bounds();")
    L.append("    camera_shake_apply();")

    # BG scroll offset H+V (+ streaming des bords pour un grand niveau)
    if bgi:
        for bi in bgi:
            if bi.get("stream"):
                L.append(f"    bg_stream_update(MAP_RAM({bi['sbb']}), {bi['sym']}Map, "
                         f"{bi['tw']}, {bi['th']}, {bi['win_w']}, {bi['win_h']}, "
                         f"{int(bi['stream_h'])}, {int(bi['stream_v'])}, cam_x, cam_y);")
            # Scroll = caméra × vitesse de parallax + décalage propre au layer
            # (layer_set_scroll / layer_scroll_by depuis Lua).
            L.append(f"    BGOFS({bi['bg']})=(u16)(((cam_x*{bi['speed']})>>8)+layer_get_scroll_x({bi['bg']}));")
            L.append(f"    BGVOFS({bi['bg']})=(u16)(((cam_y*{bi['speed']})>>8)+layer_get_scroll_y({bi['bg']}));")

    # Fonds animés : APRÈS le streaming, qui recharge des colonnes/lignes
    # entières de la carte en ROM — un animé recouvert par une colonne entrante
    # se redessinerait avec un cycle de retard.
    _all = scene_anim_descriptors(p, scene, bgi)
    _anims = [a for a in _all if not a["shared"]]
    _tanims = [a for a in _all if a["shared"]]
    if _anims:
        L.append(f"    bg_anim_update(g_bganim_{sym}, {len(_anims)});")
    if _tanims:
        L.append(f"    bg_tileanim_update(g_bgtileanim_{sym}, {len(_tanims)});")

    # Animation (state machine + direction)
    anim_actors = [(actor_offset + j, a, s2) for j, (a, s2) in enumerate(scene_actors) if s2 and s2.asset and s2.states]
    for idx, actor, sprite in anim_actors:
        L += _anim_tick_lines(idx, f"sprite_{c_sym(sprite.name)}")

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
            # UI en sprite : x/y SONT déjà des pixels d'écran, la caméra ne les
            # touche pas. Décidé ici, au build — un acteur de monde émet
            # exactement le C qu'il émettait avant (cf. Actor.screen_space).
            _ss = bool(getattr(actor, "screen_space", False))
            _cx = "" if _ss else "-cam_x"
            _cy = "" if _ss else "-cam_y"
            if idx in _aff:
                inner = _affine_oam_lines(idx, _aff[idx], sprite, bt,
                                          str(actor.priority), screen_space=_ss)
                L += [
                    f"    if(g_actors[{idx}].active && g_actors[{idx}].visible){{",
                    *inner,
                    f"    }}else{{ shadow_oam[{idx}].attr0=0x0200; }}",
                ]
            else:
                L += [
                    f"    if(g_actors[{idx}].active && g_actors[{idx}].visible){{",
                    f"        int sx=g_actors[{idx}].x{_cx}{ox_s}; int sy=g_actors[{idx}].y{_cy}{oy_s};",
                    f"        u16 ti=(u16)({bt}+g_actors[{idx}].frame*{sprite.tiles_per_frame});",
                    f"        int fh=g_actors[{idx}].flip_h; int fv=g_actors[{idx}].flip_v;",
                    f"        shadow_oam[{idx}].attr0=(sy&0xFF)|(g_actors[{idx}].obj_mode<<10)|({sh}<<14);",
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
                    f"        shadow_oam[{oam_slot}].attr0=(sy&0xFF)|(g_actors[{oam_slot}].obj_mode<<10)|({sh}<<14);",
                    f"        shadow_oam[{oam_slot}].attr1=(sx&0x1FF)|(fh<<12)|(fv<<13)|({sz}<<14);",
                    f"        shadow_oam[{oam_slot}].attr2=(ti&0x3FF)|(0<<10)|(g_actors[{oam_slot}].pal_bank<<12);",
                    f"    }}else{{ shadow_oam[{oam_slot}].attr0=0x0200; }}",
                ]

    # Après les scripts, avant le flush OAM : une lecture démarrée pendant le
    # tick avance dès cette frame, et les sprites des glyphes animés sont posés
    # avant d'être copiés en OAM.
    L.append("    ui_image_update();")
    L.append("    text_update();")
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
    # Un sprite qui ne sert QU'à une image d'interface n'est porté par aucun
    # acteur : sans ceci, ses tuiles ne partiraient jamais en VRAM.
    all_sprite_pairs += ui_image_sprites(p)

    sprite_offsets, sprite_nframes = _sprite_offsets_for(p, all_sprite_pairs)

    # Bases de la bande de texte OBJ : la queue de ce que les sprites occupent.
    _obj_alloc = _obj_text_alloc(p)
    _obj_need  = max((pl["oam_rel"] + pl["oam"] for pl in _obj_alloc.values()),
                     default=0)
    obj_text_oam  = n_actors if _obj_need else -1
    obj_text_tile = _obj_tiles_used(p, all_sprite_pairs)
    # Débordement OBJ : BLOQUANT, et calculé même sans `emit`.
    #
    # Ces deux dépassements n'étaient que journalisés — `generate_main` rendait
    # `True` quoi qu'il arrive, donc la ROM se construisait avec des slots hors
    # des 128 du matériel : rien à l'écran, aucune erreur. Le fond de panneau en
    # sprites rend le cas trivial à atteindre (un panneau de 224×48 pavé d'une
    # frame 8×8 réclame 168 slots à lui seul), d'où le passage en erreur — même
    # règle que le budget de tuiles BG, qui bloque déjà.
    _fatal: list[str] = []
    if _obj_need:
        if emit:
            emit("log_line",
                 f"[text] bande OBJ : OAM {obj_text_oam}..{obj_text_oam + _obj_need - 1} "
                 f"(sur 128), tuiles depuis {obj_text_tile}")
        if obj_text_oam + _obj_need > 128:
            _fatal.append(
                f"[error] l'interface en sprites (zones de texte, images, fonds "
                f"de conteneur) demande {_obj_need} slots OAM après {n_actors} "
                f"d'acteurs — le matériel n'en a que 128. Réduire un pavage de "
                f"fond, passer une zone en cible BG, ou diminuer le pool de "
                f"prefabs.")
        # Les tuiles OBJ tombent à 512 en mode bitmap (la VRAM BG y empiète sur
        # l'espace sprite) : c'est la scène la plus contrainte qui commande.
        _tiles_need = max((pl["tile_rel"] + pl["tiles"] for pl in _obj_alloc.values()),
                          default=0)
        _cap = 512 if any(getattr(sc, "render_mode", 0) in (3, 4, 5)
                          for sc in p.scenes) else 1024
        if obj_text_tile + _tiles_need > _cap:
            _fatal.append(
                f"[error] les zones de texte en sprites demandent "
                f"{_tiles_need} tuiles OBJ après {obj_text_tile} de sprites, "
                f"soit plus que les {_cap} disponibles.")
    # Débordement de la SRAM, ou deux variables persistantes indiscernables :
    # même règle que ci-dessus, ça bloque. Une sauvegarde qui déborde ne se
    # verrait qu'à l'exécution, chez le joueur.
    _fatal += save_fatal(p)
    if _fatal:
        for _m in _fatal:
            if emit:
                emit("error_line", _m)
        return False

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
        bgi_d = bg_info(p, d["scene"])
        _log_vram_layout(d["scene"], emit)
        for bi in bgi_d:
            _add_inc(f'#include "{bi["sym"]}.h"')
        # Tables d'images des fonds animés — un header par scène, toujours émis
        # (vide si la scène n'en pose aucun), pour que l'include ne dépende pas
        # d'un état que le générateur devrait deviner.
        from codegen.bg_anim import scene_anim_sym, shared_anim_sym
        _add_inc(f'#include "{scene_anim_sym(d["scene"])}.h"')
        _add_inc(f'#include "{shared_anim_sym(d["scene"])}.h"')
        for _, sprite in d["scene_actors"]:
            if sprite and sprite.asset:
                _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    for _, sprite in prefab_actor_sprites:
        if sprite and sprite.asset:
            _add_inc(f'#include "sprite_{c_sym(sprite.name)}.h"')

    # Externs actors + scènes (filtrés sur les events réellement implémentés)
    def _def(sym, ev):
        """True si l'event est défini dans le script Lua de cet actor."""
        if actor_defined_events is None:
            return True
        return ev in actor_defined_events.get(sym, set())

    for d in all_scene_data:
        sc = d["scene"]
        sc_sym = c_sym(sc.name)
        for actor, _ in d["scene_actors"]:
            s = c_sym(actor.name)
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

    # ── Caméras du projet ────────────────────────────────────────
    # Une caméra est une DONNÉE : la table ci-dessous en est la forme runtime,
    # l'entrée 0 étant toujours la caméra par défaut (fixe à l'origine, sans
    # bornes) — celle qu'obtient une scène qui n'en désigne aucune, sans
    # qu'aucun fichier n'ait à exister.
    cams = project_cameras(p)
    for cam in cams[1:]:
        if getattr(cam, "script", ""):
            cs = camera_sym(cam.name)
            L += [
                f"extern void {cs}_camera_on_start(void);",
                f"extern void {cs}_camera_on_update(void);",
            ]
    L.append(f"const Camera g_cam_table[{len(cams)}] = {{")
    for cam in cams:
        if cam is None:
            L.append("    { 0, 40, 20, 0, 0, 0, 0, NULL, NULL },   /* (default) */")
            continue
        cs = camera_sym(cam.name)
        hooks = (f"{cs}_camera_on_start, {cs}_camera_on_update"
                 if getattr(cam, "script", "") else "NULL, NULL")
        L.append(
            f"    {{ {cam.mode_id()}, {int(cam.margin_x)}, {int(cam.margin_y)}, "
            f"{int(cam.x)}, {int(cam.y)}, "
            f"{int(cam.bounds_w or 0)}, {int(cam.bounds_h or 0)}, {hooks} }},"
            f"   /* {cam.name} — {cam.mode} */"
        )
    L += ["};", ""]

    # ── Polices + table des textes ───────────────────────────────
    L += _fonts_and_texts_lines(p, emit)

    # ── Tables d'animation par SpriteAsset (dédupliquées) ────────
    # Les sprites des IMAGES d'interface en font partie : `g_ui_images` pointe
    # ces tables-là, donc elles doivent exister — et être émises AVANT.
    _all_sprites_flat = [
        pair
        for d in all_scene_data
        for pair in d["scene_actors"]
    ] + (prefab_actor_sprites or []) + ui_image_sprites(p)
    done_anim: set[str] = set()
    for _, sprite in _all_sprites_flat:
        if sprite and sprite.asset and sprite.name not in done_anim:
            done_anim.add(sprite.name)
            L += _anim_tables_for(p, sprite)
            L.append("")

    # ── Images d'interface ────────────────────────────────────────
    L += _ui_images_lines(p, sprite_offsets, emit)

    # ── Sauvegarde ────────────────────────────────────────────────
    # Après globals.h (inclus plus haut) : les tables citent les index
    # GLOBAL_*, et le pilote appelle global_read/global_write.
    L += _save_lines(p, emit)

    # ── Tile helpers (dispatch via pointeur) ──────────────────────
    L += _gen_tile_helpers()

    # ── Cmap flat arrays par scène ────────────────────────────────
    for d in all_scene_data:
        sc = d["scene"]
        sym = c_sym(sc.name)
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
        sym = c_sym(sc.name)
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
        sym = c_sym(sc.name)
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
        "int   g_cam_max_x = -1, g_cam_max_y = -1;",
        "int   g_cam_active = 0;",
        # État de la secousse — un événement en cours, pas un réglage : il vit
        # ici et non dans la table des caméras (cf. actor_api_static.h).
        "int   g_shake_amp = 0, g_shake_left = 0, g_shake_total = 1;",
        "int   g_shake_dx = 0, g_shake_dy = 0;",
        "u32   g_shake_seed = 2463534242u;",
        "int   _g_frame = 0;",
        "int   g_current_scene = -1;",
        "int   g_next_scene    = -1;",
        "",
    ]

    # Spawn helpers — index de banque des prefabs poolés résolu via la
    # 1ère scène (spawn_X est global).
    _anchor_obj_layout = scene_bank_layout(p, all_scenes[0], "obj") if all_scenes else None
    L += _section_spawn(pi, p, _anchor_obj_layout, actor_defined_events=actor_defined_events)

    # Position d'un acteur pour les zones de texte ancrées : `gba_engine.h`
    # ignore la structure Actor (elle est déclarée dans actor_api_static.h, qui
    # inclut le moteur et non l'inverse), d'où ces deux accesseurs passés par
    # pointeur de fonction plutôt qu'une dépendance inversée.
    if obj_text_oam >= 0:
        L += [
            "/* ── Position d'acteur pour les zones de texte ancrées ─── */",
            "static int _txt_actor_x(int i) { return g_actors[i].x; }",
            "static int _txt_actor_y(int i) { return g_actors[i].y; }",
            "",
        ]

    # ── scene_init_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc         = d["scene"]
        act_off    = scene_offsets[i]
        bgi_d      = bg_info(p, d["scene"])
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
            obj_text_oam=obj_text_oam, obj_text_tile=obj_text_tile,
            emit=emit,
        )

    # ── scene_tick_X() par scène ──────────────────────────────────
    for i, d in enumerate(all_scene_data):
        sc      = d["scene"]
        act_off = scene_offsets[i]
        bgi_d   = bg_info(p, d["scene"])
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
    # `trans_mode`/`trans_frames` : la transition de CETTE scène, employée
    # aussi bien quand on la quitte (fermeture) que quand on l'ouvre
    # (ouverture) — chaque scène décrit sa propre disparition et sa propre
    # apparition, cf. ROADMAP v0.6.2. L'héritage projet→scène est résolu ici :
    # le runtime ne connaît pas la notion.
    from core.models.scene import TRANSITION_MODES, transition_of
    n_scenes = len(all_scene_data)
    trans = []   # (mode BLDCNT, durée d'une moitié) par scène
    for d in all_scene_data:
        kind, frames = transition_of(d["scene"], p.settings)
        trans.append((TRANSITION_MODES.get(kind, 0), min(255, max(1, frames)), kind))
    # Aucune scène n'a de transition → rien de tout ceci n'est émis : un projet
    # qui n'en veut pas garde la bascule sèche d'avant, au bit près.
    has_transitions = any(m for m, _, _ in trans)

    if has_transitions:
        L += [
            "typedef struct { void(*init)(void); void(*tick)(void);",
            "                 u8 trans_mode; u8 trans_frames; } _SceneVtable;",
        ]
    else:
        L.append("typedef struct { void(*init)(void); void(*tick)(void); } _SceneVtable;")
    L.append(f"static const _SceneVtable g_scene_vtable[{n_scenes}] = {{")
    for d, (mode, frames, kind) in zip(all_scene_data, trans):
        sym = c_sym(d["scene"].name)
        entry = f"    {{ scene_init_{sym}, scene_tick_{sym}"
        entry += f", {mode}, {frames} }},   /* transition : {kind} */" if has_transitions else " },"
        L.append(entry)
    L += ["};", ""]

    if has_transitions:
        L += [
            "/* ── Transition de scène (cf. ROADMAP v0.6.2) ──────────────────── */",
            "/* Phase 0 = aucune, 1 = fermeture (la scène sortante est gelée),",
            "   2 = ouverture. L'intensité va de 0 (net) à 16 (éteint). */",
            "static int g_trans_phase = 0, g_trans_i = 0, g_trans_n = 1;",
            "",
            "/* Bascule effective. L'écran est déjà éteint quand scene_init tourne :",
            "   son display_reset() n'écrit que dans les shadows tant que la",
            "   transition possède les registres, donc la scène entrante ne",
            "   surgit pas en pleine lumière au milieu de son chargement. */",
            "static void scene_enter(void){",
            "    int m = 0, n = 1;",
            f"    if(g_next_scene>=0 && g_next_scene<{n_scenes}){{",
            "        m = g_scene_vtable[g_next_scene].trans_mode;",
            "        n = g_scene_vtable[g_next_scene].trans_frames;",
            "    }",
            "    if(m){ transition_begin(m); transition_fade(16); }",
            "    g_current_scene = g_next_scene;",
            f"    if(g_current_scene>=0 && g_current_scene<{n_scenes})",
            "        g_scene_vtable[g_current_scene].init();",
            "    if(m){ g_trans_i = n; g_trans_n = n; g_trans_phase = 2; }",
            "    else { transition_end(); g_trans_phase = 0; }",
            "}",
            "",
        ]

    # ── main() ────────────────────────────────────────────────────
    L.append("int main(void){")
    L.append("    irqInit(); irqEnable(IRQ_VBLANK);")
    # Waitstates SRAM, posés avant toute lecture. Inconditionnel : c'est une
    # écriture de registre, et la rendre conditionnelle ferait dépendre le
    # démarrage d'un état du projet pour économiser un cycle.
    L.append("    sram_init();")

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
            L.append(f"    mmStart(MOD_{c_sym(music_item.name).upper()}, {loop});")

    # Sprites VRAM (une seule fois au démarrage — toutes scènes). Les
    # palettes OBJ ne sont PLUS copiées ici : chaque scene_init_X() charge
    # déjà la sienne (g_pal_obj_{sym}) au bon moment, y compris pour la
    # scène de départ (appelée juste après, cf. boucle principale ci-dessous).
    if sprite_offsets:
        L.append("    /* Tiles sprites → OBJ VRAM (toutes scènes) */")
        for name, base in sprite_offsets.items():
            ss = f"sprite_{c_sym(name)}"
            L.append(f"    copy16(OBJ_VRAM+{base}*16, {ss}Tiles, {ss}TilesLen);")

    L.append(f"    g_next_scene = {start_idx};   /* {start_scene} */")
    L.append("    while(1){")
    if has_transitions:
        L += [
            "        /* Fermeture : la scène qu'on QUITTE décide du fondu, et gèle",
            "           pendant celui-ci. Rien à jouer → bascule immédiate. */",
            "        if(g_trans_phase==0 && g_next_scene!=g_current_scene){",
            "            int m = (g_current_scene>=0 && g_current_scene<"
            f"{n_scenes}) ? g_scene_vtable[g_current_scene].trans_mode : 0;",
            "            if(m){",
            "                g_trans_phase = 1; g_trans_i = 0;",
            "                g_trans_n = g_scene_vtable[g_current_scene].trans_frames;",
            "                transition_begin(m); transition_fade(0);",
            "            } else scene_enter();",
            "        }",
        ]
    else:
        L += [
            "        if(g_next_scene != g_current_scene){",
            "            g_current_scene = g_next_scene;",
            f"            if(g_current_scene>=0 && g_current_scene<{n_scenes})",
            "                g_scene_vtable[g_current_scene].init();",
            "        }",
        ]
    L.append("        VBlankIntrWait();")
    if has_sound and soundbank_h.exists():
        L.append("        mmFrame();   /* doc maxmod.h : _doit_ être appelée chaque frame */")
    L += [
        "        _g_frame++;",
        "        scanKeys();",
        "        _g_keys_held    = keysHeld();",
        "        _g_keys_pressed = keysDown();",
    ]
    if has_transitions:
        # La musique et le compteur de frames continuent pendant le fondu : une
        # transition est un effet d'affichage, pas une pause du moteur. Seul le
        # tick de la scène s'arrête, et seulement à la fermeture.
        L += [
            "        if(g_trans_phase==1){",
            "            g_trans_i++;",
            "            transition_fade((16*g_trans_i)/g_trans_n);",
            "            if(g_trans_i>=g_trans_n) scene_enter();",
            "            continue;   /* la scène sortante est gelée */",
            "        }",
            "        if(g_trans_phase==2){",
            "            g_trans_i--;",
            "            transition_fade((16*g_trans_i)/g_trans_n);",
            "            if(g_trans_i<=0){ transition_end(); g_trans_phase = 0; }",
            "        }",
        ]
    L += [
        f"        if(g_current_scene>=0 && g_current_scene<{n_scenes})",
        "            g_scene_vtable[g_current_scene].tick();",
        "    }",
        "    return 0;",
        "}",
    ]

    out = p.src_dir / "main.c"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    emit("log_line", f"[gen] {out.relative_to(p.root)}")
    return True
