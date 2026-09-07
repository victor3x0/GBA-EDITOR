"""codegen/runtime_codegen/gen_sprite.py — l'émetteur du domaine sprite/animation.

Extrait de `main_gen` (A3), au-dessus de la couche de requêtes (il n'en a pas
besoin : il ne dépend que de `grit_conversion`/`c_names`, vers le bas). Deux
familles :
  - `frame_action_ids`/`frame_sfx_syms` rendent la DONNÉE par frame (action de
    SoundBox, Sfx direct) ;
  - `anim_tables_for`/`anim_tick_lines`/`actor_frame_event_lines` ÉMETTENT le C
    des tables d'animation et du bloc de tick.

`_actor_script_functions` (et son cache) restent privés : seul
`actor_frame_event_lines` les consomme, ils ne traversent pas ce module.
"""
from __future__ import annotations

from typing import Optional

from core.models.sprite import SpriteAsset
from core.models.scene import Actor
from core.project import Project
from codegen.c_names import sym as c_sym
from codegen.grit_conversion import sprite_unique_frames, seq_key


def frame_action_ids(p: Project, sprite: SpriteAsset) -> list[int]:
    """L'ACTION de chaque frame du sprite, dans l'ordre ABSOLU des frames.

    Source de vérité unique pour la table émise et pour le test du stepper : les
    deux doivent voir exactement la même liste, sinon on émet un test qui lit
    une table absente.

    Une frame nomme une action (« pas »), jamais un effet : c'est l'état
    courant de la SoundBox qui dit vers quel échantillon elle pointe. L'index
    vient de `Project.sound_action_names()`, COMMUN au projet — une frame ne
    sait pas quelle SoundBox sera active quand elle se jouera.

    Un nom qu'aucun graphe ne déclare rend -1. C'est le cas le plus courant
    aujourd'hui (aucun graphe n'existe encore) et c'est volontairement le
    comportement le plus inoffensif : silencieux plutôt que faux. Le validateur,
    lui, le signale — pour que « silencieux » ne veuille pas dire « invisible ».
    """
    actions = p.sound_action_names("sound_box")
    index = {name: i for i, name in enumerate(actions)}
    _, ordered = sprite_unique_frames(sprite)
    return [index.get(getattr(fr, "action_name", "") or "", -1)
            for fr, _fh, _fv in ordered]


def frame_sfx_syms(p: Project, sprite: SpriteAsset) -> list[tuple[str, int]]:
    """Le Sfx DIRECT de chaque frame du sprite (ROADMAP v0.8.9), dans l'ordre
    ABSOLU des frames — même patron que `frame_action_ids`, mais résolu au
    nom du Sfx lui-même : pas d'indirection par un espace de noms d'actions,
    `AnimFrame.direct_sfx_name` VISE déjà un Sfx du projet. La constante `SFX_*`
    existe forcément (cf. `referenced_sound_names`, source ⑤) puisque
    `resolve_sound_assets` garde tout Sfx cité par une frame.

    Retourne (symbole C du volume, ou "-1") — le volume vient de la ressource
    Sfx elle-même, même lecture que `self:play_sfx()`/`sfx.play()`
    (`Sfx.volume` → `volume_to_effect`), pas d'un réglage propre à la frame.

    Un nom qui ne correspond à aucun Sfx du projet rend ("-1", 0) — signalé
    par le validateur (`_check_sound_boxes`), silencieux ici plutôt que faux.
    """
    from codegen.c_names import c_ident
    from core.models.audio import volume_to_effect
    by_name = {s.name: s for s in getattr(p, "sfx", [])}
    _, ordered = sprite_unique_frames(sprite)
    out = []
    for fr, _fh, _fv in ordered:
        name = getattr(fr, "direct_sfx_name", "") or ""
        sfx = by_name.get(name)
        if sfx is not None:
            out.append((f"SFX_{c_ident(name)}", volume_to_effect(sfx.volume)))
        else:
            out.append(("-1", 0))
    return out


_actor_fn_cache: dict = {}


def _actor_script_functions(p: Project, actor: Actor) -> set[str]:
    """Les noms de fonctions top-level déclarées dans le script Lua de cet
    actor — même lecture que `ValidationContext.script_functions`
    (core/validator.py), mais indépendante : le build n'a pas de
    ValidationContext sous la main ici. Cache module-level : plusieurs actors
    de la même scène partagent parfois le même fichier de script."""
    comp = actor.get_component("script")
    if not comp or not comp.active or not comp.script:
        return set()
    sp = p.asset_abs(comp.script)
    if not sp or not sp.exists():
        return set()
    key = str(sp)
    if key not in _actor_fn_cache:
        from scripting.parser import parse as lua_parse, LuaParseError
        try:
            script = lua_parse(sp.read_text(encoding="utf-8"))
            _actor_fn_cache[key] = {fn.name for fn in script.functions}
        except (LuaParseError, OSError):
            _actor_fn_cache[key] = set()
    return _actor_fn_cache[key]


def actor_frame_event_lines(p: Project, actor: Actor, sprite: SpriteAsset) -> tuple[list[str], bool]:
    """Table de pointeurs de fonction EventCall pour CET actor (ROADMAP
    v0.8.9) — PAS pour son sprite : contrairement à `frame_action_ids`/
    `frame_sfx_syms`, la cible d'un EventCall est une fonction du script de
    l'actor, donc deux actors qui partagent le même sprite peuvent résoudre
    le même `event_name` vers deux fonctions différentes (ou aucune). La
    table est donc nommée par ACTOR (`{actor_sym}_frame_event`), pas par
    sprite, et régénérée pour chaque actor qui en a besoin.

    Un event qui ne correspond à aucune fonction déclarée dans le script
    résout vers NULL — averti par le validateur (`_check_frame_events`),
    silencieux ici comme les deux autres emplacements plutôt que de casser
    le lien."""
    declared = _actor_script_functions(p, actor)
    if not declared:
        return [], False
    asym = c_sym(actor.name)
    _, ordered = sprite_unique_frames(sprite)
    entries: list[str] = []
    used: set[str] = set()
    for fr, _fh, _fv in ordered:
        name = getattr(fr, "event_name", "") or ""
        if name and name in declared:
            entries.append(f"&{asym}_{name}")
            used.add(name)
        else:
            entries.append("0")
    if not used:
        return [], False
    L = [f"extern void {asym}_{name}(Actor*);" for name in sorted(used)]
    L.append(f"static void (* const {asym}_frame_event[])(Actor*) = {{{','.join(entries)}}};")
    return L, True


def anim_tables_for(p: Project, sprite: SpriteAsset) -> list[str]:
    """Génère les tables C d'animation pour un SpriteAsset.

    Produit :
      {sym}_anim_dirs[]   — {dir, frame_start, frame_count} par état+direction
      {sym}_state_start[] — index dans anim_dirs où commence chaque état
      {sym}_state_speed[] — speed (ticks) par état
      {sym}_state_loop[]  — loop (0/1) par état
    """
    sym = f"sprite_{c_sym(sprite.name)}"
    entries: list[str] = []          # "{dir,start,count}"
    state_starts: list[int] = []
    state_speeds: list[int] = []
    state_loops: list[int] = []

    # seq_starts fait autorité sur le layout du sheet : chaque direction occupe
    # un bloc contigu [start, start+count) — le runtime joue frame=start+k.
    seq_starts, _ = sprite_unique_frames(sprite)

    for state in sprite.states:
        state_starts.append(len(entries))
        state_speeds.append(state.speed)
        state_loops.append(1 if state.loop else 0)
        dir_map = {sd.dir: sd for sd in state.directions}
        for sd in state.directions:
            src_sd = dir_map.get(sd.mirror_of, sd) if sd.mirror_of is not None else sd
            start = seq_starts[seq_key(src_sd, sd.flip_h, sd.flip_v)]
            count = len(src_sd.frames)
            entries.append(f"{{{sd.dir},{start},{count}}}")
        entries.append("{255,0,0}")   # sentinel de fin d'état

    # Effets posés sur les frames. `ordered` fait autorité sur l'index absolu de
    # frame — le même layout que le sheet reconstruit — donc la table s'indexe
    # directement par `Actor.frame`.
    #
    # Conséquence ASSUMÉE de la déduplication par séquence : une source et son
    # miroir partagent leur bloc, donc leur effet. C'est voulu (le pas est le
    # même à gauche et à droite) ; deux états identiques le partagent aussi, et
    # qui veut les différencier renonce au miroir (ROADMAP v0.8.5).
    frame_actions = frame_action_ids(p, sprite)

    L: list[str] = [
        f"static const u8 __attribute__((unused)) {sym}_anim_dirs[][3] = {{",
        "    " + ",".join(entries),
        "};",
        f"static const u8 __attribute__((unused)) {sym}_state_start[] = {{{','.join(str(x) for x in state_starts)}}};",
        f"static const u8 __attribute__((unused)) {sym}_state_speed[] = {{{','.join(str(x) for x in state_speeds)}}};",
        f"static const u8 __attribute__((unused)) {sym}_state_loop[]  = {{{','.join(str(x) for x in state_loops)}}};",
    ]
    # Émise SEULEMENT si au moins une frame porte un emplacement : une table de
    # -1 serait de la ROM dépensée pour rien, et un test par frame pour rien.
    #
    # Ce qui est émis est un id d'EMPLACEMENT, pas un effet : c'est l'état
    # courant de la machine SFX qui dit vers quel échantillon il pointe, et le
    # runtime le lit dans `g_sound_box_action[]`. C'est ce qui permet au même cycle de
    # marche de sonner « sable » ou « cailloux » sans être authoré deux fois.
    if any(a >= 0 for a in frame_actions):
        L += [
            "/* Emplacement joué en arrivant sur la frame — -1 = aucun. */",
            f"static const s16 {sym}_frame_action[] = {{{','.join(str(a) for a in frame_actions)}}};",
        ]
    # Sfx DIRECT par frame (ROADMAP v0.8.9) — même garde qu'au-dessus : une
    # table de -1 ne vaut pas la ROM qu'elle coûterait.
    frame_sfx = frame_sfx_syms(p, sprite)
    if any(s != "-1" for s, _v in frame_sfx):
        L += [
            "/* Sfx joué directement en arrivant sur la frame — -1 = aucun. */",
            f"static const s16 {sym}_frame_sfx[] = {{{','.join(s for s, _v in frame_sfx)}}};",
            f"static const u8  {sym}_frame_sfxv[] = {{{','.join(str(v) for _s, v in frame_sfx)}}};",
        ]
    return L


def anim_tick_lines(idx: int, sym: str, has_frame_sfx: bool = False,
                    has_frame_direct_sfx: bool = False,
                    event_lines: Optional[list[str]] = None,
                    has_frame_events: bool = False,
                    actor_sym: str = "") -> list[str]:
    """Génère le bloc C de tick d'animation pour un acteur (dans scene_tick).

    `has_frame_sfx` dit si le sprite porte des ACTIONS de SoundBox sur ses
    frames (`{sym}_frame_action[]`), `has_frame_direct_sfx` s'il porte des Sfx
    DIRECTS (`{sym}_frame_sfx[]`, ROADMAP v0.8.9) — deux tables indépendantes,
    chacune son propre test, pour ne pas payer une comparaison par frame et
    par acteur sur les sprites qui n'en portent aucune.

    `event_lines`/`has_frame_events`/`actor_sym` : EventCall (ROADMAP v0.8.9).
    Contrairement aux deux précédents, la table (`{actor_sym}_frame_event`,
    cf. `actor_frame_event_lines`) est par ACTOR et non par sprite — deux
    actors qui partagent un sprite peuvent résoudre le même `event_name` vers
    deux fonctions différentes. Elle est donc déclarée `static` ICI, en
    portée LOCALE à ce bloc (un `static` de fonction est légal en C, même
    patron que `_dlut` juste en dessous), plutôt qu'au niveau fichier.
    """
    return [
        f"    if(g_actors[{idx}].sprite.auto_dir&&(g_actors[{idx}].vx||g_actors[{idx}].vy)){{",
        f"        g_actors[{idx}].dir_x=(g_actors[{idx}].vx>0)-(g_actors[{idx}].vx<0);",
        f"        g_actors[{idx}].dir_y=(g_actors[{idx}].vy>0)-(g_actors[{idx}].vy<0);",
        f"    }}",
        # dir_x/dir_y → indice 1-8 (NW=8,N=1,NE=2,W=7,0=0,E=3,SW=6,S=5,SE=4)
        f"    {{",
        *([f"        {line}" for line in event_lines] if has_frame_events and event_lines else []),
        f"        static const s8 _dlut[3][3]={{{{8,1,2}},{{7,0,3}},{{6,5,4}}}};",
        f"        int _ad=_dlut[g_actors[{idx}].dir_y+1][g_actors[{idx}].dir_x+1];",
        f"        int _st=g_actors[{idx}].sprite.anim_state;",
        f"        int _b={sym}_state_start[_st];",
        f"        int _fs=0,_fc=1,_fb=-1,_fbc=1;",
        f"        for(int _e=_b;{sym}_anim_dirs[_e][0]!=255;_e++){{",
        f"            if({sym}_anim_dirs[_e][0]==_ad){{_fs={sym}_anim_dirs[_e][1];_fc={sym}_anim_dirs[_e][2];goto _af{idx};}}",
        f"            if({sym}_anim_dirs[_e][0]==0){{_fb={sym}_anim_dirs[_e][1];_fbc={sym}_anim_dirs[_e][2];}}",
        f"        }}",
        f"        if(_fb>=0){{_fs=_fb;_fc=_fbc;}}",
        f"        _af{idx}:;",
        # RESYNC : `frame` peut être hors de [_fs, _fs+_fc) — self:play_anim
        # le remet à 0 (frame ABSOLUE dans le sheet dédupliqué du sprite en
        # entier), qui ne tombe dans le bloc du nouvel état que si celui-ci
        # commence pile à 0 ; il en va de même en tournant vers une direction
        # dont le bloc de frames diffère. Sans ce recalage, `_fi` ci-dessous
        # part négatif et l'animation affiche des frames d'un AUTRE état le
        # temps de quelques ticks de vitesse, avant de reconverger par hasard.
        f"        if(g_actors[{idx}].sprite.frame<_fs||g_actors[{idx}].sprite.frame>=_fs+_fc){{",
        f"            g_actors[{idx}].sprite.frame=_fs; g_actors[{idx}].timer=0;",
        f"        }}",
        f"        g_actors[{idx}].timer++;",
        # self.anim_speed surcharge la vitesse de l'état ; 0 = celle du sprite
        # (même règle que UIImageInfo.speed, cf. ARCHITECTURE.md « Animation »).
        f"        int _asp=g_actors[{idx}].sprite.anim_speed?g_actors[{idx}].sprite.anim_speed:{sym}_state_speed[_st];",
        f"        if(g_actors[{idx}].timer>=_asp){{",
        f"            g_actors[{idx}].timer=0;",
        f"            int _fi=g_actors[{idx}].sprite.frame-_fs;",
        f"            int _fprev=g_actors[{idx}].sprite.frame;",
        f"            if({sym}_state_loop[_st]) g_actors[{idx}].sprite.frame=_fs+(_fc>1?(_fi+1)%_fc:0);",
        f"            else if(_fi<_fc-1) g_actors[{idx}].sprite.frame=_fs+_fi+1;",
        # L'effet se déclenche en ARRIVANT sur la frame, donc seulement quand
        # elle change — sinon une animation d'une seule frame, ou arrêtée sur
        # sa dernière, rejouerait le son à chaque tick de vitesse.
        *(([f"            if(g_actors[{idx}].sprite.frame!=_fprev){{"]
           + ([f"                int _ac={sym}_frame_action[g_actors[{idx}].sprite.frame];",
               # L'indirection : l'emplacement, puis ce vers quoi l'état courant le
               # résout. Un emplacement non réglé dans cet état vaut -1 et ne joue
               # rien — « pas de bruit de pas en vol » se dit sans réglage dédié.
               f"                if(_ac>=0&&g_sound_box_action[_ac]>=0)",
               f"                    sfx_play(g_sound_box_action[_ac],g_sound_box_action_vol[_ac],0);"]
              if has_frame_sfx else [])
           + ([f"                int _as={sym}_frame_sfx[g_actors[{idx}].sprite.frame];",
               f"                if(_as>=0) sfx_play(_as,{sym}_frame_sfxv[g_actors[{idx}].sprite.frame],0);"]
              if has_frame_direct_sfx else [])
           + ([f"                void (*_ev)(Actor*)={actor_sym}_frame_event[g_actors[{idx}].sprite.frame];",
               f"                if(_ev) _ev(&g_actors[{idx}]);"]
              if has_frame_events else [])
           + [f"            }}"]) if (has_frame_sfx or has_frame_direct_sfx or has_frame_events)
          else [f"            (void)_fprev;"]),
        f"        }}",
        # self.anim_length / anim_loop / anim_finished (recopiés à CHAQUE
        # tick, pas seulement quand la frame avance) : {sym}_state_loop[] est
        # `static` dans ce fichier, invisible d'un script — c'est ce qui force
        # à recopier sur l'Actor plutôt que d'exposer les tables telles
        # quelles. Le recalage ci-dessus garantit `frame` dans [_fs,_fs+_fc) :
        # « finished » se lit donc directement dessus — vrai dès que la
        # position dans la séquence (frame-_fs, 0-based) a atteint la
        # DERNIÈRE case de sa longueur (anim_length), et reste vrai tant que
        # l'état ne change pas, comme `grounded` reste vrai tant qu'on ne
        # quitte pas le sol. Toujours faux pour un état qui boucle : il n'a
        # pas de dernière frame, il n'a qu'une case suivante.
        f"        g_actors[{idx}].sprite.anim_length = _fc;",
        f"        g_actors[{idx}].sprite.anim_loop = {sym}_state_loop[_st];",
        f"        g_actors[{idx}].sprite.anim_finished = !{sym}_state_loop[_st] "
        f"&& (g_actors[{idx}].sprite.frame - _fs) >= _fc - 1;",
        f"    }}",
    ]
