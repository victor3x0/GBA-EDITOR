"""
ui/text_editor/glyph_paint.py — helpers de rendu partagés par les trois vues de
glyphes (planche, case isolée, aperçu écran).

Pendant côté AFFICHAGE de `Font.key_colors()` : les trois doivent trouer
pareil, sinon l'une promet un rendu que la ROM ne tiendra pas.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QPixmap, QPainter, QColor, QImage, QBrush

from ui.common.theme import C


def key_out(px: Optional[QPixmap], keys) -> Optional[QPixmap]:
    """Copie de `px` où les couleurs de `keys` deviennent transparentes.
    Retourne l'original tel quel si rien n'est à trouer."""
    if px is None or px.isNull() or not keys:
        return px
    import numpy as np
    # RGBA8888 : ordre R,G,B,A garanti, contrairement à ARGB32 (BGRA sur x86).
    img = px.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    arr = (np.frombuffer(ptr, dtype=np.uint8)
             .reshape(h, img.bytesPerLine())[:, :w * 4]
             .reshape(h, w, 4).copy())
    mask = np.zeros((h, w), dtype=bool)
    for k in keys:
        mask |= np.all(arr[:, :, :3] == np.array(tuple(k), dtype=np.uint8), axis=2)
    arr[mask] = 0
    # .copy() : `arr` est un tampon Python, l'image ne doit pas rester dessus.
    return QPixmap.fromImage(
        QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy())


def checker_brush(base=None) -> QBrush:
    """Damier de transparence — même convention que l'écran Palette.

    `base` teinte les deux tuiles (fond d'épreuve du `BackdropButton`) ; `None`
    garde le fond sombre de l'éditeur. Le damier reste, même sur un fond clair :
    c'est lui qui dit « transparent » plutôt que « pixel de cette couleur »."""
    if base is None:
        lo, hi = QColor(C.BG_DEEP), QColor(C.BG_RAISED)
    else:
        lo = QColor(base)
        # Seconde tuile décalée vers le contraste : plus sombre sur un fond
        # clair, plus claire sur un fond sombre — visible dans les deux sens.
        hi = lo.darker(115) if lo.lightness() > 128 else lo.lighter(135)
    px = QPixmap(16, 16)
    px.fill(lo)
    q = QPainter(px)
    q.fillRect(0, 0, 8, 8, hi)
    q.fillRect(8, 8, 8, 8, hi)
    q.end()
    return QBrush(px)
