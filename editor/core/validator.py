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
