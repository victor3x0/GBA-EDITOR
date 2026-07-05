"""
scripting/script_templates.py — Génère le contenu initial d'un nouveau
script Lua selon son contexte (scène / actor / behavior / générique).

Point d'entrée unique utilisé par les endroits de l'UI qui créent un script
(SceneInspector, ScriptEditor du component, Script finder, Assets finder) —
avant, chacun réimplémentait son propre template de façon indépendante,
avec des résultats incohérents entre eux (ex: noms d'event en camelCase au
lieu de snake_case, jamais reconnus par KNOWN_EVENTS). L'écriture disque
reste du ressort de l'UI ; ce module ne produit que du texte.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ScriptTemplateContext:
    """kind: "scene" | "actor" | "behavior" | "empty" """
    kind: str = "empty"
    name: str = ""                 # nom du script (sans .lua)
    scene_name: str = ""           # pour kind="scene"
    actor_name: str = ""           # pour kind="actor"
    component_labels: list[str] = field(default_factory=list)
    has_sprite: bool = False
    has_sfx: bool = False
    # (tag, on_enter_callback_name, on_exit_callback_name)
    solid_tags: list[tuple[str, str, str]] = field(default_factory=list)
    trigger_tags: list[tuple[str, str, str]] = field(default_factory=list)


def generate_script_template(ctx: ScriptTemplateContext) -> str:
    if ctx.kind == "scene":
        return _generate_scene_template(ctx)
    if ctx.kind == "actor":
        return _generate_actor_template(ctx)
    if ctx.kind == "behavior":
        return _generate_behavior_template(ctx)
    return ""   # "empty" : fichier vide


def _generate_scene_template(ctx: ScriptTemplateContext) -> str:
    return (
        f"-- Script de scène : {ctx.scene_name}\n\n"
        "function on_start()\nend\n\n"
        "function on_update()\nend\n\n"
        "function on_late_update()\nend\n"
    )


def _generate_behavior_template(ctx: ScriptTemplateContext) -> str:
    return (
        f"-- Behavior : {ctx.name}\n"
        f"-- Module réutilisable. Usage : local M = require('behaviors/{ctx.name}')\n\n"
        "local M = {}\n\n"
        "function M.update(actor)\nend\n\n"
        "return M\n"
    )


def _generate_actor_template(ctx: ScriptTemplateContext) -> str:
    lines = [
        f"-- Actor script : {ctx.name}",
        f"-- Actor       : {ctx.actor_name or '?'}",
        f"-- Components  : {', '.join(ctx.component_labels) or 'aucun'}",
        "",
        "-- Déclare ici les variables configurables depuis l'éditeur :",
        "-- exports = {",
        "--     speed  = { type = \"int\",  default = 5,       label = \"Speed\", min = 0, max = 20 },",
        "--     name   = { type = \"string\", default = \"Hero\", label = \"Name\" },",
        "--     active = { type = \"bool\",   default = true,    label = \"Active\" },",
        "-- }",
        "",
        "function on_start()",
    ]
    if ctx.has_sprite: lines += ["    -- self:play_anim('Idle')"]
    lines += ["end", "", "function on_update()"]
    if ctx.has_sprite: lines += ["    -- self:play_anim('Run')"]
    if ctx.has_sfx:    lines += ["    -- self:play_sfx()"]
    lines += ["end", ""]

    for tag, enter, exit_ in ctx.solid_tags:
        note = f"  -- tag='{tag}'" if tag != "body" else ""
        lines += [f"function {enter}(other_id){note}",
                  "    -- local other = actors[other_id]", "end",
                  f"function {exit_}(other_id)", "end", ""]
    for tag, enter, exit_ in ctx.trigger_tags:
        note = f"  -- tag='{tag}'" if tag != "body" else ""
        lines += [f"function {enter}(other_id){note}",
                  "    -- local other = actors[other_id]", "end",
                  f"function {exit_}(other_id)", "end", ""]

    if not (ctx.has_sprite or ctx.solid_tags or ctx.trigger_tags or ctx.has_sfx):
        lines += ["-- Ajoute des components dans l'inspector pour débloquer l'API.", ""]
    return "\n".join(lines)
