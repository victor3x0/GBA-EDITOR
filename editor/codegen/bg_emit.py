"""codegen/bg_emit.py — émet un fond COMPRESSÉ (métadonnées BackgroundAsset) en C.

Produit des tableaux compatibles grit ({sym}Tiles / {sym}TilesLen / {sym}Map)
pour réutiliser tel quel le chargement de main_gen (copy16 + load_map). La
différence vs grit : les SE portent un pal_bank PAR TUILE et le fond utilise
jusqu'à 16 palettes (chargées via g_pal_bg, cf. main_gen), là où grit ne fait
qu'une palette de 16.
"""
from __future__ import annotations


def _tile_words(hextile: str) -> list[int]:
    """Tuile (64 nibbles hex, index 0-15) -> 8 mots u32 (format tuile 4bpp GBA :
    pixel i de la rangée dans le nibble i)."""
    idx = [int(ch, 16) for ch in hextile]
    return [sum((idx[r * 8 + i] & 0xF) << (4 * i) for i in range(8)) for r in range(8)]


def tileset_words(tileset: list) -> list[int]:
    out: list[int] = []
    for t in tileset:
        out += _tile_words(t)
    return out


def bg_palette_words(palettes: list) -> list[int]:
    """≤16 palettes -> 256 mots BGR555 (16 banques × 16), pour PAL_BG_RAM / g_pal_bg."""
    words = [0] * 256
    for b, pal in enumerate(palettes[:16]):
        for i, c in enumerate(pal[:16]):
            words[b * 16 + i] = c
    return words


def emit_bg_c(sym: str, tileset: list, tilemap: list, pal_offset: int = 0) -> tuple[str, str]:
    """Retourne (source .c, header .h) compatibles grit pour un fond compressé.

    `pal_offset` : banque physique de la 1ère sous-palette de ce fond dans
    PAL_BG_RAM (allouée par palette_alloc.scene_bank_layout — plusieurs fonds
    compressés d'une même scène occupent des blocs de banques distincts). Les
    SE stockent un pal_bank LOCAL (0..N-1, relatif à la palette de l'asset) ;
    on le décale ici vers sa banque physique réelle."""
    tiles = tileset_words(tileset)
    se = [(w + (pal_offset << 12)) & 0xFFFF for w in tilemap] if pal_offset else list(tilemap)
    tiles_len = len(tiles) * 4
    attr = '__attribute__((aligned(4)))'
    c = (
        f"const unsigned int {sym}Tiles[{len(tiles)}] {attr}=\n"
        "{" + ",".join(f"0x{w:08X}" for w in tiles) + "};\n\n"
        f"const unsigned short {sym}Map[{len(se)}] {attr}=\n"
        "{" + ",".join(f"0x{w:04X}" for w in se) + "};\n"
    )
    h = (
        f"#ifndef GRIT_{sym.upper()}_H\n#define GRIT_{sym.upper()}_H\n\n"
        f"#define {sym}TilesLen {tiles_len}\n"
        f"extern const unsigned int {sym}Tiles[{len(tiles)}];\n\n"
        f"extern const unsigned short {sym}Map[{len(se)}];\n\n"
        f"#endif // GRIT_{sym.upper()}_H\n"
    )
    return c, h
