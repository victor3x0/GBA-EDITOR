"""Éditeur du SoundFxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from core.models.components import SFX_AUTO_TRIGGERS
from . import BaseComponentEditor, register
from ui.common.labels import label

# CLÉS de libellé pour chaque trigger — résolues par `label()` à l'affichage.
_TRIGGER_LABELS: dict[str, str] = {
    "manual":            "comped.trig_manual",
    "on_spawn":          "comped.trig_on_spawn",
    "on_destroy":        "comped.trig_on_destroy",
    "on_button_a":       "comped.trig_button_a",
    "on_button_b":       "comped.trig_button_b",
    "on_button_l":       "comped.trig_button_l",
    "on_button_r":       "comped.trig_button_r",
    "on_button_start":   "comped.trig_button_start",
    "on_button_select":  "comped.trig_button_select",
    "on_button_up":      "comped.trig_up",
    "on_button_down":    "comped.trig_down",
    "on_button_left":    "comped.trig_left",
    "on_button_right":   "comped.trig_right",
}
_TRIGGER_VALUES: list[str] = ["manual", *SFX_AUTO_TRIGGERS]


@register("sound_fx")
class SfxEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj  = self.insp._project
        names = [s.name for s in proj.sfx.items] if proj else []

        sfx = QComboBox()
        if names:
            sfx.addItems(names)
            if comp.sfx_name in names:
                sfx.setCurrentText(comp.sfx_name)
        else:
            sfx.addItem(label("comped.sfx_none"))
            sfx.setEnabled(False)
        sfx.setToolTip(label("comped.sfx_tip"))
        sfx.currentTextChanged.connect(
            lambda v: self.set_field(comp, "sfx_name", v if v in names else None)
        )
        row(label("comped.sfx"), sfx)

        trigger = QComboBox()
        for v in _TRIGGER_VALUES:
            trigger.addItem(label(_TRIGGER_LABELS[v]), v)
        current = comp.trigger if comp.trigger in _TRIGGER_VALUES else "manual"
        trigger.setCurrentIndex(_TRIGGER_VALUES.index(current))
        trigger.setToolTip(label("comped.trigger_tip"))
        trigger.currentIndexChanged.connect(
            lambda i: self.set_field(comp, "trigger", trigger.itemData(i))
        )
        row(label("comped.trigger"), trigger)
