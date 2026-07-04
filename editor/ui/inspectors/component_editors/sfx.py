"""Éditeur du SoundFxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from . import BaseComponentEditor, register


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
        trigger.addItems(["manual", "on_spawn"])
        trigger.setCurrentText(comp.trigger if comp.trigger in ("manual", "on_spawn") else "manual")
        trigger.setToolTip(
            "<b>manual</b> — ne joue rien automatiquement, appeler <b>self:play_sfx()</b> depuis un script.<br>"
            "<b>on_spawn</b> — joue automatiquement au démarrage de l'actor, sans script."
        )
        trigger.currentTextChanged.connect(lambda v: self.set_field(comp, "trigger", v))
        row("Trigger", trigger)
