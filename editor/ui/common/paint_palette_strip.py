"""editor/ui/common/paint_palette_strip.py — bande de sélection de palette active.

Bande horizontale de swatches (les sous-palettes d'un asset) placée en TÊTE d'un
canvas : clic = palette active (surbrillance). Purement une vue — émet
`selected(idx)`. Partagée : Background Editor (palette de peinture de tuiles) et
Sprite Editor (palette active de preview)."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C, T
from ui.common.palette_swatch import swatch_icon


class PaintPaletteStrip(QWidget):
    selected = pyqtSignal(int)
    _ICON = 24

    def __init__(self, accent: str, label: str = "PALETTE", parent=None):
        super().__init__(parent)
        self._accent = accent
        self._active = 0
        self._btns: list[QPushButton] = []
        self._colors: list = []   # palettes du dernier load(), pour ré-identifier la
                                   # sélection par CONTENU (pas par index) au reload suivant
        self.setStyleSheet(
            f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        lay.addWidget(lbl)
        self._row = QHBoxLayout()
        self._row.setSpacing(4)
        lay.addLayout(self._row)
        lay.addStretch()

    def active(self) -> int:
        return self._active

    def load(self, palettes: list, active: int = 0):
        """`active` ne sert que de repli (premier chargement, ou si la palette
        précédemment active a disparu) : si elle est encore présente dans
        `palettes` (même contenu, peu importe son nouvel index — une palette
        insérée avant elle décale tout), elle reste sélectionnée. Sans ce
        repérage par CONTENU, un index resterait valide mais pointerait sur
        une palette différente après insertion/suppression, désynchronisant
        la surbrillance et l'aperçu peint (couleurs d'une autre palette)."""
        prev_colors = (
            self._colors[self._active]
            if self._colors and 0 <= self._active < len(self._colors) else None
        )
        for b in self._btns:
            self._row.removeWidget(b)
            b.deleteLater()
        self._btns.clear()
        self._colors = [list(cols) for cols in palettes]
        n = len(self._colors)
        resolved = active
        if prev_colors is not None:
            try:
                resolved = self._colors.index(prev_colors)
            except ValueError:
                pass
        self._active = max(0, min(resolved, n - 1)) if n else 0
        for i, cols in enumerate(self._colors):
            btn = QPushButton()
            btn.setFixedSize(self._ICON + 8, self._ICON + 8)
            btn.setIcon(swatch_icon(list(cols), self._ICON))
            btn.setIconSize(QSize(self._ICON, self._ICON))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Palette {i}")
            btn.clicked.connect(lambda _c=False, i=i: self._select(i))
            self._style(btn, i == self._active)
            self._row.addWidget(btn)
            self._btns.append(btn)

    def _style(self, btn: QPushButton, active: bool):
        border = self._accent if active else C.BORDER_MID
        width = 2 if active else 1
        btn.setStyleSheet(
            f"QPushButton{{background:{C.BG_INPUT};border:{width}px solid {border};"
            f"border-radius:4px;}}"
            f"QPushButton:hover{{border-color:{self._accent};}}")

    def _select(self, i: int):
        self._active = i
        for j, b in enumerate(self._btns):
            self._style(b, j == i)
        self.selected.emit(i)
