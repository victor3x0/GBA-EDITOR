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
)
from codegen.build_utils import sym as _sym_fn
from codegen.runtime_codegen.headers import generate_actor_types, generate_actor_api
from codegen.runtime_codegen.lua_compiler import transpile_all
from codegen.runtime_codegen.main_gen import generate_main
from core.project import (Project, Scene, SceneLayer, Background, Actor, SpriteAsset,
                     SpriteComponent, CollisionBoxComponent, ScriptComponent)
from core.validator import validate_project

# Scripting pipeline (Lua → C)
sys.path.insert(0, str(Path(__file__).parent))
from scripting.parser  import parse as lua_parse, LuaParseError
from scripting.checker import check as lua_check, BuildContext
from scripting.codegen import generate as lua_generate, CodegenContext
from scripting.globals import write_globals

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
                # BG layers
                bg_pairs: list[tuple[SceneLayer, Background]] = []
                for layer in scene.active_layers():
                    bg = p.get_background(layer.background_name)
                    if bg and bg.asset:
                        bg_pairs.append((layer, bg))

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

            # grit BG : un tileset par scène (symboles préfixés {scene_sym}_tileset)
            for d in all_scene_data:
                if ok and d["bg_pairs"]:
                    ok = ok and self._step_grit_bg(p, d["bg_pairs"],
                                                   scene_sym=_sym_fn(d["scene"].name))

            # grit Sprites : union de toutes scènes + prefabs (dédupliqués par nom)
            seen_sprites: set[str] = set()
            unique_sprites: list = []
            for _, sprite in all_actor_sprites_flat + prefab_actor_sprites:
                if sprite and sprite.asset and sprite.name not in seen_sprites:
                    seen_sprites.add(sprite.name)
                    unique_sprites.append((None, sprite))
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

            # Pré-collecte de tous les globals (toutes scènes + prefabs)
            precomputed_globals = None
            if ok:
                precomputed_globals = self._precompute_globals(p, all_scene_data, scene_names)

            # Transpilation Lua → C pour chaque scène
            if ok:
                for d in all_scene_data:
                    if not ok:
                        break
                    ok = self._step_transpile_scripts(
                        p, d["scene"], d["scene_actors"], scene_names=scene_names,
                        precomputed_global_names=precomputed_globals,
                    )

            if ok:
                ok = self._step_gen_main(
                    p, all_scene_data, sound_assets,
                    prefab_actor_sprites=prefab_actor_sprites,
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

    def _step_grit_bg(self, p, bg_pairs, scene_sym: str = ""):
        return GritBackground(
            self.toolchain.resolve_grit(), self._emit, self._run_cmd
        ).run(p, bg_pairs, scene_sym=scene_sym)

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

    # ── Pré-collecte des globals (toutes scènes réunies) ─────────────

    def _precompute_globals(self, p, all_scene_data, scene_names):
        """Parse tous les scripts Lua du projet et génère globals.h/c une seule fois."""
        from scripting.parser import parse as _parse, LuaParseError
        from scripting.globals import write_globals as _write_globals

        all_asts = []
        for d in all_scene_data:
            scene = d["scene"]
            for actor, _ in d["scene_actors"]:
                comp = actor.get_component("script")
                if comp and comp.active and comp.script:
                    sp = p.asset_abs(comp.script)
                    if sp and sp.exists() and sp.suffix.lower() == ".lua":
                        try:
                            all_asts.append(_parse(sp.read_text(encoding="utf-8")))
                        except LuaParseError:
                            pass
            scene_script = getattr(scene, "script", "")
            if scene_script:
                sp = p.asset_abs(scene_script)
                if sp and sp.exists() and sp.suffix.lower() == ".lua":
                    try:
                        all_asts.append(_parse(sp.read_text(encoding="utf-8")))
                    except LuaParseError:
                        pass

        for pf in self.project.prefabs:
            if getattr(pf, "max_instances", 0) <= 0:
                continue
            from core.project import ScriptComponent
            sc = next((c for c in pf.components if isinstance(c, ScriptComponent)), None)
            if sc and sc.script:
                sp = p.asset_abs(sc.script)
                if sp and sp.exists() and sp.suffix.lower() == ".lua":
                    try:
                        all_asts.append(_parse(sp.read_text(encoding="utf-8")))
                    except LuaParseError:
                        pass

        names = _write_globals(p.src_dir, all_asts)
        if names:
            self._emit("log_line", f"[lua] globals: {', '.join('g_' + n for n in names)}")
        return names

    # ── Transpilation Lua → C ─────────────────────────────────────────

    def _step_transpile_scripts(self, p, scene, scene_actors, scene_names=None,
                                 precomputed_global_names=None):
        return transpile_all(
            p, scene, scene_actors, self.project.prefabs, self._emit,
            scene_names=scene_names,
            precomputed_global_names=precomputed_global_names,
        )

    # ── Génération de main.c ──────────────────────────────────────────

    def _step_gen_main(self, p, all_scene_data,
                       sound_assets=None, prefab_actor_sprites=None):
        return generate_main(
            p, all_scene_data, sound_assets,
            prefab_actor_sprites or [], self.project.prefabs, self._emit,
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
