"""
ui/text_editor/text_table.py — colonne centre (contexte Texte), partie HAUTE :
la table des textes.

**Une table PLATE, comme le stockage.** `texts.json` est une liste dont chaque
entrée porte son chemin : l'arbre qui précédait cette vue en était déjà une
projection, la table l'est tout autant. Ce qu'elle apporte en plus, c'est le
geste qu'un arbre ne sait pas faire — **balayer** deux cents entrées d'un coup
d'œil, trier par ce qui manque, comparer deux lignes qui ne sont pas rangées au
même endroit. C'est le geste de la traduction et celui du ménage de fin de
projet ; retrouver UNE réplique, que l'arbre servait bien, reste couvert par le
filtre.

Le rangement ne disparaît pas pour autant : ses trois niveaux deviennent trois
colonnes, et le groupement par catégorie se rallume à la demande (lignes
d'en-tête repliables). Il est OPTIONNEL, parce que grouper interdit de trier
sur autre chose que le rangement.

Aucune colonne ne s'appelle « Key » pour un niveau de chemin : dans le modèle,
`key` désigne une chose et une seule — la poignée que le Lua écrit et que le
build résout. Un niveau de rangement n'est jamais résolu ni référencé. Deux
mots pour deux choses.

Cette vue ne MODIFIE rien : elle dit ce qui a été édité et laisse le panneau en
tirer une commande annulable. Le modèle est plat et l'ordre des lignes est un
tri d'affichage — laisser Qt écrire dans la table la ferait mentir hors
historique.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView,
    QStyledItemDelegate, QStyle,
)
from PyQt6.QtGui import QFont, QColor, QBrush, QPen, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF

from core.text_markup import parse, resolve
from ui.common.theme import C, T, S
from ui.common.widgets import W, BTN_ICON, HoverIconButton
from ui.common import icons
from ui.text_editor.colors import TEXT_COLOR


# Une colonne = un rôle, nommé une fois ici : la construction des lignes, le
# routage du double-clic et le tri s'y réfèrent tous les trois.
COL_CAT, COL_SEC, COL_VAR, COL_KEY, COL_CONTENT, COL_STATUS, COL_USED = range(7)
_HEADERS = ("Category", "Section", "Variant", "Key", "Content", "Status", "Used")
# Les trois premières colonnes SONT les trois niveaux du chemin, dans l'ordre.
_PATH_COLS = (COL_CAT, COL_SEC, COL_VAR)

_ROLE_TEXT = Qt.ItemDataRole.UserRole        # Text, sur une ligne
_ROLE_GROUP = Qt.ItemDataRole.UserRole + 1   # str, sur une ligne d'en-tête
_ROLE_SORT = Qt.ItemDataRole.UserRole + 2    # clé de tri, quand ≠ de l'affichage

# Ce que la ligne raconte d'elle-même, indépendamment du filtre.
FLAG_EMPTY = "empty"      # référencée peut-être, mais rien à afficher
FLAG_UNUSED = "unused"    # écrite, mais personne ne la demande
# N'existe que pendant qu'on TRADUIT une langue — cf. `_apply_filter`. Distinct
# de FLAG_EMPTY : une entrée non traduite affiche la SOURCE (donc rarement
# vide), et une entrée traduite peut très bien être vide. Deux axes, deux
# flags, comme le veut la ROADMAP v0.9.
FLAG_MISSING = "missing"

# Catégorie des textes rangés à la racine. Entre parenthèses : ce n'est pas un
# libellé que quelqu'un a écrit, c'est l'absence de libellé.
NO_CATEGORY = "(unfiled)"


class _CategoryDelegate(QStyledItemDelegate):
    """Peint la catégorie en pastille plutôt qu'en texte nu.

    Le premier niveau se répète sur des dizaines de lignes consécutives : en
    texte, il ajoute du bruit à chaque ligne ; en pastille, l'œil le lit comme
    la bordure d'un bloc et saute directement au contenu."""

    def paint(self, painter: QPainter, option, index):
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        # Le fond de sélection est peint par la vue pour les autres colonnes :
        # sans ce rappel, la ligne sélectionnée aurait un trou ici.
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(C.BG_SEL))
        if not label:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        w = min(painter.fontMetrics().horizontalAdvance(label) + 12,
                max(option.rect.width() - 8, 16))
        r = QRectF(option.rect.left() + 6, option.rect.center().y() - 7.0, w, 15.0)
        painter.setPen(QPen(QColor(C.BORDER_MID)))
        painter.setBrush(QBrush(QColor(C.BG_RAISED)))
        painter.drawRoundedRect(r, 3, 3)
        painter.setPen(QPen(QColor(C.TEXT_DIM)))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class _Row(QTreeWidgetItem):
    """Une ligne qui se trie par ce qu'elle VAUT, pas par ce qu'elle affiche.

    « 12 scripts » se range avant « 2 scripts » dans l'ordre alphabétique, et
    une colonne d'usage qui trie faux est pire qu'une colonne qui ne trie
    pas."""

    def __lt__(self, other):
        tree = self.treeWidget()
        col = tree.sortColumn() if tree is not None else 0
        a, b = self.data(col, _ROLE_SORT), other.data(col, _ROLE_SORT)
        if a is not None and b is not None:
            return a < b
        return self.text(col).casefold() < other.text(col).casefold()


class TextTable(QWidget):
    """La table des textes, ses filtres et son groupement.

    Vue seulement : elle signale ce qui a été édité, le panneau décide."""

    selection_changed = pyqtSignal(list)               # [Text] (vide = plus rien)
    key_edited = pyqtSignal(object, str)               # (Text, clé saisie)
    path_edited = pyqtSignal(object, int, str)         # (Text, niveau, segment)
    group_renamed = pyqtSignal(str, str)               # (catégorie, nouveau nom)
    add_asked = pyqtSignal()
    delete_asked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._usages = None            # TextUsageIndex, None = à reconstruire
        self._blocking = False
        self._values: dict = {}
        # "" = source. Reçue de l'extérieur — cf. `set_active_lang` — la table
        # ne CHOISIT plus la langue depuis la v0.9.2 : les onglets de l'atelier
        # s'en chargent, elle en tire juste ce que Content/Status/le chip
        # « Missing » doivent montrer.
        self._active_lang = ""
        # Groupes explicitement REPLIÉS, et non l'inverse : une catégorie qui
        # vient d'apparaître doit s'ouvrir seule, sinon le texte semble perdu.
        self._collapsed: set[str] = set()
        self._flags: dict[int, set[str]] = {}    # {id du texte: {FLAG_*}}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_bar())

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_HEADERS))
        self._tree.setHeaderLabels(_HEADERS)
        self._tree.setRootIsDecorated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setAllColumnsShowFocus(True)
        # Multi-sélection : ranger vingt entrées d'un coup est le geste que le
        # glisser-déposer d'un arbre ne savait pas faire.
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        # Aucun déclencheur automatique : le double-clic est routé à la main
        # vers les colonnes ÉDITABLES — jamais vers le contenu, qui est un
        # rendu (balises résolues) et non la source.
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setItemDelegateForColumn(COL_CAT, _CategoryDelegate(self))
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.UI_STACK}; font-size:{T.MD}px; outline:none;}}"
            f"QTreeWidget::item{{padding:2px 4px; height:{S.ROW}px;"
            f"border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{TEXT_COLOR};}}"
            f"QTreeWidget::item:hover:!selected{{background:{C.BG_PANEL};}}"
            f"QHeaderView::section{{background:transparent; color:{C.TEXT_MUTED};"
            f"border:none; border-bottom:1px solid {C.BORDER_DARK}; padding:4px 6px;"
            f"font-family:{T.UI_STACK}; font-size:{T.XS}px; font-weight:700;"
            f"letter-spacing:1px;}}"
            f"QHeaderView::section:hover{{color:{C.TEXT_DIM};}}"
        )
        th = self._tree.header()
        for col in (COL_CAT, COL_SEC, COL_VAR, COL_KEY):
            th.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        th.setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(COL_USED, QHeaderView.ResizeMode.ResizeToContents)
        for col, width in ((COL_CAT, 110), (COL_SEC, 130), (COL_VAR, 100),
                           (COL_KEY, 190)):
            self._tree.setColumnWidth(col, width)
        # Colonne muette tant qu'on n'édite pas une traduction : un projet
        # monolingue — le cas de tous ceux d'avant la v0.9 — ne voit rien de
        # nouveau. `refresh_languages()` la révèle en même temps que la barre.
        self._tree.setColumnHidden(COL_STATUS, True)
        self._tree.setSortingEnabled(True)
        # Un ordre de départ EXPLICITE : la table est triée dès qu'elle est
        # triable, et laisser Qt choisir donnait le rangement à l'envers.
        self._tree.sortByColumn(COL_CAT, Qt.SortOrder.AscendingOrder)
        self._tree.itemSelectionChanged.connect(self._on_sel)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemExpanded.connect(lambda it: self._on_fold(it, False))
        self._tree.itemCollapsed.connect(lambda it: self._on_fold(it, True))
        root.addWidget(self._tree, 1)
        root.addWidget(self._build_footer())

    # ── Barres ────────────────────────────────────────────────────

    def _build_bar(self) -> QFrame:
        hdr = W.finder_bar("Texts")
        hl = hdr.layout()
        self._count = QLabel("")
        self._count.setFont(QFont(T.MONO, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hl.addWidget(self._count)
        hl.addStretch()

        # Deux axes, deux filtres cumulables — pas une pastille unique. Une
        # entrée peut être écrite ET orpheline, ou référencée ET vide : les
        # fondre ferait disparaître celui des deux qui n'a pas la priorité.
        self._chips: dict[str, QToolButton] = {}
        for flag, label, tip in (
            (FLAG_EMPTY, "Empty", "Entries with no content yet"),
            (FLAG_UNUSED, "Unused",
             "Entries no script and no layout refers to"),
            # Ajouté ici pour vivre dans le même style, mais caché tant qu'on
            # n'édite pas une traduction — `refresh_languages()` le révèle.
            (FLAG_MISSING, "Missing", "Entries not yet translated"),
        ):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setFont(QFont(T.UI, T.XS))
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QToolButton{{background:transparent; color:{C.TEXT_DIM};"
                f"border:1px solid {C.BORDER}; border-radius:9px; padding:1px 8px;}}"
                f"QToolButton:hover{{color:{C.TEXT_NORM}; border-color:{C.BORDER_MID};}}"
                f"QToolButton:checked{{background:{C.BG_SEL}; color:{TEXT_COLOR};"
                f"border-color:{TEXT_COLOR};}}"
            )
            b.toggled.connect(lambda _c: self._apply_filter())
            hl.addWidget(b)
            self._chips[flag] = b
        self._chips[FLAG_MISSING].setVisible(False)

        self._search = W.search_box("Filter: key, filing or content…")
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(lambda _q: self._apply_filter())
        hl.addWidget(self._search)

        # Coché > survolé > au repos — `HoverIconButton` recolore son icône
        # elle-même aux trois états (cf. ui/common/widgets.py).
        self._btn_group = HoverIconButton(
            "folder", C.TEXT_DIM, C.ACCENT, checked=icons.COLOR_FOLDER)
        self._btn_group.setCheckable(True)
        self._btn_group.setFixedSize(22, 22)
        self._btn_group.setStyleSheet(BTN_ICON)
        self._btn_group.setToolTip(
            "Group by category — folds the table back into its filing.\n"
            "Sorting then applies inside each group.")
        self._btn_group.toggled.connect(self._on_group_toggled)
        hl.addWidget(self._btn_group)

        self._btn_add = W.btn_add("New text (filed where the selection is)")
        self._btn_add.clicked.connect(self.add_asked.emit)
        hl.addWidget(self._btn_add)
        self._btn_del = W.btn_danger("Delete the selected texts")
        self._btn_del.clicked.connect(self.delete_asked.emit)
        self._btn_del.setEnabled(False)
        hl.addWidget(self._btn_del)
        return hdr

    def _build_footer(self) -> QFrame:
        """Ce que la sélection couvre et ce que le filtre cache : deux nombres
        qu'on ne peut pas deviner en regardant des lignes."""
        bar = QFrame()
        bar.setFixedHeight(20)
        bar.setStyleSheet(
            f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        self._sel_lbl = QLabel("")
        self._sel_lbl.setFont(QFont(T.UI, T.XS))
        self._sel_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bl.addWidget(self._sel_lbl)
        bl.addStretch()
        self._total_lbl = QLabel("")
        self._total_lbl.setFont(QFont(T.UI, T.XS))
        self._total_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bl.addWidget(self._total_lbl)
        return bar

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        self._project = project
        self._values = project.text_values() if project else {}
        self._usages = None
        self._active_lang = ""
        self.refresh()

    def invalidate_usages(self):
        """Les scripts ont bougé : l'index est périmé.

        Reconstruit paresseusement, au prochain `refresh` — luaparser est trop
        lent pour être relancé sur un écran qui n'est peut-être pas affiché."""
        self._usages = None

    def _usage_index(self):
        if self._usages is None and self._project is not None:
            self._usages = self._project.text_usage_index()
        return self._usages

    # ── Langue en cours d'édition ────────────────────────────────
    # Choisie par les ONGLETS de l'atelier (`TextWorkbench`), jamais ici : la
    # table en tire seulement ce que Content/Status/le chip « Missing »
    # doivent montrer. `TextPanel` est le relais entre les deux.

    def active_lang(self) -> str:
        return self._active_lang

    def is_translating(self) -> bool:
        """Vrai quand la langue active est une TRADUCTION — pas la source, pas
        « aucune langue déclarée ». C'est ce qui décide si Status et le chip
        « Missing » ont un sens."""
        p = self._project
        return bool(self._active_lang and p
                    and self._active_lang != p.settings.source_lang.code)

    def set_active_lang(self, code: str):
        """La langue éditée change — appelé par le panneau, lui-même averti
        par les onglets de l'atelier."""
        if code == self._active_lang:
            return
        self._active_lang = code
        translating = self.is_translating()
        self._tree.setColumnHidden(COL_STATUS, not translating)
        self._chips[FLAG_MISSING].setVisible(translating)
        if not translating:
            self._chips[FLAG_MISSING].setChecked(False)
        self.refresh()

    def refresh(self, select_ids: Optional[list[int]] = None):
        """Reconstruit la table depuis le projet, sélection conservée."""
        if select_ids is None:
            select_ids = [t.id for t in self.selected_texts()]
        self._blocking = True
        # Le tri se rétablit APRÈS le remplissage : trier à chaque insertion
        # est quadratique, et Qt le refait de toute façon en une passe.
        col, order = (self._tree.sortColumn(),
                      self._tree.header().sortIndicatorOrder())
        self._tree.setSortingEnabled(False)
        self._tree.clear()
        texts = list(self._project.texts) if self._project else []
        usages = self._usage_index()
        self._flags = {}

        groups: dict[str, QTreeWidgetItem] = {}
        for t in texts:
            row = _Row()
            self._fill_row(row, t, usages)
            if self._btn_group.isChecked():
                cat = t.path[0] if t.path else NO_CATEGORY
                parent = groups.get(cat) or self._make_group(cat, groups)
                parent.addChild(row)
                # La catégorie est portée par l'en-tête : la répéter sur chaque
                # ligne est précisément ce que grouper sert à éviter.
                row.setText(COL_CAT, "")
            else:
                self._tree.addTopLevelItem(row)

        for cat, item in groups.items():
            n = item.childCount()
            # Le compte se pose CONTRE le nom, pas au bout de la ligne : une
            # ligne d'en-tête n'est pas une entrée, ses colonnes ne portent pas
            # le sens qu'elles ont ailleurs.
            item.setText(COL_SEC, f"{n} text{'s' if n > 1 else ''}")
            item.setExpanded(cat not in self._collapsed)

        self._tree.setSortingEnabled(True)
        self._tree.sortItems(col, order)
        self._count.setText(f"  {len(texts)}")
        self._apply_filter()
        self._blocking = False

        if select_ids:
            self.select_by_ids(select_ids)
        self._on_sel()

    def _make_group(self, cat: str, groups: dict) -> QTreeWidgetItem:
        """Ligne d'en-tête d'une catégorie — un CLASSEUR, jamais une entrée."""
        item = _Row(self._tree)
        item.setText(COL_CAT, cat)
        item.setData(0, _ROLE_GROUP, cat)
        item.setIcon(COL_CAT, icons.get("folder", icons.COLOR_FOLDER))
        item.setForeground(COL_SEC, QColor(C.TEXT_MUTED))
        item.setToolTip(
            COL_CAT,
            "Texts filed at the root — this is the absence of a category,\n"
            "not a name: it cannot be renamed. File them from the level 1\n"
            "field below." if cat == NO_CATEGORY else
            "Double-click to rename this category — it renames the filing of\n"
            "every text it contains.")
        groups[cat] = item
        return item

    def retitle_group(self, old: str, new: str):
        """Reporte l'état replié sur le nouveau nom d'une catégorie.

        Sans ça, renommer un groupe replié le rouvrirait — le pliage était
        mémorisé sous l'ancien nom."""
        if old in self._collapsed:
            self._collapsed.discard(old)
            self._collapsed.add(new)

    def _fill_row(self, row: QTreeWidgetItem, t, usages):
        """Une ligne : où c'est rangé, comment ça s'appelle, ce que ça dit, et
        qui s'en sert."""
        for lvl, col in enumerate(_PATH_COLS):
            seg = t.path[lvl] if lvl < len(t.path) else ""
            row.setText(col, seg)
            if col != COL_CAT:
                row.setForeground(col, QColor(C.TEXT_DIM if seg else C.TEXT_MUTED))
        row.setData(0, _ROLE_TEXT, t)
        row.setToolTip(
            COL_SEC, "Filing — accents, spaces and duplicates allowed.\n"
                     "Never resolved, never referenced: it organizes the table\n"
                     "and suggests the key, without ever owning it.")

        row.setText(COL_KEY, t.key)
        row.setFont(COL_KEY, QFont(T.CODE, T.SM))
        # Clé dérivée = jetable, en retrait ; clé nommée à la main = un contrat
        # posé par quelqu'un, elle mérite l'accent.
        row.setForeground(COL_KEY,
                          QColor(C.TEXT_MUTED if t.auto_key else TEXT_COLOR))
        row.setToolTip(COL_KEY,
                       ("Automatic key — follows the filing" if t.auto_key
                        else "Named by hand — independent of the filing")
                       + "\nDouble-click to name it by hand.")

        flags = set()
        # Le texte tel qu'on le LIT dans la langue ACTIVE : balises retirées,
        # valeurs substituées, et — hors source — repli sur la source tant que
        # rien n'est traduit (`Project.text_content`, point unique de la
        # règle : "" comme langue inconnue rendent tous les deux la source).
        # Le balisage, lui, s'édite dans l'atelier.
        content = (self._project.text_content(t, self._active_lang)
                  if self._project else t.content)
        display = resolve(parse(content), self._values).replace("\n", " ⏎ ")
        row.setText(COL_CONTENT, display or "(empty)")
        row.setForeground(COL_CONTENT,
                          QColor(C.TEXT_HI if display else C.ACCENT_YLW))
        if not display:
            flags.add(FLAG_EMPTY)

        if self.is_translating():
            translated = bool(self._project.translations
                              .get(self._active_lang, {}).get(t.id, ""))
            row.setText(COL_STATUS, "Translated" if translated else "Missing")
            row.setForeground(COL_STATUS,
                              QColor(C.TEXT_DIM if translated else C.ACCENT_YLW))
            row.setData(COL_STATUS, _ROLE_SORT, 1 if translated else 0)
            if not translated:
                flags.add(FLAG_MISSING)

        use = usages.get(t.key) if usages is not None else None
        if usages is not None and not usages.scripts_scanned:
            # Sans luaparser, l'index ne sait pas : il le DIT. Afficher zéro
            # ferait passer tout le projet pour orphelin, et un orphelin, ça
            # se supprime.
            row.setText(COL_USED, "?")
            row.setForeground(COL_USED, QColor(C.TEXT_MUTED))
            row.setToolTip(COL_USED, "Scripts could not be parsed — "
                                     "usage is unknown, not zero.")
            row.setData(COL_USED, _ROLE_SORT, -1)
        elif use is not None and use.count:
            row.setText(COL_USED, use.summary())
            row.setForeground(COL_USED, QColor(C.TEXT_DIM))
            row.setToolTip(COL_USED, use.detail())
            row.setData(COL_USED, _ROLE_SORT, use.count)
        else:
            row.setText(COL_USED, "unused")
            row.setForeground(COL_USED, QColor(C.TEXT_MUTED))
            row.setToolTip(COL_USED,
                           "No script and no layout refers to this key.")
            row.setData(COL_USED, _ROLE_SORT, 0)
            flags.add(FLAG_UNUSED)
        self._flags[t.id] = flags

    def update_content(self, t, display: str):
        """Recale la cellule de contenu pendant la frappe, sans reconstruire.

        L'atelier édite la SOURCE ; la table montre le RENDU. Elle doit suivre
        la frappe, mais reconstruire la table à chaque caractère perdrait la
        sélection et le tri."""
        row = self._row_of(t)
        if row is None:
            return
        self._blocking = True
        row.setText(COL_CONTENT, display or "(empty)")
        row.setForeground(COL_CONTENT,
                          QColor(C.TEXT_HI if display else C.ACCENT_YLW))
        self._blocking = False

    # ── Sélection ─────────────────────────────────────────────────

    def selected_texts(self) -> list:
        """Les `Text` sélectionnés, dans l'ordre de la table. Les lignes de
        groupe et les lignes masquées par le filtre n'en sont pas."""
        return [t for it in self._tree.selectedItems()
                if not it.isHidden()
                and (t := it.data(0, _ROLE_TEXT)) is not None]

    def selected_path(self) -> list[str]:
        """Rangement courant — sert au « + » : la nouvelle entrée naît là où on
        regarde."""
        items = self._tree.selectedItems()
        if not items:
            return []
        t = items[0].data(0, _ROLE_TEXT)
        if t is not None:
            return list(t.path)
        cat = items[0].data(0, _ROLE_GROUP)
        return [cat] if cat and cat != NO_CATEGORY else []

    def select_by_ids(self, ids: list[int]):
        self._blocking = True
        self._tree.clearSelection()
        wanted, first = set(ids), None
        for item in self._iter_rows():
            t = item.data(0, _ROLE_TEXT)
            if t is not None and t.id in wanted:
                if first is None:
                    # La ligne courante D'ABORD : `setCurrentItem` remplace la
                    # sélection, l'appeler après aurait réduit un lot de vingt
                    # entrées à une seule.
                    first = item
                    self._tree.setCurrentItem(item)
                item.setSelected(True)
        if first is not None:
            self._tree.scrollToItem(first)
        self._blocking = False

    def clear_selection(self):
        """Vide la sélection sans rien émettre — l'écran bascule de contexte,
        ce n'est pas l'utilisateur qui a désélectionné."""
        self._blocking = True
        self._tree.clearSelection()
        self._tree.setCurrentItem(None)
        self._blocking = False
        self._update_footer()

    def _row_of(self, t) -> Optional[QTreeWidgetItem]:
        for item in self._iter_rows():
            if item.data(0, _ROLE_TEXT) is t:
                return item
        return None

    def _iter_rows(self, parent: Optional[QTreeWidgetItem] = None):
        node = parent if parent is not None else self._tree.invisibleRootItem()
        for i in range(node.childCount()):
            child = node.child(i)
            yield child
            yield from self._iter_rows(child)

    def _on_sel(self):
        if self._blocking:
            return
        texts = self.selected_texts()
        self._btn_del.setEnabled(bool(texts))
        self._update_footer()
        self.selection_changed.emit(texts)

    def _update_footer(self):
        n = len(self.selected_texts())
        self._sel_lbl.setText(f"{n} selected" if n else "")
        total = len(self._project.texts) if self._project else 0
        shown = sum(1 for it in self._iter_rows()
                    if it.data(0, _ROLE_TEXT) is not None and not it.isHidden())
        self._total_lbl.setText(
            f"{total} text{'s' if total > 1 else ''}" if shown == total
            else f"{shown} of {total} shown")

    # ── Filtre et groupement ──────────────────────────────────────

    def _apply_filter(self):
        """Masque ce qui ne correspond pas ; une ligne d'en-tête survit tant
        qu'un de ses textes survit."""
        q = self._search.text().strip().casefold()
        wanted = {f for f, b in self._chips.items() if b.isChecked()}
        was_blocking, self._blocking = self._blocking, True

        def visit(item: QTreeWidgetItem) -> bool:
            t = item.data(0, _ROLE_TEXT)
            hits = [visit(item.child(i)) for i in range(item.childCount())]
            if t is None:
                item.setHidden(not any(hits))
                return any(hits)
            hay = " ".join((item.text(c) for c in
                            (COL_CAT, COL_SEC, COL_VAR, COL_KEY, COL_CONTENT))
                           ).casefold()
            # Les deux chips se CUMULENT : « Empty » + « Unused » demande les
            # entrées qui sont les deux, pas leur réunion.
            visible = ((not q) or (q in hay)) and \
                      wanted <= self._flags.get(t.id, set())
            item.setHidden(not visible)
            return visible

        for i in range(self._tree.invisibleRootItem().childCount()):
            visit(self._tree.invisibleRootItem().child(i))
        self._blocking = was_blocking
        self._update_footer()

    def _on_group_toggled(self, on: bool):
        # L'icône se recolore d'elle-même (`HoverIconButton`, cf. `_build_bar`).
        # Grouper trie d'abord par catégorie : un tri sur une autre colonne ne
        # survivrait pas au regroupement, autant repartir du rangement.
        self._tree.setRootIsDecorated(on)
        self._tree.sortItems(COL_CAT if on else COL_KEY,
                             Qt.SortOrder.AscendingOrder)
        self.refresh()

    def _on_fold(self, item: QTreeWidgetItem, collapsed: bool):
        cat = item.data(0, _ROLE_GROUP)
        if self._blocking or cat is None:
            return
        self._collapsed.add(cat) if collapsed else self._collapsed.discard(cat)

    # ── Édition en place ──────────────────────────────────────────

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        """Édition sur place, jamais de boîte de dialogue.

        S'édite : les trois niveaux de rangement, la clé, et le nom d'une
        catégorie (qui range alors tout ce qu'elle contient). Le contenu, lui,
        est un RENDU — sa source s'édite dans l'atelier, en dessous."""
        is_group = item.data(0, _ROLE_GROUP) is not None
        editable = (col == COL_CAT) if is_group else (col in _PATH_COLS or
                                                      col == COL_KEY)
        if not editable:
            return
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.editItem(item, col)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        """Fin d'édition — la table SIGNALE, elle n'écrit pas.

        `setFlags` ré-émet `itemChanged` comme `setText` : sans le garde, le
        handler se rappelle indéfiniment. Et le panneau reconstruit la table en
        réponse, ce qui DÉTRUIT l'item dont on traite le signal — d'où le
        report d'un tour de boucle, sans quoi Qt revient dans un objet libéré.
        """
        if self._blocking:
            return
        self._blocking = True
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._blocking = False
        typed = item.text(col).strip()

        cat = item.data(0, _ROLE_GROUP)
        if cat is not None:
            if not typed or typed == cat or cat == NO_CATEGORY:
                self._reset_cell(item, col, cat)
                return
            QTimer.singleShot(0, lambda: self.group_renamed.emit(cat, typed))
            return

        t = item.data(0, _ROLE_TEXT)
        if t is None:
            return
        if col == COL_KEY:
            if not typed or typed == t.key:
                self._reset_cell(item, col, t.key)
                return
            QTimer.singleShot(0, lambda: self.key_edited.emit(t, typed))
            return
        lvl = _PATH_COLS.index(col)
        if typed == (t.path[lvl] if lvl < len(t.path) else ""):
            return
        QTimer.singleShot(0, lambda: self.path_edited.emit(t, lvl, typed))

    def _reset_cell(self, item: QTreeWidgetItem, col: int, value: str):
        """Repose la valeur d'origine après une saisie vide ou inchangée."""
        self._blocking = True
        item.setText(col, value)
        self._blocking = False
