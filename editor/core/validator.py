"""
Validation du projet avant build.

Usage :
    from validator import validate_project
    warnings, errors = validate_project(project)

Plugins : enregistrer un validateur avec @register_validator
    from validator import register_validator, ValidationContext

    @register_validator
    def check_my_comp(ctx: ValidationContext):
        for actor in ctx.actors:
            for comp in actor.components:
                if isinstance(comp, MyComp) and comp.speed <= 0:
                    ctx.error(actor, "MyComp.speed doit être > 0")
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from core.project import Project

_VALIDATORS: list[Callable] = []


def register_validator(fn: Callable) -> Callable:
    """Décorateur — enregistre une fonction de validation."""
    _VALIDATORS.append(fn)
    return fn


@dataclass
class ValidationMessage:
    level: str      # "warning" | "error"
    actor: str      # nom de l'actor ou "" si global
    message: str

    def __str__(self):
        prefix = f"[{self.actor}] " if self.actor else ""
        return f"{'⚠' if self.level == 'warning' else '✖'}  {prefix}{self.message}"


class ValidationContext:
    def __init__(self, project: "Project"):
        self.project = project
        self.scene   = project.active_scene
        self.actors  = self.scene.actors if self.scene else []
        self._msgs: list[ValidationMessage] = []

    def warn(self, actor_or_name, message: str):
        name = getattr(actor_or_name, "name", str(actor_or_name)) if actor_or_name else ""
        self._msgs.append(ValidationMessage("warning", name, message))

    def error(self, actor_or_name, message: str):
        name = getattr(actor_or_name, "name", str(actor_or_name)) if actor_or_name else ""
        self._msgs.append(ValidationMessage("error", name, message))

    @property
    def warnings(self) -> list[ValidationMessage]:
        return [m for m in self._msgs if m.level == "warning"]

    @property
    def errors(self) -> list[ValidationMessage]:
        return [m for m in self._msgs if m.level == "error"]


def validate_project(project: "Project") -> tuple[list[ValidationMessage], list[ValidationMessage]]:
    """Retourne (warnings, errors). Errors bloquent le build, warnings non."""
    ctx = ValidationContext(project)

    # ── Validateurs built-in ─────────────────────────────────────────
    _check_scene(ctx)
    _check_actors(ctx)
    _check_backgrounds(ctx)
    # NB : pas d'avertissement quand un même sprite/prefab/layer pointant un
    # SLOT (pal_bank 0-15) résout vers des palettes différentes selon la scène.
    # C'est un comportement PRÉVISIBLE et voulu (palette-swap par slot, comme
    # le recoloring de sprites sur GB/NES) : le slot est le même partout, seul
    # le contenu du slot varie par scène. À l'utilisateur d'aligner ses
    # palettes par index en amont.
    _check_bg_text_cbb_conflict(ctx)
    _check_pal_bank_reference(ctx)
    _check_palette_bank_overflow(ctx)
    _check_api_prototypes(ctx)
    _check_api_domains(ctx)
    _check_text_overflow(ctx)
    _check_ui_text_key(ctx)
    _check_ui_image(ctx)
    _check_blend(ctx)
    _check_ui_panel_fill(ctx)
    _check_scene_font(ctx)
    _check_screen_space(ctx)

    # ── Validateurs plugins ──────────────────────────────────────────
    for fn in _VALIDATORS:
        try:
            fn(ctx)
        except Exception as exc:
            ctx.warn(None, f"Validateur '{fn.__name__}' a planté : {exc}")

    return ctx.warnings, ctx.errors


# ── Validateurs built-in ──────────────────────────────────────────────

def _check_api_domains(ctx: ValidationContext):
    """Un domaine d'argument doit être connu de SES DEUX consommateurs.

    Le `domain` d'un `Param` (`scripting/api.py`) dit qu'un argument cite un
    élément nommé du projet. Trois modules en dépendent — `refactor` (suivre
    les renommages), `checker` (le nom existe-t-il ?), `codegen` (quelle
    constante C émettre ?). Le premier DÉRIVE sa table du catalogue et n'a rien
    à oublier ; les deux autres portaient une liste écrite à la main, et un
    domaine absent n'y produisait aucun signal : le checker ne validait
    simplement rien, et le codegen retombait sur « émettre la chaîne telle
    quelle », donc du texte C là où le C attend un entier — panne au `make`,
    sur la ligne générée, jamais sur la cause.

    Même famille que `_check_api_prototypes` ci-dessous, même remède : les
    listes sont comparées ici, en ERREUR bloquante, plutôt que découvertes par
    la chaîne C. Placer un nouveau domaine dans l'une des cases (validé par
    domaine, validé par appel, non validé — et pourquoi) fait partie de son
    ajout, ce n'est pas une formalité.
    """
    from scripting.api import ALL_DOMAINS
    from scripting import checker, codegen

    for role, couverts in (("checker", checker.covered_domains()),
                           ("codegen", codegen.covered_domains())):
        manquants = sorted(ALL_DOMAINS - couverts)
        if manquants:
            ctx.error(None,
                      f"Domaine(s) d'argument inconnu(s) de {role} : "
                      f"{', '.join(manquants)}. Ajouter une entrée dans la table "
                      f"correspondante (scripting/{role}.py) — sans elle, un nom "
                      f"cité dans ce domaine n'est ni vérifié ni résolu.")
        # Un domaine listé mais qui n'existe plus est l'autre sens de la même
        # dérive : la table garde une entrée morte que rien ne peut plus
        # atteindre. Avertissement — ça ne casse pas le build.
        fantomes = sorted(couverts - ALL_DOMAINS)
        if fantomes:
            ctx.warn(None,
                     f"{role} : domaine(s) déclaré(s) mais inexistant(s) dans "
                     f"api.py : {', '.join(fantomes)}.")


def _check_api_prototypes(ctx: ValidationContext):
    """Une fonction du MOTEUR exposée en Lua doit être déclarée DEUX fois.

    `gba_engine.h` porte l'implémentation ; `actor_api_static.h` redéclare la
    même chose pour les unités de compilation de scène et d'actor, qui n'incluent
    pas le moteur. Une fonction ajoutée d'un seul côté franchit tout le chemin —
    checker vert, C émis correct — pour échouer au `make` sur un « implicit
    declaration of function », message qui pointe la ligne générée et jamais la
    cause. C'est ce qu'a fait `text_clear_in` : écrite dans le moteur, jamais
    redéclarée, donc inexposable en Lua sans casser le build.

    La règle est DÉRIVÉE, pas listée : est exigé dans le second en-tête ce qui
    est déjà présent dans le premier. Les fonctions résolues ailleurs (méthodes
    d'actor, `scene_switch`, `sfx_play`, helpers de globals — générés dans
    `actor_api.h` ou déclarés dans `runtime.h`) ne sont donc pas testées, sans
    qu'on ait à les énumérer ni à maintenir une liste d'exceptions.

    Erreur et non avertissement : le lien est garanti perdu, autant le dire
    avant de lancer la chaîne C que dans son log."""
    import re
    from core.app_paths import RUNTIME_DIR
    from scripting.api import RUNTIME_API

    engine = RUNTIME_DIR / "include" / "gba_engine.h"
    facade = RUNTIME_DIR / "include" / "actor_api_static.h"
    if not (engine.exists() and facade.exists()):
        ctx.warn(None, "En-têtes du runtime introuvables — prototypes non vérifiés.")
        return
    eng = engine.read_text(encoding="utf-8", errors="ignore")
    fac = facade.read_text(encoding="utf-8", errors="ignore")

    def declared(src: str, fn: str) -> bool:
        return re.search(r"\b" + re.escape(fn) + r"\s*\(", src) is not None

    missing = sorted({
        f.c_func for f in RUNTIME_API.values()
        if f.c_func and declared(eng, f.c_func) and not declared(fac, f.c_func)
    })
    if missing:
        ctx.error(None,
                  "Fonctions du moteur exposées en Lua mais non déclarées dans "
                  f"actor_api_static.h : {', '.join(missing)}. Le C généré les "
                  "appellera sans prototype et le build échouera.")

    # ── Ordre des arguments : Lua ↔ C ─────────────────────────────
    # `codegen._emit_api_call` mappe les arguments par POSITION. Si l'ordre des
    # `params` d'api.py et celui du prototype C divergent, chaque valeur atterrit
    # dans le mauvais paramètre — et comme ils sont tous `int`, le compilateur ne
    # peut RIEN dire. C'est le seul désaccord de cette chaîne qui compile
    # proprement et rend faux à l'exécution.
    #
    # On ne signale que les PERMUTATIONS (mêmes noms, autre ordre). Un simple
    # renommage — `layer.show(n, on)` en Lua contre `layer_show(bg, on)` en C, où
    # « n » parle d'un numéro de layer côté script — est délibéré et sans effet.
    def c_params(fn: str) -> list[str] | None:
        m = re.search(r"^\s*(?:void|int)\s+" + re.escape(fn) + r"\s*\(([^)]*)\)\s*;",
                      eng, re.M)
        if not m:
            return None
        a = m.group(1).strip()
        if a in ("", "void"):
            return []
        return [p.strip().split()[-1].lstrip("*") for p in a.split(",")]

    permuted = []
    for key, f in RUNTIME_API.items():
        cp = c_params(f.c_func) if f.c_func else None
        if cp is None:
            continue
        lua = [p.name for p in f.params]
        if lua != cp and sorted(lua) == sorted(cp):
            permuted.append(f"{key} : Lua ({', '.join(lua)}) vs C ({', '.join(cp)})")
    if permuted:
        ctx.error(None,
                  "Ordre des arguments incohérent entre api.py et gba_engine.h — "
                  "les valeurs atterriront dans le mauvais paramètre sans que le "
                  f"compilateur puisse le voir : {' ; '.join(permuted)}.")


def _check_scene(ctx: ValidationContext):
    if not ctx.scene:
        ctx.error(None, "Aucune scène active — impossible de compiler.")
        return
    if not ctx.actors:
        ctx.warn(None, "La scène ne contient aucun actor.")


def _check_actors(ctx: ValidationContext):
    from core.models.components import component_type_name

    for actor in ctx.actors:
        for comp in actor.components:
            try:
                ctype = component_type_name(comp)
            except ValueError:
                ctx.warn(actor, f"Composant de type non supporté ignoré : {type(comp).__name__}")
                continue

            if ctype == "sprite":
                _check_sprite(ctx, actor, comp)
            elif ctype == "collision_box":
                _check_collision(ctx, actor, comp)
            elif ctype == "script":
                _check_script(ctx, actor, comp)


def _check_sprite(ctx, actor, comp):
    proj   = ctx.project
    sprite = proj.get_sprite(comp.sprite_name) if comp.sprite_name else None

    if not sprite:
        ctx.warn(actor, "SpriteComponent sans SpriteAsset lié (pas de sprite_name).")
        return
    if not sprite.asset:
        ctx.warn(actor, f"Sprite '{sprite.name}' n'a pas de PNG assigné.")
        return
    ap = proj.asset_abs(sprite.asset)
    if not ap or not ap.exists():
        ctx.error(actor, f"Sprite '{sprite.name}' : fichier PNG introuvable ({sprite.asset}).")
    if sprite.frame_w <= 0 or sprite.frame_h <= 0:
        ctx.error(actor, f"Sprite '{sprite.name}' : frame_w/h invalides ({sprite.frame_w}×{sprite.frame_h}).")


def _check_collision(ctx, actor, comp):
    if getattr(comp, "w", 0) <= 0 or getattr(comp, "h", 0) <= 0:
        ctx.error(actor,
                  f"CollisionBox '{comp.tag}' : largeur ou hauteur nulle "
                  f"({comp.w}×{comp.h}) — hitbox invisible.")


def _check_script(ctx, actor, comp):
    proj = ctx.project
    if not comp.script:
        ctx.warn(actor, "ScriptComponent sans script assigné.")
        return
    sp = proj.asset_abs(comp.script)
    if not sp or not sp.exists():
        ctx.error(actor, f"Script introuvable : {comp.script}")


def _check_backgrounds(ctx: ValidationContext):
    proj = ctx.project
    if not ctx.scene:
        return

    for layer in ctx.scene.background_layers:
        if not layer.background_name:
            continue
        ba = proj.get_background(layer.background_name)
        if not ba:
            ctx.warn(None, f"Background BG{layer.bg_slot} : image '{layer.background_name}' introuvable — layer ignoré.")
            continue
        png = ba.asset if ba.asset else f"{layer.background_name}.png"
        if not (proj.background_images_dir / png).exists():
            ctx.warn(None, f"Background BG{layer.bg_slot} : PNG introuvable ({png}) — layer ignoré.")


def _check_bg_text_cbb_conflict(ctx: ValidationContext):
    """tte_init_se(text_bg, BG_CBB(text_bg)|BG_SBB(text_bg*8+7), ...) (cf.
    main_gen._gen_scene_init) loge la police DANS le charblock du layer UI
    choisi (bg_slot == text_bg) — plus de CBB3 figé. Le layer UI est donc
    censé ne porter AUCUNE image : son charblock entier est dédié à la
    police. Si un vrai layer BG occupe ce même bg_slot, ses tuiles ET son
    registre BGxCNT sont écrasés par la police — corruption garantie, pas
    juste un mauvais rendu (même sévérité que _check_bg_tile_budget), donc
    bloquant plutôt qu'un avertissement."""
    p = ctx.project
    for scene in p.scenes:
        text_bg = getattr(scene, "text_bg", -1)
        if text_bg not in (0, 1, 2, 3):
            continue
        for layer in scene.background_layers:
            if layer.background_name and layer.bg_slot == text_bg:
                ctx.error(None,
                    f"Scène '{scene.name}' : le layer BG{text_bg} ('{layer.background_name}') "
                    f"partage son bg_slot avec le Layer UI (text_bg={text_bg}) — "
                    f"son charblock est écrasé par les tuiles de police au build. "
                    f"Change le Layer UI de slot ou vide l'image de ce layer.")


def _check_text_overflow(ctx: ValidationContext):
    """Un texte qui ne tient pas dans sa zone est TRONQUÉ au dernier glyphe qui
    tient (cf. runtime `text_glyph_fits`), sans un mot en jeu.

    Ne juge que le DÉCIDABLE : la paire (zone, clé) doit être littérale dans le
    script — repérage par DOMAINE (`iter_call_sites`), donc toute future
    primitive « zone + contenu » est couverte sans rien déclarer — et le texte
    ne doit citer aucun global, `$score` faisant 1 ou 3 caractères selon la
    partie. Une constante, cuite au build, reste mesurable après substitution.
    Le reste appartient à la coupe au runtime : avertir sur une supposition
    apprendrait à ignorer les avertissements."""
    p = ctx.project
    if not getattr(p, "texts", None) or not getattr(p, "fonts", None):
        return
    from scripting.refactor import find_call_sites_in_project
    from scripting.api import DOMAIN_REGION, DOMAIN_TEXT
    from core.text_markup import parse, resolve, KIND_VALUE
    from core.engine_emulation.text_layout import layout_text

    regions = {r.name: r for _lay, r in p.all_regions()}
    fonts   = {f.name: f for f in p.fonts}
    globals_names = {g.name for g in getattr(p, "globals", [])}
    consts = {c.name: c.value for c in getattr(p, "constants", [])}

    # Une zone qui ne nomme pas sa police prend celle de la scène (cf.
    # font_emit.scene_default_font). Or une mise en page est PARTAGÉE : deux
    # scènes peuvent l'afficher avec deux polices par défaut différentes, donc
    # deux largeurs. On mesure contre chacune plutôt que d'en élire une —
    # choisir, ici, ce serait taire un débordement réel dans l'autre scène.
    from codegen.font_emit import scene_default_font
    first = p.fonts[0]
    lay_defaults: dict[str, list] = {}
    for _scene in p.scenes:
        _f = fonts.get(scene_default_font(p, _scene)[1]) or first
        _seen_f = lay_defaults.setdefault(getattr(_scene, "ui_layout", "") or "", [])
        if not any(x is _f for x in _seen_f):
            _seen_f.append(_f)
    region_layout = {r.name: lay.name for lay, r in p.all_regions()}

    def _fonts_for(el) -> list:
        """Polices contre lesquelles mesurer `el` : la sienne si elle est
        nommée, sinon tous les défauts de scène qui peuvent lui échoir."""
        if getattr(el, "font_name", "") in fonts:
            return [fonts[el.font_name]]
        return lay_defaults.get(region_layout.get(el.name, ""), None) or [first]

    seen: set = set()
    for site in find_call_sites_in_project(p, DOMAIN_REGION, DOMAIN_TEXT):
        region = regions.get(site.values[DOMAIN_REGION])
        text   = p.get_text(site.values[DOMAIN_TEXT])
        if region is None or text is None:
            continue          # le checker le dit déjà, et mieux
        parsed = parse(text.content or "")
        if any(m.kind == KIND_VALUE and m.value in globals_names
               for m in parsed.markers):
            continue          # largeur connue en jeu seulement
        for font in _fonts_for(region):
            # La police entre dans la clé de dédup : la même paire mesurée
            # contre deux défauts de scène donne deux verdicts distincts.
            trio = (region.name, text.key, font.name)
            if trio in seen:
                continue      # la même paire dans dix scripts, un seul message
            seen.add(trio)
            _placed, over = layout_text(font, resolve(parsed, consts),
                                        region.w, region.h)
            if over:
                ctx.warn(None,
                    f"Le texte '{text.key}' déborde de la zone '{region.name}' "
                    f"({region.w}×{region.h} px, police '{font.name}') — il sera "
                    f"tronqué au dernier glyphe qui tient. Agrandis la zone, "
                    f"raccourcis le texte, ou coupe-le en deux entrées.")

    # Textes AUTHORÉS : le couple (élément, contenu) est connu sans lire un
    # script, et plus sûr que le cas script — c'est `scene_init` qui l'écrit,
    # rien ne peut changer le texte avant l'affichage.
    from core.models.ui_region import KIND_TEXT
    for _lay, el in p.all_regions():
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        text = p.get_text(getattr(el, "text_key", "") or "")
        if text is None:
            continue          # clé vide ou cassée : _check_ui_text_key le dit
        parsed = parse(text.content or "")
        if any(m.kind == KIND_VALUE and m.value in globals_names
               for m in parsed.markers):
            continue
        for font in _fonts_for(el):
            _placed, over = layout_text(font, resolve(parsed, consts), el.w, el.h)
            if over:
                ctx.warn(None,
                    f"Le texte '{text.key}' déborde de l'élément '{el.name}' "
                    f"({el.w}×{el.h} px, police '{font.name}') — il sera tronqué au "
                    f"dernier glyphe qui tient. Agrandis l'élément dans le canvas, "
                    f"ou raccourcis le texte.")


def _check_ui_text_key(ctx: ValidationContext):
    """Un texte qui pointe une clé DISPARUE ne dessine rien.

    Erreur silencieuse par excellence : l'élément reste visible dans le canvas,
    le build n'émet aucun appel, et la ROM affiche un vide sans que rien n'ait
    échoué.

    Une clé VIDE, elle, ne se signale plus : depuis la fusion des deux types de
    texte, c'est un choix d'authoring normal — l'élément est un emplacement
    qu'un script remplira (`text.draw_in`). Le signaler ferait crier le
    validateur sur chaque boîte de dialogue d'un projet qui pilote son texte au
    script, c'est-à-dire sur le cas le plus courant."""
    p = ctx.project
    for lay, el in p.all_regions():
        key = getattr(el, "text_key", "") or ""
        if key and p.get_text(key) is None:
            ctx.error(None,
                f"Le texte '{el.name}' (mise en page '{lay.name}') pointe la clé "
                f"'{key}', qui n'existe plus dans la table de textes.")


def _check_blend(ctx: ValidationContext):
    """Les deux pannes MUETTES du mélange de couleurs.

    Le matériel n'échoue pas : il n'applique simplement rien, et rien ne le dit.
    Les deux cas se ressemblent à l'écran (« mon effet ne marche pas ») et se
    diagnostiquent dans deux registres différents.

    Avertissement et non erreur : la ROM tourne, elle est juste moins jolie que
    prévu — et un auteur peut très bien régler le mode d'abord et les cibles
    ensuite sans qu'on lui bloque un build entre les deux."""
    from core.models.scene import (BLEND_NONE, BLEND_TOP, BLEND_BOTTOM,
                                   BLEND_NEEDS_BOTTOM, blend_role_of)
    for scene in ctx.project.scenes:
        mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
        if mode == BLEND_NONE:
            continue
        if not scene.blend_has_target(BLEND_TOP):
            ctx.warn(None,
                f"Scène '{scene.name}' : un mode de fusion est réglé mais aucune "
                f"première cible n'est désignée — rien n'est mélangé, l'effet "
                f"n'aura aucun effet. Passe un layer (ou les sprites) en « dessus ».")
        elif mode in BLEND_NEEDS_BOTTOM and not scene.blend_has_target(BLEND_BOTTOM):
            ctx.warn(None,
                f"Scène '{scene.name}' : alpha sans seconde cible — le mélange "
                f"n'a lieu que là où un pixel du dessus a un pixel du dessous "
                f"derrière lui. Passe le layer de derrière, ou le backdrop, en "
                f"« dessous ».")
        # Un rôle « dessous » sous un mode qui ne l'emploie pas ne fait rien.
        if mode not in BLEND_NEEDS_BOTTOM:
            idle = [f"BG{L.bg_slot}" for L in scene.background_layers
                    if blend_role_of(L) == BLEND_BOTTOM]
            if idle:
                ctx.warn(None,
                    f"Scène '{scene.name}' : {', '.join(idle)} en « dessous », "
                    f"mais ce mode n'emploie que le dessus — ce rôle ne fait rien.")


def _check_ui_image(ctx: ValidationContext):
    """Une image sans sprite résoluble ne dessine rien.

    Même famille de panne silencieuse que la clé de texte disparue : l'élément
    est bien là dans le canvas, la table est bien émise, et la ROM ne montre
    rien à cet endroit. La distinction vide / cassé est reprise telle quelle —
    on ne réclame pas un sprite à une image fraîchement dessinée, on signale
    seulement une référence qui ne résout plus.

    L'état, lui, n'a pas besoin d'être vérifié : un `state_name` qui ne résout
    plus retombe sur l'état 0 (`UIImage.state_index`), ce qui affiche quelque
    chose plutôt que rien."""
    p = ctx.project
    if not hasattr(p, "all_images"):
        return
    from core.models.ui_region import KIND_PANEL
    for lay, im in p.all_images():
        # `all_images` porte aussi les panneaux à fond sprite : même table, même
        # panne, seul le mot change pour que le message désigne le bon objet.
        what = ("le fond du conteneur" if getattr(im, "kind", "") == KIND_PANEL
                else "l'image")
        name = getattr(im, "sprite_name", "") or ""
        if not name:
            continue
        if p.get_sprite(name) is None:
            ctx.error(None,
                f"{what.capitalize()} '{im.name}' (mise en page '{lay.name}') "
                f"pointe le sprite '{name}', qui n'existe plus dans le projet.")
        elif im.state_name and not any(
                s.name == im.state_name
                for s in getattr(p.get_sprite(name), "states", []) or []):
            ctx.warn(None,
                f"{what.capitalize()} '{im.name}' demande l'état "
                f"'{im.state_name}', absent du sprite '{name}' — il affichera "
                f"le premier état.")


def _check_ui_panel_fill(ctx: ValidationContext):
    """Le canvas peint le fond d'un conteneur d'UI quoi qu'il arrive ; le build,
    lui, n'en émet qu'une partie. Un panneau hors de ce cadre disparaît entre
    l'éditeur et la ROM, sans une ligne de log.

    Deux chemins depuis que les fonds OBJ existent, et le mode DIT lequel :
    couleur / nine-slice / background posent des tuiles et une carte, donc BG
    (`scene_color_fills` / `scene_image_fills`, root ancré ÉCRAN) ; sprite pave
    des OBJ, donc OBJ (`g_ui_images`). `fill_allowed` interdit les croisements —
    ce qui reste ici, ce sont les cas qui PASSENT le modèle et tombent quand
    même au build.

    Avertissement et non erreur : le texte de la zone s'affiche quand même, il
    lui manque son fond."""
    p = ctx.project
    from core.models.ui_region import (KIND_PANEL, FILL_NONE, FILL_COLOR,
                                       FILL_SPRITE, ANCHOR_SCREEN, TARGET_BG,
                                       fill_allowed)
    for scene in p.scenes:
        lay = p.scene_ui_layout(scene)
        if lay is None:
            continue
        rm = int(getattr(scene, "render_mode", 0) or 0)
        active = list(getattr(scene, "active_bg_palettes", []) or [])
        for el in lay.elements:
            if getattr(el, "kind", "") != KIND_PANEL:
                continue
            fk = getattr(el, "fill_kind", FILL_NONE)
            if fk == FILL_NONE:
                continue
            target = lay.resolved_target(el, rm)
            # ① Mode incompatible avec la cible. Le cas le plus courant est un
            # fond posé quand le root était ancré à l'écran, puis le root est
            # passé sur un acteur — la cible bascule en OBJ et emporte tout le
            # sous-arbre, sans que le fond ait été retouché.
            if not fill_allowed(fk, target):
                quoi = ("un fond sprite" if target != TARGET_BG
                        else "une couleur, un nine-slice ou un background")
                ctx.warn(None,
                    f"Scène '{scene.name}' : le fond du conteneur '{el.name}' "
                    f"est en mode « {fk} », qui n'existe pas en cible "
                    f"{target.upper()} — rien ne sera dessiné. Sur cette cible, "
                    f"choisir {quoi}.")
                continue
            why = []
            if fk == FILL_SPRITE:
                # ② Chemin OBJ. La résolution du sprite est dite par
                # `_check_ui_image` (même table) : ici, ce qui lui est propre.
                if not getattr(el, "fill_sprite", ""):
                    why.append("aucun sprite n'est choisi")
            else:
                # ③ Chemin BG.
                if getattr(scene, "text_bg", -1) not in (0, 1, 2, 3):
                    why.append("la scène n'a pas de calque UI (text_bg)")
                anchor = lay.effective_anchor(el)[0]
                if anchor != ANCHOR_SCREEN:
                    why.append(f"son ancrage est « {anchor} » (seul l'écran est émis)")
                if fk == FILL_COLOR and getattr(el, "fill_palette", "") not in active:
                    why.append(f"sa palette « {getattr(el, 'fill_palette', '') or '(aucune)'} » "
                               f"n'est pas dans les palettes BG actives de la scène")
            if why:
                ctx.warn(None,
                    f"Scène '{scene.name}' : le fond du conteneur "
                    f"'{el.name}' ne sera PAS dans la ROM — {' ; '.join(why)}. "
                    f"Le canvas le montre quand même : c'est l'éditeur qui "
                    f"promet plus que le build ne tient.")


def _check_scene_font(ctx: ValidationContext):
    """`Scene.font_name` désigne la police que `scene_init` charge. Un nom qui
    ne répond pas retombe sur la première police encodable du projet — il FAUT
    charger quelque chose, sinon la scène n'affiche plus une lettre.

    Deux causes, deux messages : la police n'existe plus (renommée, supprimée),
    ou elle existe mais n'est pas encodable — sa planche manque, donc
    `project_fonts` la saute et le `#define FONT_*` n'existe pas non plus.
    Distinguer les deux évite de faire chercher un fichier pour un nom mort."""
    p = ctx.project
    from codegen.runtime_codegen.main_gen import project_fonts
    encodable = {f.name for f in project_fonts(p)}
    known = {f.name for f in getattr(p, "fonts", [])}
    fallback = sorted(encodable)[0] if len(encodable) == 1 else None
    for scene in p.scenes:
        want = getattr(scene, "font_name", "") or ""
        if not want or want in encodable:
            continue           # vide = premier du projet, choix légitime
        repli = (f" — la scène retombe sur « {fallback} »" if fallback
                 else " — la scène retombe sur la première police du projet")
        if want in known:
            ctx.warn(None,
                f"Scène '{scene.name}' : la police par défaut « {want} » n'a pas "
                f"de planche exploitable (PNG manquant ou aucun glyphe), elle "
                f"n'est donc pas compilée{repli}.")
        else:
            ctx.warn(None,
                f"Scène '{scene.name}' : la police par défaut « {want} » "
                f"n'existe pas dans le projet{repli}.")


def _check_screen_space(ctx: ValidationContext):
    """Un acteur ancré à l'écran (`Actor.screen_space`) lit ses x/y en pixels
    d'ÉCRAN. Trois systèmes continuent, eux, de les lire comme des coordonnées
    de MONDE — sans rien casser au build, donc sans rien dire.

    On n'avertit que sur ces trois-là : chacun a une correction évidente, ce qui
    est la seule raison d'écrire un avertissement (cf. la règle de verbosité —
    l'éditeur rend le matériel, il ne le commente pas).

    Toutes les scènes, pas seulement l'active : le build les compile toutes."""
    p = ctx.project
    for scene in p.scenes:
        ui = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
        for actor in getattr(scene, "actors", []) or []:
            if not getattr(actor, "screen_space", False):
                continue
            # ① Collision — la carte de collision est en pixels de monde. Une
            # hitbox posée à des coordonnées d'écran teste donc la mauvaise case.
            if any(type(c).__name__ == "CollisionBoxComponent"
                   for c in getattr(actor, "components", []) or []):
                ctx.warn(actor,
                    f"Scène '{scene.name}' : '{actor.name}' est ancré à l'écran "
                    f"mais porte une CollisionBox — la carte de collision est en "
                    f"pixels de MONDE, la hitbox testera donc une autre case que "
                    f"celle qu'on voit. Retirer la CollisionBox, ou l'ancrage écran.")
            # ② Caméra — suivre une position d'écran fige la caméra sur place.
            if (getattr(scene, "cam_mode", "") == "follow"
                    and getattr(scene, "cam_follow", "") == actor.name):
                ctx.warn(actor,
                    f"Scène '{scene.name}' : la caméra suit '{actor.name}', qui est "
                    f"ancré à l'écran — sa position ne bouge pas avec le monde, la "
                    f"caméra restera donc immobile. Cibler un acteur de monde.")
            # ③ Zone d'UI ancrée SUR cet acteur — `text_region_origin()` retranche
            # la caméra pour une ancre acteur (elle la suppose dans le monde) ;
            # sur un acteur d'écran ça décale la zone du scroll courant.
            if ui is None:
                continue
            from core.models.ui_region import ANCHOR_ACTOR
            for el in getattr(ui, "elements", []) or []:
                # Sur les ROOTS seulement : un enfant hérite de l'ancrage de son
                # root (cf. effective_anchor), le signaler pour tout un
                # sous-arbre répéterait le même défaut autant de fois.
                if getattr(el, "parent", ""):
                    continue
                if (getattr(el, "anchor", "") == ANCHOR_ACTOR
                        and getattr(el, "anchor_actor", "") == actor.name):
                    ctx.warn(actor,
                        f"Scène '{scene.name}' : l'élément d'interface '{el.name}' "
                        f"est ancré sur '{actor.name}', lui-même ancré à l'écran — "
                        f"l'ancrage acteur suppose une position de monde et "
                        f"retranchera le scroll une seconde fois. Ancrer l'élément "
                        f"à l'ÉCRAN : les deux sont déjà dans le même repère.")


def _check_pal_bank_reference(ctx: ValidationContext):
    """Un asset (actor / prefab / layer BG) peut pointer une palette RÉFÉRENCÉE
    (pal_bank 0-15) dont le slot est hors de active_*_palettes, vide, ou dont la
    palette a été supprimée du catalogue. Ce n'est PAS bloquant — ça peut être
    délibéré (banque destinée à être remplie plus tard, palette-swap par slot) —
    mais l'asset s'affichera alors avec le contenu du slot tel quel en PAL RAM
    (souvent la palette de secours de la banque 0), donc de mauvaises couleurs.
    On avertit en nommant le type et le nom de l'asset concerné.

    Résolution des slots identique au build :
    - actors  -> active_obj_palettes de LEUR scène ;
    - prefabs -> active_obj_palettes de la scène d'ancrage (1ère) ;
    - layers  -> active_bg_palettes de chaque scène utilisant le background."""
    from core.models.palette import OWN_PAL_BANK
    p = ctx.project

    def _slot_missing(active: list, slot: int) -> bool:
        if not (0 <= slot < len(active)):
            return True
        name = active[slot]
        return not (name and p.get_palette(name))

    def _sprite_of(entity):
        comp = entity.get_component("sprite")
        if not (comp and getattr(comp, "active", True) and comp.sprite_name):
            return None
        return p.get_sprite(comp.sprite_name)

    # ── Actors (par scène) ───────────────────────────────────────────
    for scene in p.scenes:
        active = getattr(scene, "active_obj_palettes", [])
        for actor in scene.actors:
            if not actor.active:
                continue
            pb = getattr(actor, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            sp = _sprite_of(actor)
            if not (sp and sp.asset):
                continue  # pas de sprite construit -> pal_bank sans effet
            if _slot_missing(active, pb):
                ctx.warn(actor,
                    f"Actor '{actor.name}' pointe la banque OBJ {pb} de la scène "
                    f"'{scene.name}', vide ou hors de la sélection active — le "
                    f"sprite s'affichera avec le contenu par défaut de ce slot.")

    # ── Prefabs poolés (via scène d'ancrage = 1ère scène) ────────────
    anchor = p.scenes[0] if p.scenes else None
    anchor_active = getattr(anchor, "active_obj_palettes", []) if anchor else []
    for pf in p.prefabs:
        if getattr(pf, "max_instances", 0) <= 0:
            continue
        pb = getattr(pf, "pal_bank", OWN_PAL_BANK)
        if pb == OWN_PAL_BANK:
            continue
        sp = _sprite_of(pf)
        if not (sp and sp.asset):
            continue
        if _slot_missing(anchor_active, pb):
            where = f" (résolue via la scène '{anchor.name}')" if anchor else ""
            ctx.warn(None,
                f"Prefab '{pf.name}' pointe la banque OBJ {pb}{where}, vide ou "
                f"hors de la sélection active — ses instances s'afficheront avec "
                f"le contenu par défaut de ce slot.")

    # ── Layers BG (portés par la scène) ──────────────────────────────
    for scene in p.scenes:
        active = getattr(scene, "active_bg_palettes", [])
        for layer in scene.background_layers:
            if not layer.background_name:
                continue
            pb = getattr(layer, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            if _slot_missing(active, pb):
                ctx.warn(None,
                    f"Background '{layer.background_name}' BG{layer.bg_slot} (scène "
                    f"'{scene.name}') pointe la banque BG {pb}, vide ou hors de "
                    f"la sélection active — le layer s'affichera avec le contenu "
                    f"par défaut de ce slot.")


def _check_palette_bank_overflow(ctx: ValidationContext):
    """Chaque scene ne dispose que de 16 banques materielles par pool (OBJ /
    BG). Palettes referencees + palettes propres distinctes (assets en mode
    OWN) sont auto-allouees par palette_alloc ; si le total depasse 16, une
    ou plusieurs palettes propres ne trouvent pas de slot -> avertissement
    (non bloquant : ces assets retombent sur la banque 0 au build)."""
    from codegen.palette_alloc import scene_bank_layout
    p = ctx.project
    for scene in p.scenes:
        for pool, label in (("obj", "OBJ (sprites)"), ("bg", "BG (fonds)")):
            layout = scene_bank_layout(p, scene, pool)
            if layout.overflow():
                ctx.warn(None,
                    f"Scène '{scene.name}' : plus de 16 palettes {label} "
                    "nécessaires (référencées + palettes propres des assets "
                    "sans palette assignée). Certains assets retomberont sur la "
                    "banque 0 et afficheront de mauvaises couleurs — réduire le "
                    "nombre de palettes distinctes ou partager des palettes "
                    "référencées.")
