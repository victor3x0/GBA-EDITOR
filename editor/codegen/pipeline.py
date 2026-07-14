"""
GBA Editor — pipeline de build
Prend la scène active du projet et génère la ROM.

Flux :
  scène active → résolution des backgrounds + actors
  → grit BG    → grit_out/tileset.h
  → grit Actor → grit_out/actor_{name}.h
  → main.c     → src/main.c (+ scripts C copiés)
  → make       → obj/*.o → rom.elf → rom.gba
  → mgba
"""

import math
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from core.events import EventEmitter
from core.toolchain import Toolchain
from codegen.asset_pipeline import (
    GritBackground, GritSprites, MmutilAudio,
    resolve_sound_assets, count_frames, png_size,
    bg_layer_sym, bg_layer_sym_for, bg_map_geometry, bg_map_sbb_count,
    resolve_palette_bank,
)
from codegen.palette_alloc import scene_bank_layout, effective_palette_colors
from codegen.build_utils import sym as _sym_fn
from codegen.runtime_codegen.headers import generate_actor_types, generate_actor_api
from codegen.runtime_codegen.lua_compiler import transpile_all
from codegen.runtime_codegen.main_gen import generate_main
from core.project import (Project, Scene, BackgroundLayer, Actor, SpriteAsset,
                     SpriteComponent, CollisionBoxComponent, ScriptComponent,
                     OWN_PAL_BANK)
from core.validator import validate_project

# Scripting pipeline (Lua → C)
sys.path.insert(0, str(Path(__file__).parent))
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals

# En mode figé (PyInstaller), "editor" n'est plus un dossier parent réel du
# module (il devient la racine de sys.path) : remonter 3 parents depuis
# __file__ ne pointe plus vers la racine du repo mais au-dessus du bundle.
# runtime/ est donc embarqué à la racine du bundle (voir le .spec) et on
# le résout depuis sys._MEIPASS dans ce cas.
if getattr(sys, "frozen", False):
    RUNTIME_DIR = Path(sys._MEIPASS) / "runtime"
else:
    RUNTIME_DIR = Path(__file__).parent.parent.parent / "runtime"


class BuildWorker(EventEmitter, threading.Thread):
    """
    Worker de build GBA — Python pur, sans dépendance GUI.

    Événements émis (depuis le thread de build) :
        "log_line"   (str)   — ligne de log normale
        "error_line" (str)   — ligne d'erreur
        "finished"   (bool)  — succès/échec en fin de build

    La GUI est responsable de marshaller ces callbacks vers son propre
    thread principal (ex. queue + QTimer pour PyQt6).
    """

    # processus mGBA en cours (partagé entre toutes les instances)
    _mgba_proc: "subprocess.Popen | None" = None

    def __init__(self, project: Project, toolchain: Toolchain):
        EventEmitter.__init__(self)
        threading.Thread.__init__(self, daemon=True)
        self.project   = project
        self.toolchain = toolchain

    def run(self):
        try:
            # Ferme mGBA si encore ouvert (sinon objcopy ne peut pas écraser rom.gba)
            if BuildWorker._mgba_proc and BuildWorker._mgba_proc.poll() is None:
                BuildWorker._mgba_proc.terminate()
                try:
                    BuildWorker._mgba_proc.wait(timeout=3)
                except Exception:
                    BuildWorker._mgba_proc.kill()
            BuildWorker._mgba_proc = None

            p = self.project

            if not p.scenes:
                self._emit("error_line","[build] aucune scène dans le projet")
                self._emit("finished",False)
                return

            # ── Validation ────────────────────────────────────────
            warns, errors = validate_project(p)
            for w in warns:
                self._emit("log_line", f"[warn]  {w}")
            for e in errors:
                self._emit("error_line", f"[error] {e}")
            if errors:
                self._emit("error_line", f"[build] {len(errors)} erreur(s) bloquante(s) — build annulé.")
                self._emit("finished", False)
                return

            all_scenes = p.scenes
            scene_names = [s.name for s in all_scenes]
            self._emit("log_line", f"[build] {p.settings.name}")
            self._emit("log_line", f"[build] {len(all_scenes)} scène(s) : {', '.join(scene_names)}")

            p.prepare_build()
            sound_assets = self._resolve_sound_assets(p)

            # ── Résolution par scène ───────────────────────────────
            all_scene_data: list[dict] = []
            all_bg_pairs_flat: list = []
            all_actor_sprites_flat: list = []

            for scene in all_scenes:
                # BG layers = ceux de la SCÈNE (chacun référence une image dont
                # la compression vit dans un BackgroundAsset sidecar keyé par nom).
                bg_pairs = list(getattr(scene, "background_layers", []))

                # Actors
                scene_actors: list[tuple[Actor, Optional[SpriteAsset]]] = []
                for actor in scene.actors:
                    if actor.active:
                        sprite_comp = actor.get_component("sprite")
                        sprite = (p.get_sprite(sprite_comp.sprite_name)
                                  if sprite_comp and sprite_comp.active and sprite_comp.sprite_name
                                  else None)
                        scene_actors.append((actor, sprite))

                all_scene_data.append({
                    "scene": scene,
                    "bg_pairs": bg_pairs,
                    "scene_actors": scene_actors,
                })
                all_bg_pairs_flat += bg_pairs
                all_actor_sprites_flat += scene_actors

            # Prefab sprites (communs à toutes les scènes)
            prefab_actor_sprites: list[tuple[Actor, Optional[SpriteAsset]]] = []
            for pf in self.project.prefabs:
                if getattr(pf, "max_instances", 0) <= 0:
                    continue
                _pf_sc = next((c for c in pf.components
                               if isinstance(c, SpriteComponent) and c.sprite_name), None)
                if _pf_sc:
                    _pf_sprite = p.get_sprite(_pf_sc.sprite_name)
                    if _pf_sprite:
                        prefab_actor_sprites.append((pf, _pf_sprite))

            ok = True

            # Chaque layer de scène référence une image ; sa compression vit dans
            # un BackgroundAsset sidecar (keyé par nom). Fond compressé -> émission
            # directe (pas grit) ; sinon grit (legacy, rare car tout est compressé).
            # Dédup globale par (image, bg_slot).
            seen_bg_layers: set = set()
            unique_bg_layers: list = []
            seen_compressed: set = set()
            for d in all_scene_data:
                scene = d["scene"]
                bg_layout = scene_bank_layout(p, scene, "bg")
                for layer in d["bg_pairs"]:
                    if not layer.image:
                        continue
                    ba = p.get_background(layer.image)
                    # Fond bitmap (Mode 4) : non supporté au build (increment 2) —
                    # ignoré (sinon traité comme un fond tuilé/grit → données invalides).
                    if ba is not None and getattr(ba, "mode", "tiled") == "bitmap":
                        self._emit("log_line",
                                   f"[bg] '{ba.name}' bitmap (Mode 4) — non supporté au "
                                   f"build (increment 2) → ignoré")
                        continue
                    if ba and ba.tileset:
                        has_ov = bool(getattr(layer, "tile_palette_overrides", None))
                        sym = bg_layer_sym_for(scene, layer)
                        # Map PROPRE À LA SCÈNE si overrides (scène = source de
                        # vérité), sinon partagée entre scènes (dédup ROM).
                        key = (scene.name, sym) if has_ov else (ba.name, layer.bg_slot)
                        if key not in seen_compressed:
                            seen_compressed.add(key)
                            # Garde-fou 8bpp → 4bpp (transitoire) : aucun tileset
                            # 8bpp ne doit atteindre bg_emit (il serait interprété
                            # en 4bpp = corrompu).
                            build_ba = self._bg_build_asset(p, ba)
                            if build_ba is None:
                                continue   # bitmap (Mode 4) — non émis (increment 2)
                            # 8bpp = palette 256 sur TOUTE la PAL_BG_RAM : incompatible
                            # avec un 2e calque de fond dans la même scène.
                            if (getattr(build_ba, "bpp", 4) == 8
                                    and sum(1 for L in d["bg_pairs"] if L.image) > 1):
                                self._emit("error_line",
                                           f"[bg] '{build_ba.name}' 8bpp occupe toute la palette "
                                           f"BG — les autres calques de fond de la scène "
                                           f"'{scene.name}' auront des couleurs incorrectes")
                            pal_offset = bg_layout.bg_block_offset(build_ba) or 0
                            final_map = self._bg_final_tilemap(
                                p, scene, build_ba, layer, pal_offset)
                            self._emit_compressed_bg(p, build_ba, sym, final_map)
                        continue
                    key = (layer.image, layer.bg_slot)
                    if key in seen_bg_layers:
                        continue
                    seen_bg_layers.add(key)
                    png = p.background_images_dir / (ba.source if ba and ba.source else f"{layer.image}.png")
                    colors = effective_palette_colors(
                        p, layer.pal_bank, png, scene.active_bg_palettes)
                    mp_slot = bg_layout.bank_index(layer.pal_bank, colors)
                    unique_bg_layers.append((ba, layer, colors, mp_slot))
            if ok and unique_bg_layers:
                ok = ok and self._step_grit_bg(p, unique_bg_layers)
            if ok and unique_bg_layers:
                ok = ok and self._check_bg_tile_budget(p, unique_bg_layers)

            # grit Sprites : union de toutes scènes + prefabs (dédupliqués par
            # nom — 1er rencontré gagne). Les couleurs effectives sont résolues
            # via la scène propriétaire de l'actor ; pour un prefab poolé, via
            # la 1ère scène du projet — cohérence inter-scènes vérifiée par le
            # validateur (avertissement, pas un blocage).
            seen_sprites: set[str] = set()
            unique_sprites: list = []
            for d in all_scene_data:
                scene = d["scene"]
                for actor, sprite in d["scene_actors"]:
                    if sprite and sprite.asset and sprite.name not in seen_sprites:
                        seen_sprites.add(sprite.name)
                        colors = effective_palette_colors(
                            p, actor.pal_bank, p.asset_abs(sprite.asset),
                            scene.active_obj_palettes, own_pal=sprite.own_palette)
                        unique_sprites.append((actor, sprite, colors))
            anchor_scene = all_scenes[0] if all_scenes else None
            anchor_obj = anchor_scene.active_obj_palettes if anchor_scene else []
            for pf, sprite in prefab_actor_sprites:
                if sprite and sprite.asset and sprite.name not in seen_sprites:
                    seen_sprites.add(sprite.name)
                    colors = effective_palette_colors(
                        p, getattr(pf, "pal_bank", OWN_PAL_BANK), p.asset_abs(sprite.asset),
                        anchor_obj, own_pal=sprite.own_palette)
                    unique_sprites.append((pf, sprite, colors))
            if ok and unique_sprites:
                ok = ok and self._step_grit_actors(p, unique_sprites)

            if ok and sound_assets:
                ok = ok and self._step_mmutil(p, sound_assets)

            # Headers : tous les actors de toutes les scènes
            if ok:
                all_sa = [(a, s) for d in all_scene_data for a, s in d["scene_actors"]]
                ok = self._step_generate_actor_headers(
                    p, all_sa, sound_assets, all_scenes=all_scenes,
                    total_actors=sum(len(d["scene_actors"]) for d in all_scene_data),
                )

            # Collecte des events définis + écriture globals.h/c depuis project.globals
            actor_defined_events: dict[str, set[str]] = {}
            global_names: list[str] = []
            if ok:
                global_names = self._write_project_globals(p, all_scene_data, actor_defined_events)

            # Écriture constants.h depuis project.constants
            const_names: list[str] = []
            if ok:
                const_names = self._write_project_constants(p)

            # Transpilation Lua → C pour chaque scène (prefabs compilés une seule fois)
            compiled_prefabs: set[str] = set()
            if ok:
                for d in all_scene_data:
                    if not ok:
                        break
                    ok = self._step_transpile_scripts(
                        p, d["scene"], d["scene_actors"], scene_names=scene_names,
                        precomputed_global_names=global_names,
                        precomputed_const_names=const_names,
                        compiled_prefabs=compiled_prefabs,
                    )

            if ok:
                ok = self._step_gen_main(
                    p, all_scene_data, sound_assets,
                    prefab_actor_sprites=prefab_actor_sprites,
                    actor_defined_events=actor_defined_events,
                )
            if ok:
                ok = self._step_make(p)
            if ok:
                ok = self._step_launch_mgba(p)

            self._emit("finished", ok)

        except Exception as e:
            self._emit("error_line",f"[erreur inattendue] {e}")
            import traceback
            self._emit("error_line",traceback.format_exc())
            self._emit("finished",False)

    # ── Utilitaires ───────────────────────────────────────────────

    @staticmethod
    def _actor_script(actor: Actor) -> Optional[str]:
        comp = actor.get_component("script")
        return comp.script if comp and comp.active else None

    @staticmethod
    def _sym(s: str) -> str:
        return _sym_fn(s)

    @staticmethod
    def _png_size(path: Path) -> tuple[int, int]:
        return png_size(path)

    def _count_frames(self, p: Project, sprite: SpriteAsset) -> int:
        return count_frames(p, sprite)

    def _run_cmd(self, cmd, prefix, cwd=None, env=None) -> bool:
        self._emit("log_line",f"{prefix} {' '.join(str(c) for c in cmd)}")
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(cwd) if cwd else None, env=env
            )
            for line in proc.stdout.splitlines():
                self._emit("log_line",f"  {line}")
            for line in proc.stderr.splitlines():
                self._emit("error_line",f"  {line}")
            return proc.returncode == 0
        except FileNotFoundError as e:
            self._emit("error_line",f"{prefix} introuvable : {e}")
            return False

    def _make_env(self) -> dict:
        env = os.environ.copy()
        dkp = self.toolchain.devkitpro_path or Path("C:/devkitPro")
        arm = self.toolchain.resolve_arm_gcc()
        env["DEVKITPRO"] = str(dkp).replace("\\", "/")
        env["DEVKITARM"] = str(dkp / "devkitARM").replace("\\", "/")
        extras = [
            str(dkp / "devkitARM" / "bin"),
            str(dkp / "tools" / "bin"),
            str(dkp / "msys2" / "usr" / "bin"),
        ]
        if arm:
            extras.insert(0, str(arm.parent))
        sep = ";" if os.name == "nt" else ":"
        env["PATH"] = sep.join(extras) + sep + env.get("PATH", "")
        return env

    # ── Étape 1 : grit BG ─────────────────────────────────────────

    def _step_grit_bg(self, p, layers):
        return GritBackground(
            self.toolchain.resolve_grit(), self._emit, self._run_cmd
        ).run(p, layers)

    def _bg_final_tilemap(self, p, scene, ba, layer, pal_offset: int) -> list:
        """SE finale par cellule du layer (pal_offset DÉJÀ appliqué) :
        - tuile PEINTE (`layer.tile_palette_overrides`) -> SE_PALBANK = banque HW de la
          banque de scène choisie (slot dans active_bg_palettes == index HW, cf.
          scene_bank_layout qui place chaque banque active à son slot). La scène
          est la source de vérité : l'asset (`ba.tilemap`) reste intact.
        - tuile normale -> pal_bank local + pal_offset (bloc de l'asset)."""
        from core.bg_compress import unpack_se, pack_se
        tp = getattr(layer, "tile_palette_overrides", None) or {}
        tw = ba.tiles_w or 1
        out = []
        # effective_tilemap() = baseline + overrides d'inpainting ASSET
        # (BackgroundInpainting, partagé). Les overrides de SCÈNE (`tp`) se
        # superposent par-dessus ci-dessous.
        for cell, se in enumerate(ba.effective_tilemap()):
            tid, pb, fh, fv = unpack_se(se)
            col, row = cell % tw, cell // tw
            slot = tp.get((col, row))
            # Override valide seulement si la banque de scène résout des couleurs
            # (sinon rien à afficher — on garde la palette d'origine).
            if slot is not None and 0 <= slot < 16:
                bank = resolve_palette_bank(p, scene.active_bg_palettes, slot)
                if bank and bank.colors:
                    out.append(pack_se(tid, slot, fh, fv))
                    continue
            out.append(pack_se(tid, pb + pal_offset, fh, fv))
        return out

    def _bg_build_asset(self, p, ba):
        """Filtre les fonds non émissibles au build. Un fond BITMAP (Mode 4) est
        ignoré (retourne None — support ROM = increment 2). Les fonds tuilés,
        4bpp comme 8bpp, sont émis nativement (retournés tels quels)."""
        if getattr(ba, "mode", "tiled") == "bitmap":
            self._emit("log_line",
                       f"[bg] '{ba.name}' fond bitmap (Mode 4) — non supporté au build "
                       f"(increment 2) → ignoré")
            return None
        return ba

    def _emit_compressed_bg(self, p, ba, sym, final_tilemap):
        """Émet un fond COMPRESSÉ (métadonnées) en C compatible grit — pas de
        grit. `sym` = symbole du layer (partagé, ou propre à la scène si peint,
        cf. bg_layer_sym_for). `final_tilemap` = SE avec pal_offset + overrides
        déjà appliqués (cf. _bg_final_tilemap) — donc pal_offset=0 ici. cf.
        codegen/bg_emit."""
        from codegen.bg_emit import emit_bg_c
        bpp = getattr(ba, "bpp", 4)
        c, h = emit_bg_c(sym, ba.tileset, final_tilemap, pal_offset=0, bpp=bpp)
        p.grit_out_dir.mkdir(parents=True, exist_ok=True)
        (p.grit_out_dir / f"{sym}.c").write_text(c)
        (p.grit_out_dir / f"{sym}.h").write_text(h)
        self._emit("log_line",
                   f"[bg] {ba.name} compressé ({bpp}bpp) -> {sym} "
                   f"({len(ba.tileset)} tuiles, {len(ba.palettes)} palettes)")

    def _check_bg_tile_budget(self, p, layers) -> bool:
        """Garde-fou VRAM : chaque layer a son propre CBB (16 Ko / 512 tuiles
        4bpp), partagé avec sa propre map (les derniers N SBB du CBB, N selon
        map_size). Un layer dont les tuiles générées débordent sur l'espace
        réservé à sa map écraserait silencieusement cette map en VRAM au
        runtime — on bloque le build plutôt que de laisser cette corruption
        passer inaperçue (contrairement au conflit de palette OBJ/BG entre
        scènes, qui n'est qu'un avertissement — ici c'est de la mémoire
        écrasée, pas juste une mauvaise couleur)."""
        ok = True
        for asset, layer, *_rest in layers:
            if not layer.image:
                continue
            w, h = png_size(p.background_images_dir / layer.image)
            _, _, ms = bg_map_geometry(w, h)
            map_sbb_count = bg_map_sbb_count(ms)
            tile_budget = (8 - map_sbb_count) * 64
            sym = bg_layer_sym(asset.name, layer.bg_slot)
            header = p.grit_out_dir / f"{sym}.h"
            m = re.search(rf"{sym}TilesLen\s+(\d+)", header.read_text()) if header.exists() else None
            if not m:
                self._emit("error_line", f"[grit BG] {sym}.h introuvable/illisible — build annulé")
                ok = False
                continue
            tiles_used = int(m.group(1)) // 32
            if tiles_used > tile_budget:
                self._emit(
                    "error_line",
                    f"[grit BG] '{asset.name}' BG{layer.bg_slot} : {tiles_used} tuiles "
                    f"générées, budget CBB{layer.bg_slot} disponible {tile_budget} tuiles "
                    f"(après réservation de {map_sbb_count} SBB pour sa propre map) — "
                    f"réduire le nombre de tuiles uniques de ce layer (moins de "
                    f"couleurs/motifs) ou sa taille de map."
                )
                ok = False
        return ok

    # ── Étape 2 : grit Actors ─────────────────────────────────────

    def _step_grit_actors(self, p, sprites):
        return GritSprites(
            self.toolchain.resolve_grit(), self._emit, self._run_cmd
        ).run(p, sprites)

    # ── Étape 3 : audio ───────────────────────────────────────────

    def _resolve_sound_assets(self, p):
        return resolve_sound_assets(p)

    def _step_mmutil(self, p, sound_assets):
        return MmutilAudio(
            self.toolchain.resolve_mmutil(),
            self.toolchain.resolve_bin2s(),
            self._emit, self._run_cmd,
        ).run(p, sound_assets)

    # ── Génération des headers C ─────────────────────────────────────

    def _step_generate_actor_headers(self, p, scene_actors, sound_assets,
                                      all_scenes=None, total_actors: int | None = None):
        has_sound = bool(sound_assets and (sound_assets.get('sfx') or sound_assets.get('music')))
        generate_actor_types(p, scene_actors, self.project.prefabs)
        generate_actor_api(
            p, scene_actors, self.project.prefabs, has_sound,
            all_scenes=all_scenes, max_actors=total_actors,
        )
        self._emit('log_line', '[gen] actor_types.h + actor_api.h')
        return True

    # ── Globals projet + collecte des events définis ──────────────────

    def _write_project_globals(self, p, all_scene_data,
                                actor_defined_events: dict | None = None) -> list[str]:
        """
        Génère globals.h/c depuis project.globals (source de vérité explicite).
        Parse aussi les scripts pour collecter actor_defined_events (events implémentés).
        """
        from scripting.parser import parse as _parse, LuaParseError
        from scripting.globals import write_globals as _write_globals
        from codegen.build_utils import sym as _sym

        # Écriture globals.h/c depuis la liste déclarée dans le projet
        names = _write_globals(p.src_dir, p.globals)
        if names:
            self._emit("log_line", f"[lua] globals: {', '.join('g_' + n for n in names)}")

        # Parse léger pour collecter les events définis par chaque acteur/prefab
        if actor_defined_events is None:
            return names

        def _collect_events(sym, sp):
            if sp and sp.exists() and sp.suffix.lower() == ".lua":
                try:
                    ast = _parse(sp.read_text(encoding="utf-8"))
                    actor_defined_events[sym] = {fn.name for fn in ast.functions}
                except LuaParseError:
                    pass

        for d in all_scene_data:
            scene = d["scene"]
            for actor, _ in d["scene_actors"]:
                comp = actor.get_component("script")
                if comp and comp.active and comp.script:
                    _collect_events(_sym(actor.name), p.asset_abs(comp.script))
            scene_script = getattr(scene, "script", "")
            if scene_script:
                _collect_events(_sym(scene.name) + "_scene", p.asset_abs(scene_script))

        for pf in self.project.prefabs:
            if getattr(pf, "max_instances", 0) <= 0:
                continue
            from core.project import ScriptComponent
            sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
            if sc and sc.script:
                _collect_events(_sym(pf.name), p.asset_abs(sc.script))

        return names

    # ── Constants projet ────────────────────────────────────────────────

    def _write_project_constants(self, p) -> list[str]:
        """Génère constants.h depuis project.constants (source de vérité explicite)."""
        from scripting.constants import write_constants as _write_constants

        names = _write_constants(p.src_dir, p.constants)
        if names:
            self._emit("log_line", f"[lua] constants: {', '.join('CONST_' + n.upper() for n in names)}")
        return names

    # ── Transpilation Lua → C ─────────────────────────────────────────

    def _step_transpile_scripts(self, p, scene, scene_actors, scene_names=None,
                                 precomputed_global_names=None, precomputed_const_names=None,
                                 compiled_prefabs=None):
        return transpile_all(
            p, scene, scene_actors, self.project.prefabs, self._emit,
            scene_names=scene_names,
            precomputed_global_names=precomputed_global_names,
            precomputed_const_names=precomputed_const_names,
            compiled_prefabs=compiled_prefabs,
        )

    # ── Génération de main.c ──────────────────────────────────────────

    def _step_gen_main(self, p, all_scene_data,
                       sound_assets=None, prefab_actor_sprites=None,
                       actor_defined_events=None):
        return generate_main(
            p, all_scene_data, sound_assets,
            prefab_actor_sprites or [], self.project.prefabs, self._emit,
            actor_defined_events=actor_defined_events,
        )

    # ── Étape 4 : make ────────────────────────────────────────────

    def _step_make(self, p: Project) -> bool:
        make = self.toolchain.resolve_make()
        if not make:
            self._emit("error_line","[make] introuvable"); return False
        src = RUNTIME_DIR / "Makefile"
        if not src.exists():
            self._emit("error_line",f"[make] Makefile manquant : {src}"); return False
        shutil.copy2(src, p.makefile_path)
        return self._run_cmd(
            [str(make)], "[make]", cwd=p.build_dir, env=self._make_env()
        )

    # ── Étape 5 : mgba ────────────────────────────────────────────

    def _step_launch_mgba(self, p: Project) -> bool:
        if not p.rom_path.exists():
            self._emit("error_line",f"[mgba] ROM manquante : {p.rom_path}")
            return False
        mgba = self.toolchain.resolve_mgba()
        if not mgba:
            self._emit("error_line","[mgba] introuvable"); return False
        BuildWorker._mgba_proc = subprocess.Popen([str(mgba), str(p.rom_path)])
        self._emit("log_line","[mgba] lance")
        return True
