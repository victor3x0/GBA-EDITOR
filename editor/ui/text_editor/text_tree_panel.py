"""
ui/text_editor/text_tree_panel.py — colonne centre (contexte Texte) : arbre des
textes + atelier d'écriture (éditeur de contenu et aperçu écran côte à côte).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter,
    QTextEdit, QLineEdit, QComboBox, QToolButton,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView,
    QMessageBox, QApplication,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.models.text import (
    MAX_DEPTH, SEP, norm_path, tree_paths, repath_segment, texts_under,
)
from core.text_markup import parse, resolve
from core.history import (
    get_history, SetFieldCmd, AddListItemCmd, RemoveListItemCmd,
)
from ui.common.theme import C, T, S, QSS
from ui.common.widgets import W, BTN_ICON
from ui.common import icons
from ui.text_editor.colors import TEXT_COLOR
from ui.text_editor.font_screen_preview import FontScreenPreview
from ui.text_editor.markup_highlighter import MarkupHighlighter
from ui.text_editor.markup_toolbar import MarkupToolbar
from ui.text_editor.text_commands import (
    RenameTextKeyCmd, SetTextPathCmd, RelinkTextKeyCmd,
)


class _ContentEdit(QTextEdit):
    """Éditeur de contenu qui ne commite qu'à la perte du focus.

    Une commande par frappe rendrait l'historique inutilisable (modèle de
    `NotesEdit`). `edited` reste émis à chaque frappe, pour l'aperçu.
    """

    committed = pyqtSignal(str, str)   # (avant, après)
    edited    = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._baseline = ""
        self.textChanged.connect(lambda: self.edited.emit(self.toPlainText()))

    def set_text_silent(self, text: str):
        """Remplit le champ et repose la ligne de base, sans rien émettre."""
        self._baseline = text or ""
        self.blockSignals(True)
        self.setPlainText(self._baseline)
        self.blockSignals(False)

    def commit(self):
        """Force le commit — aussi appelé avant un changement de sélection, qui
        ne provoque pas toujours un focus-out."""
        text = self.toPlainText()
        if text != self._baseline:
            before, self._baseline = self._baseline, text
            self.committed.emit(before, text)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.commit()


# Rôles portés par les items — au module, parce que l'arbre et le panneau les
# lisent tous les deux (la classe les ré-expose sous ses anciens noms).
_ROLE_TEXT = Qt.ItemDataRole.UserRole        # Text, sur une feuille
_ROLE_PATH = Qt.ItemDataRole.UserRole + 1    # tuple(str), sur un nœud

# Où l'item lâché a atterri, vu de la cible.
DROP_ON, DROP_ABOVE, DROP_BELOW = "on", "above", "below"


class _TextTree(QTreeWidget):
    """L'arbre des textes, augmenté du glisser-déposer.

    Il ne déplace RIEN lui-même : l'arbre est dérivé de la liste plate, et
    laisser Qt bouger des lignes le ferait mentir hors historique. Il dit ce qui
    a été lâché et où ; le panneau en tire une commande annulable.
    """

    drop_asked = pyqtSignal(object, object, str)   # (source, cible|None, DROP_*)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDropIndicatorShown(True)
        # Le curseur doit dire « déplacer », pas « copier » : un texte n'existe
        # qu'à un endroit. Le retrait de ligne par Qt est neutralisé dans
        # `dropEvent`.
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    @staticmethod
    def _path_of(item) -> Optional[tuple]:
        """Chemin du nœud, ou du rangement qui contient la feuille."""
        if item is None:
            return None
        t = item.data(0, _ROLE_TEXT)
        return tuple(t.path) if t is not None else item.data(0, _ROLE_PATH)

    def _refuses(self, src, dst) -> bool:
        """Cibles impossibles — un nœud ne se range ni dans lui-même ni dans ce
        qu'il contient : le chemin qu'on obtiendrait n'existerait plus."""
        if src is None or src is dst:
            return True
        node = src.data(0, _ROLE_PATH)
        if node is None:
            return False
        target = self._path_of(dst)
        return target is not None and target[:len(node)] == node

    def dragMoveEvent(self, e):
        """Refuse à la SOURCE plutôt qu'à l'arrivée : le curseur barré dit non
        pendant le geste, une erreur après coup arriverait trop tard."""
        dst = self.itemAt(e.position().toPoint())
        if self._refuses(self.currentItem(), dst):
            e.ignore()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        src = self.currentItem()
        dst = self.itemAt(e.position().toPoint())
        if self._refuses(src, dst):
            e.ignore()
            return
        pos = self.dropIndicatorPosition()
        where = (DROP_ABOVE if pos == QAbstractItemView.DropIndicatorPosition.AboveItem
                 else DROP_BELOW if pos == QAbstractItemView.DropIndicatorPosition.BelowItem
                 else DROP_ON)
        # `IgnoreAction` : accepté en MoveAction, Qt retirerait de lui-même la
        # ligne déplacée — l'arbre perdrait une entrée que le modèle a encore.
        e.setDropAction(Qt.DropAction.IgnoreAction)
        e.accept()
        # Cible None = le vide sous l'arbre, c'est-à-dire la racine.
        self.drop_asked.emit(src, dst, where)


# ──────────────────────────────────────────────────────────────────
#  Arbre des textes + atelier d'écriture
# ──────────────────────────────────────────────────────────────────
class TextTreePanel(QWidget):
    """Arbre des `Text` rangés par chemin + éditeur du contenu sélectionné.

    L'arbre est une VUE, pas un stockage : `texts.json` reste une liste plate
    dont chaque entrée porte son chemin, et les nœuds sont dérivés à chaque
    reconstruction. Contrepartie assumée : pas de groupe vide — créer un groupe,
    c'est créer un texte dedans.
    """

    text_selected    = pyqtSignal(object)   # Text | None
    changed          = pyqtSignal()         # contenu modifié → persistance
    identity_changed = pyqtSignal(object)   # clé/chemin modifiés
    parsed           = pyqtSignal(object)   # ParsedText de l'entrée courante
    preview_font_changed = pyqtSignal(object)   # Font | None

    _COLS = ("Folder / Content", "Key")
    # Les rôles vivent au module (l'arbre les lit aussi) ; ces alias gardent le
    # `self._ROLE_*` du reste de la classe.
    _ROLE_TEXT = globals()["_ROLE_TEXT"]      # Text, sur une feuille
    _ROLE_PATH = globals()["_ROLE_PATH"]      # tuple(str), sur un nœud

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._blocking = False
        self._current: Optional[object] = None
        self._values: dict = {}
        # Nœuds explicitement REPLIÉS, et non l'inverse : un chemin qui vient
        # d'apparaître doit s'ouvrir seul, sinon le texte semble disparu.
        self._collapsed: set[tuple] = set()
        # Cadenas ouvert : le champ est éditable, mais `auto_key` ne tombera
        # qu'au commit d'un nom réellement différent.
        self._key_unlocked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Même bandeau d'identité que les autres viewers, augmenté du compteur,
        # du filtre et des actions — ce panneau n'a pas de section repliable.
        hdr = W.finder_bar("TEXTS")
        hl = hdr.layout()
        self._count = QLabel("")
        self._count.setFont(QFont(T.MONO, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hl.addWidget(self._count)
        hl.addStretch()
        # Filtre TOUJOURS visible : dès qu'on peut replier, on peut se cacher
        # son propre contenu — la recherche est la contrepartie du pliage.
        self._search = W.search_box("Filter: key, folder or content…")
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(lambda _q: self._apply_filter())
        hl.addWidget(self._search)
        self._btn_add = W.btn_add("New text (filed where the selection is)")
        self._btn_add.clicked.connect(self._add_text)
        hl.addWidget(self._btn_add)
        self._btn_del = W.btn_danger("Delete selected text")
        self._btn_del.clicked.connect(self._delete_text)
        hl.addWidget(self._btn_del)
        root.addWidget(hdr)

        self._tree = _TextTree()
        self._tree.setColumnCount(len(self._COLS))
        self._tree.setHeaderLabels(self._COLS)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Aucun déclencheur automatique : le double-clic est routé à la main
        # vers le libellé d'un NŒUD ou la CLÉ d'une feuille — jamais vers le
        # contenu, qui est un rendu (balises résolues) et non la source.
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setUniformRowHeights(True)
        # Corps, hauteur de ligne et survol communs aux viewers ; seule la
        # couleur de sélection reste celle des textes.
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.UI_STACK}; font-size:{T.MD}px; outline:none;}}"
            f"QTreeWidget::item{{padding:2px 4px; height:{S.ROW}px;}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{TEXT_COLOR};}}"
            f"QTreeWidget::item:hover:!selected{{background:{C.BG_PANEL};}}"
            f"QHeaderView::section{{background:transparent; color:{C.TEXT_MUTED};"
            f"border:none; border-bottom:1px solid {C.BORDER_DARK}; padding:4px 6px;"
            f"font-family:{T.UI_STACK}; font-size:{T.XS}px; font-weight:700;"
            f"letter-spacing:1px;}}"
        )
        th = self._tree.header()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.itemSelectionChanged.connect(self._on_sel)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemExpanded.connect(self._on_expanded)
        self._tree.itemCollapsed.connect(self._on_collapsed)
        self._tree.drop_asked.connect(self._on_drop)

        # ── Découpage : la liste en haut, l'atelier en bas ─────────
        # Écriture et rendu CÔTE À CÔTE : empilés, l'aperçu repoussait
        # l'éditeur hors de vue. Splitters plutôt que tailles figées.
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setStyleSheet(QSS.splitter)
        vsplit.setChildrenCollapsible(False)
        vsplit.addWidget(self._tree)

        workbench = QSplitter(Qt.Orientation.Horizontal)
        workbench.setStyleSheet(QSS.splitter)
        workbench.setChildrenCollapsible(False)

        edit_pane = QWidget()
        edit_pane.setStyleSheet(f"background:{C.BG_BASE};")
        root_edit = QVBoxLayout(edit_pane)
        root_edit.setContentsMargins(0, 0, 0, 0)
        root_edit.setSpacing(0)

        # Identité sur une ligne, contenu dessous : éditer là où on lit. La
        # clé est en mono — c'est du code, elle part telle quelle dans les Lua.
        ed_hdr = QFrame()
        ed_hdr.setFixedHeight(30)
        ed_hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        el = QHBoxLayout(ed_hdr)
        el.setContentsMargins(8, 2, 8, 2)
        el.setSpacing(4)

        self._key_edit = QLineEdit()
        self._key_edit.setFont(QFont(T.CODE, T.SM))
        self._key_edit.setFixedWidth(180)
        self._key_edit.setPlaceholderText("key")
        self._key_edit.editingFinished.connect(self._commit_key)
        el.addWidget(self._key_edit)

        # Cadenas : la clé est en lecture seule tant qu'elle DÉRIVE du
        # rangement. La nommer à la main l'en détache définitivement.
        self._btn_lock = QToolButton()
        self._btn_lock.setFixedSize(22, 22)
        self._btn_lock.setStyleSheet(BTN_ICON)
        self._btn_lock.clicked.connect(self._toggle_key_lock)
        el.addWidget(self._btn_lock)

        self._btn_copy = QToolButton()
        self._btn_copy.setFixedSize(22, 22)
        self._btn_copy.setStyleSheet(BTN_ICON)
        self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM))
        self._btn_copy.setToolTip("Copy the key — paste into a Lua script")
        self._btn_copy.clicked.connect(self._copy_key)
        el.addWidget(self._btn_copy)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{C.BORDER};")
        el.addSpacing(4)
        el.addWidget(sep)
        el.addSpacing(4)

        # Un champ par niveau plutôt qu'une chaîne à séparateur : un libellé a
        # le droit de contenir « / », et la profondeur max se voit.
        self._path_edits: list[QLineEdit] = []
        for lvl in range(MAX_DEPTH):
            if lvl:
                arrow = QLabel(SEP.strip())
                arrow.setFont(QFont(T.UI, T.SM))
                arrow.setStyleSheet(f"color:{C.TEXT_MUTED};")
                el.addWidget(arrow)
            e = QLineEdit()
            e.setFont(QFont(T.MONO, T.SM))
            e.setStyleSheet(QSS.lineedit)
            e.setPlaceholderText(f"level {lvl + 1}")
            e.setToolTip(
                "<b>Filing</b> — accents, spaces and duplicates allowed.<br>"
                "Never resolved, never referenced: it organizes the tree and<br>"
                "suggests the key, without ever owning it."
            )
            e.editingFinished.connect(self._commit_path)
            el.addWidget(e, 1)
            self._path_edits.append(e)
        root_edit.addWidget(ed_hdr)

        self._editor = _ContentEdit()
        self._editor.setFont(QFont(T.CODE, T.MD))
        self._editor.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI}; border:none;"
            f"padding:6px;}}"
        )
        self._editor.setPlaceholderText("Select a text entry to edit its content…")
        # Les balises se voient pendant qu'on écrit, et ce qui cloche se
        # souligne — même analyse que l'aperçu et que l'inspecteur.
        self._highlighter = MarkupHighlighter(self._editor.document())
        self._editor.edited.connect(self._on_content_edited)
        self._editor.committed.connect(self._on_content_committed)
        # Barre de balisage ENTRE l'identité et le texte : elle agit sur ce qui
        # est juste dessous.
        self._markup_bar = MarkupToolbar(self._editor)
        root_edit.addWidget(self._markup_bar)
        root_edit.addWidget(self._editor, 1)
        workbench.addWidget(edit_pane)

        prev_pane = QWidget()
        prev_pane.setStyleSheet(f"background:{C.BG_DEEP};")
        root_prev = QVBoxLayout(prev_pane)
        root_prev.setContentsMargins(0, 0, 0, 0)
        root_prev.setSpacing(0)

        # Aperçu mis à jour à la FRAPPE, pas au commit : c'est en écrivant
        # qu'on veut voir où le texte coupe.
        prev_hdr = QFrame()
        prev_hdr.setFixedHeight(20)
        prev_hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        pl = QHBoxLayout(prev_hdr)
        pl.setContentsMargins(8, 0, 8, 0)
        pv = QLabel("SCREEN PREVIEW")
        pv.setFont(QFont(T.UI, T.XS, QFont.Weight.DemiBold))
        pv.setStyleSheet(QSS.title_panel)
        pl.addWidget(pv)
        pl.addStretch()
        self._preview_font = QComboBox()
        self._preview_font.setFont(QFont(T.UI, T.XS))
        self._preview_font.setStyleSheet(QSS.combobox)
        self._preview_font.setToolTip("Font used for the preview (doesn't affect the text)")
        self._preview_font.currentIndexChanged.connect(self._on_preview_font)
        pl.addWidget(self._preview_font)
        root_prev.addWidget(prev_hdr)

        # Pas de QScrollArea : l'aperçu est son PROPRE viewport (molette = zoom,
        # clic-central = pan), deux défilements superposés se voleraient la
        # molette.
        self._preview = FontScreenPreview()
        root_prev.addWidget(self._preview, 1)
        workbench.addWidget(prev_pane)

        # L'écriture prime : l'aperçu n'a besoin que de ses 240 px logiques.
        workbench.setSizes([520, 360])
        workbench.setStretchFactor(0, 1)
        workbench.setStretchFactor(1, 0)
        vsplit.addWidget(workbench)
        vsplit.setSizes([260, 340])
        vsplit.setStretchFactor(0, 0)
        vsplit.setStretchFactor(1, 1)
        root.addWidget(vsplit, 1)

        self._set_enabled(False)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        """Ouvre un projet : polices d'aperçu puis arbre."""
        self._project = project
        # Valeurs initiales des globals et constantes, relues à l'ouverture :
        # l'aperçu montre des chiffres, pas des places réservées.
        self._values = project.text_values() if project else {}
        self._markup_bar.set_project(project)
        self._reload_preview_fonts()
        self.refresh()

    def _reload_preview_fonts(self):
        """Peuple le sélecteur de police d'aperçu — confort d'édition : le
        texte reste indépendant de toute police (traductions v0.8)."""
        self._blocking = True
        cur = self._preview_font.currentText()
        self._preview_font.clear()
        fonts = list(self._project.fonts) if self._project else []
        for f in fonts:
            self._preview_font.addItem(f.name, f)
        idx = self._preview_font.findText(cur)
        self._preview_font.setCurrentIndex(idx if idx >= 0 else 0)
        self._blocking = False
        self._apply_preview_font()

    def _apply_preview_font(self):
        """Passe la police choisie à l'aperçu — et à qui veut la confronter au
        texte (l'inspecteur, pour les caractères manquants)."""
        f = self._preview_font.currentData()
        self._preview.set_font_asset(f, self._project)
        # La même police décide de ce que `[icon=…]` peut désigner : les cases
        # fusionnées n'existent que dans une planche précise.
        self._markup_bar.set_font(f)
        self.preview_font_changed.emit(f)

    def preview_font(self):
        return self._preview_font.currentData()

    def _on_preview_font(self, _i):
        if not self._blocking:
            self._apply_preview_font()

    def refresh_preview_font(self):
        """Retroue la planche d'aperçu (mise en cache au chargement) après un
        changement de couleur-clé."""
        self._apply_preview_font()

    def refresh(self, select_id: Optional[int] = None):
        """Reconstruit l'arbre depuis le projet, sélection conservée."""
        # Le refresh peut venir du watcher pendant que l'utilisateur travaille :
        # garder son entrée plutôt que le renvoyer en haut de l'arbre.
        if select_id is None and self._current is not None:
            select_id = self._current.id
        self._blocking = True
        self._tree.clear()
        texts = list(self._project.texts) if self._project else []

        # Deux passes : les nœuds d'abord (déjà triés parent avant enfant),
        # puis les feuilles dans l'ordre du projet — les rangements apparaissent
        # donc avant les textes d'un même niveau, comme dans un explorateur.
        nodes: dict[tuple, QTreeWidgetItem] = {}
        for path in tree_paths(texts):
            parent = nodes.get(path[:-1]) if len(path) > 1 else None
            it = QTreeWidgetItem(parent) if parent is not None else QTreeWidgetItem(self._tree)
            it.setText(0, path[-1])
            it.setData(0, self._ROLE_PATH, path)
            it.setForeground(0, QColor(C.TEXT_DIM))
            it.setIcon(0, icons.get("folder", icons.COLOR_FOLDER))
            it.setToolTip(0, "Double-click to rename this folder "
                             "(and everything it contains).\n"
                             "Drag it to file it elsewhere.")
            it.setExpanded(path not in self._collapsed)
            nodes[path] = it

        for t in texts:
            parent = nodes.get(tuple(t.path))
            leaf = QTreeWidgetItem(parent) if parent is not None else QTreeWidgetItem(self._tree)
            self._fill_leaf(leaf, t)

        for path, it in nodes.items():
            n = self._leaf_count(it)
            it.setText(1, str(n))
            it.setForeground(1, QColor(C.TEXT_MUTED))

        self._count.setText(f"  {len(texts)}")
        self._apply_filter()
        self._blocking = False

        if select_id is not None:
            self.select_by_id(select_id)
        # L'entrée visée a pu disparaître (supprimée hors éditeur) : la
        # sélection n'a pas été rétablie, il faut vider l'éditeur.
        if self._selected_text() is None:
            self._current = None
            self._sync_editor()

    def _fill_leaf(self, item: QTreeWidgetItem, t):
        """Une feuille montre ce qu'on LIT (le contenu) et ce qu'on COPIE (la
        clé) : le rangement est déjà porté par la place dans l'arbre."""
        # Le texte tel qu'on le LIT : balises retirées, valeurs substituées.
        # Le balisage, lui, s'édite dans l'atelier.
        preview = resolve(parse(t.content), self._values).replace("\n", " ⏎ ")
        item.setText(0, preview or "(empty)")
        item.setForeground(0, QColor(C.TEXT_NORM if preview else C.TEXT_MUTED))
        item.setData(0, self._ROLE_TEXT, t)
        item.setText(1, t.key)
        # Clé dérivée = jetable, en retrait ; clé nommée à la main = un
        # contrat posé par quelqu'un, elle mérite l'accent.
        item.setForeground(1, QColor(C.TEXT_MUTED if t.auto_key else TEXT_COLOR))
        item.setToolTip(1, ("Automatic key — follows the folder"
                            if t.auto_key else
                            "Named by hand — independent of the folder")
                        + "\nDouble-click to name it by hand.")

    @staticmethod
    def _leaf_count(item: QTreeWidgetItem) -> int:
        """Nombre de textes sous un nœud, tous niveaux confondus."""
        n = 0
        for i in range(item.childCount()):
            c = item.child(i)
            n += 1 if c.data(0, TextTreePanel._ROLE_TEXT) is not None \
                   else TextTreePanel._leaf_count(c)
        return n

    def select_by_id(self, tid: int):
        """Sélectionne le texte d'id `tid` et le fait défiler à vue."""
        for item in self._iter_items():
            t = item.data(0, self._ROLE_TEXT)
            if t is not None and t.id == tid:
                self._tree.setCurrentItem(item)
                self._tree.scrollToItem(item)
                return

    def clear_selection(self):
        """Vide la sélection et l'atelier, sans émettre."""
        self._blocking = True
        self._tree.clearSelection()
        self._tree.setCurrentItem(None)
        self._blocking = False
        self._current = None
        self._sync_editor()

    def _iter_items(self, parent: Optional[QTreeWidgetItem] = None):
        """Parcours en profondeur de l'arbre."""
        node = parent if parent is not None else self._tree.invisibleRootItem()
        for i in range(node.childCount()):
            child = node.child(i)
            yield child
            yield from self._iter_items(child)

    # ── Filtre ────────────────────────────────────────────────────

    def _apply_filter(self):
        """Masque ce qui ne correspond pas ; un nœud reste visible si lui ou un
        descendant correspond, et il est alors déplié d'office.

        Le pliage forcé ne touche PAS `_collapsed` : l'état choisi à la main
        revient tel quel quand le filtre se vide."""
        q = self._search.text().strip().casefold()
        was_blocking, self._blocking = self._blocking, True

        def visit(item: QTreeWidgetItem) -> bool:
            t = item.data(0, self._ROLE_TEXT)
            hay = (f"{item.text(0)} {item.text(1)} {t.path_str()}" if t is not None
                   else item.text(0)).casefold()
            # Liste et non générateur : `any` court-circuiterait et laisserait
            # les frères suivants avec une visibilité périmée.
            hits = [visit(item.child(i)) for i in range(item.childCount())]
            visible = (not q) or (q in hay) or any(hits)
            item.setHidden(not visible)
            path = item.data(0, self._ROLE_PATH)
            if path is not None:
                item.setExpanded(any(hits) if q else path not in self._collapsed)
            return visible

        for i in range(self._tree.invisibleRootItem().childCount()):
            visit(self._tree.invisibleRootItem().child(i))
        self._blocking = was_blocking

    def _on_expanded(self, item: QTreeWidgetItem):
        path = item.data(0, self._ROLE_PATH)
        if not self._blocking and path is not None:
            self._collapsed.discard(path)

    def _on_collapsed(self, item: QTreeWidgetItem):
        path = item.data(0, self._ROLE_PATH)
        if not self._blocking and path is not None:
            self._collapsed.add(path)

    # ── Sélection / édition ───────────────────────────────────────

    def _selected_text(self):
        """Le `Text` sélectionné, ou None (nœud, rien, ou ligne filtrée)."""
        item = self._tree.currentItem()
        if item is None or item.isHidden():
            return None
        return item.data(0, self._ROLE_TEXT)

    def _selected_path(self) -> list[str]:
        """Chemin courant — du texte sélectionné, ou du nœud si c'est un
        rangement. Sert au « + » : la nouvelle entrée naît là où on regarde."""
        item = self._tree.currentItem()
        if item is None:
            return []
        t = item.data(0, self._ROLE_TEXT)
        if t is not None:
            return list(t.path)
        path = item.data(0, self._ROLE_PATH)
        return list(path) if path else []

    def _on_sel(self):
        if self._blocking:
            return
        # Commiter AVANT de changer d'entrée, sinon la frappe non validée
        # serait attribuée au texte suivant.
        self._editor.commit()
        self._current = self._selected_text()
        self._key_unlocked = False      # le cadenas se referme d'une entrée à l'autre
        self._sync_editor()
        self.text_selected.emit(self._current)

    def _sync_editor(self):
        """Recharge l'atelier depuis l'entrée courante."""
        t = self._current
        self._set_enabled(t is not None)
        self._blocking = True
        self._key_edit.setText(t.key if t else "")
        path = list(t.path) if t else []
        for lvl, e in enumerate(self._path_edits):
            e.setText(path[lvl] if lvl < len(path) else "")
        self._sync_key_lock()
        self._blocking = False
        # L'atelier édite la SOURCE (balises comprises), l'aperçu montre le
        # rendu — c'est tout l'intérêt de les avoir côte à côte.
        self._editor.set_text_silent(t.content if t else "")
        self._push_parsed(t.content if t else "")

    def _sync_key_lock(self):
        """Reflète l'état de la clé : dérivée (verrouillée), dérivée mais
        déverrouillée le temps de l'édition, ou nommée à la main."""
        t = self._current
        auto = bool(t and t.auto_key)
        editable = bool(t) and (not auto or self._key_unlocked)
        self._key_edit.setReadOnly(not editable)
        self._key_edit.setStyleSheet(
            QSS.lineedit if editable else
            QSS.lineedit + f"QLineEdit{{color:{C.TEXT_MUTED}; background:{C.BG_PANEL};}}"
        )
        self._key_edit.setToolTip(
            "<b>Key</b> — the handle Lua scripts write, resolved at build time.<br><br>"
            + ("It DERIVES from the folder and will follow it. Unlock to<br>"
               "name it by hand: it will detach from it permanently."
               if auto else
               "Named by hand: the folder no longer affects it.<br>"
               "Renaming it updates the scripts that reference it.")
        )
        self._btn_lock.setIcon(icons.get(
            "key_auto" if auto else "key_manual",
            C.TEXT_DIM if auto else TEXT_COLOR))
        self._btn_lock.setToolTip(
            ("Key attached to the folder — click to name it by hand"
             if not self._key_unlocked else
             "Click to re-attach it to the folder")
            if auto else
            "Named by hand — click to re-attach it to the folder")

    def _set_enabled(self, on: bool):
        """Active l'atelier — il n'a de sens qu'avec une entrée sélectionnée."""
        self._editor.setEnabled(on)
        self._markup_bar.setEnabled(on)
        self._key_edit.setEnabled(on)
        self._btn_lock.setEnabled(on)
        self._btn_copy.setEnabled(on)
        for e in self._path_edits:
            e.setEnabled(on)
        self._btn_del.setEnabled(on)

    # ── Identité (clé / rangement) ────────────────────────────────

    def _toggle_key_lock(self):
        """Ouvre le champ clé, ou ré-accroche une clé manuelle au rangement."""
        t = self._current
        if not t or not self._project:
            return
        if t.auto_key:
            # Le cadenas n'ouvre que le champ : cliquer par curiosité ne doit
            # rien casser, `auto_key` ne tombe qu'au commit.
            self._key_unlocked = not self._key_unlocked
            self._blocking = True
            self._key_edit.setText(t.key)
            self._sync_key_lock()
            self._blocking = False
            if self._key_unlocked:
                self._key_edit.setFocus()
                self._key_edit.selectAll()
            return
        # Clé nommée à la main : la ré-accrocher au rangement.
        self._key_unlocked = False
        get_history().push(RelinkTextKeyCmd(
            self._project, t, persist_fn=self._after_identity_change))

    def _copy_key(self):
        """Copie la clé dans le presse-papier (à coller dans un script)."""
        t = self._current
        if not t:
            return
        QApplication.clipboard().setText(t.key)
        self._btn_copy.setIcon(icons.get("copied", C.POWER))
        QTimer.singleShot(
            900, lambda: self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM)))

    def _commit_key(self):
        """Valide la clé saisie dans l'atelier."""
        t = self._current
        if self._blocking or not t:
            return
        if not self._rename_key(t, self._key_edit.text()):
            self._key_edit.setText(t.key)

    def _rename_key(self, t, raw: str) -> bool:
        """Renomme la clé de `t` — refuse le vide et les doublons.

        Point unique du renommage MANUEL : le champ de l'atelier et la colonne
        « Key » de l'arbre écrivent la même chose (la clé se détache du
        rangement), il ne doit pas y avoir deux versions de cette règle.
        Retourne False si rien n'a été renommé, à charge de l'appelant de
        remettre l'ancienne valeur dans son champ."""
        new = (raw or "").strip()
        if not self._project or not new or new == t.key:
            return False
        old, old_auto = t.key, t.auto_key
        if not self._project.rename_text_key(t, new):
            QMessageBox.warning(
                self, "Invalid key",
                f"“{new}” is empty or already used by another text.")
            return False
        self._key_unlocked = False      # la clé est désormais nommée à la main
        get_history().push(RenameTextKeyCmd(
            self._project, t, old, new, old_auto,
            persist_fn=self._after_identity_change,
        ))
        return True

    def _commit_path(self):
        """Valide le rangement saisi dans les champs de niveau."""
        t = self._current
        if self._blocking or not t or not self._project:
            return
        new = norm_path([e.text() for e in self._path_edits])
        if new == list(t.path):
            return
        get_history().push(SetTextPathCmd(
            self._project, [(t, list(t.path), new)],
            label=f"Ranger {t.key} dans {SEP.join(new) or '(racine)'}",
            persist_fn=self._after_identity_change,
        ))

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        """Édition sur place (jamais de boîte de dialogue) : le libellé d'un
        NŒUD, qui renomme le segment pour tout ce qu'il contient, ou la CLÉ
        d'une feuille, qui la détache du rangement."""
        is_node = item.data(0, self._ROLE_PATH) is not None
        if not (is_node and col == 0) and not (not is_node and col == 1):
            return
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.editItem(item, col)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        """Fin d'édition : clé d'une feuille, ou libellé d'un nœud (qui range
        alors tous les textes qu'il contient)."""
        if self._blocking or not self._project:
            return
        path = item.data(0, self._ROLE_PATH)
        if col == 1 and path is None:
            self._commit_tree_key(item)
            return
        if col != 0 or path is None:
            return
        new_seg = item.text(0).strip()
        # Refermer l'édition ré-émet `itemChanged` : sans ce garde le handler
        # se rappelle indéfiniment et la pile déborde.
        self._blocking = True
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if not new_seg or new_seg == path[-1]:
            item.setText(0, path[-1])
        self._blocking = False
        if not new_seg or new_seg == path[-1]:
            return
        entries = repath_segment(self._project.texts, path, new_seg)
        if not entries:
            return
        # Le nœud replié l'était sous son ancien nom : sans report, le
        # renommer le rouvrirait.
        renamed = path[:-1] + (new_seg,)
        if path in self._collapsed:
            self._collapsed.discard(path)
            self._collapsed.add(renamed)
        cmd = SetTextPathCmd(
            self._project, entries,
            label=f"Rename folder {path[-1]} → {new_seg}",
            persist_fn=self._after_identity_change,
        )
        # Différé d'un tour de boucle : la commande reconstruit l'arbre, donc
        # DÉTRUIT l'item dont on traite le signal — le C++ reviendrait dans un
        # objet libéré.
        QTimer.singleShot(0, lambda: get_history().push(cmd))

    def _commit_tree_key(self, item: QTreeWidgetItem):
        """Fin d'édition de la colonne « Key » : même renommage que le champ de
        l'atelier, refus compris."""
        t = item.data(0, self._ROLE_TEXT)
        self._blocking = True
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._blocking = False
        if t is None:
            return
        typed = item.text(1)

        def _commit():
            # Différé pour la même raison que le renommage de nœud : le succès
            # reconstruit l'arbre sous l'item qu'on est en train de traiter.
            if not self._rename_key(t, typed):
                self._blocking = True
                item.setText(1, t.key)
                self._blocking = False

        QTimer.singleShot(0, _commit)

    # ── Glisser-déposer ───────────────────────────────────────────

    def _on_drop(self, src: QTreeWidgetItem, dst: Optional[QTreeWidgetItem],
                 where: str):
        """Déplace ce qu'on a lâché.

        Ranger, c'est changer un chemin : les clés AUTO des textes concernés
        sont recalculées EN BLOC derrière (et les `text.draw` des scripts
        réécrits), les clés nommées à la main ne bougent pas. Un dossier
        emporte tout son contenu, comme son renommage."""
        if not self._project or src is None:
            return
        target, anchor = self._drop_target(dst, where)
        t = src.data(0, self._ROLE_TEXT)
        entries, order, label = (
            self._move_text(t, target, anchor, where) if t is not None
            else self._move_node(src.data(0, self._ROLE_PATH), target))
        if not entries and order is None:
            return
        cmd = SetTextPathCmd(self._project, entries, label=label,
                             persist_fn=self._after_identity_change, order=order)
        QTimer.singleShot(0, lambda: get_history().push(cmd))

    def _drop_target(self, dst: Optional[QTreeWidgetItem], where: str):
        """(rangement visé, texte d'ancrage) — l'ancrage dit à quelle PLACE
        dans la liste, le rangement dit dans quel dossier.

        Lâcher SUR un texte vise son dossier, un texte ne contenant rien ;
        lâcher ENTRE deux lignes vise le niveau de la ligne visée."""
        if dst is None:
            return [], None
        t = dst.data(0, self._ROLE_TEXT)
        if t is not None:
            return list(t.path), t
        path = dst.data(0, self._ROLE_PATH) or ()
        # Un nœud ne s'ordonne pas (les rangements sont triés par nom) : au-
        # dessus ou en dessous de lui, on vise donc son PARENT.
        return (list(path) if where == DROP_ON else list(path[:-1])), None

    def _move_text(self, t, target: list, anchor, where: str):
        """Une entrée : elle change de rangement, de place dans la liste, ou
        des deux."""
        same_path = list(t.path) == target
        order = list(self._project.texts)
        order.remove(t)
        if anchor is not None and anchor is not t:
            i = order.index(anchor)
            order.insert(i if where == DROP_ABOVE else i + 1, t)
        else:
            order.append(t)
        if same_path and order == list(self._project.texts):
            return [], None, ""
        return ([] if same_path else [(t, list(t.path), target)],
                order,
                f"Reorder {t.key}" if same_path else
                f"Move {t.key} to {SEP.join(target) or '(root)'}")

    def _move_node(self, node: Optional[tuple], target: list):
        """Un dossier : il emporte son contenu, et sa profondeur doit tenir."""
        if not node:
            return [], None, ""
        new_parent = list(target)
        if new_parent == list(node[:-1]):        # déjà là
            return [], None, ""
        under = texts_under(self._project.texts, node)
        deepest = max((len(t.path) for t in under), default=len(node))
        if len(new_parent) + 1 + (deepest - len(node)) > MAX_DEPTH:
            # Refus EXPLIQUÉ : le geste est légitime, seul le plafond de
            # profondeur ne suit pas — sinon l'arbre refuse sans raison visible.
            QMessageBox.warning(
                self, "Too deep",
                f"“{node[-1]}” cannot be filed there: filing goes "
                f"{MAX_DEPTH} levels deep at most.")
            return [], None, ""
        prefix = new_parent + [node[-1]]
        entries = [(t, list(t.path), prefix + list(t.path[len(node):]))
                   for t in under]
        # Le nœud replié l'était sous son ancien chemin, et ses descendants
        # aussi : sans report, le déplacer rouvrirait toute la branche.
        for path in [p for p in self._collapsed if p[:len(node)] == tuple(node)]:
            self._collapsed.discard(path)
            self._collapsed.add(tuple(prefix) + path[len(node):])
        return entries, None, \
            f"Move folder {node[-1]} to {SEP.join(new_parent) or '(root)'}"

    def _after_identity_change(self):
        """Persiste, reconstruit l'arbre et prévient l'inspecteur."""
        self.changed.emit()
        self.refresh()
        self.identity_changed.emit(self._current)

    def _on_content_edited(self, text: str):
        """Frappe en cours : aperçu et ligne de la table seulement, aucune
        écriture au modèle (elle arrive au commit)."""
        if self._blocking or not self._current:
            return
        parsed = self._push_parsed(text)
        item = self._tree.currentItem()
        if item is not None and item.data(0, self._ROLE_TEXT) is not None:
            self._blocking = True
            preview = parsed.display.replace("\n", " ⏎ ")
            item.setText(0, preview or "(empty)")
            item.setForeground(0, QColor(C.TEXT_NORM if preview else C.TEXT_MUTED))
            self._blocking = False

    def _push_parsed(self, source: str):
        """Analyse une fois et diffuse : l'aperçu dessine le texte affiché,
        l'inspecteur montre balises et anomalies. Un seul parcours par frappe."""
        parsed = parse(source)
        self._preview.set_text(resolve(parsed, self._values))
        self.parsed.emit(parsed)
        return parsed

    def _on_content_committed(self, before: str, after: str):
        """Contenu validé : une commande d'historique."""
        t = self._current
        if not t:
            return
        get_history().push(SetFieldCmd(
            t, "content", before, after,
            label=f"Contenu de {t.key}", persist_fn=self._emit_changed,
        ))

    def _emit_changed(self):
        self.changed.emit()

    # ── CRUD ──────────────────────────────────────────────────────

    def _add_text(self):
        """Crée un texte DANS le rangement courant — seul moyen de créer un
        groupe, et évite de re-ranger chaque entrée après coup."""
        if not self._project:
            return
        t = self._project.new_text(content="", path=self._selected_path())

        def _after():
            self.changed.emit()
            self.refresh(select_id=t.id if t in self._project.texts else None)

        # new_text a déjà ajouté l'entrée : execute() est un no-op au premier
        # passage, undo la retire, redo la remet.
        get_history().push(AddListItemCmd(
            self._project.texts, t, persist_fn=_after,
            label=f"New text {t.key}",
        ))

    def _delete_text(self):
        """Supprime l'entrée courante, après confirmation."""
        t = self._current
        if not t or not self._project:
            return
        if QMessageBox.question(
            self, "Delete text",
            f"Delete “{t.key}”?\n\nScripts that use it will no longer compile.",
        ) != QMessageBox.StandardButton.Yes:
            return
        def _after():
            self.changed.emit()
            if t not in self._project.texts:
                self._current = None
                self.refresh()
                self.text_selected.emit(None)
            else:                       # undo : l'entrée est revenue
                self.refresh(select_id=t.id)

        get_history().push(RemoveListItemCmd(
            self._project.texts, t, persist_fn=_after,
            label=f"Delete text {t.key}",
        ))
