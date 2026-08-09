"""UIInspector — édition de N'IMPORTE QUEL élément d'une mise en page UI
(zone de texte runtime, conteneur, texte authoré), sélectionné dans l'arbre ou
le canvas.

UN inspecteur adaptatif, pas un par type : nom, ancrage et géométrie sont les
mêmes champs pour les trois kinds — les dupliquer dans deux classes (l'état
d'avant) garantissait leur divergence. Les sections spécifiques (bande/glyphes
d'une zone, fond d'un conteneur, clé de texte d'un texte) se montrent ou se
cachent au chargement, comme les MODE_INFO du SceneInspector.

Écrit dans la grammaire `W` (labels à gauche, paires d'axes colorées) — la même
que tous les autres inspecteurs, pour que l'UI ne soit pas un écran étranger.

Les invariants métier restent ceux des modèles (models/ui_region.py) :
  • la zone porte la GÉOMÉTRIE, jamais l'enchaînement (pas d'éditeur de dialogue) ;
  • l'ancrage n'est éditable que sur un ROOT — un enfant l'hérite ;
  • la cible n'est pas un menu quand elle est contrainte (actor → OBJ, bitmap →
    OBJ) : le champ affiche la valeur ET sa raison.
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
from core.color_utils import bgr555_to_rgb888
from core.models.ui_region import (
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, ALIGNS, TARGET_BG, TARGET_OBJ,
    KIND_REGION, KIND_PANEL, KIND_TEXT,
    FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG, fill_allowed,
    forced_target, forced_target_reason, surface_conflicts,
    unique_region_name, unique_element_name,
    preset_rect, H_LEFT, H_CENTER, H_RIGHT, V_TOP, V_MIDDLE, V_BOTTOM,
)
from ui.common import icons
from ui.common.theme import C, T, QSS
from ui.common.widgets import W

_ANCHORS = [
    (ANCHOR_SCREEN, "Screen (fixed)"),
    (ANCHOR_WORLD,  "World (scrolls)"),
    (ANCHOR_ACTOR,  "Actor (follows)"),
]
_ALIGN_LABELS = ["Left", "Centered", "Right"]
_TARGETS = [(TARGET_BG, "Background (BG)"), (TARGET_OBJ, "Sprite (OBJ)")]
_FILL_LABELS = [
    (FILL_NONE,  "None (invisible group)"),
    (FILL_COLOR, "Color (palette)"),
    (FILL_NINE,  "Nine-slice"),
    (FILL_BG,    "Background"),
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

        # ── Identité ──────────────────────────────────────────────
        self._name = QLineEdit()
        self._name.setFont(QFont(T.UI, T.MD))
        self._name.setStyleSheet(QSS.lineedit)
        self._name.setToolTip("Name referenced by the script (REGION_* constant for a zone)")
        self._name.editingFinished.connect(self._on_name)
        W.row("Name", self._name, L)

        W.separator(L)

        # ── Ancrage (root uniquement — un enfant hérite) ──────────
        W.section("ANCHOR", L)
        self._anchor = QComboBox()
        self._anchor.setFont(QFont(T.UI, T.MD))
        self._anchor.setStyleSheet(QSS.combobox)
        for _, lab in _ANCHORS:
            self._anchor.addItem(lab)
        self._anchor.currentIndexChanged.connect(self._on_anchor)
        W.row("Anchor", self._anchor, L)

        self._actor = QComboBox()
        self._actor.setFont(QFont(T.UI, T.MD))
        self._actor.setStyleSheet(QSS.combobox)
        self._actor.currentIndexChanged.connect(self._on_actor)
        self._actor_row = W.row("Actor", self._actor, L).parentWidget()

        self._target = QComboBox()
        self._target.setFont(QFont(T.UI, T.MD))
        self._target.setStyleSheet(QSS.combobox)
        for _, lab in _TARGETS:
            self._target.addItem(lab)
        self._target.currentIndexChanged.connect(self._on_target)
        self._target_row = W.row("Target", self._target, L).parentWidget()

        self._frame_why = W.hint("", L)

        W.separator(L)

        # ── Géométrie ─────────────────────────────────────────────
        self._geom_lbl = W.section("GEOMETRY (PX)", L)

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
        W.row("Place", self._presets, L)
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
               "Y", C.AXIS_Y, self._sp["y"], L)
        W.pair("Size", "L", C.AXIS_X, self._sp["w"],
               "H", C.AXIS_Y, self._sp["h"], L)
        self._size_lbl = W.hint("", L)

        # ── Section TEXTE (zone runtime ET texte authoré) ─────────
        self._text_sep = W.separator(L)
        self._text_title = W.section("TEXT", L)

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
        L.addWidget(self._content)

        self._key_lbl = W.hint("", L)

        self._text_key = QComboBox()
        self._text_key.setFont(QFont(T.UI, T.SM))
        self._text_key.setStyleSheet(QSS.combobox)
        self._text_key.setToolTip(
            "Bind this element to another existing entry — to share one label "
            "between several screens.")
        self._text_key.currentIndexChanged.connect(self._on_text_key)
        self._text_key_row = W.row("Entry", self._text_key, L).parentWidget()

        self._preview = QComboBox()
        self._preview.setFont(QFont(T.UI, T.MD))
        self._preview.setStyleSheet(QSS.combobox)
        self._preview.setToolTip("Editor only: used to measure overflow, "
                                 "never compiled — the script decides the displayed text.")
        self._preview.currentIndexChanged.connect(self._on_preview)
        self._preview_row = W.row("Preview", self._preview, L).parentWidget()

        self._font = QComboBox()
        self._font.setFont(QFont(T.UI, T.MD))
        self._font.setStyleSheet(QSS.combobox)
        self._font.currentIndexChanged.connect(self._on_font)
        self._font_row = W.row("Font", self._font, L).parentWidget()

        self._align = QComboBox()
        self._align.setFont(QFont(T.UI, T.MD))
        self._align.setStyleSheet(QSS.combobox)
        for lab in _ALIGN_LABELS:
            self._align.addItem(lab)
        self._align.currentIndexChanged.connect(self._on_align)
        self._align_row = W.row("Alignment", self._align, L).parentWidget()

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
        self._color_row = W.row("Color", self._color, L).parentWidget()

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
        self._anim_row = W.row("Anim. gl.", self._anim, L).parentWidget()

        # ── Section FOND (conteneur) ──────────────────────────────
        self._fill_sep = W.separator(L)
        self._fill_title = W.section("BACKGROUND", L)

        self._fill_kind = QComboBox()
        self._fill_kind.setFont(QFont(T.UI, T.MD))
        self._fill_kind.setStyleSheet(QSS.combobox)
        for k, lab in _FILL_LABELS:
            self._fill_kind.addItem(lab, k)
        self._fill_kind.currentIndexChanged.connect(self._on_fill_kind)
        self._fill_kind_row = W.row("Mode", self._fill_kind, L).parentWidget()

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
        self._fill_color_row = W.row("Color", color_box, L).parentWidget()

        self._fill_asset = QComboBox()
        self._fill_asset.setFont(QFont(T.UI, T.SM))
        self._fill_asset.setStyleSheet(QSS.combobox)
        self._fill_asset.currentIndexChanged.connect(self._on_fill_asset)
        self._fill_asset_row = W.row("Asset", self._fill_asset, L).parentWidget()

        # Sous-éditeur du cadre nine-slice sélectionné : image source + 4 marges
        # de coupe. Édite l'ASSET partagé (répercuté sur tous les panels qui le
        # référencent), d'où le persist projet.
        self._ns_source = QComboBox()
        self._ns_source.setFont(QFont(T.UI, T.SM))
        self._ns_source.setStyleSheet(QSS.combobox)
        self._ns_source.currentIndexChanged.connect(self._on_ns_source)
        self._ns_source_row = W.row("Source", self._ns_source, L).parentWidget()

        ns_margins = QWidget()
        ns_margins.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(ns_margins)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(4)
        self._ns_m = {}
        for key, lab in (("left", "L"), ("right", "R"), ("top", "T"), ("bottom", "B")):
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
        self._ns_margins_row = W.row("Margins", ns_margins, L).parentWidget()

        self._ns_create = W.btn_ghost("Create a frame from a background…")
        self._ns_create.setFont(QFont(T.UI, T.XS))
        self._ns_create.clicked.connect(self._on_ns_create)
        L.addWidget(self._ns_create)

        self._fill_why = W.hint("", L)

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
            self._name.setText(element.name)

            users = project.ui_layout_users(layout_asset.name) if project else []
            shared = (f"  ·  shared by {len(users)} scenes" if len(users) > 1 else "")
            self._layout_lbl.setText(f"Layout: {layout_asset.name}{shared}")
            self._layout_lbl.setStyleSheet(
                f"color:{C.ACCENT_YLW};" if len(users) > 1 else f"color:{C.TEXT_MUTED};")

            self._reload_actors()
            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(element, k, 0)))

            # Sections par type — tout se montre/cache ICI, une seule fois.
            is_region, is_text, is_panel = (
                kind == KIND_REGION, kind == KIND_TEXT, kind == KIND_PANEL)
            self._target_row.setVisible(is_region)
            self._text_sep.setVisible(is_region or is_text)
            self._text_title.setVisible(is_region or is_text)
            self._content.setVisible(is_text)
            self._key_lbl.setVisible(is_text)
            self._text_key_row.setVisible(is_text)
            self._preview_row.setVisible(is_region)
            self._font_row.setVisible(is_region or is_text)
            self._align_row.setVisible(is_region or is_text)
            self._color_row.setVisible(is_region or is_text)
            self._anim_row.setVisible(is_region)
            for w in (self._fill_sep, self._fill_title, self._fill_kind_row,
                      self._fill_color_row, self._fill_asset_row,
                      self._ns_source_row, self._ns_margins_row,
                      self._ns_create, self._fill_why):
                w.setVisible(is_panel)
            self._del.setText("Delete zone" if is_region else "Delete element")

            if is_region or is_text:
                self._reload_fonts()
                self._align.setCurrentIndex(
                    ALIGNS.index(element.align) if element.align in ALIGNS else 0)
                self._reload_color()
            if is_region:
                self._reload_previews()
                self._anim.setValue(int(getattr(element, "animated_glyphs", 0) or 0))
            if is_text:
                self._reload_text_key()
                self._reload_content()
            if is_panel:
                self._reload_fill()

            self._sync_frame()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    # ── Contexte ──────────────────────────────────────────────────
    def _kind(self) -> str:
        return getattr(self._element, "kind", KIND_REGION)

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
        if self._kind() == KIND_REGION:
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
        self._geom_lbl.setText(
            "GEOMETRY (PX, RELATIVE TO PARENT)" if not is_root
            else "GEOMETRY (PX, TILE-ALIGNED)" if eff == TARGET_BG
            else "GEOMETRY (PX, ACTOR OFFSET)" if eff_anchor == ANCHOR_ACTOR
            else "GEOMETRY (PX)")

    def _refresh_diagnostics(self):
        """Empreinte + avertissements des éléments qui accueillent du texte.

        Zone ET texte authoré : tous deux occupent une entrée de `g_ui_regions`
        et la même VRAM (cf. KIND_SLOTS). Un conteneur, non."""
        if self._kind() not in (KIND_REGION, KIND_TEXT):
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
                        "chosen: the zone will land at the screen origin.")
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
        self._sync_fill()

    def _reload_fill_asset(self):
        """Peuple le combo d'asset selon le mode : cadres nine-slice, ou fonds
        (backgrounds). blockSignals pour ne pas écraser `fill_asset` pendant le
        repeuplement."""
        fk = self._fill_kind.currentData()
        self._fill_asset.blockSignals(True)
        self._fill_asset.clear()
        self._fill_asset.addItem("(asset)", "")
        if fk == FILL_NINE:
            for n in (self._project.nine_slices if self._project else []):
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
        for w in (self._ns_source_row, self._ns_margins_row, self._ns_create):
            w.setVisible(fk == FILL_NINE)
        if fk == FILL_NINE:
            self._reload_ns()
        note = {
            FILL_COLOR: "A palette entry (index 0 = transparent on hardware).",
            FILL_NINE:  "Stretchable frame: fixed corners, repeated edges/center.",
            FILL_BG:    "Tiled background, cropped on bottom/right if the zone is "
                        "smaller. Not allowed on OBJ target.",
        }.get(fk, "")
        self._fill_why.setText(note)
        self._update_swatch()

    def _current_ns(self):
        if not self._project:
            return None
        return self._project.get_nine_slice(getattr(self._element, "fill_asset", "") or "")

    def _reload_ns(self):
        """Charge source + marges du cadre sélectionné ; grise si aucun."""
        prev, self._blocking = self._blocking, True
        try:
            self._ns_source.clear()
            self._ns_source.addItem("(source background)", "")
            for b in (getattr(self._project, "backgrounds", []) if self._project else []):
                self._ns_source.addItem(b.name, b.name)
            ns = self._current_ns()
            has = ns is not None
            for w in (self._ns_source, *self._ns_m.values()):
                w.setEnabled(has)
            if has:
                si = self._ns_source.findData(ns.source or "")
                self._ns_source.setCurrentIndex(si if si >= 0 else 0)
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

    def _set(self, field: str, value, label: str):
        from core.history import get_history, SetFieldCmd
        old = getattr(self._element, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(self._element, field, old, value,
                                       label=label, persist_fn=self._persist))

    def _on_name(self):
        if self._blocking or not self._element:
            return
        new = self._name.text().strip()
        if not new or new == self._element.name:
            self._name.setText(self._element.name)
            return
        is_region = self._kind() == KIND_REGION
        # Unicité : l'espace des constantes REGION_* est le PROJET pour une
        # zone ; pour les autres, la mise en page élargie aux zones du projet.
        if is_region:
            taken = set(self._project.region_names()) - {self._element.name}
            if new in taken:
                new = unique_region_name(taken, new)
        else:
            taken = (set(self._layout_asset.element_names())
                     | set(self._project.region_names())) - {self._element.name}
            if new in taken:
                new = unique_element_name(taken, new)
        old = self._element.name
        # Les enfants pointent le parent par NOM : les rebrancher AVANT le
        # changement de nom, pour que la commande qui suit (et son persist) les
        # sauve dans la foulée.
        self._layout_asset.retarget_parent(old, new)
        self._set("name", new, f"Rename {old}")
        if is_region:
            # Le nom se résout en REGION_* : le renommer doit réécrire les
            # scripts qui le citent, comme pour une clé de texte.
            try:
                from scripting.refactor import rename_in_project
                from scripting.api import DOMAIN_REGION
                hits = rename_in_project(self._project, DOMAIN_REGION, old, new)
                total = sum(hits.values())
                if total:
                    from core.command_dispatcher import get_dispatcher
                    get_dispatcher().status(
                        f"{total} reference(s) updated in {len(hits)} script(s)")
            except Exception:
                pass   # le renommage du modèle reste valable même sans réécriture
        self._name.setText(self._element.name)

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

    def _on_ns_source(self, i):
        if self._blocking or i < 0:
            return
        ns = self._current_ns()
        if ns is not None:
            self._set_ns(ns, "source", self._ns_source.currentData() or "", "Frame source")

    def _on_ns_margin(self, key, v):
        if self._blocking:
            return
        ns = self._current_ns()
        if ns is not None:
            self._set_ns(ns, key, int(v), "Frame margin")

    def _on_ns_create(self):
        """Crée un cadre depuis le premier background disponible, le sélectionne."""
        if not self._project or not self._fill_editable():
            return
        from core.models.nine_slice import NineSlice
        taken = {n.name for n in self._project.nine_slices}
        bgs = list(getattr(self._project, "backgrounds", []))
        ns = NineSlice(name=unique_element_name(taken, "frame"),
                       source=bgs[0].name if bgs else "")
        self._project.nine_slices.items.append(ns)
        self._project.nine_slices.save(ns)
        self._set("fill_asset", ns.name, "Background frame")
        self._reload_fill_asset()
        self._reload_ns()

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
