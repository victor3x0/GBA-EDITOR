"""ui/sprite_editor/sprite_center_panel.py — zone centre : playback, canvas, tile picker, timeline."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QToolButton, QSplitter,
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from ui.common.theme import C, T
from core.project import Project, SpriteAsset, AnimState, StateDirection
from core.command_dispatcher import get_dispatcher
from .frame_canvas import _FrameCanvasPanel, _FrameTimeline, _make_frame_pixmap
from .spritesheet_viewer import _SpritesheetViewer

# ── Zone centre — Preview ──────────────────────────────────────────────────────
# La barre playback (|◀ ▶ ▶| grille/palette) et le header (flip/fit/zoom,
# tag CANVAS, stats) sont flottants, superposés au canvas — voir
# _CanvasFloatingToolbar / _FrameCanvasPanel dans frame_canvas.py.


class _PaletteStrip(QWidget):
    """
    Grille 2 colonnes de swatches cliquables (banques OBJ) — change la
    teinte de preview du canvas (aperçu d'animation uniquement, ne modifie
    ni les pixels du PNG source ni la palette réellement assignée au sprite).
    """

    bank_picked = pyqtSignal(int)   # index dans la liste passée à load_banks()
    _COLS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(52)
        self.setStyleSheet(f"background:{C.BG_PANEL}; border-right:1px solid {C.BORDER_DARK};")
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(4, 6, 4, 6)
        self._layout.setSpacing(3)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._buttons: list[QToolButton] = []
        self._active = 0

    def load_banks(self, banks: list):
        for b in self._buttons:
            self._layout.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()

        for i, bank in enumerate(banks):
            btn = QToolButton()
            btn.setFixedSize(20, 20)
            btn.setCheckable(True)
            if bank.colors:
                from core.color_utils import bgr555_to_rgb888
                mid_r, mid_g, mid_b = bgr555_to_rgb888(bank.colors[len(bank.colors) // 2])
                btn.setStyleSheet(
                    f"QToolButton{{background:rgb({mid_r},{mid_g},{mid_b});"
                    f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
                    f"QToolButton:checked{{border:2px solid {C.ACCENT_GRN};}}"
                )
                btn.setToolTip(bank.name)
                btn.clicked.connect(lambda _checked, i=i: self._pick(i))
            else:
                btn.setEnabled(False)
                btn.setStyleSheet(
                    f"QToolButton{{background:{C.BG_INPUT};"
                    f"border:1px dashed {C.BORDER_MID};border-radius:3px;}}"
                )
                btn.setToolTip("Palette vide")
            row, col = divmod(i, self._COLS)
            self._layout.addWidget(btn, row, col)
            self._buttons.append(btn)

    def select_default(self, index: int = 0):
        """Sélectionne une banque par défaut sans émettre bank_picked (état initial)."""
        self._select(index)

    def _pick(self, i: int):
        self._select(i)
        self.bank_picked.emit(i)

    def _select(self, i: int):
        self._active = i
        for j, b in enumerate(self._buttons):
            b.setChecked(j == i)


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

        self._palette_strip = _PaletteStrip()
        self._palette_strip.bank_picked.connect(self._on_palette_picked)

        canvas_row = QWidget()
        canvas_row_l = QHBoxLayout(canvas_row)
        canvas_row_l.setContentsMargins(0, 0, 0, 0)
        canvas_row_l.setSpacing(0)
        canvas_row_l.addWidget(self._palette_strip)
        canvas_row_l.addWidget(self._canvas_panel, 1)

        self._tiles = _SpritesheetViewer()
        self._tiles.selection_changed.connect(self._on_tile_selection_changed)

        splitter.addWidget(canvas_row)
        splitter.addWidget(self._tiles)
        splitter.setSizes([320, 200])

        root.addWidget(splitter, 1)

        self._timeline = _FrameTimeline()
        self._timeline.frame_selected.connect(self._on_frame_selected)
        self._timeline.frames_changed.connect(self._on_frames_changed)
        root.addWidget(self._timeline)

        toolbar = self._canvas_panel.toolbar
        toolbar.btn_play.toggled.connect(self._on_play_toggled)
        toolbar.btn_palette.toggled.connect(self._palette_strip.setVisible)

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
        self._canvas_panel.toolbar.btn_play.setChecked(False)
        self._canvas_panel.set_info(
            tiles=sprite.tiles_per_frame * sum(
                len(sd.frames)
                for s in sprite.states
                for sd in s.directions
                if sd.mirror_of is None
            ),
            unique=sprite.tiles_per_frame,
        )
        self._tiles.load(self._abs_path())

        # Teinte de preview : toujours réinitialisée à "DMG (GB Default)"
        # (verte) pour un sprite fraîchement sélectionné — recherché par nom,
        # pas par index 0 : le catalogue est chargé par ordre alphabétique de
        # fichier (ResourceManager), pas par ordre de création.
        obj_banks = list(project.obj_palettes) if project else []
        self._palette_strip.load_banks(obj_banks)
        default_bank = (project.get_obj_palette("DMG (GB Default)") if project else None) \
            or (obj_banks[0] if obj_banks else None)
        default_idx = obj_banks.index(default_bank) if default_bank in obj_banks else 0
        self._palette_strip.select_default(default_idx)
        self._canvas.set_tint(default_bank.colors if default_bank else None)

    def _on_palette_picked(self, index: int):
        if not self._project:
            return
        banks = list(self._project.obj_palettes)
        if 0 <= index < len(banks):
            self._canvas.set_tint(banks[index].colors)

    def load_direction(self, state: AnimState, sd: StateDirection):
        if not self._sprite or not self._project:
            return
        self._state = state
        self._sd = sd
        self._sel_frame = 0
        self._anim_timer.stop()
        self._canvas_panel.toolbar.btn_play.setChecked(False)
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
