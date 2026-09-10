
"""Panneau gauche (haut) — contenu de la scène ACTIVE : acteurs + mise en
page UI. Sépare deux questions distinctes que l'ancien panneau unique
posait ensemble : « quelles scènes/prefabs/scripts existent dans le projet »
(AssetsFinderPanel, cf. assets_finder_panel.py) et « qu'est-ce qu'il y a DANS
la scène que j'édite en ce moment » (ce module).

Le vocabulaire de l'arbre (rôles QTreeWidgetItem, types de nœud, icônes,
`_lua_handle`) vit ICI : c'est le seul arbre du Scene Manager à en avoir
besoin depuis que la liste projet est rendue par le composant partagé
(ui/common/asset_finder.py)."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTreeWidget,
    QTreeWidgetItem, QMenu, QAbstractItemView, QScrollArea, QSizePolicy,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer, QSize

from ui.common.theme import T, C, S, QSS, ui_font
from ui.common.widgets import W
from ui.common.labels import label
from ui.common.icons import get as _ico, COLOR_DEFAULT, COLOR_UI

from core.models.scene import Actor, Scene
from core.project import Project
from core.selection_bus import (
    get_bus, UIElementSelection, CameraSelection, UILayoutSelection)
from core.command_dispatcher import get_dispatcher, unique_name
from core.history import (
    get_history, AddListItemCmd, RemoveListItemCmd, UILayoutOrderCmd,
    DeleteInterfaceCmd,
)
from core.models.ui_region import KIND_CONTAINER, KIND_LIST, KIND_TEXT, KIND_IMAGE

# ── Rôles QTreeWidgetItem ─────────────────────────────────────────
_ROLE_TYPE = Qt.ItemDataRole.UserRole
_ROLE_OBJ  = Qt.ItemDataRole.UserRole + 1
_ROLE_PATH = Qt.ItemDataRole.UserRole + 2

T_SCENE  = "scene"
T_ACTOR  = "actor"
T_CAMERA = "camera"          # une caméra POSSÉDÉE par la scène active
T_PREFAB = "prefab"
T_SCRIPT = "script"
T_FOLDER = "folder"
T_UI_LAYOUT = "ui_layout"    # nœud « Interface » d'une scène (asset partagé)
T_UI_ELEM   = "ui_elem"      # un élément de la mise en page (zone/conteneur/texte)

# Icône par type d'élément UI (la couleur reste celle de la famille Interface —
# le type se lit à la FORME, cf. project_theme_gba_redesign).
_UI_ELEM_ICON = {KIND_CONTAINER: "ui_container", KIND_LIST: "ui_list",
                 KIND_TEXT: "ui_text", KIND_IMAGE: "ui_image"}
_UI_ELEM_LABEL = {KIND_CONTAINER: "container", KIND_LIST: "list",
                  KIND_TEXT: "text", KIND_IMAGE: "image"}
# Les types proposés à la création, dans l'ordre où l'auteur les rencontre.
_UI_ELEM_ADD = ((KIND_TEXT, "common.text"), (KIND_CONTAINER, "common.container"),
                (KIND_LIST, "common.list"), (KIND_IMAGE, "common.image"))


def _lua_handle(node_type: str, obj) -> str:
    """Poignée d'un nœud RÉFÉRENÇABLE en Lua, ou "" si authoring-only.

    C'est le cœur de l'idée « l'arbre montre ce qu'un script peut nommer » : un
    actor (`get_actor`), un texte (`REGION_*` / `text.draw_in`) et une image
    (`IMAGE_*` / `ui.image_set`) le sont ; un conteneur ne l'est pas — il n'a
    pas de domaine (cf. api.py). Sert au tooltip ET à décider si le nœud
    s'affiche en clair (référençable) ou grisé (authoring)."""
    if node_type == T_ACTOR:
        return f'get_actor("{obj.name}")'
    if node_type == T_CAMERA:
        return f'camera.switch("{obj.name}")'
    if node_type == T_UI_ELEM:
        kind = getattr(obj, "kind", "")
        if kind == KIND_TEXT:
            return f'text.draw_in("{obj.name}", …)'
        if kind == KIND_IMAGE:
            return f'ui.image_set("{obj.name}", …)'
        if kind == KIND_LIST:
            return f'list.index("{obj.name}")'
    return ""

# ── Thème ─── surfaces indigo centralisées (cf. project_theme_gba_redesign) ──
_BG      = C.BG_BASE      # fond de l'arbre / panneaux (indigo profond)
_HEADER  = C.BG_PANEL     # bandeaux de section (SCENES, PREFABS…)
_HOVER   = C.BG_HOVER     # survol de ligne
_SEL_BG  = C.BG_SEL       # fond sélection périwinkle
_SEL_FG  = C.ACCENT       # texte/liseré sélection
_TEXT    = C.TEXT_NORM
_DIM     = C.TEXT_DIM
# Plus de code couleur par type d'asset dans le finder : texte en tons de
# thème, icônes en neutre (COLOR_DEFAULT), distinction par forme d'icône.
# Le code couleur ne subsiste qu'aux niveaux locaux (scene canvas) et dans
# l'en-tête d'inspecteur (AssetHeaderBar).
_C_SCENE  = C.TEXT_HI     # parent de l'arbre : plus clair que ses enfants
_C_PREFAB = _TEXT
_C_SCRIPT = _TEXT
_C_FOLDER = _DIM





# ──────────────────────────────────────────────────────────────────
#  QTreeWidget commun
# ──────────────────────────────────────────────────────────────────

class _Tree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setAnimated(False)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Renommage en place, jamais de dialogue modal : clic sur un item déjà
        # sélectionné, F2 (EditKeyPressed), ou « Renommer » au menu contextuel
        # (add_rename_action ci-dessous) — les trois ouvrent le même éditeur,
        # validé par Entrée ou perte de focus (itemChanged → _commit_rename_*).
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setStyleSheet(QSS.tree_widget)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # Ajuster la hauteur au contenu
        self.model().rowsInserted.connect(self._fit)
        self.model().rowsRemoved.connect(self._fit)
        self.itemExpanded.connect(self._fit)
        self.itemCollapsed.connect(self._fit)

    def add_rename_action(self, menu: QMenu, item: QTreeWidgetItem, label: str):
        """Entrée « Renommer » qui bascule l'item en édition en place. Grisée
        si l'item n'est pas renommable (dossier, en-tête de section)."""
        act = menu.addAction(label)
        act.setShortcut("F2")            # affiché dans le menu ; géré par EditKeyPressed
        act.setEnabled(bool(item.flags() & Qt.ItemFlag.ItemIsEditable))
        # editItem() sur l'item survolé, pas sur la sélection courante : le clic
        # droit ne sélectionne pas forcément la ligne visée.
        act.triggered.connect(lambda _=False, it=item: self.editItem(it, 0))
        return act

    def _fit(self):
        # Compter les lignes VISIBLES : un nœud, plus les descendants de chaque
        # parent déplié.
        total = 0
        root = self.invisibleRootItem()
        stack = [root.child(n) for n in range(root.childCount())]
        while stack:
            item = stack.pop()
            total += 1
            if item.isExpanded():
                stack.extend(item.child(n) for n in range(item.childCount()))
        # Mesurer la hauteur d'une ligne plutôt que de la supposer égale à
        # S.ROW : `setUniformRowHeights` donne à TOUTES les lignes celle de la
        # première, et une ligne d'UI (ui_font(T.LG) + icône) dépasse S.ROW.
        # Provisionner `total * S.ROW` sous-dimensionnait alors la colonne d'un
        # ou deux pixels par ligne — invisible d'abord, puis coupant le bas de
        # la hiérarchie dès qu'assez de lignes s'accumulent. `sizeHintForRow`
        # rend la valeur réellement utilisée ; S.ROW ne sert que de repli tant
        # que la vue n'est pas encore posée (hint < 0).
        row = self.sizeHintForRow(0) if total else 0
        if row <= 0:
            row = S.ROW
        self.setFixedHeight(max(total * row, 4))

    def sizeHint(self):
        return QSize(self.width(), self.minimumHeight())


try:
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
except ImportError:
    QTreeWidgetItemIterator = None


# ──────────────────────────────────────────────────────────────────
#  Arbre du CONTENU de la scène active : acteurs + branche « Interface »
# ──────────────────────────────────────────────────────────────────

class _ActiveSceneTree(_Tree):
    def __init__(self, panel: "SceneTreePanel"):
        super().__init__()
        self._panel = panel
        self._scene: Scene | None = None
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.itemClicked.connect(self._on_click)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.itemChanged.connect(self._on_item_changed)
        # Repli/dépli des éléments d'UI mémorisé PAR OBJET, comme l'ancien
        # arbre unique — sinon chaque populate() (courant après le moindre
        # edit) réouvre tout ce qu'on venait de refermer.
        self._expand_overrides: dict[int, bool] = {}
        self.itemExpanded.connect(self._on_item_expanded)
        self.itemCollapsed.connect(self._on_item_collapsed)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        obj = item.data(0, _ROLE_OBJ)
        if obj is not None:
            self._expand_overrides[id(obj)] = True

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        obj = item.data(0, _ROLE_OBJ)
        if obj is not None:
            self._expand_overrides[id(obj)] = False

    # ── Peuplement ────────────────────────────────────────────────

    def populate(self, project: Project, scene: Scene | None):
        self._scene = scene
        self.blockSignals(True)
        self.clear()
        if scene is not None:
            # Les acteurs se posent en ARBRE depuis la v0.23 : un acteur dont
            # `parent` nomme un autre acteur de la scène s'accroche sous lui.
            # Même dérivation que la branche Interface juste en dessous, qui
            # tire sa hiérarchie des mêmes refs `parent` — une seule façon de
            # montrer une hiérarchie dans ce panneau.
            #
            # Un parent introuvable laisse son acteur à la RACINE plutôt que de
            # le faire disparaître : le Build le nomme déjà comme une erreur, et
            # un acteur invisible dans l'arbre serait le pire moment pour
            # l'apprendre.
            items: dict = {}
            for actor in scene.actors:
                a_item = QTreeWidgetItem()
                a_item.setData(0, _ROLE_TYPE, T_ACTOR)
                a_item.setData(0, _ROLE_OBJ, actor)
                self._update_actor_item(a_item, actor)
                items[actor.name] = a_item
            for actor in scene.actors:
                par = getattr(actor, "parent", None)
                host = items.get(par) if par else None
                if host is not None and host is not items[actor.name]:
                    host.addChild(items[actor.name])
                else:
                    self.addTopLevelItem(items[actor.name])
            for it in items.values():
                it.setExpanded(True)
            for camera in scene.cameras:
                c_item = QTreeWidgetItem()
                c_item.setData(0, _ROLE_TYPE, T_CAMERA)
                c_item.setData(0, _ROLE_OBJ, camera)
                self._update_camera_item(c_item, camera)
                self.addTopLevelItem(c_item)
            self._populate_ui_branch(scene, project)
        self.blockSignals(False)
        self._fit()

    def _populate_ui_branch(self, scene: Scene, project: Project):
        """Ajoute, en tête de liste, les nœuds `Interface` de la scène (une LISTE
        depuis v0.25) : un nœud racine par mise en page référencée, puis la
        hiérarchie de ses éléments (`in_tree_order`).

        Étiquette : « Interface » tant qu'il n'y en a qu'un (le cas courant),
        le NOM de chaque nœud dès qu'il y en a plusieurs — sinon deux racines
        homonymes seraient impossibles à distinguer dans l'arbre."""
        layouts = (project.scene_ui_layouts(scene)
                   if hasattr(project, "scene_ui_layouts") else [])
        many = len(layouts) > 1
        for lay in layouts:
            users = (project.ui_layout_users(lay.name)
                     if hasattr(project, "ui_layout_users") else [])
            shared = len(users) > 1
            root_item = QTreeWidgetItem(self)
            root_item.setData(0, _ROLE_TYPE, T_UI_LAYOUT)
            root_item.setData(0, _ROLE_OBJ, lay)
            root_item.setIcon(0, _ico("ui_layout", COLOR_UI))
            base = lay.name if many else label("common.interface")
            root_item.setText(0, label("scttree.iface_shared_label", base=base, n=len(users))
                              if shared else base)
            root_item.setForeground(0, QColor(C.ACCENT_YLW if shared else _DIM))
            root_item.setFont(0, ui_font(T.MD, bold=True))
            root_item.setToolTip(
                0, label("scttree.iface_tip_shared", name=lay.name, n=len(users)) if shared
                   else label("scttree.iface_tip", name=lay.name))
            items: dict[str, QTreeWidgetItem] = {}
            for _depth, el in lay.in_tree_order():
                parent_item = items.get(el.parent, root_item)
                e_item = QTreeWidgetItem(parent_item)
                self._update_ui_elem_item(e_item, el, lay)
                e_item.setExpanded(self._expand_overrides.get(id(el), True))
                items[el.name] = e_item
            root_item.setExpanded(self._expand_overrides.get(id(lay), True))

    def _update_ui_elem_item(self, item: QTreeWidgetItem, el, layout):
        """Peuple la ligne d'un élément UI : icône de type (forme), nom éditable,
        et — signal central — couleur selon la RÉFÉRENÇABILITÉ Lua (clair =
        nommable dans un script, grisé = authoring-only)."""
        kind = getattr(el, "kind", KIND_TEXT)
        item.setData(0, _ROLE_TYPE, T_UI_ELEM)
        item.setData(0, _ROLE_OBJ, el)
        item.setData(0, _ROLE_PATH, layout)     # la layout porteuse (pour le bus/cmd)
        item.setIcon(0, _ico(_UI_ELEM_ICON.get(kind, "ui_text"), COLOR_UI))
        item.setText(0, el.name)
        item.setFont(0, ui_font(T.LG))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        handle = _lua_handle(T_UI_ELEM, el)
        if handle:
            item.setForeground(0, QColor(_TEXT))
            item.setToolTip(0, label("scttree.elem_ref",
                                     type=_UI_ELEM_LABEL.get(kind, kind), handle=handle))
        else:
            item.setForeground(0, QColor(_DIM))
            item.setToolTip(0, label("scttree.elem_authoring",
                                     type=_UI_ELEM_LABEL.get(kind, kind)))

    def _update_actor_item(self, item: QTreeWidgetItem, actor: Actor):
        handle = _lua_handle(T_ACTOR, actor)
        if actor.prefab_name:
            item.setIcon(0, _ico("prefab", COLOR_DEFAULT))
            item.setToolTip(0, label("scttree.actor_prefab_tip",
                                     name=actor.prefab_name, handle=handle))
        else:
            item.setIcon(0, _ico("actor", COLOR_DEFAULT))
            item.setToolTip(0, label("scttree.ref_tip", handle=handle))
        item.setText(0, actor.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setForeground(0, QColor(_TEXT))

    def _update_camera_item(self, item: QTreeWidgetItem, camera):
        handle = _lua_handle(T_CAMERA, camera)
        item.setIcon(0, _ico("camera", COLOR_DEFAULT))
        item.setToolTip(0, label("scttree.ref_tip", handle=handle))
        item.setText(0, camera.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setForeground(0, QColor(_TEXT))

    def highlight_actor(self, actor: Actor):
        self._highlight(T_ACTOR, actor)

    def highlight_camera(self, camera):
        self._highlight(T_CAMERA, camera)

    def highlight_ui_element(self, element):
        self._highlight(T_UI_ELEM, element)

    def _highlight(self, node_type: str, obj):
        if QTreeWidgetItemIterator is None:
            return
        self.blockSignals(True)
        self.clearSelection()
        it = QTreeWidgetItemIterator(self)
        while it.value():
            node = it.value()
            if node.data(0, _ROLE_TYPE) == node_type and node.data(0, _ROLE_OBJ) is obj:
                node.setSelected(True)
                self.scrollToItem(node)
                break
            it += 1
        self.blockSignals(False)

    # ── Clic ──────────────────────────────────────────────────────

    def _on_click(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_ACTOR:
            get_bus().select(item.data(0, _ROLE_OBJ))
        elif typ == T_CAMERA:
            get_bus().select(CameraSelection(self._scene, item.data(0, _ROLE_OBJ)))
        elif typ == T_UI_ELEM:
            get_bus().select(UIElementSelection(item.data(0, _ROLE_PATH),
                                                item.data(0, _ROLE_OBJ)))
        elif typ == T_UI_LAYOUT:
            # Le nœud « Interface » porte l'ancrage + la cible de son sous-arbre
            # (v0.25) : son propre inspecteur, dans le contexte de la scène.
            get_bus().select(UILayoutSelection(item.data(0, _ROLE_OBJ), self._scene))

    # ── Drag & drop : acteurs OU éléments d'UI ────────────────────

    def dropEvent(self, event):
        dragged = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if dragged is None:
            event.ignore()
            return
        dtype = dragged.data(0, _ROLE_TYPE)

        if dtype == T_UI_ELEM:
            indicator = self.dropIndicatorPosition()
            event.accept()
            self._handle_ui_drop(dragged, target, indicator)
            return

        if dtype == T_ACTOR:
            # Un acteur ne se pose SUR un autre item que si c'est un acteur,
            # jamais sur la branche « Interface » (pas de nesting) — mais un
            # lâché hors de tout item (case vide) est accepté : c'est ce qui
            # retire le parent (l'acteur remonte à la racine).
            Pos = QAbstractItemView.DropIndicatorPosition
            if target is not None and target.data(0, _ROLE_TYPE) != T_ACTOR:
                event.ignore()
                return
            if target is not None and self.dropIndicatorPosition() == Pos.OnItem:
                # Lâché SUR un acteur = reparentage (ROADMAP v0.23), pas un
                # réordonnancement — Qt ne doit pas y toucher.
                event.accept()
                self._reparent_actor(dragged.data(0, _ROLE_OBJ), target.data(0, _ROLE_OBJ))
                return
            if target is None:
                # Lâché hors de tout item : Qt n'a pas de position où
                # replacer visuellement l'item (rien à indiquer), donc on le
                # fait nous-même plutôt que de laisser passer à super().
                event.accept()
                self._unparent_actor(dragged.data(0, _ROLE_OBJ))
                return
            super().dropEvent(event)   # Qt réordonne/redéplace visuellement
            if self._scene is None or QTreeWidgetItemIterator is None:
                return
            # DFS sur l'arbre ENTIER, pas seulement le premier niveau : un
            # acteur posé (Actor.parent) apparaît en enfant, et un tour
            # limité au premier niveau le ferait disparaître de
            # `scene.actors` — perdu, pas seulement mal trié. On relit aussi
            # LE PARENT de chaque acteur depuis sa position résultante : Qt
            # autorise de déposer un acteur imbriqué à côté d'acteurs racine
            # (indicateur Au-dessus/En dessous plutôt que Sur), et c'est
            # cette repose qui doit lui retirer son parent — pas seulement un
            # lâché en case vide.
            new_order = []
            reparented = False
            it = QTreeWidgetItemIterator(self)
            while it.value():
                node = it.value()
                if node.data(0, _ROLE_TYPE) == T_ACTOR:
                    actor = node.data(0, _ROLE_OBJ)
                    new_order.append(actor)
                    host = node.parent()
                    new_parent = (
                        host.data(0, _ROLE_OBJ).name
                        if host is not None and host.data(0, _ROLE_TYPE) == T_ACTOR
                        else None)
                    if actor.parent != new_parent:
                        actor.parent = new_parent
                        reparented = True
                it += 1
            self._scene.actors[:] = new_order
            get_dispatcher().save_scene()
            if reparented:
                get_dispatcher()._emit("actors_list_changed")
            self._panel.refresh()
            return

        event.ignore()

    def _reparent_actor(self, actor: Actor, new_parent: Actor):
        """Pose `actor` sous `new_parent` (Actor.parent, ROADMAP v0.23).

        Même garde anti-cycle que l'inspecteur (`_descendants` dans
        actor_inspector.py) : se poser sur soi-même ou sur son propre
        sous-arbre ferait un cycle que le Build refuserait de toute façon."""
        if self._scene is None or actor is new_parent:
            return
        from core.models.scene import actor_descendant_names
        if new_parent.name in actor_descendant_names(self._scene.actors, actor.name):
            return
        if actor.parent == new_parent.name:
            return
        actor.parent = new_parent.name
        get_dispatcher().save_scene()
        get_dispatcher()._emit("actors_list_changed")

    def _unparent_actor(self, actor: Actor):
        """Retire le parent (Actor.parent = None) — l'acteur remonte à la
        racine de l'arbre, en dernière position parmi les acteurs racine."""
        if self._scene is None or actor.parent is None:
            return
        actor.parent = None
        # En dernière position racine : sortir de sous un parent n'a pas de
        # place naturelle ailleurs dans l'ordre, et la fin évite de le
        # glisser devant des acteurs qui n'ont pas bougé.
        actors = self._scene.actors
        actors.append(actors.pop(actors.index(actor)))
        get_dispatcher().save_scene()
        get_dispatcher()._emit("actors_list_changed")

    def _actor_pos(self, name: str):
        """(x, y) de l'acteur nommé, ou None — même contrat que
        `SceneRegionItem._actor_pos` dans scene_canvas.py : passé aux helpers
        d'ancrage du modèle, qui eux ne connaissent pas la scène."""
        for a in getattr(self._scene, "actors", []):
            if a.name == name:
                return (a.x, a.y)
        return None

    def _handle_ui_drop(self, dragged_item, target_item, indicator):
        """Reparente + repositionne un élément d'UI d'après la cible et
        l'indicateur (ON = dernier enfant ; AU-DESSUS = avant la cible ;
        EN DESSOUS = après). Refuse de sortir de la mise en page d'origine."""
        Pos = QAbstractItemView.DropIndicatorPosition
        dragged = dragged_item.data(0, _ROLE_OBJ)
        layout = dragged_item.data(0, _ROLE_PATH)
        if target_item is None or layout is None:
            return
        ttype = target_item.data(0, _ROLE_TYPE)
        if ttype == T_UI_LAYOUT:
            if target_item.data(0, _ROLE_OBJ) is not layout:
                return                         # autre mise en page → refus
            new_parent, before = "", None      # lâché sur « Interface » = racine
        elif ttype == T_UI_ELEM:
            target = target_item.data(0, _ROLE_OBJ)
            if target is dragged or target_item.data(0, _ROLE_PATH) is not layout:
                return
            if indicator == Pos.OnItem:
                new_parent, before = target.name, None
            else:
                new_parent = layout._parent_key(target)
                sibs = [s.name for s in layout._siblings(new_parent)
                        if s.name != dragged.name]
                if target.name in sibs and indicator == Pos.AboveItem:
                    before = target.name
                elif target.name in sibs:      # BelowItem → devant le suivant
                    ti = sibs.index(target.name)
                    before = sibs[ti + 1] if ti + 1 < len(sibs) else None
                else:
                    before = None
        else:
            return

        def mutate(name=dragged.name, parent=new_parent, before=before):
            # `place_child` rattache et réordonne, mais ne touche pas x/y —
            # ce sont des coordonnées RELATIVES AU PARENT (cf.
            # `UILayout.absolute_origin`). Un changement de parent doit donc
            # les recalculer, sous peine de garder les anciennes valeurs comme
            # offset dans le NOUVEAU repère : un texte posé aux coordonnées
            # écran de son panel, glissé dans ce panel, se retrouverait décalé
            # de sa propre origine (position doublée), invisible ou hors-cadre.
            # On préserve la position ÉCRAN — c'est ce que l'œil voit bouger,
            # pas les nombres.
            el = layout.get(name)
            ax = ay = None
            if el is not None and el.parent != parent:
                ax, ay, _ = layout.absolute_origin(el, self._actor_pos)
            if not layout.place_child(name, parent, before):
                return
            if ax is not None:
                px, py = layout.parent_origin(el, self._actor_pos)
                el.x, el.y = ax - px, ay - py

        cmd = UILayoutOrderCmd(layout, mutate, f"Déplacer {dragged.name}",
                               persist_fn=self._panel._after_ui_change)
        QTimer.singleShot(0, lambda: get_history().push(cmd))

    # ── Menu contextuel ───────────────────────────────────────────

    def _ctx_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        typ = item.data(0, _ROLE_TYPE)
        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))

        if typ == T_ACTOR:
            actor: Actor = item.data(0, _ROLE_OBJ)
            scene = self._scene
            menu.addAction(label("scttree.move_top")).triggered.connect(
                lambda: self._move_actor(scene, actor, "top"))
            menu.addAction(label("scttree.move_up")).triggered.connect(
                lambda: self._move_actor(scene, actor, "up"))
            menu.addAction(label("scttree.move_down")).triggered.connect(
                lambda: self._move_actor(scene, actor, "down"))
            menu.addAction(label("scttree.move_bottom")).triggered.connect(
                lambda: self._move_actor(scene, actor, "bottom"))
            menu.addSeparator()
            self.add_rename_action(menu, item, label("scttree.rename_actor"))
            menu.addAction(label("scttree.delete_actor")).triggered.connect(
                lambda: get_dispatcher().delete_actor(actor))

        elif typ == T_CAMERA:
            camera = item.data(0, _ROLE_OBJ)
            self.add_rename_action(menu, item, label("scttree.rename_camera"))
            menu.addAction(label("scttree.delete_camera")).triggered.connect(
                lambda: get_dispatcher().delete_camera(camera))

        elif typ == T_UI_LAYOUT:
            layout = item.data(0, _ROLE_OBJ)
            add = menu.addMenu(label("scttree.add_widget"))
            add.setFont(QFont(T.UI, T.MD))
            for kind, lbl_key in _UI_ELEM_ADD:
                act = add.addAction(_ico(_UI_ELEM_ICON[kind], COLOR_UI), label(lbl_key))
                act.triggered.connect(
                    lambda _, k=kind, lay=layout: self._create_ui_elem(lay, k, ""))
            menu.addSeparator()
            # Un nœud partagé ne perd que sa référence dans CETTE scène ; le seul
            # à le référencer emporte l'asset avec lui. Le libellé le dit, pour ne
            # pas laisser croire qu'on détruit une interface utilisée ailleurs.
            proj = self._panel._project
            users = proj.ui_layout_users(layout.name) if proj else []
            shared = len(users) > 1
            menu.addAction(label("scttree.remove_from_scene") if shared
                           else label("scttree.delete_interface")).triggered.connect(
                lambda _, lay=layout, sh=shared: self._delete_interface(lay, sh))

        elif typ == T_UI_ELEM:
            el = item.data(0, _ROLE_OBJ)
            layout = item.data(0, _ROLE_PATH)
            sibs = [s.name for s in layout._siblings(layout._parent_key(el))]
            i, n = sibs.index(el.name), len(sibs)
            for lbl_key, direction, on in (
                ("scttree.move_top", "top", i > 0),
                ("scttree.move_up", "up", i > 0),
                ("scttree.move_down", "down", i < n - 1),
                ("scttree.move_bottom", "bottom", i < n - 1),
            ):
                a = menu.addAction(label(lbl_key))
                a.setEnabled(on)
                a.triggered.connect(
                    lambda _, d=direction, e=el, lay=layout: self._move_ui_elem(lay, e, d))
            accepted = getattr(el, "can_contain", ())
            if accepted:
                menu.addSeparator()
                sub = menu.addMenu(label("scttree.add_child"))
                sub.setFont(QFont(T.UI, T.MD))
                # Ce que CE parent accueille : une liste ne prend que des
                # textes, ses enfants étant ses rangées. Offrir une image ici
                # ferait poser un élément que le build ignore ensuite.
                for kind, lbl_key in (kl for kl in _UI_ELEM_ADD if kl[0] in accepted):
                    act = sub.addAction(_ico(_UI_ELEM_ICON[kind], COLOR_UI), label(lbl_key))
                    act.triggered.connect(
                        lambda _, k=kind, lay=layout, p=el.name: self._create_ui_elem(lay, k, p))
            menu.addSeparator()
            self.add_rename_action(menu, item, label("scttree.rename"))
            menu.addAction(label("common.delete")).triggered.connect(
                lambda _, e=el, lay=layout: self._delete_ui_elem(lay, e))

        menu.exec(self.viewport().mapToGlobal(pos))

    # ── Éléments d'UI : création / réordonnancement / suppression ─
    def _create_ui_elem(self, layout, kind: str, parent_name: str):
        proj = self._panel._project
        if proj is None:
            return
        from core.models.ui_region import (
            UIContainer, UIList, UIText, UIImage, unique_element_name)
        taken = set(layout.element_names()) | set(proj.ui_element_names())
        if kind == KIND_CONTAINER:
            el = UIContainer(name=unique_element_name(taken, "container"),
                         parent=parent_name, x=8, y=8, w=96, h=48)
        elif kind == KIND_LIST:
            el = UIList(name=unique_element_name(taken, "list"),
                        parent=parent_name, x=8, y=8, w=96, h=48)
        elif kind == KIND_IMAGE:
            el = UIImage(name=unique_element_name(taken, "image"),
                         parent=parent_name, x=8, y=8, w=16, h=16)
        else:
            el = UIText(name=unique_element_name(taken, "text"),
                        parent=parent_name, x=8, y=8, w=80, h=16)
        get_history().push(AddListItemCmd(
            layout.elements, el, persist_fn=self._panel._after_ui_change,
            label=f"New {_UI_ELEM_LABEL.get(kind, kind)} {el.name}"))
        get_bus().select(UIElementSelection(layout, el))

    def _move_ui_elem(self, layout, element, direction: str):
        def mutate(name=element.name, d=direction):
            layout.move_sibling(name, d)
        get_history().push(UILayoutOrderCmd(
            layout, mutate, f"Reorder {element.name}",
            persist_fn=self._panel._after_ui_change))

    def _delete_ui_elem(self, layout, element):
        get_history().push(RemoveListItemCmd(
            layout.elements, element, persist_fn=self._panel._after_ui_change,
            label=f"Delete {element.name}"))
        get_bus().clear()

    def _delete_interface(self, layout, shared: bool):
        """Retire un nœud `Interface` de la scène. Partagé → seule la référence
        de cette scène part ; sinon l'asset aussi (sans quoi ses `REGION_*`/
        `IMAGE_*` resteraient dans les tables — `all_regions` itère TOUT le
        projet, pas les seuls nœuds référencés)."""
        proj = self._panel._project
        if proj is None or self._scene is None:
            return
        get_history().push(DeleteInterfaceCmd(
            proj.ui_layouts, layout, self._scene.ui_layouts,
            delete_asset=not shared,
            persist_fn=self._panel._after_ui_change))
        get_bus().clear()

    # ── Renommage / réordonnancement d'un acteur ───────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int):
        typ = item.data(0, _ROLE_TYPE)
        if typ == T_ACTOR:
            self._commit_rename_actor(item)
        elif typ == T_CAMERA:
            self._commit_rename_camera(item)
        elif typ == T_UI_ELEM:
            self._commit_rename_ui_elem(item)

    def _commit_rename_camera(self, item: QTreeWidgetItem):
        camera = item.data(0, _ROLE_OBJ)
        new_name = item.text(0).strip()
        proj = self._panel._project
        if not proj or not self._scene or not new_name or new_name == camera.name:
            self.blockSignals(True)
            self._update_camera_item(item, camera)
            self.blockSignals(False)
            return
        # `rename_camera` émet "renamed" → "project_tree_changed" en cascade
        # SYNCHRONE : l'arbre est déjà reconstruit à ce point, `item` déjà
        # détruit — ne plus y toucher après cet appel (même mise en garde que
        # `_commit_rename_actor`). Une collision de nom est refusée en
        # silence par `Project.rename_camera` : le rebuild qui suit remontre
        # alors l'ancien nom, sans message dédié.
        proj.rename_camera(self._scene, camera, new_name)
        get_dispatcher()._emit("cameras_list_changed")

    def _commit_rename_ui_elem(self, item: QTreeWidgetItem):
        el = item.data(0, _ROLE_OBJ)
        layout = item.data(0, _ROLE_PATH)
        proj = self._panel._project
        new_name = item.text(0).strip()
        if not proj or not new_name or new_name == el.name:
            self.blockSignals(True)
            item.setText(0, el.name)
            self.blockSignals(False)
            return
        # `rename_ui_element` émet "renamed", relayé SYNCHRONEMENT en
        # "project_tree_changed" par le dispatcher : ce panneau a déjà
        # reconstruit l'arbre (avec le nom, possiblement dédupliqué, à jour)
        # avant que cet appel ne rende la main. `item` est un QTreeWidgetItem
        # que cette reconstruction a détruit — ne plus y toucher après.
        proj.rename_ui_element(layout, el, new_name)
        self._panel._after_ui_change()

    def _commit_rename_actor(self, item: QTreeWidgetItem):
        actor: Actor = item.data(0, _ROLE_OBJ)
        new_name = item.text(0).strip()
        proj = self._panel._project
        if not new_name or new_name == actor.name:
            self.blockSignals(True)
            self._update_actor_item(item, actor)
            self.blockSignals(False)
            return
        if proj:
            # Émet "renamed" → "project_tree_changed" en cascade SYNCHRONE :
            # l'arbre est déjà reconstruit à ce point, `item` déjà détruit —
            # ne plus y toucher après cet appel (même mise en garde que
            # ci-dessus et que `_commit_rename_scene` dans assets_finder_panel).
            proj.rename_actor(actor, new_name, scene=self._scene)
        else:
            actor.name = new_name
            self.blockSignals(True)
            self._update_actor_item(item, actor)
            self.blockSignals(False)
        get_dispatcher()._emit("actors_list_changed")

    def _move_actor(self, scene: Scene, actor: Actor, direction: str):
        actors = scene.actors
        idx = actors.index(actor)
        if direction == "top":
            actors.insert(0, actors.pop(idx))
        elif direction == "up" and idx > 0:
            actors[idx], actors[idx - 1] = actors[idx - 1], actors[idx]
        elif direction == "down" and idx < len(actors) - 1:
            actors[idx], actors[idx + 1] = actors[idx + 1], actors[idx]
        elif direction == "bottom":
            actors.append(actors.pop(idx))
        get_dispatcher().save_scene()
        self._panel.refresh()


# ──────────────────────────────────────────────────────────────────
#  Panneau principal
# ──────────────────────────────────────────────────────────────────

class SceneTreePanel(QWidget):
    # Un élément d'UI a été créé / déplacé / renommé / supprimé depuis
    # l'arbre : le scene_editor sauve et redessine le canvas (câblé dans
    # window.py) — même contrat que l'ancien AssetsFinderPanel.
    ui_layout_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Project | None = None
        self._scene: Scene | None = None
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{_BG};")
        self._setup_ui()
        get_bus().changed.connect(self.on_selection)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Bandeau nom de la scène active + « + » (ajouter un acteur) ──
        hdr = QFrame()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(f"background:{_HEADER}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(S.GUTTER, 0, S.MD, 0)
        hl.setSpacing(S.SM)
        self._scene_lbl = QLabel(label("scttree.no_scene"))
        self._scene_lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._scene_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        hl.addWidget(self._scene_lbl, 1)
        # Menu plutôt qu'un clic direct : deux natures d'objet se créent
        # depuis ce bouton, toutes deux possédées par la scène — un acteur et
        # une caméra (cf. command_dispatcher.add_camera).
        self._btn_add = W.btn_add(label("scttree.add"))
        add_menu = QMenu(self._btn_add)
        add_menu.setFont(QFont(T.UI, T.MD))
        add_menu.addAction(_ico("actor", COLOR_DEFAULT), label("common.actor")).triggered.connect(self._add_actor)
        add_menu.addAction(_ico("camera", COLOR_DEFAULT), label("common.camera")).triggered.connect(self._add_camera)
        add_menu.addAction(_ico("ui_layout", COLOR_UI), label("common.interface")).triggered.connect(self._add_interface)
        self._btn_add.setMenu(add_menu)
        self._btn_add.setPopupMode(self._btn_add.ToolButtonPopupMode.InstantPopup)
        hl.addWidget(self._btn_add)
        layout.addWidget(hdr)

        # ── Bandeau "finder" (identité du panneau) ────────────────
        layout.addWidget(W.finder_bar(label("scttree.finder_bar")))

        # ── Corps : arbre, ou état vide si aucune scène active ────
        self._tree = _ActiveSceneTree(self)

        self._empty = QLabel(label("scttree.no_scene"))
        self._empty.setFont(QFont(T.UI, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:{S.CONTENT}px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG}; border:none;")
        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, S.SM, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._tree)
        cl.addWidget(self._empty)
        cl.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self.set_active_scene(project.active_scene)

    def set_active_scene(self, scene: Scene | None):
        self._scene = scene
        self.refresh()

    def refresh(self):
        self._scene_lbl.setText(self._scene.name if self._scene else label("scttree.no_scene"))
        self._btn_add.setEnabled(self._scene is not None)
        self._tree.populate(self._project, self._scene)
        has_scene = self._scene is not None
        self._tree.setVisible(has_scene)
        self._empty.setVisible(not has_scene)

    # ── Sélection bus ─────────────────────────────────────────────

    def on_selection(self, obj):
        if isinstance(obj, Actor):
            self._tree.highlight_actor(obj)
        elif isinstance(obj, CameraSelection):
            if obj.camera is not None:
                self._tree.highlight_camera(obj.camera)
        elif isinstance(obj, UIElementSelection):
            self._tree.highlight_ui_element(obj.element)

    def _after_ui_change(self):
        """Après une mutation d'UI depuis l'arbre (créer/déplacer/renommer/
        supprimer) : prévenir le scene_editor (sauve + redessine le canvas),
        reconstruire l'arbre, puis re-cibler la sélection courante du bus —
        `populate` reconstruit des items neufs, mais les objets modèle
        persistent, donc on retrouve l'élément par identité."""
        self.ui_layout_changed.emit()
        self.refresh()
        cur = get_bus().current
        if isinstance(cur, UIElementSelection):
            self._tree.highlight_ui_element(cur.element)

    # ── Ajout d'un acteur (inline, pas de dialogue — cf. Scenes/Prefabs) ──

    def _add_actor(self):
        if not self._project or not self._scene:
            return
        name = unique_name("Actor", {a.name for a in self._scene.actors})
        get_dispatcher().add_actor(name)
        self.refresh()
        self._begin_rename_actor(name)

    def _begin_rename_actor(self, name: str):
        self._begin_rename(T_ACTOR, name)

    # ── Ajout d'un nœud « Interface » (nouvel asset, comme un acteur) ──

    def _add_interface(self):
        """Crée un nouveau nœud `Interface` (asset `UILayout`) et le pose dans la
        scène. Comme un acteur : un nouvel asset, pas une copie d'un existant. Le
        nom se change ensuite dans l'en-tête (l'inspecteur du nœud), pas en place
        dans l'arbre — la ligne y affiche « Interface », jamais le nom du .json."""
        if not self._project or not self._scene:
            return
        from core.models.ui_region import UILayout
        base, name, n = (self._scene.name or "ui"), (self._scene.name or "ui"), 2
        while self._project.get_ui_layout(name) is not None:
            name = f"{base}_{n:02d}"
            n += 1
        lay = UILayout(name=name)
        self._project.ui_layouts.append(lay)
        self._scene.ui_layouts.append(name)
        get_dispatcher().save_all()      # persiste l'asset neuf ET la scène
        self._after_ui_change()
        get_bus().select(UILayoutSelection(lay, self._scene))

    # ── Ajout d'une caméra (inline — même geste que l'acteur) ─────

    def _add_camera(self):
        if not self._project or not self._scene:
            return
        cam = get_dispatcher().add_camera()
        if cam is None:
            return
        self.refresh()
        self._begin_rename(T_CAMERA, cam.name)

    def _begin_rename(self, node_type: str, name: str):
        if QTreeWidgetItemIterator is None:
            return
        def go():
            it = QTreeWidgetItemIterator(self._tree)
            while it.value():
                item = it.value()
                if item.data(0, _ROLE_TYPE) == node_type and item.text(0) == name:
                    self._tree.setCurrentItem(item)
                    self._tree.editItem(item, 0)
                    return
                it += 1
        QTimer.singleShot(0, go)
