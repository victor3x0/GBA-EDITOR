"""Éditeur du ScriptComponent."""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QLineEdit,
)

from . import BaseComponentEditor, register
from ui.widgets import W, ScriptSlot
from ui.theme import C, T, QSS


@register("script")
class ScriptEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj = self.insp._project
        sp   = proj.asset_abs(comp.script) if comp.script else None

        slot = ScriptSlot(
            add_label    = "Ajouter un script",
            accent_color = C.ACCENT_GRN,
            hint         = "on_start · on_update · on_collide · …",
        )
        if sp and sp.exists():
            slot.set_script(sp.name)
        slot.set_callbacks(
            on_add   = lambda: self._new_script(comp, slot),
            on_open  = lambda: self._open_script(comp),
            on_clear = lambda: self._clear_script(comp, slot),
        )
        layout.addWidget(slot)

        # ── Variables exposées du script ───────────────────────────
        self._build_exports_panel(comp, sp, layout)

    # ── Panneau variables exposées ────────────────────────────────────

    def _build_exports_panel(self, comp, script_path, layout):
        from scripting.exports_parser import parse_exports

        if not script_path:
            return

        variables = parse_exports(script_path)
        if not variables:
            return

        W.separator(layout)
        W.section("VARIABLES EXPOSÉES", layout)

        for var in variables:
            self._build_var_row(comp, var, layout)

    def _build_var_row(self, comp, var: dict, layout):
        name    = var["name"]
        typ     = var["type"]
        label   = var.get("label", name)
        current = comp.exports_values.get(name, var["default"])
        proj    = self.insp._project

        def save(value, _name=name):
            comp.exports_values[_name] = value
            self.insp._save_component_change(None)

        # ── bool ──────────────────────────────────────────────────
        if typ == "bool":
            chk = W.checkbox_row(label, "", layout)
            chk.setChecked(bool(current))
            chk.toggled.connect(save)

        # ── int ───────────────────────────────────────────────────
        elif typ == "int":
            mn = int(var["min"]) if var["min"] is not None else -9999
            mx = int(var["max"]) if var["max"] is not None else  9999
            sp = W.spinbox(int(current) if current != "" else 0, mn, mx)
            W.row(label, sp, layout)
            sp.valueChanged.connect(save)

        # ── float ─────────────────────────────────────────────────
        elif typ == "float":
            mn = float(var["min"]) if var["min"] is not None else -9999.0
            mx = float(var["max"]) if var["max"] is not None else  9999.0
            try:   val = float(current)
            except: val = 0.0
            sp = W.double_spinbox(val, mn, mx)
            W.row(label, sp, layout)
            sp.valueChanged.connect(save)

        # ── string ────────────────────────────────────────────────
        elif typ == "string":
            le = QLineEdit(str(current))
            le.setFont(QFont(T.MONO, T.MD))
            le.setStyleSheet(QSS.lineedit)
            W.row(label, le, layout)
            le.editingFinished.connect(lambda w=le: save(w.text()))

        # ── vec2 ──────────────────────────────────────────────────
        elif typ == "vec2":
            vals = current if isinstance(current, (list, tuple)) and len(current) >= 2 else [0, 0]
            sp_x = W.spinbox(int(vals[0]), -9999, 9999)
            sp_y = W.spinbox(int(vals[1]), -9999, 9999)
            W.pair(label, "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
            sp_x.valueChanged.connect(lambda _, sx=sp_x, sy=sp_y: save([sx.value(), sy.value()]))
            sp_y.valueChanged.connect(lambda _, sx=sp_x, sy=sp_y: save([sx.value(), sy.value()]))

        # ── rect ──────────────────────────────────────────────────
        elif typ == "rect":
            vals = current if isinstance(current, (list, tuple)) and len(current) >= 4 else [0, 0, 16, 16]
            sp_x = W.spinbox(int(vals[0]), -9999, 9999)
            sp_y = W.spinbox(int(vals[1]), -9999, 9999)
            sp_w = W.spinbox(int(vals[2]),     0, 9999)
            sp_h = W.spinbox(int(vals[3]),     0, 9999)
            W.pair(label, "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
            W.pair("",    "W", C.TEXT_DIM, sp_w, "H", C.TEXT_DIM, sp_h, layout)

            def _save_rect(_, sx=sp_x, sy=sp_y, sw=sp_w, sh=sp_h):
                save([sx.value(), sy.value(), sw.value(), sh.value()])
            for sp in (sp_x, sp_y, sp_w, sp_h):
                sp.valueChanged.connect(_save_rect)

        # ── enum ──────────────────────────────────────────────────
        elif typ == "enum":
            values = var.get("values") or []
            cb = W.combobox(values, str(current))
            W.row(label, cb, layout)
            cb.currentTextChanged.connect(save)

        # ── scene_ref ─────────────────────────────────────────────
        elif typ == "scene_ref":
            scenes = [""] + [s.name for s in proj.scenes] if proj else [""]
            cb = W.combobox(scenes, str(current))
            W.row(label, cb, layout)
            cb.currentTextChanged.connect(save)

        # ── sfx_ref ───────────────────────────────────────────────
        elif typ == "sfx_ref":
            sfx_list = [""] + [s.name for s in proj.sfx] if proj else [""]
            cb = W.combobox(sfx_list, str(current))
            W.row(label, cb, layout)
            cb.currentTextChanged.connect(save)

        # ── actor_ref ─────────────────────────────────────────────
        elif typ == "actor_ref":
            actors = [""]
            if proj and proj.active_scene:
                actors += [a.name for a in proj.active_scene.actors
                           if a is not self.insp._actor]
            cb = W.combobox(actors, str(current))
            W.row(label, cb, layout)
            cb.currentTextChanged.connect(save)

    # ── Actions ───────────────────────────────────────────────────────

    def _open_script(self, comp):
        proj = self.insp._project
        sp = proj.asset_abs(comp.script) if comp.script else None
        if not (sp and sp.exists()):
            return
        # Ouvrir dans le script editor interne
        fn = getattr(self.insp, "_script_open_fn", None)
        if fn:
            fn(str(sp))

    def _new_script(self, comp, slot: ScriptSlot):
        from core.command_dispatcher import get_dispatcher
        proj = self.insp._project
        name, ok = QInputDialog.getText(self.insp, "Nouveau script actor", "Nom (sans .lua) :")
        if not ok or not name.strip(): return
        actors_dir = proj.scripts_actors_dir
        actors_dir.mkdir(parents=True, exist_ok=True)
        sp = actors_dir / f"{name.strip()}.lua"
        if not sp.exists():
            sp.write_text(self._generate_template(name.strip()), encoding="utf-8")
        comp.script = proj.asset_rel(sp)
        slot.set_script(sp.name)
        self.insp._save_component_change(None)
        get_dispatcher().notify_scripts_changed()
        fn = getattr(self.insp, "_script_open_fn", None)
        if fn:
            fn(str(sp))

    def _clear_script(self, comp, slot: ScriptSlot):
        comp.script = None
        comp.exports_values = {}
        slot.clear_script()
        self.insp._save_component_change(None)

    def _generate_template(self, script_name: str) -> str:
        from core.project import (CollisionBoxComponent, SpriteComponent,
                             SoundFxComponent, PathComponent, component_type_name)
        insp  = self.insp
        actor = insp._actor
        comps = actor.components if actor else []

        has_sprite = any(isinstance(c, SpriteComponent)  for c in comps)
        has_sfx    = any(isinstance(c, SoundFxComponent) for c in comps)
        has_path   = any(isinstance(c, PathComponent)    for c in comps)
        solids     = [c for c in comps if isinstance(c, CollisionBoxComponent) and c.solid]
        triggers   = [c for c in comps if isinstance(c, CollisionBoxComponent) and not c.solid]

        comp_labels = []
        for c in comps:
            base = component_type_name(c); tag = getattr(c, "tag", None)
            comp_labels.append(f"{base}({tag})" if tag and tag != "body" else base)

        lines = [
            f"-- Actor script : {script_name}",
            f"-- Actor       : {actor.name if actor else '?'}",
            f"-- Components  : {', '.join(comp_labels) or 'aucun'}",
            "",
            "-- Déclare ici les variables configurables depuis l'éditeur :",
            "-- exports = {",
            "--     speed  = { type = \"int\",  default = 5,       label = \"Speed\", min = 0, max = 20 },",
            "--     name   = { type = \"string\", default = \"Hero\", label = \"Name\" },",
            "--     active = { type = \"bool\",   default = true,    label = \"Active\" },",
            "-- }",
            "",
            "function onSpawn()",
        ]
        if has_sprite: lines += ["    -- self:play_anim('Idle')"]
        lines += ["end", "", "function onUpdate()"]
        if has_sprite: lines += ["    -- self:play_anim('Run')"]
        if has_path:   lines += ["    -- self:follow_path()"]
        if has_sfx:    lines += ["    -- self:play_sfx()"]
        lines += ["end", ""]

        for c in solids:
            enter = getattr(c, "on_collision_enter", "onCollisionEnter")
            exit_ = getattr(c, "on_collision_exit",  "onCollisionExit")
            note  = f"  -- tag='{c.tag}'" if c.tag != "body" else ""
            lines += [f"function {enter}(other_id){note}",
                      "    -- local other = actors[other_id]", "end",
                      f"function {exit_}(other_id)", "end", ""]
        for c in triggers:
            enter = getattr(c, "on_trigger_enter", "onTriggerEnter")
            exit_ = getattr(c, "on_trigger_exit",  "onTriggerExit")
            note  = f"  -- tag='{c.tag}'" if c.tag != "body" else ""
            lines += [f"function {enter}(other_id){note}",
                      "    -- local other = actors[other_id]", "end",
                      f"function {exit_}(other_id)", "end", ""]

        if not (has_sprite or solids or triggers or has_sfx or has_path):
            lines += ["-- Ajoute des components dans l'inspector pour débloquer l'API.", ""]
        return "\n".join(lines)
