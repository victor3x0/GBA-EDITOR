"""Éditeur du CollisionBoxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.common.widgets import W
from ui.common.notice import notice
from ui.common.labels import label
from ui.common.theme import C, T, QSS


@register("collision_box")
class CollisionEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        is_solid = getattr(comp, "solid", True)

        # ── Tag ─────────────────────────────────────────────────────
        # Distinct de l'"id" de la meta_bar : l'id distingue les boxes de
        # CET acteur (utile avec plusieurs CollisionBoxComponent, ex.
        # "head_hurtbox" / "body_hurtbox") ; le tag est le GROUPE de
        # collision, partagé entre acteurs, celui que lit la matrice de
        # Project Settings > Collisions et que le codegen émet en
        # BOXTAG_<TAG> (cf. codegen/runtime_codegen/headers.py). Les deux
        # étaient confondus avant le tag registry (2026-08-25) — plus
        # aujourd'hui, chacun peut varier indépendamment.
        proj = self.insp._project
        tag_combo = QComboBox()
        tag_combo.setEditable(True)
        tag_combo.setStyleSheet(QSS.combobox)
        current = getattr(comp, "tag", "body") or "body"
        for t in proj.collision_tags():
            tag_combo.addItem(t)
        if tag_combo.findText(current) < 0:
            tag_combo.addItem(current)
        tag_combo.setCurrentText(current)
        notice("collision.tag", tag_combo, layout)

        def _commit_tag():
            self.set_field(comp, "tag", tag_combo.currentText().strip() or "body")

        tag_combo.lineEdit().editingFinished.connect(_commit_tag)
        tag_combo.activated.connect(lambda _i: _commit_tag())
        self.register_syncer("tag", lambda v, w=tag_combo: (
            w.blockSignals(True), w.setCurrentText(str(v) or "body"), w.blockSignals(False)))
        W.row(label("comped.tag"), tag_combo, layout)

        # ── Mode Solid / Trigger ──────────────────────────────────
        chk_solid = QCheckBox()
        chk_solid.setChecked(is_solid)
        notice("collision.solid", chk_solid, layout)

        mode_lbl = QWidget()
        hl = QHBoxLayout(mode_lbl); hl.setSpacing(6); hl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label("comped.collision_solid"))
        lbl.setFont(QFont(T.UI, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent; border:none;")
        hl.addWidget(chk_solid); hl.addWidget(lbl); hl.addStretch()
        W.row(label("comped.mode"), mode_lbl, layout)

        # ── AABB — champs px/tile ou référence de variable ────────
        # Les valeurs peuvent être un littéral (px/tile) ou pointer une
        # variable déclarée (global g_<nom> / constante CONST_<NOM>).
        vf_x = W.value_field(getattr(comp, "x", 0), project=proj)
        vf_y = W.value_field(getattr(comp, "y", 0), project=proj)
        vf_w = W.value_field(getattr(comp, "w", 16), project=proj, min_px=1)
        vf_h = W.value_field(getattr(comp, "h", 16), project=proj, min_px=1)

        # La clé de notice est ÉCRITE, pas construite : `f"collision.{fname}"`
        # se lit bien mais échappe au contrôle catalogue ↔ code, qui ne sait
        # pas à quoi il se résoudra.
        for vf, fname, key in ((vf_x, "x", "collision.x"),
                               (vf_y, "y", "collision.y"),
                               (vf_w, "w", "collision.w"),
                               (vf_h, "h", "collision.h")):
            vf.changed.connect(lambda raw, f=fname: self.set_field(comp, f, raw))
            self.register_syncer(fname, lambda v, w=vf: w.set_raw(v))
            notice(key, vf, layout)

        W.pair(label("comped.offset"), "X", C.AXIS_X, vf_x, "Y", C.AXIS_Y, vf_y, layout)
        W.pair(label("comped.size"), "W", C.AXIS_X, vf_w, "H", C.AXIS_Y, vf_h, layout)

        def _on_solid(v):
            self.set_field(comp, "solid", v)

        chk_solid.toggled.connect(_on_solid)
        self.register_syncer("solid", lambda v, w=chk_solid: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False)))

