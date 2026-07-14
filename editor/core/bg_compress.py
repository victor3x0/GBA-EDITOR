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
GBA_SCREEN_W = 240
GBA_SCREEN_H = 160


def _tile_to_hex(tile: list) -> str:
    """Tuile (64 index 0-15) -> 64 caractères hex (1 nibble/index). Compact + JSON."""
    return "".join("%x" % (i & 0xF) for i in tile)


def _hex_to_tile(s: str) -> list:
    return [int(ch, 16) for ch in s]


def _tile_to_hex8(tile: list) -> str:
    """Tuile 8bpp (64 index 0-255) -> 128 caractères hex (2/octet)."""
    return "".join("%02x" % (i & 0xFF) for i in tile)


def _hex_to_tile8(s: str) -> list:
    return [int(s[i:i + 2], 16) for i in range(0, len(s), 2)]


def detect_bpp(source) -> int:
    """Mode couleur conseillé : 8 si l'image a > 256 couleurs distinctes, sinon 4.
    Instantané (getcolors s'arrête à 256). Ne modifie pas le source."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGB")
    return 8 if img.getcolors(maxcolors=256) is None else 4


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


def _open_padded(source):
    """Ouvre le source en RGBA, paddé à un multiple de 8. Retourne (img, w, h,
    tw, th) où (w,h) sont les dimensions D'ORIGINE (avant padding)."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    tw, th = (w + 7) // 8, (h + 7) // 8
    if w % 8 or h % 8:
        padded = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
        padded.paste(img, (0, 0))
        img = padded
    return img, w, h, tw, th


def _extract_tile_colors(img) -> tuple:
    """Grilles de pixels + jeu de couleurs opaques par tuile (couleurs snappées
    5-bit). `img` doit déjà être RGBA et paddé. Retourne (tw, th, tile_grids,
    tile_colors). Partagé entre compression et diagnostic (aucune divergence)."""
    w, h = img.size
    tw, th = w // 8, h // 8
    px = img.load()
    tile_grids: list = []   # 64 éléments : (r,g,b) ou None (transparent)
    tile_colors: list = []  # set de couleurs opaques
    for ty in range(th):
        for tx in range(tw):
            grid, colors = [], set()
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
    return tw, th, tile_grids, tile_colors


def _pack_palettes(tile_colors: list, editable: int, method: str) -> tuple:
    """Packing glouton (PRÉ-fusion) des palettes : chaque tuile (réduite à
    <=`editable` couleurs) rejoint une palette existante si l'union tient, sinon
    en ouvre une. Retourne (palettes, tile_pal, tile_cmap). Partagé entre
    compression et diagnostic."""
    palettes: list = []          # list[list[(r,g,b)]] (ordre = index 1..N)
    tile_pal: list = [0] * len(tile_colors)
    tile_cmap: list = [None] * len(tile_colors)   # réduction couleur par tuile si >15
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
    return palettes, tile_pal, tile_cmap


def analyze_background_source(source, max_colors: int = 16,
                             method: str = "median_cut") -> dict:
    """Diagnostic NON-DESTRUCTIF d'un PNG de fond — ce que la compression devra
    faire, SANS construire le tileset (chemin léger, pour valider un asset déjà
    importé). Le fichier n'est jamais modifié."""
    img, w, h, tw, th = _open_padded(source)
    editable = max_colors - 1
    _, _, _, tile_colors = _extract_tile_colors(img)
    palettes, _, tile_cmap = _pack_palettes(tile_colors, editable, method)
    return {
        "src_w": w, "src_h": h,
        "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
        "tiles_w": tw, "tiles_h": th,
        "max_tile_colors": max((len(c) for c in tile_colors), default=0),
        "tiles_reduced": sum(1 for cm in tile_cmap if cm),
        "pre_merge_palettes": len(palettes),
    }


def compress_background(source, max_palettes: int = 16, max_colors: int = 16,
                        method: str = "median_cut") -> dict:
    """PNG -> représentation GBA (palettes BGR555 + tileset + tilemap). Ne modifie
    jamais le source. `max_colors`=16 (dont index 0 transparent), `max_palettes`=16.
    Le résultat inclut un sous-dict `diagnostics` (pression de compression : couleurs
    par tuile, palettes avant fusion, dimensions) pour le validateur de l'éditeur."""
    img, w, h, tw, th = _open_padded(source)
    editable = max_colors - 1   # 15 couleurs utiles + index 0 transparent

    # 1. Grille de pixels + jeu de couleurs par tuile (couleurs snappées 5-bit).
    _, _, tile_grids, tile_colors = _extract_tile_colors(img)

    # 2. Packing glouton des palettes (pré-fusion).
    palettes, tile_pal, tile_cmap = _pack_palettes(tile_colors, editable, method)
    pre_merge_palettes = len(palettes)
    max_tile_colors = max((len(c) for c in tile_colors), default=0)
    tiles_reduced = sum(1 for cm in tile_cmap if cm)

    # 2b. Cap RAPIDE à max_palettes. L'ancienne fusion des paires les plus proches
    #     était en O(P³) (une photo → des centaines de palettes → l'éditeur gelait
    #     ~7 min). On garde plutôt les palettes les plus utilisées et on réaffecte
    #     les tuiles des autres à la palette gardée la plus proche (recouvrement de
    #     couleurs max), en comblant ses emplacements libres pour limiter la perte ;
    #     la perte résiduelle est absorbée par le nearest de l'étape 3. Coût O(P·k).
    if len(palettes) > max_palettes:
        usage = [0] * len(palettes)
        for pi in tile_pal:
            usage[pi] += 1
        keep = sorted(range(len(palettes)), key=lambda i: usage[i], reverse=True)[:max_palettes]
        keep_sets = [set(palettes[i]) for i in keep]
        remap = {old: new for new, old in enumerate(keep)}   # kept -> index compacté
        for old in range(len(palettes)):
            if old in remap:
                continue
            cset = set(palettes[old])
            best = max(range(len(keep)), key=lambda k: len(keep_sets[k] & cset))
            kpal = palettes[keep[best]]
            for c in palettes[old]:            # comble les slots libres (≤ editable)
                if len(kpal) >= editable:
                    break
                if c not in keep_sets[best]:
                    kpal.append(c)
                    keep_sets[best].add(c)
            remap[old] = best
        palettes = [palettes[i] for i in keep]
        tile_pal = [remap[pi] for pi in tile_pal]

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
        "bpp": 4,
        # Diagnostics (validateur éditeur) — le source n'est jamais modifié.
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "max_tile_colors": max_tile_colors,   # couleurs opaques max dans une tuile
            "tiles_reduced": tiles_reduced,       # tuiles > 15 couleurs (réduites, perte)
            "pre_merge_palettes": pre_merge_palettes,  # palettes avant le cap à 16
            "final_palettes": len(pal_lists),     # palettes après fusion
            "unique_tiles": len(tileset),         # budget VRAM
        },
    }


def compress_background_8bpp(source, dither: bool = False) -> dict:
    """PNG -> représentation GBA 8bpp : UNE palette de ≤256 couleurs, tuiles en
    octets (index 0-255), dédup (flips). Ne modifie jamais le source. Rapide : le
    quantifieur C de PIL fait le gros du travail (pas de packing multi-palettes).
    L'index 0 est réservé/transparent (pixels alpha 0)."""
    from PIL import Image
    img, w, h, tw, th = _open_padded(source)
    alpha = img.getchannel("A").load()
    rgb = img.convert("RGB")
    dmode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    # 255 couleurs : l'index 0 reste réservé au transparent.
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=dmode)
    qidx = q.load()
    pal_raw = q.getpalette() or []   # [r,g,b, ...]

    pal256 = [RESERVED_SLOT_COLOR]   # slot 0 réservé
    for i in range(255):
        base = i * 3
        if base + 2 < len(pal_raw):
            pal256.append(rgb888_to_bgr555(pal_raw[base], pal_raw[base + 1], pal_raw[base + 2]))
        else:
            pal256.append(0)

    gc = rgb.getcolors(maxcolors=65536)
    total_colors = len(gc) if gc is not None else -1   # -1 = très nombreux

    tileset: list = []
    lookup: dict = {}
    tilemap: list = []
    for ty in range(th):
        for tx in range(tw):
            grid = []
            for y in range(8):
                for x in range(8):
                    px, py = tx * 8 + x, ty * 8 + y
                    if alpha[px, py] == 0:
                        grid.append(0)
                    else:
                        grid.append((qidx[px, py] + 1) & 0xFF)   # 1..255
            tid, fh, fv = _dedup_tile(tuple(grid), lookup, tileset)
            tilemap.append(pack_se(tid, 0, fh, fv))

    return {
        "palettes": [pal256],                              # UNE palette de 256
        "tileset": [_tile_to_hex8(t) for t in tileset],    # list[str] (128 hex/tuile)
        "tilemap": tilemap,
        "tiles_w": tw,
        "tiles_h": th,
        "compress_method": "quantize_256",
        "bpp": 8,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "multiple_of_8": (w % 8 == 0 and h % 8 == 0),
            "tiles_w": tw, "tiles_h": th,
            "total_colors": total_colors,   # couleurs distinctes du source (-1 = >65536)
            "unique_tiles": len(tileset),
            "dither": dither,
            "bpp": 8,
        },
    }


def _render_bg_preview_8bpp(compiled: dict):
    """Rendu 8bpp : tuiles en octets, une seule palette de 256."""
    from PIL import Image
    tw, th = compiled["tiles_w"], compiled["tiles_h"]
    tiles = [_hex_to_tile8(t) for t in compiled["tileset"]]
    pal = compiled["palettes"][0] if compiled["palettes"] else []
    rgb = [bgr555_to_rgb888(c) for c in pal]
    out = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
    px = out.load()
    for cell, se in enumerate(compiled["tilemap"]):
        tid, _pb, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            grid = _flip_h(grid)
        if fv:
            grid = _flip_v(grid)
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(rgb):
                    continue
                r, g, b = rgb[idx]
                px[ox + x, oy + y] = (r, g, b, 255)
    return out


def render_bg_preview(compiled: dict):
    """Reconstruit l'image RGBA depuis la représentation compressée (aperçu éditeur)."""
    from PIL import Image
    if compiled.get("bpp", 4) == 8:
        return _render_bg_preview_8bpp(compiled)
    tw, th = compiled["tiles_w"], compiled["tiles_h"]
    tiles = [_hex_to_tile(t) for t in compiled["tileset"]]
    palettes = compiled["palettes"]
    pal_rgb = [[bgr555_to_rgb888(c) for c in pal] for pal in palettes]
    out = Image.new("RGBA", (tw * 8, th * 8), (0, 0, 0, 0))
    px = out.load()
    # Défensif (comme BgLayerRaster côté scène) : un tile_id ou un pal_bank hors
    # limites (données legacy/incohérentes, ou banque référencée absente après
    # édition de palettes) ne doit pas faire planter le rendu — on retombe sur la
    # tuile vide / la palette 0, et on ignore les index de couleur hors palette.
    for cell, se in enumerate(compiled["tilemap"]):
        tid, pb, fh, fv = unpack_se(se)
        grid = tuple(tiles[tid]) if tid < len(tiles) else tuple([0] * 64)
        if fh:
            grid = _flip_h(grid)
        if fv:
            grid = _flip_v(grid)
        rgb = pal_rgb[pb] if pb < len(pal_rgb) else (pal_rgb[0] if pal_rgb else [])
        ox, oy = (cell % tw) * 8, (cell // tw) * 8
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(rgb):
                    continue
                r, g, b = rgb[idx]
                px[ox + x, oy + y] = (r, g, b, 255)
    return out


def compress_background_bitmap(source, dither: bool = False) -> dict:
    """PNG -> représentation GBA Mode 4 : bitmap plein écran ≤240×160, 8bpp (un
    index par pixel) + palette de 256. L'image est ajustée « contain » (ratio
    préservé, jamais agrandie) dans 240×160. Le source n'est jamais modifié.
    Rapide (quantifieur C de PIL). Convient aux photos (pas de tuiles → pas de
    limite de déduplication)."""
    from PIL import Image
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGBA")
    w, h = img.size
    scale = min(GBA_SCREEN_W / w, GBA_SCREEN_H / h, 1.0)   # jamais d'agrandissement
    out_w = max(1, min(GBA_SCREEN_W, round(w * scale)))
    out_h = max(1, min(GBA_SCREEN_H, round(h * scale)))
    if (out_w, out_h) != (w, h):
        img = img.resize((out_w, out_h), Image.LANCZOS)
    alpha = img.getchannel("A").load()
    rgb = img.convert("RGB")
    dmode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=dmode)
    qidx = q.load()
    pal_raw = q.getpalette() or []

    pal256 = [RESERVED_SLOT_COLOR]
    for i in range(255):
        base = i * 3
        if base + 2 < len(pal_raw):
            pal256.append(rgb888_to_bgr555(pal_raw[base], pal_raw[base + 1], pal_raw[base + 2]))
        else:
            pal256.append(0)

    buf = bytearray(out_w * out_h)
    for y in range(out_h):
        row = y * out_w
        for x in range(out_w):
            buf[row + x] = 0 if alpha[x, y] == 0 else ((qidx[x, y] + 1) & 0xFF)

    gc = rgb.getcolors(maxcolors=65536)
    total_colors = len(gc) if gc is not None else -1
    return {
        "mode": "bitmap",
        "palettes": [pal256],
        "bitmap": buf.hex(),
        "out_w": out_w, "out_h": out_h,
        "bpp": 8,
        "diagnostics": {
            "src_w": w, "src_h": h,
            "out_w": out_w, "out_h": out_h,
            "scaled": (out_w, out_h) != (w, h),
            "total_colors": total_colors,
            "dither": dither,
            "mode": "bitmap",
        },
    }


def render_bitmap_preview(compiled: dict):
    """Reconstruit l'image RGBA d'un fond bitmap (Mode 4) : buffer d'index + palette
    256. Trivial (pas de tuiles)."""
    from PIL import Image
    w, h = compiled["out_w"], compiled["out_h"]
    pal = compiled["palettes"][0] if compiled["palettes"] else []
    rgb = [bgr555_to_rgb888(c) for c in pal]
    buf = bytes.fromhex(compiled["bitmap"])
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = out.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            idx = buf[row + x] if row + x < len(buf) else 0
            if idx == 0 or idx >= len(rgb):
                continue
            r, g, b = rgb[idx]
            px[x, y] = (r, g, b, 255)
    return out


def detect_bg_mode(source, tile_budget: int = TILE_BUDGET) -> str:
    """'bitmap' si l'image ne rentrera pas en tuilé (tuiles 8×8 uniques estimées >
    budget — typiquement une photo), sinon 'tiled'. Estimation rapide via numpy
    (sans dédup de flips → borne haute suffisante pour trancher photo vs pixel-art)."""
    from PIL import Image
    try:
        import numpy as np
    except Exception:
        return "tiled"
    img = (source if hasattr(source, "mode") else Image.open(source)).convert("RGB")
    w, h = img.size
    tw, th = w // 8, h // 8
    if tw == 0 or th == 0:
        return "tiled"
    a = (np.asarray(img)[:th * 8, :tw * 8, :3] & 0xF8)
    a = a.reshape(th, 8, tw, 8, 3).transpose(0, 2, 1, 3, 4).reshape(th * tw, 8 * 8 * 3)
    uniq = len(np.unique(a, axis=0))
    return "bitmap" if uniq > tile_budget else "tiled"


def bg_fits_vram(tileset: list, budget: int = TILE_BUDGET) -> tuple[bool, int]:
    """(rentre ?, budget) — nombre de tuiles uniques vs budget VRAM d'un charblock."""
    return len(tileset) <= budget, budget
