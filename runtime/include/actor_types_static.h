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
    int pal_bank;          /* palette OAM (0-15) — modifiable via set_pal() */
    int data[8];           /* variables locales par instance (prefabs poolés) */
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
