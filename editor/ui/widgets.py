"""
ui/widgets.py — Bibliothèque de widgets réutilisables pour les éditeurs de components.

Usage dans un éditeur de component (ou plugin) :
    from ui.widgets import W

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
    QDoubleSpinBox, QComboBox, QScrollArea, QApplication,
    QHBoxLayout, QVBoxLayout, QSizePolicy,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QPoint, pyqtSignal

from ui.theme import C, T


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
        from ui.theme import QSS as _QSS
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
        from ui.theme import QSS as _QSS
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
        from ui.theme import QSS as _QSS
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
                 hint: str = "", parent=None):
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

        self._lbl = QLabel("")
        self._lbl.setFont(QFont(T.MONO, T.SM))
        self._lbl.setStyleSheet(f"color:{accent_color}; background:transparent; border:none;")

        self._btn_edit = QPushButton("Éditer")
        self._btn_edit.setFont(QFont(T.MONO, T.SM))
        self._btn_edit.setFixedHeight(22)
        self._btn_edit.setStyleSheet(BTN_ACCENT)

        self._btn_clear = QToolButton()
        self._btn_clear.setText("×")
        self._btn_clear.setFont(QFont(T.MONO, T.XL))
        self._btn_clear.setStyleSheet(BTN_DANGER)

        hl.addWidget(self._lbl, 1)
        hl.addWidget(self._btn_edit)
        hl.addWidget(self._btn_clear)
        root.addWidget(self._active_w)
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

    def set_script(self, name: str):
        self._lbl.setText(name)
        self._btn_add.setVisible(False)
        self._active_w.setVisible(True)

    def clear_script(self):
        self._lbl.setText("")
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

    def __init__(self, scripts: list[tuple[str, str]], accent: str, parent=None):
        """
        scripts : liste de (nom_affichage, chemin_relatif)
        accent  : couleur d'accentuation (hex)
        """
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._scripts = scripts          # [(display, rel_path), ...]
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

        # ── Séparateur ─────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{C.BORDER};")
        root.addWidget(sep)

        # ── Bouton "Nouveau script" ────────────────────────────────
        btn_new = QPushButton(f"＋  Nouveau script")
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

        matches = [(d, r) for d, r in self._scripts if query in d.lower()]

        if not matches:
            lbl = QLabel("Aucun résultat")
            lbl.setFont(QFont(T.MONO, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_MUTED};padding:4px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(lbl)
        else:
            for display, rel in matches:
                btn = QPushButton(display)
                btn.setFont(QFont(T.MONO, T.SM))
                btn.setFixedHeight(26)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        # Éviter de sortir à droite de l'écran
        screen = QApplication.primaryScreen().availableGeometry()
        if pos.x() + self.width() > screen.right():
            pos.setX(screen.right() - self.width() - 4)
        self.move(pos)
        self.show()
