"""
ui/sprite_editor/sprite_editor_screen.py — Éditeur de sprites (style GB Studio).

Layout : 3 colonnes
  Gauche  : liste des sprites du projet + arbre d'animations
  Centre  : barre playback + preview + tiles + frames
  Droite  : propriétés + collision + anim settings
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from ui.common.theme import C
from core.project import Project, SpriteAsset, AnimState, StateDirection
from .sprite_finder_panel import SpriteFinderPanel
from .sprite_center_panel import SpriteCenterPanel
from .sprite_right_panel import SpriteRightPanel

class SpriteEditorScreen(QWidget):
    """Écran principal du Sprite Editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project: Optional[Project] = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{C.ACCENT};}}"
        )

        self._left   = SpriteFinderPanel()
        self._center = SpriteCenterPanel()
        self._right  = SpriteRightPanel()

        splitter.addWidget(self._left)
        splitter.addWidget(self._center)
        splitter.addWidget(self._right)
        splitter.setSizes([240, 860, 270])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root.addWidget(splitter)

        self._left.sprite_selected.connect(self._on_sprite_selected)
        self._left.direction_selected.connect(self._on_direction_selected)
        self._right.sprite_changed.connect(self._left.refresh_anim_tree)
        self._right.direction_added.connect(self._left.select_direction)
        self._right.image_changed.connect(self._on_image_changed)
        self._right.palettes_changed.connect(self._center.refresh_palettes)

    def _on_image_changed(self):
        """Le PNG du sprite courant a changé (réindexation/remplacement) —
        recharger le centre pour refléter les nouvelles couleurs/tuiles."""
        if self._project and self._right._sprite:
            self._center.load_sprite(self._right._sprite, self._project)

    def load_project(self, project: Project):
        self._project = project
        self._left.load_project(project)

    def _on_sprite_selected(self, sprite: SpriteAsset):
        self._center.load_sprite(sprite, self._project)
        self._right.load_sprite(sprite, self._project)

    def _on_direction_selected(self, state: AnimState, sd: StateDirection):
        self._center.load_direction(state, sd)
        self._right.load_state(state)
