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

    if project.settings.start_scene:
        for i, s in enumerate(project.scenes):
            if s.name == project.settings.start_scene:
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
