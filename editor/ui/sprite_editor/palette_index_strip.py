"""ui/sprite_editor/palette_index_strip.py — bande de swatches réordonnable.

Affiche la own_palette du sprite courant (index 0 transparent verrouillé +
couleurs déplaçables). Réordonner édite la LISTE own_palette dans le JSON du
sprite (le PNG source n'est jamais touché). Drag & drop maison (fantôme + trait
vert), fiable en zone scrollable contrairement au drag interne de QListWidget.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
)
from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QEvent

from ui.common.theme import C, T

_SW = 22  # côté d'un swatch


def _swatch(rgb: tuple[int, int, int], size: int = _SW) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(*rgb))
    p = QPainter(pm)
    p.setPen(QColor(C.BORDER))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return pm


def _transparent_swatch(size: int = _SW) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor("#2a2a2a"))
    p = QPainter(pm)
    p.fillRect(0, 0, size // 2, size // 2, QColor("#3a3a3a"))
    p.fillRect(size // 2, size // 2, size // 2, size // 2, QColor("#3a3a3a"))
    p.setPen(QColor(C.BORDER))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return pm


_ROW_H = 30


class _SwatchRow(QFrame):
    """Une ligne : swatch + numéro d'index + hex. Porte son index réel."""

    def __init__(self, real_index: int, rgb: tuple[int, int, int], pos: int, parent=None):
        super().__init__(parent)
        self.real_index = real_index
        self.rgb = rgb
        self.setFixedHeight(_ROW_H)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._apply_style()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 8, 0)
        lay.setSpacing(10)
        sw = QLabel(); sw.setPixmap(_swatch(rgb)); sw.setFixedSize(_SW, _SW)
        num = QLabel(str(pos)); num.setFixedWidth(24)
        num.setFont(QFont(T.MONO, T.SM))
        num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        num.setStyleSheet(f"color:{C.TEXT_DIM};")
        hexs = QLabel(f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
        hexs.setFont(QFont(T.MONO, T.SM))
        hexs.setStyleSheet(f"color:{C.TEXT_NORM};")
        lay.addWidget(sw)
        lay.addWidget(num)
        lay.addWidget(hexs, 1)

    def _apply_style(self, ghost_src: bool = False):
        if ghost_src:
            self.setStyleSheet(f"_SwatchRow{{background:transparent; border:1px dashed {C.BORDER};"
                               "border-radius:3px;}")
        else:
            self.setStyleSheet(f"_SwatchRow{{background:{C.BG_DEEP}; border:1px solid {C.BORDER};"
                               "border-radius:3px;}")


class SwatchReorderBar(QWidget):
    """Liste verticale de swatches réordonnables (drag maison, fiable en zone
    scrollable). Émet `reordered(new_real_order)` — les anciens index réels
    dans le nouvel ordre."""

    reordered = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[tuple[int, tuple[int, int, int]]] = []
        self._rows: list[_SwatchRow] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)

        self._ghost = QLabel(self)
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ghost.hide()

        self._indicator = QFrame(self)
        self._indicator.setFixedHeight(2)
        self._indicator.setStyleSheet(f"background:{C.ACCENT_GRN}; border-radius:1px;")
        self._indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._indicator.hide()

        self._drag_row: Optional[_SwatchRow] = None
        self._drag_start: Optional[QPoint] = None
        self._dragging = False
        self._target = 0

    # ── Peuplement ─────────────────────────────────────────────────────

    def set_entries(self, entries: list[tuple[int, tuple[int, int, int]]]):
        self._entries = list(entries)
        self._rebuild()

    def _rebuild(self):
        for r in self._rows:
            r.hide(); r.setParent(None)
        self._rows = []
        for pos, (real_idx, rgb) in enumerate(self._entries, start=1):
            row = _SwatchRow(real_idx, rgb, pos)
            row.installEventFilter(self)
            self._layout.addWidget(row)
            self._rows.append(row)

    # ── Drag & drop (adapté de ReorderableButtonBar, vertical) ─────────

    def eventFilter(self, obj, event):
        if not isinstance(obj, _SwatchRow):
            return False
        t = event.type()
        if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_row = obj
            self._drag_start = event.globalPosition().toPoint()
            self._dragging = False
            return False
        if t == QEvent.Type.MouseMove and self._drag_row is obj:
            if not self._dragging:
                if (event.globalPosition().toPoint() - self._drag_start).manhattanLength() < 6:
                    return False
                self._begin_drag(obj)
            if self._dragging:
                ly = self.mapFromGlobal(event.globalPosition().toPoint()).y()
                self._update_drag(ly)
                return True
        if t == QEvent.Type.MouseButtonRelease and self._drag_row is obj:
            if self._dragging:
                self._end_drag()
                return True
            self._drag_row = None
        return False

    def _begin_drag(self, row: _SwatchRow):
        self._dragging = True
        row._apply_style(ghost_src=True)
        row.setCursor(Qt.CursorShape.ClosedHandCursor)
        pm = QPixmap(row.size())
        row.render(pm)
        self._ghost.setPixmap(pm)
        self._ghost.setFixedSize(row.size())
        self._ghost.move(row.pos())
        self._ghost.show(); self._ghost.raise_()
        self._indicator.raise_()
        self._target = self._rows.index(row)

    def _update_drag(self, mouse_y: int):
        gh = self._ghost.height()
        gy = max(0, min(mouse_y - gh // 2, self.height() - gh))
        self._ghost.move(self._drag_row.x(), gy)
        self._target = self._compute_target(mouse_y)
        self._place_indicator(self._target)

    def _compute_target(self, mouse_y: int) -> int:
        others = [r for r in self._rows if r is not self._drag_row]
        for j, row in enumerate(others):
            mid = row.y() + row.height() // 2
            if mouse_y < mid:
                return j
        return len(others)

    def _place_indicator(self, target: int):
        others = [r for r in self._rows if r is not self._drag_row]
        if not others:
            self._indicator.hide(); return
        self._indicator.setFixedWidth(self.width())
        if target <= 0:
            y = others[0].y() - 2
        elif target >= len(others):
            y = others[-1].y() + others[-1].height()
        else:
            y = (others[target - 1].y() + others[target - 1].height() + others[target].y()) // 2
        self._indicator.move(0, y)
        self._indicator.show()

    def _end_drag(self):
        src = self._rows.index(self._drag_row)
        entry = self._entries[src]
        rest = [e for i, e in enumerate(self._entries) if i != src]
        rest.insert(self._target, entry)

        self._drag_row._apply_style(ghost_src=False)
        self._drag_row.setCursor(Qt.CursorShape.OpenHandCursor)
        self._ghost.hide(); self._indicator.hide()
        self._dragging = False
        self._drag_row = None

        if rest != self._entries:
            self._entries = rest
            self._rebuild()
            self.reordered.emit([ri for ri, _ in self._entries])


class PaletteIndexStrip(QWidget):
    reordered = pyqtSignal()          # PNG réécrit → rafraîchir la preview
    reindex_requested = pyqtSignal()  # sprite non indexé / bouton "indexer"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._sprite = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._hint = QLabel("Sprite non indexé — importe/indexe pour éditer ses couleurs.")
        self._hint.setWordWrap(True)
        self._hint.setFont(QFont(T.MONO, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_DIM};")
        root.addWidget(self._hint)

        self._reindex_btn = QPushButton("Indexer ce sprite…")
        self._reindex_btn.setFont(QFont(T.MONO, T.SM))
        self._reindex_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reindex_btn.clicked.connect(self.reindex_requested)
        root.addWidget(self._reindex_btn)

        row0 = QHBoxLayout(); row0.setSpacing(10); row0.setContentsMargins(6, 0, 8, 0)
        t_sw = QLabel(); t_sw.setPixmap(_transparent_swatch()); t_sw.setFixedSize(_SW, _SW)
        lbl0 = QLabel("0 · transparent (verrouillé)")
        lbl0.setFont(QFont(T.MONO, T.XS)); lbl0.setStyleSheet(f"color:{C.TEXT_DIM};")
        row0.addWidget(t_sw); row0.addWidget(lbl0, 1)
        self._row0 = QWidget(); self._row0.setLayout(row0)
        root.addWidget(self._row0)

        self._bar = SwatchReorderBar()
        self._bar.reordered.connect(self._on_reordered)
        root.addWidget(self._bar)

    # ── API ────────────────────────────────────────────────────────────

    def load(self, sprite, project):
        self._sprite = sprite
        self._project = project
        self._reload()

    def _reload(self):
        """Peuple la bande depuis `sprite.own_palette` (métadonnées, PNG jamais
        lu ici) — chaque couleur BGR555 devient un swatch réordonnable."""
        from core.color_utils import bgr555_to_rgb888
        op = list(getattr(self._sprite, "own_palette", []) or []) if self._sprite else []
        indexed = bool(op)
        # payload = valeur BGR555 (identifiant de réordonnancement) ; le libellé
        # affiché reste la position logique 1..N (géré par la bande).
        entries = [(bgr, bgr555_to_rgb888(bgr)) for bgr in op]
        self._bar.set_entries(entries)
        self._hint.setVisible(not indexed)
        self._reindex_btn.setVisible(not indexed)
        self._row0.setVisible(indexed)
        self._bar.setVisible(indexed)

    def _on_reordered(self, new_order: list):
        """`new_order` = la nouvelle liste `own_palette` (BGR555) réordonnée. On
        édite les MÉTADONNÉES du sprite (JSON, watcher suspendu par le
        dispatcher) — le PNG source n'est jamais touché."""
        if not self._sprite or not self._project:
            return
        if list(new_order) == list(self._sprite.own_palette):
            return
        from core.command_dispatcher import get_dispatcher
        self._sprite.own_palette = list(new_order)
        get_dispatcher().save_sprite(self._sprite)
        self._reload()
        self.reordered.emit()
