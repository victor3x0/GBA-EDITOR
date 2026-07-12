"""ui/sprite_editor/sprite_center_panel.py — zone centre : playback, canvas, tile picker, timeline."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QTimer

from ui.common.theme import C, T
from core.project import Project, SpriteAsset, AnimState, StateDirection
from core.command_dispatcher import get_dispatcher
from .frame_canvas import _FrameCanvasPanel, _FrameTimeline, _make_frame_pixmap
from .spritesheet_viewer import _SpritesheetViewer

# ── Zone centre — Preview ──────────────────────────────────────────────────────
# La barre playback (|◀ ▶ ▶| grille/palette) et le header (flip/fit/zoom,
# tag CANVAS, stats) sont flottants, superposés au canvas — voir
# _CanvasFloatingToolbar / _FrameCanvasPanel dans frame_canvas.py.


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
        # Direction miroir (mirror_of défini) : affichée en lecture seule à
        # partir des frames de la direction source, retournées (flip).
        self._read_only:   bool = False
        self._disp_frames: Optional[list] = None
        self._flip:        tuple[bool, bool] = (False, False)
        self._preview_banks: list = []   # banques proposées dans le dropdown palette
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

        toolbar = self._canvas_panel.toolbar
        toolbar.btn_play.toggled.connect(self._on_play_toggled)
        toolbar.btn_palette.clicked.connect(self._open_preview_palette_picker)

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

    def refresh_own_palette(self):
        """Re-applique la compression du sprite courant au canvas (après un
        réordonnancement de la bande) → le rendu dérivé se met à jour."""
        if self._sprite:
            self._canvas.set_own_palette(getattr(self._sprite, "own_palette", []))

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._sprite  = sprite
        self._project = project
        self._canvas.set_own_palette(getattr(sprite, "own_palette", []))
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

        # Palette de preview : mémorisée par sprite (SpriteAsset.preview_palette).
        # Repli sur "DMG (GB Default)" (verte) si rien de mémorisé ou palette
        # supprimée — recherchée par nom, pas par index 0 (le catalogue est
        # chargé par ordre alphabétique de fichier, pas par ordre de création).
        self._preview_banks = list(project.palettes) if project else []
        stored = getattr(sprite, "preview_palette", None)
        bank = (project.get_palette(stored) if (stored and project) else None) \
            or (project.get_palette("DMG (GB Default)") if project else None) \
            or (self._preview_banks[0] if self._preview_banks else None)
        self._set_preview_palette(bank)

    # ── Palette de preview (dropdown depuis la barre d'outils) ─────────

    def _set_preview_palette(self, bank):
        """Applique une banque à la preview du canvas et reflète son icône
        sur le bouton palette de la barre d'outils (ou l'icône générique si
        aucune banque)."""
        self._canvas.set_tint(bank.colors if bank else None)
        btn = self._canvas_panel.toolbar.btn_palette
        if bank:
            from ui.common.palette_swatch import bank_icon
            btn.setIcon(bank_icon(bank, 22))
            btn.setToolTip(f"Palette de preview : {bank.name}")
        else:
            from ui.common.icons import get as _ico
            btn.setIcon(_ico("tool_palette", C.TEXT_DIM, C.ACCENT_GRN))
            btn.setToolTip("Palette de preview")

    def _open_preview_palette_picker(self):
        if not self._preview_banks:
            return
        from ui.common.widgets import ScriptPickerPopup
        from ui.common.palette_swatch import bank_icon
        entries = [(b.name, b.name, bank_icon(b)) for b in self._preview_banks]
        popup = ScriptPickerPopup(entries, C.ACCENT_GRN, parent=self, new_label=None)
        popup.picked.connect(self._on_preview_palette_picked)
        popup.show_below(self._canvas_panel.toolbar.btn_palette)

    def _on_preview_palette_picked(self, name: str):
        bank = self._project.get_palette(name) if self._project else None
        if bank:
            self._set_preview_palette(bank)
            self._remember_preview(name)

    def _remember_preview(self, name: str):
        """Persiste le choix de palette de preview sur le sprite courant (JSON
        sidecar, watcher suspendu par le dispatcher). Ne recharge pas l'écran."""
        if (self._sprite and self._project
                and getattr(self._sprite, "preview_palette", None) != name):
            self._sprite.preview_palette = name
            get_dispatcher().save_sprite(self._sprite)

    def on_palette_extracted(self, name: str):
        """Une palette vient d'être extraite du PNG (bouton du panneau droit)
        — la sélectionner pour la preview et basculer en mode indexé pour
        montrer immédiatement le rendu quantifié."""
        if not self._project:
            return
        self._preview_banks = list(self._project.palettes)
        self._canvas_panel.toolbar._set_preview_indexed(True)
        bank = self._project.get_palette(name)
        if bank:
            self._set_preview_palette(bank)
            self._remember_preview(name)

    def load_direction(self, state: AnimState, sd: StateDirection):
        if not self._sprite or not self._project:
            return
        self._state = state
        self._sd = sd
        self._sel_frame = 0
        self._anim_timer.stop()
        self._canvas_panel.toolbar.btn_play.setChecked(False)

        # Miroir : les frames n'appartiennent pas à cette direction, elles sont
        # dérivées de la source (mirror_of) + flip. Affichage seul, pas d'édition
        # — c'est aussi ce que fait le build (asset_pipeline._dedup_frames).
        self._read_only = sd.mirror_of is not None
        if self._read_only:
            src = next((s for s in state.directions if s.dir == sd.mirror_of), None)
            self._disp_frames = src.frames if src else sd.frames
            self._flip = (sd.flip_h, sd.flip_v)
        else:
            self._disp_frames = None
            self._flip = (False, False)

        self._timeline.load(self._sprite, state, sd, self._abs_path(),
                            self._read_only, self._disp_frames, self._flip)
        self._canvas.set_read_only(self._read_only)
        self._canvas.set_display_flip(*self._flip)
        self._tiles.setEnabled(not self._read_only)
        from ui.sprite_editor.sprite_finder_panel import _dir_label
        self._canvas_panel.set_read_only_banner(
            f"MIROIR · {_dir_label(sd)} · lecture seule" if self._read_only else None)
        self._refresh_canvas()

    def _active_frames(self) -> list:
        """Frames effectivement affichées : source retournée pour un miroir,
        sinon les frames propres de la direction."""
        if self._read_only and self._disp_frames is not None:
            return self._disp_frames
        return self._sd.frames if self._sd else []

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
        if playing and self._sd and self._active_frames():
            speed_ms = max(16, int((self._state.speed if self._state else 8) * 1000 / 60))
            self._anim_timer.start(speed_ms)
        else:
            self._anim_timer.stop()

    def _on_play_tick(self):
        if not self._sd or not self._active_frames():
            return
        n = len(self._active_frames())
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
        frames = self._active_frames()
        if not frames or not (0 <= self._sel_frame < len(frames)):
            self._canvas.load_frame(None, None, None)
            return
        self._canvas.load_frame(self._sprite, self._abs_path(), frames[self._sel_frame])
