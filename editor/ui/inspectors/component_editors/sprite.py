"""Éditeur du SpriteComponent."""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import QLabel, QComboBox, QHBoxLayout, QWidget, QFileDialog
from PyQt6.QtGui import QFont

from . import BaseComponentEditor, register
from ui.widgets import W
from ui.theme import C, T


@register("sprite")
class SpriteEditor(BaseComponentEditor):

    def build(self, comp, row, layout):
        proj   = self.insp._project
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

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

        # ── PNG ───────────────────────────────────────────────────
        ap  = proj.asset_abs(sprite.asset) if sprite else None
        lbl = QLabel(ap.name if ap else "Aucun")
        lbl.setFont(QFont(T.MONO, T.SM))
        lbl.setStyleSheet(
            f"color:{C.ACCENT_GRN}; background:transparent; border:none;" if ap
            else f"color:{C.TEXT_MUTED}; background:transparent; border:none;"
        )
        btn_pick  = W.btn_ghost("Choisir…")
        btn_pick.clicked.connect(lambda: self._pick_sprite_asset(comp, lbl))
        btn_clear = W.btn_danger()
        btn_clear.clicked.connect(lambda: self._clear_sprite_asset(comp, lbl))

        png_row = QHBoxLayout(); png_row.setSpacing(4); png_row.setContentsMargins(0, 0, 0, 0)
        png_row.addWidget(lbl, 1); png_row.addWidget(btn_pick); png_row.addWidget(btn_clear)
        png_w = QWidget(); png_w.setLayout(png_row)
        W.row("PNG", png_w, layout)

        # ── État initial ──────────────────────────────────────────
        combo = QComboBox(); combo.setFont(QFont(T.MONO, T.SM))
        if sprite and sprite.states:
            for s in sprite.states:
                combo.addItem(s.name)
            combo.setCurrentIndex(max(0, combo.findText(comp.initial_state)))
        else:
            combo.addItem(comp.initial_state or "Idle")

        def _on_state(text):
            comp.initial_state = text
            self.insp._save_component_change(None)
            self.insp._refresh_sprite_preview()

        combo.currentTextChanged.connect(_on_state)
        W.row("Etat init", combo, layout)

        # ── Anim speed ────────────────────────────────────────────
        speed = W.spinbox(
            sprite.states[0].speed if sprite and sprite.states else 8,
            min_v=1, max_v=120
        )
        speed.setToolTip(
            "<b style='color:#7ecfff'>Vitesse animation</b><br><br>"
            "Ticks GBA (60 fps) entre deux frames.<br>"
            "8 ticks ≈ 7.5 fps  |  4 = 15 fps  |  2 = 30 fps"
        )
        speed.valueChanged.connect(lambda v: self._set_anim_speed(comp, v))
        W.row("Anim speed", speed, layout)

    # ── Helpers ──────────────────────────────────────────────────────

    def _ensure_sprite(self, comp):
        from core.project import SpriteAsset
        proj   = self.insp._project
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None
        if not sprite:
            sprite = SpriteAsset(name=f"{self.insp._actor.name}_{comp.id}")
            proj.sprites.append(sprite)
            comp.sprite_name = sprite.name
        return sprite

    def _set_sprite_field(self, comp, field, value):
        if self.insp._blocking or not self.insp._actor: return
        sprite = self._ensure_sprite(comp)
        setattr(sprite, field, value)
        self.insp._project.save_sprite(sprite)
        self.insp._save_component_change(comp)

    def _set_anim_speed(self, comp, value: int):
        if self.insp._blocking or not self.insp._actor: return
        sprite = self._ensure_sprite(comp)
        for state in sprite.states:
            state.speed = value
        self.insp._project.save_sprite(sprite)
        self.insp._persist()
        self.insp.changed.emit()

    def _pick_sprite_asset(self, comp, lbl: QLabel):
        from core.project import SpriteAsset
        proj = self.insp._project
        path, _ = QFileDialog.getOpenFileName(
            self.insp, "Sprite", str(proj.assets_dir / "sprites"), "Images (*.png *.bmp)"
        )
        if not path:
            return
        dst         = proj.import_asset(Path(path), "sprites")
        sprite_name = Path(path).stem
        sprite      = proj.get_sprite(sprite_name)
        if not sprite:
            sprite = SpriteAsset(name=sprite_name, asset=proj.asset_rel(dst))
            proj.sprites.append(sprite)
            proj.save_sprite(sprite)
        elif sprite.asset != proj.asset_rel(dst):
            sprite.asset = proj.asset_rel(dst)
            proj.save_sprite(sprite)
        comp.sprite_name = sprite_name
        lbl.setText(dst.name)
        lbl.setStyleSheet(f"color:{C.ACCENT_GRN}; background:transparent; border:none;")
        self.insp._save_component_change(None)
        self.insp._refresh_sprite_preview()

    def _clear_sprite_asset(self, comp, lbl: QLabel):
        proj   = self.insp._project
        sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None
        if sprite:
            sprite.asset = None
            proj.save_sprite(sprite)
        lbl.setText("Aucun")
        lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; background:transparent; border:none;")
        self.insp._save_component_change(None)
