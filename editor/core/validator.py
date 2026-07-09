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
    from core.project import Project, Actor

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
    _check_pal_bank_scene_consistency(ctx)
    _check_bg_pal_bank_scene_consistency(ctx)
    _check_bg_text_cbb_conflict(ctx)
    _check_direct_index_mode(ctx)

    # ── Validateurs plugins ──────────────────────────────────────────
    for fn in _VALIDATORS:
        try:
            fn(ctx)
        except Exception as exc:
            ctx.warn(None, f"Validateur '{fn.__name__}' a planté : {exc}")

    return ctx.warnings, ctx.errors


# ── Validateurs built-in ──────────────────────────────────────────────

def _check_scene(ctx: ValidationContext):
    if not ctx.scene:
        ctx.error(None, "Aucune scène active — impossible de compiler.")
        return
    if not ctx.actors:
        ctx.warn(None, "La scène ne contient aucun actor.")


def _check_actors(ctx: ValidationContext):
    from core.project import (SpriteComponent, CollisionBoxComponent,
                         ScriptComponent, component_type_name)

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

    ba_name = getattr(ctx.scene, "background_asset", "")
    if not ba_name:
        return

    ba = proj.get_background(ba_name)
    if not ba:
        ctx.warn(None, f"Background asset '{ba_name}' introuvable — la scène compilera sans background.")
        return

    for layer in ba.layers:
        if not layer.image:
            continue
        ap = proj.background_images_dir / layer.image
        if not ap.exists():
            ctx.warn(None, f"Background '{ba_name}' : image introuvable ({layer.image}) — layer ignoré.")


def _check_pal_bank_scene_consistency(ctx: ValidationContext):
    """La quantification des tuiles OBJ (asset_pipeline.py) et les pools de
    prefabs partagent une résolution globale par nom de sprite/prefab (1er
    rencontré gagne, cf. ROADMAP.md v0.2 — pas de variante par scène). Si
    deux scènes résolvent des palettes différentes pour le même sprite ou le
    même prefab poolé, un avertissement signale les scènes qui vont rendre
    avec les mauvaises couleurs plutôt que d'échouer silencieusement."""
    from core.project import AUTO_PAL_BANK

    p = ctx.project
    scenes = list(p.scenes)
    if len(scenes) < 2:
        return  # pas de conflit possible avec une seule scène

    def _resolve(entity, scene):
        pal_bank = getattr(entity, "pal_bank", 0)
        if pal_bank == AUTO_PAL_BANK:
            return None
        active = getattr(scene, "active_obj_palettes", [])
        if not (0 <= pal_bank < len(active)):
            return None
        return active[pal_bank] or None

    # Sprites référencés par des actors, potentiellement dans plusieurs scènes
    sprite_resolutions: dict[str, dict[str, str]] = {}
    for scene in scenes:
        for actor in scene.actors:
            if not actor.active:
                continue
            comp = actor.get_component("sprite")
            if not comp or not comp.active or not comp.sprite_name:
                continue
            pal_name = _resolve(actor, scene)
            if pal_name is not None:
                sprite_resolutions.setdefault(comp.sprite_name, {})[scene.name] = pal_name

    for sprite_name, by_scene in sprite_resolutions.items():
        if len(set(by_scene.values())) > 1:
            detail = ", ".join(f"{sn}→{pn}" for sn, pn in by_scene.items())
            ctx.warn(None,
                f"Sprite '{sprite_name}' résout vers des palettes différentes selon "
                f"la scène ({detail}) — une seule sera utilisée pour les tuiles au "
                f"build (1ère scène rencontrée), les autres scènes afficheront "
                f"potentiellement les mauvaises couleurs.")

    # Prefabs poolés — pas de scène propriétaire unique (spawn_X() appelable
    # depuis n'importe quel script Lua, non analysé statiquement).
    for pf in p.prefabs:
        if getattr(pf, "max_instances", 0) <= 0:
            continue
        by_scene = {}
        for scene in scenes:
            pal_name = _resolve(pf, scene)
            if pal_name is not None:
                by_scene[scene.name] = pal_name
        if len(set(by_scene.values())) > 1:
            detail = ", ".join(f"{sn}→{pn}" for sn, pn in by_scene.items())
            ctx.warn(None,
                f"Prefab '{pf.name}' (poolé) résout vers des palettes différentes "
                f"selon la scène ({detail}) — un prefab poolé est global (spawn_X() "
                f"utilisable depuis n'importe quelle scène), une seule couleur sera "
                f"correcte partout.")


def _check_bg_pal_bank_scene_consistency(ctx: ValidationContext):
    """Un BackgroundAsset peut être partagé par plusieurs scènes (comme un
    Prefab poolé) — chaque BackgroundLayer choisit sa propre banque
    (pal_bank, slot de scene.active_bg_palettes). Si layer.pal_bank résout
    vers des palettes différentes selon la scène qui utilise cet asset, un
    avertissement signale les scènes qui vont rendre avec les mauvaises
    couleurs (1ère scène rencontrée gagne au build, cf. pipeline.py —
    déduplication globale par (asset.name, bg_slot))."""
    p = ctx.project
    scenes = list(p.scenes)
    if len(scenes) < 2:
        return  # pas de conflit possible avec une seule scène

    def _resolve(layer, scene):
        active = getattr(scene, "active_bg_palettes", [])
        pal_bank = getattr(layer, "pal_bank", 0)
        if not (0 <= pal_bank < len(active)):
            return None
        return active[pal_bank] or None

    layer_resolutions: dict[tuple[str, int], dict[str, str]] = {}
    for scene in scenes:
        ba_name = getattr(scene, "background_asset", "")
        if not ba_name:
            continue
        ba = p.get_background(ba_name)
        if not ba:
            continue
        for layer in ba.layers:
            if not layer.image:
                continue
            pal_name = _resolve(layer, scene)
            if pal_name is not None:
                layer_resolutions.setdefault((ba_name, layer.bg_slot), {})[scene.name] = pal_name

    for (ba_name, bg_slot), by_scene in layer_resolutions.items():
        if len(set(by_scene.values())) > 1:
            detail = ", ".join(f"{sn}→{pn}" for sn, pn in by_scene.items())
            ctx.warn(None,
                f"Background '{ba_name}' BG{bg_slot} résout vers des palettes "
                f"différentes selon la scène ({detail}) — une seule sera utilisée "
                f"pour les tuiles au build (1ère scène rencontrée), les autres "
                f"scènes afficheront potentiellement les mauvaises couleurs.")


def _check_bg_text_cbb_conflict(ctx: ValidationContext):
    """tte_init_se(text_bg, BG_CBB(3)|BG_SBB(31), ...) (cf.
    main_gen._gen_scene_init) fait deux choses distinctes, chacune un
    problème séparé pour un layer BG :
    (1) il reprogramme le registre BGxCNT du slot `text_bg` APRÈS la boucle
    d'init des layers, quel que soit ce slot — un layer BG assigné à ce même
    bg_slot reste chargé en VRAM mais devient invisible (le registre pointe
    vers la police, plus vers ce layer) ;
    (2) il pointe TOUJOURS physiquement vers CBB3/SBB31 pour les données de
    police, quelle que soit la valeur de text_bg — depuis que chaque
    BackgroundLayer a son propre CBB (= bg_slot), un layer au bg_slot 3 voit
    ses propres tuiles écrasées par la police dès qu'un text_bg est actif
    dans la même scène, peu importe sa valeur. Avant ce changement, tous les
    layers partageaient CBB0, donc CBB3 restait toujours libre pour le texte
    — ce 2e cas est une conséquence directe du redesign palette BG par layer."""
    p = ctx.project
    for scene in p.scenes:
        text_bg = getattr(scene, "text_bg", -1)
        if text_bg not in (0, 1, 2, 3):
            continue
        ba_name = getattr(scene, "background_asset", "")
        ba = p.get_background(ba_name) if ba_name else None
        if not ba:
            continue
        for layer in ba.layers:
            if not layer.image:
                continue
            if layer.bg_slot == text_bg:
                ctx.warn(None,
                    f"Scène '{scene.name}' : text_bg={text_bg} reprogramme le "
                    f"registre BG{text_bg} après l'init du layer BG{text_bg} de "
                    f"'{ba_name}' — ce layer restera chargé en VRAM mais "
                    f"invisible (BG{text_bg} affichera le texte, pas le décor).")
            elif layer.bg_slot == 3:
                ctx.warn(None,
                    f"Scène '{scene.name}' : le layer BG3 de '{ba_name}' partage "
                    f"le character base block CBB3 avec la police TTE (toujours "
                    f"CBB3, quelle que soit la valeur de text_bg={text_bg}) — ses "
                    f"propres tuiles seront écrasées par les glyphes de police.")


def _check_direct_index_mode(ctx: ValidationContext):
    """match_mode="direct_index" (cf. core/color_utils.direct_index_to_bank)
    suppose un PNG en mode 'P' natif (palette + index par pixel), avec sa
    transparence conventionnellement à l'index 0 — indépendamment de
    l'éventuel tag de transparence natif du fichier (contrat fixe de ce
    mode, pas une détection automatique). Avertit sans bloquer si le PNG
    assigné n'est pas indexé, ou si sa transparence native déclarée diffère
    de l'index 0 (signe probable que le fichier n'a pas été préparé pour ce
    mode)."""
    from PIL import Image
    p = ctx.project

    def _check_png(path, label: str):
        try:
            img = Image.open(path)
        except Exception:
            return  # fichier illisible/manquant — déjà signalé ailleurs
        if img.mode != "P":
            ctx.warn(None,
                f"{label} : match_mode=\"indexation directe\" mais le PNG n'est "
                f"pas en mode indexé (mode {img.mode!r}) — aucune couleur ne "
                f"sera assignée pour ce mode.")
            return
        native = img.info.get("transparency")
        if isinstance(native, int) and native != 0:
            ctx.warn(None,
                f"{label} : le PNG a une transparence native à l'index {native}, "
                f"pas 0 — l'indexation directe traite toujours l'index 0 comme "
                f"transparent, ce fichier n'est probablement pas préparé pour "
                f"ce mode.")

    for scene in p.scenes:
        for actor in scene.actors:
            if getattr(actor, "match_mode", "nearest") != "direct_index":
                continue
            comp = actor.get_component("sprite")
            sprite = p.get_sprite(comp.sprite_name) if comp and comp.sprite_name else None
            if sprite and sprite.asset:
                ap = p.asset_abs(sprite.asset)
                if ap and ap.exists():
                    _check_png(ap, f"Sprite '{sprite.name}' (actor '{actor.name}')")

    for pf in p.prefabs:
        if getattr(pf, "match_mode", "nearest") != "direct_index":
            continue
        comp = pf.get_component("sprite")
        sprite = p.get_sprite(comp.sprite_name) if comp and comp.sprite_name else None
        if sprite and sprite.asset:
            ap = p.asset_abs(sprite.asset)
            if ap and ap.exists():
                _check_png(ap, f"Sprite '{sprite.name}' (prefab '{pf.name}')")

    for ba in p.backgrounds:
        for layer in ba.layers:
            if getattr(layer, "match_mode", "nearest") != "direct_index" or not layer.image:
                continue
            ap = p.background_images_dir / layer.image
            if ap.exists():
                _check_png(ap, f"Background '{ba.name}' BG{layer.bg_slot}")
