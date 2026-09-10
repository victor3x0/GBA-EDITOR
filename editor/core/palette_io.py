"""Import et export des formats d'échange de palettes.

Cette couche ne lit pas les sources canoniques ``project/palettes/*.hex`` :
celles-ci sont définies par ``PaletteBank.from_hex``. Elle lit au contraire des
formats externes, tolérants et hétérogènes, pour les transformer en banque GBA.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.models.gba_color import (
    bgr555_to_rgb888, extract_palette_from_image, rgb888_to_bgr555,
)
from core.models.palette import PaletteBank


PALETTE_IMPORT_FILTER = "Palettes (*.gpl *.pal *.txt *.hex *.png);;All files (*)"
_HEX6 = re.compile(r"#?([0-9a-fA-F]{6})")


def parse_palette_file(path: Path) -> list[tuple[int, int, int]]:
    """Lit GPL, JASC PAL, liste hex ou lignes ``R G B`` en RGB888."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    head = lines[0].strip().lower() if lines else ""
    out: list[tuple[int, int, int]] = []
    if head.startswith("jasc-pal"):
        for line in lines[3:]:
            numbers = line.split()
            if len(numbers) >= 3 and all(number.isdigit() for number in numbers[:3]):
                out.append(tuple(min(255, int(number)) for number in numbers[:3]))
    elif head.startswith("gimp palette"):
        for line in lines[1:]:
            value = line.strip()
            if not value or value.startswith("#") or ":" in value:
                continue
            numbers = value.split()
            if len(numbers) >= 3 and all(number.isdigit() for number in numbers[:3]):
                out.append(tuple(min(255, int(number)) for number in numbers[:3]))
    else:
        for line in lines:
            hexes = _HEX6.findall(line)
            if hexes:
                out.extend((int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
                           for value in hexes)
                continue
            numbers = line.split()
            if len(numbers) >= 3 and all(number.isdigit() for number in numbers[:3]):
                out.append(tuple(min(255, int(number)) for number in numbers[:3]))
    return out


def parse_palette_image(path: Path) -> list[tuple[int, int, int]]:
    """Extrait jusqu'à 255 couleurs opaques d'un PNG, en précision GBA."""
    # Le helper existant sait ignorer l'alpha et réduire proprement un PNG trop
    # riche. Son slot 0 est réservé ; un fichier d'échange ne le transporte pas.
    return [bgr555_to_rgb888(color)
            for color in extract_palette_from_image(path, max_colors=255)[1:]]


def import_palette(path: Path, name: str | None = None) -> PaletteBank:
    """Crée une ``PaletteBank`` depuis un format externe, sans I/O de projet."""
    if path.suffix.lower() == ".png":
        colors = parse_palette_image(path)
        # Le PNG n'a pas de case transparente explicite : le helper la réserve
        # déjà. On garde donc toutes ses couleurs réelles après le slot 0.
        size = 256 if len(colors) > 15 else 16
        bgr = [0] + [rgb888_to_bgr555(*color) for color in colors[:size - 1]]
        bgr += [0] * (size - len(bgr))
    else:
        colors = parse_palette_file(path)
        size = 256 if len(colors) > 16 else 16
        # Compatibilité avec l'import historique : le premier slot du fichier
        # est le slot 0 de la banque GBA, donc rendu transparent par PaletteBank.
        bgr = [rgb888_to_bgr555(*color) for color in colors[:size]]
        bgr += [0] * (size - len(bgr))
    if not colors:
        raise ValueError("No color recognized in this file.")
    return PaletteBank(name=name or path.stem, colors=bgr, size=size)


def serialize_palette(name: str, rgb: list[tuple[int, int, int]], fmt: str) -> str:
    """Sérialise ``rgb`` au format GPL, JASC PAL ou liste hex."""
    if fmt == "pal":
        return "\n".join(["JASC-PAL", "0100", str(len(rgb))]
                         + [f"{r} {g} {b}" for r, g, b in rgb]) + "\n"
    if fmt == "hex":
        return "\n".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in rgb) + "\n"
    return "\n".join(["GIMP Palette", f"Name: {name}", "Columns: 16", "#"]
                     + [f"{r:>3} {g:>3} {b:>3}\tindex {index}"
                        for index, (r, g, b) in enumerate(rgb)]) + "\n"
