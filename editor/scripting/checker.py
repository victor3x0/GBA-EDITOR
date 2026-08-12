"""
editor/scripting/checker.py — Vérification sémantique d'un LuaScript.

Reçoit le LuaScript produit par parser.py et une description du contexte
de build (nom de l'actor, sprites disponibles, sfx disponibles…).
Retourne une liste de CheckError ; si vide, le script peut être compilé.

Vérifications en v1 :
  - Toutes les fonctions top-level sont des handlers connus (KNOWN_EVENTS)
  - Les appels self:method correspondent à l'API (RUNTIME_API)
  - Les appels module.func correspondent à l'API
  - Les noms d'animation passés à play_anim existent dans le SpriteAsset
  - Les noms de sfx existent dans le projet
  - Les noms de music existent dans le projet
  - Les boutons passés à input.held / input.pressed sont valides
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from .parser import (
    LuaScript, LuaFunction,
    StmtCall, StmtAssign, StmtLocalAssign, StmtIf, StmtWhile, StmtForNum,
    ExprInvoke, ExprCall, ExprIndex, ExprName, ExprString,
    ExprNumber, ExprUnop, ExprBool,
)
from .api import (RUNTIME_API, REMOVED_API, KNOWN_EVENTS, DOMAIN_ANIM, DOMAIN_SFX,
                  DOMAIN_MUSIC, DOMAIN_KEY, DOMAIN_SCENE, DOMAIN_CAMERA, DOMAIN_TEXT, DOMAIN_FONT,
                  DOMAIN_PALETTE,
                  DOMAIN_REGION, DOMAIN_IMAGE,
                  DOMAIN_TAG, DOMAIN_PREFAB, DOMAIN_ACTOR, DOMAIN_GLOBAL,
                  DOMAIN_CONST)


# Ce à quoi ressemble une CLÉ et pas un libellé : minuscules, chiffres, au
# moins un tiret bas, ni espace ni accent. « village_garde_01 » oui, « Appuyez
# sur A » non — de quoi voir la faute de frappe sans suspecter chaque littéral
# (cf. Checker._check_text).
_KEY_SHAPED = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")


# ─── Résultat ─────────────────────────────────────────────────────

@dataclass
class CheckError:
    level:   str   # "error" | "warning"
    message: str


@dataclass
class BuildContext:
    """
    Informations fournies par build.py pour la validation contextuelle.
    Tous les champs sont optionnels ; si absent, la vérification est relâchée.
    """
    actor_name:   str        = ""
    anim_names:   list[str]  = None    # noms d'anim définis dans le SpriteAsset lié
    sfx_names:    list[str]  = None    # noms de Sfx dans le projet
    music_names:  list[str]  = None    # noms de Music dans le projet
    scene_names:  list[str]  = None    # noms de scènes du projet
    camera_names: list[str]  = None    # noms de caméras du projet (pour camera.switch)
    actor_names:  list[str]  = None    # noms des actors de la scène (pour get_actor)
    prefab_names: list[str]  = None    # noms de Prefab du projet (pour actor.spawn)
    global_names: list[str]  = None    # noms de GlobalVar déclarées dans le projet
    global_types: dict[str, str] = None  # nom -> type ("int"/"bool"/"u8"/"u16"/"s8"/"s16")
    const_names:  list[str]  = None    # noms de Constant déclarées dans le projet
    sfx_component_name: Optional[str] = None  # Sfx lié au SoundFxComponent de cet actor (si présent)
    text_keys:    list[str]  = None    # clés de la table de textes du projet
    font_names:   list[str]  = None    # noms des polices encodables
    palette_names: list[str] = None    # palettes du catalogue de couleurs
    region_names: list[str]  = None    # emplacements de texte (toutes mises en page)
    image_names:  list[str]  = None    # images d'interface (toutes mises en page)
    save_slots:   Optional[int] = None # emplacements de sauvegarde déclarés au projet
    # Y a-t-il seulement quelque chose à sauver ? Sauver sans variable
    # persistante n'échoue pas, ça ne fait simplement RIEN — le genre de silence
    # qu'on ne diagnostique pas en regardant son script.
    has_persistent: Optional[bool] = None

    VALID_KEYS = {"a", "b", "l", "r", "start", "select", "up", "down", "left", "right"}


# Plage valide par type C généré (cf. scripting/globals.py) — "int" n'a pas
# de plage restreinte (entier natif ARM 32 bits), donc absent de la table.
_TYPE_RANGES = {
    "bool": (0, 1),
    "u8":   (0, 255),
    "s8":   (-128, 127),
    "u16":  (0, 65535),
    "s16":  (-32768, 32767),
}


# ─── Checker ──────────────────────────────────────────────────────

class Checker:

    def __init__(self, ctx: BuildContext):
        self.ctx    = ctx
        self.errors: list[CheckError] = []

    def check(self, script: LuaScript, check_event_names: bool = True) -> list[CheckError]:
        for fn in script.functions:
            self._check_function(fn, check_event_names)
        return self.errors

    # ── Fonctions ─────────────────────────────────────────────────

    def _check_function(self, fn: LuaFunction, check_event_names: bool = True):
        # check_event_names=False pour les modules de behavior : leurs
        # fonctions top-level sont des noms de méthode arbitraires (M.update),
        # pas des handlers d'événement actor/scène — seul le corps est validé.
        if check_event_names and fn.name not in KNOWN_EVENTS:
            self.errors.append(CheckError(
                "warning",
                f"Fonction '{fn.name}' inconnue — les fonctions top-level doivent être "
                f"des handlers d'événement ({', '.join(KNOWN_EVENTS[:5])}…).",
            ))
        self._check_block(fn.body)

    # ── Statements ────────────────────────────────────────────────

    def _check_block(self, stmts: list):
        for s in stmts:
            self._check_stmt(s)

    def _check_stmt(self, s):
        if isinstance(s, StmtCall):
            self._check_call_expr(s.call)
        elif isinstance(s, (StmtAssign, StmtLocalAssign)):
            self._check_expr(getattr(s, "value", None))
        elif isinstance(s, StmtIf):
            self._check_expr(s.cond)
            self._check_block(s.then)
            for _, b in s.elseifs:
                self._check_block(b)
            self._check_block(s.else_)
        elif isinstance(s, (StmtWhile, StmtForNum)):
            self._check_block(s.body)

    def _check_expr(self, e):
        if e is None:
            return
        if isinstance(e, (ExprInvoke, ExprCall)):
            self._check_call_expr(e)

    # ── Appels ────────────────────────────────────────────────────

    def _check_call_expr(self, e):
        if isinstance(e, ExprInvoke):
            # self:method(args)
            if isinstance(e.obj, ExprName) and e.obj.name == "self":
                key = f"self:{e.method}"
                api = RUNTIME_API.get(key)
                if api is None:
                    self.errors.append(CheckError(
                        "warning",
                        f"Méthode inconnue : self:{e.method}() — "
                        f"vérifiez l'orthographe ou consultez l'API.",
                    ))
                else:
                    self._check_args(key, api, e.args)
                    if key == "self:play_sfx" and not self.ctx.sfx_component_name:
                        self.errors.append(CheckError(
                            "warning",
                            "self:play_sfx() : cet actor n'a pas de component SoundFX "
                            "(ou son champ Sfx est vide) — l'appel ne jouera rien.",
                        ))

        elif isinstance(e, ExprCall):
            # module.func(args) ou func(args)
            key = self._call_key(e.func)
            if key is None:
                return
            # Les NOMS cités (scène, prefab, actor, global, constante) sont
            # vérifiés par leur domaine dans `_check_args`, comme tout autre
            # argument nommé — ces appels n'ont donc plus de chemin à part.
            # Ne restent ici que les contrôles qui portent sur autre chose que
            # le nom : la valeur d'un `global.set`, le numéro d'emplacement
            # d'un `save.*`. Aucun `return` : le reste des vérifications
            # (nombre d'arguments compris) doit suivre.
            if key == "global.set":
                self._check_global_set_value(e.args)
            if key.startswith("save."):
                self._check_save(key, e.args)
                # pas de `return` : le nombre d'arguments reste à vérifier
            api = RUNTIME_API.get(key)
            if api is None:
                # Une API RETIRÉE est une erreur guidée ; un nom simplement
                # inconnu reste toléré (helper défini par l'utilisateur).
                removed = REMOVED_API.get(key or "")
                if removed:
                    self.errors.append(CheckError("error", removed))
            else:
                self._check_args(key, api, e.args)

    def _call_key(self, func_expr) -> Optional[str]:
        """Reconstruit la clé API depuis l'expression de la fonction appelée."""
        if isinstance(func_expr, ExprName):
            return func_expr.name                    # ex: "get_actor", fonction helper user
        if isinstance(func_expr, ExprIndex):
            if isinstance(func_expr.obj, ExprName):
                return f"{func_expr.obj.name}.{func_expr.field}"   # ex: "sfx.play"
        return None

    def _check_args(self, key: str, api, args: list):
        """Vérifie le nombre d'arguments et les valeurs string si possible."""
        expected = len(api.params)
        got      = len(args)
        if api.variadic:
            if got < expected:
                self.errors.append(CheckError(
                    "error",
                    f"{key}() : au moins {expected} argument(s) attendu(s), {got} fourni(s).",
                ))
                return
        elif got != expected:
            self.errors.append(CheckError(
                "error",
                f"{key}() : {expected} argument(s) attendu(s), {got} fourni(s).",
            ))
            return

        for i, (param, arg) in enumerate(zip(api.params, args)):
            if not isinstance(arg, ExprString):
                continue   # on ne valide les strings que si elles sont littérales

            check = _DOMAIN_CHECKS.get(param.domain)
            if check:
                check(self, key, arg.value, param)

    def _check_anim(self, call_key: str, name: str):
        if self.ctx.anim_names is not None and name not in self.ctx.anim_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : animation '{name}' introuvable dans le "
                f"sprite lié ({', '.join(self.ctx.anim_names) or 'aucune'}).",
            ))

    def _check_sfx(self, call_key: str, name: str):
        if self.ctx.sfx_names is not None and name not in self.ctx.sfx_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : sfx '{name}' introuvable dans le projet.",
            ))

    def _check_music(self, call_key: str, name: str):
        if self.ctx.music_names is not None and name not in self.ctx.music_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : music '{name}' introuvable dans le projet.",
            ))

    def _check_text(self, call_key: str, key: str, literal_ok: bool = False):
        """Une clé de texte inconnue est une ERREUR, pas un avertissement : le
        #define n'existerait pas et la compilation C échouerait de toute façon,
        avec un message bien moins clair.

        Sauf là où un littéral est permis (`text.draw`) : la chaîne résout vers
        une clé si elle en matche une, sinon elle EST le texte. Reste le piège
        de la faute de frappe — `villag_garde_01` s'afficherait tel quel au
        joueur. On ne le signale que si la chaîne a la FORME d'une clé : aucun
        vrai libellé ne ressemble à ça, donc la faute se voit sans faire de
        bruit sur les littéraux légitimes. Même compromis que le silence sur
        les crochets en prose, côté balisage."""
        if self.ctx.text_keys is None or key in self.ctx.text_keys:
            return
        if literal_ok:
            if _KEY_SHAPED.match(key):
                self.errors.append(CheckError(
                    "warning",
                    f"{call_key}('{key}') : aucune entrée de ce nom dans la "
                    f"table — le texte « {key} » sera affiché tel quel. Faute "
                    f"de frappe sur une clé, ou littéral volontaire ?",
                ))
            return
        near = ", ".join(sorted(self.ctx.text_keys)[:5]) or "aucun texte dans le projet"
        self.errors.append(CheckError(
            "error",
            f"{call_key}('{key}') : texte '{key}' introuvable dans la table du "
            f"projet ({near}).",
        ))

    def _check_font(self, call_key: str, name: str):
        if self.ctx.font_names is not None and name not in self.ctx.font_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : police '{name}' introuvable ou sans glyphes "
                f"({', '.join(self.ctx.font_names) or 'aucune police utilisable'}).",
            ))

    def _check_palette(self, call_key: str, name: str):
        """Une palette inconnue est une ERREUR : le nom devient un `#define
        PAL_*`, et sans lui le C généré ne compile pas — autant le dire ici,
        avec la liste, plutôt qu'au `make` sur un identifiant indéfini."""
        if self.ctx.palette_names is not None and name not in self.ctx.palette_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : palette '{name}' introuvable dans le "
                f"catalogue de couleurs "
                f"({', '.join(self.ctx.palette_names) or 'catalogue vide'}).",
            ))

    def _check_region(self, call_key: str, name: str):
        """Une zone inconnue est une ERREUR, pas un avertissement : le
        `#define REGION_*` n'existerait pas et la faute ne remonterait qu'en
        « implicit declaration » à la compilation C, qui ne dit pas quoi
        écrire. Même sévérité que pour une clé de texte, pour la même raison."""
        if self.ctx.region_names is not None and name not in self.ctx.region_names:
            near = ", ".join(sorted(self.ctx.region_names)[:5]) or                 "aucune zone dans le projet — dessines-en une dans le canvas de scène"
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : zone de texte '{name}' introuvable ({near}).",
            ))

    def _check_image(self, call_key: str, name: str):
        """Même sévérité et même raison que `_check_region` : sans l'élément, le
        `#define IMAGE_*` n'existe pas et la faute ne remonte qu'en « implicit
        declaration » à la compilation C.

        L'ÉTAT, lui, n'est pas vérifié ici : il se lit dans le sprite de cette
        image-là, que le contexte de build ne porte pas. Le codegen émet une
        constante par état existant, donc un état inconnu échoue quand même au
        link — plus tard, mais jamais en silence."""
        if self.ctx.image_names is not None and name not in self.ctx.image_names:
            near = ", ".join(sorted(self.ctx.image_names)[:5]) or                 "aucune image dans le projet — dessines-en une dans le canvas de scène"
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : image d'interface '{name}' introuvable ({near}).",
            ))

    def _check_global(self, call_key: str, name: str):
        if self.ctx.global_names is not None and name not in self.ctx.global_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : variable globale '{name}' non déclarée dans le projet. "
                f"Ajoutez-la dans le panneau Globals de l'éditeur.",
            ))

    def _check_global_set_value(self, args: list):
        """La VALEUR d'un `global.set` — ce que le domaine ne dit pas.

        Le nom, lui, est vérifié par `_check_global` comme tout autre argument
        porteur d'un domaine. Un nom inconnu n'a pas de type déclaré, donc
        `_check_global_range` se tait de lui-même : pas besoin de séquencer les
        deux contrôles."""
        if len(args) < 2 or not isinstance(args[0], ExprString):
            return
        if self.ctx.global_types is None:
            return
        name = args[0].value
        self._check_global_range(name, self.ctx.global_types.get(name), args[1])

    @staticmethod
    def _literal_int(expr) -> Optional[int]:
        """Valeur entière d'un littéral connu à la compilation, sinon None
        (variable, expression calculée, etc. — pas de vérif possible)."""
        if isinstance(expr, ExprNumber):
            return expr.value
        if isinstance(expr, ExprUnop) and expr.op == "-" and isinstance(expr.operand, ExprNumber):
            return -expr.operand.value
        if isinstance(expr, ExprBool):
            return 1 if expr.value else 0
        return None

    def _check_global_range(self, name: str, typ: Optional[str], value_expr):
        rng = _TYPE_RANGES.get(typ)
        if rng is None:
            return
        val = self._literal_int(value_expr)
        if val is None:
            return
        lo, hi = rng
        if not (lo <= val <= hi):
            self.errors.append(CheckError(
                "warning",
                f"global.set('{name}', {val}) : valeur hors plage pour le type '{typ}' "
                f"({lo} à {hi}) — sera tronquée/wrap au build (comportement natif GBA/C), "
                f"pas d'erreur mais probablement pas ce que tu voulais.",
            ))

    def _check_save(self, call_key: str, args: list):
        """Le numéro d'emplacement, quand il est écrit en clair.

        Un emplacement hors capacité ne casse rien au runtime — les fonctions
        rendent 0 — mais un `save.write(1)` dans un projet à un seul emplacement
        est une sauvegarde qui n'a jamais lieu et ne dit rien. Vérifié seulement
        sur un littéral : un slot calculé (un menu qui compte les emplacements)
        est un usage légitime que le moteur borne déjà."""
        if self.ctx.has_persistent is False:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}() : aucune variable globale n'est marquée "
                f"persistante dans ce projet — l'appel ne sauvera rien. Cocher "
                f"« persist » sur les variables à conserver."))
        slots = self.ctx.save_slots
        if not args or slots is None:
            return
        val = self._literal_int(args[0])
        if val is None:
            return
        if not (0 <= val < slots):
            self.errors.append(CheckError(
                "error",
                f"{call_key}({val}) : le projet déclare {slots} emplacement(s) "
                f"de sauvegarde, numérotés de 0 à {slots - 1}."))

    def _check_const(self, call_key: str, name: str):
        if self.ctx.const_names is not None and name not in self.ctx.const_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : constante '{name}' non déclarée dans le projet. "
                f"Ajoutez-la dans le panneau Constants de l'éditeur.",
            ))

    def _check_scene(self, call_key: str, name: str):
        """Une scène inconnue est une ERREUR, pas un avertissement : le
        #define SCENE_IDX_* n'existerait pas et gcc échouerait de toute façon,
        avec un message bien moins clair (même raison que _check_text).
        Rappel : on attend le nom de la SCÈNE, pas celui de son script."""
        if self.ctx.scene_names is not None and name not in self.ctx.scene_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : scène '{name}' introuvable dans le projet. "
                f"Scènes disponibles : {', '.join(self.ctx.scene_names) or 'aucune'}.",
            ))

    def _check_camera(self, call_key: str, name: str):
        """Même raison que la scène : sans caméra de ce nom, le #define CAM_*
        n'existe pas et gcc échoue sur la ligne générée. `(default)` n'est pas
        acceptée ici — la caméra par défaut n'a pas de nom, un script qui veut
        y revenir écrit camera.switch sur une caméra qu'il a nommée."""
        if self.ctx.camera_names is not None and name not in self.ctx.camera_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : caméra '{name}' introuvable dans le projet. "
                f"Caméras disponibles : {', '.join(self.ctx.camera_names) or 'aucune'}.",
            ))

    def _check_prefab(self, call_key: str, name: str):
        """Un prefab inconnu est une ERREUR, même raison que la scène : le
        codegen émet `spawn_<Nom>(...)` sans rien vérifier, donc la faute ne se
        voyait qu'à la compilation C, sur un « implicit declaration of
        function » qui pointe la ligne générée."""
        if self.ctx.prefab_names is not None and name not in self.ctx.prefab_names:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : prefab '{name}' introuvable dans le projet. "
                f"Prefabs disponibles : {', '.join(self.ctx.prefab_names) or 'aucun'}.",
            ))

    def _check_actor(self, call_key: str, name: str):
        if self.ctx.actor_names is not None and name not in self.ctx.actor_names:
            self.errors.append(CheckError(
                "warning",
                f"{call_key}('{name}') : aucun actor nommé '{name}' dans la scène "
                f"({', '.join(self.ctx.actor_names) or 'aucun'}).",
            ))

    def _check_key(self, call_key: str, name: str):
        if name.lower() not in BuildContext.VALID_KEYS:
            self.errors.append(CheckError(
                "error",
                f"{call_key}('{name}') : bouton '{name}' invalide. "
                f"Valeurs valides : {', '.join(sorted(BuildContext.VALID_KEYS))}.",
            ))


# ─── Validation par domaine ───────────────────────────────────────
# Un domaine → comment vérifier que le nom cité existe. Table et non chaîne
# d'`elif` : elle se compare à `ALL_DOMAINS` au build
# (`validator._check_api_domains`). Un domaine sans entrée ici n'était validé
# par RIEN, en silence — l'erreur n'apparaissait qu'à la compilation C.
#
# Signature uniforme (checker, clé d'appel, valeur, param) : seul `_check_text`
# lit le `param`, mais une signature à géométrie variable redonnerait une table
# qu'on ne peut pas parcourir.
_DOMAIN_CHECKS: dict = {
    DOMAIN_ANIM:    lambda c, key, val, p: c._check_anim(key, val),
    DOMAIN_SFX:     lambda c, key, val, p: c._check_sfx(key, val),
    DOMAIN_MUSIC:   lambda c, key, val, p: c._check_music(key, val),
    DOMAIN_KEY:     lambda c, key, val, p: c._check_key(key, val),
    DOMAIN_TEXT:    lambda c, key, val, p: c._check_text(key, val, p.literal_ok),
    DOMAIN_FONT:    lambda c, key, val, p: c._check_font(key, val),
    DOMAIN_PALETTE: lambda c, key, val, p: c._check_palette(key, val),
    DOMAIN_REGION:  lambda c, key, val, p: c._check_region(key, val),
    DOMAIN_IMAGE:   lambda c, key, val, p: c._check_image(key, val),
    DOMAIN_SCENE:   lambda c, key, val, p: c._check_scene(key, val),
    DOMAIN_CAMERA:  lambda c, key, val, p: c._check_camera(key, val),
    DOMAIN_PREFAB:  lambda c, key, val, p: c._check_prefab(key, val),
    DOMAIN_ACTOR:   lambda c, key, val, p: c._check_actor(key, val),
    DOMAIN_GLOBAL:  lambda c, key, val, p: c._check_global(key, val),
    DOMAIN_CONST:   lambda c, key, val, p: c._check_const(key, val),
}

# Cinq de ces domaines étaient auparavant vérifiés par un contrôle accroché au
# NOM DE L'APPEL (`scene.switch`, `get_actor`, `global.*`, `const.get`) : une
# seconde fonction prenant le même domaine n'aurait rien déclenché, et
# `actor.spawn` n'était vérifié nulle part. Ils sont maintenant vérifiés par
# leur domaine, comme les autres. Ce qui reste accroché à un appel précis dans
# `_check_call_expr` ne porte plus sur un nom : la VALEUR d'un `global.set`, le
# numéro d'emplacement d'un `save.*`.

# Domaine NON validé, et pourquoi :
#   tag → `TAG_*` est un espace ouvert, l'auteur y met ce qu'il veut ; il
#         n'existe aucune liste de tags du projet contre quoi vérifier.
_DOMAINS_UNCHECKED: frozenset = frozenset({DOMAIN_TAG})


def covered_domains() -> frozenset:
    """Domaines dont le checker sait quoi faire — validés, ou explicitement
    laissés de côté.

    Rendus par une fonction et non par les tables elles-mêmes : le contrôle
    (`validator._check_api_domains`) demande « ce domaine t'est-il connu ? »,
    pas la mécanique interne. Les tables restent privées."""
    return frozenset(_DOMAIN_CHECKS) | _DOMAINS_UNCHECKED


# ─── Point d'entrée public ────────────────────────────────────────

def check(script: LuaScript, ctx: BuildContext, check_event_names: bool = True) -> list[CheckError]:
    return Checker(ctx).check(script, check_event_names)
