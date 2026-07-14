"""ActorInspector — transform, components, éditeur de component sélectionné."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QFrame, QCheckBox, QListWidget, QListWidgetItem, QMenu, QScrollArea, QSizePolicy,
)
from PyQt6.QtGui import QFont, QCursor, QPixmap, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from core.project import (
    Project, Scene, Actor, MIME_SCRIPT, component_type_name,
)
from core.history import get_history, SetFieldCmd, AddComponentCmd, RemoveComponentCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS

COMPONENT_LABELS = {
    "sprite":        "Sprite",
    "collision_box": "Collision",
    "sound_fx":      "SoundFX",
    "script":        "Script",
}

# ── Tooltips Lua mirror (transform/actor uniquement — les tooltips par
# component vivent dans leur propre component_editor, ex: collision.py) ──
_TOOLTIPS = {
    "actor.active":      ("self.active",
                          "Si false, l'actor est ignoré : pas d'update,\npas de collision, OAM slot libéré.\n"
                          "Lua : self.active = false"),
    "actor.x":           ("self.x",
                          "Position horizontale en pixels (0–239).\n"
                          "Lecture directe depuis Lua : local px = self.x\n"
                          "Écriture → self:set_pos(x, y)  ou  self:move(dx, dy)"),
    "actor.y":           ("self.y",
                          "Position verticale en pixels (0–159).\n"
                          "Lecture directe depuis Lua : local py = self.y\n"
                          "Écriture → self:set_pos(x, y)  ou  self:move(dx, dy)"),
    "actor.priority":    ("self.priority  (lecture seule)",
                          "Ordre d'affichage sur les BG layers.\n"
                          "0 = devant tous les backgrounds,  3 = derrière tous.\n"
                          "GBA : OAM attribute 2, bits 10–11."),
    "actor.visible":     ("self:set_visible(true/false)",
                          "Masque l'actor sans le désactiver.\n"
                          "Le slot OAM reste réservé mais avec bit OBJ_DISABLE."),
}

def _tip(w: QWidget, key: str):
    """Applique le tooltip Lua+GBA sur un widget."""
    if key not in _TOOLTIPS:
        return
    lua_expr, desc = _TOOLTIPS[key]
    w.setToolTip(f"<b style='color:{C.ACCENT_BLU}'>{lua_expr}</b><br><br>{desc.replace(chr(10), '<br>')}")


# ──────────────────────────────────────────────────────────────────
#  Liste de components qui accepte le drop d'un Script
# ──────────────────────────────────────────────────────────────────
class ComponentListWidget(QListWidget):
    script_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT): e.acceptProposedAction()
        else: super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT): e.acceptProposedAction()
        else: super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT):
            self.script_dropped.emit(bytes(e.mimeData().data(MIME_SCRIPT)).decode("utf-8"))
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Sélecteur de direction 3×3
# ──────────────────────────────────────────────────────────────────
_DIR_ARROWS = {
    (-1, -1): "↖", (0, -1): "↑", (1, -1): "↗",
    (-1,  0): "←", (0,  0): "·", (1,  0): "→",
    (-1,  1): "↙", (0,  1): "↓", (1,  1): "↘",
}

class _DirectionPicker(QWidget):
    """Grille 3×3 de boutons représentant une direction discrète (-1|0|1 × -1|0|1)."""

    changed = pyqtSignal(int, int)   # dir_x, dir_y

    _CELL = 22   # px par cellule
    _GAP  = 2

    _SS_OFF = (
        f"QPushButton{{background:#1e1e1e;color:#555;border:1px solid #2a2a2a;"
        f"border-radius:2px;font-size:11px;padding:0;}}"
        f"QPushButton:hover{{background:#2a2a2a;color:#aaa;border-color:#3a3a3a;}}"
    )
    _SS_ON = (
        f"QPushButton{{background:#1e3a2a;color:#4caf78;border:1px solid #4caf78;"
        f"border-radius:2px;font-size:11px;padding:0;}}"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir_x = 0
        self._dir_y = 0

        grid = QHBoxLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        # 3 colonnes
        self._btns: dict[tuple[int,int], QPushButton] = {}
        cols = [QVBoxLayout() for _ in range(3)]
        for col_l in cols:
            col_l.setSpacing(self._GAP)
            col_l.setContentsMargins(0, 0, 0, 0)

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                btn = QPushButton(_DIR_ARROWS[(dx, dy)])
                btn.setFixedSize(QSize(self._CELL, self._CELL))
                btn.setStyleSheet(self._SS_OFF)
                btn.clicked.connect(lambda _=False, x=dx, y=dy: self._on_click(x, y))
                self._btns[(dx, dy)] = btn
                col_idx = dx + 1
                cols[col_idx].addWidget(btn)

        for i, col_l in enumerate(cols):
            w = QWidget()
            w.setLayout(col_l)
            w.setFixedWidth(self._CELL)
            grid.addWidget(w)
            if i < 2:
                grid.addSpacing(self._GAP)

        self._update_styles()
        total = 3 * self._CELL + 2 * self._GAP
        self.setFixedSize(total, 3 * self._CELL + 2 * self._GAP)

    def set_direction(self, dx: int, dy: int):
        self._dir_x = max(-1, min(1, dx))
        self._dir_y = max(-1, min(1, dy))
        self._update_styles()

    def _on_click(self, dx: int, dy: int):
        self._dir_x = dx
        self._dir_y = dy
        self._update_styles()
        self.changed.emit(dx, dy)

    def _update_styles(self):
        for (dx, dy), btn in self._btns.items():
            btn.setStyleSheet(
                self._SS_ON if (dx == self._dir_x and dy == self._dir_y) else self._SS_OFF
            )


# ──────────────────────────────────────────────────────────────────
#  ActorInspector
# ──────────────────────────────────────────────────────────────────
class ActorInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actor: Optional[Actor] = None
        self._project: Optional[Project] = None
        self._scene: Optional[Scene] = None
        self._blocking = False
        self._is_prefab_template = False
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_DEEP}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel("Selectionne un actor\ndans le panneau gauche")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        self._content.setStyleSheet(f"background:{C.BG_DEEP};")
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(5)

        # ── Header : preview sprite + nom ────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            f"background:{C.BG_BASE}; border-bottom:1px solid {C.BORDER}; border-radius:0;"
        )
        header_frame.setFixedHeight(60)
        hl = QHBoxLayout(header_frame)
        hl.setContentsMargins(8, 6, 8, 6)
        hl.setSpacing(10)

        self._sprite_preview = QLabel()
        self._sprite_preview.setFixedSize(52, 52)
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED}; border:1px solid {C.BORDER}; border-radius:5px;"
        )
        self._sprite_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sprite_preview.setToolTip(
            f"<b style='color:{C.ACCENT_BLU}'>Sprite de départ</b><br><br>"
            "Cliquer pour assigner un sprite depuis le projet.<br>"
            "Première frame de l'AnimState initial."
        )
        self._sprite_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sprite_preview.mousePressEvent = lambda e: self._pick_sprite()
        hl.addWidget(self._sprite_preview)

        name_col = QVBoxLayout()
        name_col.setSpacing(3)

        self._tag_lbl = QLabel("Index : —")
        self._tag_lbl.setFont(QFont(T.MONO, T.SM))
        self._tag_lbl.setStyleSheet(f"color:{C.ACCENT_GRN};")
        self._tag_lbl.setToolTip(
            "Position de l'actor dans la scène (ordre de traitement et de rendu)."
        )
        name_col.addWidget(self._tag_lbl)
        hl.addLayout(name_col, 1)
        cl.addWidget(header_frame)

        # ── Badge prefab (visible seulement si actor.prefab_name) ──
        self._prefab_badge = QFrame()
        self._prefab_badge.setStyleSheet(
            f"background:{C.BG_DEEP}; border-left:3px solid {C.ACCENT_PRP}; border-radius:2px;"
        )
        self._prefab_badge.setFixedHeight(28)
        pb_layout = QHBoxLayout(self._prefab_badge)
        pb_layout.setContentsMargins(8, 0, 6, 0)
        pb_layout.setSpacing(6)
        self._prefab_badge_lbl = QLabel()
        self._prefab_badge_lbl.setFont(QFont(T.MONO, T.SM))
        self._prefab_badge_lbl.setStyleSheet(f"color:{C.ACCENT_PRP};")
        pb_layout.addWidget(self._prefab_badge_lbl, 1)
        btn_open_prefab = QPushButton("Ouvrir prefab")
        btn_open_prefab.setFont(QFont(T.MONO, T.XS))
        btn_open_prefab.setFixedHeight(18)
        btn_open_prefab.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT_PRP};background:transparent;border:1px solid {C.ACCENT_PRP};"
            f"border-radius:2px;padding:0 5px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.ACCENT_PRP};}}"
        )
        btn_open_prefab.clicked.connect(self._open_prefab)
        pb_layout.addWidget(btn_open_prefab)
        btn_unlink = QPushButton("×")
        btn_unlink.setFont(QFont(T.MONO, T.MD))
        btn_unlink.setFixedSize(18, 18)
        btn_unlink.setToolTip("Casser le lien avec le prefab\n(l'actor devient indépendant)")
        btn_unlink.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:transparent;border:none;}}"
            f"QPushButton:hover{{color:{C.ACCENT_RED};}}"
        )
        btn_unlink.clicked.connect(self._unlink_prefab)
        pb_layout.addWidget(btn_unlink)
        self._prefab_badge.setVisible(False)
        cl.addWidget(self._prefab_badge)

        self._active = QCheckBox("Actif au démarrage")
        self._active.setFont(QFont(T.MONO, T.MD))
        self._active.setStyleSheet(
            f"color:{C.TEXT_NORM}; padding:4px 6px;"
            f"background:{C.BG_BASE}; border-radius:3px;"
        )
        self._active.toggled.connect(lambda v: self._set("active", v))
        _tip(self._active, "actor.active")
        cl.addWidget(self._active)

        # ── TRANSFORM card ───────────────────────────────────────────
        self._transform_group = QFrame()
        self._transform_group.setObjectName("transform_card")
        self._transform_group.setStyleSheet(
            f"QFrame#transform_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
            f"border-left:3px solid {C.ACCENT_GRN};border-radius:4px;}}"
            # Les enfants QFrame (séparateurs, etc.) ne reçoivent pas le style parent
            f"QFrame#transform_card QFrame{{background:transparent;border:none;}}"
            f"QLabel{{background:transparent;border:none;}}"
        )
        tl = QVBoxLayout(self._transform_group)
        tl.setContentsMargins(8, 6, 8, 8)
        tl.setSpacing(7)

        # En-tête section avec barre colorée
        tg_hdr = QHBoxLayout()
        tg_lbl = QLabel("TRANSFORM")
        tg_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        tg_lbl.setStyleSheet(f"color:{C.ACCENT_GRN}; letter-spacing:1px;")
        tg_hdr.addWidget(tg_lbl); tg_hdr.addStretch()
        tl.addLayout(tg_hdr)

        from ui.common.widgets import W as _W

        # ── Position : X [ ]  Y [ ] ──────────────────────────────
        self._tx = _W.spinbox(0, min_v=-512, max_v=512)
        self._tx.valueChanged.connect(lambda v: self._set("x", v))
        _tip(self._tx, "actor.x")
        self._ty = _W.spinbox(0, min_v=-512, max_v=512)
        self._ty.valueChanged.connect(lambda v: self._set("y", v))
        _tip(self._ty, "actor.y")
        _W.pair("Position", "X", C.AXIS_X, self._tx, "Y", C.AXIS_Y, self._ty, tl,
                label_width=58)

        # ── Direction initiale : sélecteur 3×3 ───────────────────
        dir_row = QHBoxLayout(); dir_row.setSpacing(8)
        dir_row.setContentsMargins(0, 2, 0, 2)
        dir_lbl = QLabel("Direction"); dir_lbl.setFont(QFont(T.MONO, T.MD))
        dir_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        dir_lbl.setFixedWidth(58)
        dir_row.addWidget(dir_lbl)
        self._dir_picker = _DirectionPicker()
        self._dir_picker.changed.connect(self._on_direction)
        dir_row.addWidget(self._dir_picker)
        dir_row.addStretch()
        tl.addLayout(dir_row)

        # ── Priority ─────────────────────────────────────────────
        # (la palette OBJ se règle désormais dans l'éditeur du SpriteComponent,
        # cf. component_editors/sprite.py — palette_picker_slot)
        self._tpriority = _W.spinbox(0, min_v=0, max_v=3)
        self._tpriority.valueChanged.connect(lambda v: self._set("priority", v))
        _tip(self._tpriority, "actor.priority")
        _W.row("Priority", self._tpriority, tl, label_width=58)

        # ── Visible ───────────────────────────────────────────────
        self._tvisible = QCheckBox("Visible"); self._tvisible.setStyleSheet(QSS.checkbox)
        self._tvisible.toggled.connect(lambda v: self._set("visible", v))
        _tip(self._tvisible, "actor.visible")
        tl.addWidget(self._tvisible)
        cl.addWidget(self._transform_group)

        # ── COMPONENTS card ──────────────────────────────────────────
        _comp_card = QFrame()
        _comp_card.setObjectName("comp_card")
        _comp_card.setStyleSheet(
            f"QFrame#comp_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
            f"border-left:3px solid {C.ACCENT_GRN};border-radius:4px;}}"
            f"QFrame#comp_card QFrame{{background:transparent;border:none;}}"
            f"QFrame#comp_card QLabel{{background:transparent;border:none;}}"
        )
        _comp_card_l = QVBoxLayout(_comp_card)
        _comp_card_l.setContentsMargins(0, 0, 0, 0)
        _comp_card_l.setSpacing(0)
        cl.addWidget(_comp_card)

        _ico_btn = (
            f"QPushButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;"
            f"font-family:{T.MONO};font-size:{T.XL}px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};border-color:#555;}}"
        )
        # Template avec slot {c} pour la couleur d'accent
        _toggle_style = (
            "QToolButton{color:" + "{c}" + f";border:none;background:{C.BG_PANEL};"
            "font-family:monospace;font-size:8pt;font-weight:bold;"
            f"text-align:left;padding:4px 8px;letter-spacing:1px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};}}"
        )

        self._toggle_style_tpl = _toggle_style   # gardé pour _apply_context_color

        # Header COMPONENTS (collapsible)
        comp_hdr_row = QHBoxLayout()
        comp_hdr_row.setContentsMargins(0, 0, 4, 0)
        comp_hdr_row.setSpacing(2)
        self._comp_toggle = QToolButton()
        self._comp_toggle.setText(f"▾  COMPONENTS")
        self._comp_toggle.setStyleSheet(_toggle_style.replace("{c}", C.ACCENT_GRN))
        self._comp_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._comp_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._comp_toggle.setFixedHeight(26)

        btn_add = QPushButton("+"); btn_add.setFixedSize(20, 20)
        btn_add.setStyleSheet(_ico_btn); btn_add.clicked.connect(self._show_add_menu)
        btn_del = QPushButton("−"); btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet(_ico_btn); btn_del.clicked.connect(self._remove_selected_component)
        comp_hdr_row.addWidget(self._comp_toggle, 1)
        comp_hdr_row.addWidget(btn_add); comp_hdr_row.addWidget(btn_del)
        _comp_card_l.addLayout(comp_hdr_row)

        # Séparateur sous le header de la carte
        _comp_hdr_sep = QFrame(); _comp_hdr_sep.setFrameShape(QFrame.Shape.HLine)
        _comp_hdr_sep.setStyleSheet(f"color:{C.BORDER}; margin:0;")
        _comp_card_l.addWidget(_comp_hdr_sep)

        self._comp_list = ComponentListWidget()
        self._comp_list.setFixedHeight(100)
        self._comp_list.setFont(QFont(T.MONO, T.MD))
        self._comp_list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};color:{C.TEXT_NORM};"
            f"border:none;border-radius:0;}}"
            f"QListWidget::item{{padding:4px 8px;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};color:{C.ACCENT_GRN};"
            f"border-left:2px solid {C.ACCENT_GRN};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )
        self._comp_list.currentRowChanged.connect(self._on_component_selected)
        self._comp_list.script_dropped.connect(self._on_script_dropped)
        _comp_card_l.addWidget(self._comp_list)

        self._comp_toggle.clicked.connect(lambda: self._toggle_section(
            self._comp_toggle, self._comp_list, "COMPONENTS", self._ctx_color))

        # ── ÉDITEUR card ─────────────────────────────────────────────
        self._editor_card = QFrame()
        self._editor_card.setObjectName("editor_card")
        self._editor_card.setStyleSheet(
            f"QFrame#editor_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
            f"border-left:3px solid {C.ACCENT_ORG};border-radius:4px;}}"
            f"QFrame#editor_card QFrame{{background:transparent;border:none;}}"
            f"QFrame#editor_card QLabel{{background:transparent;border:none;}}"
        )
        _editor_card_l = QVBoxLayout(self._editor_card)
        _editor_card_l.setContentsMargins(0, 0, 0, 0)
        _editor_card_l.setSpacing(0)
        cl.addWidget(self._editor_card)

        self._editor_toggle = QToolButton()
        self._editor_toggle.setText("▾  ÉDITEUR")
        self._editor_toggle.setStyleSheet(_toggle_style.replace("{c}", C.ACCENT_ORG))
        self._editor_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._editor_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._editor_toggle.setFixedHeight(26)
        _editor_card_l.addWidget(self._editor_toggle)

        _editor_hdr_sep = QFrame(); _editor_hdr_sep.setFrameShape(QFrame.Shape.HLine)
        _editor_hdr_sep.setStyleSheet(f"color:{C.BORDER}; margin:0;")
        _editor_card_l.addWidget(_editor_hdr_sep)

        self._editor_container = QWidget()
        self._editor_container.setStyleSheet(f"background:{C.BG_BASE};")
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(8, 6, 8, 8)
        self._editor_layout.setSpacing(6)
        _editor_card_l.addWidget(self._editor_container)

        self._editor_toggle.clicked.connect(lambda: self._toggle_section(
            self._editor_toggle, self._editor_container, "ÉDITEUR", self._ctx_color))

        self._ctx_color = C.ACCENT_GRN   # couleur courante du contexte (actor par défaut)
        self._editor_section_visible = True   # état mémorisé du toggle ÉDITEUR

        cl.addStretch()

        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    # ── Chargement ───────────────────────────────────────────────

    # Couleurs de contexte (cohérentes avec assets_finder_panel et InspectorPanel)
    _COLOR_ACTOR  = C.ACCENT_GRN
    _COLOR_PREFAB = C.ACCENT_BLU
    _COLOR_SEL_BG_ACTOR  = C.BG_SEL
    _COLOR_SEL_BG_PREFAB = f"{C.ACCENT_BLU}15"

    def _apply_context_color(self, color: str, sel_bg: str):
        """Met à jour les toggles COMPONENTS / ÉDITEUR, la bordure de carte et la sélection de liste."""
        self._ctx_color = color
        tpl = self._toggle_style_tpl
        self._comp_toggle.setStyleSheet(tpl.replace("{c}", color))
        # La bordure gauche de la carte Components suit la couleur de contexte
        self._editor_card.setStyleSheet(
            f"QFrame#editor_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
            f"border-left:3px solid {C.ACCENT_ORG};border-radius:4px;}}"
        )
        self._comp_list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};color:{C.TEXT_NORM};"
            f"border:none;border-radius:0;}}"
            f"QListWidget::item{{padding:4px 8px;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{sel_bg};color:{color};"
            f"border-left:2px solid {color};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )

    def load_prefab(self, prefab, project: Project):
        self._actor = prefab
        self._project = project
        self._is_prefab_template = True
        self._scene = None
        self._apply_context_color(self._COLOR_PREFAB, self._COLOR_SEL_BG_PREFAB)
        if not prefab:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._active.setChecked(True)
        self._prefab_badge.setVisible(False)   # un prefab n'est pas une instance
        self._transform_group.setVisible(False)
        self._blocking = False
        self._refresh_component_list()

    def load(self, actor: Actor, project: Project, scene: Optional[Scene] = None):
        self._actor = actor
        self._project = project
        self._is_prefab_template = False
        self._scene = scene
        self._apply_context_color(self._COLOR_ACTOR, self._COLOR_SEL_BG_ACTOR)
        if not actor:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        # Index dans la scène
        if scene:
            try:
                idx = scene.actors.index(actor)
                self._tag_lbl.setText(f"Index : {idx}")
            except ValueError:
                self._tag_lbl.setText("Index : —")
        else:
            self._tag_lbl.setText("Index : (prefab)")
        self._active.setChecked(actor.active)
        # Badge prefab
        if actor.prefab_name:
            self._prefab_badge_lbl.setText(f"◈ Instance de  {actor.prefab_name}")
            self._prefab_badge.setVisible(True)
        else:
            self._prefab_badge.setVisible(False)
        self._transform_group.setVisible(True)
        self._tx.setValue(actor.x); self._ty.setValue(actor.y)
        self._dir_picker.set_direction(getattr(actor, "dir_x", 0), getattr(actor, "dir_y", 0))
        self._tpriority.setValue(actor.priority)
        self._tvisible.setChecked(actor.visible)
        self._blocking = False
        self._refresh_component_list()
        self._refresh_sprite_preview()

    def update_position(self, x: int, y: int):
        if self._blocking or not self._actor: return
        self._blocking = True
        self._tx.setValue(x); self._ty.setValue(y)
        self._blocking = False

    def notify_lua_changed(self, path: str):
        """Appelé par MainWindow quand ProjectWatcher détecte un changement Lua."""
        pass

    def _refresh_sprite_preview(self):
        """Affiche la première frame de l'état initial dans le header."""
        self._sprite_preview.clear()
        self._sprite_preview.setText("?")
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED};border:1px solid {C.BORDER};border-radius:4px;"
            f"color:{C.BORDER_MID};font-size:18px;"
        )
        if not self._actor or not self._project:
            return
        comp = self._actor.get_component("sprite")
        if not comp or not comp.sprite_name:
            return
        sprite = self._project.get_sprite(comp.sprite_name)
        if not sprite or not sprite.asset:
            return
        asset_path = self._project.asset_abs(sprite.asset)
        if not asset_path or not asset_path.exists():
            return
        # Trouver l'AnimState correspondant à initial_state
        state_name = getattr(comp, "initial_state", "Idle")
        state = next((s for s in sprite.states if s.name == state_name), None)
        if not state and sprite.states:
            state = sprite.states[0]
        sd = state.directions[0] if state and state.directions else None
        if not sd or not sd.frames:
            return
        frame = sd.frames[0]
        px = QPixmap(str(asset_path))
        if px.isNull():
            return
        cropped = QPixmap(sprite.frame_w, sprite.frame_h)
        cropped.fill(Qt.GlobalColor.transparent)
        painter = QPainter(cropped)
        for t in frame.tiles:
            tile_px = px.copy(t.src_col * 8, t.src_row * 8, 8, 8)
            painter.drawPixmap(t.dst_col * 8, t.dst_row * 8, tile_px)
        painter.end()
        scaled = cropped.scaled(
            44, 44,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._sprite_preview.setPixmap(scaled)
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED};border:1px solid {C.BORDER_MID};border-radius:4px;"
        )
        self._sprite_preview.setText("")

    def _pick_sprite(self):
        if not self._actor or not self._project:
            return
        sprites_dir = self._project.root / "assets" / "sprites"
        pngs = sorted(sprites_dir.glob("*.png")) if sprites_dir.exists() else []
        if not pngs:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Aucun sprite",
                "Aucun PNG trouvé dans assets/sprites/.")
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID};font-family:monospace;font-size:10pt;padding:2px;}}"
            f"QMenu::item{{padding:5px 20px 5px 12px;border-radius:2px;}}"
            f"QMenu::item:selected{{background:{C.BG_SEL};color:{C.ACCENT_GRN};}}"
        )
        for png in pngs:
            action = menu.addAction(png.stem)
            action.setData(str(png))

        pos = self._sprite_preview.mapToGlobal(
            self._sprite_preview.rect().bottomLeft()
        )
        chosen = menu.exec(pos)
        if not chosen:
            return

        png_path = Path(chosen.data())
        sprite_name = png_path.stem

        # Récupérer ou créer le SpriteAsset correspondant
        from core.project import SpriteAsset
        sprite = self._project.get_sprite(sprite_name)
        if not sprite:
            dst = self._project.import_asset(png_path, "sprites")
            sprite = SpriteAsset(
                name=sprite_name,
                asset=self._project.asset_rel(dst),
            )
            self._project.sprites.append(sprite)
            with __import__("contextlib").suppress(Exception):
                get_dispatcher().save_sprite(sprite)

        comp = self._actor.get_component("sprite")
        if comp:
            comp.sprite_name = sprite_name
        else:
            self._actor.add_component("sprite", sprite_name=sprite_name)
        self._persist()
        self._refresh_sprite_preview()
        self._refresh_component_list()
        self.changed.emit()

    def _persist(self):
        if not self._project or not self._actor: return
        if self._is_prefab_template:
            get_dispatcher().save_prefab(self._actor)
        else:
            get_dispatcher().save_scene()
            get_dispatcher()._emit("scene_sprites_changed")

    def _open_prefab(self):
        """Bascule l'inspector sur le prefab source de cet actor."""
        if not self._actor or not self._actor.prefab_name or not self._project:
            return
        prefab = self._project.get_prefab(self._actor.prefab_name)
        if prefab:
            get_bus().select(prefab)

    def _unlink_prefab(self):
        """Casse le lien prefab — l'actor devient un actor standalone."""
        if not self._actor:
            return
        self._actor.prefab_name = None
        self._prefab_badge.setVisible(False)
        get_dispatcher().save_scene()

    def _set(self, field, value):
        if self._blocking or not self._actor: return
        old = getattr(self._actor, field, None)
        if old == value:
            return
        get_history().push(SetFieldCmd(
            self._actor, field, old, value,
            label=f"{self._actor.name}.{field}",
            persist_fn=self._persist,
        ))
        self.changed.emit()

    def _on_direction(self, dx: int, dy: int):
        if self._blocking or not self._actor: return
        self._set("dir_x", dx)
        self._set("dir_y", dy)

    # ── Components ───────────────────────────────────────────────

    def _refresh_component_list(self, keep_row: int = 0):
        self._comp_list.blockSignals(True)
        self._comp_list.clear()
        if self._actor:
            for comp in self._actor.components:
                type_name = component_type_name(comp)
                label = COMPONENT_LABELS.get(type_name, type_name)
                text = f"{label} [{comp.id}]" + ("  (inactif)" if not comp.active else "")
                self._comp_list.addItem(QListWidgetItem(text))
        self._comp_list.blockSignals(False)
        if self._comp_list.count():
            row = max(0, min(keep_row, self._comp_list.count() - 1))
            # setCurrentRow() (signaux débloqués ci-dessus) déclenche déjà
            # currentRowChanged -> _on_component_selected -> _build_editor() ;
            # un appel explicite ici reconstruirait tout l'éditeur une 2e fois
            # pour rien (double le travail à chaque sélection d'actor).
            self._comp_list.setCurrentRow(row)
        else:
            self._build_editor(None)

    def _toggle_section(self, toggle_btn: QToolButton, body: QWidget,
                        label: str, color: str):
        visible = not body.isVisible()
        body.setVisible(visible)
        arrow = "▾" if visible else "▸"
        toggle_btn.setText(f"{arrow}  {label}")
        # Mémoriser l'état pour que _clear_editor puisse le restaurer
        if body is self._editor_container:
            self._editor_section_visible = visible

    def _show_add_menu(self):
        if not self._actor: return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_NORM};border:1px solid {C.BORDER};}}"
            f"QMenu::item:selected{{background:{C.BG_SEL};}}"
        )
        existing_script = self._actor.get_component("script")
        has_active_script = existing_script is not None and existing_script.active
        for type_name, label in COMPONENT_LABELS.items():
            # Un seul ScriptComponent actif à la fois : le compilateur Lua->C
            # (lua_compiler._actor_script) n'en lit de toute façon qu'un seul.
            if type_name == "script" and has_active_script:
                continue
            menu.addAction(label, lambda t=type_name: self._add_component(t))
        menu.exec(QCursor.pos())

    def _add_component(self, type_name: str):
        comp = self._actor.add_component(type_name)
        target_row = len(self._actor.components) - 1

        def undo_refresh():
            self._persist()
            self._refresh_component_list(keep_row=max(0, target_row - 1))
            self.changed.emit()

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=target_row)
            self.changed.emit()

        # Construire la commande APRÈS que add_component a ajouté le comp
        # execute() est appelé par push() mais le comp est déjà dans la liste —
        # on substitue un no-op execute et on surcharge undo/redo manuellement.
        cmd = AddComponentCmd(self._actor, comp, persist_fn=do_refresh)
        # Retirer temporairement le comp pour que push() puisse l'ajouter via execute()
        self._actor.components.remove(comp)
        get_history().push(cmd)   # execute() le remet + rafraîchit

    def _on_script_dropped(self, script_rel: str):
        if not self._actor: return
        existing = self._actor.get_component("script")
        if existing is not None and existing.active:
            # Un seul ScriptComponent actif par actor (cf. _show_add_menu) —
            # on réassigne le script existant plutôt que d'en ajouter un 2e,
            # qui serait de toute façon ignoré au build.
            old_script = existing.script
            if old_script == script_rel:
                return
            row = self._actor.components.index(existing)

            def do_refresh():
                self._persist()
                self._refresh_component_list(keep_row=row)
                self.changed.emit()

            get_history().push(SetFieldCmd(
                existing, "script", old_script, script_rel,
                label=f"{self._actor.name}.script", persist_fn=do_refresh,
            ))
            return

        comp = self._actor.add_component("script", script=script_rel)
        target_row = len(self._actor.components) - 1

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=target_row)
            self.changed.emit()

        cmd = AddComponentCmd(self._actor, comp, persist_fn=do_refresh)
        self._actor.components.remove(comp)
        get_history().push(cmd)

    def _remove_selected_component(self):
        row = self._comp_list.currentRow()
        if row < 0 or not self._actor: return
        comp = self._actor.components[row]

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=row)
            self.changed.emit()

        get_history().push(RemoveComponentCmd(self._actor, comp, row, persist_fn=do_refresh))

    def _on_component_selected(self, row: int):
        if not self._actor or row < 0 or row >= len(self._actor.components):
            self._build_editor(None); return
        self._build_editor(self._actor.components[row])

    def _save_component_change(self, comp=None):
        """
        Persist sans reconstruire l'éditeur.
        Si comp est le composant actuellement affiché, synce les widgets via _field_syncers.
        Sinon (undo sur un autre comp), reconstruit l'éditeur complet.
        """
        self._persist()
        self._refresh_list_labels()
        if comp is not None and comp is not getattr(self, "_current_comp", None):
            row = self._comp_list.currentRow()
            self._build_editor(self._actor.components[row] if row >= 0 else None)
        self.changed.emit()

    def _refresh_list_labels(self):
        """Met à jour les textes de la QListWidget sans toucher à l'éditeur."""
        if not self._actor:
            return
        self._comp_list.blockSignals(True)
        for i, comp in enumerate(self._actor.components):
            item = self._comp_list.item(i)
            if item is None:
                continue
            type_name = component_type_name(comp)
            label = COMPONENT_LABELS.get(type_name, type_name)
            text = f"{label} [{comp.id}]" + ("  (inactif)" if not comp.active else "")
            item.setText(text)
        self._comp_list.blockSignals(False)

    def _clear_editor(self):
        # Détruire le QWidget container et recréer — la seule façon sûre
        # de purger à la fois les widgets ET les QHBoxLayout ajoutés par row().
        old = self._editor_container
        new_container = QWidget()
        new_container.setStyleSheet(f"background:{C.BG_BASE};")
        new_layout = QVBoxLayout(new_container)
        new_layout.setContentsMargins(8, 6, 8, 8)
        new_layout.setSpacing(6)

        # Remplacer dans le layout parent
        parent_layout = old.parent().layout() if old.parent() else None
        if parent_layout:
            idx = parent_layout.indexOf(old)
            if idx >= 0:
                parent_layout.insertWidget(idx, new_container)

        self._editor_container = new_container
        self._editor_layout    = new_layout

        # Restaurer l'état du toggle (replié/déplié) sur le nouveau container
        new_container.setVisible(self._editor_section_visible)
        arrow = "▾" if self._editor_section_visible else "▸"
        self._editor_toggle.setText(f"{arrow}  ÉDITEUR")

        # Rebrancher le toggle sur le nouveau container
        try:
            self._editor_toggle.clicked.disconnect()
        except RuntimeError:
            pass
        self._editor_toggle.clicked.connect(lambda: self._toggle_section(
            self._editor_toggle, self._editor_container, "ÉDITEUR", self._ctx_color))

        # Supprimer l'ancien (schedules deleteLater pour éviter crash de signal en cours)
        old.hide()
        old.setParent(None)  # type: ignore[arg-type]
        old.deleteLater()

    def _build_editor(self, comp):
        self._clear_editor()
        self._current_comp = comp
        # dict field → callable(value) pour resync les widgets sans rebuild
        self._field_syncers: dict[str, callable] = {}

        if not comp:
            lbl = QLabel("Sélectionne un component ci-dessus")
            lbl.setFont(QFont(T.MONO, T.MD))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:10px 6px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._editor_layout.addWidget(lbl); return

        from ui.common.widgets import W as _W

        def row(label, widget):
            return _W.row(label, widget, self._editor_layout)

        # ── Méta-header Id + Active (via W) ──────────────────────
        _W.meta_bar(comp, self._field_syncers, self._set_comp, self._editor_layout)
        _W.separator(self._editor_layout, margin_v=2)

        from ui.scene_manager.inspectors.component_editors import get_editor
        type_name = component_type_name(comp)
        EditorCls = get_editor(type_name)
        if EditorCls:
            EditorCls(self).build(comp, row, self._editor_layout)
        else:
            lbl = QLabel(f"{type_name} — pas d'éditeur enregistré")
            lbl.setFont(QFont(T.MONO, T.SM)); lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            self._editor_layout.addWidget(lbl)

    def _set_comp(self, comp, field, value):
        if self._blocking or not self._actor: return
        old = getattr(comp, field, None)
        if old == value:
            return
        comp_id = getattr(comp, "id", "?")
        get_history().push(SetFieldCmd(
            comp, field, old, value,
            label=f"{self._actor.name}.{comp_id}.{field}",
            persist_fn=lambda c=comp: self._save_component_change(c),
        ))
        # Syncer les autres widgets du même comp sans rebuild (ex: label liste)
        self._refresh_list_labels()
        self.changed.emit()
