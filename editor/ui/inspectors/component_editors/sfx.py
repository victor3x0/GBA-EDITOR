"""Éditeur du SoundFxComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit
from . import BaseComponentEditor, register


@register("sound_fx")
class SfxEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        sfx_name = QLineEdit(comp.sfx_name or "")
        sfx_name.setPlaceholderText("nom du Sfx (project/sfx/)")
        sfx_name.textChanged.connect(lambda v: self.set_field(comp, "sfx_name", v or None))
        row("Sfx", sfx_name)

        trigger = QLineEdit(comp.trigger)
        trigger.textChanged.connect(lambda v: self.set_field(comp, "trigger", v))
        row("Trigger", trigger)

