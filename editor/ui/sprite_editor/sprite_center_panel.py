"""ui/sprite_editor/sprite_center_panel.py — zone centre : playback, canvas, tile picker, timeline."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QToolButton, QSplitter,
)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSize, QTimer

from ui.common.theme import C, T
from ui.common.icons import get as _ico
from core.project import Project, SpriteAsset, AnimState, StateDirection
from core.command_dispatcher import get_dispatcher
from .frame_canvas import _FrameCanvasPanel, _FrameTimeline, _make_frame_pixmap
from .spritesheet_viewer import _SpritesheetViewer

# ── Zone centre — Preview ──────────────────────────────────────────────────────

class _PlaybackBar(QWidget):
    """Barre de contrôle playback (|◀ ▶ ▶| ⊞ ◉)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER_DARK};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)

        _BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;"
            f"font-size:{T.LG}px;padding:4px 8px;min-width:28px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{color:{C.ACCENT_GRN};border-color:{C.ACCENT_GRN};}}"
        )

        from ui.common.icons import get as _ico

        specs = [
            ("playback_prev",     "Première frame"),
            ("playback_play",     "Lecture"),
            ("playback_next",     "Dernière frame"),
            (None, None),
            ("playback_grid",     "Afficher grille"),
            # Placeholder en attendant la gestion des palettes de couleurs —
            # désactivé pour ne pas laisser croire qu'il fait quelque chose.
            ("tool_palette",      "Couleur de peinture (bientôt disponible)"),
        ]

        self.btn_play: Optional[QToolButton] = None
        self.btn_grid: Optional[QToolButton] = None

        for icon_key, tip in specs:
            if icon_key is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color:{C.BORDER}; margin:6px 4px;")
                layout.addWidget(sep)
                continue
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, C.TEXT_DIM, C.ACCENT_GRN))
            btn.setIconSize(QSize(18, 18))
            btn.setStyleSheet(_BTN)
            btn.setCheckable(icon_key in ("playback_play", "playback_grid"))
            if icon_key == "tool_palette":
                btn.setEnabled(False)
            if tip:
                btn.setToolTip(tip)
            layout.addWidget(btn)
            if icon_key == "playback_play":
                self.btn_play = btn
            elif icon_key == "playback_grid":
                btn.setChecked(True)
                self.btn_grid = btn

        layout.addStretch()

        self._info = QLabel("")
        self._info.setFont(QFont(T.MONO, T.XS))
        self._info.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        layout.addWidget(self._info)

    def set_info(self, tiles: int, unique: int):
        self._info.setText(f"Tiles={tiles}  Unique={unique}")
class SpriteCenterPanel(QWidget):
    """Zone centre : playback · canvas · tile picker · timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._sprite:    Optional[SpriteAsset]   = None
        self._project:   Optional[Project]        = None
        self._state:     Optional[AnimState]      = None
        self._sd:        Optional[StateDirection] = None
        self._sel_frame: int = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_play_tick)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._playback = _PlaybackBar()
        root.addWidget(self._playback)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:vertical{{height:3px;}}"
            f"QSplitter::handle:vertical:hover{{background:{C.ACCENT_GRN};}}"
        )

        self._canvas_panel = _FrameCanvasPanel()
        self._canvas = self._canvas_panel.canvas
        self._canvas.frame_painted.connect(self._on_frame_painted)
        self._canvas.set_persist_fn(self._on_frame_painted)
        self._canvas.selection_reset.connect(self._on_selection_reset)
        self._canvas.brush_picked_up.connect(self._on_brush_picked_up)

        self._tiles = _SpritesheetViewer()
        self._tiles.selection_changed.connect(self._on_tile_selection_changed)

        splitter.addWidget(self._canvas_panel)
        splitter.addWidget(self._tiles)
        splitter.setSizes([320, 200])

        root.addWidget(splitter, 1)

        self._timeline = _FrameTimeline()
        self._timeline.frame_selected.connect(self._on_frame_selected)
        self._timeline.frames_changed.connect(self._on_frames_changed)
        root.addWidget(self._timeline)

        if self._playback.btn_grid:
            self._playback.btn_grid.toggled.connect(self._canvas.set_grid)
        if self._playback.btn_play:
            self._playback.btn_play.toggled.connect(self._on_play_toggled)

        # Shift+X/Y : portés ici (pas sur _FrameCanvas seul) pour marcher
        # aussi bien après un clic dans le canvas que dans le tile picker —
        # WidgetWithChildrenShortcut s'active dès qu'un descendant a le focus.
        flip_x = QShortcut(QKeySequence("Shift+X"), self)
        flip_x.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_x.activated.connect(self._canvas.flip_brush_x)
        flip_y = QShortcut(QKeySequence("Shift+Y"), self)
        flip_y.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_y.activated.connect(self._canvas.flip_brush_y)

    # ── API publique ──────────────────────────────────────────────────

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._sprite  = sprite
        self._project = project
        self._anim_timer.stop()
        if self._playback.btn_play:
            self._playback.btn_play.setChecked(False)
        self._playback.set_info(
            tiles=sprite.tiles_per_frame * sum(
                len(sd.frames)
                for s in sprite.states
                for sd in s.directions
                if sd.mirror_of is None
            ),
            unique=sprite.tiles_per_frame,
        )
        self._tiles.load(self._abs_path())

    def load_direction(self, state: AnimState, sd: StateDirection):
        if not self._sprite or not self._project:
            return
        self._state = state
        self._sd = sd
        self._sel_frame = 0
        self._anim_timer.stop()
        if self._playback.btn_play:
            self._playback.btn_play.setChecked(False)
        self._timeline.load(self._sprite, state, sd, self._abs_path())
        self._refresh_canvas()

    # ── Slots internes ────────────────────────────────────────────────

    def _abs_path(self) -> Optional[Path]:
        if not self._project or not self._sprite or not self._sprite.asset:
            return None
        return self._project.root / self._sprite.asset

    def _on_frame_selected(self, index: int):
        self._sel_frame = index
        self._refresh_canvas()

    def _on_tile_selection_changed(self, tiles: list):
        self._canvas.set_brush(tiles)
        self._tiles.set_brush_label(len(tiles))

    def _on_selection_reset(self):
        self._tiles.clear_selection()
        self._canvas.set_brush([])

    def _on_brush_picked_up(self, n: int):
        """Tuiles ramassées directement dans le canvas (cf _FrameCanvas) —
        seul le libellé du picker doit refléter la nouvelle brosse ; ne pas
        appeler _tiles.clear_selection() ici, ça réémettrait une sélection
        vide et effacerait la brosse qu'on vient de charger."""
        self._tiles.set_brush_label(n)

    def _on_frame_painted(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
        if self._sd and 0 <= self._sel_frame < len(self._sd.frames):
            pm = _make_frame_pixmap(self._abs_path(), self._sd.frames[self._sel_frame],
                                    self._sprite.frame_w, self._sprite.frame_h)
            self._timeline.refresh_thumb(self._sel_frame, pm)

    def _on_frames_changed(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)

    # ── Playback ──────────────────────────────────────────────────────

    def _on_play_toggled(self, playing: bool):
        if playing and self._sd and self._sd.frames:
            speed_ms = max(16, int((self._state.speed if self._state else 8) * 1000 / 60))
            self._anim_timer.start(speed_ms)
        else:
            self._anim_timer.stop()

    def _on_play_tick(self):
        if not self._sd or not self._sd.frames:
            return
        n = len(self._sd.frames)
        self._sel_frame = (self._sel_frame + 1) % n
        # Mettre à jour la sélection dans la timeline sans émettre frame_selected
        for i, t in enumerate(self._timeline._thumbs):
            t.set_selected(i == self._sel_frame)
        self._timeline._selected = self._sel_frame
        self._refresh_canvas()

    # ── Canvas ────────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if not self._sd or not self._sprite:
            self._canvas.load_frame(None, None, None)
            return
        frames = self._sd.frames
        if not frames or not (0 <= self._sel_frame < len(frames)):
            self._canvas.load_frame(None, None, None)
            return
        self._canvas.load_frame(self._sprite, self._abs_path(), frames[self._sel_frame])
