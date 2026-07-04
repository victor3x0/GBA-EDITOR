/* actor_api_static.h — implémentations inline de l'API acteur (partie non générée).
   Inclus depuis actor_api.h (généré par build.py).
   Dépend de : actor_types.h (inclus avant ce fichier). */
#ifndef ACTOR_API_STATIC_H
#define ACTOR_API_STATIC_H

/* Globaux définis dans main.c, visibles par tous les scripts */
extern Actor g_actors[];
extern u32   _g_keys_held;
extern u32   _g_keys_pressed;

/* Caméra */
extern int cam_x, cam_y;
static inline void camera_set(int x, int y) { cam_x=x; cam_y=y; }
static inline int  camera_get_x(void)        { return cam_x; }
static inline int  camera_get_y(void)        { return cam_y; }

/* Mouvement */
static inline void actor_move(Actor* s, int dx, int dy)        { s->x+=dx; s->y+=dy; }
static inline void actor_set_pos(Actor* s, int x, int y)       { s->x=x; s->y=y; }
static inline void actor_set_velocity(Actor* s, int vx, int vy){ s->vx=vx; s->vy=vy; }
static inline void actor_apply_velocity(Actor* s)               { s->x+=s->vx; s->y+=s->vy; }

/* Lecture de position et vélocité */
static inline int actor_get_x (const Actor* s) { return s->x;  }
static inline int actor_get_y (const Actor* s) { return s->y;  }
static inline int actor_get_vx(const Actor* s) { return s->vx; }
static inline int actor_get_vy(const Actor* s) { return s->vy; }

/* Animation — play_anim reçoit l'index d'état (résolu à la compile par le transpileur) */
static inline void actor_play_anim(Actor* s, int id) { if(s->anim_state!=id){s->anim_state=id;s->frame=0;s->timer=0;} }
static inline void actor_set_frame(Actor* s, int f)  { s->frame=f; }
static inline void actor_set_visible(Actor* s, int v){ s->visible=v; }
/* v=-1 → retourné, v=1 → normal (compatible variable de direction) */
static inline void actor_set_flip_h(Actor* s, int v) { s->flip_h = (v < 0) ? 1 : 0; }
static inline void actor_set_flip_v(Actor* s, int v) { s->flip_v = (v < 0) ? 1 : 0; }

/* Direction 8-axes pour l'animation (0=override, 1=N..8=NW) */
static inline int  actor_get_dir(const Actor* s)          { static const s8 _lut[3][3]={{8,1,2},{7,0,3},{6,5,4}}; return _lut[s->dir_y+1][s->dir_x+1]; }
static inline void actor_set_dir(Actor* s, int dir)       { static const s8 _dx[]={0,0,1,1,1,0,-1,-1,-1}; static const s8 _dy[]={0,-1,-1,0,1,1,1,0,-1}; if(dir>=0&&dir<=8){s->dir_x=_dx[dir];s->dir_y=_dy[dir];} }
static inline void actor_set_auto_dir(Actor* s, int v)    { s->auto_dir=v?1:0; }

/* Direction : vecteur discret (-1|0|1) indépendant du flip */
static inline int  actor_get_dir_x(const Actor* s)        { return s->dir_x; }
static inline int  actor_get_dir_y(const Actor* s)        { return s->dir_y; }
static inline void actor_set_direction(Actor* s, int dx, int dy) {
    s->dir_x = (dx > 0) - (dx < 0);   /* clamp à -1/0/1 */
    s->dir_y = (dy > 0) - (dy < 0);
}

/* Activation / destruction */
static inline void actor_set_active(Actor* s, int v) { s->active=v; }
static inline void actor_destroy_internal(Actor* s)  { s->active=0; s->visible=0; }

/* Input */
static inline int input_held(int b)    { return (_g_keys_held   &(u32)b)?1:0; }
static inline int input_pressed(int b) { return (_g_keys_pressed&(u32)b)?1:0; }

/* Collision AABB — teste une paire de CollisionBox dans l'espace monde */
static inline int box_overlap(int ax, int ay, const CollisionBox*ba,
                               int bx, int by, const CollisionBox*bb) {
    int alx=ax+(int)ba->x, aly=ay+(int)ba->y;
    int blx=bx+(int)bb->x, bly=by+(int)bb->y;
    return (alx < blx+(int)bb->w) && (alx+(int)ba->w > blx) &&
           (aly < bly+(int)bb->h) && (aly+(int)ba->h > bly);
}

/* Vrai si au moins une paire de boxes se chevauche.
   Écrit les tags BOXTAG_* des boxes impliquées dans *my_box / *other_box. */
static inline int actors_overlap_boxes(const Actor*a, const Actor*b,
                                        u8*my_box, u8*other_box) {
    for (int i=0; i<a->box_count; i++)
        for (int j=0; j<b->box_count; j++)
            if (box_overlap(a->x,a->y,&a->boxes[i],
                            b->x,b->y,&b->boxes[j])) {
                *my_box    = a->boxes[i].tag;
                *other_box = b->boxes[j].tag;
                return 1;
            }
    return 0;
}

/* Rétrocompatibilité — teste sans récupérer les tags */
static inline int actors_overlap(const Actor*a, const Actor*b) {
    u8 _a=0,_b=0; return actors_overlap_boxes(a,b,&_a,&_b);
}

/* Tag */
static inline int actor_get_tag(const Actor* s) { return s->tag; }

/* Palette (flash de dégâts, invincibilité…) */
static inline void actor_set_pal(Actor* s, int bank) { s->pal_bank = bank & 0xF; }

/* Maths */
static inline int math_abs  (int x)              { return x < 0 ? -x : x; }
static inline int math_clamp(int x, int lo, int hi){ return x<lo?lo:x>hi?hi:x; }
static inline int math_sign (int x)              { return (x > 0) - (x < 0); }
static inline int math_min  (int a, int b)       { return a < b ? a : b; }
static inline int math_max  (int a, int b)       { return a > b ? a : b; }

/* Frame counter global (défini dans main.c) */
extern int _g_frame;
static inline int scene_frame(void) { return _g_frame; }

/* Tile — lire la valeur brute d'une tile à une position monde */
extern int tile_get(int px, int py);

/* Aléatoire — LCG 32-bit, zéro overhead, pas de division flottante */
static u32 _rand_seed = 73244475u;
static inline int math_rand(int lo, int hi) {
    _rand_seed = _rand_seed * 1664525u + 1013904223u;
    int range = hi - lo + 1;
    if (range <= 0) return lo;
    return lo + (int)((_rand_seed >> 16) % (u32)range);
}

/* Caméra — suivi avec zone morte (dead-zone follow) */
static inline void camera_follow(int tx, int ty, int mx, int my) {
    if (tx - cam_x < mx)           cam_x = tx - mx;
    if (tx - cam_x > 240 - mx)     cam_x = tx - (240 - mx);
    if (ty - cam_y < my)           cam_y = ty - my;
    if (ty - cam_y > 160 - my)     cam_y = ty - (160 - my);
}

/* Envoi d'event à tous les actors actifs (G_ACTOR_COUNT défini dans actor_api.h) */
/* La fn C cible (event_handler) est appelée si l'actor est actif. */
/* broadcast("on_receive", 42) → tous les on_receive reçoivent (0, 42) */
/* Implémenté comme macro pour éviter les pointeurs de fonction sur GBA. */
/* Usage codegen : broadcast(tag, value) — résolu statiquement dans main.c. */
/* Note : broadcast est résolu directement dans le codegen de chaque scène. */

/* tile_solid_at exposée pour les scripts (définie dans main.c) */
extern int tile_solid_at(int px, int py);

/* Fonctions texte HUD — définies dans main.c via GBA_ENGINE_IMPL (wrappers TTE) */
extern void draw_printf(int col, int row, const char *fmt, ...);
extern void draw_clear (int col, int row, int len);

/* Vrai si au moins une solid box a un tile solide juste dessous */
static inline int actor_on_ground(const Actor*a) {
    for (int i=0; i<a->box_count; i++) {
        if (!a->boxes[i].solid) continue;
        int left =a->x+(int)a->boxes[i].x;
        int right=left+(int)a->boxes[i].w-1;
        int bot  =a->y+(int)a->boxes[i].y+(int)a->boxes[i].h;
        for (int px=left; px<=right; px+=8)
            if (tile_solid_at(px,bot)) return 1;
        if (tile_solid_at(right,bot)) return 1;
    }
    return 0;
}

#endif /* ACTOR_API_STATIC_H */
