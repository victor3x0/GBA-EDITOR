"""editor/ui/common/palette_swatch.py — Icône QIcon générée depuis une PaletteBank.

Partagé entre l'écran Palette Editor et les widgets de sélection de palette
(ScriptSlot/ScriptPickerPopup réutilisés en picker de palette).
"""
from __future__ import annotations

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt

from ui.common.theme import C
from core.project import PaletteBank
from core.color_utils import bgr555_to_rgb888


def _qcolor(v: int) -> QColor:
    r, g, b = bgr555_to_rgb888(v)
    return QColor(r, g, b)


def bank_icon(bank: PaletteBank, size: int = 16) -> QIcon:
    """Icone 2x2 échantillonnant 4 couleurs de la banque (claire -> sombre).
    Grisée si la banque n'a pas encore de couleurs (slot réservé). L'index 0
    (toujours réservé/transparent) est exclu de l'échantillonnage — sinon un
    quadrant afficherait la même couleur pour toutes les banques du catalogue."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    half = size // 2
    editable = bank.colors[1:] if len(bank.colors) > 1 else bank.colors
    if editable:
        n = len(editable)
        stops = [editable[min(i * (n - 1) // 3, n - 1)] for i in range(4)]
        for (x, y), c in zip([(0, 0), (half, 0), (0, half), (half, half)], stops):
            painter.fillRect(x, y, half, half, _qcolor(c))
    else:
        painter.fillRect(0, 0, size, size, QColor(C.BG_INPUT))
        painter.setPen(QColor(C.BORDER_MID))
        painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return QIcon(px)
