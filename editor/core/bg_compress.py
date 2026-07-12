"""core/bg_compress.py — compression NON-DESTRUCTIVE d'un fond GBA (Mode 0, 4bpp).

Transforme un PNG de fond en la représentation matérielle GBA, stockée en
métadonnées (le PNG source n'est jamais modifié) :
- jusqu'à 16 palettes de 16 couleurs (256), sélection par tuile ;
- un tileset de tuiles 8×8 UNIQUES (dédup + flips H/V) — c'est la dédup qui fait
  rentrer un grand niveau en VRAM ;
- une tilemap de SE (screen entries) : (tile_id, pal_bank, flip_h, flip_v) par case.

Algorithme glouton (MVP raffinable). Toutes les couleurs sont snappées en 5 bits
par canal (représentables en BGR555) dès l'extraction, donc la dédup couleur est
exacte vis-à-vis du hardware.
"""
from __future__ import annotations
from typing import Optional

from core.color_utils import (
    reduce_colors, nearest_rgb, rgb888_to_bgr555, bgr555_to_rgb888,
    RESERVED_SLOT_COLOR,
)

TILE_BUDGET = 512   # tuiles 4bpp par charblock (16 Ko)


def _tile_to_hex(tile: list) -> str:
    """Tuile (64 index 0-15) -> 64 caractères hex (1 nibble/index). Compact + JSON."""
    return "".join("%x" % (i & 0xF) for i in tile)


def _hex_to_tile(s: str) -> list:
    return [int(ch, 16) for ch in s]


def pack_se(tile_id: int, pal_bank: int, flip_h: bool, flip_v: bool) -> int:
    """Screen entry GBA : tile_id (0-9) | flip_h (10) | flip_v (11) | pal_bank (12-15)."""
    return (tile_id & 0x3FF) | (int(flip_h) << 10) | (int(flip_v) << 11) | ((pal_bank & 0xF) << 12)


def unpack_se(se: int) -> tuple[int, int, bool, bool]:
    return se & 0x3FF, (se >> 12) & 0xF, bool(se & 0x400), bool(se & 0x800)


def _snap5(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Snappe une couleur RGB888 sur la grille 5-bit/canal (représentable BGR555)."""
    return (r & 0xF8, g & 0xF8, b & 0xF8)


def _flip_h(grid: tuple) -> tuple:
    return tuple(grid[r * 8 + (7 - c)] for r in range(8) for c in range(8))


def _flip_v(grid: tuple) -> tuple:
    return tuple(grid[(7 - r) * 8 + c] for r in range(8) for c in range(8))


def _dedup_tile(idxgrid: tuple, lookup: dict, tileset: list) -> tuple[int, bool, bool]:
    """Renvoie (tile_id, flip_h, flip_v) : réutilise une tuile existante (ou son
    flip H/V/HV) si possible, sinon en crée une nouvelle."""
    if idxgrid in lookup:
        return lookup[idxgrid], False, False
    fh = _flip_h(idxgrid)
    if fh in lookup:
        return lookup[fh], True, False
    fv = _flip_v(idxgrid)
    if fv in lookup:
        return lookup[fv], False, True
    fhv = _flip_h(fv)
    if fhv in lookup:
        return lookup[fhv], True, True
    tid = len(tileset)
    tileset.append(list(idxgrid))
    lookup[idxgrid] = tid
    return tid, False, False


def compress_background(source, max_palettes: int = 16, max_colors: int = 16,
                        method: str = "median_cut") -> dict:
    """PNG -> représentation GBA (palettes BGR555 + tileset + tilemap). Ne modifie
    jamais le source. `max_colors`=16 (dont index 0 transparent), `max_palettes`=16."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    tw, th = (w + 7) // 8, (h + 7) // 8
    if w % 8 or h % 8:
        padded = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
        padded.paste(img, (0, 0))
        img = padded
    px = img.load()
    editable = max_colors - 1   # 15 couleurs utiles + index 0 transparent

    # 1. Grille de pixels + jeu de couleurs par tuile (couleurs snappées 5-bit).
    tile_grids: list = []       # 64 éléments : (r,g,b) ou None (transparent)
    tile_colors: list = []      # set de couleurs opaques
    for ty in range(th):
        for tx in range(tw):
            grid = []
            colors = set()
            for y in range(8):
                for x in range(8):
                    r, g, b, a = px[tx * 8 + x, ty * 8 + y]
                    if a == 0:
                        grid.append(None)
                    else:
                        c = _snap5(r, g, b)
                        grid.append(c)
                        colors.add(c)
            tile_grids.append(grid)
            tile_colors.append(colors)

    # 2. Packing glouton des palettes. Chaque tuile (réduite à <=15 couleurs)
    #    rejoint une palette existante si l'union tient, sinon en ouvre une.
    palettes: list = []          # list[list[(r,g,b)]] (ordre = index 1..N)
    tile_pal: list = [0] * len(tile_grids)
    tile_cmap: list = [None] * len(tile_grids)   # réduction couleur par tuile si >15
    for i, colors in enumerate(tile_colors):
        cols = list(colors)
        if len(cols) > editable:
            cmap = reduce_colors(cols, {c: 1 for c in cols}, editable, method)
            cols = list(dict.fromkeys(cmap.values()))
            tile_cmap[i] = cmap
        cset = set(cols)
        best = None
        for pi, pal in enumerate(palettes):
            if len(set(pal) | cset) <= editable:
                best = pi
                break
        if best is None:
            palettes.append(list(cset))
            best = len(palettes) - 1
        else:
            for c in cset:
                if c not in palettes[best]:
                    palettes[best].append(c)
        tile_pal[i] = best

    # 2b. Trop de palettes -> fusion des deux plus proches (union minimale), lossy.
    while len(palettes) > max_palettes:
        pair, best_u = None, None
        for a in range(len(palettes)):
            for b in range(a + 1, len(palettes)):
                u = len(set(palettes[a]) | set(palettes[b]))
                if best_u is None or u < best_u:
                    best_u, pair = u, (a, b)
        a, b = pair
        merged = list(dict.fromkeys(palettes[a] + palettes[b]))
        if len(merged) > editable:
            cmap = reduce_colors(merged, {c: 1 for c in merged}, editable, method)
            merged = list(dict.fromkeys(cmap.values()))
        palettes[a] = merged
        palettes.pop(b)
        for i in range(len(tile_pal)):
            if tile_pal[i] == b:
                tile_pal[i] = a
            elif tile_pal[i] > b:
                tile_pal[i] -= 1

    # 3. Indexation des pixels dans la palette de chaque tuile + dédup (flips).
    pal_lists = [list(pal) for pal in palettes]
    pal_index = [{c: k + 1 for k, c in enumerate(pal)} for pal in pal_lists]
    tileset: list = []
    lookup: dict = {}
    tilemap: list = []
    for i, grid in enumerate(tile_grids):
        pb = tile_pal[i]
        cmap = tile_cmap[i]
        pidx = pal_index[pb]
        pal = pal_lists[pb]
        idxgrid = []
        for c in grid:
            if c is None:
                idxgrid.append(0)
                continue
            cc = cmap[c] if cmap else c
            k = pidx.get(cc)
            if k is None:   # perdu à la fusion -> plus proche dans la palette
                k = pidx[nearest_rgb(cc, pal)] if pal else 0
            idxgrid.append(k)
        tid, fh, fv = _dedup_tile(tuple(idxgrid), lookup, tileset)
        tilemap.append(pack_se(tid, pb, fh, fv))

    return {
        "palettes": [[RESERVED_SLOT_COLOR] + [rgb888_to_bgr555(*c) for c in pal]
                     for pal in pal_lists],
        "tileset": [_tile_to_hex(t) for t in tileset],   # list[str] (64 hex nibbles)
        "tilemap": tilemap,                               # list[int] (screen entries GBA)
        "tiles_w": tw,
        "tiles_h": th,
        "compress_method": method,
    }


def render_bg_preview(compiled: dict):
    """Reconstruit l'image RGBA depuis la représentation compressée (aperçu éditeur)."""
    from PIL import Image
    tw, th = compiled["tiles_w"], compiled["tiles_h"]
    tiles = [_hex_to_tile(t) for t in compiled["tileset"]]
    palettes = compiled["palettes"]
    pal_rgb = [[bgr555_to_rgb888(c) for c in pal] for pal in palettes]
    out = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
    px = out.load()
    for cell, se in enumerate(compiled["tilemap"]):
        tid, pb, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid])
        if fh:
            grid = _flip_h(grid)
        if fv:
            grid = _flip_v(grid)
        rgb = pal_rgb[pb]
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0:
                    continue
                r, g, b = rgb[idx]
                px[ox + x, oy + y] = (r, g, b, 255)
    return out


def bg_fits_vram(tileset: list, budget: int = TILE_BUDGET) -> tuple[bool, int]:
    """(rentre ?, budget) — nombre de tuiles uniques vs budget VRAM d'un charblock."""
    return len(tileset) <= budget, budget
