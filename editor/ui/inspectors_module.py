"""Inspectors : SceneInspector, ActorInspector, BackgroundInspector,
               PrefabUsesInspector, DynamicInspector."""

import os
import re
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QFrame, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QListWidget, QListWidgetItem,
    QStackedWidget, QMenu, QFileDialog, QInputDialog, QScrollArea, QComboBox, QSizePolicy,
)
from PyQt6.QtGui import QFont, QCursor, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.project import (
    Project, Scene, Actor, Background, Tileset, SpriteAsset,
    COMPONENT_REGISTRY, component_type_name, MIME_SCRIPT,
)
from core.asset_manager import AssignSlot, BgLayerRow
from core.history import get_history, SetFieldCmd, AddComponentCmd, RemoveComponentCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from ui.theme import C, T, QSS
from ui.widgets import W

COMPONENT_LABELS = {
    "sprite":        "Sprite",
    "collision_box": "Collision",
    "sound_fx":      "SoundFX",
    "script":        "Script",
    "path":          "Path",
}

def _comp_label(comp) -> str:
    """Nom lisible d'une instance de component (pour les templates de script)."""
    from core.project import component_type_name
    type_name = component_type_name(comp)
    base = COMPONENT_LABELS.get(type_name, type_name)
    tag = getattr(comp, "tag", None)
    return f"{base}({tag})" if tag and tag != "body" else base

# ── Tooltips Lua mirror ───────────────────────────────────────────
_TOOLTIPS = {
    "actor.name":        ("self.name  (lecture seule)",
                          "Nom de l'actor dans l'éditeur.\nAccessible en Lua en lecture : self.name\n"
                          "Le tag C (TAG_Hero) est l'index réel dans g_actors[]."),
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
    "actor.flip_h":      ("self.flip_h  (lecture seule)",
                          "Retournement horizontal du sprite.\n"
                          "GBA : bit OAM attribute 1, bit 12."),
    "actor.flip_v":      ("self.flip_v  (lecture seule)",
                          "Retournement vertical du sprite.\n"
                          "GBA : bit OAM attribute 1, bit 13."),
    "actor.priority":    ("self.priority  (lecture seule)",
                          "Ordre d'affichage sur les BG layers.\n"
                          "0 = devant tous les backgrounds,  3 = derrière tous.\n"
                          "GBA : OAM attribute 2, bits 10–11."),
    "actor.pal_bank":    ("self.pal_bank  (lecture seule)",
                          "Banque de palette couleurs (0–15).\n"
                          "Chaque banque contient 16 couleurs 15-bit.\n"
                          "GBA : OAM attribute 2, bits 12–15 (mode 16c)."),
    "actor.visible":     ("self:set_visible(true/false)",
                          "Masque l'actor sans le désactiver.\n"
                          "Le slot OAM reste réservé mais avec bit OBJ_DISABLE."),
    "sprite.state":      ("self:play_anim('NomEtat')",
                          "Animation jouée au démarrage de la scène.\n"
                          "Lua : self:play_anim('Run')  change l'anim en cours."),
    "collision.solid":   ("self.collision.solid",
                          "true  → résolution physique : l'actor est repoussé au contact.\n"
                          "false → trigger : détecte l'overlap sans bloquer le mouvement.\n"
                          "Un trigger déclenche onTriggerEnter / onTriggerExit."),
    "collision.tag":     ("self.collision.tag",
                          "Label libre identifiant ce collider parmi plusieurs sur un même actor.\n"
                          "Ex : 'body', 'sword_hitbox', 'ground_check'.\n"
                          "Accessible dans les callbacks Lua via other.tag."),
    "collision.x":       ("self.collision.x",
                          "Décalage horizontal de la hitbox par rapport au pivot du sprite (px)."),
    "collision.y":       ("self.collision.y",
                          "Décalage vertical de la hitbox par rapport au pivot du sprite (px)."),
    "collision.w":       ("self.collision.width",
                          "Largeur de la hitbox en pixels. Tout est AABB côté C — pas de cercle."),
    "collision.h":       ("self.collision.height",
                          "Hauteur de la hitbox en pixels."),
    "collision.on_collision_enter": (
                          "function onCollisionEnter(other_id)",
                          "Fonction Lua appelée quand un actor SOLIDE entre en contact.\n"
                          "other_id = index de l'actor dans actors[] (table Lua de la scène)."),
    "collision.on_collision_exit":  (
                          "function onCollisionExit(other_id)",
                          "Fonction Lua appelée quand le contact avec un actor solide est rompu."),
    "collision.on_trigger_enter":   (
                          "function onTriggerEnter(other_id)",
                          "Fonction Lua appelée quand un actor entre dans la zone trigger.\n"
                          "Nécessite solid=false sur ce composant."),
    "collision.on_trigger_exit":    (
                          "function onTriggerExit(other_id)",
                          "Fonction Lua appelée quand un actor quitte la zone trigger."),
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

        from ui.widgets import W as _W

        # ── Position : X [ ]  Y [ ] ──────────────────────────────
        self._tx = _W.spinbox(0, min_v=-512, max_v=512)
        self._tx.valueChanged.connect(lambda v: self._set("x", v))
        _tip(self._tx, "actor.x")
        self._ty = _W.spinbox(0, min_v=-512, max_v=512)
        self._ty.valueChanged.connect(lambda v: self._set("y", v))
        _tip(self._ty, "actor.y")
        _W.pair("Position", "X", C.AXIS_X, self._tx, "Y", C.AXIS_Y, self._ty, tl,
                label_width=58)

        # ── Flip : □ H  □ V ──────────────────────────────────────
        flip_row = QHBoxLayout(); flip_row.setSpacing(12)
        flip_lbl = QLabel("Flip"); flip_lbl.setFont(QFont(T.MONO, T.MD))
        flip_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        flip_lbl.setFixedWidth(58)
        flip_row.addWidget(flip_lbl)
        self._tflip_h = QCheckBox("H")
        self._tflip_h.toggled.connect(lambda v: self._set("flip_h", v))
        _tip(self._tflip_h, "actor.flip_h")
        flip_row.addWidget(self._tflip_h)
        self._tflip_v = QCheckBox("V")
        self._tflip_v.toggled.connect(lambda v: self._set("flip_v", v))
        _tip(self._tflip_v, "actor.flip_v")
        flip_row.addWidget(self._tflip_v)
        flip_row.addStretch()
        tl.addLayout(flip_row)

        # ── Priority + Palette sur une même ligne ─────────────────
        self._tpriority = _W.spinbox(0, min_v=0, max_v=3)
        self._tpriority.valueChanged.connect(lambda v: self._set("priority", v))
        _tip(self._tpriority, "actor.priority")
        self._tpal = _W.spinbox(0, min_v=0, max_v=15)
        self._tpal.valueChanged.connect(lambda v: self._set("pal_bank", v))
        _tip(self._tpal, "actor.pal_bank")

        pp_container = QWidget(); pp_container.setStyleSheet("background:transparent;")
        pp_row = QHBoxLayout(pp_container); pp_row.setSpacing(8); pp_row.setContentsMargins(0, 2, 0, 2)
        _lbl_sty = f"color:{C.TEXT_DIM}; font-family:{T.MONO}; font-size:{T.MD}px; background:transparent; border:none;"
        pri_lbl = QLabel("Priority"); pri_lbl.setFont(QFont(T.MONO, T.MD))
        pri_lbl.setStyleSheet(_lbl_sty); pri_lbl.setFixedWidth(58)
        pal_lbl = QLabel("Palette");  pal_lbl.setFont(QFont(T.MONO, T.MD))
        pal_lbl.setStyleSheet(_lbl_sty); pal_lbl.setFixedWidth(52)
        pp_row.addWidget(pri_lbl); pp_row.addWidget(self._tpriority, 1)
        pp_row.addWidget(pal_lbl); pp_row.addWidget(self._tpal, 1)
        tl.addWidget(pp_container)

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
        _toggle_style = (
            "QToolButton{{color:{{c}};border:none;background:{bg};"
            "font-family:monospace;font-size:8pt;font-weight:bold;"
            "text-align:left;padding:4px 8px;letter-spacing:1px;}}"
            "QToolButton:hover{{background:{bgh};}}"
        ).format(bg=C.BG_PANEL, bgh=C.BG_HOVER)
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

    # Couleurs de contexte (cohérentes avec project_panel et InspectorPanel)
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
        self._tflip_h.setChecked(actor.flip_h); self._tflip_v.setChecked(actor.flip_v)
        self._tpriority.setValue(actor.priority); self._tpal.setValue(actor.pal_bank)
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
        if not state or not state.frames:
            return
        frame = state.frames[0]
        px = QPixmap(str(asset_path))
        if px.isNull():
            return
        x = frame.col * sprite.frame_w
        y = frame.row * sprite.frame_h
        cropped = px.copy(x, y, sprite.frame_w, sprite.frame_h)
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

        from PyQt6.QtWidgets import QMenu
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
        from core.project import SpriteAsset, Tileset
        sprite = self._project.get_sprite(sprite_name)
        if not sprite:
            dst = self._project.import_asset(png_path, "sprites")
            sprite = SpriteAsset(
                name=sprite_name,
                asset=self._project.asset_rel(dst),
            )
            self._project.sprites.append(sprite)
            with __import__("contextlib").suppress(Exception):
                self._project.save_sprite(sprite)

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
            self._comp_list.setCurrentRow(row)
            self._build_editor(self._actor.components[row])
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
        for type_name, label in COMPONENT_LABELS.items():
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

        from ui.widgets import W as _W

        def row(label, widget):
            return _W.row(label, widget, self._editor_layout)

        # ── Méta-header Id + Active (via W) ──────────────────────
        _W.meta_bar(comp, self._field_syncers, self._set_comp, self._editor_layout)
        _W.separator(self._editor_layout, margin_v=2)

        from ui.inspectors.component_editors import get_editor
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



# ──────────────────────────────────────────────────────────────────
#  BackgroundInspector
# ──────────────────────────────────────────────────────────────────
class BackgroundInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg: Optional[Background] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._empty = QLabel("Selectionne un background\ndans le panneau gauche")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        self._name = QLineEdit()
        self._name.setFont(QFont(T.MONO, T.MD))
        self._name.setStyleSheet(
            f"background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER};border-radius:3px;padding:3px;"
        )
        self._name.editingFinished.connect(self._rename_background)
        W.row("Nom", self._name, cl, label_width=80)

        arow = QHBoxLayout()
        self._asset_lbl = QLabel("Aucun")
        self._asset_lbl.setFont(QFont(T.MONO, T.SM)); self._asset_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        btn = QPushButton("Choisir…"); btn.setFont(QFont(T.MONO, T.SM))
        btn.clicked.connect(self._pick_asset)
        arow.addWidget(self._asset_lbl, 1); arow.addWidget(btn)
        aw = QWidget(); aw.setLayout(arow)
        W.row("PNG", aw, cl, label_width=80)

        self._speed = QSpinBox(); self._speed.setRange(0, 999)
        self._speed.setFont(QFont(T.MONO, T.MD))
        self._speed.setStyleSheet(
            f"background:{C.BG_INPUT};color:{C.TEXT_NORM};border:1px solid {C.BORDER};border-radius:3px;"
        )
        self._speed.valueChanged.connect(lambda v: self._set("scroll_speed", v / 100.0))
        W.row("Scroll x100", self._speed, cl, label_width=80)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def load(self, bg: Background, project: Project):
        self._bg = bg; self._project = project
        if not bg:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._name.setText(bg.name)
        self._speed.setValue(int(bg.scroll_speed * 100))
        tileset = project.get_tileset(bg.tileset_name) if bg.tileset_name else None
        ap = project.asset_abs(tileset.asset) if tileset else None
        self._asset_lbl.setText(ap.name if ap else "Aucun")
        self._blocking = False

    def _set(self, field, value):
        if self._blocking or not self._bg: return
        setattr(self._bg, field, value); self.changed.emit()

    def _rename_background(self):
        if self._blocking or not self._bg: return
        self._project.rename_background(self._bg, self._name.text())
        self._name.setText(self._bg.name); self.changed.emit()

    def _ensure_tileset(self) -> Tileset:
        tileset = self._project.get_tileset(self._bg.tileset_name) if self._bg.tileset_name else None
        if not tileset:
            tileset = Tileset(name=f"{self._bg.name}_tileset")
            self._project.tilesets.append(tileset)
            self._bg.tileset_name = tileset.name
            self._project.save_background(self._bg)
        return tileset

    def _pick_asset(self):
        if not self._project or not self._bg: return
        path, _ = QFileDialog.getOpenFileName(
            self, "Background PNG",
            str(self._project.assets_dir / "backgrounds"), "Images (*.png *.bmp)"
        )
        if path:
            dst = self._project.import_asset(Path(path), "backgrounds")
            tileset = self._ensure_tileset()
            tileset.asset = self._project.asset_rel(dst)
            self._project.save_tileset(tileset)
            self._asset_lbl.setText(dst.name)
            self.changed.emit()


# ──────────────────────────────────────────────────────────────────
#  SceneInspector
# ──────────────────────────────────────────────────────────────────
class SceneInspector(QWidget):
    changed = pyqtSignal()
    slot_assigned = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel("Selectionne une scene")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def _card(accent: str) -> tuple:
            """Retourne (card QFrame, inner_layout QVBoxLayout)."""
            f = QFrame()
            f.setStyleSheet(
                f"QFrame#sc_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
                f"border-left:3px solid {accent};border-radius:4px;}}"
                f"QFrame#sc_card QFrame{{background:transparent;border:none;}}"
                f"QFrame#sc_card QLabel{{background:transparent;border:none;}}"
            )
            f.setObjectName("sc_card")
            inner = QVBoxLayout(f)
            inner.setContentsMargins(8, 6, 8, 8)
            inner.setSpacing(6)
            return f, inner

        def _card_title(text: str, accent: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
            lbl.setStyleSheet(
                f"color:{accent};letter-spacing:1px;"
                f"border-bottom:1px solid {C.BORDER};padding-bottom:4px;"
            )
            return lbl

        # ── Carte BG Layers ───────────────────────────────────────
        bg_card, bg_inner = _card(C.ACCENT_BLU)

        bg_hdr = QHBoxLayout(); bg_hdr.setContentsMargins(0, 0, 0, 0); bg_hdr.setSpacing(4)
        bg_hdr.addWidget(_card_title("BG LAYERS", C.ACCENT_BLU), 1)
        self._btn_bg_add = W.btn_add("Ajouter un calque BG (max 4)")
        self._btn_bg_add.clicked.connect(self._add_bg_layer)
        bg_hdr.addWidget(self._btn_bg_add)
        bg_inner.addLayout(bg_hdr)

        self._bg_rows: list[BgLayerRow] = []
        for i in range(4):
            row = BgLayerRow(i)
            row.asset_changed.connect(self._on_bg_slot)
            row.speed_changed.connect(self._on_speed_changed)
            row.bound_toggled.connect(self._on_bound_toggled)
            row.layer_removed.connect(self._on_layer_removed)
            row.setVisible(False)
            bg_inner.addWidget(row)
            self._bg_rows.append(row)

        cl.addWidget(bg_card)

        # ── Carte Paramètres ──────────────────────────────────────
        param_card, param_inner = _card(C.TEXT_DIM)
        param_inner.addWidget(_card_title("PARAMÈTRES", C.TEXT_NORM))

        ui_row = QHBoxLayout(); ui_row.setSpacing(6)
        lbl_ui = QLabel("Layer UI :")
        lbl_ui.setFont(QFont(T.MONO, T.SM)); lbl_ui.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_ui.setFixedWidth(70)
        self._combo_text_bg = QComboBox()
        self._combo_text_bg.setFont(QFont(T.MONO, T.SM))
        self._combo_text_bg.setStyleSheet(QSS.combobox)
        for i in range(4):
            self._combo_text_bg.addItem(f"BG{i}" + (" (défaut)" if i == 1 else ""), i)
        self._combo_text_bg.currentIndexChanged.connect(self._on_text_bg_changed)
        self._combo_text_bg.setToolTip(
            "<b>Calque réservé au texte HUD (TTE)</b><br><br>"
            "Le texte affiché en jeu (score, dialogue…) occupe un calque BG entier.<br>"
            "Choisir un BG qui n'est pas utilisé par un décor.<br><br>"
            "<b>Conflit ⚠</b> : si ce BG est déjà assigné à un background,<br>"
            "les deux se superposent et le résultat est indéfini."
        )
        self._lbl_text_bg_warn = QLabel("")
        self._lbl_text_bg_warn.setFont(QFont(T.MONO, T.XS))
        self._lbl_text_bg_warn.setStyleSheet(f"color:{C.ACCENT_YLW};")
        ui_row.addWidget(lbl_ui)
        ui_row.addWidget(self._combo_text_bg)
        ui_row.addWidget(self._lbl_text_bg_warn, 1)
        param_inner.addLayout(ui_row)

        scroll_row = QHBoxLayout(); scroll_row.setSpacing(6)
        lbl_scroll = QLabel("Scrolling :")
        lbl_scroll.setFont(QFont(T.MONO, T.SM)); lbl_scroll.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_scroll.setFixedWidth(70)
        self._chk_scroll_h = QCheckBox("Horizontal")
        self._chk_scroll_v = QCheckBox("Vertical")
        for chk in (self._chk_scroll_h, self._chk_scroll_v):
            chk.setFont(QFont(T.MONO, T.SM))
            chk.setStyleSheet(QSS.checkbox)
            scroll_row.addWidget(chk)
        scroll_row.insertWidget(0, lbl_scroll)
        scroll_row.addStretch()
        self._chk_scroll_h.toggled.connect(self._on_scroll_changed)
        self._chk_scroll_v.toggled.connect(self._on_scroll_changed)
        param_inner.addLayout(scroll_row)

        cl.addWidget(param_card)

        # ── Carte Script ──────────────────────────────────────────
        sc_card, sc_inner = _card(C.ACCENT_ORG)
        sc_inner.addWidget(_card_title("SCRIPT", C.ACCENT_ORG))

        from ui.widgets import ScriptSlot, ScriptPickerPopup  # noqa: F401 (ScriptPickerPopup used later)
        self._scene_script_slot = ScriptSlot(
            add_label    = "Ajouter un script de scène",
            accent_color = C.ACCENT_ORG,
            hint         = "on_start · on_update · on_late_update",
        )
        self._scene_script_slot.set_callbacks(
            on_add   = self._scene_script_new,
            on_open  = self._scene_script_open,
            on_clear = self._scene_script_clear,
        )
        sc_inner.addWidget(self._scene_script_slot)

        cl.addWidget(sc_card)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def load(self, scene: Scene, project: Project):
        self._scene = scene; self._project = project
        if not scene:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._chk_scroll_h.setChecked(scene.scroll_h)
        self._chk_scroll_v.setChecked(scene.scroll_v)
        self._refresh_scroll_speeds()
        text_bg = getattr(scene, "text_bg", 3)
        self._combo_text_bg.setCurrentIndex(text_bg)
        self._refresh_text_bg_warn()
        self._refresh_scene_script_label()
        active_count = 0
        text_bg = getattr(scene, "text_bg", -1)
        for i, row in enumerate(self._bg_rows):
            layer = scene.bg_layers[i] if i < len(scene.bg_layers) else None
            if layer:
                row.set_speed(layer.scroll_speed)
            bg_name = layer.background_name if layer else ""
            bg = project.get_background(bg_name) if bg_name else None
            tileset = project.get_tileset(bg.tileset_name) if bg and bg.tileset_name else None
            has_asset = False
            if tileset:
                ap = project.asset_abs(tileset.asset)
                if ap and ap.exists():
                    row.set_asset(str(ap))
                    has_asset = True
            if not has_asset:
                row.clear_asset()
            is_ui = (i == text_bg)
            row.set_ui_layer(is_ui)
            visible = has_asset or is_ui or i < active_count or i == 0
            row.setVisible(visible)
            if visible:
                active_count = i + 1
        collision_layer = getattr(scene, "collision_layer", 0)
        for i, row in enumerate(self._bg_rows):
            row.set_bound(i == collision_layer)
        self._btn_bg_add.setEnabled(active_count < 4)
        self._blocking = False

    def _on_bound_toggled(self, idx: int):
        if self._blocking or not self._scene: return
        self._scene.collision_layer = idx
        for i, row in enumerate(self._bg_rows):
            row.set_bound(i == idx)
        self.changed.emit()

    def _on_layer_removed(self, idx: int):
        if not self._scene: return
        self._bg_rows[idx].setVisible(False)
        self._bg_rows[idx].clear_asset()
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().assign_bg_slot(idx, "")
        self._btn_bg_add.setEnabled(True)
        # Si ce layer était le layer de collision, réassigner au premier visible
        if self._scene.collision_layer == idx:
            for i, row in enumerate(self._bg_rows):
                if row.isVisible():
                    self._on_bound_toggled(i)
                    break

    def _add_bg_layer(self):
        for row in self._bg_rows:
            if not row.isVisible():
                row.setVisible(True)
                self._btn_bg_add.setEnabled(
                    any(not r.isVisible() for r in self._bg_rows)
                )
                return

    def _refresh_scroll_speeds(self):
        show_h = self._chk_scroll_h.isChecked()
        show_v = self._chk_scroll_v.isChecked()
        for row in self._bg_rows:
            row.set_speed_visible(show_h or show_v)

    def _on_scroll_changed(self):
        if self._blocking or not self._scene: return
        self._scene.scroll_h = self._chk_scroll_h.isChecked()
        self._scene.scroll_v = self._chk_scroll_v.isChecked()
        self._refresh_scroll_speeds()
        self.changed.emit()

    def _on_text_bg_changed(self):
        if self._blocking or not self._scene: return
        self._scene.text_bg = self._combo_text_bg.currentData()
        self._refresh_text_bg_warn()
        self.changed.emit()

    def _refresh_text_bg_warn(self):
        if not self._scene: return
        text_bg = getattr(self._scene, "text_bg", -1)
        conflict = any(
            L.bg == text_bg and L.background_name
            for L in self._scene.bg_layers
        )
        self._lbl_text_bg_warn.setText("⚠ conflit avec background" if conflict else "")
        for i, row in enumerate(self._bg_rows):
            row.set_ui_layer(i == text_bg)

    # ── Script de scène — helpers ──────────────────────────────────

    def _refresh_scene_script_label(self):
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc and self._project else None
        if sp and sp.exists():
            self._scene_script_slot.set_script(sp.name)
        else:
            self._scene_script_slot.clear_script()

    def _scene_script_new(self):
        """Ouvre le picker : liste des scripts de scène + bouton Nouveau."""
        if not self._scene or not self._project: return
        from ui.widgets import ScriptPickerPopup

        # Collecter les scripts de scène existants
        scenes_dir = self._project.scripts_scenes_dir
        scripts: list[tuple[str, str]] = []
        if scenes_dir.exists():
            for f in sorted(scenes_dir.glob("*.lua")):
                rel = str(f.relative_to(self._project.root)).replace("\\", "/")
                scripts.append((f.name, rel))

        popup = ScriptPickerPopup(scripts, C.ACCENT_ORG, parent=self)
        popup.picked.connect(self._scene_script_assign)
        popup.new_requested.connect(self._scene_script_create_new)
        popup.show_below(self._scene_script_slot)

    def _scene_script_assign(self, rel: str):
        """Assigne un script existant à la scène."""
        if not self._scene: return
        self._scene.script = rel
        self._refresh_scene_script_label()
        self.changed.emit()

    def _scene_script_create_new(self):
        """Dialogue de création d'un nouveau script de scène."""
        if not self._scene or not self._project: return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nouveau script de scène", "Nom (sans .lua) :")
        if not ok or not name.strip(): return
        d = self._project.scripts_scenes_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            sp.write_text(
                "-- Script de scène : " + self._scene.name + "\n\n"
                "function on_start()\nend\n\n"
                "function on_update()\nend\n\n"
                "function on_late_update()\nend\n",
                encoding="utf-8"
            )
        rel = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._scene.script = rel
        self._refresh_scene_script_label()
        self.changed.emit()
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_open(self):
        if not self._scene or not self._project: return
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc else None
        if sp and sp.exists() and hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_clear(self):
        if not self._scene: return
        self._scene.script = ""
        self._refresh_scene_script_label()
        self.changed.emit()

    def _on_speed_changed(self, idx: int, value: float):
        if self._blocking or not self._scene: return
        if idx >= len(self._scene.bg_layers): return
        layer = self._scene.bg_layers[idx]
        old_val = layer.scroll_speed
        get_history().push(SetFieldCmd(
            layer, "scroll_speed", old_val, value,
            f"BG{idx} vitesse",
            persist_fn=self.changed.emit,
        ))

    def _on_bg_slot(self, slot_index: int, path_str: str):
        self.slot_assigned.emit(slot_index, path_str)

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn


# ──────────────────────────────────────────────────────────────────
#  CameraInspector
# ──────────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────────
#  PrefabUsesInspector — liste des instances d'un prefab par scène
# ──────────────────────────────────────────────────────────────────
class PrefabUsesInspector(QWidget):
    """
    Vue 'PREFAB USES' affichée dans l'inspector quand on clique
    'Voir les instances' dans le panneau projet.

    Structure :
        ┌─ Header bleu : nom du prefab  ────────── [v] ─┐
        │  PREFAB USES              [Éditer le prefab]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        │      · Actor 2                                │
        │  ▸ Scene B                                    │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(object)   # Prefab — demande d'édition

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefab  = None
        self._project = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bleu avec nom du prefab ────────────────────────
        self._top = QFrame()
        self._top.setFixedHeight(40)
        self._top.setStyleSheet(f"background:{C.ACCENT_BLU}30; border-bottom:1px solid {C.ACCENT_BLU}50;")
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(12, 0, 8, 0)
        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.MONO, T.LG, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        btn_close = QPushButton("v")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT_BLU};background:transparent;border:none;"
            "font-family:monospace;font-size:10px;}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_close.setToolTip("Fermer cette vue")
        btn_close.clicked.connect(self._on_close)
        tl.addWidget(self._name_lbl, 1)
        tl.addWidget(btn_close)
        root.addWidget(self._top)

        # ── Barre de section ──────────────────────────────────────
        sec_bar = QFrame()
        sec_bar.setFixedHeight(28)
        sec_bar.setStyleSheet(f"background:{C.BG_DEEP}; border-bottom:1px solid {C.BORDER_DARK};")
        sl = QHBoxLayout(sec_bar)
        sl.setContentsMargins(10, 0, 8, 0)
        sec_lbl = QLabel("PREFAB USES")
        sec_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        sec_lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; letter-spacing:1px;")
        self._edit_btn = QPushButton("Éditer le prefab")
        self._edit_btn.setFont(QFont(T.MONO, T.SM))
        self._edit_btn.setFixedHeight(20)
        self._edit_btn.setStyleSheet(
            "QPushButton{color:#7ecfff;background:transparent;border:none;"
            "font-family:monospace;font-size:8px;}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        self._edit_btn.clicked.connect(self._on_edit)
        sl.addWidget(sec_lbl, 1)
        sl.addWidget(self._edit_btn)
        root.addWidget(sec_bar)

        # ── Liste des utilisations ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{C.BG_PANEL};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

    # ── Chargement ────────────────────────────────────────────────

    def load(self, prefab, project):
        from core.project import Prefab
        self._prefab  = prefab
        self._project = project
        self._name_lbl.setText(prefab.name)

        # Vider la liste
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Parcourir toutes les scènes pour trouver les instances liées
        found_any = False
        for scene in project.scenes:
            linked = [a for a in scene.actors if a.prefab_name == prefab.name]
            if not linked:
                continue
            found_any = True

            # Ligne scène
            scene_row = QFrame()
            scene_row.setFixedHeight(24)
            scene_row.setStyleSheet(f"background:{C.BG_RAISED};")
            sl = QHBoxLayout(scene_row)
            sl.setContentsMargins(10, 0, 8, 0)
            scene_icon = QLabel("◈")
            scene_icon.setFont(QFont(T.MONO, T.MD))
            scene_icon.setStyleSheet("color:#7ecfff;")
            scene_icon.setFixedWidth(16)
            scene_name = QLabel(scene.name)
            scene_name.setFont(QFont(T.MONO, T.MD))
            scene_name.setStyleSheet("color:#7ecfff;")
            count_lbl = QLabel(f"×{len(linked)}")
            count_lbl.setFont(QFont(T.MONO, T.SM))
            count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            sl.addWidget(scene_icon)
            sl.addWidget(scene_name, 1)
            sl.addWidget(count_lbl)
            self._list_layout.addWidget(scene_row)

            # Lignes acteurs
            for actor in linked:
                actor_row = QFrame()
                actor_row.setFixedHeight(22)
                actor_row.setStyleSheet(f"background:{C.BG_PANEL};")
                actor_row.setCursor(Qt.CursorShape.PointingHandCursor)
                al = QHBoxLayout(actor_row)
                al.setContentsMargins(28, 0, 8, 0)
                icon_lbl = QLabel("·")
                icon_lbl.setFont(QFont(T.MONO, T.MD2))
                icon_lbl.setStyleSheet(f"color:{C.BORDER_MID};")
                icon_lbl.setFixedWidth(12)
                name_lbl = QLabel(actor.name)
                name_lbl.setFont(QFont(T.MONO, T.MD))
                name_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
                al.addWidget(icon_lbl)
                al.addWidget(name_lbl, 1)
                self._list_layout.addWidget(actor_row)

                # Clic → sélectionner l'actor dans la scène active
                from core.selection_bus import get_bus
                actor_row.mousePressEvent = (
                    lambda e, a=actor: get_bus().select(a)
                )

        if not found_any:
            empty = QLabel("  Aucune instance dans le projet.")
            empty.setFont(QFont(T.MONO, T.MD))
            empty.setStyleSheet("color:#444; padding:12px;")
            self._list_layout.addWidget(empty)

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_edit(self):
        if self._prefab:
            self.edit_requested.emit(self._prefab)

    def _on_close(self):
        """Renvoie à la vue précédente via le bus (re-sélectionne le prefab)."""
        if self._prefab:
            from core.selection_bus import get_bus
            get_bus().select(self._prefab)


# ──────────────────────────────────────────────────────────────────
#  ScriptUsesInspector — liste des actors qui utilisent un script
# ──────────────────────────────────────────────────────────────────
class ScriptUsesInspector(QWidget):
    """
    Vue 'SCRIPT USES' — affiche toutes les scènes et actors
    qui ont un ScriptComponent pointant vers ce fichier script.

    Structure :
        ┌─ Header orange : nom du script  ──────── [v] ─┐
        │  SCRIPT USES              [Éditer le script]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(str)   # path du script

    def __init__(self, parent=None):
        super().__init__(parent)
        self._script_path = None
        self._project     = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header orange avec nom du script ──────────────────────
        self._top = QFrame()
        self._top.setFixedHeight(40)
        self._top.setStyleSheet(f"background:{C.ACCENT_ORG}25; border-bottom:1px solid {C.ACCENT_ORG}40;")
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(12, 0, 8, 0)
        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.MONO, T.LG, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        btn_close = QPushButton("v")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT_ORG};background:transparent;border:none;"
            "font-family:monospace;font-size:10px;}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_close.setToolTip("Fermer cette vue")
        btn_close.clicked.connect(self._on_close)
        tl.addWidget(self._name_lbl, 1)
        tl.addWidget(btn_close)
        root.addWidget(self._top)

        # ── Barre de section ──────────────────────────────────────
        sec_bar = QFrame()
        sec_bar.setFixedHeight(28)
        sec_bar.setStyleSheet(f"background:{C.BG_DEEP}; border-bottom:1px solid {C.BORDER_DARK};")
        sl = QHBoxLayout(sec_bar)
        sl.setContentsMargins(10, 0, 8, 0)
        sec_lbl = QLabel("SCRIPT USES")
        sec_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        sec_lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; letter-spacing:1px;")
        self._edit_btn = QPushButton("Éditer le script")
        self._edit_btn.setFont(QFont(T.MONO, T.SM))
        self._edit_btn.setFixedHeight(20)
        self._edit_btn.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT_ORG};background:transparent;border:none;"
            "font-family:monospace;font-size:8px;}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        self._edit_btn.clicked.connect(self._on_edit)
        sl.addWidget(sec_lbl, 1)
        sl.addWidget(self._edit_btn)
        root.addWidget(sec_bar)

        # ── Liste des utilisations ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{C.BG_PANEL};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

    # ── Chargement ────────────────────────────────────────────────

    def load(self, script_path: str, project):
        self._script_path = script_path
        self._project     = project

        from pathlib import Path as _Path
        name = _Path(script_path).name
        self._name_lbl.setText(name)

        # Vider la liste
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Parcourir toutes les scènes
        found_any = False
        for scene in project.scenes:
            linked = [
                a for a in scene.actors
                if a.get_component("script") is not None
                and _Path(a.get_component("script").script or "").name == name
            ]
            if not linked:
                continue
            found_any = True

            # Ligne scène
            scene_row = QFrame()
            scene_row.setFixedHeight(24)
            scene_row.setStyleSheet(f"background:{C.BG_RAISED};")
            sl = QHBoxLayout(scene_row)
            sl.setContentsMargins(10, 0, 8, 0)
            scene_icon = QLabel("✦")
            scene_icon.setFont(QFont(T.MONO, T.MD))
            scene_icon.setStyleSheet(f"color:{C.ACCENT_ORG};")
            scene_icon.setFixedWidth(16)
            scene_name = QLabel(scene.name)
            scene_name.setFont(QFont(T.MONO, T.MD))
            scene_name.setStyleSheet(f"color:{C.ACCENT_ORG};")
            count_lbl = QLabel(f"×{len(linked)}")
            count_lbl.setFont(QFont(T.MONO, T.SM))
            count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            sl.addWidget(scene_icon)
            sl.addWidget(scene_name, 1)
            sl.addWidget(count_lbl)
            self._list_layout.addWidget(scene_row)

            # Lignes acteurs
            for actor in linked:
                actor_row = QFrame()
                actor_row.setFixedHeight(22)
                actor_row.setStyleSheet(f"background:{C.BG_PANEL};")
                actor_row.setCursor(Qt.CursorShape.PointingHandCursor)
                al = QHBoxLayout(actor_row)
                al.setContentsMargins(28, 0, 8, 0)
                icon_lbl = QLabel("·")
                icon_lbl.setFont(QFont(T.MONO, T.MD2))
                icon_lbl.setStyleSheet(f"color:{C.BORDER_MID};")
                icon_lbl.setFixedWidth(12)
                name_lbl = QLabel(actor.name)
                name_lbl.setFont(QFont(T.MONO, T.MD))
                name_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
                al.addWidget(icon_lbl)
                al.addWidget(name_lbl, 1)
                self._list_layout.addWidget(actor_row)

                from core.selection_bus import get_bus
                actor_row.mousePressEvent = (
                    lambda e, a=actor: get_bus().select(a)
                )

        if not found_any:
            empty = QLabel("  Aucun actor n'utilise ce script.")
            empty.setFont(QFont(T.MONO, T.MD))
            empty.setStyleSheet("color:#444; padding:12px;")
            self._list_layout.addWidget(empty)

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_edit(self):
        if self._script_path:
            self.edit_requested.emit(self._script_path)

    def _on_close(self):
        """Ferme la vue — revient à l'état vide."""
        from core.selection_bus import get_bus
        get_bus().clear()


# ──────────────────────────────────────────────────────────────────
#  DynamicInspector — remplace le QTabWidget Scene/Actor
# ──────────────────────────────────────────────────────────────────
class DynamicInspector(QWidget):
    """
    Inspector contextuel sans onglets.
    Affiche automatiquement le bon panneau selon la selection :
      - rien        → message d'aide
      - scene       → SceneInspector (nom + BG slots)
      - actor       → ActorInspector (transform + components)
      - prefab      → ActorInspector (components seulement)
      - prefab uses → PrefabUsesInspector
    """
    changed       = pyqtSignal()
    actor_changed = pyqtSignal(object)   # Actor | None — payload propre pour window.py
    slot_assigned = pyqtSignal(int, str)

    _MODE_EMPTY       = 0
    _MODE_SCENE       = 1
    _MODE_ACTOR       = 2
    _MODE_CAMERA      = 3
    _MODE_PREFAB_USES = 4
    _MODE_SCRIPT_USES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None   # mis à jour via set_project()
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self.setMinimumWidth(200)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Bandeau contextuel coloré
        self._header = QFrame()
        self._header.setFixedHeight(44)
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(12, 0, 12, 0); hl.setSpacing(0)

        self._header_type_lbl = QLabel("")
        self._header_type_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))

        self._header_name_edit = QLineEdit("")
        self._header_name_edit.setFont(QFont(T.MONO, T.XXL, QFont.Weight.Bold))
        self._header_name_edit.setFrame(False)
        self._header_name_edit.setReadOnly(True)
        self._header_name_edit.editingFinished.connect(self._on_header_rename)
        self._header_mode = "empty"

        name_col = QVBoxLayout(); name_col.setSpacing(1)
        name_col.addWidget(self._header_type_lbl)
        name_col.addWidget(self._header_name_edit)
        hl.addLayout(name_col, 1)
        main.addWidget(self._header)

        # Palette (bg, type-label, name-label) — cohérente avec project_panel.py
        #   vert    #4caf78  → Actor
        #   violet  #b48aff  → Scene / Caméra / Instances
        #   bleu    #7ecfff  → Prefab
        #   orange  #c48b3c  → Script
        self._HEADER_COLORS = {
            "actor":  ("#0d1f12", "#3a7a50", "#a8e6bf"),   # vert
            "scene":  ("#170f2a", "#6a4a9a", "#d4aaff"),   # violet
            "camera": ("#170f2a", "#6a4a9a", "#d4aaff"),   # violet
            "prefab": ("#0a1a2a", "#3a6a8a", "#b3e5fc"),   # bleu
            "uses":   ("#170f2a", "#6a4a9a", "#d4aaff"),   # violet
            "script": ("#1a1500", "#8a5a20", "#f5c87a"),   # orange
            "empty":  ("#161616", "#333",    "#555"),
        }

        self._stack = QStackedWidget()
        main.addWidget(self._stack, 1)

        # 0 — vide
        empty_w = QWidget()
        empty_w.setStyleSheet(f"background:{C.BG_PANEL};")
        el = QVBoxLayout(empty_w)
        hint = QLabel("Selectionnez une scene\nou un actor pour\nafficher ses proprietes")
        hint.setFont(QFont(T.MONO, T.MD))
        hint.setStyleSheet(f"color:{C.BORDER_MID};")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addStretch(); el.addWidget(hint); el.addStretch()
        self._stack.addWidget(empty_w)

        # 1 — scene
        self._scene_insp = SceneInspector()
        self._scene_insp.changed.connect(self.changed)
        self._scene_insp.slot_assigned.connect(self.slot_assigned)
        self._stack.addWidget(self._scene_insp)

        # 2 — actor / prefab
        self._actor_insp = ActorInspector()
        self._actor_insp.changed.connect(self._on_actor_insp_changed)
        self._stack.addWidget(self._actor_insp)

        # 3 — caméra
        self._camera_insp = CameraInspector()
        self._camera_insp.changed.connect(self.changed)
        self._stack.addWidget(self._camera_insp)

        # 4 — prefab uses
        self._uses_insp = PrefabUsesInspector()
        self._uses_insp.edit_requested.connect(
            lambda p: self.show_prefab(p, self._project))
        self._stack.addWidget(self._uses_insp)

        # 5 — script uses
        self._script_uses_insp = ScriptUsesInspector()
        self._script_uses_insp.edit_requested.connect(self._on_script_edit_requested)
        self._stack.addWidget(self._script_uses_insp)

        self._stack.setCurrentIndex(self._MODE_EMPTY)

        from core.selection_bus import get_bus
        get_bus().changed.connect(self.on_selection)

    def _on_actor_insp_changed(self):
        """Relaye changed ET émet actor_changed(actor) avec le payload explicite."""
        self.changed.emit()
        self.actor_changed.emit(self._actor_insp._actor)

    # ── Helpers header ───────────────────────────────────────────

    def _set_header(self, kind: str, type_text: str, name_text: str):
        bg, tc, nc = self._HEADER_COLORS.get(kind, self._HEADER_COLORS["empty"])
        self._header.setStyleSheet(f"background:{bg};")
        self._header_type_lbl.setStyleSheet(f"color:{tc}; font-size:8pt; font-weight:bold;")
        editable = kind in ("scene", "actor", "prefab")
        self._header_name_edit.setStyleSheet(
            f"background:transparent; color:{nc}; font-size:13pt; font-weight:bold;"
            f"border:none; border-bottom:1px solid {'rgba(255,255,255,30)' if editable else 'transparent'};"
            f"padding:0;"
        )
        self._header_name_edit.setReadOnly(not editable)
        self._header_name_edit.setCursor(
            Qt.CursorShape.IBeamCursor if editable else Qt.CursorShape.ArrowCursor
        )
        self._header_type_lbl.setText(type_text)
        self._header_name_edit.setText(name_text)
        self._header_mode = kind

    def _on_header_rename(self):
        new_name = self._header_name_edit.text().strip()
        if not new_name:
            return
        if self._header_mode == "scene":
            scene = self._scene_insp._scene
            project = self._scene_insp._project
            if scene and project and new_name != scene.name:
                project.rename_scene(scene, new_name)
                self._header_name_edit.setText(scene.name)
                self._scene_insp.changed.emit()
        elif self._header_mode in ("actor", "prefab"):
            actor = self._actor_insp._actor
            project = self._actor_insp._project
            if actor and new_name != actor.name:
                if self._actor_insp._is_prefab_template:
                    project.prefabs.rename(actor, new_name)
                else:
                    actor.name = new_name
                    self._actor_insp._persist()
                    from core.command_dispatcher import get_dispatcher
                    get_dispatcher()._emit("actors_list_changed")
                self._header_name_edit.setText(actor.name)

    # ── API publique ─────────────────────────────────────────────

    def set_project(self, project):
        """Appelé par MainWindow à chaque ouverture/changement de projet."""
        self._project = project

    def on_selection(self, obj):
        """Reçu du bus — afficher le bon panneau selon le type de l'objet."""
        from core.project import Actor, Scene, Prefab
        if obj is None:
            self.show_empty()
        elif isinstance(obj, Actor):
            scene = self._project.active_scene if self._project else None
            self.show_actor(obj, self._project, scene)
        elif isinstance(obj, Scene):
            # Sélection d'une scène via le canvas (caméra) → inspector caméra
            self.show_camera(obj, self._project)
        elif isinstance(obj, Prefab):
            self.show_prefab(obj, self._project)

    def show_empty(self):
        self._set_header("empty", "", "")
        self._stack.setCurrentIndex(self._MODE_EMPTY)

    def show_scene(self, scene, project):
        self._scene_insp.load(scene, project)
        self._set_header("scene", "SCÈNE", scene.name if scene else "")
        self._stack.setCurrentIndex(self._MODE_SCENE)
        # Sync si l'inspector SceneInspector émet changed après un rename interne
        self._scene_insp.changed.connect(
            lambda: self._header_name_edit.setText(
                self._scene_insp._scene.name if self._scene_insp._scene else ""
            )
        )

    def show_actor(self, actor, project, scene=None):
        self._actor_insp.load(actor, project, scene)
        self._set_header("actor", "ACTOR", actor.name if actor else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_prefab(self, prefab, project):
        self._actor_insp.load_prefab(prefab, project)
        self._set_header("prefab", "PREFAB", prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_ACTOR)

    def show_camera(self, scene, project):
        self._camera_insp.load(scene, project)
        self._set_header("camera", "CAMÉRA", "240 × 160")
        self._stack.setCurrentIndex(self._MODE_CAMERA)

    def show_prefab_uses(self, prefab, project=None):
        proj = project or self._project
        if not proj:
            return
        self._uses_insp.load(prefab, proj)
        self._set_header("uses", "INSTANCES", prefab.name if prefab else "")
        self._stack.setCurrentIndex(self._MODE_PREFAB_USES)

    def show_script_uses(self, script_path: str, project=None):
        proj = project or self._project
        if not proj:
            return
        from pathlib import Path as _P
        self._script_uses_insp.load(script_path, proj)
        self._set_header("script", "SCRIPT", _P(script_path).name)
        self._stack.setCurrentIndex(self._MODE_SCRIPT_USES)

    def _on_script_edit_requested(self, path: str):
        """Ouvre le script dans l'éditeur — relayé par window.py via script_opened."""
        # On émet via un signal dédié ou on passe par le bus.
        # Ici on utilise directement l'import window pour éviter une dépendance circulaire :
        # c'est window.py qui connecte script_opened → open_script().
        # On stocke un callback optionnel.
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(path)

    def set_script_open_fn(self, fn):
        """Injecté par window.py pour ouvrir un script depuis la vue ScriptUses."""
        self._script_open_fn = fn
        self._actor_insp._script_open_fn = fn

    def update_actor_position(self, x: int, y: int):
        self._actor_insp.update_position(x, y)

    @property
    def actor_inspector(self) -> ActorInspector:
        return self._actor_insp
