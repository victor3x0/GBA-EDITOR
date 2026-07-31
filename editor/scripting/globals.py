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
        # ── Index ────────────────────────────────────────────────
        # Chaque variable garde SON type (un u8 coûte un octet) et reçoit en
        # plus un index stable. Les deux servent à deux choses distinctes : un
        # script écrit `g_score` et paie le prix d'un accès direct ; ce qui ne
        # connaît la variable que par une DONNÉE (valeur interpolée dans un
        # texte) passe par l'index, sans jamais avoir vu son nom.
        lines += ["", "/* Index — l'accès quand le nom n'est pas connu à l'écriture. */"]
        for i, g in enumerate(globals_):
            lines.append(f"#define GLOBAL_{g.name.upper()} {i}")
        lines.append(f"#define GLOBAL_COUNT {len(globals_)}")
    else:
        lines.append("/* aucune variable globale déclarée dans ce projet */")
        lines += ["", "#define GLOBAL_COUNT 0"]
    # Toujours déclarés, même sans variable : le moteur les appelle pour les
    # valeurs interpolées, et une déclaration manquante ne se verrait qu'à
    # l'édition de liens.
    lines += [
        "",
        "/* Lecture/écriture PAR INDEX. Un switch et non une table de pointeurs :",
        "   les variables n'ont pas toutes le même type, donc aucun tableau ne",
        "   peut les contenir sans mentir sur l'une d'elles. Le compilateur, lui,",
        "   sait convertir chaque cas. */",
        "extern int  global_read (int i);",
        "extern void global_write(int i, int v);",
    ]
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

    lines += ["", "int global_read(int i) {", "    switch (i) {"]
    for i, g in enumerate(globals_):
        lines.append(f"    case {i}: return (int)g_{g.name};")
    lines += ["    default: return 0;", "    }", "}", ""]
    lines += ["void global_write(int i, int v) {", "    switch (i) {"]
    for i, g in enumerate(globals_):
        c_type = _C_TYPES.get(g.type, "int")
        lines.append(f"    case {i}: g_{g.name} = ({c_type})v; break;")
    lines += ["    default: (void)v; break;", "    }", "}"]
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
