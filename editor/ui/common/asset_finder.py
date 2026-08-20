"""
ui/common/asset_finder.py — LE panneau qui liste les assets d'un projet.

Un seul composant pour toutes les familles (sprites, scènes, prefabs, fonds,
scripts, polices, palettes, sfx, musiques, tables). Les écrans ne décrivent que
ce qui diffère vraiment — où sont les assets, comment on les renomme, comment on
les supprime — via `AssetKind` ; le peuplement, les sous-sections repliables, le
filtre, le renommage en place, le menu contextuel et la sélection sont écrits
ici, une fois.

## L'arbre de nœuds

La source d'une famille n'est pas une liste mais un ARBRE (`AssetNode` : un
dossier, ou un asset). C'est la couture du chantier, et elle est délibérée :
l'utilisateur pourra ranger ses assets dans ses propres dossiers. Aujourd'hui
les scripts rendent déjà un vrai arbre (leur dossier est imbriqué sur disque) et
les familles adossées à un `ResourceStore` n'en rendent qu'un seul niveau —
`ResourceStore` est plat par construction. Le jour où il saura les sous-dossiers,
`store_nodes` rendra un arbre et CE fichier ne bouge pas.

## La source de vérité

`AssetKind.nodes` lit la source de vérité de sa famille, jamais une copie :
- les neuf familles adossées à un `ResourceStore` lisent la COLLECTION EN
  MÉMOIRE (`project.sprites`…), pas le disque — sinon un asset renommé mais pas
  encore sauvé, ou `soft_delete`é mais dont le JSON traîne jusqu'à la fermeture,
  apparaîtrait à côté de la plaque ;
- les scripts lisent le DISQUE, parce que c'est leur vérité à eux : ce sont des
  fichiers `.lua`, sans modèle `Resource` qui les tiendrait en mémoire.

Cf. docs/asset-finder.md pour l'état des lieux et la décision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QMenu,
    QAbstractItemView, QMessageBox, QSizePolicy, QScrollArea,
)
from PyQt6.QtGui import QFont, QColor, QDrag
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QMimeData, QByteArray

from ui.common.theme import C, T, S, QSS, ui_font
from ui.common.widgets import W, FinderSection
from ui.common.icons import get as _ico, COLOR_DEFAULT, COLOR_FOLDER

_ROLE_OBJ = Qt.ItemDataRole.UserRole


# ──────────────────────────────────────────────────────────────────
#  Le nœud
# ──────────────────────────────────────────────────────────────────

@dataclass
class AssetNode:
    """Un nœud de l'arbre d'une famille : un dossier, ou un asset.

    `obj` est l'asset lui-même — un `Resource` pour les familles adossées à un
    `ResourceStore`, un `Path` pour les scripts. Il vaut None pour un dossier :
    c'est ce qui distingue les deux, plutôt qu'un drapeau à tenir d'accord avec
    le reste."""
    name: str
    obj: Any = None
    children: list["AssetNode"] = field(default_factory=list)

    @property
    def is_folder(self) -> bool:
        return self.obj is None


# ──────────────────────────────────────────────────────────────────
#  La description d'une famille
# ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AssetKind:
    """Ce qu'un écran déclare pour qu'une famille s'affiche dans un finder.

    Tout est optionnel sauf `label`, `icon` et `nodes` : une famille sans
    `rename` n'est simplement pas renommable depuis le finder, et son entrée de
    menu n'apparaît pas. On ne grise pas une action impossible, on ne la propose
    pas — l'éditeur rend le matériel fidèlement, il ne le commente pas.
    """

    label: str                                   # titre de section — « Tables »
    icon: str                                    # clé ui/common/icons.py
    nodes: Callable[[Any], list[AssetNode]]      # projet -> arbre (LA vérité)

    # Icône neutre par défaut : dans un finder, un type se lit à la FORME de
    # l'icône, pas à sa couleur (cf. project_theme_gba_redesign). `icon_of`
    # n'existe que pour les familles dont l'icône dépend de l'asset lui-même —
    # l'extension d'un script, les couleurs d'une palette.
    color: str = COLOR_DEFAULT
    icon_of: Optional[Callable[[Any], Any]] = None
    # Affiché à la place de la liste quand la famille est vide. Dit d'où vient
    # un asset quand ce n'est pas d'un « + » — une police naît d'un PNG déposé
    # dans assets/fonts/, pas d'un bouton.
    empty_text: str = ""
    # Suffixe affiché après le nom, jamais édité — « (12 × 3) », « (16) ».
    # Le nom NU reste l'identité : c'est lui qu'on édite et qu'on cherche.
    suffix_of: Optional[Callable[[Any], str]] = None
    tooltip_of: Optional[Callable[[Any], str]] = None

    # (projet, asset, nouveau_nom) -> nom RÉELLEMENT appliqué ("" si refusé).
    rename: Optional[Callable[[Any, Any, str], str]] = None
    # (projet, asset) -> None. Doit pousser dans l'historique (Ctrl+Z).
    delete: Optional[Callable[[Any, Any], None]] = None
    delete_prompt: Optional[Callable[[Any], str]] = None
    # Le « + » de la section. Une famille sait se créer elle-même (`add`), ou
    # délègue à l'écran (`add_tooltip` seul -> signal `add_requested`) quand
    # naître demande plus que le projet — importer un PNG, par exemple.
    # Ni l'un ni l'autre : pas de bouton.
    add: Optional[Callable[[Any], Any]] = None
    add_tooltip: str = ""
    # Entrées de menu propres à la famille : [(libellé, (projet, asset) -> None)]
    actions: tuple = ()

    # Glisser-déposer vers le canvas : (type MIME, asset -> charge utile texte).
    # Une famille sans `mime` n'est pas glissable.
    mime: Optional[tuple] = None


# ──────────────────────────────────────────────────────────────────
#  Constructeurs d'arbres — les deux sources de vérité qui existent
# ──────────────────────────────────────────────────────────────────

def store_nodes(attr: str,
                group_by: Optional[Callable[[Any], str]] = None,
                where: Optional[Callable[[Any], bool]] = None,
                collapse_singletons: bool = False,
                ) -> Callable[[Any], list[AssetNode]]:
    """Arbre d'une famille adossée à un `ResourceStore` (`project.<attr>`).

    Lit la collection EN MÉMOIRE, qui est la source de vérité (cf. en-tête).
    `ResourceStore` étant plat, l'arbre n'a aujourd'hui qu'un seul niveau —
    sauf si `group_by` donne un axe de regroupement déjà porté par le modèle
    (le `kind` d'un fond : scene / ui / animated).

    `where` restreint à une partie du store, pour les écrans qui donnent à
    chaque sous-famille sa propre section — le Background Editor a un bouton
    d'import par `kind`, ce qu'une section unique ne saurait pas offrir.

    `collapse_singletons` remonte au premier niveau un groupe qui n'a qu'un
    membre. Réservé aux regroupements DEVINÉS (les sprites se rangent par
    préfixe de nom) : un dossier pour un seul asset y est du bruit, alors qu'un
    vrai dossier — celui que l'utilisateur a créé — existe même vide.

    Le jour où `ResourceStore` saura les sous-dossiers, c'est ICI que l'arbre
    prendra sa profondeur ; le panneau, lui, sait déjà l'afficher."""
    def build(project) -> list[AssetNode]:
        items = list(getattr(project, attr, []) or [])
        if where is not None:
            items = [it for it in items if where(it)]
        if group_by is None:
            return [AssetNode(name=it.name, obj=it) for it in items]
        folders: dict[str, AssetNode] = {}
        roots: list[AssetNode] = []
        for it in items:
            group = group_by(it) or ""
            leaf = AssetNode(name=it.name, obj=it)
            if not group:
                roots.append(leaf)
                continue
            folder = folders.get(group)
            if folder is None:
                folder = folders[group] = AssetNode(name=group)
                roots.append(folder)
            folder.children.append(leaf)
        if collapse_singletons:
            roots = [n.children[0] if n.is_folder and len(n.children) == 1 else n
                     for n in roots]
        return roots
    return build


def dir_nodes(attr: str, suffixes: tuple[str, ...]
              ) -> Callable[[Any], list[AssetNode]]:
    """Arbre d'une famille dont la vérité est le DISQUE — les scripts.

    Parcourt `project.<attr>` récursivement : les dossiers deviennent des nœuds
    dossier, les fichiers dont l'extension figure dans `suffixes` des feuilles
    portant leur `Path`."""
    def walk(directory: Path) -> list[AssetNode]:
        try:
            entries = sorted(directory.iterdir(),
                             key=lambda p: (not p.is_dir(), p.name.lower()))
        except (OSError, PermissionError):
            return []
        out: list[AssetNode] = []
        for entry in entries:
            if entry.is_dir():
                out.append(AssetNode(name=entry.name, children=walk(entry)))
            elif entry.suffix in suffixes:
                out.append(AssetNode(name=entry.name, obj=entry))
        return out

    def build(project) -> list[AssetNode]:
        directory = getattr(project, attr, None)
        if not directory or not Path(directory).exists():
            return []
        return walk(Path(directory))
    return build


# ──────────────────────────────────────────────────────────────────
#  L'arbre Qt d'une famille
# ──────────────────────────────────────────────────────────────────

class _KindTree(QTreeWidget):
    """L'arbre d'UNE famille. Ne connaît que son `AssetKind` et son panneau."""

    def __init__(self, panel: "AssetFinder", kind: AssetKind):
        super().__init__()
        self._panel = panel
        self._kind = kind
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(14, 14))
        self.setStyleSheet(QSS.tree_widget)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Renommage en place, jamais de dialogue modal : clic sur un item déjà
        # sélectionné, ou F2. Même geste que partout ailleurs dans l'éditeur.
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        # Hauteur RÉGLÉE SUR LE CONTENU (cf. `_fit`), jamais extensible : c'est
        # ce qui ferre les sections en haut du panneau. Une liste extensible se
        # partagerait la colonne avec ses voisines, et une section courte
        # flotterait au milieu du vide qu'on lui a donné.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        if kind.mime is not None:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.currentItemChanged.connect(self._on_current_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.customContextMenuRequested.connect(self._on_ctx_menu)
        self.itemChanged.connect(self._on_item_changed)
        self.model().rowsInserted.connect(self._fit)
        self.model().rowsRemoved.connect(self._fit)
        self.itemExpanded.connect(self._fit)
        self.itemCollapsed.connect(self._fit)

    # ── Peuplement ────────────────────────────────────────────────

    def populate(self, project):
        self.blockSignals(True)
        self.clear()
        if project is not None:
            self._fill(self.invisibleRootItem(), self._kind.nodes(project))
        self.blockSignals(False)
        self._fit()
        return self.topLevelItemCount() > 0

    def _fill(self, parent, nodes: list[AssetNode]):
        for node in nodes:
            item = QTreeWidgetItem(parent)
            item.setFont(0, ui_font(T.LG))
            if node.is_folder:
                item.setIcon(0, _ico("folder", COLOR_FOLDER))
                item.setText(0, node.name)
                item.setForeground(0, QColor(C.TEXT_DIM))
                self._fill(item, node.children)
                item.setExpanded(True)
            else:
                item.setIcon(0, self._kind.icon_of(node.obj) if self._kind.icon_of
                                else _ico(self._kind.icon, self._kind.color))
                item.setData(0, _ROLE_OBJ, node.obj)
                item.setForeground(0, QColor(C.TEXT_NORM))
                self._set_label(item, node.obj)
                if self._kind.rename is not None:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                if self._kind.tooltip_of is not None:
                    item.setToolTip(0, self._kind.tooltip_of(node.obj))
                if node.children:
                    self._fill(item, node.children)

    def _set_label(self, item: QTreeWidgetItem, obj):
        """Nom + suffixe informatif. Le suffixe n'est QUE de l'affichage : le nom
        nu vit dans l'objet, et c'est lui que l'édition en place reprend."""
        name = self._name_of(obj)
        suffix = self._kind.suffix_of(obj) if self._kind.suffix_of else ""
        item.setText(0, f"{name}  {suffix}" if suffix else name)

    @staticmethod
    def _name_of(obj) -> str:
        return obj.name if isinstance(obj, Path) else getattr(obj, "name", str(obj))

    def _fit(self):
        rows, stack = 0, [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            rows += 1
            if it.isExpanded():
                stack.extend(it.child(n) for n in range(it.childCount()))
        # S.ROW = hauteur d'une ligne dans QSS.tree_widget : les deux doivent
        # rester d'accord, sinon l'arbre se coupe ou traîne du vide.
        self.setFixedHeight(max(rows * S.ROW, 4))

    # ── Sélection ─────────────────────────────────────────────────

    def _on_current_changed(self, current: Optional[QTreeWidgetItem], _prev):
        obj = current.data(0, _ROLE_OBJ) if current else None
        if obj is not None:
            # Une seule ligne surlignée dans TOUT le panneau : deux sections
            # surlignées à la fois, et le surlignage ne dirait plus ce que
            # l'écran montre.
            self._panel.clear_selection(except_label=self._kind.label)
            self._panel.selected.emit(self._kind.label, obj)

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int):
        obj = item.data(0, _ROLE_OBJ)
        if obj is not None:
            self._panel.activated.emit(self._kind.label, obj)

    # ── Glisser vers le canvas ────────────────────────────────────

    def startDrag(self, _actions):
        """Le finder ne sait pas ce qu'on fait d'un asset lâché sur un canvas ;
        il ne fait qu'annoncer lequel, dans le type MIME que la famille déclare.
        C'est le canvas qui décide (instancier un prefab, poser un fond animé…)."""
        item = self.currentItem()
        obj = item.data(0, _ROLE_OBJ) if item else None
        if obj is None or self._kind.mime is None:
            return
        mime_type, payload = self._kind.mime
        project = self._panel.project
        data = QMimeData()
        data.setData(mime_type, QByteArray(str(payload(project, obj)).encode()))
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.exec(Qt.DropAction.MoveAction)

    @staticmethod
    def _same(a, b) -> bool:
        """Identité pour un asset en mémoire — deux `Resource` de mêmes champs
        restent deux assets distincts. Égalité pour un `Path`, qui est reconstruit
        à chaque parcours du disque et ne survivrait pas à un test d'identité."""
        return a is b or (isinstance(a, Path) and isinstance(b, Path) and a == b)

    def select_obj(self, obj) -> bool:
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if self._same(it.data(0, _ROLE_OBJ), obj):
                self.setCurrentItem(it)
                self.scrollToItem(it)
                return True
            stack.extend(it.child(n) for n in range(it.childCount()))
        return False

    def edit_obj(self, obj):
        """Ouvre l'édition en place sur `obj` — appelé après une création, pour
        que l'asset naisse nommé et renommable d'un geste, sans pop-up."""
        def go():
            if self.select_obj(obj):
                self.editItem(self.currentItem(), 0)
        QTimer.singleShot(0, go)

    # ── Renommage en place ────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int):
        obj = item.data(0, _ROLE_OBJ)
        if obj is None or self._kind.rename is None:
            return
        typed = item.text(0).strip()
        if not typed or typed == self._name_of(obj):
            self.blockSignals(True)
            self._set_label(item, obj)          # remet nom + suffixe
            self.blockSignals(False)
            return
        project = self._panel.project
        if project is None:
            return
        # Un renommage réécrit les références et peut faire repeupler l'arbre
        # DANS l'appel (project.events "renamed" -> "project_tree_changed" est
        # synchrone) : `item` est alors déjà détruit. On ne le retouche donc pas
        # après — on repeuple et on re-cible l'objet par IDENTITÉ, qui survit.
        applied = self._kind.rename(project, obj, typed)
        self._panel.refresh()
        if applied:
            self.select_obj(obj)

    # ── Menu contextuel ───────────────────────────────────────────

    def _on_ctx_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        obj = item.data(0, _ROLE_OBJ)
        if obj is None:
            return                      # dossier : rien à proposer pour l'instant
        self.setCurrentItem(item)
        kind, project = self._kind, self._panel.project
        menu = QMenu(self)
        menu.setStyleSheet(QSS.menu)
        menu.setFont(QFont(T.UI, T.MD))

        # Actions de la famille (les mêmes partout), puis celles que l'écran a
        # ajoutées — « Voir les instances » n'a de sens que là où un inspecteur
        # peut les montrer.
        for label, fn in kind.actions:
            menu.addAction(label).triggered.connect(
                lambda _=False, f=fn, o=obj: f(project, o))
        for label, fn in self._panel.extra_actions(kind.label):
            menu.addAction(label).triggered.connect(
                lambda _=False, f=fn, o=obj: f(o))

        if kind.rename is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            act = menu.addAction(f"Rename {kind.label.rstrip('s').lower()}")
            act.setShortcut("F2")       # affiché ; géré par EditKeyPressed
            act.triggered.connect(lambda _=False, it=item: self.editItem(it, 0))

        if kind.delete is not None:
            menu.addSeparator()
            menu.addAction("Delete").triggered.connect(
                lambda _=False, o=obj: self._delete(o))

        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _delete(self, obj):
        kind, project = self._kind, self._panel.project
        if project is None:
            return
        name = self._name_of(obj)
        prompt = (kind.delete_prompt(obj) if kind.delete_prompt
                  else f"Delete “{name}”?\n(Ctrl+Z to undo)")
        if QMessageBox.question(
            self, "Delete", prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        kind.delete(project, obj)
        self._panel.refresh()
        self._panel.emptied.emit(kind.label)


# ──────────────────────────────────────────────────────────────────
#  Le panneau
# ──────────────────────────────────────────────────────────────────

class AssetFinder(QWidget):
    """Colonne « finder » d'un écran : une section repliable par famille.

        finder = AssetFinder("Data finder", [DATA_TABLES])
        finder.load_project(project)
        finder.selected.connect(...)
    """

    selected      = pyqtSignal(str, object)   # (AssetKind.label, asset)
    activated     = pyqtSignal(str, object)   # double-clic
    emptied       = pyqtSignal(str)           # une suppression a eu lieu
    add_requested = pyqtSignal(str)           # « + » d'une famille qui délègue

    def __init__(self, title: str, kinds: list[AssetKind],
                 min_width: int = 220, max_width: int = 420, parent=None):
        super().__init__(parent)
        self._project = None
        self._kinds = list(kinds)
        self._trees: dict[str, _KindTree] = {}
        self._sections: dict[str, QWidget] = {}
        self._empties: dict[str, QLabel] = {}
        self._extra_actions: dict[str, list] = {}
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self.setMinimumWidth(min_width)
        self.setMaximumWidth(max_width)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(W.finder_bar(title))

        # Toutes les sections dans UNE zone défilante, calées en haut. Chacune
        # vaut sa hauteur de contenu ; le ressort de queue prend le reste, sinon
        # QVBoxLayout répartirait le rab entre les sections et une liste courte
        # flotterait au milieu du vide. Une liste plus haute que la colonne fait
        # défiler tout le panneau — et non elle seule, ce qui remettrait un
        # ascenseur par famille.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
        container = QWidget()
        container.setStyleSheet(f"background:{C.BG_BASE};")
        self._column = QVBoxLayout(container)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)

        for kind in self._kinds:
            # Titre en tons de thème : les finders n'ont plus de code couleur
            # par famille, la distinction se fait à la forme de l'icône.
            section = FinderSection(kind.label)
            tree = _KindTree(self, kind)
            self._trees[kind.label] = tree
            self._sections[kind.label] = section
            section.set_widget(self._wrap(tree, kind))
            if kind.add is None and not kind.add_tooltip:
                section.set_add_visible(False)
            else:
                section.set_add_tooltip(kind.add_tooltip or f"Add to {kind.label}")
                section.add_clicked.connect(lambda k=kind: self._add(k))
            self._column.addWidget(section)

        self._column.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def show_only(self, labels):
        """N'affiche que ces familles — le finder suit ce qu'on édite.

        Une banque d'effets n'a rien à faire à côté d'un graphe musical : elle
        ne s'y glisse pas et ne s'y référence pas. Masquer plutôt que griser,
        comme partout ailleurs : on ne propose pas une action impossible.
        `None` remet tout.
        """
        for label, section in self._sections.items():
            section.setVisible(labels is None or label in labels)

    def add_section(self, section: QWidget):
        """Ajoute une section À LA SUITE des familles, dans la même colonne
        défilante — pour ce qu'un écran affiche sous ses assets sans que ce
        soient des assets : les états d'animation d'un sprite, les constantes
        et globales du Script Editor. Sans quoi ces sections vivraient hors de
        la zone défilante et flotteraient en bas du panneau."""
        self._column.insertWidget(self._column.count() - 1, section)

    def _wrap(self, tree: _KindTree, kind: AssetKind) -> QWidget:
        """Liste + message d'état vide, l'un ou l'autre. Une famille sans
        `empty_text` n'affiche rien : une liste vide se voit toute seule."""
        if not kind.empty_text:
            return tree
        box = QWidget()
        box.setStyleSheet(f"background:{C.BG_BASE};")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        empty = QLabel(kind.empty_text)
        empty.setFont(QFont(T.UI, T.SM))
        empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:{S.CONTENT}px;")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        lay.addWidget(tree)
        lay.addWidget(empty)
        self._empties[kind.label] = empty
        return box

    # ── Chargement ────────────────────────────────────────────────

    @property
    def project(self):
        return self._project

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        for label, tree in self._trees.items():
            filled = tree.populate(self._project)
            empty = self._empties.get(label)
            if empty is not None:
                tree.setVisible(filled)
                empty.setVisible(not filled)

    def activate_current(self):
        """Émet `activated` pour l'asset sélectionné dans l'arbre qui a le focus
        — de quoi câbler un raccourci (Espace = écouter, dans le Sound Mixer)
        sans que le composant ait à savoir ce qu'« activer » veut dire."""
        for label, tree in self._trees.items():
            if tree.hasFocus():
                item = tree.currentItem()
                obj = item.data(0, _ROLE_OBJ) if item else None
                if obj is not None:
                    self.activated.emit(label, obj)
                return

    def clear_selection(self, except_label: str = ""):
        """Désélectionne sans réémettre — quand un autre panneau prend la main
        sur le contexte de l'écran (le Text Editor bascule Police ↔ Texte), ou
        qu'une autre famille du même panneau vient d'être choisie."""
        for label, tree in self._trees.items():
            if label == except_label:
                continue
            tree.blockSignals(True)
            tree.clearSelection()
            tree.setCurrentItem(None)
            tree.blockSignals(False)

    # ── Sélection pilotée de l'extérieur ──────────────────────────

    def select(self, kind_label: str, obj) -> bool:
        """Sélectionne `obj` — navigation venue d'un autre écran ou d'un undo."""
        tree = self._trees.get(kind_label)
        return tree.select_obj(obj) if tree is not None else False

    def current(self, kind_label: str):
        tree = self._trees.get(kind_label)
        item = tree.currentItem() if tree is not None else None
        return item.data(0, _ROLE_OBJ) if item is not None else None

    def begin_rename(self, kind_label: str, obj):
        """Ouvre l'édition en place sur `obj` — après une création faite ailleurs
        que par le « + » du finder (le menu Fichier, un import)."""
        tree = self._trees.get(kind_label)
        if tree is not None:
            tree.edit_obj(obj)

    # ── Actions ajoutées par l'écran ──────────────────────────────

    def add_action(self, kind_label: str, text: str, fn: Callable[[Any], None]):
        """Ajoute une entrée au menu contextuel d'une famille, DANS CET ÉCRAN.

        Ce qu'une famille sait faire d'elle-même vit dans `AssetKind.actions`
        (dupliquer une palette : vrai partout). Ce qui dépend de l'écran passe
        par ici — « Voir les instances » suppose un inspecteur pour les
        afficher, que seul le Scene Manager possède."""
        self._extra_actions.setdefault(kind_label, []).append((text, fn))

    def extra_actions(self, kind_label: str) -> list:
        return self._extra_actions.get(kind_label, [])

    # ── Ajout ─────────────────────────────────────────────────────

    def _add(self, kind: AssetKind):
        if self._project is None:
            return
        if kind.add is None:
            self.add_requested.emit(kind.label)   # l'écran prend la main
            return
        obj = kind.add(self._project)
        self.refresh()
        if obj is not None:
            # Créé nommé d'office puis renommable en place : pas de dialogue qui
            # réclame un nom avant que la chose existe.
            self._trees[kind.label].edit_obj(obj)
