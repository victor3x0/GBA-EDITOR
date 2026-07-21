"""Éditeur du CollisionBoxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QLineEdit, QHBoxLayout, QWidget
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.common.widgets import W
from ui.common.theme import C

_TOOLTIPS = {
    "collision.solid":              ("self.collision.solid",
                                     "true → résolution physique.\n"
                                     "false → trigger (onTriggerEnter/Exit)."),
    "collision.tag":                ("self.collision.tag",
                                     "Label identifiant ce collider. Ex : 'body', 'sword_hitbox'."),
    "collision.x":                  ("self.collision.x", "Décalage horizontal de la hitbox (px)."),
    "collision.y":                  ("self.collision.y", "Décalage vertical de la hitbox (px)."),
    "collision.w":                  ("self.collision.width",  "Largeur AABB (px)."),
    "collision.h":                  ("self.collision.height", "Hauteur AABB (px)."),
    "collision.on_collision_enter": ("function onCollisionEnter(other_id)",
                                     "Appelée quand un actor SOLIDE entre en contact."),
    "collision.on_collision_exit":  ("function onCollisionExit(other_id)",
                                     "Appelée quand le contact avec un actor solide est rompu."),
    "collision.on_trigger_enter":   ("function onTriggerEnter(other_id)",
                                     "Appelée quand un actor entre dans la zone trigger."),
    "collision.on_trigger_exit":    ("function onTriggerExit(other_id)",
                                     "Appelée quand un actor quitte la zone trigger."),
}

def _tip(w, key):
    if key in _TOOLTIPS:
        expr, desc = _TOOLTIPS[key]
        w.setToolTip(f"<b style='color:{C.ACCENT_BLU}'>{expr}</b><br><br>{desc.replace(chr(10),'<br>')}")


@register("collision_box")
class CollisionEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        is_solid = getattr(comp, "solid", True)

        # Rediriger le champ "id" de la meta_bar vers "tag"
        # (la meta_bar est déjà construite avant build(); on retrouve son QLineEdit)
        from PyQt6.QtWidgets import QLineEdit as _QLE
        id_edit = next(
            (w for w in layout.parentWidget().findChildren(_QLE)
             if w.placeholderText() == "id…"),
            None
        ) if layout.parentWidget() else None
        if id_edit:
            id_edit.setText(getattr(comp, "tag", "body"))
            id_edit.setToolTip(
                f"<b style='color:{C.ACCENT_BLU}'>BOXTAG</b><br><br>"
                "Identifiant de cette box dans les callbacks de collision.<br>"
                "Ex : <b>body</b>, <b>sword</b>, <b>ground_check</b><br>"
                "→ génère <b>BOXTAG_BODY</b>, <b>BOXTAG_SWORD</b>…"
            )
            try: id_edit.editingFinished.disconnect()
            except RuntimeError: pass
            id_edit.editingFinished.connect(
                lambda: (self.set_field(comp, "tag", id_edit.text()),
                         self.set_field(comp, "id",  id_edit.text()))
            )
            self.register_syncer("tag", lambda v, w=id_edit: (
                w.blockSignals(True), w.setText(str(v)), w.blockSignals(False)))

        # ── Mode Solid / Trigger ──────────────────────────────────
        chk_solid = QCheckBox()
        chk_solid.setChecked(is_solid)
        _tip(chk_solid, "collision.solid")

        mode_lbl = QWidget()
        hl = QHBoxLayout(mode_lbl); hl.setSpacing(6); hl.setContentsMargins(0, 0, 0, 0)
        lbl = W.hint("Solid  (décocher = Trigger)", hl, color=C.TEXT_NORM)
        lbl.setParent(None)
        hl.addWidget(chk_solid); hl.addWidget(lbl); hl.addStretch()
        W.row("Mode", mode_lbl, layout)

        # ── AABB — champs px/tile ou référence de variable ────────
        # Les valeurs peuvent être un littéral (px/tile) ou pointer une
        # variable déclarée (global g_<nom> / constante CONST_<NOM>).
        proj = self.insp._project
        vf_x = W.value_field(getattr(comp, "x", 0), project=proj)
        vf_y = W.value_field(getattr(comp, "y", 0), project=proj)
        vf_w = W.value_field(getattr(comp, "w", 16), project=proj, min_px=1)
        vf_h = W.value_field(getattr(comp, "h", 16), project=proj, min_px=1)

        for vf, fname in ((vf_x, "x"), (vf_y, "y"), (vf_w, "w"), (vf_h, "h")):
            vf.changed.connect(lambda raw, f=fname: self.set_field(comp, f, raw))
            self.register_syncer(fname, lambda v, w=vf: w.set_raw(v))
            _tip(vf, f"collision.{fname}")

        W.pair("Offset", "X", C.AXIS_X, vf_x, "Y", C.AXIS_Y, vf_y, layout)
        W.pair("Taille", "W", C.ACCENT_BLU, vf_w, "H", C.ACCENT_PRP, vf_h, layout)

        def _on_solid(v):
            self.set_field(comp, "solid", v)

        chk_solid.toggled.connect(_on_solid)
        self.register_syncer("solid", lambda v, w=chk_solid: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False)))

