"""
ui/text_editor/font_screen_preview.py — aperçu écran GBA d'un texte, rendu avec
les vrais glyphes de la police.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, QRect

from core.text_layout import layout_text
from ui.common.theme import C, T
from ui.text_editor.glyph_paint import key_out


class FontScreenPreview(QWidget):
    """Écran GBA simulé, dessiné avec les VRAIS glyphes de la police : ce qui
    s'affiche ici est ce que la console affichera.

    À ne pas confondre avec `ScreenTextPreview` (ui/common), simple jauge de
    longueur à chasse fixe de 8 px, qui se trompe dès qu'une police 16×16 ou une
    ligature entre en jeu.
    """

    GBA_W, GBA_H = 240, 160
    TILE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._sheet: Optional[QPixmap] = None
        self._text = ""
        self._overflow = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)

    def set_font_asset(self, font, project):
        """Charge la planche de `font` et la met en cache, déjà trouée."""
        self._font, self._project = font, project
        self._sheet = None
        if font and project and font.asset:
            path = project.asset_abs(font.asset)
            if path and path.exists():
                px = QPixmap(str(path))
                # Trouée : sur une planche opaque, chaque glyphe sortirait en
                # pavé de couleur de fond — l'inverse de ce que fait la ROM.
                self._sheet = None if px.isNull() else key_out(px, font.key_colors())
        self.update()

    def set_text(self, text: str):
        self._text = text or ""
        self.update()

    # ── Géométrie ─────────────────────────────────────────────────

    def _scale(self) -> int:
        """Échelle ENTIÈRE : le pixel art ne supporte pas l'interpolation."""
        return max(1, min(self.width() // self.GBA_W, 3)) if self.width() else 1

    def resizeEvent(self, e):
        self.setFixedHeight(self.GBA_H * self._scale() + 2)
        super().resizeEvent(e)

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        # Écran CENTRÉ : la largeur du volet ne tombe jamais juste sur un
        # multiple de 240, et collé à gauche il se lirait comme un désalignement.
        p.translate(max(0, (self.width() - w) // 2), 0)
        p.fillRect(QRect(0, 0, w, h), QColor(C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(QRect(0, 0, w - 1, h - 1))

        if not self._sheet or not self._font:
            p.setPen(QColor(C.TEXT_MUTED))
            p.setFont(QFont(T.MONO, T.XS))
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "Choisir une police d'aperçu")
            return

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        placed, over = layout_text(self._font, self._text,
                                   self.GBA_W, self.GBA_H)
        for g, px, py in placed:
            src = QRect(g.x, g.y, g.w, g.h)
            dst = QRect(px * s, py * s, g.w * s, g.h * s)
            p.drawPixmap(dst, self._sheet, src)

        if over:
            p.setPen(QColor(C.ACCENT_YLW))
            p.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            p.drawText(QRect(0, h - 16, w - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "déborde de l'écran")
