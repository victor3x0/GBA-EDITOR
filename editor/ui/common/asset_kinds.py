"""
ui/common/asset_kinds.py — LE catalogue des familles d'assets.

Un seul endroit qui dit, pour chaque famille : où elle vit, comment on la
renomme, comment on la supprime, comment on en crée une. Les écrans n'en
choisissent que les familles qui les concernent :

    AssetFinder("Data finder",    [DATA_TABLES])
    AssetFinder("Project viewer", [SCENES, PREFABS, SCRIPTS])
    AssetFinder("Sound finder",   [SFX, MUSIC])

Avant ce fichier, chaque écran réécrivait ces quatre réponses pour sa propre
famille — d'où huit panneaux qui divergeaient. Cf. docs/asset-finder.md.

Les renommages passent TOUS par `Project.rename_*` et jamais par le store :
seul le projet réécrit aussi ce qui cite l'asset par son nom (les scènes, les
prefabs, les scripts Lua). Renommer dans le store laisserait des références
pendantes, silencieusement.
"""
from __future__ import annotations

from pathlib import Path

from ui.common.icons import get as _ico, COLOR_DEFAULT
from ui.common.theme import QSS
from ui.common.asset_finder import AssetKind, store_nodes, dir_nodes, resource_dir

from core.models.resource import (
    MIME_ANIMATED_BG, MIME_MUSIC, MIME_PREFAB_TEMPLATE, MIME_SCRIPT,
)
from core.history import (
    get_history, DeleteResourceCmd, DeleteFileCmd, RenameFileCmd,
)


# ──────────────────────────────────────────────────────────────────
#  Plomberie commune
# ──────────────────────────────────────────────────────────────────

def _renamer(method: str):
    """Adapte un `Project.rename_*` au contrat `AssetKind.rename`.

    Les `rename_*` ne rendent pas tous la même chose (rien, un booléen, le nom
    appliqué) ; ce qui est vrai dans tous les cas, c'est que `obj.name` porte le
    nom retenu APRÈS l'appel — y compris quand le projet a dédupliqué ou refusé."""
    def rename(project, obj, new_name: str) -> str:
        getattr(project, method)(obj, new_name)
        return obj.name
    return rename


def _store_deleter(attr: str):
    """Bâtit la suppression annulable d'un asset d'un `ResourceStore` (Ctrl+Z).

    Rend la commande SANS la pousser : le finder la pousse seule, ou groupe tout
    un lot dans un seul `MacroCmd` pour un unique Ctrl+Z (cf. AssetKind.delete)."""
    def delete(project, obj):
        return DeleteResourceCmd(getattr(project, attr), obj)
    return delete


def _unique(store, base: str) -> str:
    """Premier nom libre de la forme `base`, `base 2`, `base 3`…"""
    base = (base or "").strip() or "Asset"
    if store.get(base) is None:
        return base
    i = 2
    while store.get(f"{base} {i}") is not None:
        i += 1
    return f"{base} {i}"


def _menu_choice(entries):
    """Petit menu au curseur — `entries` = [(libellé, action) | (None, None)].

    Un menu plutôt qu'une enfilade de modales : le « + » d'une famille qui a
    plusieurs façons de naître (créer en 16 ou 256 couleurs, importer) pose la
    question en un clic, et l'asset naît nommé, renommable en place."""
    from PyQt6.QtWidgets import QMenu
    from PyQt6.QtGui import QCursor
    menu = QMenu()
    menu.setStyleSheet(QSS.menu)
    chosen = {}
    for label, fn in entries:
        if label is None:
            menu.addSeparator()
            continue
        act = menu.addAction(label)
        chosen[act] = fn
    act = menu.exec(QCursor.pos())
    fn = chosen.get(act)
    return fn() if fn else None


# ──────────────────────────────────────────────────────────────────
#  Monde — scènes, prefabs
# ──────────────────────────────────────────────────────────────────

SCENES = AssetKind(
    label         = "Scenes",
    icon          = "scene",
    nodes         = store_nodes("scenes"),
    rename        = _renamer("rename_scene"),
    delete        = _store_deleter("scenes"),
    delete_prompt = lambda s: f"Delete scene “{s.name}”?\n(Ctrl+Z to undo)",
    add_tooltip   = "New scene",     # l'écran crée (scène active à reporter)
    dir_of        = resource_dir("scenes_dir"),
)

PREFABS = AssetKind(
    label         = "Prefabs",
    icon          = "prefab",
    nodes         = store_nodes("prefabs"),
    rename        = _renamer("rename_prefab"),
    delete        = _store_deleter("prefabs"),
    delete_prompt = lambda p: f"Delete prefab “{p.name}”?\n(Ctrl+Z to undo)",
    add_tooltip   = "New prefab",
    # Glisser un prefab sur le canvas l'y instancie.
    mime          = (MIME_PREFAB_TEMPLATE, lambda project, pf: pf.name),
    dir_of        = resource_dir("prefab_dir"),
)


# ──────────────────────────────────────────────────────────────────
#  Logique — scripts (seule famille dont le DISQUE est la vérité)
# ──────────────────────────────────────────────────────────────────

def _script_icon(path: Path):
    return _ico("script_lua" if path.suffix == ".lua" else "script_file",
                COLOR_DEFAULT)


def _rename_script(project, path: Path, new_text: str) -> str:
    """Un script est un fichier : le renommer, c'est renommer le fichier.

    L'arbre affiche le nom COMPLET (avec extension) et c'est ce texte qu'on
    édite ; si l'utilisateur n'a pas tapé une extension de script reconnue, on
    conserve celle d'origine plutôt que de la perdre sans un mot."""
    new_path = (path.parent / new_text if Path(new_text).suffix in (".lua", ".c")
                else path.parent / f"{new_text}{path.suffix}")
    if new_path == path:
        return path.name
    get_history().push(RenameFileCmd(path, new_path))
    return new_path.name


SCRIPTS = AssetKind(
    label         = "Scripts",
    icon          = "script_lua",
    icon_of       = _script_icon,
    nodes         = dir_nodes("scripts_dir", (".lua", ".c")),
    rename        = _rename_script,
    delete        = lambda project, path: DeleteFileCmd(path),
    delete_prompt = lambda p: f"Delete “{p.name}”?\n(Ctrl+Z to undo)",
    add_tooltip   = "New script",
    # Glisser un script sur un actor lui attache un ScriptComponent. La charge
    # utile est le chemin RELATIF au projet : un chemin absolu ne survivrait pas
    # au déplacement du dossier de projet.
    mime          = (MIME_SCRIPT,
                     lambda project, path: (project.asset_rel(path)
                                            if project else path)),
    dir_of        = resource_dir("scripts_dir"),
)


# ──────────────────────────────────────────────────────────────────
#  Entités — sprites
# ──────────────────────────────────────────────────────────────────

def _sprite_group(sprite) -> str:
    """Dossier DEVINÉ d'un sprite : ce qui précède le premier « _ ». Un préfixe
    trop court ne dit rien (« a_ », « ui_ ») et ne fait pas un rangement."""
    head, sep, _rest = sprite.name.partition("_")
    return head if sep and len(head) > 2 else ""


def _rename_sprite(project, sprite, new_name: str) -> str:
    """Par le DISPATCHER et non par le projet : renommer un sprite déplace aussi
    le PNG et son sidecar, ce qui doit se faire surveillant suspendu, et les
    canvas de scène ouverts doivent être prévenus."""
    from core.command_dispatcher import get_dispatcher
    if project.sprites.get(new_name) is not None:
        return sprite.name              # nom déjà pris : refus silencieux
    get_dispatcher().rename_sprite(sprite, new_name)
    return sprite.name


SPRITES = AssetKind(
    label         = "Sprites",
    icon          = "sprite",
    nodes         = store_nodes("sprites", group_by=_sprite_group,
                                collapse_singletons=True),
    rename        = _rename_sprite,
    delete        = _store_deleter("sprites"),
    delete_prompt = lambda s: f"Delete sprite “{s.name}”?\n(Ctrl+Z to undo)",
    # Un sprite se crée uniquement par import d'une image : l'écran ouvre le
    # dialogue (il lui faut un parent), le finder ne fait que le demander.
    add_tooltip   = "Import a sprite sheet",
    dir_of        = resource_dir("sprites_dir"),
)


# ──────────────────────────────────────────────────────────────────
#  Décor — fonds
# ──────────────────────────────────────────────────────────────────

BACKGROUNDS = AssetKind(
    label  = "Backgrounds",
    icon   = "background",
    # `kind` (scene / ui / animated) est le seul axe de rangement que le modèle
    # porte déjà : on s'en sert comme dossier tant que l'utilisateur n'a pas les
    # siens (cf. docs/asset-finder.md).
    nodes  = store_nodes("backgrounds", group_by=lambda bg: getattr(bg, "kind", "")),
    rename = _renamer("rename_background"),
    delete = _store_deleter("backgrounds"),
    dir_of = resource_dir("backgrounds_dir"),
)


def _background_of_kind(bg_kind: str, label: str, add_tooltip: str,
                        mime=None) -> AssetKind:
    """Une famille par `kind` de fond — le Background Editor donne à chacune sa
    propre section, parce que chacune a son propre import (« un PNG », « un
    cadre d'UI », « une planche d'animation ») : trois boutons, trois phrases,
    ce qu'une section unique ne saurait pas offrir.

    Ailleurs (Scene Manager), `BACKGROUNDS` ci-dessus montre les trois d'un coup,
    rangées par `kind`. Même store, deux façons de le présenter."""
    return AssetKind(
        label       = label,
        icon        = "background",
        nodes       = store_nodes("backgrounds",
                                  where=lambda bg, k=bg_kind: getattr(bg, "kind", "") == k),
        rename      = _renamer("rename_background"),
        delete      = _store_deleter("backgrounds"),
        add_tooltip = add_tooltip,      # sans `add` : l'écran ouvre l'import
        mime        = mime,
        dir_of      = resource_dir("backgrounds_dir"),
    )


BACKGROUNDS_SCENE = _background_of_kind("scene", "Backgrounds", "Import a PNG")
BACKGROUNDS_UI    = _background_of_kind("ui", "UI backgrounds",
                                        "Import a UI frame or panel PNG")
# Un fond animé se POSE sur le canvas d'un fond hôte : c'est la seule famille de
# fonds qui se glisse (cf. project_v04_decor_animation).
BACKGROUNDS_ANIM  = _background_of_kind("animated", "Animated",
                                        "Import an animation sheet PNG",
                                        mime=(MIME_ANIMATED_BG,
                                              lambda project, bg: bg.name))


# ──────────────────────────────────────────────────────────────────
#  Texte — polices
# ──────────────────────────────────────────────────────────────────

FONTS = AssetKind(
    label      = "Fonts",
    icon       = "font",
    nodes      = store_nodes("fonts"),
    rename     = _renamer("rename_font"),
    delete     = _store_deleter("fonts"),
    dir_of     = resource_dir("fonts_dir"),
    # Pas de « + » : une police s'obtient en déposant un PNG ou un .fnt dans
    # assets/fonts/ (asset_encoding.sync_font_file), comme sprites et fonds.
    empty_text = "No font.\n\nDrop a PNG or a .fnt\ninto assets/fonts/",
    tooltip_of = lambda f: (
        f"{f.name}\n{len(f.glyphs)} glyphs · {f.cell_w}×{f.cell_h} px\n"
        f"{f.tile_count()} tiles in the UI layer's charblock\n"
        f"source: {f.source_format}"
    ),
)


# ──────────────────────────────────────────────────────────────────
#  Couleurs — palettes
# ──────────────────────────────────────────────────────────────────

def _palette_icon(bank):
    from ui.common.palette_swatch import bank_icon
    return bank_icon(bank)


def _new_palette(project, size: int):
    from core.models.palette import PaletteBank
    from core.palette_presets import hsb_ramp_bgr555
    from core.history import AddResourceCmd
    bank = PaletteBank(name=_unique(project.palettes, "Palette"),
                       colors=hsb_ramp_bgr555(0, 0, steps=size), size=size)
    get_history().push(AddResourceCmd(project.palettes, bank))
    return bank


def _import_palette(project):
    """Crée une palette depuis un fichier (.gpl / .pal / liste hex) — nom = nom
    de fichier, taille déduite du nombre de couleurs."""
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from pathlib import Path as _P
    from core.models.palette import PaletteBank
    from core.models.gba_color import rgb888_to_bgr555
    from core.history import AddResourceCmd
    from ui.palette_editor.palette_file_io import parse_palette_file

    path, _ = QFileDialog.getOpenFileName(
        None, "Import a palette", "", "Palettes (*.gpl *.pal *.txt *.hex);;All files (*)")
    if not path:
        return None
    try:
        colors = parse_palette_file(_P(path))
    except OSError as e:
        QMessageBox.warning(None, "Import", f"Unreadable file: {e}")
        return None
    if not colors:
        QMessageBox.warning(None, "Import", "No color recognized in this file.")
        return None
    size = 256 if len(colors) > 16 else 16
    bgr = [rgb888_to_bgr555(*c) for c in colors[:size]]
    bgr += [0] * (size - len(bgr))            # complète si le fichier est court
    bank = PaletteBank(name=_unique(project.palettes, _P(path).stem), colors=bgr, size=size)
    get_history().push(AddResourceCmd(project.palettes, bank))
    return bank


def _add_palette(project):
    """Le « + » propose la taille et l'import dans un seul menu, plutôt que
    d'enchaîner deux modales avant que la palette existe (cf. la règle « inline
    plutôt que dialogues ») : la banque naît nommée, et le finder ouvre aussitôt
    son renommage en place."""
    return _menu_choice([
        ("New 16-color palette (4bpp)",  lambda: _new_palette(project, 16)),
        ("New 256-color palette (8bpp)", lambda: _new_palette(project, 256)),
        (None, None),
        ("Import…",                      lambda: _import_palette(project)),
    ])


def _duplicate_palette(project, bank):
    """Partir d'une palette existante pour en dériver une variante, sans toucher
    à l'originale ni aux scènes qui la citent par nom. Annulable (Ctrl+Z)."""
    from core.models.palette import PaletteBank
    from core.history import AddResourceCmd
    copy = PaletteBank(name=_unique(project.palettes, f"{bank.name} copy"),
                       colors=list(bank.colors), size=bank.size)
    get_history().push(AddResourceCmd(project.palettes, copy))


PALETTES = AssetKind(
    label       = "Palettes",
    icon        = "palette",
    icon_of     = _palette_icon,
    nodes       = store_nodes("palettes"),
    suffix_of   = lambda bank: f"({bank.size})",
    rename      = _renamer("rename_palette"),
    delete      = _store_deleter("palettes"),
    delete_prompt = lambda b: f"Delete palette “{b.name}”?\n(Ctrl+Z to undo)",
    add         = _add_palette,
    add_tooltip = "Add a palette (create / import)",
    actions     = (("Duplicate", _duplicate_palette),),
    dir_of      = resource_dir("palettes_dir"),
)


# ──────────────────────────────────────────────────────────────────
#  Audio — sfx, musiques
# ──────────────────────────────────────────────────────────────────

def _add_sound(attr: str, cls_name: str, base: str):
    """Crée un SFX / une piste nommé d'office. Pas de modale qui réclame un nom
    avant que la chose existe : le finder ouvre le renommage en place ensuite."""
    def add(project):
        import core.models.audio as audio_models
        from core.history import AddResourceCmd
        store = getattr(project, attr)
        asset = getattr(audio_models, cls_name)(name=_unique(store, base))
        get_history().push(AddResourceCmd(store, asset))
        return asset
    return add


SFX = AssetKind(
    label         = "SFX",
    icon          = "sfx",
    nodes         = store_nodes("sfx"),
    rename        = _renamer("rename_sound"),
    delete        = _store_deleter("sfx"),
    delete_prompt = lambda a: f"Delete SFX “{a.name}”?\n(Ctrl+Z to undo)",
    add           = _add_sound("sfx", "Sfx", "SFX"),
    add_tooltip   = "Add an SFX",
    dir_of        = resource_dir("sfx_dir"),
)

MUSIC = AssetKind(
    label         = "Music",
    icon          = "music",
    nodes         = store_nodes("music"),
    # Glissable vers le graphe de la MusicBox : lâchée sur un nœud, elle en
    # devient la piste ; lâchée sur le vide, elle crée l'état qui la joue.
    mime          = (MIME_MUSIC, lambda _p, m: m.name),
    rename        = _renamer("rename_sound"),
    delete        = _store_deleter("music"),
    delete_prompt = lambda a: f"Delete track “{a.name}”?\n(Ctrl+Z to undo)",
    add           = _add_sound("music", "Music", "Track"),
    add_tooltip   = "Add a track",
    dir_of        = resource_dir("music_dir"),
)


# ──────────────────────────────────────────────────────────────────
#  Données — tables
# ──────────────────────────────────────────────────────────────────

def _add_data_table(project):
    """Crée une table d'UNE colonne et d'aucune ligne. Une colonne d'office
    plutôt qu'une table vide : une grille sans colonne n'a nulle part où poser
    une ligne."""
    from core.models.data_table import DataTable, DataColumn
    from core.history import AddResourceCmd

    base, name, i = "Table", "Table", 2
    while project.data_tables.get(name):
        name = f"{base}_{i}"
        i += 1
    table = DataTable(name=name, columns=[DataColumn(name="valeur", type="int")], rows=[])
    get_history().push(AddResourceCmd(project.data_tables, table))
    return table


def _rename_data_table(project, table, new_name: str) -> str:
    # Seul `rename_*` à rendre un booléen : le nom d'une table s'écrit comme du
    # code dans les scripts (`data.Objets`), donc il doit être un identifiant.
    # Un refus laisse `table.name` inchangé, ce que l'arbre réaffichera.
    project.rename_data_table(table, new_name)
    return table.name


DATA_TABLES = AssetKind(
    label         = "Tables",
    icon          = "data_table",
    nodes         = store_nodes("data_tables"),
    suffix_of     = lambda t: f"({len(t.rows)} × {len(t.columns)})",
    rename        = _rename_data_table,
    delete        = _store_deleter("data_tables"),
    delete_prompt = lambda t: f"Delete table “{t.name}”?\n(Ctrl+Z to undo)",
    add           = _add_data_table,
    add_tooltip   = "New table",
    dir_of        = resource_dir("data_tables_dir"),
)


ALL_KINDS = (
    SCENES, PREFABS, SCRIPTS, SPRITES, BACKGROUNDS,
    FONTS, PALETTES, SFX, MUSIC, DATA_TABLES,
)
