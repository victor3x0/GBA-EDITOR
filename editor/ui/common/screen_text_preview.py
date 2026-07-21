"""
editor/ui/common/screen_text_preview.py — aperçu du rendu d'une chaîne sur
l'écran cible.

Simule un écran de largeur SCREEN_W px avec une police à chasse fixe de CELL px
par caractère (approximation de `fwf_default`, la police libtonc TTE utilisée
par le moteur — cf. runtime, tte_init_se + draw_printf qui positionne en
cellules de 8px). Chaque `\\n` = nouvelle ligne. Ce qui dépasse la largeur de
l'écran est coupé (clip) et la ligne trop longue est marquée : l'utilisateur
voit immédiatement si son texte est tronqué.

L'écran logique (SCREEN_W) est mis à l'échelle pour remplir la largeur du
widget — la troncature tombe donc toujours au bord droit, quelle que soit la
largeur du panneau.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QPainter, QColor
from PyQt6.QtCore import Qt, QRectF

from ui.common.theme import C, T

SCREEN_W = 260          # largeur écran cible (px logiques)
CELL = 8                # avance fixe par caractère (px logiques)
MAX_CELLS = SCREEN_W // CELL   # caractères tenant pleinement sur une ligne (32)


class ScreenTextPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = [""]
        self._overflow = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(int(CELL))

    def set_text(self, text: str):
        self._lines = (text or "").split("\n")
        self._overflow = any(len(line) > MAX_CELLS for line in self._lines)
        self._update_height()
        self.update()

    # ── Géométrie ─────────────────────────────────────────────────
    def _scale(self) -> float:
        return (self.width() or SCREEN_W) / SCREEN_W

    def _update_height(self):
        s = self._scale()
        self.setFixedHeight(max(1, int(len(self._lines) * CELL * s)) + 2)

    def resizeEvent(self, e):
        self._update_height()
        super().resizeEvent(e)

    # ── Rendu ─────────────────────────────────────────────────────
    def paintEvent(self, e):
        p = QPainter(self)
        s = self._scale()
        cell = CELL * s
        screen_px = int(SCREEN_W * s)
        clip_w = min(self.width(), screen_px)

        # Fond « écran »
        p.fillRect(self.rect(), QColor(C.BG_DEEP))

        font = QFont(T.MONO)
        font.setPixelSize(max(6, int(cell)))
        p.setFont(font)
        p.setPen(QColor(C.TEXT_HI))
        p.setClipRect(0, 0, clip_w, self.height())

        for r, line in enumerate(self._lines):
            y = r * cell
            for c, ch in enumerate(line):
                x = c * cell
                if x >= clip_w:      # entièrement hors écran → inutile de dessiner
                    break
                p.drawText(QRectF(x, y, cell, cell),
                           int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                           ch)

        # Marqueur de troncature : liseré rouge au bord droit de l'écran
        p.setClipping(False)
        if self._overflow:
            p.fillRect(clip_w - 2, 0, 2, self.height(), QColor(C.ACCENT_RED))

    @property
    def truncated(self) -> bool:
        return self._overflow
