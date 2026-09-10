"""Valeurs de secours et rampe neutre pour le runtime des palettes.

Ce module ne crée aucun asset de projet. Les palettes livrées avec un projet
neuf sont les fichiers ``editor/project_starters/Basic/project/palettes``.
"""

from __future__ import annotations

import colorsys

from core.models.gba_color import RESERVED_SLOT_COLOR, rgb888_to_bgr555


def hsb_ramp_bgr555(hue_deg: float, sat: float, steps: int = 16) -> list[int]:
    """Rampe BGR555, utilisée uniquement pour une palette créée à la demande."""
    hue = (hue_deg % 360) / 360.0
    colors = []
    for index in range(steps):
        value = 0.95 - (0.95 - 0.08) * (index / (steps - 1))
        r, g, b = colorsys.hsv_to_rgb(hue, sat, value)
        colors.append(rgb888_to_bgr555(round(r * 255), round(g * 255), round(b * 255)))
    return colors


# Contenu déterministe de la banque hardware 0 lorsque le build ne peut pas
# lui attribuer une palette de projet. Ce n'est pas une palette utilisateur.
DEFAULT_PAL_BANK_COLORS = [RESERVED_SLOT_COLOR] + hsb_ramp_bgr555(0, 0.0)[1:]
