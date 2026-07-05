"""
editor/ui/script_editor/script_editor.py — Écran d'édition de scripts Lua pour acteurs GBA.

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

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QFrame,
    QInputDialog, QMessageBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QFileSystemWatcher

from scripting.api import EVENT_REGISTRY as _EVENT_META
from ui.common.theme import C, T
from ui.common.icons import COLOR_SCRIPT
from ui.common.build_panel import BuildPanel
from .colors import _BG, _BG_HDR, _BORDER, _TEXT_HI, _TEXT_NORM, _C_API, _C_EVENT, _C_BEHAVIOR
from .lua_editor import LuaEditor
from .sidebar_panel import SidebarPanel
from .script_finder_panel import ScriptFinderPanel

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

        from ui.common.widgets import _kind_colors as _badge_bg
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
        from ui.common.widgets import _kind_colors
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
        from scripting.script_templates import ScriptTemplateContext, generate_script_template
        ctx = ScriptTemplateContext(kind="empty", name=name[:-4] if name.endswith(".lua") else name)
        path.write_text(generate_script_template(ctx), encoding="utf-8")
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
