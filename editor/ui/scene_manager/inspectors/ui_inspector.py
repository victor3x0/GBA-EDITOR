"""UIInspector — édition de N'IMPORTE QUEL élément d'une mise en page UI
(texte, conteneur, image), sélectionné dans l'arbre ou le canvas.

UN inspecteur adaptatif, pas un par type : ancrage et géométrie sont les mêmes
champs pour les trois kinds — les dupliquer dans deux classes (l'état d'avant)
garantissait leur divergence. Les sections spécifiques (contenu et police d'un
texte, fond d'un conteneur, sprite et état d'une image) se montrent ou se
cachent au chargement, comme les MODE_INFO du SceneInspector.

**Le nom se change dans l'EN-TÊTE**, pas dans un champ. C'est là qu'il est déjà
affiché en gros, et c'est là que scène, acteur, prefab et script se renomment
(`AssetHeaderBar`, cf. DynamicInspector) : un champ « Name » de plus faisait de
l'interface le seul écran à en avoir deux, l'un montrant le nom et l'autre
seul capable de le changer.

Écrit dans la grammaire `W` (labels à gauche, paires d'axes colorées) — la même
que tous les autres inspecteurs, pour que l'UI ne soit pas un écran étranger.

Les invariants métier restent ceux des modèles (models/ui_region.py) :
  • l'élément porte la GÉOMÉTRIE, jamais l'enchaînement (pas d'éditeur de dialogue) ;
  • l'ancrage n'est éditable que sur un ROOT — un enfant l'hérite ;
  • la cible n'est pas un menu quand elle est contrainte (actor → OBJ, bitmap →
    OBJ) : le champ affiche la valeur ET sa raison ;
  • la taille d'une image n'est pas libre — c'est la frame de son sprite.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QScrollArea, QSpinBox, QLineEdit, QTextEdit, QToolButton,
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QPainter, QPen, QColor
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from core.project import Project
from core.text_markup import display_text
from core.gba_color import bgr555_to_rgb888
from core.models.ui_region import (
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, ALIGNS, TARGET_BG, TARGET_OBJ,
    KIND_PANEL, KIND_TEXT, KIND_IMAGE,
    FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG, FILL_SPRITE, fill_allowed,
    sprite_grid,
    forced_target, forced_target_reason, surface_conflicts,
    image_geometry,
    preset_rect, H_LEFT, H_CENTER, H_RIGHT, V_TOP, V_MIDDLE, V_BOTTOM,
)
from ui.common import icons
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, CollapsibleCard

_ANCHORS = [
    (ANCHOR_SCREEN, "Screen (fixed)"),
    (ANCHOR_WORLD,  "World (scrolls)"),
    (ANCHOR_ACTOR,  "Actor (follows)"),
]
_ALIGN_LABELS = ["Left", "Centered", "Right"]
_TARGETS = [(TARGET_BG, "Background (BG)"), (TARGET_OBJ, "Sprite (OBJ)")]
_FILL_LABELS = [
    (FILL_NONE,   "None (invisible group)"),
    (FILL_COLOR,  "Color (palette)"),
    (FILL_NINE,   "Nine-slice"),
    (FILL_BG,     "Background"),
    (FILL_SPRITE, "Sprite (tiled)"),
]

# ── Presets de placement ──────────────────────────────────────────
_H_POS = (H_LEFT, H_CENTER, H_RIGHT)
_V_POS = (V_TOP, V_MIDDLE, V_BOTTOM)
_POS_WORD = {H_LEFT: "left", H_CENTER: "centre", H_RIGHT: "right",
             V_TOP: "top", V_MIDDLE: "middle", V_BOTTOM: "bottom"}


def _preset_tip(hpos: str, vpos: str, sh: bool, sv: bool) -> str:
    if sh and sv:
        return "Fill the frame"
    if sh:
        return f"Full width, {_POS_WORD[vpos]}"
    if sv:
        return f"Full height, {_POS_WORD[hpos]}"
    return f"{_POS_WORD[vpos].capitalize()} {_POS_WORD[hpos]}"


def _preset_icon(hpos: str, vpos: str, sh: bool, sv: bool) -> QIcon:
    """Le cadre, et dedans la boîte à sa place — dessiné plutôt que nommé.

    Neuf libellés « haut-gauche / haut-centre / … » se lisent moins vite qu'un
    dessin. Générée plutôt que douze fichiers, pour suivre le thème."""
    S, M = 32, 3                      # taille de rendu, marge du cadre
    fw = fh = S - 2 * M
    # ~40 % du cadre : assez pour que la POSITION saute aux yeux.
    bw = fw if sh else int(fw * 0.42)
    bh = fh if sv else int(fh * 0.42)
    bx = {H_LEFT: 0, H_CENTER: (fw - bw) // 2}.get(hpos, fw - bw)
    by = {V_TOP: 0, V_MIDDLE: (fh - bh) // 2}.get(vpos, fh - bh)

    px = QPixmap(S, S)
    px.fill(Qt.GlobalColor.transparent)
    q = QPainter(px)
    q.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    q.setPen(QPen(QColor(C.TEXT_MUTED), 1))
    q.setBrush(Qt.BrushStyle.NoBrush)
    q.drawRect(M, M, fw - 1, fh - 1)
    q.setPen(Qt.PenStyle.NoPen)
    q.setBrush(QColor(icons.COLOR_UI))
    q.drawRect(M + bx, M + by, bw, bh)
    q.end()
    return QIcon(px)


class UIInspector(QWidget):
    changed = pyqtSignal()
    # Le nom a changé sous nos pieds (collision d'unicité résolue par le
    # modèle) : l'en-tête, qui l'affiche, doit se remettre d'accord. Émis par
    # `rename` — la seule porte d'entrée du renommage, cf. la docstring.
    renamed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._layout_asset = None
        self._element = None
        self._scene = None
        self._blocking = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        L = QVBoxLayout(inner)
        L.setContentsMargins(8, 8, 8, 8)
        L.setSpacing(4)
        scroll.setWidget(inner)

        # ── Appartenance ──────────────────────────────────────────
        # La mise en page est un ASSET partagé : modifier ici touche N scènes,
        # et ça se dit en couleur, pas en silence.
        self._layout_lbl = W.hint("", L)

        # ── Ancrage (root uniquement — un enfant hérite) ──────────
        anchor_card = CollapsibleCard("Anchor")
        self._anchor = QComboBox()
        self._anchor.setFont(QFont(T.UI, T.MD))
        self._anchor.setStyleSheet(QSS.combobox)
        for _, lab in _ANCHORS:
            self._anchor.addItem(lab)
        self._anchor.currentIndexChanged.connect(self._on_anchor)
        W.row("Anchor", self._anchor, anchor_card.body_layout)

        self._actor = QComboBox()
        self._actor.setFont(QFont(T.UI, T.MD))
        self._actor.setStyleSheet(QSS.combobox)
        self._actor.currentIndexChanged.connect(self._on_actor)
        self._actor_row = W.row("Actor", self._actor, anchor_card.body_layout).parentWidget()

        self._target = QComboBox()
        self._target.setFont(QFont(T.UI, T.MD))
        self._target.setStyleSheet(QSS.combobox)
        for _, lab in _TARGETS:
            self._target.addItem(lab)
        self._target.currentIndexChanged.connect(self._on_target)
        self._target_row = W.row("Target", self._target, anchor_card.body_layout).parentWidget()

        self._frame_why = W.hint("", anchor_card.body_layout)
        L.addWidget(anchor_card)

        # ── Géométrie ─────────────────────────────────────────────
        geom_card = CollapsibleCard("Geometry (px)")
        self._geom_lbl = geom_card

        # Presets de placement — la grille de Godot, adaptée au matériel : poser
        # une boîte basse sans taper quatre nombres. Les champs restent là pour
        # l'ajustement fin (icône plutôt que libellé, cf. `_preset_icon`).
        self._presets = QWidget()
        self._presets.setStyleSheet("background:transparent;")
        pg = QGridLayout(self._presets)
        pg.setContentsMargins(0, 2, 0, 2)
        pg.setSpacing(2)
        for r_i, vpos in enumerate(_V_POS):
            for c_i, hpos in enumerate(_H_POS):
                pg.addWidget(self._preset_btn(hpos, vpos), r_i, c_i)
        # 4e colonne : les étirements, qui eux CHANGENT la taille — séparés des
        # neuf placements pour que la différence se voie avant le clic.
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sh=True), 0, 3)
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sv=True), 1, 3)
        pg.addWidget(self._preset_btn(H_LEFT, V_TOP, sh=True, sv=True), 2, 3)
        pg.setColumnMinimumWidth(3, 34)     # respire : c'est un autre groupe
        # Colonne fantôme qui absorbe la largeur restante : sinon la grille
        # s'étire et les neuf cases se dispersent, or leur disposition EST
        # l'information — elles doivent rester serrées et carrées.
        pg.setColumnStretch(4, 1)
        W.row("Place", self._presets, geom_card.body_layout)
        self._sp = {}
        for key in ("x", "y", "w", "h"):
            s = QSpinBox()
            s.setFont(QFont(T.MONO, T.MD))
            s.setStyleSheet(QSS.spinbox)
            # Sans ça, taper « 120 » vaut trois valeurs (1, 12, 120) : trois
            # écritures disque et trois redessins du canvas pour un seul geste.
            s.setKeyboardTracking(False)
            s.valueChanged.connect(lambda v, k=key: self._on_geom(k, v))
            self._sp[key] = s
        self._sp["x"].setRange(-512, 512)
        self._sp["y"].setRange(-512, 512)
        self._sp["w"].setRange(8, 512)
        self._sp["h"].setRange(8, 512)
        W.pair("Position", "X", C.AXIS_X, self._sp["x"],
               "Y", C.AXIS_Y, self._sp["y"], geom_card.body_layout)
        W.pair("Size", "L", C.AXIS_X, self._sp["w"],
               "H", C.AXIS_Y, self._sp["h"], geom_card.body_layout)
        self._size_lbl = W.hint("", geom_card.body_layout)
        L.addWidget(geom_card)

        # ── Visibilité (commune aux trois types) ──────────────────
        # État AUTHORÉ de départ, pas l'état effectif : un enfant sous un parent
        # caché reste coché ici (rien ne lui est arrivé), `_visible_why` dit
        # pourquoi il ne s'affiche quand même pas. Un script bascule cette même
        # valeur au runtime via `ui.show(nom, on)` — cf. models/ui_region.py.
        visible_card = CollapsibleCard("Visibility")
        self._visible = W.checkbox_row("Visible", "Shown at scene start", visible_card.body_layout)
        self._visible.toggled.connect(self._on_visible)
        self._visible_why = W.hint("", visible_card.body_layout)
        L.addWidget(visible_card)

        # ── Section TEXTE (zone runtime ET texte authoré) ─────────
        self._text_card = CollapsibleCard("Text")

        # Contenu ÉDITABLE SUR PLACE d'un texte authoré, pour ne pas avoir à
        # créer l'entrée dans l'écran Texte puis revenir la choisir ici.
        #
        # Le contenu n'est PAS stocké dans l'élément : ce widget édite l'entrée
        # de la table pointée par `text_key` (créée à la volée à la première
        # frappe). Le dupliquer ici le sortirait de l'édition centralisée, donc
        # de la traduction et de l'interpolation `$nom`.
        self._content = QTextEdit()
        self._content.setFont(QFont(T.MONO, T.MD))
        self._content.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}")
        self._content.setFixedHeight(72)
        self._content.setPlaceholderText("Type the text shown in-game…")
        self._content.setToolTip(
            "Written into the text table, not into the element — the same entry "
            "is editable from the Text screen. Markup accepted ([speed=…], $var…).")
        # Même coloration que l'atelier Texte, sinon on tape les balises à
        # l'aveugle ici.
        from ui.text_editor.markup_highlighter import MarkupHighlighter
        self._hl = MarkupHighlighter(self._content.document())
        self._content.textChanged.connect(self._on_content_typed)
        self._content.focusOutEvent = self._content_focus_out
        # Commit DIFFÉRÉ : `_persist` sauve le projet et redessine le canvas, ce
        # qui à chaque frappe ferait onze sauvegardes pour « PRESS START ».
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(600)
        self._commit_timer.timeout.connect(self._commit_content)
        self._content_baseline = None   # None = rien en cours d'édition
        self._text_card.body_layout.addWidget(self._content)

        self._key_lbl = W.hint("", self._text_card.body_layout)

        self._text_key = QComboBox()
        self._text_key.setFont(QFont(T.UI, T.SM))
        self._text_key.setStyleSheet(QSS.combobox)
        self._text_key.setToolTip(
            "Bind this element to another existing entry — to share one label "
            "between several screens.")
        self._text_key.currentIndexChanged.connect(self._on_text_key)
        self._text_key_row = W.row("Entry", self._text_key, self._text_card.body_layout).parentWidget()

        self._preview = QComboBox()
        self._preview.setFont(QFont(T.UI, T.MD))
        self._preview.setStyleSheet(QSS.combobox)
        self._preview.setToolTip("Editor only: used to measure overflow, "
                                 "never compiled — the script decides the displayed text.")
        self._preview.currentIndexChanged.connect(self._on_preview)
        self._preview_row = W.row("Preview", self._preview, self._text_card.body_layout).parentWidget()

        self._font = QComboBox()
        self._font.setFont(QFont(T.UI, T.MD))
        self._font.setStyleSheet(QSS.combobox)
        self._font.currentIndexChanged.connect(self._on_font)
        self._font_row = W.row("Font", self._font, self._text_card.body_layout).parentWidget()

        self._align = QComboBox()
        self._align.setFont(QFont(T.UI, T.MD))
        self._align.setStyleSheet(QSS.combobox)
        for lab in _ALIGN_LABELS:
            self._align.addItem(lab)
        self._align.currentIndexChanged.connect(self._on_align)
        self._align_row = W.row("Alignment", self._align, self._text_card.body_layout).parentWidget()

        # Couleur du texte : un INDEX dans la banque d'UI de la scène, pas un
        # RGB — le matériel n'offre que des index. 0 = encre d'origine (seul
        # moyen de garder une police à contour) ; sinon l'encre est APLATIE,
        # comme avec `[color=n]`.
        self._color = QComboBox()
        self._color.setFont(QFont(T.UI, T.MD))
        self._color.setStyleSheet(QSS.combobox)
        self._color.currentIndexChanged.connect(self._on_color)
        self._color.setToolTip(
            "<b>Text color</b> — an index in the scene's UI palette bank.<br><br>"
            "<b>Font ink</b> keeps the font's own shades (outline, fill).<br>"
            "Any other value flattens the ink to that single color.<br><br>"
            "Each color used costs one more copy of the scene's glyphs in VRAM."
        )
        self._color_row = W.row("Color", self._color, self._text_card.body_layout).parentWidget()

        self._anim = QSpinBox()
        self._anim.setFont(QFont(T.MONO, T.MD))
        self._anim.setStyleSheet(QSS.spinbox)
        self._anim.setRange(0, 32)
        self._anim.setKeyboardTracking(False)
        self._anim.setToolTip(
            "How many characters, at most, can leave the strip to "
            "receive an effect. Reserved for build (counted in the gauge); "
            "beyond that, glyphs fall back to static.")
        self._anim.valueChanged.connect(self._on_anim)
        self._anim_row = W.row("Anim. gl.", self._anim, self._text_card.body_layout).parentWidget()
        L.addWidget(self._text_card)

        # ── Section FOND (conteneur) ──────────────────────────────
        self._fill_card = CollapsibleCard("Background")

        self._fill_kind = QComboBox()
        self._fill_kind.setFont(QFont(T.UI, T.MD))
        self._fill_kind.setStyleSheet(QSS.combobox)
        for k, lab in _FILL_LABELS:
            self._fill_kind.addItem(lab, k)
        self._fill_kind.currentIndexChanged.connect(self._on_fill_kind)
        self._fill_kind_row = W.row("Mode", self._fill_kind, self._fill_card.body_layout).parentWidget()

        # Couleur : palette + index + pastille de rendu.
        color_box = QWidget()
        color_box.setStyleSheet("background:transparent;")
        cc = QHBoxLayout(color_box)
        cc.setContentsMargins(0, 0, 0, 0)
        cc.setSpacing(6)
        self._fill_palette = QComboBox()
        self._fill_palette.setFont(QFont(T.UI, T.SM))
        self._fill_palette.setStyleSheet(QSS.combobox)
        self._fill_palette.currentIndexChanged.connect(self._on_fill_palette)
        cc.addWidget(self._fill_palette, 1)
        self._fill_index = QSpinBox()
        self._fill_index.setFont(QFont(T.MONO, T.MD))
        self._fill_index.setStyleSheet(QSS.spinbox)
        self._fill_index.setRange(0, 15)
        self._fill_index.setKeyboardTracking(False)
        self._fill_index.valueChanged.connect(self._on_fill_index)
        cc.addWidget(self._fill_index)
        self._fill_swatch = QLabel()
        self._fill_swatch.setFixedSize(22, 22)
        cc.addWidget(self._fill_swatch)
        self._fill_color_row = W.row("Color", color_box, self._fill_card.body_layout).parentWidget()

        self._fill_asset = QComboBox()
        self._fill_asset.setFont(QFont(T.UI, T.SM))
        self._fill_asset.setStyleSheet(QSS.combobox)
        self._fill_asset.currentIndexChanged.connect(self._on_fill_asset)
        self._fill_asset_row = W.row("Asset", self._fill_asset, self._fill_card.body_layout).parentWidget()

        # ── Fond SPRITE (cible OBJ) ───────────────────────────────
        # Mêmes trois questions que pour une image — quel sprite, quel état —
        # plus la seule chose qu'un fond ajoute : sa cadence propre.
        self._fill_sprite = QComboBox()
        self._fill_sprite.setFont(QFont(T.UI, T.SM))
        self._fill_sprite.setStyleSheet(QSS.combobox)
        self._fill_sprite.setToolTip(
            "Sprite tiled across the panel. Unlike an image, the panel keeps "
            "its own size: the sprite repeats to cover it, one OAM slot per "
            "cell (the hardware cannot stretch an OBJ without affine mode).")
        self._fill_sprite.currentIndexChanged.connect(self._on_fill_sprite)
        self._fill_sprite_row = W.row("Sprite", self._fill_sprite, self._fill_card.body_layout).parentWidget()

        self._fill_state = QComboBox()
        self._fill_state.setFont(QFont(T.UI, T.SM))
        self._fill_state.setStyleSheet(QSS.combobox)
        self._fill_state.setToolTip(
            "Initial animation state. A script can change it later with "
            "ui.image_set — a panel background gets an IMAGE_* constant of its "
            "own, like any image.")
        self._fill_state.currentIndexChanged.connect(self._on_fill_state)
        self._fill_state_row = W.row("State", self._fill_state, self._fill_card.body_layout).parentWidget()

        self._fill_speed = QSpinBox()
        self._fill_speed.setFont(QFont(T.MONO, T.MD))
        self._fill_speed.setStyleSheet(QSS.spinbox)
        self._fill_speed.setRange(0, 255)
        self._fill_speed.setSpecialValueText("From sprite")
        self._fill_speed.setSuffix(" frames")
        self._fill_speed.setKeyboardTracking(False)
        self._fill_speed.setToolTip(
            "Frames between two animation frames, overriding the state's own "
            "speed.\n\n0 (= From sprite) keeps the value edited in the Sprite "
            "Editor, which stays the single source of truth — otherwise fixing "
            "a speed there would silently stop having any effect here.")
        self._fill_speed.valueChanged.connect(self._on_fill_speed)
        self._fill_speed_row = W.row("Speed", self._fill_speed, self._fill_card.body_layout).parentWidget()

        # Marges de coupe du cadre sélectionné. Elles vivent sur le FOND
        # D'INTERFACE lui-même (`BackgroundAsset.slice_*`), asset PARTAGÉ entre
        # tous les panels qui le citent — d'où le persist projet. Pas de champ
        # « source » ici : le fond cité EST l'image. Pas de bouton « créer un
        # cadre » non plus — un cadre s'importe dans le Background Editor, comme
        # toute autre image, et c'est là que le canvas montre où passe la coupe.
        ns_margins = QWidget()
        ns_margins.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(ns_margins)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(4)
        self._ns_m = {}
        for key, lab in (("slice_left", "L"), ("slice_right", "R"),
                         ("slice_top", "T"), ("slice_bottom", "B")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 64)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda v, k=key: self._on_ns_margin(k, v))
            mrow.addWidget(t)
            mrow.addWidget(sp, 1)
            self._ns_m[key] = sp
        self._ns_margins_row = W.row("Margins", ns_margins, self._fill_card.body_layout).parentWidget()

        self._fill_why = W.hint("", self._fill_card.body_layout)
        L.addWidget(self._fill_card)

        # ── Section LISTE (ROADMAP v0.22) ─────────────────────────
        # Une propriété du PANNEAU, pas un quatrième type d'élément : le moteur
        # prend la navigation, pas la mise en page. Les rangées sont les zones
        # de texte posées DANS ce panneau — rien à déclarer de plus.
        self._list_card = CollapsibleCard("Liste")
        self._list_on = W.checkbox_row(
            "Navigation", "Ce panneau est une liste", self._list_card.body_layout)
        self._list_on.toggled.connect(
            lambda v: (self._set("is_list", bool(v), "List"),
                       self._sync_list_rows()))
        self._list_axis = W.combobox(["Verticale", "Horizontale"])
        self._list_axis.currentIndexChanged.connect(
            lambda i: self._set("list_axis",
                                "horizontal" if i == 1 else "vertical", "List axis"))
        self._list_axis_row = W.row("Axe", self._list_axis, self._list_card.body_layout).parentWidget()
        self._list_wrap = W.checkbox_row(
            "Boucle", "Du dernier au premier", self._list_card.body_layout)
        self._list_wrap.toggled.connect(
            lambda v: self._set("list_wrap", bool(v), "List wrap"))
        self._list_why = W.hint("", self._list_card.body_layout)
        L.addWidget(self._list_card)

        # ── Section IMAGE (sprite à état) ─────────────────────────
        # L'élément DÉSIGNE, il ne redéfinit pas : ni vitesse, ni liste de
        # frames, ni direction ici — tout ça vit dans le SpriteAsset et s'édite
        # dans le Sprite Editor. Recopier une vitesse donnerait deux vérités
        # pour un même dessin (cf. models/ui_region.UIImage).
        self._img_card = CollapsibleCard("Image")

        self._img_sprite = QComboBox()
        self._img_sprite.setFont(QFont(T.UI, T.MD))
        self._img_sprite.setStyleSheet(QSS.combobox)
        self._img_sprite.setToolTip(
            "Sprite asset drawn here. Picking one resizes the element to its "
            "frame — the hardware cannot stretch a sprite.")
        self._img_sprite.currentIndexChanged.connect(self._on_img_sprite)
        self._img_sprite_row = W.row("Sprite", self._img_sprite, self._img_card.body_layout).parentWidget()

        self._img_state = QComboBox()
        self._img_state.setFont(QFont(T.UI, T.MD))
        self._img_state.setStyleSheet(QSS.combobox)
        self._img_state.setToolTip(
            "State shown when the scene starts. A script can switch to any "
            "other state of this sprite — ui.image_set(\"name\", \"state\").")
        self._img_state.currentIndexChanged.connect(self._on_img_state)
        self._img_state_row = W.row("State", self._img_state, self._img_card.body_layout).parentWidget()

        self._img_play = QComboBox()
        self._img_play.setFont(QFont(T.UI, T.MD))
        self._img_play.setStyleSheet(QSS.combobox)
        self._img_play.addItem("Playing", True)
        self._img_play.addItem("Frozen on frame 1", False)
        self._img_play.setToolTip(
            "A frozen image costs no per-frame work and never rewrites the "
            "tilemap — the right default for a static HUD icon.")
        self._img_play.currentIndexChanged.connect(self._on_img_play)
        self._img_play_row = W.row("Frames", self._img_play, self._img_card.body_layout).parentWidget()

        self._img_prio = QSpinBox()
        self._img_prio.setFont(QFont(T.MONO, T.MD))
        self._img_prio.setStyleSheet(QSS.spinbox)
        self._img_prio.setRange(0, 3)
        self._img_prio.setKeyboardTracking(False)
        self._img_prio.setToolTip("0 = frontmost. Carried by the element, not "
                                  "inherited: a gauge and its frame overlap on purpose.")
        self._img_prio.valueChanged.connect(self._on_img_prio)
        self._img_prio_row = W.row("Priority", self._img_prio, self._img_card.body_layout).parentWidget()

        self._img_why = W.hint("", self._img_card.body_layout)
        L.addWidget(self._img_card)

        # ── Diagnostic + suppression ──────────────────────────────
        self._warn = W.hint("", L, color=C.ACCENT_YLW)

        W.separator(L)
        self._del = W.btn_ghost("Delete element")
        self._del.setFont(QFont(T.UI, T.SM))
        self._del.clicked.connect(self._on_delete)
        L.addWidget(self._del)
        L.addStretch()

    # ── Presets de placement ──────────────────────────────────────
    def _preset_btn(self, hpos: str, vpos: str,
                    sh: bool = False, sv: bool = False) -> QToolButton:
        b = QToolButton()
        b.setFixedSize(24, 24)
        b.setStyleSheet(QSS.toolbutton_icon)
        b.setIcon(_preset_icon(hpos, vpos, sh, sv))
        b.setIconSize(b.size() * 0.8)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(_preset_tip(hpos, vpos, sh, sv))
        b.clicked.connect(lambda _=False: self._apply_preset(hpos, vpos, sh, sv))
        return b

    def _apply_preset(self, hpos: str, vpos: str, sh: bool, sv: bool):
        """Repose l'élément dans son cadre. UNE commande pour les quatre champs
        (`ResizeUIRegionCmd`, celle des poignées du canvas) : quatre
        `SetFieldCmd` donneraient quatre annulations pour un clic."""
        el, lay = self._element, self._layout_asset
        if el is None or lay is None:
            return
        fw, fh = lay.frame_size(el)
        tile = lay.resolved_target(el, self._render_mode()) == TARGET_BG
        old = (el.x, el.y, el.w, el.h)
        new = preset_rect(el.w, el.h, fw, fh, hpos, vpos, sh, sv, tile)
        if tuple(new) == old:
            return
        from core.history import get_history, ResizeUIRegionCmd
        cmd = ResizeUIRegionCmd(el, old, new, persist_fn=self._persist)
        cmd.label = f"Place {el.name} — {_preset_tip(hpos, vpos, sh, sv)}"
        get_history().push(cmd)
        self._blocking = True
        try:
            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(el, k)))
        finally:
            self._blocking = False
        self._refresh_diagnostics()

    # ── Chargement ────────────────────────────────────────────────
    def load(self, layout_asset, element, project: Project, scene):
        # Une frappe en attente appartient à l'élément PRÉCÉDENT : la commiter
        # avant de changer de contexte, sinon le timer tirera sur le nouveau.
        self._commit_content()
        self._layout_asset, self._element = layout_asset, element
        self._project, self._scene = project, scene
        self._blocking = True
        try:
            kind = self._kind()

            users = project.ui_layout_users(layout_asset.name) if project else []
            shared = (f"  ·  shared by {len(users)} scenes" if len(users) > 1 else "")
            self._layout_lbl.setText(f"Layout: {layout_asset.name}{shared}")
            self._layout_lbl.setStyleSheet(
                f"color:{C.ACCENT_YLW};" if len(users) > 1 else f"color:{C.TEXT_MUTED};")

            self._reload_actors()
            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(element, k, 0)))
            self._visible.setChecked(bool(getattr(element, "visible", True)))
            self._sync_visible_hint()

            # Sections par type — tout se montre/cache ICI, une seule fois.
            is_text  = kind == KIND_TEXT
            is_panel = kind == KIND_PANEL
            is_image = kind == KIND_IMAGE
            # La cible est un choix de l'auteur pour tout ce qui DESSINE ; un
            # conteneur, lui, la tient de son root comme le reste de sa branche.
            self._target_row.setVisible(is_text or is_image)
            self._text_card.setVisible(is_text)
            self._fill_card.setVisible(is_panel)
            self._list_card.setVisible(is_panel)
            self._sync_list_rows()
            self._img_card.setVisible(is_image)
            # La taille d'une image est celle de la frame de son sprite : la
            # laisser éditable inviterait à un étirement que le matériel ne sait
            # pas faire. Les presets de PLACEMENT restent actifs (ils ne
            # redimensionnent pas sans `stretch_*`).
            for k in ("w", "h"):
                self._sp[k].setEnabled(not is_image)
            self._del.setText("Delete element")

            if is_text:
                self._reload_fonts()
                self._align.setCurrentIndex(
                    ALIGNS.index(element.align) if element.align in ALIGNS else 0)
                self._reload_color()
                self._reload_previews()
                self._anim.setValue(int(getattr(element, "animated_glyphs", 0) or 0))
                self._reload_text_key()
                self._reload_content()
            if is_panel:
                self._reload_fill()
            if is_image:
                self._reload_image()

            self._sync_frame()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    # ── Contexte ──────────────────────────────────────────────────
    def _kind(self) -> str:
        return getattr(self._element, "kind", KIND_TEXT)

    def _render_mode(self) -> int:
        return int(getattr(self._scene, "render_mode", 0) or 0)

    def _is_root(self) -> bool:
        """Un élément de premier niveau (sans parent, ou parent pendant) : c'est
        LUI qui porte l'ancrage. Un enfant l'hérite et n'y touche pas."""
        e = self._element
        return not e.parent or self._layout_asset.get(e.parent) is None

    # ── Rechargements de combos ───────────────────────────────────
    def _reload_actors(self):
        self._actor.clear()
        names = [a.name for a in getattr(self._scene, "actors", [])] if self._scene else []
        self._actor.addItems(names or ["(no actor)"])
        e = self._element
        anchor, actor = self._layout_asset.effective_anchor(e) if e else ("", "")
        self._anchor.setCurrentIndex(
            next((i for i, (a, _) in enumerate(_ANCHORS) if a == anchor), 0))
        if e and actor in names:
            self._actor.setCurrentIndex(names.index(actor))
        self._actor_row.setVisible(anchor == ANCHOR_ACTOR)

    def _reload_fonts(self):
        self._font.clear()
        self._font.addItem("(scene font)", "")
        for f in (self._project.fonts if self._project else []):
            self._font.addItem(f.name, f.name)
        i = self._font.findData(getattr(self._element, "font_name", "") or "")
        self._font.setCurrentIndex(i if i >= 0 else 0)

    def _reload_previews(self):
        self._preview.clear()
        self._preview.addItem("(none)", "")
        values = self._project.text_values() if self._project else {}
        for t in (self._project.texts if self._project else []):
            self._preview.addItem(
                f"{t.key} — {display_text(t.content, values)[:24]}", t.key)
        i = self._preview.findData(getattr(self._element, "preview_text", "") or "")
        self._preview.setCurrentIndex(i if i >= 0 else 0)

    def _reload_text_key(self):
        self._text_key.clear()
        self._text_key.addItem("(new entry)", "")
        for t in (self._project.texts if self._project else []):
            self._text_key.addItem(t.key, t.key)
        i = self._text_key.findData(getattr(self._element, "text_key", "") or "")
        self._text_key.setCurrentIndex(i if i >= 0 else 0)

    # ── Image (désigne un sprite et l'un de ses états) ────────────
    def _current_sprite(self):
        """Le SpriteAsset que cette image affiche, ou None (nom vide/cassé)."""
        name = getattr(self._element, "sprite_name", "") or ""
        if not (self._project and name):
            return None
        return next((s for s in getattr(self._project, "sprites", [])
                     if s.name == name), None)

    def _reload_image(self):
        prev, self._blocking = self._blocking, True
        try:
            self._img_sprite.clear()
            self._img_sprite.addItem("(no sprite)", "")
            for s in (getattr(self._project, "sprites", []) if self._project else []):
                self._img_sprite.addItem(s.name, s.name)
            i = self._img_sprite.findData(getattr(self._element, "sprite_name", "") or "")
            self._img_sprite.setCurrentIndex(i if i >= 0 else 0)
            self._reload_image_states()
            j = self._img_play.findData(bool(getattr(self._element, "playing", True)))
            self._img_play.setCurrentIndex(j if j >= 0 else 0)
            self._img_prio.setValue(int(getattr(self._element, "priority", 0) or 0))
        finally:
            self._blocking = prev
        self._sync_image_note()

    def _reload_image_states(self):
        """Les états du sprite courant. « (first state) » plutôt qu'un premier
        état nommé en dur : un `state_name` vide suit le sprite quand on en
        réordonne les états, un nom figé désignerait l'ancien."""
        self._img_state.blockSignals(True)
        self._img_state.clear()
        sprite = self._current_sprite()
        self._img_state.addItem("(first state)", "")
        for st in (getattr(sprite, "states", []) if sprite else []):
            self._img_state.addItem(st.name, st.name)
        self._img_state.setEnabled(sprite is not None)
        k = self._img_state.findData(getattr(self._element, "state_name", "") or "")
        self._img_state.setCurrentIndex(k if k >= 0 else 0)
        self._img_state.blockSignals(False)

    def _sprite_frame_count(self, sprite) -> int:
        """Frames que le build chargera pour ce sprite.

        `count_frames`, celle du build, et pas un comptage maison : elle DÉDUPLIQUE
        (deux états qui partagent une pose ne coûtent qu'une frame), et annoncer
        ici un chiffre plus gros que celui réservé ferait douter de la jauge à
        chaque fois que les deux ne tombent pas d'accord."""
        if sprite is None or self._project is None:
            return 1
        from codegen.grit_conversion import count_frames
        return count_frames(self._project, sprite)

    def _sync_image_note(self):
        """Ce que l'image coûte, dit avant le build. Un sprite manquant est un
        trou visible à l'écran, pas une erreur de compilation : on le nomme."""
        el = self._element
        if el is None or self._kind() != KIND_IMAGE:
            return
        sprite = self._current_sprite()
        if sprite is None:
            self._img_why.setText(
                "No sprite bound — nothing will be drawn here."
                if not getattr(el, "sprite_name", "") else
                f"Sprite “{el.sprite_name}” not found in the project.")
            self._img_why.setStyleSheet(f"color:{C.ACCENT_YLW};")
            return
        frames = self._sprite_frame_count(sprite)
        g = image_geometry(el, frames)
        target = self._layout_asset.resolved_target(el, self._render_mode())
        n = g["tiles"]
        tiles = f"{n} tile" + ("s" if n > 1 else "")
        # Une image OBJ ne réserve RIEN : ses tuiles sont celles du sprite, déjà
        # résidentes. Annoncer un coût VRAM là serait compter deux fois le même
        # dessin (cf. models/ui_region.layout_obj_budget).
        where = (f"1 OAM slot, sharing the sprite's {tiles} already in OBJ VRAM"
                 if target == TARGET_OBJ
                 else f"{tiles} in the UI charblock")
        self._img_why.setText(
            f"{el.w}×{el.h} px  ·  {frames} frame(s) across all states  ·  {where}. "
            f"Every state stays resident: a script may switch at any frame.")
        self._img_why.setStyleSheet(f"color:{C.TEXT_MUTED};")

    def _on_img_sprite(self, i):
        """Choisir un sprite REDIMENSIONNE l'élément sur sa frame — une seule
        entrée d'historique pour les deux, sinon annuler laisserait un rectangle
        qui ne correspond à aucun dessin."""
        if self._blocking or not self._element or i < 0:
            return
        name = self._img_sprite.currentData() or ""
        self._set("sprite_name", name, "Image sprite")
        # `state_name` pointe un état de l'ANCIEN sprite : le remettre au défaut
        # plutôt que de garder une ref qui ne résout plus (elle retomberait
        # silencieusement sur l'état 0 au build).
        self._set("state_name", "", "Image state")
        sprite = self._current_sprite()
        if sprite is not None and self._element.sync_size_from(sprite):
            self._blocking = True
            try:
                for k in ("w", "h"):
                    self._sp[k].setValue(int(getattr(self._element, k)))
            finally:
                self._blocking = False
        self._blocking = True
        try:
            self._reload_image_states()
        finally:
            self._blocking = False
        self._persist()
        self._sync_image_note()

    def _on_img_state(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("state_name", self._img_state.currentData() or "", "Image state")

    def _on_img_play(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("playing", bool(self._img_play.currentData()), "Image playback")
        self._sync_image_note()

    def _on_img_prio(self, v):
        if self._blocking or not self._element:
            return
        self._set("priority", int(v), "Image priority")

    # ── Contenu (édite l'entrée de table, pas l'élément) ──────────
    def _current_text(self):
        """L'entrée de table que cet élément affiche, ou None s'il n'en a pas
        encore (elle naîtra à la première frappe)."""
        key = getattr(self._element, "text_key", "") or ""
        return self._project.get_text(key) if (self._project and key) else None

    def _reload_content(self):
        """Repose le contenu et le badge de clé. Sous `_blocking` : setPlainText
        déclenche `textChanged`, qui prendrait un rechargement pour une frappe."""
        t = self._current_text()
        self._content.setPlainText(t.content if t else "")
        self._content_baseline = None
        self._sync_key_badge()

    def _sync_key_badge(self):
        """Le badge sous l'éditeur : quelle entrée, dérivée ou nommée, partagée
        ou non. Séparé du rechargement du contenu — le reposer pendant que
        l'utilisateur écrit lui remettrait le curseur au début."""
        t = self._current_text()
        if t is None:
            self._key_lbl.setText("No entry yet — typing here creates one.")
            self._key_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            return
        users = self._text_users(t.key)
        shared = f"  ·  shown by {users} other element(s)" if users else ""
        self._key_lbl.setText(
            f"key: {t.key}"
            + ("  ·  auto" if t.auto_key else "  ·  named by hand")
            + shared)
        # Une entrée partagée se corrige en un endroit — mais se casse aussi en
        # un endroit. Même règle que le badge « mise en page partagée ».
        self._key_lbl.setStyleSheet(
            f"color:{C.ACCENT_YLW};" if users else f"color:{C.TEXT_MUTED};")

    def _text_users(self, key: str) -> int:
        """Autres éléments d'UI du projet qui affichent la même entrée."""
        if not self._project:
            return 0
        return sum(1 for _l, e in self._project.all_regions()
                   if e is not self._element
                   and getattr(e, "text_key", "") == key)

    def _on_content_typed(self):
        """Frappe : on écrit dans le modèle TOUT DE SUITE — c'est ce qui fait
        vivre l'aperçu du canvas — mais on ne sauve ni ne pousse d'historique
        avant la fin de la salve."""
        if self._blocking or not self._element or self._kind() != KIND_TEXT:
            return
        new = self._content.toPlainText()
        t = self._current_text()
        if t is None:
            if not new.strip():
                return          # frappe vide : pas de quoi créer une entrée
            self._create_text_entry(new)
            self.changed.emit()
            self._commit_timer.start()
            return
        if self._content_baseline is None:
            self._content_baseline = t.content      # début de salve
        t.content = new
        self.changed.emit()     # redessin du canvas, sans écriture disque
        self._commit_timer.start()

    def _content_focus_out(self, e):
        QTextEdit.focusOutEvent(self._content, e)
        self._commit_content()

    def _commit_content(self):
        """Fin de salve : une commande d'historique et une sauvegarde.

        La valeur est DÉJÀ dans le modèle (posée à la frappe) : la commande la
        repose à l'identique, elle n'existe que pour rendre le geste annulable.
        `SetFieldCmd.merge` fusionne la salve en une entrée d'historique."""
        self._commit_timer.stop()
        if self._content_baseline is None:
            return
        old, self._content_baseline = self._content_baseline, None
        t = self._current_text()
        if t is None or t.content == old:
            return
        from core.history import get_history, SetFieldCmd
        get_history().push(SetFieldCmd(
            t, "content", old, t.content,
            label=f"Edit text {t.key}", persist_fn=self._persist))

    def _create_text_entry(self, content: str):
        """Crée l'entrée de table qui manquait et l'accroche à l'élément.

        Le chemin PROPOSE la clé : mise en page puis nom de l'élément, ce qui
        situe sans jamais posséder (`auto_key` reste vrai, ranger l'entrée
        ailleurs la recalera). Cf. models/text.py."""
        from ui.text_editor.text_commands import CreateTextForElementCmd
        from core.history import get_history
        get_history().push(CreateTextForElementCmd(
            self._project, self._element, content,
            path=[self._layout_asset.name, self._element.name],
            scene=getattr(self._scene, "name", "") or "",
            persist_fn=self._persist))
        self._blocking = True
        try:
            self._reload_text_key()     # l'entrée neuve entre dans la liste
            self._sync_key_badge()
        finally:
            self._blocking = False

    # ── Frame : ancrage + cible + pas de grille ───────────────────
    def _sync_frame(self):
        """Verrouille ancrage/cible selon le rôle (root ou enfant) et le
        matériel, et le DIT : une contrainte muette se lit comme un bug."""
        e, rm = self._element, self._render_mode()
        lay = self._layout_asset
        is_root = self._is_root()
        eff_anchor, _ = lay.effective_anchor(e)
        forced = forced_target(eff_anchor, rm)
        eff = lay.resolved_target(e, rm)

        self._anchor.setEnabled(is_root)
        self._actor.setEnabled(is_root)
        if self._kind() in (KIND_TEXT, KIND_IMAGE):
            self._target.setCurrentIndex(
                next((i for i, (t, _) in enumerate(_TARGETS) if t == eff), 0))
            self._target.setEnabled(is_root and forced is None)

        if not is_root:
            root = lay.root_of(e.name)
            self._frame_why.setText(
                f"Inherited from root “{root.name if root else '?'}” — anchor {eff_anchor}")
            self._frame_why.setStyleSheet(f"color:{C.TEXT_MUTED};")
        elif forced:
            self._frame_why.setText(f"Target forced — {forced_target_reason(eff_anchor, rm)}")
            self._frame_why.setStyleSheet(f"color:{C.ACCENT_YLW};")
        else:
            self._frame_why.setText("")

        # Le BG ne peut pas se poser hors grille : le pas des spinbox le dit.
        step = 8 if eff == TARGET_BG else 1
        for k in ("x", "y", "w", "h"):
            self._sp[k].setSingleStep(step)
        self._geom_lbl.set_title(
            "Geometry (px, relative to parent)" if not is_root
            else "Geometry (px, tile-aligned)" if eff == TARGET_BG
            else "Geometry (px, actor offset)" if eff_anchor == ANCHOR_ACTOR
            else "Geometry (px)")

    def _sync_visible_hint(self):
        """Dit pourquoi l'élément ne s'affiche pas quand la case est cochée :
        un ancêtre caché l'emporte sans jamais toucher à cette case (cf.
        `UILayout.is_visible`, qui remonte la chaîne au lieu de la propager)."""
        e, lay = self._element, self._layout_asset
        if e is None or lay is None or not self._visible.isChecked():
            self._visible_why.setText("")
            return
        hidden_ancestor = next(
            (a for a in lay.ancestors(e.name)
             if not getattr(lay.get(a), "visible", True)), None)
        if hidden_ancestor:
            self._visible_why.setText(
                f"Hidden anyway — parent “{hidden_ancestor}” is not visible.")
            self._visible_why.setStyleSheet(f"color:{C.ACCENT_YLW};")
        else:
            self._visible_why.setText("")

    def _refresh_diagnostics(self):
        """Empreinte + avertissements d'un élément de TEXTE.

        Une image a sa propre note (`_sync_image_note`) : son empreinte se lit
        dans le sprite, pas dans le rectangle. Un conteneur n'en a aucune."""
        if self._kind() == KIND_IMAGE:
            self._size_lbl.setText("")
            self._warn.setText("")
            self._sync_image_note()
            return
        if self._kind() != KIND_TEXT:
            self._size_lbl.setText("")
            self._warn.setText("")
            return
        r, rm = self._element, self._render_mode()
        lay = self._layout_asset
        target = lay.resolved_target(r, rm)
        eff_anchor, eff_actor = lay.effective_anchor(r)
        tx, ty, tw, th = r.tile_rect()
        msgs = []
        if target == TARGET_OBJ:
            from core.models.ui_region import strip_geometry
            g = strip_geometry(r)
            self._size_lbl.setText(
                f"{tw}×{th} tiles  ·  {g['oam']} OAM and {g['tiles']} OBJ tiles "
                f"({g['strip_oam']} strip + {g['anim']} animated)")
        else:
            self._size_lbl.setText(f"{tw}×{th} tiles  ·  {tw * th} tiles footprint")

        if target == TARGET_OBJ and eff_anchor == ANCHOR_ACTOR and not eff_actor:
            msgs.append("Anchored on an actor (via its root), but no actor "
                        "chosen: the element will land at the screen origin.")
        # Aliasing de surface entre slots BG de la MÊME mise en page. `slots` et
        # non `regions` : un texte authoré compose sur la même surface.
        others = [o for o in lay.slots
                  if o is not r and lay.resolved_target(o, rm) == TARGET_BG]
        if target == TARGET_BG and others:
            for a, b in surface_conflicts([r] + others):
                if a is r or b is r:
                    other = b if a is r else a
                    msgs.append(
                        f"Surface overlap with “{other.name}”: in composed "
                        f"font mode, two zones a multiple of 8 rows apart "
                        f"share their tiles and erase each other.")
                    break
        self._warn.setText("\n\n".join(msgs))

    # ── Fond (conteneur) ──────────────────────────────────────────
    def _reload_fill(self):
        """Peuple la section fond et grise les modes incompatibles avec la cible
        (dérivée du root) : un background n'est pas un sprite."""
        el, rm = self._element, self._render_mode()
        target = self._layout_asset.resolved_target(el, rm)
        for i in range(self._fill_kind.count()):
            item = self._fill_kind.model().item(i)
            if item is not None:
                item.setEnabled(fill_allowed(self._fill_kind.itemData(i), target))
        fi = self._fill_kind.findData(getattr(el, "fill_kind", FILL_NONE))
        self._fill_kind.setCurrentIndex(fi if fi >= 0 else 0)
        self._fill_palette.clear()
        self._fill_palette.addItem("(palette)", "")
        for p in (self._project.palettes if self._project else []):
            self._fill_palette.addItem(p.name, p.name)
        pi = self._fill_palette.findData(getattr(el, "fill_palette", "") or "")
        self._fill_palette.setCurrentIndex(pi if pi >= 0 else 0)
        self._fill_index.setValue(int(getattr(el, "fill_index", 0) or 0))
        self._reload_fill_asset()
        self._reload_fill_sprite()
        self._sync_fill()
        # Navigation (ROADMAP v0.22) — lue depuis le panneau comme le reste.
        self._list_on.setChecked(bool(getattr(el, "is_list", False)))
        self._list_axis.setCurrentIndex(
            1 if getattr(el, "list_axis", "vertical") == "horizontal" else 0)
        self._list_wrap.setChecked(bool(getattr(el, "list_wrap", True)))
        self._sync_list_rows()

    def _reload_fill_sprite(self):
        """Peuple sprite/état/vitesse du fond sprite. blockSignals : repeupler
        un combo émet `currentIndexChanged`, qui écrirait dans le modèle."""
        el = self._element
        self._fill_sprite.blockSignals(True)
        self._fill_sprite.clear()
        self._fill_sprite.addItem("(no sprite)", "")
        for s in (getattr(self._project, "sprites", []) if self._project else []):
            self._fill_sprite.addItem(s.name, s.name)
        i = self._fill_sprite.findData(getattr(el, "fill_sprite", "") or "")
        self._fill_sprite.setCurrentIndex(i if i >= 0 else 0)
        self._fill_sprite.blockSignals(False)
        self._reload_fill_states()
        self._fill_speed.blockSignals(True)
        self._fill_speed.setValue(int(getattr(el, "fill_speed", 0) or 0))
        self._fill_speed.blockSignals(False)

    def _reload_fill_states(self):
        """États du sprite de fond. « (first state) » plutôt qu'un premier état
        nommé en dur — même raison que pour une image : un nom vide suit le
        sprite quand on en réordonne les états, un nom figé désigne l'ancien."""
        self._fill_state.blockSignals(True)
        self._fill_state.clear()
        sprite = (self._project.get_sprite(getattr(self._element, "fill_sprite", "") or "")
                  if self._project else None)
        self._fill_state.addItem("(first state)", "")
        for st in (getattr(sprite, "states", []) if sprite else []):
            self._fill_state.addItem(st.name, st.name)
        self._fill_state.setEnabled(sprite is not None)
        k = self._fill_state.findData(getattr(self._element, "fill_state", "") or "")
        self._fill_state.setCurrentIndex(k if k >= 0 else 0)
        self._fill_state.blockSignals(False)

    def _reload_fill_asset(self):
        """Peuple le combo d'asset selon le mode. blockSignals pour ne pas
        écraser `fill_asset` pendant le repeuplement.

        En nine-slice, seuls les fonds d'INTERFACE de rôle « nine-slice » sont
        proposés : eux seuls portent des marges de coupe, et citer une image qui
        n'en a pas donnerait un cadre sans coins. En mode background, toute
        image reste citable — poser un décor derrière un panneau est légitime,
        et rien dans les données ne s'y oppose."""
        fk = self._fill_kind.currentData()
        self._fill_asset.blockSignals(True)
        self._fill_asset.clear()
        self._fill_asset.addItem("(asset)", "")
        if fk == FILL_NINE:
            from core.models.background import UI_ROLE_NINE
            ui_bgs = (self._project.ui_backgrounds(UI_ROLE_NINE)
                      if self._project else [])
            for n in ui_bgs:
                self._fill_asset.addItem(n.name, n.name)
        elif fk == FILL_BG:
            for b in (getattr(self._project, "backgrounds", []) if self._project else []):
                self._fill_asset.addItem(b.name, b.name)
        ai = self._fill_asset.findData(getattr(self._element, "fill_asset", "") or "")
        self._fill_asset.setCurrentIndex(ai if ai >= 0 else 0)
        self._fill_asset.blockSignals(False)

    def _sync_fill(self):
        """Montre les champs du mode courant + une note ; met à jour la pastille."""
        if self._kind() != KIND_PANEL:
            return
        fk = self._fill_kind.currentData()
        self._fill_color_row.setVisible(fk == FILL_COLOR)
        self._fill_asset_row.setVisible(fk in (FILL_NINE, FILL_BG))
        self._ns_margins_row.setVisible(fk == FILL_NINE)
        for w in (self._fill_sprite_row, self._fill_state_row,
                  self._fill_speed_row):
            w.setVisible(fk == FILL_SPRITE)
        if fk == FILL_NINE:
            self._reload_ns()
        note = {
            FILL_COLOR: "A palette entry (index 0 = transparent on hardware).",
            FILL_NINE:  "Stretchable frame: fixed corners, repeated edges/center. "
                        "Margins belong to the UI background — editing them here "
                        "changes every panel using it.",
            FILL_BG:    "Tiled background, cropped on bottom/right if the zone is "
                        "smaller. BG target only.",
            FILL_SPRITE: self._sprite_fill_note(),
        }.get(fk, "")
        self._fill_why.setText(note)
        self._update_swatch()

    def _sprite_fill_note(self) -> str:
        """Ce que le pavage coûte VRAIMENT, chiffré sur le sprite choisi.

        Le nombre de slots OAM est la seule information que l'auteur ne peut pas
        deviner en regardant le canvas, et c'est celle qui fait échouer un build
        (128 slots pour toute la scène, acteurs compris)."""
        sprite = (self._project.get_sprite(getattr(self._element, "fill_sprite", "") or "")
                  if self._project else None)
        if sprite is None:
            return ("Sprite tiled across the panel — the only background that "
                    "exists on OBJ target, where there is no tilemap.")
        fw = int(getattr(sprite, "frame_w", 0) or 0)
        fh = int(getattr(sprite, "frame_h", 0) or 0)
        cols, rows = sprite_grid(self._element, fw, fh)
        n = cols * rows
        over = (cols * fw - int(self._element.w), rows * fh - int(self._element.h))
        txt = (f"{fw}×{fh} tiled {cols}×{rows} = {n} OAM slot"
               f"{'s' if n > 1 else ''} of the 128 the hardware has, actors "
               f"included. Tiles cost nothing extra: every cell points at the "
               f"same frame.")
        if over[0] or over[1]:
            txt += (f"\nThe last column/row overflows by {over[0]}×{over[1]} px: "
                    f"the hardware cannot crop a sprite.")
        return txt

    def _current_ns(self):
        """Le fond d'interface cité comme cadre — c'est lui qui porte l'image
        ET les marges."""
        if not self._project:
            return None
        return self._project.get_background(getattr(self._element, "fill_asset", "") or "")

    def _reload_ns(self):
        """Charge les marges du cadre sélectionné ; grise si aucun."""
        prev, self._blocking = self._blocking, True
        try:
            ns = self._current_ns()
            has = ns is not None
            for sp in self._ns_m.values():
                sp.setEnabled(has)
            if has:
                for k, sp in self._ns_m.items():
                    sp.setValue(int(getattr(ns, k, 0)))
        finally:
            self._blocking = prev

    def _update_swatch(self):
        css = f"background:transparent; border:1px solid {C.BORDER};"
        if self._fill_kind.currentData() == FILL_COLOR and self._project is not None:
            bank = self._project.get_palette(self._fill_palette.currentData() or "")
            idx = self._fill_index.value()
            if bank and 0 <= idx < len(bank.colors):
                r, g, b = bgr555_to_rgb888(bank.colors[idx])
                css = f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER};"
        self._fill_swatch.setStyleSheet(css)

    # ── Édition (toutes les écritures passent par l'historique) ────
    def _persist(self):
        # Par le dispatcher, jamais `project.save()` en direct : il suspend le
        # watcher de fichiers le temps de l'écriture. Sans ça le watcher voit le
        # JSON changer, croit à une édition externe et fait recharger la scène —
        # ce qui rebascule l'inspecteur sur la scène et fait perdre l'élément en
        # cours d'édition à chaque champ modifié.
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def _sync_list_rows(self):
        """Montre les réglages de liste quand le panneau en est une, et dit
        combien de rangées il porte — une liste sans zone de texte enfant
        n'afficherait rien, et c'est le genre de chose qu'on veut lire ici
        plutôt que découvrir au Build."""
        e = self._element
        on = bool(getattr(e, "is_list", False)) if e is not None else False
        for w in (self._list_axis_row, self._list_wrap):
            w.setVisible(on)
        if not on:
            self._list_why.setText("")
            return
        from core.models.ui_region import KIND_TEXT
        lay = self._layout_asset
        rows = [x for x in (lay.elements if lay else [])
                if getattr(x, "parent", "") == e.name
                and getattr(x, "kind", "") == KIND_TEXT]
        if rows:
            self._list_why.setText(
                f"{len(rows)} rangée(s) : {', '.join(r.name for r in rows)}. "
                f"Le script écrit leur contenu — list.row(…) rend la zone.")
        else:
            self._list_why.setText(
                "Aucune rangée : posez des zones de texte DANS ce panneau. "
                "Ce sont elles que la liste parcourt.")

    def _set(self, field: str, value, label: str):
        from core.history import get_history, SetFieldCmd
        old = getattr(self._element, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(self._element, field, old, value,
                                       label=label, persist_fn=self._persist))

    def rename(self, new_name: str) -> str:
        """Renomme l'élément courant — appelé par l'EN-TÊTE, seule porte d'entrée.

        Tout le travail (unicité projet, rebranchement des enfants sur le
        nouveau nom, réécriture des scripts qui citent la constante) est déjà
        dans `Project.rename_ui_element` : le refaire ici en donnerait une
        seconde version, et c'est toujours la seconde qui oublie un cas.

        Retourne le nom RÉELLEMENT appliqué — il peut différer de la demande si
        une collision a été résolue, et l'en-tête doit afficher celui-là."""
        el, lay = self._element, self._layout_asset
        if el is None or lay is None or not self._project:
            return ""
        old = el.name
        applied = self._project.rename_ui_element(lay, el, new_name)
        if applied != old:
            self._persist()
            self.renamed.emit(applied)
        return applied

    def _on_anchor(self, i):
        if self._blocking or not self._element:
            return
        self._set("anchor", _ANCHORS[i][0], "Anchor")
        self._blocking = True
        try:
            self._reload_actors()
            self._sync_frame()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    def _on_actor(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("anchor_actor", self._actor.currentText(), "Element actor")

    def _on_target(self, i):
        if self._blocking or not self._element:
            return
        self._set("target", _TARGETS[i][0], "Zone target")
        self._refresh_diagnostics()

    def _on_geom(self, key: str, val: int):
        if self._blocking or not self._element:
            return
        self._set(key, int(val), "Geometry")
        self._refresh_diagnostics()

    def _on_visible(self, on: bool):
        if self._blocking or not self._element:
            return
        self._set("visible", bool(on), "Visibility")
        self._sync_visible_hint()

    def _on_align(self, i):
        if self._blocking or not self._element:
            return
        self._set("align", ALIGNS[i], "Alignment")

    def _on_font(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("font_name", self._font.currentData() or "", "Font")

    def _on_color(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("text_color", int(self._color.currentData() or 0), "Text color")

    def _ui_bank(self):
        """PaletteBank où le texte de CETTE scène lit ses couleurs, ou None.

        None en mode automatique (la police impose sa propre palette) ou si le
        slot désigné est vide : pas de pastilles à montrer dans ces cas."""
        if not (self._project and self._scene):
            return None
        slot = int(getattr(self._scene, "ui_pal_bank", -1))
        active = list(getattr(self._scene, "active_bg_palettes", []) or [])
        if not 0 <= slot < len(active):
            return None
        return self._project.get_palette(active[slot])

    def _reload_color(self):
        """Remplit la liste des couleurs. Les 15 index sont TOUJOURS proposés
        (pastille en plus quand la banque est connue) : l'index reste valide
        même sans banque désignée, les masquer effacerait un choix déjà posé."""
        self._color.blockSignals(True)
        self._color.clear()
        bank = self._ui_bank()
        self._color.addItem("Font ink (default)", 0)
        for idx in range(1, 16):
            if bank and idx < len(bank.colors):
                r, g, b = bgr555_to_rgb888(bank.colors[idx])
                pm = QPixmap(12, 12)
                pm.fill(QColor(r, g, b))
                self._color.addItem(QIcon(pm), f"{idx}", idx)
            else:
                self._color.addItem(f"{idx}", idx)
        cur = int(getattr(self._element, "text_color", 0) or 0)
        j = self._color.findData(cur)
        self._color.setCurrentIndex(j if j >= 0 else 0)
        self._color.blockSignals(False)

    def _on_preview(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("preview_text", self._preview.currentData() or "", "Zone preview")

    def _on_text_key(self, i):
        """Ré-accroche l'élément à une AUTRE entrée existante. La salve en cours
        appartient à l'ancienne : la commiter avant de basculer."""
        if self._blocking or not self._element or i < 0:
            return
        self._commit_content()
        self._set("text_key", self._text_key.currentData() or "", "Element text")
        self._blocking = True
        try:
            self._reload_content()
        finally:
            self._blocking = False
        self._refresh_diagnostics()

    def _on_anim(self, v):
        if self._blocking or not self._element:
            return
        self._set("animated_glyphs", int(v), "Zone animated glyphs")
        self._refresh_diagnostics()

    # ── Fond : écritures ──────────────────────────────────────────
    def _fill_editable(self) -> bool:
        return bool(self._element) and self._kind() == KIND_PANEL

    def _on_fill_kind(self, i):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_kind", self._fill_kind.currentData() or FILL_NONE, "Container background")
        self._blocking = True
        try:
            self._reload_fill_asset()
            self._sync_fill()
        finally:
            self._blocking = False

    def _on_fill_palette(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_palette", self._fill_palette.currentData() or "", "Background palette")
        self._update_swatch()

    def _on_fill_index(self, v):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_index", int(v), "Background index")
        self._update_swatch()

    def _on_fill_asset(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_asset", self._fill_asset.currentData() or "", "Background asset")
        self._reload_ns()

    # ── Fond sprite (cible OBJ) ───────────────────────────────────
    def _on_fill_sprite(self, i):
        """Changer de sprite REMET l'état au défaut — `fill_state` pointe un état
        de l'ANCIEN sprite, et le garder retomberait silencieusement sur l'état 0
        au build. Même règle que pour une image.

        Le panneau, lui, n'est PAS redimensionné : sa taille est celle du
        conteneur, c'est le fond qui s'y adapte en se pavant."""
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_sprite", self._fill_sprite.currentData() or "", "Panel sprite")
        self._set("fill_state", "", "Panel sprite state")
        self._reload_fill_states()
        self._sync_fill()

    def _on_fill_state(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_state", self._fill_state.currentData() or "",
                  "Panel sprite state")

    def _on_fill_speed(self, v):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_speed", int(v), "Panel sprite speed")

    # ── Nine-slice (asset partagé) ────────────────────────────────
    def _persist_ns(self):
        """Le cadre est un asset PARTAGÉ : sauver le projet + redessiner."""
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def _set_ns(self, ns, field, value, label):
        from core.history import get_history, SetFieldCmd
        old = getattr(ns, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(ns, field, old, value,
                                       label=label, persist_fn=self._persist_ns))

    def _on_ns_margin(self, key, v):
        if self._blocking:
            return
        ns = self._current_ns()
        if ns is not None:
            self._set_ns(ns, key, int(v), "Frame margin")

    # ── Suppression ───────────────────────────────────────────────
    def _on_delete(self):
        """Supprime l'élément ET son sous-arbre — même règle qu'au canvas
        (Suppr) : la position d'un enfant étant relative à son conteneur, les
        orphelins ne resteraient pas en place, ils sauteraient ailleurs."""
        if not self._element or not self._layout_asset:
            return
        from core.history import get_history, RemoveListItemsCmd
        from core.selection_bus import get_bus
        lay = self._layout_asset
        victims = [self._element] + lay.descendants(self._element.name)
        n = len(victims)
        get_bus().clear()     # avant la persistance, qui réémet la sélection
        get_history().push(RemoveListItemsCmd(
            lay.elements, victims, persist_fn=self._persist,
            label=f"Delete {self._element.name}"
                  + (f" (+{n - 1} children)" if n > 1 else "")))
