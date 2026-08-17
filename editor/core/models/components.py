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

    `solid` décide d'UNE chose et d'une seule : cette box est-elle arrêtée par la
    CARTE DE COLLISION de la scène (murs, pentes, plafonds) ?

        solid=True  → l'acteur est repoussé par les tuiles, se pose sur les
                      pentes, se cogne aux plafonds (cf. ROADMAP v0.6.3)
        solid=False → la carte l'ignore : à un script de gérer les tuiles s'il
                      le veut, via `tile.get`

    Les collisions acteur-contre-acteur ne le consultent PAS : les callbacks
    ci-dessous se déclenchent au recouvrement, quelle que soit la valeur. La
    docstring a longtemps prétendu que `solid` « repoussait les autres actors
    solides » — aucune ligne du runtime ne l'a jamais fait, et la v0.6.3 l'a
    découvert en cherchant qui avait droit à la résolution.

    Handlers Lua appelés par le runtime C. Ils n'appartiennent PAS à ce
    composant : ce sont des fonctions globales du script de l'actor, et le
    codegen se contente de regarder lesquelles le .lua définit.

        on_collision_enter(other, my_box, other_box)  — premier frame de contact
        on_collision_exit(other, my_box, other_box)   — premier frame sans contact
        on_collide(other, my_box, other_box)          — chaque frame de contact
        on_tile_collide(normal_x, normal_y)           — choc contre la carte

    `other` est une référence d'actor (pas un index) ; `my_box`/`other_box`
    valent une constante `BOXTAG_<TAG>` dérivée du champ `tag` ci-dessous —
    c'est ainsi qu'un script distingue quelle box a touché, y compris entre
    boxes solides et boxes trigger : il n'existe pas de handler trigger séparé.

    tag : label libre pour que le script distingue plusieurs colliders
          sur un même actor (ex: "body", "sword_hitbox", "ground_check").
    """
    id: str = "collision"
    active: bool = True
    solid: bool = True      # arrêté par la carte de collision (cf. docstring)
    tag: str = "body"       # ex: "body", "ground_check", "hitbox", "hurtbox"
    x: int = 0              # offset relatif au pivot du sprite (pixels)
    y: int = 0
    w: int = 16
    h: int = 16


@dataclass
class SpriteComponent:
    id: str = "sprite"
    active: bool = True
    sprite_name: Optional[str] = None   # référence SpriteAsset.name
    initial_state: str = "Idle"         # nom de l'AnimState joué au démarrage
    auto_dir: bool = True               # calcule dir depuis vélocité automatiquement
    # Transform affine LOCAL (cf. ARCHITECTURE.md « Le modèle affine »). Ces
    # valeurs ne valent QUE si l'Actor qui porte ce composant a `affine_transform`
    # coché (réservation du slot de matrice affine OAM) : elles se composent alors
    # par-dessus le transform MONDE de l'actor — rotation locale ajoutée à la
    # rotation de l'actor, scale local multiplié par le scale de l'actor. Sans
    # `affine_transform`, elles sont ignorées (aucun slot alloué, OAM normale).
    scale_x: float = 1.0               # affine OAM (1.0 = normal), local
    scale_y: float = 1.0
    rotation: int = 0                  # degrés 0–359 (OAM affine), local
    # Position du sprite RELATIVE à son actor, en pixels, dans le repère local de
    # l'actor : l'offset tourne/scale AVEC l'actor (hérarchie parent→enfant). Le
    # sprite n'a pas de position monde — la position monde reste Actor.x/y.
    offset_x: int = 0
    offset_y: int = 0

    def __post_init__(self):
        self.scale_x  = float(self.scale_x)
        self.scale_y  = float(self.scale_y)
        self.rotation = int(self.rotation)
        self.offset_x = int(self.offset_x)
        self.offset_y = int(self.offset_y)


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


def components_to_list(components: list) -> list[dict]:
    """Sérialise une liste de Component polymorphes (utilisé par Actor ET Prefab)."""
    return [
        {"component_type": component_type_name(c), **dataclasses.asdict(c)}
        for c in components
    ]


def components_from_list(data: list) -> list:
    """Inverse de components_to_list."""
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
