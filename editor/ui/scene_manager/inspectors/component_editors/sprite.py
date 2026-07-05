"""Éditeur du SpriteComponent."""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.common.widgets import W, ScriptSlot, ScriptPickerPopup
from ui.common.theme import C, T
from ui.common.icons import COLOR_SPRITE
from core.command_dispatcher import get_dispatcher


@register("sprite")
class SpriteEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj   = self.insp._project
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

        # ── Sprite : bouton qui se déploie en liste filtrable, comme le
        #    slot "Ajouter un script" — plus de sélection de PNG direct.
        slot = ScriptSlot(
            add_label="Choisir un sprite",
            accent_color=COLOR_SPRITE,
            edit_label="Changer",
        )
        if sprite:
            slot.set_script(sprite.name)

        def _open_picker():
            names = sorted(s.name for s in proj.sprites)
            popup = ScriptPickerPopup(
                [(n, n) for n in names], COLOR_SPRITE, parent=self.insp, new_label=None,
            )
            popup.picked.connect(lambda name: _on_sprite_picked(name))
            popup.show_below(slot)

        def _on_sprite_picked(name: str):
            if self.insp._blocking or not self.insp._actor or name == comp.sprite_name:
                return
            comp.sprite_name = name
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)   # re-affiche Frame/État/Anim pour le sprite choisi

        def _on_sprite_cleared():
            if self.insp._blocking or not self.insp._actor:
                return
            comp.sprite_name = None
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)

        slot.set_callbacks(on_add=_open_picker, on_open=_open_picker, on_clear=_on_sprite_cleared)
        W.row("Sprite", slot, layout)

        # ── Frame size (tailles OAM valides GBA uniquement) ──────
        _VALID_SIZES = {
            8:  [8, 16, 32],
            16: [8, 16, 32],
            32: [8, 16, 32, 64],
            64: [32, 64],
        }
        cur_w = sprite.frame_w if sprite else 16
        cur_h = sprite.frame_h if sprite else 16

        cb_w = QComboBox(); cb_w.setFont(QFont(T.MONO, T.SM))
        cb_h = QComboBox(); cb_h.setFont(QFont(T.MONO, T.SM))
        cb_w.setEnabled(sprite is not None)
        cb_h.setEnabled(sprite is not None)

        for v in [8, 16, 32, 64]:
            cb_w.addItem(str(v))
        cb_w.setCurrentText(str(cur_w))

        def _refresh_h(w_val, keep_h=None):
            cb_h.blockSignals(True)
            cb_h.clear()
            for v in _VALID_SIZES.get(w_val, [8]):
                cb_h.addItem(str(v))
            target = str(keep_h) if keep_h in _VALID_SIZES.get(w_val, []) else str(_VALID_SIZES[w_val][0])
            cb_h.setCurrentText(target)
            cb_h.blockSignals(False)

        _refresh_h(cur_w, cur_h)

        def _on_w(idx):
            w = int(cb_w.currentText())
            old_h = int(cb_h.currentText()) if cb_h.currentText() else None
            _refresh_h(w, old_h)
            h = int(cb_h.currentText())
            self._set_sprite_field(comp, "frame_w", w)
            self._set_sprite_field(comp, "frame_h", h)

        def _on_h(_idx):
            self._set_sprite_field(comp, "frame_h", int(cb_h.currentText()))

        cb_w.currentIndexChanged.connect(_on_w)
        cb_h.currentIndexChanged.connect(_on_h)
        W.pair("Frame", "W", C.AXIS_X, cb_w, "H", C.AXIS_Y, cb_h, layout)

        # ── État initial : même bouton+popup filtrable que "Sprite" ──
        state_slot = ScriptSlot(
            add_label="Choisir un état",
            accent_color=COLOR_SPRITE,
            edit_label="Changer",
            show_clear=False,   # un state initial est toujours requis, rien à "vider"
        )
        state_slot.set_script(comp.initial_state or "Idle")
        state_slot.setEnabled(sprite is not None)

        def _open_state_picker():
            if not sprite:
                return
            names = [s.name for s in sprite.states] or [comp.initial_state or "Idle"]
            popup = ScriptPickerPopup(
                [(n, n) for n in names], COLOR_SPRITE, parent=self.insp, new_label=None,
            )
            popup.picked.connect(lambda name: _on_state_picked(name))
            popup.show_below(state_slot)

        def _on_state_picked(name: str):
            if self.insp._blocking or not self.insp._actor or name == comp.initial_state:
                return
            comp.initial_state = name
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            state_slot.set_script(name)
            new_state = next((s for s in sprite.states if s.name == name), None) if sprite else None
            if new_state:
                speed.blockSignals(True)
                speed.setValue(new_state.speed)
                speed.blockSignals(False)

        state_slot.set_callbacks(on_add=_open_state_picker, on_open=_open_state_picker)
        W.row("Etat init", state_slot, layout)

        # ── Anim speed (du state initial uniquement — pas des autres states) ──
        _init_state = (
            next((s for s in sprite.states if s.name == comp.initial_state), None)
            if sprite else None
        ) or (sprite.states[0] if sprite and sprite.states else None)
        speed = W.spinbox(_init_state.speed if _init_state else 8, min_v=1, max_v=120)
        speed.setEnabled(sprite is not None)
        speed.setToolTip(
            "<b style='color:#7ecfff'>Vitesse animation</b><br><br>"
            "Ticks GBA (60 fps) entre deux frames, pour l'état initial "
            f"(<b>{comp.initial_state}</b>) uniquement.<br>"
            "8 ticks ≈ 7.5 fps  |  4 = 15 fps  |  2 = 30 fps<br><br>"
            "Les autres états gardent leur propre vitesse — réglable dans le Sprite Editor."
        )
        speed.valueChanged.connect(lambda v: self._set_anim_speed(comp, v))
        W.row("Anim speed", speed, layout)

        # ── Scale ─────────────────────────────────────────────────
        sx = W.double_spinbox(getattr(comp, "scale_x", 1.0), min_v=0.1, max_v=4.0, step=0.1)
        sy = W.double_spinbox(getattr(comp, "scale_y", 1.0), min_v=0.1, max_v=4.0, step=0.1)
        sx.setToolTip("Échelle X — OAM affine (1.0 = normal, GBA uniquement)")
        sy.setToolTip("Échelle Y — OAM affine")
        sx.valueChanged.connect(lambda v: self._set_comp_field(comp, "scale_x", v))
        sy.valueChanged.connect(lambda v: self._set_comp_field(comp, "scale_y", v))
        W.pair("Scale", "X", C.AXIS_X, sx, "Y", C.AXIS_Y, sy, layout)

        # ── Rotation ──────────────────────────────────────────────
        rot = W.spinbox(int(getattr(comp, "rotation", 0)), min_v=0, max_v=359)
        rot.setSuffix("°")
        rot.setWrapping(True)
        rot.setToolTip("Rotation en degrés — OAM affine (GBA uniquement)")
        rot.valueChanged.connect(lambda v: self._set_comp_field(comp, "rotation", v))
        W.row("Rotation", rot, layout)

    # ── Helpers ──────────────────────────────────────────────────────

    def _set_comp_field(self, comp, field, value):
        if self.insp._blocking or not self.insp._actor: return
        setattr(comp, field, value)
        self.insp._save_component_change(comp)

    def _set_sprite_field(self, comp, field, value):
        if self.insp._blocking or not self.insp._actor: return
        sprite = self.insp._project.get_sprite(comp.sprite_name) if comp.sprite_name else None
        if not sprite:
            return
        setattr(sprite, field, value)
        get_dispatcher().save_sprite(sprite)
        self.insp._save_component_change(comp)

    def _set_anim_speed(self, comp, value: int):
        """Ne modifie que le state initial de ce component — les autres states du
        sprite gardent leur propre vitesse (réglée dans le Sprite Editor)."""
        if self.insp._blocking or not self.insp._actor: return
        sprite = self.insp._project.get_sprite(comp.sprite_name) if comp.sprite_name else None
        if not sprite:
            return
        state = next((s for s in sprite.states if s.name == comp.initial_state), None)
        if not state and sprite.states:
            state = sprite.states[0]
        if state:
            state.speed = value
        get_dispatcher().save_sprite(sprite)
        self.insp._persist()
        self.insp.changed.emit()
