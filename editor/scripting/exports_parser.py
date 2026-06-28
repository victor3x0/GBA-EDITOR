"""
Parse la table `exports` d'un script Lua actor.

Convention dans le .lua :

    exports = {
        speed   = { type = "int",    default = 5,        label = "Speed",     min = 0, max = 20 },
        name    = { type = "string", default = "Hero",   label = "Name" },
        active  = { type = "bool",   default = true,     label = "Active" },
        gravity = { type = "float",  default = 9.8,      label = "Gravity",   min = 0.0, max = 100.0 },
        pos     = { type = "vec2",   default = {0, 0},   label = "Position" },
        bounds  = { type = "rect",   default = {0,0,16,16}, label = "Bounds" },
        dir     = { type = "enum",   default = "LEFT",   label = "Direction", values = {"LEFT","RIGHT","UP","DOWN"} },
        sfx     = { type = "sfx_ref",   default = "",   label = "Sound" },
        next    = { type = "scene_ref", default = "",   label = "Next Scene" },
        target  = { type = "actor_ref", default = "",   label = "Target" },
    }

Retourne une liste ordonnée de dicts :
    { name, type, default, label, min, max, values }
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any


# ── Types reconnus ─────────────────────────────────────────────────

KNOWN_TYPES = {
    "int", "float", "string", "bool",
    "vec2", "rect",
    "enum",
    "actor_ref", "scene_ref", "sfx_ref",
}


def parse_exports(lua_path: Path) -> list[dict]:
    """Lit le fichier .lua et retourne les variables exportées."""
    if not lua_path or not lua_path.exists():
        return []
    text = lua_path.read_text(encoding="utf-8", errors="ignore")
    return _parse_exports_table(text)


# ── Parser interne ─────────────────────────────────────────────────

def _parse_exports_table(text: str) -> list[dict]:
    m = re.search(r'\bexports\s*=\s*\{', text)
    if not m:
        return []

    # Extraire le bloc {...} de niveau 0
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    block = text[start : i - 1]

    return [v for v in (_parse_entry(e) for e in _split_entries(block)) if v]


def _split_entries(block: str) -> list[str]:
    """Découpe le bloc en entrées de niveau 0 (séparées par ',')."""
    entries, current, depth = [], [], 0
    for ch in block:
        if ch == '{':
            depth += 1
            current.append(ch)
        elif ch == '}':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            s = ''.join(current).strip()
            if s:
                entries.append(s)
            current = []
        else:
            current.append(ch)
    s = ''.join(current).strip()
    if s:
        entries.append(s)
    return entries


def _parse_entry(entry: str) -> dict | None:
    """Parse une entrée   key = { type=..., default=..., ... }"""
    m = re.match(r'^(\w+)\s*=\s*\{(.+)\}$', entry, re.DOTALL)
    if not m:
        return None

    name  = m.group(1)
    inner = m.group(2)

    var: dict = {
        "name":    name,
        "type":    "string",
        "default": "",
        "label":   name,
        "min":     None,
        "max":     None,
        "values":  [],
    }

    # type
    t = re.search(r'\btype\s*=\s*"(\w+)"', inner)
    if t and t.group(1) in KNOWN_TYPES:
        var["type"] = t.group(1)

    # label
    lb = re.search(r'\blabel\s*=\s*"([^"]*)"', inner)
    if lb:
        var["label"] = lb.group(1)

    # default — tout ce qui suit jusqu'à la prochaine clé connue ou fin
    df = re.search(r'\bdefault\s*=\s*((?:\{[^}]*\}|"[^"]*"|[^,]+))', inner)
    if df:
        var["default"] = _parse_value(df.group(1).strip(), var["type"])

    # min / max
    mn = re.search(r'\bmin\s*=\s*(-?[\d.]+)', inner)
    if mn:
        raw = mn.group(1)
        var["min"] = float(raw) if '.' in raw else int(raw)

    mx = re.search(r'\bmax\s*=\s*(-?[\d.]+)', inner)
    if mx:
        raw = mx.group(1)
        var["max"] = float(raw) if '.' in raw else int(raw)

    # values (enum)
    vl = re.search(r'\bvalues\s*=\s*\{([^}]*)\}', inner)
    if vl:
        var["values"] = [v.strip().strip('"\'')
                         for v in vl.group(1).split(',') if v.strip()]

    return var


def _parse_value(raw: str, typ: str) -> Any:
    raw = raw.strip().rstrip(',').strip()

    if typ == "bool":
        return raw.lower() == "true"

    if typ == "int":
        try:    return int(float(raw))
        except: return 0

    if typ == "float":
        try:    return float(raw)
        except: return 0.0

    if typ == "vec2":
        nums = re.findall(r'-?[\d.]+', raw)
        return [float(nums[0]), float(nums[1])] if len(nums) >= 2 else [0.0, 0.0]

    if typ == "rect":
        nums = re.findall(r'-?[\d.]+', raw)
        if len(nums) >= 4:
            return [float(n) for n in nums[:4]]
        return [0.0, 0.0, 16.0, 16.0]

    # string, enum, *_ref
    return raw.strip('"\'')
