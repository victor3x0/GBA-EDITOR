"""ui/background_editor/bg_inpaint_canvas.py — canvas de peinture BackgroundInpainting.

Repeindre, AU NIVEAU ÉDITEUR (partagé entre toutes les scènes), la palette
(pal_bank local) de chaque tuile 8×8 d'un fond. Les overrides vivent dans
`BackgroundAsset.tile_palette_overrides` ; la baseline `tilemap` reste intacte
(cf. BackgroundAsset.effective_tilemap). Analogue au SceneInpaintingController,
mais côté asset — d'où la nomenclature « BackgroundInpainting ».

Composants :
- BgInpaintController : état + peinture (brosse/fill/rect/gomme) + rendu
  incrémental + persistance + undo.
- BgInpaintView       : QGraphicsView (zoom molette, pan clic-central, grille 8×8)
  déléguant la souris à l'outil actif.
- BgInpaintToolbar    : barre d'outils flottante déplaçable (4 outils).
- BgInpaintCanvas     : wrapper vue + toolbar.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QLabel, QToolButton,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap, QImage, QTransform, QPen
from PyQt6.QtCore import Qt, QPoint, QSize, QRectF, QTimer, pyqtSignal

from core.bg_compress import (
    unpack_se, _hex_to_tile, _flip_h, _flip_v, render_bg_preview,
    render_bitmap_preview,
)
from core.color_utils import bgr555_to_rgb888
from ui.common.icons import get as _ico, COLOR_DEFAULT, COLOR_ACTIVE


def _pil_to_qimage(img) -> QImage:
    """PIL RGBA → QImage indépendant (buffer copié)."""
    data = bytes(img.tobytes("raw", "RGBA"))
    return QImage(data, img.width, img.height,
                  QImage.Format.Format_RGBA8888).copy()


# ──────────────────────────────────────────────────────────────────
#  Contrôleur de peinture (état + rendu + undo + persistance)
# ──────────────────────────────────────────────────────────────────
class BgInpaintController:
    """Pilote la peinture par palette d'un BackgroundAsset. Détient l'image
    rendue (baseline + overrides), applique/persiste les overrides tuile par
    tuile, et expose un delta undoable par stroke."""

    def __init__(self):
        self._project = None
        self._ba = None
        self._active_pal = 0
        self._stroke: Optional[dict] = None
        self._qimg: Optional[QImage] = None
        self._tiles: list = []          # tuiles décodées (cache patch)
        self._pal_rgb: list = []        # palettes RGB (cache patch)
        self._paint_enabled = True      # False en 8bpp (une seule palette, pas d'inpainting)
        self.on_rendered = None         # callback() : la vue rafraîchit son pixmap

    # ── Contexte ─────────────────────────────────────────────────
    def set_context(self, project, ba):
        self._project = project
        self._ba = ba
        self._stroke = None
        self._active_pal = 0
        self._render_full()

    def set_active_palette(self, idx: int):
        self._active_pal = idx

    @property
    def ready(self) -> bool:
        if self._ba is None:
            return False
        if getattr(self._ba, "mode", "tiled") == "bitmap":
            return bool(self._ba.bitmap)
        return bool(self._ba.tileset)

    def set_paint_enabled(self, on: bool):
        self._paint_enabled = on

    @property
    def paintable(self) -> bool:
        """Peinture possible : rendu prêt ET mode le permet (tuilé 4bpp uniquement)."""
        return self.ready and self._paint_enabled

    def tiles_size(self) -> tuple[int, int]:
        if not self._ba:
            return (0, 0)
        return (self._ba.tiles_w, self._ba.tiles_h)

    def image_size(self) -> tuple[int, int]:
        """Dimensions en pixels de l'image rendue (bitmap : out_w×out_h ; tuilé :
        tiles×8) — pour dimensionner la vue/le sceneRect."""
        if not self._ba:
            return (0, 0)
        if getattr(self._ba, "mode", "tiled") == "bitmap":
            return (self._ba.out_w, self._ba.out_h)
        return (self._ba.tiles_w * 8, self._ba.tiles_h * 8)

    def grid_visible(self) -> bool:
        return bool(self._ba and getattr(self._ba, "mode", "tiled") == "tiled" and self._ba.tileset)

    def pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self._qimg) if self._qimg else QPixmap()

    def _notify(self):
        if self.on_rendered:
            self.on_rendered()

    # ── Rendu ────────────────────────────────────────────────────
    def _render_full(self):
        if not self.ready:
            self._qimg = None
            return
        ba = self._ba
        if getattr(ba, "mode", "tiled") == "bitmap":
            # Mode 4 : bitmap plein écran, aucun patch incrémental (peinture off).
            self._qimg = _pil_to_qimage(render_bitmap_preview({
                "out_w": ba.out_w, "out_h": ba.out_h,
                "palettes": ba.palettes, "bitmap": ba.bitmap,
            }))
            self._tiles = []
            self._pal_rgb = []
            return
        compiled = {
            "tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
            "tileset": ba.tileset, "palettes": ba.palettes,
            "tilemap": ba.effective_tilemap(), "bpp": getattr(ba, "bpp", 4),
        }
        self._qimg = _pil_to_qimage(render_bg_preview(compiled))
        self._tiles = [_hex_to_tile(t) for t in ba.tileset]
        self._pal_rgb = [[bgr555_to_rgb888(c) for c in pal] for pal in ba.palettes]

    def reload_render(self):
        """Re-render complet (après édition des palettes côté inspecteur)."""
        self._render_full()
        self._notify()

    def _patch(self, col: int, row: int):
        """Recolorise le bloc 8×8 (col,row) dans l'image, palette effective."""
        if self._qimg is None:
            return
        tw = self._ba.tiles_w or 1
        cell = row * tw + col
        if not (0 <= cell < len(self._ba.tilemap)):
            return
        tid, pb, fh, fv = unpack_se(self._ba.tilemap[cell])
        ov = self._ba.tile_palette_overrides.get((col, row))
        eff = pb if ov is None else ov
        grid = tuple(self._tiles[tid]) if tid < len(self._tiles) else tuple([0] * 64)
        if fh:
            grid = _flip_h(grid)
        if fv:
            grid = _flip_v(grid)
        pal = self._pal_rgb[eff] if eff < len(self._pal_rgb) else (
            self._pal_rgb[0] if self._pal_rgb else [(0, 0, 0)] * 16)
        blk = QImage(8, 8, QImage.Format.Format_RGBA8888)
        blk.fill(0)
        for y in range(8):
            for x in range(8):
                idx = grid[y * 8 + x]
                if idx == 0 or idx >= len(pal):
                    continue
                r, g, b = pal[idx]
                blk.setPixelColor(x, y, QColor(r, g, b, 255))
        painter = QPainter(self._qimg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(col * 8, row * 8, blk)
        painter.end()

    # ── Palette effective / baseline d'une tuile ─────────────────
    def _base_pb(self, col: int, row: int) -> int:
        tw = self._ba.tiles_w or 1
        return unpack_se(self._ba.tilemap[row * tw + col])[1]

    def _effective_pb(self, col: int, row: int) -> int:
        ov = self._ba.tile_palette_overrides.get((col, row))
        return self._base_pb(col, row) if ov is None else ov

    # ── Peinture ─────────────────────────────────────────────────
    def begin_stroke(self):
        self._stroke = {}

    def _paint_one(self, col: int, row: int, erase: bool):
        """Applique la palette active (ou restaure l'origine si `erase`) à UNE
        tuile, enregistre le delta — SANS notifier (batch fill/rect)."""
        tw, th = self.tiles_size()
        if not (0 <= col < tw and 0 <= row < th):
            return
        key = (col, row)
        if erase:
            new = None
        else:
            # Peindre la palette de base = pas d'override (JSON minimal, gomme cohérente).
            new = None if self._active_pal == self._base_pb(col, row) else self._active_pal
        old = self._ba.tile_palette_overrides.get(key)
        if old == new:
            return
        if self._stroke is not None:
            self._stroke[key] = (self._stroke.get(key, (old, None))[0], new)
        if new is None:
            self._ba.tile_palette_overrides.pop(key, None)
        else:
            self._ba.tile_palette_overrides[key] = new
        self._patch(col, row)

    def set_tile(self, col: int, row: int, erase: bool = False):
        if not self.paintable:
            return
        self._paint_one(col, row, erase)
        self._notify()

    def fill(self, col: int, row: int):
        """Flood-fill contigu (4-voisins) des tuiles de même palette effective."""
        if not self.paintable:
            return
        tw, th = self.tiles_size()
        if not (0 <= col < tw and 0 <= row < th):
            return
        target = self._effective_pb(col, row)
        if self._active_pal == target:
            return
        seen: set = set()
        stack = [(col, row)]
        while stack:
            c, r = stack.pop()
            if (c, r) in seen or not (0 <= c < tw and 0 <= r < th):
                continue
            if self._effective_pb(c, r) != target:
                continue
            seen.add((c, r))
            self._paint_one(c, r, erase=False)
            stack += [(c + 1, r), (c - 1, r), (c, r + 1), (c, r - 1)]
        self._notify()

    def paint_rect(self, c0: int, r0: int, c1: int, r1: int, erase: bool = False):
        if not self.paintable:
            return
        for r in range(min(r0, r1), max(r0, r1) + 1):
            for c in range(min(c0, c1), max(c0, c1) + 1):
                self._paint_one(c, r, erase)
        self._notify()

    def end_stroke(self):
        """Clôt le stroke : pousse la commande d'historique + persiste."""
        delta = self._stroke or {}
        self._stroke = None
        if not delta or not self.ready:
            return
        from core.history import BackgroundInpaintingCmd, get_history
        cmd = BackgroundInpaintingCmd(self, self._ba, dict(delta))
        h = get_history()
        h._undo.append(cmd)
        h._redo.clear()
        h.changed.emit()
        self._persist()

    # ── Undo/redo (appelé par BackgroundInpaintingCmd) ───────────
    def apply_override_delta(self, ba, delta: dict, forward: bool):
        for key, (old, new) in delta.items():
            val = new if forward else old
            if val is None:
                ba.tile_palette_overrides.pop(key, None)
            else:
                ba.tile_palette_overrides[key] = val
        if self._project:
            from core.command_dispatcher import get_dispatcher
            with get_dispatcher().suspended():
                self._project.save_background(ba)
        if ba is self._ba:
            self._render_full()
            self._notify()

    def _persist(self):
        if not self._project or not self._ba:
            return
        from core.command_dispatcher import get_dispatcher
        with get_dispatcher().suspended():
            self._project.save_background(self._ba)


# ──────────────────────────────────────────────────────────────────
#  Overlay grille 8×8 (item unique)
# ──────────────────────────────────────────────────────────────────
class _GridOverlay(QGraphicsItem):
    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._w, self._h = w, h
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w, self._h = w, h

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(QColor(255, 255, 255, 28))
        pen.setWidth(0)
        painter.setPen(pen)
        for x in range(0, self._w + 1, 8):
            painter.drawLine(x, 0, x, self._h)
        for y in range(0, self._h + 1, 8):
            painter.drawLine(0, y, self._w, y)


# ──────────────────────────────────────────────────────────────────
#  Vue zoomable / pan / peinture
# ──────────────────────────────────────────────────────────────────
class BgInpaintView(QGraphicsView):
    def __init__(self, controller: BgInpaintController, parent=None):
        self._ctrl = controller
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setBackgroundBrush(QColor("#111111"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._pix_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pix_item)
        self._grid = _GridOverlay(0, 0)
        self._grid.setZValue(10)
        self._scene.addItem(self._grid)

        self._zoom = 2.0
        self._apply_zoom()

        self._tool = "brush"
        self._painting = False
        self._rect_start: Optional[tuple[int, int]] = None
        self._panning = False
        self._pan_last = QPoint()

        controller.on_rendered = self._on_rendered

    # ── API ──────────────────────────────────────────────────────
    def _on_rendered(self):
        # Mise à jour du pixmap seule (peinture / re-render palette) — ne touche
        # pas au zoom : l'utilisateur garde son cadrage pendant qu'il peint.
        self._pix_item.setPixmap(self._ctrl.pixmap())

    def load_background(self):
        """Nouveau fond sélectionné : pixmap + grille + sceneRect, puis fit.
        Le fit est aussi différé (singleShot) car, au moment du chargement, la
        vue n'a pas toujours encore sa taille finale (layout du splitter)."""
        self._pix_item.setPixmap(self._ctrl.pixmap())
        w, h = self._ctrl.image_size()
        self._grid.resize(w, h)
        self._grid.setVisible(self._ctrl.grid_visible())
        self._scene.setSceneRect(0, 0, max(w, 1), max(h, 1))
        self.fit()
        QTimer.singleShot(0, self.fit)

    def set_tool(self, tool: str):
        self._tool = tool

    # ── Zoom ─────────────────────────────────────────────────────
    def _apply_zoom(self):
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.25, min(self._zoom * factor, 16.0))
        self._apply_zoom()

    def fit(self):
        w, h = self._ctrl.image_size()
        if w and h:
            self.fitInView(0, 0, w, h, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

    # ── Hit-test ─────────────────────────────────────────────────
    def _cell_at(self, e) -> tuple[int, int]:
        pos = self.mapToScene(e.position().toPoint())
        return int(pos.x() // 8), int(pos.y() // 8)

    # ── Souris ───────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and self._ctrl.paintable:
            self._handle_press(e)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning:
            p = e.position().toPoint()
            d = p - self._pan_last
            self._pan_last = p
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            e.accept()
            return
        if self._painting and self._tool in ("brush", "eraser"):
            c, r = self._cell_at(e)
            self._ctrl.set_tile(c, r, erase=(self._tool == "eraser"))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            e.accept()
            return
        if self._painting and e.button() == Qt.MouseButton.LeftButton:
            if self._tool == "rect" and self._rect_start is not None:
                c, r = self._cell_at(e)
                c0, r0 = self._rect_start
                self._ctrl.paint_rect(c0, r0, c, r)
                self._rect_start = None
            self._ctrl.end_stroke()
            self._painting = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        e.accept()  # clic-droit réservé (pas de menu contextuel sur le canvas)

    def _handle_press(self, e):
        c, r = self._cell_at(e)
        tool = self._tool
        if tool in ("brush", "eraser"):
            self._ctrl.begin_stroke()
            self._painting = True
            self._ctrl.set_tile(c, r, erase=(tool == "eraser"))
        elif tool == "fill":
            self._ctrl.begin_stroke()
            self._ctrl.fill(c, r)
            self._ctrl.end_stroke()
        elif tool == "rect":
            self._ctrl.begin_stroke()
            self._painting = True
            self._rect_start = (c, r)


# ──────────────────────────────────────────────────────────────────
#  Barre d'outils flottante
# ──────────────────────────────────────────────────────────────────
class BgInpaintToolbar(QFrame):
    tool_changed = pyqtSignal(str)

    _TOOLS = [
        ("brush",  "tool_inpaint_brush", "Pinceau — repeindre la palette (8×8)"),
        ("fill",   "tool_fill",          "Pot de peinture — remplir par contiguïté"),
        ("rect",   "tool_inpaint_rect",  "Rectangle — repeindre une zone"),
        ("eraser", "tool_erase",         "Gomme — restaurer la palette d'origine"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._drag_offset = QPoint()
        self._current = "brush"

        self.setFixedWidth(46)
        self.setStyleSheet("""
            BgInpaintToolbar {
                background: #1c1c1c;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QToolButton { border: none; background: transparent; border-radius: 5px; }
            QToolButton:hover   { background: #2a2a2a; }
            QToolButton:checked { background: #253525; border: 1px solid #3a6a3a; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(2)
        # La toolbar n'est pas gérée par un layout parent (elle est déplaçable,
        # positionnée en absolu au-dessus du canvas) : sans cette contrainte, le
        # QFrame n'est jamais dimensionné à son contenu et les boutons sont écrasés.
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        handle = QLabel("⋮⋮")
        handle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        handle.setStyleSheet("color:#3a3a3a; font-size:10px; letter-spacing:-2px;")
        handle.setFixedHeight(12)
        layout.addWidget(handle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2a2a; margin:2px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._btns: dict[str, QToolButton] = {}
        for tool_id, icon_key, tip in self._TOOLS:
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, COLOR_DEFAULT, COLOR_ACTIVE))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFixedSize(36, 36)
            btn.clicked.connect(lambda _=False, t=tool_id: self._select(t))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._btns[tool_id] = btn

        self._btns["brush"].setChecked(True)

    def _select(self, tool: str):
        self._current = tool
        for tid, b in self._btns.items():
            b.setChecked(tid == tool)
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._current

    # ── Drag ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and self.parent():
            new_pos = self.mapToParent(e.pos()) - self._drag_offset
            p = self.parent()
            x = max(0, min(new_pos.x(), p.width() - self.width()))
            y = max(0, min(new_pos.y(), p.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Wrapper canvas + toolbar
# ──────────────────────────────────────────────────────────────────
class BgInpaintCanvas(QWidget):
    """Panneau central du Background Editor : canvas de peinture + toolbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctrl = BgInpaintController()
        self._view = BgInpaintView(self._ctrl, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._toolbar = BgInpaintToolbar(self)
        self._toolbar.move(10, 10)
        self._toolbar.tool_changed.connect(self._view.set_tool)
        self._toolbar.raise_()

        # Overlay « Compression… » (compression hors-thread — voir screen).
        self._busy = QLabel("Compression…", self)
        self._busy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._busy.setStyleSheet(
            "background:rgba(0,0,0,160); color:#eeeeee; font-family:monospace;"
            "font-size:13px; border-radius:6px; padding:10px 20px;"
        )
        self._busy.hide()

    def set_busy(self, on: bool, text: str = "Compression…"):
        self._busy.setText(text)
        self._busy.setVisible(on)
        if on:
            self._busy.adjustSize()
            self._center_busy()
            self._busy.raise_()

    def _center_busy(self):
        self._busy.move((self.width() - self._busy.width()) // 2,
                        (self.height() - self._busy.height()) // 2)

    def load(self, project, ba):
        self._ctrl.set_context(project, ba)
        # Inpainting = tuilé 4bpp uniquement. En 8bpp (une palette 256) et en
        # bitmap (Mode 4) : peinture désactivée, toolbar masquée (aperçu seul).
        paintable = bool(ba and getattr(ba, "mode", "tiled") == "tiled"
                         and getattr(ba, "bpp", 4) == 4)
        self._ctrl.set_paint_enabled(paintable)
        self._toolbar.setVisible(paintable)
        self._view.load_background()

    def set_active_palette(self, idx: int):
        self._ctrl.set_active_palette(idx)

    def reload(self):
        """Re-render après édition des palettes (inspecteur) — met à jour le
        pixmap via le callback on_rendered, sans réinitialiser le zoom."""
        self._ctrl.reload_render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self._toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        if self._busy.isVisible():
            self._center_busy()
