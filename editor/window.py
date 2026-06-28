"""GBA Editor — fenêtre principale (MainWindow uniquement)."""

import queue
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QPushButton, QFrame,
    QSizePolicy, QStatusBar, QDialog,
    QInputDialog, QMessageBox,
    QToolButton, QStackedWidget, QButtonGroup,
    QToolBar,
)
from PyQt6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QByteArray, QTimer

from ui.theme import T

from codegen import BuildWorker
from core.scene_editor import SceneEditor
from core.toolchain import Toolchain
from core.project_watcher import ProjectWatcher
from core.history import get_history, SetBgLayerCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from core.project import (
    Project, Scene, Actor, Prefab,
    MIME_PREFAB_TEMPLATE, MIME_SCRIPT,
)

# ── Sous-composants UI ────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from ui.project_panel import ProjectPanel
from ui.build_panel import BuildPanel, ToolchainBar, ToolchainDialog
from ui.inspectors import DynamicInspector
from ui.sound_panel import SoundMixerScreen
from ui.script_editor import ScriptEditorScreen
from ui.home_screen import HomeScreen, add_recent

PROJECTS_DIR = Path(__file__).parent.parent / "projects"


# ──────────────────────────────────────────────────────────────────
#  GBA Status Bar — contraintes hardware visibles en permanence
# ──────────────────────────────────────────────────────────────────
class GbaStatusBar(QWidget):
    """
    Barre fixe en bas de la fenêtre affichant les compteurs GBA en temps réel.
    Inspiré de GB Studio : les limites hardware sont visibles, pas cachées.
    """
    _STYLE_OK   = "color:#4caf78;"
    _STYLE_WARN = "color:#f0a030;"
    _STYLE_CRIT = "color:#e05050;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setStyleSheet("background:#0e0e0e; border-top:1px solid #2a2a2a;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        self._counters: list[QLabel] = []
        specs = [
            ("OAM",      "0/128 sprites",
             "OAM — Object Attribute Memory\n"
             "La GBA peut afficher 128 sprites simultanément.\n"
             "Au-delà, les sprites supplémentaires n'apparaissent pas.\n"
             "Chaque actor visible consomme 1 slot OAM par frame.",
             128, 96),
            ("scanline", "0/10 sprites/ligne",
             "Limite scanline\n"
             "Maximum 10 sprites peuvent occuper la même ligne horizontale.\n"
             "Au-delà, les sprites scintillent ou disparaissent.\n"
             "Estimé depuis la taille des sprites — valeur approchée.",
             10, 8),
            ("VRAM",     "0/1024 tiles",
             "VRAM sprites — Zone OBJ\n"
             "La zone sprite en VRAM contient 1024 tiles 8×8 (16Ko en mode 16c).\n"
             "Chaque sprite 16×16 utilise 4 tiles, un 32×32 en utilise 16.",
             1024, 768),
            ("PAL",      "0/16 palettes",
             "Palettes sprites\n"
             "La GBA dispose de 16 palettes de 16 couleurs pour les sprites.\n"
             "Chaque couleur est codée sur 15 bits (32 768 couleurs possibles).\n"
             "La couleur 0 de chaque palette est transparente.",
             16, 12),
        ]
        for i, (name, default, tooltip, limit, warn) in enumerate(specs):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet("color:#2a2a2a; margin:4px 12px;")
                layout.addWidget(sep)
            lbl_name = QLabel(f"{name}  ")
            lbl_name.setFont(QFont(T.MONO, T.XS))
            lbl_name.setStyleSheet("color:#444;")
            layout.addWidget(lbl_name)
            lbl_val = QLabel(default)
            lbl_val.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            lbl_val.setStyleSheet(self._STYLE_OK)
            lbl_val.setToolTip(tooltip)
            lbl_name.setToolTip(tooltip)
            layout.addWidget(lbl_val)
            self._counters.append((lbl_val, limit, warn))

        layout.addStretch()

        gba_info = QLabel("GBA  240×160  ARM7TDMI 16MHz  256KB WRAM")
        gba_info.setFont(QFont(T.MONO, T.XS))
        gba_info.setStyleSheet("color:#333;")
        gba_info.setToolTip(
            "Game Boy Advance — spécifications hardware\n"
            "CPU  : ARM7TDMI @ 16.78 MHz\n"
            "RAM  : 256 KB WRAM externe + 32 KB IRAM interne\n"
            "VRAM : 96 KB total\n"
            "Ecran: 240×160 pixels, 15 bits/couleur\n"
            "Sound: 2 canaux DirectSound PCM + 4 canaux GB legacy"
        )
        layout.addWidget(gba_info)

    def update_scene(self, scene: Scene, project: Project):
        """Recalcule les compteurs depuis la scène active."""
        if not scene:
            self._set(0, 0); self._set(1, 0); self._set(2, 0); self._set(3, 0)
            return

        visible_actors = [a for a in scene.actors if a.visible and a.active]
        oam_count = sum(1 for a in visible_actors if a.get_component("sprite"))

        # Estimation tiles VRAM
        tiles = 0
        for a in visible_actors:
            sc = a.get_component("sprite")
            if not sc or not sc.sprite_name: continue
            sp = project.get_sprite(sc.sprite_name)
            if sp:
                tw = max(1, sp.frame_w // 8)
                th = max(1, sp.frame_h // 8)
                tiles += tw * th

        # Palettes uniques
        pal_set = {a.pal_bank for a in visible_actors if a.get_component("sprite")}

        # Estimation sprites par scanline (approx : actors visibles / hauteur en tiles)
        scanline_est = max(oam_count, sum(
            1 for a in visible_actors
            if a.get_component("sprite")
        ) // max(1, (160 // 16)))

        values = [oam_count, scanline_est, tiles, len(pal_set)]
        labels = [
            f"{oam_count}/128 sprites",
            f"~{scanline_est}/10 sprites/ligne",
            f"{tiles}/1024 tiles",
            f"{len(pal_set)}/16 palettes",
        ]
        for i, (val, lbl) in enumerate(zip(values, labels)):
            self._set(i, val, lbl)

    def _set(self, idx: int, value: int, text: str = ""):
        lbl, limit, warn = self._counters[idx]
        if text:
            lbl.setText(text)
        if value >= limit:
            lbl.setStyleSheet(self._STYLE_CRIT)
        elif value >= warn:
            lbl.setStyleSheet(self._STYLE_WARN)
        else:
            lbl.setStyleSheet(self._STYLE_OK)


# ──────────────────────────────────────────────────────────────────
#  Fenêtre principale
# ──────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    SCREENS = [
        "Scene Manager", "Tileset Manager", "Background Editor",
        "Sprite Editor", "Sound Mixer", "Script Editor",
    ]

    def __init__(self, project_path: Path = None):
        super().__init__()
        self.setWindowTitle("GBA Editor")
        self.resize(1280, 760)
        self.project: Project = None
        self._worker = None
        self._startup_project = project_path
        self.toolchain = Toolchain()
        self._watcher = ProjectWatcher(self)
        self._history = get_history()

        # Debounce : regrouper les sauvegardes rapides (SpinBox drag, etc.)
        self._save_timer = QTimer(); self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._flush_changes)

        self._setup_ui()

        # Raccourcis clavier globaux — après _setup_ui() pour que _btn_undo existe
        self._history.changed.connect(self._on_history_changed)
        self._sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._sc_undo.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_undo.activated.connect(self._do_undo)
        self._sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._sc_redo_y.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_redo_y.activated.connect(self._do_redo)
        self._sc_redo_z = QShortcut(QKeySequence.StandardKey.Redo, self)
        self._sc_redo_z.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sc_redo_z.activated.connect(self._do_redo)
        self._restore_layout()
        self._load_default_project()

        if not self.toolchain.devkitpro_ok or not self.toolchain.mgba_ok:
            self._open_toolchain_dialog()

    def _setup_ui(self):
        self._setup_toolbar()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.toolchain_bar = ToolchainBar(self.toolchain)
        self.toolchain_bar.configure_requested.connect(self._open_toolchain_dialog)
        root_layout.addWidget(self.toolchain_bar)

        self._screen_stack = QStackedWidget()
        root_layout.addWidget(self._screen_stack, 1)

        # Index 0 — Écran d'accueil (toujours présent)
        self._home_screen = HomeScreen(PROJECTS_DIR)
        self._home_screen.new_project_requested.connect(self._on_home_new)
        self._home_screen.open_project_requested.connect(self._on_home_open)
        self._home_screen.recent_project_requested.connect(
            lambda p: self._open_project(Path(p))
        )
        self._screen_stack.addWidget(self._home_screen)

        # Index 1+ — Écrans éditeur
        self._build_scene_manager_screen()
        for title in ("Tileset Manager", "Background Editor", "Sprite Editor"):
            self._screen_stack.addWidget(self._make_placeholder_screen(title))
        self._sound_mixer = SoundMixerScreen()
        self._screen_stack.addWidget(self._sound_mixer)
        self._script_editor = ScriptEditorScreen()
        self._script_editor.back_requested.connect(
            lambda: self._switch_screen("Scene Manager")
        )
        self._screen_stack.addWidget(self._script_editor)

        # Démarrer sur l'accueil, nav cachée
        self._screen_stack.setCurrentIndex(0)
        self._set_editor_nav_visible(False)

        self._gba_bar = GbaStatusBar()
        root_layout.addWidget(self._gba_bar)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    def _make_placeholder_screen(self, title: str) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#181818;")
        lbl = QLabel(f"{title}\n\n(bientôt disponible)")
        lbl.setFont(QFont(T.MONO, T.XL)); lbl.setStyleSheet("color:#444;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from PyQt6.QtWidgets import QVBoxLayout as _VL
        l = _VL(w); l.addWidget(lbl)
        return w

    def _build_scene_manager_screen(self):
        _splitter_style = (
            "QSplitter::handle{background:#2a2a2a;}"
            "QSplitter::handle:horizontal{width:3px;}"
            "QSplitter::handle:vertical{height:3px;}"
            "QSplitter::handle:hover{background:#4a8a5a;}"
        )

        screen = QWidget()
        screen_layout = QVBoxLayout(screen)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(0)

        # Splitter horizontal principal : 3 colonnes
        self._h_split = QSplitter(Qt.Orientation.Horizontal)
        self._h_split.setStyleSheet(_splitter_style)

        # ── Colonne 1 : Project Panel (pleine hauteur) ────────────
        self.project_panel = ProjectPanel()
        self._setup_menu()
        self.project_panel.scene_selected.connect(self._on_scene_selected)
        self.project_panel.scene_add_requested.connect(self._add_scene)
        self.project_panel.actor_add_requested.connect(self._add_actor)
        self.project_panel.prefab_add_requested.connect(self._add_prefab)
        self.project_panel.script_opened.connect(self.open_script)
        self.project_panel.project_created.connect(self._new_project)
        self.project_panel.project_opened.connect(self._on_home_open)
        self.project_panel.prefab_uses_requested.connect(
            lambda p: self._inspector.show_prefab_uses(p))
        self.project_panel.script_uses_requested.connect(
            lambda path: self._inspector.show_script_uses(path))
        self._h_split.addWidget(self.project_panel)

        # ── Colonne 2 : Canvas (haut) + Console (bas) ────────────
        self._center_v_split = QSplitter(Qt.Orientation.Vertical)
        self._center_v_split.setStyleSheet(_splitter_style)

        self.scene_editor = SceneEditor()
        self.scene_editor.scene_changed.connect(self._on_scene_changed)
        self._center_v_split.addWidget(self.scene_editor)

        self.build_panel = BuildPanel()
        self.build_panel.btn_build.clicked.connect(self._run_build)
        self.build_panel.setMinimumHeight(80)
        self._center_v_split.addWidget(self.build_panel)
        self._center_v_split.setSizes([600, 160])
        self._center_v_split.setStretchFactor(0, 1)
        self._center_v_split.setStretchFactor(1, 0)

        self._h_split.addWidget(self._center_v_split)

        # ── Colonne 3 : Inspector (pleine hauteur) ────────────────
        self._inspector = DynamicInspector()
        self._inspector.actor_changed.connect(self._on_inspector_actor_changed)
        self._inspector.slot_assigned.connect(self._on_slot_assigned)
        self._inspector.set_script_open_fn(self.open_script)
        self._inspector._scene_insp.set_script_open_fn(self.open_script)
        self._h_split.addWidget(self._inspector)

        # Bus de sélection — vider sur changement de scène/écran
        self._bus = get_bus()

        # CommandDispatcher — abonnements aux événements engine
        _d = get_dispatcher()
        _d.on("scene_sprites_changed", self.scene_editor._reload_sprites)
        _d.on("actors_list_changed",   self.project_panel.refresh)
        _d.on("actors_list_changed",   self._update_gba_bar)
        _d.on("bg_slot_changed",       self.scene_editor.refresh_bg)
        _d.on("status_message",        lambda msg: self._status.showMessage(msg, 3000))
        _d.on("scripts_changed",       self.project_panel._refresh_scripts)

        self._h_split.setSizes([220, 820, 240])
        self._h_split.setStretchFactor(0, 0)
        self._h_split.setStretchFactor(1, 1)
        self._h_split.setStretchFactor(2, 0)

        screen_layout.addWidget(self._h_split)
        self._screen_stack.addWidget(screen)

    # ── Persistance layout ────────────────────────────────────────

    def _restore_layout(self):
        s = QSettings("GBAEditor", "Layout")
        geom = s.value("geometry")
        if isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        for name, splitter in (
            ("h_split", self._h_split),
            ("center_v_split", self._center_v_split),
        ):
            data = s.value(name)
            if isinstance(data, QByteArray):
                splitter.restoreState(data)

    def _save_layout(self):
        s = QSettings("GBAEditor", "Layout")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("h_split", self._h_split.saveState())
        s.setValue("center_v_split", self._center_v_split.saveState())

    def closeEvent(self, event):
        self._save_layout()
        super().closeEvent(event)

    # ── Menu ──────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()
        mb.setMinimumHeight(32)
        mb.setStyleSheet(
            f"QMenuBar{{background:#1a1a1a;color:#ccc;font-family:{T.MONO};font-size:{T.MD}px;padding:4px 4px;}}"
            "QMenuBar::item{padding:4px 10px;border-radius:3px;}"
            "QMenuBar::item:selected{background:#2a2a2a;}"
            f"QMenu{{background:#1e1e1e;color:#ccc;border:1px solid #333;font-family:{T.MONO};font-size:{T.MD}px;}}"
            "QMenu::item{padding:5px 20px 5px 12px;}"
            "QMenu::item:selected{background:#2a3a2a;}"
        )
        m_file = mb.addMenu("File")
        a_new  = QAction("Nouveau projet", self); a_new.setShortcut("Ctrl+N")
        a_open = QAction("Ouvrir projet",  self); a_open.setShortcut("Ctrl+O")
        a_save = QAction("Sauvegarder",    self); a_save.setShortcut("Ctrl+S")
        a_quit = QAction("Quitter",        self); a_quit.setShortcut("Ctrl+Q")
        a_new.triggered.connect(self.project_panel._prompt_new)
        a_open.triggered.connect(self.project_panel._prompt_open)
        a_save.triggered.connect(lambda: self.project.save() if self.project else None)
        a_quit.triggered.connect(self.close)
        for a in [a_new, a_open, a_save, None, a_quit]:
            if a: m_file.addAction(a)
            else: m_file.addSeparator()
        m_game = mb.addMenu("Game")
        a_build = QAction("Build & Run", self); a_build.setShortcut("F5")
        a_build.triggered.connect(self._run_build)
        m_game.addAction(a_build)
        mb.addMenu("View")
        m_help = mb.addMenu("Help")
        a_about = QAction("A propos", self)
        a_about.triggered.connect(lambda: QMessageBox.information(
            self, "GBA Editor", "GBA Editor - homebrew Game Boy Advance"))
        m_help.addAction(a_about)

    # ── Toolbar ───────────────────────────────────────────────────

    def _setup_toolbar(self):
        tb = QToolBar("Principale")
        tb.setMovable(False)
        tb.setMinimumHeight(48)
        tb.setStyleSheet(
            f"QToolBar{{background:#1e1e1e;border-bottom:1px solid #2a2a2a;spacing:4px;padding:4px 12px;}}"
            f"QToolButton{{color:#ccc;border:none;padding:4px 12px;font-family:{T.MONO};font-size:{T.MD}px;}}"
            f"QToolButton:hover{{background:#2a2a2a;border-radius:4px;}}"
        )
        self.addToolBar(tb)
        self._tb_project_lbl = QPushButton("GBA Editor")
        self._tb_project_lbl.setFont(QFont(T.MONO, T.XL, QFont.Weight.Bold))
        self._tb_project_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tb_project_lbl.setStyleSheet(
            "QPushButton{color:#555;background:none;border:none;padding:0 12px;}"
            "QPushButton:hover{color:#888;}"
        )
        self._tb_project_lbl.clicked.connect(self._go_home)
        tb.addWidget(self._tb_project_lbl)
        tb.addSeparator()
        self._tb_build_btn = QToolButton()
        self._tb_build_btn.setText("  Build & Run")
        self._tb_build_btn.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        self._tb_build_btn.setStyleSheet(
            "QToolButton{background:#2a5c34;color:#c8ffc8;border:none;"
            "border-radius:4px;padding:6px 16px;}"
            "QToolButton:hover{background:#3a7a44;}"
            "QToolButton:disabled{background:#1a3a24;color:#666;}"
        )
        self._tb_build_btn.setEnabled(False)
        self._tb_build_btn.clicked.connect(self._run_build)
        tb.addWidget(self._tb_build_btn)
        tb.addSeparator()

        # Boutons Undo / Redo
        _undo_redo_style = (
            f"QToolButton{{color:#777;border:none;padding:4px 10px;"
            f"font-family:{T.MONO};font-size:{T.MD}px;border-radius:4px;}}"
            "QToolButton:hover:enabled{background:#2a2a2a;color:#ccc;}"
            "QToolButton:disabled{color:#333;}"
        )
        self._btn_undo = QToolButton()
        self._btn_undo.setText("↩ Undo")
        self._btn_undo.setFont(QFont(T.MONO, T.MD))
        self._btn_undo.setStyleSheet(_undo_redo_style)
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._do_undo)
        tb.addWidget(self._btn_undo)

        self._btn_redo = QToolButton()
        self._btn_redo.setText("↪ Redo")
        self._btn_redo.setFont(QFont(T.MONO, T.MD))
        self._btn_redo.setStyleSheet(_undo_redo_style)
        self._btn_redo.setEnabled(False)
        self._btn_redo.clicked.connect(self._do_redo)
        tb.addWidget(self._btn_redo)
        tb.addSeparator()

        self._screen_group = QButtonGroup(self)
        self._screen_group.setExclusive(True)
        for i, name in enumerate(self.SCREENS):
            btn = QToolButton()
            btn.setText(name); btn.setCheckable(True)
            btn.setFont(QFont(T.MONO, T.MD))
            btn.setStyleSheet(
                "QToolButton{color:#aaa;border:none;padding:6px 14px;border-radius:4px;}"
                "QToolButton:hover{background:#2a2a2a;color:#eee;}"
                "QToolButton:checked{background:#2a3a2a;color:#4caf78;}"
            )
            btn.clicked.connect(lambda checked=False, idx=i: self._show_screen(idx))
            self._screen_group.addButton(btn, i)
            tb.addWidget(btn)
        self._screen_group.button(0).setChecked(True)

    def _show_screen(self, index: int):
        # index 0 dans SCREENS → index 1 dans le stack (0 = HomeScreen)
        self._screen_stack.setCurrentIndex(index + 1)
        self._history.clear()
        self._bus.clear()

    def _switch_screen(self, name: str):
        idx = self.SCREENS.index(name) if name in self.SCREENS else 0
        self._show_screen(idx)
        btn = self._screen_group.button(idx)
        if btn:
            btn.setChecked(True)

    def _go_home(self):
        """Retourne à l'écran d'accueil."""
        self._set_editor_nav_visible(False)
        self._screen_stack.setCurrentIndex(0)

    def open_script(self, path):
        """Ouvre un script .lua dans le Script Editor et bascule l'écran."""
        from pathlib import Path
        self._script_editor.set_project(self.project)
        self._script_editor.open_script(Path(path))
        self._switch_screen("Script Editor")

    # ── Chargement projet ─────────────────────────────────────────

    def _load_default_project(self):
        """Au démarrage : ouvre le projet passé en argument, sinon affiche l'accueil."""
        PROJECTS_DIR.mkdir(exist_ok=True)
        if self._startup_project and self._startup_project.exists():
            self._open_project(self._startup_project)

    def _on_home_new(self, name: str, path: str):
        self._new_project(name, Path(path))

    def _on_home_open(self, path: str):
        self._open_project(Path(path))

    def _new_project(self, name: str, path):
        path = Path(path)
        self.project = Project.create(path, name)
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        add_recent(path, name)
        self._home_screen.refresh()
        self._enter_editor()
        self._refresh_ui()
        self._status.showMessage(f"Nouveau projet : {name}")

    def _open_project(self, path: Path):
        self.project = Project.open(path)
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        add_recent(path, self.project.settings.name)
        self._home_screen.refresh()
        self._enter_editor()
        self._refresh_ui()
        self._status.showMessage(f"Projet : {self.project.settings.name}")

    def _enter_editor(self):
        """Bascule de l'accueil vers l'éditeur."""
        self._set_editor_nav_visible(True)
        self._show_screen(0)   # Scene Manager (index 0 dans SCREENS → index 1 dans le stack)

    def _set_editor_nav_visible(self, visible: bool):
        """Affiche ou masque les boutons de navigation de l'éditeur."""
        for i in range(len(self.SCREENS)):
            btn = self._screen_group.button(i)
            if btn:
                btn.setVisible(visible)
        self._tb_build_btn.setVisible(visible)
        self._btn_undo.setVisible(visible)
        self._btn_redo.setVisible(visible)

    def _refresh_ui(self):
        if not self.project: return
        name = self.project.settings.name
        self.setWindowTitle(f"GBA Editor — {name}")
        self._tb_project_lbl.setText(name)   # QPushButton.setText
        can_build = self.toolchain.devkitpro_ok and bool(self.project.scenes)
        self._tb_build_btn.setEnabled(can_build)
        self.build_panel.btn_build.setEnabled(can_build)
        self.project_panel.load_project(self.project)
        self._sound_mixer.load_project(self.project)
        self._inspector.set_project(self.project)
        self._script_editor.set_project(self.project)
        if self.project.active_scene:
            self.scene_editor.load_project(self.project)
            # Montrer l'inspector de scène par défaut (sans passer par le bus)
            self._inspector.show_scene(self.project.active_scene, self.project)
        self._update_gba_bar()

    # ── Slots scène ───────────────────────────────────────────────

    def _on_scene_selected(self, index: int):
        if not self.project: return
        self.project.set_active_scene(index)
        self._history.clear()
        self._bus.clear()      # nouvelle scène = nouvelle sélection
        self.scene_editor.load_project(self.project)
        self._inspector.show_scene(self.project.active_scene, self.project)
        self.project_panel.refresh()
        self._update_gba_bar()
        self._status.showMessage(f"Scene active : {self.project.active_scene.name}")

    def _add_scene(self):
        if not self.project: return
        name, ok = QInputDialog.getText(self, "Nouvelle scene", "Nom :")
        if ok and name.strip():
            get_dispatcher().add_scene(name.strip())
            self.project_panel.refresh()

    def _add_actor(self):
        if not self.project or not self.project.active_scene: return
        name, ok = QInputDialog.getText(self, "Nouvel acteur", "Nom :")
        if ok and name.strip():
            get_dispatcher().add_actor(name.strip())

    # ── Slots prefab ─────────────────────────────────────────────

    def _add_prefab(self):
        if not self.project: return
        name, ok = QInputDialog.getText(self, "Nouveau Prefab", "Nom :")
        if ok and name.strip():
            get_dispatcher().add_prefab(name.strip())
            self.project_panel.refresh()

    # ── Slot assigned (BG layers) ─────────────────────────────────

    def _on_slot_assigned(self, slot_index: int, path_str: str):
        if not self.project or not self.project.active_scene: return
        scene = self.project.active_scene
        if slot_index >= len(scene.bg_layers): return
        layer = scene.bg_layers[slot_index]
        old_bg = layer.background_name
        get_dispatcher().assign_bg_slot(slot_index, path_str)
        new_bg = layer.background_name
        if old_bg != new_bg:
            def _refresh():
                if self.project and self.project.active_scene:
                    self._inspector.show_scene(self.project.active_scene, self.project)
            self._history.record(SetBgLayerCmd(
                layer, old_bg, new_bg, slot_index,
                save_fn=lambda: self.project.save_scene(scene) if self.project else None,
                refresh_fn=_refresh,
            ))
        self._inspector.show_scene(scene, self.project)

    # ── Autres slots ──────────────────────────────────────────────

    def _on_scene_changed(self):
        """Fin de drag actor ou déplacement caméra — sauvegarder via le dispatcher."""
        if not self.project or not self.project.active_scene:
            return
        self.scene_editor.flush_camera_pos()
        get_dispatcher().save_scene()

    def _on_inspector_actor_changed(self, actor):
        """Un champ a changé dans l'inspector — payload propre, pas d'accès privé."""
        if actor:
            self.scene_editor.move_actor_item(actor)
        self._save_timer.start()    # 400 ms → _flush_changes (debounce)

    def _flush_changes(self):
        """Sauvegarde globale différée (400 ms après le dernier changement inspector)."""
        get_dispatcher().save_all()

    def _update_gba_bar(self):
        """Met à jour les compteurs hardware GBA (OAM, VRAM, PAL, scanline)."""
        if self.project and self.project.active_scene:
            self._gba_bar.update_scene(self.project.active_scene, self.project)

    # ── Undo / Redo ───────────────────────────────────────────────

    def _on_history_changed(self):
        self._btn_undo.setEnabled(self._history.can_undo)
        self._btn_redo.setEnabled(self._history.can_redo)
        ul = self._history.undo_label
        rl = self._history.redo_label
        self._btn_undo.setToolTip(f"Annuler : {ul}" if ul else "Rien à annuler")
        self._btn_redo.setToolTip(f"Refaire : {rl}" if rl else "Rien à refaire")

    def _do_undo(self):
        label = self._history.undo()
        if label:
            self._status.showMessage(f"Annulé : {label}", 2000)
            self._flush_after_undo_redo()

    def _do_redo(self):
        label = self._history.redo()
        if label:
            self._status.showMessage(f"Refait : {label}", 2000)
            self._flush_after_undo_redo()

    def _flush_after_undo_redo(self):
        """Rafraîchit l'UI après un undo ou redo."""
        if not self.project or not self.project.active_scene:
            return
        # Sauvegarder l'état actuel (le modèle en mémoire = vérité après undo)
        with self._watcher.suspended():
            self.project.save_scene(self.project.active_scene)
        # Rafraîchissement ciblé : sprites uniquement (pas reset zoom/cam/BG)
        self.project_panel.refresh()
        self.scene_editor._reload_sprites()
        self._update_gba_bar()
        # Recharger l'inspector scène
        si = self._inspector._scene_insp
        if si._scene:
            si.load(si._scene, self.project)
        # Recharger l'inspector si un actor est sélectionné
        actor_insp = self._inspector.actor_inspector
        if actor_insp._actor:
            actor_insp.load(actor_insp._actor, self.project,
                            self.project.active_scene)

    # ── Réactivité fichiers externes ─────────────────────────────

    def _connect_watcher(self):
        """Connecte tous les signaux du ProjectWatcher aux handlers."""
        w = self._watcher
        w.asset_appeared.connect(self._on_asset_appeared)
        w.asset_removed.connect(self._on_asset_removed)
        w.asset_modified.connect(self._on_asset_modified)
        w.lua_changed.connect(self._on_lua_changed)
        w.scene_changed.connect(self._on_scene_file_changed)

    def _on_asset_appeared(self, path: str):
        """Nouveau fichier brut détecté dans assets/ — créer le sidecar si nécessaire."""
        if not self.project:
            return
        p = Path(path)
        if p.suffix.lower() in (".png", ".bmp"):
            parent = p.parent.name
            if parent == "sprites":
                self.project.sync_sprite_png(p)
                self._refresh_ui()
                self._status.showMessage(f"Sprite importé : {p.name}", 3000)
            elif parent == "backgrounds":
                self.project.sync_background_png(p)
                self._refresh_ui()
                self._status.showMessage(f"Background importé : {p.name}", 3000)

    def _on_asset_removed(self, path: str):
        """Fichier brut supprimé de assets/ — retirer le sidecar et mettre à jour l'UI."""
        if not self.project:
            return
        p = Path(path)
        if p.suffix.lower() in (".png", ".bmp"):
            parent = p.parent.name
            if parent == "sprites":
                self.project.remove_sprite_png(p)
                self._refresh_ui()
                self._status.showMessage(f"Sprite retiré : {p.name}", 3000)

    def _on_asset_modified(self, path: str):
        """Fichier existant modifié dans assets/ (ex. PNG retouché) — rafraîchir la preview."""
        self._inspector.actor_inspector._refresh_sprite_preview()
        self._status.showMessage(f"Asset modifié : {Path(path).name}", 2000)

    def _on_lua_changed(self, path: str):
        """Un .lua a changé (éditeur externe)."""
        self._inspector.actor_inspector.notify_lua_changed(path)
        self._status.showMessage(f"Script modifié : {Path(path).name}", 2000)

    def _on_scene_file_changed(self, path: str):
        """Un .json de scène a changé depuis un éditeur externe — recharger la scène active."""
        if not self.project:
            return
        active = self.project.active_scene
        if not active:
            return
        scene_file = self.project.scenes._path(active.name)
        if Path(path) == scene_file:
            self.project.scenes.load_one(active.name)
            self.scene_editor.load_project(self.project)
            self._inspector.show_scene(self.project.active_scene, self.project)
            self._status.showMessage(f"Scène rechargée : {active.name}", 2000)

    def _open_toolchain_dialog(self):
        dlg = ToolchainDialog(self.toolchain, self)
        dlg.exec()
        self.toolchain_bar.refresh()
        if self.project:
            self.build_panel.btn_build.setEnabled(self.toolchain.devkitpro_ok)

    # ── Build ─────────────────────────────────────────────────────

    def _run_build(self):
        if not self.project or not self.project.active_scene: return
        if not self.toolchain.devkitpro_ok:
            self._open_toolchain_dialog(); return

        self.build_panel.set_building(True)
        msg = f"\n[build] {self.project.settings.name} — scene : {self.project.active_scene.name}"
        self.build_panel.log_info(msg)
        self._script_editor.build_panel.log_info(msg)

        # Bridge thread-safe : BuildWorker (thread Python) → Qt main thread
        # Les callbacks de l'engine sont appelés depuis le thread de build ;
        # on les empile dans une queue et un QTimer les draine sur le main thread.
        self._build_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._build_drain = QTimer()
        self._build_drain.setInterval(30)
        self._build_drain.timeout.connect(self._drain_build_queue)

        self._script_editor.build_panel.console.clear()
        self._worker = BuildWorker(project=self.project, toolchain=self.toolchain)
        self._worker.on("log_line",   lambda m:  self._build_queue.put(("log",      m)))
        self._worker.on("error_line", lambda m:  self._build_queue.put(("error",    m)))
        self._worker.on("finished",   lambda ok: self._build_queue.put(("finished", ok)))
        self._worker.start()
        self._build_drain.start()

    def _drain_build_queue(self):
        """Draine les messages du thread de build vers les widgets Qt (main thread)."""
        try:
            while True:
                kind, data = self._build_queue.get_nowait()
                if kind == "log":
                    self.build_panel.log(data)
                    self._script_editor.build_panel.log(data)
                elif kind == "error":
                    self.build_panel.log_error(data)
                    self._script_editor.build_panel.log_error(data)
                elif kind == "finished":
                    self._build_drain.stop()
                    self._on_build_finished(data)
        except queue.Empty:
            pass

    def _on_build_finished(self, success: bool):
        self.build_panel.set_building(False)
        if success:
            self.build_panel.log_info("[build] ROM generee — mgba lance")
            self._script_editor.build_panel.log_info("[build] ROM generee — mgba lance")
            self._status.showMessage("Build OK")
        else:
            self.build_panel.log_error("[build] Echec — voir console")
            self._script_editor.build_panel.log_error("[build] Echec — voir console")
            self._status.showMessage("Erreur de build")
