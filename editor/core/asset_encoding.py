"""Orchestration d'encodage GBA déclenchée par l'apparition/suppression d'un
fichier asset sur disque (ProjectWatcher, dialogues d'import UI). Calcule
l'encodage (délégué à core.bg_import / core.sprite_import) et l'applique au
sidecar JSON (BackgroundAsset / SpriteAsset) — jamais le PNG source.

Deux déclencheurs, un seul geste : `sync_*` pour UN fichier qui apparaît
maintenant, `reconcile_*` (en fin de module) pour le dossier entier à
l'ouverture d'un projet, quand des fichiers ont été déposés éditeur fermé."""

from pathlib import Path
from typing import Optional

from core.models.background import BackgroundAsset
from core.models.sprite import SpriteAsset
from core.models.audio import MUSIC_FILE_EXTS, SFX_FILE_EXTS, WAV_BITS_OK


def check_audio_file(path) -> Optional[str]:
    """None si le fichier est utilisable, sinon la raison du refus, rédigée
    pour être affichée telle quelle à l'auteur.

    Ce contrôle n'est pas une ceinture de plus : c'est le SEUL. mmutil ne
    renvoie jamais un code d'erreur — ni sur un wav 24 bits (dont il émet
    quand même la constante, donc un effet muet dans la ROM), ni sur une
    extension inconnue. S'il n'y a pas de refus ici, il n'y en a nulle part.

    Appelé à l'import ET par le validateur, parce que le ProjectWatcher
    ramasse aussi les fichiers déposés à la main dans assets/.
    """
    from pathlib import Path
    path = Path(path)
    ext = path.suffix.lower()

    if ext in MUSIC_FILE_EXTS:
        # Le contenu décide, pas l'extension : c'est la règle de la v0.8.1, et
        # elle vaut d'autant plus avec quatre formats — un `.xm` renommé `.mod`
        # se joue très bien, et un `.mod` qui n'en est pas un doit se refuser
        # ici, puisque mmutil ne dira jamais non.
        from core.engine_emulation.module_model import load_module
        try:
            mod = load_module(path)
        except ValueError as e:
            return f"{e} — l'extension dit « {ext[1:]} », le contenu non."
        except Exception as e:
            return f"module illisible ({e})."
        if not mod.order:
            return "module sans table d'ordre — aucun motif à jouer."
        if not any(s.data.size for s in mod.samples):
            return "module sans aucun échantillon — il ne rendrait aucun son."
        return None

    if ext == ".wav":
        import wave
        try:
            with wave.open(str(path)) as w:
                bits = w.getsampwidth() * 8
        except wave.Error as e:
            return (f"WAV non reconnu ({e}). Il faut du PCM non compressé, "
                    f"8 ou 16 bits.")
        except Exception as e:
            return f"lecture impossible ({e})."
        if bits not in WAV_BITS_OK:
            return (f"WAV {bits} bits : mmutil ne convertit que 8 et 16 bits. "
                    f"Il construirait la ROM sans le dire, avec un effet muet.")
        return None

    accepted = ", ".join(sorted(SFX_FILE_EXTS | MUSIC_FILE_EXTS))
    return f"extension {ext or '(aucune)'} non prise en charge — accepté : {accepted}."


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


def resync_sprite_png(project, png_path: Path) -> Optional[str]:
    """La planche d'un sprite EXISTANT a changé sur le disque : recalculer ses
    palettes depuis les nouveaux pixels. Pendant de `resync_background_png`.

    Moins grave qu'un fond — le build fait relire le PNG par grit, donc la ROM
    est juste — mais l'éditeur affichait, lui, les anciennes couleurs : aperçu
    d'acteur, coût en palettes, allocation de banques. Tout ce que l'auteur a
    dessiné (découpe en frames, états, directions, miroirs) ne dépend pas des
    couleurs et reste intact ; `apply_sprite_encoding` ne touche qu'aux
    palettes."""
    sprite = project.sprites.get(png_path.stem)
    if sprite is None:
        return None
    before = len(sprite.palettes)
    pal_overrides = dict(sprite.palette_overrides)
    try:
        warning = encode_sprite_asset(sprite, png_path)
    except Exception as e:
        return f"“{sprite.name}”: image could not be re-read ({e})."
    sprite.source_stamp = file_stamp(png_path)
    if len(sprite.palettes) == before:
        # Autant de sous-palettes qu'avant : les renvois au catalogue visent
        # toujours les mêmes, on les garde.
        sprite.palette_overrides = pal_overrides
    project.sprites.save(sprite)
    if pal_overrides and len(sprite.palettes) != before:
        return (f"“{sprite.name}”: palette count changed, "
                f"{len(pal_overrides)} palette link(s) could not be kept.")
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


def remove_font_file(project, path: Path):
    """Fichier supprimé de assets/fonts/ : suppression différée du JSON.

    Une police vit sur DEUX fichiers possibles (planche + descripteur `.fnt`),
    dont les noms peuvent différer. On retire donc la police que ce fichier
    porte réellement — par son stem, ou parce qu'elle le référence comme
    planche/descripteur — plutôt que de supposer stem == nom de police."""
    font = project.fonts.get(path.stem)
    if font is None:
        for f in project.fonts:
            for rel in (f.asset, f.descriptor):
                if rel and project.asset_abs(rel) == path:
                    font = f
                    break
            if font:
                break
    if font:
        project.fonts.soft_delete(font)


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


def sync_font_file(project, path: Path) -> Optional[str]:
    """Appelé quand une planche PNG ou un descripteur `.fnt` apparaît dans
    assets/fonts/. Crée le Font + son sidecar si absent.

    Deux points d'entrée, un seul asset : le `.fnt` apporte le mapping des
    caractères, le PNG nu le fait déduire (grille + charset proposé, corrigeables
    dans l'écran Police). Une police déjà connue n'est jamais ré-analysée
    automatiquement — sinon on écraserait les corrections de l'utilisateur.

    Renvoie un avertissement d'import, None si tout va bien."""
    from core.models.font import Font
    from core import font_import

    name = path.stem
    font = project.fonts.get(name)
    warning = None
    if font is None:
        # La planche d'un `.fnt` déjà importé ne doit pas créer une SECONDE
        # police : le descripteur fait foi (il porte le mapping des caractères)
        # et référence déjà cette image. reconcile_fonts applique cette règle en
        # ordonnant ses passes, mais un dépôt à chaud (watcher) arrive fichier
        # par fichier — d'où le garde ici, au seul endroit qui crée un Font.
        if path.suffix.lower() != ".fnt":
            for f in project.fonts:
                if f.asset and project.asset_abs(f.asset) == path:
                    return None
        font = Font(name=name)
        # Échec dur (format illisible, planche introuvable) : aucun asset créé —
        # mieux vaut rien qu'une police vide qui traîne et se sauvegarde. Un
        # échec mou (planche lisible mais aucun glyphe trouvé) crée l'asset :
        # l'utilisateur corrigera la taille de cellule dans l'écran Police.
        try:
            if path.suffix.lower() == ".fnt":
                fields = font_import.import_font_fnt(path)
                page = fields.pop("page_path", None)
                if page is None:
                    return (f"Police « {name} » : le descripteur ne référence aucune "
                            f"planche PNG trouvable — dépose la planche à côté du .fnt.")
                font.asset = project.asset_rel(page)
                font.descriptor = project.asset_rel(path)
            else:
                # Planche opaque : le fond dominant est PROPOSÉ comme couleur
                # transparente. Une proposition, pas un verdict — l'écran
                # Police laisse la repiquer, ou l'effacer si elle est fausse.
                font.bg_color = font_import.detect_bg_color(path)
                # `space_color` est None à ce stade (rien à deviner : un
                # marqueur d'espacement ne se distingue pas d'une couleur de
                # dessin), donc la police entre en MONO. Elle passera en
                # proportionnel le jour où l'utilisateur repiquera la couleur.
                fields = font_import.import_font_png(
                    path, keys=font.key_colors(), space_color=font.space_color)
                font.asset = project.asset_rel(path)
            font_import.apply_font_import(font, fields)
        except Exception as exc:
            return f"Police « {name} » : import impossible ({exc})."
        if not font.glyphs:
            warning = (f"Police « {name} » : aucun glyphe détecté — vérifie la "
                       f"taille de cellule dans l'écran Police.")
        project.fonts.append(font)
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        project.fonts.save(font)
    return warning


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


def resync_background_png(project, png_path: Path) -> Optional[str]:
    """Le PNG d'un fond EXISTANT a changé sur le disque : recalculer sa
    compression depuis les nouveaux pixels.

    `sync_background_png` ne touche pas à un asset déjà connu (c'est sa règle :
    ne jamais écraser un import), et `reconcile_backgrounds` ne rattrape que les
    sidecars SANS tileset. Un fond retouché gardait donc ses anciennes tuiles
    pour toujours — à l'écran ET dans la ROM, puisque le build lit `ba.tileset`
    et non le PNG.

    Les choix de l'utilisateur sont conservés : `encode_background_asset` ne
    re-détecte pas le mode, et le `kind`, le rôle UI, les marges de découpe et
    les animations ne dépendent pas des pixels. Les repeints par tuile, eux,
    sont indexés par (colonne, ligne) : ils ne survivent que si la géométrie n'a
    pas bougé — sinon ils désigneraient d'autres tuiles que celles peintes.

    Renvoie un avertissement si des repeints ont dû être abandonnés, None sinon.
    """
    ba = project.backgrounds.get(png_path.stem)
    if ba is None:
        return None
    before = (ba.tiles_w, ba.tiles_h, len(ba.palettes))
    tile_overrides = dict(ba.tile_palette_overrides)
    pal_overrides = dict(ba.palette_overrides)

    encode_background_asset(ba, png_path)
    ba.source_stamp = file_stamp(png_path)

    same_geometry = (ba.tiles_w, ba.tiles_h, len(ba.palettes)) == before
    if same_geometry:
        # Simple retouche : les repeints désignent toujours les mêmes tuiles.
        ba.tile_palette_overrides = tile_overrides
        ba.palette_overrides = pal_overrides
    project.backgrounds.save(ba)

    dropped = len(tile_overrides) + len(pal_overrides)
    if dropped and not same_geometry:
        return (f"“{ba.name}”: image geometry changed, {dropped} palette "
                f"repaint(s) could not be kept.")
    return None


def file_stamp(path: Path) -> str:
    """Empreinte d'un fichier : sa taille et le hachage de son contenu.

    On lit les octets plutôt que de se fier à la date : le sidecar est réécrit
    à chaque sauvegarde du projet — il est donc presque toujours plus récent que
    son image, ce qui rendrait toute comparaison de dates aveugle — et un
    logiciel de dessin peut reposer l'ancienne date en enregistrant. Les images
    d'un fond tiennent dans un écran GBA : les relire ne coûte rien."""
    import hashlib
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return f"{len(data)}:{hashlib.sha1(data).hexdigest()[:16]}"


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


# ── Rattrapage à l'ouverture d'un projet ──────────────────────────
# Le ProjectWatcher voit les fichiers qui apparaissent PENDANT que l'éditeur
# tourne. Ceux déposés à l'explorateur, éditeur fermé, ne sont vus par personne :
# les `reconcile_*` ci-dessous repassent une fois par ouverture de projet.
#
# C'est le même geste que les `sync_*` de ce module, appliqué au DOSSIER au lieu
# d'un fichier — d'où leur place ici : aucune n'a besoin d'importer quoi que ce
# soit, elles bouclent sur ce qui précède. Elles rattrapent aussi le sidecar dont
# l'encodage manque (import interrompu, échec avalé en tâche de fond) : le
# fichier source est là, l'encodage se recalcule.
#
# Toutes NON-DESTRUCTIVES — le PNG / le .mod source n'est jamais modifié, seul le
# sidecar JSON est écrit — et idempotentes : un asset déjà encodé est sauté.
# Appelées uniquement depuis `Project.load()`, dans l'ordre (cf. project.py).


def reconcile_backgrounds(project):
    """(1) PNG déposés hors éditeur dans assets/backgrounds/ → crée le
    BackgroundAsset + sa compression. (2) Fonds dont le sidecar existe sans
    tileset → compression recalculée depuis le PNG. (3) Fonds dont le PNG a été
    RETOUCHÉ éditeur fermé → compression refaite depuis les nouveaux pixels."""
    d = project.background_images_dir
    for f in (sorted(d.glob("*")) if d.exists() else []):
        if f.is_file() and f.suffix.lower() in (".png", ".bmp"):
            sync_background_png(project, f)
    for ba in list(project.backgrounds):
        img = ba.image_name()
        ap = project.background_images_dir / img if img else None
        if not (ap and ap.exists()):
            continue
        if not ba.tileset and ba.mode != "bitmap":
            encode_background_asset(ba, ap)
            ba.source_stamp = file_stamp(ap)
            if ba.tileset:
                project.backgrounds.save(ba)
        elif ba.source_stamp != file_stamp(ap):
            # Le watcher ne voit que ce qui bouge pendant que l'éditeur tourne ;
            # une retouche faite à côté ne serait vue par personne, et le fond
            # resterait périmé à l'écran ET dans la ROM sans que rien ne le dise.
            #
            # Empreinte vide = asset antérieur à ce champ : on ré-encode une
            # fois pour reprendre pied. C'est sans effet si l'image n'a pas
            # bougé (l'encodage est déterministe), et ça répare justement les
            # fonds déjà périmés au moment où cette version arrive.
            resync_background_png(project, ap)


def reconcile_sprites(project):
    """(1) Sprites dont le sidecar existe sans PAL_BANK → encodage recalculé
    depuis le PNG source : c'est le cas du sprite créé par `sync_sprite_png`
    alors que son encodage avait échoué — l'exception y est avalée (tâche de
    fond watcher), la réparation est ici. (2) Sprites dont la planche a été
    RETOUCHÉE éditeur fermé → palettes refaites depuis les nouveaux pixels.

    Pendant de `reconcile_backgrounds`, aux mêmes conditions d'empreinte."""
    for sp in list(project.sprites):
        if not sp.asset:
            continue
        ap = project.asset_abs(sp.asset)
        if not ap or not ap.exists():
            continue
        if not sp.palettes:
            try:
                from core.sprite_import import encode_sprite
                apply_sprite_encoding(sp, encode_sprite(ap, sp.quantize_method))
                sp.source_stamp = file_stamp(ap)
                project.sprites.save(sp)
            except Exception:
                pass
        elif sp.source_stamp != file_stamp(ap):
            # Empreinte vide = sprite antérieur au champ : on ré-encode une fois
            # pour reprendre pied (sans effet si la planche n'a pas bougé,
            # l'encodage étant déterministe).
            resync_sprite_png(project, ap)


def reconcile_sfx_and_music(project):
    """Crée les sidecars manquants pour les fichiers audio bruts déjà présents
    dans assets/sfx/ et assets/music/."""
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
