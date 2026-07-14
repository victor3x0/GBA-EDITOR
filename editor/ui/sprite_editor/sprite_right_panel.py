"""ui/sprite_editor/sprite_right_panel.py — panneau droit : propriétés, collision, anim settings."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QComboBox, QScrollArea
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W
from core.project import Project, SpriteAsset, AnimState, AnimFrame, StateDirection
from core.command_dispatcher import get_dispatcher
from .direction_widget import DirectionWidget, _H_MIRROR_PAIRS, _V_MIRROR_PAIRS

_VALID_FRAME_SIZES = {
    8:  [8, 16, 32],
    16: [8, 16, 32],
    32: [8, 16, 32, 64],
    64: [32, 64],
}

class SpriteRightPanel(QWidget):
    """
    Panneau droit : header (nom éditable) + paramètres sprite + widget directionnel.
    """

    sprite_changed   = pyqtSignal()
    direction_added  = pyqtSignal(object, object)  # AnimState, StateDirection nouvellement ajoutée
    palette_extracted = pyqtSignal(str)            # nom de la PaletteBank créée/mise à jour
    image_changed    = pyqtSignal()                # source/compression du sprite changée — recharger le centre
    own_palette_changed = pyqtSignal()             # own_palette réordonnée — rafraîchir le rendu du canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(440)
        self.setStyleSheet(
            f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};"
        )
        self._project: Optional[Project] = None
        self._sprite:  Optional[SpriteAsset] = None
        self._state:   Optional[AnimState] = None
        self._blocking = False
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header : nom du sprite — composant partagé (voir ui/widgets.py),
        # même template/couleurs/renommage que Scene Manager, Sound Mixer, Script Editor.
        from ui.common.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_name_changed)
        root.addWidget(self._header)

        # ── Contenu scrollable ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{C.BG_PANEL}; border:none;}}"
        )

        content = QWidget()
        content.setStyleSheet(f"background:{C.BG_PANEL};")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(10, 8, 10, 8)
        self._content_layout.setSpacing(2)

        self._build_params()
        self._build_direction()
        self._build_palette()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_params(self):
        lay = self._content_layout
        W.section("CANVAS SIZE", lay)

        # Frame W / H
        self._cb_w = QComboBox(); self._cb_w.setFont(QFont(T.MONO, T.SM))
        self._cb_h = QComboBox(); self._cb_h.setFont(QFont(T.MONO, T.SM))
        for v in [8, 16, 32, 64]:
            self._cb_w.addItem(str(v))
        self._cb_w.currentIndexChanged.connect(self._on_frame_w_changed)
        self._cb_h.currentIndexChanged.connect(self._on_frame_h_changed)
        W.pair("Frame", "W", C.AXIS_X, self._cb_w, "H", C.AXIS_Y, self._cb_h, lay)

        W.separator(lay)
        W.section("ANIMATION", lay)

        self._sp_speed = W.spinbox(8, min_v=1, max_v=120)
        self._sp_speed.setToolTip("Ticks GBA entre deux frames (60fps). 8=7.5fps  4=15fps  2=30fps")
        self._sp_speed.valueChanged.connect(self._on_speed_changed)
        W.row("Speed", self._sp_speed, lay)

        self._chk_loop = W.checkbox_row("", "Loop", lay)
        self._chk_loop.setChecked(True)
        self._chk_loop.toggled.connect(self._on_loop_changed)

        W.separator(lay)

    def _build_direction(self):
        lay = self._content_layout
        W.section("DIRECTIONS", lay)
        self._dir_widget = DirectionWidget()
        self._dir_widget.directions_changed.connect(self._on_directions_changed)
        lay.addWidget(self._dir_widget)

    def _build_palette(self):
        from .palette_index_strip import PaletteIndexStrip
        from core.color_utils import COMPRESSION_METHODS
        lay = self._content_layout
        W.separator(lay)
        W.section("PALETTE", lay)

        # Algo de compression — recalcule own_palette depuis le source (le mode
        # « png » du canvas montre le résultat en direct). Réinitialise l'ordre
        # manuel (attendu). Sans effet si le source a ≤15 couleurs.
        self._cb_compress = QComboBox(); self._cb_compress.setFont(QFont(T.MONO, T.SM))
        for tok, label in COMPRESSION_METHODS:
            self._cb_compress.addItem(label, tok)
        self._cb_compress.currentIndexChanged.connect(self._on_compress_changed)
        W.row("Compression", self._cb_compress, lay)

        # Bande de swatches réordonnable (palette propre du sprite)
        self._strip = PaletteIndexStrip()
        self._strip.reindex_requested.connect(self._on_reindex_image)
        # Réordonner own_palette change le rendu du mode « indexed » (index →
        # couleur de banque différente) — on rafraîchit le canvas, sans reset de
        # la palette de preview (own_palette est en mémoire, pas de watcher).
        self._strip.reordered.connect(self.own_palette_changed)
        lay.addWidget(self._strip)

        self._btn_import = W.btn_accent("⟐  Importer / remplacer l'image…")
        self._btn_import.setToolTip(
            "Choisit une image, l'indexe (mode GBA, ≤15 couleurs + "
            "transparence) et l'attache au sprite courant."
        )
        self._btn_import.clicked.connect(self._on_replace_image)
        lay.addWidget(self._btn_import)

        self._btn_extract = W.btn_accent("⟐  Extraire du PNG")
        self._btn_extract.setToolTip(
            "Crée une palette « pal_<nom> » depuis les couleurs du PNG "
            "(index 0 = transparence, puis du plus sombre au plus lumineux)."
        )
        self._btn_extract.clicked.connect(self._on_extract_palette)
        lay.addWidget(self._btn_extract)

    def _on_reindex_image(self):
        """Réindexe sur place le PNG existant (migration RGBA → indexé)."""
        if not self._sprite or not self._project:
            return
        from .import_png_dialog import reindex_sprite
        if reindex_sprite(self._project, self._sprite, self):
            self._after_image_change()

    def _on_replace_image(self):
        """Attache un nouveau fichier image au sprite courant."""
        if not self._sprite or not self._project:
            return
        from .import_png_dialog import replace_sprite_image
        if replace_sprite_image(self._project, self._sprite, self):
            self._after_image_change()

    def _after_image_change(self):
        get_dispatcher().save_sprite(self._sprite)
        self._strip.load(self._sprite, self._project)
        self.image_changed.emit()

    def _on_compress_changed(self, _):
        """Recalcule own_palette avec l'algo choisi, depuis le PNG source (jamais
        modifié). Réinitialise l'ordre manuel de la palette."""
        if self._blocking or not self._sprite or not self._project or not self._sprite.asset:
            return
        method = self._cb_compress.currentData()
        if method == self._sprite.compress_method:
            return
        ap = self._project.root / self._sprite.asset
        if not ap.exists():
            return
        from core.color_utils import own_palette_from_source
        pal = own_palette_from_source(ap, method)
        if not pal:
            return
        self._sprite.own_palette = pal
        self._sprite.compress_method = method
        get_dispatcher().save_sprite(self._sprite)
        self._strip.load(self._sprite, self._project)
        self.own_palette_changed.emit()

    # ── API publique ──────────────────────────────────────────────

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._project = project
        self._sprite  = sprite
        self._state   = sprite.states[0] if sprite.states else None
        self._blocking = True

        self._header.set_header("sprite", "SPRITE", sprite.name)

        # Frame size
        self._cb_w.setCurrentText(str(sprite.frame_w))
        self._refresh_h_combo(sprite.frame_w, sprite.frame_h)

        # Animation (premier state)
        if self._state:
            self._sp_speed.setValue(self._state.speed)
            self._chk_loop.setChecked(self._state.loop)
            self._dir_widget.load(self._state)

        # Compression : algo mémorisé + bande réordonnable
        _mi = self._cb_compress.findData(getattr(sprite, "compress_method", "median_cut"))
        self._cb_compress.setCurrentIndex(_mi if _mi >= 0 else 0)
        self._strip.load(sprite, project)

        self._blocking = False

    def load_state(self, state: AnimState):
        """Met à jour les paramètres d'animation pour l'état sélectionné."""
        self._state = state
        self._blocking = True
        self._sp_speed.setValue(state.speed)
        self._chk_loop.setChecked(state.loop)
        self._dir_widget.load(state)
        self._blocking = False

    # ── Helpers ───────────────────────────────────────────────────

    def _refresh_h_combo(self, w_val: int, keep_h: int = 0):
        self._cb_h.blockSignals(True)
        self._cb_h.clear()
        valid = _VALID_FRAME_SIZES.get(w_val, [8])
        for v in valid:
            self._cb_h.addItem(str(v))
        target = str(keep_h) if keep_h in valid else str(valid[0])
        self._cb_h.setCurrentText(target)
        self._cb_h.blockSignals(False)

    def _save(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
            self.sprite_changed.emit()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_extract_palette(self):
        if not self._sprite or not self._project or not self._sprite.asset:
            return
        ap = self._project.root / self._sprite.asset
        if not ap.exists():
            return
        from core.color_utils import extract_palette_from_image
        from core.project import PaletteBank
        colors = extract_palette_from_image(ap)
        name = f"pal_{self._sprite.name}"
        existing = self._project.palettes.get(name)
        if existing:
            # Ré-extraction d'une palette déjà générée : on écrase ses couleurs
            # (action explicite "extraire", régénération attendue).
            existing.colors = colors
            bank = existing
        else:
            bank = PaletteBank(name=name, colors=colors)
        # Passe par le dispatcher : persistance (watcher suspendu) + événement
        # "palettes_changed" pour que le Palette Finder se rafraîchisse.
        get_dispatcher().save_palette(bank)
        self.palette_extracted.emit(name)

    def _on_name_changed(self, new_name: str):
        if self._blocking or not self._sprite or not self._project:
            return
        new_name = new_name.strip()
        if new_name and new_name != self._sprite.name:
            self._project.sprites.rename(self._sprite, new_name)
            self.sprite_changed.emit()

    def _on_frame_w_changed(self, _):
        if self._blocking or not self._sprite:
            return
        w = int(self._cb_w.currentText())
        old_h = int(self._cb_h.currentText()) if self._cb_h.currentText() else 16
        self._refresh_h_combo(w, old_h)
        self._sprite.frame_w = w
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_frame_h_changed(self, _):
        if self._blocking or not self._sprite:
            return
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_speed_changed(self, value: int):
        if self._blocking or not self._state:
            return
        self._state.speed = value
        self._save()

    def _on_loop_changed(self, checked: bool):
        if self._blocking or not self._state:
            return
        self._state.loop = checked
        self._save()

    def _on_directions_changed(self, active_dirs: list, h_mirror: bool, v_mirror: bool):
        if self._blocking or not self._state or not self._sprite:
            return
        # Reconstruire les StateDirection depuis la sélection
        dir_map = {sd.dir: sd for sd in self._state.directions}
        added_dirs = [d for d in active_dirs if d not in dir_map]
        new_dirs = []
        mirrored_set: set[int] = set()
        if h_mirror:
            for src, dst in _H_MIRROR_PAIRS:
                if src in active_dirs:
                    mirrored_set.add(dst)
        if v_mirror:
            for src, dst in _V_MIRROR_PAIRS:
                if src in active_dirs:
                    mirrored_set.add(dst)

        for d in active_dirs:
            if d in mirrored_set:
                # Trouver la source de ce miroir
                src = next(
                    (s for s, dst in (_H_MIRROR_PAIRS + _V_MIRROR_PAIRS) if dst == d),
                    None
                )
                fh = any(dst == d for s, dst in _H_MIRROR_PAIRS) and h_mirror
                fv = any(dst == d for s, dst in _V_MIRROR_PAIRS) and v_mirror
                existing = dir_map.get(d)
                new_dirs.append(StateDirection(
                    dir=d,
                    frames=existing.frames if existing else [AnimFrame()],
                    flip_h=fh, flip_v=fv,
                    mirror_of=src,
                ))
            else:
                existing = dir_map.get(d)
                new_dirs.append(existing or StateDirection(
                    dir=d, frames=[AnimFrame()],
                ))

        self._state.directions = new_dirs or [StateDirection()]
        self._save()

        # Une direction tout juste créée doit devenir visible immédiatement
        # dans l'arbre de gauche et le canvas central — sinon ceux-ci
        # continuent d'afficher/peindre l'ancienne direction sélectionnée.
        if added_dirs:
            added_sd = next((d for d in self._state.directions if d.dir == added_dirs[0]), None)
            if added_sd is not None:
                self.direction_added.emit(self._state, added_sd)

