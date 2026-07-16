"""
ui/widgets.py — Bibliothèque de widgets réutilisables pour les éditeurs de components.

Usage dans un éditeur de component (ou plugin) :
    from ui.common.widgets import W

    W.row("Frame", fw_widget, layout)
    W.pair("Offset", "X", C.AXIS_X, sp_x, "Y", C.AXIS_Y, sp_y, layout)
    W.section("CALLBACKS", layout)
    W.separator(layout)

    btn = W.btn_ghost("Choisir…")
    btn = W.btn_accent("Ouvrir")
    btn = W.btn_danger("×")


    W.callback_row("onCollisionEnter", comp, "on_collision_enter", register_syncer, set_field, layout)
"""
from __future__ import annotations
from typing import Callable, Any

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QToolButton, QCheckBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QScrollArea, QApplication, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QHBoxLayout, QVBoxLayout, QSizePolicy,
)
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal

from ui.common.theme import C, T


# ── Constantes de style ───────────────────────────────────────────────

_FONT_MONO_SM  = QFont(T.MONO, T.SM)
_FONT_MONO_XS  = QFont(T.MONO, T.XS)
_FONT_MONO_AX  = QFont(T.MONO, T.MD, QFont.Weight.Bold)   # axes X/Y/W/H

_LBL_STY    = f"color:{C.TEXT_DIM}; background:transparent; border:none;"
_LBL_AX_STY = "color:{c}; background:transparent; border:none;"

BTN_GHOST = (
    f"QPushButton{{color:{C.TEXT_DIM};background:transparent;"
    f"border:1px solid {C.BORDER};border-radius:3px;"
    f"font-family:{T.MONO};font-size:{T.SM}px;padding:2px 6px;}}"
    f"QPushButton:hover{{color:{C.TEXT_HI};background:{C.BG_HOVER};border-color:#555;}}"
    f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
)
BTN_ACCENT = (
    f"QPushButton{{color:{C.ACCENT_GRN};background:transparent;"
    f"border:1px solid {C.ACCENT_GRN};border-radius:3px;"
    f"font-family:{T.MONO};font-size:{T.SM}px;padding:2px 6px;}}"
    f"QPushButton:hover{{color:{C.BG_DEEP};background:{C.ACCENT_GRN};}}"
    f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
)
BTN_DANGER = (
    f"QToolButton{{color:{C.TEXT_NORM};background:transparent;border:none;"
    f"font-family:{T.MONO};font-size:{T.XL}px;padding:0;}}"
    f"QToolButton:hover{{color:{C.ACCENT_RED};}}"
    f"QToolButton:pressed{{color:#ff3030;}}"
)

# Bouton icône sans bordure (+ ajout, ⌕ recherche) — même style que project panel
BTN_ICON = (
    f"QToolButton{{color:{C.TEXT_DIM};background:transparent;border:none;"
    f"font-size:{T.XXL}px;padding:0 3px;}}"
    f"QToolButton:hover{{color:{C.ACCENT_GRN};}}"
    f"QToolButton:pressed{{color:{C.ACCENT_GRN};opacity:0.7;}}"
)


# ── Factory class (namespace) ─────────────────────────────────────────

class _W:
    """Toutes les fonctions retournent le widget principal pour chaînage."""

    # ── Boutons ───────────────────────────────────────────────────────

    def btn_ghost(self, text: str) -> QPushButton:
        """Bouton discret (actions secondaires : Choisir, Nouveau…)."""
        b = QPushButton(text); b.setStyleSheet(BTN_GHOST); return b

    def btn_accent(self, text: str) -> QPushButton:
        """Bouton contour coloré (action principale : Ouvrir, Créer…)."""
        b = QPushButton(text); b.setStyleSheet(BTN_ACCENT); return b

    def btn_danger(self, tooltip: str = "") -> QToolButton:
        """Bouton × danger (supprimer, détacher…). Visible au repos, rouge au survol."""
        b = QToolButton()
        b.setText("×")
        b.setStyleSheet(BTN_DANGER)
        b.setFixedSize(22, 22)
        if tooltip:
            b.setToolTip(tooltip)
        return b

    def btn_add(self, tooltip: str = "Ajouter") -> QToolButton:
        """Bouton + sans bordure, survol vert — style project panel."""
        b = QToolButton()
        b.setText("+")
        b.setStyleSheet(BTN_ICON)
        b.setFixedSize(24, 24)
        b.setToolTip(tooltip)
        return b

    def btn_search(self, tooltip: str = "Rechercher") -> QToolButton:
        """Bouton ⌕ sans bordure, survol vert — style project panel."""
        b = QToolButton()
        b.setText("⌕")
        b.setStyleSheet(BTN_ICON)
        b.setFixedSize(24, 24)
        b.setToolTip(tooltip)
        return b

    def search_box(self, placeholder: str = "Filtrer par nom…") -> QLineEdit:
        """Champ de filtre par nom — apparaît sous un header au clic sur btn_search()."""
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(24)
        e.setFont(_FONT_MONO_SM)
        e.setStyleSheet(
            f"QLineEdit{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;"
            f"font-family:{T.MONO};font-size:{T.SM}px;padding:2px 6px;}}"
            f"QLineEdit:focus{{border-color:{C.ACCENT_GRN};}}"
        )
        return e

    def filter_tree(self, tree: QTreeWidget, query: str):
        """
        Filtre les items d'un QTreeWidget par sous-chaîne du nom (insensible
        à la casse). Un item reste visible si son propre texte correspond ou
        si un de ses descendants correspond (l'ancêtre est alors déplié pour
        garder le résultat visible). query vide → tout réafficher.
        """
        query = query.strip().lower()

        def _apply(item: QTreeWidgetItem) -> bool:
            self_match = query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if _apply(item.child(i)):
                    child_match = True
            visible = (not query) or self_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            _apply(root.child(i))

    def filter_table(self, table, query: str, name_col: int = 0):
        """
        Filtre les lignes d'un QTableWidget par sous-chaîne du nom (colonne
        name_col), insensible à la casse. query vide → tout réafficher.
        """
        query = query.strip().lower()
        for row in range(table.rowCount()):
            item = table.item(row, name_col)
            text = item.text() if item else ""
            table.setRowHidden(row, bool(query) and query not in text.lower())

    # ── Ligne label + widget ──────────────────────────────────────────

    def row(self, label: str, widget: QWidget, layout: QVBoxLayout,
            label_width: int = 76) -> QWidget:
        """
        Ligne horizontale : « label »  [ widget ]
        Retourne le widget pour usage ultérieur.
        """
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        r = QHBoxLayout(container)
        r.setSpacing(8); r.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label); lbl.setFont(_FONT_MONO_SM)
        lbl.setStyleSheet(_LBL_STY); lbl.setFixedWidth(label_width)
        r.addWidget(lbl); r.addWidget(widget, 1)
        layout.addWidget(container)
        return widget

    # ── Paire d'inputs avec axes colorés ─────────────────────────────

    def pair(self, row_label: str,
             ax1: str, color1: str, widget1: QWidget,
             ax2: str, color2: str, widget2: QWidget,
             layout: QVBoxLayout,
             label_width: int = 76) -> tuple[QWidget, QWidget]:
        """
        Ligne :  « row_label »  AX1 [widget1]  AX2 [widget2]
        Axes colorés (ex: X rouge, Y bleu).
        Retourne (widget1, widget2).
        """
        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        r = QHBoxLayout(inner); r.setSpacing(4); r.setContentsMargins(0, 0, 0, 0)
        for ax, col, w in ((ax1, color1, widget1), (ax2, color2, widget2)):
            lbl = QLabel(ax); lbl.setFont(_FONT_MONO_AX)
            lbl.setStyleSheet(_LBL_AX_STY.format(c=col))
            lbl.setFixedWidth(14)
            r.addWidget(lbl); r.addWidget(w, 1)
        self.row(row_label, inner, layout, label_width)
        return widget1, widget2

    # ── Checkbox inline ───────────────────────────────────────────────

    def checkbox_row(self, row_label: str, check_label: str,
                     layout: QVBoxLayout) -> QCheckBox:
        """
        Ligne :  « row_label »  ☑ check_label
        Retourne le QCheckBox.
        """
        chk = QCheckBox(check_label)
        chk.setFont(_FONT_MONO_SM)
        chk.setStyleSheet(f"color:{C.TEXT_NORM}; background:transparent;")
        self.row(row_label, chk, layout)
        return chk

    # ── Séparateur horizontal ─────────────────────────────────────────

    def separator(self, layout: QVBoxLayout, margin_v: int = 4) -> QFrame:
        """Séparateur horizontal fin."""
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background:{C.BORDER}; border:none; margin:{margin_v}px 0;"
        )
        layout.addWidget(sep)
        return sep

    # ── En-tête de sous-section ───────────────────────────────────────

    def section(self, text: str, layout: QVBoxLayout) -> QLabel:
        """Petit titre de sous-section (ex: 'CALLBACKS SOLID')."""
        lbl = QLabel(text); lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(
            f"color:{C.TEXT_DIM}; letter-spacing:1px;"
            f"background:transparent; border:none;"
        )
        layout.addWidget(lbl)
        return lbl

    # ── Ligne callback Lua ────────────────────────────────────────────

    def callback_row(self, display_label: str, default_fn: str,
                     comp: Any, field_name: str,
                     register_syncer: Callable, set_field: Callable,
                     layout: QVBoxLayout) -> QWidget:
        """
        Ligne callback Lua :  « display_label »  [ onFunctionName ]
        Le QLineEdit est en vert GBA sur fond sombre.
        Retourne le container QWidget.
        """
        le = QLineEdit(getattr(comp, field_name, default_fn))
        le.setFont(_FONT_MONO_SM)
        le.setPlaceholderText(default_fn)
        le.setStyleSheet(
            f"color:{C.ACCENT_GRN}; background:{C.BG_DEEP};"
            f"border:1px solid {C.BORDER_DARK}; border-radius:3px; padding:2px 5px;"
        )
        le.textChanged.connect(
            lambda v, f=field_name, d=default_fn: set_field(comp, f, v or d))
        register_syncer(field_name, lambda v, w=le: (
            w.blockSignals(True), w.setText(str(v)), w.blockSignals(False)))

        container = QWidget(); container.setStyleSheet("background:transparent;")
        r = QHBoxLayout(container)
        r.setContentsMargins(0, 1, 0, 1); r.setSpacing(8)
        lbl = QLabel(display_label); lbl.setFont(_FONT_MONO_SM)
        lbl.setStyleSheet(_LBL_STY); lbl.setFixedWidth(76)
        r.addWidget(lbl); r.addWidget(le, 1)
        layout.addWidget(container)
        return container

    # ── Barre méta (id + Active) ──────────────────────────────────────

    def meta_bar(self, comp: Any,
                 field_syncers: dict,
                 set_comp_fn: Callable,
                 layout: QVBoxLayout) -> tuple[QLineEdit, QCheckBox]:
        """
        Barre horizontale compacte :  id [ … ]  ☑ Active
        Enregistre automatiquement les syncers pour 'id' et 'active'.
        Retourne (id_edit, active_cb).
        """
        meta = QWidget()
        meta.setStyleSheet(
            f"background:{C.BG_PANEL}; border-radius:3px; border:1px solid {C.BORDER_DARK};"
        )
        ml = QHBoxLayout(meta); ml.setContentsMargins(8, 4, 8, 4); ml.setSpacing(10)

        id_lbl = QLabel("id"); id_lbl.setFont(_FONT_MONO_SM)
        id_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")

        id_edit = QLineEdit(comp.id); id_edit.setFont(_FONT_MONO_SM)
        id_edit.setPlaceholderText("id…")
        id_edit.editingFinished.connect(lambda: set_comp_fn(comp, "id", id_edit.text()))
        field_syncers["id"] = lambda v, w=id_edit: (
            w.blockSignals(True), w.setText(str(v)), w.blockSignals(False))

        active_cb = QCheckBox("Active"); active_cb.setFont(_FONT_MONO_SM)
        active_cb.setChecked(comp.active)
        active_cb.toggled.connect(lambda v: set_comp_fn(comp, "active", v))
        field_syncers["active"] = lambda v, w=active_cb: (
            w.blockSignals(True), w.setChecked(bool(v)), w.blockSignals(False))

        ml.addWidget(id_lbl); ml.addWidget(id_edit, 1); ml.addWidget(active_cb)
        layout.addWidget(meta)
        return id_edit, active_cb

    # ── Texte inerte (message, hint) ─────────────────────────────────

    def hint(self, text: str, layout: QVBoxLayout,
             color: str = C.TEXT_MUTED) -> QLabel:
        """Label informatif discret."""
        lbl = QLabel(text); lbl.setFont(_FONT_MONO_SM)
        lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        return lbl

    # ── Spinbox standard ──────────────────────────────────────────────

    def double_spinbox(self, value: float = 0.0,
                       min_v: float = -9999.0, max_v: float = 9999.0,
                       step: float = 0.1, decimals: int = 2) -> QDoubleSpinBox:
        """QDoubleSpinBox précâblé, même style que spinbox."""
        from ui.common.theme import QSS as _QSS
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setValue(value)
        sp.setFont(QFont(T.MONO, T.MD))
        sp.setStyleSheet(_QSS.spinbox)
        return sp

    def combobox(self, items: list[str], current: str = "") -> QComboBox:
        """QComboBox précâblé avec les items donnés."""
        from ui.common.theme import QSS as _QSS
        cb = QComboBox()
        cb.addItems(items)
        if current in items:
            cb.setCurrentIndex(items.index(current))
        cb.setFont(QFont(T.MONO, T.MD))
        cb.setStyleSheet(_QSS.combobox)
        return cb

    def spinbox(self, value: int = 0,
                min_v: int = -512, max_v: int = 512,
                step: int = 1) -> QSpinBox:
        """
        QSpinBox précâblé, visuellement identique à ceux du Transform.
        Applique explicitement QSS.spinbox pour ne pas dépendre de la cascade parent.
        """
        from ui.common.theme import QSS as _QSS
        sp = QSpinBox()
        sp.setRange(min_v, max_v); sp.setSingleStep(step)
        sp.setValue(value)
        sp.setFont(QFont(T.MONO, T.MD))
        sp.setStyleSheet(_QSS.spinbox)
        return sp


W = _W()
"""Instance globale — importer W et utiliser W.row(), W.btn_ghost(), etc."""


# ── ScriptSlot ────────────────────────────────────────────────────────
# Widget réutilisable : bouton "+" pointillé quand vide,
# ligne (nom · Éditer · ×) quand un script est assigné.

class ScriptSlot(QWidget):
    """
    Slot d'assignation de script réutilisable.

    États :
      - vide  → bouton "＋ <add_label>" dashed, cliquable
      - actif → label nom + btn "Éditer" + btn "×"

    Signaux émis via callbacks :
      on_add()    → l'utilisateur clique "＋"
      on_open()   → l'utilisateur clique "Éditer"
      on_clear()  → l'utilisateur clique "×"

    Appeler set_script(name) / clear_script() pour changer l'état.
    """

    def __init__(self, add_label: str, accent_color: str,
                 hint: str = "", edit_label: str = "Éditer",
                 show_clear: bool = True, parent=None):
        super().__init__(parent)
        self._color = accent_color

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # ── Bouton "+" ────────────────────────────────────────────
        self._btn_add = QPushButton(f"＋  {add_label}")
        self._btn_add.setFont(QFont(T.MONO, T.MD))
        self._btn_add.setFixedHeight(36)
        self._btn_add.setStyleSheet(
            f"QPushButton{{background:{C.BG_DEEP};color:{C.TEXT_DIM};"
            f"border:1px dashed {C.BORDER};border-radius:4px;}}"
            f"QPushButton:hover{{color:{accent_color};border-color:{accent_color};}}"
        )
        root.addWidget(self._btn_add)

        # ── Ligne active ──────────────────────────────────────────
        self._active_w = QWidget()
        hl = QHBoxLayout(self._active_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)

        self._icon_lbl = QLabel("")
        self._icon_lbl.setFixedSize(16, 16)
        self._icon_lbl.setVisible(False)

        self._lbl = QLabel("")
        self._lbl.setFont(QFont(T.MONO, T.SM))
        self._lbl.setStyleSheet(f"color:{accent_color}; background:transparent; border:none;")

        self._btn_edit = QPushButton(edit_label)
        self._btn_edit.setFont(QFont(T.MONO, T.SM))
        self._btn_edit.setFixedHeight(22)
        self._btn_edit.setStyleSheet(BTN_ACCENT)

        self._btn_clear = QToolButton()
        self._btn_clear.setText("×")
        self._btn_clear.setFont(QFont(T.MONO, T.XL))
        self._btn_clear.setStyleSheet(BTN_DANGER)

        hl.addWidget(self._icon_lbl)
        hl.addWidget(self._lbl, 1)
        hl.addWidget(self._btn_edit)
        hl.addWidget(self._btn_clear)
        root.addWidget(self._active_w)
        # setVisible() APRÈS avoir été ajouté au layout (donc parenté) :
        # appelé avant, sur un QToolButton encore sans parent, Qt le montre
        # brièvement comme une vraie fenêtre top-level ("micro popup" observé
        # à l'ouverture d'un projet / à la sélection d'un sprite).
        self._btn_clear.setVisible(show_clear)
        self._active_w.setVisible(False)

        # ── Hint ──────────────────────────────────────────────────
        if hint:
            lbl_hint = QLabel(hint)
            lbl_hint.setFont(QFont(T.MONO, T.XS))
            lbl_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
            root.addWidget(lbl_hint)

        # ── Connexions internes ───────────────────────────────────
        self._on_add   = None
        self._on_open  = None
        self._on_clear = None
        self._btn_add.clicked.connect(self._click_add)
        self._btn_edit.clicked.connect(self._click_open)
        self._btn_clear.clicked.connect(self._click_clear)

    def set_callbacks(self, on_add=None, on_open=None, on_clear=None):
        self._on_add   = on_add
        self._on_open  = on_open
        self._on_clear = on_clear

    def set_script(self, name: str, icon: QIcon | None = None):
        self._lbl.setText(name)
        if icon is not None:
            self._icon_lbl.setPixmap(icon.pixmap(16, 16))
            self._icon_lbl.setVisible(True)
        else:
            self._icon_lbl.setVisible(False)
        self._btn_add.setVisible(False)
        self._active_w.setVisible(True)

    def clear_script(self):
        self._lbl.setText("")
        self._icon_lbl.setVisible(False)
        self._btn_add.setVisible(True)
        self._active_w.setVisible(False)

    def _click_add(self):
        if self._on_add: self._on_add()

    def _click_open(self):
        if self._on_open: self._on_open()

    def _click_clear(self):
        if self._on_clear: self._on_clear()


# ── ScriptPickerPopup ─────────────────────────────────────────────────────────

class ScriptPickerPopup(QFrame):
    """
    Dropdown flottant pour choisir ou créer un script.

    Signaux :
        picked(rel_path: str)  — l'utilisateur a sélectionné un script existant
        new_requested()        — l'utilisateur clique "Nouveau script"
    """

    picked        = pyqtSignal(str)   # chemin relatif au projet
    new_requested = pyqtSignal()

    def __init__(self, scripts: list[tuple], accent: str, parent=None,
                 new_label: str | None = "＋  Nouveau script"):
        """
        scripts   : liste de (nom_affichage, valeur) ou (nom_affichage, valeur, QIcon)
                    — le 3e élément (icône par ligne) est optionnel, pour les
                    pickers qui ont une identité visuelle (palettes, sprites...).
        accent    : couleur d'accentuation (hex)
        new_label : texte du bouton de création en bas du popup ; None pour
                    l'omettre (ex: picker qui ne propose que des éléments déjà
                    existants, sans création à la volée).
        """
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # Normalise en (display, valeur, icone|None) — accepte les anciens
        # appels à 2-tuples sans modification.
        self._scripts = [(e[0], e[1], e[2] if len(e) > 2 else None) for e in scripts]
        self._accent  = accent

        self.setFixedWidth(260)
        self.setStyleSheet(
            f"QFrame{{background:{C.BG_PANEL};border:1px solid {accent};"
            f"border-radius:6px;}}"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Barre de recherche ─────────────────────────────────────
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrer…")
        self._search.setFont(QFont(T.MONO, T.SM))
        self._search.setStyleSheet(
            f"QLineEdit{{background:{C.BG_DEEP};color:{C.TEXT_NORM};border:1px solid {C.BORDER};"
            f"border-radius:3px;padding:3px 6px;}}"
            f"QLineEdit:focus{{border-color:{accent};}}"
        )
        root.addWidget(self._search)

        # ── Zone scrollable des scripts ────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll)

        # ── Séparateur + bouton de création (optionnels) ────────────
        if new_label is not None:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{C.BORDER};")
            root.addWidget(sep)

            btn_new = QPushButton(new_label)
            btn_new.setFont(QFont(T.MONO, T.SM))
            btn_new.setFixedHeight(28)
            btn_new.setStyleSheet(
                f"QPushButton{{background:{C.BG_DEEP};color:{accent};"
                f"border:1px solid {accent};border-radius:3px;}}"
                f"QPushButton:hover{{background:{accent};color:{C.BG_DEEP};}}"
            )
            btn_new.clicked.connect(self._on_new)
            root.addWidget(btn_new)

        self._search.textChanged.connect(self._filter)
        self._filter("")
        self._search.setFocus()

    # ── Internals ─────────────────────────────────────────────────

    def _filter(self, text: str):
        query = text.lower().strip()
        # Vider la liste
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        matches = [(d, r, i) for d, r, i in self._scripts if query in d.lower()]

        if not matches:
            lbl = QLabel("Aucun résultat")
            lbl.setFont(QFont(T.MONO, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED};padding:4px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(lbl)
        else:
            for display, rel, icon in matches:
                btn = QPushButton(display)
                btn.setFont(QFont(T.MONO, T.SM))
                btn.setFixedHeight(26)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                if icon is not None:
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(16, 16))
                btn.setStyleSheet(
                    f"QPushButton{{background:transparent;color:{C.TEXT_NORM};"
                    f"border:none;border-radius:3px;text-align:left;padding:0 6px;}}"
                    f"QPushButton:hover{{background:{C.BG_DEEP};color:{self._accent};}}"
                )
                btn.clicked.connect(lambda checked, r=rel: self._on_pick(r))
                self._list_layout.addWidget(btn)

        self._list_layout.addStretch()

    def _on_pick(self, rel: str):
        self.picked.emit(rel)
        self.close()

    def _on_new(self):
        self.new_requested.emit()
        self.close()

    # ── Positionnement ────────────────────────────────────────────

    def show_below(self, anchor: QWidget):
        """Affiche le popup sous le widget anchor."""
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        # Éviter de sortir à droite de l'écran — celui de l'ancre (pas
        # forcément l'écran primaire : la fenêtre peut être sur un 2e moniteur).
        screen = anchor.screen() or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        if pos.x() + self.width() > geo.right():
            pos.setX(geo.right() - self.width() - 4)
        self.move(pos)
        self.show()


# ──────────────────────────────────────────────────────────────────
#  FinderSection — en-tête de section collapsible commun aux 4 finders
#  (Assets finder / Sprite finder / Script finder / Sound finder)
# ──────────────────────────────────────────────────────────────────

class FinderSection(QFrame):
    """
    Section collapsible standard : flèche ▾/▸ + titre coloré en gras,
    boutons "+" et "recherche" à droite, champ de filtre masqué par défaut.
    Le filtre s'applique automatiquement à tout QTreeWidget posé via
    set_widget() (recherche par nom sur les colonnes de l'arbre).

    Utilisée par les 4 finders pour une apparence et un comportement
    identiques — voir assets_finder_panel.py pour l'exemple de référence.
    """

    add_clicked = pyqtSignal()

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{C.BG_BASE};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — le clic sur la zone texte/flèche toggle, les boutons sont indépendants
        hdr = QFrame()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background:{C.BG_PANEL}; border-top:1px solid #232323;"
            f"border-bottom:1px solid #232323;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 6, 0)

        # Zone cliquable pour toggle (flèche fixe + titre)
        toggle_area = QWidget()
        toggle_area.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ta_layout = QHBoxLayout(toggle_area)
        ta_layout.setContentsMargins(6, 0, 0, 0)
        ta_layout.setSpacing(6)

        self._arrow_lbl = QLabel("▾")
        self._arrow_lbl.setFixedWidth(12)
        self._arrow_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow_lbl.setStyleSheet(f"color:{color}; font-size:{T.SM}pt; font-weight:bold; background:transparent;")

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{color}; font-family:{T.MONO}; font-size:{T.SM}pt;"
            f"font-weight:bold; letter-spacing:1px; background:transparent;"
        )

        ta_layout.addWidget(self._arrow_lbl)
        ta_layout.addWidget(title_lbl, 1)

        toggle_area.mousePressEvent = lambda e: self._toggle()
        self._color = color
        self._title = title

        self._btn_add = W.btn_add("Ajouter un élément")
        self._btn_add.clicked.connect(self.add_clicked)

        self._btn_search = W.btn_search("Filtrer par nom")
        self._btn_search.setCheckable(True)
        self._btn_search.toggled.connect(self._on_search_toggled)

        hl.addWidget(toggle_area, 1)
        hl.addWidget(self._btn_add)
        hl.addWidget(self._btn_search)
        root.addWidget(hdr)

        # Champ de filtre — masqué par défaut, révélé par btn_search
        self._search_box = W.search_box(f"Filtrer {title.lower()}…")
        self._search_box.textChanged.connect(self._apply_filter)
        _orig_keypress = self._search_box.keyPressEvent
        def _search_key_press(e, _orig=_orig_keypress):
            if e.key() == Qt.Key.Key_Escape:
                self._btn_search.setChecked(False)
            else:
                _orig(e)
        self._search_box.keyPressEvent = _search_key_press
        search_row = QWidget()
        search_row.setStyleSheet(f"background:{C.BG_BASE};")
        sr_layout = QHBoxLayout(search_row)
        sr_layout.setContentsMargins(6, 4, 6, 4)
        sr_layout.addWidget(self._search_box)
        self._search_row = search_row
        self._search_row.setVisible(False)
        root.addWidget(self._search_row)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{C.BG_BASE};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

    def set_add_tooltip(self, tooltip: str):
        self._btn_add.setToolTip(tooltip)

    def set_add_visible(self, visible: bool):
        self._btn_add.setVisible(visible)

    def set_search_visible(self, visible: bool):
        self._btn_search.setVisible(visible)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._arrow_lbl.setText("▾" if self._expanded else "▸")

    def _on_search_toggled(self, checked: bool):
        self._search_row.setVisible(checked)
        if checked:
            self._search_box.setFocus()
        else:
            self._search_box.clear()  # déclenche _apply_filter("") via textChanged

    def _apply_filter(self, query: str):
        for tree in self._body.findChildren(QTreeWidget):
            W.filter_tree(tree, query)
        for table in self._body.findChildren(QTableWidget):
            W.filter_table(table, query)

    def set_widget(self, w: QWidget):
        """Remplace le contenu de la section par w."""
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            old = item.widget()
            if old:
                # hide() avant setParent(None) : un widget visible détaché de
                # son parent redevient une fenêtre top-level à part entière.
                old.hide()
                old.setParent(None)
                old.deleteLater()
        self._body_layout.addWidget(w)
        if self._search_box.text():
            self._apply_filter(self._search_box.text())


# ──────────────────────────────────────────────────────────────────
#  AssetHeaderBar — en-tête unifié "type + nom" pour l'objet sélectionné
# ──────────────────────────────────────────────────────────────────

def _kind_colors(accent: str) -> tuple[str, str, str]:
    """Dérive (fond sombre, couleur du label TYPE, couleur du nom) depuis une
    seule couleur d'accent canonique (voir ui/icons.py), pour que toute la
    palette dérive d'une unique source par type d'objet."""
    from PyQt6.QtGui import QColor
    c = QColor(accent)
    h, s, _v, _a = c.getHsv()
    bg  = QColor.fromHsv(h, max(0, int(s * 0.55)), 22).name()
    mid = QColor.fromHsv(h, s, 150).name()
    return bg, mid, accent


class AssetHeaderBar(QWidget):
    """
    En-tête réutilisable affichant le type et le nom (renommable) de l'objet
    actuellement sélectionné — même template/couleurs/renommage partout
    (Scene Manager, Sprite Editor, Sound Mixer, Script Editor).

    Couleurs pilotées par `kind`, dérivées des couleurs canoniques de
    ui/icons.py (mêmes couleurs que les icônes du project panel).

    Usage :
        header = AssetHeaderBar()
        header.renamed.connect(lambda new_name: ...)
        header.set_header("actor", "ACTOR", actor.name, editable=True)
    """

    renamed = pyqtSignal(str)   # nouveau nom, émis quand l'utilisateur valide

    _PALETTE: dict[str, tuple[str, str, str]] = {}  # rempli au premier accès (import tardif)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "empty"
        self._editable = False

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(0)
        self.setFixedHeight(44)

        self._type_lbl = QLabel("")
        self._type_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))

        self._name_edit = QLineEdit("")
        self._name_edit.setFont(QFont(T.MONO, T.XXL, QFont.Weight.Bold))
        self._name_edit.setFrame(False)
        self._name_edit.setReadOnly(True)
        self._name_edit.editingFinished.connect(self._on_editing_finished)

        col = QVBoxLayout(); col.setSpacing(1)
        col.addWidget(self._type_lbl)
        col.addWidget(self._name_edit)
        root.addLayout(col, 1)

        self.set_header("empty", "", "")

    @classmethod
    def _palette(cls) -> dict[str, tuple[str, str, str]]:
        if not cls._PALETTE:
            from ui.common import icons
            cls._PALETTE = {
                "actor":  _kind_colors(icons.COLOR_ACTOR),
                "prefab": _kind_colors(icons.COLOR_PREFAB),
                "scene":  _kind_colors(icons.COLOR_SCENE),
                "camera": _kind_colors(icons.COLOR_SCENE),
                "script": _kind_colors(icons.COLOR_SCRIPT),
                "sprite": _kind_colors(icons.COLOR_SPRITE),
                "background": _kind_colors(icons.COLOR_BACKGROUND),
                "sfx":    _kind_colors(icons.COLOR_SFX),
                "music":  _kind_colors(icons.COLOR_MUSIC),
                "uses":   _kind_colors(icons.COLOR_PREFAB),
                "empty":  ("#161616", "#333333", "#555555"),
            }
        return cls._PALETTE

    def set_header(self, kind: str, type_text: str, name_text: str, editable: bool = True):
        """kind : clé de palette (voir _palette()). editable=False → lecture seule
        (ex: caméra, ou un contexte où le renommage se fait ailleurs)."""
        bg, tc, nc = self._palette().get(kind, self._palette()["empty"])
        editable = editable and kind != "empty"
        self.setStyleSheet(f"background:{bg};")
        self._type_lbl.setStyleSheet(f"color:{tc}; font-size:8pt; font-weight:bold;")
        self._name_edit.setStyleSheet(
            f"background:transparent; color:{nc}; font-size:13pt; font-weight:bold;"
            f"border:none; border-bottom:1px solid {'rgba(255,255,255,30)' if editable else 'transparent'};"
            f"padding:0;"
        )
        self._name_edit.setReadOnly(not editable)
        self._name_edit.setCursor(
            Qt.CursorShape.IBeamCursor if editable else Qt.CursorShape.ArrowCursor
        )
        self._type_lbl.setText(type_text)
        self._name_edit.setText(name_text)
        self._kind = kind
        self._editable = editable

    def set_name(self, name_text: str):
        """Met à jour uniquement le nom affiché (ex: après renommage externe)."""
        self._name_edit.setText(name_text)

    def _on_editing_finished(self):
        if not self._editable:
            return
        new_name = self._name_edit.text().strip()
        if new_name:
            self.renamed.emit(new_name)
