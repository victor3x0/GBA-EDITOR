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

# ── Mélange de couleurs (BLDCNT / BLDALPHA / BLDY) ────────────────
# **Le mode est GLOBAL à l'écran**, pas par layer : `BLDCNT` n'a qu'un champ
# mode (bits 6-7). Ce qui est par layer est son appartenance à l'ensemble du
# DESSUS (bits 0-5, ce qui est mélangé) ou du DESSOUS (bits 8-13, ce avec quoi,
# situé derrière selon les priorités). D'où le partage : le mode et les
# coefficients sur la Scene, le rôle sur le BackgroundLayer.
#
# Le mélange ne se produit QUE là où un pixel du dessus a effectivement un pixel
# du dessous derrière lui — c'est la cause n°1 des « alpha qui ne font rien »,
# et ce que le validateur doit dire.
BLEND_NONE     = 0   # aucun mélange — le défaut, et le comportement d'avant
BLEND_ALPHA    = 1   # dessus×EVA + dessous×EVB, saturé à 31 par canal
BLEND_BRIGHTEN = 2   # le dessus fond vers le BLANC, intensité EVY
BLEND_DARKEN   = 3   # le dessus fond vers le NOIR, intensité EVY
BLEND_MODES = (BLEND_NONE, BLEND_ALPHA, BLEND_BRIGHTEN, BLEND_DARKEN)

# Les modes 2 et 3 n'emploient QUE le dessus : désigner un dessous n'y change
# rien. L'inspecteur s'en sert pour griser le rôle « dessous » plutôt que de
# laisser composer un réglage sans effet.
BLEND_NEEDS_BOTTOM = (BLEND_ALPHA,)

BLEND_TOP    = "top"      # première cible — ce qui est mélangé
BLEND_BOTTOM = "bottom"   # seconde cible — ce avec quoi, situé DERRIÈRE
BLEND_ROLES  = ("", BLEND_TOP, BLEND_BOTTOM)

# Coefficients 0-16, bornes MATÉRIELLES (5 bits, valeurs >16 se comportent
# comme 16). 16 = « en entier », 0 = « rien ».
BLEND_EV_MAX = 16


def clamp_ev(v) -> int:
    try:
        return max(0, min(BLEND_EV_MAX, int(v)))
    except (TypeError, ValueError):
        return 0


def blend_role_of(layer) -> str:
    """Rôle d'un layer, normalisé — une valeur inconnue vaut « aucun »."""
    r = getattr(layer, "blend_role", "")
    return r if r in BLEND_ROLES else ""


# ── Effets : l'INTENTION, au-dessus des registres ─────────────────
# `BLDCNT` se règle en six bits de cible + un mode + deux ou trois
# coefficients ; c'est le matériel, et c'est ce que la scène stocke. Mais
# personne ne pense « première cible » : on pense « fondu au noir » ou « ce
# layer est translucide ». Ces trois effets sont la traduction, et ils couvrent
# ce pour quoi le blending GBA sert réellement.
#
# Rien n'est perdu : l'effet ÉCRIT les mêmes champs, et un réglage composé à la
# main (cibles partielles, EVA+EVB > 16 pour un halo) reste lisible et
# modifiable — il ressort simplement en « personnalisé ».
EFFECT_NONE        = "none"
EFFECT_FADE_BLACK  = "fade_black"    # mode 3, tout l'écran
EFFECT_FADE_WHITE  = "fade_white"    # mode 2, tout l'écran
EFFECT_TRANSLUCENT = "translucent"   # mode 1, un layer par-dessus ce qu'il y a derrière
EFFECT_CUSTOM      = "custom"        # composé à la main : on n'y touche pas

_FADE_EFFECTS = {EFFECT_FADE_BLACK: BLEND_DARKEN, EFFECT_FADE_WHITE: BLEND_BRIGHTEN}


def blend_effect_of(scene) -> str:
    """L'effet que ce réglage REPRÉSENTE, ou « personnalisé ».

    Reconnaissance et non mémorisation : l'effet n'est pas un champ stocké de
    plus (qui pourrait mentir sur les registres), il se relit des registres.
    Un réglage fait à la main reste donc éditable sans qu'un champ caché
    prétende le contraire."""
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    if mode == BLEND_NONE:
        return EFFECT_NONE
    layers = list(getattr(scene, "background_layers", []))
    tops = [L for L in layers if blend_role_of(L) == BLEND_TOP]
    bottoms = [L for L in layers if blend_role_of(L) == BLEND_BOTTOM]
    obj = getattr(scene, "blend_obj_role", "")
    bd = getattr(scene, "blend_backdrop_role", "")
    if mode in (BLEND_DARKEN, BLEND_BRIGHTEN):
        # Fondu d'écran = TOUT est première cible, rien n'est seconde.
        whole = (len(tops) == len(layers) and not bottoms
                 and obj == BLEND_TOP and bd == BLEND_TOP)
        if whole:
            return EFFECT_FADE_BLACK if mode == BLEND_DARKEN else EFFECT_FADE_WHITE
        return EFFECT_CUSTOM
    # Alpha : un ou plusieurs layers devant, tout le reste derrière, et les
    # deux coefficients complémentaires (ce que « X % opaque » veut dire).
    #
    # `tops` VIDE compte quand même comme translucidité : c'est l'état d'un
    # réglage commencé mais pas fini — on a choisi l'effet, on n'a pas encore
    # marqué le layer. Le renvoyer en « personnalisé » ferait sauter le
    # sélecteur sur autre chose entre deux clics, alors que l'avertissement dit
    # déjà quoi faire.
    rest_ok = all(blend_role_of(L) == BLEND_BOTTOM for L in layers if L not in tops)
    if (rest_ok and bd == BLEND_BOTTOM and not obj
            and int(scene.blend_eva) + int(scene.blend_evb) == BLEND_EV_MAX):
        return EFFECT_TRANSLUCENT
    return EFFECT_CUSTOM


def blend_amount_of(scene) -> int:
    """L'effet en POURCENTAGE, tel que l'inspecteur le montre.

    Fondu : 0 = rien, 100 = noir (ou blanc) plein. Translucidité : c'est
    l'opacité du layer de devant, 100 = opaque."""
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    ev = int(scene.blend_eva) if mode == BLEND_ALPHA else int(scene.blend_evy)
    return round(ev * 100 / BLEND_EV_MAX)


def apply_blend_effect(scene, effect: str, amount_pct: int) -> None:
    """Écrit les registres d'un effet. Les CIBLES sont posées d'office :

    - fondu → tout l'écran est première cible (layers, sprites, backdrop). C'est
      ce qu'on veut d'une transition, et oublier le backdrop laisserait les
      zones vides allumées pendant que le reste s'éteint — la panne classique ;
    - translucidité → les layers marqués restent devant, TOUT le reste passe
      derrière. Le matériel ne mélange qu'avec la couche immédiatement
      inférieure : marquer largement garantit qu'elle en fasse partie, quelle
      qu'elle soit (cf. la règle du « pas de saut de couche »).

    `EFFECT_CUSTOM` ne touche à rien : c'est le réglage composé à la main."""
    if effect == EFFECT_CUSTOM:
        return
    ev = max(0, min(BLEND_EV_MAX, round(int(amount_pct) * BLEND_EV_MAX / 100)))
    layers = list(getattr(scene, "background_layers", []))
    if effect == EFFECT_NONE:
        scene.blend_mode = BLEND_NONE
        for L in layers:
            L.blend_role = ""
        scene.blend_obj_role = scene.blend_backdrop_role = ""
        return
    if effect in _FADE_EFFECTS:
        scene.blend_mode = _FADE_EFFECTS[effect]
        scene.blend_evy = ev
        for L in layers:
            L.blend_role = BLEND_TOP
        scene.blend_obj_role = scene.blend_backdrop_role = BLEND_TOP
        return
    if effect == EFFECT_TRANSLUCENT:
        scene.blend_mode = BLEND_ALPHA
        scene.blend_eva = ev
        scene.blend_evb = BLEND_EV_MAX - ev
        for L in layers:
            if blend_role_of(L) != BLEND_TOP:
                L.blend_role = BLEND_BOTTOM
        scene.blend_obj_role = ""
        scene.blend_backdrop_role = BLEND_BOTTOM

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
    notes: str = ""   # note libre utilisateur (éditeur uniquement, jamais compilée)

    def to_dict(self) -> dict:
        return {
            "name":          self.name,
            "components":    _components_to_list(self.components),
            "pal_bank":      self.pal_bank,
            "max_instances": self.max_instances,
            "notes":         self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Prefab":
        return cls(
            name          = d.get("name", "Prefab"),
            components    = _components_from_list(d.get("components", [])),
            pal_bank      = d.get("pal_bank", OWN_PAL_BANK),
            max_instances = d.get("max_instances", d.get("pool_size", 0)),  # compat anciens JSON
            notes         = d.get("notes", ""),
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
    # Mode OAM (bits 10-11 d'attr0) : 0 = sprite normal, 2 = fenêtre-objet —
    # le sprite n'est plus dessiné, ses pixels opaques DÉCOUPENT la région
    # window.OBJ (forme libre, animable). Mode 1 (semi-transparent) suppose le
    # blending, pas encore câblé. Modifiable au runtime par self:set_obj_mode().
    obj_mode: int = 0
    # Ancrage ÉCRAN : x/y ne sont plus des coordonnées de monde mais des pixels
    # d'écran, et l'émission OAM ne retranche pas la caméra — l'acteur ne
    # défile pas. C'est l'UI en sprite (score, cœurs, curseur) avec tout le
    # SpriteComponent existant : états, animations, éditeur de sprite.
    #
    # Résolu au BUILD, pas au runtime : aucun champ dans `g_actors`, aucun
    # setter Lua. Un acteur est de l'UI ou du monde pour toute sa vie, et le
    # défaut doit rester littéralement gratuit (le C émis est mot pour mot
    # celui d'avant pour un acteur de monde).
    screen_space: bool = False
    # Direction initiale discrète (-1|0|1 × -1|0|1) : oriente le sprite affiché
    # dans l'éditeur et initialise dir_x/dir_y de l'Actor au runtime. (0,0)=omni.
    dir_x: int = 0
    dir_y: int = 0
    notes: str = ""   # note libre utilisateur (éditeur uniquement, jamais compilée)

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
            "obj_mode":    self.obj_mode,
            "screen_space": self.screen_space,
            "dir_x":       self.dir_x,
            "dir_y":       self.dir_y,
            "notes":       self.notes,
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
            obj_mode    = d.get("obj_mode", 0),
            screen_space = d.get("screen_space", False),
            dir_x       = d.get("dir_x", 0),
            dir_y       = d.get("dir_y", 0),
            notes       = d.get("notes", ""),
        )


# ──────────────────────────────────────────────────────────────────
#  Window — une région d'écran matérielle (WIN0 ou WIN1)
# ──────────────────────────────────────────────────────────────────

@dataclass
class WindowSlot:
    """Une window matérielle GBA (WIN0 ou WIN1) authorée par la scène.
    `region` est l'index hardware réel (0 ou 1) — PAS la position dans
    Scene.windows, pour rester correct si l'utilisateur n'a que WIN1 sans
    WIN0. Rectangle en pixels écran, clampé 240×160 par window_set() au
    runtime (même fonction que l'API Lua window.set() — un seul point
    d'écriture, cf. project_camera_abstraction pour le même principe
    appliqué à la caméra).

    Défaut = tout traverse (visible=False, tous les layers_shown à True,
    obj_shown=True) : ajouter une window sans rien configurer ne doit RIEN
    cacher — l'utilisateur restreint ensuite, jamais l'inverse (neutralité
    de style, cf. ROADMAP v0.3.2). L'OBJ-window (région 2) et la région
    "extérieur" (3) n'ont pas de rectangle propre — elles restent 100%
    scriptables (window.set_obj, window.set_layer(3, ...)), hors périmètre
    de cette UI géométrique."""
    region: int = 0     # 0 = WIN0, 1 = WIN1
    x: int = 0
    y: int = 0
    w: int = 240
    h: int = 160
    visible: bool = False
    layers_shown: list = field(default_factory=lambda: [True, True, True, True])  # BG0-3
    obj_shown: bool = True


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
    cam_follow: str = ""   # nom de l'Actor à suivre (utilisé si cam_mode == "follow")
    # Mode caméra — pilote QUI écrit cam_x/cam_y au runtime :
    #   "fixed"  : reste à (cam_x, cam_y), authoré ci-dessus (pas de mouvement)
    #   "follow" : suit cam_follow via camera_follow() (deadzone cam_margin_x/y),
    #              même fonction runtime que l'API Lua camera.follow()
    #   "script" : le codegen ne touche plus à la caméra, scripts seuls
    # (cf. mémoire project_camera_abstraction — un seul point d'écriture).
    cam_mode: str = "fixed"
    cam_margin_x: int = 40   # deadzone horizontale (px), mode "follow"
    cam_margin_y: int = 20   # deadzone verticale (px), mode "follow"
    # Bornes de scroll (taille du monde en pixels) ; None = axe illimité.
    # Champ explicite (plus de déduction depuis la vitesse de parallax d'un
    # layer) ; pré-remplissable dans l'inspecteur depuis les fonds de la scène.
    cam_bounds_w: Optional[int] = None
    cam_bounds_h: Optional[int] = None
    # Windows matérielles (WIN0/WIN1) authorées pour cette scène — max 2,
    # une par région (cf. WindowSlot). Liste vide = comportement identique à
    # aujourd'hui (aucune window active, tout s'affiche normalement).
    windows: list = field(default_factory=list)  # list[WindowSlot]
    scroll_h: bool = True  # défilement horizontal activé (mode "follow")
    scroll_v: bool = False # défilement vertical activé (mode "follow")
    # Mode vidéo GBA de la scène (0-5). 0 = 4 fonds tuilés réguliers (défaut) ;
    # 1/2 = tuilé + affine ; 3/4/5 = un fond bitmap plein écran (BG2). Pilote
    # l'inspecteur (zones background/palettes). cf. ui MODE_INFO.
    render_mode: int = 0
    script: str = ""       # chemin relatif vers le script Lua de la scène ("" = aucun)
    text_bg: int = 1       # BG hardware (0-3) utilisé pour le calque texte TTE
    # Mise en page d'UI référencée par NOM (project/ui_layouts/<nom>.json) —
    # la géométrie authorée des zones de texte. "" = aucune, le script place
    # alors tout lui-même via text.draw(id, tx, ty). cf. models/ui_region.py
    ui_layout: str = ""
    # Police chargée par `scene_init`, celle qu'obtient tout texte qui n'en
    # nomme pas (zone sans `font_name`, `text.draw` sans `text.set_font`).
    # Référencée par NOM comme tout asset.
    #
    # "" = la première police encodable du projet — le comportement historique
    # (`text_set_font(0)` en dur), et le seul défaut qui ne soit pas un choix :
    # une police par défaut livrée avec le moteur imposerait un style, ce que la
    # v0.3.2 refuse explicitement. Un nom introuvable retombe sur la même
    # première police, et le validateur le dit.
    font_name: str = ""
    # Banque de palette où le texte lit ses couleurs — un SLOT de la sélection
    # de la scène (`active_bg_palettes` en cible BG, `active_obj_palettes` en
    # OBJ), donc les couleurs de l'UI sont celles que la scène a choisies.
    #
    # -1 = automatique : la police charge sa PROPRE palette dans la banque 15,
    # comportement historique. C'est le défaut, le retirer d'office changerait
    # en silence la couleur du texte de tout projet existant.
    ui_pal_bank: int = -1
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
    # ── Mélange de couleurs (cf. BLEND_* en tête de module) ───────
    # Le MODE est ici et pas sur les layers : le matériel n'en a qu'un pour tout
    # l'écran. Les layers ne portent que leur rôle (`BackgroundLayer.blend_role`).
    blend_mode: int = BLEND_NONE
    blend_eva: int = BLEND_EV_MAX   # poids du dessus (mode alpha)
    blend_evb: int = 0              # poids du dessous (mode alpha)
    blend_evy: int = BLEND_EV_MAX // 2   # intensité du fondu (modes 2 et 3)
    # Les sprites et le backdrop sont deux cibles comme les layers (BLDCNT bits
    # 4/5 et 12/13), mais ils n'ont pas de ligne dans la liste des layers : leur
    # rôle vit donc ici. Le backdrop en DESSOUS est le réglage qui fait marcher
    # un alpha au-dessus d'une zone vide — sans lui, rien derrière, donc rien à
    # mélanger.
    blend_obj_role: str = ""
    blend_backdrop_role: str = ""
    notes: str = ""   # note libre utilisateur (éditeur uniquement, jamais compilée)

    # ── Mélange : lectures dérivées ───────────────────────────────
    def blend_layers(self, role: str) -> list:
        """Layers tenant `role` dans le mélange, dans l'ordre de la scène."""
        return [L for L in self.background_layers if blend_role_of(L) == role]

    def blend_has_target(self, role: str) -> bool:
        """Y a-t-il au moins une cible dans ce rôle — layer, sprites ou backdrop ?

        C'est la question que pose le validateur : un mode sans DESSUS ne fait
        rien du tout, et un alpha sans DESSOUS ne fait rien non plus."""
        if self.blend_layers(role):
            return True
        return role in (self.blend_obj_role, self.blend_backdrop_role)

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
                 **({"blend_role": L.blend_role} if L.blend_role else {}),
                 **({} if L.visible else {"visible": False})}
                for L in self.background_layers
            ],
            "actors": [a.to_dict() for a in self.actors],
            "cam_x": self.cam_x,
            "cam_y": self.cam_y,
            "cam_follow": self.cam_follow,
            "cam_mode": self.cam_mode,
            "cam_margin_x": self.cam_margin_x,
            "cam_margin_y": self.cam_margin_y,
            "cam_bounds_w": self.cam_bounds_w,
            "cam_bounds_h": self.cam_bounds_h,
            "windows": [
                {"region": ws.region, "x": ws.x, "y": ws.y, "w": ws.w, "h": ws.h,
                 "visible": ws.visible, "layers_shown": ws.layers_shown,
                 "obj_shown": ws.obj_shown}
                for ws in self.windows
            ],
            "render_mode": self.render_mode,
            "scroll_h": self.scroll_h,
            "scroll_v": self.scroll_v,
            "script": self.script,
            "text_bg": self.text_bg,
            "ui_layout": self.ui_layout,
            "font_name": self.font_name,
            "ui_pal_bank": self.ui_pal_bank,
            "collision_layer": self.collision_layer,
            "collision_map": self.collision_map,
            "active_obj_palettes": self.active_obj_palettes,
            "active_bg_palettes": self.active_bg_palettes,
            "backdrop_color": self.backdrop_color,
            # Écrits seulement si un mélange est réglé : sans ça, tous les JSON
            # de scène du projet gagneraient cinq clés inertes.
            **({"blend_mode": self.blend_mode,
                "blend_eva": self.blend_eva, "blend_evb": self.blend_evb,
                "blend_evy": self.blend_evy,
                "blend_obj_role": self.blend_obj_role,
                "blend_backdrop_role": self.blend_backdrop_role}
               if self.blend_mode != BLEND_NONE else {}),
            "notes": self.notes,
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
                blend_role   = (L.get("blend_role", "")
                                if L.get("blend_role", "") in BLEND_ROLES else ""),
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
            # Migration : anciennes scènes sans cam_mode — "follow" si un
            # cam_follow était déjà authoré, sinon "fixed" (le scroll libre au
            # D-pad qui s'activait implicitement en son absence est retiré,
            # cf. project_camera_abstraction).
            cam_mode=d.get("cam_mode") or ("follow" if d.get("cam_follow") else "fixed"),
            cam_margin_x=d.get("cam_margin_x", 40),
            cam_margin_y=d.get("cam_margin_y", 20),
            cam_bounds_w=d.get("cam_bounds_w"),
            cam_bounds_h=d.get("cam_bounds_h"),
            windows=[
                WindowSlot(
                    region=wd.get("region", 0),
                    x=wd.get("x", 0), y=wd.get("y", 0),
                    w=wd.get("w", 240), h=wd.get("h", 160),
                    visible=wd.get("visible", False),
                    layers_shown=wd.get("layers_shown", [True, True, True, True]),
                    obj_shown=wd.get("obj_shown", True),
                )
                for wd in d.get("windows", [])
            ],
            render_mode=int(d.get("render_mode", 0)),
            scroll_h=d.get("scroll_h", True),
            scroll_v=d.get("scroll_v", False),
            script=d.get("script", ""),
            text_bg=d.get("text_bg", 1),
            ui_layout=d.get("ui_layout", ""),
            font_name=d.get("font_name", ""),
            ui_pal_bank=int(d.get("ui_pal_bank", -1)),
            collision_layer=d.get("collision_layer", 0),
            collision_map=d.get("collision_map", []),
            active_obj_palettes=d.get("active_obj_palettes", []),
            active_bg_palettes=d.get("active_bg_palettes", []),
            backdrop_color=d.get("backdrop_color"),
            blend_mode=(int(d.get("blend_mode", BLEND_NONE))
                        if int(d.get("blend_mode", BLEND_NONE)) in BLEND_MODES
                        else BLEND_NONE),
            blend_eva=clamp_ev(d.get("blend_eva", BLEND_EV_MAX)),
            blend_evb=clamp_ev(d.get("blend_evb", 0)),
            blend_evy=clamp_ev(d.get("blend_evy", BLEND_EV_MAX // 2)),
            blend_obj_role=(d.get("blend_obj_role", "")
                            if d.get("blend_obj_role", "") in BLEND_ROLES else ""),
            blend_backdrop_role=(d.get("blend_backdrop_role", "")
                                 if d.get("blend_backdrop_role", "") in BLEND_ROLES else ""),
            notes=d.get("notes", ""),
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
