"""SceneInspector — background layers, paramètres d'affichage, script de scène."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QScrollArea, QPushButton, QMessageBox, QMenu, QToolButton,
    QCheckBox, QSpinBox,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint

from core.models.palette import OWN_PAL_BANK
from core.models.scene import Scene, WindowSlot
from core.project import Project
from core.models.scene import (
    BLEND_NONE, BLEND_ALPHA, BLEND_BRIGHTEN, BLEND_DARKEN,
    BLEND_TOP, BLEND_BOTTOM, BLEND_NEEDS_BOTTOM, blend_role_of,
    EFFECT_NONE, EFFECT_FADE_BLACK, EFFECT_FADE_WHITE, EFFECT_TRANSLUCENT,
    EFFECT_CUSTOM, blend_effect_of, blend_amount_of, apply_blend_effect,
    TRANSITION_INHERIT,
)
from ui.scene_manager.inspectors.bg_layer_row import BgLayerRow
from ui.scene_manager.inspectors.project_inspector import TRANSITION_LABELS
from core.history import (
    get_history, Command, SetFieldCmd, SwapFieldCmd, AddListItemCmd,
    RemoveListItemCmd, SetSceneModeCmd,
)
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, ScriptPickerPopup, NotesEdit
from ui.common.palette_slot_grid import PaletteSlotGridAsset
from ui.common import icons


# ── Blending — libellés ───────────────────────────────────────────
# Les QUATRE modes du matériel, pas un de plus : `BLDCNT` bits 6-7 n'en code
# que quatre. Pas de « multiply » ni d'« overlay » — les proposer promettrait
# un rendu que la GBA ne sait pas produire.
_BLEND_LABELS = [
    (BLEND_NONE,     "Normal (no blending)"),
    (BLEND_ALPHA,    "Alpha (mix with what is behind)"),
    (BLEND_BRIGHTEN, "Brighten (fade to white)"),
    (BLEND_DARKEN,   "Darken (fade to black)"),
]
_BLEND_ROLE_LABELS = [
    ("",           "—"),
    (BLEND_TOP,    "Top (blended)"),
    (BLEND_BOTTOM, "Bottom (behind)"),
]

# Ce à quoi on PENSE, par-dessus les registres. « Custom » n'est jamais choisi :
# c'est ce que l'inspecteur affiche quand le réglage a été composé à la main,
# et le sélectionner ne réécrit rien (cf. models/scene.apply_blend_effect).
_EFFECT_LABELS = [
    (EFFECT_NONE,        "None"),
    (EFFECT_FADE_BLACK,  "Fade to black (whole screen)"),
    (EFFECT_FADE_WHITE,  "Fade to white (whole screen)"),
    (EFFECT_TRANSLUCENT, "Translucent layer"),
    (EFFECT_CUSTOM,      "Custom (set in Hardware)"),
]
# Ce que le pourcentage veut dire, par effet — le libellé change avec lui :
# « 100 % » ne dit pas la même chose d'un fondu et d'une opacité.
_AMOUNT_LABELS = {
    EFFECT_FADE_BLACK:  ("Darkness:", "0 = untouched, 100 = fully black"),
    EFFECT_FADE_WHITE:  ("Whiteness:", "0 = untouched, 100 = fully white"),
    EFFECT_TRANSLUCENT: ("Opacity:", "Opacity of the marked layer — 100 = opaque, "
                                     "so nothing shows through"),
}
# Le matériel ne connaît que 17 crans (0-16) : un pourcentage tapé se recale sur
# le plus proche. Le dire, sinon « 40 » qui devient « 38 » passe pour un bug.
_AMOUNT_QUANTIZED = ("<br><br>Snaps to the hardware's 17 steps (0-16), so the "
                     "value may shift by a percent or two.")
# ── Transition — libellés ─────────────────────────────────────────
# Les mêmes mots que l'inspecteur de projet (qui les définit, la transition
# étant d'abord un réglage de projet), plus l'item d'absence de surcharge. Son
# libellé dit ce que la scène hérite RÉELLEMENT (cf. _refresh_transition) : un
# « from project » nu obligerait à aller voir ailleurs ce que ça donne.
_TRANSITIONS: tuple[tuple[str, str], ...] = (
    (TRANSITION_INHERIT, "From project"),
) + TRANSITION_LABELS

# Où un effet FRAÎCHEMENT choisi se pose. À mi-course : assez pour se voir dans
# le canvas, jamais au point d'éteindre l'écran au moment du clic.
_EFFECT_DEFAULT_AMOUNT = {
    EFFECT_FADE_BLACK: 50,
    EFFECT_FADE_WHITE: 50,
    EFFECT_TRANSLUCENT: 50,
}


class _ScenePaletteCmd(Command):
    """Mutation undoable de l'allocation palette d'un pool ("obj"|"bg") de la
    scène. Snapshot COMPLET (active_*_palettes + pal_bank de toutes les
    instances du pool) → undo/redo fidèles, couvre uniformément replace / add /
    remove (avec réindexation des références) / override / restore.

    `mutate_fn` applique la nouvelle configuration ; le snapshot avant (pris à
    la construction) et après (pris au 1er execute) suffisent à rejouer sans
    ré-exécuter la logique de mutation."""

    def __init__(self, scene, pool: str, mutate_fn, label: str,
                 persist_fn=None, refresh_fn=None):
        self._scene = scene
        self._pool = pool
        self._mutate = mutate_fn
        self.label = label
        self._persist = persist_fn
        self._refresh = refresh_fn
        self._before = self._snapshot()
        self._after = None

    def _active(self) -> list:
        return getattr(self._scene, f"active_{self._pool}_palettes")

    def _instances(self) -> list:
        return (self._scene.actors if self._pool == "obj"
                else self._scene.background_layers)

    def _snapshot(self):
        return (list(self._active()),
                [(o, getattr(o, "pal_bank", OWN_PAL_BANK)) for o in self._instances()])

    def _restore(self, snap):
        active, banks = snap
        self._active()[:] = active
        for o, pb in banks:
            o.pal_bank = pb

    def _finish(self):
        if self._persist:
            self._persist()
        if self._refresh:
            self._refresh()

    def execute(self):
        if self._after is None:
            self._mutate()
            self._after = self._snapshot()
        else:
            self._restore(self._after)   # redo
        self._finish()

    def undo(self):
        self._restore(self._before)
        self._finish()


# ── Table des modes vidéo GBA (pilote l'inspecteur adaptatif) ──────────────────
# kind : "tiled" (0/1/2, fonds tuilés) | "bitmap" (3/4/5, un fond plein écran BG2).
# bg_slots : slots BG hardware valides ; affine : slots en mode affine (rotation).
# bg_palettes : la scène sélectionne-t-elle des banques de palette BG ? (non en 3/5).
MODE_INFO: dict[int, dict] = {
    0: {"kind": "tiled",  "bg_slots": (0, 1, 2, 3), "affine": (),     "bg_palettes": True,
        "res": (240, 160), "tip": "4 regular tiled backgrounds (BG0-3) · 4/8bpp"},
    1: {"kind": "tiled",  "bg_slots": (0, 1, 2),    "affine": (2,),   "bg_palettes": True,
        "res": (240, 160), "tip": "BG0-1 regular + BG2 affine (rotation/scale)"},
    2: {"kind": "tiled",  "bg_slots": (2, 3),       "affine": (2, 3), "bg_palettes": True,
        "res": (240, 160), "tip": "BG2-3 affine"},
    3: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": False,
        "res": (240, 160), "bpp": 16, "tip": "Bitmap BG2 · 16bpp direct color · 240×160 (no palette)"},
    4: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": True,
        "res": (240, 160), "bpp": 8,  "tip": "Bitmap BG2 · 8bpp paletted (256 colors) · 240×160"},
    5: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": False,
        "res": (160, 128), "bpp": 16, "tip": "Bitmap BG2 · 16bpp direct color · 160×128"},
}


# ──────────────────────────────────────────────────────────────────
#  _WindowSlotRow — une window matérielle (WIN0 ou WIN1) authorée
# ──────────────────────────────────────────────────────────────────
class _WindowSlotRow(QFrame):
    """Rectangle + visibilité + gating de layers pour une WindowSlot.
    Mutation directe de la WindowSlot (pas d'historique par frappe, comme
    CameraInspector) ; `changed` déclenche la persistance côté SceneInspector."""
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)   # (slot,)

    def __init__(self, slot, parent=None):
        super().__init__(parent)
        self.slot = slot
        self.setObjectName("win_row")
        self.setStyleSheet(
            f"QFrame#win_row{{background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};"
            f"border-radius:4px;}}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        is_obj = int(slot.region) == 2
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        title = QLabel("WINDOW OBJ" if is_obj else f"WIN{slot.region}")
        title.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C.TEXT_NORM}; letter-spacing:1px;")
        hdr.addWidget(title)
        self._chk_visible = QCheckBox("Active")
        self._chk_visible.setStyleSheet(QSS.checkbox)
        self._chk_visible.setChecked(slot.visible)
        self._chk_visible.toggled.connect(self._on_field_changed)
        hdr.addWidget(self._chk_visible)
        hdr.addStretch()
        btn_del = QPushButton("×")
        btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_DIM};background:transparent;border:none;font-weight:bold;}}"
            f"QPushButton:hover{{color:{C.ACCENT_RED};}}"
        )
        btn_del.clicked.connect(lambda: self.remove_requested.emit(self.slot))
        hdr.addWidget(btn_del)
        outer.addLayout(hdr)

        # La fenêtre-objet n'a pas de rectangle : sa forme vient des pixels
        # opaques des sprites en mode « fenêtre-objet » (Actor.obj_mode).
        self._spins = {}
        if is_obj:
            note = QLabel("No rectangle: the shape comes from sprites set to\n"
                          "“Mask (OBJ window)” in the Actor inspector.")
            note.setFont(QFont(T.UI, T.XS))
            note.setStyleSheet(f"color:{C.TEXT_MUTED};")
            note.setWordWrap(True)
            outer.addWidget(note)
        else:
            rect_row = QHBoxLayout(); rect_row.setSpacing(6)
            for label, attr, maxv in (("X", "x", 240), ("Y", "y", 160), ("L", "w", 240), ("H", "h", 160)):
                col = QVBoxLayout()
                lbl = QLabel(label)
                lbl.setFont(QFont(T.UI, T.XS)); lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
                col.addWidget(lbl)
                spin = QSpinBox()
                spin.setFont(QFont(T.MONO, T.SM))
                spin.setStyleSheet(QSS.spinbox)
                spin.setRange(0, maxv)
                spin.setValue(getattr(slot, attr))
                spin.setFixedWidth(52)
                spin.valueChanged.connect(self._on_field_changed)
                self._spins[attr] = spin
                col.addWidget(spin)
                rect_row.addLayout(col)
            rect_row.addStretch()
            outer.addLayout(rect_row)

        layers_row = QHBoxLayout(); layers_row.setSpacing(6)
        layers_row.addWidget(self._mk_dim_label("Show through:"))
        self._chk_bg = []
        for i in range(4):
            c = QCheckBox(f"BG{i}")
            c.setStyleSheet(QSS.checkbox)
            c.setChecked(bool(slot.layers_shown[i]) if i < len(slot.layers_shown) else True)
            c.toggled.connect(self._on_field_changed)
            self._chk_bg.append(c)
            layers_row.addWidget(c)
        self._chk_obj = QCheckBox("OBJ")
        self._chk_obj.setStyleSheet(QSS.checkbox)
        self._chk_obj.setChecked(slot.obj_shown)
        self._chk_obj.toggled.connect(self._on_field_changed)
        layers_row.addWidget(self._chk_obj)
        layers_row.addStretch()
        outer.addLayout(layers_row)

    def _mk_dim_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(T.UI, T.XS))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        return lbl

    def _on_field_changed(self, *_):
        s = self.slot
        for attr, spin in self._spins.items():   # vide pour la fenêtre-objet
            setattr(s, attr, spin.value())
        s.visible = self._chk_visible.isChecked()
        s.layers_shown = [c.isChecked() for c in self._chk_bg]
        s.obj_shown = self._chk_obj.isChecked()
        self.changed.emit()


# ──────────────────────────────────────────────────────────────────
#  SceneInspector
# ──────────────────────────────────────────────────────────────────
class SceneInspector(QWidget):
    changed = pyqtSignal()
    slot_assigned = pyqtSignal(int, str)
    # Le mélange a changé — le canvas doit RECOMPOSER ses pixmaps, pas
    # seulement se redessiner. Distinct de `changed`, cf. `_emit_blend_changed`.
    blend_changed = pyqtSignal()

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

        self._empty = QLabel("Select a scene")
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def _card(accent: str = "") -> tuple:
            """Section à plat : léger fond élevé (BG_RAISED sur le BG_PANEL de
            l'inspecteur), sans bordure ni liseré. Le regroupement se fait par
            élévation, l'identité par la couleur du titre — plus les cadres
            empilés jugés « lourds » (voir project_theme_gba_redesign)."""
            f = QFrame()
            f.setObjectName("sc_card")
            f.setStyleSheet(QSS.card("sc_card"))
            inner = QVBoxLayout(f)
            inner.setContentsMargins(10, 8, 10, 10)
            inner.setSpacing(6)
            return f, inner

        def _card_title(text: str, accent: str = None) -> QLabel:
            # Titre de section unifié périwinkle (brique QSS.title_section),
            # plus un filet bas. `accent` conservé pour compat mais ignoré.
            lbl = QLabel(text)
            lbl.setFont(QFont(T.UI, T.SM, QFont.Weight.DemiBold))
            lbl.setStyleSheet(
                QSS.title_section()
                + f"border-bottom:1px solid {C.BORDER};padding-bottom:4px;"
            )
            return lbl

        # ── Carte Note libre ───────────────────────────────────────
        notes_card, notes_inner = _card(C.TEXT_DIM)
        notes_inner.addWidget(_card_title("NOTE", C.TEXT_NORM))
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(lambda text: self._set_scene_field("notes", text))
        notes_inner.addWidget(self._notes_edit)
        cl.addWidget(notes_card)

        # ── Carte Mode vidéo (Scene Mode) — mode + paramètres + script ─────
        # Fusion des anciennes cartes SCENE MODE / PARAMÈTRES / SCRIPT : un seul
        # bouton affiche le mode actif (menu déroulant pour en choisir un autre,
        # même logique de garde-fou/pruning qu'avant), les paramètres de la scène
        # (Layer UI, Scrolling) prennent place à sa droite, et le script de scène
        # est rattaché juste en dessous.
        mode_card, mode_inner = _card(C.ACCENT)
        mode_inner.addWidget(_card_title("SCENE MODE", C.ACCENT))

        mode_row = QHBoxLayout(); mode_row.setContentsMargins(0, 0, 0, 0); mode_row.setSpacing(12)
        self._btn_mode = QPushButton("MODE 0")
        self._btn_mode.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_mode.setFixedSize(84, 44)
        self._btn_mode.setStyleSheet(
            f"QPushButton{{color:{C.ACCENT}; background:{C.BG_INPUT};"
            f"border:2px solid {C.ACCENT}; border-radius:5px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
        )
        self._btn_mode.setToolTip("Change the scene's video mode")
        self._btn_mode.clicked.connect(self._show_mode_menu)
        mode_row.addWidget(self._btn_mode)

        # Colonne paramètres (Layer UI + Scrolling) — masquée en mode bitmap
        # (cf. _apply_mode_ui), placée à droite du bouton de mode.
        self._param_col = QWidget()
        param_inner = QVBoxLayout(self._param_col)
        param_inner.setContentsMargins(0, 0, 0, 0)
        param_inner.setSpacing(4)

        scroll_row = QHBoxLayout(); scroll_row.setSpacing(6)
        lbl_scroll = QLabel("Scrolling:")
        lbl_scroll.setFont(QFont(T.UI, T.SM)); lbl_scroll.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_scroll.setFixedWidth(70)
        scroll_row.addWidget(lbl_scroll)
        self._chk_scroll_h = self._mk_scroll_toggle("scroll_h", "Horizontal scrolling")
        self._chk_scroll_v = self._mk_scroll_toggle("scroll_v", "Vertical scrolling")
        scroll_row.addWidget(self._chk_scroll_h)
        scroll_row.addWidget(self._chk_scroll_v)
        scroll_row.addStretch()
        self._chk_scroll_h.toggled.connect(self._on_scroll_changed)
        self._chk_scroll_v.toggled.connect(self._on_scroll_changed)
        param_inner.addLayout(scroll_row)

        ui_row = QHBoxLayout(); ui_row.setSpacing(6)
        lbl_ui = QLabel("UI layer:")
        lbl_ui.setFont(QFont(T.UI, T.SM)); lbl_ui.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_ui.setFixedWidth(70)
        self._combo_text_bg = QComboBox()
        self._combo_text_bg.setFont(QFont(T.UI, T.SM))
        self._combo_text_bg.setStyleSheet(QSS.combobox)
        for i in range(4):
            self._combo_text_bg.addItem(f"BG{i}" + (" (default)" if i == 1 else ""), i)
        self._combo_text_bg.currentIndexChanged.connect(self._on_text_bg_changed)
        self._combo_text_bg.setToolTip(
            "<b>Layer reserved for HUD text (TTE)</b><br><br>"
            "In-game text (score, dialogue…) takes up a whole BG layer.<br>"
            "Pick a BG that isn't used by a background.<br><br>"
            "<b>Conflict ⚠</b>: if this BG is already assigned to a background,<br>"
            "the two overlap and the result is undefined."
        )
        self._lbl_text_bg_warn = QLabel()
        self._lbl_text_bg_warn.setPixmap(icons.get("warning", C.ACCENT_YLW).pixmap(QSize(14, 14)))
        self._lbl_text_bg_warn.setVisible(False)
        ui_row.addWidget(lbl_ui)
        ui_row.addWidget(self._combo_text_bg)
        ui_row.addWidget(self._lbl_text_bg_warn)
        ui_row.addStretch(1)
        param_inner.addLayout(ui_row)

        # ── Banque de couleurs de l'UI ────────────────────────────
        # Où le texte lit ses couleurs : un SLOT de la sélection BG de la scène.
        # « Automatic » (le défaut) garde le comportement historique, la police
        # imposant sa propre palette.
        pal_row = QHBoxLayout(); pal_row.setSpacing(6)
        lbl_pal = QLabel("UI colors:")
        lbl_pal.setFont(QFont(T.UI, T.SM)); lbl_pal.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_pal.setFixedWidth(70)
        self._combo_ui_pal = QComboBox()
        self._combo_ui_pal.setFont(QFont(T.UI, T.SM))
        self._combo_ui_pal.setStyleSheet(QSS.combobox)
        self._combo_ui_pal.currentIndexChanged.connect(self._on_ui_pal_changed)
        self._combo_ui_pal.setToolTip(
            "<b>Palette bank the UI text reads its colors from</b><br><br>"
            "A slot of this scene's BG selection. Each text slot then picks one "
            "color in it.<br><br>"
            "<b>Automatic</b>: the font loads its own palette instead — its "
            "shades are kept, but two fonts can't have different colors at once."
        )
        pal_row.addWidget(lbl_pal)
        pal_row.addWidget(self._combo_ui_pal, 1)
        param_inner.addLayout(pal_row)

        # ── Police par défaut de la scène ─────────────────────────
        # Celle que `scene_init` charge, donc celle qu'obtient tout texte qui
        # n'en nomme pas — un élément d'UI réglé sur « (scene font) », ou un
        # `text.draw` sans `text.set_font`.
        font_row = QHBoxLayout(); font_row.setSpacing(6)
        lbl_font = QLabel("UI font:")
        lbl_font.setFont(QFont(T.UI, T.SM)); lbl_font.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_font.setFixedWidth(70)
        self._combo_font = QComboBox()
        self._combo_font.setFont(QFont(T.UI, T.SM))
        self._combo_font.setStyleSheet(QSS.combobox)
        self._combo_font.currentIndexChanged.connect(self._on_scene_font_changed)
        self._combo_font.setToolTip(
            "<b>Font this scene loads at init</b><br><br>"
            "What any text without a font of its own gets: a UI element set to "
            "<i>(scene font)</i>, or a <code>text.draw</code> with no "
            "<code>text.set_font</code> before it.<br><br>"
            "<b>Automatic</b>: the first font of the project. There is no "
            "engine-provided default font — that would be a style choice."
        )
        font_row.addWidget(lbl_font)
        font_row.addWidget(self._combo_font, 1)
        param_inner.addLayout(font_row)

        # ── Backdrop ──────────────────────────────────────────────
        # Couleur de l'index 0 de PAL_BG_RAM : ce que le hardware affiche là où
        # AUCUN layer ni sprite ne dessine — donc aussi ce qui apparaît dans une
        # window qui masque tout.
        bd_row = QHBoxLayout(); bd_row.setSpacing(6)
        lbl_bd = QLabel("Backdrop:")
        lbl_bd.setFont(QFont(T.UI, T.SM)); lbl_bd.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_bd.setFixedWidth(70)
        self._btn_backdrop = QPushButton()
        self._btn_backdrop.setFixedSize(40, 22)
        self._btn_backdrop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backdrop.clicked.connect(self._pick_backdrop)
        self._btn_backdrop.setToolTip(
            "<b>Couleur de fond (backdrop)</b><br><br>"
            "Index 0 of the BG palette — shown wherever no layer or<br>"
            "sprite draws, including through a window that masks everything.<br><br>"
            "Quantized to BGR555 (5 bits per channel) like on hardware."
        )
        self._lbl_backdrop = QLabel()
        self._lbl_backdrop.setFont(QFont(T.MONO, T.XS))
        self._lbl_backdrop.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._btn_backdrop_reset = W.btn_ghost("Project default")
        self._btn_backdrop_reset.setFont(QFont(T.UI, T.XS))
        self._btn_backdrop_reset.setToolTip(
            "Reuse the backdrop color defined at project level")
        self._btn_backdrop_reset.clicked.connect(self._reset_backdrop)
        bd_row.addWidget(lbl_bd)
        bd_row.addWidget(self._btn_backdrop)
        bd_row.addWidget(self._lbl_backdrop)
        bd_row.addStretch(1)
        bd_row.addWidget(self._btn_backdrop_reset)
        param_inner.addLayout(bd_row)

        mode_row.addWidget(self._param_col, 1)
        mode_inner.addLayout(mode_row)

        self._mode_hint = QLabel("")
        self._mode_hint.setFont(QFont(T.UI, T.XS)); self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:2px;")
        mode_inner.addWidget(self._mode_hint)

        # ── Transition ────────────────────────────────────────────
        # Le fondu joué en QUITTANT cette scène et en l'OUVRANT. Hors de la
        # colonne des paramètres : une transition vaut aussi en mode bitmap,
        # alors que cette colonne y est masquée.
        trans_row = QHBoxLayout(); trans_row.setSpacing(6)
        lbl_trans = QLabel("Transition:")
        lbl_trans.setFont(QFont(T.UI, T.SM)); lbl_trans.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_trans.setFixedWidth(70)
        self._combo_trans = QComboBox()
        self._combo_trans.setFont(QFont(T.UI, T.SM))
        self._combo_trans.setStyleSheet(QSS.combobox)
        for kind, label in _TRANSITIONS:
            self._combo_trans.addItem(label, kind)
        self._combo_trans.setToolTip(
            "<b>Fade played when leaving AND when opening this scene</b><br><br>"
            "Each scene describes its own disappearance and its own "
            "appearance,<br>so two scenes never fight over a switch.<br><br>"
            "The outgoing scene is frozen while its fade plays, and this "
            "scene's<br>color blending is suspended for the duration — the "
            "hardware has a<br>single blend mode, there is no fade on top of a "
            "translucency."
        )
        self._combo_trans.currentIndexChanged.connect(self._on_transition_kind)
        self._spin_trans = QSpinBox()
        self._spin_trans.setRange(1, 255)
        self._spin_trans.setFixedWidth(60)
        self._spin_trans.setSuffix(" f")
        self._spin_trans.setFont(QFont(T.MONO, T.SM))
        self._spin_trans.setStyleSheet(QSS.spinbox)
        self._spin_trans.setToolTip("Frames per half — leaving, then opening.")
        self._spin_trans.valueChanged.connect(
            lambda v: self._set_scene_field("transition_frames", int(v)))
        trans_row.addWidget(lbl_trans)
        trans_row.addWidget(self._combo_trans, 1)
        trans_row.addWidget(self._spin_trans)
        mode_inner.addLayout(trans_row)

        W.separator(mode_inner)

        from ui.common.widgets import ScriptSlot, ScriptPickerPopup  # noqa: F401 (ScriptPickerPopup used later)
        self._scene_script_slot = ScriptSlot(
            add_label    = "Add a scene script",
            accent_color = C.ACCENT_ORG,
            hint         = "on_start · on_update · on_late_update",
        )
        self._scene_script_slot.set_callbacks(
            on_add   = self._scene_script_new,
            on_open  = self._scene_script_open,
            on_clear = self._scene_script_clear,
        )
        mode_inner.addWidget(self._scene_script_slot)

        cl.addWidget(mode_card)

        # ── Carte Windows (WIN0/WIN1) ──────────────────────────────
        win_card, win_inner = _card(C.ACCENT_BLU)
        win_hdr = QHBoxLayout(); win_hdr.setContentsMargins(0, 0, 0, 0); win_hdr.setSpacing(4)
        win_hdr.addWidget(_card_title("WINDOWS", C.ACCENT_BLU), 1)
        self._btn_win_add = {}
        for region, tip in (
            (0, "Add WIN0"),
            (1, "Add WIN1"),
            (2, "Add the OBJ window (free-form, defined by sprites)"),
        ):
            btn = W.btn_add(tip)
            btn.clicked.connect(lambda _c=False, r=region: self._add_window(r))
            self._btn_win_add[region] = btn
            win_hdr.addWidget(btn)
        win_inner.addLayout(win_hdr)

        win_info = QLabel(
            "Screen masks: WIN0/WIN1 are rectangular, the OBJ window is "
            "free-form. They frame where a layer or sprite shows — they draw "
            "nothing themselves. Scriptable too (window.*)."
        )
        win_info.setFont(QFont(T.UI, T.XS))
        win_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        win_info.setWordWrap(True)
        win_inner.addWidget(win_info)

        self._window_rows: list[_WindowSlotRow] = []
        self._windows_container = QVBoxLayout()
        self._windows_container.setContentsMargins(0, 2, 0, 0)
        self._windows_container.setSpacing(4)
        win_inner.addLayout(self._windows_container)

        cl.addWidget(win_card)

        # ── Carte Blending ─────────────────────────────────────────
        # DEUX niveaux, et le premier suffit presque toujours.
        #
        # Devant : un EFFET (fondu au noir, fondu au blanc, layer translucide)
        # et un pourcentage. C'est ce à quoi les gens pensent, et ça pose les
        # cibles d'office — y compris le backdrop, dont l'oubli est la panne
        # n°1 du blending GBA.
        #
        # Derrière, replié : les registres eux-mêmes (BLDCNT/BLDALPHA/BLDY),
        # pour composer ce que les trois effets ne couvrent pas — cibles
        # partielles, EVA+EVB > 16 pour un halo saturé. Un réglage fait là
        # ressort en « Custom » et n'est jamais réécrit par l'effet.
        blend_card, blend_inner = _card(C.ACCENT_BLU)
        blend_inner.addWidget(_card_title("BLENDING", C.ACCENT_BLU))

        eff_row = QHBoxLayout(); eff_row.setContentsMargins(0, 0, 0, 0); eff_row.setSpacing(8)
        lbl_eff = self._dim_label("Effect:")
        lbl_eff.setFixedWidth(70)
        self._combo_effect = QComboBox()
        self._combo_effect.setFont(QFont(T.UI, T.MD))
        self._combo_effect.setStyleSheet(QSS.combobox)
        for eff, lab in _EFFECT_LABELS:
            self._combo_effect.addItem(lab, eff)
        self._combo_effect.setToolTip(
            "<b>Fade to black / white</b> — the whole screen, for a transition.<br>"
            "<b>Translucent layer</b> — one layer mixed with what is behind it;<br>"
            "mark which one with the ▲ button on its row.<br><br>"
            "The hardware has one blend mode for the entire screen, so these<br>"
            "are exclusive. Open <i>Hardware</i> below to compose something else."
        )
        self._combo_effect.currentIndexChanged.connect(self._on_blend_effect)
        eff_row.addWidget(lbl_eff)
        eff_row.addWidget(self._combo_effect, 1)
        blend_inner.addLayout(eff_row)

        amt_row = QHBoxLayout(); amt_row.setContentsMargins(0, 0, 0, 0); amt_row.setSpacing(8)
        self._lbl_amount = self._dim_label("Amount:")
        self._lbl_amount.setFixedWidth(70)
        self._blend_amount = QSpinBox()
        self._blend_amount.setRange(0, 100)
        self._blend_amount.setSingleStep(5)
        self._blend_amount.setSuffix(" %")
        self._blend_amount.setFont(QFont(T.MONO, T.SM))
        self._blend_amount.setStyleSheet(QSS.spinbox)
        self._blend_amount.setKeyboardTracking(False)
        self._blend_amount.valueChanged.connect(self._on_blend_amount)
        amt_row.addWidget(self._lbl_amount)
        amt_row.addWidget(self._blend_amount)
        amt_row.addStretch(1)
        self._amount_row = QWidget(); self._amount_row.setLayout(amt_row)
        self._amount_row.setStyleSheet("background:transparent;")
        blend_inner.addWidget(self._amount_row)

        self._blend_hint = QLabel("")
        self._blend_hint.setFont(QFont(T.UI, T.XS))
        self._blend_hint.setWordWrap(True)
        self._blend_hint.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:2px;")
        blend_inner.addWidget(self._blend_hint)

        # ── Repli « Hardware » : les registres tels quels ──────────
        self._btn_blend_adv = W.btn_ghost("Hardware ▸")
        self._btn_blend_adv.setFont(QFont(T.UI, T.XS))
        self._btn_blend_adv.setToolTip(
            "The BLDCNT / BLDALPHA / BLDY registers as they are — for what the "
            "three effects above do not cover.")
        self._btn_blend_adv.clicked.connect(self._toggle_blend_adv)
        blend_inner.addWidget(self._btn_blend_adv)

        self._blend_adv = QWidget()
        self._blend_adv.setStyleSheet("background:transparent;")
        adv = QVBoxLayout(self._blend_adv)
        adv.setContentsMargins(0, 2, 0, 0); adv.setSpacing(4)
        self._blend_adv.setVisible(False)
        blend_inner.addWidget(self._blend_adv)

        bl_row = QHBoxLayout(); bl_row.setContentsMargins(0, 0, 0, 0); bl_row.setSpacing(8)
        lbl_bl = self._dim_label("Mode:")
        lbl_bl.setFixedWidth(70)
        self._combo_blend = QComboBox()
        self._combo_blend.setFont(QFont(T.UI, T.SM))
        self._combo_blend.setStyleSheet(QSS.combobox)
        for m, lab in _BLEND_LABELS:
            self._combo_blend.addItem(lab, m)
        self._combo_blend.setToolTip("BLDCNT bits 6-7 — one mode for the whole screen.")
        self._combo_blend.currentIndexChanged.connect(self._on_blend_mode)
        bl_row.addWidget(lbl_bl)
        bl_row.addWidget(self._combo_blend, 1)
        adv.addLayout(bl_row)

        # Coefficients bruts — EVA/EVB pour l'alpha, EVY pour les fondus. Les
        # trois existent toujours, seuls ceux qui AGISSENT se montrent.
        self._blend_ev = {}
        for key, lab, tip in (
            ("eva", "EVA", "Weight of the top layer, 0-16 (16 = full)"),
            ("evb", "EVB", "Weight of the layer behind, 0-16"),
            ("evy", "EVY", "Fade intensity toward white or black, 0-16"),
        ):
            r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(8)
            t = self._dim_label(lab + ":")
            t.setFixedWidth(70)
            sp = QSpinBox()
            sp.setRange(0, 16)          # borne MATÉRIELLE : 5 bits, >16 vaut 16
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setKeyboardTracking(False)
            sp.setToolTip(tip)
            sp.valueChanged.connect(lambda v, k=key: self._on_blend_ev(k, v))
            r.addWidget(t); r.addWidget(sp); r.addStretch(1)
            holder = QWidget(); holder.setLayout(r)
            holder.setStyleSheet("background:transparent;")
            self._blend_ev[key] = (holder, sp)
            adv.addWidget(holder)

        # Sprites et backdrop sont deux cibles comme les layers, mais n'ont pas
        # de ligne dans la liste des layers : leur rôle vit donc ici.
        self._blend_extra = {}
        for attr, lab, tip in (
            ("blend_obj_role", "Sprites",
             "Actors as a blend target — a sprite in semi-transparent OBJ mode "
             "is a separate door and blends regardless of this."),
            ("blend_backdrop_role", "Backdrop",
             "The backdrop as the layer behind. This is what makes a blend "
             "work over an empty area — with nothing behind, nothing blends."),
        ):
            r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(8)
            t = self._dim_label(lab + ":")
            t.setFixedWidth(70)
            cb = QComboBox()
            cb.setFont(QFont(T.UI, T.SM))
            cb.setStyleSheet(QSS.combobox)
            for role, rlab in _BLEND_ROLE_LABELS:
                cb.addItem(rlab, role)
            cb.setToolTip(tip)
            cb.currentIndexChanged.connect(lambda _i, a=attr: self._on_blend_extra(a))
            r.addWidget(t); r.addWidget(cb, 1)
            holder = QWidget(); holder.setLayout(r)
            holder.setStyleSheet("background:transparent;")
            self._blend_extra[attr] = (holder, cb)
            adv.addWidget(holder)

        cl.addWidget(blend_card)

        # ── Carte Background Asset ────────────────────────────────
        bg_card, bg_inner = _card(C.ACCENT)
        self._bg_card = bg_card

        bg_hdr = QHBoxLayout(); bg_hdr.setContentsMargins(0, 0, 0, 0); bg_hdr.setSpacing(4)
        bg_hdr.addWidget(_card_title("BACKGROUND LAYERS", C.ACCENT), 1)
        self._btn_bg_add = W.btn_add("Add a BG layer (max 4)")
        self._btn_bg_add.clicked.connect(self._add_bg_layer)
        bg_hdr.addWidget(self._btn_bg_add)
        bg_inner.addLayout(bg_hdr)

        # Rows dynamiques des BackgroundLayers (portés par la scène)
        self._bg_layer_rows: list[BgLayerRow] = []
        self._inpaint_layer_slot: Optional[int] = None  # layer BG peint actif
        self._bg_layers_container = QVBoxLayout()
        self._bg_layers_container.setContentsMargins(0, 2, 0, 0)
        self._bg_layers_container.setSpacing(3)
        bg_inner.addLayout(self._bg_layers_container)

        # Slot « fond bitmap » (modes 3/4/5) — un seul fond plein écran sur BG2.
        self._bitmap_box = QWidget()
        bmp_l = QVBoxLayout(self._bitmap_box)
        bmp_l.setContentsMargins(0, 2, 0, 0); bmp_l.setSpacing(3)
        self._btn_bitmap_pick = QPushButton("Choose a bitmap background…")
        self._btn_bitmap_pick.setFont(QFont(T.UI, T.SM))
        self._btn_bitmap_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_bitmap_pick.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px 8px; text-align:left;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; border-color:{C.ACCENT_BLU};}}"
        )
        self._btn_bitmap_pick.clicked.connect(self._pick_bitmap_bg)
        bmp_l.addWidget(self._btn_bitmap_pick)
        self._bitmap_note = QLabel("")
        self._bitmap_note.setFont(QFont(T.UI, T.XS)); self._bitmap_note.setWordWrap(True)
        self._bitmap_note.setStyleSheet(f"color:{C.TEXT_DIM};")
        bmp_l.addWidget(self._bitmap_note)
        bg_inner.addWidget(self._bitmap_box)
        self._bitmap_box.setVisible(False)

        cl.addWidget(bg_card)

        # ── Carte Palettes ─────────────────────────────────────────
        # Le catalogue de palettes (Palette Editor) est illimité au niveau
        # projet — c'est ICI qu'on choisit jusqu'à 16 palettes par pool comme
        # "actives" pour cette scène. Actor.pal_bank référence un slot de
        # cette sélection (0-15), pas directement le catalogue.
        pal_card, pal_inner = _card(C.ACCENT)
        pal_inner.addWidget(_card_title("PALETTES", C.ACCENT))

        self._pal_grids: dict[str, PaletteSlotGridAsset] = {}
        self._pal_sublabels: dict[str, QLabel] = {}
        for pool, color, title in (("obj", C.ACCENT_ORG, "OBJ (sprites)"),
                                    ("bg", C.ACCENT_BLU, "BCK (backgrounds)")):
            sub_lbl = QLabel(title)
            sub_lbl.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
            sub_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px; margin-top:4px;")
            pal_inner.addWidget(sub_lbl)
            grid = PaletteSlotGridAsset(color)
            grid.scene_replace.connect(lambda slot, name, pool=pool: self._on_scene_replace(pool, slot, name))
            grid.scene_add.connect(lambda name, pool=pool: self._on_scene_add(pool, name))
            grid.scene_remove.connect(lambda slot, pool=pool: self._on_scene_remove(pool, slot))
            grid.asset_override.connect(lambda entry, name, pool=pool: self._on_asset_override(pool, entry, name))
            grid.asset_restore.connect(lambda entry, pool=pool: self._on_asset_restore(pool, entry))
            pal_inner.addWidget(grid)
            self._pal_grids[pool] = grid
            self._pal_sublabels[pool] = sub_lbl

        cl.addWidget(pal_card)

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
        self._notes_edit.set_text_silent(getattr(scene, "notes", ""))
        self._chk_scroll_h.setChecked(scene.scroll_h)
        self._chk_scroll_v.setChecked(scene.scroll_v)
        self._refresh_scroll_speeds()
        text_bg = getattr(scene, "text_bg", 3)
        self._combo_text_bg.setCurrentIndex(text_bg)
        self._refresh_text_bg_warn()
        self._refresh_scene_script_label()
        self._rebuild_palette_slots()
        # Après `_rebuild_palette_slots` : la liste des banques d'UI se lit dans
        # la sélection BG, que ce dernier vient de rafraîchir.
        self._reload_ui_pal()
        self._reload_scene_font()
        self._rebuild_window_rows()
        self._refresh_backdrop()
        # Après `_rebuild_bg_layers` (via _apply_mode_ui) : `_refresh_blend`
        # pilote la visibilité du rôle sur chaque ligne, qui doit exister.
        self._apply_mode_ui()
        self._refresh_blend()
        self._refresh_transition()
        self._blocking = False

    def _mk_scroll_toggle(self, icon_key: str, tip: str) -> QToolButton:
        """Toggle iconifié (double flèche) pour un axe de scrolling — remplace
        la case à cocher texte, cohérent avec les toggles d'affichage du canvas
        (cf. scene_canvas._mk_view_toggle)."""
        b = QToolButton()
        b.setIcon(icons.get(icon_key, C.TEXT_DIM, C.ACCENT))
        b.setIconSize(QSize(16, 16))
        b.setCheckable(True)
        b.setFixedSize(28, 26)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton{{border:1px solid {C.BORDER_MID};background:{C.BG_INPUT};"
            f"border-radius:4px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
            f"QToolButton:checked{{background:{C.BG_SEL};border:1px solid {C.ACCENT};}}"
        )
        return b

    # ── Scene Mode (0-5) ──────────────────────────────────────────

    def _show_mode_menu(self):
        """Menu déroulant du bouton de mode — remplace l'ancienne rangée de
        6 boutons. Seul le Mode 0 rend réellement pour l'instant ; les autres
        restent grisés (le sélecteur/inspecteur adaptatif existe déjà, pas
        encore le rendu), même garde-fou qu'avant."""
        current = getattr(self._scene, "render_mode", 0) if self._scene else 0
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setToolTipsVisible(True)
        for m in range(6):
            label = f"Mode {m}" + ("  ✓" if m == current else "")
            act = menu.addAction(label)
            if m == 0:
                act.setToolTip(MODE_INFO[0]["tip"])
            else:
                act.setEnabled(False)
                act.setToolTip(f"{MODE_INFO[m]['tip']}\n(rendering not implemented yet — coming soon)")
            act.triggered.connect(lambda _c=False, m=m: self._on_set_mode(m))
        menu.exec(self._btn_mode.mapToGlobal(QPoint(0, self._btn_mode.height())))

    def _refresh_mode_buttons(self):
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        self._btn_mode.setText(f"MODE {mode}")

    def _is_bitmap_layer(self, layer) -> bool:
        ba = self._project.get_background(layer.background_name) if (self._project and layer.background_name) else None
        return bool(ba and getattr(ba, "mode", "tiled") == "bitmap")

    def _pruned_by_mode(self, m: int) -> list:
        """Liste lisible des éléments qui seront supprimés en passant au mode `m`."""
        info = MODE_INFO[m]
        out: list = []
        if info["kind"] == "bitmap":
            for L in self._scene.background_layers:
                if not self._is_bitmap_layer(L):
                    out.append(f"BG{L.bg_slot} layer" + (f" ({L.background_name})" if L.background_name else " (empty)"))
        else:
            valid = set(info["bg_slots"])
            for L in self._scene.background_layers:
                if L.bg_slot not in valid or self._is_bitmap_layer(L):
                    out.append(f"BG{L.bg_slot} layer" + (f" ({L.background_name})" if L.background_name else " (empty)"))
        if not info["bg_palettes"]:
            n = sum(1 for name in self._scene.active_bg_palettes if name)
            if n:
                out.append(f"{n} active BG palette(s)")
        return out

    def _on_set_mode(self, m: int):
        if self._blocking or not self._scene:
            return
        if m == getattr(self._scene, "render_mode", 0):
            self._refresh_mode_buttons(); return
        pruned = self._pruned_by_mode(m)
        if pruned:
            msg = (f"Switching to Mode {m} will remove:\n• " + "\n• ".join(pruned)
                   + "\n\nContinue? (Ctrl+Z to undo)")
            if QMessageBox.question(
                self, "Change scene mode", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self._refresh_mode_buttons()
                return
        info = MODE_INFO[m]
        old = self._scene.background_layers
        if info["kind"] == "bitmap":
            new_layers = [L for L in old if self._is_bitmap_layer(L)][:1]
            for L in new_layers:
                L.bg_slot = 2
        else:
            valid = set(info["bg_slots"])
            new_layers = [L for L in old if L.bg_slot in valid and not self._is_bitmap_layer(L)]
        new_bg_pals = list(self._scene.active_bg_palettes) if info["bg_palettes"] else []
        get_history().push(SetSceneModeCmd(
            self._scene, m, new_layers, new_bg_pals,
            persist_fn=self._persist_scene,
            refresh_fn=lambda: self.load(self._scene, self._project),
        ))
        self.changed.emit()

    def _clear_layer_rows(self):
        for row in self._bg_layer_rows:
            row.hide(); row.setParent(None); row.deleteLater()
        self._bg_layer_rows.clear()

    def _refresh_bitmap_slot(self, info: dict):
        """Met à jour le slot « fond bitmap » (modes 3/4/5) depuis la scène."""
        layer = next((L for L in self._scene.background_layers
                      if self._is_bitmap_layer(L)), None)
        name = layer.background_name if layer else None
        self._btn_bitmap_pick.setText(name or "Choose a bitmap background…")
        rw, rh = info.get("res", (240, 160))
        bpp = info.get("bpp", 8)
        depth = "8bpp paletted (256)" if bpp == 8 else "16bpp direct color"
        self._bitmap_note.setText(f"BG2 · {rw}×{rh} · {depth}"
                                  + ("" if name else " — no background selected"))

    def _pick_bitmap_bg(self):
        if not self._project or not self._scene:
            return
        bitmaps = [b for b in self._project.backgrounds
                   if getattr(b, "mode", "tiled") == "bitmap"]
        if not bitmaps:
            QMessageBox.information(
                self, "Aucun fond bitmap",
                "Importe d'abord une image en mode Bitmap dans le Background Editor.")
            return
        entries = [(b.name, b.name) for b in bitmaps]
        popup = ScriptPickerPopup(entries, C.ACCENT_BLU, parent=self, new_label=None)
        popup.picked.connect(self._set_bitmap_bg)
        popup.show_below(self._btn_bitmap_pick)

    def _set_bitmap_bg(self, name: str):
        from core.models.background import BackgroundLayer
        self._scene.background_layers[:] = [BackgroundLayer(background_name=name, bg_slot=2)]
        self._persist_scene()
        self._apply_mode_ui()
        self.changed.emit()

    def _apply_mode_ui(self):
        """Adapte l'inspecteur au mode de la scène : zone background, paramètres,
        palettes actives."""
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        info = MODE_INFO.get(mode, MODE_INFO[0])
        is_tiled = info["kind"] == "tiled"
        self._refresh_mode_buttons()
        self._mode_hint.setText(info["tip"])
        # BACKGROUND : rangées tuilées vs slot bitmap.
        self._btn_bg_add.setVisible(is_tiled)
        self._bitmap_box.setVisible(not is_tiled)
        self._clear_layer_rows()
        if is_tiled:
            self._rebuild_layer_rows()
        else:
            self._refresh_bitmap_slot(info)
        # Paramètres (texte TTE + scroll) : tuilé seulement.
        self._param_col.setVisible(is_tiled)
        # PALETTES : OBJ toujours, BG seulement en tuilé.
        self._pal_sublabels["bg"].setVisible(is_tiled)
        self._pal_grids["bg"].setVisible(is_tiled)

    def _rebuild_layer_rows(self):
        """Reconstruit les BgLayerRow depuis les layers de la SCÈNE."""
        for row in self._bg_layer_rows:
            # hide() avant setParent(None) : un widget visible détaché de son
            # parent redevient une fenêtre top-level à part entière (c'est le
            # popup flottant "GBA Editor" observé au Ctrl+S) ; deleteLater()
            # pour le détruire proprement plutôt que le laisser orphelin.
            row.hide()
            row.setParent(None)
            row.deleteLater()
        self._bg_layer_rows.clear()

        if not (self._project and self._scene):
            self._btn_bg_add.setEnabled(False)
            return

        active_names = self._scene.active_bg_palettes
        active_banks = [b for n in active_names if (b := self._project.get_palette(n))]
        bg_names = [b.name for b in self._project.backgrounds]

        for layer in self._scene.background_layers:
            row = BgLayerRow(layer.bg_slot)
            row.set_backgrounds(bg_names, layer.background_name)
            if layer.background_name:
                ba = self._project.get_background(layer.background_name)
                png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
                ap = self._project.background_images_dir / png
                if ap.exists():
                    row.set_asset(str(ap))
            row.set_speed(layer.scroll_speed)
            current_pal_name = (
                active_names[layer.pal_bank]
                if 0 <= layer.pal_bank < len(active_names) else None
            )
            row.set_pal_banks(active_banks, current_pal_name)
            row.asset_changed.connect(lambda _, name, l=layer: self._on_layer_image(l, name))
            row.speed_changed.connect(lambda _, v, l=layer: self._on_layer_speed(l, v))
            row.pal_bank_changed.connect(lambda _, n, l=layer: self._on_layer_pal_bank(l, n))
            row.layer_removed.connect(lambda _, l=layer: self._on_layer_remove(l))
            row.bound_toggled.connect(lambda idx: self._on_bound_toggled(idx))
            row.layer_swap_requested.connect(self._on_layer_swap)
            row.visibility_toggled.connect(self._on_layer_visibility)
            row.inpaint_layer_selected.connect(self._on_inpaint_layer)
            row.blend_role_changed.connect(
                lambda _, r, l=layer: self._on_layer_blend_role(l, r))
            row.set_blend_role(blend_role_of(layer))
            row.set_visible_state(getattr(layer, "visible", True))
            row.set_inpaint_layer(layer.bg_slot == self._inpaint_layer_slot)
            self._bg_layers_container.addWidget(row)
            self._bg_layer_rows.append(row)

        self._refresh_bound_rows()
        self._refresh_ui_layer_marks()
        self._sync_layer_blend_rows()
        self._btn_bg_add.setEnabled(len(self._scene.background_layers) < 4)

    # ── Blending ──────────────────────────────────────────────────
    def _refresh_blend(self):
        """Repose la carte BLENDING et n'y montre que ce qui AGIT.

        Les modes 2 et 3 n'emploient que le dessus et lisent BLDY : afficher
        EVA/EVB à côté laisserait composer un réglage sans effet, et chercher
        ensuite pourquoi il n'en a pas."""
        sc = self._scene
        if sc is None:
            return
        mode = int(getattr(sc, "blend_mode", BLEND_NONE) or BLEND_NONE)
        prev, self._blocking = self._blocking, True
        try:
            i = self._combo_blend.findData(mode)
            self._combo_blend.setCurrentIndex(i if i >= 0 else 0)
            for key, (holder, sp) in self._blend_ev.items():
                sp.setValue(int(getattr(sc, f"blend_{key}", 0) or 0))
            on = mode != BLEND_NONE
            self._blend_ev["eva"][0].setVisible(mode == BLEND_ALPHA)
            self._blend_ev["evb"][0].setVisible(mode == BLEND_ALPHA)
            self._blend_ev["evy"][0].setVisible(mode in (BLEND_BRIGHTEN, BLEND_DARKEN))
            for attr, (holder, cb) in self._blend_extra.items():
                holder.setVisible(on)
                j = cb.findData(getattr(sc, attr, "") or "")
                cb.setCurrentIndex(j if j >= 0 else 0)
                # « Dessous » n'a de sens qu'en alpha : le griser plutôt que de
                # le retirer garde un choix déjà posé visible.
                item = cb.model().item(2)
                if item is not None:
                    item.setEnabled(mode in BLEND_NEEDS_BOTTOM)
            # ── Devant : l'effet et son pourcentage ────────────────
            eff = blend_effect_of(sc)
            k = self._combo_effect.findData(eff)
            self._combo_effect.setCurrentIndex(k if k >= 0 else 0)
            # « Custom » n'est proposé que lorsqu'on Y EST : c'est un constat,
            # pas un choix — le sélectionner ne saurait pas quoi écrire.
            item = self._combo_effect.model().item(len(_EFFECT_LABELS) - 1)
            if item is not None:
                item.setEnabled(eff == EFFECT_CUSTOM)
            lab, tip = _AMOUNT_LABELS.get(eff, ("Amount:", ""))
            self._lbl_amount.setText(lab)
            self._blend_amount.setToolTip(tip + _AMOUNT_QUANTIZED if tip else "")
            self._blend_amount.setValue(blend_amount_of(sc))
            self._amount_row.setVisible(eff in _AMOUNT_LABELS)
        finally:
            self._blocking = prev
        self._sync_layer_blend_rows()
        self._refresh_blend_hint()

    def _toggle_blend_adv(self):
        """Déplie les registres. Le repli n'est pas un état de la scène : c'est
        une préférence d'affichage, elle ne se sauvegarde pas."""
        show = not self._blend_adv.isVisible()
        self._blend_adv.setVisible(show)
        self._btn_blend_adv.setText("Hardware ▾" if show else "Hardware ▸")

    def _on_blend_effect(self, _i):
        """Un effet POSE les cibles, pas seulement le mode — c'est tout
        l'intérêt : le backdrop en seconde cible, qu'on oublie toujours, arrive
        avec le reste."""
        if self._blocking or not self._scene:
            return
        eff = self._combo_effect.currentData() or EFFECT_NONE
        if eff == EFFECT_CUSTOM:
            return
        # Le pourcentage n'est repris QUE si l'effet ne change pas : les
        # échelles ne sont pas comparables (100 % d'opacité = rien à voir, 100 %
        # de fondu = écran noir). Sans ça, passer de l'alpha au fondu éteignait
        # l'écran au moment même où on choisissait l'effet.
        amount = (self._blend_amount.value() if blend_effect_of(self._scene) == eff
                  else _EFFECT_DEFAULT_AMOUNT.get(eff, 50))
        from core.history import get_history, SceneBlendCmd
        get_history().push(SceneBlendCmd(
            self._scene, eff, amount,
            label=f"Blending — {self._combo_effect.currentText()}",
            persist_fn=self._persist))
        self._refresh_blend()
        self._rebuild_layer_rows()      # les rôles ont changé sous les lignes
        self._sync_layer_blend_rows()
        self._emit_blend_changed()

    def _on_blend_amount(self, pct: int):
        if self._blocking or not self._scene:
            return
        eff = blend_effect_of(self._scene)
        if eff not in _AMOUNT_LABELS:
            return
        from core.history import get_history, SceneBlendCmd
        get_history().push(SceneBlendCmd(
            self._scene, eff, int(pct),
            label="Blending amount", persist_fn=self._persist))
        self._emit_blend_changed()

    def _sync_layer_blend_rows(self):
        """État de mélange des lignes de layer. Appelé et par `_refresh_blend`
        et par la reconstruction des lignes : une seule fonction, sinon les deux
        chemins divergent au premier ajout de layer."""
        sc = self._scene
        if sc is None:
            return
        # Ce que la ligne propose découle de l'EFFET, pas du mode brut :
        #   aucun effet        → rien à choisir ;
        #   fondu d'écran      → tout est pris, rien à choisir non plus ;
        #   layer translucide  → devant ↔ derrière, deux états ;
        #   composé à la main  → les trois rôles du registre.
        eff = blend_effect_of(sc)
        ui_mode = {EFFECT_NONE: "hidden",
                   EFFECT_FADE_BLACK: "hidden",
                   EFFECT_FADE_WHITE: "hidden",
                   EFFECT_TRANSLUCENT: "toggle"}.get(eff, "full")
        for row, layer in zip(self._bg_layer_rows, sc.background_layers):
            row.set_blend_role(blend_role_of(layer))
            row.set_blend_ui(ui_mode)

    def _refresh_blend_hint(self):
        """Dit ce que la scène fera, ou pourquoi elle ne fera rien.

        Les deux pannes muettes du blending GBA : un mode sans DESSUS (rien
        n'est désigné comme mélangé) et un alpha sans DESSOUS (le mélange n'a
        lieu que là où un pixel du dessus a un pixel du dessous derrière lui).
        Les taire, c'est laisser chercher dans le mauvais registre."""
        sc = self._scene
        mode = int(getattr(sc, "blend_mode", BLEND_NONE) or BLEND_NONE)
        if mode == BLEND_NONE:
            self._blend_hint.setText("")
            return
        msgs = []
        if not sc.blend_has_target(BLEND_TOP):
            # Deux formulations pour la même panne : celle de l'effet dit le
            # geste à faire, celle des registres dit ce qui manque. Un auteur
            # qui n'a pas ouvert « Hardware » n'a pas à connaître le mot
            # « cible » pour comprendre qu'il lui manque un clic.
            if blend_effect_of(sc) == EFFECT_TRANSLUCENT:
                msgs.append("Nothing is translucent yet — click the ▲ button on "
                            "the layer you want to see through.")
            else:
                msgs.append("No <b>top</b> target: nothing is being blended, so "
                            "this mode does nothing. Set a layer (or the "
                            "sprites) to Top.")
        elif mode in BLEND_NEEDS_BOTTOM and not sc.blend_has_target(BLEND_BOTTOM):
            msgs.append("No <b>bottom</b> target: alpha only happens where a top "
                        "pixel has a bottom pixel behind it. Set the layer behind "
                        "— or the backdrop — to Bottom.")
        self._blend_hint.setText("<br>".join(msgs))
        self._blend_hint.setStyleSheet(
            f"color:{C.ACCENT_YLW}; margin-top:2px;" if msgs
            else f"color:{C.TEXT_DIM}; margin-top:2px;")

    def _on_blend_mode(self, _i):
        if self._blocking or not self._scene:
            return
        self._set_scene_field("blend_mode", int(self._combo_blend.currentData() or 0))
        self._refresh_blend()
        self._emit_blend_changed()

    def _on_blend_ev(self, key: str, value: int):
        if self._blocking or not self._scene:
            return
        self._set_scene_field(f"blend_{key}", int(value))
        self._emit_blend_changed()

    def _on_blend_extra(self, attr: str):
        if self._blocking or not self._scene:
            return
        _holder, cb = self._blend_extra[attr]
        self._set_scene_field(attr, cb.currentData() or "")
        self._refresh_blend_hint()
        self._emit_blend_changed()

    def _on_layer_blend_role(self, layer, role: str):
        if self._blocking or not self._scene:
            return
        from core.history import get_history, SetFieldCmd
        old = blend_role_of(layer)
        if old == role:
            return
        get_history().push(SetFieldCmd(
            layer, "blend_role", old, role,
            label=f"BG{layer.bg_slot} blend role", persist_fn=self._persist))
        self._refresh_blend_hint()
        self._emit_blend_changed()

    def _emit_blend_changed(self):
        """Le mélange change des PIXELS : le canvas doit recomposer.

        Un signal DÉDIÉ et non `changed` : ce dernier part à chaque champ de
        scène, et recomposer à chaque fois ferait payer la composition pour un
        renommage. Le canvas y répond par `refresh_blend()`, qui ne relit aucun
        fichier — c'est ce qui rend le curseur suivable."""
        self.blend_changed.emit()

    def _dim_label(self, text: str) -> QLabel:
        """Libellé de champ en ton atténué — le pendant SceneInspector de celui
        de `_WindowSlotRow`, qui appartient à cette autre classe."""
        lbl = QLabel(text)
        lbl.setFont(QFont(T.UI, T.XS))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        return lbl

    def _persist_scene(self):
        if self._project and self._scene:
            # Suspendre le watcher pendant l'écriture : sinon le fichier de scène
            # qu'on vient d'écrire est re-détecté comme « modifié en externe »,
            # ce qui recharge la scène et RECONSTRUIT l'inspecteur — détruisant
            # le widget en cours d'interaction (ex. le QDoubleSpinBox de vitesse
            # d'un BG sous la molette) → crash. Cf. dispatcher._save_scene.
            with get_dispatcher().suspended():
                self._project.save_scene(self._scene)

    def _on_layer_image(self, layer, name: str):
        """Un BackgroundImage (nom) a été choisi pour un layer — l'image existe
        déjà dans assets/backgrounds/ (import via le Background Editor)."""
        if not self._scene or layer.background_name == name:
            return
        get_history().push(SetFieldCmd(
            layer, "background_name", layer.background_name, name,
            label=f"BG{layer.bg_slot}.background_name",
            persist_fn=lambda: (self._persist_scene(), self._rebuild_layer_rows()),
        ))
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_speed(self, layer, value: float):
        if not self._scene or layer.scroll_speed == value:
            return
        get_history().push(SetFieldCmd(
            layer, "scroll_speed", layer.scroll_speed, value,
            label=f"BG{layer.bg_slot}.scroll_speed", persist_fn=self._persist_scene,
        ))

    def _on_layer_pal_bank(self, layer, pal_name: str):
        """Banque de palette d'un layer — index dans scene.active_bg_palettes
        (même mécanisme qu'Actor.pal_bank)."""
        if not self._scene: return
        from ui.common.pickers import PALETTE_NONE
        from core.models.palette import OWN_PAL_BANK
        active_names = self._scene.active_bg_palettes
        if pal_name == PALETTE_NONE:
            idx = OWN_PAL_BANK
        else:
            try:
                idx = active_names.index(pal_name)
            except ValueError:
                return
        if layer.pal_bank == idx:
            return
        get_history().push(SetFieldCmd(
            layer, "pal_bank", layer.pal_bank, idx,
            label=f"BG{layer.bg_slot}.pal_bank", persist_fn=self._persist_scene,
        ))
        self._rebuild_layer_rows()
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_visibility(self, bg_slot: int, visible: bool):
        """Œil de visibilité viewport d'un layer — persiste layer.visible et
        met à jour le canvas (le codegen ignore ce champ)."""
        if not self._scene:
            return
        layer = next((l for l in self._scene.background_layers
                      if l.bg_slot == bg_slot), None)
        if layer is None or layer.visible == visible:
            return
        layer.visible = visible
        self._persist_scene()
        get_dispatcher()._emit("bg_layer_visibility", bg_slot, visible)

    def _on_inpaint_layer(self, bg_slot: int):
        """Sélectionne le layer peint par l'outil de peinture par palette.
        Radio-like : une seule cible active, les autres lignes se décochent."""
        self._inpaint_layer_slot = bg_slot
        for row in self._bg_layer_rows:
            row.set_inpaint_layer(row.slot_index == bg_slot)
        get_dispatcher()._emit("inpaint_layer_changed", bg_slot)

    def _on_layer_swap(self, src_slot: int, dst_slot: int):
        """Glisser-déposer d'un BgLayerRow sur un autre : échange leurs
        bg_slot — donc leur priorité d'affichage (pri = 3 - bg_slot côté
        codegen). Ne déplace ni image ni palette : seul le bg_slot change."""
        if not self._scene or src_slot == dst_slot:
            return
        src = next((l for l in self._scene.background_layers if l.bg_slot == src_slot), None)
        dst = next((l for l in self._scene.background_layers if l.bg_slot == dst_slot), None)
        if not src or not dst:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(SwapFieldCmd(
            src, dst, "bg_slot",
            label=f"Échanger BG{src_slot} <-> BG{dst_slot}", persist_fn=_refresh,
        ))
        get_dispatcher()._emit("bg_slot_changed", src_slot)
        get_dispatcher()._emit("bg_slot_changed", dst_slot)
        self.changed.emit()

    def _on_layer_remove(self, layer):
        if not self._scene or layer not in self._scene.background_layers:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(RemoveListItemCmd(
            self._scene.background_layers, layer, persist_fn=_refresh,
            label=f"Remove layer BG{layer.bg_slot}",
        ))
        self.changed.emit()

    def _add_bg_layer(self):
        """Ajoute un nouveau layer vide à la scène, sur un slot BG valide pour le
        mode courant (Mode 0 : BG0-3 ; Mode 1 : BG0-2 ; Mode 2 : BG2-3)."""
        if not self._scene:
            return
        valid_slots = MODE_INFO.get(getattr(self._scene, "render_mode", 0),
                                    MODE_INFO[0])["bg_slots"]
        used_slots = {L.bg_slot for L in self._scene.background_layers}
        next_slot = next((i for i in valid_slots if i not in used_slots), None)
        if next_slot is None:
            return   # tous les slots BG du mode sont occupés
        from core.models.background import BackgroundLayer
        new_layer = BackgroundLayer(background_name="", bg_slot=next_slot, scroll_speed=1.0)

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(AddListItemCmd(
            self._scene.background_layers, new_layer, persist_fn=_refresh,
            label=f"Ajouter layer BG{next_slot}",
        ))
        self.changed.emit()

    # ── Windows (WIN0/WIN1) ──────────────────────────────────────────

    def _add_window(self, region: int):
        if not self._scene or any(ws.region == region for ws in self._scene.windows):
            return
        new_slot = WindowSlot(region=region)

        def _refresh():
            self._persist_scene()
            self._rebuild_window_rows()
            get_dispatcher()._emit("windows_changed")

        get_history().push(AddListItemCmd(
            self._scene.windows, new_slot, persist_fn=_refresh,
            label=f"Ajouter WIN{region}",
        ))
        self.changed.emit()

    def _remove_window(self, slot):
        if not self._scene or slot not in self._scene.windows:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_window_rows()
            get_dispatcher()._emit("windows_changed")

        get_history().push(RemoveListItemCmd(
            self._scene.windows, slot, persist_fn=_refresh,
            label=f"Supprimer WIN{slot.region}",
        ))
        self.changed.emit()

    def _on_window_field_changed(self):
        self._persist_scene()
        get_dispatcher()._emit("windows_changed")
        self.changed.emit()

    def _rebuild_window_rows(self):
        while self._windows_container.count():
            item = self._windows_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._window_rows = []
        windows = list(self._scene.windows) if self._scene else []
        for slot in sorted(windows, key=lambda ws: ws.region):
            row = _WindowSlotRow(slot)
            row.changed.connect(self._on_window_field_changed)
            row.remove_requested.connect(self._remove_window)
            self._windows_container.addWidget(row)
            self._window_rows.append(row)
        used_regions = {ws.region for ws in windows}
        for region, btn in self._btn_win_add.items():
            btn.setVisible(region not in used_regions)

    # ── Palettes actives ────────────────────────────────────────────

    _DEFAULT_PALETTE_NAME    = "DMG (GB Default)"        # OBJ : 3 nuances (index 0 transparent)
    _DEFAULT_BG_PALETTE_NAME = "DMG (GB Default) (BG)"   # BG  : 4 nuances

    def _rebuild_palette_slots(self):
        from codegen.palette_alloc import scene_palette_view, ScenePaletteView
        if not self._scene or not self._project:
            empty = ScenePaletteView("", [], [], 0)
            for pool in ("obj", "bg"):
                self._pal_grids[pool].load(empty, [])
            return

        # Catalogue unifié — les deux barres (OBJ/BG) piochent dans le même
        # project.palettes, seule la sélection ACTIVE reste séparée par pool
        # (contrainte hardware : PAL_OBJ_RAM et PAL_BG_RAM sont distincts).
        banks = list(self._project.palettes)
        for pool in ("obj", "bg"):
            attr = "active_obj_palettes" if pool == "obj" else "active_bg_palettes"
            active = getattr(self._scene, attr)

            # Scène neuve sans aucune sélection -> défaut DMG au slot 0
            # (variante BG pour le pool BG), plutôt qu'un pool entièrement
            # noir/vide. Repli sur la variante OBJ si la BG n'existe pas.
            default_name = self._DEFAULT_BG_PALETTE_NAME if pool == "bg" else self._DEFAULT_PALETTE_NAME
            if not active and not self._project.get_palette(default_name):
                default_name = self._DEFAULT_PALETTE_NAME
            if not active and self._project.get_palette(default_name):
                active.append(default_name)
                self._persist()

            view = scene_palette_view(self._project, self._scene, pool)
            self._pal_grids[pool].load(view, banks)

    # ── Handlers grille de palettes ─────────────────────────────────

    def _active_list(self, pool: str) -> list:
        return self._scene.active_obj_palettes if pool == "obj" else self._scene.active_bg_palettes

    def _palette_refresh(self, pool: str):
        """Rebâtit la grille + rafraîchit le canvas après une mutation palette."""
        self._rebuild_palette_slots()
        if pool == "bg":
            self._rebuild_layer_rows()   # les BgLayerRow résolvent leur icône via active_bg_palettes
            for L in self._scene.background_layers:
                get_dispatcher()._emit("bg_slot_changed", L.bg_slot)
        else:
            get_dispatcher()._emit("scene_sprites_changed")   # re-quantifier les acteurs
        self.changed.emit()

    def _push_palette_cmd(self, pool: str, mutate_fn, label: str):
        get_history().push(_ScenePaletteCmd(
            self._scene, pool, mutate_fn, label,
            persist_fn=self._persist,
            refresh_fn=lambda p=pool: self._palette_refresh(p),
        ))

    def _on_scene_replace(self, pool: str, slot: int, name: str):
        """Remplace la palette de scène du slot par une autre du catalogue."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)) or active[slot] == name:
            return

        def mutate(a=active, s=slot, n=name):
            a[s] = n
        self._push_palette_cmd(pool, mutate, f"Palette scène [{slot}] → {name}")

    def _on_scene_add(self, pool: str, name: str):
        """Ajoute une palette de scène au premier slot libre — donc juste après
        la dernière palette de scène (les slots libres = banques auto des
        assets). Le « + » et les grisées se décalent d'un cran."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)

        def mutate(a=active, n=name):
            free = next((i for i, x in enumerate(a) if not x), None)
            if free is None:
                a.append(n)
            else:
                a[free] = n
        self._push_palette_cmd(pool, mutate, f"Ajouter palette scène {name}")

    def _on_scene_remove(self, pool: str, slot: int):
        """Retire la palette de scène du slot et RÉINDEXE les références :
        instance pointant sur `slot` → OWN ; pointant au-delà → décrémentée."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)):
            return
        instances = self._instances_for(pool)

        def mutate(a=active, s=slot, insts=instances):
            del a[s]
            for o in insts:
                pb = getattr(o, "pal_bank", OWN_PAL_BANK)
                if pb == s:
                    o.pal_bank = OWN_PAL_BANK
                elif pb > s:
                    o.pal_bank = pb - 1
        self._push_palette_cmd(pool, mutate, f"Remove scene palette [{slot}]")

    def _on_asset_override(self, pool: str, entry, name: str):
        """Override la palette propre d'un groupe d'assets vers une palette du
        CATALOGUE de l'éditeur (comme une couleur normale, pas seulement les
        palettes déjà actives de la scène) : réutilise le slot actif existant
        si `name` y figure déjà, sinon l'ajoute au premier slot libre (même
        logique que `_on_scene_add`) — jamais deux slots pour la même palette."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        targets = [i.obj for i in entry.instances if getattr(i, "obj", None) is not None]
        if not targets:
            return

        def mutate(a=active, n=name, objs=targets):
            try:
                slot = a.index(n)
            except ValueError:
                free = next((i for i, x in enumerate(a) if not x), None)
                if free is None:
                    if len(a) >= 16:
                        return
                    a.append(n)
                    slot = len(a) - 1
                else:
                    a[free] = n
                    slot = free
            for o in objs:
                o.pal_bank = slot
        self._push_palette_cmd(pool, mutate, f"Override asset → {name}")

    def _on_asset_restore(self, pool: str, entry):
        """Revient à la palette d'origine (propre) du groupe d'assets."""
        if self._blocking or not self._scene:
            return
        targets = [i.obj for i in entry.instances if getattr(i, "obj", None) is not None]
        if not targets:
            return

        def mutate(objs=targets):
            for o in objs:
                o.pal_bank = OWN_PAL_BANK
        self._push_palette_cmd(pool, mutate, "Restaurer palette d'origine")

    def _instances_for(self, pool: str) -> list:
        return self._scene.actors if pool == "obj" else self._scene.background_layers

    def _on_bound_toggled(self, idx: int):
        if self._blocking or not self._scene: return
        self._set_scene_field("collision_layer", idx, extra_persist=self._refresh_bound_rows)
        self.changed.emit()

    def _refresh_bound_rows(self):
        cl_idx = getattr(self._scene, "collision_layer", 0)
        for row in self._bg_layer_rows:
            row.set_bound(row.slot_index == cl_idx)

    def _refresh_scroll_speeds(self):
        pass  # vitesse gérée dans BackgroundAsset désormais

    def _on_scroll_changed(self):
        if self._blocking or not self._scene: return
        self._set_scene_field("scroll_h", self._chk_scroll_h.isChecked())
        self._set_scene_field("scroll_v", self._chk_scroll_v.isChecked())
        self.changed.emit()

    # ── Transition ──────────────────────────────────────────────────

    def _refresh_transition(self):
        """Réaffiche la surcharge — et, sur l'item « From project », CE QUE la
        scène hérite : sans ça, savoir ce qu'on obtient demande d'aller ouvrir
        l'inspecteur de projet."""
        sc, p = self._scene, self._project
        kind = getattr(sc, "transition_kind", TRANSITION_INHERIT)
        st = p.settings if p else None
        inherited = getattr(st, "transition_kind", EFFECT_NONE) or EFFECT_NONE
        inh_frames = getattr(st, "transition_frames", 16)
        label = dict(_TRANSITIONS).get(inherited, inherited)
        self._combo_trans.setItemText(
            0, f"From project — {label.lower()}"
            + (f", {inh_frames} f" if inherited != EFFECT_NONE else ""))
        self._combo_trans.blockSignals(True)
        idx = self._combo_trans.findData(kind)
        self._combo_trans.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_trans.blockSignals(False)
        self._spin_trans.blockSignals(True)
        self._spin_trans.setValue(getattr(sc, "transition_frames", 16))
        self._spin_trans.blockSignals(False)
        # La durée n'appartient à la scène que si elle surcharge par un fondu.
        self._spin_trans.setVisible(kind not in (TRANSITION_INHERIT, EFFECT_NONE))

    def _on_transition_kind(self, idx: int):
        if self._blocking or not self._scene: return
        self._set_scene_field("transition_kind",
                              self._combo_trans.itemData(idx) or TRANSITION_INHERIT,
                              extra_persist=self._refresh_transition)
        self.changed.emit()

    # ── Backdrop ────────────────────────────────────────────────────

    def _effective_backdrop(self) -> int:
        """BGR555 réellement compilé : override de scène, sinon défaut projet
        (même résolution que main_gen._resolve_backdrop_color)."""
        if not self._scene:
            return 0
        v = getattr(self._scene, "backdrop_color", None)
        if v is not None:
            return v
        return self._project.settings.backdrop_color if self._project else 0

    def _refresh_backdrop(self):
        from core.gba_color import bgr555_to_rgb888
        v = self._effective_backdrop()
        r, g, b = bgr555_to_rgb888(v)
        self._btn_backdrop.setStyleSheet(
            f"QPushButton{{background:rgb({r},{g},{b});"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        overridden = getattr(self._scene, "backdrop_color", None) is not None
        self._lbl_backdrop.setText(f"0x{v:04X}" + ("" if overridden else "  (projet)"))
        self._btn_backdrop_reset.setVisible(overridden)

    def _pick_backdrop(self):
        from PyQt6.QtWidgets import QColorDialog
        from core.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
        if not self._scene:
            return
        r, g, b = bgr555_to_rgb888(self._effective_backdrop())
        col = QColorDialog.getColor(
            QColor(r, g, b), self, "Couleur de backdrop",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if not col.isValid():
            return
        # Quantification BGR555 : la valeur stockée est celle que la console
        # affichera réellement, pas la couleur 8 bits choisie dans le dialogue.
        self._set_scene_field(
            "backdrop_color", rgb888_to_bgr555(col.red(), col.green(), col.blue()),
            extra_persist=self._notify_backdrop,
        )
        self.changed.emit()

    def _reset_backdrop(self):
        """Retire l'override de scène — la couleur du projet reprend la main."""
        self._set_scene_field("backdrop_color", None, extra_persist=self._notify_backdrop)
        self.changed.emit()

    def _notify_backdrop(self):
        self._refresh_backdrop()
        get_dispatcher()._emit("backdrop_changed")

    def _reload_ui_pal(self):
        """Remplit la liste des banques d'UI depuis la sélection BG de la scène.

        Les slots VIDES sont listés quand même, mais dits comme tels : la
        sélection peut être remplie après coup, et masquer le slot ferait
        disparaître un choix déjà fait dans le JSON."""
        if not self._scene:
            return
        self._combo_ui_pal.blockSignals(True)
        self._combo_ui_pal.clear()
        self._combo_ui_pal.addItem("Automatic (font palette)", -1)
        active = list(getattr(self._scene, "active_bg_palettes", []) or [])
        for i in range(16):
            name = active[i] if i < len(active) else ""
            self._combo_ui_pal.addItem(f"{i} — {name or '(empty)'}", i)
        cur = int(getattr(self._scene, "ui_pal_bank", -1))
        j = self._combo_ui_pal.findData(cur)
        self._combo_ui_pal.setCurrentIndex(j if j >= 0 else 0)
        self._combo_ui_pal.blockSignals(False)

    def _on_ui_pal_changed(self):
        if not self._scene:
            return
        self._set_scene_field("ui_pal_bank", int(self._combo_ui_pal.currentData()))

    def _reload_scene_font(self):
        """Remplit la liste des polices du projet.

        Une police SANS planche exploitable est listée mais dite telle quelle :
        elle n'est pas compilée (`project_fonts` la saute), la choisir ferait
        retomber la scène sur la première du projet. La masquer ferait
        disparaître un choix déjà posé dans le JSON — même règle que les slots
        de palette vides juste au-dessus."""
        if not self._scene:
            return
        p = self._project
        try:
            from codegen.runtime_codegen.main_gen import project_fonts
            usable = {f.name for f in project_fonts(p)} if p else set()
        except Exception:
            usable = {f.name for f in (getattr(p, "fonts", []) or [])} if p else set()
        self._combo_font.blockSignals(True)
        self._combo_font.clear()
        first = sorted(usable)[0] if len(usable) == 1 else ""
        self._combo_font.addItem(
            f"Automatic — {first}" if first else "Automatic (first font)", "")
        for f in (getattr(p, "fonts", []) or []):
            self._combo_font.addItem(
                f.name if f.name in usable else f"{f.name} (no usable sheet)", f.name)
        cur = getattr(self._scene, "font_name", "") or ""
        j = self._combo_font.findData(cur)
        if j < 0 and cur:
            # Police disparue du projet : garder le nom visible plutôt que de
            # retomber en silence sur « Automatic », ce qui EFFACERAIT le choix
            # au premier changement d'un autre champ.
            self._combo_font.addItem(f"{cur} (missing)", cur)
            j = self._combo_font.count() - 1
        self._combo_font.setCurrentIndex(j if j >= 0 else 0)
        self._combo_font.blockSignals(False)

    def _on_scene_font_changed(self):
        if self._blocking or not self._scene:
            return
        self._set_scene_field("font_name", self._combo_font.currentData() or "")
        self.changed.emit()

    def _on_text_bg_changed(self):
        if self._blocking or not self._scene: return
        self._set_scene_field(
            "text_bg", self._combo_text_bg.currentData(),
            extra_persist=self._refresh_text_bg_warn,
        )
        self.changed.emit()

    def _refresh_text_bg_warn(self):
        if not self._scene: return
        self._refresh_ui_layer_marks()
        text_bg = getattr(self._scene, "text_bg", -1)
        conflict = next((l for l in self._scene.background_layers
                          if l.background_name and l.bg_slot == text_bg), None)
        self._lbl_text_bg_warn.setVisible(bool(conflict))
        if conflict:
            self._lbl_text_bg_warn.setToolTip(
                f"BG{text_bg} porte '{conflict.background_name}' — sera écrasé par le texte"
            )

    def _refresh_ui_layer_marks(self):
        """Marque visuellement (icône 'UI') la rangée dont le bg_slot == Layer
        UI de la scène — son charblock est réservé à la police TTE (cf.
        main_gen._gen_scene_init), aucune image ne devrait y être assignée."""
        text_bg = getattr(self._scene, "text_bg", -1) if self._scene else -1
        for row in self._bg_layer_rows:
            row.set_ui_layer(row.slot_index == text_bg)

    def _persist(self):
        if self._project and self._scene:
            get_dispatcher().save_scene()

    def _set_scene_field(self, field: str, value, extra_persist=None):
        """Pousse un SetFieldCmd undoable sur un champ scalaire de la scène
        (no-op si la valeur est inchangée)."""
        if self._blocking or not self._scene: return
        old = getattr(self._scene, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._scene, field, old, value,
            label=f"{self._scene.name}.{field}",
            persist_fn=_do_persist,
        ))

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
        from ui.common.widgets import ScriptPickerPopup

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
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def _scene_script_create_new(self):
        """Dialogue de création d'un nouveau script de scène."""
        if not self._scene or not self._project: return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New scene script", "Name (without .lua):")
        if not ok or not name.strip(): return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        d = self._project.scripts_scenes_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            ctx = ScriptTemplateContext(kind="scene", name=name.strip(), scene_name=self._scene.name)
            sp.write_text(generate_script_template(ctx), encoding="utf-8")
        rel = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
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
        self._set_scene_field("script", "", extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn
