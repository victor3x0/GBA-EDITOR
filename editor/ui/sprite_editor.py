"""
ui/sprite_editor.py — Éditeur de spritesheet GBA Editor.

Workflow :
  1. Tile picker (bas) : PNG découpé en 8×8, sélection rectangle de tiles
  2. Canvas editor (haut) : frame frame_w×frame_h en cellules 8×8, on y peint la sélection
  3. AnimPreview : lecture de l'animation (rendu depuis les cells)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QScrollArea, QSpinBox, QSizePolicy,
    QFileDialog, QInputDialog, QToolButton, QApplication, QMenu,
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QPen, QColor, QDrag, QCursor,
)
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, QMimeData, QByteArray, pyqtSignal, QSize

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import Project, SpriteAsset, AnimState, AnimFrame, TileCell
from ui.theme import C, T, QSS

# ──────────────────────────────────────────────────────────────────
_FRAME_THUMB  = 48
_DRAG_FRAME   = "application/x-gba-frame"
_TILE_SIZE    = 8   # toujours 8×8 px dans le spritesheet

_SECTION_HDR = (
    f"background:{C.BG_PANEL}; color:{C.TEXT_DIM}; "
    f"font-family:monospace; font-size:{T.SM}px; "
    f"padding:3px 6px; border-bottom:1px solid {C.BORDER};"
)
_ANIM_ITEM_NORM = (
    f"background:transparent; color:{C.TEXT_NORM}; "
    f"font-family:monospace; font-size:{T.MD}px; "
    f"padding:3px 8px; border:none; text-align:left;"
)
_ANIM_ITEM_SEL = (
    f"background:{C.BG_SEL}; color:{C.ACCENT_GRN}; "
    f"border-left:2px solid {C.ACCENT_GRN}; "
    f"font-family:monospace; font-size:{T.MD}px; "
    f"padding:3px 6px; border-top:none; border-right:none; border-bottom:none; text-align:left;"
)


# ──────────────────────────────────────────────────────────────────
#  Mixin zoom / pan (molette + clic central)
# ──────────────────────────────────────────────────────────────────

class ZoomPanMixin:
    def _zp_init(self, scale: float = 4.0):
        self._zp_scale  = scale
        self._zp_offset = QPointF(0.0, 0.0)
        self._zp_pan_origin: Optional[QPointF] = None

    def _zp_wheel(self, e, min_s=0.5, max_s=32.0):
        f = 1.15 if e.angleDelta().y() > 0 else (1 / 1.15)
        pos = QPointF(e.position())
        self._zp_offset = pos - f * (pos - self._zp_offset)
        self._zp_scale  = max(min_s, min(max_s, self._zp_scale * f))
        self.update()

    def _zp_press(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._zp_pan_origin = QPointF(e.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _zp_move(self, e):
        if self._zp_pan_origin and e.buttons() & Qt.MouseButton.MiddleButton:
            self._zp_offset += QPointF(e.position()) - self._zp_pan_origin
            self._zp_pan_origin = QPointF(e.position())
            self.update()

    def _zp_release(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._zp_pan_origin = None
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _zp_rect(self, cw: float, ch: float) -> QRectF:
        w = cw * self._zp_scale; h = ch * self._zp_scale
        cx = self.width()  / 2 + self._zp_offset.x()
        cy = self.height() / 2 + self._zp_offset.y()
        return QRectF(cx - w/2, cy - h/2, w, h)


# ──────────────────────────────────────────────────────────────────
#  TilePickerView — PNG découpé en 8×8, rubber-band select
# ──────────────────────────────────────────────────────────────────

class TilePickerView(ZoomPanMixin, QWidget):
    """Grille 8×8 sur le PNG. Sélection rectangle de tiles → signal."""

    selection_changed = pyqtSignal(int, int, int, int)  # tx, ty, tw, th (tiles)

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._zp_init(4.0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._pixmap: Optional[QPixmap] = None
        self._sel:    Optional[tuple[int,int,int,int]] = None  # tx,ty,tw,th
        self._drag_origin: Optional[tuple[int,int]] = None     # tile col,row

    # ── API ───────────────────────────────────────────────────────

    def load(self, path: Optional[Path]):
        self._pixmap = QPixmap(str(path)) if path and path.exists() else None
        self._sel = None
        self.update()

    def selection(self) -> Optional[tuple[int,int,int,int]]:
        return self._sel

    def zoom_in(self):
        self._zp_scale = min(32.0, self._zp_scale * 1.25); self.update()

    def zoom_out(self):
        self._zp_scale = max(0.5, self._zp_scale / 1.25); self.update()

    def zoom_label(self) -> str:
        return f"{int(round(self._zp_scale * 100))}%"

    # ── Tile sous curseur ─────────────────────────────────────────

    def _tile_at(self, pos: QPointF) -> Optional[tuple[int,int]]:
        if not self._pixmap:
            return None
        cr = self._zp_rect(self._pixmap.width(), self._pixmap.height())
        lx = (pos.x() - cr.left()) / self._zp_scale
        ly = (pos.y() - cr.top())  / self._zp_scale
        tc = int(lx // _TILE_SIZE)
        tr = int(ly // _TILE_SIZE)
        max_c = self._pixmap.width()  // _TILE_SIZE
        max_r = self._pixmap.height() // _TILE_SIZE
        if 0 <= tc < max_c and 0 <= tr < max_r:
            return tc, tr
        return None

    # ── Events ────────────────────────────────────────────────────

    def wheelEvent(self, e):       self._zp_wheel(e); e.accept()
    def mousePressEvent(self, e):
        self._zp_press(e)
        if e.button() == Qt.MouseButton.LeftButton:
            t = self._tile_at(QPointF(e.position()))
            if t:
                self._drag_origin = t
                self._sel = (t[0], t[1], 1, 1)
                self.selection_changed.emit(*self._sel)
                self.update()

    def mouseMoveEvent(self, e):
        self._zp_move(e)
        if self._drag_origin and e.buttons() & Qt.MouseButton.LeftButton:
            t = self._tile_at(QPointF(e.position()))
            if t:
                ox, oy = self._drag_origin
                tx = min(ox, t[0]); ty = min(oy, t[1])
                tw = abs(t[0] - ox) + 1; th = abs(t[1] - oy) + 1
                self._sel = (tx, ty, tw, th)
                self.selection_changed.emit(*self._sel)
                self.update()

    def mouseReleaseEvent(self, e):
        self._zp_release(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None

    def leaveEvent(self, _): self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.fillRect(self.rect(), QColor(C.BG_BASE))

        if not self._pixmap:
            p.setPen(QColor(C.TEXT_MUTED))
            p.setFont(QFont(T.MONO, T.MD))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aucun PNG")
            return

        cr = self._zp_rect(self._pixmap.width(), self._pixmap.height())
        p.drawPixmap(cr.toRect(), self._pixmap)

        ts = _TILE_SIZE * self._zp_scale
        # Grille 8×8
        pen = QPen(QColor(80, 80, 80, 180)); pen.setWidth(1); p.setPen(pen)
        x = cr.left()
        while x <= cr.right() + 1:
            p.drawLine(QPointF(x, cr.top()), QPointF(x, cr.bottom())); x += ts
        y = cr.top()
        while y <= cr.bottom() + 1:
            p.drawLine(QPointF(cr.left(), y), QPointF(cr.right(), y)); y += ts

        # Sélection
        if self._sel:
            tx, ty, tw, th = self._sel
            sx = cr.left() + tx * ts; sy = cr.top() + ty * ts
            p.fillRect(QRectF(sx, sy, tw*ts, th*ts), QColor(68, 204, 136, 60))
            pen2 = QPen(QColor(C.ACCENT_GRN)); pen2.setWidth(2); p.setPen(pen2)
            p.drawRect(QRectF(sx, sy, tw*ts, th*ts))


# ──────────────────────────────────────────────────────────────────
#  CanvasEditor — frame en 8×8 cells, peinture des tiles
# ──────────────────────────────────────────────────────────────────

class CanvasEditor(ZoomPanMixin, QWidget):
    """Canvas de la frame courante. Peint les tiles sélectionnés au clic/drag."""

    frame_changed = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._zp_init(6.0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(128, 128)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._pixmap:   Optional[QPixmap] = None
        self._frame:    Optional[AnimFrame] = None
        self._frame_w:  int = 16
        self._frame_h:  int = 16
        self._sel:      Optional[tuple[int,int,int,int]] = None  # tx,ty,tw,th
        self._painting: bool = False
        self._hover_cell: Optional[tuple[int,int]] = None  # cx,cy

    def load(self, pixmap, frame, frame_w, frame_h, sel):
        self._pixmap  = pixmap
        self._frame   = frame
        self._frame_w = frame_w
        self._frame_h = frame_h
        self._sel     = sel
        self.update()

    def set_selection(self, sel: Optional[tuple[int,int,int,int]]):
        self._sel = sel
        self.update()

    def set_frame(self, frame: Optional[AnimFrame]):
        self._frame = frame
        self.update()

    # ── Cell sous curseur ─────────────────────────────────────────

    def _cell_at(self, pos: QPointF) -> Optional[tuple[int,int]]:
        cr = self._zp_rect(self._frame_w, self._frame_h)
        ts = _TILE_SIZE * self._zp_scale
        lx = (pos.x() - cr.left()) / ts
        ly = (pos.y() - cr.top())  / ts
        cx = int(lx); cy = int(ly)
        cw = self._frame_w // _TILE_SIZE
        ch = self._frame_h // _TILE_SIZE
        if 0 <= cx < cw and 0 <= cy < ch:
            return cx, cy
        return None

    def _paint_at(self, cx: int, cy: int):
        """Peint la sélection courante en partant de (cx, cy)."""
        if not self._frame or not self._sel:
            return
        tx, ty, tw, th = self._sel
        cw = self._frame_w // _TILE_SIZE
        ch = self._frame_h // _TILE_SIZE

        # Supprime les cells qui seront écrasées
        to_remove = set()
        for r in range(th):
            for c in range(tw):
                to_remove.add((cx + c, cy + r))
        self._frame.cells = [c for c in self._frame.cells
                              if (c.cx, c.cy) not in to_remove]

        # Ajoute les nouvelles cells
        for r in range(th):
            for c in range(tw):
                ncx = cx + c; ncy = cy + r
                if 0 <= ncx < cw and 0 <= ncy < ch:
                    self._frame.cells.append(
                        TileCell(cx=ncx, cy=ncy, tx=tx+c, ty=ty+r)
                    )
        self.frame_changed.emit()
        self.update()

    # ── Events ────────────────────────────────────────────────────

    def wheelEvent(self, e):       self._zp_wheel(e); e.accept()
    def mousePressEvent(self, e):
        self._zp_press(e)
        if e.button() == Qt.MouseButton.LeftButton:
            cell = self._cell_at(QPointF(e.position()))
            if cell and self._sel:
                self._painting = True
                self._paint_at(*cell)

    def mouseMoveEvent(self, e):
        self._zp_move(e)
        cell = self._cell_at(QPointF(e.position()))
        self._hover_cell = cell
        if self._painting and cell and self._sel:
            self._paint_at(*cell)
        self.update()

    def mouseReleaseEvent(self, e):
        self._zp_release(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self._painting = False

    def leaveEvent(self, _):
        self._hover_cell = None; self.update()

    def contextMenuEvent(self, e):
        """Clic droit → effacer la cell sous le curseur."""
        if not self._frame:
            return
        cell = self._cell_at(QPointF(e.pos()))
        if cell:
            cx, cy = cell
            self._frame.cells = [c for c in self._frame.cells
                                  if not (c.cx == cx and c.cy == cy)]
            self.frame_changed.emit()
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        w, h = self.width(), self.height()

        # Damier
        cell = 8
        c1, c2 = QColor(40, 40, 40), QColor(56, 56, 56)
        for cy in range(0, h, cell):
            for cx in range(0, w, cell):
                c = c1 if ((cx//cell)+(cy//cell))%2==0 else c2
                p.fillRect(cx, cy, min(cell,w-cx), min(cell,h-cy), c)

        cr = self._zp_rect(self._frame_w, self._frame_h)
        ts = _TILE_SIZE * self._zp_scale
        cw = self._frame_w // _TILE_SIZE
        ch = self._frame_h // _TILE_SIZE

        # Fond du canvas
        p.fillRect(cr.toRect(), QColor(20, 20, 20, 180))

        # Tiles peintes
        if self._pixmap and self._frame:
            for tc in self._frame.cells:
                src = QRect(tc.tx * _TILE_SIZE, tc.ty * _TILE_SIZE,
                            _TILE_SIZE, _TILE_SIZE)
                dst = QRectF(cr.left() + tc.cx * ts,
                             cr.top()  + tc.cy * ts, ts, ts)
                p.drawPixmap(dst.toRect(), self._pixmap, src)

        # Grille du canvas
        pen = QPen(QColor(255, 255, 255, 30)); pen.setWidth(1); p.setPen(pen)
        for col in range(cw + 1):
            x = cr.left() + col * ts
            p.drawLine(QPointF(x, cr.top()), QPointF(x, cr.bottom()))
        for row in range(ch + 1):
            y = cr.top() + row * ts
            p.drawLine(QPointF(cr.left(), y), QPointF(cr.right(), y))

        # Contour canvas
        pen2 = QPen(QColor(C.ACCENT_GRN)); pen2.setWidth(1); p.setPen(pen2)
        p.drawRect(cr.toRect())

        # Aperçu de la sélection au survol
        if self._hover_cell and self._sel:
            hcx, hcy = self._hover_cell
            tx, ty, tw, th = self._sel
            preview_r = QRectF(cr.left() + hcx*ts, cr.top() + hcy*ts,
                               tw*ts, th*ts)
            if self._pixmap:
                src = QRect(tx*_TILE_SIZE, ty*_TILE_SIZE,
                            tw*_TILE_SIZE, th*_TILE_SIZE)
                p.setOpacity(0.5)
                p.drawPixmap(preview_r.toRect(), self._pixmap, src)
                p.setOpacity(1.0)
            pen3 = QPen(QColor(C.ACCENT_GRN)); pen3.setWidth(1)
            pen3.setStyle(Qt.PenStyle.DashLine); p.setPen(pen3)
            p.drawRect(preview_r)


# ──────────────────────────────────────────────────────────────────
#  AnimPreview — lecture de l'animation
# ──────────────────────────────────────────────────────────────────

class AnimPreview(ZoomPanMixin, QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self._zp_init(4.0)
        self.setMinimumSize(80, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._pixmap:  Optional[QPixmap] = None
        self._frames:  list[AnimFrame]   = []
        self._frame_w: int = 16
        self._frame_h: int = 16
        self._cur:     int = 0
        self._playing: bool = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

    def load(self, pixmap, state, frame_w, frame_h):
        self._pixmap  = pixmap
        self._frames  = state.frames if state else []
        self._frame_w = frame_w
        self._frame_h = frame_h
        self._cur     = 0
        speed_ms = (state.speed * 1000 // 60) if state else 133
        self._timer.setInterval(max(16, speed_ms))
        if self._playing and len(self._frames) > 1:
            self._timer.start()
        self.update()

    def set_playing(self, playing: bool):
        self._playing = playing
        if playing and len(self._frames) > 1:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _next_frame(self):
        if self._frames:
            self._cur = (self._cur + 1) % len(self._frames)
            self.update()

    def wheelEvent(self, e):       self._zp_wheel(e); e.accept()
    def mousePressEvent(self, e):  self._zp_press(e)
    def mouseMoveEvent(self, e):   self._zp_move(e)
    def mouseReleaseEvent(self, e):self._zp_release(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        w, h = self.width(), self.height()

        # Damier
        cs = 8; c1, c2 = QColor(40,40,40), QColor(56,56,56)
        for cy in range(0, h, cs):
            for cx in range(0, w, cs):
                c = c1 if ((cx//cs)+(cy//cs))%2==0 else c2
                p.fillRect(cx, cy, min(cs,w-cx), min(cs,h-cy), c)

        cr = self._zp_rect(self._frame_w, self._frame_h)
        ts = _TILE_SIZE * self._zp_scale

        p.fillRect(cr.toRect(), QColor(20,20,20,180))

        if self._pixmap and self._frames:
            frame = self._frames[self._cur % len(self._frames)]
            for tc in frame.cells:
                src = QRect(tc.tx*_TILE_SIZE, tc.ty*_TILE_SIZE, _TILE_SIZE, _TILE_SIZE)
                dst = QRectF(cr.left()+tc.cx*ts, cr.top()+tc.cy*ts, ts, ts)
                p.drawPixmap(dst.toRect(), self._pixmap, src)

        pen = QPen(QColor(C.ACCENT_GRN)); pen.setWidth(1); p.setPen(pen)
        p.drawRect(cr.toRect())


# ──────────────────────────────────────────────────────────────────
#  FrameThumb
# ──────────────────────────────────────────────────────────────────

class FrameThumb(QWidget):
    remove_requested  = pyqtSignal(int)

    def __init__(self, idx: int, frame: AnimFrame,
                 pixmap: Optional[QPixmap], frame_w: int, frame_h: int,
                 selected: bool = False, parent=None):
        super().__init__(parent)
        self._idx = idx
        self.setFixedSize(_FRAME_THUMB + 4, _FRAME_THUMB + 20)
        self._drag_start: Optional[QPointF] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        self._canvas = QLabel()
        self._canvas.setFixedSize(_FRAME_THUMB, _FRAME_THUMB)
        self._canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas.setStyleSheet(
            f"background:{C.BG_INPUT}; border:1px solid "
            + (C.ACCENT_GRN if selected else C.BORDER) + ";"
        )
        if pixmap and not pixmap.isNull() and frame.cells:
            thumb = QPixmap(frame_w, frame_h)
            thumb.fill(QColor(0, 0, 0, 0))
            tp = QPainter(thumb)
            tp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            for tc in frame.cells:
                src = QRect(tc.tx*_TILE_SIZE, tc.ty*_TILE_SIZE, _TILE_SIZE, _TILE_SIZE)
                dst = QRect(tc.cx*_TILE_SIZE, tc.cy*_TILE_SIZE, _TILE_SIZE, _TILE_SIZE)
                tp.drawPixmap(dst, pixmap, src)
            tp.end()
            self._canvas.setPixmap(thumb.scaled(
                _FRAME_THUMB, _FRAME_THUMB,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            ))
        layout.addWidget(self._canvas)

        bot = QWidget(); bl = QHBoxLayout(bot)
        bl.setContentsMargins(0,0,0,0); bl.setSpacing(2)
        num = QLabel(str(idx)); num.setFont(QFont(T.MONO, T.XS))
        num.setStyleSheet(f"color:{C.TEXT_DIM};")
        bl.addWidget(num, 1)
        layout.addWidget(bot)

    def contextMenuEvent(self, e):
        menu = QMenu(self); menu.setStyleSheet(QSS.menu)
        menu.addAction("Supprimer").triggered.connect(
            lambda: self.remove_requested.emit(self._idx)
        )
        menu.exec(e.globalPos())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = QPointF(e.position())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_start and e.buttons() & Qt.MouseButton.LeftButton:
            if (QPointF(e.position()) - self._drag_start).manhattanLength() > QApplication.startDragDistance():
                mime = QMimeData()
                mime.setData(_DRAG_FRAME, QByteArray(str(self._idx).encode()))
                drag = QDrag(self)
                drag.setMimeData(mime)
                pix = self._canvas.pixmap()
                if pix and not pix.isNull():
                    drag.setPixmap(pix)
                drag.exec(Qt.DropAction.MoveAction)
                self._drag_start = None
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_start = None
        super().mouseReleaseEvent(e)


# ──────────────────────────────────────────────────────────────────
#  FramesArea — timeline avec drop
# ──────────────────────────────────────────────────────────────────

class FramesArea(QWidget):
    frame_added     = pyqtSignal()        # bouton +
    frame_reordered = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(4)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasFormat(_DRAG_FRAME) else e.ignore()

    def dragMoveEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasFormat(_DRAG_FRAME) else e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasFormat(_DRAG_FRAME):
            src = int(bytes(e.mimeData().data(_DRAG_FRAME)).decode())
            dst = self._drop_index(e.position().x())
            if dst != src:
                self.frame_reordered.emit(src, dst)
            e.acceptProposedAction()

    def _drop_index(self, x: float) -> int:
        for i in range(self._lay.count()):
            item = self._lay.itemAt(i)
            if item and item.widget():
                mid = item.widget().x() + item.widget().width() / 2
                if x < mid:
                    return i
        return max(0, self._lay.count() - 1)


# ──────────────────────────────────────────────────────────────────
#  FloatingPreview — overlay draggable + repliable sur le canvas
# ──────────────────────────────────────────────────────────────────

class FloatingPreview(QWidget):
    """Fenêtre flottante posée en overlay sur le CanvasEditor.
    Draggable par la barre de titre. Repliable via le bouton ▲/▼.
    """

    _PREVIEW_SIZE = 160
    _HDR_H        = 22

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("FloatingPreview")
        self._collapsed   = False
        self._drag_offset: Optional[QPointF] = None
        self._playing     = False

        self._setup_ui()
        self.resize(self._PREVIEW_SIZE + 2, self._PREVIEW_SIZE + self._HDR_H + 28)
        self.move(8, 8)
        self.raise_()

    # ── UI ────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(
            "QWidget#FloatingPreview {"
            f"background:{C.BG_PANEL};"
            f"border:1px solid {C.BORDER};"
            "border-radius:4px;"
            "}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        self._hdr = QWidget()
        self._hdr.setFixedHeight(self._HDR_H)
        self._hdr.setStyleSheet(
            f"background:{C.BG_DEEP};border-radius:3px 3px 0 0;"
            "border-bottom:1px solid " + C.BORDER + ";"
        )
        self._hdr.setCursor(Qt.CursorShape.SizeAllCursor)
        hdr_lay = QHBoxLayout(self._hdr)
        hdr_lay.setContentsMargins(6, 0, 4, 0)
        hdr_lay.setSpacing(4)

        lbl = QLabel("PREVIEW")
        lbl.setFont(QFont(T.MONO, T.XS))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;border:none;")
        hdr_lay.addWidget(lbl, 1)

        self._btn_collapse = QToolButton()
        self._btn_collapse.setText("▲")
        self._btn_collapse.setFixedSize(16, 16)
        self._btn_collapse.setFont(QFont(T.MONO, 7))
        self._btn_collapse.setStyleSheet(
            f"QToolButton{{background:transparent;color:{C.TEXT_DIM};border:none;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};}}"
        )
        self._btn_collapse.clicked.connect(self._toggle_collapse)
        hdr_lay.addWidget(self._btn_collapse)
        lay.addWidget(self._hdr)

        # ── Body ──────────────────────────────────────────────────
        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self._preview = AnimPreview()
        self._preview.setFixedSize(self._PREVIEW_SIZE, self._PREVIEW_SIZE)
        body_lay.addWidget(self._preview)

        # Barre de lecture
        pb = QWidget(); pb.setFixedHeight(26)
        pb.setStyleSheet(
            f"background:{C.BG_DEEP};border-top:1px solid {C.BORDER};"
            "border-radius:0 0 3px 3px;"
        )
        pb_lay = QHBoxLayout(pb)
        pb_lay.setContentsMargins(4, 2, 4, 2); pb_lay.setSpacing(2)
        for label, slot in [("⏮", self._first), ("▶", self._play_pause), ("⏭", self._last)]:
            btn = QPushButton(label); btn.setFixedSize(22, 20)
            btn.setFont(QFont(T.MONO, T.SM))
            btn.setStyleSheet(
                f"QPushButton{{background:{C.BG_INPUT};color:{C.TEXT_NORM};"
                f"border:1px solid {C.BORDER};border-radius:2px;}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            )
            btn.clicked.connect(slot)
            pb_lay.addWidget(btn)
            if label == "▶": self._btn_play = btn
        pb_lay.addStretch(1)
        body_lay.addWidget(pb)

        lay.addWidget(self._body)

    # ── API publique ──────────────────────────────────────────────

    def load(self, pixmap, state, frame_w, frame_h):
        self._preview.load(pixmap, state, frame_w, frame_h)

    # ── Collapse ──────────────────────────────────────────────────

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._btn_collapse.setText("▼" if self._collapsed else "▲")
        if self._collapsed:
            self.resize(self._PREVIEW_SIZE + 2, self._HDR_H + 2)
        else:
            self.resize(self._PREVIEW_SIZE + 2, self._PREVIEW_SIZE + self._HDR_H + 28)

    # ── Playback ──────────────────────────────────────────────────

    def _play_pause(self):
        self._playing = not self._playing
        self._preview.set_playing(self._playing)
        self._btn_play.setText("⏸" if self._playing else "▶")

    def _first(self):
        self._preview._cur = 0; self._preview.update()

    def _last(self):
        frames = self._preview._frames
        if frames:
            self._preview._cur = len(frames) - 1; self._preview.update()

    # ── Drag par le header ────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._hdr.geometry().contains(e.position().toPoint()):
            self._drag_offset = e.position()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_offset and e.buttons() & Qt.MouseButton.LeftButton:
            delta = e.position() - self._drag_offset
            new_pos = self.pos() + delta.toPoint()
            # Clamp dans le parent
            if self.parent():
                pw, ph = self.parent().width(), self.parent().height()
                new_pos.setX(max(0, min(new_pos.x(), pw - self.width())))
                new_pos.setY(max(0, min(new_pos.y(), ph - self.height())))
            self.move(new_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
        super().mouseReleaseEvent(e)


# ──────────────────────────────────────────────────────────────────
#  SpriteEditorScreen
# ──────────────────────────────────────────────────────────────────

class SpriteEditorScreen(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project:    Optional[Project]     = None
        self._sprite:     Optional[SpriteAsset] = None
        self._pixmap:     Optional[QPixmap]     = None
        self._sel_state:  int = 0
        self._sel_frame:  int = 0
        self._tile_sel:   Optional[tuple[int,int,int,int]] = None
        self._setup_ui()

    # ── Setup UI ──────────────────────────────────────────────────

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        h_split = QSplitter(Qt.Orientation.Horizontal)
        h_split.setStyleSheet(QSS.splitter)
        root.addWidget(h_split)

        h_split.addWidget(self._build_left_panel())
        h_split.addWidget(self._build_center_panel())
        h_split.addWidget(self._build_right_panel())
        h_split.setSizes([220, 820, 200])

    # ── Panneau gauche ─────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(160)
        w.setStyleSheet(f"background:{C.BG_BASE};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        def _hdr(label, slot):
            row = QWidget()
            row.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER};")
            rl = QHBoxLayout(row); rl.setContentsMargins(0,0,0,0); rl.setSpacing(0)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};font-family:monospace;font-size:{T.SM}px;padding:3px 6px;")
            rl.addWidget(lbl, 1)
            btn = QToolButton(); btn.setText("+"); btn.setFixedSize(22, 22)
            btn.setFont(QFont(T.MONO, T.MD))
            btn.setStyleSheet(
                f"QToolButton{{background:{C.BG_PANEL};color:{C.ACCENT_GRN};"
                f"border:none;border-left:1px solid {C.BORDER};}}"
                f"QToolButton:hover{{background:{C.BG_HOVER};}}"
            )
            btn.clicked.connect(slot)
            rl.addWidget(btn)
            return row

        lay.addWidget(_hdr("SPRITES", self._import_sprite))

        self._sprite_list_w   = QWidget()
        self._sprite_list_lay = QVBoxLayout(self._sprite_list_w)
        self._sprite_list_lay.setContentsMargins(0,0,0,0)
        self._sprite_list_lay.setSpacing(0)
        self._sprite_list_lay.addStretch(1)
        sa_s = QScrollArea(); sa_s.setWidget(self._sprite_list_w)
        sa_s.setWidgetResizable(True)
        sa_s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa_s.setStyleSheet(f"border:none;background:{C.BG_BASE};")
        lay.addWidget(sa_s, 2)

        anim_hdr = _hdr("ANIMATIONS", self._add_anim_state)
        anim_hdr.setStyleSheet(
            f"background:{C.BG_PANEL};border-top:1px solid {C.BORDER};border-bottom:1px solid {C.BORDER};"
        )
        lay.addWidget(anim_hdr)

        self._anim_list_w   = QWidget()
        self._anim_list_lay = QVBoxLayout(self._anim_list_w)
        self._anim_list_lay.setContentsMargins(0,0,0,0)
        self._anim_list_lay.setSpacing(0)
        self._anim_list_lay.addStretch(1)
        sa_a = QScrollArea(); sa_a.setWidget(self._anim_list_w)
        sa_a.setWidgetResizable(True)
        sa_a.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa_a.setStyleSheet(f"border:none;background:{C.BG_BASE};")
        lay.addWidget(sa_a, 3)

        return w

    # ── Zone centrale ──────────────────────────────────────────────

    def _build_center_panel(self) -> QWidget:
        outer = QWidget()
        outer.setStyleSheet(f"background:{C.BG_BASE};")
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0,0,0,0)
        outer_lay.setSpacing(0)

        # Barre lecture
        playbar = QWidget(); playbar.setFixedHeight(36)
        playbar.setStyleSheet(f"background:{C.BG_PANEL};border-bottom:1px solid {C.BORDER};")
        pb_lay = QHBoxLayout(playbar); pb_lay.setContentsMargins(8,4,8,4); pb_lay.setSpacing(4)
        for label, slot in [("⏮", self._frame_first), ("▶", self._play_pause), ("⏭", self._frame_last)]:
            btn = QPushButton(label); btn.setFixedSize(28, 24)
            btn.setFont(QFont(T.MONO, T.MD))
            btn.setStyleSheet(
                f"QPushButton{{background:{C.BG_INPUT};color:{C.TEXT_NORM};"
                f"border:1px solid {C.BORDER};border-radius:3px;}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
            )
            btn.clicked.connect(slot); pb_lay.addWidget(btn)
        pb_lay.addStretch(1)
        self._lbl_info = QLabel("")
        self._lbl_info.setFont(QFont(T.MONO, T.SM))
        self._lbl_info.setStyleSheet(f"color:{C.TEXT_DIM};")
        pb_lay.addWidget(self._lbl_info)
        outer_lay.addWidget(playbar)

        # Splitter vertical
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setStyleSheet(QSS.splitter)
        outer_lay.addWidget(v_split, 1)

        # ── Canvas editor (haut) ───────────────────────────────────
        canvas_wrap = QWidget()
        canvas_wrap.setStyleSheet(f"background:{C.BG_DEEP};")
        cw_lay = QVBoxLayout(canvas_wrap)
        cw_lay.setContentsMargins(0,0,0,0); cw_lay.setSpacing(0)

        canvas_hdr = QWidget(); canvas_hdr.setFixedHeight(24)
        canvas_hdr.setStyleSheet(f"background:{C.BG_PANEL};border-bottom:1px solid {C.BORDER};")
        ch_lay = QHBoxLayout(canvas_hdr); ch_lay.setContentsMargins(6,0,6,0)
        self._lbl_canvas = QLabel("▼  CANVAS")
        self._lbl_canvas.setFont(QFont(T.MONO, T.SM))
        self._lbl_canvas.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;border:none;")
        ch_lay.addWidget(self._lbl_canvas)
        ch_lay.addStretch(1)

        # Hint effacement
        hint = QLabel("clic droit = effacer cell")
        hint.setFont(QFont(T.MONO, T.XS))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;border:none;")
        ch_lay.addWidget(hint)
        cw_lay.addWidget(canvas_hdr)

        self._canvas_editor = CanvasEditor()
        self._canvas_editor.frame_changed.connect(self._on_canvas_changed)
        cw_lay.addWidget(self._canvas_editor, 1)
        v_split.addWidget(canvas_wrap)

        # ── Tile picker (bas) ──────────────────────────────────────
        tiles_wrap = QWidget()
        tiles_wrap.setStyleSheet(f"background:{C.BG_BASE};")
        tw_lay = QVBoxLayout(tiles_wrap)
        tw_lay.setContentsMargins(0,0,0,0); tw_lay.setSpacing(0)

        tiles_hdr = QWidget(); tiles_hdr.setFixedHeight(24)
        tiles_hdr.setStyleSheet(f"background:{C.BG_PANEL};border-bottom:1px solid {C.BORDER};")
        th_lay = QHBoxLayout(tiles_hdr); th_lay.setContentsMargins(6,0,6,0)
        lbl_t = QLabel("▼  TILES  (8×8)")
        lbl_t.setFont(QFont(T.MONO, T.SM))
        lbl_t.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;border:none;")
        th_lay.addWidget(lbl_t); th_lay.addStretch(1)

        btn_zm = QToolButton(); btn_zm.setText("−")
        btn_zp = QToolButton(); btn_zp.setText("+")
        self._lbl_zoom = QLabel("400%")
        self._lbl_zoom.setFont(QFont(T.MONO, T.SM))
        self._lbl_zoom.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;border:none;")
        for b in (btn_zm, btn_zp):
            b.setFixedSize(20, 20); b.setFont(QFont(T.MONO, T.MD))
            b.setStyleSheet(
                f"QToolButton{{background:transparent;color:{C.TEXT_DIM};border:none;}}"
                f"QToolButton:hover{{color:{C.TEXT_HI};}}"
            )
        btn_zm.clicked.connect(self._zoom_out)
        btn_zp.clicked.connect(self._zoom_in)
        for ww in (btn_zm, self._lbl_zoom, btn_zp):
            th_lay.addWidget(ww)
        tw_lay.addWidget(tiles_hdr)

        self._tile_picker = TilePickerView()
        self._tile_picker.selection_changed.connect(self._on_tile_selection)
        tw_lay.addWidget(self._tile_picker, 1)

        # Edit Image
        edit_row = QWidget(); edit_row.setFixedHeight(28)
        edit_row.setStyleSheet(f"background:{C.BG_BASE};border-top:1px solid {C.BORDER};")
        er_lay = QHBoxLayout(edit_row); er_lay.setContentsMargins(6,3,6,3)
        btn_edit = QPushButton("Edit Image"); btn_edit.setFont(QFont(T.MONO, T.SM))
        btn_edit.setFixedHeight(20)
        btn_edit.setStyleSheet(
            f"QPushButton{{background:{C.BG_INPUT};color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER};border-radius:3px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )
        btn_edit.clicked.connect(self._open_in_external_editor)
        er_lay.addWidget(btn_edit); er_lay.addStretch(1)
        tw_lay.addWidget(edit_row)
        v_split.addWidget(tiles_wrap)

        # ── FRAMES timeline ────────────────────────────────────────
        frames_wrap = QWidget()
        frames_wrap.setStyleSheet(f"background:{C.BG_DEEP};")
        fw_lay = QVBoxLayout(frames_wrap)
        fw_lay.setContentsMargins(0,0,0,0); fw_lay.setSpacing(0)
        self._frames_hdr = QLabel("▼  FRAMES")
        self._frames_hdr.setFixedHeight(24)
        self._frames_hdr.setStyleSheet(_SECTION_HDR)
        fw_lay.addWidget(self._frames_hdr)

        self._frames_area = FramesArea()
        self._frames_area.frame_reordered.connect(self._on_frame_reordered)
        sa_frames = QScrollArea(); sa_frames.setWidget(self._frames_area)
        sa_frames.setWidgetResizable(True)
        sa_frames.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa_frames.setStyleSheet(f"border:none;background:{C.BG_DEEP};")
        fw_lay.addWidget(sa_frames, 1)
        v_split.addWidget(frames_wrap)

        v_split.setSizes([300, 400, 120])

        # FloatingPreview posé en overlay sur le canvas
        self._floating_preview = FloatingPreview(canvas_wrap)
        self._floating_preview.show()

        return outer

    # ── Panneau droit ──────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(160)
        w.setStyleSheet(f"background:{C.BG_PANEL};border-left:1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self._lbl_sprite_name = QLabel("—")
        self._lbl_sprite_name.setFont(QFont(T.MONO, T.MD))
        self._lbl_sprite_name.setStyleSheet(
            f"color:{C.TEXT_HI};background:{C.BG_DEEP};padding:6px 8px;border-bottom:1px solid {C.BORDER};"
        )
        self._lbl_sprite_name.setWordWrap(True)
        lay.addWidget(self._lbl_sprite_name)

        # Canvas Size
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner); il.setContentsMargins(8,8,8,8); il.setSpacing(10)
        cs_lbl = QLabel("Canvas Size"); cs_lbl.setFont(QFont(T.MONO, T.SM))
        cs_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        il.addWidget(cs_lbl)

        wh_row = QWidget(); wh_l = QHBoxLayout(wh_row)
        wh_l.setContentsMargins(0,0,0,0); wh_l.setSpacing(6)

        def _spin(attr):
            sb = QSpinBox(); sb.setRange(8, 128); sb.setSingleStep(8)
            sb.setFont(QFont(T.MONO, T.SM)); sb.setStyleSheet(QSS.spinbox)
            sb.valueChanged.connect(lambda v, a=attr: self._on_frame_size_changed(a, v))
            return sb

        self._spin_w = _spin("frame_w"); self._spin_h = _spin("frame_h")
        for prefix, sb in [("W", self._spin_w), ("H", self._spin_h)]:
            col = QWidget(); cl = QVBoxLayout(col)
            cl.setContentsMargins(0,0,0,0); cl.setSpacing(2)
            pl = QLabel(prefix); pl.setFont(QFont(T.MONO, T.XS))
            pl.setStyleSheet(f"color:{C.TEXT_DIM};")
            cl.addWidget(pl); cl.addWidget(sb); wh_l.addWidget(col)
        il.addWidget(wh_row)

        # Info sélection tiles
        self._lbl_sel_info = QLabel("Aucune sélection")
        self._lbl_sel_info.setFont(QFont(T.MONO, T.XS))
        self._lbl_sel_info.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._lbl_sel_info.setWordWrap(True)
        il.addWidget(self._lbl_sel_info)

        il.addStretch(1)
        lay.addWidget(inner)
        return w

    # ── API publique ──────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._sprite  = None
        self._refresh_sprite_list()

    def load_sprite(self, sprite: SpriteAsset):
        self._sprite    = sprite
        self._sel_state = 0
        self._sel_frame = 0
        self._load_pixmap()
        self._refresh_all()

    # ── Refresh ───────────────────────────────────────────────────

    def _load_pixmap(self):
        self._pixmap = None
        if self._sprite and self._sprite.asset and self._project:
            p = self._project.asset_abs(self._sprite.asset)
            if p and p.exists():
                self._pixmap = QPixmap(str(p))

    def _refresh_all(self):
        self._refresh_sprite_list()
        self._refresh_anim_list()
        self._refresh_canvas()
        self._refresh_tile_picker()
        self._refresh_frames()
        self._refresh_preview()
        self._refresh_settings()

    def _refresh_sprite_list(self):
        for i in reversed(range(self._sprite_list_lay.count())):
            item = self._sprite_list_lay.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()
        if not self._project: return
        for sp in self._project.sprites:
            if not sp.asset: continue
            sel = self._sprite and sp.name == self._sprite.name
            btn = QPushButton(sp.name); btn.setFont(QFont(T.MONO, T.SM))
            btn.setStyleSheet(_ANIM_ITEM_SEL if sel else _ANIM_ITEM_NORM)
            btn.clicked.connect(lambda _=False, s=sp: self.load_sprite(s))
            self._sprite_list_lay.insertWidget(self._sprite_list_lay.count()-1, btn)

    def _refresh_anim_list(self):
        for i in reversed(range(self._anim_list_lay.count())):
            item = self._anim_list_lay.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()
        if not self._sprite: return
        for idx, state in enumerate(self._sprite.states):
            sel = idx == self._sel_state
            btn = QPushButton(state.name); btn.setFont(QFont(T.MONO, T.SM))
            btn.setStyleSheet(_ANIM_ITEM_SEL if sel else _ANIM_ITEM_NORM)
            btn.clicked.connect(lambda _=False, i=idx: self._select_anim(i))
            self._anim_list_lay.insertWidget(self._anim_list_lay.count()-1, btn)

    def _refresh_canvas(self):
        if not self._sprite: return
        frame = self._current_frame()
        self._canvas_editor.load(
            self._pixmap, frame,
            self._sprite.frame_w, self._sprite.frame_h,
            self._tile_sel,
        )
        state = self._current_state()
        self._lbl_canvas.setText(
            f"▼  CANVAS — {state.name if state else ''}  "
            f"frame {self._sel_frame + 1}/{len(state.frames) if state else 0}"
        )

    def _refresh_tile_picker(self):
        if self._sprite and self._sprite.asset and self._project:
            p = self._project.asset_abs(self._sprite.asset)
            self._tile_picker.load(p)
            if self._pixmap:
                tc = self._pixmap.width()  // _TILE_SIZE
                tr = self._pixmap.height() // _TILE_SIZE
                self._lbl_info.setText(f"Tiles={tc*tr}  {tc}×{tr}")
        else:
            self._tile_picker.load(None)
            self._lbl_info.setText("")

    def _refresh_frames(self):
        for i in reversed(range(self._frames_area._lay.count())):
            item = self._frames_area._lay.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()
        state = self._current_state()
        self._frames_hdr.setText(
            f"▼  FRAMES : {state.name.upper()}" if state else "▼  FRAMES"
        )
        if not state: return
        fw = self._sprite.frame_w if self._sprite else 16
        fh = self._sprite.frame_h if self._sprite else 16
        for idx, frame in enumerate(state.frames):
            thumb = FrameThumb(idx, frame, self._pixmap, fw, fh, idx == self._sel_frame)
            thumb.remove_requested.connect(self._remove_frame)
            thumb.mousePressEvent = self._make_frame_select(idx, thumb.mousePressEvent)
            self._frames_area._lay.addWidget(thumb)
        # Bouton +
        btn_add = QToolButton(); btn_add.setText("+")
        btn_add.setFixedSize(_FRAME_THUMB, _FRAME_THUMB)
        btn_add.setFont(QFont(T.MONO, T.XL))
        btn_add.setStyleSheet(
            f"QToolButton{{background:{C.BG_INPUT};color:{C.TEXT_DIM};"
            f"border:1px dashed {C.BORDER};border-radius:3px;}}"
            f"QToolButton:hover{{color:{C.ACCENT_GRN};border-color:{C.ACCENT_GRN};}}"
        )
        btn_add.clicked.connect(self._add_frame)
        self._frames_area._lay.addWidget(btn_add)

    def _make_frame_select(self, idx, original_press):
        def handler(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._sel_frame = idx
                self._refresh_frames()
                self._refresh_canvas()
            original_press(e)
        return handler

    def _refresh_preview(self):
        state = self._current_state()
        fw = self._sprite.frame_w if self._sprite else 16
        fh = self._sprite.frame_h if self._sprite else 16
        self._floating_preview.load(self._pixmap, state, fw, fh)

    def _refresh_settings(self):
        if self._sprite:
            self._lbl_sprite_name.setText(self._sprite.name)
            self._spin_w.blockSignals(True); self._spin_h.blockSignals(True)
            self._spin_w.setValue(self._sprite.frame_w)
            self._spin_h.setValue(self._sprite.frame_h)
            self._spin_w.blockSignals(False); self._spin_h.blockSignals(False)
        else:
            self._lbl_sprite_name.setText("—")

    # ── Helpers ───────────────────────────────────────────────────

    def _current_state(self) -> Optional[AnimState]:
        if self._sprite and self._sprite.states:
            return self._sprite.states[min(self._sel_state, len(self._sprite.states)-1)]
        return None

    def _current_frame(self) -> Optional[AnimFrame]:
        state = self._current_state()
        if state and state.frames:
            return state.frames[min(self._sel_frame, len(state.frames)-1)]
        return None

    def _save(self):
        if self._project and self._sprite:
            self._project.save_sprite(self._sprite)

    # ── Slots ─────────────────────────────────────────────────────

    def _on_tile_selection(self, tx: int, ty: int, tw: int, th: int):
        self._tile_sel = (tx, ty, tw, th)
        self._canvas_editor.set_selection(self._tile_sel)
        self._lbl_sel_info.setText(f"Sélection : {tw}×{th} tiles à ({tx},{ty})")

    def _on_canvas_changed(self):
        self._save()
        self._refresh_frames()
        self._refresh_preview()

    def _select_anim(self, idx: int):
        self._sel_state = idx
        self._sel_frame = 0
        self._refresh_anim_list()
        self._refresh_frames()
        self._refresh_canvas()
        self._refresh_preview()

    def _add_frame(self):
        state = self._current_state()
        if not state: return
        state.frames.append(AnimFrame())
        self._sel_frame = len(state.frames) - 1
        self._save()
        self._refresh_frames()
        self._refresh_canvas()

    def _remove_frame(self, idx: int):
        state = self._current_state()
        if state and 0 <= idx < len(state.frames):
            state.frames.pop(idx)
            self._sel_frame = max(0, self._sel_frame - 1)
            self._save()
            self._refresh_frames()
            self._refresh_canvas()
            self._refresh_preview()

    def _on_frame_reordered(self, src: int, dst: int):
        state = self._current_state()
        if not state: return
        frames = state.frames
        if 0 <= src < len(frames) and 0 <= dst < len(frames):
            frame = frames.pop(src)
            frames.insert(dst, frame)
            self._sel_frame = dst
            self._save()
            self._refresh_frames()
            self._refresh_canvas()

    def _add_anim_state(self):
        if not self._sprite: return
        name, ok = QInputDialog.getText(self, "Nouvel état", "Nom :")
        if ok and name.strip():
            self._sprite.states.append(AnimState(name=name.strip()))
            self._sel_state = len(self._sprite.states) - 1
            self._sel_frame = 0
            self._save()
            self._refresh_anim_list()
            self._refresh_frames()
            self._refresh_canvas()

    def _on_frame_size_changed(self, attr: str, value: int):
        if not self._sprite: return
        setattr(self._sprite, attr, value)
        self._canvas_editor._frame_w = self._sprite.frame_w
        self._canvas_editor._frame_h = self._sprite.frame_h
        self._canvas_editor.update()
        self._refresh_preview()
        self._save()

    def _import_sprite(self):
        if not self._project: return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer PNG",
            str(self._project.assets_dir / "sprites"),
            "Images (*.png *.bmp)"
        )
        if not path: return
        from core.project import SpriteAsset as _SA
        dst = self._project.import_asset(Path(path), "sprites")
        name = Path(path).stem
        sprite = self._project.get_sprite(name)
        if not sprite:
            sprite = _SA(name=name, asset=self._project.asset_rel(dst))
            self._project.sprites.append(sprite)
            self._project.save_sprite(sprite)
        self.load_sprite(sprite)

    def _open_in_external_editor(self):
        if not self._sprite or not self._sprite.asset or not self._project: return
        p = self._project.asset_abs(self._sprite.asset)
        if p and p.exists():
            import os
            if os.name == "nt": os.startfile(str(p))
            else:
                import subprocess; subprocess.Popen(["xdg-open", str(p)])

    # ── Playback ──────────────────────────────────────────────────

    def _play_pause(self):
        self._floating_preview._play_pause()

    def _frame_first(self):
        self._floating_preview._first()

    def _frame_last(self):
        self._floating_preview._last()

    # ── Zoom tile picker ──────────────────────────────────────────

    def _zoom_out(self):
        self._tile_picker.zoom_out()
        self._lbl_zoom.setText(self._tile_picker.zoom_label())

    def _zoom_in(self):
        self._tile_picker.zoom_in()
        self._lbl_zoom.setText(self._tile_picker.zoom_label())
