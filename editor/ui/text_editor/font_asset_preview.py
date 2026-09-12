"""Aperçu comparatif fondé sur les ``RasterGlyph`` du pipeline."""
from __future__ import annotations

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QTextEdit, QSpinBox, QFrame)
from PyQt6.QtGui import (QFont, QImage, QColor, QPainter, QPen, QBrush,
                         QRadialGradient, QGradient)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRect

from core.font_rasterizer import (FontRasterizerError, FontRasterizerUnavailable,
                                  display_coverage, rasterize_asset_glyph)
from ui.common.theme import C, T, QSS
from ui.common.labels import label


_SAMPLE = "AaBb 0123!?\nInterligne"


class _RasterComparisonCanvas(QWidget):
    """Deux rendus synchronisés : grille de tuiles, zoom et panoramique.

    Le canevas est unique pour empêcher les deux moitiés de se décaler l'une
    par rapport à l'autre pendant une comparaison.
    """

    MIN_ZOOM, MAX_ZOOM = 1, 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coverage = self._output = QImage()
        self._zoom = 5
        self._pan = QPoint(0, 0)
        self._pan_last = None
        self._hover = None
        self.setMinimumHeight(136)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_images(self, coverage: QImage, output: QImage):
        self._coverage, self._output = coverage, output
        self.update()

    def clear(self):
        self._coverage = self._output = QImage()
        self.update()

    def _image_rect(self, image: QImage, side: int, zoom=None) -> QRect:
        zoom = self._zoom if zoom is None else zoom
        half = self.width() // 2
        x0, width = (0, half) if side == 0 else (half + 1, self.width() - half - 1)
        w, h = image.width() * zoom, image.height() * zoom
        return QRect(x0 + (width - w) // 2 + self._pan.x(),
                     (self.height() - h) // 2 + self._pan.y(), w, h)

    def paintEvent(self, _event):
        painter = QPainter(self)
        # Une vraie surface de visualisation, pas un champ éditable : le noir
        # l'éloigne visuellement des contrôles placés au-dessus.
        painter.fillRect(self.rect(), QColor(C.BG_DEEP))
        if self._coverage.isNull() and self._output.isNull():
            return
        for side, image in enumerate((self._coverage, self._output)):
            if image.isNull():
                continue
            rect = self._image_rect(image, side)
            viewport = self._viewport(side)
            # Chaque moitié est un viewport réel. Rien, ni la grille ni un
            # rendu panné, ne peut passer de l'autre côté du séparateur.
            painter.save()
            painter.setClipRect(viewport)
            self._draw_grid(painter, viewport, rect)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(rect, image)
            self._draw_reveal(painter, viewport, rect)
            painter.restore()
        painter.setPen(QPen(QColor(C.BORDER_MID)))
        painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height())
        painter.setPen(QColor(C.TEXT_MUTED))
        painter.setFont(QFont(T.MONO, T.XS))
        painter.drawText(7, self.height() - 7, f"x{self._zoom}")

    def _viewport(self, side: int) -> QRect:
        half = self.width() // 2
        return QRect(0, 0, half, self.height()) if side == 0 else QRect(
            half + 1, 0, self.width() - half - 1, self.height())

    def _grid_lines(self, painter: QPainter, viewport: QRect, image_rect: QRect):
        """Dessine une grille alignée sur l'origine du rendu, mais qui se
        prolonge en arrière-plan du viewport pour rester lisible au pan."""
        tile = 8 * self._zoom
        start_x = image_rect.left() + ((viewport.left() - image_rect.left()) // tile) * tile
        start_y = image_rect.top() + ((viewport.top() - image_rect.top()) // tile) * tile
        for x in range(start_x, viewport.right() + tile, tile):
            painter.drawLine(x, viewport.top(), x, viewport.bottom())
        for y in range(start_y, viewport.bottom() + tile, tile):
            painter.drawLine(viewport.left(), y, viewport.right(), y)

    def _draw_grid(self, painter: QPainter, viewport: QRect, image_rect: QRect):
        """Grille grise permanente, à peine visible sur le fond noir."""
        pen = QPen(QColor(150, 150, 165, 28))
        pen.setCosmetic(True)
        painter.setPen(pen)
        self._grid_lines(painter, viewport, image_rect)

    def _draw_reveal(self, painter: QPainter, viewport: QRect, image_rect: QRect):
        """La grille blanche n'est jamais une sélection : un dégradé radial
        n'en révèle que la zone proche du pointeur, sans case encadrée."""
        if self._hover is None or not viewport.contains(self._hover):
            return
        halo = QRadialGradient(QPointF(self._hover), float(max(48, 12 * self._zoom)))
        halo.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
        halo.setColorAt(0.0, QColor(255, 255, 255, 145))
        halo.setColorAt(0.35, QColor(255, 255, 255, 72))
        halo.setColorAt(1.0, QColor(255, 255, 255, 0))
        pen = QPen(QBrush(halo), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        self._grid_lines(painter, viewport, image_rect)

    def wheelEvent(self, event):
        old = self._zoom
        new = max(self.MIN_ZOOM, min(self.MAX_ZOOM, old + (1 if event.angleDelta().y() > 0 else -1)))
        if new == old:
            event.accept(); return
        pos = event.position().toPoint()
        side = 0 if pos.x() < self.width() // 2 else 1
        image = self._coverage if side == 0 else self._output
        if not image.isNull():
            old_rect = self._image_rect(image, side, old)
            gx, gy = (pos.x() - old_rect.x()) / old, (pos.y() - old_rect.y()) / old
            self._zoom = new
            base = self._image_rect(image, side, new)
            self._pan += QPoint(round(pos.x() - base.x() - gx * new),
                                round(pos.y() - base.y() - gy * new))
        else:
            self._zoom = new
        self.update(); event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._hover = event.position().toPoint()
        if self._pan_last is not None and event.buttons() & Qt.MouseButton.MiddleButton:
            pos = event.position().toPoint()
            self._pan += pos - self._pan_last
            self._pan_last = pos
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None; self.unsetCursor(); event.accept(); return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._hover = None; self.update(); super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-clic : retrouve instantanément la vue de comparaison."""
        self._zoom, self._pan = 5, QPoint(0, 0)
        self.update(); event.accept()


class FontAssetPreview(QWidget):
    """Compare la couverture et la sortie finale sur un texte libre."""

    field_changed = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._asset = self._project = None
        self._blocking = False

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = QLabel(label("fontasset.preview_title")); header.setFixedHeight(28)
        header.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold)); header.setStyleSheet(QSS.title_panel)
        header.setContentsMargins(8, 0, 8, 0); root.addWidget(header)
        body = QWidget(); body.setStyleSheet(f"background:{C.BG_BASE};")
        lay = QVBoxLayout(body); lay.setContentsMargins(32, 16, 32, 18); lay.setSpacing(8)
        # Le nom et le réglage qui lui appartient le plus sont réunis : le
        # sommet du panneau est un en-tête compact, pas un second titre d'écran.
        meta = QHBoxLayout(); meta.setSpacing(8)
        self._name = QLabel(""); self._name.setFont(QFont(T.MONO, T.LG, QFont.Weight.DemiBold)); self._name.setStyleSheet(f"color:{C.ACCENT};")
        meta.addWidget(self._name); meta.addStretch()
        size_label = QLabel(label("fontasset.preview_size")); size_label.setStyleSheet(QSS.label_field); meta.addWidget(size_label)
        self._size = QSpinBox(); self._size.setRange(1, 128); self._size.setSuffix(" px"); self._size.setFont(QFont(T.MONO, T.SM)); self._size.setStyleSheet(QSS.spinbox)
        self._size.setToolTip(label("fontasset.preview_size_tip")); meta.addWidget(self._size)
        lay.addLayout(meta)

        text_label = QLabel(label("fontasset.preview_sample_text")); text_label.setStyleSheet(QSS.label_field)
        lay.addWidget(text_label)
        text_row = QHBoxLayout(); text_row.setSpacing(0)
        self._text = QTextEdit(_SAMPLE); self._text.setAcceptRichText(False)
        self._text.setPlaceholderText(label("fontasset.preview_text_placeholder")); self._text.setToolTip(label("fontasset.preview_text_tip"))
        self._text.setFixedHeight(48); self._text.setFont(QFont(T.MONO, T.SM))
        self._text.setStyleSheet(f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI}; border:1px solid {C.BORDER_MID}; border-radius:4px; padding:4px;}} QTextEdit:focus{{border-color:{C.ACCENT};}}")
        text_row.addWidget(self._text, 1); lay.addLayout(text_row)

        headings = QHBoxLayout(); headings.setSpacing(0)
        coverage_heading = QLabel(label("fontasset.preview_coverage")); coverage_heading.setAlignment(Qt.AlignmentFlag.AlignCenter); coverage_heading.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold)); coverage_heading.setStyleSheet(f"color:{C.TEXT_NORM};")
        output_heading = QLabel(label("fontasset.preview_output")); output_heading.setAlignment(Qt.AlignmentFlag.AlignCenter); output_heading.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold)); output_heading.setStyleSheet(f"color:{C.TEXT_NORM};")
        heading_divider = QFrame(); heading_divider.setFrameShape(QFrame.Shape.VLine); heading_divider.setStyleSheet(f"color:{C.BORDER_MID}; background:{C.BORDER_MID};"); heading_divider.setFixedWidth(1)
        headings.addWidget(coverage_heading, 1); headings.addWidget(heading_divider); headings.addWidget(output_heading, 1)
        lay.addLayout(headings)
        self._canvas = _RasterComparisonCanvas(); self._canvas.setToolTip(label("fontasset.preview_canvas_tip")); lay.addWidget(self._canvas, 1)
        footer = QFrame(); footer.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")
        footer_lay = QVBoxLayout(footer); footer_lay.setContentsMargins(8, 6, 8, 6); footer_lay.setSpacing(2)
        self._summary = QLabel(""); self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter); self._summary.setFont(QFont(T.MONO, T.SM)); self._summary.setStyleSheet(f"color:{C.TEXT_NORM}; border:none;"); footer_lay.addWidget(self._summary)
        self._status = QLabel(""); self._status.setAlignment(Qt.AlignmentFlag.AlignCenter); self._status.setWordWrap(True); self._status.setFont(QFont(T.UI, T.SM)); self._status.setStyleSheet(f"color:{C.TEXT_MUTED}; border:none;"); footer_lay.addWidget(self._status)
        lay.addWidget(footer)
        root.addWidget(body, 1)
        self._text.textChanged.connect(self._render); self._size.valueChanged.connect(self._size_changed)

    def load(self, asset, project):
        self._asset, self._project = asset, project
        self._blocking = True; self._name.setText(asset.name if asset else ""); self._size.setValue(asset.pixel_height if asset else 8); self._blocking = False
        self._canvas.clear()
        if asset is None:
            self._summary.setText(""); self._status.setText(""); return
        sources = " → ".join(asset.source_names()) or label("common.none_dash")
        self._summary.setText(label("fontasset.preview_summary", pixel_height=asset.pixel_height, line_height=asset.line_height, hinting=asset.hinting, pixel_fit=asset.pixel_fit, raster_mode=asset.raster_mode, sources=sources))
        self._render()

    def refresh(self):
        if self._asset is not None:
            self.load(self._asset, self._project)

    def _size_changed(self, value):
        if not self._blocking and self._asset is not None and value != self._asset.pixel_height:
            self.field_changed.emit("pixel_height", value)

    def _render(self):
        if self._asset is None or self._project is None:
            return
        try:
            glyphs = [None if char == "\n" else rasterize_asset_glyph(self._project, self._asset, char) for char in self._text.toPlainText().replace("\r", "")]
            self._canvas.set_images(self._compose(glyphs, raster_mode="coverage"), self._compose(glyphs, raster_mode=self._asset.raster_mode))
            self._status.setText(self._quality_message(glyphs))
        except FontRasterizerUnavailable as exc:
            self._canvas.clear(); self._status.setText(label("fontasset.preview_unavailable", detail=str(exc)))
        except FontRasterizerError as exc:
            self._canvas.clear(); self._status.setText(label("fontasset.preview_error", detail=str(exc)))

    def _compose(self, glyphs, *, raster_mode: str) -> QImage:
        baseline = max((g.bearing_y for g in glyphs if g is not None), default=0) + 2
        pen_x, line_y, placements = 2, 0, []
        min_y, max_y, max_x = 0, max(1, baseline + 2), 2
        for glyph in glyphs:
            if glyph is None:
                pen_x, line_y = 2, line_y + self._asset.line_height; max_y = max(max_y, line_y + baseline + 2); continue
            x, y = pen_x + glyph.bearing_x, line_y + baseline - glyph.bearing_y
            placements.append((glyph, x, y)); min_y, max_y = min(min_y, y), max(max_y, y + glyph.height)
            pen_x += max(1, glyph.advance); max_x = max(max_x, pen_x + 2)
        width, height = max(1, max_x), max(1, max_y - min_y + 2)
        image = QImage(width, height, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.transparent); ink = QColor(C.ACCENT)
        for glyph, x, y in placements:
            for gy in range(glyph.height):
                for gx in range(glyph.width):
                    alpha = display_coverage(glyph.coverage_at(gx, gy), gx, gy, raster_mode=raster_mode, threshold=self._asset.coverage_threshold, dither_pattern=self._asset.dither_pattern)
                    if alpha:
                        color = QColor(ink); color.setAlpha(alpha); image.setPixelColor(x + gx, y - min_y + gy, color)
        return image

    def _quality_message(self, glyphs) -> str:
        glyphs = [glyph for glyph in glyphs if glyph is not None]
        raw = sum(value > 0 for glyph in glyphs for value in glyph.coverage)
        final = sum(display_coverage(value, x, y, raster_mode=self._asset.raster_mode, threshold=self._asset.coverage_threshold, dither_pattern=self._asset.dither_pattern) > 0 for glyph in glyphs for y in range(glyph.height) for x, value in enumerate(glyph.coverage[y * glyph.width:(y + 1) * glyph.width]))
        kept = round(100 * final / raw) if raw else 100
        if self._asset.raster_mode != "coverage" and kept < 65:
            return label("fontasset.preview_ink_loss", kept=kept, threshold=self._asset.coverage_threshold)
        return label("fontasset.preview_live")
