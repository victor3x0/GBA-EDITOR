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

# ── Couleurs par type d'asset — 4 FAMILLES (voir project_theme_gba_redesign)
# Une couleur par famille ; l'identité intra-famille passe par la FORME de
# l'icône (account / puzzle / image…), pas par la teinte. Bande chaude pour
# Entités/Monde/Logique, teal pour l'Audio — toutes distinctes du périwinkle
# chrome (C.ACCENT) et du vert power-LED (C.POWER).
_FAM_ENTITY = "#f75c3c"   # Entités : actor, prefab, sprite  (rouge vermillon)
_FAM_WORLD  = "#f5a623"   # Monde   : scene, camera, background  (ambre-orange)
_FAM_LOGIC  = "#ec4a9a"   # Logique : script  (magenta)
_FAM_AUDIO  = "#15c9b2"   # Audio   : sfx, music  (teal vif)

COLOR_DEFAULT = "#8a8aa0"   # neutre légèrement teinté indigo
COLOR_ACTIVE  = "#5be08b"   # = C.POWER — état actif / live
COLOR_FOLDER  = "#5a6b82"   # dossier — slate neutre

COLOR_ACTOR      = _FAM_ENTITY
COLOR_PREFAB     = _FAM_ENTITY
COLOR_SPRITE     = _FAM_ENTITY
COLOR_SCENE      = _FAM_WORLD
COLOR_BACKGROUND = _FAM_WORLD
COLOR_SCRIPT     = _FAM_LOGIC
COLOR_SFX        = _FAM_AUDIO
COLOR_MUSIC      = _FAM_AUDIO
# Script Editor — vocabulaire « code » (events / behaviors / globals / consts).
# Tout ce qui relève du code partage UNE couleur = la famille Logique
# (COLOR_SCRIPT, magenta) ; on distingue les catégories par la FORME de l'icône
# et le libellé, pas par la teinte. Les valeurs One-Dark d'origine (teal/violet/
# jaune/rouge) collisionnaient avec Audio / chrome / warning / danger.
COLOR_EVENT    = COLOR_SCRIPT
COLOR_BEHAVIOR = COLOR_SCRIPT
COLOR_GLOBAL   = COLOR_SCRIPT
COLOR_CONST    = COLOR_SCRIPT

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
    "tool_inpaint_brush":         ("mdi.brush",                   "🖌"),
    "tool_inpaint_rect":          ("mdi.select-drag",             "▭"),
    "tool_fill":                  ("mdi.format-color-fill",       "🪣"),
    "eye":                   ("mdi.eye-outline",             "◉"),
    "eye_off":               ("mdi.eye-off-outline",         "◎"),
    # Toggles d'affichage du canvas (toolbar Scene Manager)
    "zoom":                  ("mdi.magnify",                 "⚲"),
    "zoom_in":               ("mdi.magnify-plus-outline",    "⊕"),
    "zoom_out":              ("mdi.magnify-minus-outline",   "⊖"),
    "fit_page":              ("mdi.fit-to-page-outline",     "⊡"),
    "view_grid":             ("mdi.grid",                    "▦"),
    "view_grid_large":       ("mdi.grid-large",              "▤"),
    "view_snap":             ("mdi.magnet",                  "⇲"),
    "view_boxes":            ("mdi.account-box",             "▭"),
    "view_collision":        ("mdi.wall",                    "▨"),
    "warning":               ("mdi.alert",                   "⚠"),
    "scroll_h":              ("mdi.arrow-left-right-bold",   "↔"),
    "scroll_v":              ("mdi.arrow-up-down-bold",      "↕"),
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
