"""
editor/asset_pipeline.py — Conversion des assets bruts en fichiers C/headers.

Trois étapes indépendantes, chacune appelable séparément :

    GritBackground(emit, run_cmd).run(p, bg_pairs)   -> tileset.h/.c
    GritSprites(emit, run_cmd).run(p, sprites)        -> sprite_X.h/.c
    MmutilAudio(emit, run_cmd, toolchain).run(p, assets) -> soundbank.h/.bin

`emit(event, data)` et `run_cmd(cmd, prefix, cwd)` sont injectés depuis
BuildWorker pour que le pipeline reste découplé de l'UI.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional, Callable

from core.project import Project, BackgroundLayer, Actor, SpriteAsset


# ── Helpers image ──────────────────────────────────────────────────────────────

def png_size(path: Path) -> tuple[int, int]:
    """Lit width/height depuis le header IHDR du PNG (bytes 16-23)."""
    try:
        with open(path, "rb") as f:
            f.seek(16)
            w, h = struct.unpack(">II", f.read(8))
        return w, h
    except Exception:
        return 0, 0


def count_frames(p: Project, sprite: SpriteAsset) -> int:
    """Nombre de frames uniques (dédupliquées) que grit convertit réellement pour ce sprite."""
    _, ordered = sprite_unique_frames(sprite)
    return max(1, len(ordered))


def pad_sprite_png(
    src: Path,
    frame_w: int,
    frame_h: int,
    out_dir: Path,
    emit: Callable,
) -> Optional[Path]:
    """Padde le PNG à des multiples de frame_w×frame_h et le convertit en RGBA.

    La conversion RGBA est indispensable pour les PNGs indexés à palette étendue :
    grit construit alors sa propre palette optimale depuis les couleurs réellement présentes.
    """
    try:
        from PIL import Image
        img = Image.open(src)
        w, h = img.size
        target_w = ((w + frame_w - 1) // frame_w) * frame_w
        target_h = ((h + frame_h - 1) // frame_h) * frame_h
        needs_pad = (w != target_w or h != target_h)
        rgba = img.convert("RGBA")
        if not needs_pad:
            out = out_dir / f"_rgba_{src.name}"
            rgba.save(out)
            return out
        emit("log_line",
             f"[pad] {src.name} {w}×{h} -> {target_w}×{target_h} "
             f"(frame {frame_w}×{frame_h})")
        padded = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        padded.paste(rgba, (0, 0))
        out = out_dir / f"_pad_{src.name}"
        padded.save(out)
        return out
    except Exception as e:
        emit("error_line", f"[pad] erreur padding {src.name} : {e}")
        return None


# ── GritBackground ─────────────────────────────────────────────────────────────

class GritBackground:
    """Convertit les tilesets BG via grit -> tileset.h/.c."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd

    def run(
        self,
        p: Project,
        bg_pairs: list[BackgroundLayer],
        scene_sym: str = "",
    ) -> bool:
        if not bg_pairs:
            return True
        if not self._grit:
            self._emit("error_line", "[grit BG] introuvable"); return False

        png_paths = []
        for layer in bg_pairs:
            if not layer.image:
                continue
            ap = p.background_images_dir / layer.image
            if not ap.exists():
                self._emit("error_line", f"[grit BG] image manquante : {layer.image}")
                return False
            png_paths.append(ap)
            self._emit("log_line", f"[grit BG] BG{layer.bg_slot} <- {layer.image}")
        if not png_paths:
            return True

        # Symbole préfixé par scène pour éviter les conflits de symboles C
        ts_sym  = f"{scene_sym}_tileset" if scene_sym else "tileset"
        out_base = str(p.grit_out_dir / ts_sym)
        cmd = (
            [str(self._grit)]
            + [str(pp) for pp in png_paths]
            + ["-gt", "-gB4", "-gS", "-mRtf", "-mLf",
               "-p", "-pS", "-ftc", "-fa",
               "-S", ts_sym, "-o", out_base]
        )
        ok = self._run_cmd(cmd, "[grit BG]", cwd=p.grit_out_dir)
        if ok:
            for f in sorted(p.grit_out_dir.glob(f"{ts_sym}*.h")):
                self._emit("log_line", f"[grit BG] -> {f.name}")
        return ok


# ── Sprite sheet reconstruction ────────────────────────────────────────────────

def _frame_key(frame: "AnimFrame") -> tuple:
    """Clé hashable identifiant la composition d'une frame (tuiles + positions
    + flip par tuile — deux frames identiques sauf pour une tuile retournée
    doivent être traitées comme distinctes)."""
    return tuple(sorted(
        (t.src_col, t.src_row, t.dst_col, t.dst_row, t.flip_h, t.flip_v)
        for t in frame.tiles
    ))


def sprite_unique_frames(sprite: SpriteAsset) -> tuple[dict, list]:
    """Déduplique les frames d'un sprite (toutes states/directions confondues).

    Fait autorité sur l'ordre des frames à la fois pour le sheet reconstruit
    (build_sprite_sheet) et pour les tables d'animation C (main_gen._anim_tables_for) :
    les deux doivent utiliser ce même index pour rester synchronisés.

    Retourne (frame_index, ordered) où frame_index[key] = position dans ordered,
    et ordered = [(AnimFrame, flip_h, flip_v), ...] dans l'ordre d'apparition.
    """
    frame_index: dict[tuple, int] = {}
    ordered: list = []
    for state in sprite.states:
        dir_map = {sd.dir: sd for sd in state.directions}
        for sd in state.directions:
            src_sd = dir_map.get(sd.mirror_of, sd) if sd.mirror_of is not None else sd
            for f in src_sd.frames:
                key = _frame_key(f) + (sd.flip_h, sd.flip_v)
                if key not in frame_index:
                    frame_index[key] = len(ordered)
                    ordered.append((f, sd.flip_h, sd.flip_v))
    return frame_index, ordered


def _compose_frame(src_img, frame: "AnimFrame", fw: int, fh: int):
    """Compose une frame fw×fh en peignant chaque tuile 8×8 depuis le PNG source.
    Une tuile flip_h/flip_v est physiquement retournée avant d'être collée —
    la GBA n'a pas de flip matériel par tuile au sein d'un OBJ composé."""
    from PIL import Image
    out = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    sw, sh = src_img.size
    for t in frame.tiles:
        sx, sy = t.src_col * 8, t.src_row * 8
        if sx < 0 or sy < 0 or sx + 8 > sw or sy + 8 > sh:
            continue
        piece = src_img.crop((sx, sy, sx + 8, sy + 8))
        if t.flip_h:
            piece = piece.transpose(Image.FLIP_LEFT_RIGHT)
        if t.flip_v:
            piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
        dx, dy = t.dst_col * 8, t.dst_row * 8
        out.paste(piece, (dx, dy), piece)
    return out


def build_sprite_sheet(
    src: Path,
    sprite: SpriteAsset,
    out_dir: Path,
    emit: Callable,
) -> Optional[Path]:
    """
    Reconstruit un spritesheet compact à partir de la source PNG et des AnimState.
    Chaque frame est composée tuile par tuile (8×8) depuis le PNG source.
    Les frames mirrorées (flip_h / flip_v) sont générées ici et incluses dans le sheet.
    Retourne le chemin du PNG intermédiaire (dans out_dir), ou None si erreur.
    """
    try:
        from PIL import Image
        fw, fh = sprite.frame_w, sprite.frame_h
        src_img = Image.open(src).convert("RGBA")

        _, ordered = sprite_unique_frames(sprite)
        if not ordered:
            return pad_sprite_png(src, fw, fh, out_dir, emit)

        all_frames: list = []
        for f, flip_h, flip_v in ordered:
            tile = _compose_frame(src_img, f, fw, fh)
            if flip_h:
                tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
            if flip_v:
                tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
            all_frames.append(tile)

        # Pack en une seule rangée (grit le préfère)
        sheet = Image.new("RGBA", (fw * len(all_frames), fh), (0, 0, 0, 0))
        for i, tile in enumerate(all_frames):
            sheet.paste(tile, (i * fw, 0))

        out = out_dir / f"_sheet_{src.stem}.png"
        sheet.save(out)
        emit("log_line",
             f"[sheet] {src.name} -> {len(all_frames)} frames "
             f"({fw}x{fh}px) -> {out.name}")
        return out
    except Exception as e:
        emit("error_line", f"[sheet] erreur reconstruction {src.name} : {e}")
        return None


# ── GritSprites ────────────────────────────────────────────────────────────────

def _sym(s: str) -> str:
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return ("_" + r) if r and r[0].isdigit() else r


_ARRAY_RE = r'(\w+{suffix})\[(\d+)\][^=]*=\s*\{{([^}}]*)\}}'


def remap_sprite_to_bank(c_path: Path, bank_colors: list[int], emit: Callable) -> bool:
    """Réécrit en place le .c généré par grit pour un sprite 4bpp : les index
    de tuiles (nibbles) sont remappés vers l'ordre canonique de `bank_colors`,
    et la palette locale est remplacée par `bank_colors` telle quelle. Permet
    à plusieurs sprites assignés à la même banque de partager des index de
    palette identiques (condition nécessaire pour être copiés une seule fois
    dans PAL_OBJ_RAM par main_gen.py)."""
    import re

    text = c_path.read_text()
    tiles_m = re.search(_ARRAY_RE.format(suffix="Tiles"), text)
    pal_m   = re.search(_ARRAY_RE.format(suffix="Pal"), text)
    if not tiles_m or not pal_m:
        emit("error_line", f"[palette] format grit inattendu dans {c_path.name}")
        return False

    tiles_vals = [int(x, 16) for x in tiles_m.group(3).split(",") if x.strip()]
    pal_vals   = [int(x, 16) for x in pal_m.group(3).split(",") if x.strip()]

    remap: dict[int, int] = {}
    for local_idx, color in enumerate(pal_vals):
        remap[local_idx] = next(
            (canon_idx for canon_idx, bc in enumerate(bank_colors) if bc == color),
            local_idx,  # slot de padding grit (couleur inutilisée) — jamais référencé par Tiles
        )

    new_tiles = []
    for word in tiles_vals:
        new_word = 0
        for i in range(8):
            nibble = (word >> (4 * i)) & 0xF
            new_word |= (remap.get(nibble, nibble) & 0xF) << (4 * i)
        new_tiles.append(new_word)

    new_tiles_str = ",".join(f"0x{v:08X}" for v in new_tiles) + ","
    new_pal_str   = ",".join(f"0x{c:04X}" for c in (bank_colors + [0] * 16)[:16]) + ","

    text = text[:tiles_m.start(3)] + new_tiles_str + text[tiles_m.end(3):]
    pal_m2 = re.search(_ARRAY_RE.format(suffix="Pal"), text)
    text = text[:pal_m2.start(3)] + new_pal_str + text[pal_m2.end(3):]

    c_path.write_text(text)
    return True


def resolve_obj_palette_bank(p: Project, entity, scene: Optional["Scene"]):
    """Résout la PaletteBank OBJ ciblée par `entity.pal_bank` (Actor ou
    Prefab) via les palettes actives de `scene` — pal_bank est un slot
    (0-15) dans scene.active_obj_palettes, pas une référence directe au
    catalogue projet (illimité). None si non résolvable (AUTO_PAL_BANK,
    scène sans sélection à ce slot, ou palette supprimée du catalogue) —
    dans ce cas le sprite garde son comportement legacy (palette grit
    propre, non forcée)."""
    from core.project import AUTO_PAL_BANK
    pal_bank = getattr(entity, "pal_bank", 0)
    if scene is None or pal_bank == AUTO_PAL_BANK:
        return None
    active = getattr(scene, "active_obj_palettes", [])
    if not (0 <= pal_bank < len(active)):
        return None
    name = active[pal_bank]
    return p.get_obj_palette(name) if name else None


class GritSprites:
    """Convertit les sprites OBJ (acteurs + prefabs) via grit -> sprite_X.h/.c."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd

    def run(
        self,
        p: Project,
        sprites: list[tuple[any, Optional[SpriteAsset], Optional["PaletteBank"]]],
    ) -> bool:
        """
        sprites : liste de (actor_ou_prefab, SpriteAsset, PaletteBank résolue
        ou None). Un même SpriteAsset n'est converti qu'une fois (dédupliqué
        par nom — la résolution de banque, y compris le choix de la scène
        propriétaire en cas de doublon, est faite par l'appelant).
        """
        if not sprites:
            return True
        if not self._grit:
            self._emit("error_line", "[grit Actor] introuvable"); return False

        done: set[str] = set()
        for actor_or_pf, sprite, bank in sprites:
            if not sprite or not sprite.asset or sprite.name in done:
                continue
            done.add(sprite.name)

            ap = p.asset_abs(sprite.asset)
            if not ap or not ap.exists():
                self._emit("error_line", f"[grit Actor] asset manquant : {sprite.asset}")
                return False

            grit_src = build_sprite_sheet(ap, sprite, p.grit_out_dir, self._emit)
            if grit_src is None:
                return False

            pal_bank = getattr(actor_or_pf, "pal_bank", 0)
            if bank and bank.colors:
                from PIL import Image
                from core.color_utils import quantize_image_to_bank
                img = Image.open(grit_src).convert("RGBA")
                quantize_image_to_bank(img, bank.colors).save(grit_src)
                self._emit("log_line",
                           f"[palette] {sprite.name} -> banque {pal_bank} "
                           f"({bank.name or 'sans nom'}, {len(bank.colors)} couleurs)")

            out_base = str(p.grit_out_dir / f"sprite_{_sym(sprite.name)}")
            self._emit("log_line",
                       f"[grit Actor] {sprite.name} <- {ap.name} "
                       f"({sprite.frame_w}x{sprite.frame_h}px)")
            cmd = [
                str(self._grit), str(grit_src),
                "-gt", "-gB4",
                f"-Mw{sprite.tile_w}", f"-Mh{sprite.tile_h}",
                "-m!", "-p", "-pn16", "-ftc",
                "-o", out_base,
            ]
            if not self._run_cmd(cmd, f"[grit:{sprite.name}]", cwd=p.grit_out_dir):
                return False

            if bank and bank.colors:
                if not remap_sprite_to_bank(Path(out_base + ".c"), bank.colors, self._emit):
                    return False
        return True


# ── MmutilAudio ────────────────────────────────────────────────────────────────

def resolve_sound_assets(p: Project) -> dict:
    """Retourne {'sfx': [(Sfx, Path)], 'music': [(Music, Path)]}."""
    sfx_list, music_list = [], []
    for sfx in p.sfx:
        ap = p.asset_abs(sfx.asset) if sfx.asset else None
        if ap and ap.exists():
            sfx_list.append((sfx, ap))
    for music in p.music:
        ap = p.asset_abs(music.asset) if music.asset else None
        if ap and ap.exists():
            music_list.append((music, ap))
    return {"sfx": sfx_list, "music": music_list}


class MmutilAudio:
    """Lance mmutil + bin2s pour produire soundbank.h/.bin/.s."""

    def __init__(self, mmutil_path, bin2s_path, emit: Callable, run_cmd: Callable):
        self._mmutil  = mmutil_path
        self._bin2s   = bin2s_path
        self._emit    = emit
        self._run_cmd = run_cmd

    def run(self, p: Project, sound_assets: dict) -> bool:
        if not self._mmutil:
            self._emit("error_line", "[mmutil] introuvable — skip audio"); return True

        all_files = (
            [str(ap) for _, ap in sound_assets["sfx"]] +
            [str(ap) for _, ap in sound_assets["music"]]
        )
        if not all_files:
            return True

        soundbank_bin = p.build_dir / "soundbank.bin"
        soundbank_h   = p.build_dir / "soundbank.h"
        cmd = [str(self._mmutil)] + all_files + ["-osoundbank.bin", "-hsoundbank.h"]
        self._emit("log_line",
                   f"[mmutil] {len(sound_assets['sfx'])} sfx + "
                   f"{len(sound_assets['music'])} music")
        ok = self._run_cmd(cmd, "[mmutil]", cwd=p.build_dir)
        if ok and soundbank_h.exists():
            # mmutil écrit soundbank.h dans build/ — le Makefile ne compile
            # que depuis build/src/ (-Isrc), donc le header doit y être copié
            # pour que le #include "soundbank.h" de main.c le trouve.
            shutil.copy2(soundbank_h, p.src_dir / "soundbank.h")
            self._emit("log_line", "[mmutil] -> src/soundbank.h")
        if ok:
            bin2s = self._bin2s
            if bin2s and soundbank_bin.exists():
                # bin2s écrit l'assembleur sur stdout (pas de flag -o) : on doit
                # capturer nous-mêmes la sortie pour la sauver dans src/soundbank.s.
                # _run_cmd() générique se contente de logger stdout/stderr et
                # renvoie un bool, ce qui perdait ce contenu (symbole
                # "soundbank_bin" jamais linké → undefined reference au link).
                self._emit("log_line", f"[bin2s] {bin2s} soundbank.bin")
                try:
                    proc = subprocess.run(
                        [str(bin2s), "soundbank.bin"],
                        cwd=str(p.build_dir), capture_output=True, text=True,
                    )
                except FileNotFoundError as e:
                    self._emit("error_line", f"[bin2s] introuvable : {e}")
                    proc = None
                if proc is not None:
                    for line in proc.stderr.splitlines():
                        self._emit("error_line" if proc.returncode != 0 else "log_line", f"  {line}")
                if proc is not None and proc.returncode == 0:
                    s_dst = p.src_dir / "soundbank.s"
                    s_dst.write_text(proc.stdout, encoding="utf-8")
                    self._emit("log_line", "[bin2s] -> src/soundbank.s")
                    # bin2s ne génère pas de header : déclarer nous-mêmes le
                    # symbole "soundbank_bin" (dérivé de "soundbank.bin" par
                    # bin2s) que main.c référence via mmInitDefault().
                    h_dst = p.src_dir / "soundbank.bin.h"
                    h_dst.write_text(
                        "/* Généré par GBA Editor — déclare le symbole produit par bin2s */\n"
                        "#ifndef SOUNDBANK_BIN_H\n"
                        "#define SOUNDBANK_BIN_H\n"
                        "extern const unsigned char soundbank_bin[];\n"
                        "#endif\n",
                        encoding="utf-8",
                    )
                    self._emit("log_line", "[bin2s] -> src/soundbank.bin.h")
            else:
                self._emit("log_line", "[bin2s] introuvable — soundbank non linke")
        return ok
