"""
editor/ui/icons.py — Registre centralisé des icônes.

Toutes les icônes de l'application passent par ce module.
Pour migrer vers un autre icon set (font bundlée, SVGs…),
seul ce fichier change — le reste du code appelle get() / fallback().

Backend actuel : qtawesome — Material Design Icons (mdi.*)
Fallback       : QIcon vide si qtawesome absent (pas de crash)
"""

from __future__ import annotations
import tempfile
from pathlib import Path
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

# ── Couleurs par type d'asset — 4 FAMILLES (voir project_theme_gba_redesign)
# Une couleur par famille ; l'identité intra-famille passe par la FORME de
# l'icône (account / puzzle / image…), pas par la teinte. Bande chaude pour
# Entités/Monde/Logique, teal pour l'Audio — toutes distinctes du périwinkle
# chrome (C.ACCENT) et du vert power-LED (C.POWER).
_FAM_ENTITY = "#f75c3c"   # Entités : actor, prefab, sprite  (rouge vermillon)
_FAM_WORLD  = "#f5a623"   # Monde   : scene, camera, background  (ambre-orange)
_FAM_LOGIC  = "#ec4a9a"   # Logique : script  (magenta)
_FAM_AUDIO  = "#15c9b2"   # Audio   : sfx, music  (teal vif)
_FAM_UI     = "#4f8ff7"   # Interface : layout, conteneur, texte, zone  (bleu franc)

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
# Interface — mise en page UI et ses trois types d'éléments. UNE couleur pour
# la famille ; zone / conteneur / texte se distinguent par la FORME de l'icône,
# comme partout ailleurs (règle « forme, pas teinte »).
COLOR_UI        = _FAM_UI
COLOR_UI_LAYOUT = _FAM_UI
COLOR_UI_PANEL  = _FAM_UI
COLOR_UI_TEXT   = _FAM_UI
COLOR_UI_REGION = _FAM_UI

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
    # Zone de texte : un rectangle qui contient du texte — l'outil délimite une
    # surface, il ne saisit pas de texte (celui-ci vient de la table).
    "tool_text_region":      ("mdi.format-text-variant-outline", "⌸"),
    # Interface — types d'éléments d'une mise en page (arbre, toolbar, canvas).
    # Un type = une FORME : la couleur est celle de la famille (COLOR_UI).
    "ui_layout":             ("mdi.view-dashboard-outline",  "⊞"),
    "ui_panel":              ("mdi.card-outline",            "▭"),
    "ui_text":               ("mdi.format-text",             "T"),
    # Image : le pictogramme d'image, pas celui de sprite — c'est un ÉLÉMENT
    # d'interface qui affiche un sprite, pas le sprite lui-même (qui garde son
    # icône et sa famille de couleur dans le Project Viewer).
    "ui_image":              ("mdi.image-outline",           "▣"),
    "tool_inpaint_brush":         ("mdi.brush",                   "🖌"),
    "tool_inpaint_rect":          ("mdi.select-drag",             "▭"),
    "tool_fill":                  ("mdi.format-color-fill",       "🪣"),
    # Rôle d'un layer dans le mélange de couleurs — la FORME dit le rôle :
    # hors du mélange, au-dessus (ce qui est mélangé), en dessous (ce avec quoi).
    "blend_off":             ("mdi.circle-outline",          "○"),
    "blend_top":             ("mdi.arrow-up-bold-circle-outline",   "▲"),
    "blend_bottom":          ("mdi.arrow-down-bold-circle-outline", "▼"),
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
    "background":            ("mdi.image-multiple-outline",  "▥"),
    "palette":               ("mdi.palette-outline",         "◐"),
    "font":                  ("mdi.format-font",             "A"),
    "anim_state":            ("mdi.play-box-outline",        "▶"),
    "sfx":                   ("mdi.volume-high",             "♪"),
    "music":                 ("mdi.music-note",              "♫"),
    "data_table":            ("mdi.table",                   "▦"),
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
    # Text Editor — couleurs-clés d'une planche de police
    "eyedropper":            ("mdi.eyedropper",              "⚲"),
    "clear":                 ("mdi.close",                   "✕"),
    # Text Editor — barre de balisage (une par balise de core.text_markup.TAGS,
    # plus le marqueur de valeur ; « mk_ » comme markup)
    "mk_speed":              ("mdi.speedometer",             "»"),
    "mk_pause":              ("mdi.timer-sand",              "⏸"),
    "mk_icon":               ("mdi.sticker-emoji",           "☺"),
    "mk_wave":               ("mdi.waves",                   "∿"),
    "mk_shake":              ("mdi.vibrate",                 "⚡"),
    "mk_color":              ("mdi.palette-outline",         "◐"),
    "mk_value":              ("mdi.variable",                "$"),
    "mk_tag":                ("mdi.tag-outline",             "⌗"),
    # Text Editor — clé d'un texte : accrochée au rangement ou nommée à la main
    "key_auto":              ("mdi.link-variant",            "⚯"),
    "key_manual":            ("mdi.link-variant-off",        "⚮"),
    "copy":                  ("mdi.content-copy",            "⧉"),
    "copied":                ("mdi.check",                   "✓"),
    # Chrome des widgets — consommées par les QSS via qss_image()
    "spin_up":               ("mdi.menu-up",                 "▲"),
    "spin_down":             ("mdi.menu-down",               "▼"),
    # Chevrons de repli/dépli des arborescences (QTreeWidget::branch) — même
    # rôle que le ▾/▸ de FinderSection, matérialisé en PNG pour la QSS.
    "tree_closed":           ("mdi.chevron-right",           "▸"),
    "tree_open":             ("mdi.chevron-down",            "▾"),
    # Data Editor — bandeau TABLE : deux actions "+" distinctes côte à côte,
    # la FORME dit ce qui est ajouté (ligne vs colonne), pas juste "+".
    "add_row":                ("mdi.table-row-plus-after",    "+▭"),
    "add_column":             ("mdi.table-column-plus-after", "+▯"),
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


# ── Icônes dessinées dans une vue zoomable ───────────────────────
# Un pixmap rendu une fois à N px devient flou (ou crénelé) dès que la vue
# l'agrandit. Les items de canvas passent donc par ici : ils redemandent le
# glyphe à la résolution ÉCRAN effective (zoom de la vue × devicePixelRatio)
# et le dessinent dans un rect de `size` unités de scène.

_SCALE_STEP = 0.5     # quantification du facteur — borne le nombre d'entrées
_SCALE_MAX = 16.0     # au-delà, le glyphe est déjà largement sur-échantillonné
_scaled_cache: dict[tuple[str, str, int, float], QPixmap] = {}


def scaled_pixmap(name: str,
                  color: str = COLOR_DEFAULT,
                  size: int = 16,
                  scale: float = 1.0) -> QPixmap:
    """
    Pixmap de l'icône rendue à `size × scale` pixels réels, mise en cache.
    L'appelant dessine dans un rect de `size` unités (rect cible + rect source
    complet) : le résultat est net à tout niveau de zoom.
    """
    q = min(max(round(scale / _SCALE_STEP) * _SCALE_STEP, _SCALE_STEP), _SCALE_MAX)
    key = (name, color, size, q)
    px = _scaled_cache.get(key)
    if px is None:
        n = max(1, int(round(size * q)))
        px = get(name, color).pixmap(QSize(n, n))
        _scaled_cache[key] = px
    return px


def fallback(name: str) -> str:
    """Caractère Unicode de repli pour les widgets qui ne supportent pas QIcon."""
    entry = _REGISTRY.get(name)
    return entry[1] if entry else "?"


# ── Icônes pour les QSS ───────────────────────────────────────────
# `image: url(...)` ne sait lire qu'un fichier ou une ressource Qt : pas de
# police d'icônes, pas de data-URI. On matérialise donc l'icône en PNG dans
# un cache disque. Le CHEMIN est déterministe (clé + couleur + taille), donc
# calculable à l'import de theme.py — alors que le RENDU exige une
# QApplication vivante et n'arrive qu'ensuite (ensure_qss_assets).

_CACHE_DIR = Path(tempfile.gettempdir()) / "gba_editor_icons"
_pending: dict[Path, tuple[str, str, int, float]] = {}


def _render(path: Path) -> None:
    """Écrit le PNG si possible ; silencieux tant que Qt n'est pas prêt."""
    if _qta is None or QApplication.instance() is None or path.exists():
        return
    qta_key, color, size, scale = _pending[path]
    try:
        icon = _qta.icon(qta_key, color=color, scale_factor=scale)
        path.parent.mkdir(parents=True, exist_ok=True)
        icon.pixmap(size, size).save(str(path), "PNG")
    except Exception:
        pass


def qss_image(name: str, color: str = COLOR_DEFAULT,
              size: int = 16, scale: float = 1.0) -> str:
    """
    Chemin POSIX (QSS n'aime pas les `\\`) d'un PNG rendu depuis l'icon set.
    `scale` grossit le glyphe dans sa boîte — les icônes MDI laissent une
    marge généreuse, trop discrète pour du petit chrome de widget.
    Retourne "" si l'icône est inconnue ou le backend absent : l'appelant
    omet alors la règle `image:` au lieu de pointer un fichier fantôme.
    """
    entry = _REGISTRY.get(name)
    if entry is None or _qta is None:
        return ""
    qta_key = entry[0]
    slug = f"{qta_key.replace('.', '_')}_{color.lstrip('#')}_{size}_{scale:g}"
    path = _CACHE_DIR / f"{slug}.png"
    _pending[path] = (qta_key, color, size, scale)
    _render(path)
    return path.as_posix()


def ensure_qss_assets() -> None:
    """
    Rend les PNG demandés par les QSS. À appeler une fois après la création
    de la QApplication et avant `setStyleSheet`.
    """
    for path in list(_pending):
        _render(path)
