/* SPDX-License-Identifier: Zlib
   Copyright (c) 2026 Yasor Rovic

   Licence zlib — PAS la GPL de l'éditeur (cf. runtime/LICENSE). Ce fichier est
   recopié dans le projet de l'utilisateur au build, puis compilé dans sa ROM :
   le jeu produit lui appartient entièrement, il peut le vendre, et il n'a
   aucune notice à joindre à sa ROM. */
/* actor_api_static.h — implémentations inline de l'API acteur (partie non générée).
   Inclus depuis actor_api.h (généré par build.py).
   Dépend de : actor_types.h (inclus avant ce fichier). */
#ifndef ACTOR_API_STATIC_H
#define ACTOR_API_STATIC_H

/* Modes OAM et directions, nommés — le Lua les cite par leur nom
   (`self:set_dir("north")`), le codegen émet ces constantes. Voir
   scripting/api.py, « Énumérations matérielles ».
   Les directions suivent l'ordre des tables de actor_set_dir : 0 = aucune,
   puis dans le sens horaire depuis le nord. */
#define OBJ_MODE_NORMAL   0
#define OBJ_MODE_BLEND    1
#define OBJ_MODE_WINDOW   2

#define DIR_NONE          0
#define DIR_NORTH         1
#define DIR_NORTH_EAST    2
#define DIR_EAST          3
#define DIR_SOUTH_EAST    4
#define DIR_SOUTH         5
#define DIR_SOUTH_WEST    6
#define DIR_WEST          7
#define DIR_NORTH_WEST    8

/* Courbes d'accélération de math.ease() — mêmes noms qu'en Lua. */
#define EASE_IN           0
#define EASE_OUT          1
#define EASE_IN_OUT       2

/* Régions de window et cibles de blending. Elles DOUBLENT celles de
   `gba_engine.h`, pour la même raison que les prototypes plus bas : le moteur
   n'est inclus que par main.c, alors que les scènes et les acteurs — qui sont
   ceux qui écrivent `window.set_layer("win0", ...)` — ne voient que ce
   fichier-ci. Manquantes ici, elles passaient checker et codegen pour échouer
   au `make` sur un identifiant inconnu, sur la ligne générée et jamais sur sa
   cause.

   Les deux listes sont comparées au build (`validator._check_api_prototypes`,
   dérivé de `HARDWARE_ENUMS`), et une valeur qui divergerait entre les deux
   fichiers ferait crier le préprocesseur dans main.c, qui les voit toutes
   les deux. */
#define WINR_0            0
#define WINR_1            1
#define WINR_OBJ          2
#define WINR_OUT          3

#define BLD_MODE_NONE     0
#define BLD_MODE_ALPHA    1
#define BLD_MODE_BRIGHTEN 2
#define BLD_MODE_DARKEN   3

#define BLD_SIDE_TOP      0
#define BLD_SIDE_BOTTOM   1

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
extern int g_scene_w, g_scene_h;   /* taille du monde de la scène (px), posée par scene_init */
static inline void camera_set_position(Vec2 p)  { cam_x=p.x; cam_y=p.y; }
static inline Vec2 camera_get_position(void)     { return (Vec2){ cam_x, cam_y }; }

/* Bornes de scroll — la zone scrollable du monde, un RECTANGLE (origine
   x/y + taille w/h en pixels). g_bounds_* (définis dans main.c) valent 0 par
   défaut (axe illimité). Réglées à l'activation d'une caméra (camera_switch,
   depuis ses bounds_x/y/w/h) ou par un script via camera.bound — débloquer
   une nouvelle zone au runtime, par exemple. */
extern int g_bounds_x, g_bounds_y, g_bounds_w, g_bounds_h;
static inline void camera_set_bounds(Rect b) {
    g_bounds_x = b.x; g_bounds_y = b.y;
    g_bounds_w = b.w; g_bounds_h = b.h;
}
static inline Rect camera_get_bounds(void) {
    return (Rect){ g_bounds_x, g_bounds_y, g_bounds_w, g_bounds_h };
}
/* Appliquée une fois par frame par le moteur (scene tick), après tout code
   ayant pu écrire cam_x/cam_y cette frame-là — suivi authoré ou script :
   un seul point de vérité pour les bornes, peu importe qui a bougé la
   caméra. */
static inline void camera_apply_bounds(void) {
    if (g_bounds_w > 0) {
        int lo = g_bounds_x, hi = g_bounds_x + g_bounds_w - SCREEN_W;
        if (cam_x < lo) cam_x = lo;
        if (cam_x > hi) cam_x = hi;
    }
    if (g_bounds_h > 0) {
        int lo = g_bounds_y, hi = g_bounds_y + g_bounds_h - SCREEN_H;
        if (cam_y < lo) cam_y = lo;
        if (cam_y > hi) cam_y = hi;
    }
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
    s16 bounds_x, bounds_y;   /* origine de la zone scrollable */
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
    camera_set_bounds((Rect){ c->bounds_x, c->bounds_y, c->bounds_w, c->bounds_h });
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

/* Vec2/Vec3 — opérateurs composante à composante. Pas d'opérateur `+`/`-`/`*`
   sur les structs en C : ce sont ces fonctions que le codegen appelle pour
   `a + b` / `a - b` / `v * k` sur deux valeurs vec2 ou vec3 (jamais mélangées
   entre elles — cf. scripting/vec_types.py, seul juge du type). */
static inline Vec2 vec2_add  (Vec2 a, Vec2 b) { return (Vec2){ a.x+b.x, a.y+b.y }; }
static inline Vec2 vec2_sub  (Vec2 a, Vec2 b) { return (Vec2){ a.x-b.x, a.y-b.y }; }
static inline Vec2 vec2_scale(Vec2 v, int k)  { return (Vec2){ v.x*k,   v.y*k   }; }
static inline Vec3 vec3_add  (Vec3 a, Vec3 b) { return (Vec3){ a.x+b.x, a.y+b.y, a.z+b.z }; }
static inline Vec3 vec3_sub  (Vec3 a, Vec3 b) { return (Vec3){ a.x-b.x, a.y-b.y, a.z-b.z }; }
static inline Vec3 vec3_scale(Vec3 v, int k)  { return (Vec3){ v.x*k,   v.y*k,   v.z*k   }; }

/* Transform — position instantanée, sans notion de temps ni de vitesse.
   ROADMAP v0.19 : s->x/s->y sont en Q8 en interne (256 = 1 px), mais
   self.position continue de rendre des PIXELS — décision verrouillée : un
   projet existant ne change pas de comportement, et un auteur qui n'a pas
   besoin de sous-pixel n'en entend jamais parler. L'écriture perd donc toute
   fraction sous-pixel accumulée (ex: par self:apply_velocity()) — c'est
   attendu d'un appel qui dit « l'acteur est ICI, au pixel », pas « avance ». */
static inline void actor_set_position(Actor* s, Vec2 p) { s->x=p.x<<8; s->y=p.y<<8; }
static inline Vec2 actor_get_position(const Actor* s)   { return (Vec2){ s->x>>8, s->y>>8 }; }

/* Racine carrée entière (algorithme bit à bit) — pas de FPU sur GBA, et le
   BIOS Sqrt coûte un appel SWI pour un résultat qu'on ne calcule qu'une fois
   par mouvement. Sert à normaliser une direction dans move()/move_to(). */
static inline int isqrt(int n) {
    if (n <= 0) return 0;
    int res = 0, bit = 1 << 30;
    while (bit > n) bit >>= 2;
    while (bit != 0) {
        if (n >= res + bit) { n -= res + bit; res = (res >> 1) + bit; }
        else res >>= 1;
        bit >>= 2;
    }
    return res;
}

/* Movement — déplacement étalé sur plusieurs frames : appelées depuis
   on_update à chaque frame, elles avancent d'au plus `speed` px CE frame-là.
   `speed` et `target` restent des PIXELS entiers, comme avant v0.19 — ce sont
   des arguments Lua, et le sous-ensemble Lua reste entier (décision
   verrouillée). Aucun état gardé sur l'Actor (ni cible, ni reste
   fractionnaire) : la direction est recalculée à chaque appel depuis la
   position courante.

   actor_move accumule en Q8 (dx/dy/mag restent petits — une direction, pas
   une distance monde — aucun risque de débordement à multiplier speed<<8) :
   un bonus de précision, gratuit, sur un calcul qui tronquait avant. */
static inline void actor_move(Actor* s, Vec2 dir, int speed) {
    int dx = dir.x, dy = dir.y;
    int mag = isqrt(dx*dx + dy*dy);
    if (mag == 0) return;
    s->x += dx * (speed<<8) / mag;
    s->y += dy * (speed<<8) / mag;
}
/* actor_move_to, à l'inverse, calcule dx/dy/dist contre la position ARRONDIE
   (cx/cy) : `target` est une distance MONDE, potentiellement grande, et
   speed<<8 dans le même produit déborderait un int 32 bits. Le résultat est
   remis à l'échelle Q8 seulement à l'écriture — la même règle qu'ailleurs
   dans ce chantier : un seul arrondi, jamais dans le calcul intermédiaire. */
static inline void actor_move_to(Actor* s, Vec2 target, int speed) {
    int cx = s->x>>8, cy = s->y>>8;
    int dx = target.x - cx, dy = target.y - cy;
    int dist = isqrt(dx*dx + dy*dy);
    if (dist <= speed) { s->x = target.x<<8; s->y = target.y<<8; return; }
    s->x += (dx * speed / dist) << 8;
    s->y += (dy * speed / dist) << 8;
}

/* Physics — vélocité stockée sur l'Actor, lue par get_velocity. Ne déplace
   rien seule : c'est le script qui l'applique, via actor_apply_velocity
   (cf. Ball.lua) ou en l'ignorant.

   ROADMAP v0.19 : self.velocity change de SENS — s->vx/s->vy sont Q8, et
   get/set_velocity ne convertissent plus rien (contrairement à la position,
   qui reste pixels). Un script qui lisait/écrivait self.velocity en pixels
   avant cette version doit être migré : c'est la rupture assumée qui rend le
   sous-pixel utilisable sans un second nom (self.velocity_q8) à côté du
   premier. */
static inline void actor_set_velocity(Actor* s, Vec2 v) { s->vx=v.x; s->vy=v.y; }
static inline void actor_add_velocity(Actor* s, Vec2 dv){ s->vx+=dv.x; s->vy+=dv.y; }
static inline Vec2 actor_get_velocity(const Actor* s)    { return (Vec2){ s->vx, s->vy }; }
/* Applique la vélocité Q8 stockée à la position Q8 stockée — l'accumulateur
   sous-pixel est LITTÉRALEMENT s->x/s->y, donc rien à reporter ailleurs
   (contrairement à slope_acc, qui corrige une AUTRE fraction : le cosinus de
   pente en collision, cf. resolve_actor_tiles). Remplace l'ancien idiome
   `self.position = self.position + self.velocity`, qui n'a plus de sens dès
   que les deux membres ont des échelles différentes. */
static inline void actor_apply_velocity(Actor* s) { s->x+=s->vx; s->y+=s->vy; }

/* Animation — play_anim reçoit l'index d'état (résolu à la compile par le transpileur) */
static inline void actor_play_anim(Actor* s, int id) { if(s->anim_state!=id){s->anim_state=id;s->frame=0;s->timer=0;} }
static inline int  actor_get_frame(const Actor* s)   { return s->frame; }
static inline void actor_set_frame(Actor* s, int f)  { s->frame=f; }
static inline int  actor_get_visible(const Actor* s) { return s->visible; }
static inline void actor_set_visible(Actor* s, int v){ s->visible=v; }
static inline int  actor_get_active(const Actor* s)  { return s->active; }
static inline void actor_set_active(Actor* s, int v) { s->active=v; }
/* Booléens (self.flip_h = true/false) — le sens du flip est porté par l'état,
   pas par un signe passé à l'ancien self:set_flip_h. */
static inline int  actor_get_flip_h(const Actor* s)  { return s->flip_h; }
static inline void actor_set_flip_h(Actor* s, int v) { s->flip_h = v ? 1 : 0; }
static inline int  actor_get_flip_v(const Actor* s)  { return s->flip_v; }
static inline void actor_set_flip_v(Actor* s, int v) { s->flip_v = v ? 1 : 0; }

/* ── Transform affine au runtime ──────────────────────────────────────────
   Champs PAR-ACTOR de la struct Actor (cf. actor_types_static.h), et non des
   globaux par slot : un script de prefab poolé est UNE fonction C partagée par
   toutes ses instances, mais chaque instance a sa propre struct Actor et un
   slot différent (Actor.affine_slot). Des globaux dans ce header `static`
   créaient une COPIE par unité de compilation (main.c vs actor_*.c) — les
   écritures self.rotation/self.scale n'atteignaient jamais le rendu.
   Pas de FPU sur GBA : SIN_LUT est une table degrés→Q8 (×256) écrite en dur.
   gba_cos se déduit d'un déphasage de 90° plutôt qu'une seconde table. */
static const s16 SIN_LUT[360] = {
    0, 4, 9, 13, 18, 22, 27, 31, 36, 40, 44, 49,
    53, 58, 62, 66, 71, 75, 79, 83, 88, 92, 96, 100,
    104, 108, 112, 116, 120, 124, 128, 132, 136, 139, 143, 147,
    150, 154, 158, 161, 165, 168, 171, 175, 178, 181, 184, 187,
    190, 193, 196, 199, 202, 204, 207, 210, 212, 215, 217, 219,
    222, 224, 226, 228, 230, 232, 234, 236, 237, 239, 241, 242,
    243, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 254,
    255, 255, 255, 256, 256, 256, 256, 256, 256, 256, 255, 255,
    255, 254, 254, 253, 252, 251, 250, 249, 248, 247, 246, 245,
    243, 242, 241, 239, 237, 236, 234, 232, 230, 228, 226, 224,
    222, 219, 217, 215, 212, 210, 207, 204, 202, 199, 196, 193,
    190, 187, 184, 181, 178, 175, 171, 168, 165, 161, 158, 154,
    150, 147, 143, 139, 136, 132, 128, 124, 120, 116, 112, 108,
    104, 100, 96, 92, 88, 83, 79, 75, 71, 66, 62, 58,
    53, 49, 44, 40, 36, 31, 27, 22, 18, 13, 9, 4,
    0, -4, -9, -13, -18, -22, -27, -31, -36, -40, -44, -49,
    -53, -58, -62, -66, -71, -75, -79, -83, -88, -92, -96, -100,
    -104, -108, -112, -116, -120, -124, -128, -132, -136, -139, -143, -147,
    -150, -154, -158, -161, -165, -168, -171, -175, -178, -181, -184, -187,
    -190, -193, -196, -199, -202, -204, -207, -210, -212, -215, -217, -219,
    -222, -224, -226, -228, -230, -232, -234, -236, -237, -239, -241, -242,
    -243, -245, -246, -247, -248, -249, -250, -251, -252, -253, -254, -254,
    -255, -255, -255, -256, -256, -256, -256, -256, -256, -256, -255, -255,
    -255, -254, -254, -253, -252, -251, -250, -249, -248, -247, -246, -245,
    -243, -242, -241, -239, -237, -236, -234, -232, -230, -228, -226, -224,
    -222, -219, -217, -215, -212, -210, -207, -204, -202, -199, -196, -193,
    -190, -187, -184, -181, -178, -175, -171, -168, -165, -161, -158, -154,
    -150, -147, -143, -139, -136, -132, -128, -124, -120, -116, -112, -108,
    -104, -100, -96, -92, -88, -83, -79, -75, -71, -66, -62, -58,
    -53, -49, -44, -40, -36, -31, -27, -22, -18, -13, -9, -4,
};
static inline int gba_sin(int deg) { deg = ((deg % 360) + 360) % 360; return SIN_LUT[deg]; }
static inline int gba_cos(int deg) { return gba_sin(deg + 90); }

/* Un matrix slot est réservé au build quand Actor.affine_transform est coché
   (cf. main_gen._compute_affine_info) ; affine_slot est alors >= 0 et les
   champs transform ci-dessous sont lus par le rendu. Sans slot, les getters
   renvoient l'identité (0° / 100 %) et les setters sont sans effet. */

/* Transform MONDE (self.rotation / self.scale). */
static inline void actor_set_rotation(Actor* s, int deg) {
    if (s->affine_slot >= 0) s->rotation = deg;
}
static inline void actor_set_scale(Actor* s, Vec2 v) {
    if (s->affine_slot < 0) return;
    s->scale_x = v.x * 256 / 100;
    s->scale_y = v.y * 256 / 100;
}
static inline int  actor_get_rotation(const Actor* s) {
    return (s->affine_slot >= 0) ? s->rotation : 0;
}
static inline Vec2 actor_get_scale(const Actor* s) {
    if (s->affine_slot < 0) return (Vec2){ 100, 100 };
    return (Vec2){ s->scale_x * 100 / 256, s->scale_y * 100 / 256 };
}

/* Transform LOCAL du sprite (self.sprite_rotation / self.sprite_scale /
   self.sprite_offset), composé par-dessus le monde : la rotation s'AJOUTE,
   le scale se MULTIPLIE, l'offset déplace le sprite dans le repère de l'actor. */
static inline void actor_set_sprite_rotation(Actor* s, int deg) {
    if (s->affine_slot >= 0) s->sprite_rot = deg;
}
static inline void actor_set_sprite_scale(Actor* s, Vec2 v) {
    if (s->affine_slot < 0) return;
    s->sprite_scale_x = v.x * 256 / 100;
    s->sprite_scale_y = v.y * 256 / 100;
}
static inline void actor_set_sprite_offset(Actor* s, Vec2 o) {
    if (s->affine_slot < 0) return;
    s->offset_x = o.x;
    s->offset_y = o.y;
}
static inline int  actor_get_sprite_rotation(const Actor* s) {
    return (s->affine_slot >= 0) ? s->sprite_rot : 0;
}
static inline Vec2 actor_get_sprite_scale(const Actor* s) {
    if (s->affine_slot < 0) return (Vec2){ 100, 100 };
    return (Vec2){ s->sprite_scale_x * 100 / 256, s->sprite_scale_y * 100 / 256 };
}
static inline Vec2 actor_get_sprite_offset(const Actor* s) {
    if (s->affine_slot < 0) return (Vec2){ 0, 0 };
    return (Vec2){ s->offset_x, s->offset_y };
}

/* Direction 8-axes pour l'animation (0=override, 1=N..8=NW) */
static inline int  actor_get_dir(const Actor* s)          { static const s8 _lut[3][3]={{8,1,2},{7,0,3},{6,5,4}}; return _lut[s->dir_y+1][s->dir_x+1]; }
static inline void actor_set_dir(Actor* s, int dir)       { static const s8 _dx[]={0,0,1,1,1,0,-1,-1,-1}; static const s8 _dy[]={0,-1,-1,0,1,1,1,0,-1}; if(dir>=0&&dir<=8){s->dir_x=_dx[dir];s->dir_y=_dy[dir];} }
static inline void actor_set_auto_dir(Actor* s, int v)    { s->auto_dir=v?1:0; }
/* La lecture manquait : `auto_dir` s'écrivait sans pouvoir se relire, donc un
   script qui voulait le basculer devait tenir son propre drapeau à côté. */
static inline int  actor_get_auto_dir(const Actor* s)     { return s->auto_dir; }

/* Direction : vecteur discret (-1|0|1) indépendant du flip */
static inline Vec2 actor_get_direction(const Actor* s) {
    return (Vec2){ s->dir_x, s->dir_y };
}
static inline void actor_set_direction(Actor* s, Vec2 v) {
    s->dir_x = (v.x > 0) - (v.x < 0);   /* clamp à -1/0/1 */
    s->dir_y = (v.y > 0) - (v.y < 0);
}

/* Activation / destruction */
static inline void actor_destroy_internal(Actor* s)  { s->active=0; s->visible=0; }

/* Input */
static inline int input_held(int b)    { return (_g_keys_held   &(u32)b)?1:0; }
static inline int input_pressed(int b) { return (_g_keys_pressed&(u32)b)?1:0; }

/* Axe -1/0/1 par composante, dérivé de la croix directionnelle — pas d'état
   propre, juste la différence des deux boutons opposés lus sur _g_keys_held.
   Un seul appel côté script (input.get_axis()) plutôt que deux fonctions à
   recombiner soi-même : x et y sont lus le même frame, jamais désynchronisés. */
static inline Vec2 input_get_axis(void) {
    Vec2 a;
    a.x = ((_g_keys_held & BTN_RIGHT) ? 1 : 0) - ((_g_keys_held & BTN_LEFT) ? 1 : 0);
    a.y = ((_g_keys_held & BTN_DOWN)  ? 1 : 0) - ((_g_keys_held & BTN_UP)   ? 1 : 0);
    return a;
}

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
static inline int  actor_get_pal(const Actor* s)    { return s->pal_bank; }
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
/* Interpolation linéaire entre a et b, à la fraction num/den (mêmes entiers
   que le reste de l'API — pas de virgule flottante sur GBA). Ex: une valeur
   qui glisse de 0 à 100 sur 30 frames : math.lerp(0, 100, frame, 30). */
static inline int math_lerp(int a, int b, int num, int den) {
    if (den == 0) return a;
    return a + (b - a) * num / den;
}
/* Comme math.lerp, mais en courbant la fraction num/den avant de l'appliquer
   (quadratique — pas de sinus/flottant sur GBA) :
     "in"     démarre lentement, accélère à l'arrivée (ex: chute) ;
     "out"    démarre vite, ralentit à l'arrivée (ex: freinage, rebond) ;
     "in_out" les deux, symétriques autour du milieu. */
static inline int math_ease(int a, int b, int num, int den, int kind) {
    if (den <= 0) return a;
    if (num <= 0) return a;
    if (num >= den) return b;
    int t = num, d = den, t2;
    switch (kind) {
        case EASE_OUT:
            t2 = d - (d - t) * (d - t) / d;
            break;
        case EASE_IN_OUT:
            if (t < d / 2) t2 = 2 * t * t / d;
            else { int u = d - t; t2 = d - 2 * u * u / d; }
            break;
        default: /* EASE_IN */
            t2 = t * t / d;
            break;
    }
    return a + (b - a) * t2 / d;
}

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

/* Trigonométrie — réutilise SIN_LUT/gba_sin/gba_cos (déjà écrits plus haut
   pour la matrice affine) : même échelle Q8 (×256) que le hardware, donc pas
   de nouvelle table à maintenir en cohérence. */
static inline int math_sin(int deg) { return gba_sin(deg); }
static inline int math_cos(int deg) { return gba_cos(deg); }

/* Racine carrée entière (méthode du chiffre binaire) — pas de sqrt() flottant
   sur GBA. Négatif ou nul → 0 plutôt que NaN. */
static inline int math_sqrt(int x) {
    if (x <= 0) return 0;
    u32 n = (u32)x, res = 0, bit = 1u << 30;
    while (bit > n) bit >>= 2;
    while (bit != 0) {
        if (n >= res + bit) { n -= res + bit; res = (res >> 1) + bit; }
        else res >>= 1;
        bit >>= 2;
    }
    return (int)res;
}

/* Angle en degrés (0-359) du vecteur (x, y) — même convention d'axes que
   self.rotation puisque calculé par dichotomie CONTRE gba_sin/gba_cos plutôt
   qu'avec une approximation séparée : toujours cohérent avec la matrice
   affine réellement posée à l'écran. sin croît et cos décroît sur [0, 90],
   donc sin(d)*ax - cos(d)*ay est monotone → la dichotomie cherche son zéro. */
static inline int math_atan2(int y, int x) {
    if (x == 0 && y == 0) return 0;
    int ax = math_abs(x), ay = math_abs(y);
    int deg;
    if (ay == 0) deg = 0;
    else if (ax == 0) deg = 90;
    else {
        int lo = 0, hi = 90;
        while (hi - lo > 1) {
            int mid = (lo + hi) / 2;
            if (gba_sin(mid) * ax >= gba_cos(mid) * ay) hi = mid; else lo = mid;
        }
        deg = hi;
    }
    if (x >= 0 && y >= 0) return deg;
    if (x <  0 && y >= 0) return 180 - deg;
    if (x <  0 && y <  0) return 180 + deg;
    return 360 - deg;
}

/* Juiciness — effets de feedback sur le sprite (self:squash, self:stretch,
   self:bounce, self:shake, self:flash, self:blink, self:pulse, self:pop,
   self:wobble). Chacun est une fonction PURE de (t, duration, amount) :
   aucun état caché, aucune coroutine (impossible sur GBA, cf.
   ARCHITECTURE.md) — c'est l'appelant qui fait avancer `t` d'une frame à
   l'autre et qui décide où ce compteur vit (une variable de tête du script,
   ou une GlobalVar quand plusieurs scripts la regardent). Au-delà de
   `duration`, chacun retombe à son état neutre (scale 100, offset 0,
   rotation 0, pal 0, visible true) — rien à réinitialiser à la main.
   Ne composent QUE scripting/api.py, « self.sprite_scale/sprite_offset/
   sprite_rotation/pal/visible » et math_ease/math_lerp/math_rand
   ci-dessus : un script Lua pourrait écrire la même chose à la main. */
static inline void actor_squash(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    Vec2 v;
    v.x = math_ease(100 + amount, 100, t, duration, EASE_OUT);
    v.y = math_ease(100 - amount, 100, t, duration, EASE_OUT);
    actor_set_sprite_scale(s, v);
}
static inline void actor_stretch(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    Vec2 v;
    v.x = math_ease(100 - amount, 100, t, duration, EASE_OUT);
    v.y = math_ease(100 + amount, 100, t, duration, EASE_OUT);
    actor_set_sprite_scale(s, v);
}
static inline void actor_bounce(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int half = math_max(1, duration / 2);
    int y;
    if (t <= half) y = -math_ease(0, amount, t, half, EASE_OUT);
    else           y =  math_ease(-amount, 0, t - half, math_max(1, duration - half), EASE_IN);
    Vec2 o = actor_get_sprite_offset(s);
    o.y = y;
    actor_set_sprite_offset(s, o);
}
static inline void actor_shake(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int decayed = math_ease(amount, 0, t, math_max(1, duration), EASE_OUT);
    Vec2 o;
    o.x = math_rand(-decayed, decayed);
    o.y = math_rand(-decayed, decayed);
    actor_set_sprite_offset(s, o);
}
static inline void actor_flash(Actor* s, int t, int duration, int pal) {
    actor_set_pal(s, (t >= 0 && t < duration) ? pal : 0);
}
static inline void actor_blink(Actor* s, int t, int duration, int interval) {
    if (t < 0 || t >= duration) { actor_set_visible(s, 1); return; }
    interval = math_max(1, interval);
    actor_set_visible(s, ((t / interval) % 2) == 0);
}
static inline void actor_pulse(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int half = math_max(1, duration / 2);
    int a;
    if (t <= half) a = math_ease(100, 100 + amount, t, half, EASE_OUT);
    else           a = math_ease(100 + amount, 100, t - half, math_max(1, duration - half), EASE_IN);
    actor_set_sprite_scale(s, (Vec2){ a, a });
}
static inline void actor_pop(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int split = math_max(1, duration * 3 / 5);
    int a;
    if (t <= split) a = math_ease(0, 100 + amount, t, split, EASE_OUT);
    else            a = math_ease(100 + amount, 100, t - split, math_max(1, duration - split), EASE_IN_OUT);
    actor_set_sprite_scale(s, (Vec2){ a, a });
}
static inline void actor_wobble(Actor* s, int t, int duration, int amount) {
    t = math_clamp(t, 0, duration);
    int period = math_max(1, duration / 3);
    int half = math_max(1, period / 2);
    int phase = t % period;
    int decayed = amount * (duration - t) / math_max(1, duration);
    int deg;
    if (phase < half) deg = math_lerp(-decayed, decayed, phase, half);
    else               deg = math_lerp(decayed, -decayed, phase - half, math_max(1, period - half));
    actor_set_sprite_rotation(s, ((deg % 360) + 360) % 360);
}

/* Caméra — suivi avec zone morte (dead-zone follow) */
static inline void camera_follow(Vec2 target, int mx, int my) {
    int tx = target.x, ty = target.y;
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
extern int  ui_image_state    (int img);

/* Visibilité — commune aux trois types d'élément (texte, panel, image) :
   `ui.get("nom")` résout au NOM d'élément DIRECTEMENT en `UIELEM_*` (cf.
   ui_element_constant), donc AUCUN appel de fonction pour `ui.get` lui-même
   — seul `self:show()`/`self:hide()` en émettent un, vers celle-ci. */
extern void ui_element_show(int idx, int on);

/* ── Listes d'interface (ROADMAP v0.22) ───────────────────────────
   La NAVIGATION d'un menu, et rien d'autre : le moteur suit un index, le
   script écrit ce que chaque rangée affiche. `list.row(...)` rend la zone de
   texte d'une rangée, à passer à `text_draw_in` — un item est une ligne de
   donnée, pas un objet d'interface. */
extern int  ui_list_count    (int l);
extern void ui_list_set_count(int l, int n);
extern int  ui_list_index    (int l);
extern void ui_list_set_index(int l, int i);
extern int  ui_list_first    (int l);
extern int  ui_list_row      (int l, int r);

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
