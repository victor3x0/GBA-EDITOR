"""
GBA Editor — gestion de projet

Structure de projet :

  assets/              ← géré par l'utilisateur
    sprites/           ← PNG + JSON sidecar (auto-créé au dépôt)
    backgrounds/       ← PNG + JSON sidecar
    sounds/            ← WAV, MOD
    sfx/               ← effets sonores
    music/             ← musiques
    fonts/             ← polices
    scripts/           ← Lua (pas de sidecar)
      actors/
      scenes/
      behaviors/

  project/             ← géré exclusivement par l'éditeur
    scenes/            ← une scène par JSON (actors inline)
    prefab/            ← templates d'actors (jamais compilés directement)

  project.json         ← settings globaux (nom, scène de démarrage, auteur)
  build/               ← 100 % jetable (regénéré à chaque build)

Ce module ne porte plus que la classe `Project` (chemins canoniques, CRUD,
orchestration save/load). Le modèle de domaine vit dans `core.models.*`,
l'I/O générique de collection dans `core.resource_manager`, les migrations
de format legacy dans `core.project_migrations`, et l'orchestration
d'encodage d'assets dans `core.asset_sync`. Les noms de modèle sont
ré-exportés ci-dessous pour que le reste du code (`from core.project import
Scene, Actor, ...`) continue de fonctionner sans changement.
"""

import json
import shutil
import copy
from pathlib import Path
from typing import Optional

from core import asset_sync, project_migrations
from core.resource_manager import ResourceManager, safe_filename, _atomic_write

# ── Ré-export du modèle de domaine (compat des ~27 fichiers qui font
#    `from core.project import Scene, Actor, SpriteAsset, ...`) ────────────
from core.models.resource import Resource, MIME_PREFAB_TEMPLATE, MIME_SCRIPT
from core.models.settings import ProjectSettings, GlobalVar, Constant
from core.models.palette import PaletteBank, OWN_PAL_BANK
from core.models.sub_palette import SubPaletteAssetMixin
from core.models.components import (
    CollisionBoxComponent, SpriteComponent, SoundFxComponent, ScriptComponent,
    COMPONENT_REGISTRY, component_type_name, ComponentOwnerMixin,
)
from core.models.sprite import TilePlacement, AnimFrame, StateDirection, AnimState, SpriteAsset
from core.models.background import BackgroundLayer, BackgroundAsset, Tileset
from core.models.audio import Sfx, Music, Font, SFX_FILE_EXTS, MUSIC_FILE_EXTS
from core.models.scene import (
    TILE_EMPTY, TILE_SOLID,
    TILE_SLOPE_L, TILE_SLOPE_R, TILE_SLOPE_L_LO, TILE_SLOPE_L_HI,
    TILE_SLOPE_R_LO, TILE_SLOPE_R_HI,
    TILE_SLOPE_L_INV, TILE_SLOPE_R_INV, TILE_SLOPE_L_LO_INV, TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_R_LO_INV, TILE_SLOPE_R_HI_INV,
    TILE_SLOPE_R_STEEP_HI, TILE_SLOPE_R_STEEP_LO, TILE_SLOPE_L_STEEP_HI, TILE_SLOPE_L_STEEP_LO,
    TILE_SLOPE_R_STEEP_HI_INV, TILE_SLOPE_R_STEEP_LO_INV,
    TILE_SLOPE_L_STEEP_HI_INV, TILE_SLOPE_L_STEEP_LO_INV,
    COLLISION_TILE_SIZE, make_collision_map, SceneLayer, Prefab, Actor, Scene,
)


# ──────────────────────────────────────────────────────────────────
#  Project — conteneur principal
# ──────────────────────────────────────────────────────────────────

class Project:
    """
    Représente un projet GBA ouvert.
    Chemins canoniques et I/O vers le disque.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.settings = ProjectSettings(name=root.name)

        self.backgrounds: ResourceManager[BackgroundAsset] = ResourceManager(self.backgrounds_dir, BackgroundAsset)
        self.sprites:     ResourceManager[SpriteAsset]     = ResourceManager(self.sprites_dir, SpriteAsset)
        self.prefabs:     ResourceManager[Prefab]      = ResourceManager(self.prefab_dir, Prefab)
        self.scenes:      ResourceManager[Scene]       = ResourceManager(self.scenes_dir, Scene)
        self.sfx:         ResourceManager[Sfx]         = ResourceManager(self.sfx_dir, Sfx)
        self.music:       ResourceManager[Music]       = ResourceManager(self.music_dir, Music)
        self.fonts:       ResourceManager[Font]        = ResourceManager(self.fonts_dir, Font)
        self.palettes: ResourceManager[PaletteBank] = ResourceManager(self.palettes_dir, PaletteBank)

        # Variables globales déclarées explicitement dans le projet
        self.globals:     list[GlobalVar] = []

        # Constantes déclarées explicitement dans le projet (lecture seule)
        self.constants:   list[Constant] = []

        # Scène active (index dans self.scenes)
        self._active_scene_idx: int = 0

    # ── Chemins canoniques ────────────────────────────────────────

    @property
    def assets_dir(self) -> Path:
        """Espace libre utilisateur — PNGs bruts, sons..."""
        return self.root / "assets"

    @property
    def project_dir(self) -> Path:
        """Objets moteur (scenes, actors, sprites, tilesets, backgrounds, scripts)."""
        return self.root / "project"

    @property
    def scenes_dir(self) -> Path:
        return self.project_dir / "scenes"

    @property
    def prefab_dir(self) -> Path:
        return self.project_dir / "prefab"

    @property
    def variables_file(self) -> Path:
        """Globals + constants du projet — project/variables.json (pas de dépendance externe)."""
        return self.project_dir / "variables.json"

    @property
    def legacy_palettes_file(self) -> Path:
        """Ancien catalogue monolithique (pré-migration) — project/palettes.json."""
        return self.project_dir / "palettes.json"

    @property
    def palettes_dir(self) -> Path:
        """Catalogue de palettes unifié (illimité, partagé OBJ/BG) — project/palettes/*.json."""
        return self.project_dir / "palettes"

    @property
    def legacy_obj_palettes_dir(self) -> Path:
        """Ancien pool OBJ séparé (pré-fusion) — project/palettes/obj/."""
        return self.project_dir / "palettes" / "obj"

    @property
    def legacy_bg_palettes_dir(self) -> Path:
        """Ancien pool BG séparé (pré-fusion) — project/palettes/bg/."""
        return self.project_dir / "palettes" / "bg"

    @property
    def sprites_dir(self) -> Path:
        return self.assets_dir / "sprites"

    @property
    def tilesets_dir(self) -> Path:
        return self.assets_dir / "backgrounds"

    @property
    def backgrounds_dir(self) -> Path:
        """Dossier des sidecars BackgroundAsset (JSON) — co-localisé avec le PNG
        source dans assets/backgrounds/, même modèle que SpriteAsset
        (assets/sprites/). Migration depuis l'ancien project/backgrounds/ :
        project_migrations.migrate_bg_sidecar_location()."""
        return self.assets_dir / "backgrounds"

    @property
    def background_images_dir(self) -> Path:
        """Dossier des images brutes PNG background."""
        return self.assets_dir / "backgrounds"

    @property
    def sfx_dir(self) -> Path:
        return self.assets_dir / "sfx"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.assets_dir / "fonts"

    @property
    def scripts_dir(self) -> Path:
        return self.assets_dir / "scripts"

    @property
    def scripts_actors_dir(self) -> Path:
        return self.scripts_dir / "actors"

    @property
    def scripts_behaviors_dir(self) -> Path:
        return self.scripts_dir / "behaviors"

    @property
    def scripts_scenes_dir(self) -> Path:
        return self.scripts_dir / "scenes"

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def grit_out_dir(self) -> Path:
        return self.build_dir / "grit_out"

    @property
    def src_dir(self) -> Path:
        return self.build_dir / "src"

    @property
    def obj_dir(self) -> Path:
        return self.build_dir / "obj"

    @property
    def makefile_path(self) -> Path:
        return self.build_dir / "Makefile"

    @property
    def rom_path(self) -> Path:
        return self.build_dir / "rom.gba"

    @property
    def project_file(self) -> Path:
        return self.root / "project.json"

    # ── Scène active ──────────────────────────────────────────────

    @property
    def active_scene(self) -> Optional[Scene]:
        if not self.scenes:
            return None
        idx = max(0, min(self._active_scene_idx, len(self.scenes) - 1))
        return self.scenes[idx]

    def set_active_scene(self, index: int):
        self._active_scene_idx = max(0, min(index, len(self.scenes) - 1))
        if self.active_scene:
            self.settings.start_scene = self.active_scene.name
            self.save_settings()

    # ── Résolution des assets ─────────────────────────────────────

    def asset_abs(self, rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        p = Path(rel)
        return (self.root / p).resolve() if not p.is_absolute() else p

    def asset_rel(self, abs_path: Path) -> str:
        try:
            return str(abs_path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return f"assets/{abs_path.name}"

    def import_asset(self, src: Path, subdir: str = "") -> Path:
        """
        Copie un fichier dans assets/{subdir}/.
        Retourne le chemin absolu dans le projet.
        """
        dst_dir = self.assets_dir / subdir if subdir else self.assets_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    # ── Encodage d'assets (déclenché watcher/import UI) ─────────────
    # Orchestration déléguée à core.asset_sync ; méthodes minces conservées
    # ici car appelées depuis plusieurs écrans UI et le ProjectWatcher.

    def sync_sprite_png(self, png_path: Path) -> Optional[str]:
        return asset_sync.sync_sprite_png(self, png_path)

    @staticmethod
    def apply_sprite_encoding(sprite: "SpriteAsset", c: dict):
        asset_sync.apply_sprite_encoding(sprite, c)

    def remove_sprite_png(self, png_path: Path):
        asset_sync.remove_sprite_png(self, png_path)

    def remove_background_png(self, png_path: Path):
        asset_sync.remove_background_png(self, png_path)

    def remove_sfx_file(self, path: Path):
        asset_sync.remove_sfx_file(self, path)

    def remove_music_file(self, path: Path):
        asset_sync.remove_music_file(self, path)

    def sync_sfx_file(self, path: Path) -> "Sfx":
        return asset_sync.sync_sfx_file(self, path)

    def sync_music_file(self, path: Path) -> "Music":
        return asset_sync.sync_music_file(self, path)

    def sync_background_png(self, png_path: Path) -> Optional[str]:
        return asset_sync.sync_background_png(self, png_path)

    @staticmethod
    def apply_bg_encoding(ba: "BackgroundAsset", source_name: str, c: dict):
        asset_sync.apply_bg_encoding(ba, source_name, c)

    def commit_all_removals(self):
        """Efface définitivement tous les JSONs en attente (appeler à la fermeture)."""
        for mgr in (self.sprites, self.backgrounds, self.sfx, self.music,
                    self.fonts, self.scenes, self.prefabs):
            mgr.commit_deletes()

    # ── Helpers de lookup ────────────────────────────────────────

    def get_background(self, name: str) -> Optional[BackgroundAsset]:
        return self.backgrounds.get(name)

    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        return self.sprites.get(name)

    def get_prefab(self, name: str) -> Optional[Prefab]:
        return self.prefabs.get(name)

    def get_palette(self, name: str) -> Optional[PaletteBank]:
        return self.palettes.get(name)

    def instantiate_actor_from_prefab(self, prefab: Prefab, name: str,
                                       x: int = 112, y: int = 72) -> Actor:
        """Crée un Actor inline depuis un Prefab (copie des Components, aucun lien vivant)."""
        return Actor(
            name        = name,
            prefab_name = prefab.name,
            active      = True,
            components  = copy.deepcopy(prefab.components),
            x=x, y=y,
        )

    # ── Build ─────────────────────────────────────────────────────

    def prepare_build(self):
        for d in (self.grit_out_dir, self.src_dir):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
        self.obj_dir.mkdir(parents=True, exist_ok=True)

    # ── I/O settings globaux ──────────────────────────────────────

    def save_settings(self):
        data = {
            "name":        self.settings.name,
            "start_scene": self.settings.start_scene,
            "author":      self.settings.author,
            "version":     self.settings.version,
            "palette_auto_import_enabled": self.settings.palette_auto_import_enabled,
            "backdrop_color": self.settings.backdrop_color,
        }
        _atomic_write(self.project_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_settings(self):
        if not self.project_file.exists():
            return
        d = json.loads(self.project_file.read_text(encoding="utf-8"))
        self.settings.name        = d.get("name", self.root.name)
        self.settings.start_scene = d.get("start_scene", "")
        self.settings.author      = d.get("author", "")
        self.settings.version     = d.get("version", "0.1")
        self.settings.palette_auto_import_enabled = d.get("palette_auto_import_enabled", True)
        self.settings.backdrop_color = d.get("backdrop_color", 0)

    # ── I/O variables (globals + constants) ─────────────────────────
    # Assets côté éditeur sans dépendance externe -> project/variables.json,
    # pas project.json (config racine uniquement, cf. ARCHITECTURE.md).

    def save_variables(self):
        data = {
            "globals": [
                {"name": g.name, "type": g.type, "default": g.default, "desc": g.desc}
                for g in self.globals
            ],
            "constants": [
                {"name": c.name, "type": c.type, "value": c.value, "desc": c.desc}
                for c in self.constants
            ],
        }
        self.project_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.variables_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_variables(self):
        self.globals = []
        self.constants = []
        if not self.variables_file.exists():
            return
        d = json.loads(self.variables_file.read_text(encoding="utf-8"))
        self.globals = [
            GlobalVar(
                name    = g.get("name", "var"),
                type    = g.get("type", "int"),
                default = g.get("default", 0),
                desc    = g.get("desc", ""),
            )
            for g in d.get("globals", [])
        ]
        self.constants = [
            Constant(
                name  = c.get("name", "const"),
                type  = c.get("type", "int"),
                value = c.get("value", 0),
                desc  = c.get("desc", ""),
            )
            for c in d.get("constants", [])
        ]

    # ── Renommage (supprime l'ancien fichier + répare les références) ──
    # ResourceManager.rename() seul ne suffit pas : il faut aussi mettre à
    # jour tout ce qui référence l'ancien nom ailleurs dans le projet.

    def rename_background(self, bg: BackgroundAsset, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == bg.name:
            return
        old_name = bg.name
        # Renommer aussi le PNG source : un BackgroundAsset est keyé par le stem
        # de son PNG (name == stem(source)). Sans ça, la réconciliation des fonds
        # recréerait un asset orphelin depuis l'ancien PNG au prochain chargement.
        old_png = (self.background_images_dir / bg.asset) if bg.asset else None
        if old_png and old_png.exists():
            new_png = old_png.with_name(f"{new_name}{old_png.suffix}")
            if not new_png.exists():
                old_png.rename(new_png)
                bg.asset = new_png.name
        self.backgrounds.rename(bg, new_name)
        # Met à jour les layers des scènes qui référencent ce fond par nom.
        for scene in self.scenes:
            touched = False
            for L in scene.background_layers:
                if L.background_name == old_name:
                    L.background_name = new_name
                    touched = True
            if touched:
                self.save_scene(scene)

    def rename_sprite(self, sprite: SpriteAsset, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == sprite.name:
            return
        old_name = sprite.name
        # Renommer aussi le PNG source : un SpriteAsset est keyé par le stem
        # de son PNG (comme BackgroundAsset). Sans ça, la réconciliation des
        # sprites recréerait un asset orphelin depuis l'ancien PNG au prochain
        # chargement.
        old_png = self.asset_abs(sprite.asset) if sprite.asset else None
        if old_png and old_png.exists():
            new_png = old_png.with_name(f"{new_name}{old_png.suffix}")
            if not new_png.exists():
                old_png.rename(new_png)
                sprite.asset = self.asset_rel(new_png)
        self.sprites.rename(sprite, new_name)
        # Met à jour les SpriteComponent (Actors inline dans les scènes, et
        # Prefabs) qui référencent ce sprite par nom.
        for scene in self.scenes:
            touched = False
            for actor in scene.actors:
                for comp in actor.components:
                    if isinstance(comp, SpriteComponent) and comp.sprite_name == old_name:
                        comp.sprite_name = new_name
                        touched = True
            if touched:
                self.save_scene(scene)
        for prefab in self.prefabs:
            touched = False
            for comp in prefab.components:
                if isinstance(comp, SpriteComponent) and comp.sprite_name == old_name:
                    comp.sprite_name = new_name
                    touched = True
            if touched:
                self.save_prefab(prefab)

    def rename_scene(self, scene: Scene, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == scene.name:
            return
        old_name = scene.name
        self.scenes.rename(scene, new_name)
        if self.settings.start_scene == old_name:
            self.settings.start_scene = new_name
            self.save_settings()

    # ── CRUD variables (globals / constants) ────────────────────────
    # Unicité vérifiée PAR TYPE uniquement : un global et une constante
    # peuvent partager un nom (préfixes C distincts : g_<nom> / CONST_<NOM>).

    def _variable_list(self, kind: str) -> list:
        """kind: "global" | "const" """
        return self.constants if kind == "const" else self.globals

    def variable_name_taken(self, kind: str, name: str, *, exclude=None) -> bool:
        return any(e is not exclude and e.name == name for e in self._variable_list(kind))

    def add_variable(self, kind: str, name: str):
        """Ajoute un global ou une constante. Retourne None si le nom est vide ou déjà pris (par type)."""
        name = name.strip()
        if not name or self.variable_name_taken(kind, name):
            return None
        entry = Constant(name=name) if kind == "const" else GlobalVar(name=name)
        self._variable_list(kind).append(entry)
        self.save_variables()
        return entry

    def rename_variable(self, kind: str, entry, new_name: str) -> bool:
        """Renomme en place. Retourne False (no-op) si le nom est vide/inchangé/déjà pris."""
        new_name = new_name.strip()
        if not new_name or new_name == entry.name:
            return False
        if self.variable_name_taken(kind, new_name, exclude=entry):
            return False
        entry.name = new_name
        self.save_variables()
        return True

    # ── Raccourcis de sauvegarde par objet (delegue au ResourceManager) ──

    def save_scene(self, scene: Scene):                    self.scenes.save(scene)
    def save_prefab(self, prefab: Prefab):                 self.prefabs.save(prefab)
    def save_sprite(self, sprite: SpriteAsset):           self.sprites.save(sprite)
    def save_background(self, bg: BackgroundAsset):       self.backgrounds.save(bg)
    def save_sfx(self, sfx: Sfx):                         self.sfx.save(sfx)
    def save_music(self, music: Music):                   self.music.save(music)
    def save_tileset(self, tileset):                      pass  # stub rétrocompat

    # ── Sauvegarde / chargement global ────────────────────────────

    def save(self):
        self.save_settings()
        self.save_variables()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def load(self):
        # S'assurer que tous les sous-dossiers existent
        for sub in ("project/scenes", "project/prefab",
                    "project/palettes",
                    "assets/sprites", "assets/backgrounds",
                    "assets/scripts", "assets/scripts/actors",
                    "assets/scripts/scenes", "assets/scripts/behaviors",
                    "assets/sfx", "assets/music", "assets/fonts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        project_migrations.migrate_on_load(self)
        self.load_settings()
        self.load_variables()
        self.palettes.load()
        project_migrations.seed_or_migrate_palettes(self)
        self.sprites.load()
        project_migrations.migrate_sprite_palettes(self)
        self.sfx.load()
        self.music.load()
        self.fonts.load()
        project_migrations.migrate_bg_sidecar_location(self)
        self.backgrounds.load()
        project_migrations.reconcile_backgrounds(self)
        self.prefabs.load()
        project_migrations.reconcile_sfx_and_music(self)
        project_migrations.load_scenes_with_migration(self)
        project_migrations.migrate_scene_backgrounds(self)

    # ── Création / ouverture ──────────────────────────────────────

    @classmethod
    def create(cls, root: Path, name: str) -> "Project":
        """Crée un nouveau projet vide avec la structure de dossiers."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "assets/sprites",
            "assets/backgrounds",
            "assets/sounds",
            "assets/sfx",
            "assets/music",
            "assets/fonts",
            "assets/scripts",
            "assets/scripts/actors",
            "assets/scripts/scenes",
            "assets/scripts/behaviors",
            "project/scenes",
            "project/prefab",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)

        proj = cls(root)
        proj.settings.name = name

        # Peupler le catalogue de palettes par défaut dès la création (sinon
        # le seeding n'a lieu qu'au prochain load() et les palettes n'apparaissent
        # qu'après un redémarrage). Réutilise la logique de seed/migration :
        # palettes.items étant vide, on retombe sur les presets par défaut.
        project_migrations.seed_or_migrate_palettes(proj)

        # Créer une scène de démarrage par défaut
        default_scene = Scene(name="Scene_01")
        proj.scenes.append(default_scene)
        proj.settings.start_scene = "Scene_01"

        proj.save()

        # Launcher .bat — ouvre l'éditeur directement sur ce projet
        editor_dir = Path(__file__).parent
        editor_root = editor_dir.parent
        bat_path = root / f"{name}.bat"
        bat_path.write_text(
            f"@echo off\r\n"
            f"cd /d \"{editor_root}\"\r\n"
            f"python editor\\main.py --project \"{root}\"\r\n",
            encoding="utf-8"
        )

        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        """Ouvre un projet existant."""
        proj = cls(root)
        proj.load()
        return proj
