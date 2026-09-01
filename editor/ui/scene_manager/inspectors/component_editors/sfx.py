"""Éditeur du SoundFxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from core.models.components import SFX_AUTO_TRIGGERS
from . import BaseComponentEditor, register

# Libellé affiché pour chaque trigger — dans l'ordre du menu déroulant.
_TRIGGER_LABELS: dict[str, str] = {
    "manual":            "manual",
    "on_spawn":          "on_spawn",
    "on_destroy":        "on_destroy",
    "on_button_a":       "bouton A",
    "on_button_b":       "bouton B",
    "on_button_l":       "gâchette L",
    "on_button_r":       "gâchette R",
    "on_button_start":   "Start",
    "on_button_select":  "Select",
    "on_button_up":      "↑",
    "on_button_down":    "↓",
    "on_button_left":    "←",
    "on_button_right":   "→",
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
            sfx.addItem("Aucun Sfx dans le projet")
            sfx.setEnabled(False)
        sfx.setToolTip(
            "Sfx joué par ce component.\n"
            "Ajoute des sons depuis l'écran Sound Mixer pour les voir apparaître ici."
        )
        sfx.currentTextChanged.connect(
            lambda v: self.set_field(comp, "sfx_name", v if v in names else None)
        )
        row("Sfx", sfx)

        trigger = QComboBox()
        for v in _TRIGGER_VALUES:
            trigger.addItem(_TRIGGER_LABELS[v], v)
        current = comp.trigger if comp.trigger in _TRIGGER_VALUES else "manual"
        trigger.setCurrentIndex(_TRIGGER_VALUES.index(current))
        trigger.setToolTip(
            "<b>manual</b> — ne joue rien automatiquement, appeler <b>self:play_sfx()</b> depuis un script.<br>"
            "<b>on_spawn</b> — joue au démarrage de l'actor, sans script.<br>"
            "<b>on_destroy</b> — joue juste avant que l'actor soit détruit (par lui-même ou par un "
            "autre), sans script sur cet actor.<br>"
            "<b>bouton</b> — joue tant que l'actor est actif et que ce bouton est pressé, sans "
            "script. Pratique pour un item de menu."
        )
        trigger.currentIndexChanged.connect(
            lambda i: self.set_field(comp, "trigger", trigger.itemData(i))
        )
        row("Trigger", trigger)
