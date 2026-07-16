"""Components — briques attachables à un Actor (système type ECS).
Un Actor a une liste de composants ; plusieurs instances du même
type sont autorisées (ex: CollisionBox "ground_check" + "sword_hitbox").
Chaque composant a un `id` (label libre, unique au sein de l'actor)
et un flag `active` pour le désactiver sans le retirer."""

import dataclasses
from dataclasses import dataclass, field, fields
from typing import Optional


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
    auto_dir: bool = True               # calcule dir depuis vélocité automatiquement
    scale_x: float = 1.0               # affine OAM (1.0 = normal)
    scale_y: float = 1.0
    rotation: int = 0                  # degrés 0–359 (OAM affine)

    def __post_init__(self):
        self.scale_x  = float(self.scale_x)
        self.scale_y  = float(self.scale_y)
        self.rotation = int(self.rotation)


@dataclass
class SoundFxComponent:
    """
    Associe un Sfx à un actor.
    trigger="manual"   : ne joue rien automatiquement — appeler self:play_sfx() depuis un script.
    trigger="on_spawn" : joue automatiquement au démarrage de l'actor (on_start), sans script.
    """
    id: str = "sound_fx"
    active: bool = True
    sfx_name: Optional[str] = None      # référence Sfx.name
    trigger: str = "manual"             # "manual" | "on_spawn"


@dataclass
class ScriptComponent:
    id: str = "script"
    active: bool = True
    script: Optional[str] = None        # chemin relatif vers le .lua
    exports_values: dict = field(default_factory=dict)  # valeurs overrides par instance


# Registre type-name -> classe, utilisé pour la (dé)sérialisation
# polymorphe et pour piloter le menu "+ Component" de l'UI.
COMPONENT_REGISTRY: dict = {
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
