"""
core/sprite_compose.py — Composition d'une frame de sprite depuis son PNG source.

Extrait de ui/sprite_editor_screen.py : logique de traitement d'image pure
(PIL), sans dépendance PyQt, réutilisable par l'UI sprite editor ET par le
canvas de scène (core/scene_editor.py).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from core.project import AnimFrame


def compose_frame_image(abs_path: Optional[Path], frame: AnimFrame, fw: int, fh: int):
    """Compose une frame fw×fh en peignant chaque tuile 8×8 depuis le PNG source (PIL Image)."""
    from PIL import Image
    out = Image.new("RGBA", (max(fw, 1), max(fh, 1)), (0, 0, 0, 0))
    if not abs_path or not abs_path.exists() or not frame.tiles:
        return out
    try:
        img = Image.open(abs_path).convert("RGBA")
        sw, sh = img.size
        for t in frame.tiles:
            sx, sy = t.src_col * 8, t.src_row * 8
            if sx < 0 or sy < 0 or sx + 8 > sw or sy + 8 > sh:
                continue
            piece = img.crop((sx, sy, sx + 8, sy + 8))
            if t.flip_h:
                piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
            if t.flip_v:
                piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
            dx, dy = t.dst_col * 8, t.dst_row * 8
            out.paste(piece, (dx, dy), piece)
    except Exception:
        pass
    return out
