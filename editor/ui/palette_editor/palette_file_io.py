"""ui/palette_editor/palette_file_io.py — interopérabilité fichiers de palette.

Lecture/écriture des formats d'échange courants (.gpl GIMP, .pal JASC, liste
hexadécimale) en RGB888 — la conversion BGR555 reste à la charge de l'appelant.
"""
from __future__ import annotations

import re
from pathlib import Path

_HEX6 = re.compile(r"#?([0-9a-fA-F]{6})")


def parse_palette_file(path: Path) -> list[tuple[int, int, int]]:
    """Extrait une liste de couleurs RGB888 depuis un .gpl (GIMP), .pal (JASC)
    ou une liste hexadécimale/RVB. Tolérant : ignore entêtes et commentaires."""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    head = lines[0].strip().lower() if lines else ""
    out: list[tuple[int, int, int]] = []
    if head.startswith("jasc-pal"):
        for ln in lines[3:]:
            nums = ln.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    elif head.startswith("gimp palette"):
        for ln in lines[1:]:
            s = ln.strip()
            if not s or s.startswith("#") or ":" in s:   # commentaires / Name:/Columns:
                continue
            nums = s.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    else:                                                # liste hex ou "R G B"
        for ln in lines:
            m = _HEX6.findall(ln)
            if m:
                out += [(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)) for h in m]
                continue
            nums = ln.split()
            if len(nums) >= 3 and all(n.isdigit() for n in nums[:3]):
                out.append(tuple(min(255, int(n)) for n in nums[:3]))
    return out


def serialize_palette(name: str, rgb: list[tuple[int, int, int]], fmt: str) -> str:
    """Sérialise `rgb` (RGB888) au format 'gpl', 'pal' (JASC) ou 'hex'."""
    if fmt == "pal":
        return "\n".join(["JASC-PAL", "0100", str(len(rgb))]
                         + [f"{r} {g} {b}" for r, g, b in rgb]) + "\n"
    if fmt == "hex":
        return "\n".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in rgb) + "\n"
    return "\n".join(["GIMP Palette", f"Name: {name}", "Columns: 16", "#"]
                     + [f"{r:>3} {g:>3} {b:>3}\tindex {i}"
                        for i, (r, g, b) in enumerate(rgb)]) + "\n"
