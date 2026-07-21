"""ui/sprite_editor/sprite_finder_panel.py — panneau gauche : liste des sprites + arbre d'animations."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy,
    QMenu, QMessageBox, QAbstractItemView,
    QTreeWidget, QTreeWidgetItem,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.common.widgets import FinderSection
from ui.common.theme import C, T
from ui.common.icons import get as _ico, COLOR_DEFAULT
from core.project import Project, SpriteAsset, AnimState, StateDirection
from core.history import get_history, DeleteResourceCmd, RemoveListItemCmd
from core.command_dispatcher import get_dispatcher

# ── Helpers styles ─────────────────────────────────────────────────────────────

_PANEL_BG   = f"background:{C.BG_BASE};"

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
    color: {C.ACCENT};
    border-left: 2px solid {C.ACCENT};
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
    f"QMenu::item:selected{{background:{C.BG_SEL};color:{C.ACCENT};}}"
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
        sec_sprites = FinderSection("SPRITES")
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
        sec_anim = FinderSection("ANIMATIONS STATES")
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
        item.setIcon(0, _ico("sprite", COLOR_DEFAULT))
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
            state_item.setIcon(0, _ico("anim_state", COLOR_DEFAULT))
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
                # Mirror signalé par le texte grisé (fg) ; icône neutre.
                sd_item.setIcon(0, _ico(_DIR_ICON_KEYS.get(sd.dir, "dir_omni"), COLOR_DEFAULT))
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
        # Un sprite se crée uniquement par import d'une image (l'option
        # « sprite vide » a été retirée) — le « + » ouvre directement l'import.
        if not self._project:
            return
        self._import_sprite()

    def _import_sprite(self):
        from .import_png_dialog import import_new_sprite
        dst = import_new_sprite(self._project, self)
        if not dst:
            return
        sprite = self._project.sprites.get(dst.stem)
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
        get_dispatcher().rename_sprite(sp, new_name)
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

