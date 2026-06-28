"""
editor/scripting/globals.py — Génère globals.c + globals.h depuis la liste
des GlobalVar déclarées explicitement dans le projet.

Plus de détection automatique depuis les scripts : les variables globales
sont une ressource explicite du projet (project.globals).
"""

from __future__ import annotations
from pathlib import Path


_C_TYPES = {
    "int":  "int",
    "bool": "bool",
    "u8":   "u8",
    "u16":  "u16",
    "s8":   "s8",
    "s16":  "s16",
}


def generate_globals_h(globals_) -> str:
    """globals_ : list[GlobalVar] (duck-typed: .name, .type)"""
    lines = [
        "/* globals.h — variables globales partagées entre les scripts acteur */",
        "/* Généré par GBA Editor — ne pas éditer */",
        "",
        "#ifndef GLOBALS_H",
        "#define GLOBALS_H",
        "",
    ]
    if globals_:
        for g in globals_:
            c_type = _C_TYPES.get(g.type, "int")
            lines.append(f"extern {c_type} g_{g.name};")
    else:
        lines.append("/* aucune variable globale déclarée dans ce projet */")
    lines += ["", "#endif /* GLOBALS_H */", ""]
    return "\n".join(lines)


def generate_globals_c(globals_) -> str:
    lines = [
        "/* globals.c — définitions des variables globales partagées */",
        "/* Généré par GBA Editor — ne pas éditer */",
        "",
        '#include "globals.h"',
        "",
    ]
    if globals_:
        for g in globals_:
            c_type = _C_TYPES.get(g.type, "int")
            lines.append(f"{c_type} g_{g.name} = {int(g.default)};")
    else:
        lines.append("/* aucune variable globale */")
    lines.append("")
    return "\n".join(lines)


def write_globals(src_dir: Path, globals_) -> list[str]:
    """
    Écrit globals.h et globals.c dans src_dir depuis la liste de GlobalVar.
    Retourne la liste des noms (utile pour CodegenContext).
    """
    (src_dir / "globals.h").write_text(generate_globals_h(globals_), encoding="utf-8")
    (src_dir / "globals.c").write_text(generate_globals_c(globals_), encoding="utf-8")
    return [g.name for g in globals_]
