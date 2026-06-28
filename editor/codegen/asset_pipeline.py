"""
editor/asset_pipeline.py — Conversion des assets bruts en fichiers C/headers.

Trois étapes indépendantes, chacune appelable séparément :

    GritBackground(emit, run_cmd).run(p, bg_pairs)   → tileset.h/.c
    GritSprites(emit, run_cmd).run(p, sprites)        → sprite_X.h/.c
    MmutilAudio(emit, run_cmd, toolchain).run(p, assets) → soundbank.h/.bin

`emit(event, data)` et `run_cmd(cmd, prefix, cwd)` sont injectés depuis
BuildWorker pour que le pipeline reste découplé de l'UI.
"""
from __future__ import annotations

import shutil
import struct
from pathlib import Path
from typing import Optional, Callable

from core.project import Project, SceneLayer, Background, Tileset, Actor, SpriteAsset


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
    """Nombre de frames dans le spritesheet."""
    ap = p.asset_abs(sprite.asset)
    if not ap or not ap.exists():
        return 1
    w, h = png_size(ap)
    if w == 0 or h == 0:
        return 1
    cols = max(1, w // sprite.frame_w)
    rows = max(1, h // sprite.frame_h)
    return cols * rows


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
             f"[pad] {src.name} {w}×{h} → {target_w}×{target_h} "
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
    """Convertit les tilesets BG via grit → tileset.h/.c."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd

    def run(
        self,
        p: Project,
        bg_pairs: list[tuple[SceneLayer, Background, Tileset]],
        scene_sym: str = "",
    ) -> bool:
        if not bg_pairs:
            return True
        if not self._grit:
            self._emit("error_line", "[grit BG] introuvable"); return False

        png_paths = []
        for layer, bg, tileset in bg_pairs:
            ap = p.asset_abs(tileset.asset)
            if not ap or not ap.exists():
                self._emit("error_line", f"[grit BG] asset manquant : {tileset.asset}")
                return False
            png_paths.append(ap)
            self._emit("log_line", f"[grit BG] BG{layer.bg} <- {bg.name} ({ap.name})")

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


# ── GritSprites ────────────────────────────────────────────────────────────────

def _sym(s: str) -> str:
    r = "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return ("_" + r) if r and r[0].isdigit() else r


class GritSprites:
    """Convertit les sprites OBJ (acteurs + prefabs) via grit → sprite_X.h/.c."""

    def __init__(self, grit_path: Path, emit: Callable, run_cmd: Callable):
        self._grit    = grit_path
        self._emit    = emit
        self._run_cmd = run_cmd

    def run(
        self,
        p: Project,
        sprites: list[tuple[any, Optional[SpriteAsset]]],
    ) -> bool:
        """
        sprites : liste de (actor_ou_prefab, SpriteAsset).
        Un même SpriteAsset n'est converti qu'une fois (dédupliqué par nom).
        """
        if not sprites:
            return True
        if not self._grit:
            self._emit("error_line", "[grit Actor] introuvable"); return False

        done: set[str] = set()
        for _, sprite in sprites:
            if not sprite or not sprite.asset or sprite.name in done:
                continue
            done.add(sprite.name)

            ap = p.asset_abs(sprite.asset)
            if not ap or not ap.exists():
                self._emit("error_line", f"[grit Actor] asset manquant : {sprite.asset}")
                return False

            grit_src = pad_sprite_png(ap, sprite.frame_w, sprite.frame_h,
                                      p.grit_out_dir, self._emit)
            if grit_src is None:
                return False

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
        cmd = [str(self._mmutil)] + all_files + ["-osoundbank.bin", "-hsoundbank.h"]
        self._emit("log_line",
                   f"[mmutil] {len(sound_assets['sfx'])} sfx + "
                   f"{len(sound_assets['music'])} music")
        ok = self._run_cmd(cmd, "[mmutil]", cwd=p.build_dir)
        if ok:
            bin2s = self._bin2s
            if bin2s and soundbank_bin.exists():
                ok2 = self._run_cmd([str(bin2s), "soundbank.bin"],
                                    "[bin2s]", cwd=p.build_dir)
                if ok2:
                    s_out = p.build_dir / "soundbank.bin.s"
                    s_dst = p.build_dir / "src" / "soundbank.s"
                    if s_out.exists():
                        shutil.copy2(s_out, s_dst)
                        self._emit("log_line", "[bin2s] -> src/soundbank.s")
            else:
                self._emit("log_line", "[bin2s] introuvable — soundbank non linke")
        return ok
