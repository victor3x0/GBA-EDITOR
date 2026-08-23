"""GBA Editor — fenêtre principale (MainWindow uniquement)."""

import queue
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QLabel, QPushButton, QFrame,
    QStatusBar, QDialog,
    QMessageBox,
    QToolButton, QStackedWidget, QToolBar,
)
from PyQt6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSettings, QByteArray, QTimer

from ui.common.theme import C, T, QSS

from codegen import BuildWorker
from ui.scene_manager.scene_canvas import SceneEditor
from core import asset_encoding
from core.toolchain import Toolchain
from core.project_watcher import ProjectWatcher
from core.history import get_history, SetFieldCmd
from core.selection_bus import get_bus
from core.command_dispatcher import get_dispatcher
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS
from core.models.font import FONT_FILE_EXTS
from core.models.scene import Scene
from core.project import Project
from ui.screens import EditorScreen, ProjectScreen, plugin_screens

# ── Sous-composants UI ────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from ui.scene_manager.assets_finder_panel import AssetsFinderPanel
from ui.scene_manager.scene_tree_panel import SceneTreePanel
from ui.common.build_panel import BuildPanel, ToolchainBar, AnimatedBuildButton
from ui.common.settings_dialog import SettingsDialog
from core.external_tools import ExternalTools
from core.keybindings import bind
from ui.scene_manager.inspectors import DynamicInspector
from ui.sound_mixer.sound_panel import SoundMixerScreen
from ui.script_editor.script_editor import ScriptEditorScreen
from ui.home.project_picker import HomeScreen, push_recent, PROJECTS_DIR
from ui.sprite_editor.sprite_editor_screen import SpriteEditorScreen
from ui.palette_editor.palette_editor_screen import PaletteEditorScreen
from ui.background_editor.background_editor_screen import BackgroundEditorScreen
from ui.data_editor.data_editor_screen import DataEditorScreen
from ui.text_editor.text_editor_screen import TextEditorScreen


# ──────────────────────────────────────────────────────────────────
#  GBA Status Bar — contraintes hardware visibles en permanence
# ──────────────────────────────────────────────────────────────────
class GbaStatusBar(QWidget):
    """
    Barre fixe en bas de la fenêtre affichant les compteurs GBA en temps réel.
    Inspiré de GB Studio : les limites hardware sont visibles, pas cachées.
    """
    # Compteurs neutres par défaut : la couleur n'apparaît qu'en alerte (jaune
    # = proche du budget, rouge = dépassé). Le vert POWER reste réservé aux
    # signaux « live » (Build, process actif).
    _STYLE_OK   = f"color:{C.TEXT_NORM};"
    _STYLE_WARN = f"color:{C.ACCENT_YLW};"
    _STYLE_CRIT = f"color:{C.ACCENT_RED};"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")

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
            # La GBA n'a PAS de limite « 10 objets par ligne » — c'est celle de
            # la Game Boy et de la GBC. Elle a un budget de CYCLES par
            # scanline : 1210 en temps normal (954 si le bit « H-Blank interval
            # free » est posé), et un objet régulier coûte environ sa largeur en
            # pixels. Une ligne de 26 glyphes 8×8 en sprites coûte ~208 cycles,
            # soit un sixième du budget — avec l'ancien compteur elle passait
            # pour trois fois hors limite.
            ("scanline", "0/1210 cycles/line",
             "Budget OBJ par scanline (GBA)\n"
             "Le matériel dispose de 1210 cycles par ligne pour dessiner les\n"
             "sprites ; un objet régulier en coûte environ sa largeur en pixels\n"
             "(un objet en rotation/échelle : 2 × largeur + 10).\n"
             "Au-delà, les objets suivants dans l'ordre OAM ne sont pas dessinés.\n"
             "Valeur = pire ligne de l'écran, zones de texte en sprites incluses.",
             1210, 900),
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
                sep.setStyleSheet(f"color:{C.BORDER}; margin:4px 12px;")
                layout.addWidget(sep)
            lbl_name = QLabel(f"{name}  ")
            lbl_name.setFont(QFont(T.MONO, T.XS))
            lbl_name.setStyleSheet(f"color:{C.TEXT_MUTED};")
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
        gba_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
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

        # Rectangles occupant l'écran : (y, hauteur, largeur). Servent à la fois
        # au coût par scanline et — pour le texte — au compte d'OAM.
        spans: list[tuple[int, int, int]] = []

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
                spans.append((a.y, sp.frame_h, sp.frame_w))

        # Zones de texte en cible sprite — leur coût est EXACT, pas estimé :
        # il ne dépend que de la géométrie authorée (cf. models/ui_region).
        from core.models.ui_region import strip_geometry, TARGET_OBJ
        rm = int(getattr(scene, "render_mode", 0) or 0)
        layout = project.scene_ui_layout(scene) if hasattr(project, "scene_ui_layout") else None
        text_oam = text_tiles = 0
        def _actor_pos(name):
            return next(((a.x, a.y) for a in scene.actors if a.name == name), None)
        for r in (layout.slots if layout else []):
            if layout.resolved_target(r, rm) != TARGET_OBJ:
                continue
            g = strip_geometry(r)
            text_oam   += g["oam"]
            text_tiles += g["tiles"]
            # y ÉCRAN résolu par le modèle : offsets cumulés jusqu'au root +
            # socle du frame (l'acteur pour un root actor). Sans ça une bulle
            # atterrissait hors écran et ne coûtait rien.
            _, ry, _ = layout.absolute_origin(r, _actor_pos)
            # Une bande est un pavage de sprites de 8 px de haut : chaque rangée
            # pèse la largeur totale de la zone sur les 8 lignes qu'elle couvre.
            for row in range(g["rows"]):
                spans.append((ry + row * 8, 8, sum(g["cols"])))
            # Un glyphe animé est un OBJ 16×16 de plus. Où il tombe dans la zone
            # dépend du texte, donc du runtime : on les impute tous à la première
            # rangée, ce qui majore. Les omettre sous-estimerait la pire ligne,
            # ce qui est le seul sens dans lequel une jauge ne doit pas mentir.
            if g["anim"]:
                spans.append((ry, 16, g["anim"] * 16))
        oam_count += text_oam
        tiles     += text_tiles

        # Palettes OBJ occupées (référencées + palettes propres auto-allouées)
        from codegen.palette_alloc import scene_bank_layout
        obj_banks = scene_bank_layout(project, scene, "obj").bank_count()

        # Pire ligne de l'écran : un objet régulier coûte ~sa largeur en pixels,
        # et seules comptent les lignes qu'il recouvre réellement. Sommer tout
        # l'écran donnerait un chiffre toujours rouge ; ne rien sommer du tout
        # laissait passer une ligne de texte en sprites.
        line_cost = [0] * 160
        for y, h, w in spans:
            for ly in range(max(0, y), min(160, y + max(1, h))):
                line_cost[ly] += w
        scanline_cost = max(line_cost) if line_cost else 0

        values = [oam_count, scanline_cost, tiles, obj_banks]
        labels = [
            f"{oam_count}/128 sprites",
            f"{scanline_cost}/1210 cycles/line",
            f"{tiles}/1024 tiles",
            f"{obj_banks}/16 palettes",
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
#  Écrans dont la fenêtre est le propriétaire
# ──────────────────────────────────────────────────────────────────
class SceneManagerScreen(QWidget):
    """Les colonnes du Scene Manager (colonne 1 scindée en deux panneaux
    empilés : liste projet au-dessus, contenu de la scène active en-dessous).

    Assemblée par `MainWindow._build_scene_manager_screen` : ses colonnes sont
    des attributs de la FENÊTRE (`assets_finder_panel`, `scene_tree_panel`,
    `scene_editor`, `_inspector`), lues depuis une trentaine d'endroits. Les
    faire descendre ici est un chantier à part — cette classe existe pour que
    l'écran porte le même contrat que les sept autres, et pour que la
    propagation du projet aux colonnes soit écrite une fois, ici, plutôt que
    dispersée dans
    `_refresh_ui`."""

    def __init__(self, finder, scene_tree, canvas, inspector, parent=None):
        super().__init__(parent)
        self._finder     = finder
        self._scene_tree = scene_tree
        self._canvas     = canvas
        self._inspector  = inspector

    def load_project(self, project):
        self._finder.load_project(project)
        self._scene_tree.load_project(project)
        self._inspector.set_project(project)
        if project.active_scene:
            self._canvas.load_project(project)
            # Inspecteur de scène par défaut, sans passer par le bus.
            self._inspector.show_scene(project.active_scene, project)


# ──────────────────────────────────────────────────────────────────
#  Fenêtre principale
# ──────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    # Routage assets/<dossier>/*.ext → (fonction sync, fonction remove, label)
    # — une seule table pour _on_asset_appeared/_removed, qui n'était avant
    # dupliquée qu'avec "sync_"/"remove_" échangés.
    #
    # Les FONCTIONS d'`asset_encoding`, pas leurs noms. La table portait des
    # chaînes appelées par `getattr(self.project, nom)` : les treize passe-plats
    # correspondants ont été retirés de `Project` (cf. core/project.py, « ce
    # module ne fait plus passe-plat vers asset_encoding ») et le routage a
    # continué de les épeler. Rien ne pouvait le voir — ni l'import, ni
    # `check_architecture.py`, qui contrôle pourtant les noms résolus — et
    # déposer un PNG dans assets/sprites/ levait un AttributeError dans un slot
    # Qt, donc tuait l'éditeur. Une référence directe échoue à l'import.
    _ASSET_ROUTES = [
        ("sprites",     (".png", ".bmp"), asset_encoding.sync_sprite_png,
                                          asset_encoding.remove_sprite_png,     "Sprite"),
        ("backgrounds", (".png", ".bmp"), asset_encoding.sync_background_png,
                                          asset_encoding.remove_background_png, "Background"),
        ("sfx",         SFX_FILE_EXTS,    asset_encoding.sync_sfx_file,
                                          asset_encoding.remove_sfx_file,       "SFX"),
        ("music",       MUSIC_FILE_EXTS,  asset_encoding.sync_music_file,
                                          asset_encoding.remove_music_file,     "Music"),
        ("fonts",       FONT_FILE_EXTS,   asset_encoding.sync_font_file,
                                          asset_encoding.remove_font_file,      "Font"),
    ]

    def __init__(self, project_path: Path = None):
        super().__init__()
        self.setWindowTitle("GBA Editor")
        self.resize(1280, 760)
        self.project: Project = None
        self._worker = None
        self._startup_project = project_path
        self.toolchain = Toolchain()
        self._external_tools = ExternalTools()
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

    def _setup_ui(self):
        # Le catalogue AVANT la barre d'outils : elle en tire ses libellés.
        # Construire le catalogue ne construit aucun widget — ce sont des
        # fabriques.
        self._screens: list[EditorScreen] = self._screen_catalogue()
        self._setup_toolbar()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.toolchain_bar = ToolchainBar(self.toolchain)
        self.toolchain_bar.configure_requested.connect(lambda: self._open_settings("Toolchains"))
        root_layout.addWidget(self.toolchain_bar)

        self._screen_stack = QStackedWidget()
        root_layout.addWidget(self._screen_stack, 1)

        # Écrans éditeur — l'accueil (HomeScreen) est un QDialog séparé
        # (ui/project_picker.py), affiché par main.py avant la fenêtre
        # principale, et rouvrable via _go_home() pour changer de projet.
        self._build_screens()

        # Nav cachée tant qu'aucun projet n'est chargé
        self._screen_stack.setCurrentIndex(0)   # Scene Manager
        self._set_editor_nav_visible(False)

        self._gba_bar = GbaStatusBar()
        root_layout.addWidget(self._gba_bar)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    # ── Catalogue d'écrans ────────────────────────────────────────
    #
    # L'UNIQUE liste. La barre de navigation, l'ordre du QStackedWidget et la
    # propagation du projet en dérivent tous — il n'y a plus deux listes à
    # tenir d'accord, ni d'index à compter. Ajouter un écran, c'est ajouter
    # une ligne ici et écrire sa fabrique.
    #
    # Une fabrique par écran plutôt qu'une classe : deux écrans ne se
    # construisent pas par simple appel de constructeur, et ceux que la fenêtre
    # ré-adresse plus tard (`self._sprite_editor.select_sprite(...)`) doivent
    # garder une référence nommée. Le branchement propre à un écran vit dans sa
    # fabrique, à côté de sa construction, au lieu d'être dispersé.

    def _screen_catalogue(self) -> list[EditorScreen]:
        return [
            EditorScreen("Scenes",      self._build_scene_manager_screen),
            EditorScreen("Datas",       self._make_data_editor),
            EditorScreen("Backgrounds", self._make_background_editor),
            EditorScreen("Animations",  self._make_sprite_editor),
            EditorScreen("Palettes",    self._make_palette_editor),
            EditorScreen("Texts",       self._make_text_editor),
            EditorScreen("Sounds",      self._make_sound_mixer),
            EditorScreen("Scripts",     self._make_script_editor),
        ] + plugin_screens()

    @property
    def _screen_names(self) -> list[str]:
        return [s.name for s in self._screens]

    def _build_screens(self):
        """Construit chaque écran du catalogue, dans l'ordre, et le monte.

        Le contrat `ProjectScreen` est vérifié ICI et pas par un contrôle
        statique : un écran venu d'un plugin n'existe pour personne avant ce
        moment. Un écran qui ne le remplit pas est monté quand même — il
        s'affiche, il ne reçoit simplement jamais le projet — et le défaut est
        signalé au démarrage plutôt que de se manifester en écran vide.
        """
        self._screen_widgets: list[QWidget] = []
        self.screen_errors: list[str] = []
        for spec in self._screens:
            widget = spec.build()
            self._screen_widgets.append(widget)
            self._screen_stack.addWidget(widget)
            if not isinstance(widget, ProjectScreen):
                self.screen_errors.append(
                    f"« {spec.name} » ne remplit pas le contrat ProjectScreen "
                    f"(pas de load_project) — l'écran ne recevra aucun projet."
                )

    def _make_data_editor(self) -> QWidget:
        self._data_editor = DataEditorScreen()
        return self._data_editor

    def _make_background_editor(self) -> QWidget:
        self._bg_editor = BackgroundEditorScreen()
        return self._bg_editor

    def _make_sprite_editor(self) -> QWidget:
        self._sprite_editor = SpriteEditorScreen()
        return self._sprite_editor

    def _make_palette_editor(self) -> QWidget:
        self._palette_editor = PaletteEditorScreen()
        self._palette_editor.usage_activated.connect(self._open_palette_usage)
        return self._palette_editor

    def _make_text_editor(self) -> QWidget:
        self._text_editor = TextEditorScreen()
        return self._text_editor

    def _make_sound_mixer(self) -> QWidget:
        self._sound_mixer = SoundMixerScreen()
        return self._sound_mixer

    def _make_script_editor(self) -> QWidget:
        self._script_editor = ScriptEditorScreen()
        self._script_editor.back_requested.connect(
            lambda: self._switch_screen("Scenes")
        )
        self._script_editor.build_panel.cartridge_mib_changed.connect(self._set_cartridge_mib)
        return self._script_editor

    def _build_scene_manager_screen(self) -> QWidget:
        # L'écran est construit EN DERNIER (cf. fin de méthode) : il reçoit ses
        # trois colonnes, qui n'existent qu'une fois le splitter peuplé.

        # Splitter horizontal principal : 3 colonnes
        self._h_split = QSplitter(Qt.Orientation.Horizontal)
        self._h_split.setStyleSheet(QSS.splitter)

        # ── Colonne 1 : Project Panel (haut) + Scene Tree (bas) ───
        # Deux questions distinctes, deux panneaux : « quelles scènes/prefabs/
        # scripts existe-t-il dans le projet » (AssetsFinderPanel) et « qu'y
        # a-t-il DANS la scène active » (SceneTreePanel — acteurs + mise en
        # page UI, à la façon du Scene dock de Godot).
        self.assets_finder_panel = AssetsFinderPanel()
        self._setup_menu()
        self.assets_finder_panel.scene_selected.connect(self._on_scene_selected)
        self.assets_finder_panel.scene_add_requested.connect(self._add_scene)
        self.assets_finder_panel.prefab_add_requested.connect(self._add_prefab)
        self.assets_finder_panel.script_opened.connect(self.open_script)
        self.assets_finder_panel.project_created.connect(self._new_project)
        self.assets_finder_panel.project_opened.connect(self._on_home_open)
        self.assets_finder_panel.prefab_uses_requested.connect(
            lambda p: self._inspector.show_prefab_uses(p))
        self.assets_finder_panel.script_uses_requested.connect(
            lambda path: self._inspector.show_script_uses(path))

        self.scene_tree_panel = SceneTreePanel()

        self._left_v_split = QSplitter(Qt.Orientation.Vertical)
        self._left_v_split.setStyleSheet(QSS.splitter)
        self._left_v_split.addWidget(self.scene_tree_panel)
        self._left_v_split.addWidget(self.assets_finder_panel)
        self._left_v_split.setSizes([260, 420])
        self._left_v_split.setStretchFactor(0, 1)
        self._left_v_split.setStretchFactor(1, 1)
        self._h_split.addWidget(self._left_v_split)

        # ── Colonne 2 : Canvas (haut) + Console (bas) ────────────
        self._center_v_split = QSplitter(Qt.Orientation.Vertical)
        self._center_v_split.setStyleSheet(QSS.splitter)

        self.scene_editor = SceneEditor()
        self.scene_editor.scene_changed.connect(self._on_scene_changed)
        self._center_v_split.addWidget(self.scene_editor)

        self.build_panel = BuildPanel()
        self.build_panel.btn_build.clicked.connect(self._run_build)
        self.build_panel.cartridge_mib_changed.connect(self._set_cartridge_mib)
        self.build_panel.setMinimumHeight(80)
        self._center_v_split.addWidget(self.build_panel)
        self._center_v_split.setSizes([600, 160])
        self._center_v_split.setStretchFactor(0, 1)
        self._center_v_split.setStretchFactor(1, 0)

        self._h_split.addWidget(self._center_v_split)

        # ── Colonne 3 : Inspector (pleine hauteur) ────────────────
        self._inspector = DynamicInspector()
        self._inspector.actor_changed.connect(self._on_inspector_actor_changed)
        # Une zone éditée dans l'inspecteur doit se redessiner dans le canvas.
        self._inspector.ui_regions_changed.connect(
            self.scene_editor._reload_ui_regions)
        # Mélange de couleurs : recomposition des pixmaps du canvas, en direct.
        # `refresh_blend` ne relit aucun fichier, on peut donc la brancher sur
        # chaque cran du curseur sans le rendre poussif.
        self._inspector.blend_changed.connect(self.scene_editor.refresh_blend)
        self._inspector.set_script_open_fn(self.open_script)
        self._inspector._scene_insp.set_script_open_fn(self.open_script)
        self._h_split.addWidget(self._inspector)

        # Mise en page UI éditée depuis l'arbre de scène (ajout/suppression/
        # reparentage/réordonnancement/renommage) → sauver ET redessiner le
        # canvas, même contrat qu'avant (porté par SceneTreePanel désormais).
        # À l'inverse, une édition venue de l'inspecteur ou du canvas
        # reconstruit l'arbre.
        self.scene_tree_panel.ui_layout_changed.connect(
            self.scene_editor._save_ui_regions)
        self.scene_tree_panel.ui_layout_changed.connect(
            self.scene_editor._reload_ui_regions)
        self._inspector.ui_regions_changed.connect(
            self.scene_tree_panel.refresh)
        self.scene_editor.scene_changed.connect(
            self.scene_tree_panel.refresh)

        # Bus de sélection — vider sur changement de scène/écran
        self._bus = get_bus()

        # CommandDispatcher — abonnements aux événements engine
        _d = get_dispatcher()
        _d.on("scene_sprites_changed", self.scene_editor._reload_sprites)
        _d.on("actors_list_changed",   self.scene_tree_panel.refresh)
        _d.on("actors_list_changed",   self._update_gba_bar)
        _d.on("actors_list_changed",   self._refresh_actor_inspector)
        _d.on("bg_slot_changed",       self.scene_editor.refresh_bg)
        _d.on("inpaint_layer_changed", self.scene_editor.set_inpaint_layer)
        _d.on("bg_layer_visibility",    self.scene_editor.set_layer_visible)
        _d.on("windows_changed",        self.scene_editor.refresh_windows)
        _d.on("backdrop_changed",       self.scene_editor.refresh_backdrop)
        _d.on("status_message",        lambda msg: self._status.showMessage(msg, 6000))
        _d.on("project_tree_changed",  self.assets_finder_panel.refresh)
        _d.on("project_tree_changed",  self.scene_tree_panel.refresh)
        _d.on("scripts_changed",       self.assets_finder_panel._refresh_scripts)
        # lambda : _text_editor / _script_editor / _palette_editor sont construits
        # plus loin dans _setup_ui que ce bloc d'abonnement — résoudre l'attribut
        # au moment de l'émission, pas ici.
        _d.on("scripts_changed",       lambda: self._text_editor.invalidate_script_usages())
        _d.on("flush_script_edits",    lambda: self._script_editor.flush_pending_edits())
        _d.on("palettes_changed",      lambda: self._palette_editor.refresh())

        self._h_split.setSizes([220, 820, 240])
        self._h_split.setStretchFactor(0, 0)
        self._h_split.setStretchFactor(1, 1)
        self._h_split.setStretchFactor(2, 0)

        screen = SceneManagerScreen(self.assets_finder_panel, self.scene_tree_panel,
                                    self.scene_editor, self._inspector)
        screen_layout = QVBoxLayout(screen)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(0)
        screen_layout.addWidget(self._h_split)
        return screen

    # ── Persistance layout ────────────────────────────────────────

    def _restore_layout(self):
        s = QSettings("GBAEditor", "Layout")
        geom = s.value("geometry")
        if isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        for name, splitter in (
            ("h_split", self._h_split),
            ("center_v_split", self._center_v_split),
            ("left_v_split", self._left_v_split),
        ):
            data = s.value(name)
            if isinstance(data, QByteArray):
                splitter.restoreState(data)

    def _save_layout(self):
        s = QSettings("GBAEditor", "Layout")
        s.setValue("geometry", self.saveGeometry())
        s.setValue("h_split", self._h_split.saveState())
        s.setValue("center_v_split", self._center_v_split.saveState())
        s.setValue("left_v_split", self._left_v_split.saveState())

    def closeEvent(self, event):
        self._save_layout()
        if self.project:
            self.project.commit_all_removals()
        super().closeEvent(event)

    # ── Menu ──────────────────────────────────────────────────────

    def _setup_menu(self):
        mb = self.menuBar()
        mb.setMinimumHeight(32)
        mb.setStyleSheet(
            f"QMenuBar{{background:{C.BG_PANEL};color:{C.TEXT_NORM};font-family:{T.UI_STACK};font-size:{T.MD}px;padding:4px 4px;}}"
            "QMenuBar::item{padding:4px 10px;border-radius:3px;}"
            f"QMenuBar::item:selected{{background:{C.BG_HOVER};}}"
            f"QMenu{{background:{C.BG_RAISED};color:{C.TEXT_NORM};border:1px solid {C.BORDER_MID};font-family:{T.UI_STACK};font-size:{T.MD}px;}}"
            "QMenu::item{padding:5px 20px 5px 12px;}"
            f"QMenu::item:selected{{background:{C.BG_SEL};}}"
        )
        m_file = mb.addMenu("File")
        a_new  = QAction("New project",  self); bind("file.new",  a_new)
        a_open = QAction("Open project", self); bind("file.open", a_open)
        a_save = QAction("Save",         self); bind("file.save", a_save)
        a_save.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        # Réglages du LOGICIEL (devkitPro/mgba, thème, raccourcis, outils
        # tiers — un état par machine) : distinct du menu Game → Project
        # Settings, qui ouvre le projet OUVERT. Même dialogue que le bouton
        # « ⚙ Configure » de la barre toolchain, une seconde porte vers la
        # même donnée.
        a_file_settings = QAction("Settings", self)
        a_quit = QAction("Quit", self); bind("file.quit", a_quit)
        a_new.triggered.connect(self.assets_finder_panel._prompt_new)
        a_open.triggered.connect(self.assets_finder_panel._prompt_open)
        a_save.triggered.connect(self._save_project)
        a_file_settings.triggered.connect(self._open_settings)
        a_quit.triggered.connect(self.close)
        for a in [a_new, a_open, a_save, None, a_file_settings, None, a_quit]:
            if a: m_file.addAction(a)
            else: m_file.addSeparator()
        m_game = mb.addMenu("Game")
        a_build = QAction("Build & Run", self); bind("game.build", a_build)
        a_build.triggered.connect(self._run_build)
        m_game.addAction(a_build)
        m_game.addSeparator()
        a_project_settings = QAction("Project Settings", self)
        a_project_settings.triggered.connect(self._open_project_settings)
        m_game.addAction(a_project_settings)
        mb.addMenu("View")
        m_help = mb.addMenu("Help")
        a_about = QAction("About", self)
        a_about.triggered.connect(lambda: QMessageBox.information(
            self, "GBA Editor", "GBA Editor - homebrew Game Boy Advance"))
        m_help.addAction(a_about)

    # ── Toolbar ───────────────────────────────────────────────────

    def _setup_toolbar(self):
        tb = QToolBar("Principale")
        tb.setMovable(False)
        tb.setMinimumHeight(48)
        tb.setStyleSheet(
            f"QToolBar{{background:{C.BG_RAISED};border-bottom:1px solid {C.BORDER};spacing:4px;padding:4px 12px;}}"
            f"QToolButton{{color:{C.TEXT_NORM};border:none;padding:4px 12px;font-family:{T.UI_STACK};font-size:{T.MD}px;}}"
            f"QToolButton:hover{{background:{C.BG_HOVER};border-radius:4px;}}"
        )
        self.addToolBar(tb)
        self._tb_project_lbl = QPushButton("GBA Editor")
        self._tb_project_lbl.setFont(QFont(T.UI, T.XL, QFont.Weight.DemiBold))
        self._tb_project_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tb_project_lbl.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_MUTED};background:none;border:none;padding:0 12px;}}"
            f"QPushButton:hover{{color:{C.TEXT_DIM};}}"
        )
        self._tb_project_lbl.clicked.connect(self._go_home)
        tb.addWidget(self._tb_project_lbl)
        tb.addSeparator()
        self._tb_build_btn = AnimatedBuildButton()
        self._tb_build_btn.setEnabled(False)
        self._tb_build_btn.clicked.connect(self._run_build)
        tb.addWidget(self._tb_build_btn)
        tb.addSeparator()

        # Boutons Undo / Redo
        _undo_redo_style = (
            f"QToolButton{{color:{C.TEXT_DIM};border:none;padding:4px 10px;"
            f"font-family:{T.UI_STACK};font-size:{T.MD}px;border-radius:4px;}}"
            f"QToolButton:hover:enabled{{background:{C.BG_HOVER};color:{C.TEXT_NORM};}}"
            f"QToolButton:disabled{{color:{C.TEXT_MUTED};}}"
        )
        self._btn_undo = QToolButton()
        self._btn_undo.setText("↩ Undo")
        self._btn_undo.setFont(QFont(T.UI, T.MD))
        self._btn_undo.setStyleSheet(_undo_redo_style)
        self._btn_undo.setEnabled(False)
        self._btn_undo.clicked.connect(self._do_undo)
        tb.addWidget(self._btn_undo)

        self._btn_redo = QToolButton()
        self._btn_redo.setText("↪ Redo")
        self._btn_redo.setFont(QFont(T.UI, T.MD))
        self._btn_redo.setStyleSheet(_undo_redo_style)
        self._btn_redo.setEnabled(False)
        self._btn_redo.clicked.connect(self._do_redo)
        tb.addWidget(self._btn_redo)
        tb.addSeparator()

        from ui.common.reorderable_bar import ReorderableButtonBar
        self._nav_bar = ReorderableButtonBar(self._screen_names)
        self._nav_bar.screen_requested.connect(self._show_screen)
        tb.addWidget(self._nav_bar)
        self._nav_bar.check_screen(0)

    def _open_project_settings(self):
        """Menu Game → Project Settings. Rien de nouveau à construire : c'est
        exactement le panneau que montre déjà `_inspector` quand rien n'est
        sélectionné (`DynamicInspector.on_selection(None)` → `show_project()`,
        cf. dynamic_inspector.py) — `_switch_screen` vide le bus en y allant,
        ce qui déclenche ce même chemin."""
        if not self.project:
            return
        self._switch_screen("Scenes")

    def _show_screen(self, index: int):
        # Un seul catalogue : l'index de nav EST l'index du stack, par
        # construction (`_build_screens` monte dans l'ordre de `_screens`).
        self._screen_stack.setCurrentIndex(index)
        self._history.clear()
        self._bus.clear()
        if index == 0:   # Scene Manager : re-synchroniser avec les assets
            self._refresh_scene_manager()   # modifiés dans un autre écran

    def _refresh_scene_manager(self):
        """En revenant au Scene Manager, re-render le canvas + l'inspecteur
        depuis les assets COURANTS. Le switch d'écran ne recharge rien : une
        modification faite dans le Background/Sprite Editor (recompression,
        inpainting, palettes) resterait sinon invisible ici jusqu'à la
        re-sélection de la scène."""
        se = getattr(self, "scene_editor", None)
        if se is not None and getattr(se, "_project", None) is not None:
            se.refresh_bg()        # re-render les fonds depuis les BackgroundAsset
            se._reload_sprites()   # re-quantifier les acteurs (sprites édités)
        insp = getattr(self, "_inspector", None)
        if insp is not None:
            insp.refresh_current()  # carte palettes / rangées layers (grisées d'asset)

    def _switch_screen(self, name: str):
        names = self._screen_names
        idx = names.index(name) if name in names else 0
        self._show_screen(idx)
        self._nav_bar.check_screen(idx)

    def _go_home(self):
        """Ouvre l'écran d'accueil (HomeScreen) pour changer de projet."""
        picker = HomeScreen(PROJECTS_DIR, self)
        if picker.exec() == QDialog.DialogCode.Accepted and picker.result_path:
            if picker.result_is_new and picker.result_name:
                self._new_project(picker.result_name, picker.result_path)
            else:
                self._open_project(picker.result_path)

    def open_script(self, path):
        """Ouvre un script .lua dans le Script Editor et bascule l'écran."""
        from pathlib import Path
        self._script_editor.load_project(self.project)
        self._script_editor.open_script(Path(path))
        self._switch_screen("Scripts")

    def _open_palette_usage(self, kind: str, name: str):
        """Clic sur une ligne de la carte « USAGE » du Palette Editor :
        ouvrir l'écran qui édite cet élément et l'y sélectionner. La sélection
        vient APRÈS le changement d'écran — _show_screen vide le bus."""
        if not self.project:
            return
        if kind == "sprite":
            self._switch_screen("Animations")
            self._sprite_editor.select_sprite(name)
        elif kind == "background":
            self._switch_screen("Backgrounds")
            self._bg_editor.select_background(name)
        elif kind == "scene":
            index = next((i for i, s in enumerate(self.project.scenes) if s.name == name), None)
            if index is None:
                return
            self._switch_screen("Scenes")
            self._on_scene_selected(index)
        elif kind == "prefab":
            prefab = self.project.prefabs.get(name)
            if prefab is None:
                return
            self._switch_screen("Scenes")
            self._bus.select(prefab)

    # ── Chargement projet ─────────────────────────────────────────

    def _load_default_project(self):
        """Au démarrage : ouvre le projet passé en argument, sinon affiche l'accueil."""
        if self._startup_project and self._startup_project.exists():
            self._open_project(self._startup_project)

    def _on_home_open(self, path: str):
        self._open_project(Path(path))

    def _new_project(self, name: str, path):
        path = Path(path)
        self.project = Project.create(path, name)
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        push_recent(path)
        self._enter_editor()
        self._refresh_ui()
        self._status.showMessage(f"New project: {name}")

    def _open_project(self, path: Path):
        self.project = Project.open(path)
        get_dispatcher().setup(self.project, self._watcher)
        self._watcher.watch_project(path)
        self._connect_watcher()
        push_recent(path)
        self._enter_editor()
        self._refresh_ui()
        self._status.showMessage(f"Project: {self.project.settings.name}")

    def _enter_editor(self):
        """Affiche l'éditeur (nav visible) sur le Scene Manager."""
        self._set_editor_nav_visible(True)
        self._show_screen(0)   # Scene Manager

    def _set_editor_nav_visible(self, visible: bool):
        """Affiche ou masque les boutons de navigation de l'éditeur."""
        self._nav_bar.setVisible(visible)
        self._tb_build_btn.setVisible(visible)
        self._btn_undo.setVisible(visible)
        self._btn_redo.setVisible(visible)
        # La barre compacte n'a d'utilité que dans l'éditeur (bouton Configurer
        # rapide) — l'accueil affiche déjà son propre statut, plus explicite.
        self.toolchain_bar.setVisible(visible)

    def _refresh_ui(self):
        if not self.project: return
        name = self.project.settings.name
        self.setWindowTitle(f"GBA Editor — {name}")
        self._tb_project_lbl.setText(name)   # QPushButton.setText
        can_build = (self.toolchain.devkitpro_ok and self.toolchain.mgba_ok
                     and bool(self.project.scenes))
        tooltip = self._build_tooltip()
        self._tb_build_btn.setEnabled(can_build)
        self._tb_build_btn.setToolTip(tooltip)
        self.build_panel.btn_build.setEnabled(can_build)
        self.build_panel.btn_build.setToolTip(tooltip)
        cart_mib = getattr(self.project.settings, "cartridge_mib", 4)
        self.build_panel.set_cartridge_mib(cart_mib)
        self._script_editor.build_panel.set_cartridge_mib(cart_mib)
        # Le projet part vers chaque écran, dans l'ordre du catalogue. Le Scene
        # Manager propage à ses trois colonnes (SceneManagerScreen.load_project).
        for spec, widget in zip(self._screens, self._screen_widgets):
            if not isinstance(widget, ProjectScreen):
                continue      # signalé au démarrage par _build_screens
            if not spec.plugin:
                widget.load_project(self.project)
                continue
            # Un écran de plugin est du code tiers dans un slot Qt : une
            # exception non rattrapée y fait abandonner le process (PyQt6),
            # donc ouvrir un projet deviendrait impossible à cause d'un écran
            # accessoire. Même traitement que les validateurs de plugin.
            try:
                widget.load_project(self.project)
            except Exception as exc:
                self._status.showMessage(f"Écran « {spec.name} » : {exc}", 8000)
        self._update_gba_bar()

    # ── Slots scène ───────────────────────────────────────────────

    def _on_scene_selected(self, index: int):
        if not self.project: return
        self.project.set_active_scene(index)
        self._history.clear()
        self._bus.clear()      # nouvelle scène = nouvelle sélection
        self.scene_editor.load_project(self.project)
        self._inspector.show_scene(self.project.active_scene, self.project)
        self.assets_finder_panel.refresh()
        self.scene_tree_panel.set_active_scene(self.project.active_scene)
        self._update_gba_bar()
        self._status.showMessage(f"Active scene: {self.project.active_scene.name}")

    def _add_scene(self):
        if not self.project: return
        from core.command_dispatcher import unique_name
        name = unique_name("Scene", {s.name for s in self.project.scenes})
        get_dispatcher().add_scene(name)
        self.assets_finder_panel.refresh()
        self.assets_finder_panel.begin_rename_scene(name)

    # ── Slots prefab ─────────────────────────────────────────────

    def _add_prefab(self):
        if not self.project: return
        from core.command_dispatcher import unique_name
        name = unique_name("Prefab", {p.name for p in self.project.prefabs})
        get_dispatcher().add_prefab(name)
        self.assets_finder_panel.refresh()
        self.assets_finder_panel.begin_rename_prefab(name)

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

    def _save_project(self):
        """
        Ctrl+S global — seul raccourci de sauvegarde de l'app (contexte
        ApplicationShortcut : actif quel que soit l'écran affiché dans le
        QStackedWidget). Flush d'abord l'état en cours d'édition des écrans
        qui ont un concept de "non sauvegardé" avant l'écriture disque —
        les autres écrans persistent déjà à chaque modification.
        """
        if not self.project:
            return
        self.scene_editor.flush_camera_pos()
        self._script_editor.flush_pending_edits()
        self.project.save()
        self._status.showMessage("Project saved", 2000)

    def _refresh_actor_inspector(self):
        """Recharge l'inspecteur d'acteur s'il en montre un — un champ (ex :
        Parent, posé depuis l'arbre de scène par drag & drop) peut avoir
        changé ailleurs que par l'inspecteur lui-même."""
        self._reload_actor_inspector()

    def _reload_actor_inspector(self):
        """Recharge l'inspecteur d'acteur EN RESPECTANT ce qu'il affiche —
        acteur de scène, racine d'un prefab, ou partie d'un prefab (ROADMAP
        v0.23) — pas juste `.load()` à l'aveugle : un prefab EST son actor
        racine (core/models/scene.Prefab), `.load()` seule ne sait pas
        retrouver ce contexte depuis l'Actor nu qu'elle affiche déjà."""
        actor_insp = self._inspector.actor_inspector
        if not actor_insp._actor:
            return
        scene = self.project.active_scene if self.project else None
        if actor_insp._is_prefab_template and actor_insp._prefab:
            actor_insp.load_prefab(actor_insp._prefab, self.project, scene)
        elif actor_insp._child_owner is not None:
            actor_insp.load_child(actor_insp._actor, actor_insp._child_owner,
                                   self.project, scene)
        else:
            actor_insp.load(actor_insp._actor, self.project, scene)

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
        self._btn_undo.setToolTip(f"Undo: {ul}" if ul else "Nothing to undo")
        self._btn_redo.setToolTip(f"Redo: {rl}" if rl else "Nothing to redo")

    def _do_undo(self):
        label = self._history.undo()
        if label:
            self._status.showMessage(f"Undone: {label}", 2000)
            self._flush_after_undo_redo()

    def _do_redo(self):
        label = self._history.redo()
        if label:
            self._status.showMessage(f"Redone: {label}", 2000)
            self._flush_after_undo_redo()

    def _flush_after_undo_redo(self):
        """Rafraîchit l'UI après un undo ou redo."""
        if not self.project:
            return
        # Textes/polices : indépendants de la scène active, donc rafraîchis
        # AVANT le garde-fou ci-dessous (annuler un renommage de clé doit se
        # voir même dans un projet sans scène).
        self._text_editor.refresh()
        if not self.project.active_scene:
            return
        # Sauvegarder l'état actuel (le modèle en mémoire = vérité après undo)
        with self._watcher.suspended():
            self.project.save_scene(self.project.active_scene)
        # Rafraîchissement ciblé : sprites uniquement (pas reset zoom/cam/BG)
        self.assets_finder_panel.refresh()
        self.scene_tree_panel.refresh()
        self.scene_editor._reload_sprites()
        self._update_gba_bar()
        # Recharger l'inspector scène
        si = self._inspector._scene_insp
        if si._scene:
            si.load(si._scene, self.project)
        # Recharger l'inspector si un actor est sélectionné
        self._reload_actor_inspector()

    # ── Réactivité fichiers externes ─────────────────────────────

    def _connect_watcher(self):
        """
        Connecte tous les signaux du ProjectWatcher aux handlers.
        Se déconnecte d'abord : _open_project()/_new_project() rappellent
        cette méthode à chaque changement de projet sur le même watcher
        persistant (self._watcher) — sans ça, chaque événement fichier finit
        par déclencher le handler N fois après N ouvertures de projet.
        """
        w = self._watcher
        for sig in (w.asset_appeared, w.asset_removed, w.asset_modified,
                    w.lua_changed, w.scene_changed):
            try:
                sig.disconnect()
            except TypeError:
                pass   # aucune connexion existante — rien à faire
        w.asset_appeared.connect(self._on_asset_appeared)
        w.asset_removed.connect(self._on_asset_removed)
        w.asset_modified.connect(self._on_asset_modified)
        w.lua_changed.connect(self._on_lua_changed)
        w.scene_changed.connect(self._on_scene_file_changed)

    def _match_asset_route(self, p: Path):
        """Trouve la route (sync/remove/label) pour un fichier assets/<dossier>/*.ext."""
        suffix, parent = p.suffix.lower(), p.parent.name
        for folder, exts, sync_fn, remove_fn, label in self._ASSET_ROUTES:
            if parent == folder and suffix in exts:
                return sync_fn, remove_fn, label
        return None

    def _on_asset_appeared(self, path: str):
        """Nouveau fichier brut détecté dans assets/ — créer le sidecar si nécessaire."""
        if not self.project:
            return
        p = Path(path)
        route = self._match_asset_route(p)
        if not route:
            return
        sync_fn, _, label = route
        # Certains sync_* renvoient un avertissement d'import (police sans
        # glyphe, format illisible…) — le taire laisserait un asset muet à
        # l'écran sans que l'utilisateur sache pourquoi. D'autres renvoient la
        # Resource créée (Sfx/Music) : seule une chaîne est un avertissement.
        result = sync_fn(self.project, p)
        warning = result if isinstance(result, str) else None
        self._refresh_ui()
        if warning:
            self._status.showMessage(warning, 6000)
        else:
            self._status.showMessage(f"{label} imported: {p.name}", 3000)

    def _on_asset_removed(self, path: str):
        """Fichier brut supprimé de assets/ — suppression différée du JSON, UI mise à jour."""
        if not self.project:
            return
        p = Path(path)
        route = self._match_asset_route(p)
        if not route:
            return
        _, remove_fn, label = route
        remove_fn(self.project, p)
        self._refresh_ui()
        self._status.showMessage(f"{label} removed: {p.name}", 3000)

    def _on_asset_modified(self, path: str):
        """Fichier existant modifié dans assets/ (ex. PNG retouché) — rafraîchir la preview."""
        p = Path(path)
        if p.suffix.lower() in (".png", ".bmp") and p.parent.name == "backgrounds":
            # Un fond ne se contente pas d'un rafraîchissement d'affichage : sa
            # compression (palettes + tuiles) est stockée dans le sidecar, et
            # c'est ELLE que lit le build. Sans ré-encodage, l'ancienne image
            # resterait à l'écran ET dans la ROM.
            if not self.project:
                return
            with self._watcher.suspended():   # le sidecar réécrit est NOTRE écriture
                warning = asset_encoding.resync_background_png(self.project, p)
            # Le fond retouché reste celui qu'on regardait : `select` le remet à
            # l'écran plutôt que de renvoyer au premier de la liste.
            self._bg_editor._refresh_finder(select=p.stem)
            self.scene_editor.load_project(self.project)
            self._update_gba_bar()
            self._status.showMessage(warning or f"Background updated: {p.stem}",
                                     8000 if warning else 3000)
            return
        if p.suffix.lower() in (".png", ".bmp") and p.parent.name == "sprites":
            # Comme un fond : les palettes stockées viennent des pixels, il faut
            # les refaire. La ROM, elle, était juste — grit relit le PNG au
            # build — mais l'éditeur affichait les anciennes couleurs (aperçu
            # d'acteur, coût en palettes, allocation de banques).
            if not self.project:
                return
            with self._watcher.suspended():   # le sidecar réécrit est NOTRE écriture
                warning = asset_encoding.resync_sprite_png(self.project, p)
            self._sprite_editor.load_project(self.project)
            self.scene_editor._reload_sprites()
            self._inspector.actor_inspector._refresh_sprite_preview()
            self._update_gba_bar()
            self._status.showMessage(warning or f"Sprite updated: {p.stem}",
                                     8000 if warning else 3000)
            return
        if p.parent.name == "fonts":
            # Planche retouchée : les métriques affichées (glyphes, coût en
            # tuiles) sont dérivées de l'asset, pas du fichier — un refresh
            # suffit, l'asset lui-même n'est jamais ré-analysé automatiquement
            # (sinon on écraserait les corrections de l'utilisateur).
            self._text_editor.refresh()
        self._inspector.actor_inspector._refresh_sprite_preview()
        self._status.showMessage(f"Asset modified: {Path(path).name}", 2000)

    def _on_lua_changed(self, path: str):
        """Un .lua a changé (éditeur externe)."""
        self._inspector.actor_inspector.notify_lua_changed(path)
        self._status.showMessage(f"Script modified: {Path(path).name}", 2000)

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
            self._status.showMessage(f"Scene reloaded: {active.name}", 2000)

    def _open_settings(self, category: str = "Toolchains"):
        """Écran Réglages unique (File → Settings, bouton « ⚙ Configure » de
        la barre toolchain, et le garde-fou du build quand devkitPro/mgba
        manquent) — `category` ne fait que présélectionner l'entrée de
        gauche, les trois autres restent à un clic."""
        dlg = SettingsDialog(self.toolchain, self._external_tools, category, self)
        dlg.exec()
        self.toolchain_bar.refresh()
        if self.project:
            self._refresh_ui()

    def _build_tooltip(self) -> str:
        """Explique pourquoi Build & Run est grisé, ou son raccourci sinon."""
        missing = []
        if not self.toolchain.devkitpro_ok:
            missing.append("devkitPro (ARM + grit)")
        if not self.toolchain.mgba_ok:
            missing.append("mGBA")
        if missing:
            return "Build indisponible — installe : " + " et ".join(missing)
        if self.project and not self.project.scenes:
            return "Ajoute au moins une scène avant de build"
        return "Build & Run (F5)"

    # ── Build ─────────────────────────────────────────────────────

    def _set_cartridge_mib(self, mib: int):
        """Choix de cartouche fait depuis le mot « ROM » du bandeau — même
        réglage, même commande annulable que le combo de l'inspecteur de
        projet (`ProjectInspector._set_setting`) : deux entrées, un seul
        champ. Les DEUX bandeaux (Scene Manager, Script Editor) se
        resynchronisent aussitôt, avant même le prochain build."""
        if not self.project:
            return
        settings = self.project.settings
        old = getattr(settings, "cartridge_mib", 4)
        if old == mib:
            return
        project = self.project

        def _persist():
            # Resynchronise les DEUX bandeaux sur `execute` ET `undo` — même
            # règle que `ProjectInspector._persist` pour son combo.
            project.save()
            cur = getattr(settings, "cartridge_mib", 4)
            self.build_panel.set_cartridge_mib(cur)
            self._script_editor.build_panel.set_cartridge_mib(cur)

        get_history().push(SetFieldCmd(
            settings, "cartridge_mib", old, mib,
            label="Projet.cartridge_mib", persist_fn=_persist,
        ))

    def _run_build(self):
        if not self.project or not self.project.active_scene: return
        if not self.toolchain.devkitpro_ok or not self.toolchain.mgba_ok:
            self._open_settings("Toolchains"); return

        self.build_panel.set_building(True)
        self._tb_build_btn.build_started.emit()
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
        self._worker.on("progress",   lambda f:  self._build_queue.put(("progress", f)))
        self._worker.on("finished",   lambda ok: self._build_queue.put(("finished", ok)))
        self._worker.on("rom_report", lambda r:  self._build_queue.put(("rom_report", r)))
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
                elif kind == "progress":
                    self._tb_build_btn.set_progress(data)
                elif kind == "rom_report":
                    self.build_panel.update_rom_report(data)
                    self._script_editor.build_panel.update_rom_report(data)
                elif kind == "finished":
                    self._build_drain.stop()
                    self._on_build_finished(data)
        except queue.Empty:
            pass

    def _on_build_finished(self, success: bool):
        self.build_panel.set_building(False)
        self._tb_build_btn.build_finished.emit(success)
        if success:
            self.build_panel.log_info("[build] ROM generated — mgba launched")
            self._script_editor.build_panel.log_info("[build] ROM generated — mgba launched")
            self._status.showMessage("Build OK")
        else:
            self.build_panel.log_error("[build] Failed — see console")
            self._script_editor.build_panel.log_error("[build] Failed — see console")
            self._status.showMessage("Build error")
