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
    # NB : pas d'avertissement quand un même sprite/prefab/layer pointant un
    # SLOT (pal_bank 0-15) résout vers des palettes différentes selon la scène.
    # C'est un comportement PRÉVISIBLE et voulu (palette-swap par slot, comme
    # le recoloring de sprites sur GB/NES) : le slot est le même partout, seul
    # le contenu du slot varie par scène. À l'utilisateur d'aligner ses
    # palettes par index en amont.
    _check_bg_text_cbb_conflict(ctx)
    _check_pal_bank_reference(ctx)
    _check_palette_bank_overflow(ctx)

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
    from core.project import OWN_PAL_BANK
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

    # ── Layers BG (par scène utilisant le background) ────────────────
    for scene in p.scenes:
        active = getattr(scene, "active_bg_palettes", [])
        ba_name = getattr(scene, "background_asset", "")
        ba = p.get_background(ba_name) if ba_name else None
        if not ba:
            continue
        for layer in ba.layers:
            if not layer.image:
                continue
            pb = getattr(layer, "pal_bank", OWN_PAL_BANK)
            if pb == OWN_PAL_BANK:
                continue
            if _slot_missing(active, pb):
                ctx.warn(None,
                    f"Background '{ba.name}' BG{layer.bg_slot} (scène "
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
