/* SPDX-License-Identifier: Zlib
   Copyright (c) 2026 Yasor Rovic

   Licence zlib — PAS la GPL de l'éditeur (cf. runtime/LICENSE). Ce fichier est
   recopié dans le projet de l'utilisateur au build, puis compilé dans sa ROM :
   le jeu produit lui appartient entièrement, il peut le vendre, et il n'a
   aucune notice à joindre à sa ROM. */
/* actor_types_static.h — structs et constantes GBA (partie non générée).
   Inclus depuis actor_types.h (généré par build.py). */
#ifndef ACTOR_TYPES_STATIC_H
#define ACTOR_TYPES_STATIC_H

#define MAX_BOXES 4   /* boxes de collision max par acteur */

typedef struct CollisionBox {
    s8  x, y;   /* offset relatif au pivot (pixels) */
    u8  w, h;   /* dimensions (pixels) */
    u8  solid;  /* 1=physique, 0=trigger */
    u8  tag;    /* BOXTAG_* */
} CollisionBox;

/* Vec2/Vec3/Rect — les valeurs COMPOSÉES du sous-ensemble Lua (vec2(x,y),
   vec3(x,y,z), rect(x,y,w,h)). Des entiers, rien d'autre : pas de virgule
   flottante sur GBA. + et - composante à composante et * par un entier ne
   valent que pour vec2/vec3 — cf. actor_api_static.h (vec2_add et consorts)
   et scripting/vec_types.py côté transpileur, seul et même repère de type
   entre checker.py et codegen.py. */
typedef struct { int x, y; }    Vec2;
typedef struct { int x, y, z; } Vec3;
typedef struct { int x, y, w, h; } Rect;

/* UNE seule entité runtime — cf. ROADMAP v0.25, et ARCHITECTURE.md
   « Une seule entité runtime ». L'éditeur distingue trois choses (un actor, son
   sprite, le décor) ; le C n'a qu'une struct, et c'est assumé : un actor porte
   au plus un SpriteComponent, donc séparer coûterait un déréférencement par
   accès sur un ARM7TDMI sans cache pour un rapport 1:1. Le décor, lui, n'a pas
   de type parce que le calque EST le matériel (les layer_ et tilemap_ de
   gba_engine.h, indexées par le numéro de plan).

   Ce que le merge ne dispense pas de faire : nommer ses parties. Les deux blocs
   ci-dessous sont exactement les composants de l'éditeur —
   `sprite` ↔ SpriteComponent, `collision` ↔ CollisionBoxComponent — pour que le
   C émis se lise avec le vocabulaire de l'inspecteur, et pas un second. */
typedef struct Actor {
    /* Position et vélocité MONDE, en Q8 (256 = 1 pixel) depuis la ROADMAP
       v0.19 (2026-08-20) — le point fixe existait déjà dans cette même
       struct pour scale_x/y, il n'avait simplement jamais atteint la
       position. self.position (script) continue de ne rendre/accepter que
       des pixels entiers ; self.velocity, elle, expose le Q8 directement —
       rupture assumée plutôt qu'un second nom (self.velocity_q8) à côté du
       premier. self:apply_velocity() ajoute vx/vy à x/y SANS convertir :
       c'est exactement ce qui fait vivre le sous-pixel d'une frame à
       l'autre. */
    int x, y;               /* position monde, Q8 */
    int vx, vy;             /* vélocité, Q8 */
    int timer;             /* compteur interne (animation, délai…) */
    int tag;               /* TAG_* — type de l'acteur */
    int active;            /* 0 = ignoré (update + rendu désactivés) */
    int visible;           /* 0 = OAM caché */
    int flip_h;            /* 1 = miroir horizontal */
    int flip_v;            /* 1 = miroir vertical */
    int dir_x;             /* direction X courante : -1 | 0 | 1 */
    int dir_y;             /* direction Y courante : -1 | 0 | 1 */
    int pal_bank;          /* palette OAM (0-15) — modifiable via self.pal */
    int obj_mode;          /* 0=normal, 1=semi-transparent, 2=fenêtre-objet (OBJWIN) */
    /* Ordre d'affichage face aux BG layers (OAM attr2 bits 10-11), 0=devant
       tous, 3=derrière tous — self.priority. Posée au build depuis la valeur
       authorée (Actor.priority côté éditeur, 0 pour un acteur poolé — sans
       sens pour un template, cf. core/models/scene.py), modifiable ensuite
       comme pal_bank/obj_mode : ce sont les trois mêmes registres OAM,
       aucune raison qu'un seul des trois soit figé. */
    int priority;
    /* Transform MONDE (cf. ARCHITECTURE.md « Le modèle affine »). C'est de
       l'ÉTAT DE JEU : toujours lisible et écrivable, avec ou sans slot de
       matrice affine. Ce qui décide s'il se VOIT est `sprite.affine_slot`.

       Champs PAR-ACTOR et non par slot : un script de prefab poolé est une
       fonction C partagée par toutes ses instances, mais chaque instance a sa
       propre struct Actor (donc ses propres valeurs) et un slot différent.
       Un global par slot aurait exigé de connaître le slot à l'écriture et
       violait l'inclusion mono-texte des headers (copie `static` par TU). */
    int rotation;          /* monde, degrés 0-359 (self.rotation) */
    int scale_x;           /* monde, Q8 (256 = 100%) — self.scale */
    int scale_y;           /* monde, Q8 */

    /* ── sprite ↔ SpriteComponent ─────────────────────────────────────
       Le RENDU de l'acteur. Sa DÉFINITION, elle, n'est pas ici : les états, les
       directions et les vitesses vivent en ROM, dans les tables
       `sprite_{nom}_anim_dirs/_state_start/_state_speed/_state_loop` émises par
       main_gen. La coupure est const/variable, pas classe/classe. */
    struct {
        int frame;         /* index de frame dans le spritesheet */
        int anim_state;    /* index de l'AnimState courant */
        /* Surcharge de la vitesse (ticks entre deux frames) de l'état courant —
           même mécanisme que UIImageInfo.speed (cf. gba_engine.h), amené sur
           l'acteur. 0 = la vitesse réglée pour cet état dans le Sprite Editor,
           qui reste la source de vérité (self.anim_speed). Ne se remet pas à 0
           tout seul quand l'état change : un effet temporaire (temps ralenti)
           se referme explicitement par le script qui l'a ouvert. */
        int anim_speed;
        /* Écrits à CHAQUE tick d'animation par main_gen._anim_tick_lines. Ce
           n'est PAS une duplication des tables ROM : `anim_length` est la
           longueur du bloc de la DIRECTION actuellement jouée, que le tick
           trouve par un parcours de `anim_dirs[]` avec repli sur la direction
           omni. Ces trois champs MÉMOÏSENT ce parcours — un script qui lit
           self.anim_length ne le refait pas. (Évalué puis écarté en v0.25 :
           exposer les tables aux scripts déplacerait la boucle dans chaque
           lecture.)
             anim_length   : nombre de frames de la direction actuellement jouée
                             de l'état courant (self.anim_length).
             anim_loop     : 1 = l'état courant boucle (self.anim_loop).
             anim_finished : 1 = état NON bouclé, actuellement sur sa dernière
                             frame — reste vrai tant qu'on n'a pas changé
                             d'état, comme `collision.grounded` reste vrai tant
                             qu'on ne quitte pas le sol (self.anim_finished). */
        int anim_length;
        int anim_loop;
        int anim_finished;
        /* Taille de frame du sprite, en pixels — posée une fois à l'init/au
           spawn depuis SpriteAsset.frame_w/frame_h (self.frame_w/self.frame_h,
           lecture seule). Utile pour centrer un effet ou trouver les bords d'un
           AUTRE acteur (other.frame_w) sans dupliquer sa géométrie dans un
           script. Par instance et non en #define : le script d'un prefab poolé
           est une fonction C partagée par toutes ses instances. */
        int frame_w, frame_h;
        int auto_dir;      /* 1 = recalcule dir_x/dir_y depuis vx/vy chaque frame */
        /* Transform LOCAL, composé PAR-DESSUS le monde (self.sprite_rotation /
           self.sprite_scale / self.sprite_offset) : la rotation s'AJOUTE à la
           rotation monde, le scale se MULTIPLIE par le scale monde, l'offset
           déplace le sprite dans le repère de l'actor (il tourne et scale avec
           lui). Le sprite n'a pas de position monde : elle reste x/y. */
        int rotation;      /* local, degrés */
        int scale_x;       /* local, Q8 */
        int scale_y;       /* local, Q8 */
        int offset_x;      /* local, pixels */
        int offset_y;      /* local, pixels */
        /* Slot de matrice affine OAM (0-31), ou -1. Réservé au build à tout
           sprite dont « Affine transform » est coché (cf. main_gen.
           _compute_affine_info) — c'est une capacité de RENDU, d'où sa place
           ici et non à la racine. -1 = OAM normale : le transform monde de
           l'acteur et le transform local ci-dessus gardent leur valeur, mais
           aucune matrice n'est écrite et rien ne les affiche. */
        int affine_slot;
    } sprite;

    /* ── collision ↔ CollisionBoxComponent ────────────────────────────── */
    struct {
        /* Résolution contre la carte de collision — écrits par
           resolve_actor_tiles, lus par elle à la frame suivante (cf. ROADMAP
           v0.6.3) :
             grounded : y avait-il un sol sous les pieds à la fin de la frame ?
                        C'est ce que rend actor_on_ground() ;
             last_x   : abscisse à la fin de la frame précédente, en PIXELS (pas
                        Q8, contrairement à x — resolve_actor_tiles travaille en
                        pixels du début à la fin, cf. gba_engine.h, ROADMAP
                        v0.19). Le déplacement horizontal RÉELLEMENT parcouru
                        s'en déduit, quelle que soit la façon dont le script
                        bouge l'acteur (vélocité, move(), move_to(),
                        set_position()) — c'est lui qui donne la distance de
                        collage en descente, sans réglage à exposer. */
        int grounded;
        int last_x;
        /* Reste de la correction de vitesse en pente, en 1/256 de pixel. Sans ce
           report, un pas de 2 px sur une pente à 45° tomberait toujours sur 1 px
           (troncature) et le personnage ramperait au lieu d'aller 1,41 fois
           moins vite. */
        int slope_acc;
        int box_count;     /* nombre de boxes actives (0..MAX_BOXES) */
        CollisionBox boxes[MAX_BOXES];
    } collision;
} Actor;

/* Masques boutons */
#define BTN_A      0x0001
#define BTN_B      0x0002
#define BTN_SELECT 0x0004
#define BTN_START  0x0008
#define BTN_RIGHT  0x0010
#define BTN_LEFT   0x0020
#define BTN_UP     0x0040
#define BTN_DOWN   0x0080
#define BTN_R      0x0100
#define BTN_L      0x0200

#endif /* ACTOR_TYPES_STATIC_H */
