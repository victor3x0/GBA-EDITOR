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
COLOR_SPRITE  = "#f78c6c"
COLOR_SFX     = "#c3e88d"
COLOR_MUSIC   = "#87d3c3"
# Script Editor — catégories du panneau latéral (pas de type d'objet dédié)
COLOR_EVENT    = "#4ec9b0"   # teal — event handlers (on_start, on_update...)
COLOR_BEHAVIOR = "#b48aff"   # violet — modules behavior (require())
COLOR_GLOBAL   = "#e5c07b"   # jaune — variables globales
COLOR_CONST    = "#e06c75"   # rouge corail — constantes (lecture seule)

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
    "sprite":                ("mdi.image-outline",           "▧"),
    "anim_state":            ("mdi.play-box-outline",        "▶"),
    "sfx":                   ("mdi.volume-high",             "♪"),
    "music":                 ("mdi.music-note",              "♫"),
    "asset_missing":         ("mdi.circle-outline",          "○"),
    # Canvas
    "camera":                ("mdi.camera-outline",          "[]"),
    # Sprite Editor — directions
    "dir_n":                 ("mdi.arrow-up",                "↑"),
    "dir_ne":                ("mdi.arrow-top-right",         "↗"),
    "dir_e":                 ("mdi.arrow-right",             "→"),
    "dir_se":                ("mdi.arrow-bottom-right",      "↘"),
    "dir_s":                 ("mdi.arrow-down",               "↓"),
    "dir_sw":                ("mdi.arrow-bottom-left",       "↙"),
    "dir_w":                 ("mdi.arrow-left",              "←"),
    "dir_nw":                ("mdi.arrow-top-left",          "↖"),
    "dir_omni":              ("mdi.arrow-all",               "⊙"),
    "mirror_h":              ("mdi.flip-horizontal",         "↔"),
    "mirror_v":              ("mdi.flip-vertical",           "↕"),
    # Sprite Editor — playback
    "playback_prev":         ("mdi.skip-previous",           "⏮"),
    "playback_play":         ("mdi.play",                    "▶"),
    "playback_next":         ("mdi.skip-next",               "⏭"),
    "playback_grid":         ("mdi.grid",                    "⊞"),
    "playback_contrast":     ("mdi.contrast-circle",         "◑"),
    # Script Editor — events (EVENT_REGISTRY)
    "ev_start":              ("mdi.play",                    "▶"),
    "ev_update":             ("mdi.autorenew",                "↺"),
    "ev_late_update":        ("mdi.replay",                  "↻"),
    "ev_collide":            ("mdi.hexagon-outline",         "⬡"),
    "ev_collision_enter":    ("mdi.login-variant",           "→"),
    "ev_tile_collide":       ("mdi.grid",                    "▦"),
    "ev_collision_exit":     ("mdi.logout-variant",          "←"),
    "ev_destroy":            ("mdi.trash-can-outline",       "✕"),
    # Script Editor — boutons GBA
    "btn_a":                 ("mdi.alpha-a-circle-outline",  "🅐"),
    "btn_b":                 ("mdi.alpha-b-circle-outline",  "🅑"),
    "btn_l":                 ("mdi.alpha-l-box-outline",     "L"),
    "btn_r":                 ("mdi.alpha-r-box-outline",     "R"),
    "btn_start":             ("mdi.keyboard-return",         "⏎"),
    "btn_select":            ("mdi.menu",                    "≡"),
    "behavior_stub":         ("mdi.function-variant",        "ƒ"),
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
