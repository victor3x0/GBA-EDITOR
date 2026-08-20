"""
runtime_codegen/headers.py — Génération de actor_types.h et actor_api.h.

Entrées  : Project, liste (Actor, SpriteAsset), présence audio
Sorties  : fichiers écrits dans p.src_dir/
"""
from __future__ import annotations
import shutil
from typing import Optional

from core.models.components import CollisionBoxComponent
from core.models.sprite import AnimState, SpriteAsset
from core.models.scene import Actor
from core.project import Project
from codegen.c_names import sym as c_sym
from core.app_paths import RUNTIME_DIR


def generate_actor_types(
    p: Project,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,      # iterable de Prefab
) -> None:
    """Écrit actor_types_static.h (copie) et actor_types.h (généré)."""
    _types_static = RUNTIME_DIR / "include" / "actor_types_static.h"
    if _types_static.exists():
        shutil.copy2(_types_static, p.src_dir / "actor_types_static.h")

    h = [
        "/* actor_types.h — struct Actor partagée entre main.c et les scripts */",
        "/* Généré par GBA Editor */",
        "#ifndef ACTOR_TYPES_H",
        "#define ACTOR_TYPES_H",
        "#include <gba_types.h>",
        "",
    ]

    # Tags de boxes de collision
    box_tags: list[str] = []
    for actor, _ in scene_actors:
        for comp in actor.components:
            if isinstance(comp, CollisionBoxComponent) and comp.active:
                tag = comp.tag or "body"
                if tag not in box_tags:
                    box_tags.append(tag)
    if not box_tags:
        box_tags = ["body"]

    for ti, tag in enumerate(box_tags):
        h.append(f"#define BOXTAG_{c_sym(tag).upper()} {ti}")
    h.append("")
    h.append('#include "actor_types_static.h"')
    h.append("")

    # TAG_* pour les actors de scène
    for i, (actor, _) in enumerate(scene_actors):
        h.append(f"#define TAG_{c_sym(actor.name).upper()} {i}")

    # TAG_* pour les prefabs poolés (offset après les actors de scène), et la
    # géométrie de la plage — POOL_<SYM>_START / POOL_<SYM>_SIZE. Le script
    # transpilé en a besoin pour dimensionner son état par instance et pour
    # retrouver le slot d'un `self` (`self - &g_actors[START]`) ; il est compilé
    # une fois pour le PROJET et ne peut donc pas connaître ces bornes autrement.
    # Émis ici parce que c'est ici que l'offset est calculé — `_pool_info`
    # (main_gen) part du même total d'acteurs de scène, ces headers recevant les
    # acteurs de TOUTES les scènes.
    pool_offset = len(scene_actors)
    for pf in prefabs:
        if getattr(pf, "max_instances", 0) > 0:
            pf_s = c_sym(pf.name)
            h.append(f"#define TAG_{pf_s.upper()} {pool_offset}  /* prefab pool début */")
            h.append(f"#define POOL_{pf_s.upper()}_START {pool_offset}")
            h.append(f"#define POOL_{pf_s.upper()}_SIZE {pf.max_instances}")
            pool_offset += pf.max_instances

    h += ["", "#endif /* ACTOR_TYPES_H */", ""]
    (p.src_dir / "actor_types.h").write_text("\n".join(h), encoding="utf-8")


def generate_actor_api(
    p: Project,
    scene_actors: list[tuple[Actor, Optional[SpriteAsset]]],
    prefabs,
    has_sound: bool,
    all_scenes=None,   # liste de Scene — pour SCENE_IDX_* et scene_switch()
    max_actors: int | None = None,  # taille réelle du tableau g_actors
) -> None:
    """Écrit actor_api_static.h (copie) et actor_api.h (généré)."""
    # gba_font.h retiré : police 1bpp dont le consommateur (`text_init()`)
    # n'existe plus depuis l'asset Font — elle était encore recopiée dans
    # chaque build sans qu'aucune ligne ne la lise.
    for static_h in ("actor_api_static.h", "gba_engine.h"):
        src_h = RUNTIME_DIR / "include" / static_h
        if src_h.exists():
            shutil.copy2(src_h, p.src_dir / static_h)
    _api_static = RUNTIME_DIR / "include" / "actor_api_static.h"

    prefab_slots = sum(pf.max_instances for pf in prefabs if getattr(pf, "max_instances", 0) > 0)
    total_actors = max_actors if max_actors is not None else (len(scene_actors) + prefab_slots)

    a = [
        "/* actor_api.h — API runtime pour les scripts acteur */",
        "/* Généré par GBA Editor */",
        "#ifndef ACTOR_API_H",
        "#define ACTOR_API_H",
        '#include "actor_types.h"',
        "",
        f"#define G_ACTOR_COUNT {total_actors}",
        "",
        '#include "actor_api_static.h"',
        "",
    ]

    if has_sound:
        a += [
            "#include <maxmod.h>",
            "/* API audio — miroir direct des fonctions maxmod (mm_sound_effect, mmEffectEx,",
            "   mmEffectVolume/Panning/Cancel, mmStart/Pause/Resume/Stop/Active, mmSet*Volume). */",
            "/* Une référence d'effet vaut 0 quand maxmod n'en a pas donné : soit",
            "   aucun des 8 canaux n'était libre (l'effet ne sonne pas), soit les 16",
            "   handles étaient pris (il sonne, sans référence). Deux plafonds, et",
            "   un seul zéro — mesuré au désassemblage, cf. ROADMAP v0.8.6.",
            "   Un handle PÉRIMÉ ne fait rien : maxmod range un compteur dans le",
            "   handle et le relit à chaque appel, donc les cinq réglages ci-dessous",
            "   deviennent des non-opérations silencieuses. Rien à garder ici. */",
            "static inline int sfx_slot(mm_sfxhand h){return (int)(h & 0xFF) - 1;}",
            "/* La hauteur COURANTE de chaque effet, en facteur 6.10 (1024 = normale).",
            "   mmEffectRate n'est pas un facteur — il écrit la fréquence brute du",
            "   mixeur, inutilisable sans le taux d'origine de l'échantillon. Le seul",
            "   réglage relatif, mmEffectScaleRate, est CUMULATIF : sans mémoire du",
            "   facteur courant, set_pitch(120) appelé deux fois monterait deux fois.",
            "   16 entrées, comme le pool de handles de maxmod. Défini dans main.c. */",
            "extern mm_hword g_sfx_rate[16];",
            "/* `hold` dit si l'appelant TIENT cet effet (ROADMAP v0.8.8).",
            "   Mesuré dans mmAllocChannel : un canal libre est pris d'abord, sinon",
            "   le canal d'ARRIÈRE-PLAN le plus faible est volé, et un canal CUSTOM",
            "   ne l'est JAMAIS. Demander une référence (handle = 0) fait un canal",
            "   CUSTOM ; ne pas en vouloir (handle = 255) laisse le canal volable.",
            "   D'où la règle : ce qu'on tient est protégé, ce qu'on lâche peut céder",
            "   la place — au lieu que le neuvième bruitage d'une frame chargée soit",
            "   perdu en silence. */",
            "static inline mm_sfxhand sfx_play(int id, int volume, int hold){",
            "    mm_sound_effect ex;",
            "    ex.id = (mm_word)id; ex.rate = (mm_hword)1024;",
            "    ex.handle = (mm_hword)(hold ? 0 : 255);",
            "    ex.volume = (mm_byte)volume; ex.panning = (mm_byte)128;",
            "    mm_sfxhand h = mmEffectEx(&ex);",
            "    int s = sfx_slot(h);",
            "    if(s >= 0 && s < 16) g_sfx_rate[s] = 1024;",
            "    return h;",
            "}",
            "static inline void sfx_set_volume(mm_sfxhand h, int volume){mmEffectVolume(h,(mm_word)volume);}",
            "static inline void sfx_set_panning(mm_sfxhand h, int panning){mmEffectPanning(h,(mm_byte)panning);}",
            "static inline void sfx_stop(mm_sfxhand h){mmEffectCancel(h);}",
            "static inline int  sfx_is_playing(mm_sfxhand h){return (int)mmEffectActive(h);}",
            "static inline void sfx_set_pitch(mm_sfxhand h, int rate){",
            "    int s = sfx_slot(h);",
            "    if(s < 0 || s >= 16 || rate <= 0) return;",
            "    mmEffectScaleRate(h, (mm_word)(((mm_word)rate << 10) / g_sfx_rate[s]));",
            "    g_sfx_rate[s] = (mm_hword)rate;",
            "}",
            "static inline void sfx_set_effects_volume(int volume){mmSetEffectsVolume((mm_word)volume);}",
            "static inline void music_play(int id, int loop, int volume){",
            "    mmStart((mm_word)id, loop ? MM_PLAY_LOOP : MM_PLAY_ONCE);",
            "    mmSetModuleVolume((mm_word)volume);",
            "}",
            "static inline void music_stop(void){mmStop();}",
            "static inline void music_pause(void){mmPause();}",
            "static inline void music_resume(void){mmResume();}",
            "static inline int  music_is_playing(void){return mmActive();}",
            "static inline void music_set_volume(int volume){mmSetModuleVolume((mm_word)volume);}",
            "",
            "/* ── Jingle — la SEULE superposition de la console ──────────────── */",
            "/* mmJingle() est la deuxième couche de module de maxmod, avec son propre",
            "   scaler. C'est le seul endroit où deux sources musicales sonnent",
            "   ensemble — donc le seul endroit où un duck a un sens ici.",
            "   Trois contraintes matérielles, à respecter et non à contourner :",
            "     - il NE BOUCLE PAS : c'est une fanfare, jamais un thème ;",
            "     - il est plafonné à 4 canaux (doc maxmod), pris sur les 8 ;",
            "     - il n'y en a qu'UN à la fois. */",
            "static inline void music_jingle(int id, int volume){",
            "    mmJingle((mm_word)id);",
            "    mmSetJingleVolume((mm_word)volume);",
            "}",
            "static inline void music_jingle_volume(int volume){mmSetJingleVolume((mm_word)volume);}",
            "static inline int  music_jingle_playing(void){return mmActiveSub();}",
            "",
            "/* ── Boîtes à état sonores (ROADMAP v0.8.7) ─────────────────────── */",
            "/* Définies dans main.c, appelées depuis les scripts — qui sont d'autres",
            "   unités de compilation. Les tables, elles, restent privées à main.c :",
            "   seul son stepper d'animation les lit. */",
            "void sound_box_set_state(int state);",
            "void jingle_box_set_state(int state);",
            "void music_box_trigger(int trigger);",
            "",
            "/* ── Transitions musicales (ROADMAP v0.8.3) ─────────────────────── */",
            "/* DEUX transitions, et deux seulement, parce que le matériel n'en tient",
            "   pas plus : maxmod n'a qu'une couche de module qui boucle (mmJingle ne",
            "   boucle pas, par construction). Aucun fondu ENCHAÎNÉ n'est possible sur",
            "   cette console ; ne pas en reproposer un.",
            "     mode 1 — fondu traversant : le volume tombe à 0, on change, il remonte.",
            "              Marche entre deux morceaux quelconques ; laisse un creux.",
            "     mode 2 — coupe à la position : on attend la frontière de motif, puis on",
            "              démarre l'autre module au MÊME index d'ordre. Sans creux, en",
            "              mesure — c'est ce qui enchaîne deux variantes d'un morceau.",
            "   L'état vit dans main.c (une seule unité de compilation le porte). */",
            "extern int g_mtr_mode, g_mtr_id, g_mtr_loop, g_mtr_vol;",
            "extern int g_mtr_i, g_mtr_n, g_mtr_row;",
            "static inline void music_fade_to(int id, int loop, int volume, int frames){",
            "    /* Sous deux frames il n'y a pas de fondu à jouer : on bascule sec",
            "       plutôt que de faire semblant. */",
            "    if(frames < 2){ music_play(id, loop, volume); return; }",
            "    g_mtr_mode = 1; g_mtr_id = id; g_mtr_loop = loop; g_mtr_vol = volume;",
            "    g_mtr_i = 0; g_mtr_n = frames;",
            "}",
            "static inline void music_cut_to(int id, int loop, int volume){",
            "    /* Rien ne joue : il n'y a aucune position à respecter. */",
            "    if(!mmActive()){ music_play(id, loop, volume); return; }",
            "    g_mtr_mode = 2; g_mtr_id = id; g_mtr_loop = loop; g_mtr_vol = volume;",
            "    g_mtr_row = (int)mmGetPositionRow();",
            "}",
        ]
    else:
        a += [
            # Le type de la référence existe même sans son : un script qui
            # écrit `local pas = sfx.play(...)` se compile dans un projet où
            # aucun asset audio n'est encore importé, et échouerait sinon sur
            # un type inconnu plutôt que sur ce qui manque vraiment.
            "typedef int mm_sfxhand;",
            "static inline int  sfx_play(int id, int volume, int hold)"
            "{(void)id;(void)volume;(void)hold;return 0;}",
            "static inline void sfx_set_volume(int h, int volume){(void)h;(void)volume;}",
            "static inline void sfx_set_panning(int h, int panning){(void)h;(void)panning;}",
            "static inline void sfx_stop(int h){(void)h;}",
            "static inline int  sfx_is_playing(int h){(void)h;return 0;}",
            "static inline void sfx_set_pitch(int h, int rate){(void)h;(void)rate;}",
            "static inline void sfx_set_effects_volume(int volume){(void)volume;}",
            "static inline void music_play(int id, int loop, int volume){(void)id;(void)loop;(void)volume;}",
            "static inline void music_stop(void){}",
            "static inline void music_pause(void){}",
            "static inline void music_resume(void){}",
            "static inline int  music_is_playing(void){return 0;}",
            "static inline void music_set_volume(int volume){(void)volume;}",
            "static inline void music_jingle(int id, int volume){(void)id;(void)volume;}",
            "static inline void music_jingle_volume(int volume){(void)volume;}",
            "static inline int  music_jingle_playing(void){return 0;}",
            "static inline void sound_box_set_state(int s){(void)s;}",
            "static inline void jingle_box_set_state(int s){(void)s;}",
            "static inline void music_box_trigger(int t){(void)t;}",
            "static inline void music_fade_to(int id, int loop, int volume, int frames)"
            "{(void)id;(void)loop;(void)volume;(void)frames;}",
            "static inline void music_cut_to(int id, int loop, int volume)"
            "{(void)id;(void)loop;(void)volume;}",
        ]

    spawnable = [pf for pf in prefabs if getattr(pf, "max_instances", 0) > 0]
    if spawnable:
        a.append("")
        a.append("/* spawn_X() — défini dans main.c, visible par tous les scripts */")
        for pf in spawnable:
            a.append(f"extern int spawn_{c_sym(pf.name)}(int x, int y);")

    # Constantes ANIM_* par SpriteAsset — résolues à la compile par le transpileur
    done_sprites: set[str] = set()
    for _, sprite in scene_actors:
        if sprite and sprite.states and sprite.name not in done_sprites:
            done_sprites.add(sprite.name)
            a.append("")
            a.append(f"/* Animations : {sprite.name} */")
            for i, st in enumerate(sprite.states):
                a.append(f"#define ANIM_{c_sym(st.name).upper()} {i}")

    if all_scenes:
        a.append("")
        a.append("/* Indices de scènes — utilisés par scene.switch() */")
        for i, sc in enumerate(all_scenes):
            a.append(f"#define SCENE_IDX_{c_sym(sc.name).upper()} {i}")
        a += [
            "",
            "extern int g_next_scene;",
            "static inline void scene_switch(int idx){ g_next_scene = idx; }",
        ]

    # Constantes LAYER_* — un fond posé dans une scène (bg_slot 0-3), adressable
    # depuis un script (layer.set_scroll(LAYER_X, ...)) sans littéral magique.
    # `sym` (bg_layer_sym_for) inclut déjà le bg_slot → pas de collision entre
    # deux layers de la même scène référençant le même asset à des slots
    # différents. Dédupliquée : un layer partagé (même asset+slot) entre
    # plusieurs scènes ne produit qu'une seule constante.
    if all_scenes:
        from codegen.runtime_codegen.main_gen import bg_info
        seen_layer_syms: set[str] = set()
        layer_lines: list[str] = []
        for sc in all_scenes:
            for bi in bg_info(p, sc):
                sym_u = bi["sym"].upper()
                if sym_u in seen_layer_syms:
                    continue
                seen_layer_syms.add(sym_u)
                layer_lines.append(f"#define LAYER_{sym_u} {bi['bg']}")
        if layer_lines:
            a.append("")
            a.append("/* Fonds posés dans les scènes — un par (asset, bg_slot) unique */")
            a += layer_lines

    # Constantes CAM_* — l'index d'une caméra dans la table du runtime, tel que
    # `camera.switch(CAM_X)` l'attend. Même ordre que `project_cameras`, qui
    # émet la table : les deux dérivent de la même liste, sinon un script
    # activerait la mauvaise caméra.
    from codegen.runtime_codegen.main_gen import project_cameras
    _cams = project_cameras(p)
    if len(_cams) > 1:
        a.append("")
        a.append("/* Caméras du projet — utilisées par camera.switch() */")
        a.append("#define CAM_DEFAULT 0")
        for i, cam in enumerate(_cams):
            if cam is not None:
                a.append(f"#define CAM_{c_sym(cam.name).upper()} {i}")

    a += ["", "#endif /* ACTOR_API_H */", ""]
    (p.src_dir / "actor_api.h").write_text("\n".join(a), encoding="utf-8")
