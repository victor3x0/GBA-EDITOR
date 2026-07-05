"""
editor/scripting/api.py — Catalogue de l'API runtime GBA.

Chaque entrée décrit une fonction appelable depuis un script Lua,
avec sa signature Lua, sa traduction C, et le type de retour.

Le checker utilise ce catalogue pour valider les appels inconnus.
Le codegen l'utilise pour émettre le C correct (nom de fonction,
conversion des arguments string → constante entière, etc.).

Convention de nommage des clés :
  "self:method"   →  méthode d'actor (premier arg = self)
  "module.func"   →  fonction de module (sfx.play, input.held…)
  "func"          →  fonction globale (send, broadcast)
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── Types de paramètre ────────────────────────────────────────────
# Utilisés par le codegen pour savoir comment convertir l'arg Lua → C.
#
#   "int"   → entier littéral, passé directement
#   "str"   → string Lua → constante C (ANIM_*, SFX_*, KEY_*, TAG_*)
#             Le codegen fait la résolution via le contexte de build.
#   "bool"  → 0/1 entier
#   "actor" → référence à un acteur (nom Lua → pointeur C)

PARAM_INT          = "int"
PARAM_STR          = "str"
PARAM_STR_LITERAL  = "str_literal"   # string passée telle quelle entre guillemets C (pas de résolution de constante)
PARAM_BOOL         = "bool"
PARAM_ACTOR        = "actor"         # nom Lua → &g_actors[TAG_NAME]

# ─── Domaines de résolution pour les arguments "str" ──────────────
# Quand le codegen voit PARAM_STR il a besoin de savoir dans quel
# espace de noms chercher la constante C.
DOMAIN_ANIM  = "anim"    # ANIM_{actor}_{name}
DOMAIN_SFX   = "sfx"     # SFX_{name}
DOMAIN_MUSIC = "music"   # MUSIC_{name}
DOMAIN_KEY   = "key"     # BTN_{name}
DOMAIN_TAG   = "tag"     # TAG_{name}
DOMAIN_SCENE = "scene"   # SCENE_IDX_{name}


@dataclass
class Param:
    name: str
    ptype: str                        # PARAM_*
    domain: Optional[str] = None      # DOMAIN_* (seulement si ptype == PARAM_STR)


@dataclass
class ApiFunc:
    """Décrit une fonction de l'API runtime."""
    lua_name:  str                          # clé d'accès (ex: "self:play_anim")
    c_func:    str                          # nom C généré (ex: "actor_play_anim")
    params:    list[Param] = field(default_factory=list)
    ret:       str = "void"                 # type de retour C ("void", "int", "bool")
    self_first: bool = False                # True → émettre (self, ...) en C
    variadic:   bool = False                # True → args restants après params passés tels quels
    doc:       str = ""


# ─── Constantes écran (résolues par le codegen en littéraux C) ────
# Accessibles en Lua comme screen.width, screen.center_x, etc.
SCREEN_CONSTANTS: dict[str, int] = {
    "width":    240,
    "height":   160,
    "center_x": 120,
    "center_y": 80,
}


# ─── Catalogue complet ─────────────────────────────────────────────

RUNTIME_API: dict[str, ApiFunc] = {

    # ── Mouvement ──────────────────────────────────────────────────
    "self:move": ApiFunc(
        lua_name="self:move", c_func="actor_move",
        params=[Param("dx", PARAM_INT), Param("dy", PARAM_INT)],
        self_first=True,
        doc="Déplace l'actor de (dx, dy) pixels ce frame.",
    ),
    "self:set_pos": ApiFunc(
        lua_name="self:set_pos", c_func="actor_set_pos",
        params=[Param("x", PARAM_INT), Param("y", PARAM_INT)],
        self_first=True,
        doc="Téléporte l'actor à la position monde (x, y).",
    ),
    "self:set_velocity": ApiFunc(
        lua_name="self:set_velocity", c_func="actor_set_velocity",
        params=[Param("vx", PARAM_INT), Param("vy", PARAM_INT)],
        self_first=True,
        doc="Définit la vélocité (appliquée chaque frame par apply_velocity).",
    ),
    "self:apply_velocity": ApiFunc(
        lua_name="self:apply_velocity", c_func="actor_apply_velocity",
        params=[], self_first=True,
        doc="Applique vx/vy à x/y.",
    ),

    # ── Lecture position / vélocité ───────────────────────────────
    "self:get_x": ApiFunc(
        lua_name="self:get_x", c_func="actor_get_x",
        params=[], self_first=True, ret="int",
        doc="Retourne la position X monde de l'actor.",
    ),
    "self:get_y": ApiFunc(
        lua_name="self:get_y", c_func="actor_get_y",
        params=[], self_first=True, ret="int",
        doc="Retourne la position Y monde de l'actor.",
    ),
    "self:get_vx": ApiFunc(
        lua_name="self:get_vx", c_func="actor_get_vx",
        params=[], self_first=True, ret="int",
        doc="Retourne la vélocité X de l'actor.",
    ),
    "self:get_vy": ApiFunc(
        lua_name="self:get_vy", c_func="actor_get_vy",
        params=[], self_first=True, ret="int",
        doc="Retourne la vélocité Y de l'actor.",
    ),

    # ── Animation ─────────────────────────────────────────────────
    "self:play_anim": ApiFunc(
        lua_name="self:play_anim", c_func="actor_play_anim",
        params=[Param("name", PARAM_STR, DOMAIN_ANIM)],
        self_first=True,
        doc="Démarre l'animation nommée (définie dans le SpriteAsset).",
    ),
    "self:set_frame": ApiFunc(
        lua_name="self:set_frame", c_func="actor_set_frame",
        params=[Param("frame", PARAM_INT)],
        self_first=True,
        doc="Force la frame courante.",
    ),
    "self:set_visible": ApiFunc(
        lua_name="self:set_visible", c_func="actor_set_visible",
        params=[Param("v", PARAM_BOOL)],
        self_first=True,
        doc="Affiche (1) ou cache (0) le sprite.",
    ),
    "self:set_active": ApiFunc(
        lua_name="self:set_active", c_func="actor_set_active",
        params=[Param("v", PARAM_BOOL)],
        self_first=True,
        doc="Active (1) ou désactive (0) l'actor : update, collisions et rendu arrêtés si 0.",
    ),
    "self:set_flip_h": ApiFunc(
        lua_name="self:set_flip_h", c_func="actor_set_flip_h",
        params=[Param("v", PARAM_INT)],
        self_first=True,
        doc="Orientation horizontale : -1=gauche (retourné), 1=droite (normal). Passer la variable direction directement.",
    ),
    "self:set_flip_v": ApiFunc(
        lua_name="self:set_flip_v", c_func="actor_set_flip_v",
        params=[Param("v", PARAM_INT)],
        self_first=True,
        doc="Orientation verticale : -1=bas (retourné), 1=haut (normal).",
    ),
    "self:get_dir_x": ApiFunc(
        lua_name="self:get_dir_x", c_func="actor_get_dir_x",
        params=[], self_first=True, ret="int",
        doc="Retourne la direction X courante : -1 (gauche), 0 (neutre), 1 (droite).",
    ),
    "self:get_dir_y": ApiFunc(
        lua_name="self:get_dir_y", c_func="actor_get_dir_y",
        params=[], self_first=True, ret="int",
        doc="Retourne la direction Y courante : -1 (haut), 0 (neutre), 1 (bas).",
    ),
    "self:set_direction": ApiFunc(
        lua_name="self:set_direction", c_func="actor_set_direction",
        params=[Param("dx", PARAM_INT), Param("dy", PARAM_INT)],
        self_first=True,
        doc="Définit la direction discrète (dx, dy). Chaque valeur est clampée à -1|0|1.",
    ),
    "self:set_dir": ApiFunc(
        lua_name="self:set_dir", c_func="actor_set_dir",
        params=[Param("dir", PARAM_INT)],
        self_first=True,
        doc="Force la direction d'animation (1=N, 2=NE, 3=E, 4=SE, 5=S, 6=SW, 7=W, 8=NW, 0=override).",
    ),
    "self:get_dir": ApiFunc(
        lua_name="self:get_dir", c_func="actor_get_dir",
        params=[], self_first=True, ret="int",
        doc="Retourne la direction d'animation courante (1-8, 0=override).",
    ),
    "self:set_auto_dir": ApiFunc(
        lua_name="self:set_auto_dir", c_func="actor_set_auto_dir",
        params=[Param("v", PARAM_BOOL)],
        self_first=True,
        doc="Active (true) ou désactive (false) le calcul automatique de la direction depuis la vélocité.",
    ),
    "self:destroy": ApiFunc(
        lua_name="self:destroy", c_func="_destroy",  # résolu par codegen
        params=[], self_first=True,
        doc="Détruit l'actor : appelle on_destroy() puis le désactive (plus d'update, plus de rendu).",
    ),
    "self:get_tag": ApiFunc(
        lua_name="self:get_tag", c_func="actor_get_tag",
        params=[], self_first=True, ret="int",
        doc="Retourne le TAG_* de cet actor. Utile dans on_collide pour identifier other.",
    ),
    "self:set_pal": ApiFunc(
        lua_name="self:set_pal", c_func="actor_set_pal",
        params=[Param("bank", PARAM_INT)], self_first=True,
        doc="Change la palette bank OAM (0-15). Utile pour flash de dégâts ou effet d'invincibilité.",
    ),
    "self:play_sfx": ApiFunc(
        lua_name="self:play_sfx", c_func="_play_sfx",  # résolu par codegen (SoundFxComponent de l'actor)
        params=[], self_first=True,
        doc="Joue le Sfx configuré dans le SoundFX component de cet actor.",
    ),

    # ── Spawn ──────────────────────────────────────────────────────
    "actor.spawn": ApiFunc(
        lua_name="actor.spawn", c_func="_spawn",     # résolu par codegen
        params=[Param("prefab", PARAM_STR, "prefab"), Param("x", PARAM_INT), Param("y", PARAM_INT)],
        ret="void",
        doc='Instancie un prefab poolé à (x, y). Ex: actor.spawn("Bullet", self:get_x(), self:get_y()).',
    ),
    "get_actor": ApiFunc(
        lua_name="get_actor", c_func="_get_actor",   # résolu par codegen
        params=[Param("name", PARAM_STR)],
        ret="actor",
        doc='Référence directe vers un actor de la scène par son nom. Résolu à la compilation, zéro overhead runtime. Ex: get_actor("PADDLE_AUTO"):get_x().',
    ),

    # ── Input ──────────────────────────────────────────────────────
    "input.held": ApiFunc(
        lua_name="input.held", c_func="input_held",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY)],
        ret="bool",
        doc="Vrai si le bouton est maintenu appuyé ce frame.",
    ),
    "input.pressed": ApiFunc(
        lua_name="input.pressed", c_func="input_pressed",
        params=[Param("btn", PARAM_STR, DOMAIN_KEY)],
        ret="bool",
        doc="Vrai si le bouton vient d'être pressé (front montant).",
    ),

    # ── Audio ──────────────────────────────────────────────────────
    "sfx.play": ApiFunc(
        lua_name="sfx.play", c_func="sfx_play",
        params=[Param("name", PARAM_STR, DOMAIN_SFX)],
        doc="Joue un effet sonore one-shot.",
    ),
    "music.play": ApiFunc(
        lua_name="music.play", c_func="music_play",
        params=[Param("name", PARAM_STR, DOMAIN_MUSIC)],
        doc="Démarre une piste musicale (en boucle).",
    ),
    "music.stop": ApiFunc(
        lua_name="music.stop", c_func="music_stop",
        params=[],
        doc="Arrête la musique.",
    ),

    # ── Scènes ─────────────────────────────────────────────────────
    "scene.switch": ApiFunc(
        lua_name="scene.switch", c_func="scene_switch",
        params=[Param("name", PARAM_STR, DOMAIN_SCENE)],
        doc="Passe à une autre scène au début de la prochaine frame.",
    ),

    # ── Globals ────────────────────────────────────────────────────
    # Le codegen émet un accès direct à la variable (g_score) plutôt
    # qu'un appel de fonction. Ces entrées servent surtout au checker.
    "global.get": ApiFunc(
        lua_name="global.get", c_func="_global_get",   # résolu par codegen
        params=[Param("name", PARAM_STR)],
        ret="int",
        doc="Lit une variable globale (partagée entre tous les scripts).",
    ),
    "global.set": ApiFunc(
        lua_name="global.set", c_func="_global_set",   # résolu par codegen
        params=[Param("name", PARAM_STR), Param("value", PARAM_INT)],
        doc="Écrit une variable globale.",
    ),

    # ── Constants ──────────────────────────────────────────────────
    # Le codegen émet un accès direct au symbole (CONST_NOM) plutôt
    # qu'un appel de fonction. Lecture seule — pas de const.set.
    "const.get": ApiFunc(
        lua_name="const.get", c_func="_const_get",   # résolu par codegen
        params=[Param("name", PARAM_STR)],
        ret="int",
        doc="Lit une constante (valeur fixe déclarée dans le projet, jamais modifiée).",
    ),

    # ── Affichage texte HUD ───────────────────────────────────────
    # col/row en tiles (1 tile = 8px).
    # display.print : style printf — args variadiques passés tels quels au C.
    "display.print": ApiFunc(
        lua_name="display.print", c_func="draw_printf",
        params=[Param("col", PARAM_INT), Param("row", PARAM_INT), Param("fmt", PARAM_STR_LITERAL)],
        variadic=True,
        doc='Affiche du texte formaté à (col, row). Ex: display.print(1,1,"P1: %d",score)',
    ),
    "display.clear": ApiFunc(
        lua_name="display.clear", c_func="draw_clear",
        params=[Param("col", PARAM_INT), Param("row", PARAM_INT), Param("len", PARAM_INT)],
        doc="Efface len tiles à partir de (col, row) sur le HUD.",
    ),

    # ── Caméra ────────────────────────────────────────────────────
    "camera.set": ApiFunc(
        lua_name="camera.set", c_func="camera_set",
        params=[Param("x", PARAM_INT), Param("y", PARAM_INT)],
        doc="Place la caméra exactement à (x, y).",
    ),
    "camera.get_x": ApiFunc(
        lua_name="camera.get_x", c_func="camera_get_x",
        params=[], ret="int",
        doc="Retourne la position X courante de la caméra.",
    ),
    "camera.get_y": ApiFunc(
        lua_name="camera.get_y", c_func="camera_get_y",
        params=[], ret="int",
        doc="Retourne la position Y courante de la caméra.",
    ),
    "camera.follow": ApiFunc(
        lua_name="camera.follow", c_func="camera_follow",
        params=[
            Param("x",        PARAM_INT),
            Param("y",        PARAM_INT),
            Param("margin_x", PARAM_INT),
            Param("margin_y", PARAM_INT),
        ],
        doc="Suit le point (x,y) avec une zone morte. Ex: camera.follow(self:get_x(), self:get_y(), 40, 20)",
    ),

    # ── Maths ────────────────────────────────────────────────────
    "math.abs": ApiFunc(
        lua_name="math.abs", c_func="math_abs",
        params=[Param("x", PARAM_INT)], ret="int",
        doc="Valeur absolue entière.",
    ),
    "math.clamp": ApiFunc(
        lua_name="math.clamp", c_func="math_clamp",
        params=[Param("x", PARAM_INT), Param("lo", PARAM_INT), Param("hi", PARAM_INT)],
        ret="int",
        doc="Bloque x entre lo et hi.",
    ),
    "math.rand": ApiFunc(
        lua_name="math.rand", c_func="math_rand",
        params=[Param("lo", PARAM_INT), Param("hi", PARAM_INT)],
        ret="int",
        doc="Entier aléatoire entre lo et hi inclus. Ex: math.rand(1, 3) → 1, 2 ou 3.",
    ),
    "math.sign": ApiFunc(
        lua_name="math.sign", c_func="math_sign",
        params=[Param("x", PARAM_INT)], ret="int",
        doc="Signe de x : retourne -1, 0 ou 1.",
    ),
    "math.min": ApiFunc(
        lua_name="math.min", c_func="math_min",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT)], ret="int",
        doc="Minimum de deux entiers.",
    ),
    "math.max": ApiFunc(
        lua_name="math.max", c_func="math_max",
        params=[Param("a", PARAM_INT), Param("b", PARAM_INT)], ret="int",
        doc="Maximum de deux entiers.",
    ),

    # ── Scène ──────────────────────────────────────────────────────
    "scene.frame": ApiFunc(
        lua_name="scene.frame", c_func="scene_frame",
        params=[], ret="int",
        doc="Compteur de frames global depuis le début de la scène. Utile pour timers sans variable locale.",
    ),

    # ── Tile ───────────────────────────────────────────────────────
    "tile.get": ApiFunc(
        lua_name="tile.get", c_func="tile_get",
        params=[Param("x", PARAM_INT), Param("y", PARAM_INT)], ret="int",
        doc="Valeur brute de la tile à la position monde (x, y) en pixels. 0 = vide, >0 = valeur de la tile.",
    ),


}


# ─── Registre des événements ──────────────────────────────────────
# Source unique de vérité pour tous les events Lua/C.
# Clés par event :
#   icon    — icône affichée dans le script editor sidebar
#   stub    — template Lua inséré au clic
#   desc    — description courte (tooltip)
#   params  — liste de {name, type, description} (args Lua)
#   c_sig   — signature C générée par build.py / codegen
#
# Pour ajouter un event : une seule entrée ici suffit.

EVENT_REGISTRY: dict[str, dict] = {
    "on_start": {
        "icon": "▶",
        "icon_key": "ev_start",
        "stub": "function on_start()\n    \nend\n",
        "desc": "Appelé une fois au démarrage de la scène.",
        "params": [],
        "c_sig": "void {prefix}_on_start(Actor* self)",
    },
    "on_update": {
        "icon": "↺",
        "icon_key": "ev_update",
        "stub": "function on_update()\n    \nend\n",
        "desc": "Appelé chaque frame (60 fps). Logique principale.",
        "params": [],
        "c_sig": "void {prefix}_on_update(Actor* self)",
    },
    "on_late_update": {
        "icon": "↻",
        "icon_key": "ev_late_update",
        "stub": "function on_late_update()\n    \nend\n",
        "desc": "Appelé après physique et collisions. Idéal pour la caméra et le HUD.",
        "params": [],
        "c_sig": "void {prefix}_on_late_update(Actor* self)",
    },
    "on_collide": {
        "icon": "⬡",
        "icon_key": "ev_collide",
        "stub": "function on_collide(other, my_box, other_box)\n    \nend\n",
        "desc": "Appelé chaque frame où cet actor touche un autre.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor en contact"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collide(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_collision_enter": {
        "icon": "→",
        "icon_key": "ev_collision_enter",
        "stub": "function on_collision_enter(other, my_box, other_box)\n    \nend\n",
        "desc": "Premier frame de contact avec un autre actor.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor entrant en contact"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collision_enter(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_tile_collide": {
        "icon": "▦",
        "icon_key": "ev_tile_collide",
        "stub": "function on_tile_collide(normal_x, normal_y)\n    \nend\n",
        "desc": "Appelé quand cet actor heurte une tile solide de la collision map.",
        "params": [
            {"name": "normal_x", "type": "int", "description": "-1/0/1 : direction horizontale du choc"},
            {"name": "normal_y", "type": "int", "description": "-1/0/1 : direction verticale du choc"},
        ],
        "c_sig": "void {prefix}_on_tile_collide(Actor* self, int normal_x, int normal_y)",
    },
    "on_collision_exit": {
        "icon": "←",
        "icon_key": "ev_collision_exit",
        "stub": "function on_collision_exit(other, my_box, other_box)\n    \nend\n",
        "desc": "Premier frame sans contact après une collision.",
        "params": [
            {"name": "other",     "type": "actor", "description": "Référence à l'actor qui s'est éloigné"},
            {"name": "my_box",    "type": "int",   "description": "BOXTAG_* de ma box impliquée"},
            {"name": "other_box", "type": "int",   "description": "BOXTAG_* de la box adverse"},
        ],
        "c_sig": "void {prefix}_on_collision_exit(Actor* self, Actor* other, u8 my_box, u8 other_box)",
    },
    "on_button_a": {
        "icon": "🅐",
        "icon_key": "btn_a",
        "stub": "function on_button_a()\n    \nend\n",
        "desc": "Appui sur le bouton A (front montant).",
        "params": [],
        "c_sig": "void {prefix}_on_button_a(Actor* self)",
    },
    "on_button_b": {
        "icon": "🅑",
        "icon_key": "btn_b",
        "stub": "function on_button_b()\n    \nend\n",
        "desc": "Appui sur le bouton B (front montant).",
        "params": [],
        "c_sig": "void {prefix}_on_button_b(Actor* self)",
    },
    "on_button_l": {
        "icon": "L",
        "icon_key": "btn_l",
        "stub": "function on_button_l()\n    \nend\n",
        "desc": "Appui sur la gâchette L.",
        "params": [],
        "c_sig": "void {prefix}_on_button_l(Actor* self)",
    },
    "on_button_r": {
        "icon": "R",
        "icon_key": "btn_r",
        "stub": "function on_button_r()\n    \nend\n",
        "desc": "Appui sur la gâchette R.",
        "params": [],
        "c_sig": "void {prefix}_on_button_r(Actor* self)",
    },
    "on_button_start": {
        "icon": "⏎",
        "icon_key": "btn_start",
        "stub": "function on_button_start()\n    \nend\n",
        "desc": "Appui sur Start.",
        "params": [],
        "c_sig": "void {prefix}_on_button_start(Actor* self)",
    },
    "on_button_select": {
        "icon": "≡",
        "icon_key": "btn_select",
        "stub": "function on_button_select()\n    \nend\n",
        "desc": "Appui sur Select.",
        "params": [],
        "c_sig": "void {prefix}_on_button_select(Actor* self)",
    },
    "on_button_up": {
        "icon": "↑",
        "icon_key": "dir_n",
        "stub": "function on_button_up()\n    \nend\n",
        "desc": "Appui sur ↑.",
        "params": [],
        "c_sig": "void {prefix}_on_button_up(Actor* self)",
    },
    "on_button_down": {
        "icon": "↓",
        "icon_key": "dir_s",
        "stub": "function on_button_down()\n    \nend\n",
        "desc": "Appui sur ↓.",
        "params": [],
        "c_sig": "void {prefix}_on_button_down(Actor* self)",
    },
    "on_button_left": {
        "icon": "←",
        "icon_key": "dir_w",
        "stub": "function on_button_left()\n    \nend\n",
        "desc": "Appui sur ←.",
        "params": [],
        "c_sig": "void {prefix}_on_button_left(Actor* self)",
    },
    "on_button_right": {
        "icon": "→",
        "icon_key": "dir_e",
        "stub": "function on_button_right()\n    \nend\n",
        "desc": "Appui sur →.",
        "params": [],
        "c_sig": "void {prefix}_on_button_right(Actor* self)",
    },
    "on_destroy": {
        "icon": "✕",
        "icon_key": "ev_destroy",
        "stub": "function on_destroy()\n    \nend\n",
        "desc": "Appelé juste avant que l'actor soit désactivé par destroy().",
        "params": [],
        "c_sig": "void {prefix}_on_destroy(Actor* self)",
    },
}

# Aliases dérivés — ne plus éditer, générés depuis EVENT_REGISTRY
KNOWN_EVENTS: list[str] = list(EVENT_REGISTRY.keys())
EVENT_C_SIGNATURES: dict[str, str] = {k: v["c_sig"] for k, v in EVENT_REGISTRY.items()}


# ─── Résolution des constantes "str" ──────────────────────────────
# Helpers utilisés par le codegen pour convertir "nom_lua" → "NOM_C"

def _c_ident(name: str) -> str:
    """
    Assainit un nom de ressource arbitraire (espaces, ponctuation...) en
    fragment d'identifiant C valide, ex. 'Ruin At Last DX' -> 'RUIN_AT_LAST_DX'.
    Sans ça, un nom de Sfx/Music avec espace génère un #define invalide (le
    préprocesseur C coupe le nom de macro au premier espace et traite le
    reste comme texte de substitution).
    """
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    return r.upper()


def anim_constant(actor_sym: str, anim_name: str) -> str:
    """'walk' pour Hero → 'ANIM_HERO_WALK'"""
    return f"ANIM_{actor_sym.upper()}_{_c_ident(anim_name)}"


def sfx_constant(sfx_name: str) -> str:
    return f"SFX_{_c_ident(sfx_name)}"


def music_constant(music_name: str) -> str:
    return f"MUSIC_{_c_ident(music_name)}"


def key_constant(key_name: str) -> str:
    """'a' → 'BTN_A', 'left' → 'BTN_LEFT'"""
    return f"BTN_{_c_ident(key_name)}"


def tag_constant(actor_name: str) -> str:
    """'enemy' → 'TAG_ENEMY'"""
    return f"TAG_{_c_ident(actor_name)}"


def scene_constant(scene_name: str) -> str:
    """'Victory' → 'SCENE_IDX_VICTORY'"""
    return f"SCENE_IDX_{_c_ident(scene_name)}"


# ─── Événements de scène ───────────────────────────────────────────
# Distinct des events d'acteur : pas de paramètre `self`.

KNOWN_SCENE_EVENTS: list[str] = [
    "on_start",
    "on_update",
    "on_late_update",
]

def scene_event_sig(scene_sym: str, event: str) -> str:
    """Signature C namespacée pour un hook de scène."""
    return f"void {scene_sym}_scene_{event}(void)"


SCENE_EVENT_C_SIGNATURES: dict[str, str] = {
    "on_start":       "void {scene_sym}_scene_on_start(void)",
    "on_update":      "void {scene_sym}_scene_on_update(void)",
    "on_late_update": "void {scene_sym}_scene_on_late_update(void)",
}
