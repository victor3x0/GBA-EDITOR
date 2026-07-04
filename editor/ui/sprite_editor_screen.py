"""
ui/sprite_editor_screen.py — Éditeur de sprites (style GB Studio).

Layout : 3 colonnes
  Gauche  : liste des sprites du projet + arbre d'animations
  Centre  : barre playback + preview + tiles + frames  (WIP)
  Droite  : propriétés + collision + anim settings     (WIP)
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QToolButton, QTreeWidget, QTreeWidgetItem,
    QFrame, QSizePolicy, QScrollArea, QLineEdit,
    QComboBox, QFileDialog, QPushButton, QScrollArea,
    QMenu, QApplication, QInputDialog, QMessageBox, QAbstractItemView,
)
from PyQt6.QtGui import QFont, QColor, QPixmap, QImage, QDrag, QPainter, QPen, QCursor, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QRect, QSize, QTimer

from ui.widgets import W, FinderSection
from ui.theme import C, T
from ui.icons import get as _ico, COLOR_SPRITE
from core.project import Project, SpriteAsset, AnimState, AnimFrame, StateDirection, TilePlacement
from core.history import get_history, PaintFrameCmd, DeleteResourceCmd, RemoveListItemCmd
from core.command_dispatcher import get_dispatcher


# ── Helpers styles ─────────────────────────────────────────────────────────────

_PANEL_BG   = f"background:{C.BG_BASE};"
_SECTION_BG = f"background:{C.BG_PANEL};"

_HDR_STYLE = (
    f"color:{C.TEXT_DIM}; background:{C.BG_BASE};"
    f"font-family:{T.MONO}; font-size:{T.XS}px;"
    f"letter-spacing:1px; padding:4px 8px;"
    f"border-bottom:1px solid {C.BORDER_DARK};"
)
_ITEM_STYLE = (
    f"font-family:{T.MONO}; font-size:{T.SM}px;"
    f"color:{C.TEXT_NORM};"
)
_TREE_STYLE = f"""
QTreeWidget {{
    background: {C.BG_BASE};
    color: {C.TEXT_NORM};
    border: none;
    outline: none;
    font-family: {T.MONO};
    font-size: {T.SM}px;
}}
QTreeWidget::item {{
    padding: 3px 4px;
    border: none;
}}
QTreeWidget::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT_GRN};
    border-left: 2px solid {C.ACCENT_GRN};
}}
QTreeWidget::item:hover:!selected {{
    background: {C.BG_HOVER};
}}
QTreeWidget::branch {{
    background: {C.BG_BASE};
}}
QTreeWidget::branch:has-children:closed {{
    image: none;
}}
QTreeWidget::branch:has-children:open {{
    image: none;
}}
"""

_DIR_LABELS = {
    0: "All Directions",
    1: "North",      2: "North East", 3: "East",      4: "South East",
    5: "South",      6: "South West", 7: "West",      8: "North West",
}

_DIR_ICON_KEYS = {
    0: "dir_omni",
    1: "dir_n",  2: "dir_ne", 3: "dir_e",  4: "dir_se",
    5: "dir_s",  6: "dir_sw", 7: "dir_w",  8: "dir_nw",
}

_CTX_MENU_QSS = (
    f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_NORM};"
    f"border:1px solid {C.BORDER_MID};font-family:monospace;"
    f"font-size:{T.MD}px;padding:2px;}}"
    f"QMenu::item{{padding:4px 20px 4px 12px;border-radius:2px;}}"
    f"QMenu::item:selected{{background:{C.BG_SEL};color:{C.ACCENT_GRN};}}"
)

# Sentinelle : "conserver la sélection courante si elle existe encore après
# rebuild de l'arbre" — distincte de None qui signifie "ne rien sélectionner".
_KEEP_SELECTION = object()


def _dir_label(sd: StateDirection) -> str:
    base = _DIR_LABELS.get(sd.dir, str(sd.dir))
    if sd.mirror_of is not None:
        src = _DIR_LABELS.get(sd.mirror_of, str(sd.mirror_of))
        flips = ("H" if sd.flip_h else "") + ("V" if sd.flip_v else "")
        return f"{base}  ↔{src}{'['+flips+']' if flips else ''}"
    return base


# ── Panneau gauche ─────────────────────────────────────────────────────────────


class SpriteFinderPanel(QWidget):
    """
    Panneau gauche : liste des sprites (arbre fichiers) + arbre d'animations.
    Sélectionner un sprite charge ses animations dans l'arbre du dessous.
    Sélectionner une animation (StateDirection) notifie l'éditeur centre.
    """

    sprite_selected   = pyqtSignal(object)   # SpriteAsset
    direction_selected = pyqtSignal(object, object)  # AnimState, StateDirection

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(_PANEL_BG)
        self._project: Optional[Project] = None
        self._current_sprite: Optional[SpriteAsset] = None
        self._blocking = False
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Bandeau "finder" (identité du panneau, cohérent avec les
        #    autres écrans : Assets finder / Script finder / Sound finder) ──
        finder_hdr = QFrame()
        finder_hdr.setFixedHeight(20)
        finder_hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        fl = QHBoxLayout(finder_hdr)
        fl.setContentsMargins(8, 0, 0, 0)
        finder_lbl = QLabel("SPRITE FINDER")
        finder_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        finder_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        fl.addWidget(finder_lbl)
        root.addWidget(finder_hdr)

        # ── Sprites ───────────────────────────────────────────────
        sec_sprites = FinderSection("SPRITES", COLOR_SPRITE)
        sec_sprites.add_clicked.connect(self._on_add_sprite)
        root.addWidget(sec_sprites, 3)

        self._sprite_tree = QTreeWidget()
        self._sprite_tree.setHeaderHidden(True)
        self._sprite_tree.setStyleSheet(_TREE_STYLE)
        self._sprite_tree.setIndentation(14)
        self._sprite_tree.setIconSize(QSize(14, 14))
        self._sprite_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._sprite_tree.currentItemChanged.connect(self._on_sprite_item_changed)
        self._sprite_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sprite_tree.customContextMenuRequested.connect(self._on_sprite_context_menu)
        # Renommage en place : clic sur un item déjà sélectionné (pas de dialogue modal)
        self._sprite_tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._sprite_tree.itemChanged.connect(self._on_sprite_item_text_changed)
        sec_sprites.set_widget(self._sprite_tree)

        # ── Animations ────────────────────────────────────────────
        sec_anim = FinderSection("ANIMATIONS STATES", COLOR_SPRITE)
        sec_anim.add_clicked.connect(self._on_add_state)
        root.addWidget(sec_anim, 2)

        self._anim_tree = QTreeWidget()
        self._anim_tree.setHeaderHidden(True)
        self._anim_tree.setStyleSheet(_TREE_STYLE)
        self._anim_tree.setIndentation(14)
        self._anim_tree.setIconSize(QSize(14, 14))
        self._anim_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._anim_tree.currentItemChanged.connect(self._on_anim_item_changed)
        self._anim_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._anim_tree.customContextMenuRequested.connect(self._on_anim_context_menu)
        self._anim_tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._anim_tree.itemChanged.connect(self._on_anim_item_text_changed)
        sec_anim.set_widget(self._anim_tree)

    # ── API publique ──────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._refresh_sprites()

    def refresh_anim_tree(self):
        """Recharge l'arbre d'animations depuis le sprite courant (conserve la sélection)."""
        self._refresh_anim_tree(self._current_sprite)

    def select_direction(self, state: AnimState, sd: StateDirection):
        """Sélectionne explicitement (state, sd) dans l'arbre — ex: après ajout
        d'une direction depuis le panneau droit, pour que le canvas central
        bascule immédiatement dessus au lieu de rester sur l'ancienne sélection."""
        self._refresh_anim_tree(self._current_sprite, select=(state, sd))

    # ── Peuplement sprite tree ────────────────────────────────────

    def _find_sprite_item(self, sprite: Optional[SpriteAsset]) -> Optional[QTreeWidgetItem]:
        if sprite is None:
            return None
        root = self._sprite_tree.invisibleRootItem()
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, Qt.ItemDataRole.UserRole) is sprite:
                return item
            stack.extend(item.child(i) for i in range(item.childCount()))
        return None

    def _refresh_sprites(self, select: Any = _KEEP_SELECTION):
        target_sprite = self._current_sprite if select is _KEEP_SELECTION else select

        self._blocking = True
        self._sprite_tree.blockSignals(True)
        self._sprite_tree.clear()

        if not self._project:
            self._blocking = False
            self._sprite_tree.blockSignals(False)
            return

        sprites = list(self._project.sprites)
        if not sprites:
            self._blocking = False
            self._sprite_tree.blockSignals(False)
            self._current_sprite = None
            return

        # Regrouper par dossier fictif = première partie du nom (avant "_" ou "/")
        groups: dict[str, list[SpriteAsset]] = {}
        ungrouped: list[SpriteAsset] = []
        for sp in sorted(sprites, key=lambda s: s.name):
            parts = sp.name.split("_", 1)
            if len(parts) > 1 and len(parts[0]) > 2:
                groups.setdefault(parts[0], []).append(sp)
            else:
                ungrouped.append(sp)

        # Items sans groupe
        for sp in ungrouped:
            self._make_sprite_item(self._sprite_tree.invisibleRootItem(), sp)

        # Groupes
        for grp_name, members in groups.items():
            if len(members) == 1:
                self._make_sprite_item(self._sprite_tree.invisibleRootItem(), members[0])
                continue
            grp_item = QTreeWidgetItem([f"  {grp_name}"])
            grp_item.setFont(0, QFont(T.MONO, T.SM, QFont.Weight.Bold))
            grp_item.setForeground(0, QColor(C.TEXT_DIM))
            grp_item.setData(0, Qt.ItemDataRole.UserRole, None)
            self._sprite_tree.invisibleRootItem().addChild(grp_item)
            grp_item.setExpanded(True)
            for sp in members:
                self._make_sprite_item(grp_item, sp)

        self._blocking = False
        self._sprite_tree.blockSignals(False)

        # Sélectionner le sprite ciblé si possible, sinon le premier
        target_item = self._find_sprite_item(target_sprite)
        if target_item is None:
            first = self._sprite_tree.topLevelItem(0)
            target_item = (first.child(0) if first.childCount() else first) if first else None
        if target_item is not None:
            self._sprite_tree.setCurrentItem(target_item)

    def _make_sprite_item(self, parent: QTreeWidgetItem, sp: SpriteAsset):
        item = QTreeWidgetItem([sp.name])
        item.setFont(0, QFont(T.MONO, T.SM))
        item.setForeground(0, QColor(C.TEXT_NORM))
        item.setIcon(0, _ico("sprite", COLOR_SPRITE))
        item.setData(0, Qt.ItemDataRole.UserRole, sp)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    # ── Peuplement anim tree ──────────────────────────────────────

    def _refresh_anim_tree(self, sprite: Optional[SpriteAsset], select: Any = _KEEP_SELECTION):
        if select is _KEEP_SELECTION:
            current = self._anim_tree.currentItem()
            data = current.data(0, Qt.ItemDataRole.UserRole) if current else None
            target = data if isinstance(data, tuple) else None
        else:
            target = select

        self._blocking = True
        self._anim_tree.blockSignals(True)
        self._anim_tree.clear()

        if not sprite:
            self._blocking = False
            self._anim_tree.blockSignals(False)
            return

        for state in sprite.states:
            state_item = QTreeWidgetItem([state.name])
            state_item.setFont(0, QFont(T.MONO, T.SM, QFont.Weight.Bold))
            state_item.setForeground(0, QColor(C.TEXT_HI))
            state_item.setIcon(0, _ico("anim_state", COLOR_SPRITE))
            state_item.setData(0, Qt.ItemDataRole.UserRole, (state, None))
            state_item.setFlags(state_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._anim_tree.addTopLevelItem(state_item)
            state_item.setExpanded(True)

            for sd in state.directions:
                lbl = _dir_label(sd)
                sd_item = QTreeWidgetItem([f"    {lbl}"])
                sd_item.setFont(0, QFont(T.MONO, T.SM))
                mirrored = sd.mirror_of is not None
                fg = C.TEXT_DIM if mirrored else C.TEXT_NORM
                sd_item.setForeground(0, QColor(fg))
                icon_color = C.ACCENT_BLU if mirrored else COLOR_SPRITE
                sd_item.setIcon(0, _ico(_DIR_ICON_KEYS.get(sd.dir, "dir_omni"), icon_color))
                sd_item.setData(0, Qt.ItemDataRole.UserRole, (state, sd))
                state_item.addChild(sd_item)

        self._blocking = False
        self._anim_tree.blockSignals(False)

        # Sélectionner la cible demandée si elle existe encore, sinon la
        # première direction du premier état.
        target_item = None
        if target:
            t_state, t_sd = target
            for i in range(self._anim_tree.topLevelItemCount()):
                state_item = self._anim_tree.topLevelItem(i)
                data = state_item.data(0, Qt.ItemDataRole.UserRole)
                if not data or data[0] is not t_state:
                    continue
                if t_sd is None:
                    target_item = state_item.child(0) if state_item.childCount() else state_item
                else:
                    for j in range(state_item.childCount()):
                        child = state_item.child(j)
                        cdata = child.data(0, Qt.ItemDataRole.UserRole)
                        if cdata and cdata[1] is t_sd:
                            target_item = child
                            break
                break
        if target_item is None:
            first = self._anim_tree.topLevelItem(0)
            if first and first.childCount():
                target_item = first.child(0)
        if target_item is not None:
            self._anim_tree.setCurrentItem(target_item)

    # ── Slots ─────────────────────────────────────────────────────

    def _on_sprite_item_changed(self, current, _prev):
        if self._blocking or not current:
            return
        sp = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(sp, SpriteAsset):
            return
        self._current_sprite = sp
        # Le sprite actif doit être propagé avant que l'arbre d'animations
        # ne sélectionne automatiquement sa première direction (sinon le
        # panneau central résout encore l'ancien sprite/PNG).
        self.sprite_selected.emit(sp)
        self._refresh_anim_tree(sp)

    def _on_anim_item_changed(self, current, _prev):
        if self._blocking or not current:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        state, sd = data
        if sd is None:
            sd = state.directions[0] if state.directions else None
        if sd is not None:
            self.direction_selected.emit(state, sd)

    def _on_add_state(self):
        if not self._current_sprite:
            return
        name = f"State{len(self._current_sprite.states) + 1}"
        new_state = AnimState(name=name)
        self._current_sprite.states.append(new_state)
        if self._project:
            get_dispatcher().save_sprite(self._current_sprite)
        self._refresh_anim_tree(self._current_sprite, select=(new_state, None))

    # ── Sprites : ajout / renommage / suppression ───────────────────

    def _on_add_sprite(self):
        if not self._project:
            return
        name, ok = QInputDialog.getText(self, "Nouveau sprite", "Nom :")
        name = name.strip() if ok else ""
        if not name:
            return
        if self._project.sprites.get(name):
            QMessageBox.warning(self, "Nom déjà utilisé",
                                f"Un sprite nommé « {name} » existe déjà.")
            return
        sprite = SpriteAsset(name=name)
        self._project.sprites.append(sprite)
        self._project.sprites.save(sprite)
        self._refresh_sprites(select=sprite)

    def _on_sprite_context_menu(self, pos):
        item = self._sprite_tree.itemAt(pos)
        if not item:
            return
        sp = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(sp, SpriteAsset):
            return
        menu = QMenu(self)
        menu.setStyleSheet(_CTX_MENU_QSS)
        delete_a = menu.addAction("Supprimer le sprite")
        act = menu.exec(self._sprite_tree.viewport().mapToGlobal(pos))
        if act == delete_a:
            self._delete_sprite(sp)

    def _on_sprite_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        sp = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(sp, SpriteAsset):
            return
        new_name = item.text(0).strip()
        if not new_name or new_name == sp.name:
            self._sprite_tree.blockSignals(True)
            item.setText(0, sp.name)
            self._sprite_tree.blockSignals(False)
            return
        if not self._project or self._project.sprites.get(new_name):
            QMessageBox.warning(self, "Nom déjà utilisé",
                                f"Un sprite nommé « {new_name} » existe déjà.")
            self._sprite_tree.blockSignals(True)
            item.setText(0, sp.name)
            self._sprite_tree.blockSignals(False)
            return
        self._project.sprites.rename(sp, new_name)
        self._sprite_tree.blockSignals(True)
        item.setText(0, sp.name)
        self._sprite_tree.blockSignals(False)
        # setCurrentItem() ne réémet pas currentItemChanged si l'item était déjà
        # courant : forcer explicitement le rafraîchissement des panneaux
        # centre/droite pour que le nouveau nom s'y reflète.
        self.sprite_selected.emit(sp)

    def _delete_sprite(self, sp: SpriteAsset):
        if not self._project:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer le sprite « {sp.name} » ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        get_history().push(DeleteResourceCmd(
            self._project.sprites, sp,
            lambda: self._refresh_sprites(),
        ))

    # ── Animations : renommage / suppression d'un état ──────────────

    def _on_anim_context_menu(self, pos):
        item = self._anim_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        state, sd = data
        if sd is not None:
            return  # pas de menu sur une direction (gérée via le panneau DIRECTIONS)
        menu = QMenu(self)
        menu.setStyleSheet(_CTX_MENU_QSS)
        delete_a = menu.addAction("Supprimer l'état")
        can_delete = bool(self._current_sprite) and len(self._current_sprite.states) > 1
        delete_a.setEnabled(can_delete)
        act = menu.exec(self._anim_tree.viewport().mapToGlobal(pos))
        if act == delete_a:
            self._delete_state(state)

    def _on_anim_item_text_changed(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or data[1] is not None:
            return  # seuls les états (pas les directions) sont renommables
        state: AnimState = data[0]
        new_name = item.text(0).strip()
        if not new_name or new_name == state.name:
            self._anim_tree.blockSignals(True)
            item.setText(0, state.name)
            self._anim_tree.blockSignals(False)
            return
        state.name = new_name
        if self._project and self._current_sprite:
            get_dispatcher().save_sprite(self._current_sprite)
        self._anim_tree.blockSignals(True)
        item.setText(0, state.name)
        self._anim_tree.blockSignals(False)

    def _delete_state(self, state: AnimState):
        if not self._current_sprite or len(self._current_sprite.states) <= 1:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer l'état « {state.name} » ?\n(Ctrl+Z pour annuler)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        sprite = self._current_sprite
        project = self._project
        get_history().push(RemoveListItemCmd(
            sprite.states, state,
            persist_fn=(lambda: get_dispatcher().save_sprite(sprite)) if project else None,
            label=f"Supprimer état {state.name}",
        ))
        self._refresh_anim_tree(self._current_sprite)


# ── Zone centre — Preview ──────────────────────────────────────────────────────

class _PlaybackBar(QWidget):
    """Barre de contrôle playback (|◀ ▶ ▶| ⊞ ◉)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER_DARK};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(2)

        _BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;"
            f"font-size:{T.LG}px;padding:4px 8px;min-width:28px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
            f"QToolButton:checked{{color:{C.ACCENT_GRN};border-color:{C.ACCENT_GRN};}}"
        )

        from ui.icons import get as _ico

        specs = [
            ("playback_prev",     "Première frame"),
            ("playback_play",     "Lecture"),
            ("playback_next",     "Dernière frame"),
            (None, None),
            ("playback_grid",     "Afficher grille"),
            # Placeholder en attendant la gestion des palettes de couleurs —
            # désactivé pour ne pas laisser croire qu'il fait quelque chose.
            ("tool_palette",      "Couleur de peinture (bientôt disponible)"),
        ]

        self.btn_play: Optional[QToolButton] = None
        self.btn_grid: Optional[QToolButton] = None

        for icon_key, tip in specs:
            if icon_key is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color:{C.BORDER}; margin:6px 4px;")
                layout.addWidget(sep)
                continue
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, C.TEXT_DIM, C.ACCENT_GRN))
            btn.setIconSize(QSize(18, 18))
            btn.setStyleSheet(_BTN)
            btn.setCheckable(icon_key in ("playback_play", "playback_grid"))
            if icon_key == "tool_palette":
                btn.setEnabled(False)
            if tip:
                btn.setToolTip(tip)
            layout.addWidget(btn)
            if icon_key == "playback_play":
                self.btn_play = btn
            elif icon_key == "playback_grid":
                btn.setChecked(True)
                self.btn_grid = btn

        layout.addStretch()

        self._info = QLabel("")
        self._info.setFont(QFont(T.MONO, T.XS))
        self._info.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        layout.addWidget(self._info)

    def set_info(self, tiles: int, unique: int):
        self._info.setText(f"Tiles={tiles}  Unique={unique}")


# ── Frame timeline ─────────────────────────────────────────────────────────────

_THUMB_IMG  = 52   # px image dans la vignette
_THUMB_W    = 64   # largeur totale vignette
_THUMB_H    = 74   # image + label index
_TIMELINE_H = 106  # hauteur fixe de la zone timeline


def _compose_frame_image(abs_path: Optional[Path], frame: AnimFrame, fw: int, fh: int):
    """Compose une frame fw×fh en peignant chaque tuile 8×8 depuis le PNG source (PIL Image)."""
    from PIL import Image
    out = Image.new("RGBA", (max(fw, 1), max(fh, 1)), (0, 0, 0, 0))
    if not abs_path or not abs_path.exists() or not frame.tiles:
        return out
    try:
        img = Image.open(abs_path).convert("RGBA")
        sw, sh = img.size
        for t in frame.tiles:
            sx, sy = t.src_col * 8, t.src_row * 8
            if sx < 0 or sy < 0 or sx + 8 > sw or sy + 8 > sh:
                continue
            piece = img.crop((sx, sy, sx + 8, sy + 8))
            if t.flip_h:
                piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
            if t.flip_v:
                piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
            dx, dy = t.dst_col * 8, t.dst_row * 8
            out.paste(piece, (dx, dy), piece)
    except Exception:
        pass
    return out


def _pil_to_pixmap(img, size: int) -> QPixmap:
    if img.width <= 0 or img.height <= 0:
        pm = QPixmap(size, size)
        pm.fill(QColor(C.BG_PANEL))
        return pm
    img = img.resize((size, size), __import__("PIL").Image.NEAREST)
    data = bytes(img.tobytes("raw", "RGBA"))
    qi = QImage(data, size, size, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


def _make_frame_pixmap(abs_path: Optional[Path], frame: AnimFrame,
                       fw: int, fh: int, size: int = _THUMB_IMG) -> QPixmap:
    img = _compose_frame_image(abs_path, frame, fw, fh)
    return _pil_to_pixmap(img, size)


def _clone_frame(frame: AnimFrame) -> AnimFrame:
    return AnimFrame(tiles=[
        TilePlacement(t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
        for t in frame.tiles
    ])


class _FrameThumb(QFrame):
    """Vignette d'un frame, draggable via QDrag."""

    MIME = "application/x-frame-index"

    clicked        = pyqtSignal(int)  # index
    context_asked  = pyqtSignal(int, object)  # index, QPoint global

    def __init__(self, index: int, frame: AnimFrame,
                 pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._index    = index
        self._frame    = frame
        self._selected = False
        self._press_pos: Optional[QPoint] = None

        self.setFixedSize(_THUMB_W, _THUMB_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(False)

        self._pix_lbl = QLabel(self)
        self._pix_lbl.setPixmap(pixmap)
        self._pix_lbl.setGeometry((_THUMB_W - _THUMB_IMG) // 2, 4, _THUMB_IMG, _THUMB_IMG)
        self._pix_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._idx_lbl = QLabel(str(index + 1), self)
        self._idx_lbl.setFont(QFont(T.MONO, T.XS))
        self._idx_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idx_lbl.setGeometry(0, _THUMB_IMG + 8, _THUMB_W, 14)
        self._idx_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._refresh_style()

    def set_selected(self, sel: bool):
        if self._selected != sel:
            self._selected = sel
            self._refresh_style()

    def update_index(self, index: int):
        self._index = index
        self._idx_lbl.setText(str(index + 1))

    def update_pixmap(self, pixmap: QPixmap):
        self._pix_lbl.setPixmap(pixmap)

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(
                f"QFrame{{background:{C.BG_SEL};border:2px solid {C.ACCENT_GRN};"
                f"border-radius:4px;}}"
            )
            self._idx_lbl.setStyleSheet(
                f"color:{C.ACCENT_GRN};background:transparent;")
        else:
            self.setStyleSheet(
                f"QFrame{{background:{C.BG_INPUT};border:1px solid {C.BORDER};"
                f"border-radius:4px;}}"
            )
            self._idx_lbl.setStyleSheet(
                f"color:{C.TEXT_DIM};background:transparent;")

    # ── Events ────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.pos()
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_asked.emit(self._index, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._press_pos is None:
            return
        if (e.pos() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return
        # Démarrer le drag
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME, str(self._index).encode())
        drag.setMimeData(mime)
        # Ghost semi-transparent
        ghost = self.grab()
        painter = QPainter(ghost)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(ghost.rect(), QColor(0, 0, 0, 160))
        painter.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(self._press_pos)
        self._press_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            self.clicked.emit(self._index)
            self._press_pos = None


class _FrameTimeline(QWidget):
    """
    Bande horizontale de frames avec :
    - clic → sélection
    - drag-drop → réordonnancement
    - clic droit → copy / clone / delete
    - bouton + → ajouter une frame
    """

    frame_selected = pyqtSignal(int)    # index sélectionné
    frames_changed = pyqtSignal()       # frames modifiées (save)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_TIMELINE_H)
        self.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-top:1px solid {C.BORDER_DARK};"
        )
        # Focus requis pour que Ctrl+D / Suppr n'agissent que quand la
        # timeline est active (ex: pas pendant l'édition d'un nom ailleurs).
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._sprite:    Optional[SpriteAsset]    = None
        self._state:     Optional[AnimState]       = None
        self._sd:        Optional[StateDirection]  = None
        self._abs_path:  Optional[Path]            = None
        self._selected:  int                       = 0
        self._thumbs:    list[_FrameThumb]         = []
        self._drop_before: Optional[int]           = None   # indicateur pendant drag

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Label section
        hdr = QLabel("  FRAMES")
        hdr.setFont(QFont(T.MONO, T.XS))
        hdr.setFixedHeight(18)
        hdr.setStyleSheet(
            f"color:{C.TEXT_DIM};background:{C.BG_RAISED};"
            f"border-bottom:1px solid {C.BORDER_DARK};"
        )
        outer.addWidget(hdr)

        # Zone de scroll horizontale
        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:horizontal{height:6px;}"
        )

        self._content = QWidget()
        self._content.setAcceptDrops(True)
        self._content.dragEnterEvent  = self._drag_enter
        self._content.dragMoveEvent   = self._drag_move
        self._content.dragLeaveEvent  = self._drag_leave
        self._content.dropEvent       = self._drop
        self._content.paintEvent      = self._paint_drop_indicator

        self._layout = QHBoxLayout(self._content)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Bouton +
        self._add_btn = QToolButton()
        self._add_btn.setText("+")
        self._add_btn.setFixedSize(36, _THUMB_H)
        self._add_btn.setStyleSheet(
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px dashed {C.BORDER};border-radius:4px;"
            f"font-size:{T.LG}px;}}"
            f"QToolButton:hover{{color:{C.ACCENT_GRN};border-color:{C.ACCENT_GRN};}}"
        )
        self._add_btn.setToolTip("Ajouter une frame")
        self._add_btn.clicked.connect(self._on_add)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        # Raccourcis : n'agissent que quand la timeline (ou un enfant) a le focus.
        dup = QShortcut(QKeySequence("Ctrl+D"), self)
        dup.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        dup.activated.connect(lambda: self._copy_frame(self._selected))
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.activated.connect(lambda: self._delete_frame(self._selected))

    # ── API publique ───────────────────────────────────────────────────

    def load(self, sprite: SpriteAsset, state: AnimState,
             sd: StateDirection, abs_path: Optional[Path]):
        self._sprite   = sprite
        self._state    = state
        self._sd       = sd
        self._abs_path = abs_path
        self._selected = 0
        self._rebuild()

    def clear(self):
        self._sprite = self._state = self._sd = None
        self._rebuild()

    # ── Construction ──────────────────────────────────────────────────

    def _rebuild(self):
        # Supprimer les anciens thumbs
        for t in self._thumbs:
            self._layout.removeWidget(t)
            t.deleteLater()
        self._thumbs.clear()

        # Retirer le stretch (dernier) et le bouton + pour les réinsérer
        while self._layout.count():
            item = self._layout.itemAt(self._layout.count() - 1)
            if item.widget() is self._add_btn or item.spacerItem():
                self._layout.takeAt(self._layout.count() - 1)
            else:
                break
        # hide() avant setParent(None) : même détaché puis rattaché dans la
        # foulée (voir plus bas), un bouton visible reparenté à rien devient
        # furtivement une fenêtre top-level ("micro popup" au changement de
        # sprite sélectionné).
        self._add_btn.hide()
        self._add_btn.setParent(None)

        if self._sd:
            fw = self._sprite.frame_w if self._sprite else 16
            fh = self._sprite.frame_h if self._sprite else 16
            for i, frame in enumerate(self._sd.frames):
                pm  = _make_frame_pixmap(self._abs_path, frame, fw, fh)
                t   = _FrameThumb(i, frame, pm)
                t.set_selected(i == self._selected)
                t.clicked.connect(self._on_thumb_clicked)
                t.context_asked.connect(self._on_context_menu)
                self._layout.addWidget(t)
                self._thumbs.append(t)

        self._layout.addWidget(self._add_btn)
        self._add_btn.show()
        self._layout.addStretch()

        # Hauteur fixe = viewport, largeur = nombre de frames
        n = len(self._thumbs)
        content_w = n * (_THUMB_W + 6) + 16 + 6 + 42   # thumbs + marges + btn +
        vp_h = _TIMELINE_H - 20   # hauteur header (18) + séparateur (2)
        self._content.setFixedSize(max(content_w, self._scroll.width()), vp_h)

    def _select(self, index: int):
        if self._sd and 0 <= index < len(self._sd.frames):
            for i, t in enumerate(self._thumbs):
                t.set_selected(i == index)
            self._selected = index
            self.frame_selected.emit(index)

    def refresh_thumb(self, index: int, pixmap: QPixmap):
        """Met à jour l'image d'une vignette sans changer la sélection (après peinture)."""
        if 0 <= index < len(self._thumbs):
            self._thumbs[index].update_pixmap(pixmap)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_thumb_clicked(self, index: int):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._select(index)

    def _on_add(self):
        if not self._sd:
            return
        # Copie de la frame sélectionnée (ou frame vide)
        if self._sd.frames:
            src = self._sd.frames[self._selected]
            self._sd.frames.append(_clone_frame(src))
        else:
            self._sd.frames.append(AnimFrame())
        self.frames_changed.emit()
        self._rebuild()
        self._select(len(self._sd.frames) - 1)

    def _on_context_menu(self, index: int, pos: QPoint):
        if not self._sd:
            return
        menu = QMenu(self)
        menu.setStyleSheet(_CTX_MENU_QSS)
        copy_a  = menu.addAction("Copier              Ctrl+D")
        clone_a = menu.addAction("Cloner")
        clear_a = menu.addAction("Vider la frame")
        menu.addSeparator()
        del_a   = menu.addAction("Supprimer           Suppr")
        del_a.setEnabled(len(self._sd.frames) > 1)

        act = menu.exec(pos)
        if act == copy_a:
            self._copy_frame(index)
        elif act == clone_a:
            self._clone_frame_to_end(index)
        elif act == clear_a:
            self._clear_frame(index)
        elif act == del_a:
            self._delete_frame(index)

    # ── Actions frame (partagées menu contextuel + raccourcis clavier) ──

    def _copy_frame(self, index: int):
        if not self._sd or not self._sd.frames:
            return
        src = self._sd.frames[index]
        self._sd.frames.insert(index + 1, _clone_frame(src))
        self.frames_changed.emit()
        self._rebuild()
        self._select(index + 1)

    def _clone_frame_to_end(self, index: int):
        if not self._sd or not self._sd.frames:
            return
        src = self._sd.frames[index]
        self._sd.frames.append(_clone_frame(src))
        self.frames_changed.emit()
        self._rebuild()
        self._select(len(self._sd.frames) - 1)

    def _clear_frame(self, index: int):
        if not self._sd or not self._sd.frames:
            return
        self._sd.frames[index].tiles.clear()
        self.frames_changed.emit()
        self._rebuild()
        self._select(index)

    def _delete_frame(self, index: int):
        if not self._sd or len(self._sd.frames) <= 1:
            return
        self._sd.frames.pop(index)
        self.frames_changed.emit()
        self._rebuild()
        self._select(min(index, len(self._sd.frames) - 1))

    # ── Drag-drop reorder ─────────────────────────────────────────────

    def _drag_enter(self, e):
        if e.mimeData().hasFormat(_FrameThumb.MIME):
            e.acceptProposedAction()

    def _drag_move(self, e):
        if not e.mimeData().hasFormat(_FrameThumb.MIME):
            return
        self._drop_before = self._drop_index(e.position().toPoint().x())
        self._content.update()
        e.acceptProposedAction()

    def _drag_leave(self, e):
        self._drop_before = None
        self._content.update()

    def _drop(self, e):
        if not e.mimeData().hasFormat(_FrameThumb.MIME) or not self._sd:
            return
        src_idx  = int(e.mimeData().data(_FrameThumb.MIME).data())
        dst_idx  = self._drop_index(e.position().toPoint().x())
        self._drop_before = None
        self._content.update()

        if src_idx == dst_idx or src_idx + 1 == dst_idx:
            return
        frame = self._sd.frames.pop(src_idx)
        insert_at = dst_idx if dst_idx <= src_idx else dst_idx - 1
        self._sd.frames.insert(insert_at, frame)
        self.frames_changed.emit()
        self._rebuild()
        self._select(insert_at)
        e.acceptProposedAction()

    def _drop_index(self, x: int) -> int:
        """Retourne l'index d'insertion (0..n) correspondant à la position x."""
        for i, t in enumerate(self._thumbs):
            mid = t.x() + t.width() // 2
            if x < mid:
                return i
        return len(self._thumbs)

    def _paint_drop_indicator(self, e):
        """Ligne verte indiquant l'emplacement de dépôt."""
        from PyQt6.QtGui import QPainter, QPen
        QWidget.paintEvent(self._content, e)
        if self._drop_before is None or not self._thumbs:
            return
        painter = QPainter(self._content)
        pen = QPen(QColor(C.ACCENT_GRN), 2)
        painter.setPen(pen)
        n = len(self._thumbs)
        if self._drop_before < n:
            t = self._thumbs[self._drop_before]
            x = t.x() - 3
        else:
            t = self._thumbs[-1]
            x = t.x() + t.width() + 3
        y1 = t.y()
        y2 = t.y() + t.height()
        painter.drawLine(x, y1, x, y2)
        painter.end()


# ── Canvas de frame (composition peinte tuile par tuile) ───────────────────────

class _FrameCanvas(QWidget):
    """
    Zone de composition — grille de tuiles 8×8.
    Clic gauche = peindre (brosse active) ou sélectionner/ramasser des
    tuiles déjà posées (aucune brosse active) ; clic droit = effacer +
    reset sélection picker. Molette = zoom, molette centrale glissée = pan.
    Shift+X / Shift+Y = flip horizontal/vertical de la brosse active.
    """

    frame_painted      = pyqtSignal()
    selection_reset    = pyqtSignal()   # demande reset de la sélection dans le picker
    hover_changed       = pyqtSignal(object)  # (col, row) survolé, ou None
    brush_picked_up     = pyqtSignal(int)     # nb de tuiles ramassées depuis le canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sprite:     Optional[SpriteAsset] = None
        self._abs_path:   Optional[Path]        = None
        self._src_pixmap: Optional[QPixmap]     = None
        self._frame:      Optional[AnimFrame]   = None
        self._tile_w = self._tile_h = 1
        self._show_grid  = True
        # (rel_c, rel_r, src_col, src_row, flip_h, flip_v)
        self._brush: list[tuple[int, int, int, int, bool, bool]] = []
        self._hover: Optional[tuple[int, int]]       = None
        self._persist_fn = None
        # Zoom/pan manuel
        self._zoom: int = 0          # 0 = auto-fit, >0 = manuel
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._mid_drag: Optional[tuple] = None   # (start_pos, start_pan_x, start_pan_y)
        # Sélection de tuiles déjà posées (active seulement sans brosse)
        self._select_start: Optional[tuple[int, int]] = None
        self._select_end:   Optional[tuple[int, int]] = None
        self.setMinimumHeight(80)
        self.setMouseTracking(True)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        # Focus au clic — les raccourcis Shift+X/Y sont portés par
        # SpriteCenterPanel (WidgetWithChildrenShortcut) pour marcher aussi
        # bien après un clic dans le tile picker qu'après un clic ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ── API ──────────────────────────────────────────────────────────

    def load_frame(self, sprite: Optional[SpriteAsset], abs_path: Optional[Path],
                   frame: Optional[AnimFrame]):
        self._sprite   = sprite
        self._abs_path = abs_path
        self._frame    = frame
        self._tile_w   = sprite.tile_w if sprite else 1
        self._tile_h   = sprite.tile_h if sprite else 1
        self._src_pixmap = QPixmap(str(abs_path)) if abs_path and abs_path.exists() else None
        self._zoom = 0; self._pan_x = self._pan_y = 0
        self.update()

    def set_brush(self, tiles: list[tuple[int, int]]):
        if not tiles:
            self._brush = []
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            min_c = min(c for c, r in tiles)
            min_r = min(r for c, r in tiles)
            self._brush = [(c - min_c, r - min_r, c, r, False, False) for c, r in tiles]
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def flip_brush_x(self):
        """Miroir horizontal de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_h)."""
        if not self._brush:
            return
        max_c = max(rel_c for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(max_c - rel_c, rel_r, sc, sr, not fh, fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def flip_brush_y(self):
        """Miroir vertical de la brosse active — réarrange les tuiles
        ET retourne le contenu de chaque tuile (flip_v)."""
        if not self._brush:
            return
        max_r = max(rel_r for rel_c, rel_r, sc, sr, fh, fv in self._brush)
        self._brush = [(rel_c, max_r - rel_r, sc, sr, fh, not fv)
                       for rel_c, rel_r, sc, sr, fh, fv in self._brush]
        self.update()

    def set_persist_fn(self, fn):
        self._persist_fn = fn

    def set_grid(self, on: bool):
        self._show_grid = on
        self.update()

    # ── Géométrie ────────────────────────────────────────────────────

    def _auto_zoom(self) -> int:
        w, h = self.width(), self.height()
        pw, ph = max(self._tile_w * 8, 1), max(self._tile_h * 8, 1)
        return max(1, min(w // pw, h // ph))

    # ── Zoom (molette ou boutons du header) ─────────────────────────

    def _adjust_zoom(self, delta: int):
        cur = self._zoom if self._zoom > 0 else self._auto_zoom()
        self._zoom = max(1, min(24, cur + delta))
        if self._zoom == self._auto_zoom():
            self._zoom = 0; self._pan_x = self._pan_y = 0
        self.update()

    def zoom_in(self):
        self._adjust_zoom(1)

    def zoom_out(self):
        self._adjust_zoom(-1)

    def zoom_fit(self):
        self._zoom = 0
        self._pan_x = self._pan_y = 0
        self.update()

    def _geometry(self):
        zoom = self._zoom if self._zoom > 0 else self._auto_zoom()
        pw, ph = self._tile_w * 8, self._tile_h * 8
        dw, dh = pw * zoom, ph * zoom
        ox = (self.width()  - dw) // 2 + self._pan_x
        oy = (self.height() - dh) // 2 + self._pan_y
        return zoom, ox, oy, dw, dh

    def _cell_at(self, pos) -> Optional[tuple[int, int]]:
        zoom, ox, oy, dw, dh = self._geometry()
        x, y = pos.x() - ox, pos.y() - oy
        if x < 0 or y < 0 or x >= dw or y >= dh:
            return None
        return int(x // (8 * zoom)), int(y // (8 * zoom))

    # ── Événements souris ─────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = (e.pos(), self._pan_x, self._pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._frame or not self._sprite:
            return
        cell = self._cell_at(e.position())
        if cell is None:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._brush:
                self._do_paint(*cell)
            else:
                # Pas de brosse active : démarrer une sélection rectangulaire
                # des tuiles déjà posées, pour les ramasser (cf mouseReleaseEvent).
                self._select_start = self._select_end = cell
                self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._do_erase(*cell)
            self.selection_reset.emit()

    def mouseMoveEvent(self, e):
        if self._mid_drag and e.buttons() & Qt.MouseButton.MiddleButton:
            sp, spx, spy = self._mid_drag
            self._pan_x = spx + int(e.pos().x() - sp.x())
            self._pan_y = spy + int(e.pos().y() - sp.y())
            self.update(); return
        cell = self._cell_at(e.position())
        if cell != self._hover:
            self._hover = cell
            self.update()
            self.hover_changed.emit(cell)
        if e.buttons() & Qt.MouseButton.LeftButton and cell:
            if self._brush:
                self._do_paint(*cell)
            elif self._select_start is not None:
                self._select_end = cell
                self.update()
        elif e.buttons() & Qt.MouseButton.RightButton and cell:
            self._do_erase(*cell)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor if self._brush
                           else Qt.CursorShape.ArrowCursor)
        elif e.button() == Qt.MouseButton.LeftButton and self._select_start is not None:
            self._finish_canvas_selection()

    def leaveEvent(self, e):
        self._hover = None
        self.update()
        self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._adjust_zoom(1 if delta > 0 else -1)
        e.accept()

    # ── Peinture / effacement ─────────────────────────────────────────

    def _snapshot(self) -> list:
        return [TilePlacement(t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
                for t in self._frame.tiles]

    def _do_paint(self, col: int, row: int):
        if not self._frame or not self._brush:
            return
        old = self._snapshot()
        changed = False
        for rel_c, rel_r, sc, sr, fh, fv in self._brush:
            dc, dr = col + rel_c, row + rel_r
            if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                continue
            self._frame.tiles = [t for t in self._frame.tiles
                                 if not (t.dst_col == dc and t.dst_row == dr)]
            self._frame.tiles.append(TilePlacement(sc, sr, dc, dr, fh, fv))
            changed = True
        if changed:
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _do_erase(self, col: int, row: int):
        if not self._frame:
            return
        old = self._snapshot()
        self._frame.tiles = [t for t in self._frame.tiles
                             if not (t.dst_col == col and t.dst_row == row)]
        if len(self._frame.tiles) != len(old):
            self.update()
            self.frame_painted.emit()
            get_history().record(PaintFrameCmd(
                self._frame, old, self._snapshot(), self._persist_fn))

    def _finish_canvas_selection(self):
        """
        Fin de la sélection rectangulaire (aucune brosse active) : ramasse
        les tuiles déjà posées sous le rectangle — les retire du canvas et
        les charge comme brosse, prêtes à être reposées ailleurs sans
        repasser par le tile picker.
        """
        c0, r0 = self._select_start
        c1, r1 = self._select_end
        self._select_start = self._select_end = None
        if not self._frame:
            self.update()
            return
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        picked = [t for t in self._frame.tiles
                  if cmin <= t.dst_col <= cmax and rmin <= t.dst_row <= rmax]
        if not picked:
            self.update()
            return
        old = self._snapshot()
        picked_pos = {(t.dst_col, t.dst_row) for t in picked}
        self._frame.tiles = [t for t in self._frame.tiles
                             if (t.dst_col, t.dst_row) not in picked_pos]
        self.frame_painted.emit()
        get_history().record(PaintFrameCmd(
            self._frame, old, self._snapshot(), self._persist_fn))

        self._brush = [(t.dst_col - cmin, t.dst_row - rmin, t.src_col, t.src_row,
                        t.flip_h, t.flip_v) for t in picked]
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.brush_picked_up.emit(len(self._brush))
        self.update()

    # ── Rendu ─────────────────────────────────────────────────────────

    def paintEvent(self, e):
        painter = QPainter(self)

        if not self._frame or not self._sprite:
            painter.setPen(QColor(C.TEXT_MUTED))
            painter.setFont(QFont(T.MONO, T.MD))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Sélectionnez une frame")
            painter.end()
            return

        zoom, ox, oy, dw, dh = self._geometry()
        tile_px = 8 * zoom

        # Damier transparence
        cs = max(4, zoom * 2)
        for cy in range(0, dh, cs):
            for cx in range(0, dw, cs):
                c = QColor("#1e1e1e") if (cx // cs + cy // cs) % 2 == 0 else QColor("#2a2a2a")
                painter.fillRect(ox + cx, oy + cy,
                                 min(cs, dw - cx), min(cs, dh - cy), c)

        # Image composée
        img = _compose_frame_image(self._abs_path, self._frame,
                                   self._tile_w * 8, self._tile_h * 8)
        if img.width > 0 and img.height > 0:
            data = bytes(img.tobytes("raw", "RGBA"))
            qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            painter.drawPixmap(QRect(ox, oy, dw, dh), QPixmap.fromImage(qi))

        # Grille 8×8
        if self._show_grid:
            painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
            x = ox
            while x <= ox + dw:
                painter.drawLine(x, oy, x, oy + dh); x += tile_px
            y = oy
            while y <= oy + dh:
                painter.drawLine(ox, y, ox + dw, y); y += tile_px

        # Ghost preview de la brosse
        if self._hover and self._brush and self._src_pixmap:
            hc, hr = self._hover
            painter.setOpacity(0.55)
            for rel_c, rel_r, sc, sr, fh, fv in self._brush:
                dc, dr = hc + rel_c, hr + rel_r
                if not (0 <= dc < self._tile_w and 0 <= dr < self._tile_h):
                    continue
                dest = QRect(ox + dc * tile_px, oy + dr * tile_px, tile_px, tile_px)
                src = QRect(sc * 8, sr * 8, 8, 8)
                if fh or fv:
                    painter.save()
                    cx, cy = dest.center().x(), dest.center().y()
                    painter.translate(cx, cy)
                    painter.scale(-1 if fh else 1, -1 if fv else 1)
                    painter.translate(-cx, -cy)
                    painter.drawPixmap(dest, self._src_pixmap, src)
                    painter.restore()
                else:
                    painter.drawPixmap(dest, self._src_pixmap, src)
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(C.ACCENT_GRN), 2))
            painter.drawRect(QRect(ox + hc * tile_px, oy + hr * tile_px, tile_px, tile_px))
        elif self._hover:
            painter.setPen(QPen(QColor(C.TEXT_DIM), 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRect(ox + self._hover[0] * tile_px,
                                   oy + self._hover[1] * tile_px, tile_px, tile_px))

        # Sélection en cours (ramassage de tuiles déjà posées, sans brosse)
        if self._select_start is not None and self._select_end is not None:
            c0, r0 = self._select_start
            c1, r1 = self._select_end
            cmin, cmax = min(c0, c1), max(c0, c1)
            rmin, rmax = min(r0, r1), max(r0, r1)
            rect = QRect(ox + cmin * tile_px, oy + rmin * tile_px,
                         (cmax - cmin + 1) * tile_px, (rmax - rmin + 1) * tile_px)
            fill_color = QColor(C.ACCENT_BLU)
            fill_color.setAlpha(64)
            painter.fillRect(rect, fill_color)
            painter.setPen(QPen(QColor(C.ACCENT_BLU), 2))
            painter.drawRect(rect)

        # Indicateur de zoom manuel
        if self._zoom > 0:
            painter.setPen(QColor(C.TEXT_DIM))
            painter.setFont(QFont(T.MONO, T.XS))
            painter.drawText(6, self.height() - 6, f"{self._zoom}×")

        painter.end()


class _FrameCanvasPanel(QWidget):
    """
    Enrobe _FrameCanvas avec un header (zoom −/+, Fit, coordonnées survolées) —
    même pattern que _SpritesheetViewer pour la zone tiles juste en dessous.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr_w = QWidget()
        hdr_w.setFixedHeight(22)
        hdr_w.setStyleSheet(
            f"background:{C.BG_RAISED};border-bottom:1px solid {C.BORDER_DARK};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(8, 0, 4, 0)
        hdr_lay.setSpacing(4)

        lbl_canvas = QLabel("CANVAS")
        lbl_canvas.setFont(QFont(T.MONO, T.XS))
        lbl_canvas.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        hdr_lay.addWidget(lbl_canvas)

        hdr_lay.addStretch()

        self._coord_lbl = QLabel("")
        self._coord_lbl.setFont(QFont(T.MONO, T.XS))
        self._coord_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._coord_lbl)

        hdr_lay.addSpacing(12)

        _BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;"
            f"border:none;font-size:{T.MD}px;padding:0 4px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_flip_x = QToolButton()
        btn_flip_x.setIcon(_ico("mirror_h", C.TEXT_DIM, C.ACCENT_GRN))
        btn_flip_x.setIconSize(QSize(14, 14))
        btn_flip_x.setStyleSheet(_BTN)
        btn_flip_x.setToolTip("Flip horizontal de la brosse active (Shift+X)")
        btn_flip_y = QToolButton()
        btn_flip_y.setIcon(_ico("mirror_v", C.TEXT_DIM, C.ACCENT_GRN))
        btn_flip_y.setIconSize(QSize(14, 14))
        btn_flip_y.setStyleSheet(_BTN)
        btn_flip_y.setToolTip("Flip vertical de la brosse active (Shift+Y)")
        hdr_lay.addWidget(btn_flip_x)
        hdr_lay.addWidget(btn_flip_y)

        hdr_lay.addSpacing(12)

        btn_fit = QToolButton(); btn_fit.setText("Fit"); btn_fit.setStyleSheet(_BTN)
        btn_fit.setToolTip("Réinitialiser le zoom (ajustement automatique)")
        btn_zm = QToolButton(); btn_zm.setText("−"); btn_zm.setStyleSheet(_BTN)
        btn_zp = QToolButton(); btn_zp.setText("+"); btn_zp.setStyleSheet(_BTN)
        hdr_lay.addWidget(btn_fit)
        hdr_lay.addWidget(btn_zm)
        hdr_lay.addWidget(btn_zp)

        root.addWidget(hdr_w)

        self.canvas = _FrameCanvas()
        self.canvas.hover_changed.connect(self._on_hover_changed)
        root.addWidget(self.canvas, 1)

        btn_flip_x.clicked.connect(self.canvas.flip_brush_x)
        btn_flip_y.clicked.connect(self.canvas.flip_brush_y)
        btn_fit.clicked.connect(self.canvas.zoom_fit)
        btn_zm.clicked.connect(self.canvas.zoom_out)
        btn_zp.clicked.connect(self.canvas.zoom_in)

    def _on_hover_changed(self, cell):
        self._coord_lbl.setText(f"tuile {cell[0]},{cell[1]}" if cell else "")


# ── Viewer du spritesheet source (tile picker) ─────────────────────────────────

class _SpritesheetCanvas(QWidget):
    """Canvas interne du picker — grille 8×8, sélection multi-tiles, zoom, pan."""

    selection_changed = pyqtSignal(list)
    hover_changed      = pyqtSignal(object)  # (col, row) survolé, ou None

    def __init__(self, scroll_area=None, parent=None):
        super().__init__(parent)
        self._pixmap:    Optional[QPixmap]       = None
        self._zoom:      int                     = 2
        self._scroll_area                        = scroll_area   # pour le pan molette
        self._drag_start: Optional[tuple]        = None
        self._drag_end:   Optional[tuple]        = None
        self._selection:  list[tuple[int, int]]  = []
        self._mid_drag:   Optional[tuple]        = None   # pan (start_global, h_val, v_val)
        self._hover:      Optional[tuple]        = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Focus au clic — même raison que _FrameCanvas : permet à Shift+X/Y
        # (portés par SpriteCenterPanel) de marcher après une sélection ici.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def load(self, path: Optional[Path]):
        self._pixmap = QPixmap(str(path)) if path and path.exists() else None
        self._selection = []
        self._drag_start = self._drag_end = None
        self._update_size()
        self.update()

    def clear_selection(self):
        self._selection = []
        self._drag_start = self._drag_end = None
        self.update()
        self.selection_changed.emit([])

    def _update_size(self):
        if self._pixmap:
            self.setFixedSize(self._pixmap.width()  * self._zoom,
                              self._pixmap.height() * self._zoom)
        else:
            self.setFixedSize(200, 100)

    def _tile_at(self, pos) -> tuple[int, int]:
        tpx = 8 * self._zoom
        col = int(pos.x() // tpx)
        row = int(pos.y() // tpx)
        if self._pixmap:
            col = max(0, min(col, self._pixmap.width()  // 8 - 1))
            row = max(0, min(row, self._pixmap.height() // 8 - 1))
        return col, row

    # ── Événements ────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.MiddleButton and self._scroll_area:
            self._mid_drag = (e.globalPosition().toPoint(),
                              self._scroll_area.horizontalScrollBar().value(),
                              self._scroll_area.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not self._pixmap or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_start = self._tile_at(e.position())
        self._drag_end = self._drag_start
        self._recompute_selection()

    def mouseMoveEvent(self, e):
        if self._mid_drag and self._scroll_area:
            start, hv, vv = self._mid_drag
            delta = e.globalPosition().toPoint() - start
            self._scroll_area.horizontalScrollBar().setValue(hv - delta.x())
            self._scroll_area.verticalScrollBar().setValue(vv - delta.y())
            return
        if self._pixmap:
            cell = self._tile_at(e.position())
            if cell != self._hover:
                self._hover = cell
                self.hover_changed.emit(cell)
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        self._drag_end = self._tile_at(e.position())
        self._recompute_selection()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._mid_drag = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        if e.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            self._drag_end = self._tile_at(e.position())
            self._recompute_selection()
            self._drag_start = None

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.hover_changed.emit(None)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        self._zoom = max(1, min(8, self._zoom + (1 if delta > 0 else -1)))
        self._update_size()
        self.update()
        e.accept()

    def _recompute_selection(self):
        if self._drag_start is None or self._drag_end is None:
            return
        c0, r0 = self._drag_start
        c1, r1 = self._drag_end
        cmin, cmax = min(c0, c1), max(c0, c1)
        rmin, rmax = min(r0, r1), max(r0, r1)
        self._selection = [(c, r) for r in range(rmin, rmax + 1)
                           for c in range(cmin, cmax + 1)]
        self.update()
        self.selection_changed.emit(self._selection)

    def paintEvent(self, e):
        painter = QPainter(self)
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor(C.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Aucun PNG source")
            painter.end()
            return

        pw = self._pixmap.width()  * self._zoom
        ph = self._pixmap.height() * self._zoom
        painter.drawPixmap(QRect(0, 0, pw, ph), self._pixmap)

        tpx = 8 * self._zoom
        painter.setPen(QPen(QColor(0, 200, 100, 60), 1))
        x = 0
        while x <= pw:
            painter.drawLine(x, 0, x, ph); x += tpx
        y = 0
        while y <= ph:
            painter.drawLine(0, y, pw, y); y += tpx

        for col, row in self._selection:
            r = QRect(col * tpx, row * tpx, tpx, tpx)
            painter.fillRect(r, QColor(76, 175, 120, 80))
            painter.setPen(QPen(QColor(C.ACCENT_GRN), 1))
            painter.drawRect(r)

        painter.end()


class _SpritesheetViewer(QWidget):
    """Zone basse — spritesheet scrollable, picker multi-tiles, zoom, indicateur brosse."""

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header : titre + indicateur brosse + zoom
        _BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:transparent;"
            f"border:none;font-size:{T.MD}px;padding:0 4px;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};}}"
        )
        hdr_w = QWidget()
        hdr_w.setFixedHeight(22)
        hdr_w.setStyleSheet(
            f"background:{C.BG_RAISED};border-bottom:1px solid {C.BORDER_DARK};")
        hdr_lay = QHBoxLayout(hdr_w)
        hdr_lay.setContentsMargins(8, 0, 4, 0)
        hdr_lay.setSpacing(4)

        lbl_tiles = QLabel("TILES")
        lbl_tiles.setFont(QFont(T.MONO, T.XS))
        lbl_tiles.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        hdr_lay.addWidget(lbl_tiles)

        hdr_lay.addStretch()

        self._brush_lbl = QLabel("Aucune brosse")
        self._brush_lbl.setFont(QFont(T.MONO, T.XS))
        self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._brush_lbl)

        hdr_lay.addSpacing(12)

        self._coord_lbl = QLabel("")
        self._coord_lbl.setFont(QFont(T.MONO, T.XS))
        self._coord_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        hdr_lay.addWidget(self._coord_lbl)

        hdr_lay.addSpacing(12)

        btn_zm = QToolButton(); btn_zm.setText("−"); btn_zm.setStyleSheet(_BTN)
        btn_zp = QToolButton(); btn_zp.setText("+"); btn_zp.setStyleSheet(_BTN)
        btn_zm.clicked.connect(self._zoom_out)
        btn_zp.clicked.connect(self._zoom_in)
        hdr_lay.addWidget(btn_zm)
        hdr_lay.addWidget(btn_zp)

        root.addWidget(hdr_w)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        # Le canvas gère lui-même la molette (zoom) et le middle-drag (pan) ;
        # on neutralise le scroll natif de la molette sur le QScrollArea.
        scroll.wheelEvent = lambda e: None
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._canvas = _SpritesheetCanvas(scroll_area=scroll)
        self._canvas.selection_changed.connect(self.selection_changed)
        self._canvas.hover_changed.connect(self._on_hover_changed)
        scroll.setWidget(self._canvas)
        root.addWidget(scroll, 1)

    def _on_hover_changed(self, cell):
        self._coord_lbl.setText(f"tuile {cell[0]},{cell[1]}" if cell else "")

    def load(self, path: Optional[Path]):
        self._canvas.load(path)

    def clear_selection(self):
        self._canvas.clear_selection()
        self.set_brush_label(0)

    def set_brush_label(self, n: int):
        if n == 0:
            self._brush_lbl.setText("Aucune brosse")
            self._brush_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;")
        else:
            self._brush_lbl.setText(f"Brosse : {n} tuile{'s' if n > 1 else ''}")
            self._brush_lbl.setStyleSheet(f"color:{C.ACCENT_GRN};background:transparent;")

    def _zoom_in(self):
        if self._canvas._zoom < 6:
            self._canvas._zoom += 1
            self._canvas._update_size()
            self._canvas.update()

    def _zoom_out(self):
        if self._canvas._zoom > 1:
            self._canvas._zoom -= 1
            self._canvas._update_size()
            self._canvas.update()


# ── Zone centre — Canvas + Tiles + Timeline ────────────────────────────────────

class SpriteCenterPanel(QWidget):
    """Zone centre : playback · canvas · tile picker · timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._sprite:    Optional[SpriteAsset]   = None
        self._project:   Optional[Project]        = None
        self._state:     Optional[AnimState]      = None
        self._sd:        Optional[StateDirection] = None
        self._sel_frame: int = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_play_tick)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._playback = _PlaybackBar()
        root.addWidget(self._playback)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:vertical{{height:3px;}}"
            f"QSplitter::handle:vertical:hover{{background:{C.ACCENT_GRN};}}"
        )

        self._canvas_panel = _FrameCanvasPanel()
        self._canvas = self._canvas_panel.canvas
        self._canvas.frame_painted.connect(self._on_frame_painted)
        self._canvas.set_persist_fn(self._on_frame_painted)
        self._canvas.selection_reset.connect(self._on_selection_reset)
        self._canvas.brush_picked_up.connect(self._on_brush_picked_up)

        self._tiles = _SpritesheetViewer()
        self._tiles.selection_changed.connect(self._on_tile_selection_changed)

        splitter.addWidget(self._canvas_panel)
        splitter.addWidget(self._tiles)
        splitter.setSizes([320, 200])

        root.addWidget(splitter, 1)

        self._timeline = _FrameTimeline()
        self._timeline.frame_selected.connect(self._on_frame_selected)
        self._timeline.frames_changed.connect(self._on_frames_changed)
        root.addWidget(self._timeline)

        if self._playback.btn_grid:
            self._playback.btn_grid.toggled.connect(self._canvas.set_grid)
        if self._playback.btn_play:
            self._playback.btn_play.toggled.connect(self._on_play_toggled)

        # Shift+X/Y : portés ici (pas sur _FrameCanvas seul) pour marcher
        # aussi bien après un clic dans le canvas que dans le tile picker —
        # WidgetWithChildrenShortcut s'active dès qu'un descendant a le focus.
        flip_x = QShortcut(QKeySequence("Shift+X"), self)
        flip_x.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_x.activated.connect(self._canvas.flip_brush_x)
        flip_y = QShortcut(QKeySequence("Shift+Y"), self)
        flip_y.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        flip_y.activated.connect(self._canvas.flip_brush_y)

    # ── API publique ──────────────────────────────────────────────────

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._sprite  = sprite
        self._project = project
        self._anim_timer.stop()
        if self._playback.btn_play:
            self._playback.btn_play.setChecked(False)
        self._playback.set_info(
            tiles=sprite.tiles_per_frame * sum(
                len(sd.frames)
                for s in sprite.states
                for sd in s.directions
                if sd.mirror_of is None
            ),
            unique=sprite.tiles_per_frame,
        )
        self._tiles.load(self._abs_path())

    def load_direction(self, state: AnimState, sd: StateDirection):
        if not self._sprite or not self._project:
            return
        self._state = state
        self._sd = sd
        self._sel_frame = 0
        self._anim_timer.stop()
        if self._playback.btn_play:
            self._playback.btn_play.setChecked(False)
        self._timeline.load(self._sprite, state, sd, self._abs_path())
        self._refresh_canvas()

    # ── Slots internes ────────────────────────────────────────────────

    def _abs_path(self) -> Optional[Path]:
        if not self._project or not self._sprite or not self._sprite.asset:
            return None
        return self._project.root / self._sprite.asset

    def _on_frame_selected(self, index: int):
        self._sel_frame = index
        self._refresh_canvas()

    def _on_tile_selection_changed(self, tiles: list):
        self._canvas.set_brush(tiles)
        self._tiles.set_brush_label(len(tiles))

    def _on_selection_reset(self):
        self._tiles.clear_selection()
        self._canvas.set_brush([])

    def _on_brush_picked_up(self, n: int):
        """Tuiles ramassées directement dans le canvas (cf _FrameCanvas) —
        seul le libellé du picker doit refléter la nouvelle brosse ; ne pas
        appeler _tiles.clear_selection() ici, ça réémettrait une sélection
        vide et effacerait la brosse qu'on vient de charger."""
        self._tiles.set_brush_label(n)

    def _on_frame_painted(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
        if self._sd and 0 <= self._sel_frame < len(self._sd.frames):
            pm = _make_frame_pixmap(self._abs_path(), self._sd.frames[self._sel_frame],
                                    self._sprite.frame_w, self._sprite.frame_h)
            self._timeline.refresh_thumb(self._sel_frame, pm)

    def _on_frames_changed(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)

    # ── Playback ──────────────────────────────────────────────────────

    def _on_play_toggled(self, playing: bool):
        if playing and self._sd and self._sd.frames:
            speed_ms = max(16, int((self._state.speed if self._state else 8) * 1000 / 60))
            self._anim_timer.start(speed_ms)
        else:
            self._anim_timer.stop()

    def _on_play_tick(self):
        if not self._sd or not self._sd.frames:
            return
        n = len(self._sd.frames)
        self._sel_frame = (self._sel_frame + 1) % n
        # Mettre à jour la sélection dans la timeline sans émettre frame_selected
        for i, t in enumerate(self._timeline._thumbs):
            t.set_selected(i == self._sel_frame)
        self._timeline._selected = self._sel_frame
        self._refresh_canvas()

    # ── Canvas ────────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if not self._sd or not self._sprite:
            self._canvas.load_frame(None, None, None)
            return
        frames = self._sd.frames
        if not frames or not (0 <= self._sel_frame < len(frames)):
            self._canvas.load_frame(None, None, None)
            return
        self._canvas.load_frame(self._sprite, self._abs_path(), frames[self._sel_frame])


# ── Panneau droit ──────────────────────────────────────────────────────────────

_VALID_FRAME_SIZES = {
    8:  [8, 16, 32],
    16: [8, 16, 32],
    32: [8, 16, 32, 64],
    64: [32, 64],
}

_DIR_GRID = [
    # (dir_id, icon_key, tooltip, grid_row, grid_col)
    (8, "dir_nw", "NW", 0, 0), (1, "dir_n", "N",  0, 1), (2, "dir_ne", "NE", 0, 2),
    (7, "dir_w",  "W",  1, 0), (0, "dir_omni", "Omni (toutes directions)", 1, 1), (3, "dir_e", "E",  1, 2),
    (6, "dir_sw", "SW", 2, 0), (5, "dir_s", "S",  2, 1), (4, "dir_se", "SE", 2, 2),
]

# Paires source → miroir horizontal (E→W, NE→NW, SE→SW)
_H_MIRROR_PAIRS = [(3, 7), (2, 8), (4, 6)]
# Paires source → miroir vertical (N→S, NE→SE, NW→SW)
_V_MIRROR_PAIRS = [(1, 5), (2, 4), (8, 6)]

_BTN_SIZE = 44   # pixels, carré

_STY_NORMAL = (
    f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
    f"border:1px solid {C.BORDER};border-radius:5px;"
    f"font-size:16px;}}"
    f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};"
    f"border-color:{C.BORDER_MID};}}"
    f"QToolButton:checked{{color:{C.ACCENT_GRN};border:2px solid {C.ACCENT_GRN};"
    f"background:{C.BG_SEL};}}"
)
_STY_MIRRORED = (
    f"QToolButton{{color:#3a6a8a;background:#0d1a22;"
    f"border:1px dashed #2a4a5a;border-radius:5px;"
    f"font-size:16px;}}"
    f"QToolButton:checked{{color:{C.ACCENT_BLU};border:2px dashed {C.ACCENT_BLU};"
    f"background:#0e1f2e;}}"
)
_STY_OMNI = (
    f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_DEEP};"
    f"border:1px solid {C.BORDER_DARK};border-radius:5px;"
    f"font-size:14px;}}"
    f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
    f"QToolButton:checked{{color:{C.ACCENT_GRN};border:2px solid {C.ACCENT_GRN};"
    f"background:{C.BG_SEL};}}"
)


class _DirButton(QToolButton):
    """Bouton de direction dans la grille 3×3 — icône flèche (ui/icons.py), taille carrée fixe."""

    def __init__(self, dir_id: int, icon_key: str, tooltip: str, parent=None):
        super().__init__(parent)
        self.dir_id = dir_id
        self._icon_key = icon_key
        self.setCheckable(True)
        self.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        self.setIconSize(QSize(20, 20))
        self.setToolTip(tooltip)
        self._is_omni = (dir_id == 0)
        self.set_mirrored(False)

    def set_mirrored(self, mirrored: bool):
        from ui.icons import get as _ico

        if self._is_omni:
            self.setStyleSheet(_STY_OMNI)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT_GRN))
        elif mirrored:
            self.setStyleSheet(_STY_MIRRORED)
            self.setIcon(_ico(self._icon_key, "#3a6a8a", C.ACCENT_BLU))
        else:
            self.setStyleSheet(_STY_NORMAL)
            self.setIcon(_ico(self._icon_key, C.TEXT_DIM, C.ACCENT_GRN))


class DirectionWidget(QWidget):
    """
    Grille 3×3 de directions + boutons H-Mirror / V-Mirror.
    Émet directions_changed(active_dirs, h_mirror, v_mirror).
    """

    directions_changed = pyqtSignal(list, bool, bool)  # [dir_id], h_mirror, v_mirror

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocking = False
        self._h_mirror = False
        self._v_mirror = False
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QGridLayout

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 6)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Grille 3×3 — taille fixe pour garder un vrai carré
        GAP = 4
        SIDE = _BTN_SIZE * 3 + GAP * 2
        grid_w = QWidget()
        grid_w.setFixedSize(SIDE, SIDE)
        grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(GAP)
        grid.setContentsMargins(0, 0, 0, 0)
        for c in range(3):
            grid.setColumnMinimumWidth(c, _BTN_SIZE)
            grid.setRowMinimumHeight(c, _BTN_SIZE)

        self._dir_btns: dict[int, _DirButton] = {}
        for dir_id, icon, tip, row, col in _DIR_GRID:
            btn = _DirButton(dir_id, icon, tip)
            btn.toggled.connect(lambda checked, d=dir_id: self._on_dir_toggled(d, checked))
            grid.addWidget(btn, row, col)
            self._dir_btns[dir_id] = btn

        root.addWidget(grid_w, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Boutons H / V mirror
        _MIRROR_BTN = (
            f"QToolButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;"
            f"font-family:{T.MONO};font-size:{T.XS}px;padding:4px 8px;}}"
            f"QToolButton:checked{{color:{C.ACCENT_BLU};border-color:{C.ACCENT_BLU};"
            f"background:#0e1a22;}}"
            f"QToolButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};}}"
        )

        mirror_row = QHBoxLayout()
        mirror_row.setSpacing(4)
        mirror_row.setContentsMargins(0, 0, 0, 0)

        from ui.icons import get as _ico

        self._btn_h = QToolButton(); self._btn_h.setText("  H-Mirror")
        self._btn_h.setIcon(_ico("mirror_h", C.TEXT_DIM, C.ACCENT_BLU))
        self._btn_h.setIconSize(QSize(16, 16))
        self._btn_h.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_h.setCheckable(True); self._btn_h.setStyleSheet(_MIRROR_BTN)
        self._btn_h.setFixedHeight(28)
        self._btn_h.setToolTip("Miroir horizontal : génère W, NW, SW depuis E, NE, SE")
        self._btn_h.toggled.connect(self._on_h_mirror)

        self._btn_v = QToolButton(); self._btn_v.setText("  V-Mirror")
        self._btn_v.setIcon(_ico("mirror_v", C.TEXT_DIM, C.ACCENT_BLU))
        self._btn_v.setIconSize(QSize(16, 16))
        self._btn_v.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn_v.setCheckable(True); self._btn_v.setStyleSheet(_MIRROR_BTN)
        self._btn_v.setFixedHeight(28)
        self._btn_v.setToolTip("Miroir vertical : génère S, SE, SW depuis N, NE, NW")
        self._btn_v.toggled.connect(self._on_v_mirror)

        mirror_row.addWidget(self._btn_h, 1)
        mirror_row.addWidget(self._btn_v, 1)
        root.addLayout(mirror_row)

    def load(self, state: AnimState):
        """Charge la configuration de directions depuis un AnimState."""
        self._blocking = True
        active = {sd.dir for sd in state.directions}
        mirrored = {sd.dir for sd in state.directions if sd.mirror_of is not None}
        h_mirror = any(sd.mirror_of is not None and sd.flip_h for sd in state.directions)
        v_mirror = any(sd.mirror_of is not None and sd.flip_v for sd in state.directions)

        for dir_id, btn in self._dir_btns.items():
            btn.setChecked(dir_id in active)
            btn.set_mirrored(dir_id in mirrored)

        self._btn_h.setChecked(h_mirror)
        self._btn_v.setChecked(v_mirror)
        self._h_mirror = h_mirror
        self._v_mirror = v_mirror
        self._blocking = False

    def _on_dir_toggled(self, dir_id: int, checked: bool):
        if self._blocking:
            return
        self._update_mirrors()
        self._emit()

    def _on_h_mirror(self, checked: bool):
        if self._blocking:
            return
        self._h_mirror = checked
        self._update_mirrors()
        self._emit()

    def _on_v_mirror(self, checked: bool):
        if self._blocking:
            return
        self._v_mirror = checked
        self._update_mirrors()
        self._emit()

    def _update_mirrors(self):
        """Met à jour l'apparence des boutons miroirs selon l'état H/V."""
        self._blocking = True
        active = {d for d, btn in self._dir_btns.items() if btn.isChecked()}
        mirrored: set[int] = set()

        if self._h_mirror:
            for src, dst in _H_MIRROR_PAIRS:
                if src in active:
                    mirrored.add(dst)
                    self._dir_btns[dst].setChecked(True)
        if self._v_mirror:
            for src, dst in _V_MIRROR_PAIRS:
                if src in active:
                    mirrored.add(dst)
                    self._dir_btns[dst].setChecked(True)

        for dir_id, btn in self._dir_btns.items():
            btn.set_mirrored(dir_id in mirrored)

        self._blocking = False

    def _emit(self):
        active = [d for d, btn in self._dir_btns.items() if btn.isChecked()]
        self.directions_changed.emit(active, self._h_mirror, self._v_mirror)


class SpriteRightPanel(QWidget):
    """
    Panneau droit : header (nom éditable) + paramètres sprite + widget directionnel.
    """

    sprite_changed  = pyqtSignal()
    direction_added = pyqtSignal(object, object)  # AnimState, StateDirection nouvellement ajoutée

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(440)
        self.setStyleSheet(
            f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};"
        )
        self._project: Optional[Project] = None
        self._sprite:  Optional[SpriteAsset] = None
        self._state:   Optional[AnimState] = None
        self._blocking = False
        self._build()

    # ── Construction ──────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header : nom du sprite — composant partagé (voir ui/widgets.py),
        # même template/couleurs/renommage que Scene Manager, Sound Mixer, Script Editor.
        from ui.widgets import AssetHeaderBar
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_name_changed)
        root.addWidget(self._header)

        # ── Contenu scrollable ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{C.BG_PANEL}; border:none;}}"
        )

        content = QWidget()
        content.setStyleSheet(f"background:{C.BG_PANEL};")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(10, 8, 10, 8)
        self._content_layout.setSpacing(2)

        self._build_params()
        self._build_direction()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_params(self):
        lay = self._content_layout
        W.section("CANVAS SIZE", lay)

        # Frame W / H
        self._cb_w = QComboBox(); self._cb_w.setFont(QFont(T.MONO, T.SM))
        self._cb_h = QComboBox(); self._cb_h.setFont(QFont(T.MONO, T.SM))
        for v in [8, 16, 32, 64]:
            self._cb_w.addItem(str(v))
        self._cb_w.currentIndexChanged.connect(self._on_frame_w_changed)
        self._cb_h.currentIndexChanged.connect(self._on_frame_h_changed)
        W.pair("Frame", "W", C.AXIS_X, self._cb_w, "H", C.AXIS_Y, self._cb_h, lay)

        W.separator(lay)
        W.section("ANIMATION", lay)

        self._sp_speed = W.spinbox(8, min_v=1, max_v=120)
        self._sp_speed.setToolTip("Ticks GBA entre deux frames (60fps). 8=7.5fps  4=15fps  2=30fps")
        self._sp_speed.valueChanged.connect(self._on_speed_changed)
        W.row("Speed", self._sp_speed, lay)

        self._chk_loop = W.checkbox_row("", "Loop", lay)
        self._chk_loop.setChecked(True)
        self._chk_loop.toggled.connect(self._on_loop_changed)

        W.separator(lay)

    def _build_direction(self):
        lay = self._content_layout
        W.section("DIRECTIONS", lay)
        self._dir_widget = DirectionWidget()
        self._dir_widget.directions_changed.connect(self._on_directions_changed)
        lay.addWidget(self._dir_widget)

    # ── API publique ──────────────────────────────────────────────

    def load_sprite(self, sprite: SpriteAsset, project: Project):
        self._project = project
        self._sprite  = sprite
        self._state   = sprite.states[0] if sprite.states else None
        self._blocking = True

        self._header.set_header("sprite", "SPRITE", sprite.name)

        # Frame size
        self._cb_w.setCurrentText(str(sprite.frame_w))
        self._refresh_h_combo(sprite.frame_w, sprite.frame_h)

        # Animation (premier state)
        if self._state:
            self._sp_speed.setValue(self._state.speed)
            self._chk_loop.setChecked(self._state.loop)
            self._dir_widget.load(self._state)

        self._blocking = False

    def load_state(self, state: AnimState):
        """Met à jour les paramètres d'animation pour l'état sélectionné."""
        self._state = state
        self._blocking = True
        self._sp_speed.setValue(state.speed)
        self._chk_loop.setChecked(state.loop)
        self._dir_widget.load(state)
        self._blocking = False

    # ── Helpers ───────────────────────────────────────────────────

    def _refresh_h_combo(self, w_val: int, keep_h: int = 0):
        self._cb_h.blockSignals(True)
        self._cb_h.clear()
        valid = _VALID_FRAME_SIZES.get(w_val, [8])
        for v in valid:
            self._cb_h.addItem(str(v))
        target = str(keep_h) if keep_h in valid else str(valid[0])
        self._cb_h.setCurrentText(target)
        self._cb_h.blockSignals(False)

    def _save(self):
        if self._sprite and self._project:
            get_dispatcher().save_sprite(self._sprite)
            self.sprite_changed.emit()

    # ── Slots ─────────────────────────────────────────────────────

    def _on_name_changed(self, new_name: str):
        if self._blocking or not self._sprite or not self._project:
            return
        new_name = new_name.strip()
        if new_name and new_name != self._sprite.name:
            self._project.sprites.rename(self._sprite, new_name)
            self.sprite_changed.emit()

    def _on_frame_w_changed(self, _):
        if self._blocking or not self._sprite:
            return
        w = int(self._cb_w.currentText())
        old_h = int(self._cb_h.currentText()) if self._cb_h.currentText() else 16
        self._refresh_h_combo(w, old_h)
        self._sprite.frame_w = w
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_frame_h_changed(self, _):
        if self._blocking or not self._sprite:
            return
        self._sprite.frame_h = int(self._cb_h.currentText())
        self._save()

    def _on_speed_changed(self, value: int):
        if self._blocking or not self._state:
            return
        self._state.speed = value
        self._save()

    def _on_loop_changed(self, checked: bool):
        if self._blocking or not self._state:
            return
        self._state.loop = checked
        self._save()

    def _on_directions_changed(self, active_dirs: list, h_mirror: bool, v_mirror: bool):
        if self._blocking or not self._state or not self._sprite:
            return
        # Reconstruire les StateDirection depuis la sélection
        dir_map = {sd.dir: sd for sd in self._state.directions}
        added_dirs = [d for d in active_dirs if d not in dir_map]
        new_dirs = []
        mirrored_set: set[int] = set()
        if h_mirror:
            for src, dst in _H_MIRROR_PAIRS:
                if src in active_dirs:
                    mirrored_set.add(dst)
        if v_mirror:
            for src, dst in _V_MIRROR_PAIRS:
                if src in active_dirs:
                    mirrored_set.add(dst)

        for d in active_dirs:
            if d in mirrored_set:
                # Trouver la source de ce miroir
                src = next(
                    (s for s, dst in (_H_MIRROR_PAIRS + _V_MIRROR_PAIRS) if dst == d),
                    None
                )
                fh = any(dst == d for s, dst in _H_MIRROR_PAIRS) and h_mirror
                fv = any(dst == d for s, dst in _V_MIRROR_PAIRS) and v_mirror
                existing = dir_map.get(d)
                new_dirs.append(StateDirection(
                    dir=d,
                    frames=existing.frames if existing else [AnimFrame()],
                    flip_h=fh, flip_v=fv,
                    mirror_of=src,
                ))
            else:
                existing = dir_map.get(d)
                new_dirs.append(existing or StateDirection(
                    dir=d, frames=[AnimFrame()],
                ))

        self._state.directions = new_dirs or [StateDirection()]
        self._save()

        # Une direction tout juste créée doit devenir visible immédiatement
        # dans l'arbre de gauche et le canvas central — sinon ceux-ci
        # continuent d'afficher/peindre l'ancienne direction sélectionnée.
        if added_dirs:
            added_sd = next((d for d in self._state.directions if d.dir == added_dirs[0]), None)
            if added_sd is not None:
                self.direction_added.emit(self._state, added_sd)


# ── Écran complet ──────────────────────────────────────────────────────────────

class SpriteEditorScreen(QWidget):
    """Écran principal du Sprite Editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project: Optional[Project] = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{C.ACCENT_GRN};}}"
        )

        self._left   = SpriteFinderPanel()
        self._center = SpriteCenterPanel()
        self._right  = SpriteRightPanel()

        splitter.addWidget(self._left)
        splitter.addWidget(self._center)
        splitter.addWidget(self._right)
        splitter.setSizes([240, 860, 270])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root.addWidget(splitter)

        self._left.sprite_selected.connect(self._on_sprite_selected)
        self._left.direction_selected.connect(self._on_direction_selected)
        self._right.sprite_changed.connect(self._left.refresh_anim_tree)
        self._right.direction_added.connect(self._left.select_direction)

    def load_project(self, project: Project):
        self._project = project
        self._left.load_project(project)

    def _on_sprite_selected(self, sprite: SpriteAsset):
        self._center.load_sprite(sprite, self._project)
        self._right.load_sprite(sprite, self._project)

    def _on_direction_selected(self, state: AnimState, sd: StateDirection):
        self._center.load_direction(state, sd)
        self._right.load_state(state)
