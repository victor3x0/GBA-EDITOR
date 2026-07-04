"""
editor/ui/script_editor.py — Écran d'édition de scripts Lua pour acteurs GBA.

Layout :
┌──────────────────────────────────────────────────────────────┐
│  ← Retour   Hero.lua                             [Enregistrer]│
├───────────────────┬──────────────────────────────────────────┤
│  ▾ EVENTS         │                                          │
│    ● on_start     │   function on_start()                    │
│    ○ on_update    │       self:play_anim("idle")             │
│                   │   end                                    │
│  ▾ API            │                                          │
│    Mouvement      │   function on_update()                   │
│    self:move()    │       ...                                │
│    ...            │   end                                    │
│  ▾ RÉFÉRENCES     │                                          │
│    Scènes         │                                          │
│    Actors         │                                          │
│    Scripts        │                                          │
│    Prefabs        │                                          │
└───────────────────┴──────────────────────────────────────────┘
"""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QPlainTextEdit, QLineEdit, QFrame,
    QScrollArea, QSizePolicy, QToolButton, QInputDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QAbstractItemView,
    QMenu,
)
from PyQt6.QtGui import (
    QFont, QColor, QSyntaxHighlighter, QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRegularExpression, QFileSystemWatcher, QPoint, QEvent, QSize

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripting.api import KNOWN_EVENTS, KNOWN_SCENE_EVENTS
from ui.theme import C, T
from ui.icons import COLOR_SCRIPT, COLOR_EVENT, COLOR_BEHAVIOR, COLOR_GLOBAL, COLOR_CONST
from ui.build_panel import BuildPanel
from ui.widgets import FinderSection


# ── Couleurs — proxy vers le thème global ────────────────────────────
_BG       = C.BG_PANEL    # fond sidebar / body
_BG_HDR   = C.BG_PANEL    # fond headers de section
_BG_HOVER = C.BG_HOVER    # état survol
_BORDER   = C.BORDER      # séparateurs
_TEXT_DIM   = C.TEXT_DIM  # labels discrets
_TEXT_NORM  = C.TEXT_NORM # texte courant
_TEXT_HI    = C.TEXT_HI   # texte mis en avant
_C_API      = C.ACCENT_ORG  # orange — API Lua
_C_REF      = C.ACCENT_BLU  # bleu — références projet
_C_SUB      = C.TEXT_MUTED  # sous-labels grisés
# Couleurs de catégorie du script editor — centralisées dans ui/icons.py
# (pas de type d'objet dédié dans COMPONENT/PROJECT panel pour ces concepts).
_C_EVENT    = COLOR_EVENT
_C_BEHAVIOR = COLOR_BEHAVIOR
_C_GLOBAL   = COLOR_GLOBAL
_C_CONST    = COLOR_CONST
_BG_SEL_REF = "#1a2a3a"   # fond "sélectionné" pour fichiers/refs — dérivé de _C_REF


# ─── Syntaxe Lua ──────────────────────────────────────────────────────

class LuaHighlighter(QSyntaxHighlighter):

    _KEYWORDS = (
        r"\bfunction\b", r"\bend\b", r"\bif\b", r"\bthen\b",
        r"\belseif\b", r"\belse\b", r"\bwhile\b", r"\bdo\b",
        r"\bfor\b", r"\breturn\b", r"\blocal\b", r"\band\b",
        r"\bor\b", r"\bnot\b", r"\btrue\b", r"\bfalse\b",
        r"\bnil\b", r"\bbreak\b", r"\bin\b", r"\brepeat\b",
        r"\buntil\b",
    )
    _API_MODULES = (
        r"\bself\b", r"\bsfx\b", r"\bmusic\b",
        r"\binput\b", r"\bglobal\b", r"\bsend\b", r"\bbroadcast\b",
        r"\bcamera\b", r"\bdisplay\b", r"\bmath\b",
    )

    def __init__(self, doc):
        super().__init__(doc)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        def fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:   f.setFontWeight(700)
            if italic: f.setFontItalic(True)
            return f

        kw_fmt = fmt("#c586c0", bold=True)
        for p in self._KEYWORDS:
            self._rules.append((QRegularExpression(p), kw_fmt))

        api_fmt = fmt("#4ec9b0")
        for p in self._API_MODULES:
            self._rules.append((QRegularExpression(p), api_fmt))

        self._rules.append((QRegularExpression(r"\b0x[0-9a-fA-F]+\b|\b\d+\.?\d*\b"),
                            fmt("#b5cea8")))
        self._str_fmt = fmt("#ce9178")
        self._rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), self._str_fmt))
        self._rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), self._str_fmt))
        self._cmt_fmt = fmt("#6a9955", italic=True)
        self._rules.append((QRegularExpression(r"--[^\n]*"), self._cmt_fmt))

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ─── Éditeur de code ──────────────────────────────────────────────────

class LuaEditor(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont(T.CODE, T.LG)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            f"QPlainTextEdit{{"
            f"  background:{C.BG_RAISED}; color:{C.TEXT_HI};"
            f"  border:none; padding:4px;"
            f"}}"
        )
        self.setTabStopDistance(32)
        self._hl = LuaHighlighter(self.document())

    def jump_to_function(self, func_name: str):
        doc = self.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            if f"function {func_name}" in block.text():
                cur = QTextCursor(block)
                cur.movePosition(QTextCursor.MoveOperation.NextBlock)
                cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cur)
                self.ensureCursorVisible()
                return

    def insert_at_cursor(self, text: str):
        """Insère text à la position courante du curseur."""
        cur = self.textCursor()
        cur.insertText(text)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        self.setFocus()

    def insert_stub(self, stub: str):
        """Insère un stub en fin de document, saute au corps."""
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if not self.toPlainText().endswith("\n"):
            cur.insertText("\n")
        cur.insertText("\n" + stub)
        self.setTextCursor(cur)
        self.ensureCursorVisible()


# ─── Sidebar ──────────────────────────────────────────────────────────

_BTN_BASE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE_SEL = (
    f"QPushButton{{color:{_C_REF};background:{_BG_SEL_REF};border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_C_REF};background:{_BG_SEL_REF};}}"
)
_BTN_EVENT_DEFINED = (
    f"QPushButton{{color:{_C_EVENT};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;font-weight:bold;}}"
    f"QPushButton:hover{{background:{_BG_HOVER};}}"
)
_BTN_API = (
    f"QPushButton{{color:{_C_API};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_REF = (
    f"QPushButton{{color:{_C_REF};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_BEHAVIOR = (
    f"QPushButton{{color:{_C_BEHAVIOR};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)


from scripting.api import EVENT_REGISTRY as _EVENT_META


def _event_tooltip(name: str) -> str:
    meta = _EVENT_META.get(name, {})
    desc = meta.get("desc", "")
    params = meta.get("params", [])
    stub_sig = f"function {name}(" + ", ".join(p["name"] for p in params) + ")"

    lines = [
        f"<b style='font-family:Consolas,monospace;color:{_C_EVENT}'>{stub_sig}</b>",
        f"<p style='color:{_TEXT_NORM};margin:4px 0'>{desc}</p>",
    ]
    if params:
        lines.append("<table cellspacing='2' style='margin-top:4px'>")
        for p in params:
            lines.append(
                f"<tr>"
                f"<td style='font-family:Consolas,monospace;color:{C.ACCENT_ORG}'>{p['name']}</td>"
                f"<td style='color:{_TEXT_DIM};padding:0 6px'>{p['type']}</td>"
                f"<td style='color:{_TEXT_DIM}'>{p['description']}</td>"
                f"</tr>"
            )
        lines.append("</table>")
    lines.append(f"<p style='color:{_C_SUB};margin-top:6px;font-size:9px'>? doc (bientôt disponible)</p>")
    return "".join(lines)


class _Section(QWidget):
    """Section collapsible avec header cliquable."""

    def __init__(self, title: str, color: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(26)
        hdr.setStyleSheet(
            f"background:{_BG_HDR};border-top:1px solid {_BORDER};"
            f"border-bottom:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        self._toggle = QPushButton()
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{color};border:none;background:transparent;"
            f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:0 4px 0 4px;}}"
            f"QPushButton:hover{{background:{_BG_HOVER};}}"
        )
        self._toggle.setText(f"▾  {title}")
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._do_toggle)
        self._color = color
        self._title = title
        hl.addWidget(self._toggle)
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 2, 0, 4)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._toggle.setText(f"{'▾' if self._expanded else '▸'}  {self._title}")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)

    def clear_body(self):
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def sub_label(self, text: str) -> QLabel:
        """Sous-label statique (utilisé pour RÉFÉRENCES)."""
        lbl = QLabel(f"  {text}")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(
            f"color:{_C_SUB};background:{_BG_HDR};"
            f"border-bottom:1px solid {_BORDER};padding:3px 0;"
        )
        lbl.setFixedHeight(18)
        self._body_layout.addWidget(lbl)
        return lbl

    def sub_section(self, text: str) -> "_SubSection":
        """Sous-section collapsible (utilisé pour les catégories API)."""
        ss = _SubSection(text)
        self._body_layout.addWidget(ss)
        return ss


class _SubSection(QWidget):
    """Sous-section collapsible (catégories API, ou dossiers du file tree si icon_key donné)."""

    def __init__(self, title: str, expanded: bool = False, icon_key: str | None = None, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toggle = QPushButton()
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{_C_SUB};border:none;background:{_BG_HDR};"
            f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:2px 4px 2px 8px;}}"
            f"QPushButton:hover{{color:{_TEXT_NORM};background:{_BG_HOVER};}}"
        )
        self._toggle.setFixedHeight(20)
        if icon_key:
            from ui.icons import get as _ico, COLOR_FOLDER
            self._toggle.setIcon(_ico(icon_key, COLOR_FOLDER))
            self._toggle.setIconSize(QSize(13, 13))
        self._toggle.setText(f"▾ {title}")
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._do_toggle)
        self._title = title
        root.addWidget(self._toggle)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        arrow = "▾" if self._expanded else "▸"
        self._toggle.setText(f"{arrow} {self._title}")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)


class _EntryButton(QPushButton):
    """Bouton d'entrée sidebar avec tooltip riche, icône optionnelle (ui/icons.py)."""

    def __init__(self, label: str, style: str, tooltip_html: str,
                 icon_key: str | None = None, icon_color: str | None = None, parent=None):
        super().__init__(label, parent)
        self.setFont(QFont(T.CODE, T.MD))
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(style)
        self.setToolTip(tooltip_html)
        self._icon_key = icon_key
        if icon_key:
            self.setIconSize(QSize(15, 15))
            self.set_icon_color(icon_color or _TEXT_DIM)

    def set_icon_color(self, color: str):
        """Recolore l'icône — QSS ne peut pas teinter un QIcon, contrairement au texte."""
        if self._icon_key:
            from ui.icons import get as _ico
            self.setIcon(_ico(self._icon_key, color))


# ─── Panneau globals ──────────────────────────────────────────────────

_TBL_SS = f"""
QTableWidget {{
    background:{C.BG_PANEL}; color:{C.TEXT_HI};
    border:none; gridline-color:{C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
    selection-background-color:#264f78; selection-color:#ffffff;
}}
QHeaderView::section {{
    background:{C.BG_PANEL}; color:{C.TEXT_DIM};
    border:none; border-bottom:1px solid {C.BORDER};
    font-family:{T.MONO}; font-size:{T.XS}px;
    padding:2px 4px;
}}
QTableWidget::item {{ padding:1px 4px; }}
QComboBox {{
    background:{C.BG_PANEL}; color:{C.TEXT_HI};
    border:1px solid {C.BORDER};
    font-family:{T.CODE}; font-size:{T.MD}px;
}}
QComboBox QAbstractItemView {{
    background:{C.BG_RAISED}; color:{C.TEXT_HI};
    selection-background-color:#264f78;
}}
"""


class VarTablePanel(QWidget):
    """
    Tableau nom/type/valeur pour GLOBALS ou CONSTANTS, déclarées dans le
    projet. Double-clic sur une ligne → insère un snippet get (et set pour
    les globals) au curseur. Clic droit → même menu + Supprimer.

    Pas de header propre : posé via FinderSection.set_widget() pour la même
    apparence (flèche + titre coloré + boutons +/recherche) que les autres
    finders — le bouton "+" de la section appelle add_var() directement.
    """
    snippet_requested = pyqtSignal(str)
    changed           = pyqtSignal()   # pour notifier le projet de sauvegarder

    def __init__(self, kind: str = "global", parent=None):
        super().__init__(parent)
        self._kind = kind   # "global" | "const"
        self._project = None
        self._updating = False
        self._label = "GLOBALS" if kind == "global" else "CONSTANTS"
        self._color = _C_GLOBAL if kind == "global" else _C_CONST
        value_col = "défaut" if kind == "global" else "valeur"
        self._cols = ["nom", "type", value_col]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Table (3 colonnes : nom / type / défaut ou valeur)
        self._tbl = QTableWidget(0, 3)
        self._tbl.setStyleSheet(_TBL_SS)
        self._tbl.setHorizontalHeaderLabels(self._cols)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tbl.setColumnWidth(1, 46)
        self._tbl.setColumnWidth(2, 46)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._ctx_menu)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.cellDoubleClicked.connect(self._on_double_click)
        self._tbl.setMinimumHeight(80)
        self._tbl.setMaximumHeight(240)
        root.addWidget(self._tbl)

    def _entries(self):
        if not self._project:
            return []
        return self._project.constants if self._kind == "const" else self._project.globals

    def set_project(self, project):
        self._project = project
        self._reload()

    def _reload(self):
        self._updating = True
        self._tbl.setRowCount(0)
        for e in self._entries():
            value = e.value if self._kind == "const" else e.default
            self._append_row(e.name, e.type, str(value))
        self._updating = False

    def _append_row(self, name="var", typ="int", default="0"):
        from PyQt6.QtWidgets import QComboBox
        row = self._tbl.rowCount()
        self._tbl.insertRow(row)
        self._tbl.setRowHeight(row, 20)

        name_item = QTableWidgetItem(name)
        name_item.setForeground(QColor(self._color))
        self._tbl.setItem(row, 0, name_item)

        combo = QComboBox()
        combo.addItems(["int", "bool", "u8", "u16", "s8", "s16"])
        combo.setCurrentText(typ)
        combo.setStyleSheet(_TBL_SS)
        combo.currentTextChanged.connect(lambda _, r=row: self._sync_to_project())
        self._tbl.setCellWidget(row, 1, combo)

        default_item = QTableWidgetItem(str(default))
        default_item.setForeground(QColor("#b5cea8"))
        self._tbl.setItem(row, 2, default_item)

    def _add_var(self):
        if not self._project:
            return
        from core.project import GlobalVar, Constant
        title = "Nouvelle variable globale" if self._kind == "global" else "Nouvelle constante"
        name, ok = QInputDialog.getText(self, title, "Nom :")
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(e.name == name for e in self._entries()):
            QMessageBox.warning(self, "Doublon", f"« {name} » existe déjà.")
            return
        if self._kind == "const":
            self._project.constants.append(Constant(name=name))
        else:
            self._project.globals.append(GlobalVar(name=name))
        self._project.save_settings()
        self._updating = True
        self._append_row(name)
        self._updating = False
        self.changed.emit()

    def _on_item_changed(self, item):
        if self._updating:
            return
        self._sync_to_project()

    def _sync_to_project(self):
        if not self._project or self._updating:
            return
        from core.project import GlobalVar, Constant
        entries = []
        for row in range(self._tbl.rowCount()):
            name_item = self._tbl.item(row, 0)
            combo     = self._tbl.cellWidget(row, 1)
            val_item  = self._tbl.item(row, 2)
            if name_item is None:
                continue
            name  = name_item.text().strip()
            typ   = combo.currentText() if combo else "int"
            value = int(val_item.text() or "0") if val_item else 0
            if not name:
                continue
            if self._kind == "const":
                entries.append(Constant(name=name, type=typ, value=value))
            else:
                entries.append(GlobalVar(name=name, type=typ, default=value))
        if self._kind == "const":
            self._project.constants = entries
        else:
            self._project.globals = entries
        self._project.save_settings()
        self.changed.emit()

    def _snippet_get(self, name: str) -> str:
        return f'const.get("{name}")' if self._kind == "const" else f'global.get("{name}")'

    def _on_double_click(self, row, col):
        name_item = self._tbl.item(row, 0)
        if name_item:
            self.snippet_requested.emit(self._snippet_get(name_item.text()))

    def _ctx_menu(self, pos: QPoint):
        row = self._tbl.rowAt(pos.y())
        if row < 0:
            return
        name_item = self._tbl.item(row, 0)
        if not name_item:
            return
        name = name_item.text()
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_HI};border:1px solid {C.BORDER};}}"
            f"QMenu::item:selected{{background:{C.BG_SEL};}}"
        )
        a_get = menu.addAction(self._snippet_get(name))
        a_set = menu.addAction(f'global.set("{name}", ...)') if self._kind == "global" else None
        menu.addSeparator()
        a_del = menu.addAction("Supprimer")
        action = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if action == a_get:
            self.snippet_requested.emit(self._snippet_get(name))
        elif a_set is not None and action == a_set:
            self.snippet_requested.emit(f'global.set("{name}", )')
        elif action == a_del:
            self._delete_row(row)

    def _delete_row(self, row):
        self._tbl.removeRow(row)
        self._sync_to_project()


# ─── Panneau sidebar principal ────────────────────────────────────────

class SidebarPanel(QWidget):
    """
    Panneau gauche du script editor avec 3 sections collapsibles :
    EVENTS / API / RÉFÉRENCES. Émet snippet_requested(str) à chaque clic.
    """

    snippet_requested = pyqtSignal(str)     # snippet à insérer dans l'éditeur
    stub_requested    = pyqtSignal(str)     # event name → insérer stub ou jumper

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(190)
        self.setMaximumWidth(260)
        self.setStyleSheet(f"background:{_BG};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG};border:none;")

        container = QWidget()
        container.setStyleSheet(f"background:{_BG};")
        self._cl = QVBoxLayout(container)
        self._cl.setContentsMargins(0, 0, 0, 0)
        self._cl.setSpacing(0)

        # ── Section EVENTS ─────────────────────────────────────────
        self._sec_events = _Section("EVENTS", _C_EVENT)
        self._event_btns: dict[str, _EntryButton] = {}
        for ev in KNOWN_EVENTS:
            meta  = _EVENT_META.get(ev, {})
            btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                 icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
            btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
            self._sec_events.add_widget(btn)
            self._event_btns[ev] = btn
        self._cl.addWidget(self._sec_events)

        # ── Section API ─────────────────────────────────────────────
        self._sec_api = _Section("API", _C_API, expanded=False)
        self._build_api_section()
        self._cl.addWidget(self._sec_api)

        # ── Section RÉFÉRENCES ──────────────────────────────────────
        self._sec_refs = _Section("RÉFÉRENCES", _C_REF, expanded=False)
        self._cl.addWidget(self._sec_refs)

        self._cl.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ── API section (statique, depuis api_reference.json) ────────────

    def _build_api_section(self):
        from scripting.api_reference import get_categories, make_tooltip
        for cat in get_categories():
            sub = self._sec_api.sub_section(cat["name"])
            for entry in cat.get("entries", []):
                display = entry['label'].removeprefix("self:")
                label   = f"  {display}"
                tooltip = make_tooltip(entry)
                snippet = entry.get("snippet", entry.get("label", ""))
                btn = _EntryButton(label, _BTN_API, tooltip)
                btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
                sub.add_widget(btn)

    # ── Références (dynamique, depuis le projet) ─────────────────────

    def set_project(self, project):
        """Recharge les sections dynamiques (RÉFÉRENCES) depuis le projet."""
        self._sec_refs.clear_body()
        if not project:
            return

        def _ref_btn(label: str, snippet: str, tip: str) -> _EntryButton:
            btn = _EntryButton(f"  {label}", _BTN_REF, tip)
            btn.clicked.connect(lambda _, s=snippet: self.snippet_requested.emit(s))
            return btn

        def _tip(sig: str, desc: str) -> str:
            return (
                f"<b style='font-family:Consolas,monospace;color:{_C_REF}'>{sig}</b>"
                f"<p style='color:{_TEXT_NORM};margin:4px 0'>{desc}</p>"
            )

        # Scènes
        scenes = list(project.scenes)
        if scenes:
            sub = self._sec_refs.sub_section("Scènes")
            for s in scenes:
                sn = f"scene_goto(\"{s.name}\")"
                sub.add_widget(_ref_btn(s.name, sn, _tip(sn, "Charge et démarre cette scène.")))

        # Actors
        actors = list(project.active_scene.actors) if project.active_scene else []
        if actors:
            sub = self._sec_refs.sub_section("Actors")
            for a in actors:
                sn = f"get_actor(\"{a.name}\")"
                sub.add_widget(_ref_btn(a.name, sn,
                    _tip(sn, "Référence à cet actor dans la scène active.")))

        # Prefabs
        prefabs = list(project.prefabs)
        if prefabs:
            sub = self._sec_refs.sub_section("Prefabs")
            for p in prefabs:
                sn = f"instantiate(\"{p.name}\", x, y)"
                sub.add_widget(_ref_btn(p.name, sn,
                    _tip(sn, f"Instancie le prefab <i>{p.name}</i> à (x, y).")))

        # Sprites
        sprites = list(project.sprites)
        if sprites:
            sub = self._sec_refs.sub_section("Sprites")
            for sp in sprites:
                sn = f"self:play_anim(\"{sp.name}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(sn, f"Joue l'animation du sprite <i>{sp.name}</i>.")))

        # Backgrounds
        bgs = list(project.backgrounds)
        if bgs:
            sub = self._sec_refs.sub_section("Backgrounds")
            for bg in bgs:
                sub.add_widget(_ref_btn(bg.name, f"-- BG: {bg.name}",
                    _tip(bg.name, f"Background <i>{bg.name}</i> — référence éditoriale.")))

        # SFX
        sfx_list = list(project.sfx) if hasattr(project, "sfx") else []
        if sfx_list:
            sub = self._sec_refs.sub_section("SFX")
            for sfx in sfx_list:
                sn = f"sfx.play(\"{sfx.name}\")"
                sub.add_widget(_ref_btn(sfx.name, sn,
                    _tip(sn, f"Joue l'effet sonore <i>{sfx.name}</i>.")))

        # Scripts behaviors
        behaviors_dir = project.scripts_behaviors_dir
        scripts = sorted(behaviors_dir.glob("*.lua")) if behaviors_dir.exists() else []
        if scripts:
            sub = self._sec_refs.sub_section("Scripts")
            for sp in scripts:
                rel = f"behaviors/{sp.stem}"
                sn  = f"local {sp.stem} = require(\"{rel}\")"
                sub.add_widget(_ref_btn(sp.name, sn,
                    _tip(f"require(\"{rel}\")", f"Importe le module behavior <i>{sp.stem}</i>.")))

    # ── Mise à jour état events ───────────────────────────────────────

    def update_defined_events(self, defined: set[str]):
        for ev, btn in self._event_btns.items():
            btn.setText(f"  {ev}")
            if ev in defined:
                btn.setStyleSheet(_BTN_EVENT_DEFINED)
                btn.set_icon_color(_C_EVENT)
            else:
                btn.setStyleSheet(_BTN_BASE)
                btn.set_icon_color(_TEXT_DIM)

    # ── Adaptation contextuelle ───────────────────────────────────────

    def set_context(self, context: str):
        """Adapte les sections selon le type de script (actor/scene/behavior/unknown)."""
        self._event_btns.clear()
        self._sec_events.clear_body()

        if context == "behavior":
            # Remplace EVENTS par MODULE
            self._sec_events._title = "MODULE"
            self._sec_events._color = _C_BEHAVIOR
            self._sec_events._toggle.setStyleSheet(
                f"QToolButton{{color:{_C_BEHAVIOR};border:none;background:transparent;"
                f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
                f"text-align:left;padding:0 4px 0 6px;}}"
                f"QToolButton:hover{{background:{_BG_HOVER};}}"
            )
            self._sec_events._toggle.setText(f"▾  MODULE")

            hint = QLabel("  Pas de handlers — appelé via require()")
            hint.setFont(QFont(T.MONO, T.XS))
            hint.setStyleSheet(f"color:{_TEXT_DIM};background:{_BG};padding:4px 8px;")
            hint.setWordWrap(True)
            self._sec_events.add_widget(hint)

            stub_text = "function M.nom(actor, ...)"
            stub_btn = _EntryButton(f"  {stub_text}", _BTN_BEHAVIOR,
                "<b style='font-family:Consolas,monospace'>function M.nom(actor, ...)</b>"
                f"<p style='color:{_TEXT_NORM}'>Stub de fonction exportée par ce module behavior.</p>",
                icon_key="behavior_stub", icon_color=_C_BEHAVIOR)
            stub_btn.clicked.connect(
                lambda: self.snippet_requested.emit("function M.nom(actor, ...)\n    \nend\n"))
            self._sec_events.add_widget(stub_btn)

            self._sec_refs.setVisible(False)
        else:
            # Restore EVENTS header style
            self._sec_events._title = "EVENTS"
            self._sec_events._color = _C_EVENT
            self._sec_events._toggle.setStyleSheet(
                f"QToolButton{{color:{_C_EVENT};border:none;background:transparent;"
                f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
                f"text-align:left;padding:0 4px 0 6px;}}"
                f"QToolButton:hover{{background:{_BG_HOVER};}}"
            )
            self._sec_events._toggle.setText(f"▾  EVENTS")
            self._sec_refs.setVisible(True)

            events_to_show = KNOWN_SCENE_EVENTS if context == "scene" else KNOWN_EVENTS
            for ev in events_to_show:
                meta  = _EVENT_META.get(ev, {})
                btn   = _EntryButton(f"  {ev}", _BTN_BASE, _event_tooltip(ev),
                                     icon_key=meta.get("icon_key"), icon_color=_TEXT_DIM)
                btn.clicked.connect(lambda _, e=ev: self.stub_requested.emit(e))
                self._sec_events.add_widget(btn)
                self._event_btns[ev] = btn


# ─── Entrée de fichier avec renommage inline ──────────────────────────

class _FileEntryWidget(QWidget):
    """
    Ligne de fichier : clic sur le stem → renommage inline,
    clic sur l'extension ou la ligne → ouvre le fichier.
    """
    file_opened  = pyqtSignal(str)        # path
    file_renamed = pyqtSignal(str, str)   # old_path, new_path

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path
        self._committing = False
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QWidget{background:transparent;}")

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 0, 4, 0)
        root.setSpacing(4)

        # Icône du fichier — même registre que assets_finder_panel.py
        from ui.icons import get as _ico
        icon_key = "script_lua" if path.suffix == ".lua" else "script_file"
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_ico(icon_key, COLOR_SCRIPT).pixmap(QSize(13, 13)))
        icon_lbl.setFixedWidth(16)
        root.addWidget(icon_lbl)

        # Stem cliquable → renommage
        self._name_btn = QPushButton(path.stem)
        self._name_btn.setFont(QFont(T.CODE, T.MD))
        self._name_btn.setStyleSheet(
            f"QPushButton{{color:{_TEXT_DIM};background:transparent;border:none;"
            f"text-align:left;padding:0;}}"
            f"QPushButton:hover{{color:{_TEXT_HI};text-decoration:underline;}}"
        )
        self._name_btn.setCursor(Qt.CursorShape.IBeamCursor)
        self._name_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._name_btn.clicked.connect(self._start_rename)
        root.addWidget(self._name_btn)

        # Extension → ouvre le fichier
        self._ext_lbl = QPushButton(path.suffix)
        self._ext_lbl.setFont(QFont(T.CODE, T.MD))
        self._ext_lbl.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:transparent;border:none;"
            f"text-align:left;padding:0;}}"
        )
        self._ext_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ext_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self._ext_lbl.clicked.connect(self._open_file)
        root.addWidget(self._ext_lbl)

        # Éditeur inline (masqué par défaut) — avant le stretch pour occuper la place
        self._editor = QLineEdit()
        self._editor.setFont(QFont(T.CODE, T.MD))
        self._editor.setFixedHeight(18)
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._editor.setStyleSheet(
            f"QLineEdit{{background:{C.BG_INPUT};color:{C.TEXT_HI};"
            f"border:1px solid {C.ACCENT_GRN};border-radius:2px;padding:0 3px;}}"
        )
        self._editor.hide()
        self._editor.returnPressed.connect(self._finish_rename)
        self._editor.installEventFilter(self)
        root.addWidget(self._editor)

        root.addStretch()

    # ── API ───────────────────────────────────────────────────────────

    def path(self) -> Path:
        return self._path

    def set_selected(self, selected: bool):
        color = _C_REF if selected else _TEXT_DIM
        bg    = _BG_SEL_REF if selected else "transparent"
        self.setStyleSheet(f"QWidget{{background:{bg};}}")
        self._name_btn.setStyleSheet(
            f"QPushButton{{color:{color};background:transparent;border:none;"
            f"text-align:left;padding:0;}}"
            f"QPushButton:hover{{color:{_TEXT_HI};text-decoration:underline;}}"
        )
        self._ext_lbl.setStyleSheet(
            f"QPushButton{{color:{color};background:transparent;border:none;"
            f"text-align:left;padding:0;}}"
        )

    # ── Hover ─────────────────────────────────────────────────────────

    def enterEvent(self, event):
        if "1a2a3a" not in self.styleSheet():
            self.setStyleSheet(f"QWidget{{background:{_BG_HOVER};}}")

    def leaveEvent(self, event):
        if "1a2a3a" not in self.styleSheet():
            self.setStyleSheet("QWidget{background:transparent;}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_file()
        super().mousePressEvent(event)

    # ── Actions ───────────────────────────────────────────────────────

    def _open_file(self):
        self.file_opened.emit(str(self._path))

    def _start_rename(self):
        if self._editor.isVisible():
            return
        self._name_btn.hide()
        self._ext_lbl.hide()
        self._editor.setText(self._path.stem)
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()

    def _finish_rename(self):
        if self._committing:
            return
        self._committing = True
        new_stem = self._editor.text().strip()
        if new_stem and new_stem != self._path.stem:
            new_path = self._path.parent / (new_stem + self._path.suffix)
            if not new_path.exists():
                try:
                    self._path.rename(new_path)
                    old = str(self._path)
                    self._path = new_path
                    self._name_btn.setText(new_stem)
                    self.file_renamed.emit(old, str(new_path))
                except OSError:
                    pass
        self._editor.hide()
        self._name_btn.show()
        self._ext_lbl.show()
        self._committing = False

    def _cancel_rename(self):
        self._editor.hide()
        self._name_btn.show()
        self._ext_lbl.show()

    def eventFilter(self, obj, event):
        if obj is self._editor:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_rename()
                    return True
            elif event.type() == QEvent.Type.FocusOut:
                if not self._committing:
                    self._finish_rename()
        return False


# ─── Panneau arbre de fichiers ────────────────────────────────────────

class ScriptFinderPanel(QWidget):
    """Panneau droit collapsible affichant project/scripts/ en arbre + globals."""

    file_requested    = pyqtSignal(str)   # absolute path of .lua file
    snippet_requested = pyqtSignal(str)   # snippet à insérer dans l'éditeur

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._root_path: Optional[Path] = None
        self._file_entries: dict[str, _FileEntryWidget] = {}
        self._selected_path: Optional[str] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Thin toggle strip ──────────────────────────────────────
        self._strip = QWidget()
        self._strip.setFixedWidth(24)
        self._strip.setStyleSheet(
            f"background:{_BG_HDR};border-left:1px solid {_BORDER};"
        )
        strip_l = QVBoxLayout(self._strip)
        strip_l.setContentsMargins(0, 0, 0, 0)
        strip_l.setSpacing(0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText("‹")
        self._toggle_btn.setFixedWidth(24)
        self._toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._toggle_btn.setStyleSheet(
            f"QToolButton{{color:{_TEXT_NORM};border:none;background:transparent;"
            f"font-size:14px;padding:0;}}"
            f"QToolButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
        )
        self._toggle_btn.clicked.connect(self._do_toggle)
        strip_l.addWidget(self._toggle_btn)
        layout.addWidget(self._strip)

        # ── Tree panel ─────────────────────────────────────────────
        self._tree_panel = QWidget()
        self._tree_panel.setStyleSheet(f"background:{_BG};")
        self._tree_panel.setFixedWidth(200)
        tree_l = QVBoxLayout(self._tree_panel)
        tree_l.setContentsMargins(0, 0, 0, 0)
        tree_l.setSpacing(0)

        # SCRIPT FINDER — même en-tête (flèche + titre coloré + recherche)
        # que les autres finders ; pas de "+" ici (aucune création de script
        # depuis ce panneau, seulement depuis l'Assets finder).
        sec_scripts = FinderSection("SCRIPT FINDER", COLOR_SCRIPT)
        sec_scripts.set_add_visible(False)
        tree_l.addWidget(sec_scripts, 1)

        # Zone scrollable de sous-sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{_BG};border:none;")
        self._sections_widget = QWidget()
        self._sections_widget.setStyleSheet(f"background:{_BG};")
        self._sections_layout = QVBoxLayout(self._sections_widget)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(0)
        self._sections_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._sections_widget)
        sec_scripts.set_widget(scroll)

        # CONSTANTS puis GLOBALS — même ordre et même en-tête que l'Assets finder
        sec_const = FinderSection("CONSTANTS", COLOR_CONST)
        self._constants_panel = VarTablePanel(kind="const")
        self._constants_panel.snippet_requested.connect(self.snippet_requested)
        sec_const.set_widget(self._constants_panel)
        sec_const.add_clicked.connect(self._constants_panel._add_var)
        tree_l.addWidget(sec_const)

        sec_globals = FinderSection("GLOBALS", COLOR_GLOBAL)
        self._globals_panel = VarTablePanel(kind="global")
        self._globals_panel.snippet_requested.connect(self.snippet_requested)
        sec_globals.set_widget(self._globals_panel)
        sec_globals.add_clicked.connect(self._globals_panel._add_var)
        tree_l.addWidget(sec_globals)

        layout.addWidget(self._tree_panel)
        self._tree_panel.setVisible(False)

    def set_project(self, project):
        self._constants_panel.set_project(project)
        self._globals_panel.set_project(project)

    def show_panel(self):
        self._expanded = True
        self._tree_panel.setVisible(True)
        self._toggle_btn.setText("‹")

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._tree_panel.setVisible(self._expanded)
        self._toggle_btn.setText("›" if self._expanded else "‹")

    def set_root(self, scripts_dir: Path):
        self._root_path = scripts_dir
        self._file_entries.clear()
        self._selected_path = None
        while self._sections_layout.count():
            item = self._sections_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not scripts_dir or not scripts_dir.exists():
            return
        self._build_sections(scripts_dir)

    def _build_sections(self, root: Path):
        try:
            entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                sub = _SubSection(entry.name, expanded=True, icon_key="folder")
                self._fill_subsection(sub, entry)
                self._sections_layout.addWidget(sub)
            elif entry.suffix == ".lua":
                self._sections_layout.addWidget(self._make_file_entry(entry))

    def _fill_subsection(self, sub: _SubSection, directory: Path):
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except PermissionError:
            return
        for entry in entries:
            if entry.suffix == ".lua":
                sub.add_widget(self._make_file_entry(entry))

    def _make_file_entry(self, path: Path) -> _FileEntryWidget:
        w = _FileEntryWidget(path)
        w.file_opened.connect(self._on_file_opened)
        w.file_renamed.connect(self._on_file_renamed)
        self._file_entries[str(path)] = w
        return w

    def _on_file_opened(self, path: str):
        self._set_selected(path)
        self.file_requested.emit(path)

    def _on_file_renamed(self, old_path: str, new_path: str):
        entry = self._file_entries.pop(old_path, None)
        if entry:
            self._file_entries[new_path] = entry
        if self._selected_path == old_path:
            self._selected_path = new_path
        self.file_requested.emit(new_path)

    def _set_selected(self, path: str):
        if self._selected_path and self._selected_path in self._file_entries:
            self._file_entries[self._selected_path].set_selected(False)
        self._selected_path = path
        if path in self._file_entries:
            self._file_entries[path].set_selected(True)

    def highlight_file(self, path: Path):
        self._set_selected(str(path))


# ─── Écran principal ──────────────────────────────────────────────────

class ScriptEditorScreen(QWidget):
    """Écran complet d'édition de script Lua."""

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Optional[Path] = None
        self._dirty = False
        self._root_scripts_dir: Optional[Path] = None

        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._refresh_events)

        self._file_watcher = QFileSystemWatcher()
        self._file_watcher.fileChanged.connect(self._on_external_change)
        self._external_reload_timer = QTimer()
        self._external_reload_timer.setSingleShot(True)
        self._external_reload_timer.setInterval(300)
        self._external_reload_timer.timeout.connect(self._reload_from_disk)

        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Barre du haut ──────────────────────────────────────────
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"background:{_BG_HDR};border-bottom:1px solid {_BORDER};")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(8, 0, 8, 0)
        bar_l.setSpacing(8)

        btn_back = QPushButton("← Retour")
        btn_back.setFont(QFont(T.MONO, T.MD))
        btn_back.setFixedHeight(24)
        btn_back.setStyleSheet(
            f"QPushButton{{color:{_TEXT_NORM};background:none;border:1px solid {C.BORDER};"
            f"border-radius:3px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{_TEXT_HI};border-color:{C.BORDER_MID};}}"
        )
        btn_back.clicked.connect(self._on_back)
        bar_l.addWidget(btn_back)

        # Couleur alignée sur la palette canonique par type d'objet (voir ui/icons.py,
        # même source que AssetHeaderBar utilisé dans Scene Manager / Sprite Editor / Sound Mixer).
        # Pas de bandeau dédié ici : ce titre partage la barre d'outils avec Retour/Enregistrer.
        self._title_lbl = QLabel("—")
        self._title_lbl.setFont(QFont(T.MONO, T.MD2, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color:{COLOR_SCRIPT};")
        bar_l.addWidget(self._title_lbl, 1)

        from ui.widgets import _kind_colors as _badge_bg
        self._ctx_badge = QLabel("")
        self._ctx_badge.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._ctx_badge.setStyleSheet(
            f"color:{_C_API};background:{_badge_bg(_C_API)[0]};border:1px solid {_C_API};"
            "border-radius:3px;padding:1px 6px;"
        )
        self._ctx_badge.setVisible(False)
        bar_l.addWidget(self._ctx_badge)

        self._save_btn = QPushButton("Enregistrer")
        self._save_btn.setFont(QFont(T.MONO, T.MD))
        self._save_btn.setFixedHeight(24)
        self._save_btn.setStyleSheet(
            f"QPushButton{{color:{_C_EVENT};background:none;border:1px solid {_C_EVENT};"
            "border-radius:3px;padding:0 8px;}"
            f"QPushButton:hover{{background:#1a2a2a;}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED};border-color:{C.BORDER_DARK};}}"
        )
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        bar_l.addWidget(self._save_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{_BORDER};")
        sep.setFixedWidth(1)
        bar_l.addWidget(sep)

        for label, subdir in [("+ Script", ""), ("+ Actor", "actors"), ("+ Scene", "scenes")]:
            btn = QPushButton(label)
            btn.setFont(QFont(T.MONO, T.SM))
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                f"QPushButton{{color:{C.TEXT_NORM};background:none;border:1px solid {C.BORDER};"
                f"border-radius:3px;padding:0 8px;}}"
                f"QPushButton:hover{{color:{C.TEXT_HI};border-color:{C.BORDER_MID};}}"
            )
            btn.clicked.connect(lambda checked, sd=subdir: self._create_script(sd))
            bar_l.addWidget(btn)

        root.addWidget(bar)

        # ── Corps : sidebar | (éditeur / log) | scripts ──────────────
        self._sidebar = SidebarPanel()
        self._sidebar.snippet_requested.connect(self._editor_insert_snippet)
        self._sidebar.stub_requested.connect(self._on_event_activated)

        self._editor = LuaEditor()
        self._editor.textChanged.connect(self._on_text_changed)

        # Colonne centrale : éditeur (haut) + log (bas)
        self.build_panel = BuildPanel()
        self.build_panel.setMinimumHeight(60)

        center_split = QSplitter(Qt.Orientation.Vertical)
        center_split.setStyleSheet(
            f"QSplitter::handle{{background:{_BORDER};}}"
            "QSplitter::handle:vertical{{height:2px;}}"
        )
        center_split.addWidget(self._editor)
        center_split.addWidget(self.build_panel)
        center_split.setSizes([600, 150])
        center_split.setStretchFactor(0, 1)
        center_split.setStretchFactor(1, 0)

        # ScriptFinderPanel — colonne droite
        self._file_tree = ScriptFinderPanel()
        self._file_tree.file_requested.connect(lambda p: self.open_script(Path(p)))
        self._file_tree.snippet_requested.connect(self._editor_insert_snippet)

        body = QWidget()
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(0)
        body_l.addWidget(self._sidebar)
        body_l.addWidget(center_split, 1)
        body_l.addWidget(self._file_tree)
        root.addWidget(body, 1)

    # ── API publique ──────────────────────────────────────────────────

    def open_script(self, path: Path):
        watched = self._file_watcher.files()
        if watched:
            self._file_watcher.removePaths(watched)

        self._path = path
        self._title_lbl.setText(path.name)
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        self._editor.blockSignals(True)
        self._editor.setPlainText(source)
        self._editor.blockSignals(False)
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._refresh_events()

        ctx = self._detect_context(path)
        self._sidebar.set_context(ctx)
        self._update_context_badge(ctx)
        self._file_tree.highlight_file(path)

        if path.exists():
            self._file_watcher.addPath(str(path))

    def set_project(self, project):
        """Connecte le projet pour peupler les sections dynamiques."""
        self._sidebar.set_project(project)
        self._file_tree.set_project(project)
        if project:
            scripts_dir = getattr(project, "scripts_dir", None) or \
                          project.root / "project" / "scripts"
            self._root_scripts_dir = scripts_dir
            self._file_tree.set_root(scripts_dir)
            self._file_tree.show_panel()

    # ── Détection contexte ────────────────────────────────────────────

    def _detect_context(self, path: Path) -> str:
        if "actors" in {path.parent.name}:
            return "actor"
        if "scenes" in {path.parent.name}:
            return "scene"
        if "behaviors" in {path.parent.name}:
            return "behavior"
        # deeper check via full path string
        path_str = str(path)
        if "/scripts/actors/" in path_str or "\\scripts\\actors\\" in path_str:
            return "actor"
        if "/scripts/scenes/" in path_str or "\\scripts\\scenes\\" in path_str:
            return "scene"
        if "/scripts/behaviors/" in path_str or "\\scripts\\behaviors\\" in path_str:
            return "behavior"
        return "unknown"

    def _update_context_badge(self, ctx: str):
        from ui.widgets import _kind_colors
        _BADGE = {
            "actor":    ("ACTOR",    _C_EVENT),
            "scene":    ("SCÈNE",    _C_API),
            "behavior": ("BEHAVIOR", _C_BEHAVIOR),
        }
        if ctx in _BADGE:
            text, fg = _BADGE[ctx]
            bg, _mid, _accent = _kind_colors(fg)
            self._ctx_badge.setText(text)
            self._ctx_badge.setStyleSheet(
                f"color:{fg};background:{bg};border:1px solid {fg};"
                "border-radius:3px;padding:1px 6px;"
            )
            self._ctx_badge.setVisible(True)
        else:
            self._ctx_badge.setVisible(False)

    # ── Handlers ─────────────────────────────────────────────────────

    def _editor_insert_snippet(self, snippet: str):
        self._editor.insert_at_cursor(snippet)

    def _on_text_changed(self):
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._title_lbl.setText(f"● {self._path.name}" if self._path else "●")
        self._refresh_timer.start()

    def _on_event_activated(self, event_name: str):
        defined = self._get_defined_events()
        if event_name in defined:
            self._editor.jump_to_function(event_name)
        else:
            meta = _EVENT_META.get(event_name, {})
            stub = meta.get("stub", f"function {event_name}()\n    \nend\n")
            self._editor.insert_stub(stub)
            self._editor.jump_to_function(event_name)

    def _refresh_events(self):
        self._sidebar.update_defined_events(self._get_defined_events())

    def _get_defined_events(self) -> set[str]:
        source = self._editor.toPlainText()
        defined = set()
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from scripting.parser import parse as lua_parse
            script = lua_parse(source)
            defined = {fn.name for fn in script.functions}
        except Exception:
            import re
            for m in re.finditer(r"^function\s+(\w+)\s*\(", source, re.MULTILINE):
                defined.add(m.group(1))
        return defined

    def _on_external_change(self, path: str):
        if Path(path).exists():
            self._file_watcher.addPath(path)
        if not self._dirty:
            self._external_reload_timer.start()
        else:
            self._title_lbl.setText(
                f"⚠ {self._path.name if self._path else '?'} (conflit externe)")

    def _reload_from_disk(self):
        if not self._path or not self._path.exists():
            return
        source = self._path.read_text(encoding="utf-8")
        pos = self._editor.textCursor().position()
        self._editor.blockSignals(True)
        self._editor.setPlainText(source)
        self._editor.blockSignals(False)
        cur = self._editor.textCursor()
        cur.setPosition(min(pos, len(source)))
        self._editor.setTextCursor(cur)
        self._title_lbl.setText(f"↻ {self._path.name}")
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._refresh_events()

    # ── Création de scripts ───────────────────────────────────────────

    def _create_script(self, subdir: str):
        if not self._root_scripts_dir:
            QMessageBox.warning(self, "Projet", "Aucun projet chargé.")
            return
        name, ok = QInputDialog.getText(self, "Nouveau script", "Nom du script :")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".lua"):
            name += ".lua"
        target_dir = self._root_scripts_dir / subdir if subdir else self._root_scripts_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        if path.exists():
            QMessageBox.warning(self, "Fichier existant", f"{name} existe déjà.")
            return
        path.write_text("", encoding="utf-8")
        self._file_tree.set_root(self._root_scripts_dir)
        self._file_tree.highlight_file(path)
        self.open_script(path)

    # ── Navigation ───────────────────────────────────────────────────

    def _on_back(self):
        if self._dirty:
            self._save()
        self.back_requested.emit()

    # ── Sauvegarde ───────────────────────────────────────────────────

    def flush_pending_edits(self):
        """Appelé par le Ctrl+S global (window.py) avant la sauvegarde projet —
        persiste le script en cours d'édition s'il a des changements non sauvés."""
        if self._dirty:
            self._save()

    def _save(self):
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._editor.toPlainText(), encoding="utf-8")
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._title_lbl.setText(self._path.name)
