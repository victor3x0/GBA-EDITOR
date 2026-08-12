"""CameraInspector — mode caméra, position de départ, suivi d'actor et bornes de monde.

Reflète le modèle unifié (cf. mémoire project_camera_abstraction) : un seul
mécanisme d'écriture de cam_x/cam_y au runtime (camera_follow), déclenché soit
ici (mode "follow" authoré), soit par un script (mode "script"). Les bornes de
monde sont un champ explicite de la Scene, plus jamais devinées depuis un
layer de fond.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QScrollArea,
    QSpinBox, QPushButton, QMessageBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.models.scene import Scene
from core.project import Project
from ui.common.theme import C, T, QSS

_MODES = [
    ("fixed",  "Fixed"),
    ("follow", "Follow an Actor"),
    ("script", "Script-driven"),
]


class CameraInspector(QWidget):
    """Inspecteur du rectangle caméra (sélection du CameraItem dans le canvas)."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._project: Optional[Project] = None
        self._blocking = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        scroll.setWidget(inner)

        f = QFont(T.UI, T.SM)
        fs = f"color:{C.TEXT_DIM};"

        def _section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(f)
            lbl.setStyleSheet(fs)
            return lbl

        # ── Mode ──────────────────────────────────────────────────
        layout.addWidget(_section_label("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont(T.UI, T.MD))
        self._mode_combo.setStyleSheet(QSS.combobox)
        for _, label in _MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        mode_info = QLabel(
            "Fixed: stays at the position below.\n"
            "Follow: camera_follow() on the chosen Actor (deadzone).\n"
            "Script: codegen no longer touches the camera."
        )
        mode_info.setFont(QFont(T.UI, T.XS))
        mode_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        mode_info.setWordWrap(True)
        layout.addWidget(mode_info)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet(f"color:{C.BORDER};")
        layout.addWidget(sep0)

        # ── Position de départ (lecture seule, déplacer dans le canvas) ──
        layout.addWidget(_section_label("Start position:"))
        row = QHBoxLayout()
        self._x_lbl = QLabel("X: 0")
        self._y_lbl = QLabel("Y: 0")
        for l in (self._x_lbl, self._y_lbl):
            l.setFont(QFont(T.MONO, T.MD))
            l.setStyleSheet(f"color:{C.TEXT_NORM};")
            row.addWidget(l)
        row.addStretch()
        layout.addLayout(row)

        info = QLabel("(Move the yellow rectangle in the canvas)")
        info.setFont(QFont(T.UI, T.XS))
        info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        info.setWordWrap(True)
        layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};")
        layout.addWidget(sep)

        # ── Groupe "Suivi" (visible seulement en mode follow) ────────
        self._follow_group = QWidget()
        fg = QVBoxLayout(self._follow_group)
        fg.setContentsMargins(0, 0, 0, 0)
        fg.setSpacing(8)

        fg.addWidget(_section_label("Follow an Actor:"))
        self._follow_combo = QComboBox()
        self._follow_combo.setFont(QFont(T.UI, T.MD))
        self._follow_combo.setStyleSheet(QSS.combobox)
        self._follow_combo.currentTextChanged.connect(self._on_follow_changed)
        fg.addWidget(self._follow_combo)

        margin_row = QHBoxLayout()
        margin_row.setSpacing(10)
        for label, attr in (("Margin X:", "_margin_x"), ("Margin Y:", "_margin_y")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(0, 120)
            setattr(self, attr, spin)
            col.addWidget(spin)
            margin_row.addLayout(col)
        margin_row.addStretch()
        fg.addLayout(margin_row)
        self._margin_x.valueChanged.connect(self._on_margins_changed)
        self._margin_y.valueChanged.connect(self._on_margins_changed)

        follow_info = QLabel(
            "Deadzone: the camera only moves once the Actor\n"
            "gets further than Margin X/Y from the screen center."
        )
        follow_info.setFont(QFont(T.UI, T.XS))
        follow_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        follow_info.setWordWrap(True)
        fg.addWidget(follow_info)

        layout.addWidget(self._follow_group)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{C.BORDER};")
        layout.addWidget(sep2)

        # ── Bornes du monde ───────────────────────────────────────
        layout.addWidget(_section_label("World bounds (0 = unlimited):"))
        bounds_row = QHBoxLayout()
        bounds_row.setSpacing(10)
        for label, attr in (("Width:", "_bounds_w"), ("Height:", "_bounds_h")):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setFont(QFont(T.UI, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            col.addWidget(lbl)
            spin = QSpinBox()
            spin.setFont(QFont(T.MONO, T.MD))
            spin.setStyleSheet(QSS.spinbox)
            spin.setRange(0, 32760)
            spin.setSingleStep(8)
            setattr(self, attr, spin)
            col.addWidget(spin)
            bounds_row.addLayout(col)
        bounds_row.addStretch()
        layout.addLayout(bounds_row)
        self._bounds_w.valueChanged.connect(self._on_bounds_changed)
        self._bounds_h.valueChanged.connect(self._on_bounds_changed)

        btn_recalc = QPushButton("Recompute from backgrounds")
        btn_recalc.setFont(QFont(T.UI, T.SM))
        btn_recalc.setStyleSheet(QSS.button_ghost)
        btn_recalc.setToolTip(
            "Prefills width/height from the scene background closest to\n"
            "a parallax speed of 1.0 — stays editable afterwards."
        )
        btn_recalc.clicked.connect(self._recalc_bounds)
        layout.addWidget(btn_recalc)

        layout.addStretch()

    # ── Chargement ────────────────────────────────────────────────

    def load(self, scene: Scene, project: Project):
        self._scene = scene
        self._project = project
        self._blocking = True
        self._update_position_labels()

        mode = getattr(scene, "cam_mode", "fixed")
        idx = next((i for i, (m, _) in enumerate(_MODES) if m == mode), 0)
        self._mode_combo.setCurrentIndex(idx)

        self._follow_combo.clear()
        self._follow_combo.addItem("(libre)")
        if scene:
            for actor in scene.actors:
                self._follow_combo.addItem(actor.name)
            follow = scene.cam_follow or ""
            fidx = self._follow_combo.findText(follow)
            self._follow_combo.setCurrentIndex(max(0, fidx))

        self._margin_x.setValue(getattr(scene, "cam_margin_x", 40))
        self._margin_y.setValue(getattr(scene, "cam_margin_y", 20))
        self._bounds_w.setValue(getattr(scene, "cam_bounds_w", None) or 0)
        self._bounds_h.setValue(getattr(scene, "cam_bounds_h", None) or 0)

        self._follow_group.setVisible(mode == "follow")

        self._blocking = False

    def update_position(self, x: int, y: int):
        """Appelé quand la caméra est déplacée dans le canvas."""
        if self._scene:
            self._scene.cam_x = x
            self._scene.cam_y = y
        self._x_lbl.setText(f"X: {x}")
        self._y_lbl.setText(f"Y: {y}")

    def _update_position_labels(self):
        if self._scene:
            self._x_lbl.setText(f"X: {self._scene.cam_x}")
            self._y_lbl.setText(f"Y: {self._scene.cam_y}")

    # ── Callbacks ─────────────────────────────────────────────────

    def _on_mode_changed(self, idx: int):
        if self._blocking or not self._scene:
            return
        mode = _MODES[idx][0]
        self._scene.cam_mode = mode
        self._follow_group.setVisible(mode == "follow")
        self.changed.emit()

    def _on_follow_changed(self, text: str):
        if self._blocking or not self._scene:
            return
        self._scene.cam_follow = "" if text == "(libre)" else text
        self.changed.emit()

    def _on_margins_changed(self):
        if self._blocking or not self._scene:
            return
        self._scene.cam_margin_x = self._margin_x.value()
        self._scene.cam_margin_y = self._margin_y.value()
        self.changed.emit()

    def _on_bounds_changed(self):
        if self._blocking or not self._scene:
            return
        self._scene.cam_bounds_w = self._bounds_w.value() or None
        self._scene.cam_bounds_h = self._bounds_h.value() or None
        self.changed.emit()

    def _recalc_bounds(self):
        if not self._scene or not self._project:
            return
        layers = [L for L in self._scene.background_layers if L.background_name]
        if not layers:
            QMessageBox.information(self, "World bounds", "This scene has no background placed.")
            return
        ref = min(layers, key=lambda L: abs(L.scroll_speed - 1.0))
        size = self._bg_pixel_size(ref)
        if size is None:
            QMessageBox.warning(self, "World bounds", f"Could not read dimensions of '{ref.background_name}'.")
            return
        w, h = size
        self._bounds_w.setValue(w)
        self._bounds_h.setValue(h)
        # setValue déclenche déjà _on_bounds_changed via valueChanged.

    def _bg_pixel_size(self, layer) -> Optional[tuple[int, int]]:
        ba = self._project.get_background(layer.background_name)
        if ba is None:
            return None
        if getattr(ba, "tileset", None):
            return ba.tiles_w * 8, ba.tiles_h * 8
        png = self._project.background_images_dir / (
            ba.asset if getattr(ba, "asset", None) else f"{layer.background_name}.png"
        )
        try:
            from PIL import Image
            with Image.open(png) as img:
                return img.size
        except Exception:
            return None
