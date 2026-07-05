"""ui/sprite_editor/direction_widget.py — sélecteur de directions 3×3 pour une AnimState."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QToolButton
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.common.theme import C, T
from ui.common.icons import get as _ico
from core.project import AnimState

_DIR_GRID = [
    # (dir_id, icon_key, tooltip, grid_row, grid_col)
    (8, "dir_nw", "NW", 0, 0), (1, "dir_n", "N",  0, 1), (2, "dir_ne", "NE", 0, 2),
    (7, "dir_w",  "W",  1, 0), (0, "dir_omni", "Omni (toutes directions)", 1, 1), (3, "dir_e", "E",  1, 2),
    (6, "dir_sw", "SW", 2, 0), (5, "dir_s", "S",  2, 1), (4, "dir_se", "SE", 2, 2),
]

# Paires source → miroir horizontal (E→W, NE→NW, SE→SW)
_H_MIRROR_PAIRS = [(3, 7), (2, 8), (4, 6)]
# Paires source → miroir vertical (N→S, NE→SE, NW→SW)
_V_MIRROR_PAIRS = [(1, 5), (2, 4), (8, 6)]

_BTN_SIZE = 44   # pixels, carré

_STY_NORMAL = (
    f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
    f"border:1px solid {C.BORDER};border-radius:5px;"
    f"font-size:16px;}}"
    f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};"
    f"border-color:{C.BORDER_MID};}}"
    f"QToolButton:checked{{color:{C.ACCENT_GRN};border:2px solid {C.ACCENT_GRN};"
    f"background:{C.BG_SEL};}}"
)
_STY_MIRRORED = (
    f"QToolButton{{color:#3a6a8a;background:#0d1a22;"
    f"border:1px dashed #2a4a5a;border-radius:5px;"
    f"font-size:16px;}}"
    f"QToolButton:checked{{color:{C.ACCENT_BLU};border:2px dashed {C.ACCENT_BLU};"
    f"background:#0e1f2e;}}"
)
_STY_OMNI = (
    f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_DEEP};"
    f"border:1px solid {C.BORDER_DARK};border-radius:5px;"
    f"font-size:14px;}}"
    f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
    f"QToolButton:checked{{color:{C.ACCENT_GRN};border:2px solid {C.ACCENT_GRN};"
    f"background:{C.BG_SEL};}}"
)

class _DirButton(QToolButton):
    """Bouton de direction dans la grille 3×3 — icône flèche (ui/icons.py), taille carrée fixe."""

    def __init__(self, dir_id: int, icon_key: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.dir_id = dir_id
        self._icon_key = icon_key
        self.setCheckable(True)
        self.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self.setIconSize(QSize(20, 20))
        self.setToolTip(tooltip)
        self._is_omni = (dir_id == 0)
        self.set_mirrored(False)

    def set_mirrored(self, mirrored: bool):
        from ui.common.icons import get as _ico

        if self._is_omni:
            self.setStyleSheet(_STY_OMNI)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT_GRN))
        elif mirrored:
            self.setStyleSheet(_STY_MIRRORED)
            self.setIcon(_ico(self._icon_key, "#3a6a8a", C.ACCENT_BLU))
        else:
            self.setStyleSheet(_STY_NORMAL)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT_GRN))


class DirectionWidget(QWidget):
    """
    Grille 3×3 de directions + boutons H-Mirror / V-Mirror.
    Émet directions_changed(active_dirs, h_mirror, v_mirror).
    """

    directions_changed = pyqtSignal(list, bool, bool)  # [dir_id], h_mirror, v_mirror

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocking = False
        self._h_mirror = False
        self._v_mirror = False
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QGridLayout

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Grille 3×3 — taille fixe pour garder un vrai carré
        GAP = 4
        SIDE = _BTN_SIZE * 3 + GAP * 2
        grid_w = QWidget()
        grid_w.setFixedSize(SIDE, SIDE)
        grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(GAP)
        grid.setContentsMargins(0, 0, 0, 0)
        for c in range(3):
            grid.setColumnMinimumWidth(c, _BTN_SIZE)
            grid.setRowMinimumHeight(c, _BTN_SIZE)

        self._dir_btns: dict[int, _DirButton] = {}
        for dir_id, icon, tip, row, col in _DIR_GRID:
            btn = _DirButton(dir_id, icon, tip)
            btn.toggled.connect(lambda checked, d=dir_id: self._on_dir_toggled(d, checked))
            grid.addWidget(btn, row, col)
            self._dir_btns[dir_id] = btn

        root.addWidget(grid_w, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Boutons H / V mirror
        _MIRROR_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;"
            f"font-family:{T.MONO};font-size:{T.XS}px;padding:4px 8px;}}"
            f"QToolButton:checked{{color:{C.ACCENT_BLU};border-color:{C.ACCENT_BLU};"
            f"background:#0e1a22;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )

        mirror_row = QHBoxLayout()
        mirror_row.setSpacing(4)
        mirror_row.setContentsMargins(0, 0, 0, 0)

        from ui.common.icons import get as _ico

        self._btn_h = QToolButton(); self._btn_h.setText("  H-Mirror")
        self._btn_h.setIcon(_ico("mirror_h", C.TEXT_DIM, C.ACCENT_BLU))
        self._btn_h.setIconSize(QSize(16, 16))
        self._btn_h.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_h.setCheckable(True); self._btn_h.setStyleSheet(_MIRROR_BTN)
        self._btn_h.setFixedHeight(28)
        self._btn_h.setToolTip("Miroir horizontal : génère W, NW, SW depuis E, NE, SE")
        self._btn_h.toggled.connect(self._on_h_mirror)

        self._btn_v = QToolButton(); self._btn_v.setText("  V-Mirror")
        self._btn_v.setIcon(_ico("mirror_v", C.TEXT_DIM, C.ACCENT_BLU))
        self._btn_v.setIconSize(QSize(16, 16))
        self._btn_v.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_v.setCheckable(True); self._btn_v.setStyleSheet(_MIRROR_BTN)
        self._btn_v.setFixedHeight(28)
        self._btn_v.setToolTip("Miroir vertical : génère S, SE, SW depuis N, NE, NW")
        self._btn_v.toggled.connect(self._on_v_mirror)

        mirror_row.addWidget(self._btn_h, 1)
        mirror_row.addWidget(self._btn_v, 1)
        root.addLayout(mirror_row)

    def load(self, state: AnimState):
        """Charge la configuration de directions depuis un AnimState."""
        self._blocking = True
        active = {sd.dir for sd in state.directions}
        mirrored = {sd.dir for sd in state.directions if sd.mirror_of is not None}
        h_mirror = any(sd.mirror_of is not None and sd.flip_h for sd in state.directions)
        v_mirror = any(sd.mirror_of is not None and sd.flip_v for sd in state.directions)

        for dir_id, btn in self._dir_btns.items():
            btn.setChecked(dir_id in active)
            btn.set_mirrored(dir_id in mirrored)

        self._btn_h.setChecked(h_mirror)
        self._btn_v.setChecked(v_mirror)
        self._h_mirror = h_mirror
        self._v_mirror = v_mirror
        self._blocking = False

    def _on_dir_toggled(self, dir_id: int, checked: bool):
        if self._blocking:
            return
        self._update_mirrors()
        self._emit()

    def _on_h_mirror(self, checked: bool):
        if self._blocking:
            return
        self._h_mirror = checked
        self._update_mirrors()
        self._emit()

    def _on_v_mirror(self, checked: bool):
        if self._blocking:
            return
        self._v_mirror = checked
        self._update_mirrors()
        self._emit()

    def _update_mirrors(self):
        """Met à jour l'apparence des boutons miroirs selon l'état H/V."""
        self._blocking = True
        active = {d for d, btn in self._dir_btns.items() if btn.isChecked()}
        mirrored: set[int] = set()

        if self._h_mirror:
            for src, dst in _H_MIRROR_PAIRS:
                if src in active:
                    mirrored.add(dst)
                    self._dir_btns[dst].setChecked(True)
        if self._v_mirror:
            for src, dst in _V_MIRROR_PAIRS:
                if src in active:
                    mirrored.add(dst)
                    self._dir_btns[dst].setChecked(True)

        for dir_id, btn in self._dir_btns.items():
            btn.set_mirrored(dir_id in mirrored)

        self._blocking = False

    def _emit(self):
        active = [d for d, btn in self._dir_btns.items() if btn.isChecked()]
        self.directions_changed.emit(active, self._h_mirror, self._v_mirror)


