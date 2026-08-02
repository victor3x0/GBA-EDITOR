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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QScrollArea,
    QSpinBox, QLineEdit, QPushButton, QCheckBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.project import Project
from core.text_markup import display_text
from core.color_utils import bgr555_to_rgb888
from core.models.ui_region import (
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, ALIGNS, TARGET_BG, TARGET_OBJ,
    KIND_REGION, KIND_PANEL, KIND_TEXT,
    FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG, fill_allowed,
    forced_target, forced_target_reason, surface_conflicts,
    unique_region_name, unique_element_name,
)
from ui.common.theme import C, T, QSS
from ui.common.widgets import W

_ANCHORS = [
    (ANCHOR_SCREEN, "Écran (fixe)"),
    (ANCHOR_WORLD,  "Monde (défile)"),
    (ANCHOR_ACTOR,  "Actor (suit)"),
]
_ALIGN_LABELS = ["Gauche", "Centré", "Droite"]
_TARGETS = [(TARGET_BG, "Fond (BG)"), (TARGET_OBJ, "Sprite (OBJ)")]
_FILL_LABELS = [
    (FILL_NONE,  "Aucun (groupe invisible)"),
    (FILL_COLOR, "Couleur (palette)"),
    (FILL_NINE,  "Nine-slice"),
    (FILL_BG,    "Background"),
]


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
        self._name.setFont(QFont(T.MONO, T.MD))
        self._name.setStyleSheet(QSS.lineedit)
        self._name.setToolTip("Nom cité par le script (constante REGION_* pour une zone)")
        self._name.editingFinished.connect(self._on_name)
        W.row("Nom", self._name, L)

        W.separator(L)

        # ── Ancrage (root uniquement — un enfant hérite) ──────────
        W.section("ANCRAGE", L)
        self._anchor = QComboBox()
        self._anchor.setFont(QFont(T.MONO, T.MD))
        self._anchor.setStyleSheet(QSS.combobox)
        for _, lab in _ANCHORS:
            self._anchor.addItem(lab)
        self._anchor.currentIndexChanged.connect(self._on_anchor)
        W.row("Ancrage", self._anchor, L)

        self._actor = QComboBox()
        self._actor.setFont(QFont(T.MONO, T.MD))
        self._actor.setStyleSheet(QSS.combobox)
        self._actor.currentIndexChanged.connect(self._on_actor)
        self._actor_row = W.row("Actor", self._actor, L).parentWidget()

        self._target = QComboBox()
        self._target.setFont(QFont(T.MONO, T.MD))
        self._target.setStyleSheet(QSS.combobox)
        for _, lab in _TARGETS:
            self._target.addItem(lab)
        self._target.currentIndexChanged.connect(self._on_target)
        self._target_row = W.row("Cible", self._target, L).parentWidget()

        self._frame_why = W.hint("", L)

        W.separator(L)

        # ── Géométrie ─────────────────────────────────────────────
        self._geom_lbl = W.section("GÉOMÉTRIE (PX)", L)
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
        W.pair("Taille", "L", C.AXIS_X, self._sp["w"],
               "H", C.AXIS_Y, self._sp["h"], L)
        self._size_lbl = W.hint("", L)

        # ── Section TEXTE (zone runtime ET texte authoré) ─────────
        self._text_sep = W.separator(L)
        self._text_title = W.section("TEXTE", L)

        self._text_key = QComboBox()
        self._text_key.setFont(QFont(T.MONO, T.MD))
        self._text_key.setStyleSheet(QSS.combobox)
        self._text_key.currentIndexChanged.connect(self._on_text_key)
        self._text_key_row = W.row("Texte", self._text_key, L).parentWidget()

        self._preview = QComboBox()
        self._preview.setFont(QFont(T.MONO, T.MD))
        self._preview.setStyleSheet(QSS.combobox)
        self._preview.setToolTip("Éditeur seulement : sert à mesurer le débordement, "
                                 "jamais compilé — le script décide du texte affiché.")
        self._preview.currentIndexChanged.connect(self._on_preview)
        self._preview_row = W.row("Aperçu", self._preview, L).parentWidget()

        self._font = QComboBox()
        self._font.setFont(QFont(T.MONO, T.MD))
        self._font.setStyleSheet(QSS.combobox)
        self._font.currentIndexChanged.connect(self._on_font)
        self._font_row = W.row("Police", self._font, L).parentWidget()

        self._align = QComboBox()
        self._align.setFont(QFont(T.MONO, T.MD))
        self._align.setStyleSheet(QSS.combobox)
        for lab in _ALIGN_LABELS:
            self._align.addItem(lab)
        self._align.currentIndexChanged.connect(self._on_align)
        self._align_row = W.row("Alignement", self._align, L).parentWidget()

        self._wrap = QCheckBox("Retour à la ligne")
        self._wrap.setFont(QFont(T.MONO, T.SM))
        self._wrap.setStyleSheet(QSS.checkbox)
        self._wrap.toggled.connect(self._on_wrap)
        self._wrap_row = W.row("Multiligne", self._wrap, L).parentWidget()

        self._anim = QSpinBox()
        self._anim.setFont(QFont(T.MONO, T.MD))
        self._anim.setStyleSheet(QSS.spinbox)
        self._anim.setRange(0, 32)
        self._anim.setKeyboardTracking(False)
        self._anim.setToolTip(
            "Combien de caractères, au plus, peuvent sortir de la bande pour "
            "recevoir un effet. Réservé au build (compté dans la jauge) ; "
            "au-delà, les glyphes retombent en statique.")
        self._anim.valueChanged.connect(self._on_anim)
        self._anim_row = W.row("Gl. animés", self._anim, L).parentWidget()

        # ── Section FOND (conteneur) ──────────────────────────────
        self._fill_sep = W.separator(L)
        self._fill_title = W.section("FOND", L)

        self._fill_kind = QComboBox()
        self._fill_kind.setFont(QFont(T.MONO, T.MD))
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
        self._fill_palette.setFont(QFont(T.MONO, T.SM))
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
        self._fill_color_row = W.row("Couleur", color_box, L).parentWidget()

        self._fill_asset = QComboBox()
        self._fill_asset.setFont(QFont(T.MONO, T.SM))
        self._fill_asset.setStyleSheet(QSS.combobox)
        self._fill_asset.currentIndexChanged.connect(self._on_fill_asset)
        self._fill_asset_row = W.row("Asset", self._fill_asset, L).parentWidget()

        # Sous-éditeur du cadre nine-slice sélectionné : image source + 4 marges
        # de coupe. Édite l'ASSET partagé (répercuté sur tous les panels qui le
        # référencent), d'où le persist projet.
        self._ns_source = QComboBox()
        self._ns_source.setFont(QFont(T.MONO, T.SM))
        self._ns_source.setStyleSheet(QSS.combobox)
        self._ns_source.currentIndexChanged.connect(self._on_ns_source)
        self._ns_source_row = W.row("Source", self._ns_source, L).parentWidget()

        ns_margins = QWidget()
        ns_margins.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(ns_margins)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(4)
        self._ns_m = {}
        for key, lab in (("left", "G"), ("right", "D"), ("top", "H"), ("bottom", "B")):
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
        self._ns_margins_row = W.row("Marges", ns_margins, L).parentWidget()

        self._ns_create = W.btn_ghost("Créer un cadre depuis un background…")
        self._ns_create.setFont(QFont(T.MONO, T.XS))
        self._ns_create.clicked.connect(self._on_ns_create)
        L.addWidget(self._ns_create)

        self._fill_why = W.hint("", L)

        # ── Diagnostic + suppression ──────────────────────────────
        self._warn = W.hint("", L, color=C.ACCENT_YLW)

        W.separator(L)
        self._del = W.btn_ghost("Supprimer l'élément")
        self._del.setFont(QFont(T.MONO, T.SM))
        self._del.clicked.connect(self._on_delete)
        L.addWidget(self._del)
        L.addStretch()

    # ── Chargement ────────────────────────────────────────────────
    def load(self, layout_asset, element, project: Project, scene):
        self._layout_asset, self._element = layout_asset, element
        self._project, self._scene = project, scene
        self._blocking = True
        try:
            kind = self._kind()
            self._name.setText(element.name)

            users = project.ui_layout_users(layout_asset.name) if project else []
            shared = (f"  ·  partagée par {len(users)} scènes" if len(users) > 1 else "")
            self._layout_lbl.setText(f"Mise en page : {layout_asset.name}{shared}")
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
            self._text_key_row.setVisible(is_text)
            self._preview_row.setVisible(is_region)
            self._font_row.setVisible(is_region or is_text)
            self._align_row.setVisible(is_region or is_text)
            self._wrap_row.setVisible(is_text)
            self._anim_row.setVisible(is_region)
            for w in (self._fill_sep, self._fill_title, self._fill_kind_row,
                      self._fill_color_row, self._fill_asset_row,
                      self._ns_source_row, self._ns_margins_row,
                      self._ns_create, self._fill_why):
                w.setVisible(is_panel)
            self._del.setText("Supprimer la zone" if is_region else "Supprimer l'élément")

            if is_region or is_text:
                self._reload_fonts()
                self._align.setCurrentIndex(
                    ALIGNS.index(element.align) if element.align in ALIGNS else 0)
            if is_region:
                self._reload_previews()
                self._anim.setValue(int(getattr(element, "animated_glyphs", 0) or 0))
            if is_text:
                self._reload_text_key()
                self._wrap.setChecked(bool(getattr(element, "wrap", False)))
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
        self._actor.addItems(names or ["(aucun actor)"])
        e = self._element
        anchor, actor = self._layout_asset.effective_anchor(e) if e else ("", "")
        self._anchor.setCurrentIndex(
            next((i for i, (a, _) in enumerate(_ANCHORS) if a == anchor), 0))
        if e and actor in names:
            self._actor.setCurrentIndex(names.index(actor))
        self._actor_row.setVisible(anchor == ANCHOR_ACTOR)

    def _reload_fonts(self):
        self._font.clear()
        self._font.addItem("(police de la scène)", "")
        for f in (self._project.fonts if self._project else []):
            self._font.addItem(f.name, f.name)
        i = self._font.findData(getattr(self._element, "font_name", "") or "")
        self._font.setCurrentIndex(i if i >= 0 else 0)

    def _reload_previews(self):
        self._preview.clear()
        self._preview.addItem("(aucun)", "")
        values = self._project.text_values() if self._project else {}
        for t in (self._project.texts if self._project else []):
            self._preview.addItem(
                f"{t.key} — {display_text(t.content, values)[:24]}", t.key)
        i = self._preview.findData(getattr(self._element, "preview_text", "") or "")
        self._preview.setCurrentIndex(i if i >= 0 else 0)

    def _reload_text_key(self):
        self._text_key.clear()
        self._text_key.addItem("(aucun)", "")
        for t in (self._project.texts if self._project else []):
            self._text_key.addItem(t.key, t.key)
        i = self._text_key.findData(getattr(self._element, "text_key", "") or "")
        self._text_key.setCurrentIndex(i if i >= 0 else 0)

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
                f"Hérité du root « {root.name if root else '?'} » — ancrage {eff_anchor}")
            self._frame_why.setStyleSheet(f"color:{C.TEXT_MUTED};")
        elif forced:
            self._frame_why.setText(f"Cible imposée — {forced_target_reason(eff_anchor, rm)}")
            self._frame_why.setStyleSheet(f"color:{C.ACCENT_YLW};")
        else:
            self._frame_why.setText("")

        # Le BG ne peut pas se poser hors grille : le pas des spinbox le dit.
        step = 8 if eff == TARGET_BG else 1
        for k in ("x", "y", "w", "h"):
            self._sp[k].setSingleStep(step)
        self._geom_lbl.setText(
            "GÉOMÉTRIE (PX, RELATIVE AU PARENT)" if not is_root
            else "GÉOMÉTRIE (PX, ALIGNÉE TUILE)" if eff == TARGET_BG
            else "GÉOMÉTRIE (PX, OFFSET ACTOR)" if eff_anchor == ANCHOR_ACTOR
            else "GÉOMÉTRIE (PX)")

    def _refresh_diagnostics(self):
        """Empreinte + avertissements — seulement pour une ZONE, seule à avoir
        une empreinte VRAM connue au build."""
        if self._kind() != KIND_REGION:
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
                f"{tw}×{th} tuiles  ·  {g['oam']} OAM et {g['tiles']} tuiles OBJ "
                f"({g['strip_oam']} de bande + {g['anim']} animé(s))")
        else:
            self._size_lbl.setText(f"{tw}×{th} tuiles  ·  {tw * th} tuiles d'empreinte")

        if target == TARGET_OBJ and eff_anchor == ANCHOR_ACTOR and not eff_actor:
            msgs.append("Ancrée sur un actor (via son root), mais aucun actor "
                        "choisi : la zone se posera à l'origine de l'écran.")
        # Aliasing de surface — seulement entre zones BG de la MÊME mise en page.
        others = [o for o in lay.regions
                  if o is not r and lay.resolved_target(o, rm) == TARGET_BG]
        if target == TARGET_BG and others:
            for a, b in surface_conflicts([r] + others):
                if a is r or b is r:
                    other = b if a is r else a
                    msgs.append(
                        f"Chevauchement de surface avec « {other.name} » : en police "
                        f"composée, deux zones distantes d'un multiple de 8 rangées "
                        f"partagent leurs tuiles et s'effacent mutuellement.")
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
            FILL_COLOR: "Une entrée de palette (index 0 = transparent au hardware).",
            FILL_NINE:  "Cadre étirable : coins fixes, bords/centre répétés.",
            FILL_BG:    "Fond tuilé, rogné en bas/à droite si la zone est plus "
                        "petite. Interdit sur cible OBJ.",
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
            self._ns_source.addItem("(background source)", "")
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
        self._set("name", new, f"Renommer {old}")
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
                        f"{total} référence(s) mise(s) à jour dans {len(hits)} script(s)")
            except Exception:
                pass   # le renommage du modèle reste valable même sans réécriture
        self._name.setText(self._element.name)

    def _on_anchor(self, i):
        if self._blocking or not self._element:
            return
        self._set("anchor", _ANCHORS[i][0], "Ancrage")
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
        self._set("anchor_actor", self._actor.currentText(), "Actor de l'élément")

    def _on_target(self, i):
        if self._blocking or not self._element:
            return
        self._set("target", _TARGETS[i][0], "Cible de la zone")
        self._refresh_diagnostics()

    def _on_geom(self, key: str, val: int):
        if self._blocking or not self._element:
            return
        self._set(key, int(val), "Géométrie")
        self._refresh_diagnostics()

    def _on_align(self, i):
        if self._blocking or not self._element:
            return
        self._set("align", ALIGNS[i], "Alignement")

    def _on_font(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("font_name", self._font.currentData() or "", "Police")

    def _on_preview(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("preview_text", self._preview.currentData() or "", "Aperçu de zone")

    def _on_text_key(self, i):
        if self._blocking or not self._element or i < 0:
            return
        self._set("text_key", self._text_key.currentData() or "", "Texte de l'élément")

    def _on_wrap(self, on):
        if self._blocking or not self._element:
            return
        self._set("wrap", bool(on), "Multiligne")

    def _on_anim(self, v):
        if self._blocking or not self._element:
            return
        self._set("animated_glyphs", int(v), "Glyphes animés de zone")
        self._refresh_diagnostics()

    # ── Fond : écritures ──────────────────────────────────────────
    def _fill_editable(self) -> bool:
        return bool(self._element) and self._kind() == KIND_PANEL

    def _on_fill_kind(self, i):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_kind", self._fill_kind.currentData() or FILL_NONE, "Fond du conteneur")
        self._blocking = True
        try:
            self._reload_fill_asset()
            self._sync_fill()
        finally:
            self._blocking = False

    def _on_fill_palette(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_palette", self._fill_palette.currentData() or "", "Palette du fond")
        self._update_swatch()

    def _on_fill_index(self, v):
        if self._blocking or not self._fill_editable():
            return
        self._set("fill_index", int(v), "Index du fond")
        self._update_swatch()

    def _on_fill_asset(self, i):
        if self._blocking or not self._fill_editable() or i < 0:
            return
        self._set("fill_asset", self._fill_asset.currentData() or "", "Asset du fond")
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
            self._set_ns(ns, "source", self._ns_source.currentData() or "", "Source du cadre")

    def _on_ns_margin(self, key, v):
        if self._blocking:
            return
        ns = self._current_ns()
        if ns is not None:
            self._set_ns(ns, key, int(v), "Marge du cadre")

    def _on_ns_create(self):
        """Crée un cadre depuis le premier background disponible, le sélectionne."""
        if not self._project or not self._fill_editable():
            return
        from core.models.nine_slice import NineSlice
        taken = {n.name for n in self._project.nine_slices}
        bgs = list(getattr(self._project, "backgrounds", []))
        ns = NineSlice(name=unique_element_name(taken, "cadre"),
                       source=bgs[0].name if bgs else "")
        self._project.nine_slices.items.append(ns)
        self._project.nine_slices.save(ns)
        self._set("fill_asset", ns.name, "Cadre du fond")
        self._reload_fill_asset()
        self._reload_ns()

    # ── Suppression ───────────────────────────────────────────────
    def _on_delete(self):
        if not self._element or not self._layout_asset:
            return
        from core.history import get_history, RemoveListItemCmd
        from core.selection_bus import get_bus
        get_history().push(RemoveListItemCmd(
            self._layout_asset.elements, self._element,
            persist_fn=self._persist, label=f"Supprimer {self._element.name}"))
        get_bus().clear()
