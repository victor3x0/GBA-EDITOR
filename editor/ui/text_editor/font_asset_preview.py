"""Aperçu Qt fondé sur les ``RasterGlyph`` du pipeline, jamais sur QFont."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt6.QtGui import QFont, QImage, QPixmap, QColor
from PyQt6.QtCore import Qt

from core.font_rasterizer import (FontRasterizerError, FontRasterizerUnavailable,
                                  display_coverage, rasterize_asset_glyph)
from ui.common.theme import C, T, QSS
from ui.common.labels import label


_SAMPLE = "AaBb 0123!?"


class FontAssetPreview(QWidget):
    """Compose des RasterGlyph en image ; Qt se contente de les afficher."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Le pixmap de comparaison est volontairement agrandi ×5. Il ne doit
        # jamais devenir une largeur minimale de la colonne centrale : le
        # QSplitter des écrans éditeur doit pouvoir serrer ses trois volets.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._asset = self._project = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QLabel(label("fontasset.preview_title"))
        header.setFixedHeight(28)
        header.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        header.setStyleSheet(QSS.title_panel)
        header.setContentsMargins(8, 0, 8, 0)
        root.addWidget(header)

        body = QWidget(); body.setStyleSheet(f"background:{C.BG_BASE};")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 24, 32, 24); lay.setSpacing(10)
        lay.addStretch()
        self._name = QLabel("")
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setFont(QFont(T.MONO, T.LG, QFont.Weight.DemiBold))
        self._name.setStyleSheet(f"color:{C.ACCENT};")
        lay.addWidget(self._name)
        self._sample = QLabel(label("fontasset.preview_sample", sample=_SAMPLE))
        self._sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sample.setFont(QFont(T.MONO, T.XS))
        self._sample.setStyleSheet(f"color:{C.TEXT_MUTED};")
        lay.addWidget(self._sample)
        comparisons = QHBoxLayout(); comparisons.setSpacing(28)
        self._coverage_canvas = self._preview_column(
            comparisons, label("fontasset.preview_coverage"))
        self._output_canvas = self._preview_column(
            comparisons, label("fontasset.preview_output"))
        lay.addLayout(comparisons)
        self._summary = QLabel("")
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary.setFont(QFont(T.MONO, T.SM))
        self._summary.setStyleSheet(f"color:{C.TEXT_NORM};")
        lay.addWidget(self._summary)
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setFont(QFont(T.UI, T.SM))
        self._status.setStyleSheet(f"color:{C.TEXT_MUTED};")
        lay.addWidget(self._status)
        lay.addStretch()
        root.addWidget(body, 1)

    def load(self, asset, project):
        self._asset, self._project = asset, project
        self._name.setText(asset.name if asset else "")
        self._coverage_canvas.clear(); self._output_canvas.clear()
        if asset is None:
            self._summary.setText(""); self._status.setText("")
            return
        sources = " → ".join(asset.source_names()) or label("common.none_dash")
        self._summary.setText(label(
            "fontasset.preview_summary", pixel_height=asset.pixel_height,
            line_height=asset.line_height, hinting=asset.hinting,
            pixel_fit=asset.pixel_fit, raster_mode=asset.raster_mode, sources=sources,
        ))
        self._render()

    def _render(self):
        if self._asset is None or self._project is None:
            return
        try:
            glyphs = [rasterize_asset_glyph(self._project, self._asset, char)
                      for char in _SAMPLE]
            self._coverage_canvas.setPixmap(QPixmap.fromImage(
                self._compose(glyphs, raster_mode="coverage")))
            self._output_canvas.setPixmap(QPixmap.fromImage(
                self._compose(glyphs, raster_mode=self._asset.raster_mode)))
            self._status.setText(self._quality_message(glyphs))
        except FontRasterizerUnavailable as exc:
            self._status.setText(label("fontasset.preview_unavailable", detail=str(exc)))
        except FontRasterizerError as exc:
            self._status.setText(label("fontasset.preview_error", detail=str(exc)))

    @staticmethod
    def _preview_column(layout, title):
        column = QVBoxLayout(); column.setSpacing(4)
        heading = QLabel(title); heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        heading.setStyleSheet(f"color:{C.TEXT_NORM};")
        canvas = QLabel(); canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas.setMinimumWidth(0)
        canvas.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        canvas.setMinimumHeight(72)
        column.addWidget(heading); column.addWidget(canvas)
        layout.addLayout(column)
        return canvas

    def _compose(self, glyphs, *, raster_mode: str) -> QImage:
        baseline = max((glyph.bearing_y for glyph in glyphs), default=0) + 2
        pen, placements = 2, []
        min_y, max_y = 0, max(1, baseline + 2)
        for glyph in glyphs:
            x, y = pen + glyph.bearing_x, baseline - glyph.bearing_y
            placements.append((glyph, x, y))
            min_y, max_y = min(min_y, y), max(max_y, y + glyph.height)
            pen += max(1, glyph.advance)
        width, height = max(1, pen + 2), max(1, max_y - min_y + 2)
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        ink = QColor(C.ACCENT)
        for glyph, x, y in placements:
            for gy in range(glyph.height):
                for gx in range(glyph.width):
                    alpha = display_coverage(
                        glyph.coverage_at(gx, gy), gx, gy,
                        raster_mode=raster_mode,
                        threshold=self._asset.coverage_threshold,
                        dither_pattern=self._asset.dither_pattern,
                    )
                    if alpha:
                        color = QColor(ink); color.setAlpha(alpha)
                        image.setPixelColor(x + gx, y - min_y + gy, color)
        return image.scaled(width * 5, height * 5,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation)

    def _quality_message(self, glyphs) -> str:
        raw = sum(value > 0 for glyph in glyphs for value in glyph.coverage)
        final = sum(
            display_coverage(value, x, y, raster_mode=self._asset.raster_mode,
                             threshold=self._asset.coverage_threshold,
                             dither_pattern=self._asset.dither_pattern) > 0
            for glyph in glyphs
            for y in range(glyph.height)
            for x, value in enumerate(glyph.coverage[y * glyph.width:(y + 1) * glyph.width])
        )
        kept = round(100 * final / raw) if raw else 100
        if self._asset.raster_mode != "coverage" and kept < 65:
            return label("fontasset.preview_ink_loss", kept=kept,
                         threshold=self._asset.coverage_threshold)
        return label("fontasset.preview_live")

    def refresh(self):
        if self._asset is not None:
            self.load(self._asset, self._project)
