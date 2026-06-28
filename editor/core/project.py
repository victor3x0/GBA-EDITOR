"""
GBA Editor — gestion de projet

  - project.json       : settings globaux (nom, scène de démarrage)
  - project/scenes/    : une scène par fichier JSON
                         Chaque scène contient ses acteurs en inline (pas de
                         fichier séparé) : un Actor = un objet dans la liste
                         `actors` du JSON de scène.
  - project/prefab/    : Prefab (modèle/template) par fichier JSON.
                         JAMAIS compilé. Permet d'instancier rapidement un
                         Actor dans une scène (copie ponctuelle des Components,
                         aucun lien vivant ensuite).
  - project/sprites/   : SpriteAsset (spritesheet + anims) par fichier JSON
  - project/tilesets/  : Tileset (PNG de BG brut, partageable)
  - project/backgrounds/: Background (4 bg layers + scroll)
  - project/scripts/   : scripts C
  - assets/            : PNGs, sons… espace libre utilisateur
  - build/             : 100 % jetable
"""

import json
import shutil
import copy
import dataclasses
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Optional, Generic, TypeVar, Type, Iterator


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})

def safe_filename(name: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique (tmp → rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)   # atomique sur NTFS/ext4
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ──────────────────────────────────────────────────────────────────
#  Resource — base commune à tous les objets moteur
# ──────────────────────────────────────────────────────────────────

@dataclass
class Resource:
    """
    Base pour tout objet identifié par un nom et stocké en JSON.
    to_dict/from_dict génériques via dataclasses ; les types avec des
    champs imbriqués non-dataclass-natifs (listes d'autres dataclasses)
    peuvent surcharger ces deux méthodes.
    """
    name: str = "resource"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})


T = TypeVar("T", bound=Resource)


# Mime types pour le drag&drop interne à l'éditeur (utilisés par window.py
# et scene_editor.py — définis ici pour éviter un import circulaire entre eux).
MIME_PREFAB_TEMPLATE = "application/x-gba-prefab-template"  # drag Prefab → instancier + placer dans scène
MIME_SCRIPT          = "application/x-gba-script"


# ──────────────────────────────────────────────────────────────────
#  ResourceManager — collection générique de Resource sur disque
# ──────────────────────────────────────────────────────────────────

class ResourceManager(Generic[T]):
    """
    Gère une collection de Resource d'un type donné, persistée dans
    `directory/<name>.json`. Se comporte comme une liste (itération,
    len, indexation, append) pour rester un drop-in replacement des
    anciennes `list[Actor]` / `list[Background]` etc.
    """

    def __init__(self, directory: Path, cls: Type[T]):
        self.dir = directory
        self.cls = cls
        self.items: list[T] = []

    # -- accès liste --
    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx) -> T:
        return self.items[idx]

    def append(self, item: T) -> T:
        self.items.append(item)
        return item

    def remove(self, item: T):
        if item in self.items:
            self.items.remove(item)

    def __contains__(self, item) -> bool:
        return item in self.items

    # -- lookup --
    def get(self, name: str) -> Optional[T]:
        return next((i for i in self.items if i.name == name), None)

    # -- I/O --
    def _path(self, name: str) -> Path:
        return self.dir / f"{safe_filename(name)}.json"

    def save(self, item: T):
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path(item.name), json.dumps(item.to_dict(), indent=2, ensure_ascii=False))

    def save_all(self):
        for item in self.items:
            self.save(item)

    def load(self):
        self.items = []
        if not self.dir.exists():
            return
        for f in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                self.items.append(self.cls.from_dict(d))
            except Exception as e:
                print(f"[project] erreur lecture {self.cls.__name__} {f.name}: {e}")

    def load_one(self, name: str) -> Optional[T]:
        """Recharge un seul item depuis le disque et met à jour la liste en place."""
        path = self._path(name)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            new_item = self.cls.from_dict(d)
            for i, item in enumerate(self.items):
                if item.name == name:
                    self.items[i] = new_item
                    return new_item
            self.items.append(new_item)
            return new_item
        except Exception as e:
            print(f"[project] erreur reload {self.cls.__name__} {name}: {e}")
            return None

    def delete(self, item: T):
        path = self._path(item.name)
        if path.exists():
            path.unlink()
        self.remove(item)

    def rename(self, item: T, new_name: str):
        old_path = self._path(item.name)
        if old_path.exists():
            old_path.unlink()
        item.name = new_name
        self.save(item)


# ──────────────────────────────────────────────────────────────────
#  Settings globaux du projet
# ──────────────────────────────────────────────────────────────────

@dataclass
class ProjectSettings:
    name: str = "mon_jeu"
    start_scene: str = ""
    author: str = ""
    version: str = "0.1"


# ──────────────────────────────────────────────────────────────────
#  Tileset — PNG de BG brut, partageable entre plusieurs Background
# ──────────────────────────────────────────────────────────────────

@dataclass
class Tileset(Resource):
    """
    Référence à un PNG de tileset dans assets/.
    Stocké dans project/tilesets/{name}.json
    """
    name: str = "tileset"
    asset: Optional[str] = None   # chemin relatif depuis project root


# ──────────────────────────────────────────────────────────────────
#  Background — config d'un BG layer (utilise un Tileset)
# ──────────────────────────────────────────────────────────────────

@dataclass
class Background(Resource):
    """
    Config d'un BG : référence un Tileset + son scroll_speed.
    Stocké dans project/backgrounds/{name}.json
    """
    name: str = "background"
    tileset_name: Optional[str] = None
    scroll_speed: float = 1.0


# ──────────────────────────────────────────────────────────────────
#  SpriteAsset — spritesheet + animations, réutilisable par les Actors
# ──────────────────────────────────────────────────────────────────

@dataclass
class AnimFrame:
    col: int = 0
    row: int = 0


@dataclass
class AnimState:
    name: str = "Idle"
    frames: list[AnimFrame] = field(default_factory=lambda: [AnimFrame(0, 0)])
    speed: int = 8        # ticks GBA (60fps) entre deux frames
    loop: bool = True


@dataclass
class CollisionBox:
    x: int = 0
    y: int = 0
    w: int = 16
    h: int = 16


@dataclass
class SpriteAsset(Resource):
    """
    Spritesheet PNG + découpage en frames + états d'animation.
    Stocké dans project/sprites/{name}.json
    Référencé par nom depuis Actor.sprite_name.
    """
    name: str = "sprite"
    asset: Optional[str] = None
    frame_w: int = 16
    frame_h: int = 16
    states: list[AnimState] = field(default_factory=lambda: [AnimState()])
    collision: CollisionBox = field(default_factory=CollisionBox)

    @property
    def tile_w(self) -> int:
        return max(1, self.frame_w // 8)

    @property
    def tile_h(self) -> int:
        return max(1, self.frame_h // 8)

    @property
    def tiles_per_frame(self) -> int:
        return self.tile_w * self.tile_h

    @property
    def oam_shape(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if fw == fh: return 0
        return 1 if fw > fh else 2

    @property
    def oam_size(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if self.oam_shape == 0:
            return {8: 0, 16: 1, 32: 2, 64: 3}.get(fw, 1)
        if self.oam_shape == 1:
            return {(16, 8): 0, (32, 8): 1, (32, 16): 2, (64, 32): 3}.get((fw, fh), 0)
        return {(8, 16): 0, (8, 32): 1, (16, 32): 2, (32, 64): 3}.get((fw, fh), 0)

    @property
    def oam_dims(self) -> tuple[int, int]:
        """Retourne (oam_w, oam_h) : taille OAM valide qui contient ce sprite."""
        sh, sz = self.oam_shape, self.oam_size
        if sh == 0:
            s = [8, 16, 32, 64][sz]
            return (s, s)
        if sh == 1:
            return [(16, 8), (32, 8), (32, 16), (64, 32)][sz]
        return [(8, 16), (8, 32), (16, 32), (32, 64)][sz]

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "asset":   self.asset,
            "frame_w": self.frame_w,
            "frame_h": self.frame_h,
            "states": [
                {
                    "name":   s.name,
                    "frames": [{"col": f.col, "row": f.row} for f in s.frames],
                    "speed":  s.speed,
                    "loop":   s.loop,
                }
                for s in self.states
            ],
            "collision": {
                "x": self.collision.x, "y": self.collision.y,
                "w": self.collision.w, "h": self.collision.h,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpriteAsset":
        states = [
            AnimState(
                name   = s.get("name", "Idle"),
                frames = [AnimFrame(f.get("col", 0), f.get("row", 0))
                          for f in s.get("frames", [{"col": 0, "row": 0}])],
                speed  = s.get("speed", 8),
                loop   = s.get("loop", True),
            )
            for s in d.get("states", [])
        ] or [AnimState()]
        col = d.get("collision", {})
        collision = CollisionBox(
            x=col.get("x", 0), y=col.get("y", 0),
            w=col.get("w", d.get("frame_w", 16)),
            h=col.get("h", d.get("frame_h", 16)),
        )
        return cls(
            name      = d.get("name", "sprite"),
            asset     = d.get("asset"),
            frame_w   = d.get("frame_w", 16),
            frame_h   = d.get("frame_h", 16),
            states    = states,
            collision = collision,
        )


# ──────────────────────────────────────────────────────────────────
#  Sfx — effet sonore court
#  Stocké dans project/sfx/{name}.json
#  TODO: champs à définir ensemble (format wav/source brut vs converti
#  Maxmod, volume, pitch...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Sfx(Resource):
    name: str = "sfx"
    asset: Optional[str] = None
    volume: int = 255


# ──────────────────────────────────────────────────────────────────
#  Music — piste musicale (boucle de fond)
#  Stocké dans project/music/{name}.json
#  TODO: champs à définir ensemble (module tracker .mod/.s3m via Maxmod,
#  loop point, volume...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Music(Resource):
    name: str = "music"
    asset: Optional[str] = None
    loop: bool = True
    volume: int = 255


# ──────────────────────────────────────────────────────────────────
#  Font — police bitmap pour l'affichage de texte
#  Stocké dans project/fonts/{name}.json
#  TODO: champs à définir ensemble (charset, largeur fixe/variable,
#  spritesheet glyphes...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Font(Resource):
    name: str = "font"
    asset: Optional[str] = None


# ──────────────────────────────────────────────────────────────────
#  Components — briques attachables à un Actor (système type ECS)
#  Un Actor a une liste de composants ; plusieurs instances du même
#  type sont autorisées (ex: CollisionBox "ground_check" + "sword_hitbox").
#  Chaque composant a un `id` (label libre, unique au sein de l'actor)
#  et un flag `active` pour le désactiver sans le retirer.
# ──────────────────────────────────────────────────────────────────

@dataclass
class PathComponent:
    """TODO: à définir ensemble (waypoints de patrouille, courbes...)."""
    id: str = "path"
    active: bool = True
    points: list = field(default_factory=list)


@dataclass
class CollisionBoxComponent:
    """
    Boîte de collision AABB attachée à un Actor.

    solid=True  → résolution physique (repousse les autres actors solides)
    solid=False → trigger pur : détecte les overlaps sans bloquer

    Callbacks Lua appelés par le runtime C :
        onCollisionEnter(other_id)  — actor solide entre en contact
        onCollisionExit(other_id)   — contact rompu
        onTriggerEnter(other_id)    — actor entre dans la zone trigger
        onTriggerExit(other_id)     — actor quitte la zone trigger

    other_id = index de l'actor dans actors[] (table Lua de la scène).

    tag : label libre pour que le script distingue plusieurs colliders
          sur un même actor (ex: "body", "sword_hitbox", "ground_check").
    """
    id: str = "collision"
    active: bool = True
    solid: bool = True      # True = physique, False = trigger
    tag: str = "body"       # ex: "body", "ground_check", "hitbox", "hurtbox"
    x: int = 0              # offset relatif au pivot du sprite (pixels)
    y: int = 0
    w: int = 16
    h: int = 16
    # Callbacks Lua à déclencher (chaîne vide = pas de callback)
    on_collision_enter: str = "onCollisionEnter"
    on_collision_exit:  str = "onCollisionExit"
    on_trigger_enter:   str = "onTriggerEnter"
    on_trigger_exit:    str = "onTriggerExit"


@dataclass
class SpriteComponent:
    id: str = "sprite"
    active: bool = True
    sprite_name: Optional[str] = None   # référence SpriteAsset.name
    initial_state: str = "Idle"         # nom de l'AnimState joué au démarrage


@dataclass
class SoundFxComponent:
    """TODO: affiner le déclenchement (on_spawn, on_hit, manuel via script...)."""
    id: str = "sound_fx"
    active: bool = True
    sfx_name: Optional[str] = None      # référence Sfx.name
    trigger: str = "manual"


@dataclass
class ScriptComponent:
    id: str = "script"
    active: bool = True
    script: Optional[str] = None        # chemin relatif vers le .lua
    exports_values: dict = field(default_factory=dict)  # valeurs overrides par instance


# Registre type-name -> classe, utilisé pour la (dé)sérialisation
# polymorphe et pour piloter le menu "+ Component" de l'UI.
COMPONENT_REGISTRY: dict = {
    "path":          PathComponent,
    "collision_box": CollisionBoxComponent,
    "sprite":        SpriteComponent,
    "sound_fx":      SoundFxComponent,
    "script":        ScriptComponent,
}


def component_type_name(comp) -> str:
    """Nom de type (clé COMPONENT_REGISTRY) d'une instance de composant."""
    for type_name, klass in COMPONENT_REGISTRY.items():
        if isinstance(comp, klass):
            return type_name
    raise ValueError(f"Composant de type inconnu : {comp!r}")



def _components_to_list(components: list) -> list[dict]:
    """Sérialise une liste de Component polymorphes (utilisé par Actor ET Prefab)."""
    return [
        {"component_type": component_type_name(c), **dataclasses.asdict(c)}
        for c in components
    ]


def _components_from_list(data: list) -> list:
    """Inverse de _components_to_list."""
    components = []
    for cd in data:
        cd = dict(cd)
        type_name = cd.pop("component_type", None)
        klass = COMPONENT_REGISTRY.get(type_name)
        if not klass:
            continue
        valid = {f.name for f in fields(klass)}
        components.append(klass(**{k: v for k, v in cd.items() if k in valid}))
    return components


class ComponentOwnerMixin:
    """
    Mixin pour tout objet possédant une liste `components` de type ECS
    (Actor et Prefab). Fournit la manipulation des composants ; chaque
    classe garde son propre to_dict/from_dict (chemins/dossiers différents).
    """

    def get_component(self, comp_type: str):
        """Premier composant du type donné (ou None)."""
        klass = COMPONENT_REGISTRY[comp_type]
        return next((c for c in self.components if isinstance(c, klass)), None)

    def add_component(self, comp_type: str, **kwargs):
        klass = COMPONENT_REGISTRY[comp_type]
        comp = klass(**kwargs)
        # Garantir un id unique au sein de l'actor (ex: "collision", "collision_2", ...)
        existing_ids = {c.id for c in self.components}
        if comp.id in existing_ids:
            n = 2
            base = comp.id
            while f"{base}_{n}" in existing_ids:
                n += 1
            comp.id = f"{base}_{n}"
        self.components.append(comp)
        return comp


# ──────────────────────────────────────────────────────────────────
#  Prefab — template réutilisable. Stocké dans project/prefab/{name}.json.
#  Jamais compilé ni placé directement dans une scène.
#  Instancier un Prefab = copie ponctuelle de ses Components dans un
#  nouvel Actor inline (aucun lien vivant après la création).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Prefab(Resource, ComponentOwnerMixin):
    name: str = "Prefab"
    components: list = field(default_factory=list)
    pal_bank: int = 0
    max_instances: int = 0   # 0 = non-spawnable ; N = copies simultanées max

    def to_dict(self) -> dict:
        return {
            "name":          self.name,
            "components":    _components_to_list(self.components),
            "pal_bank":      self.pal_bank,
            "max_instances": self.max_instances,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Prefab":
        return cls(
            name          = d.get("name", "Prefab"),
            components    = _components_from_list(d.get("components", [])),
            pal_bank      = d.get("pal_bank", 0),
            max_instances = d.get("max_instances", d.get("pool_size", 0)),  # compat anciens JSON
        )


# ──────────────────────────────────────────────────────────────────
#  Actor — entité inline dans une scène.
#  Stocké directement dans le JSON de la scène (pas de fichier séparé).
#  Porte ses Components (sprite, collision, script…) ET son transform
#  de placement dans la scène (x, y, flip, priority…).
#  prefab_name est purement informatif : si l'actor a été créé depuis
#  un Prefab, il indique lequel — aucun lien vivant après la création.
# ──────────────────────────────────────────────────────────────────

@dataclass
class Actor(ComponentOwnerMixin):
    name: str = "Actor"
    prefab_name: Optional[str] = None
    active: bool = True
    components: list = field(default_factory=list)
    # Transform / placement dans la scène
    x: int = 112
    y: int = 72
    flip_h: bool = False
    flip_v: bool = False
    priority: int = 0
    pal_bank: int = 0
    visible: bool = True

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "prefab_name": self.prefab_name,
            "active":      self.active,
            "components":  _components_to_list(self.components),
            "x":           self.x,
            "y":           self.y,
            "flip_h":      self.flip_h,
            "flip_v":      self.flip_v,
            "priority":    self.priority,
            "pal_bank":    self.pal_bank,
            "visible":     self.visible,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Actor":
        return cls(
            name        = d.get("name", "Actor"),
            prefab_name = d.get("prefab_name"),
            active      = d.get("active", True),
            components  = _components_from_list(d.get("components", [])),
            x           = d.get("x", 112),
            y           = d.get("y", 72),
            flip_h      = d.get("flip_h", False),
            flip_v      = d.get("flip_v", False),
            priority    = d.get("priority", 0),
            pal_bank    = d.get("pal_bank", 0),
            visible     = d.get("visible", True),
        )


# ──────────────────────────────────────────────────────────────────
#  SceneLayer — un BG layer dans une scène
# ──────────────────────────────────────────────────────────────────
#  Collision map — types de tiles 8×8
# ──────────────────────────────────────────────────────────────────

TILE_EMPTY      = 0   # passable
TILE_SOLID      = 1   # bloc plein
TILE_SLOPE_L    = 2   # ◥  45° sol montant  L→R
TILE_SLOPE_R    = 3   # ◤  45° sol descendant L→R
TILE_SLOPE_L_LO = 4   # ◢  ~26° sol montant, tile gauche (bas)
TILE_SLOPE_L_HI = 5   # ◥½ ~26° sol montant, tile droite (haut)
TILE_SLOPE_R_LO = 6   # ◣  ~26° sol descendant, tile droite (bas)
TILE_SLOPE_R_HI = 7   # ◤½ ~26° sol descendant, tile gauche (haut)
# Plafond — miroir vertical des sols
TILE_SLOPE_L_INV    = 8   # ◣  45° plafond montant  L→R
TILE_SLOPE_R_INV    = 9   # ◢  45° plafond descendant L→R
TILE_SLOPE_L_LO_INV = 10  # ~26° plafond montant, tile gauche
TILE_SLOPE_L_HI_INV = 11  # ~26° plafond montant, tile droite
TILE_SLOPE_R_LO_INV = 12  # ~26° plafond descendant, tile droite
TILE_SLOPE_R_HI_INV = 13  # ~26° plafond descendant, tile gauche
# Pentes raides sol (>45°, X=1 Y=2) — paires HI (petit triangle) + LO (grand quadrilatère)
TILE_SLOPE_R_STEEP_HI     = 14  # ~63° sol descendant L→R, tile haut (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO     = 15  # ~63° sol descendant L→R, tile bas  (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI     = 16  # ~63° sol montant  L→R, tile haut (petit triangle droit)
TILE_SLOPE_L_STEEP_LO     = 17  # ~63° sol montant  L→R, tile bas  (grand quadrilatère droit)
# Pentes raides plafond (miroir vertical)
TILE_SLOPE_R_STEEP_HI_INV = 18  # ~63° plafond descendant L→R, tile bas  (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO_INV = 19  # ~63° plafond descendant L→R, tile haut (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI_INV = 20  # ~63° plafond montant  L→R, tile bas  (petit triangle droit)
TILE_SLOPE_L_STEEP_LO_INV = 21  # ~63° plafond montant  L→R, tile haut (grand quadrilatère droit)

COLLISION_TILE_SIZE = 8   # pixels par tile de collision

def make_collision_map(width_px: int, height_px: int) -> list[list[int]]:
    """Crée une grille vide (TILE_EMPTY) aux dimensions de la scène en pixels."""
    cols = max(1, (width_px  + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    rows = max(1, (height_px + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    return [[TILE_EMPTY] * cols for _ in range(rows)]


# ──────────────────────────────────────────────────────────────────

@dataclass
class SceneLayer:
    bg: int = 0
    background_name: str = ""
    scroll_speed: float = 1.0


# ──────────────────────────────────────────────────────────────────
#  Scene — une scène complète
# ──────────────────────────────────────────────────────────────────

@dataclass
class Scene(Resource):
    name: str = "Scene"
    bg_layers: list = field(default_factory=lambda: [
        SceneLayer(bg=0, background_name="", scroll_speed=4.0),
        SceneLayer(bg=1, background_name="", scroll_speed=2.0),
        SceneLayer(bg=2, background_name="", scroll_speed=1.0),
        SceneLayer(bg=3, background_name="", scroll_speed=0.5),
    ])
    actors: list = field(default_factory=list)  # list[Actor], inline dans le JSON
    cam_x: int = 0
    cam_y: int = 0
    cam_follow: str = ""   # nom de l'Actor à suivre ("" = caméra libre)
    scroll_h: bool = True  # défilement horizontal activé
    scroll_v: bool = False # défilement vertical activé
    script: str = ""       # chemin relatif vers le script Lua de la scène ("" = aucun)
    text_bg: int = 1       # BG hardware (0-3) utilisé pour le calque texte TTE
    collision_layer: int = 0  # index BG (0-3) portant la carte de collisions
    # Grille de collision en tiles 8×8 — list[row][col] de TILE_* constants
    collision_map: list = field(default_factory=list)

    def active_layers(self) -> list:
        return [L for L in self.bg_layers if L.background_name]

    def ensure_collision_map(self, width_px: int = 240, height_px: int = 160):
        """Initialise ou redimensionne la collision_map si vide."""
        if not self.collision_map:
            self.collision_map = make_collision_map(width_px, height_px)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "bg_layers": [
                {"bg": L.bg, "background_name": L.background_name, "scroll_speed": L.scroll_speed}
                for L in self.bg_layers
            ],
            "actors": [a.to_dict() for a in self.actors],
            "cam_x": self.cam_x,
            "cam_y": self.cam_y,
            "cam_follow": self.cam_follow,
            "scroll_h": self.scroll_h,
            "scroll_v": self.scroll_v,
            "script": self.script,
            "text_bg": self.text_bg,
            "collision_layer": self.collision_layer,
            "collision_map": self.collision_map,
        }

    @classmethod
    def from_dict(cls, d: dict, legacy_actors: dict = None) -> "Scene":
        """
        legacy_actors : dict nom→Actor chargé depuis project/actors/ (anciens projets).
        Si présent, les entrées `instances[actor_name]` sont converties en Actor inline.
        """
        layers = [
            SceneLayer(
                bg              = L.get("bg", i),
                background_name = L.get("background_name", ""),
                scroll_speed    = L.get("scroll_speed", 1.0),
            )
            for i, L in enumerate(d.get("bg_layers", [{}, {}, {}, {}]))
        ]
        while len(layers) < 4:
            layers.append(SceneLayer(bg=len(layers)))

        # Nouveau format : acteurs inline
        if "actors" in d:
            actors = [Actor.from_dict(a) for a in d["actors"]]
        else:
            # Ancien format : instances avec actor_name → migration automatique
            actors = []
            for sa in d.get("instances", []):
                name = sa.get("actor_name", "") or sa.get("name", "Actor")
                base = (legacy_actors or {}).get(name)
                actors.append(Actor(
                    name        = name,
                    prefab_name = base.prefab_name if base else None,
                    active      = base.active if base else True,
                    components  = copy.deepcopy(base.components) if base else [],
                    x           = sa.get("x", 112),
                    y           = sa.get("y", 72),
                    flip_h      = sa.get("flip_h", False),
                    flip_v      = sa.get("flip_v", False),
                    priority    = sa.get("priority", 0),
                    pal_bank    = sa.get("pal_bank", 0),
                    visible     = sa.get("visible", True),
                ))

        scene = cls(
            name=d.get("name", "Scene"),
            bg_layers=layers,
            actors=actors,
            cam_x=d.get("cam_x", 0),
            cam_y=d.get("cam_y", 0),
            cam_follow=d.get("cam_follow", ""),
            scroll_h=d.get("scroll_h", True),
            scroll_v=d.get("scroll_v", False),
            script=d.get("script", ""),
            text_bg=d.get("text_bg", 1),
            collision_layer=d.get("collision_layer", 0),
            collision_map=d.get("collision_map", []),
        )
        scene.ensure_collision_map()
        return scene


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

        self.tilesets:    ResourceManager[Tileset]     = ResourceManager(self.tilesets_dir, Tileset)
        self.backgrounds: ResourceManager[Background]  = ResourceManager(self.backgrounds_dir, Background)
        self.sprites:     ResourceManager[SpriteAsset] = ResourceManager(self.sprites_dir, SpriteAsset)
        self.prefabs:     ResourceManager[Prefab]      = ResourceManager(self.prefab_dir, Prefab)
        self.scenes:      ResourceManager[Scene]       = ResourceManager(self.scenes_dir, Scene)
        self.sfx:         ResourceManager[Sfx]         = ResourceManager(self.sfx_dir, Sfx)
        self.music:       ResourceManager[Music]       = ResourceManager(self.music_dir, Music)
        self.fonts:       ResourceManager[Font]        = ResourceManager(self.fonts_dir, Font)

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
    def sprites_dir(self) -> Path:
        return self.project_dir / "sprites"

    @property
    def tilesets_dir(self) -> Path:
        return self.project_dir / "tilesets"

    @property
    def backgrounds_dir(self) -> Path:
        return self.project_dir / "backgrounds"

    @property
    def sfx_dir(self) -> Path:
        return self.project_dir / "sfx"

    @property
    def music_dir(self) -> Path:
        return self.project_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.project_dir / "fonts"

    @property
    def scripts_dir(self) -> Path:
        return self.project_dir / "scripts"

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

    # ── Helpers de lookup ────────────────────────────────────────

    def get_background(self, name: str) -> Optional[Background]:
        return self.backgrounds.get(name)

    def get_tileset(self, name: str) -> Optional[Tileset]:
        return self.tilesets.get(name)

    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        return self.sprites.get(name)

    def get_prefab(self, name: str) -> Optional[Prefab]:
        return self.prefabs.get(name)

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

    # ── I/O scenes (restaure aussi la scène active) ────────────────

    def _load_scenes_with_migration(self):
        """
        Charge les scènes en gérant la migration automatique de l'ancien
        format (instances[actor_name] → Actor inline).  Si le dossier
        project/actors/ existe encore, ses fichiers servent de référence
        pour copier les Components lors de la migration, puis sont ignorés.
        """
        legacy_actors: dict[str, "Actor"] = {}
        old_actors_dir = self.project_dir / "actors"
        if old_actors_dir.exists():
            for f in sorted(old_actors_dir.glob("*.json")):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    # Reconstituer un Actor partiel (components seulement) pour la migration
                    a = Actor(
                        name        = d.get("name", f.stem),
                        prefab_name = d.get("prefab_name"),
                        active      = d.get("active", True),
                        components  = _components_from_list(d.get("components", [])),
                    )
                    legacy_actors[a.name] = a
                except Exception:
                    pass

        self.scenes.items = []
        scenes_dir = self.scenes_dir
        if not scenes_dir.exists():
            return
        for f in sorted(scenes_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                scene = Scene.from_dict(d, legacy_actors=legacy_actors if legacy_actors else None)
                self.scenes.items.append(scene)
                # Si migration détectée (format instances → actors), re-sauvegarder
                if "instances" in d and "actors" not in d:
                    self.save_scene(scene)
            except Exception as e:
                print(f"[project] erreur lecture Scene {f.name}: {e}")

        if self.settings.start_scene:
            for i, s in enumerate(self.scenes):
                if s.name == self.settings.start_scene:
                    self._active_scene_idx = i
                    break

    # ── Renommage (supprime l'ancien fichier + répare les références) ──
    # ResourceManager.rename() seul ne suffit pas : il faut aussi mettre à
    # jour tout ce qui référence l'ancien nom ailleurs dans le projet.

    def rename_background(self, bg: Background, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == bg.name:
            return
        old_name = bg.name
        self.backgrounds.rename(bg, new_name)
        for scene in self.scenes:
            changed = False
            for layer in scene.bg_layers:
                if layer.background_name == old_name:
                    layer.background_name = new_name
                    changed = True
            if changed:
                self.save_scene(scene)

    def rename_scene(self, scene: Scene, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == scene.name:
            return
        old_name = scene.name
        self.scenes.rename(scene, new_name)
        if self.settings.start_scene == old_name:
            self.settings.start_scene = new_name
            self.save_settings()

    # ── Raccourcis de sauvegarde par objet (delegue au ResourceManager) ──

    def save_scene(self, scene: Scene):          self.scenes.save(scene)
    def save_prefab(self, prefab: Prefab):       self.prefabs.save(prefab)
    def save_sprite(self, sprite: SpriteAsset): self.sprites.save(sprite)
    def save_tileset(self, tileset: Tileset):  self.tilesets.save(tileset)
    def save_background(self, bg: Background): self.backgrounds.save(bg)
    def save_sfx(self, sfx: Sfx):              self.sfx.save(sfx)
    def save_music(self, music: Music):        self.music.save(music)

    # ── Sauvegarde / chargement global ────────────────────────────

    def save(self):
        self.save_settings()
        self.tilesets.save_all()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def load(self):
        # S'assurer que tous les sous-dossiers existent (rétrocompat projets anciens)
        for sub in ("project/scenes", "project/prefab", "project/sprites",
                    "project/tilesets", "project/backgrounds",
                    "project/scripts", "project/scripts/actors", "project/scripts/behaviors",
                    "project/sfx", "project/music", "project/fonts",
                    "assets/backgrounds", "assets/sprites"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        self.load_settings()
        self.tilesets.load()
        self.sprites.load()
        self.sfx.load()
        self.music.load()
        self.fonts.load()
        self.backgrounds.load()
        self.prefabs.load()
        self._load_scenes_with_migration()

    # ── Création / ouverture ──────────────────────────────────────

    @classmethod
    def create(cls, root: Path, name: str) -> "Project":
        """Crée un nouveau projet vide avec la structure de dossiers."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "assets/backgrounds",
            "assets/sprites",
            "assets/music",
            "assets/sfx",
            "assets/fonts",
            "project/scenes",
            "project/prefab",
            "project/sprites",
            "project/tilesets",
            "project/backgrounds",
            "project/sfx",
            "project/music",
            "project/fonts",
            "project/scripts",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)

        proj = cls(root)
        proj.settings.name = name

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
