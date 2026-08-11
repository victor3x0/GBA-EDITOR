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
#
# Le `domain` d'un paramètre est aussi la déclaration « cet argument RÉFÉRENCE
# un élément nommé du projet » : c'est ce qui permet à scripting/refactor.py de
# suivre les renommages, sans liste de fonctions codée en dur. Tout nouvel
# argument qui cite un nom d'asset doit donc porter son domaine.
DOMAIN_ANIM   = "anim"    # ANIM_{actor}_{name}
DOMAIN_SFX    = "sfx"     # SFX_{name}
DOMAIN_MUSIC  = "music"   # MUSIC_{name}
DOMAIN_KEY    = "key"     # BTN_{name} — enum fixe du hardware, jamais renommé
DOMAIN_TAG    = "tag"     # TAG_{name}
DOMAIN_SCENE  = "scene"   # SCENE_IDX_{name}
DOMAIN_TEXT   = "text"    # TEXT_{key}  — clé de la table de textes du projet
DOMAIN_FONT   = "font"    # FONT_{name}
DOMAIN_PALETTE = "palette"  # PAL_{name} — palette du catalogue de couleurs
DOMAIN_REGION = "region"  # REGION_{name} — emplacement de texte (UILayout)
DOMAIN_IMAGE  = "image"   # IMAGE_{name}  — image d'interface (UILayout)
DOMAIN_PREFAB = "prefab"  # nom de Prefab — actor.spawn()
# Domaines résolus par un _emit_* dédié du codegen (pas de constante C
# générique) : ils n'en restent pas moins des références nommées.
DOMAIN_ACTOR  = "actor"   # nom d'Actor de la scène — get_actor()
DOMAIN_GLOBAL = "global"  # GlobalVar du projet   — global.get/set()
DOMAIN_CONST  = "const"   # Constant du projet    — const.get()


@dataclass
class Param:
    name: str
    ptype: str                        # PARAM_*
    domain: Optional[str] = None      # DOMAIN_* (seulement si ptype == PARAM_STR)
    # Une chaîne qui ne résout PAS dans le domaine est-elle acceptable ?
    # Faux partout sauf `text.draw` : un nom de scène ou de sfx inconnu est une
    # faute, un texte peut s'écrire au vol dans le script (ROADMAP v0.3.2,
    # 2026-07-27). Déclaré ici plutôt que testé sur le nom de la fonction — la
    # même table pilote checker, codegen et refactor.
    literal_ok: bool = False


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

    "self:set_obj_mode": ApiFunc(
        lua_name="self:set_obj_mode", c_func="actor_set_obj_mode",
        params=[Param("mode", PARAM_INT)],
        self_first=True,
        doc="Mode OAM : 0 = sprite normal, 2 = masque (window OBJ) — le sprite n'est plus dessiné, ses pixels opaques donnent sa forme à la window OBJ (région 2). 1 = semi-transparent, réservé au blending, pas encore câblé.",
    ),
    "self:get_obj_mode": ApiFunc(
        lua_name="self:get_obj_mode", c_func="actor_get_obj_mode",
        params=[], self_first=True, ret="int",
        doc="Mode OAM courant de l'actor (0, 1 ou 2).",
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
        params=[Param("prefab", PARAM_STR, DOMAIN_PREFAB), Param("x", PARAM_INT), Param("y", PARAM_INT)],
        ret="void",
        doc='Instancie un prefab poolé à (x, y). Ex: actor.spawn("Bullet", self:get_x(), self:get_y()).',
    ),
    "get_actor": ApiFunc(
        lua_name="get_actor", c_func="_get_actor",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_ACTOR)],
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
        params=[Param("name", PARAM_STR, DOMAIN_GLOBAL)],
        ret="int",
        doc="Lit une variable globale (partagée entre tous les scripts).",
    ),
    "global.set": ApiFunc(
        lua_name="global.set", c_func="_global_set",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_GLOBAL), Param("value", PARAM_INT)],
        doc="Écrit une variable globale.",
    ),

    # ── Constants ──────────────────────────────────────────────────
    # Le codegen émet un accès direct au symbole (CONST_NOM) plutôt
    # qu'un appel de fonction. Lecture seule — pas de const.set.
    "const.get": ApiFunc(
        lua_name="const.get", c_func="_const_get",   # résolu par codegen
        params=[Param("name", PARAM_STR, DOMAIN_CONST)],
        ret="int",
        doc="Lit une constante (valeur fixe déclarée dans le projet, jamais modifiée).",
    ),

    # ── Affichage texte : voir `text.*` (cf. REMOVED_API) ─────────
    # `display.print` / `display.clear` (libtonc TTE) ont été RETIRÉS. Leur
    # chaîne de format vivait dans le script, donc hors de la table de textes :
    # intraduisible, alors que la table existe pour ça. Et la police de TTE
    # occupait les mêmes tuiles que la nôtre, les deux s'écrasant.
    #
    # Migration : un libellé devient une entrée de table (`text.draw`), une
    # valeur devient `text.draw_num`. Les noms retirés sont listés dans
    # REMOVED_API pour que le checker guide au lieu de dire « inconnu ».

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
    "camera.set_bounds": ApiFunc(
        lua_name="camera.set_bounds", c_func="camera_set_bounds",
        params=[Param("world_w", PARAM_INT), Param("world_h", PARAM_INT)],
        doc="Définit les bornes de scroll (taille du monde en pixels, 0 = axe illimité). "
            "Ex: débloquer une nouvelle zone au runtime.",
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

    # ── Layer BG ───────────────────────────────────────────────────
    # `n` = bg_slot 0-3, le même index que dans l'inspecteur de scène.
    # Priorité 0 = dessiné devant (convention alignée sur bg_slot).
    "layer.show": ApiFunc(
        lua_name="layer.show", c_func="layer_show",
        params=[Param("n", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Affiche (true) ou cache (false) le layer de fond n. Ex: layer.show(2, false)",
    ),
    "layer.is_visible": ApiFunc(
        lua_name="layer.is_visible", c_func="layer_is_visible",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="1 si le layer n est affiché, 0 sinon.",
    ),
    "layer.set_priority": ApiFunc(
        lua_name="layer.set_priority", c_func="layer_set_priority",
        params=[Param("n", PARAM_INT), Param("prio", PARAM_INT)],
        doc="Change l'ordre d'affichage du layer n (0 = devant, 3 = derrière), sprites compris.",
    ),
    "layer.get_priority": ApiFunc(
        lua_name="layer.get_priority", c_func="layer_get_priority",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="Priorité actuelle du layer n (0 = devant).",
    ),
    "layer.set_scroll": ApiFunc(
        lua_name="layer.set_scroll", c_func="layer_set_scroll",
        params=[Param("n", PARAM_INT), Param("x", PARAM_INT), Param("y", PARAM_INT)],
        doc="Décalage propre du layer n, en pixels, ajouté au scroll caméra.",
    ),
    "layer.scroll_by": ApiFunc(
        lua_name="layer.scroll_by", c_func="layer_scroll_by",
        params=[Param("n", PARAM_INT), Param("dx", PARAM_INT), Param("dy", PARAM_INT)],
        doc="Ajoute (dx, dy) au décalage propre du layer n. Ex: nuages qui dérivent seuls.",
    ),
    "layer.get_scroll_x": ApiFunc(
        lua_name="layer.get_scroll_x", c_func="layer_get_scroll_x",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="Décalage horizontal propre du layer n (hors caméra).",
    ),
    "layer.get_scroll_y": ApiFunc(
        lua_name="layer.get_scroll_y", c_func="layer_get_scroll_y",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="Décalage vertical propre du layer n (hors caméra).",
    ),
    "layer.set_map": ApiFunc(
        lua_name="layer.set_map", c_func="layer_set_map",
        params=[Param("n", PARAM_INT), Param("sbb", PARAM_INT)],
        doc="Avancé — bascule le layer n sur un autre screenblock (0-31). Permet de préparer une carte puis de l'afficher d'un coup, sans tearing.",
    ),
    "layer.get_map": ApiFunc(
        lua_name="layer.get_map", c_func="layer_get_map",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="Avancé — screenblock actuellement affiché par le layer n.",
    ),

    # ── Texte ──────────────────────────────────────────────────────
    # Le texte se pose sur LE layer d'UI de la scène (Scene.text_bg) : les
    # glyphes vivent dans le charblock de ce layer. Pas de paramètre `layer`,
    # il serait mensonger. tx/ty en tuiles.
    #
    # GRAMMAIRE : position ou conteneur D'ABORD, contenu ENSUITE. Tenue par
    # toute la famille, y compris les primitives datées ci-dessous — une
    # grammaire mixte pendant l'intérim coûterait plus cher que de les aligner.
    # Le contenu finit la liste parce que c'est lui qui grandira (valeurs
    # interpolées) ; la géométrie, elle, ne bougera plus.
    #
    # L'ordre est celui du C : `zip(api.params, lua_args)` dans
    # `codegen._emit_api_call` est positionnel, donc réordonner ici réordonne
    # l'appel émis. Les signatures de `gba_engine.h` suivent, plutôt qu'une
    # permutation invisible entre Lua et C qu'il faudrait ensuite se rappeler.
    "text.draw": ApiFunc(
        lua_name="text.draw", c_func="text_draw",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("id", PARAM_STR, DOMAIN_TEXT, literal_ok=True)],
        doc='Affiche un texte du projet à (tx, ty), en tuiles — une clé de la '
            'table, ou un littéral écrit sur place (qui ne se traduira pas). '
            'Ex: text.draw(2, 16, "village_garde_01")',
    ),
    # ── Rendu dans une RÉGION ──────────────────────────────────────
    # La région porte position, largeur de coupe, alignement et police : ce que
    # `draw_box` faisait passer en arguments, sauf que c'est désormais authoré
    # dans le canvas de scène et donc VISIBLE. Une seule grammaire pour les
    # deux placements.
    "text.draw_in": ApiFunc(
        lua_name="text.draw_in", c_func="text_draw_in",
        params=[Param("region", PARAM_STR, DOMAIN_REGION),
                Param("id", PARAM_STR, DOMAIN_TEXT)],
        doc='Affiche un texte dans une zone dessinée dans la scène. Ex: text.draw_in("boite_bas", "village_garde")',
    ),
    # Le pendant de text.clear pour une zone. Sans lui, faire disparaître une
    # boîte obligeait à recalculer son rectangle en tuiles à la main — donc à
    # tenir deux géométries d'accord, alors que la zone existe pour n'en avoir
    # qu'une. La cible (BG ou sprites) ne remonte pas jusqu'ici : c'est une
    # conséquence de l'ancrage, pas un choix d'appel.
    "text.clear_in": ApiFunc(
        lua_name="text.clear_in", c_func="text_clear_in",
        params=[Param("region", PARAM_STR, DOMAIN_REGION)],
        doc='Vide une zone de texte. Ex: text.clear_in("boite_bas")',
    ),
    # ── Lecture ────────────────────────────────────────────────────
    # Un texte à tempo (`[speed=4]`, `[pause=30]`) introduit un ÉTAT par zone :
    # il ne s'affiche plus, il se lit. Ces deux-là ne dessinent rien de neuf —
    # la règle « deux fonctions pour écrire » tient — mais sans elles, un script
    # n'aurait aucun moyen de savoir quand enchaîner.
    "text.reading": ApiFunc(
        lua_name="text.reading", c_func="text_reading",
        params=[Param("region", PARAM_STR, DOMAIN_REGION)], ret="int",
        doc='Vrai tant que le texte s\'écrit dans cette zone. Ex: if not text.reading("boite_bas") then scene.goto("SUITE") end',
    ),
    "text.skip": ApiFunc(
        lua_name="text.skip", c_func="text_skip",
        params=[Param("region", PARAM_STR, DOMAIN_REGION)],
        doc='Révèle tout le texte d\'un coup — le bouton « passer ». Ex: if input.pressed("A") then text.skip("boite_bas") end',
    ),
    "text.clear": ApiFunc(
        lua_name="text.clear", c_func="text_clear",
        params=[Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT)],
        doc="Efface un rectangle de w×h tuiles sur le layer d'UI.",
    ),
    "text.length": ApiFunc(
        lua_name="text.length", c_func="text_length",
        params=[Param("id", PARAM_STR, DOMAIN_TEXT)], ret="int",
        doc="Nombre de caractères d'un texte — la borne de la machine à écrire.",
    ),
    "text.set_font": ApiFunc(
        lua_name="text.set_font", c_func="text_set_font",
        params=[Param("f", PARAM_STR, DOMAIN_FONT)],
        doc='Charge une police en mémoire vidéo. Une seule à la fois. Ex: text.set_font("Pixelia")',
    ),

    # ── Images d'interface ─────────────────────────────────────────
    # Le pendant exact des zones de texte, pour un sprite : l'élément est
    # AUTHORÉ dans le canvas (position, sprite, état de départ) et le script ne
    # fait que changer d'état. Aucune fonction ne crée ni ne déplace une image —
    # ce serait rouvrir la géométrie au runtime, que la mise en page existe
    # justement pour fermer (cf. models/ui_region.py, « Pas de FieldValue »).
    #
    # `image_set` est le seul appel à ne pas se traduire terme à terme : l'état
    # est nommé dans le SPRITE de cette image-là, donc sa résolution en index a
    # besoin des deux arguments à la fois (cf. codegen._emit_ui_image_set).
    "ui.image_set": ApiFunc(
        lua_name="ui.image_set", c_func="ui_image_set_state",
        params=[Param("image", PARAM_STR, DOMAIN_IMAGE),
                Param("state", PARAM_STR)],
        doc='Change l\'état affiché par une image de l\'interface. '
            'Ex: ui.image_set("coeur_2", "vide")',
    ),
    "ui.image_play": ApiFunc(
        lua_name="ui.image_play", c_func="ui_image_play",
        params=[Param("image", PARAM_STR, DOMAIN_IMAGE), Param("on", PARAM_BOOL)],
        doc='Lance (true) ou fige (false) le défilement des frames. '
            'Ex: ui.image_play("curseur", false)',
    ),
    "ui.image_show": ApiFunc(
        lua_name="ui.image_show", c_func="ui_image_show",
        params=[Param("image", PARAM_STR, DOMAIN_IMAGE), Param("on", PARAM_BOOL)],
        doc='Affiche ou cache une image. Ex: ui.image_show("alerte", true)',
    ),
    "ui.image_state": ApiFunc(
        lua_name="ui.image_state", c_func="ui_image_state",
        params=[Param("image", PARAM_STR, DOMAIN_IMAGE)], ret="int",
        doc='Index de l\'état affiché — de quoi enchaîner sans mémoriser. '
            'Ex: if ui.image_state("coeur_1") == 0 then ... end',
    ),

    # ── Window ─────────────────────────────────────────────────────
    # Une window ne dessine rien : c'est un pochoir. Elle dit, par région
    # de l'écran, qui a le droit de s'afficher. L'apparence vient de ce
    # qu'on met dedans (tilemap, sprites) — jamais de la window elle-même.
    # Régions : 0 = WIN0, 1 = WIN1, 2 = window OBJ, 3 = extérieur.
    "window.show": ApiFunc(
        lua_name="window.show", c_func="window_show",
        params=[Param("n", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Active (true) ou désactive (false) la window n : 0 et 1 = les deux rectangles, 2 = la window OBJ.",
    ),
    "window.is_visible": ApiFunc(
        lua_name="window.is_visible", c_func="window_is_visible",
        params=[Param("n", PARAM_INT)], ret="int",
        doc="1 si la window n est active, 0 sinon.",
    ),
    "window.set": ApiFunc(
        lua_name="window.set", c_func="window_set",
        params=[Param("n", PARAM_INT), Param("x", PARAM_INT), Param("y", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT)],
        doc="Rectangle en pixels écran de la window n (0 ou 1). Clampé à 240×160.",
    ),
    "window.set_layer": ApiFunc(
        lua_name="window.set_layer", c_func="window_set_layer",
        params=[Param("r", PARAM_INT), Param("bg", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Autorise ou non le layer de fond `bg` dans la région r (0=WIN0, 1=WIN1, 2=window OBJ, 3=extérieur).",
    ),
    "window.get_layer": ApiFunc(
        lua_name="window.get_layer", c_func="window_get_layer",
        params=[Param("r", PARAM_INT), Param("bg", PARAM_INT)], ret="int",
        doc="1 si le layer `bg` est autorisé dans la région r, 0 sinon.",
    ),
    "window.set_obj": ApiFunc(
        lua_name="window.set_obj", c_func="window_set_obj",
        params=[Param("r", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Autorise ou non les sprites dans la région r.",
    ),
    "window.set_blend": ApiFunc(
        lua_name="window.set_blend", c_func="window_set_blend",
        params=[Param("r", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Autorise ou non le blending dans la région r. Assombrir le monde SAUF un panneau = blending activé dans la région 3, coupé dans la 0.",
    ),

    # ── Blend ──────────────────────────────────────────────────────
    # Deux jeux de cibles : le dessus (side 0, ce qui est mélangé) et le
    # dessous (side 1, ce avec quoi — situé derrière selon les priorités).
    # window.set_blend() décide ensuite des RÉGIONS où tout ceci s'applique.
    # ── Palettes au runtime ────────────────────────────────────────
    # Remplacer les seize couleurs d'une banque matérielle. C'est l'ÉCHANGE, pas
    # le cycle : faire tourner les couleurs d'une palette a été écarté (une lave
    # dessinée puis exportée en planche a des index différents d'une image à
    # l'autre — elle emprunte le chemin ordinaire des fonds animés).
    #
    # Deux fonctions et non un paramètre de cible : les deux pools sont
    # PHYSIQUEMENT distincts sur GBA (PAL_BG_RAM / PAL_OBJ_RAM), la scène les
    # sélectionne déjà séparément, et une cible en argument laisserait croire
    # qu'une même banque existe des deux côtés.
    "palette.set_bg": ApiFunc(
        lua_name="palette.set_bg", c_func="palette_set_bg",
        params=[Param("bank", PARAM_INT), Param("p", PARAM_STR, DOMAIN_PALETTE)],
        doc='Remplace les couleurs de la banque de FOND `bank` (0-15). '
            'Ex: palette.set_bg(0, "Nuit")',
    ),
    "palette.set_obj": ApiFunc(
        lua_name="palette.set_obj", c_func="palette_set_obj",
        params=[Param("bank", PARAM_INT), Param("p", PARAM_STR, DOMAIN_PALETTE)],
        doc='Remplace les couleurs de la banque de SPRITES `bank` (0-15). '
            'Ex: palette.set_obj(1, "Nuit")',
    ),

    # ── Sauvegarde (SRAM) ──────────────────────────────────────────
    # Écrit ou relit les variables globales MARQUÉES persistantes dans
    # l'éditeur. Aucun nom de variable en argument : ce qui est sauvé est une
    # propriété du projet, pas de l'appel — sinon deux endroits du jeu
    # pourraient sauver deux ensembles différents et la dernière écriture
    # gagnerait en silence.
    #
    # L'écriture est toujours explicite : le moment où l'on peut sauver est une
    # règle de game design, pas quelque chose que le moteur décide.
    "save.write": ApiFunc(
        lua_name="save.write", c_func="save_write",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Écrit les variables persistantes dans l'emplacement `slot` "
            "(0 = le premier). Rend 0 si l'emplacement n'existe pas.",
    ),
    "save.read": ApiFunc(
        lua_name="save.read", c_func="save_read",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Relit l'emplacement `slot` dans les variables persistantes. Rend 0 "
            "si l'emplacement est vide ou illisible — les variables ne sont "
            "alors PAS touchées.",
    ),
    "save.exists": ApiFunc(
        lua_name="save.exists", c_func="save_exists",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Vrai si l'emplacement `slot` contient une sauvegarde relisible. "
            "De quoi griser une entrée « Continuer ».",
    ),
    "save.erase": ApiFunc(
        lua_name="save.erase", c_func="save_erase",
        params=[Param("slot", PARAM_INT)], ret="int",
        doc="Vide l'emplacement `slot` : save.exists y répond faux ensuite.",
    ),

    "blend.set_mode": ApiFunc(
        lua_name="blend.set_mode", c_func="blend_set_mode",
        params=[Param("mode", PARAM_INT)],
        doc="0 = aucun mélange, 1 = alpha, 2 = éclaircir vers le blanc, 3 = assombrir vers le noir.",
    ),
    "blend.get_mode": ApiFunc(
        lua_name="blend.get_mode", c_func="blend_get_mode",
        params=[], ret="int",
        doc="Mode de mélange courant (0-3).",
    ),
    "blend.set_layer": ApiFunc(
        lua_name="blend.set_layer", c_func="blend_set_layer",
        params=[Param("side", PARAM_INT), Param("bg", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) le layer de fond `bg` comme cible. side 0 = le dessus, 1 = le dessous.",
    ),
    "blend.set_obj": ApiFunc(
        lua_name="blend.set_obj", c_func="blend_set_obj",
        params=[Param("side", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) les sprites comme cible du dessus (side 0) ou du dessous (side 1).",
    ),
    "blend.set_backdrop": ApiFunc(
        lua_name="blend.set_backdrop", c_func="blend_set_backdrop",
        params=[Param("side", PARAM_INT), Param("on", PARAM_BOOL)],
        doc="Prend (ou non) la couleur de fond de la scène comme cible. Souvent le dessous manquant quand rien n'est dessiné derrière.",
    ),
    "blend.set_alpha": ApiFunc(
        lua_name="blend.set_alpha", c_func="blend_set_alpha",
        params=[Param("eva", PARAM_INT), Param("evb", PARAM_INT)],
        doc="Dosage du mode 1, en seizièmes (0-16) : eva pour le dessus, evb pour le dessous. Ex: blend.set_alpha(8, 8) = moitié-moitié.",
    ),
    "blend.set_fade": ApiFunc(
        lua_name="blend.set_fade", c_func="blend_set_fade",
        params=[Param("evy", PARAM_INT)],
        doc="Intensité des modes 2 et 3, en seizièmes (0 = rien, 16 = blanc ou noir complet). Un fondu = incrémenter evy frame après frame.",
    ),

    # ── Tilemap ────────────────────────────────────────────────────
    # tx/ty en TUILES dans la map du layer (pas en pixels monde) ; les
    # coordonnées wrappent comme le hardware.
    "tilemap.set": ApiFunc(
        lua_name="tilemap.set", c_func="tilemap_set",
        params=[Param("n", PARAM_INT), Param("tx", PARAM_INT), Param("ty", PARAM_INT), Param("tile", PARAM_INT)],
        doc="Pose la tuile d'index `tile` en (tx, ty) sur le layer n. Conserve le flip et la palette de la case.",
    ),
    "tilemap.get": ApiFunc(
        lua_name="tilemap.get", c_func="tilemap_get",
        params=[Param("n", PARAM_INT), Param("tx", PARAM_INT), Param("ty", PARAM_INT)], ret="int",
        doc="Index de tuile actuellement en (tx, ty) sur le layer n.",
    ),
    "tilemap.set_palette": ApiFunc(
        lua_name="tilemap.set_palette", c_func="tilemap_set_palette",
        params=[Param("n", PARAM_INT), Param("tx", PARAM_INT), Param("ty", PARAM_INT), Param("bank", PARAM_INT)],
        doc="Repeint la case (tx, ty) avec la banque de palette `bank` (0-15) — l'inpainting, au runtime.",
    ),
    "tilemap.set_flip": ApiFunc(
        lua_name="tilemap.set_flip", c_func="tilemap_set_flip",
        params=[Param("n", PARAM_INT), Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("h", PARAM_BOOL), Param("v", PARAM_BOOL)],
        doc="Retourne la case (tx, ty) horizontalement et/ou verticalement.",
    ),
    "tilemap.fill": ApiFunc(
        lua_name="tilemap.fill", c_func="tilemap_fill",
        params=[Param("n", PARAM_INT), Param("tx", PARAM_INT), Param("ty", PARAM_INT),
                Param("w", PARAM_INT), Param("h", PARAM_INT), Param("tile", PARAM_INT)],
        doc="Remplit un rectangle de w×h tuiles à partir de (tx, ty) avec la tuile `tile`.",
    ),

}


# ─── API retirée ──────────────────────────────────────────────────
# Le checker laisse passer un appel inconnu : ce peut être un helper défini par
# l'utilisateur. Une fonction RETIRÉE, elle, doit être signalée — sinon l'erreur
# n'arrive qu'à la compilation C, sous la forme d'un « implicit declaration of
# draw_printf » qui ne dit rien de ce qu'il faut écrire à la place.
#
# {clé retirée: message de migration}. Y ajouter une entrée est le geste qui
# accompagne toute suppression d'API.

REMOVED_API: dict[str, str] = {
    "display.print":
        "display.print a été retiré (libtonc TTE hors du workflow). Sa chaîne de "
        "format vivait dans le script, donc hors de la table de textes : "
        "intraduisible. Remplace-le par une entrée de table affichée avec "
        'text.draw(tx, ty, "clé") — une valeur s\'y écrit "$mon_global", '
        "interpolée au build.",
    "display.clear":
        "display.clear a été retiré (libtonc TTE hors du workflow). Utilise "
        "text.clear(tx, ty, w, h) — même unité (tuiles), mais une HAUTEUR au "
        "lieu d'une longueur de ligne.",
    # ── Retirés avec les marqueurs de tempo (2026-07-31) ──────────
    # La machine à écrire et le rendu d'un nombre vivaient dans le SCRIPT. Le
    # tempo s'écrit désormais dans le texte (`[speed=4]`, `[pause=30]`) et une
    # valeur s'y interpole (`$score`) : les deux sont retournés à l'auteur du
    # texte, là où ils se relisent et se traduisent.
    "text.draw_upto":
        "text.draw_upto a été retiré : le tempo s'écrit maintenant DANS le texte "
        "([speed=4], [pause=30]). Une tête de lecture doit s'accrocher à quelque "
        "chose de nommé, et un couple (x, y) ne l'est pas — dessine une zone de "
        'texte dans le canvas, puis text.draw_in("nom_de_zone", "clé"). '
        "text.reading() dit si elle a fini, text.skip() la termine d'un coup.",
    "text.draw_in_upto":
        "text.draw_in_upto a été retiré : le tempo s'écrit maintenant DANS le "
        "texte. Mets [speed=4] en tête de l'entrée et appelle "
        'text.draw_in("nom_de_zone", "clé") — l\'appeler à chaque frame ne '
        "relance pas la lecture. text.reading() dit si elle a fini.",
    "text.draw_num":
        "text.draw_num a été retiré : une entrée de table sait porter sa valeur. "
        'Écris "$mon_global" dans le contenu du texte, puis '
        'text.draw(tx, ty, "clé"). Le nom cité est celui d\'un global ou d\'une '
        "constante du projet, et il suit les renommages.",
    "text.draw_num_in":
        "text.draw_num_in a été retiré : une entrée de table sait porter sa "
        'valeur. Écris "$mon_global" dans le contenu du texte, puis '
        'text.draw_in("nom_de_zone", "clé").',
    "text.draw_box":
        "text.draw_box a été retiré : sa géométrie (position, largeur de coupe) "
        "vivait dans le script, donc invisible dans l'éditeur et incalculable "
        "avant le build. Dessine une zone de texte dans le canvas de scène, "
        'puis appelle text.draw_in("nom_de_zone", "clé"). La machine à écrire '
        "s'obtient en mettant [speed=4] en tête du texte. L'alignement, lui, "
        "n'existait pas et devient un réglage de la zone.",
}


# Réordonnancement du 2026-07-27 : la famille `text.*` est passée à la grammaire
# « position/conteneur → contenu ». L'ancien ordre reste du Lua VALIDE — mêmes
# noms, mêmes arités — donc ni le checker ni le compilateur C ne peuvent le
# repérer : `text.draw("clé", 2, 16)` résoudrait « clé » comme une coordonnée et
# 16 comme une clé de texte. Un projet non migré rendrait donc n'importe quoi,
# en silence.
#
# D'où la migration automatique au chargement
# (`project_migrations.migrate_text_arg_order`), et cette table qui en est la
# source : {nom Lua: (permutation des arguments de l'ANCIEN vers le NOUVEL
# ordre)}. Une permutation plutôt que du texte à réécrire à la main, pour que la
# migration et la signature ne puissent pas se contredire.
TEXT_ARG_REORDER_2026_07: dict[str, tuple[int, ...]] = {
    # text.draw(id, tx, ty)              → (tx, ty, id)
    "text.draw":         (1, 2, 0),
    # text.draw_upto(id, tx, ty, n)      → (tx, ty, id, n)
    # text.draw_num(value, tx, ty)       → (tx, ty, value)
    # text.draw_in(id, region)           → (region, id)
    "text.draw_in":      (1, 0),
    # text.draw_in_upto(id, region, n)   → (region, id, n)
    # text.draw_num_in(value, region)    → (region, value)
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


def text_constant(text_key: str) -> str:
    """'village_garde_01' → 'TEXT_VILLAGE_GARDE_01'"""
    return f"TEXT_{_c_ident(text_key)}"


# Primitives qui acceptent un littéral à la place d'une clé — DÉDUIT du
# catalogue, jamais listé à la main : marquer un `Param.literal_ok` suffit à
# faire suivre le checker, le codegen et la collecte de littéraux.
LITERAL_TEXT_CALLS: frozenset = frozenset(
    k for k, f in RUNTIME_API.items()
    for prm in f.params if prm.domain == DOMAIN_TEXT and prm.literal_ok
)


def anon_text_key(literal: str) -> str:
    """Clé de l'entrée ANONYME que fabrique un littéral passé à `text.draw`.

    Dérivée du CONTENU : la même phrase écrite dans deux scripts partage une
    seule entrée, et la clé ne bouge pas d'un build à l'autre. Un compteur, lui,
    se décalerait au premier littéral ajouté plus haut, décalant des index C
    sans que rien n'ait changé côté auteur.

    Le préfixe la range hors du chemin de l'utilisateur. Si une vraie clé
    s'appelait pareil, c'est elle qui gagnerait — la résolution essaie la table
    d'abord — donc le pire cas reste un texte affiché à la place d'un autre,
    jamais une table incohérente."""
    import hashlib
    return "_lit_" + hashlib.sha1(literal.encode("utf-8")).hexdigest()[:8]


def font_constant(font_name: str) -> str:
    """'Pixelia' → 'FONT_PIXELIA'"""
    return f"FONT_{_c_ident(font_name)}"


def palette_constant(palette_name: str) -> str:
    """'Nuit' → 'PAL_NUIT'"""
    return f"PAL_{_c_ident(palette_name)}"


def region_constant(region_name: str) -> str:
    """'boite_bas' → 'REGION_BOITE_BAS'"""
    return f"REGION_{_c_ident(region_name)}"


def image_constant(image_name: str) -> str:
    """'coeur_2' → 'IMAGE_COEUR_2' — index dans `g_ui_images`."""
    return f"IMAGE_{_c_ident(image_name)}"


def image_state_constant(image_name: str, state_name: str) -> str:
    """('coeur_2', 'vide') → 'IMGST_COEUR_2_VIDE'.

    Indexé par IMAGE et non par sprite : c'est l'image que le script nomme, et
    deux images du même sprite doivent pouvoir citer le même état sans que
    l'auteur ait à savoir quel asset est derrière. Le build émet une constante
    par (image, état de son sprite) — quelques `#define`, contre une résolution
    de chaîne au runtime que le moteur ne fait pas."""
    return f"IMGST_{_c_ident(image_name)}_{_c_ident(state_name)}"


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
