"""Orchestration d'encodage GBA déclenchée par l'apparition/suppression d'un
fichier asset sur disque (ProjectWatcher, dialogues d'import UI). Calcule
l'encodage (délégué à core.bg_import / core.sprite_import) et l'applique au
sidecar JSON (BackgroundAsset / SpriteAsset) — jamais le PNG source."""

from pathlib import Path
from typing import Optional

from core.models.background import BackgroundAsset
from core.models.sprite import SpriteAsset


def sync_sprite_png(project, png_path: Path) -> Optional[str]:
    """Appelé quand un PNG apparaît dans assets/sprites/ (watcher/import). Crée
    le SpriteAsset + son sidecar si absent, via le pipeline aligné sur les
    backgrounds : Validator (détection) → Encodage non-destructif → asset
    éditable. Un sprite déjà connu n'est jamais ré-encodé automatiquement.
    Renvoie un éventuel avertissement d'import (palette réduite), None sinon."""
    name = png_path.stem
    sprite = project.sprites.get(name)
    warning = None
    if sprite is None:
        sprite = SpriteAsset(name=name, asset=project.asset_rel(png_path),
                             frame_w=8, frame_h=8)
        # Validator + encodage : métadonnées uniquement, PNG jamais modifié.
        try:
            warning = encode_sprite_asset(sprite, png_path)
        except Exception:
            pass
        project.sprites.append(sprite)
    sidecar = png_path.with_suffix(".json")
    if not sidecar.exists():
        project.sprites.save(sprite)
    return warning


def apply_sprite_encoding(sprite: "SpriteAsset", c: dict):
    """Applique un résultat d'`encode_sprite` au SpriteAsset (calcul/application
    séparés, comme apply_bg_encoding). Peuple la PAL_BANK (sous-palettes) +
    le pont de compat `own_palette`. Nouvelle baseline restaurable."""
    sprite.palettes = [list(p) for p in c["palettes"]]
    sprite.source_palettes = [list(p) for p in c["palettes"]]
    sprite.palette_overrides = {}
    sprite.own_palette = list(c["own_palette"])     # pont de compat build/preview
    sprite.quantize_method = c["quantize_method"]


def encode_sprite_asset(sprite: "SpriteAsset", png_path: Path, method: str = None) -> Optional[str]:
    """Détecte + encode `png_path` sur `sprite` (métadonnées, PNG intact).
    Calcul/application séparés comme `apply_sprite_encoding` : ici les deux
    sont enchaînés pour le cas simple (import/remplacement UI). Renvoie un
    éventuel avertissement d'import (palette réduite), None sinon. Propage les
    erreurs d'encodage (contrairement à `sync_sprite_png`, qui les avale en
    tâche de fond watcher)."""
    from core.sprite_import import detect_sprite_import_mode, encode_sprite
    warning = detect_sprite_import_mode(png_path).get("warning")
    apply_sprite_encoding(sprite, encode_sprite(png_path, method or sprite.quantize_method))
    return warning


def remove_sprite_png(project, png_path: Path):
    """PNG supprimé de assets/sprites/ : suppression différée du JSON."""
    sprite = project.sprites.get(png_path.stem)
    if sprite:
        project.sprites.soft_delete(sprite)


def remove_background_png(project, png_path: Path):
    """PNG supprimé de assets/backgrounds/ : suppression différée du JSON."""
    bg = project.backgrounds.get(png_path.stem)
    if bg:
        project.backgrounds.soft_delete(bg)


def remove_sfx_file(project, path: Path):
    """Fichier audio supprimé de assets/sfx/ : suppression différée du JSON."""
    sfx = project.sfx.get(path.stem)
    if sfx:
        project.sfx.soft_delete(sfx)


def remove_music_file(project, path: Path):
    """Fichier audio supprimé de assets/music/ : suppression différée du JSON."""
    music = project.music.get(path.stem)
    if music:
        project.music.soft_delete(music)


def sync_sfx_file(project, path: Path):
    """
    Appelé quand un fichier audio apparaît dans assets/sfx/.
    Crée le sidecar JSON à côté si absent, l'ajoute à project.sfx si nécessaire.
    """
    from core.models.audio import Sfx
    name = path.stem
    sfx = project.sfx.get(name)
    if sfx is None:
        sfx = Sfx(name=name, asset=project.asset_rel(path))
        project.sfx.append(sfx)
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        project.sfx.save(sfx)
    return sfx


def sync_music_file(project, path: Path):
    """
    Appelé quand un fichier audio apparaît dans assets/music/.
    Crée le sidecar JSON à côté si absent, l'ajoute à project.music si nécessaire.
    """
    from core.models.audio import Music
    name = path.stem
    music = project.music.get(name)
    if music is None:
        music = Music(name=name, asset=project.asset_rel(path))
        project.music.append(music)
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        project.music.save(music)
    return music


def sync_background_png(project, png_path: Path) -> Optional[str]:
    """Crée un BackgroundAsset (sidecar de compression par image, keyé par le
    stem du PNG) quand un PNG apparaît dans assets/backgrounds/. Ne modifie
    pas un asset existant. C'est la scène qui possède ses layers. Renvoie un
    éventuel avertissement d'import (palette déduite), None sinon."""
    name = png_path.stem
    if project.backgrounds.get(name) is None:
        ba = BackgroundAsset(name=name, asset=png_path.name)
        # Nouveau dépôt : AUTO-DÉTECTION du mode (pivot indexé/non-indexé),
        # puis compression (métadonnées) sans toucher le PNG.
        warning = None
        try:
            from core.bg_import import detect_import_mode
            d = detect_import_mode(png_path)
            ba.mode = "bitmap" if d["token"] in ("bitmap", "bitmap16") else "tiled"
            ba.bpp = 8 if d["token"] == "tiled8" else 4
            warning = d["warning"]
        except Exception:
            pass
        encode_background_asset(ba, png_path)
        project.backgrounds.append(ba)
        project.backgrounds.save(ba)
        return warning
    return None


def apply_bg_encoding(ba: "BackgroundAsset", source_name: str, c: dict):
    """Applique un résultat de compression (dict de bg_import.encode_background)
    à un BackgroundAsset. Séparé du calcul pour permettre une compression
    hors-thread : le worker calcule `c`, le thread UI applique via ce helper."""
    ba.asset = source_name
    ba.palettes = c["palettes"]
    # Nouvelle baseline dérivée du PNG : snapshot restaurable + reset des
    # overrides (l'origine des palettes repart de la compression fraîche).
    ba.source_palettes = [list(p) for p in c["palettes"]]
    ba.palette_overrides = {}
    ba.diagnostics = c.get("diagnostics", {})
    ba.bpp = c.get("bpp", 4)
    ba.mode = c.get("mode", "tiled")
    if ba.mode == "bitmap":
        ba.bitmap = c["bitmap"]
        ba.out_w = c["out_w"]
        ba.out_h = c["out_h"]
        # Pas de représentation tuilée en bitmap.
        ba.tileset = []
        ba.tilemap = []
        ba.tiles_w = 0
        ba.tiles_h = 0
        ba.tile_palette_overrides = {}
    else:
        ba.tileset = c["tileset"]
        ba.tilemap = c["tilemap"]
        ba.tiles_w = c["tiles_w"]
        ba.tiles_h = c["tiles_h"]
        ba.quantize_method = c["quantize_method"]
        ba.bitmap = ""
        ba.out_w = 0
        ba.out_h = 0


def encode_background_asset(ba: "BackgroundAsset", png_path: Path, method: str = None):
    """Calcule et stocke la compression GBA d'un fond (palettes/tileset/tilemap)
    depuis son PNG — sans modifier le fichier. cf. core/bg_import. No-op si
    illisible. Chemin SYNCHRONE (import via watcher, reconcile au chargement).
    Dispatch selon le mode DÉJÀ choisi de l'asset (`ba.mode`/`ba.bpp`) — ne
    re-détecte PAS (la détection est faite une fois à la création), pour ne
    jamais écraser un choix de mode existant lors d'un reconcile."""
    try:
        from core.bg_import import encode_by_mode
        mode_token = "bitmap" if getattr(ba, "mode", "tiled") == "bitmap" \
            else ("tiled8" if getattr(ba, "bpp", 4) == 8 else "tiled4")
        c = encode_by_mode(png_path, mode_token, method or ba.quantize_method,
                           getattr(ba, "dither", False))
        apply_bg_encoding(ba, png_path.name, c)
    except Exception:
        pass
