"""
editor/ui/common/screen_text_preview.py — jauge de longueur d'une chaîne,
rapportée à la largeur de l'écran GBA.

CE QUE C'EST : une règle graduée, volontairement grossière. On pose CELL px par
caractère sur une ligne de SCREEN_W px (l'écran GBA), on dessine avec la police
monospace de l'éditeur, et on marque la ligne qui dépasse. Chaque `\\n` = une
nouvelle ligne ; ce qui sort de l'écran est coupé (clip), pas replié. Sert à
répondre à une seule question : « cette chaîne a-t-elle une chance de tenir ? »

CE QUE ÇA NE PROMET PAS : le rendu de la ROM. Le moteur met en page avec
`text_layout` (runtime/include/gba_engine.h) — chasse propre à chaque glyphe,
correspondance au plus long (donc ligatures), coupe au mot. Rien de tout ça ici.
Sur une police proportionnelle, une police 16×16, ou dès qu'une ligature entre
en jeu, cet aperçu se trompe, et il se trompe dans les deux sens. La grille de
CELL px ne décrit AUCUNE police du projet : c'est une unité de mesure, pas une
police par défaut, et le moteur n'en a plus depuis le retrait de libtonc TTE.

Pour voir le vrai rendu, il faut une police : `FontScreenPreview`
(ui/text_editor/text_editor_screen.py) rejoue `text_layout` avec la planche de
glyphes réelle. On ne s'en sert pas ici parce qu'une chaîne exposée par un
script n'est liée à aucune police — et n'est même pas forcément du texte à
afficher.

L'écran logique (SCREEN_W) est mis à l'échelle pour remplir la largeur du
widget — la marque de dépassement tombe donc toujours au bord droit, quelle que
soit la largeur du panneau.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QPainter, QColor
from PyQt6.QtCore import Qt, QRectF

from ui.common.theme import C, T

SCREEN_W = 240          # largeur de l'écran GBA (px) — cf. SCREEN_W du runtime
CELL = 8                # avance fixe par caractère (px) — l'unité de la jauge
MAX_CELLS = SCREEN_W // CELL   # caractères tenant pleinement sur une ligne (30)


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
