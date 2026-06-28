"""
editor/scripting/globals.py — Collecte les variables globales de tous les scripts
et génère globals.c + globals.h.

Une "variable globale" Lua = une variable écrite dans un script sans être
déclarée `local`. Elle est partagée entre tous les acteurs de la scène.
Ici on collecte depuis tous les LuaScript, on déduplique, et on émet
deux fichiers C :

  globals.h  →  extern int g_score;   (inclus par chaque actor_*.c)
  globals.c  →  int g_score = 0;      (une seule définition, linkée une fois)
"""

from __future__ import annotations
from pathlib import Path

from .parser import LuaScript


def collect_global_names(scripts: list[LuaScript]) -> list[str]:
    """
    Retourne la liste triée et dédupliquée de tous les noms globaux
    écrits dans l'ensemble des scripts.
    """
    names: set[str] = set()
    for s in scripts:
        names.update(s.globals_w)
    return sorted(names)


def generate_globals_h(names: list[str]) -> str:
    lines = [
        "/* globals.h — variables globales partagées entre les scripts acteur */",
        "/* Généré par GBA Editor — ne pas éditer */",
        "",
        "#ifndef GLOBALS_H",
        "#define GLOBALS_H",
        "",
    ]
    if names:
        for name in names:
            lines.append(f"extern int g_{name};")
    else:
        lines.append("/* aucune variable globale dans ce projet */")
    lines += ["", "#endif /* GLOBALS_H */", ""]
    return "\n".join(lines)


def generate_globals_c(names: list[str]) -> str:
    lines = [
        "/* globals.c — définitions des variables globales partagées */",
        "/* Généré par GBA Editor — ne pas éditer */",
        "",
        '#include "globals.h"',
        "",
    ]
    if names:
        for name in names:
            lines.append(f"int g_{name} = 0;")
    else:
        lines.append("/* aucune variable globale */")
    lines.append("")
    return "\n".join(lines)


def write_globals(src_dir: Path, scripts: list[LuaScript]) -> list[str]:
    """
    Collecte les globals, écrit globals.h et globals.c dans src_dir.
    Retourne la liste des noms globaux (utile pour CodegenContext).
    """
    names = collect_global_names(scripts)
    (src_dir / "globals.h").write_text(generate_globals_h(names), encoding="utf-8")
    (src_dir / "globals.c").write_text(generate_globals_c(names), encoding="utf-8")
    return names
