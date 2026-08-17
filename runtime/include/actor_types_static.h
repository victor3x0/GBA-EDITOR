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

typedef struct Actor {
    int x, y;              /* position monde */
    int vx, vy;            /* vélocité */
    int frame;             /* index de frame dans le spritesheet */
    int timer;             /* compteur interne (animation, délai…) */
    int anim_state;        /* index de l'AnimState courant */
    int auto_dir;          /* 1 = recalcule dir_x/dir_y depuis vx/vy chaque frame */
    int tag;               /* TAG_* — type de l'acteur */
    int active;            /* 0 = ignoré (update + rendu désactivés) */
    int visible;           /* 0 = OAM caché */
    int flip_h;            /* 1 = miroir horizontal */
    int flip_v;            /* 1 = miroir vertical */
    int dir_x;             /* direction X courante : -1 | 0 | 1 */
    int dir_y;             /* direction Y courante : -1 | 0 | 1 */
    int pal_bank;          /* palette OAM (0-15) — modifiable via self.pal */
    int obj_mode;          /* 0=normal, 1=semi-transparent, 2=fenêtre-objet (OBJWIN) */
    /* Transformation affine (cf. ARCHITECTURE.md « Le modèle affine »).
       `affine_slot` est un slot de matrice affine OAM (0-31), ou -1 : réservé au
       build à tout actor dont `affine_transform` est coché (cf. main_gen.
       _compute_affine_info). Les champs ci-dessous ne sont lus QUE si
       affine_slot >= 0 ; sinon l'acteur est émis en OAM normale.

       Transform MONDE (self.rotation / self.scale) :
         rotation  — degrés 0-359
         scale_x/y — Q8 (256 = 100%)
       Transform LOCAL du sprite (self.sprite_rotation / self.sprite_scale /
       self.sprite_offset), composé PAR-DESSUS le monde :
         sprite_rot      — degrés, AJOUTÉ à la rotation monde
         sprite_scale_*  — Q8, MULTIPLIÉ par le scale monde
         offset_x/y      — pixels, position du sprite RELATIVE à l'actor dans le
                           repère local (tourne/scale avec l'actor). Le sprite
                           n'a pas de position monde : la position monde reste x/y.
       Champs PAR-ACTOR et non par slot : un script de prefab poolé est une
       fonction C partagée par toutes ses instances, mais chaque instance a sa
       propre struct Actor (donc ses propres valeurs) et un slot différent.
       Un global par slot aurait exigé de connaître le slot à l'écriture et
       violait l'inclusion mono-texte des headers (copie `static` par TU). */
    int affine_slot;
    int rotation;          /* monde, degrés 0-359 */
    int scale_x;           /* monde, Q8 (256 = 100%) */
    int scale_y;           /* monde, Q8 */
    int sprite_rot;        /* local, degrés */
    int sprite_scale_x;    /* local, Q8 */
    int sprite_scale_y;    /* local, Q8 */
    int offset_x;          /* local, pixels */
    int offset_y;          /* local, pixels */
    /* Résolution contre la carte de collision — écrits par resolve_actor_tiles,
       lus par elle à la frame suivante (cf. ROADMAP v0.6.3) :
         grounded : y avait-il un sol sous les pieds à la fin de la frame ?
                    C'est ce que rend actor_on_ground() ;
         last_x   : abscisse à la fin de la frame précédente. Le déplacement
                    horizontal RÉELLEMENT parcouru s'en déduit, quelle que soit
                    la façon dont le script bouge l'acteur (vélocité, move(),
                    move_to(), set_position()) — c'est lui qui donne la
                    distance de collage en descente, sans réglage à exposer. */
    int grounded;
    int last_x;
    /* Reste de la correction de vitesse en pente, en 1/256 de pixel. Sans ce
       report, un pas de 2 px sur une pente à 45° tomberait toujours sur 1 px
       (troncature) et le personnage ramperait au lieu d'aller 1,41 fois moins
       vite. */
    int slope_acc;
    int box_count;         /* nombre de boxes actives (0..MAX_BOXES) */
    CollisionBox boxes[MAX_BOXES];
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
