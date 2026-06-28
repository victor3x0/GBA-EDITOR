"""
editor/ui/icons.py — Registre centralisé des icônes.

Toutes les icônes de l'application passent par ce module.
Pour migrer vers un autre icon set (font bundlée, SVGs…),
seul ce fichier change — le reste du code appelle get() / fallback().

Backend actuel : qtawesome — Material Design Icons (mdi.*)
Fallback       : QIcon vide si qtawesome absent (pas de crash)
"""

from __future__ import annotations
from PyQt6.QtGui import QIcon

# ── Couleurs sémantiques ──────────────────────────────────────────
COLOR_DEFAULT = "#888888"
COLOR_ACTIVE  = "#4caf78"
COLOR_ACTOR   = "#7ecfff"
COLOR_PREFAB  = "#c792ea"
COLOR_SCRIPT  = "#ffcb6b"
COLOR_SCENE   = "#89ddff"
COLOR_FOLDER  = "#546e7a"

# ── Registre : nom logique → (qta_key, unicode_fallback) ──────────
# Pour swapper l'icon set : remplacer les qta_key par les nouveaux.
_REGISTRY: dict[str, tuple[str, str]] = {
    # Outils canvas
    "tool_select":           ("mdi.cursor-default",          "↖"),
    "tool_add":              ("mdi.plus-circle-outline",     "⊕"),
    "tool_erase":            ("mdi.eraser-variant",          "⌫"),
    "tool_collision_8":      ("mdi.border-outside",          "▪"),
    "tool_collision_16":     ("mdi.border-all",              "■"),
    "tool_collision_slope":      ("mdi.trending-up",             "◥"),
    "tool_collision_slope_inv":  ("mdi.trending-down",           "◣"),
    "tool_palette":          ("mdi.palette-outline",         "◐"),
    # Project panel — types d'objets
    "actor":                 ("mdi.account",                 "●"),
    "actor_empty":           ("mdi.account-outline",         "○"),
    "actor_script":          ("mdi.account-check",           "●"),
    "actor_empty_script":    ("mdi.account-check-outline",   "○"),
    "prefab":                ("mdi.puzzle-outline",          "◆"),
    "script_lua":            ("mdi.code-braces",             "λ"),
    "script_file":           ("mdi.file-outline",            "≡"),
    "scene":                 ("mdi.layers-outline",          "◈"),
    "folder":                ("mdi.folder-outline",          "▸"),
    # Canvas
    "camera":                ("mdi.camera-outline",          "[]"),
}

# ── Backend (chargé une seule fois) ──────────────────────────────
try:
    import qtawesome as _qta
    _BACKEND = "qtawesome"
except ImportError:
    _qta = None       # type: ignore
    _BACKEND = "none"


def get(name: str,
        color: str = COLOR_DEFAULT,
        color_active: str | None = None) -> QIcon:
    """
    Retourne un QIcon pour le nom logique donné.
    color_active : couleur quand le bouton est checked (QToolButton).
    """
    entry = _REGISTRY.get(name)
    if entry is None:
        return QIcon()
    qta_key, _ = entry
    if _qta is not None:
        try:
            kw: dict = {"color": color}
            if color_active:
                kw["color_active"] = color_active
            return _qta.icon(qta_key, **kw)
        except Exception:
            pass
    return QIcon()


def fallback(name: str) -> str:
    """Caractère Unicode de repli pour les widgets qui ne supportent pas QIcon."""
    entry = _REGISTRY.get(name)
    return entry[1] if entry else "?"
