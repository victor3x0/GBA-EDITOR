"""
GBA Editor — Slots d'assignation d'assets
Chaque slot représente un canal GBA (BG0-BG3, Sprite).
Import : clic sur la vignette ou sur le bouton "⊕" → QFileDialog.
Drag & drop depuis l'explorateur système également supporté.
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QToolButton, QScrollArea, QDoubleSpinBox,
)
from PyQt6.QtGui import QPixmap, QFont, QDrag
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, ScriptPickerPopup
from ui.common.palette_swatch import bank_icon
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QMimeData

from core.project import Project

LAYER_NAMES  = ["BG0", "BG1", "BG2", "BG3", "Sprite"]
LAYER_COLORS = ["#4caf78", "#5b9bd5", "#9b6bc4", "#c48b3c", "#e8a838"]
MIME_TYPE     = "application/x-gba-asset-path"
MIME_BG_LAYER = "application/x-gba-bg-layer-slot"  # réordonnancement des BgLayerRow (échange de bg_slot)
IMG_EXTS     = {".png", ".bmp"}


# ──────────────────────────────────────────────────────────────────
#  Slot unique (BG0 … Sprite)
# ──────────────────────────────────────────────────────────────────
class AssignSlot(QFrame):
    """
    Un slot représente un canal GBA assignable à un PNG.
    - Clic sur la vignette ou sur ⊕ → QFileDialog
    - Drag & drop d'un fichier PNG accepté
    - Émet asset_dropped(index, chemin_absolu) ou asset_dropped(index, "") pour effacer
    """
    asset_dropped = pyqtSignal(int, str)

    def __init__(self, slot_index: int, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self._color = LAYER_COLORS[slot_index]
        self._path: str = ""
        self._highlight = False
        self.setAcceptDrops(True)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Badge nom du layer
        badge = QLabel(LAYER_NAMES[slot_index])
        badge.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        badge.setStyleSheet(f"color:{self._color};")
        badge.setFixedWidth(38)
        layout.addWidget(badge)

        # Vignette cliquable
        self._thumb = QLabel()
        self._thumb.setFixedSize(48, 34)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "background:#111; border:1px solid #2a2a2a; border-radius:2px;"
        )
        self._thumb.setToolTip("Cliquer pour importer un PNG")
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.mousePressEvent = lambda e: self._open_dialog()
        layout.addWidget(self._thumb)

        # Nom du fichier
        self._name_lbl = QLabel("Déposer ou cliquer")
        self._name_lbl.setFont(QFont(T.MONO, T.SM))
        self._name_lbl.setStyleSheet("color:#444;")
        layout.addWidget(self._name_lbl, 1)

        # Bouton import
        btn_import = QToolButton()
        btn_import.setText("⊕")
        btn_import.setToolTip("Importer un PNG")
        btn_import.setFixedSize(20, 20)
        btn_import.setStyleSheet(
            "QToolButton{color:#666;border:none;background:none;font-size:12px;}"
            "QToolButton:hover{color:#4caf78;}"
        )
        btn_import.clicked.connect(self._open_dialog)
        layout.addWidget(btn_import)

        # Bouton effacer
        self._btn_clear = QToolButton()
        self._btn_clear.setText("×")
        self._btn_clear.setFixedSize(18, 18)
        self._btn_clear.setStyleSheet(
            "QToolButton{color:#555;border:none;background:none;font-size:11px;}"
            "QToolButton:hover{color:#ff6b6b;}"
        )
        self._btn_clear.setVisible(False)
        self._btn_clear.clicked.connect(self._clear)
        layout.addWidget(self._btn_clear)

    # ── Apparence ─────────────────────────────────────────────────

    def _update_style(self):
        if self._highlight:
            self.setStyleSheet(
                f"border:2px dashed {self._color};"
                "background:#1f2a1f; border-radius:4px;"
            )
        else:
            self.setStyleSheet(
                "QFrame{border:1px solid #2a2a2a; border-radius:4px;"
                "background:#1a1a1a;}"
            )

    # ── Import ────────────────────────────────────────────────────

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Importer asset — {LAYER_NAMES[self.slot_index]}",
            "", "Images (*.png *.bmp)"
        )
        if path:
            self.set_asset(path)
            self.asset_dropped.emit(self.slot_index, path)

    def set_asset(self, path: str):
        self._path = path
        p = Path(path)
        px = QPixmap(path)
        if not px.isNull():
            self._thumb.setPixmap(
                px.scaled(48, 34,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        name = p.name
        self._name_lbl.setText(name if len(name) <= 20 else name[:19] + "…")
        self._name_lbl.setStyleSheet("color:#ccc;")
        self._btn_clear.setVisible(True)

    def clear_asset(self):
        self._path = ""
        self._thumb.setPixmap(QPixmap())
        self._name_lbl.setText("Déposer ou cliquer")
        self._name_lbl.setStyleSheet("color:#444;")
        self._btn_clear.setVisible(False)

    def _clear(self):
        self.clear_asset()
        self.asset_dropped.emit(self.slot_index, "")

    # ── Drag & drop (depuis explorateur système) ─────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(MIME_TYPE):
            self._highlight = True
            self._update_style()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight = False
        self._update_style()

    def dropEvent(self, event):
        self._highlight = False
        self._update_style()
        path = ""
        if event.mimeData().hasFormat(MIME_TYPE):
            path = bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8")
        elif event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
        if path and Path(path).suffix.lower() in IMG_EXTS:
            self.set_asset(path)
            self.asset_dropped.emit(self.slot_index, path)
            event.acceptProposedAction()


# ──────────────────────────────────────────────────────────────────
#  BgLayerRow — ligne compacte pour l'inspector de scène
# ──────────────────────────────────────────────────────────────────

class BgLayerRow(QFrame):
    """
    Ligne compacte : [○] [thumb/×] [BG0] [vitesse] [stretch] [× layer]
    - × sur la vignette → retire le background assigné
    - × à droite       → retire le layer entier
    - Vignette vide    → fond gris + icône selon l'état (vide / UI layer)
    """
    asset_changed    = pyqtSignal(int, str)
    speed_changed    = pyqtSignal(int, float)
    bound_toggled    = pyqtSignal(int)
    layer_removed    = pyqtSignal(int)
    pal_bank_changed   = pyqtSignal(int, str)  # slot_index, nom de la PaletteBank
    layer_swap_requested = pyqtSignal(int, int)  # (bg_slot source, bg_slot cible)

    _SPEED_DEFAULTS = [4.0, 3.0, 1.0, 0.5]

    def __init__(self, slot_index: int, parent=None):
        super().__init__(parent)
        self.slot_index = slot_index
        self._color = LAYER_COLORS[slot_index]
        self._path: str = ""
        self._highlight = False
        self._is_ui_layer = False
        self._pal_banks: list = []
        self._bg_names: list = []
        self._drag_start = None
        self.setAcceptDrops(True)
        self.setFixedHeight(40)
        self._update_style()

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(8)

        # Bouton collision layer
        self._radio = QPushButton("○")
        self._radio.setFixedSize(22, 22)
        self._radio.setCheckable(False)
        self._radio.setFont(QFont(T.MONO, 11))
        self._radio.setStyleSheet(
            f"QPushButton{{color:#3a3a3a;background:transparent;border:none;padding:0;}}"
            f"QPushButton:hover{{color:{self._color};}}"
        )
        self._radio.setToolTip("Définir comme layer de collision")
        self._radio.clicked.connect(lambda: self.bound_toggled.emit(self.slot_index))
        row.addWidget(self._radio)

        # Conteneur vignette + bouton × overlay
        thumb_container = QWidget()
        thumb_container.setFixedSize(48, 32)
        thumb_container.setStyleSheet("background:transparent;")

        self._thumb = QLabel(thumb_container)
        self._thumb.setGeometry(0, 0, 48, 32)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "background:#2a2a2a;border:1px solid #333;border-radius:2px;"
            f"color:#555;font-size:14px;"
        )
        self._thumb.setText("🖼")
        self._thumb.setToolTip("Cliquer ou déposer un PNG")
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.mousePressEvent = lambda e: self._open_dialog()

        self._btn_clear = QPushButton("×", thumb_container)
        self._btn_clear.setGeometry(32, 0, 16, 16)
        self._btn_clear.setFont(QFont(T.MONO, 7, QFont.Weight.Bold))
        self._btn_clear.setStyleSheet(
            "QPushButton{background:#3a1a1a;color:#cc5555;border:none;border-radius:2px;}"
            "QPushButton:hover{background:#cc3333;color:#fff;}"
        )
        self._btn_clear.setToolTip("Retirer ce background")
        self._btn_clear.setVisible(False)
        self._btn_clear.clicked.connect(self._clear)

        row.addWidget(thumb_container)

        # Badge BG0 / BG1… — aussi poignée de glisser-déposer pour réordonner
        # les layers (échange de bg_slot, donc de priorité d'affichage : cf.
        # `pri = 3 - bg` dans main_gen._gen_scene_init).
        badge = QLabel(LAYER_NAMES[slot_index])
        badge.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        badge.setStyleSheet(f"color:{self._color};background:transparent;")
        badge.setFixedWidth(34)
        badge.setCursor(Qt.CursorShape.OpenHandCursor)
        badge.setToolTip("Glisser pour échanger la priorité d'affichage avec un autre layer")
        badge.mousePressEvent = self._badge_press
        badge.mouseMoveEvent = self._badge_move
        row.addWidget(badge)

        # Spinbox vitesse
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.0, 8.0)
        self._speed.setSingleStep(0.25)
        self._speed.setDecimals(2)
        self._speed.setValue(self._SPEED_DEFAULTS[slot_index])
        self._speed.setFont(QFont(T.MONO, T.SM))
        self._speed.setFixedWidth(68)
        self._speed.setStyleSheet(QSS.spinbox)
        self._speed.valueChanged.connect(
            lambda v: self.speed_changed.emit(self.slot_index, v)
        )
        row.addWidget(self._speed)

        # Icône palette — compacte (pas de ScriptSlot complet, pas la place
        # dans une rangée de 40px). Ouvre le même ScriptPickerPopup que
        # palette_picker_slot, câblé sur BackgroundLayer.pal_bank.
        self._pal_btn = QToolButton()
        self._pal_btn.setFixedSize(30, 30)
        self._pal_btn.setIconSize(QSize(24, 24))
        self._pal_btn.setToolTip("Choisir la palette de ce layer")
        self._pal_btn.setStyleSheet(
            "QToolButton{background:transparent;border:1px solid #333;"
            "border-radius:3px;padding:0;}"
            f"QToolButton:hover{{border-color:{self._color};}}"
        )
        self._pal_btn.clicked.connect(self._open_pal_picker)
        row.addWidget(self._pal_btn)

        row.addStretch()

        btn_remove = W.btn_danger("×")
        btn_remove.setFixedSize(22, 22)
        btn_remove.setToolTip("Retirer ce layer")
        btn_remove.clicked.connect(lambda: self.layer_removed.emit(self.slot_index))
        row.addWidget(btn_remove)

    # ── Apparence ─────────────────────────────────────────────────

    def _update_style(self):
        if self._highlight:
            self.setStyleSheet(
                f"BgLayerRow{{border:2px dashed {self._color};"
                f"background:#1a2a1a;border-radius:4px;}}"
            )
        else:
            self.setStyleSheet(
                f"BgLayerRow{{border:1px solid {C.BORDER_DARK};"
                f"border-radius:4px;background:{C.BG_PANEL};}}"
            )

    # ── Asset ─────────────────────────────────────────────────────

    def set_backgrounds(self, names: list, current: str = ""):
        """Liste des BackgroundImages du projet proposées au picker de ce layer."""
        self._bg_names = list(names)

    def _open_dialog(self):
        """Choisit un BackgroundImage EXISTANT (assets/backgrounds/) — les images
        s'importent via le Background Editor, plus de QFileDialog Windows ici.
        Entrée « Vide » en tête pour un layer sans image (même contrat que
        « Sans palette » côté pal_bank, cf. ui/common/pickers.py)."""
        from ui.common.widgets import ScriptPickerPopup
        entries = [("Vide (aucune image)", "", None)]
        entries += [(n, n, None) for n in (self._bg_names or [])]
        popup = ScriptPickerPopup(entries, self._color, parent=self, new_label=None)
        popup.picked.connect(lambda name: self.asset_changed.emit(self.slot_index, name))
        popup.show_below(self._thumb)

    def set_asset(self, path: str):
        self._path = path
        px = QPixmap(path)
        if not px.isNull():
            self._thumb.setPixmap(
                px.scaled(46, 30,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._thumb.setText("")
        self._btn_clear.setVisible(True)

    def clear_asset(self):
        self._path = ""
        self._thumb.setPixmap(QPixmap())
        self._thumb.setText("UI" if self._is_ui_layer else "🖼")
        self._btn_clear.setVisible(False)

    def set_ui_layer(self, is_ui: bool):
        self._is_ui_layer = is_ui
        if not self._path:
            self._thumb.setText("UI" if is_ui else "🖼")
        if is_ui:
            self._thumb.setStyleSheet(
                "background:#1a1a2a;border:1px solid #3a3a6a;border-radius:2px;"
                "color:#5b5bd5;font-size:11px;font-weight:bold;"
            )
        else:
            self._thumb.setStyleSheet(
                "background:#2a2a2a;border:1px solid #333;border-radius:2px;"
                "color:#555;font-size:14px;"
            )

    def set_speed(self, value: float):
        self._speed.blockSignals(True)
        self._speed.setValue(value)
        self._speed.blockSignals(False)

    def set_pal_banks(self, banks: list, current_name: Optional[str]):
        """banks : PaletteBank actives de la scène (scene.active_bg_palettes,
        filtrées des slots vides/introuvables) ; current_name : nom résolu du
        slot actuel (BackgroundLayer.pal_bank), None si non résolvable —
        même contrat que component_editors/sprite.py pour Actor.pal_bank."""
        self._pal_banks = banks
        current = next((b for b in banks if b.name == current_name), None) if current_name else None
        if current:
            self._pal_btn.setIcon(bank_icon(current))
            self._pal_btn.setToolTip(f"Palette du layer : {current.name}")
        else:
            # « Sans palette » : couleurs d'origine du PNG (défaut) — icône
            # neutre plutôt qu'un bouton vide.
            from ui.common.icons import get as _ico
            self._pal_btn.setIcon(_ico("tool_palette", C.TEXT_DIM, self._color))
            self._pal_btn.setToolTip("Sans palette (couleurs du PNG) — clic pour changer")

    def _open_pal_picker(self):
        from ui.common.pickers import PALETTE_NONE
        entries = [("Sans palette (couleurs du PNG)", PALETTE_NONE, None)]
        entries += [(bank.name, bank.name, bank_icon(bank)) for bank in self._pal_banks]
        popup = ScriptPickerPopup(entries, self._color, parent=self, new_label=None)
        popup.picked.connect(lambda name: self.pal_bank_changed.emit(self.slot_index, name))
        popup.show_below(self._pal_btn)

    def set_bound(self, checked: bool):
        if checked:
            self._radio.setText("●")
            self._radio.setStyleSheet(
                f"QPushButton{{color:{self._color};background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{self._color};}}"
            )
        else:
            self._radio.setText("○")
            self._radio.setStyleSheet(
                f"QPushButton{{color:#3a3a3a;background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{self._color};}}"
            )

    def set_speed_visible(self, visible: bool):
        self._speed.setVisible(visible)

    def _clear(self):
        self.clear_asset()
        self.asset_changed.emit(self.slot_index, "")

    # ── Drag & drop — réordonnancement (échange de bg_slot/priorité) ──
    # Plus de drop de FICHIER ici : l'assignation d'une image se fait via le
    # picker de BackgroundImages (import au Background Editor). Le drag initié
    # depuis le badge BG0/BG1… sert à échanger la priorité de deux layers.

    def _badge_press(self, e):
        self._drag_start = e.position().toPoint()

    def _badge_move(self, e):
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._drag_start).manhattanLength() < 8:
            return
        self._drag_start = None
        drag = QDrag(self)
        md = QMimeData()
        md.setData(MIME_BG_LAYER, str(self.slot_index).encode("utf-8"))
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_BG_LAYER):
            self._highlight = True
            self._update_style()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._highlight = False
        self._update_style()

    def dropEvent(self, event):
        self._highlight = False
        self._update_style()
        if not event.mimeData().hasFormat(MIME_BG_LAYER):
            return
        src = int(bytes(event.mimeData().data(MIME_BG_LAYER)).decode("utf-8"))
        if src != self.slot_index:
            self.layer_swap_requested.emit(src, self.slot_index)
        event.acceptProposedAction()


# ──────────────────────────────────────────────────────────────────
#  Panneau d'assignations (BG0-BG3 + Sprite)
# ──────────────────────────────────────────────────────────────────
class AssignPanel(QWidget):
    slot_assigned = pyqtSignal(int, str)

    def __init__(self, slot_count: int = 5, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#161616;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        self._slots: list[AssignSlot] = []
        for i in range(slot_count):
            slot = AssignSlot(i)
            slot.asset_dropped.connect(self.slot_assigned)
            layout.addWidget(slot)
            self._slots.append(slot)
        layout.addStretch()

    def refresh_from_project(self, project: Project):
        scene = project.active_scene
        # BG slots — résolution depuis les layers de la SCÈNE
        by_slot = {L.bg_slot: L for L in (scene.background_layers if scene else [])}
        for i in range(min(4, len(self._slots))):
            layer = by_slot.get(i)
            if layer and layer.image:
                ba = project.get_background(layer.image)
                png = ba.source if ba and ba.source else f"{layer.image}.png"
                ap = project.background_images_dir / png
                if ap.exists():
                    self._slots[i].set_asset(str(ap))
                    continue
            self._slots[i].clear_asset()

        if len(self._slots) > 4:
            all_actors = [a for sc in project.scenes for a in sc.actors]
            actor = next((a for a in all_actors if a.get_component("sprite")), None)
            sc = actor.get_component("sprite") if actor else None
            sprite = project.get_sprite(sc.sprite_name) if sc and sc.sprite_name else None
            if sprite and sprite.asset:
                ap = project.asset_abs(sprite.asset)
                if ap and ap.exists():
                    self._slots[4].set_asset(str(ap))
                    return
            self._slots[4].clear_asset()


# ──────────────────────────────────────────────────────────────────
#  Panneau complet (wrapper pour compatibilité MainWindow)
# ──────────────────────────────────────────────────────────────────
class AssetManagerPanel(QWidget):
    slot_assigned = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:#161616; border:none;")
        self._assign = AssignPanel(slot_count=5)
        self._assign.slot_assigned.connect(self.slot_assigned)
        scroll.setWidget(self._assign)
        layout.addWidget(scroll)

    def load_project(self, project: Project):
        self._project = project
        self._assign.refresh_from_project(project)

    def refresh(self):
        if self._project:
            self._assign.refresh_from_project(self._project)
