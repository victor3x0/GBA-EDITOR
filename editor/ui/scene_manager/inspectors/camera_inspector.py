"""CameraInspector — position et suivi d'actor du rectangle caméra."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QScrollArea,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.project import Project, Scene
from ui.common.theme import C, T


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
        layout.setSpacing(8)
        scroll.setWidget(inner)

        f = QFont(T.MONO, T.SM)
        fs = f"color:{C.TEXT_DIM};"

        # ── Position (lecture seule) ──────────────────────────────
        lbl = QLabel("Position caméra :")
        lbl.setFont(f); lbl.setStyleSheet(fs)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        self._x_lbl = QLabel("X : 0")
        self._y_lbl = QLabel("Y : 0")
        for l in (self._x_lbl, self._y_lbl):
            l.setFont(QFont(T.MONO, T.MD))
            l.setStyleSheet(f"color:{C.TEXT_NORM};")
            row.addWidget(l)
        row.addStretch()
        layout.addLayout(row)

        info = QLabel("(Déplacer le rectangle jaune dans le canvas)")
        info.setFont(QFont(T.MONO, T.XS))
        info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        info.setWordWrap(True)
        layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};")
        layout.addWidget(sep)

        # ── Suivi d'actor ─────────────────────────────────────────
        lbl2 = QLabel("Suivre un Actor :")
        lbl2.setFont(f); lbl2.setStyleSheet(fs)
        layout.addWidget(lbl2)

        self._follow_combo = QComboBox()
        self._follow_combo.setFont(QFont(T.MONO, T.MD))
        self._follow_combo.setStyleSheet(
            f"background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER};border-radius:3px;padding:2px;"
        )
        self._follow_combo.currentTextChanged.connect(self._on_follow_changed)
        layout.addWidget(self._follow_combo)

        follow_info = QLabel("Sélectionner un acteur → la caméra le\nsuit à l'exécution (cam_follow).")
        follow_info.setFont(QFont(T.MONO, T.XS))
        follow_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        follow_info.setWordWrap(True)
        layout.addWidget(follow_info)

        layout.addStretch()

    def load(self, scene: Scene, project: Project):
        self._scene = scene
        self._project = project
        self._blocking = True
        self._update_position_labels()

        self._follow_combo.clear()
        self._follow_combo.addItem("(libre)")
        if scene:
            for actor in scene.actors:
                self._follow_combo.addItem(actor.name)
            follow = scene.cam_follow or ""
            idx = self._follow_combo.findText(follow)
            self._follow_combo.setCurrentIndex(max(0, idx))

        self._blocking = False

    def update_position(self, x: int, y: int):
        """Appelé quand la caméra est déplacée dans le canvas."""
        if self._scene:
            self._scene.cam_x = x
            self._scene.cam_y = y
        self._x_lbl.setText(f"X : {x}")
        self._y_lbl.setText(f"Y : {y}")

    def _update_position_labels(self):
        if self._scene:
            self._x_lbl.setText(f"X : {self._scene.cam_x}")
            self._y_lbl.setText(f"Y : {self._scene.cam_y}")

    def _on_follow_changed(self, text: str):
        if self._blocking or not self._scene:
            return
        self._scene.cam_follow = "" if text == "(libre)" else text
        self.changed.emit()
