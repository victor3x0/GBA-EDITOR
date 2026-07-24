"""codegen/font_emit.py — polices et textes émis en C.

**Police → tuiles.** Chaque glyphe est rendu dans une cellule de
`tiles_x × tiles_y` tuiles 8×8 (1 seule pour une police 8×8, le cas courant),
posées à la suite dans le charblock du layer d'UI. Un glyphe étant une tuile,
tout ce qui s'applique à une tuile s'applique au texte : `tilemap.set_palette`
le recolore, les windows le découpent, la priorité de layer le place.

**Texte → codepoints, pas glyphes.** Un texte est émis en `u16` Unicode et la
correspondance caractère → tuile est faite au runtime via la table de la police
courante. C'est ce qui rend un texte **indépendant de la police** : la même
entrée peut être rendue avec une autre police, ce dont la v0.8 aura besoin (une
traduction peut exiger un autre jeu de glyphes). Le coût est une recherche
dichotomique par caractère, à l'affichage — pas par frame.

Limite assumée : `u16` couvre le plan multilingue de base (BMP). Les émojis et
autres plans supplémentaires ne passent pas — sans objet pour une console qui
affiche des tuiles 8×8.
"""

from __future__ import annotations

from pathlib import Path

# Banque de palette BG réservée aux glyphes. Convention héritée du chemin TTE
# (`SE_PALBANK(15)`), conservée pour ne pas déplacer la contrainte existante.
FONT_PAL_BANK = 15

# Première tuile du charblock d'UI occupée par les glyphes : la tuile 0 reste
# vide/transparente, c'est elle que pose `text_clear`.
FONT_TILE_BASE = 1

_MAX_INK_COLORS = 15   # index 0 = transparent, restent 1..15


def _bgr555(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return ((r >> 3) & 31) | (((g >> 3) & 31) << 5) | (((b >> 3) & 31) << 10)


def _tile_words(idx: list[int]) -> list[int]:
    """64 index 4bpp (row-major) → 8 mots u32, format tuile GBA."""
    return [sum((idx[r * 8 + i] & 0xF) << (4 * i) for i in range(8)) for r in range(8)]


def encode_font(font, png_path: Path) -> dict:
    """Encode une police en tuiles 4bpp + table de correspondance.

    Retourne {tiles, n_tiles, codepoints, slots, palette, tiles_x, tiles_y,
    warning}. `codepoints` est TRIÉ (le runtime fait une dichotomie dessus) et
    `slots` donne, pour chaque codepoint, l'index de sa première tuile."""
    import numpy as np
    from PIL import Image

    img = Image.open(png_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]

    cw, ch = max(1, font.cell_w), max(1, font.cell_h)
    tiles_x, tiles_y = (cw + 7) // 8, (ch + 7) // 8

    # ── Palette : les couleurs d'encre les plus fréquentes ────────
    ink = alpha > 0
    warning = None
    if ink.any():
        flat = rgb[ink].reshape(-1, 3)
        colors, counts = np.unique(flat, axis=0, return_counts=True)
        order = np.argsort(-counts)
        kept = [tuple(int(v) for v in colors[i]) for i in order[:_MAX_INK_COLORS]]
        if len(colors) > _MAX_INK_COLORS:
            warning = (f"Police « {font.name} » : {len(colors)} couleurs, "
                       f"réduites aux {_MAX_INK_COLORS} plus fréquentes.")
    else:
        kept = []
        warning = f"Police « {font.name} » : planche entièrement vide."

    # index 0 = transparent, 1..15 = encre
    palette = [0] + [_bgr555(c) for c in kept]
    palette += [0] * (16 - len(palette))
    lut = {c: i + 1 for i, c in enumerate(kept)}

    def _index_of(px, a) -> int:
        if a == 0:
            return 0
        c = tuple(int(v) for v in px)
        hit = lut.get(c)
        if hit is not None:
            return hit
        # Couleur écartée : on prend la plus proche des retenues (distance
        # euclidienne, comme le reste du pipeline palette).
        if not kept:
            return 0
        best = min(range(len(kept)),
                   key=lambda i: sum((kept[i][k] - c[k]) ** 2 for k in range(3)))
        return best + 1

    # ── Glyphes → tuiles ─────────────────────────────────────────
    tiles: list[int] = []
    codepoints: list[int] = []
    slots: list[int] = []
    h_img, w_img = alpha.shape

    for gi, g in enumerate(font.glyphs):
        if not g.char:
            continue
        # Cellule vierge, puis dépôt du bitmap du glyphe à son offset. Le
        # BMFont `xoffset`/`yoffset` positionne le dessin dans la cellule ;
        # une planche régulière a simplement des offsets nuls.
        cell = [[0] * (tiles_x * 8) for _ in range(tiles_y * 8)]
        for yy in range(g.h):
            sy = g.y + yy
            dy = yy + g.oy
            if sy >= h_img or dy < 0 or dy >= tiles_y * 8:
                continue
            for xx in range(g.w):
                sx = g.x + xx
                dx = xx + g.ox
                if sx >= w_img or dx < 0 or dx >= tiles_x * 8:
                    continue
                cell[dy][dx] = _index_of(rgb[sy, sx], alpha[sy, sx])

        slot = FONT_TILE_BASE + len(tiles) // 8
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                block = [cell[ty * 8 + r][tx * 8 + c] for r in range(8) for c in range(8)]
                tiles += _tile_words(block)
        codepoints.append(ord(g.char[0]))
        slots.append(slot)

    # Tri conjoint : le runtime cherche par dichotomie sur `codepoints`.
    if codepoints:
        pairs = sorted(zip(codepoints, slots))
        codepoints = [c for c, _ in pairs]
        slots = [s for _, s in pairs]

    return {"tiles": tiles, "n_tiles": len(tiles) // 8,
            "codepoints": codepoints, "slots": slots, "palette": palette,
            "tiles_x": tiles_x, "tiles_y": tiles_y, "warning": warning}


# ── Émission C ────────────────────────────────────────────────────

def _c_ident(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name).upper()


def emit_fonts_c(encoded: list[tuple[str, dict]]) -> list[str]:
    """`encoded` = [(nom de police, résultat d'encode_font)] → lignes C.

    Émet un `FontInfo` par police et la table `g_fonts` que `text_set_font()`
    indexe. Une police vide donne quand même une entrée : mieux vaut un texte
    invisible qu'un projet qui ne linke pas."""
    L: list[str] = ["/* ── Polices ─────────────────────────────────────── */"]
    for name, e in encoded:
        sym = _c_ident(name)
        L.append(f"static const unsigned int g_font_{sym}_tiles[{max(1, len(e['tiles']))}] "
                 "__attribute__((aligned(4))) = {"
                 + (",".join(f"0x{w:08X}" for w in e["tiles"]) or "0") + "};")
        L.append(f"static const unsigned short g_font_{sym}_pal[16] = {{"
                 + ",".join(f"0x{w:04X}" for w in e["palette"]) + "};")
        L.append(f"static const unsigned short g_font_{sym}_cp[{max(1, len(e['codepoints']))}] = {{"
                 + (",".join(str(c) for c in e["codepoints"]) or "0") + "};")
        L.append(f"static const unsigned short g_font_{sym}_slot[{max(1, len(e['slots']))}] = {{"
                 + (",".join(str(s) for s in e["slots"]) or "0") + "};")
    L.append("")
    L.append(f"const FontInfo g_fonts[{max(1, len(encoded))}] = {{")
    if encoded:
        for name, e in encoded:
            sym = _c_ident(name)
            L.append(f"    {{ g_font_{sym}_tiles, {e['n_tiles']}, g_font_{sym}_pal, "
                     f"g_font_{sym}_cp, g_font_{sym}_slot, {len(e['codepoints'])}, "
                     f"{e['tiles_x']}, {e['tiles_y']} }},")
    else:
        L.append("    { 0, 0, 0, 0, 0, 0, 1, 1 },")
    L.append("};")
    L.append("")
    return L


def emit_texts_c(texts: list) -> list[str]:
    """Table des textes : un tableau de codepoints par entrée, plus les
    longueurs. Les `#define TEXT_<CLE>` sont émis par le codegen de script (là
    où vivent déjà SFX_*/MUSIC_*), pas ici."""
    L: list[str] = ["/* ── Textes ──────────────────────────────────────── */"]
    for i, t in enumerate(texts):
        cps = [ord(c) for c in t.content if ord(c) < 0x10000]
        L.append(f"static const unsigned short g_text_{i}[{max(1, len(cps))}] = {{"
                 + (",".join(str(c) for c in cps) or "0") + "};")
    L.append(f"const unsigned short* const g_texts[{max(1, len(texts))}] = {{"
             + (",".join(f"g_text_{i}" for i in range(len(texts))) or "0") + "};")
    L.append(f"const unsigned short g_text_len[{max(1, len(texts))}] = {{"
             + (",".join(str(len([c for c in t.content if ord(c) < 0x10000]))
                         for t in texts) or "0") + "};")
    L.append("")
    return L
