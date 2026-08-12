/* actor_api_static.h — implémentations inline de l'API acteur (partie non générée).
   Inclus depuis actor_api.h (généré par build.py).
   Dépend de : actor_types.h (inclus avant ce fichier). */
#ifndef ACTOR_API_STATIC_H
#define ACTOR_API_STATIC_H

/* Globaux définis dans main.c, visibles par tous les scripts */
extern Actor g_actors[];
extern u32   _g_keys_held;
extern u32   _g_keys_pressed;

/* Caméra — une zone de taille écran fixe (SCREEN_W×SCREEN_H) dont l'origine
   (cam_x, cam_y) est en espace-monde. Tout le reste (scroll BG, position
   écran des sprites) se dérive de cette seule zone plutôt que de littéraux
   240/160/120/80 épars (cf. project_camera_abstraction). */
#define SCREEN_W 240
#define SCREEN_H 160
extern int cam_x, cam_y;
static inline void camera_set(int x, int y) { cam_x=x; cam_y=y; }
static inline int  camera_get_x(void)        { return cam_x; }
static inline int  camera_get_y(void)        { return cam_y; }

/* Bornes de scroll (taille du monde en pixels) — g_cam_max_x/y (définis dans
   main.c comme cam_x/cam_y) valent -1 par défaut (axe illimité).
   Réglées à l'activation d'une caméra (camera_switch, depuis ses bounds_w/h)
   ou par un script via camera.set_bounds() — débloquer une nouvelle zone au
   runtime, par exemple. Minimum toujours 0 (origine du monde). */
extern int g_cam_max_x, g_cam_max_y;
static inline void camera_set_bounds(int world_w, int world_h) {
    g_cam_max_x = (world_w > 0) ? world_w - SCREEN_W : -1;
    g_cam_max_y = (world_h > 0) ? world_h - SCREEN_H : -1;
}
/* Appliquée une fois par frame par le moteur (scene tick), après tout code
   ayant pu écrire cam_x/cam_y cette frame-là — suivi authoré ou script :
   un seul point de vérité pour les bornes, peu importe qui a bougé la
   caméra. */
static inline void camera_apply_bounds(void) {
    if (g_cam_max_x >= 0) { if (cam_x < 0) cam_x = 0; if (cam_x > g_cam_max_x) cam_x = g_cam_max_x; }
    if (g_cam_max_y >= 0) { if (cam_y < 0) cam_y = 0; if (cam_y > g_cam_max_y) cam_y = g_cam_max_y; }
}

/* ── Caméras nommées ─────────────────────────────────────────────
   Une configuration de cadrage est une DONNÉE (un asset de l'éditeur), pas du
   code : la table ci-dessous est émise dans main.c, une entrée par caméra du
   projet, l'entrée 0 étant toujours la caméra par défaut. Une seule est active
   à la fois — la GBA n'a qu'un écran.

   `mode` : 0 fixe, 1 suivi, 2 script. La CIBLE du suivi n'est pas ici : elle
   est un index d'acteur, donc propre à chaque scène, et vit dans une table par
   scène émise à côté du tick. */
typedef struct {
    u8  mode;
    u8  margin_x, margin_y;   /* zone morte du suivi */
    s16 x, y;                 /* cadrage posé à l'activation */
    s16 bounds_w, bounds_h;   /* taille du monde ; 0 = axe illimité */
    void (*on_start)(void);   /* script de la caméra, ou NULL */
    void (*on_update)(void);
} Camera;

extern const Camera g_cam_table[];
extern int g_cam_active;

/* Activer une caméra POSE son cadrage et ses bornes : c'est ce que « caméra
   fixe » veut dire, et une caméra en suivi se recale dans la frame même. Les
   bornes ne sont donc écrites qu'ici — un script qui appelle camera.set_bounds
   ensuite garde la main jusqu'à la prochaine activation. */
static inline void camera_switch(int idx) {
    if (idx < 0) return;
    const Camera *c = &g_cam_table[idx];
    g_cam_active = idx;
    cam_x = c->x; cam_y = c->y;
    camera_set_bounds(c->bounds_w, c->bounds_h);
    if (c->on_start) c->on_start();
}

/* ── Secousse ────────────────────────────────────────────────────
   Un ÉVÉNEMENT, pas un état de la caméra : ses valeurs vivent à l'appel.
   L'amplitude retombe linéairement à zéro sur la durée — c'est la décroissance,
   sans troisième réglage à comprendre.

   Le décalage est appliqué APRÈS le clamp aux bornes (une secousse au bord du
   monde doit se voir) et RETIRÉ au début de la frame suivante : la logique de
   suivi ne voit donc jamais une caméra tremblée, et rien d'autre dans le moteur
   n'a à connaître la secousse. */
extern int g_shake_amp, g_shake_left, g_shake_total, g_shake_dx, g_shake_dy;
extern u32 g_shake_seed;

static inline void camera_shake(int amplitude, int frames) {
    if (amplitude <= 0 || frames <= 0) { g_shake_left = 0; return; }
    g_shake_amp = amplitude; g_shake_left = frames; g_shake_total = frames;
}

static inline int _shake_offset(int a) {
    g_shake_seed = g_shake_seed * 1664525u + 1013904223u;
    return (int)((g_shake_seed >> 16) % (u32)(2 * a + 1)) - a;
}

static inline void camera_shake_undo(void) {
    cam_x -= g_shake_dx; cam_y -= g_shake_dy;
    g_shake_dx = 0; g_shake_dy = 0;
}

static inline void camera_shake_apply(void) {
    if (g_shake_left <= 0) return;
    g_shake_left--;
    int a = (g_shake_amp * g_shake_left) / g_shake_total;
    if (a <= 0) return;
    g_shake_dx = _shake_offset(a);
    g_shake_dy = _shake_offset(a);
    cam_x += g_shake_dx; cam_y += g_shake_dy;
}

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

/* Mode OAM — 0 = sprite normal, 2 = fenêtre-objet : le sprite n'est plus
   dessiné, ses pixels opaques DÉCOUPENT la région window.OBJ (forme libre,
   animable, sans interruption). Mode 1 (semi-transparent) suppose le
   blending, pas encore câblé. */
static inline void actor_set_obj_mode(Actor* s, int mode) { s->obj_mode = mode & 3; }
static inline int  actor_get_obj_mode(const Actor* s)     { return s->obj_mode; }

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
    if (tx - cam_x < mx)              cam_x = tx - mx;
    if (tx - cam_x > SCREEN_W - mx)   cam_x = tx - (SCREEN_W - mx);
    if (ty - cam_y < my)              cam_y = ty - my;
    if (ty - cam_y > SCREEN_H - my)   cam_y = ty - (SCREEN_H - my);
}

/* Envoi d'event à tous les actors actifs (G_ACTOR_COUNT défini dans actor_api.h) */
/* La fn C cible (event_handler) est appelée si l'actor est actif. */
/* broadcast("on_receive", 42) → tous les on_receive reçoivent (0, 42) */
/* Implémenté comme macro pour éviter les pointeurs de fonction sur GBA. */
/* Usage codegen : broadcast(tag, value) — résolu statiquement dans main.c. */
/* Note : broadcast est résolu directement dans le codegen de chaque scène. */

/* (`tile_solid_at` a été retirée : elle répondait « il y a quelque chose ici »
   sans distinguer un bloc plein d'une pente, ce qui n'a plus de sens depuis que
   la résolution connaît la géométrie. Son dernier appelant était
   `actor_on_ground`, et aucune entrée de l'API Lua ne la citait. Un script qui
   veut inspecter la carte lit `tile.get`.) */

/* Layers BG vivants — définis dans main.c via GBA_ENGINE_IMPL (gba_engine.h).
   `bg` = bg_slot 0-3 ; tx/ty en tuiles dans la map du layer. */
extern void layer_show        (int bg, int on);
extern int  layer_is_visible  (int bg);
extern void layer_set_priority(int bg, int prio);
extern int  layer_get_priority(int bg);
extern void layer_set_scroll  (int bg, int x, int y);
extern void layer_scroll_by   (int bg, int dx, int dy);
extern int  layer_get_scroll_x(int bg);
extern int  layer_get_scroll_y(int bg);
extern void layer_set_map     (int bg, int sbb);
extern int  layer_get_map     (int bg);

/* Windows — pochoirs par région d'écran (r : 0=WIN0, 1=WIN1, 2=fenêtre-objet,
   3=extérieur). Ne dessinent rien : autorisent ou non l'affichage. */
extern void window_show      (int n, int on);
extern int  window_is_visible(int n);
extern void window_set       (int n, int x, int y, int w, int h);
extern void window_set_layer (int r, int bg, int on);
extern int  window_get_layer (int r, int bg);
extern void window_set_obj   (int r, int on);
extern void window_set_blend (int r, int on);

/* Texte — le texte vit sur LE layer d'UI de la scène (Scene.text_bg) : les
   glyphes sont chargés dans le charblock de ce layer, d'où l'absence de
   paramètre `layer`. tx/ty en tuiles. `n` = nombre de caractères révélés
   (machine à écrire) ; le rythme appartient au script. */
extern void text_set_font (int f);
extern int  text_length   (int id);
extern void text_clear    (int tx, int ty, int w, int h);
/* GRAMMAIRE : position ou conteneur d'abord, contenu ensuite — même ordre qu'en
   Lua (cf. api.py, section Texte). */
extern void text_draw     (int tx, int ty, int id);
/* Rendu dans une zone dessinée dans le canvas de scène : elle porte position,
   largeur de coupe, alignement et police. Remplace `text_draw_box`, dont la
   géométrie vivait dans le script (donc invisible dans l'éditeur).

   ATTENTION — cette liste DOUBLE celle de `gba_engine.h` : les scènes et les
   actors sont des unités de compilation distinctes qui n'incluent pas le moteur.
   Une fonction déclarée là-bas et oubliée ici passe le checker, s'émet en C, et
   échoue au `make` sur un « implicit declaration » qui ne dit rien de la cause.
   `validate_project` compare donc les deux listes plutôt que de compter sur
   la vigilance. */
extern void text_draw_in     (int region, int id);
extern void text_clear_in    (int region);
/* Groupe LECTURE — état d'un texte à tempo dans sa zone. */
extern int  text_reading     (int region);
extern void text_skip        (int region);

/* Images d'interface — un sprite à état posé sur la mise en page. Rien pour
   créer ni déplacer : la géométrie est authorée, seul l'ÉTAT est au script. */
extern void ui_image_set_state(int img, int state);
extern void ui_image_play     (int img, int on);
extern void ui_image_show     (int img, int on);
extern int  ui_image_state    (int img);

/* Blending — `side` 0 = le dessus (ce qui est mélangé), 1 = le dessous (ce
   avec quoi, situé derrière). Modes : 0 aucun, 1 alpha, 2 vers le blanc,
   3 vers le noir. */
extern void blend_set_mode    (int mode);
extern int  blend_get_mode    (void);
extern void blend_set_layer   (int side, int bg, int on);
extern void blend_set_obj     (int side, int on);
extern void blend_set_backdrop(int side, int on);
extern void blend_set_alpha   (int eva, int evb);
extern void blend_set_fade    (int evy);

/* Palettes au runtime — remplace les seize couleurs d'une banque matérielle.
   Là où le mélange ci-dessus agit sur un CALQUE entier et seulement vers le
   blanc ou le noir, une banque ne concerne que les tuiles qui la citent : on
   peut refroidir un décor en gardant ses lanternes allumées. Les deux pools
   sont physiquement distincts, d'où deux fonctions. */
extern void palette_set_bg (int bank, int idx);
extern void palette_set_obj(int bank, int idx);

/* Sauvegarde — écrit ou relit les variables globales marquées persistantes
   dans l'emplacement `slot`. Rendent 0 si l'emplacement n'existe pas, et
   save_read 0 aussi si ce qui s'y trouve n'est pas relisible (marque, version
   ou somme de contrôle) : le jeu doit pouvoir distinguer « pas de partie » de
   « partie chargée » sans deviner. */
extern int save_write (int slot);
extern int save_read  (int slot);
extern int save_exists(int slot);
extern int save_erase (int slot);

extern void tilemap_set        (int bg, int tx, int ty, int tile);
extern int  tilemap_get        (int bg, int tx, int ty);
extern void tilemap_set_palette(int bg, int tx, int ty, int bank);
extern void tilemap_set_flip   (int bg, int tx, int ty, int fh, int fv);
extern void tilemap_fill       (int bg, int tx, int ty, int w, int h, int tile);

/* Fonctions texte HUD — définies dans main.c via GBA_ENGINE_IMPL (wrappers TTE) */
/* draw_printf / draw_clear retirés avec libtonc TTE — cf. gba_engine.h.
   Remplacements : text_draw (libellé, depuis la table) et text_draw_num
   (valeur). */

/* Y a-t-il un sol sous les pieds ?

   Lecture du drapeau posé par la résolution contre la carte de collision, et
   non un nouveau balayage : la résolution connaît les PENTES, un balayage de
   `tile_solid_at` répondrait « non » sur toute pente puisque celle-ci n'est
   solide que dans une partie de sa colonne.

   L'état est donc celui de la FIN de la frame précédente — la résolution
   s'exécute après les `on_update`. C'est le contrat normal d'un état de
   collision, et le seul possible : pendant `on_update`, l'acteur n'a pas encore
   fini de bouger. */
static inline int actor_on_ground(const Actor*a) { return a->grounded; }

#endif /* ACTOR_API_STATIC_H */
