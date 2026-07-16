"""Éditeur du SpriteComponent."""
from __future__ import annotations


from . import BaseComponentEditor, register
from ui.common.widgets import W, ScriptSlot, ScriptPickerPopup
from ui.common.pickers import sprite_picker_slot, palette_picker_slot
from ui.common.theme import C
from ui.common.icons import COLOR_SPRITE
from core.command_dispatcher import get_dispatcher


@register("sprite")
class SpriteEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj   = self.insp._project
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

        # ── Sprite : bouton qui se déploie en liste filtrable, comme le
        #    slot "Ajouter un script" — plus de sélection de PNG direct.
        def _on_sprite_picked(name: str):
            if self.insp._blocking or not self.insp._actor or name == comp.sprite_name:
                return
            comp.sprite_name = name
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)   # re-affiche État/Anim pour le sprite choisi

        def _on_sprite_cleared():
            if self.insp._blocking or not self.insp._actor:
                return
            comp.sprite_name = None
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()
            self.insp._build_editor(comp)

        slot = sprite_picker_slot(
            [s.name for s in proj.sprites], sprite.name if sprite else None,
            COLOR_SPRITE, on_picked=_on_sprite_picked, on_cleared=_on_sprite_cleared,
            add_label="Choisir un sprite", parent=self.insp,
        )
        W.row("Sprite", slot, layout)

        # ── Palette OBJ (pal_bank est un champ Actor/Prefab) ─────────────
        # Un Prefab n'est qu'un modèle : à l'instanciation, il arrive dans une
        # scène et se comporte comme un actor normal — même picker de palette
        # ACTIVE nommée (+ « Sans palette ») aux deux niveaux. Si le slot
        # assigné n'a pas de palette active dans la scène où il finit instancié,
        # il retombe sur le slot 0, comme n'importe quel actor (pas un cas
        # spécial des prefabs).
        from core.project import OWN_PAL_BANK
        from ui.common.pickers import PALETTE_NONE
        actor = self.insp._actor
        scene = self.insp._scene

        active_names = scene.active_obj_palettes if scene else []
        active_banks = [b for n in active_names if (b := proj.get_palette(n))]
        current_pal_name = (
            active_names[actor.pal_bank]
            if actor and 0 <= actor.pal_bank < len(active_names) else None
        )

        def _on_pal_picked(name: str):
            if name == PALETTE_NONE:
                self.insp._set("pal_bank", OWN_PAL_BANK)
                return
            try:
                idx = active_names.index(name)
            except ValueError:
                return
            self.insp._set("pal_bank", idx)

        pal_slot = palette_picker_slot(
            active_banks, current_pal_name,
            COLOR_SPRITE, on_picked=_on_pal_picked,
            add_label="Choisir une palette", parent=self.insp,
        )
        pal_slot.setToolTip(
            "« Sans palette » = couleurs d'origine du PNG (par défaut). "
            "Sinon, choisir une palette active de la scène (carte "
            "\"Palettes actives\" de l'inspecteur de scène)."
        )
        W.row("Palette", pal_slot, layout)

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
