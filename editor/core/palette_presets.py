"""
editor/core/palette_presets.py — Palettes GBA pré-configurées.

Génère des rampes de 16 couleurs (plus claire -> plus sombre) depuis une
simple paire (teinte, saturation) HSB, pour que l'écran Palette ne parte
jamais d'un projet totalement vide. Pas de valeurs tapées à la main :
toute la richesse vient de la liste de teintes ci-dessous.
"""
from __future__ import annotations

import colorsys

from core.color_utils import rgb888_to_bgr555


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


# (nom, teinte en degrés, saturation 0-1) — 16 presets par pool.
_OBJ_PRESETS = [
    ("DMG (GB Default)", 100, 0.45),
    ("Ember",             20, 0.75),
    ("Coral Reef",       350, 0.55),
    ("Toxic Slime",       90, 0.65),
    ("Royal Purple",     270, 0.55),
    ("Ice Cave",         195, 0.35),
    ("Desert Dune",       35, 0.45),
    ("Cyber Neon",       320, 0.85),
    ("Autumn Leaf",       25, 0.65),
    ("Blood Moon",        355, 0.70),
    ("Forest Sprite",    130, 0.50),
    ("Golden Hour",        45, 0.60),
    ("Deep Ocean",        205, 0.60),
    ("Shadow Knight",     220, 0.15),
    ("Lavender Dream",    290, 0.40),
    ("Molten Core",        15, 0.85),
]

_BG_PRESETS = [
    ("DMG (GB Default)", 100, 0.40),
    ("Twilight Sky",     250, 0.50),
    ("Volcanic Rock",     10, 0.60),
    ("Misty Swamp",      110, 0.30),
    ("Starlit Void",     240, 0.55),
    ("Sandstone Ruins",   40, 0.40),
    ("Frozen Tundra",    200, 0.30),
    ("Neon City",         300, 0.75),
    ("Autumn Grove",      30, 0.55),
    ("Blood Canyon",       15, 0.65),
    ("Emerald Vale",      140, 0.55),
    ("Sunset Dunes",       25, 0.60),
    ("Abyssal Trench",    220, 0.50),
    ("Mossy Ruins",        95, 0.35),
    ("Crimson Dusk",        5, 0.55),
    ("Cosmic Drift",      260, 0.60),
]

def _bank_list(presets: list[tuple[str, float, float]]) -> list:
    from core.project import PaletteBank

    return [
        PaletteBank(name=name, colors=hsb_ramp_bgr555(hue, sat))
        for name, hue, sat in presets
    ]


def generate_default_banks() -> tuple[list, list]:
    """16 PaletteBank nommées pour chaque pool (OBJ, BG) — point de départ
    du catalogue illimité d'un projet neuf, pas une limite."""
    return _bank_list(_OBJ_PRESETS), _bank_list(_BG_PRESETS)
