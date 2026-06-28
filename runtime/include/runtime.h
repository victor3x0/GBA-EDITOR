/*
 * runtime.h — API partagée entre main.c généré et les scripts acteur.
 *
 * Les scripts Lua sont transpilés en C par l'éditeur. Ce header définit :
 *   - la struct Actor (état d'un acteur à l'exécution)
 *   - les handlers d'événement (pointeurs de fonctions)
 *   - les prototypes de l'API runtime appelable depuis les scripts
 *   - les constantes GBA (boutons, tags acteur, IDs anim/sfx)
 *
 * Toutes les fonctions qui prennent un nom Lua (string) reçoivent ici
 * un entier résolu à la compilation par le transpileur (ANIM_*, SFX_*,
 * TAG_*, KEY_*). Zéro malloc, zéro string à runtime.
 */

#ifndef RUNTIME_H
#define RUNTIME_H

#include <gba_types.h>
#include <gba_input.h>    /* KEY_A, KEY_B, KEY_LEFT … */

/* ─── Constantes boutons (alias lisibles dans les scripts) ─── */
#define BTN_A       KEY_A
#define BTN_B       KEY_B
#define BTN_L       KEY_L
#define BTN_R       KEY_R
#define BTN_START   KEY_START
#define BTN_SELECT  KEY_SELECT
#define BTN_UP      KEY_UP
#define BTN_DOWN    KEY_DOWN
#define BTN_LEFT    KEY_LEFT
#define BTN_RIGHT   KEY_RIGHT

/* ─── Tags acteur ─────────────────────────────────────────── */
/* Générés par build.py : TAG_NomActor = index dans actors[]   */
/* Exemple : TAG_HERO 0, TAG_ENEMY 1 …                         */

/* ─── Forward-declaration ────────────────────────────────── */
typedef struct Actor Actor;

/* ─── Handlers d'événement ───────────────────────────────── */
typedef void (*EvHandler)      (Actor* self);
typedef void (*CollideHandler) (Actor* self, Actor* other, u8 my_box, u8 other_box);

/* ─── Struct Actor ───────────────────────────────────────── */
struct Actor {
    /* Transform monde */
    int x, y;
    int vx, vy;         /* vélocité (utilisée par actor_move_velocity) */

    /* Animation */
    int anim;           /* ID anim courante (ANIM_*) */
    int frame;          /* frame dans l'anim */
    int frame_timer;    /* compteur de ticks avant frame suivante */

    /* Logique */
    int tag;            /* TAG_* — type de cet acteur */
    int active;         /* 0 = skip update + collision */
    int visible;        /* 0 = OAM caché */

    /* Collision box (espace monde, relative à x/y) */
    int cb_x, cb_y;
    int cb_w, cb_h;

    /* Handlers — initialisés par main.c généré */
    EvHandler      on_start;
    EvHandler      on_update;
    EvHandler      on_button_a;
    EvHandler      on_button_b;
    EvHandler      on_button_l;
    EvHandler      on_button_r;
    EvHandler      on_button_start;
    EvHandler      on_button_select;
    CollideHandler on_collide;
};

/* ─── Table globale des acteurs ──────────────────────────── */
/* Définie dans main.c généré ; visible par tous les scripts. */
extern Actor  g_actors[];
extern int    g_actor_count;

/* ─── API Mouvement ──────────────────────────────────────── */
void actor_set_pos     (Actor* self, int x, int y);
void actor_move        (Actor* self, int dx, int dy);
void actor_set_velocity(Actor* self, int vx, int vy);
void actor_apply_velocity(Actor* self);   /* x+=vx, y+=vy */

/* ─── API Animation ──────────────────────────────────────── */
void actor_play_anim   (Actor* self, int anim_id);  /* ANIM_* */
void actor_set_frame   (Actor* self, int frame);
void actor_set_visible (Actor* self, int visible);

/* ─── API Input ──────────────────────────────────────────── */
/* Appelé depuis on_update ; état du clavier mis à jour par main.c */
int  input_held   (int btn);   /* BTN_* — tenu enfoncé */
int  input_pressed(int btn);   /* BTN_* — front montant ce frame */

/* ─── API Audio ──────────────────────────────────────────── */
void sfx_play   (int sfx_id);    /* SFX_*  — one-shot */
void music_play (int music_id);  /* MUSIC_* — boucle */
void music_stop (void);

/* ─── API Globals ─────────────────────────────────────────── */
/* Les variables globales Lua sont générées dans globals.c/.h.  */
/* Ces helpers permettent l'accès par index pour le codegen.    */
/* En pratique le transpileur émet des accès directs (g_score)  */
/* plutôt que ces appels ; ils restent disponibles pour usage   */
/* avancé (tables de scores, flags d'événement…).               */
int  global_get(int id);
void global_set(int id, int value);

/* ─── API Communication inter-actors ─────────────────────── */
/* send() appelle directement la fonction handler de la cible.  */
/* Le transpileur résout target_name → appel C à la compilation */
/* (pas de lookup runtime). broadcast() itère g_actors[].       */
void actor_send     (Actor* target, int event_id, int value);
void actor_broadcast(int event_id, int value);

/* ─── Utilitaires ─────────────────────────────────────────── */
int  aabb_overlap(const Actor* a, const Actor* b);
int  math_abs(int x);
int  math_clamp(int x, int lo, int hi);

#endif /* RUNTIME_H */
