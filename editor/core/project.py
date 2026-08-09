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
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from core import asset_sync, project_migrations
from core.app_paths import IS_FROZEN
from core.resource_manager import ResourceManager, safe_filename, _atomic_write
# Domaines de référence Lua — un renommage d'élément met à jour les scripts
# qui le citent (cf. rename_lua_refs / scripting/refactor.py).
from scripting.api import (
    DOMAIN_SCENE, DOMAIN_PREFAB, DOMAIN_SFX, DOMAIN_MUSIC, DOMAIN_FONT,
    DOMAIN_TEXT, DOMAIN_GLOBAL, DOMAIN_CONST, DOMAIN_ACTOR, DOMAIN_ANIM,
    DOMAIN_REGION, DOMAIN_IMAGE,
)

# ── Ré-export du modèle de domaine (compat des ~27 fichiers qui font
#    `from core.project import Scene, Actor, SpriteAsset, ...`) ────────────
from core.models.resource import Resource, MIME_PREFAB_TEMPLATE, MIME_SCRIPT
from core.models.settings import ProjectSettings, GlobalVar, Constant
from core.models.text import (
    Text, key_from_path as text_key_from_path, norm_path as norm_text_path,
    new_id as new_text_id,
)
from core.models.ids import new_id
from core.models.palette import PaletteBank, PaletteUsage, OWN_PAL_BANK
from core.models.sub_palette import SubPaletteAssetMixin
from core.models.components import (
    CollisionBoxComponent, SpriteComponent, SoundFxComponent, ScriptComponent,
    COMPONENT_REGISTRY, component_type_name, ComponentOwnerMixin,
)
from core.models.sprite import TilePlacement, AnimFrame, StateDirection, AnimState, SpriteAsset
from core.models.background import BackgroundLayer, BackgroundAsset, Tileset
from core.models.audio import Sfx, Music, SFX_FILE_EXTS, MUSIC_FILE_EXTS
from core.models.font import Font, Glyph, FONT_FILE_EXTS
from core.models.ui_region import UILayout
from core.models.scene import (
    TILE_EMPTY, TILE_SOLID,
    TILE_SLOPE_L, TILE_SLOPE_R, TILE_SLOPE_L_LO, TILE_SLOPE_L_HI,
    TILE_SLOPE_R_LO, TILE_SLOPE_R_HI,
    TILE_SLOPE_L_INV, TILE_SLOPE_R_INV, TILE_SLOPE_L_LO_INV, TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_R_LO_INV, TILE_SLOPE_R_HI_INV,
    TILE_SLOPE_R_STEEP_HI, TILE_SLOPE_R_STEEP_LO, TILE_SLOPE_L_STEEP_HI, TILE_SLOPE_L_STEEP_LO,
    TILE_SLOPE_R_STEEP_HI_INV, TILE_SLOPE_R_STEEP_LO_INV,
    TILE_SLOPE_L_STEEP_HI_INV, TILE_SLOPE_L_STEEP_LO_INV,
    COLLISION_TILE_SIZE, make_collision_map, SceneLayer, Prefab, Actor, Scene, WindowSlot,
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
        self.ui_layouts: ResourceManager[UILayout] = ResourceManager(self.ui_layouts_dir, UILayout)

        # Variables globales déclarées explicitement dans le projet
        self.globals:     list[GlobalVar] = []

        # Constantes déclarées explicitement dans le projet (lecture seule)
        self.constants:   list[Constant] = []

        # Table des textes destinés au joueur (traduisibles, cf. models/text.py)
        self.texts:       list[Text] = []

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
    def texts_file(self) -> Path:
        """Table des textes du joueur — project/texts.json.

        Un seul fichier plutôt qu'un par entrée (contrairement aux palettes) :
        on parle de centaines d'entrées courtes, et un traducteur veut tout voir
        d'un coup. La v0.8 ajoutera `texts.<langue>.json` à côté."""
        return self.project_dir / "texts.json"

    @property
    def ui_layouts_dir(self) -> Path:
        """Mises en page d'UI — project/ui_layouts/*.json.

        Un fichier par mise en page (contrairement aux textes, monolithiques) :
        une mise en page est un objet qu'on renomme, duplique et partage entre
        scènes, donc qui mérite une identité de fichier — comme une palette."""
        return self.project_dir / "ui_layouts"

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
        if self.active_scene and self.settings.last_scene != self.active_scene.name:
            # Mémorise la scène ouverte pour la prochaine session — surtout PAS
            # start_scene, qui est le point de départ du jeu choisi par l'auteur
            # (cf. ProjectInspector).
            self.settings.last_scene = self.active_scene.name
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

    def sync_font_file(self, path: Path) -> Optional[str]:
        return asset_sync.sync_font_file(self, path)

    def remove_font_file(self, path: Path):
        asset_sync.remove_font_file(self, path)

    @staticmethod
    def apply_bg_encoding(ba: "BackgroundAsset", source_name: str, c: dict):
        asset_sync.apply_bg_encoding(ba, source_name, c)

    def commit_all_removals(self):
        """Efface définitivement tous les JSONs en attente (appeler à la fermeture)."""
        for mgr in (self.sprites, self.backgrounds, self.sfx, self.music,
                    self.fonts, self.scenes, self.prefabs, self.ui_layouts,
                    self.palettes):
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

    def get_ui_layout(self, name: str) -> Optional[UILayout]:
        return self.ui_layouts.get(name)

    def ui_backgrounds(self, role: str = "") -> list[BackgroundAsset]:
        """Fonds d'INTERFACE du projet, éventuellement filtrés sur leur rôle
        (`UI_ROLE_NINE` / `UI_ROLE_BG`). C'est ce que propose le menu de fond
        d'un `UIPanel` — d'où le filtre : un cadre étirable et une image posée
        ne s'étalent pas pareil, les mélanger dans une liste unique laisserait
        choisir un cadre sans marges."""
        from core.models.background import KIND_UI
        return [b for b in self.backgrounds
                if b.kind == KIND_UI and (not role or b.ui_role == role)]

    def animated_backgrounds(self) -> list[BackgroundAsset]:
        from core.models.background import KIND_ANIMATED
        return [b for b in self.backgrounds if b.kind == KIND_ANIMATED]

    def scene_ui_layout(self, scene) -> Optional[UILayout]:
        """Mise en page d'une scène, ou None si elle n'en référence aucune (ou
        si la référence est cassée — un nom qui ne résout plus ne doit pas
        faire tomber le chargement, le validateur le signalera)."""
        name = getattr(scene, "ui_layout", "")
        return self.ui_layouts.get(name) if name else None

    def all_regions(self) -> list:
        """[(UILayout, élément de texte)] de tout le projet, ordre STABLE.

        C'est cet ordre qui devient l'index dans la table C `g_ui_regions` —
        même convention que les textes et les polices. Ordre des mises en page,
        puis des slots dans chacune."""
        return [(lay, r) for lay in self.ui_layouts for r in lay.slots]

    def all_images(self) -> list:
        """[(UILayout, UIImage)] de tout le projet — l'index de `g_ui_images`.

        Table séparée de `all_regions`, exactement comme les deux propriétés du
        modèle : un script qui vise une image et un script qui vise un texte ne
        parlent pas de la même chose, et un index partagé obligerait le runtime
        à trier."""
        return [(lay, im) for lay in self.ui_layouts for im in lay.images]

    def region_names(self) -> list[str]:
        """Noms de slot de texte du projet entier — l'espace de nommage des
        constantes `REGION_*`, donc ce contre quoi vérifier l'unicité."""
        return [r.name for _, r in self.all_regions()]

    def image_names(self) -> list[str]:
        """Noms d'image du projet entier — l'espace des constantes `IMAGE_*`."""
        return [im.name for _, im in self.all_images()]

    def ui_element_names(self) -> list[str]:
        """TOUS les noms d'élément d'UI du projet. L'unicité se cherche ici et
        pas par type : les deux espaces de constantes (`REGION_*`, `IMAGE_*`)
        sont distincts côté C, mais l'auteur, lui, ne devrait jamais avoir à
        savoir que deux éléments homonymes de types différents sont légaux —
        il les verrait côte à côte dans l'arbre sans pouvoir les distinguer."""
        return [e.name for lay in self.ui_layouts for e in lay.elements]

    def ui_layout_users(self, name: str) -> list:
        """Scènes qui référencent cette mise en page. Alimente le badge
        « partagée — N scènes » : éditer une région depuis le canvas modifie un
        objet commun, et le taire casserait N scènes en un geste."""
        return [s for s in self.scenes if getattr(s, "ui_layout", "") == name]

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
        self._anon_texts = self.collect_literal_texts()

    # ── Littéraux de script → entrées anonymes ────────────────────
    # `text.draw` est la seule primitive à accepter un littéral en plus d'une
    # clé (ROADMAP v0.3.2, 2026-07-27) : un accès rapide hors interface, au prix
    # assumé de la traduction. À la compilation il devient une entrée ANONYME de
    # la table, donc le runtime ne connaît qu'un seul chemin (mêmes codepoints,
    # même balisage, mêmes valeurs interpolées).

    def collect_literal_texts(self) -> list:
        """Entrées anonymes à ajouter à la table pour ce build.

        Le repérage est celui du renommage (`iter_refs`, par DOMAINE) : une
        chaîne qui matche une clé existante n'en est pas un, c'est la référence
        à cette entrée."""
        from core.models.text import Text
        from scripting.refactor import iter_refs, script_paths
        from scripting.api import DOMAIN_TEXT, LITERAL_TEXT_CALLS, anon_text_key
        keys = {t.key for t in self.texts}
        found: dict[str, str] = {}
        for path in script_paths(self):
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ref in iter_refs(src, path=path, domain=DOMAIN_TEXT):
                if ref.api_key in LITERAL_TEXT_CALLS and ref.value not in keys:
                    found.setdefault(anon_text_key(ref.value), ref.value)
        return [Text(key=k, content=v) for k, v in sorted(found.items())]

    def scene_scripts(self, scene) -> tuple[list, bool]:
        """(scripts Lua qu'une scène peut exécuter, en reste-t-il d'opaques ?).

        Le script de la scène, celui de chacun de ses actors, et ceux de TOUS
        les prefabs : un prefab est poolé au niveau projet et `actor.spawn()`
        s'appelle de n'importe où, donc rien ne dit qu'il ne tournera pas ici.

        Le second booléen dit qu'un script échappe à l'analyse : introuvable sur
        disque, ou écrit en C natif (lequel peut appeler n'importe quelle
        fonction du moteur hors catalogue Lua). L'appelant doit en tirer « je ne
        sais pas », jamais « il n'y a rien »."""
        out, opaque = [], False

        def add(rel):
            nonlocal opaque
            if not rel:
                return
            ap = self.asset_abs(rel)
            if ap is None:
                return
            if ap.suffix.lower() == ".lua":
                if ap.exists():
                    out.append(ap)
                else:
                    opaque = True
            else:
                opaque = True      # .c natif : hors de portée de l'analyse

        add(getattr(scene, "script", ""))
        owners = list(getattr(scene, "actors", [])) + list(getattr(self, "prefabs", []))
        for owner in owners:
            comp = owner.get_component("script") if hasattr(owner, "get_component") else None
            if comp and getattr(comp, "active", True):
                add(getattr(comp, "script", ""))
        return out, opaque

    def build_texts(self) -> list:
        """La table de textes VUE PAR LE BUILD : les entrées du projet, puis les
        littéraux des scripts.

        Les entrées réelles gardent leur rang — c'est lui qui fait l'index dans
        `g_texts`, et un littéral ajouté ne doit décaler aucune clé."""
        return list(self.texts) + list(getattr(self, "_anon_texts", []))

    # ── I/O settings globaux ──────────────────────────────────────

    def save_settings(self):
        data = {
            "name":        self.settings.name,
            "start_scene": self.settings.start_scene,
            "last_scene":  self.settings.last_scene,
            "author":      self.settings.author,
            "version":     self.settings.version,
            "backdrop_color": self.settings.backdrop_color,
        }
        _atomic_write(self.project_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_settings(self):
        if not self.project_file.exists():
            return
        d = json.loads(self.project_file.read_text(encoding="utf-8"))
        self.settings.name        = d.get("name", self.root.name)
        self.settings.start_scene = d.get("start_scene", "")
        # Projets antérieurs à la séparation start_scene/last_scene : start_scene
        # y servait aussi de « dernière scène ouverte ».
        self.settings.last_scene  = d.get("last_scene", self.settings.start_scene)
        self.settings.author      = d.get("author", "")
        self.settings.version     = d.get("version", "0.1")
        # `palette_auto_import_enabled` des anciens project.json est ignoré :
        # le réservoir auto-import est abandonné (cf. ROADMAP.md v0.2), la clé
        # disparaît du fichier à la prochaine sauvegarde.
        self.settings.backdrop_color = d.get("backdrop_color", 0)

    def text_values(self) -> dict:
        """Valeurs à substituer aux marqueurs `$nom` d'un texte, à l'ÉDITION.

        Un global n'a de valeur courante qu'en jeu : l'éditeur montre sa valeur
        INITIALE, la seule qu'il connaisse et celle que la ROM affichera avant
        que quoi que ce soit ne l'ait changée. Une constante, elle, ne bouge
        jamais — l'aperçu montre exactement ce que l'encodeur cuira."""
        out = {g.name: g.default for g in self.globals}
        out.update({c.name: c.value for c in self.constants})
        return out

    # ── I/O variables (globals + constants) ─────────────────────────
    # Assets côté éditeur sans dépendance externe -> project/variables.json,
    # pas project.json (config racine uniquement, cf. ARCHITECTURE.md).

    def save_variables(self):
        data = {
            "globals": [
                {"id": g.id, "name": g.name, "type": g.type,
                 "default": g.default, "desc": g.desc}
                for g in self.globals
            ],
            "constants": [
                {"id": c.id, "name": c.name, "type": c.type,
                 "value": c.value, "desc": c.desc}
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
                id      = int(g.get("id", 0)),
            )
            for g in d.get("globals", [])
        ]
        self.constants = [
            Constant(
                name  = c.get("name", "const"),
                type  = c.get("type", "int"),
                value = c.get("value", 0),
                desc  = c.get("desc", ""),
                id    = int(c.get("id", 0)),
            )
            for c in d.get("constants", [])
        ]

    # ── Identité des variables ──────────────────────────────────────

    def all_variables(self) -> list:
        """Globals puis constantes — l'ordre d'affichage, pas un ordre de C."""
        return list(self.globals) + list(self.constants)

    def variable_by_id(self, vid: int):
        """La variable d'id `vid`, ou None. C'est le chemin que suit une
        RÉFÉRENCE stockée dans un fichier de données : elle survit au
        renommage, contrairement à une résolution par nom."""
        if not vid:
            return None
        return next((v for v in self.all_variables() if v.id == vid), None)

    def variable_by_name(self, kind: str, name: str):
        """La variable nommée `name`, ou None. Sert à résoudre ce qui est écrit
        À LA MAIN (Lua, `$nom` d'un texte), pas les données."""
        return next((v for v in self._variable_list(kind) if v.name == name), None)

    def assign_variable_ids(self) -> int:
        """Donne un id aux variables qui n'en ont pas — projets d'avant
        l'identité opaque. Idempotent : une variable qui en a un n'y touche
        pas, donc rejouer la migration ne renumérote rien."""
        taken = {v.id for v in self.all_variables() if v.id}
        n = 0
        for v in self.all_variables():
            if not v.id:
                v.id = new_id(taken)
                taken.add(v.id)
                n += 1
        return n

    # ── I/O textes (table de chaînes destinées au joueur) ───────────

    def save_texts(self):
        data = {"texts": [t.to_dict() for t in self.texts]}
        self.project_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.texts_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_texts(self):
        self.texts = []
        if not self.texts_file.exists():
            return
        d = json.loads(self.texts_file.read_text(encoding="utf-8"))
        self.texts = [Text.from_dict(t) for t in d.get("texts", [])]
        self._repair_texts()

    def _repair_texts(self):
        """Rattrape un fichier édité à la main : id manquant ou dupliqué, clé
        manquante ou dupliquée. L'id prime — c'est lui l'identité ; une clé en
        double est celle qu'on renumérote."""
        seen_ids: set[int] = set()
        seen_keys: set[str] = set()
        for t in self.texts:
            t.path = norm_text_path(t.path)
            if not t.id or t.id in seen_ids:
                t.id = new_text_id(seen_ids)
            seen_ids.add(t.id)
            if not t.key or t.key in seen_keys:
                t.key = text_key_from_path(t.path, taken=seen_keys)
            seen_keys.add(t.key)

    # ── CRUD textes ─────────────────────────────────────────────────

    def text_keys(self) -> set[str]:
        return {t.key for t in self.texts}

    def get_text(self, key: str) -> Optional[Text]:
        """Résolution par clé — l'unique chemin de résolution côté script."""
        return next((t for t in self.texts if t.key == key), None)

    def get_text_by_id(self, tid: int) -> Optional[Text]:
        """Résolution par id — pour les références stockées dans les fichiers
        de données (inspecteurs, scènes), insensibles au renommage."""
        return next((t for t in self.texts if t.id == tid), None)

    def new_text(self, content: str = "", scene: str = "", path=None) -> Text:
        """Crée une entrée. La clé dérive du chemin de rangement, jamais du
        contenu (cf. models/text.py).

        Un texte créé depuis une scène naît sous un nœud portant son nom :
        l'arbre se remplit tout seul, et le chemin par défaut situe déjà."""
        p = norm_text_path(path if path is not None else ([scene] if scene else []))
        t = Text(
            id      = new_text_id({x.id for x in self.texts}),
            key     = text_key_from_path(p, taken=self.text_keys()),
            path    = p,
            content = content,
            scene   = scene,
        )
        self.texts.append(t)
        return t

    def text_path_key(self, text: Text) -> str:
        """Clé que le chemin actuel de `text` produirait — sans l'appliquer.
        Sa propre clé est exclue des collisions, sinon un texte déjà posé au
        bon endroit se verrait proposer un rang `_02` contre lui-même."""
        return text_key_from_path(text.path, taken=self.text_keys() - {text.key})

    def rename_text_key(self, text: Text, new_key: str) -> bool:
        """Renommage MANUEL. Retourne False si le nom est vide ou déjà pris —
        l'appelant (UI) affiche l'erreur. Les appels text.draw("clé") des
        scripts suivent (cf. rename_lua_refs).

        La clé se DÉTACHE alors du chemin (`auto_key=False`) : elle appartient
        à l'utilisateur, ranger le texte ailleurs ne la touchera plus."""
        return self._apply_text_key(text, new_key, manual=True)

    def resync_text_key(self, text: Text) -> Optional[str]:
        """Recale une clé automatique sur le chemin de rangement, et retourne
        la nouvelle clé (None si rien n'a bougé).

        No-op sur une clé nommée à la main — c'est tout l'intérêt de
        `auto_key` : le rangement reste un geste cosmétique tant que
        l'utilisateur n'a pas pris la main sur la clé."""
        if not text.auto_key:
            return None
        want = self.text_path_key(text)
        return want if (want != text.key
                        and self._apply_text_key(text, want, manual=False)) else None

    def restore_text_key(self, text: Text, key: str) -> bool:
        """Repose une clé telle quelle sans la marquer « nommée à la main ».

        Sert à l'ANNULATION d'un rangement : rejouer `resync_text_key` en sens
        inverse ne rendrait pas forcément la même clé (le rang `_NN` dépend des
        clés prises à cet instant), il faut donc remettre l'exacte ancienne."""
        return self._apply_text_key(text, key, manual=False)

    def _apply_text_key(self, text: Text, new_key: str, *, manual: bool) -> bool:
        new_key = (new_key or "").strip()
        if not new_key or any(t.key == new_key and t is not text for t in self.texts):
            return False
        old_key = text.key
        if new_key == old_key:
            return True
        with self._renaming():
            refs = self.rename_lua_refs(DOMAIN_TEXT, old_key, new_key)
            text.key = new_key
            if manual:
                text.auto_key = False
        self._notify_renamed("Text", old_key, new_key, refs)
        return True

    def delete_text(self, text: Text):
        if text in self.texts:
            self.texts.remove(text)

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
        self._notify_renamed("Background", old_name, new_name)

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
        # Aucun domaine Lua : un sprite se référence par son composant, pas
        # depuis un script (les animations, elles, ont DOMAIN_ANIM).
        self._notify_renamed("Sprite", old_name, new_name)

    def rename_scene(self, scene: Scene, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == scene.name:
            return
        old_name = scene.name
        with self._renaming():
            self.scenes.rename(scene, new_name)
            touched = False
            for field in ("start_scene", "last_scene"):
                if getattr(self.settings, field) == old_name:
                    setattr(self.settings, field, new_name)
                    touched = True
            if touched:
                self.save_settings()
            refs = self.rename_lua_refs(DOMAIN_SCENE, old_name, new_name)
        self._notify_renamed("Scene", old_name, new_name, refs)

    def rename_prefab(self, prefab, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == prefab.name:
            return
        old_name = prefab.name
        with self._renaming():
            self.prefabs.rename(prefab, new_name)
            # Instances placées dans les scènes : elles pointent le template par nom.
            for scene in self.scenes:
                touched = False
                for actor in scene.actors:
                    if getattr(actor, "prefab_name", "") == old_name:
                        actor.prefab_name = new_name
                        touched = True
                if touched:
                    self.save_scene(scene)
            refs = self.rename_lua_refs(DOMAIN_PREFAB, old_name, new_name)
        self._notify_renamed("Prefab", old_name, new_name, refs)

    def rename_actor(self, actor, new_name: str, scene: Optional[Scene] = None):
        """Actor placé dans une scène (pas un template de prefab — cf.
        rename_prefab). `scene` est sauvegardée si fournie."""
        new_name = new_name.strip()
        if not new_name or new_name == actor.name:
            return
        old_name = actor.name
        with self._renaming():
            refs = self.rename_lua_refs(DOMAIN_ACTOR, old_name, new_name)
            actor.name = new_name
            if scene is not None:
                self.save_scene(scene)
        self._notify_renamed("Actor", old_name, new_name, refs)

    def rename_ui_element(self, layout, element, new_name: str) -> str:
        """Renomme un élément d'une mise en page UI (texte, conteneur, image).

        **Unicité sur TOUT le projet, quel que soit le type** (cf.
        `ui_element_names`) : un texte se résout en `REGION_*` et une image en
        `IMAGE_*`, deux constantes C projet-globales, et le conteneur partage
        l'espace des refs `parent`. Chercher au plus large évite d'avoir à
        expliquer pourquoi deux éléments homonymes coexistent parfois.

        Les enfants pointant le parent par NOM, on les rebranche
        (`retarget_parent`) AVANT de figer le nouveau nom. Le domaine Lua suit
        le type — un conteneur n'en a pas, rien à réécrire. Retourne le nom
        RÉELLEMENT appliqué (peut différer si collision)."""
        from core.models.ui_region import (
            KIND_TEXT, KIND_IMAGE, unique_element_name)
        new_name = new_name.strip()
        if not new_name or new_name == element.name:
            return element.name
        taken = set(self.ui_element_names()) - {element.name}
        if new_name in taken:
            new_name = unique_element_name(taken, new_name)
        kind = getattr(element, "kind", KIND_TEXT)
        domain = {KIND_TEXT: DOMAIN_REGION, KIND_IMAGE: DOMAIN_IMAGE}.get(kind)
        label = {KIND_TEXT: "Text", KIND_IMAGE: "Image"}.get(kind, "UI element")
        old_name = element.name
        with self._renaming():
            layout.retarget_parent(old_name, new_name)
            element.name = new_name
            refs = self.rename_lua_refs(domain, old_name, new_name) if domain else {}
            self.ui_layouts.save_all()
        self._notify_renamed(label, old_name, new_name, refs)
        return new_name

    def rename_sound(self, asset, new_name: str):
        """Sfx ou Music — même chemin, seul le domaine Lua diffère."""
        new_name = new_name.strip()
        if not new_name or new_name == asset.name:
            return
        old_name = asset.name
        is_music = isinstance(asset, Music)
        with self._renaming():
            (self.music if is_music else self.sfx).rename(asset, new_name)
            refs = self.rename_lua_refs(DOMAIN_MUSIC if is_music else DOMAIN_SFX,
                                        old_name, new_name)
        self._notify_renamed("Music" if is_music else "SFX",
                             old_name, new_name, refs)

    def palette_usages(self, name: str) -> list[PaletteUsage]:
        """Tout ce qui utilise la banque `name` — alimente la carte « USAGE »
        du Palette Editor.

        MÊMES référents que `rename_palette` : les deux doivent connaître
        exactement la même liste, sinon on répare un lien qu'on n'affiche pas
        (ou l'inverse).
          - sprites / fonds : override de sous-palette (`palette_overrides`) ;
          - scènes          : sélection active OBJ/BG (l'index EST la banque
            hardware, d'où l'affichage du slot) ;
          - prefabs         : `pal_bank` résolu via la scène d'ancrage (la 1re
            scène), exactement comme au build (cf. codegen/palette_alloc.py).
        Les Actors n'ont pas de ligne propre : un actor ne peut viser qu'un slot
        DÉJÀ dans la sélection active de sa scène — la ligne de la scène couvre
        le lien."""
        usages: list[PaletteUsage] = []
        if not name:
            return usages

        for assets, kind in ((self.sprites, "sprite"), (self.backgrounds, "background")):
            for asset in assets:
                overrides = getattr(asset, "palette_overrides", None) or {}
                slots = sorted(i for i, n in overrides.items() if n == name)
                if slots:
                    usages.append(PaletteUsage(
                        kind, asset.name,
                        "sous-palette " + ", ".join(str(i) for i in slots)))

        for scene in self.scenes:
            slots = []
            for pool, attr in (("OBJ", "active_obj_palettes"), ("BG", "active_bg_palettes")):
                for i, n in enumerate(getattr(scene, attr, None) or []):
                    if n == name:
                        slots.append(f"{pool} {i}")
            if slots:
                usages.append(PaletteUsage("scene", scene.name, "banque " + ", ".join(slots)))

        anchor = self.scenes[0] if len(self.scenes) else None
        anchor_active = list(getattr(anchor, "active_obj_palettes", None) or []) if anchor else []
        for prefab in self.prefabs:
            pb = getattr(prefab, "pal_bank", OWN_PAL_BANK)
            if pb != OWN_PAL_BANK and 0 <= pb < len(anchor_active) and anchor_active[pb] == name:
                usages.append(PaletteUsage("prefab", prefab.name,
                                           f"banque OBJ {pb} via « {anchor.name} »"))
        return usages

    def rename_palette(self, bank: PaletteBank, new_name: str):
        """Renomme une PaletteBank du catalogue et répare TOUT ce qui la cite par
        nom :
          - la sélection active des scènes (`active_obj_palettes` /
            `active_bg_palettes`) — remplacement EN PLACE : l'index dans la liste
            est la banque hardware, il ne doit jamais bouger ;
          - les overrides de sous-palette des sprites et des fonds
            (`palette_overrides` = {idx dérivé -> nom de banque}).
        Sans cette réparation, `palettes.rename()` seul laisse les scènes pointer
        un nom mort : le slot devient vide au build (garde-fou du validateur) et
        l'asset s'affiche avec le contenu par défaut de la banque.
        Aucun domaine Lua : une palette ne se cite pas depuis un script."""
        new_name = new_name.strip()
        if not new_name or new_name == bank.name:
            return
        old_name = bank.name
        with self._renaming():
            self.palettes.rename(bank, new_name)
            for scene in self.scenes:
                touched = False
                for attr in ("active_obj_palettes", "active_bg_palettes"):
                    names = getattr(scene, attr, None) or []
                    for i, n in enumerate(names):
                        if n == old_name:
                            names[i] = new_name
                            touched = True
                if touched:
                    self.save_scene(scene)
            for assets, save in ((self.sprites, self.save_sprite),
                                 (self.backgrounds, self.save_background)):
                for asset in assets:
                    overrides = getattr(asset, "palette_overrides", None) or {}
                    hits = [i for i, n in overrides.items() if n == old_name]
                    for i in hits:
                        overrides[i] = new_name
                    if hits:
                        save(asset)
        self._notify_renamed("Palette", old_name, new_name)

    def rename_font(self, font, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == font.name:
            return
        old_name = font.name
        with self._renaming():
            self.fonts.rename(font, new_name)
            refs = self.rename_lua_refs(DOMAIN_FONT, old_name, new_name)
        self._notify_renamed("Font", old_name, new_name, refs)

    # ── Références Lua ───────────────────────────────────────────────
    # Un script cite un élément du projet par son NOM, mais ce nom n'est
    # qu'une étiquette d'auteur : au build il est déjà résolu en index
    # physique (SCENE_IDX_*, SFX_*, g_<var>…). Renommer côté éditeur doit
    # donc mettre les scripts à jour tout seul — le lien survit, l'écriture
    # reste lisible. Repérage structurel via scripting/refactor.py : seuls
    # les arguments déclarés comme références bougent (jamais un commentaire
    # ni une string sans rapport).

    def rename_lua_refs(self, domain: str, old: str, new: str) -> dict:
        """Propage un renommage dans les scripts. Retourne {script: n} —
        vide si aucun script ne citait l'ancien nom."""
        from scripting.refactor import rename_in_project
        return rename_in_project(self, domain, old, new)

    # ── Renommage — plomberie commune ────────────────────────────────

    @contextmanager
    def _renaming(self):
        """Suspend le watcher pendant un renommage : le fichier de scène
        déplacé et les scripts réécrits sont NOS écritures. Sans ça le watcher
        les rapporte comme « modifié à l'extérieur », l'éditeur recharge et
        son propre message écrase celui du renommage. No-op hors GUI.

        Persiste aussi la frappe en cours du Script Editor AVANT de commencer :
        la réécriture lit les scripts sur disque, une ligne encore dans le
        buffer ne serait pas mise à jour."""
        try:
            from core.command_dispatcher import get_dispatcher
        except ImportError:
            yield
            return
        dispatcher = get_dispatcher()
        dispatcher.flush_script_edits()
        with dispatcher.suspended():
            yield

    def _notify_status(self, msg: str) -> None:
        """Message de statut simple. Silencieux hors GUI (build en ligne de
        commande, tests) — même repli que _notify_renamed."""
        try:
            from core.command_dispatcher import get_dispatcher
        except ImportError:
            return
        get_dispatcher()._emit("status_message", msg)

    def _notify_renamed(self, label: str, old: str, new: str,
                        refs: Optional[dict] = None, n_texts: int = 0) -> None:
        """Message de statut + rafraîchissement des vues qui affichent le nom.
        Émis pour TOUT renommage, qu'il ait touché des scripts ou non — sinon
        l'utilisateur n'a aucun retour quand rien ne référençait l'élément.
        Silencieux hors GUI (build en ligne de commande, tests)."""
        try:
            from core.command_dispatcher import get_dispatcher
        except ImportError:
            return
        msg = f"{label} renamed: “{old}” → “{new}”"
        if refs:
            n_refs  = sum(refs.values())
            files   = ", ".join(sorted(p.name for p in refs))
            msg += (f" — {n_refs} reference(s) updated in "
                    f"{len(refs)} script(s): {files}")
        if n_texts:
            msg += f" — {n_texts} text(s) updated"
        dispatcher = get_dispatcher()
        dispatcher._emit("project_tree_changed")
        if refs:
            dispatcher.notify_scripts_changed()
        # En dernier : les rafraîchissements ci-dessus peuvent poster leur
        # propre message de statut, celui du renommage doit rester visible.
        dispatcher._emit("status_message", msg)

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
        old_name = entry.name
        with self._renaming():
            refs = self.rename_lua_refs(
                DOMAIN_CONST if kind == "const" else DOMAIN_GLOBAL, old_name, new_name)
            n_texts = self.rename_var_in_texts(old_name, new_name)
            entry.name = new_name
            self.save_variables()
        self._notify_renamed("Constant" if kind == "const" else "Global",
                             old_name, new_name, refs,
                             n_texts=n_texts)
        return True

    def rename_var_in_texts(self, old_name: str, new_name: str) -> int:
        """Réécrit les `$nom` des entrées de texte. Retourne le nombre d'entrées
        touchées.

        Un `$nom` est du texte ÉCRIT À LA MAIN, comme un script : il cite la
        variable par son nom, pas par son id, donc c'est au renommage de le
        suivre. Les références stockées dans des fichiers de données, elles,
        citent l'id et n'ont rien à faire ici."""
        from core.text_markup import rename_value
        n = 0
        for t in self.texts:
            content = rename_value(t.content, old_name, new_name)
            if content != t.content:
                t.content = content
                n += 1
        if n:
            self.save_texts()
        return n

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
        self.save_texts()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.ui_layouts.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def load(self):
        # S'assurer que tous les sous-dossiers existent
        for sub in ("project/scenes", "project/prefab",
                    "project/palettes", "project/ui_layouts",
                    "assets/sprites", "assets/backgrounds",
                    "assets/scripts", "assets/scripts/actors",
                    "assets/scripts/scenes", "assets/scripts/behaviors",
                    "assets/sfx", "assets/music", "assets/fonts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        project_migrations.migrate_on_load(self)
        self.load_settings()
        self.load_variables()
        # Les ids manquent aux projets d'avant l'identité opaque, et tout ce
        # qui référence une variable par id a besoin d'eux : attribution AVANT
        # que quoi que ce soit ne tente de résoudre.
        if self.assign_variable_ids():
            self.save_variables()
        self.load_texts()
        self.palettes.load()
        project_migrations.seed_or_migrate_palettes(self)
        self.sprites.load()
        project_migrations.migrate_sprite_palettes(self)
        self.sfx.load()
        self.music.load()
        self.fonts.load()
        # Avant les scènes et prefabs, qui portent les références de champ :
        # la migration réécrit les FICHIERS, donc doit passer avant leur lecture.
        project_migrations.migrate_var_refs_to_ids(self)
        # Avant les scènes : une scène référence sa mise en page par nom.
        self.ui_layouts.load()
        project_migrations.migrate_bg_sidecar_location(self)
        self.backgrounds.load()
        project_migrations.reconcile_backgrounds(self)
        # Après les fonds ET les mises en page : la migration reporte les marges
        # d'un cadre sur son fond source, puis repointe les panneaux qui le
        # citaient. Il lui faut donc les deux déjà chargés.
        project_migrations.migrate_nine_slices_to_ui_backgrounds(self)
        self.prefabs.load()
        project_migrations.reconcile_sfx_and_music(self)
        project_migrations.reconcile_fonts(self)
        project_migrations.load_scenes_with_migration(self)
        project_migrations.migrate_scene_backgrounds(self)
        # En dernier : ces deux migrations réécrivent des SCRIPTS (et la
        # première crée des entrées de table). Leurs messages doivent rester
        # visibles, d'où le passage par _notify (silencieux hors GUI).
        #
        # display.* d'abord : elle ÉMET des appels text.draw, qui doivent sortir
        # dans le nouvel ordre — c'est le cas, elle est à jour — et n'ont donc
        # rien à faire dans le lot que réordonne la seconde. L'inverse
        # (réordonner puis migrer) laisserait la question ouverte à chaque
        # relecture de savoir lequel produit quoi.
        # Le retrait des primitives vient EN DERNIER : il lit les arguments par
        # position (`draw_num(tx, ty, valeur)`), donc il lui faut le nouvel
        # ordre déjà posé. L'inverse aurait pris une coordonnée pour une valeur.
        for fn in (project_migrations.migrate_display_calls,
                   project_migrations.migrate_text_arg_order,
                   project_migrations.migrate_removed_text_calls):
            msg = fn(self)
            if msg:
                self._notify_status(msg)

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
        proj.settings.last_scene  = "Scene_01"

        proj.save()

        # Launcher .bat — ouvre l'éditeur directement sur ce projet.
        # Figé (exe distribué) : appeler l'exe. Depuis les sources : passer
        # par l'interpréteur courant. L'ancienne version écrivait toujours
        # `python editor\main.py` depuis la racine du repo, ce qui ne peut
        # pas marcher chez quelqu'un qui n'a que l'exe.
        bat_path = root / f"{name}.bat"
        if IS_FROZEN:
            cmd = f"\"{Path(sys.executable)}\" --project \"{root}\""
        else:
            editor_root = Path(__file__).resolve().parents[2]
            cmd = (f"cd /d \"{editor_root}\"\r\n"
                   f"\"{Path(sys.executable)}\" editor\\main.py --project \"{root}\"")
        bat_path.write_text(
            f"@echo off\r\n{cmd}\r\n",
            encoding="utf-8"
        )

        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        """Ouvre un projet existant."""
        proj = cls(root)
        proj.load()
        return proj
