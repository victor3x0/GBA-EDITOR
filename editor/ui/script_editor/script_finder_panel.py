"""ui/script_editor/script_finder_panel.py — arbre de fichiers scripts + tables globals/constants."""
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent

from ui.common.theme import C, T
from ui.common.icons import COLOR_SCRIPT, COLOR_GLOBAL, COLOR_CONST
from ui.common.widgets import FinderSection
from .colors import _BG, _BG_HDR, _BG_HOVER, _BG_SEL_REF, _BORDER, _TEXT_DIM, _TEXT_HI, _TEXT_NORM, _C_REF
from .sidebar_widgets import _SubSection
from .var_table_panel import VarTablePanel

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
        from ui.common.icons import get as _ico
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
