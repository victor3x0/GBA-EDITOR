"""Actor / Prefab / Scene — entités placées dans une scène + la scène elle-même."""

import copy
from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.palette import OWN_PAL_BANK
from core.models.components import ComponentOwnerMixin, _components_to_list, _components_from_list
from core.models.background import BackgroundLayer, _decode_tile_palette_overrides

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


# Stub rétrocompat
@dataclass
class SceneLayer:
    bg: int = 0
    background_name: str = ""
    scroll_speed: float = 1.0


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
    pal_bank: int = OWN_PAL_BANK   # -1 = palette propre du sprite (défaut)
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
            pal_bank      = d.get("pal_bank", OWN_PAL_BANK),
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
    pal_bank: int = OWN_PAL_BANK   # -1 = palette propre du sprite (défaut)
    visible: bool = True
    # Direction initiale discrète (-1|0|1 × -1|0|1) : oriente le sprite affiché
    # dans l'éditeur et initialise dir_x/dir_y de l'Actor au runtime. (0,0)=omni.
    dir_x: int = 0
    dir_y: int = 0

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
            "dir_x":       self.dir_x,
            "dir_y":       self.dir_y,
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
            pal_bank    = d.get("pal_bank", OWN_PAL_BANK),
            visible     = d.get("visible", True),
            dir_x       = d.get("dir_x", 0),
            dir_y       = d.get("dir_y", 0),
        )


# ──────────────────────────────────────────────────────────────────
#  Scene — une scène complète
# ──────────────────────────────────────────────────────────────────

@dataclass
class Scene(Resource):
    name: str = "Scene"
    # Layers de fond de CETTE scène (inline dans le JSON) — chaque layer référence
    # un BackgroundAsset (sidecar de compression) par son nom d'image.
    background_layers: list = field(default_factory=list)  # list[BackgroundLayer]
    actors: list = field(default_factory=list)  # list[Actor], inline dans le JSON
    cam_x: int = 0
    cam_y: int = 0
    cam_follow: str = ""   # nom de l'Actor à suivre ("" = caméra libre)
    scroll_h: bool = True  # défilement horizontal activé
    scroll_v: bool = False # défilement vertical activé
    # Mode vidéo GBA de la scène (0-5). 0 = 4 fonds tuilés réguliers (défaut) ;
    # 1/2 = tuilé + affine ; 3/4/5 = un fond bitmap plein écran (BG2). Pilote
    # l'inspecteur (zones background/palettes). cf. ui MODE_INFO.
    render_mode: int = 0
    script: str = ""       # chemin relatif vers le script Lua de la scène ("" = aucun)
    text_bg: int = 1       # BG hardware (0-3) utilisé pour le calque texte TTE
    collision_layer: int = 0  # index BG (0-3) portant la carte de collisions
    # Grille de collision en tiles 8×8 — list[row][col] de TILE_* constants
    collision_map: list = field(default_factory=list)
    # Palettes actives de cette scène — noms référençant project.obj_palettes/
    # bg_palettes (catalogue illimité). Ordre = index de banque hardware
    # (slot 0 = 1er élément). Actor/Prefab.pal_bank indexe dans CETTE liste,
    # pas directement le catalogue projet.
    active_obj_palettes: list = field(default_factory=list)  # list[str]
    active_bg_palettes:  list = field(default_factory=list)  # list[str]
    # Override de ProjectSettings.backdrop_color pour cette scène (BGR555) ;
    # None = hérite du défaut projet.
    backdrop_color: Optional[int] = None

    def ensure_collision_map(self, width_px: int = 240, height_px: int = 160):
        """Initialise ou redimensionne la collision_map si vide."""
        if not self.collision_map:
            self.collision_map = make_collision_map(width_px, height_px)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background_layers": [
                {"background_name": L.background_name, "bg_slot": L.bg_slot,
                 "scroll_speed": L.scroll_speed, "pal_bank": L.pal_bank,
                 **({"tile_palette_overrides": {f"{c},{r}": s
                                       for (c, r), s in L.tile_palette_overrides.items()}}
                    if L.tile_palette_overrides else {}),
                 **({} if L.visible else {"visible": False})}
                for L in self.background_layers
            ],
            "actors": [a.to_dict() for a in self.actors],
            "cam_x": self.cam_x,
            "cam_y": self.cam_y,
            "cam_follow": self.cam_follow,
            "render_mode": self.render_mode,
            "scroll_h": self.scroll_h,
            "scroll_v": self.scroll_v,
            "script": self.script,
            "text_bg": self.text_bg,
            "collision_layer": self.collision_layer,
            "collision_map": self.collision_map,
            "active_obj_palettes": self.active_obj_palettes,
            "active_bg_palettes": self.active_bg_palettes,
            "backdrop_color": self.backdrop_color,
        }

    @classmethod
    def from_dict(cls, d: dict, legacy_actors: dict = None) -> "Scene":
        """
        legacy_actors : dict nom→Actor chargé depuis project/actors/ (anciens projets).
        Si présent, les entrées `instances[actor_name]` sont converties en Actor inline.
        """
        # Layers de la scène (nouveau format). L'ancien `background_asset` (nom
        # d'un BackgroundAsset multi-layer) est migré au niveau projet
        # (Project._migrate_scene_backgrounds) car il faut lire cet asset.
        bg_layers = [
            BackgroundLayer(
                background_name = L.get("background_name", L.get("image", "")),   # rétro-compat: ancienne clé "image"
                bg_slot      = L.get("bg_slot", i),
                scroll_speed = L.get("scroll_speed", 1.0),
                pal_bank     = L.get("pal_bank", OWN_PAL_BANK),
                # Migration : ancienne clé "tile_palettes" (avant l'harmonisation
                # de nomenclature) relue pour préserver les scènes déjà peintes.
                tile_palette_overrides= _decode_tile_palette_overrides(
                    L.get("tile_palette_overrides") or L.get("tile_palettes")),
                visible      = L.get("visible", True),
            )
            for i, L in enumerate(d.get("background_layers", []))
        ]

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
                    pal_bank    = sa.get("pal_bank", OWN_PAL_BANK),
                    visible     = sa.get("visible", True),
                ))

        scene = cls(
            name=d.get("name", "Scene"),
            background_layers=bg_layers,
            actors=actors,
            cam_x=d.get("cam_x", 0),
            cam_y=d.get("cam_y", 0),
            cam_follow=d.get("cam_follow", ""),
            render_mode=int(d.get("render_mode", 0)),
            scroll_h=d.get("scroll_h", True),
            scroll_v=d.get("scroll_v", False),
            script=d.get("script", ""),
            text_bg=d.get("text_bg", 1),
            collision_layer=d.get("collision_layer", 0),
            collision_map=d.get("collision_map", []),
            active_obj_palettes=d.get("active_obj_palettes", []),
            active_bg_palettes=d.get("active_bg_palettes", []),
            backdrop_color=d.get("backdrop_color"),
        )
        # Ancien nom de BackgroundAsset (migré au load si background_layers vide).
        scene._legacy_bg_asset = d.get("background_asset", "")
        if not scene._legacy_bg_asset and "bg_layers" in d:   # très ancien format
            for L in d["bg_layers"]:
                if L.get("background_name"):
                    scene._legacy_bg_asset = L["background_name"]
                    break
        scene.ensure_collision_map()
        return scene
