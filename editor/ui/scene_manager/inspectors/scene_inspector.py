"""SceneInspector — background layers, paramètres d'affichage, script de scène."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QCheckBox, QScrollArea, QPushButton, QMessageBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.project import Project, Scene, OWN_PAL_BANK
from core.asset_manager import BgLayerRow
from core.history import (
    get_history, Command, SetFieldCmd, SwapFieldCmd, AddListItemCmd,
    RemoveListItemCmd, SetSceneModeCmd,
)
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, ScriptPickerPopup
from ui.common.palette_slot_grid import PaletteSlotGridAsset


class _ScenePaletteCmd(Command):
    """Mutation undoable de l'allocation palette d'un pool ("obj"|"bg") de la
    scène. Snapshot COMPLET (active_*_palettes + pal_bank de toutes les
    instances du pool) → undo/redo fidèles, couvre uniformément replace / add /
    remove (avec réindexation des références) / override / restore.

    `mutate_fn` applique la nouvelle configuration ; le snapshot avant (pris à
    la construction) et après (pris au 1er execute) suffisent à rejouer sans
    ré-exécuter la logique de mutation."""

    def __init__(self, scene, pool: str, mutate_fn, label: str,
                 persist_fn=None, refresh_fn=None):
        self._scene = scene
        self._pool = pool
        self._mutate = mutate_fn
        self.label = label
        self._persist = persist_fn
        self._refresh = refresh_fn
        self._before = self._snapshot()
        self._after = None

    def _active(self) -> list:
        return getattr(self._scene, f"active_{self._pool}_palettes")

    def _instances(self) -> list:
        return (self._scene.actors if self._pool == "obj"
                else self._scene.background_layers)

    def _snapshot(self):
        return (list(self._active()),
                [(o, getattr(o, "pal_bank", OWN_PAL_BANK)) for o in self._instances()])

    def _restore(self, snap):
        active, banks = snap
        self._active()[:] = active
        for o, pb in banks:
            o.pal_bank = pb

    def _finish(self):
        if self._persist:
            self._persist()
        if self._refresh:
            self._refresh()

    def execute(self):
        if self._after is None:
            self._mutate()
            self._after = self._snapshot()
        else:
            self._restore(self._after)   # redo
        self._finish()

    def undo(self):
        self._restore(self._before)
        self._finish()


# ── Table des modes vidéo GBA (pilote l'inspecteur adaptatif) ──────────────────
# kind : "tiled" (0/1/2, fonds tuilés) | "bitmap" (3/4/5, un fond plein écran BG2).
# bg_slots : slots BG hardware valides ; affine : slots en mode affine (rotation).
# bg_palettes : la scène sélectionne-t-elle des banques de palette BG ? (non en 3/5).
MODE_INFO: dict[int, dict] = {
    0: {"kind": "tiled",  "bg_slots": (0, 1, 2, 3), "affine": (),     "bg_palettes": True,
        "res": (240, 160), "tip": "4 fonds tuilés réguliers (BG0-3) · 4/8bpp"},
    1: {"kind": "tiled",  "bg_slots": (0, 1, 2),    "affine": (2,),   "bg_palettes": True,
        "res": (240, 160), "tip": "BG0-1 réguliers + BG2 affine (rotation/échelle)"},
    2: {"kind": "tiled",  "bg_slots": (2, 3),       "affine": (2, 3), "bg_palettes": True,
        "res": (240, 160), "tip": "BG2-3 affines"},
    3: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": False,
        "res": (240, 160), "bpp": 16, "tip": "Bitmap BG2 · couleur directe 16bpp · 240×160 (sans palette)"},
    4: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": True,
        "res": (240, 160), "bpp": 8,  "tip": "Bitmap BG2 · 8bpp paletté (256 couleurs) · 240×160"},
    5: {"kind": "bitmap", "bg_slots": (2,),         "affine": (),     "bg_palettes": False,
        "res": (160, 128), "bpp": 16, "tip": "Bitmap BG2 · couleur directe 16bpp · 160×128"},
}


# ──────────────────────────────────────────────────────────────────
#  SceneInspector
# ──────────────────────────────────────────────────────────────────
class SceneInspector(QWidget):
    changed = pyqtSignal()
    slot_assigned = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene: Optional[Scene] = None
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel("Selectionne une scene")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        def _card(accent: str) -> tuple:
            """Retourne (card QFrame, inner_layout QVBoxLayout)."""
            f = QFrame()
            f.setStyleSheet(
                f"QFrame#sc_card{{background:{C.BG_BASE};border:1px solid {C.BORDER};"
                f"border-left:3px solid {accent};border-radius:4px;}}"
                f"QFrame#sc_card QFrame{{background:transparent;border:none;}}"
                f"QFrame#sc_card QLabel{{background:transparent;border:none;}}"
            )
            f.setObjectName("sc_card")
            inner = QVBoxLayout(f)
            inner.setContentsMargins(8, 6, 8, 8)
            inner.setSpacing(6)
            return f, inner

        def _card_title(text: str, accent: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
            lbl.setStyleSheet(
                f"color:{accent};letter-spacing:1px;"
                f"border-bottom:1px solid {C.BORDER};padding-bottom:4px;"
            )
            return lbl

        # ── Carte Mode vidéo (Scene Mode) ─────────────────────────
        mode_card, mode_inner = _card(C.ACCENT_GRN)
        mode_inner.addWidget(_card_title("SCENE MODE", C.ACCENT_GRN))
        mode_row = QHBoxLayout(); mode_row.setContentsMargins(0, 0, 0, 0); mode_row.setSpacing(3)
        self._mode_btns: list[QPushButton] = []
        for m in range(6):
            b = self._make_mode_btn(m)
            b.clicked.connect(lambda _c=False, m=m: self._on_set_mode(m))
            mode_row.addWidget(b)
            self._mode_btns.append(b)
        mode_row.addStretch(1)   # boutons compacts alignés à gauche (les 6 tiennent toujours)
        mode_inner.addLayout(mode_row)
        self._mode_hint = QLabel("")
        self._mode_hint.setFont(QFont(T.MONO, T.XS)); self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet(f"color:{C.TEXT_DIM}; margin-top:2px;")
        mode_inner.addWidget(self._mode_hint)
        cl.addWidget(mode_card)

        # ── Carte Background Asset ────────────────────────────────
        bg_card, bg_inner = _card(C.ACCENT_BLU)
        self._bg_card = bg_card

        bg_hdr = QHBoxLayout(); bg_hdr.setContentsMargins(0, 0, 0, 0); bg_hdr.setSpacing(4)
        bg_hdr.addWidget(_card_title("BACKGROUND", C.ACCENT_BLU), 1)
        self._btn_bg_add = W.btn_add("Ajouter un calque BG (max 4)")
        self._btn_bg_add.clicked.connect(self._add_bg_layer)
        bg_hdr.addWidget(self._btn_bg_add)
        bg_inner.addLayout(bg_hdr)

        # Rows dynamiques des BackgroundLayers (portés par la scène)
        self._bg_layer_rows: list[BgLayerRow] = []
        self._inpaint_layer_slot: Optional[int] = None  # layer BG peint actif
        self._bg_layers_container = QVBoxLayout()
        self._bg_layers_container.setContentsMargins(0, 2, 0, 0)
        self._bg_layers_container.setSpacing(3)
        bg_inner.addLayout(self._bg_layers_container)

        # Slot « fond bitmap » (modes 3/4/5) — un seul fond plein écran sur BG2.
        self._bitmap_box = QWidget()
        bmp_l = QVBoxLayout(self._bitmap_box)
        bmp_l.setContentsMargins(0, 2, 0, 0); bmp_l.setSpacing(3)
        self._btn_bitmap_pick = QPushButton("Choisir un fond bitmap…")
        self._btn_bitmap_pick.setFont(QFont(T.MONO, T.SM))
        self._btn_bitmap_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_bitmap_pick.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px 8px; text-align:left;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; border-color:{C.ACCENT_BLU};}}"
        )
        self._btn_bitmap_pick.clicked.connect(self._pick_bitmap_bg)
        bmp_l.addWidget(self._btn_bitmap_pick)
        self._bitmap_note = QLabel("")
        self._bitmap_note.setFont(QFont(T.MONO, T.XS)); self._bitmap_note.setWordWrap(True)
        self._bitmap_note.setStyleSheet(f"color:{C.TEXT_DIM};")
        bmp_l.addWidget(self._bitmap_note)
        bg_inner.addWidget(self._bitmap_box)
        self._bitmap_box.setVisible(False)

        cl.addWidget(bg_card)

        # ── Carte Paramètres ──────────────────────────────────────
        param_card, param_inner = _card(C.TEXT_DIM)
        self._param_card = param_card
        param_inner.addWidget(_card_title("PARAMÈTRES", C.TEXT_NORM))

        ui_row = QHBoxLayout(); ui_row.setSpacing(6)
        lbl_ui = QLabel("Layer UI :")
        lbl_ui.setFont(QFont(T.MONO, T.SM)); lbl_ui.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_ui.setFixedWidth(70)
        self._combo_text_bg = QComboBox()
        self._combo_text_bg.setFont(QFont(T.MONO, T.SM))
        self._combo_text_bg.setStyleSheet(QSS.combobox)
        for i in range(4):
            self._combo_text_bg.addItem(f"BG{i}" + (" (défaut)" if i == 1 else ""), i)
        self._combo_text_bg.currentIndexChanged.connect(self._on_text_bg_changed)
        self._combo_text_bg.setToolTip(
            "<b>Calque réservé au texte HUD (TTE)</b><br><br>"
            "Le texte affiché en jeu (score, dialogue…) occupe un calque BG entier.<br>"
            "Choisir un BG qui n'est pas utilisé par un décor.<br><br>"
            "<b>Conflit ⚠</b> : si ce BG est déjà assigné à un background,<br>"
            "les deux se superposent et le résultat est indéfini."
        )
        self._lbl_text_bg_warn = QLabel("")
        self._lbl_text_bg_warn.setFont(QFont(T.MONO, T.XS))
        self._lbl_text_bg_warn.setStyleSheet(f"color:{C.ACCENT_YLW};")
        ui_row.addWidget(lbl_ui)
        ui_row.addWidget(self._combo_text_bg)
        ui_row.addWidget(self._lbl_text_bg_warn, 1)
        param_inner.addLayout(ui_row)

        scroll_row = QHBoxLayout(); scroll_row.setSpacing(6)
        lbl_scroll = QLabel("Scrolling :")
        lbl_scroll.setFont(QFont(T.MONO, T.SM)); lbl_scroll.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl_scroll.setFixedWidth(70)
        self._chk_scroll_h = QCheckBox("Horizontal")
        self._chk_scroll_v = QCheckBox("Vertical")
        for chk in (self._chk_scroll_h, self._chk_scroll_v):
            chk.setFont(QFont(T.MONO, T.SM))
            chk.setStyleSheet(QSS.checkbox)
            scroll_row.addWidget(chk)
        scroll_row.insertWidget(0, lbl_scroll)
        scroll_row.addStretch()
        self._chk_scroll_h.toggled.connect(self._on_scroll_changed)
        self._chk_scroll_v.toggled.connect(self._on_scroll_changed)
        param_inner.addLayout(scroll_row)

        cl.addWidget(param_card)

        # ── Carte Palettes actives ─────────────────────────────────
        # Le catalogue de palettes (Palette Editor) est illimité au niveau
        # projet — c'est ICI qu'on choisit jusqu'à 16 palettes par pool comme
        # "actives" pour cette scène. Actor.pal_bank référence un slot de
        # cette sélection (0-15), pas directement le catalogue.
        pal_card, pal_inner = _card(C.ACCENT_GRN)
        pal_inner.addWidget(_card_title("PALETTES ACTIVES", C.ACCENT_GRN))

        self._pal_grids: dict[str, PaletteSlotGridAsset] = {}
        self._pal_sublabels: dict[str, QLabel] = {}
        for pool, color, title in (("obj", C.ACCENT_ORG, "OBJ (sprites)"),
                                    ("bg", C.ACCENT_BLU, "BACKGROUND")):
            sub_lbl = QLabel(title)
            sub_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            sub_lbl.setStyleSheet(f"color:{color}; letter-spacing:1px; margin-top:4px;")
            pal_inner.addWidget(sub_lbl)
            grid = PaletteSlotGridAsset(color)
            grid.scene_replace.connect(lambda slot, name, pool=pool: self._on_scene_replace(pool, slot, name))
            grid.scene_add.connect(lambda name, pool=pool: self._on_scene_add(pool, name))
            grid.scene_remove.connect(lambda slot, pool=pool: self._on_scene_remove(pool, slot))
            grid.asset_override.connect(lambda entry, name, pool=pool: self._on_asset_override(pool, entry, name))
            grid.asset_restore.connect(lambda entry, pool=pool: self._on_asset_restore(pool, entry))
            pal_inner.addWidget(grid)
            self._pal_grids[pool] = grid
            self._pal_sublabels[pool] = sub_lbl

        cl.addWidget(pal_card)

        # ── Carte Script ──────────────────────────────────────────
        sc_card, sc_inner = _card(C.ACCENT_ORG)
        sc_inner.addWidget(_card_title("SCRIPT", C.ACCENT_ORG))

        from ui.common.widgets import ScriptSlot, ScriptPickerPopup  # noqa: F401 (ScriptPickerPopup used later)
        self._scene_script_slot = ScriptSlot(
            add_label    = "Ajouter un script de scène",
            accent_color = C.ACCENT_ORG,
            hint         = "on_start · on_update · on_late_update",
        )
        self._scene_script_slot.set_callbacks(
            on_add   = self._scene_script_new,
            on_open  = self._scene_script_open,
            on_clear = self._scene_script_clear,
        )
        sc_inner.addWidget(self._scene_script_slot)

        cl.addWidget(sc_card)

        cl.addStretch()
        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    def load(self, scene: Scene, project: Project):
        self._scene = scene; self._project = project
        if not scene:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._chk_scroll_h.setChecked(scene.scroll_h)
        self._chk_scroll_v.setChecked(scene.scroll_v)
        self._refresh_scroll_speeds()
        text_bg = getattr(scene, "text_bg", 3)
        self._combo_text_bg.setCurrentIndex(text_bg)
        self._refresh_text_bg_warn()
        self._refresh_scene_script_label()
        self._rebuild_palette_slots()
        self._apply_mode_ui()
        self._blocking = False

    # ── Scene Mode (0-5) ──────────────────────────────────────────

    def _make_mode_btn(self, m: int) -> QPushButton:
        b = QPushButton(str(m))
        b.setCheckable(True)
        b.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        b.setFixedSize(40, 26)   # compact : les 6 boutons tiennent dans un panneau étroit
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            f"QPushButton:checked{{color:{C.ACCENT_GRN}; border:2px solid {C.ACCENT_GRN};"
            f"background:{C.SEL_BG};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; background:{C.BG_BASE};"
            f"border-color:{C.BORDER_DARK};}}"
        )
        # Seul le Mode 0 rend réellement pour l'instant ; les autres sont grisés
        # (le sélecteur/inspecteur adaptatif existe, mais pas encore le rendu).
        if m == 0:
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Mode 0 — {MODE_INFO[0]['tip']}")
        else:
            b.setEnabled(False)
            b.setToolTip(f"Mode {m} — {MODE_INFO[m]['tip']}\n(rendu non encore implémenté — bientôt)")
        return b

    def _refresh_mode_buttons(self):
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        for i, b in enumerate(self._mode_btns):
            b.setChecked(i == mode)

    def _is_bitmap_layer(self, layer) -> bool:
        ba = self._project.get_background(layer.background_name) if (self._project and layer.background_name) else None
        return bool(ba and getattr(ba, "mode", "tiled") == "bitmap")

    def _pruned_by_mode(self, m: int) -> list:
        """Liste lisible des éléments qui seront supprimés en passant au mode `m`."""
        info = MODE_INFO[m]
        out: list = []
        if info["kind"] == "bitmap":
            for L in self._scene.background_layers:
                if not self._is_bitmap_layer(L):
                    out.append(f"calque BG{L.bg_slot}" + (f" ({L.background_name})" if L.background_name else " (vide)"))
        else:
            valid = set(info["bg_slots"])
            for L in self._scene.background_layers:
                if L.bg_slot not in valid or self._is_bitmap_layer(L):
                    out.append(f"calque BG{L.bg_slot}" + (f" ({L.background_name})" if L.background_name else " (vide)"))
        if not info["bg_palettes"]:
            n = sum(1 for name in self._scene.active_bg_palettes if name)
            if n:
                out.append(f"{n} palette(s) BG active(s)")
        return out

    def _on_set_mode(self, m: int):
        if self._blocking or not self._scene:
            return
        if m == getattr(self._scene, "render_mode", 0):
            self._refresh_mode_buttons(); return
        pruned = self._pruned_by_mode(m)
        if pruned:
            msg = (f"Passer en Mode {m} supprimera :\n• " + "\n• ".join(pruned)
                   + "\n\nContinuer ? (Ctrl+Z pour annuler)")
            if QMessageBox.question(
                self, "Changer de mode de scène", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                self._refresh_mode_buttons()
                return
        info = MODE_INFO[m]
        old = self._scene.background_layers
        if info["kind"] == "bitmap":
            new_layers = [L for L in old if self._is_bitmap_layer(L)][:1]
            for L in new_layers:
                L.bg_slot = 2
        else:
            valid = set(info["bg_slots"])
            new_layers = [L for L in old if L.bg_slot in valid and not self._is_bitmap_layer(L)]
        new_bg_pals = list(self._scene.active_bg_palettes) if info["bg_palettes"] else []
        get_history().push(SetSceneModeCmd(
            self._scene, m, new_layers, new_bg_pals,
            persist_fn=self._persist_scene,
            refresh_fn=lambda: self.load(self._scene, self._project),
        ))
        self.changed.emit()

    def _clear_layer_rows(self):
        for row in self._bg_layer_rows:
            row.hide(); row.setParent(None); row.deleteLater()
        self._bg_layer_rows.clear()

    def _refresh_bitmap_slot(self, info: dict):
        """Met à jour le slot « fond bitmap » (modes 3/4/5) depuis la scène."""
        layer = next((L for L in self._scene.background_layers
                      if self._is_bitmap_layer(L)), None)
        name = layer.background_name if layer else None
        self._btn_bitmap_pick.setText(name or "Choisir un fond bitmap…")
        rw, rh = info.get("res", (240, 160))
        bpp = info.get("bpp", 8)
        depth = "8bpp paletté (256)" if bpp == 8 else "16bpp couleur directe"
        self._bitmap_note.setText(f"BG2 · {rw}×{rh} · {depth}"
                                  + ("" if name else " — aucun fond sélectionné"))

    def _pick_bitmap_bg(self):
        if not self._project or not self._scene:
            return
        bitmaps = [b for b in self._project.backgrounds
                   if getattr(b, "mode", "tiled") == "bitmap"]
        if not bitmaps:
            QMessageBox.information(
                self, "Aucun fond bitmap",
                "Importe d'abord une image en mode Bitmap dans le Background Editor.")
            return
        entries = [(b.name, b.name) for b in bitmaps]
        popup = ScriptPickerPopup(entries, C.ACCENT_BLU, parent=self, new_label=None)
        popup.picked.connect(self._set_bitmap_bg)
        popup.show_below(self._btn_bitmap_pick)

    def _set_bitmap_bg(self, name: str):
        from core.project import BackgroundLayer
        self._scene.background_layers[:] = [BackgroundLayer(background_name=name, bg_slot=2)]
        self._persist_scene()
        self._apply_mode_ui()
        self.changed.emit()

    def _apply_mode_ui(self):
        """Adapte l'inspecteur au mode de la scène : zone background, paramètres,
        palettes actives."""
        mode = getattr(self._scene, "render_mode", 0) if self._scene else 0
        info = MODE_INFO.get(mode, MODE_INFO[0])
        is_tiled = info["kind"] == "tiled"
        self._refresh_mode_buttons()
        self._mode_hint.setText(info["tip"])
        # BACKGROUND : rangées tuilées vs slot bitmap.
        self._btn_bg_add.setVisible(is_tiled)
        self._bitmap_box.setVisible(not is_tiled)
        self._clear_layer_rows()
        if is_tiled:
            self._rebuild_layer_rows()
        else:
            self._refresh_bitmap_slot(info)
        # PARAMÈTRES (texte TTE + scroll) : tuilé seulement.
        self._param_card.setVisible(is_tiled)
        # PALETTES : OBJ toujours, BG seulement en tuilé.
        self._pal_sublabels["bg"].setVisible(is_tiled)
        self._pal_grids["bg"].setVisible(is_tiled)

    def _rebuild_layer_rows(self):
        """Reconstruit les BgLayerRow depuis les layers de la SCÈNE."""
        for row in self._bg_layer_rows:
            # hide() avant setParent(None) : un widget visible détaché de son
            # parent redevient une fenêtre top-level à part entière (c'est le
            # popup flottant "GBA Editor" observé au Ctrl+S) ; deleteLater()
            # pour le détruire proprement plutôt que le laisser orphelin.
            row.hide()
            row.setParent(None)
            row.deleteLater()
        self._bg_layer_rows.clear()

        if not (self._project and self._scene):
            self._btn_bg_add.setEnabled(False)
            return

        active_names = self._scene.active_bg_palettes
        active_banks = [b for n in active_names if (b := self._project.get_palette(n))]
        bg_names = [b.name for b in self._project.backgrounds]

        for layer in self._scene.background_layers:
            row = BgLayerRow(layer.bg_slot)
            row.set_backgrounds(bg_names, layer.background_name)
            if layer.background_name:
                ba = self._project.get_background(layer.background_name)
                png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
                ap = self._project.background_images_dir / png
                if ap.exists():
                    row.set_asset(str(ap))
            row.set_speed(layer.scroll_speed)
            current_pal_name = (
                active_names[layer.pal_bank]
                if 0 <= layer.pal_bank < len(active_names) else None
            )
            row.set_pal_banks(active_banks, current_pal_name)
            row.asset_changed.connect(lambda _, name, l=layer: self._on_layer_image(l, name))
            row.speed_changed.connect(lambda _, v, l=layer: self._on_layer_speed(l, v))
            row.pal_bank_changed.connect(lambda _, n, l=layer: self._on_layer_pal_bank(l, n))
            row.layer_removed.connect(lambda _, l=layer: self._on_layer_remove(l))
            row.bound_toggled.connect(lambda idx: self._on_bound_toggled(idx))
            row.layer_swap_requested.connect(self._on_layer_swap)
            row.visibility_toggled.connect(self._on_layer_visibility)
            row.inpaint_layer_selected.connect(self._on_inpaint_layer)
            row.set_visible_state(getattr(layer, "visible", True))
            row.set_inpaint_layer(layer.bg_slot == self._inpaint_layer_slot)
            self._bg_layers_container.addWidget(row)
            self._bg_layer_rows.append(row)

        self._refresh_bound_rows()
        self._refresh_ui_layer_marks()
        self._btn_bg_add.setEnabled(len(self._scene.background_layers) < 4)

    def _persist_scene(self):
        if self._project and self._scene:
            self._project.save_scene(self._scene)

    def _on_layer_image(self, layer, name: str):
        """Un BackgroundImage (nom) a été choisi pour un layer — l'image existe
        déjà dans assets/backgrounds/ (import via le Background Editor)."""
        if not self._scene or layer.background_name == name:
            return
        get_history().push(SetFieldCmd(
            layer, "background_name", layer.background_name, name,
            label=f"BG{layer.bg_slot}.background_name",
            persist_fn=lambda: (self._persist_scene(), self._rebuild_layer_rows()),
        ))
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_speed(self, layer, value: float):
        if not self._scene or layer.scroll_speed == value:
            return
        get_history().push(SetFieldCmd(
            layer, "scroll_speed", layer.scroll_speed, value,
            label=f"BG{layer.bg_slot}.scroll_speed", persist_fn=self._persist_scene,
        ))

    def _on_layer_pal_bank(self, layer, pal_name: str):
        """Banque de palette d'un layer — index dans scene.active_bg_palettes
        (même mécanisme qu'Actor.pal_bank)."""
        if not self._scene: return
        from ui.common.pickers import PALETTE_NONE
        from core.project import OWN_PAL_BANK
        active_names = self._scene.active_bg_palettes
        if pal_name == PALETTE_NONE:
            idx = OWN_PAL_BANK
        else:
            try:
                idx = active_names.index(pal_name)
            except ValueError:
                return
        if layer.pal_bank == idx:
            return
        get_history().push(SetFieldCmd(
            layer, "pal_bank", layer.pal_bank, idx,
            label=f"BG{layer.bg_slot}.pal_bank", persist_fn=self._persist_scene,
        ))
        self._rebuild_layer_rows()
        get_dispatcher()._emit("bg_slot_changed", layer.bg_slot)
        self.changed.emit()

    def _on_layer_visibility(self, bg_slot: int, visible: bool):
        """Œil de visibilité viewport d'un layer — persiste layer.visible et
        met à jour le canvas (le codegen ignore ce champ)."""
        if not self._scene:
            return
        layer = next((l for l in self._scene.background_layers
                      if l.bg_slot == bg_slot), None)
        if layer is None or layer.visible == visible:
            return
        layer.visible = visible
        self._persist_scene()
        get_dispatcher()._emit("bg_layer_visibility", bg_slot, visible)

    def _on_inpaint_layer(self, bg_slot: int):
        """Sélectionne le layer peint par l'outil de peinture par palette.
        Radio-like : une seule cible active, les autres lignes se décochent."""
        self._inpaint_layer_slot = bg_slot
        for row in self._bg_layer_rows:
            row.set_inpaint_layer(row.slot_index == bg_slot)
        get_dispatcher()._emit("inpaint_layer_changed", bg_slot)

    def _on_layer_swap(self, src_slot: int, dst_slot: int):
        """Glisser-déposer d'un BgLayerRow sur un autre : échange leurs
        bg_slot — donc leur priorité d'affichage (pri = 3 - bg_slot côté
        codegen). Ne déplace ni image ni palette : seul le bg_slot change."""
        if not self._scene or src_slot == dst_slot:
            return
        src = next((l for l in self._scene.background_layers if l.bg_slot == src_slot), None)
        dst = next((l for l in self._scene.background_layers if l.bg_slot == dst_slot), None)
        if not src or not dst:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(SwapFieldCmd(
            src, dst, "bg_slot",
            label=f"Échanger BG{src_slot} <-> BG{dst_slot}", persist_fn=_refresh,
        ))
        get_dispatcher()._emit("bg_slot_changed", src_slot)
        get_dispatcher()._emit("bg_slot_changed", dst_slot)
        self.changed.emit()

    def _on_layer_remove(self, layer):
        if not self._scene or layer not in self._scene.background_layers:
            return

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(RemoveListItemCmd(
            self._scene.background_layers, layer, persist_fn=_refresh,
            label=f"Retirer layer BG{layer.bg_slot}",
        ))
        self.changed.emit()

    def _add_bg_layer(self):
        """Ajoute un nouveau layer vide à la scène, sur un slot BG valide pour le
        mode courant (Mode 0 : BG0-3 ; Mode 1 : BG0-2 ; Mode 2 : BG2-3)."""
        if not self._scene:
            return
        valid_slots = MODE_INFO.get(getattr(self._scene, "render_mode", 0),
                                    MODE_INFO[0])["bg_slots"]
        used_slots = {L.bg_slot for L in self._scene.background_layers}
        next_slot = next((i for i in valid_slots if i not in used_slots), None)
        if next_slot is None:
            return   # tous les slots BG du mode sont occupés
        from core.project import BackgroundLayer
        new_layer = BackgroundLayer(background_name="", bg_slot=next_slot, scroll_speed=1.0)

        def _refresh():
            self._persist_scene()
            self._rebuild_layer_rows()

        get_history().push(AddListItemCmd(
            self._scene.background_layers, new_layer, persist_fn=_refresh,
            label=f"Ajouter layer BG{next_slot}",
        ))
        self.changed.emit()

    # ── Palettes actives ────────────────────────────────────────────

    _DEFAULT_PALETTE_NAME    = "DMG (GB Default)"        # OBJ : 3 nuances (index 0 transparent)
    _DEFAULT_BG_PALETTE_NAME = "DMG (GB Default) (BG)"   # BG  : 4 nuances

    def _rebuild_palette_slots(self):
        from codegen.palette_alloc import scene_palette_view, ScenePaletteView
        if not self._scene or not self._project:
            empty = ScenePaletteView("", [], [], 0)
            for pool in ("obj", "bg"):
                self._pal_grids[pool].load(empty, [])
            return

        # Catalogue unifié — les deux barres (OBJ/BG) piochent dans le même
        # project.palettes, seule la sélection ACTIVE reste séparée par pool
        # (contrainte hardware : PAL_OBJ_RAM et PAL_BG_RAM sont distincts).
        banks = list(self._project.palettes)
        for pool in ("obj", "bg"):
            attr = "active_obj_palettes" if pool == "obj" else "active_bg_palettes"
            active = getattr(self._scene, attr)

            # Scène neuve sans aucune sélection -> défaut DMG au slot 0
            # (variante BG pour le pool BG), plutôt qu'un pool entièrement
            # noir/vide. Repli sur la variante OBJ si la BG n'existe pas.
            default_name = self._DEFAULT_BG_PALETTE_NAME if pool == "bg" else self._DEFAULT_PALETTE_NAME
            if not active and not self._project.get_palette(default_name):
                default_name = self._DEFAULT_PALETTE_NAME
            if not active and self._project.get_palette(default_name):
                active.append(default_name)
                self._persist()

            view = scene_palette_view(self._project, self._scene, pool)
            self._pal_grids[pool].load(view, banks)

    # ── Handlers grille de palettes ─────────────────────────────────

    def _active_list(self, pool: str) -> list:
        return self._scene.active_obj_palettes if pool == "obj" else self._scene.active_bg_palettes

    def _palette_refresh(self, pool: str):
        """Rebâtit la grille + rafraîchit le canvas après une mutation palette."""
        self._rebuild_palette_slots()
        if pool == "bg":
            self._rebuild_layer_rows()   # les BgLayerRow résolvent leur icône via active_bg_palettes
            for L in self._scene.background_layers:
                get_dispatcher()._emit("bg_slot_changed", L.bg_slot)
        else:
            get_dispatcher()._emit("scene_sprites_changed")   # re-quantifier les acteurs
        self.changed.emit()

    def _push_palette_cmd(self, pool: str, mutate_fn, label: str):
        get_history().push(_ScenePaletteCmd(
            self._scene, pool, mutate_fn, label,
            persist_fn=self._persist,
            refresh_fn=lambda p=pool: self._palette_refresh(p),
        ))

    def _on_scene_replace(self, pool: str, slot: int, name: str):
        """Remplace la palette de scène du slot par une autre du catalogue."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)) or active[slot] == name:
            return

        def mutate(a=active, s=slot, n=name):
            a[s] = n
        self._push_palette_cmd(pool, mutate, f"Palette scène [{slot}] → {name}")

    def _on_scene_add(self, pool: str, name: str):
        """Ajoute une palette de scène au premier slot libre — donc juste après
        la dernière palette de scène (les slots libres = banques auto des
        assets). Le « + » et les grisées se décalent d'un cran."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)

        def mutate(a=active, n=name):
            free = next((i for i, x in enumerate(a) if not x), None)
            if free is None:
                a.append(n)
            else:
                a[free] = n
        self._push_palette_cmd(pool, mutate, f"Ajouter palette scène {name}")

    def _on_scene_remove(self, pool: str, slot: int):
        """Retire la palette de scène du slot et RÉINDEXE les références :
        instance pointant sur `slot` → OWN ; pointant au-delà → décrémentée."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        if not (0 <= slot < len(active)):
            return
        instances = self._instances_for(pool)

        def mutate(a=active, s=slot, insts=instances):
            del a[s]
            for o in insts:
                pb = getattr(o, "pal_bank", OWN_PAL_BANK)
                if pb == s:
                    o.pal_bank = OWN_PAL_BANK
                elif pb > s:
                    o.pal_bank = pb - 1
        self._push_palette_cmd(pool, mutate, f"Retirer palette scène [{slot}]")

    def _on_asset_override(self, pool: str, entry, name: str):
        """Override la palette propre d'un groupe d'assets vers une palette du
        CATALOGUE de l'éditeur (comme une couleur normale, pas seulement les
        palettes déjà actives de la scène) : réutilise le slot actif existant
        si `name` y figure déjà, sinon l'ajoute au premier slot libre (même
        logique que `_on_scene_add`) — jamais deux slots pour la même palette."""
        if self._blocking or not self._scene:
            return
        active = self._active_list(pool)
        targets = [i.obj for i in entry.instances if getattr(i, "obj", None) is not None]
        if not targets:
            return

        def mutate(a=active, n=name, objs=targets):
            try:
                slot = a.index(n)
            except ValueError:
                free = next((i for i, x in enumerate(a) if not x), None)
                if free is None:
                    if len(a) >= 16:
                        return
                    a.append(n)
                    slot = len(a) - 1
                else:
                    a[free] = n
                    slot = free
            for o in objs:
                o.pal_bank = slot
        self._push_palette_cmd(pool, mutate, f"Override asset → {name}")

    def _on_asset_restore(self, pool: str, entry):
        """Revient à la palette d'origine (propre) du groupe d'assets."""
        if self._blocking or not self._scene:
            return
        targets = [i.obj for i in entry.instances if getattr(i, "obj", None) is not None]
        if not targets:
            return

        def mutate(objs=targets):
            for o in objs:
                o.pal_bank = OWN_PAL_BANK
        self._push_palette_cmd(pool, mutate, "Restaurer palette d'origine")

    def _instances_for(self, pool: str) -> list:
        return self._scene.actors if pool == "obj" else self._scene.background_layers

    def _on_bound_toggled(self, idx: int):
        if self._blocking or not self._scene: return
        self._set_scene_field("collision_layer", idx, extra_persist=self._refresh_bound_rows)
        self.changed.emit()

    def _refresh_bound_rows(self):
        cl_idx = getattr(self._scene, "collision_layer", 0)
        for row in self._bg_layer_rows:
            row.set_bound(row.slot_index == cl_idx)

    def _refresh_scroll_speeds(self):
        pass  # vitesse gérée dans BackgroundAsset désormais

    def _on_scroll_changed(self):
        if self._blocking or not self._scene: return
        self._set_scene_field("scroll_h", self._chk_scroll_h.isChecked())
        self._set_scene_field("scroll_v", self._chk_scroll_v.isChecked())
        self.changed.emit()

    def _on_text_bg_changed(self):
        if self._blocking or not self._scene: return
        self._set_scene_field(
            "text_bg", self._combo_text_bg.currentData(),
            extra_persist=self._refresh_text_bg_warn,
        )
        self.changed.emit()

    def _refresh_text_bg_warn(self):
        if not self._scene: return
        self._refresh_ui_layer_marks()
        text_bg = getattr(self._scene, "text_bg", -1)
        conflict = next((l for l in self._scene.background_layers
                          if l.background_name and l.bg_slot == text_bg), None)
        self._lbl_text_bg_warn.setText(
            f"⚠ BG{text_bg} porte '{conflict.background_name}' — sera écrasé par le texte"
            if conflict else ""
        )

    def _refresh_ui_layer_marks(self):
        """Marque visuellement (icône 'UI') la rangée dont le bg_slot == Layer
        UI de la scène — son charblock est réservé à la police TTE (cf.
        main_gen._gen_scene_init), aucune image ne devrait y être assignée."""
        text_bg = getattr(self._scene, "text_bg", -1) if self._scene else -1
        for row in self._bg_layer_rows:
            row.set_ui_layer(row.slot_index == text_bg)

    def _persist(self):
        if self._project and self._scene:
            get_dispatcher().save_scene()

    def _set_scene_field(self, field: str, value, extra_persist=None):
        """Pousse un SetFieldCmd undoable sur un champ scalaire de la scène
        (no-op si la valeur est inchangée)."""
        if self._blocking or not self._scene: return
        old = getattr(self._scene, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._scene, field, old, value,
            label=f"{self._scene.name}.{field}",
            persist_fn=_do_persist,
        ))

    # ── Script de scène — helpers ──────────────────────────────────

    def _refresh_scene_script_label(self):
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc and self._project else None
        if sp and sp.exists():
            self._scene_script_slot.set_script(sp.name)
        else:
            self._scene_script_slot.clear_script()

    def _scene_script_new(self):
        """Ouvre le picker : liste des scripts de scène + bouton Nouveau."""
        if not self._scene or not self._project: return
        from ui.common.widgets import ScriptPickerPopup

        # Collecter les scripts de scène existants
        scenes_dir = self._project.scripts_scenes_dir
        scripts: list[tuple[str, str]] = []
        if scenes_dir.exists():
            for f in sorted(scenes_dir.glob("*.lua")):
                rel = str(f.relative_to(self._project.root)).replace("\\", "/")
                scripts.append((f.name, rel))

        popup = ScriptPickerPopup(scripts, C.ACCENT_ORG, parent=self)
        popup.picked.connect(self._scene_script_assign)
        popup.new_requested.connect(self._scene_script_create_new)
        popup.show_below(self._scene_script_slot)

    def _scene_script_assign(self, rel: str):
        """Assigne un script existant à la scène."""
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def _scene_script_create_new(self):
        """Dialogue de création d'un nouveau script de scène."""
        if not self._scene or not self._project: return
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nouveau script de scène", "Nom (sans .lua) :")
        if not ok or not name.strip(): return
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        d = self._project.scripts_scenes_dir
        d.mkdir(parents=True, exist_ok=True)
        sp = d / f"{name.strip()}.lua"
        if not sp.exists():
            ctx = ScriptTemplateContext(kind="scene", name=name.strip(), scene_name=self._scene.name)
            sp.write_text(generate_script_template(ctx), encoding="utf-8")
        rel = str(sp.relative_to(self._project.root)).replace("\\", "/")
        self._set_scene_field("script", rel, extra_persist=self._refresh_scene_script_label)
        self.changed.emit()
        if hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_open(self):
        if not self._scene or not self._project: return
        sc = getattr(self._scene, "script", "") or ""
        sp = self._project.asset_abs(sc) if sc else None
        if sp and sp.exists() and hasattr(self, "_script_open_fn") and self._script_open_fn:
            self._script_open_fn(str(sp))

    def _scene_script_clear(self):
        self._set_scene_field("script", "", extra_persist=self._refresh_scene_script_label)
        self.changed.emit()

    def set_script_open_fn(self, fn):
        self._script_open_fn = fn
