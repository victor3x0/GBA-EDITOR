"""ProjectInspector — aperçu du projet, mode par défaut de l'inspecteur quand
rien n'est sélectionné (clic hors de la zone active du canvas, Échap, etc.).
Lecture seule : l'édition de ProjectSettings se fait encore via le JSON
(cf. core/models/settings.py) — pas de formulaire de mutation ici."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea
from PyQt6.QtGui import QFont

from core.project import Project
from ui.common.theme import C, T


class ProjectInspector(QWidget):
    """Vue d'ensemble en lecture seule : auteur, version, scène de démarrage,
    compteurs d'assets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        def _info_row(label: str) -> QLabel:
            row = QHBoxLayout(); row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFont(QFont(T.MONO, T.SM)); lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            lbl.setFixedWidth(120)
            val = QLabel("—")
            val.setFont(QFont(T.MONO, T.SM)); val.setStyleSheet(f"color:{C.TEXT_NORM};")
            row.addWidget(lbl); row.addWidget(val, 1)
            layout.addLayout(row)
            return val

        self._lbl_author  = _info_row("Auteur :")
        self._lbl_version = _info_row("Version :")
        self._lbl_start   = _info_row("Scène de démarrage :")

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{C.BORDER}; border:none; margin:6px 0;")
        layout.addWidget(sep)

        self._lbl_counts = QLabel("")
        self._lbl_counts.setFont(QFont(T.MONO, T.SM))
        self._lbl_counts.setStyleSheet(f"color:{C.TEXT_DIM};")
        self._lbl_counts.setWordWrap(True)
        layout.addWidget(self._lbl_counts)

        hint = QLabel("Sélectionnez une scène ou un actor\ndans le panneau de gauche pour\nafficher ses propriétés.")
        hint.setFont(QFont(T.MONO, T.XS))
        hint.setStyleSheet(f"color:{C.TEXT_MUTED}; margin-top:10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

    def load(self, project: Optional[Project]):
        self._project = project
        if not project:
            self._lbl_author.setText("—")
            self._lbl_version.setText("—")
            self._lbl_start.setText("—")
            self._lbl_counts.setText("")
            return
        s = project.settings
        self._lbl_author.setText(s.author or "—")
        self._lbl_version.setText(s.version or "—")
        self._lbl_start.setText(s.start_scene or "—")
        self._lbl_counts.setText(
            f"{len(project.scenes)} scène(s) · {len(project.prefabs)} prefab(s) · "
            f"{len(project.sprites)} sprite(s) · {len(project.backgrounds)} fond(s)"
        )
