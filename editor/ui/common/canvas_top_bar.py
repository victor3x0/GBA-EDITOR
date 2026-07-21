"""ui/common/canvas_top_bar.py — barre d'état au-dessus d'un canvas.

Barre unique partagée par tous les écrans à canvas (Scene Manager, Background
Editor…) : zoom (−/%/+/ajuster) à gauche, toggles d'affichage propres à l'écran
au milieu, dimensions + position du curseur à droite.

L'écran hôte reste maître de son canvas : la barre ne fait qu'émettre
`zoom_step_asked` / `fit_asked` et afficher ce qu'on lui pousse
(`set_zoom`, `set_canvas_size`, `set_cursor_px`).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T
from ui.common import icons

BAR_HEIGHT = 36


class CanvasTopBar(QFrame):
    zoom_step_asked = pyqtSignal(int)   # -1 = dézoomer, +1 = zoomer
    fit_asked = pyqtSignal()

    def __init__(self, fit_tip: str = "Ajuster à la vue  (F)", parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        self._font = QFont(T.MONO, T.MD)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(12)
        self._lay = lay

        self._btn_zoom_out = self._icon_btn("zoom_out", 16, (24, 24),
                                            "Dézoomer  (molette bas)")
        self._btn_zoom_out.clicked.connect(lambda: self.zoom_step_asked.emit(-1))
        lay.addWidget(self._btn_zoom_out)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setFont(self._font)
        self._zoom_label.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._zoom_label.setFixedWidth(46)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._zoom_label)

        self._btn_zoom_in = self._icon_btn("zoom_in", 16, (24, 24),
                                           "Zoomer  (molette haut)")
        self._btn_zoom_in.clicked.connect(lambda: self.zoom_step_asked.emit(+1))
        lay.addWidget(self._btn_zoom_in)

        self._btn_fit = self._icon_btn("fit_page", 18, (28, 24), fit_tip)
        self._btn_fit.clicked.connect(self.fit_asked)
        lay.addWidget(self._btn_fit)

        lay.addSpacing(16)

        # Zone des toggles propres à l'écran — remplie via add_toggle/add_spacing.
        self._extras_at = lay.count()
        lay.addStretch()

        self._size_label = QLabel("")
        self._size_label.setFont(self._font)
        self._size_label.setStyleSheet(f"color:{C.TEXT_DIM};")
        lay.addWidget(self._size_label)

        lay.addSpacing(8)

        self._coord_label = QLabel()
        self._coord_label.setFont(self._font)
        lay.addWidget(self._coord_label)
        self.set_cursor_px(None, None)

    # ── Construction ──────────────────────────────────────────────

    def _icon_btn(self, key: str, icon_px: int, size, tip: str) -> QPushButton:
        b = QPushButton()
        b.setIcon(icons.get(key, C.TEXT_NORM))
        b.setIconSize(QSize(icon_px, icon_px))
        b.setFixedSize(*size)
        b.setToolTip(tip)
        return b

    def add_toggle(self, icon_key: str, tip: str, slot=None) -> QToolButton:
        """Toggle iconifié inséré dans la zone du milieu.
        L'état coché est porté par le sélecteur QSS :checked (fond périwinkle),
        donc robuste même sous blockSignals (ex: exclusion grille 8/16)."""
        b = QToolButton()
        b.setIcon(icons.get(icon_key, icons.COLOR_DEFAULT, C.ACCENT))
        b.setIconSize(QSize(18, 18))
        b.setCheckable(True)
        b.setFixedSize(32, 32)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER};background:{C.BG_INPUT};"
            f"border-radius:4px;padding:0px;margin:0px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )
        if slot is not None:
            b.toggled.connect(slot)
        self._lay.insertWidget(self._extras_at, b)
        self._extras_at += 1
        return b

    def add_spacing(self, px: int):
        """Respiration entre deux groupes de toggles."""
        self._lay.insertSpacing(self._extras_at, px)
        self._extras_at += 1

    # ── Affichage ─────────────────────────────────────────────────

    def set_zoom(self, zoom: float):
        self._zoom_label.setText(f"{round(zoom * 100)}%")

    def set_canvas_size(self, w: int, h: int):
        self._size_label.setText(f"{w}×{h}" if w and h else "")

    def set_cursor_px(self, x: int | None, y: int | None):
        """Position du curseur en pixels du canvas — (None, None) hors du canvas."""
        if x is None or y is None:
            self._coord_label.setText("x:— y:—")
            self._coord_label.setStyleSheet(f"color:{C.TEXT_DIM};")
        else:
            self._coord_label.setText(f"x:{x} y:{y}")
            self._coord_label.setStyleSheet(f"color:{C.TEXT_NORM};")
