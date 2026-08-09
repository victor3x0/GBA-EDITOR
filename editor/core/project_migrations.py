"""Migrations et réconciliations exécutées à l'ouverture d'un projet, pour
absorber les anciens formats JSON (rétro-compatibilité) et rattraper les
fichiers déposés sur disque hors éditeur. Toutes ces fonctions sont appelées
uniquement depuis Project.load(), dans l'ordre — cf. project.py."""

import json
from pathlib import Path

from core.models.background import BackgroundLayer
from core.models.scene import Actor
from core.models.components import _components_from_list
from core.models.palette import PaletteBank
from core.asset_sync import sync_background_png, sync_sfx_file, sync_music_file, encode_background_asset


def migrate_on_load(project):
    """Migrations automatiques à l'ouverture d'un projet ancien."""
    # script paths : project/scripts/ → assets/scripts/ (scènes + prefabs)
    for f in list(project.scenes_dir.glob("*.json")) + list(project.prefab_dir.glob("*.json")):
        text = f.read_text(encoding="utf-8")
        migrated = text.replace("project/scripts/", "assets/scripts/")
        if migrated != text:
            f.write_text(migrated, encoding="utf-8")


def migrate_display_calls(project):
    """`display.print` / `display.clear` (libtonc TTE, retirés) → `text.*`.

    Appelée APRÈS load_texts : la migration crée des entrées de table, il faut
    donc que la table soit chargée et que les clés déjà prises soient connues.
    Seuls les appels à littéral pur bougent ; ceux qui formatent une valeur
    restent en place et le checker les signale (cf. api.REMOVED_API) — décider
    ce qui devient un libellé traduisible et ce qui devient un `text.draw_num`
    appartient à l'auteur.

    Rewrite de scripts VERSIONNÉS en git : on le signale, on ne le fait pas en
    silence. Renvoie un message ou None."""
    from scripting.refactor import migrate_display_in_project
    r = migrate_display_in_project(project)
    migrated, skipped = r["migrated"], r["skipped"]
    if not migrated and not skipped:
        return None
    if migrated:
        project.save_texts()
    parts = []
    if migrated:
        n = sum(migrated.values())
        parts.append(f"{n} appel(s) display.* migré(s) vers text.* dans "
                     f"{len(migrated)} script(s) : "
                     + ", ".join(sorted(p.name for p in migrated)))
    if skipped:
        n = sum(len(v) for v in skipped.values())
        parts.append(f"{n} appel(s) formaté(s) à reprendre à la main "
                     f"({', '.join(sorted(p.name for p in skipped))}) — "
                     f"text.draw pour le libellé, text.draw_num pour la valeur")
    return " ; ".join(parts)


def migrate_text_arg_order(project):
    """Famille `text.*` passée à « position/conteneur → contenu » (2026-07-27).

    Appelée APRÈS load_texts ET le chargement des ui_layouts : la détection
    interroge les deux namespaces pour départager `draw_in("a", "b")`, dont les
    deux arguments sont des chaînes dans l'ancien comme dans le nouvel ordre.

    Pourquoi une migration et pas un simple avertissement : l'ancien ordre reste
    du Lua VALIDE — mêmes noms, mêmes arités — donc ni le checker ni le
    compilateur C ne peuvent le signaler. Un projet non migré compilerait et
    rendrait n'importe quoi. C'est la seule migration de cette section dont
    l'absence est INVISIBLE.

    Rewrite de scripts VERSIONNÉS en git : on le signale, on ne le fait pas en
    silence. Renvoie un message ou None."""
    from scripting.refactor import migrate_text_arg_order_in_project
    r = migrate_text_arg_order_in_project(project)
    migrated, skipped = r["migrated"], r["skipped"]
    parts = []
    if migrated:
        n = sum(migrated.values())
        parts.append(f"{n} appel(s) text.* réordonné(s) dans "
                     f"{len(migrated)} script(s) : "
                     + ", ".join(sorted(p.name for p in migrated)))
    if skipped:
        n = sum(len(v) for v in skipped.values())
        parts.append(f"{n} appel(s) text.* à vérifier à la main "
                     f"({', '.join(sorted(p.name for p in skipped))}) — ordre "
                     f"indécidable, la position vient AVANT le contenu")
    return " ; ".join(parts) if parts else None


def seed_or_migrate_palettes(project):
    """Appelé après project.palettes.load(). Priorité :
    (1) ancien catalogue monolithique project/palettes.json (pré-catalogue-
        illimité, deux pools 16+16 dans un seul fichier) ;
    (2) anciens pools séparés project/palettes/obj/ + bg/ (catalogue
        illimité mais encore scindé OBJ/BG, une session avant la fusion) ;
    (3) projet neuf sans aucune trace de ce qui précède -> seed avec les
        presets par défaut.
    Aux étapes (1)/(2), les collisions de nom entre OBJ et BG sont
    résolues : couleurs identiques -> dédupliquées (une seule entrée
    gardée) ; couleurs différentes -> le doublon BG est suffixé " (BG)"."""
    if project.palettes.items:
        return

    def _merge(name: str, colors: list, is_bg: bool):
        if not name:
            return
        existing = project.palettes.get(name)
        if existing is None:
            project.palettes.append(PaletteBank(name=name, colors=colors))
            return
        if existing.colors == colors:
            return  # doublon identique entre pools -> rien à faire
        final_name = f"{name} (BG)" if is_bg else name
        if project.palettes.get(final_name) is None:
            project.palettes.append(PaletteBank(name=final_name, colors=colors))

    if project.legacy_palettes_file.exists():
        d = json.loads(project.legacy_palettes_file.read_text(encoding="utf-8"))
        for b in d.get("obj_banks", []):
            _merge(b.get("name", ""), list(b.get("colors", [])), is_bg=False)
        for b in d.get("bg_banks", []):
            _merge(b.get("name", ""), list(b.get("colors", [])), is_bg=True)
        project.palettes.save_all()
        project.legacy_palettes_file.rename(
            project.legacy_palettes_file.parent / (project.legacy_palettes_file.name + ".migrated"))
        return

    legacy_obj_files = sorted(project.legacy_obj_palettes_dir.glob("*.json")) \
        if project.legacy_obj_palettes_dir.exists() else []
    legacy_bg_files = sorted(project.legacy_bg_palettes_dir.glob("*.json")) \
        if project.legacy_bg_palettes_dir.exists() else []
    if legacy_obj_files or legacy_bg_files:
        for f in legacy_obj_files:
            d = json.loads(f.read_text(encoding="utf-8"))
            _merge(d.get("name", ""), list(d.get("colors", [])), is_bg=False)
        for f in legacy_bg_files:
            d = json.loads(f.read_text(encoding="utf-8"))
            _merge(d.get("name", ""), list(d.get("colors", [])), is_bg=True)
        project.palettes.save_all()
        if project.legacy_obj_palettes_dir.exists():
            project.legacy_obj_palettes_dir.rename(
                project.legacy_obj_palettes_dir.parent / "obj.migrated")
        if project.legacy_bg_palettes_dir.exists():
            project.legacy_bg_palettes_dir.rename(
                project.legacy_bg_palettes_dir.parent / "bg.migrated")
        return

    from core.palette_presets import generate_default_banks
    for bank in generate_default_banks():
        project.palettes.append(bank)
    project.palettes.save_all()


def load_scenes_with_migration(project):
    """
    Charge les scènes en gérant la migration automatique de l'ancien
    format (instances[actor_name] → Actor inline).  Si le dossier
    project/actors/ existe encore, ses fichiers servent de référence
    pour copier les Components lors de la migration, puis sont ignorés.
    """
    from core.models.scene import Scene

    legacy_actors: dict[str, "Actor"] = {}
    old_actors_dir = project.project_dir / "actors"
    if old_actors_dir.exists():
        for f in sorted(old_actors_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                # Reconstituer un Actor partiel (components seulement) pour la migration
                a = Actor(
                    name        = d.get("name", f.stem),
                    prefab_name = d.get("prefab_name"),
                    active      = d.get("active", True),
                    components  = _components_from_list(d.get("components", [])),
                )
                legacy_actors[a.name] = a
            except Exception:
                pass

    project.scenes.items = []
    scenes_dir = project.scenes_dir
    if not scenes_dir.exists():
        return
    for f in sorted(scenes_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            scene = Scene.from_dict(d, legacy_actors=legacy_actors if legacy_actors else None)
            project.scenes.items.append(scene)
            # Si migration détectée (format instances → actors), re-sauvegarder
            if "instances" in d and "actors" not in d:
                project.save_scene(scene)
        except Exception as e:
            print(f"[project] erreur lecture Scene {f.name}: {e}")

    # Rouvrir sur la dernière scène éditée (repli : la scène de démarrage du jeu,
    # qui tenait ce rôle avant la séparation des deux champs).
    restore = project.settings.last_scene or project.settings.start_scene
    if restore:
        for i, s in enumerate(project.scenes):
            if s.name == restore:
                project._active_scene_idx = i
                break


def migrate_scene_backgrounds(project):
    """Migration : ancien `scene.background_asset` (BackgroundAsset multi-layer)
    -> `scene.background_layers`. Chaque layer référence l'image par son STEM ;
    on s'assure qu'un BackgroundAsset (sidecar de compression) existe par image.
    Idempotent (ne fait rien si background_layers déjà rempli). PNG intacts."""
    for scene in project.scenes:
        legacy = getattr(scene, "_legacy_bg_asset", "")
        if scene.background_layers or not legacy:
            continue
        old = project.get_background(legacy)
        for L in getattr(old, "_legacy_layers", []) if old else []:
            stem = Path(L.background_name).stem if L.background_name else ""
            if not stem:
                continue
            ap = project.background_images_dir / L.background_name
            if ap.exists() and project.get_background(stem) is None:
                sync_background_png(project, ap)   # sidecar de compression par image
            scene.background_layers.append(BackgroundLayer(
                background_name=stem, bg_slot=L.bg_slot,
                scroll_speed=L.scroll_speed, pal_bank=L.pal_bank))
        scene._legacy_bg_asset = ""
        if scene.background_layers:
            project.save_scene(scene)


def migrate_bg_sidecar_location(project):
    """Migration : sidecar BackgroundAsset déplacé de project/backgrounds/ vers
    assets/backgrounds/ (co-localisé avec le PNG source, comme SpriteAsset).
    Déplace les *.json restants (sans écraser une cible existante) puis retire
    l'ancien dossier s'il devient vide. Idempotent. PNG jamais touchés."""
    old_dir = project.project_dir / "backgrounds"
    if not old_dir.exists() or old_dir.resolve() == project.backgrounds_dir.resolve():
        return
    project.backgrounds_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(old_dir.glob("*.json")):
        dest = project.backgrounds_dir / f.name
        if not dest.exists():
            f.rename(dest)
    try:
        old_dir.rmdir()   # échoue si non vide → on laisse tel quel
    except OSError:
        pass


def migrate_nine_slices_to_ui_backgrounds(project):
    """Asset `NineSlice` → fond d'INTERFACE (`BackgroundAsset.kind == "ui"`).

    Un NineSlice ne portait qu'un `source` (le nom d'un BackgroundAsset déjà
    importé) et 4 marges : c'était un cadre SANS image à lui, dépendant d'un
    fond pour exister. Le fond d'interface EST ce cadre, marges comprises — une
    seule identité, un seul endroit où découper (le canvas du Background
    Editor), et plus de couple d'assets à garder cohérent.

    Trois gestes, dans cet ordre : reporter les marges sur le fond source,
    repointer les `UIPanel` qui citaient le cadre vers ce fond, puis retirer le
    fichier du cadre. Lit les JSON BRUTS de `project/nine_slices/` — le registre
    a disparu avec le modèle, et une migration ne peut pas dépendre de ce
    qu'elle supprime. Idempotente (dossier absent = rien à faire) ; un cadre
    dont le fond source est introuvable est LAISSÉ EN PLACE plutôt que perdu."""
    ns_dir = project.project_dir / "nine_slices"
    if not ns_dir.exists():
        return
    from core.models.background import KIND_UI, UI_ROLE_NINE

    retarget: dict[str, str] = {}      # nom du cadre -> nom du fond
    for f in sorted(ns_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ba = project.get_background(str(d.get("source", "")))
        if ba is None:
            continue                    # source cassée : on ne jette rien
        ba.kind = KIND_UI
        ba.ui_role = UI_ROLE_NINE
        ba.slice_left = int(d.get("left", 4) or 0)
        ba.slice_right = int(d.get("right", 4) or 0)
        ba.slice_top = int(d.get("top", 4) or 0)
        ba.slice_bottom = int(d.get("bottom", 4) or 0)
        project.backgrounds.save(ba)
        retarget[str(d.get("name", f.stem))] = ba.name
        f.unlink()
    try:
        ns_dir.rmdir()                  # échoue si des cadres orphelins restent
    except OSError:
        pass
    if not retarget:
        return

    # Les panneaux citaient le CADRE ; ils citent désormais le fond directement.
    from core.models.ui_region import KIND_PANEL, FILL_NINE
    for lay in project.ui_layouts:
        touched = False
        for el in lay.elements:
            if getattr(el, "kind", "") != KIND_PANEL:
                continue
            if getattr(el, "fill_kind", "") != FILL_NINE:
                continue
            new = retarget.get(getattr(el, "fill_asset", ""))
            if new:
                el.fill_asset = new
                touched = True
        if touched:
            project.ui_layouts.save(lay)


def reconcile_backgrounds(project):
    """(1) PNG déposés hors éditeur dans assets/backgrounds/ → crée le
    BackgroundAsset + sa compression (comme sync_background_png). (2) Fonds
    existants sans tileset → compression calculée. NON-DESTRUCTIF (PNG jamais
    modifié), idempotent."""
    d = project.background_images_dir
    for f in (sorted(d.glob("*")) if d.exists() else []):
        if f.is_file() and f.suffix.lower() in (".png", ".bmp"):
            sync_background_png(project, f)
    for ba in list(project.backgrounds):
        if ba.tileset:
            continue
        img = ba.image_name()
        ap = project.background_images_dir / img if img else None
        if ap and ap.exists():
            encode_background_asset(ba, ap)
            if ba.tileset:
                project.backgrounds.save(ba)


def migrate_sprite_palettes(project):
    """Normalisation NON-DESTRUCTIVE des sprites existants sans PAL_BANK :
    encode depuis le PNG source (métadonnées JSON, PNG jamais touché).
    Idempotent — une fois `palettes` présente (encode ici, ou migration
    from_dict depuis un ancien `own_palette`), la passe saute."""
    from core.asset_sync import apply_sprite_encoding
    for sp in list(project.sprites):
        if sp.palettes or not sp.asset:
            continue
        ap = project.asset_abs(sp.asset)
        if not ap or not ap.exists():
            continue
        try:
            from core.sprite_import import encode_sprite
            apply_sprite_encoding(sp, encode_sprite(ap, sp.quantize_method))
            project.sprites.save(sp)
        except Exception:
            pass


def reconcile_sfx_and_music(project):
    """
    Crée les sidecars manquants pour les fichiers audio bruts déjà présents
    dans assets/sfx/ et assets/music/ (déposés via l'explorateur pendant
    que l'éditeur était fermé — le ProjectWatcher ne peut pas les avoir vus).
    """
    from core.models.audio import SFX_FILE_EXTS, MUSIC_FILE_EXTS
    for f in sorted(project.sfx_dir.glob("*")) if project.sfx_dir.exists() else []:
        if f.is_file() and f.suffix.lower() in SFX_FILE_EXTS:
            sync_sfx_file(project, f)
    for f in sorted(project.music_dir.glob("*")) if project.music_dir.exists() else []:
        if f.is_file() and f.suffix.lower() in MUSIC_FILE_EXTS:
            sync_music_file(project, f)


def reconcile_fonts(project):
    """Même rôle pour assets/fonts/ : planches PNG et descripteurs `.fnt`
    déposés hors ligne.

    Le `.fnt` passe en premier : quand les deux fichiers sont là, c'est lui qui
    fait foi (il porte le mapping des caractères), et il référence sa planche —
    laquelle ne doit donc pas créer une seconde police en doublon."""
    from core.models.font import FONT_FILE_EXTS
    from core.asset_sync import sync_font_file
    if not project.fonts_dir.exists():
        return
    files = [f for f in sorted(project.fonts_dir.glob("*"))
             if f.is_file() and f.suffix.lower() in FONT_FILE_EXTS]
    pages = set()
    for f in [x for x in files if x.suffix.lower() == ".fnt"]:
        sync_font_file(project, f)
        font = project.fonts.get(f.stem)
        if font and font.asset:
            pages.add(project.asset_abs(font.asset))
    for f in [x for x in files if x.suffix.lower() != ".fnt"]:
        if f not in pages:
            sync_font_file(project, f)


def migrate_var_refs_to_ids(project) -> int:
    """`{"var": "<nom>"}` → `{"var": <id>}` dans les scènes et prefabs.

    Réécrit les FICHIERS avant leur chargement, et non les objets en mémoire :
    une référence de variable peut vivre dans n'importe quel champ de n'importe
    quel composant, présent ou à venir. Un parcours du JSON brut les trouve
    toutes sans que la migration ait à connaître la liste des champs — celle-ci
    aurait vieilli au premier composant ajouté.

    Idempotent : une référence déjà en id est un `int`, jamais retouchée. Un nom
    qui ne désigne plus rien est LAISSÉ tel quel — le convertir en id demanderait
    d'en inventer un, alors que la référence est déjà cassée et doit se voir.
    """
    ids = {("global", g.name): g.id for g in project.globals}
    ids.update({("const", c.name): c.id for c in project.constants})
    if not ids:
        return 0

    def walk(node) -> bool:
        """True si quelque chose a changé sous ce nœud."""
        changed = False
        if isinstance(node, dict):
            var = node.get("var")
            if isinstance(var, str) and var:
                src = node.get("src", "global")
                vid = ids.get((src if src in ("global", "const") else "global", var))
                if vid:
                    node["var"] = vid
                    changed = True
            for v in node.values():
                changed |= walk(v)
        elif isinstance(node, list):
            for v in node:
                changed |= walk(v)
        return changed

    n = 0
    for f in list(project.scenes_dir.glob("*.json")) + list(project.prefab_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if walk(data):
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            n += 1
    return n


def migrate_removed_text_calls(project):
    """`draw_upto` / `draw_in_upto` / `draw_num` / `draw_num_in` retirés.

    Appelée APRÈS load_texts : la migration crée des entrées de table et en
    modifie d'autres.

    Ne migre que le MÉCANIQUE — une valeur qui est exactement `global.get("x")`
    devient une entrée `$x` ; un `draw_in_upto(zone, clé, scene.frame() / K)`
    devient un `draw_in` avec `[speed=K]` en tête du texte. Le reste est laissé
    en place et signalé : le checker sait déjà dire quoi écrire (REMOVED_API),
    et décider ce que devient un tempo calculé appartient à l'auteur.

    Contrairement au réordonnancement d'arguments, l'absence de migration se
    VOIT ici — les fonctions n'existent plus. On peut donc laisser du travail à
    l'auteur sans risquer un projet qui rend faux en silence.

    Rewrite de scripts VERSIONNÉS en git : on le signale, on ne le fait pas en
    silence. Renvoie un message ou None."""
    from scripting.refactor import migrate_removed_text_in_project
    r = migrate_removed_text_in_project(project)
    migrated, skipped = r["migrated"], r["skipped"]
    if not migrated and not skipped:
        return None
    if migrated:
        project.save_texts()
    parts = []
    if migrated:
        n = sum(migrated.values())
        parts.append(f"{n} appel(s) text.* retiré(s) migré(s) dans "
                     f"{len(migrated)} script(s) : "
                     + ", ".join(sorted(p.name for p in migrated)))
    if skipped:
        n = sum(len(v) for v in skipped.values())
        parts.append(f"{n} appel(s) à reprendre à la main "
                     f"({', '.join(sorted(p.name for p in skipped))}) — "
                     f"le tempo s'écrit [speed=n] dans le texte, une valeur $nom")
    return " ; ".join(parts)
