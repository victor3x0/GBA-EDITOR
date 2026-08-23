"""ActorInspector — transform, components, éditeur de component sélectionné."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QCheckBox, QListWidget, QListWidgetItem, QMenu, QScrollArea,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView,
)
from PyQt6.QtGui import QFont, QCursor, QPixmap, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from core.models.resource import MIME_SCRIPT
from core.models.components import component_type_name
from core.models.scene import Actor, Scene, Prefab
from core.project import Project
from core.history import get_history, SetFieldCmd, AddComponentCmd, RemoveComponentCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from ui.common.theme import C, T, QSS
from ui.common.widgets import NotesEdit, CollapsibleCard
from ui.common.direction_grid import DirectionPicker
from ui.common import icons

COMPONENT_LABELS = {
    "sprite":        "Sprite",
    "collision_box": "Collision",
    "sound_fx":      "SoundFX",
    "script":        "Script",
}

# ── Tooltips Lua mirror (transform/actor uniquement — les tooltips par
# component vivent dans leur propre component_editor, ex: collision.py) ──
_TOOLTIPS = {
    "actor.active":      ("self.active",
                          "Si false, l'actor est ignoré : pas d'update,\npas de collision, OAM slot libéré.\n"
                          "Lua : self.active = false"),
    "actor.x":           ("self.x",
                          "Position horizontale en pixels (0–239).\n"
                          "Lecture directe depuis Lua : local px = self.position.x\n"
                          "Écriture → self.position = vec2(x, y)  ou  self:move(self.position, speed)"),
    "actor.y":           ("self.y",
                          "Position verticale en pixels (0–159).\n"
                          "Lecture directe depuis Lua : local py = self.position.y\n"
                          "Écriture → self.position = vec2(x, y)  ou  self:move(self.position, speed)"),
    "actor.priority":    ("self.priority  (lecture seule)",
                          "Ordre d'affichage sur les BG layers.\n"
                          "0 = devant tous les backgrounds,  3 = derrière tous.\n"
                          "GBA : OAM attribute 2, bits 10–11."),
    "actor.screen_space": ("(authoré — aucun équivalent Lua)",
                          "Ancre l'actor à l'ÉCRAN au lieu du monde : il ne défile\n"
                          "plus avec la caméra. C'est l'UI en sprite — score, cœurs,\n"
                          "curseur — avec tout le SpriteComponent habituel (états,\n"
                          "animations, éditeur de sprite).\n"
                          "\n"
                          "X et Y deviennent des pixels d'ÉCRAN (0–239, 0–159), le\n"
                          "même repère que les éléments d'interface ancrés à l'écran.\n"
                          "\n"
                          "Ordre d'affichage face à l'interface en background : c'est\n"
                          "Priority qui tranche, comparé à la priorité du calque UI de\n"
                          "la scène. À priorité ÉGALE, le sprite passe devant — règle\n"
                          "matérielle du GBA, pas un choix de l'éditeur.\n"
                          "\n"
                          "Résolu à la compilation : pas de bascule au runtime."),
    "actor.visible":     ("self.visible = true/false",
                          "Masque l'actor sans le désactiver.\n"
                          "Le slot OAM reste réservé mais avec bit OBJ_DISABLE."),
    "actor.affine_transform": ("self.rotation, self.scale, self.sprite_*",
                          "Réserve un des 32 slots de matrice affine du GBA pour\n"
                          "CET actor et libère son transform monde.\n"
                          "\n"
                          "Coché → l'actor a un scale et une rotation (self.rotation,\n"
                          "self.scale), et son SpriteComponent gagne un scale, une\n"
                          "rotation et un offset LOCAUX (self.sprite_*) : le sprite\n"
                          "hérite des propriétés de l'actor (rotation somme des deux,\n"
                          "scale produit des deux) et se place en OFFSET relatif à lui.\n"
                          "\n"
                          "Décoché → OAM normale, aucun slot, les champs ci-dessous\n"
                          "et les self.sprite_* sont sans effet.\n"
                          "\n"
                          "GBA : OAM attribute 1, bits 8-12 (affine matrix slot)."),
    "actor.rotation":    ("self.rotation",
                          "Rotation MONDE de cet actor, en degrés (0–359).\n"
                          "Héritée par le sprite : à l'écran, l'angle total est\n"
                          "rotation_actor + sprite_rotation.\n"
                          "Nécessite « Affine transform » coché."),
    "actor.scale":       ("self.scale  (vec2 en pourcent)",
                          "Échelle MONDE de cet actor, en pourcent — 100 = normal.\n"
                          "Héritée par le sprite : à l'écran, l'échelle totale est\n"
                          "scale_actor × sprite_scale.\n"
                          "Nécessite « Affine transform » coché.\n"
                          "Lua : self.scale = vec2(150, 150)"),
    "actor.obj_mode":    ('self.obj_mode = "normal" | "window"',
                          "Rôle du sprite dans le système de windows (masques d'écran).\n"
                          "\n"
                          "Normal : le sprite est dessiné, comme n'importe quel autre.\n"
                          "\n"
                          "Masque (window OBJ) : le sprite n'est PLUS dessiné. Ses pixels\n"
                          "opaques deviennent la FORME de la window OBJ — la seule région\n"
                          "qui ne soit pas un rectangle, contrairement à WIN0 et WIN1.\n"
                          "Elle suit le sprite et s'anime avec lui (ex. halo de lampe torche).\n"
                          "\n"
                          "Le sprite ne fait que découper : ce qui s'AFFICHE dans la découpe\n"
                          "se règle sur la ligne WINDOW OBJ de la carte WINDOWS de la scène.\n"
                          "Sans cette ligne, la découpe n'a aucun effet visible.\n"
                          "\n"
                          "GBA : OAM attribute 0, bits 10–11."),
}

def _tip(w: QWidget, key: str):
    """Applique le tooltip Lua+GBA sur un widget."""
    if key not in _TOOLTIPS:
        return
    lua_expr, desc = _TOOLTIPS[key]
    w.setToolTip(f"<b style='color:{C.ACCENT_BLU}'>{lua_expr}</b><br><br>{desc.replace(chr(10), '<br>')}")


# ──────────────────────────────────────────────────────────────────
#  Liste de components qui accepte le drop d'un Script
# ──────────────────────────────────────────────────────────────────
class ComponentListWidget(QListWidget):
    script_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT): e.acceptProposedAction()
        else: super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT): e.acceptProposedAction()
        else: super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_SCRIPT):
            self.script_dropped.emit(bytes(e.mimeData().data(MIME_SCRIPT)).decode("utf-8"))
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Arbre des CHILDREN d'un prefab (ROADMAP v0.23)
# ──────────────────────────────────────────────────────────────────
class _ChildrenTree(QTreeWidget):
    """Hiérarchie des `children` d'un prefab, dérivée de `Actor.parent` — même
    principe que `_ActiveSceneTree` (scene_tree_panel.py) pour les acteurs de
    scène, réduit à ce dont ce panneau a besoin : montrer l'arbre et permettre
    le reparentage par glisser-déposer. Pas de réordonnancement de frères ici
    (contrairement au Scene tree) : l'ORDRE de `children` compte pour le spawn
    groupé au build (ROADMAP v0.23, « le spawn avance d'un groupe à la fois »),
    et cet arbre n'a pas la logique DFS qui le préserverait sans le corrompre.

    Le double-clic reste la façon d'ouvrir une partie dans l'inspecteur
    (`itemDoubleClicked`, câblé par `ActorInspector`)."""

    reparented = pyqtSignal()   # une partie a changé de parent depuis l'arbre

    _ROLE_OBJ = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = None   # le Prefab dont .children est affiché
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setAnimated(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(QSS.tree_widget)

    def populate(self, owner):
        self._owner = owner
        self.clear()
        parts = (getattr(owner, "children", []) or []) if owner is not None else []
        items: dict = {}
        for part in parts:
            it = QTreeWidgetItem()
            it.setText(0, part.name)
            it.setData(0, self._ROLE_OBJ, part)
            items[part.name] = it
        for part in parts:
            host = items.get(part.parent) if part.parent else None
            if host is not None and host is not items[part.name]:
                host.addChild(items[part.name])
            else:
                self.addTopLevelItem(items[part.name])
        for it in items.values():
            it.setExpanded(True)

    def current_part(self):
        it = self.currentItem()
        return it.data(0, self._ROLE_OBJ) if it else None

    def select_part(self, part):
        for i in range(self.topLevelItemCount()):
            if self._select_in(self.topLevelItem(i), part):
                return

    def _select_in(self, item: QTreeWidgetItem, part) -> bool:
        if item.data(0, self._ROLE_OBJ) is part:
            self.setCurrentItem(item)
            return True
        return any(self._select_in(item.child(i), part) for i in range(item.childCount()))

    # ── Drag & drop : reparentage seulement ─────────────────────────

    def dropEvent(self, event):
        dragged = self.currentItem()
        if dragged is None or self._owner is None:
            event.ignore()
            return
        part = dragged.data(0, self._ROLE_OBJ)
        target = self.itemAt(event.position().toPoint())
        if target is None:
            # Lâché dans le vide : reparente à la racine.
            event.accept()
            self._reparent(part, None)
            return
        Pos = QAbstractItemView.DropIndicatorPosition
        if self.dropIndicatorPosition() != Pos.OnItem:
            event.ignore()   # pas de réordonnancement de frères ici (cf. docstring)
            return
        event.accept()
        self._reparent(part, target.data(0, self._ROLE_OBJ))

    def _reparent(self, part, new_parent):
        if part is None or part is new_parent:
            return
        from core.models.scene import actor_descendant_names
        children = self._owner.children or []
        new_name = new_parent.name if new_parent is not None else None
        # Même garde anti-cycle que l'inspecteur (ActorInspector._descendants) :
        # se poser sur soi-même ou son propre sous-arbre ferait un cycle que le
        # Build refuserait de toute façon.
        if new_name and new_name in actor_descendant_names(children, part.name):
            return
        if part.parent == new_name:
            return
        part.parent = new_name
        self.reparented.emit()


# ──────────────────────────────────────────────────────────────────
#  ActorInspector
# ──────────────────────────────────────────────────────────────────
class ActorInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actor: Optional[Actor] = None
        self._project: Optional[Project] = None
        self._scene: Optional[Scene] = None
        self._blocking = False
        self._is_prefab_template = False
        # Le Prefab affiché quand `_actor` EST sa racine (`prefab.actor`,
        # cf. core/models/scene.Prefab) — posé par `load_prefab`, nécessaire
        # à `_persist` : sauver le prefab prend le Prefab, pas son actor.
        self._prefab: Optional[Prefab] = None
        # Le prefab qui POSSÈDE la partie en cours d'édition (ROADMAP v0.23),
        # ou None quand on n'édite pas une partie. Une partie est un `Actor`,
        # donc l'inspecteur l'édite avec les mêmes champs qu'un acteur de
        # scène ; seul l'ENREGISTREMENT diffère — c'est le prefab qu'il faut
        # sauver, pas la scène.
        self._child_owner = None
        self.setStyleSheet(f"background:{C.BG_DEEP};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_DEEP}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        self._empty = QLabel("Select an actor\nfrom the left panel")
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        self._content = QWidget()
        self._content.setStyleSheet(f"background:{C.BG_DEEP};")
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(5)

        # ── NOTE card — partagée Actor/Prefab ────────────────────
        notes_card = CollapsibleCard("Note")
        self._notes_edit = NotesEdit()
        self._notes_edit.committed.connect(lambda text: self._set("notes", text))
        notes_card.body_layout.addWidget(self._notes_edit)
        cl.addWidget(notes_card)

        # ── Header : preview sprite + nom ────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            f"background:{C.BG_BASE}; border-bottom:1px solid {C.BORDER}; border-radius:0;"
        )
        header_frame.setFixedHeight(60)
        hl = QHBoxLayout(header_frame)
        hl.setContentsMargins(8, 6, 8, 6)
        hl.setSpacing(10)

        self._sprite_preview = QLabel()
        self._sprite_preview.setFixedSize(52, 52)
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED}; border:1px solid {C.BORDER}; border-radius:5px;"
        )
        self._sprite_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sprite_preview.setToolTip(
            f"<b style='color:{C.ACCENT_BLU}'>Starting sprite</b><br><br>"
            "Click to assign a sprite from the project.<br>"
            "First frame of the initial AnimState."
        )
        self._sprite_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sprite_preview.mousePressEvent = lambda e: self._pick_sprite()
        hl.addWidget(self._sprite_preview)

        name_col = QVBoxLayout()
        name_col.setSpacing(3)

        self._tag_lbl = QLabel("Index: —")
        self._tag_lbl.setFont(QFont(T.UI, T.SM))
        self._tag_lbl.setStyleSheet(f"color:{icons.COLOR_ACTOR};")
        self._tag_lbl.setToolTip(
            "Position de l'actor dans la scène (ordre de traitement et de rendu)."
        )
        name_col.addWidget(self._tag_lbl)
        hl.addLayout(name_col, 1)
        cl.addWidget(header_frame)

        # ── Badge prefab (visible seulement si actor.prefab_name) ──
        self._prefab_badge = QFrame()
        self._prefab_badge.setFrameShape(QFrame.Shape.NoFrame)
        self._prefab_badge.setStyleSheet(
            f"background:{C.BG_DEEP}; border:none; border-left:3px solid {icons.COLOR_PREFAB};"
        )
        self._prefab_badge.setFixedHeight(28)
        pb_layout = QHBoxLayout(self._prefab_badge)
        pb_layout.setContentsMargins(8, 0, 6, 0)
        pb_layout.setSpacing(6)
        self._prefab_badge_lbl = QLabel()
        self._prefab_badge_lbl.setFont(QFont(T.UI, T.SM))
        self._prefab_badge_lbl.setStyleSheet(f"color:{icons.COLOR_PREFAB};")
        pb_layout.addWidget(self._prefab_badge_lbl, 1)
        btn_open_prefab = QPushButton("Open prefab")
        btn_open_prefab.setFont(QFont(T.UI, T.XS))
        btn_open_prefab.setFixedHeight(18)
        btn_open_prefab.setStyleSheet(
            f"QPushButton{{color:{icons.COLOR_PREFAB};background:transparent;border:1px solid {icons.COLOR_PREFAB};"
            f"border-radius:2px;padding:0 5px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{icons.COLOR_PREFAB};}}"
        )
        btn_open_prefab.clicked.connect(self._open_prefab)
        pb_layout.addWidget(btn_open_prefab)
        _pb_btn_style = (
            f"QPushButton{{color:{icons.COLOR_PREFAB};background:transparent;border:1px solid {icons.COLOR_PREFAB};"
            f"border-radius:2px;padding:0 5px;}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER};}}"
            f"QPushButton:hover:!disabled{{color:{C.TEXT_HI};background:{icons.COLOR_PREFAB};}}"
        )
        # « Relink » et « Expose » sont l'aller-retour du statut linked/unlinked
        # (structure des components + fichier .lua identiques au prefab, cf.
        # core/models/scene.actor_prefab_linked) : Relink adopte le prefab,
        # Expose publie CETTE instance comme nouvelle définition du prefab.
        self._btn_relink = QPushButton("Relink")
        self._btn_relink.setFont(QFont(T.UI, T.XS))
        self._btn_relink.setFixedHeight(18)
        self._btn_relink.setToolTip(
            "Reload this instance's components/palette/notes from the\n"
            "prefab's current definition — discards local structural changes."
        )
        self._btn_relink.setStyleSheet(_pb_btn_style)
        self._btn_relink.clicked.connect(self._relink_to_prefab)
        pb_layout.addWidget(self._btn_relink)
        self._btn_expose = QPushButton("Expose")
        self._btn_expose.setFont(QFont(T.UI, T.XS))
        self._btn_expose.setFixedHeight(18)
        self._btn_expose.setToolTip(
            "Push this instance's components/palette/notes up to the prefab —\n"
            "every OTHER instance of it is updated too."
        )
        self._btn_expose.setStyleSheet(_pb_btn_style)
        self._btn_expose.clicked.connect(self._expose_to_prefab)
        pb_layout.addWidget(self._btn_expose)
        btn_unlink = QPushButton("×")
        btn_unlink.setFont(QFont(T.UI, T.MD))
        btn_unlink.setFixedSize(18, 18)
        btn_unlink.setToolTip("Break the link with the prefab\n(the actor becomes independent)")
        btn_unlink.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:transparent;border:none;}}"
            f"QPushButton:hover{{color:{C.ACCENT_RED};}}"
        )
        btn_unlink.clicked.connect(self._unlink_prefab)
        pb_layout.addWidget(btn_unlink)
        self._prefab_badge.setVisible(False)
        cl.addWidget(self._prefab_badge)

        # ── Ligne « Expose to prefab » (acteur ORDINAIRE, pas déjà une
        # instance) : promeut cet acteur en nouveau template réutilisable —
        # l'aller simple qui fait exister le lien que le badge ci-dessus
        # gère ensuite. Même ligne visuelle que le badge, un seul bouton.
        self._expose_row = QFrame()
        self._expose_row.setFrameShape(QFrame.Shape.NoFrame)
        self._expose_row.setStyleSheet(
            f"background:{C.BG_DEEP}; border:none; border-left:3px solid {C.BORDER_MID};"
        )
        self._expose_row.setFixedHeight(28)
        er_layout = QHBoxLayout(self._expose_row)
        er_layout.setContentsMargins(8, 0, 6, 0)
        er_layout.addStretch(1)
        btn_expose_new = QPushButton("Expose to prefab")
        btn_expose_new.setFont(QFont(T.UI, T.XS))
        btn_expose_new.setFixedHeight(18)
        btn_expose_new.setToolTip(
            "Create a new prefab from this actor's current components/palette/\n"
            "notes — this actor becomes its first linked instance."
        )
        btn_expose_new.setStyleSheet(
            f"QPushButton{{color:{icons.COLOR_PREFAB};background:transparent;border:1px solid {icons.COLOR_PREFAB};"
            f"border-radius:2px;padding:0 5px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{icons.COLOR_PREFAB};}}"
        )
        btn_expose_new.clicked.connect(self._expose_new_prefab)
        er_layout.addWidget(btn_expose_new)
        self._expose_row.setVisible(False)
        cl.addWidget(self._expose_row)

        self._active = QCheckBox("Active on start")
        self._active.setFont(QFont(T.UI, T.MD))
        self._active.setStyleSheet(
            f"color:{C.TEXT_NORM}; padding:4px 6px;"
            f"background:{C.BG_BASE}; border-radius:3px;"
        )
        self._active.toggled.connect(lambda v: self._set("active", v))
        _tip(self._active, "actor.active")
        cl.addWidget(self._active)

        # ── TRANSFORM card ───────────────────────────────────────────
        self._transform_group = CollapsibleCard("Transform")
        tl = self._transform_group.body_layout

        from ui.common.widgets import W as _W

        # ── Position : X [ ]  Y [ ] — px / tile / réf de variable ────
        self._tx = _W.value_field(0, project=self._project)
        self._tx.changed.connect(lambda raw: self._set("x", raw))
        _tip(self._tx, "actor.x")
        self._ty = _W.value_field(0, project=self._project)
        self._ty.changed.connect(lambda raw: self._set("y", raw))
        _tip(self._ty, "actor.y")
        # Largeur de colonne des libellés : mesurée sur le plus long du groupe
        # plutôt que codée en dur — « monospace » se résout à des fontes de
        # métriques différentes selon la machine, une valeur fixe tronquerait
        # « Mode window » ici et pas là.
        from PyQt6.QtGui import QFontMetrics
        _lbl_w = max(
            QFontMetrics(QFont(T.UI, T.SM)).horizontalAdvance(t)
            for t in ("Position", "Priority", "Mode window")
        ) + 4

        _W.pair("Position", "X", C.AXIS_X, self._tx, "Y", C.AXIS_Y, self._ty, tl,
                label_width=_lbl_w)

        # ── Direction initiale : sélecteur 3×3 ───────────────────
        dir_row = QHBoxLayout(); dir_row.setSpacing(8)
        dir_row.setContentsMargins(0, 2, 0, 2)
        dir_lbl = QLabel("Direction"); dir_lbl.setFont(QFont(T.UI, T.SM))
        dir_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        dir_lbl.setFixedWidth(_lbl_w)
        dir_row.addWidget(dir_lbl)
        self._dir_picker = DirectionPicker()
        self._dir_picker.changed.connect(self._on_direction)
        dir_row.addWidget(self._dir_picker)
        dir_row.addStretch()
        tl.addLayout(dir_row)

        # ── Priority ─────────────────────────────────────────────
        # (la palette OBJ se règle désormais dans l'éditeur du SpriteComponent,
        # cf. component_editors/sprite.py — palette_picker_slot)
        self._tpriority = _W.spinbox(0, min_v=0, max_v=3)
        self._tpriority.valueChanged.connect(lambda v: self._set("priority", v))
        _tip(self._tpriority, "actor.priority")
        _W.row("Priority", self._tpriority, tl, label_width=_lbl_w)

        # ── Mode window ───────────────────────────────────────────
        # 2 = window OBJ : le sprite devient un pochoir de forme libre.
        # Mode 1 (semi-transparent) volontairement absent — il suppose le
        # blending, pas encore câblé côté runtime.
        # Le champ reste `obj_mode` (nom du registre GBA, OAM attr0 bits 10-11,
        # et API Lua publique self.obj_mode) : seuls les libellés adoptent
        # le vocabulaire « window » du panneau WINDOWS de la scène.
        self._tobj_mode = _W.combobox(["Normal", "Masque (window OBJ)"])
        self._tobj_mode.currentIndexChanged.connect(
            lambda i: self._set("obj_mode", 2 if i == 1 else 0))
        _tip(self._tobj_mode, "actor.obj_mode")
        _W.row("Mode window", self._tobj_mode, tl, label_width=_lbl_w)

        # ── Parent (ROADMAP v0.23) ────────────────────────────────
        # Juste avant « Screen space », pour la même raison que lui : les deux
        # changent le SENS de X/Y. Screen space les fait passer du monde à
        # l'écran ; un parent les fait passer du monde à son repère à lui.
        self._tparent = _W.combobox([])
        self._tparent.currentIndexChanged.connect(self._on_parent_changed)
        self._tparent.setToolTip(
            "<b>Parent</b><br><br>"
            "L'acteur dans le repère duquel la position de celui-ci est "
            "exprimée.<br>X/Y, rotation et échelle deviennent alors LOCAUX : "
            "le parent<br>bouge, tourne ou grandit, et son sous-arbre suit.<br><br>"
            "Ce n'est pas de l'héritage — la définition n'est pas reprise. Pour "
            "ça,<br>c'est un prefab. Cacher le parent cache tout son sous-arbre."
            "<br><br>Un parent se choisit dans la même scène, et un cycle est "
            "refusé au Build.")
        _W.row("Parent", self._tparent, tl, label_width=_lbl_w)

        # ── Ancrage écran (UI en sprite) ──────────────────────────
        # Juste sous Position : c'est le sens de X/Y qu'il change (monde →
        # écran), pas une propriété de rendu.
        self._tscreen = QCheckBox("Screen space"); self._tscreen.setStyleSheet(QSS.checkbox)
        self._tscreen.toggled.connect(lambda v: self._set("screen_space", v))
        _tip(self._tscreen, "actor.screen_space")
        tl.addWidget(self._tscreen)

        # ── Visible ───────────────────────────────────────────────
        self._tvisible = QCheckBox("Visible"); self._tvisible.setStyleSheet(QSS.checkbox)
        self._tvisible.toggled.connect(lambda v: self._set("visible", v))
        _tip(self._tvisible, "actor.visible")
        tl.addWidget(self._tvisible)
        cl.addWidget(self._transform_group)

        # ── AFFINE card ──────────────────────────────────────────────
        # Carte à part, et non une ligne du Transform : `affine_transform` n'est
        # pas un PLACEMENT (x/y/priority/direction — propre à un actor posé dans
        # une scène) mais une capacité de RENDU, que le prefab décide pour toutes
        # les copies de son pool. C'est ce qui permet de la montrer sur un
        # Prefab, dont la carte Transform, elle, n'a aucun sens.
        # `affine_transform` réserve un slot de matrice affine OAM (32 max/scène) ;
        # sans lui, rotation/scale (et les self.sprite_* du sprite) n'ont rien où
        # écrire au runtime.
        self._affine_group = CollapsibleCard("Affine")
        al = self._affine_group.body_layout

        self._taffine = QCheckBox("Affine transform"); self._taffine.setStyleSheet(QSS.checkbox)
        self._taffine.toggled.connect(self._on_affine_toggle)
        _tip(self._taffine, "actor.affine_transform")
        al.addWidget(self._taffine)

        # Rotation/Scale de DÉPART : des valeurs d'instance, pas de template —
        # d'où des conteneurs nommés, masqués en mode Prefab (cf. load_prefab).
        self._aff_rot_row = QWidget(); self._aff_rot_row.setStyleSheet("background:transparent;")
        _aff_row = QHBoxLayout(self._aff_rot_row); _aff_row.setContentsMargins(0, 2, 0, 2)
        _aff_lbl = QLabel("Rotation"); _aff_lbl.setFont(QFont(T.UI, T.SM))
        _aff_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        _aff_lbl.setFixedWidth(_lbl_w)
        _aff_row.addWidget(_aff_lbl)
        self._taff_rot = _W.spinbox(0, min_v=0, max_v=359)
        self._taff_rot.valueChanged.connect(lambda v: self._set("rotation", v))
        _tip(self._taff_rot, "actor.rotation")
        _aff_row.addWidget(self._taff_rot)
        _aff_row.addStretch()
        al.addWidget(self._aff_rot_row)

        self._aff_scale_row = QWidget(); self._aff_scale_row.setStyleSheet("background:transparent;")
        _scale_row = QHBoxLayout(self._aff_scale_row); _scale_row.setContentsMargins(0, 2, 0, 2)
        _scale_lbl = QLabel("Scale"); _scale_lbl.setFont(QFont(T.UI, T.SM))
        _scale_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
        _scale_lbl.setFixedWidth(_lbl_w)
        _scale_row.addWidget(_scale_lbl)
        self._taff_sx = _W.double_spinbox(1.0, min_v=0.1, max_v=4.0, step=0.1)
        self._taff_sy = _W.double_spinbox(1.0, min_v=0.1, max_v=4.0, step=0.1)
        self._taff_sx.valueChanged.connect(lambda v: self._set("scale_x", v))
        self._taff_sy.valueChanged.connect(lambda v: self._set("scale_y", v))
        _tip(self._taff_sx, "actor.scale"); _tip(self._taff_sy, "actor.scale")
        _scale_row.addWidget(self._taff_sx)
        _scale_row.addWidget(QLabel("×"))
        _scale_row.addWidget(self._taff_sy)
        _scale_row.addStretch()
        al.addWidget(self._aff_scale_row)
        # Rotation/scale n'ont de sens que si le slot est réservé
        self._aff_widgets = (self._taff_rot, self._taff_sx, self._taff_sy)
        cl.addWidget(self._affine_group)

        _ico_btn = (
            f"QPushButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;"
            f"font-family:{T.UI_STACK};font-size:{T.XL}px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};border-color:{C.BORDER_MID};}}"
        )

        # ── COMPONENTS card ──────────────────────────────────────────
        self._comp_card = CollapsibleCard("Components", color=icons.COLOR_ACTOR)
        btn_add = QPushButton("+"); btn_add.setFixedSize(20, 20)
        btn_add.setStyleSheet(_ico_btn); btn_add.clicked.connect(self._show_add_menu)
        btn_del = QPushButton("−"); btn_del.setFixedSize(20, 20)
        btn_del.setStyleSheet(_ico_btn); btn_del.clicked.connect(self._remove_selected_component)
        self._comp_card.add_header_widget(btn_add)
        self._comp_card.add_header_widget(btn_del)

        self._comp_list = ComponentListWidget()
        self._comp_list.setFixedHeight(100)
        self._comp_list.setFont(QFont(T.UI, T.MD))
        self._comp_list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};color:{C.TEXT_NORM};"
            f"border:none;border-radius:0;}}"
            f"QListWidget::item{{padding:4px 8px;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};color:{C.ACCENT};"
            f"border-left:2px solid {C.ACCENT};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )
        self._comp_list.currentRowChanged.connect(self._on_component_selected)
        self._comp_list.script_dropped.connect(self._on_script_dropped)
        self._comp_card.body_layout.setContentsMargins(0, 0, 0, 0)
        self._comp_card.body_layout.addWidget(self._comp_list)
        cl.addWidget(self._comp_card)

        # ── CHILDREN card (prefab segmenté — ROADMAP v0.23) ────────────
        # Visible seulement en mode Prefab : une partie n'a de sens que dans un
        # template. Le « + » ajoute une ligne tout de suite, sans boîte de
        # dialogue — on renomme ensuite dans l'inspecteur, comme partout
        # ailleurs dans ce logiciel.
        self._children_card = CollapsibleCard("Children", color=icons.COLOR_PREFAB)
        _pb_add = QPushButton("+"); _pb_add.setFixedSize(20, 20)
        _pb_add.setStyleSheet(_ico_btn); _pb_add.clicked.connect(self._add_child)
        _pb_del = QPushButton("−"); _pb_del.setFixedSize(20, 20)
        _pb_del.setStyleSheet(_ico_btn); _pb_del.clicked.connect(self._remove_selected_child)
        self._children_card.add_header_widget(_pb_add)
        self._children_card.add_header_widget(_pb_del)

        self._children_tree = _ChildrenTree()
        self._children_tree.setFixedHeight(92)
        self._children_tree.setFont(QFont(T.UI, T.MD))
        self._children_tree.itemDoubleClicked.connect(self._open_selected_child)
        self._children_tree.reparented.connect(self._on_children_reparented)
        self._children_tree.setToolTip(chr(10).join([
            "Les ENFANTS de ce prefab — un boss segmenté, une chenille.",
            "Chaque enfant est un acteur à part entière : son sprite, ses",
            "boxes, son transform local. Double-cliquer pour l'éditer,",
            "glisser-déposer SUR un autre enfant pour le reparenter.",
            "",
            "Le pool se dit en INSTANCES : « max instances » × (1 + enfants)",
            "entrées sont réservées, et c'est ce total qui est payé.",
        ]))
        self._children_card.body_layout.setContentsMargins(0, 0, 0, 0)
        self._children_card.body_layout.addWidget(self._children_tree)
        cl.addWidget(self._children_card)
        self._children_card.setVisible(False)

        # ── ÉDITEUR intégré dans la carte Components (sous la liste) ──
        self._editor_container = QWidget()
        self._editor_container.setStyleSheet(f"background:{C.BG_BASE};")
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(8, 6, 8, 8)
        self._editor_layout.setSpacing(6)
        self._comp_card.body_layout.addWidget(self._editor_container)

        self._ctx_color = icons.COLOR_ACTOR   # couleur courante du contexte (actor par défaut)

        cl.addStretch()

        layout.addWidget(self._content)
        layout.addStretch()
        self._content.setVisible(False)

    # ── Chargement ───────────────────────────────────────────────

    # Couleurs de contexte (cohérentes avec assets_finder_panel et InspectorPanel)
    _COLOR_ACTOR  = icons.COLOR_ACTOR
    _COLOR_PREFAB = icons.COLOR_PREFAB
    _COLOR_SEL_BG_ACTOR  = C.BG_SEL
    _COLOR_SEL_BG_PREFAB = f"{icons.COLOR_PREFAB}15"

    def _apply_context_color(self, color: str, sel_bg: str):
        """Met à jour le titre COMPONENTS et la sélection de liste."""
        self._ctx_color = color
        self._comp_card.set_color(color)
        self._comp_list.setStyleSheet(
            f"QListWidget{{background:{C.BG_DEEP};color:{C.TEXT_NORM};"
            f"border:none;border-radius:0;}}"
            f"QListWidget::item{{padding:4px 8px;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{sel_bg};color:{color};"
            f"border-left:2px solid {color};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )

    def load_prefab(self, prefab: Optional[Prefab], project: Project, scene: Optional[Scene] = None):
        """Un prefab EST son actor racine (`prefab.actor`, cf.
        core/models/scene.Prefab) : ce n'est qu'un raccourci vers `load()`,
        pas une seconde construction. `scene` : scène active de l'éditeur
        (contexte d'affichage) — un Prefab n'appartient à aucune scène, mais
        son champ Palette utilise le même picker qu'un Actor normal : à
        l'instanciation, il arrive dans une scène et se comporte exactement
        comme un actor (repli sur le slot 0 si le slot assigné n'a pas de
        palette active dans cette scène-là)."""
        self._prefab = prefab
        self.load(prefab.actor if prefab else None, project, scene, is_prefab_root=True)

    def load(self, actor: Optional[Actor], project: Project, scene: Optional[Scene] = None,
              *, is_prefab_root: bool = False):
        """Constructeur UNIQUE : un acteur de scène et la racine d'un prefab
        sont tous deux des `Actor`, montrés avec les mêmes champs — seules
        les quelques différences de nature (un template n'est jamais posé
        nulle part, porte des enfants) restent des branches locales, pas une
        seconde méthode qui reconstruirait tout à la main."""
        self._actor = actor
        self._project = project
        self._is_prefab_template = is_prefab_root
        self._scene = scene
        if not is_prefab_root:
            self._prefab = None
        self._child_owner = None      # remis par `load_child` le cas échéant
        color = self._COLOR_PREFAB if is_prefab_root else self._COLOR_ACTOR
        sel_bg = self._COLOR_SEL_BG_PREFAB if is_prefab_root else self._COLOR_SEL_BG_ACTOR
        self._apply_context_color(color, sel_bg)
        if not actor:
            self._content.setVisible(False); self._empty.setVisible(True); return
        self._empty.setVisible(False); self._content.setVisible(True)
        self._blocking = True
        self._notes_edit.set_text_silent(getattr(actor, "notes", ""))
        if is_prefab_root:
            self._tag_lbl.setText("Index: (prefab)")
        elif scene:
            try:
                idx = scene.actors.index(actor)
                self._tag_lbl.setText(f"Index: {idx}")
            except ValueError:
                self._tag_lbl.setText("Index: —")
        else:
            self._tag_lbl.setText("Index: —")
        # Un template n'est jamais lui-même actif/inactif — seules ses
        # instances le sont.
        self._active.setChecked(True if is_prefab_root else actor.active)
        # Badge « instance de » : sans objet pour un template ou une partie.
        # Sinon statut linked/unlinked EN DIRECT (core/models/scene.
        # actor_prefab_linked) : c'est lui qui dit si Relink/Expose changeraient
        # quelque chose, et si le prochain enregistrement du prefab écraserait
        # une divergence locale.
        self._expose_row.setVisible(False)
        if not is_prefab_root and actor.prefab_name:
            from core.models.scene import actor_prefab_linked
            src_prefab = self._project.get_prefab(actor.prefab_name) if self._project else None
            linked = src_prefab is not None and actor_prefab_linked(actor, src_prefab)
            if src_prefab is None:
                self._prefab_badge_lbl.setText(f"◈ Instance de  {actor.prefab_name}  (introuvable)")
                self._prefab_badge_lbl.setStyleSheet(f"color:{C.ACCENT_RED};")
            elif linked:
                self._prefab_badge_lbl.setText(f"◈ Instance de  {actor.prefab_name}")
                self._prefab_badge_lbl.setStyleSheet(f"color:{icons.COLOR_PREFAB};")
            else:
                self._prefab_badge_lbl.setText(f"◈ Instance de  {actor.prefab_name}  — unlinkée")
                self._prefab_badge_lbl.setStyleSheet(f"color:{C.ACCENT_YLW};")
            # Relink n'a de sens que s'il y a une DIVERGENCE à annuler — déjà
            # linkée, le bouton n'apporterait rien à cliquer.
            self._btn_relink.setVisible(src_prefab is not None and not linked)
            self._btn_expose.setEnabled(src_prefab is not None)
            self._prefab_badge.setVisible(True)
        else:
            self._prefab_badge.setVisible(False)
            # Ligne « Expose to prefab » : seulement pour un acteur ORDINAIRE
            # posé dans une scène — pas pour un template, ni pour une partie
            # de prefab (`load_child` la masque après coup, cf. plus bas).
            self._expose_row.setVisible(not is_prefab_root)
        # La POSE (x/y/priorité/parent/écran/direction) n'a de sens que pour
        # un actor posé quelque part — jamais pour la racine d'un template.
        self._transform_group.setVisible(not is_prefab_root)
        self._affine_group.setVisible(True)
        self._aff_rot_row.setVisible(not is_prefab_root)
        self._aff_scale_row.setVisible(not is_prefab_root)
        if not is_prefab_root:
            from core.models.field_value import variables_from_project
            _vars = variables_from_project(self._project)
            self._tx.set_variables(_vars); self._ty.set_variables(_vars)
            self._tx.set_raw(actor.x); self._ty.set_raw(actor.y)
            self._dir_picker.set_direction(getattr(actor, "dir_x", 0), getattr(actor, "dir_y", 0))
            self._tpriority.setValue(actor.priority)
            self._tobj_mode.setCurrentIndex(1 if getattr(actor, "obj_mode", 0) == 2 else 0)
            self._refresh_parent_choices(actor)
            self._tscreen.setChecked(bool(getattr(actor, "screen_space", False)))
        # Les ENFANTS ne se montrent qu'ici : un enfant n'a de sens que dans
        # un template (ROADMAP v0.23).
        self._children_card.setVisible(is_prefab_root)
        if is_prefab_root:
            self._refresh_children_list()
        self._taffine.setChecked(bool(getattr(actor, "affine_transform", False)))
        self._set_affine_enabled(bool(getattr(actor, "affine_transform", False)))
        if not is_prefab_root and not self._blocking:
            self._taff_rot.setValue(getattr(actor, "rotation", 0))
            self._taff_sx.setValue(getattr(actor, "scale_x", 1.0))
            self._taff_sy.setValue(getattr(actor, "scale_y", 1.0))
        self._tvisible.setChecked(actor.visible)
        self._blocking = False
        self._refresh_component_list()
        if not is_prefab_root:
            self._refresh_sprite_preview()

    # ── Parent (ROADMAP v0.23) ────────────────────────────────────

    def _descendants(self, name: str) -> set:
        """Les acteurs qui descendent de `name`, lui compris.

        Ils sont retirés de la liste des parents possibles : se choisir
        soi-même, ou choisir quelqu'un de son propre sous-arbre, fait un cycle.
        Le Build le refuserait de toute façon — mais l'empêcher ici évite à
        l'auteur de construire une scène qui ne se compile plus, ce qui est
        toujours mieux que de le lui apprendre après coup."""
        # Sur les PARTIES d'un prefab quand on en édite une, sur les acteurs
        # de la scène sinon — même parcours, deux collections.
        pool = ((getattr(self._child_owner, "children", []) or [])
                if self._child_owner is not None
                else (self._scene.actors if self._scene else None))
        if pool is None:
            return {name}
        from core.models.scene import actor_descendant_names
        return {name} | actor_descendant_names(pool, name)

    def _refresh_parent_choices(self, actor):
        self._tparent.blockSignals(True)
        self._tparent.clear()
        self._tparent.addItem("— aucun —", None)
        exclus = self._descendants(actor.name)
        # Une PARTIE se rattache à une autre partie du même prefab, ou à la
        # racine (« — aucun — »). Rien d'extérieur n'est nommable : c'est ce
        # qui garde la profondeur connue au build (ROADMAP v0.23).
        if self._child_owner is not None:
            for pt in (getattr(self._child_owner, "children", []) or []):
                if pt.name not in exclus:
                    self._tparent.addItem(pt.name, pt.name)
        else:
            for a in (self._scene.actors if self._scene else []):
                if a.name not in exclus:
                    self._tparent.addItem(a.name, a.name)
        cur = getattr(actor, "parent", None)
        i = self._tparent.findData(cur)
        if cur and i < 0:
            # Parent disparu (acteur supprimé, scène éditée hors de l'éditeur) :
            # on le garde VISIBLE plutôt que de le réécrire en silence. Le Build
            # le nomme déjà comme introuvable ; l'inspecteur doit dire la même
            # chose que lui.
            self._tparent.addItem(f"{cur}  (introuvable)", cur)
            i = self._tparent.findData(cur)
        self._tparent.setCurrentIndex(max(0, i))
        self._tparent.blockSignals(False)

    def _on_parent_changed(self, _i: int):
        if self._blocking or not self._actor:
            return
        # Le parent conditionne l'imbrication affichée par l'arbre — celui
        # de la scène pour un actor, l'arbre CHILDREN de ce même inspecteur
        # pour une partie de prefab. `_set` persiste déjà l'actor ; il faut
        # en plus dire à l'arbre concerné de se reconstruire, undo/redo
        # compris (extra_persist tourne dans les deux sens).
        self._set("parent", self._tparent.currentData(),
                  extra_persist=self._refresh_children_list
                  if self._child_owner is not None
                  else lambda: get_dispatcher()._emit("actors_list_changed"))

        # ── Enfants d'un prefab (ROADMAP v0.23) ───────────────────────

    def _refresh_children_list(self):
        self._children_tree.populate(self._prefab)

    def _on_children_reparented(self):
        """Une partie a changé de parent depuis l'arbre (glisser-déposer) :
        même geste que tout autre changement de `children` — enregistrer le
        prefab propriétaire et reconstruire l'arbre affiché."""
        self._persist()
        self._refresh_children_list()
        self.changed.emit()

    def _add_child(self):
        """Ajoute une partie et l'ouvre tout de suite.

        Pas de boîte de dialogue : le « + » crée la ligne, et le nom se change
        dans l'inspecteur comme pour tout le reste."""
        if not self._is_prefab_template or not self._prefab:
            return
        from core.models.scene import Actor as _A
        taken = {pt.name for pt in (self._prefab.children or [])} | {self._prefab.name}
        base, n = "Part", 1
        while f"{base}{n}" in taken:
            n += 1
        # Posée SUR la racine (0, 0) : un bras se déplace ensuite là où il va,
        # et une partie qui apparaît au centre se voit — une partie posée hors
        # écran donnerait l'impression que le « + » n'a rien fait.
        part = _A(name=f"{base}{n}", x=0, y=0)
        self._prefab.children.append(part)
        self._persist()
        self._refresh_children_list()
        self._children_tree.select_part(part)
        self.changed.emit()

    def _remove_selected_child(self):
        if not self._is_prefab_template or not self._prefab:
            return
        part = self._children_tree.current_part()
        parts = self._prefab.children or []
        if part not in parts:
            return
        parts.remove(part)
        gone = part.name
        # Ce qui descendait d'elle remonte à la racine plutôt que de pointer un
        # nom disparu : le build refuserait un parent introuvable, et l'auteur
        # n'a pas demandé à casser son prefab en supprimant une pièce.
        for pt in parts:
            if getattr(pt, "parent", None) == gone:
                pt.parent = None
        self._persist()
        self._refresh_children_list()
        self.changed.emit()

    def _open_selected_child(self, item=None, _col=0):
        """Édite la partie sélectionnée — avec les champs d'un acteur, puisque
        c'en est un."""
        if not self._is_prefab_template or not self._prefab:
            return
        part = item.data(0, _ChildrenTree._ROLE_OBJ) if item else self._children_tree.current_part()
        if part is not None:
            self.load_child(part, self._prefab, self._project, self._scene)

    def load_child(self, part, prefab, project: Project, scene: Optional[Scene] = None):
        owner = prefab
        self.load(part, project, scene)
        # APRÈS `load`, qui remet `_child_owner` à None : c'est lui qui dit à
        # `_persist` de sauver le PREFAB et non la scène.
        self._child_owner = owner
        self._refresh_parent_choices(part)
        # `load()` l'a montrée (une partie n'est ni un template ni une
        # instance) : sans objet ici, une partie de prefab ne s'expose pas
        # elle-même en second prefab.
        self._expose_row.setVisible(False)

    def update_position(self, x: int, y: int):
        if self._blocking or not self._actor: return
        self._blocking = True
        self._tx.set_raw(x); self._ty.set_raw(y)
        self._blocking = False

    def notify_lua_changed(self, path: str):
        """Appelé par MainWindow quand ProjectWatcher détecte un changement Lua."""
        pass

    def _refresh_sprite_preview(self):
        """Affiche la première frame de l'état initial dans le header."""
        self._sprite_preview.clear()
        self._sprite_preview.setText("?")
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED};border:1px solid {C.BORDER};border-radius:4px;"
            f"color:{C.BORDER_MID};font-size:18px;"
        )
        if not self._actor or not self._project:
            return
        comp = self._actor.get_component("sprite")
        if not comp or not comp.sprite_name:
            return
        sprite = self._project.get_sprite(comp.sprite_name)
        if not sprite or not sprite.asset:
            return
        asset_path = self._project.asset_abs(sprite.asset)
        if not asset_path or not asset_path.exists():
            return
        # Trouver l'AnimState correspondant à initial_state
        state_name = getattr(comp, "initial_state", "Idle")
        state = next((s for s in sprite.states if s.name == state_name), None)
        if not state and sprite.states:
            state = sprite.states[0]
        sd = state.directions[0] if state and state.directions else None
        if not sd or not sd.frames:
            return
        frame = sd.frames[0]
        px = QPixmap(str(asset_path))
        if px.isNull():
            return
        cropped = QPixmap(sprite.frame_w, sprite.frame_h)
        cropped.fill(Qt.GlobalColor.transparent)
        painter = QPainter(cropped)
        for t in frame.tiles:
            tile_px = px.copy(t.src_col * 8, t.src_row * 8, 8, 8)
            painter.drawPixmap(t.dst_col * 8, t.dst_row * 8, tile_px)
        painter.end()
        scaled = cropped.scaled(
            44, 44,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._sprite_preview.setPixmap(scaled)
        self._sprite_preview.setStyleSheet(
            f"background:{C.BG_RAISED};border:1px solid {C.BORDER_MID};border-radius:4px;"
        )
        self._sprite_preview.setText("")

    def _pick_sprite(self):
        if not self._actor or not self._project:
            return
        sprites_dir = self._project.root / "assets" / "sprites"
        pngs = sorted(sprites_dir.glob("*.png")) if sprites_dir.exists() else []
        if not pngs:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Aucun sprite",
                "Aucun PNG trouvé dans assets/sprites/.")
            return

        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        for png in pngs:
            action = menu.addAction(png.stem)
            action.setData(str(png))

        pos = self._sprite_preview.mapToGlobal(
            self._sprite_preview.rect().bottomLeft()
        )
        chosen = menu.exec(pos)
        if not chosen:
            return

        png_path = Path(chosen.data())
        sprite_name = png_path.stem

        # Récupérer ou créer le SpriteAsset correspondant
        from core.models.sprite import SpriteAsset
        sprite = self._project.get_sprite(sprite_name)
        if not sprite:
            dst = self._project.import_asset(png_path, "sprites")
            sprite = SpriteAsset(
                name=sprite_name,
                asset=self._project.asset_rel(dst),
            )
            self._project.sprites.append(sprite)
            with __import__("contextlib").suppress(Exception):
                get_dispatcher().save_sprite(sprite)

        comp = self._actor.get_component("sprite")
        if comp:
            comp.sprite_name = sprite_name
        else:
            self._actor.add_component("sprite", sprite_name=sprite_name)
        self._persist()
        self._refresh_sprite_preview()
        self._refresh_component_list()
        self.changed.emit()

    def _persist(self):
        if not self._project or not self._actor: return
        if self._child_owner is not None:
            # Une partie n'est pas une ressource : c'est son prefab qui
            # la contient, donc c'est lui qu'on enregistre.
            get_dispatcher().save_prefab(self._child_owner)
        elif self._is_prefab_template:
            # `self._actor` EST `self._prefab.actor` (cf. load_prefab) : c'est
            # le Prefab qu'il faut enregistrer, pas son actor racine seul.
            get_dispatcher().save_prefab(self._prefab)
        else:
            get_dispatcher().save_scene()
            get_dispatcher()._emit("scene_sprites_changed")

    def _open_prefab(self):
        """Bascule l'inspector sur le prefab source de cet actor."""
        if not self._actor or not self._actor.prefab_name or not self._project:
            return
        prefab = self._project.get_prefab(self._actor.prefab_name)
        if prefab:
            get_bus().select(prefab)

    def _unlink_prefab(self):
        """« Unlink » — casse le lien prefab : l'actor devient un actor
        standalone plein (il porte déjà ses propres components, aucune copie
        à faire). Contrairement à Relink/Expose, sort DÉFINITIVEMENT cette
        instance de la propagation de `save_prefab()` — c'est la seule des
        trois actions qui protège une divergence locale pour de bon."""
        if not self._actor:
            return
        self._actor.prefab_name = None
        get_dispatcher().save_scene()
        get_dispatcher()._emit("actors_list_changed")
        # cf. relink_actor_to_prefab / expose_actor_to_prefab dans
        # command_dispatcher.py : même badge, le project viewer doit suivre.
        get_dispatcher()._emit("project_tree_changed")
        self.load(self._actor, self._project, self._scene)
        self.changed.emit()

    def _relink_to_prefab(self):
        """« Relink to prefab » : recharge cette instance depuis son prefab —
        cf. CommandDispatcher.relink_actor_to_prefab."""
        if not self._actor:
            return
        if get_dispatcher().relink_actor_to_prefab(self._actor):
            self.load(self._actor, self._project, self._scene)
            self.changed.emit()

    def _expose_to_prefab(self):
        """« Expose to prefab » : publie cette instance comme nouvelle
        définition du prefab — cf. CommandDispatcher.expose_actor_to_prefab."""
        if not self._actor:
            return
        if get_dispatcher().expose_actor_to_prefab(self._actor):
            self.load(self._actor, self._project, self._scene)
            self.changed.emit()

    def _expose_new_prefab(self):
        """« Expose to prefab » depuis un acteur ordinaire : crée un nouveau
        prefab — cf. CommandDispatcher.create_prefab_from_actor."""
        if not self._actor:
            return
        prefab = get_dispatcher().create_prefab_from_actor(self._actor)
        if prefab:
            self.load(self._actor, self._project, self._scene)
            self.changed.emit()

    def _set(self, field, value, extra_persist=None):
        if self._blocking or not self._actor: return
        old = getattr(self._actor, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._actor, field, old, value,
            label=f"{self._actor.name}.{field}",
            persist_fn=_do_persist,
        ))
        self.changed.emit()

    def _on_direction(self, dx: int, dy: int):
        if self._blocking or not self._actor: return
        self._set("dir_x", dx)
        self._set("dir_y", dy)

    def _on_affine_toggle(self, on: bool):
        if self._blocking or not self._actor: return
        self._set("affine_transform", on)
        self._set_affine_enabled(on)

    def _set_affine_enabled(self, on: bool):
        for w in self._aff_widgets:
            w.setEnabled(on)

    # ── Components ───────────────────────────────────────────────

    def _refresh_component_list(self, keep_row: int = 0):
        self._comp_list.blockSignals(True)
        self._comp_list.clear()
        if self._actor:
            for comp in self._actor.components:
                type_name = component_type_name(comp)
                label = COMPONENT_LABELS.get(type_name, type_name)
                text = f"{label} [{comp.id}]" + ("  (inactif)" if not comp.active else "")
                self._comp_list.addItem(QListWidgetItem(text))
        self._comp_list.blockSignals(False)
        if self._comp_list.count():
            row = max(0, min(keep_row, self._comp_list.count() - 1))
            # setCurrentRow() (signaux débloqués ci-dessus) déclenche déjà
            # currentRowChanged -> _on_component_selected -> _build_editor() ;
            # un appel explicite ici reconstruirait tout l'éditeur une 2e fois
            # pour rien (double le travail à chaque sélection d'actor).
            self._comp_list.setCurrentRow(row)
        else:
            self._build_editor(None)

    def _show_add_menu(self):
        if not self._actor: return
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        existing_script = self._actor.get_component("script")
        has_active_script = existing_script is not None and existing_script.active
        for type_name, label in COMPONENT_LABELS.items():
            # Un seul ScriptComponent actif à la fois : le compilateur Lua->C
            # (lua_compiler._actor_script) n'en lit de toute façon qu'un seul.
            if type_name == "script" and has_active_script:
                continue
            menu.addAction(label, lambda t=type_name: self._add_component(t))
        menu.exec(QCursor.pos())

    def _add_component(self, type_name: str):
        comp = self._actor.add_component(type_name)
        target_row = len(self._actor.components) - 1

        def undo_refresh():
            self._persist()
            self._refresh_component_list(keep_row=max(0, target_row - 1))
            self.changed.emit()

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=target_row)
            self.changed.emit()

        # Construire la commande APRÈS que add_component a ajouté le comp
        # execute() est appelé par push() mais le comp est déjà dans la liste —
        # on substitue un no-op execute et on surcharge undo/redo manuellement.
        cmd = AddComponentCmd(self._actor, comp, persist_fn=do_refresh)
        # Retirer temporairement le comp pour que push() puisse l'ajouter via execute()
        self._actor.components.remove(comp)
        get_history().push(cmd)   # execute() le remet + rafraîchit

    def _on_script_dropped(self, script_rel: str):
        if not self._actor: return
        existing = self._actor.get_component("script")
        if existing is not None and existing.active:
            # Un seul ScriptComponent actif par actor (cf. _show_add_menu) —
            # on réassigne le script existant plutôt que d'en ajouter un 2e,
            # qui serait de toute façon ignoré au build.
            old_script = existing.script
            if old_script == script_rel:
                return
            row = self._actor.components.index(existing)

            def do_refresh():
                self._persist()
                self._refresh_component_list(keep_row=row)
                self.changed.emit()

            get_history().push(SetFieldCmd(
                existing, "script", old_script, script_rel,
                label=f"{self._actor.name}.script", persist_fn=do_refresh,
            ))
            return

        comp = self._actor.add_component("script", script=script_rel)
        target_row = len(self._actor.components) - 1

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=target_row)
            self.changed.emit()

        cmd = AddComponentCmd(self._actor, comp, persist_fn=do_refresh)
        self._actor.components.remove(comp)
        get_history().push(cmd)

    def _remove_selected_component(self):
        row = self._comp_list.currentRow()
        if row < 0 or not self._actor: return
        comp = self._actor.components[row]

        def do_refresh():
            self._persist()
            self._refresh_component_list(keep_row=row)
            self.changed.emit()

        get_history().push(RemoveComponentCmd(self._actor, comp, row, persist_fn=do_refresh))

    def _on_component_selected(self, row: int):
        if not self._actor or row < 0 or row >= len(self._actor.components):
            self._build_editor(None); return
        self._build_editor(self._actor.components[row])

    def _save_component_change(self, comp=None):
        """
        Persist sans reconstruire l'éditeur.
        Si comp est le composant actuellement affiché, synce les widgets via _field_syncers.
        Sinon (undo sur un autre comp), reconstruit l'éditeur complet.
        """
        self._persist()
        self._refresh_list_labels()
        if comp is not None and comp is not getattr(self, "_current_comp", None):
            row = self._comp_list.currentRow()
            self._build_editor(self._actor.components[row] if row >= 0 else None)
        self.changed.emit()

    def _refresh_list_labels(self):
        """Met à jour les textes de la QListWidget sans toucher à l'éditeur."""
        if not self._actor:
            return
        self._comp_list.blockSignals(True)
        for i, comp in enumerate(self._actor.components):
            item = self._comp_list.item(i)
            if item is None:
                continue
            type_name = component_type_name(comp)
            label = COMPONENT_LABELS.get(type_name, type_name)
            text = f"{label} [{comp.id}]" + ("  (inactif)" if not comp.active else "")
            item.setText(text)
        self._comp_list.blockSignals(False)

    def _clear_editor(self):
        # Détruire le QWidget container et recréer — la seule façon sûre
        # de purger à la fois les widgets ET les QHBoxLayout ajoutés par row().
        # Le repli/dépli reste géré par self._comp_card (CollapsibleCard) :
        # remplacer le container n'y touche pas.
        old = self._editor_container
        new_container = QWidget()
        new_container.setStyleSheet(f"background:{C.BG_BASE};")
        new_layout = QVBoxLayout(new_container)
        new_layout.setContentsMargins(8, 6, 8, 8)
        new_layout.setSpacing(6)

        body_layout = self._comp_card.body_layout
        idx = body_layout.indexOf(old)
        if idx >= 0:
            body_layout.insertWidget(idx, new_container)

        self._editor_container = new_container
        self._editor_layout    = new_layout

        # Supprimer l'ancien (schedules deleteLater pour éviter crash de signal en cours)
        old.hide()
        old.setParent(None)  # type: ignore[arg-type]
        old.deleteLater()

    def _build_editor(self, comp):
        self._clear_editor()
        self._current_comp = comp
        # dict field → callable(value) pour resync les widgets sans rebuild
        self._field_syncers: dict[str, callable] = {}

        if not comp:
            lbl = QLabel("Select a component above")
            lbl.setFont(QFont(T.UI, T.MD))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:10px 6px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._editor_layout.addWidget(lbl); return

        from ui.common.widgets import W as _W

        def row(label, widget):
            return _W.row(label, widget, self._editor_layout)

        # ── Méta-header Id + Active (via W) ──────────────────────
        _W.meta_bar(comp, self._field_syncers, self._set_comp, self._editor_layout)
        _W.separator(self._editor_layout, margin_v=2)

        from ui.scene_manager.inspectors.component_editors import get_editor
        type_name = component_type_name(comp)
        EditorCls = get_editor(type_name)
        if EditorCls:
            EditorCls(self).build(comp, row, self._editor_layout)
        else:
            lbl = QLabel(f"{type_name} — no editor registered")
            lbl.setFont(QFont(T.UI, T.SM)); lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            self._editor_layout.addWidget(lbl)

    def _set_comp(self, comp, field, value):
        if self._blocking or not self._actor: return
        old = getattr(comp, field, None)
        if old == value:
            return
        comp_id = getattr(comp, "id", "?")
        get_history().push(SetFieldCmd(
            comp, field, old, value,
            label=f"{self._actor.name}.{comp_id}.{field}",
            persist_fn=lambda c=comp: self._save_component_change(c),
        ))
        # Syncer les autres widgets du même comp sans rebuild (ex: label liste)
        self._refresh_list_labels()
        self.changed.emit()
