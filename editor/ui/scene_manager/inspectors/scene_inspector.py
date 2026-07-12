"""SceneInspector — background layers, paramètres d'affichage, script de scène."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QComboBox,
    QCheckBox, QScrollArea, QPushButton,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from core.project import Project, Scene
from core.asset_manager import BgLayerRow
from core.history import get_history, SetFieldCmd, SwapFieldCmd, AddListItemCmd, RemoveListItemCmd
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, ScriptPickerPopup
from ui.common.palette_swatch import bank_icon as _bank_icon


# ──────────────────────────────────────────────────────────────────
#  _PaletteSlotGrid — 16 slots (2 barres horizontales de 8) d'un pool
# ──────────────────────────────────────────────────────────────────
class _PaletteSlotGrid(QWidget):
    """
    Grille compacte 2 lignes x 8 colonnes (2 barres horizontales) — chaque
    slot est une icône carrée cliquable (même rendu que le finder du Palette
    Editor), noire quand vide. Clic = popup de choix parmi le catalogue
    projet ; clic droit = vider.
    """

    slot_picked = pyqtSignal(int, str)   # index (0-15), nom (ou "" pour vider)

    _COLS = 8   # 2 barres horizontales de 8 (row = i//8, col = i%8)
    _ICON_SIZE = 28

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._buttons: list[QPushButton] = []

    def load(self, banks: list, active_names: list):
        for b in self._buttons:
            self._layout.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()

        for i in range(16):
            name = active_names[i] if i < len(active_names) else ""
            bank = next((b for b in banks if b.name == name), None) if name else None
            btn = QPushButton()
            btn.setFixedSize(self._ICON_SIZE + 10, self._ICON_SIZE + 10)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            if bank:
                btn.setIcon(_bank_icon(bank, size=self._ICON_SIZE))
                btn.setIconSize(QSize(self._ICON_SIZE, self._ICON_SIZE))
                btn.setToolTip(f"Slot {i} — {bank.name}")
                btn.setStyleSheet(
                    f"QPushButton{{background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};border-radius:4px;}}"
                    f"QPushButton:hover{{border-color:{self._accent};}}"
                )
            else:
                btn.setToolTip(f"Slot {i} — vide")
                btn.setStyleSheet(
                    f"QPushButton{{background:#000000;border:1px solid {C.BORDER_MID};border-radius:4px;}}"
                    f"QPushButton:hover{{border-color:{self._accent};}}"
                )
            btn.clicked.connect(lambda _c, i=i, btn=btn, banks=banks: self._open_picker(i, btn, banks))
            btn.customContextMenuRequested.connect(lambda _pos, i=i: self.slot_picked.emit(i, ""))
            row, col = divmod(i, self._COLS)
            self._layout.addWidget(btn, row, col)
            self._buttons.append(btn)

    def _open_picker(self, i: int, anchor_btn: QPushButton, banks: list):
        entries = [(b.name, b.name, _bank_icon(b)) for b in banks]
        popup = ScriptPickerPopup(entries, self._accent, parent=self, new_label=None)
        popup.picked.connect(lambda name, i=i: self.slot_picked.emit(i, name))
        popup.show_below(anchor_btn)


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

        # ── Carte Background Asset ────────────────────────────────
        bg_card, bg_inner = _card(C.ACCENT_BLU)

        bg_hdr = QHBoxLayout(); bg_hdr.setContentsMargins(0, 0, 0, 0); bg_hdr.setSpacing(4)
        bg_hdr.addWidget(_card_title("BACKGROUND", C.ACCENT_BLU), 1)
        self._btn_bg_add = W.btn_add("Ajouter un calque BG (max 4)")
        self._btn_bg_add.clicked.connect(self._add_bg_layer)
        bg_hdr.addWidget(self._btn_bg_add)
        bg_inner.addLayout(bg_hdr)

        # Rows dynamiques des BackgroundLayers (portés par la scène)
        self._bg_layer_rows: list[BgLayerRow] = []
        self._paint_target_slot: Optional[int] = None  # layer BG peint actif
        self._bg_layers_container = QVBoxLayout()
        self._bg_layers_container.setContentsMargins(0, 2, 0, 0)
        self._bg_layers_container.setSpacing(3)
        bg_inner.addLayout(self._bg_layers_container)

        cl.addWidget(bg_card)

        # ── Carte Paramètres ──────────────────────────────────────
        param_card, param_inner = _card(C.TEXT_DIM)
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

        self._pal_grids: dict[str, _PaletteSlotGrid] = {}
        for pool, color, title in (("obj", C.ACCENT_ORG, "OBJ (sprites)"),
                                    ("bg", C.ACCENT_BLU, "BACKGROUND")):
            sub_lbl = QLabel(title)
            sub_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            sub_lbl.setStyleSheet(f"color:{color}; letter-spacing:1px; margin-top:4px;")
            pal_inner.addWidget(sub_lbl)
            grid = _PaletteSlotGrid(color)
            grid.slot_picked.connect(lambda i, name, pool=pool: self._on_palette_picked(pool, i, name))
            pal_inner.addWidget(grid)
            self._pal_grids[pool] = grid

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
        self._rebuild_layer_rows()
        self._rebuild_palette_slots()
        self._blocking = False

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
            row.set_backgrounds(bg_names, layer.image)
            if layer.image:
                ba = self._project.get_background(layer.image)
                png = ba.source if ba and ba.source else f"{layer.image}.png"
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
            row.paint_target_selected.connect(self._on_paint_target)
            row.set_visible_state(getattr(layer, "visible", True))
            row.set_paint_target(layer.bg_slot == self._paint_target_slot)
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
        if not self._scene or layer.image == name:
            return
        get_history().push(SetFieldCmd(
            layer, "image", layer.image, name,
            label=f"BG{layer.bg_slot}.image",
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

    def _on_paint_target(self, bg_slot: int):
        """Sélectionne le layer peint par l'outil de peinture par palette.
        Radio-like : une seule cible active, les autres lignes se décochent."""
        self._paint_target_slot = bg_slot
        for row in self._bg_layer_rows:
            row.set_paint_target(row.slot_index == bg_slot)
        get_dispatcher()._emit("bg_paint_layer_changed", bg_slot)

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
        """Ajoute un nouveau layer vide à la scène."""
        if not self._scene or len(self._scene.background_layers) >= 4:
            return
        from core.project import BackgroundLayer
        used_slots = {L.bg_slot for L in self._scene.background_layers}
        next_slot = next((i for i in range(4) if i not in used_slots),
                         len(self._scene.background_layers))
        new_layer = BackgroundLayer(image="", bg_slot=next_slot, scroll_speed=1.0)

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
        if not self._scene or not self._project:
            for pool in ("obj", "bg"):
                self._pal_grids[pool].load([], [])
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

            self._pal_grids[pool].load(banks, active)

    def _on_palette_picked(self, pool: str, slot_idx: int, name: str):
        if self._blocking or not self._scene:
            return
        lst = self._scene.active_obj_palettes if pool == "obj" else self._scene.active_bg_palettes
        while len(lst) <= slot_idx:
            lst.append("")
        if lst[slot_idx] == name:
            return
        lst[slot_idx] = name
        self._persist()
        self._rebuild_palette_slots()
        if pool == "bg":
            # Les BgLayerRow affichent l'icône de la banque résolue via
            # layer.pal_bank -> active_bg_palettes[idx] — à reconstruire si
            # cette sélection change ailleurs que depuis la rangée elle-même.
            self._rebuild_layer_rows()
        self.changed.emit()
        self.changed.emit()

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
                          if l.image and l.bg_slot == text_bg), None)
        self._lbl_text_bg_warn.setText(
            f"⚠ BG{text_bg} porte '{conflict.image}' — sera écrasé par le texte"
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
