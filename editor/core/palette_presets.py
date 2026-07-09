"""
editor/core/palette_presets.py — Palettes GBA par défaut d'un projet neuf.

Deux palettes DMG (Nintendo Game Boy) fidèles au hardware + un jeu de
palettes "templates" d'exemple, empruntées à la communauté pixel-art (cf.
README, section Crédits — elles appartiennent à leurs auteurs).

Index 0 réservé (toujours transparent au niveau hardware, cf.
PaletteBank.__post_init__) — les palettes 16 couleurs sont donc réduites à
15 couleurs utiles + le slot transparent.
"""
from __future__ import annotations

import colorsys

from core.color_utils import rgb888_to_bgr555, RESERVED_SLOT_COLOR


def hsb_ramp_bgr555(hue_deg: float, sat: float, steps: int = 16) -> list[int]:
    """Rampe de `steps` couleurs, même teinte/saturation, luminosité
    décroissante (0.95 -> 0.08), converties en BGR555 GBA."""
    hue = (hue_deg % 360) / 360.0
    colors = []
    for i in range(steps):
        v = 0.95 - (0.95 - 0.08) * (i / (steps - 1))
        r, g, b = colorsys.hsv_to_rgb(hue, sat, v)
        colors.append(rgb888_to_bgr555(round(r * 255), round(g * 255), round(b * 255)))
    return colors


# ── DMG (Nintendo Game Boy) ─────────────────────────────────────────────
# Vert monochrome. Sur GB, un OBJ (sprite) utilise 3 nuances (l'index 0 est
# transparent) et un BG utilise les 4 teintes du registre BGP — d'où deux
# palettes distinctes de 3 et 4 couleurs.
_DMG_HUE, _DMG_SAT = 100, 0.45


# ── Palettes "templates" d'exemple ──────────────────────────────────────
# 16 couleurs chacune (hex RGB), réduites à 15 utiles au seed (index 0
# réservé). Chaque palette appartient à son auteur — voir README (Crédits).
_SAMPLE_PALETTES = [
    ("Miyazaki 16", ["232228", "284261", "5f5854", "878573", "b8b095", "c3d5c7",
                     "ebecdc", "2485a6", "54bad2", "754d45", "c65046", "e6928a",
                     "1e7453", "55a058", "a1bf41", "e3c054"]),
    ("NA16", ["8c8fae", "584563", "3e2137", "9a6348", "d79b7d", "f5edba",
              "c0c741", "647d34", "e4943a", "9d303b", "d26471", "70377f",
              "7ec4c1", "34859d", "17434b", "1f0e1c"]),
    ("PICO-8", ["000000", "1D2B53", "7E2553", "008751", "AB5236", "5F574F",
                "C2C3C7", "FFF1E8", "FF004D", "FFA300", "FFEC27", "00E436",
                "29ADFF", "83769C", "FF77A8", "FFCCAA"]),
    ("Soft 16", ["fefed7", "dbbc96", "ddac46", "c25940", "683d64", "9c6659",
                 "88434f", "4d2831", "a9aba3", "666869", "51b1ca", "1773b8",
                 "639f5b", "376e49", "323441", "161323"]),
    ("Mystic 16", ["160d13", "31293e", "4d6660", "95b666", "ef9e4e", "ad4030",
                   "56212a", "904b41", "a69998", "5f575e", "8eb89e", "f6f2c3",
                   "e79b7c", "9b4c63", "432142", "d1935f"]),
    ("Colorquest 16", ["99d4aa", "498e86", "324859", "437a4d", "7dbe58", "eadb77",
                       "dc8254", "c13d37", "61363d", "b06163", "e6af89", "fff9e5",
                       "c1a68c", "8b6962", "0d0b0d", "9d5745"]),
    ("Commodore 64", ["000000", "626262", "898989", "adadad", "ffffff", "9f4e44",
                      "cb7e75", "6d5412", "a1683c", "c9d487", "9ae29b", "5cab5e",
                      "6abfc6", "887ecb", "50459b", "a057a3"]),
    ("Microsoft Windows 16", ["000000", "7e7e7e", "bebebe", "ffffff", "7e0000",
                              "fe0000", "047e00", "06ff04", "7e7e00", "ffff04",
                              "00007e", "0000ff", "7e007e", "fe00ff", "047e7e",
                              "06ffff"]),
]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _reduce_to(colors: list[tuple[int, int, int]], n: int) -> list[tuple[int, int, int]]:
    """Réduit `colors` à `n` en retirant à chaque fois l'une des deux
    couleurs les plus proches (distance RGB²) — garde les couleurs EXACTES
    (pas de moyenne), perte perceptuelle minimale. Ordre source préservé
    pour ce qui reste."""
    colors = list(colors)
    while len(colors) > n:
        best = None
        drop = 0
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                d = sum((a - b) ** 2 for a, b in zip(colors[i], colors[j]))
                if best is None or d < best:
                    best, drop = d, j
        colors.pop(drop)
    return colors


def generate_default_banks() -> list:
    """Catalogue de palettes d'un projet neuf : DMG OBJ (3 couleurs) + DMG
    BG (4 couleurs) + les palettes d'exemple. Index 0 réservé partout."""
    from core.project import PaletteBank

    banks = [
        PaletteBank(name="DMG (GB Default)",
                    colors=[RESERVED_SLOT_COLOR] + hsb_ramp_bgr555(_DMG_HUE, _DMG_SAT, steps=3)),
        PaletteBank(name="DMG (GB Default) (BG)",
                    colors=[RESERVED_SLOT_COLOR] + hsb_ramp_bgr555(_DMG_HUE, _DMG_SAT, steps=4)),
    ]
    for name, hexes in _SAMPLE_PALETTES:
        rgbs = _reduce_to([_hex_to_rgb(h) for h in hexes], 15)
        banks.append(PaletteBank(
            name=name,
            colors=[RESERVED_SLOT_COLOR] + [rgb888_to_bgr555(*c) for c in rgbs],
        ))
    return banks
