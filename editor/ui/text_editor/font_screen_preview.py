"""
ui/text_editor/font_screen_preview.py — aperçu écran GBA d'un texte, rendu avec
les vrais glyphes de la police.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QFont, QImage, QPainter, QPen, QColor
from PyQt6.QtCore import Qt, QRect, QPoint

from core.engine_emulation.text_layout import layout_text
from codegen.font_build import build_font_asset
from core.font_rasterizer import FontRasterizerError, display_coverage
from ui.common.theme import C, T
from ui.common.labels import label
from ui.common.backdrop_button import BackdropButton


class FontScreenPreview(QWidget):
    """Écran GBA simulé, dessiné avec les VRAIS glyphes de la police : ce qui
    s'affiche ici est ce que la console affichera.

    À ne pas confondre avec `ScreenTextPreview` (ui/common), simple jauge de
    longueur à chasse fixe de 8 px, qui se trompe dès qu'une police 16×16 ou une
    ligature entre en jeu.

    Le widget est son propre viewport : molette = zoom, clic-central = pan,
    double-clic = retour à l'ajustement automatique — mêmes gestes que la
    planche de glyphes et que le canvas du Scene Manager.
    """

    GBA_W, GBA_H = 240, 160
    TILE = 8
    MIN_ZOOM, MAX_ZOOM = 1, 8
    FIT_MAX = 3          # l'ajustement automatique ne dépasse pas ×3
    MARGIN = 24          # px d'écran qui restent forcément atteignables au pan

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._text = ""
        self._render_font = None
        self._render_text = None
        self._render_error = ""
        self._glyph_images: dict[str, QImage] = {}
        # Zoom None = ajusté au volet ; un chiffre = choisi à la molette, et il
        # ne bouge plus quand on redimensionne.
        self._zoom: Optional[int] = None
        self._pan = QPoint(0, 0)
        self._pan_last: Optional[QPoint] = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)

        # Fond d'épreuve : posé DANS l'aperçu, en bas à gauche — il commente ce
        # qu'on regarde, pas la table des textes.
        self._btn_bg = BackdropButton(self)
        self._btn_bg.changed.connect(self.update)

    def set_font_asset(self, font, project):
        """Choisit une recette de police, comme le font les TextBox.

        Une FontAsset peut provenir d'une planche bitmap ou d'une fonte
        vectorielle : il n'y a donc volontairement aucune planche PNG à
        charger ici. Le même sous-ensemble temporaire que le build est produit
        à la demande par :func:`build_font_asset`.
        """
        self._font, self._project = font, project
        self._invalidate_render()
        self.update()

    def set_text(self, text: str):
        self._text = text or ""
        self._invalidate_render()
        self.update()

    def _invalidate_render(self):
        self._render_font = None
        self._render_text = None
        self._render_error = ""
        self._glyph_images = {}

    def _font_for_text(self):
        """Matérialise la recette uniquement pour les caractères visibles.

        C'est le pont utilisé par le build ; le preview ne doit surtout pas
        réinventer une lecture directe des sources de la FontAsset.
        """
        if self._render_text == self._text:
            return self._render_font
        self._render_text, self._render_font, self._render_error = self._text, None, ""
        self._glyph_images = {}
        if not self._font or not self._project:
            return None
        try:
            chars = {char for char in self._text if char not in "\r\n"} or {" "}
            self._render_font = build_font_asset(
                self._project, self._font, chars,
            )
        except FontRasterizerError as exc:
            self._render_error = str(exc)
        return self._render_font

    def _glyph_image(self, glyph) -> QImage:
        """Cellule GBA du glyphe, avec le même dépôt que l'encodeur ROM."""
        cached = self._glyph_images.get(glyph.char)
        if cached is not None:
            return cached
        image = QImage(max(1, glyph.w), max(1, glyph.h), QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.transparent)
        raster = self._render_font.raster_glyphs.get(glyph.char)
        if raster is not None:
            base_y = max(0, glyph.h - raster.bearing_y)
            for y in range(raster.height):
                for x in range(raster.width):
                    dx, dy = raster.bearing_x + x, base_y + y
                    if not (0 <= dx < image.width() and 0 <= dy < image.height()):
                        continue
                    coverage = display_coverage(
                        raster.coverage_at(x, y), dx, dy,
                        raster_mode=self._font.raster_mode,
                        threshold=self._font.coverage_threshold,
                        dither_pattern=self._font.dither_pattern,
                    )
                    if coverage:
                        image.setPixelColor(dx, dy, QColor(255, 255, 255, coverage))
        self._glyph_images[glyph.char] = image
        return image

    # ── Fond d'épreuve ────────────────────────────────────────────

    @staticmethod
    def _readable_on(bg: QColor) -> QColor:
        """Encre lisible sur `bg` — les messages de l'aperçu doivent survivre
        au fond blanc comme au fond noir."""
        return QColor("#1a1a22") if bg.lightness() > 140 else QColor(C.TEXT_DIM)

    # ── Géométrie ─────────────────────────────────────────────────

    def _fit_scale(self) -> int:
        """Échelle ENTIÈRE qui tient dans le volet : le pixel art ne supporte
        pas l'interpolation."""
        if not self.width() or not self.height():
            return 1
        return max(1, min(self.width() // self.GBA_W,
                          self.height() // self.GBA_H, self.FIT_MAX))

    def _scale(self) -> int:
        return self._zoom if self._zoom is not None else self._fit_scale()

    def _origin(self) -> QPoint:
        """Coin haut-gauche de l'écran simulé : centré dans le volet, décalé du
        pan. Centré parce que la largeur du volet ne tombe jamais juste sur un
        multiple de 240 — collé à gauche, ça se lirait comme un désalignement."""
        s = self._scale()
        return QPoint((self.width() - self.GBA_W * s) // 2 + self._pan.x(),
                      (self.height() - self.GBA_H * s) // 2 + self._pan.y())

    def _clamp_pan(self):
        """Garde toujours un morceau d'écran dans le volet — panné trop loin, il
        serait introuvable sans barres de défilement."""
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        cx, cy = (self.width() - w) // 2, (self.height() - h) // 2
        m = self.MARGIN
        self._pan.setX(max(m - w - cx, min(self._pan.x(), self.width() - m - cx)))
        self._pan.setY(max(m - h - cy, min(self._pan.y(), self.height() - m - cy)))

    def reset_view(self):
        """Retour à l'ajustement automatique, écran recentré."""
        self._zoom = None
        self._pan = QPoint(0, 0)
        self.update()

    def resizeEvent(self, e):
        self._btn_bg.move(8, self.height() - self._btn_bg.height() - 8)
        self._clamp_pan()
        super().resizeEvent(e)

    # ── Zoom / pan ────────────────────────────────────────────────

    def wheelEvent(self, e):
        """Molette = zoom, en gardant le point visé sous le curseur (sinon le
        mot qu'on lit fuit hors du volet)."""
        old = self._scale()
        new = max(self.MIN_ZOOM,
                  min(old + (1 if e.angleDelta().y() > 0 else -1), self.MAX_ZOOM))
        if new == old:
            e.accept()
            return
        # Point visé en coordonnées ÉCRAN GBA avant le zoom : le centrage
        # dépend de l'échelle, il doit sortir du calcul.
        o, pos = self._origin(), e.position()
        gx, gy = (pos.x() - o.x()) / old, (pos.y() - o.y()) / old
        self._zoom = new
        cx = (self.width() - self.GBA_W * new) // 2
        cy = (self.height() - self.GBA_H * new) // 2
        self._pan = QPoint(round(pos.x() - gx * new) - cx,
                           round(pos.y() - gy * new) - cy)
        self._clamp_pan()
        self.update()
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            # Pan au clic-central — même geste que le canvas du Scene Manager.
            self._pan_last = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan_last is not None and (e.buttons() & Qt.MouseButton.MiddleButton):
            pos = e.position().toPoint()
            self._pan += pos - self._pan_last
            self._pan_last = pos
            self._clamp_pan()
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        """Double-clic = vue remise à plat, pour sortir d'un zoom perdu sans
        compter les crans de molette."""
        self.reset_view()
        e.accept()

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        bg = self._btn_bg.color()
        ink = self._readable_on(bg)

        p.fillRect(self.rect(), QColor(C.BG_DEEP))
        o = self._origin()
        p.translate(o)
        p.fillRect(QRect(0, 0, w, h), bg)
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(QRect(0, 0, w - 1, h - 1))

        font = self._font_for_text()
        if not self._font:
            p.setPen(ink)
            p.setFont(QFont(T.UI, T.XS))
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       label("fsprev.choose_font"))
            return
        if font is None:
            p.setPen(ink)
            p.setFont(QFont(T.UI, T.XS))
            p.drawText(QRect(12, 12, w - 24, h - 24), Qt.AlignmentFlag.AlignCenter,
                       self._render_error or label("fsprev.choose_font"))
            return

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        placed, over = layout_text(font, self._text,
                                   self.GBA_W, self.GBA_H)
        for g, px, py in placed:
            image = self._glyph_image(g)
            p.drawImage(QRect(px * s, py * s, image.width() * s, image.height() * s), image)

        if over:
            p.setPen(QColor(C.ACCENT_YLW))
            p.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            p.drawText(QRect(0, h - 16, w - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       label("fsprev.overflows"))

        # Facteur affiché dans le VOLET, pas dans l'écran : c'est une donnée de
        # l'éditeur, elle n'a rien à faire sur la surface simulée.
        p.resetTransform()
        p.setPen(QColor(C.TEXT_MUTED))
        p.setFont(QFont(T.MONO, T.XS))
        p.drawText(QRect(0, self.height() - 20, self.width() - 8, 14),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"×{s}" + ("" if self._zoom is None else label("fsprev.dbl_fit")))
