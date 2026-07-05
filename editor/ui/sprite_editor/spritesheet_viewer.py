"""ui/sprite_editor/spritesheet_viewer.py — viewer du PNG source (tile picker)."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QScrollArea
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QRect

from ui.common.theme import C, T

# ── Viewer du spritesheet source (tile picker) ─────────────────────────────────

class _SpritesheetCanvas(QWidget):
    """Canvas interne du picker — grille 8×8, sélection multi-tiles, zoom, pan."""

    selection_changed = pyqtSignal(list)
    hover_changed      = pyqtSignal(object)  # (col, row) survolé, ou None

    def __init__(self, scroll_area=None, parent=None):
        super().__init__(parent)
        self._pixmap:    Optional[QPixmap]       = None
        self._zoom:      int                     = 2
        self._scroll_area                        = scroll_area   # pour le pan molette
        self._drag_start: Optional[tuple]        = None
        self._drag_end:   Optional[tuple]        = None
        self._selection:  list[tuple[int, int]]  = []
        self._mid_drag:   Optional[tuple]        = None   # pan (start_global, h_val, v_val)
        self._hover:      Optional[tuple]        = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Focus au clic — même raison que _FrameCanvas : permet à Shift+X/Y
        # (portés par SpriteCenterPanel) de marcher après une sélection ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def load(self, path: Optional[Path]):
        self._pixmap = QPixmap(str(path)) if path and path.exists() else None
        self._selection = []
        self._drag_start = self._drag_end = None
        self._update_size()
        self.update()

    def clear_selection(self):
        self._selection = []
        self._drag_start = self._drag_end = None
        self.update()
        self.selection_changed.emit([])

    def _update_size(self):
        if self._pixmap:
            self.setFixedSize(self._pixmap.width()  * self._zoom,
                              self._pixmap.height() * self._zoom)
        else:
            self.setFixedSize(200, 100)

    def _tile_at(self, pos) -> tuple[int, int]:
        tpx = 8 * self._zoom
        col = int(pos.x() // tpx)
        row = int(pos.y() // tpx)
        if self._pixmap:
            col = max(0, min(col, self._pixmap.width()  // 8 - 1))
            row = max(0, min(row, self._pixmap.height() // 8 - 1))
        return col, row

    # ── Événements ────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton and self._scroll_area:
            self._mid_drag = (e.globalPosition().toPoint(),
                              self._scroll_area.horizontalScrollBar().value(),
                              self._scroll_area.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._pixmap or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_start = self._tile_at(e.position())
        self._drag_end = self._drag_start
        self._recompute_selection()

    def mouseMoveEvent(self, e):
        if self._mid_drag and self._scroll_area:
            start, hv, vv = self._mid_drag
            delta = e.globalPosition().toPoint() - start
            self._scroll_area.horizontalScrollBar().setValue(hv - delta.x())
            self._scroll_area.verticalScrollBar().setValue(vv - delta.y())
            return
        if self._pixmap:
            cell = self._tile_at(e.position())
            if cell != self._hover:
                self._hover = cell
                self.hover_changed.emit(cell)
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        self._drag_end = self._tile_at(e.position())
        self._recompute_selection()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if e.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_end = self._tile_at(e.position())
            self._recompute_selection()
            self._drag_start = None

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._zoom = max(1, min(8, self._zoom + (1 if delta > 0 else -1)))
        self._update_size()
        self.update()
        e.accept()

    def _recompute_selection(self):
        if self._drag_start is None or self._drag_end is None:
            return
        c0, r0 = self._drag_start
        c1, r1 = self._drag_end
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        self._selection = [(c, r) for r in range(rmin, rmax + 1)
                           for c in range(cmin, cmax + 1)]
        self.update()
        self.selection_changed.emit(self._selection)

    def paintEvent(self, e):
        painter = QPainter(self)
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor(C.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Aucun PNG source")
            painter.end()
            return

        pw = self._pixmap.width()  * self._zoom
        ph = self._pixmap.height() * self._zoom
        painter.drawPixmap(QRect(0, 0, pw, ph), self._pixmap)

        tpx = 8 * self._zoom
        painter.setPen(QPen(QColor(0, 200, 100, 60), 1))
        x = 0
        while x <= pw:
            painter.drawLine(x, 0, x, ph); x += tpx
        y = 0
        while y <= ph:
            painter.drawLine(0, y, pw, y); y += tpx

        for col, row in self._selection:
            r = QRect(col * tpx, row * tpx, tpx, tpx)
            painter.fillRect(r, QColor(76, 175, 120, 80))
            painter.setPen(QPen(QColor(C.ACCENT_GRN), 1))
            painter.drawRect(r)

        painter.end()


class _SpritesheetViewer(QWidget):
    """Zone basse — spritesheet scrollable, picker multi-tiles, zoom, indicateur brosse."""

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header : titre + indicateur brosse + zoom
        _BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;"
            f"border:none;font-size:{T.MD}px;padding:0 4px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};}}"
        )
        hdr_w = QWidget()
        hdr_w.setFixedHeight(22)
        hdr_w.setStyleSheet(
            f"background:{C.BG_RAISED};border-bottom:1px solid {C.BORDER_DARK};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(8, 0, 4, 0)
        hdr_lay.setSpacing(4)

        lbl_tiles = QLabel("TILES")
        lbl_tiles.setFont(QFont(T.MONO, T.XS))
        lbl_tiles.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        hdr_lay.addWidget(lbl_tiles)

        hdr_lay.addStretch()

        self._brush_lbl = QLabel("Aucune brosse")
        self._brush_lbl.setFont(QFont(T.MONO, T.XS))
        self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._brush_lbl)

        hdr_lay.addSpacing(12)

        self._coord_lbl = QLabel("")
        self._coord_lbl.setFont(QFont(T.MONO, T.XS))
        self._coord_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._coord_lbl)

        hdr_lay.addSpacing(12)

        btn_zm = QToolButton(); btn_zm.setText("−"); btn_zm.setStyleSheet(_BTN)
        btn_zp = QToolButton(); btn_zp.setText("+"); btn_zp.setStyleSheet(_BTN)
        btn_zm.clicked.connect(self._zoom_out)
        btn_zp.clicked.connect(self._zoom_in)
        hdr_lay.addWidget(btn_zm)
        hdr_lay.addWidget(btn_zp)

        root.addWidget(hdr_w)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        # Le canvas gère lui-même la molette (zoom) et le middle-drag (pan) ;
        # on neutralise le scroll natif de la molette sur le QScrollArea.
        scroll.wheelEvent = lambda e: None
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._canvas = _SpritesheetCanvas(scroll_area=scroll)
        self._canvas.selection_changed.connect(self.selection_changed)
        self._canvas.hover_changed.connect(self._on_hover_changed)
        scroll.setWidget(self._canvas)
        root.addWidget(scroll, 1)

    def _on_hover_changed(self, cell):
        self._coord_lbl.setText(f"tuile {cell[0]},{cell[1]}" if cell else "")

    def load(self, path: Optional[Path]):
        self._canvas.load(path)

    def clear_selection(self):
        self._canvas.clear_selection()
        self.set_brush_label(0)

    def set_brush_label(self, n: int):
        if n == 0:
            self._brush_lbl.setText("Aucune brosse")
            self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        else:
            self._brush_lbl.setText(f"Brosse : {n} tuile{'s' if n > 1 else ''}")
            self._brush_lbl.setStyleSheet(f"color:{C.ACCENT_GRN};background:transparent;")

    def _zoom_in(self):
        if self._canvas._zoom < 6:
            self._canvas._zoom += 1
            self._canvas._update_size()
            self._canvas.update()

    def _zoom_out(self):
        if self._canvas._zoom > 1:
            self._canvas._zoom -= 1
            self._canvas._update_size()
            self._canvas.update()

