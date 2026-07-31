"""UIRegionInspector — édition d'une zone de texte sélectionnée dans le canvas.

La zone porte la GÉOMÉTRIE, jamais l'enchaînement : aucun champ ici ne dit quel
texte s'affiche ni quand. `preview_text` ne sert qu'à mesurer à la conception —
il n'est pas compilé (cf. models/ui_region.py, et le refus de l'éditeur de
dialogue tenu depuis ROADMAP v0.3.2).

**La cible n'est pas un menu quand elle est contrainte.** Un ancrage sur actor
impose OBJ (un acteur bouge au pixel, la grille BG avance par 8), un mode
bitmap aussi (il n'y a plus de tilemap). Dans ces cas le champ affiche la valeur
ET sa raison au lieu d'offrir un choix qui ne peut pas exister.
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QScrollArea,
    QSpinBox, QLineEdit, QPushButton,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from core.project import Project
from core.text_markup import display_text
from core.models.ui_region import (
    ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR, ALIGNS, TARGET_BG, TARGET_OBJ,
    forced_target, forced_target_reason, surface_conflicts, unique_region_name,
)
from ui.common.theme import C, T, QSS

_ANCHORS = [
    (ANCHOR_SCREEN, "Écran (fixe)"),
    (ANCHOR_WORLD,  "Monde (défile)"),
    (ANCHOR_ACTOR,  "Actor (suit)"),
]
_ALIGN_LABELS = ["Gauche", "Centré", "Droite"]
_TARGETS = [(TARGET_BG, "Fond (BG)"), (TARGET_OBJ, "Sprite (OBJ)")]


class UIRegionInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._layout_asset = None      # UILayout portant la zone
        self._region = None
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
        L.setSpacing(10)
        scroll.setWidget(inner)

        f = QFont(T.MONO, T.SM)

        def sect(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(f)
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            return lbl

        def sep() -> QFrame:
            s = QFrame()
            s.setFrameShape(QFrame.Shape.HLine)
            s.setStyleSheet(f"color:{C.BORDER};")
            return s

        # ── Mise en page d'appartenance ───────────────────────────
        self._layout_lbl = QLabel("")
        self._layout_lbl.setFont(QFont(T.MONO, T.XS))
        self._layout_lbl.setWordWrap(True)
        L.addWidget(self._layout_lbl)

        # ── Nom ───────────────────────────────────────────────────
        L.addWidget(sect("Nom (cité par le script) :"))
        self._name = QLineEdit()
        self._name.setFont(QFont(T.MONO, T.MD))
        self._name.setStyleSheet(QSS.lineedit)
        self._name.editingFinished.connect(self._on_name)
        L.addWidget(self._name)

        L.addWidget(sep())

        # ── Ancrage ───────────────────────────────────────────────
        L.addWidget(sect("Ancrage :"))
        self._anchor = QComboBox()
        self._anchor.setFont(QFont(T.MONO, T.MD))
        self._anchor.setStyleSheet(QSS.combobox)
        for _, lab in _ANCHORS:
            self._anchor.addItem(lab)
        self._anchor.currentIndexChanged.connect(self._on_anchor)
        L.addWidget(self._anchor)

        self._actor = QComboBox()
        self._actor.setFont(QFont(T.MONO, T.MD))
        self._actor.setStyleSheet(QSS.combobox)
        self._actor.currentIndexChanged.connect(self._on_actor)
        L.addWidget(self._actor)

        # ── Cible (dérivée quand contrainte) ──────────────────────
        L.addWidget(sect("Cible de rendu :"))
        self._target = QComboBox()
        self._target.setFont(QFont(T.MONO, T.MD))
        self._target.setStyleSheet(QSS.combobox)
        for _, lab in _TARGETS:
            self._target.addItem(lab)
        self._target.currentIndexChanged.connect(self._on_target)
        L.addWidget(self._target)

        self._target_why = QLabel("")
        self._target_why.setFont(QFont(T.MONO, T.XS))
        self._target_why.setWordWrap(True)
        L.addWidget(self._target_why)

        L.addWidget(sep())

        # ── Géométrie ─────────────────────────────────────────────
        self._geom_lbl = sect("Géométrie (px) :")
        L.addWidget(self._geom_lbl)
        grid = QHBoxLayout()
        self._sp = {}
        for key, lab, lo, hi in (("x", "X", -512, 512), ("y", "Y", -512, 512),
                                 ("w", "L", 8, 512),    ("h", "H", 8, 512)):
            col = QVBoxLayout()
            t = QLabel(lab); t.setFont(QFont(T.MONO, T.XS))
            t.setStyleSheet(f"color:{C.TEXT_MUTED};")
            s = QSpinBox()
            s.setFont(QFont(T.MONO, T.MD))
            s.setStyleSheet(QSS.spinbox)
            s.setRange(lo, hi)
            # Sans ça, taper « 120 » vaut trois valeurs (1, 12, 120) : trois
            # écritures disque et trois redessins du canvas pour un seul geste.
            # La valeur part à Entrée, à la perte du focus ou aux flèches.
            s.setKeyboardTracking(False)
            s.valueChanged.connect(lambda v, k=key: self._on_geom(k, v))
            col.addWidget(t); col.addWidget(s)
            grid.addLayout(col)
            self._sp[key] = s
        L.addLayout(grid)

        self._size_lbl = QLabel("")
        self._size_lbl.setFont(QFont(T.MONO, T.XS))
        self._size_lbl.setWordWrap(True)
        L.addWidget(self._size_lbl)

        L.addWidget(sep())

        # ── Typographie ───────────────────────────────────────────
        L.addWidget(sect("Alignement :"))
        self._align = QComboBox()
        self._align.setFont(QFont(T.MONO, T.MD))
        self._align.setStyleSheet(QSS.combobox)
        for lab in _ALIGN_LABELS:
            self._align.addItem(lab)
        self._align.currentIndexChanged.connect(self._on_align)
        L.addWidget(self._align)

        L.addWidget(sect("Police :"))
        self._font = QComboBox()
        self._font.setFont(QFont(T.MONO, T.MD))
        self._font.setStyleSheet(QSS.combobox)
        self._font.currentIndexChanged.connect(self._on_font)
        L.addWidget(self._font)

        L.addWidget(sect("Texte d'aperçu (éditeur seulement) :"))
        self._preview = QComboBox()
        self._preview.setFont(QFont(T.MONO, T.MD))
        self._preview.setStyleSheet(QSS.combobox)
        self._preview.currentIndexChanged.connect(self._on_preview)
        L.addWidget(self._preview)

        L.addWidget(sect("Glyphes animés réservés :"))
        self._anim = QSpinBox()
        self._anim.setFont(QFont(T.MONO, T.MD))
        self._anim.setStyleSheet(QSS.spinbox)
        self._anim.setRange(0, 32)
        self._anim.valueChanged.connect(self._on_anim)
        L.addWidget(self._anim)
        anim_help = QLabel(
            "Combien de caractères, au plus, peuvent sortir de la bande pour "
            "recevoir un effet. Réservé au build, donc compté dans la jauge ; "
            "au-delà, les glyphes retombent en statique."
        )
        anim_help.setFont(QFont(T.MONO, T.XS))
        anim_help.setStyleSheet(f"color:{C.TEXT_MUTED};")
        anim_help.setWordWrap(True)
        L.addWidget(anim_help)

        # ── Diagnostic ────────────────────────────────────────────
        self._warn = QLabel("")
        self._warn.setFont(QFont(T.MONO, T.XS))
        self._warn.setWordWrap(True)
        L.addWidget(self._warn)

        L.addWidget(sep())
        self._del = QPushButton("Supprimer la zone")
        self._del.setFont(QFont(T.MONO, T.SM))
        self._del.setStyleSheet(QSS.button_ghost)
        self._del.clicked.connect(self._on_delete)
        L.addWidget(self._del)

        L.addStretch()

    # ── Chargement ────────────────────────────────────────────────
    def load(self, layout_asset, region, project: Project, scene):
        self._layout_asset, self._region = layout_asset, region
        self._project, self._scene = project, scene
        self._blocking = True
        try:
            self._name.setText(region.name)

            users = project.ui_layout_users(layout_asset.name) if project else []
            shared = (f"  ·  partagée par {len(users)} scènes" if len(users) > 1 else "")
            self._layout_lbl.setText(f"Mise en page : {layout_asset.name}{shared}")
            # Le partage se signale en couleur : modifier ici touche N scènes.
            self._layout_lbl.setStyleSheet(
                f"color:{C.ACCENT_YLW};" if len(users) > 1 else f"color:{C.TEXT_MUTED};")

            self._anchor.setCurrentIndex(
                next((i for i, (a, _) in enumerate(_ANCHORS) if a == region.anchor), 0))
            self._reload_actors()
            self._reload_fonts()
            self._reload_previews()
            for k in ("x", "y", "w", "h"):
                self._sp[k].setValue(int(getattr(region, k)))
            self._align.setCurrentIndex(
                ALIGNS.index(region.align) if region.align in ALIGNS else 0)
            self._anim.setValue(int(getattr(region, "animated_glyphs", 0) or 0))
            self._sync_target()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    def _render_mode(self) -> int:
        return int(getattr(self._scene, "render_mode", 0) or 0)

    def _reload_actors(self):
        self._actor.clear()
        names = [a.name for a in getattr(self._scene, "actors", [])] if self._scene else []
        self._actor.addItems(names or ["(aucun actor)"])
        r = self._region
        if r and r.anchor_actor in names:
            self._actor.setCurrentIndex(names.index(r.anchor_actor))
        self._actor.setVisible(r is not None and r.anchor == ANCHOR_ACTOR)

    def _reload_fonts(self):
        self._font.clear()
        self._font.addItem("(police de la scène)", "")
        for f in (self._project.fonts if self._project else []):
            self._font.addItem(f.name, f.name)
        want = self._region.font_name if self._region else ""
        i = self._font.findData(want)
        self._font.setCurrentIndex(i if i >= 0 else 0)

    def _reload_previews(self):
        self._preview.clear()
        self._preview.addItem("(aucun)", "")
        values = self._project.text_values() if self._project else {}
        for t in (self._project.texts if self._project else []):
            self._preview.addItem(
                f"{t.key} — {display_text(t.content, values)[:24]}", t.key)
        i = self._preview.findData(self._region.preview_text if self._region else "")
        self._preview.setCurrentIndex(i if i >= 0 else 0)

    def _sync_target(self):
        """Affiche la cible ; la verrouille quand le matériel l'impose."""
        r, rm = self._region, self._render_mode()
        forced = forced_target(r.anchor, rm)
        eff = r.resolved_target(rm)
        self._target.setCurrentIndex(
            next((i for i, (t, _) in enumerate(_TARGETS) if t == eff), 0))
        self._target.setEnabled(forced is None)
        if forced:
            self._target_why.setText(f"Imposée — {forced_target_reason(r.anchor, rm)}")
            self._target_why.setStyleSheet(f"color:{C.ACCENT_YLW};")
        else:
            self._target_why.setText("")
        # Le BG ne peut pas se poser hors grille : le pas des spinbox le dit.
        step = 8 if eff == TARGET_BG else 1
        for k in ("x", "y", "w", "h"):
            self._sp[k].setSingleStep(step)
        self._geom_lbl.setText(
            "Géométrie (px, alignée tuile) :" if eff == TARGET_BG
            else "Géométrie (px, offset depuis l'actor) :" if r.anchor == ANCHOR_ACTOR
            else "Géométrie (px) :")

    def _refresh_diagnostics(self):
        r, rm = self._region, self._render_mode()
        tx, ty, tw, th = r.tile_rect()
        msgs = []
        if r.resolved_target(rm) == TARGET_OBJ:
            from core.models.ui_region import strip_geometry
            g = strip_geometry(r)
            self._size_lbl.setText(
                f"{tw}×{th} tuiles  ·  {g['oam']} OAM et {g['tiles']} tuiles OBJ "
                f"({g['strip_oam']} de bande + {g['anim']} animé(s))")
        else:
            self._size_lbl.setText(f"{tw}×{th} tuiles  ·  {tw * th} tuiles d'empreinte")
        self._size_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")

        if r.resolved_target(rm) == TARGET_OBJ and r.anchor == ANCHOR_ACTOR                 and not r.anchor_actor:
            msgs.append("Ancrée sur un actor, mais aucun actor choisi : la zone "
                        "se posera à l'origine de l'écran.")
        # Aliasing de surface — seulement entre zones BG de la MÊME mise en page.
        others = [o for o in self._layout_asset.regions
                  if o is not r and o.resolved_target(rm) == TARGET_BG]
        if r.resolved_target(rm) == TARGET_BG and others:
            for a, b in surface_conflicts([r] + others):
                if a is r or b is r:
                    other = b if a is r else a
                    msgs.append(
                        f"Chevauchement de surface avec « {other.name} » : en police "
                        f"composée, deux zones distantes d'un multiple de 8 rangées "
                        f"partagent leurs tuiles et s'effacent mutuellement.")
                    break
        self._warn.setText("\n\n".join(msgs))
        self._warn.setStyleSheet(f"color:{C.ACCENT_YLW};" if msgs else "")

    # ── Édition (toutes les écritures passent par l'historique) ────
    def _persist(self):
        # Par le dispatcher, jamais `project.save()` en direct : il suspend le
        # watcher de fichiers le temps de l'écriture. Sans ça le watcher voit le
        # JSON changer, croit à une édition externe et fait recharger la scène —
        # ce qui rebascule l'inspecteur sur la scène (window._on_scene_file_changed)
        # et fait perdre la zone en cours d'édition à chaque champ modifié.
        if self._project:
            from core.command_dispatcher import get_dispatcher
            get_dispatcher().save_all()
        self.changed.emit()

    def _set(self, field: str, value, label: str):
        from core.history import get_history, SetFieldCmd
        old = getattr(self._region, field)
        if old == value:
            return
        get_history().push(SetFieldCmd(self._region, field, old, value,
                                       label=label, persist_fn=self._persist))

    def _on_name(self):
        if self._blocking or not self._region:
            return
        new = self._name.text().strip()
        if not new or new == self._region.name:
            self._name.setText(self._region.name)
            return
        taken = set(self._project.region_names()) - {self._region.name}
        if new in taken:
            new = unique_region_name(taken, new)
        # Le nom se résout en REGION_* : le renommer doit réécrire les scripts
        # qui le citent, comme pour une clé de texte.
        old = self._region.name
        self._set("name", new, f"Renommer zone {old}")
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
        self._name.setText(self._region.name)

    def _on_anchor(self, i):
        if self._blocking or not self._region:
            return
        self._set("anchor", _ANCHORS[i][0], "Ancrage de zone")
        self._blocking = True
        try:
            self._reload_actors()
            self._sync_target()
            self._refresh_diagnostics()
        finally:
            self._blocking = False

    def _on_actor(self, i):
        if self._blocking or not self._region or i < 0:
            return
        self._set("anchor_actor", self._actor.currentText(), "Actor de la zone")

    def _on_target(self, i):
        if self._blocking or not self._region:
            return
        self._set("target", _TARGETS[i][0], "Cible de la zone")
        self._refresh_diagnostics()

    def _on_geom(self, key: str, val: int):
        if self._blocking or not self._region:
            return
        self._set(key, int(val), "Géométrie de zone")
        self._refresh_diagnostics()

    def _on_align(self, i):
        if self._blocking or not self._region:
            return
        self._set("align", ALIGNS[i], "Alignement de zone")

    def _on_font(self, i):
        if self._blocking or not self._region or i < 0:
            return
        self._set("font_name", self._font.currentData() or "", "Police de zone")

    def _on_preview(self, i):
        if self._blocking or not self._region or i < 0:
            return
        self._set("preview_text", self._preview.currentData() or "", "Aperçu de zone")

    def _on_anim(self, v):
        if self._blocking or not self._region:
            return
        self._set("animated_glyphs", int(v), "Glyphes animés de zone")
        self._refresh_diagnostics()

    def _on_delete(self):
        if not self._region or not self._layout_asset:
            return
        from core.history import get_history, RemoveListItemCmd
        from core.selection_bus import get_bus
        get_history().push(RemoveListItemCmd(
            self._layout_asset.regions, self._region,
            persist_fn=self._persist, label=f"Supprimer zone {self._region.name}"))
        get_bus().clear()
