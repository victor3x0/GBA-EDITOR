/* gba_engine.h — fonctions utilitaires GBA bas-niveau (statiques, non générées).
   Inclus UNE SEULE FOIS depuis main.c. */
#ifndef GBA_ENGINE_H
#define GBA_ENGINE_H

#include <gba_video.h>
#include <gba_sprites.h>
#include <gba_dma.h>
#include <gba_systemcalls.h>
#include <gba_interrupt.h>
#include <gba_input.h>

/* ── Accès mémoire GBA ──────────────────────────────────────────── */
#define TILE_RAM(cbb)  ((vu16*)(0x06000000+(cbb)*0x4000))
#define MAP_RAM(sbb)   ((vu16*)(0x06000000+(sbb)*0x800))
#define PAL_BG_RAM     ((vu16*)0x05000000)
#define OBJ_VRAM       ((vu16*)0x06010000)
#define PAL_OBJ_RAM    ((vu16*)0x05000200)
#define BGOFS(n)       (*((vu16*)(0x04000010+(n)*4)))
#define BGVOFS(n)      (*((vu16*)(0x04000012+(n)*4)))

/* ── Copie mot-16 vers VRAM ──────────────────────────────────────── */
static void copy16(vu16*d, const void*s, u32 b) {
    const u16*p = (const u16*)s;
    for (u32 i = 0; i < b/2; i++) d[i] = p[i];
}

/* ── Chargement map BG avec tuilage source ───────────────────────── */
/* gcols/grows = taille GBA (32 ou 64), tw/th = taille de la source  */
static void load_map(vu16*dst, const void*src,
                     int tw, int th, int gcols, int grows) {
    const u16*m = (const u16*)src;
    for (int y = 0; y < grows; y++) {
        for (int x = 0; x < gcols; x++) {
            u16 t = (x < tw && y < th) ? m[y*tw + x] : 0;
            int qx = x<32 ? x : x-32, qy = y<32 ? y : y-32;
            vu16*d = dst;
            if (x>=32 && y>=32) d += 0xC00;
            else if (y>=32)     d += 0x800;
            else if (x>=32)     d += 0x400;
            d[qy*32+qx] = t;
        }
    }
}

/* ── Streaming de map 2D (grands niveaux qui défilent) ────────────── */
/* Fenêtre VRAM win_w×win_h (≤64) qui wrappe ; bg_base_col/row = coin haut-gauche
   monde chargé. Au scroll, on recopie la colonne/ligne entrante dans sa case
   VRAM (world & 63). `map` = tilemap COMPLÈTE en ROM (tiles_w×tiles_h SE, row-
   major). `dst` = MAP_RAM(sbb). Un seul fond streamé par scène. Pattern Tonc. */
static int bg_base_col, bg_base_row;

/* Écrit une SE à (c,r) dans la fenêtre en gérant les quadrants d'une map 64-large
   (SBB contigus : +0x400 droite, +0x800 bas, +0xC00 coin) — comme load_map. */
static void bg_se_write(vu16 *dst, int c, int r, u16 se) {
    if (c >= 32 && r >= 32) dst += 0xC00;
    else if (r >= 32)       dst += 0x800;
    else if (c >= 32)       dst += 0x400;
    dst[(r & 31)*32 + (c & 31)] = se;
}

static void bg_load_col(vu16 *dst, const unsigned short *map,
                        int tiles_w, int tiles_h, int win_h, int wc) {
    for (int r = bg_base_row; r < bg_base_row + win_h; r++) {
        u16 se = (wc < tiles_w && r < tiles_h) ? map[r*tiles_w + wc] : 0;
        bg_se_write(dst, wc & 63, r & 63, se);
    }
}

static void bg_load_row(vu16 *dst, const unsigned short *map,
                        int tiles_w, int tiles_h, int win_w, int wr) {
    for (int c = bg_base_col; c < bg_base_col + win_w; c++) {
        u16 se = (c < tiles_w && wr < tiles_h) ? map[wr*tiles_w + c] : 0;
        bg_se_write(dst, c & 63, wr & 63, se);
    }
}

static void __attribute__((unused)) bg_stream_init(
        vu16 *dst, const unsigned short *map,
        int tiles_w, int tiles_h, int win_w, int win_h) {
    bg_base_col = 0; bg_base_row = 0;
    for (int r = 0; r < win_h; r++)
        for (int c = 0; c < win_w; c++) {
            u16 se = (c < tiles_w && r < tiles_h) ? map[r*tiles_w + c] : 0;
            bg_se_write(dst, c, r, se);
        }
}

/* Horizontal AVANT vertical : la ligne entrante (load_row) utilise le
   bg_base_col déjà mis à jour et corrige la case-coin. */
static void __attribute__((unused)) bg_stream_update(
        vu16 *dst, const unsigned short *map, int tiles_w, int tiles_h,
        int win_w, int win_h, int stream_h, int stream_v, int cam_x, int cam_y) {
    if (stream_h) {
        int cc = cam_x >> 3;
        while (bg_base_col < cc) { bg_load_col(dst, map, tiles_w, tiles_h, win_h, bg_base_col + 64); bg_base_col++; }
        while (bg_base_col > cc) { bg_base_col--; bg_load_col(dst, map, tiles_w, tiles_h, win_h, bg_base_col); }
    }
    if (stream_v) {
        int cr = cam_y >> 3;
        while (bg_base_row < cr) { bg_load_row(dst, map, tiles_w, tiles_h, win_w, bg_base_row + 64); bg_base_row++; }
        while (bg_base_row > cr) { bg_base_row--; bg_load_row(dst, map, tiles_w, tiles_h, win_w, bg_base_row); }
    }
}

/* ── Layers BG vivants — shadows de registres ────────────────────── */
/* DISPCNT et BGxCNT sont posés à l'init de scène puis modifiables en cours
   de jeu (Lua). On en garde une shadow pour changer un champ (visibilité,
   priorité, screenblock) sans relire ni recomposer le reste — et parce que
   BGxHOFS/VOFS, eux, sont réellement write-only : le décalage de scroll doit
   vivre en RAM. `bg` = bg_slot 0-3 = le BG hardware, même index que dans
   l'éditeur.

   `g_bg_ofs_*` = décalage de scroll PROPRE au layer, additionné au scroll
   caméra à chaque frame par scene_tick (parallax autonome, secousse, layer
   d'UI qu'on fait glisser). Un layer sans image (UI/texte) n'est pas touché
   par le tick : pour lui, l'écriture directe ci-dessous fait foi. */

void layer_show        (int bg, int on);
int  layer_is_visible  (int bg);
void layer_set_priority(int bg, int prio);
int  layer_get_priority(int bg);
void layer_set_scroll  (int bg, int x, int y);
void layer_scroll_by   (int bg, int dx, int dy);
int  layer_get_scroll_x(int bg);
int  layer_get_scroll_y(int bg);
void layer_set_map     (int bg, int sbb);
int  layer_get_map     (int bg);

/* ── Windows (régions d'écran) ───────────────────────────────────── */
/* Une window ne DESSINE rien : c'est un pochoir. Elle dit, par région de
   l'écran, quels layers / sprites ont le droit de s'afficher et si le
   blending s'y applique. L'apparence vient de ce qu'on met dedans.

   Régions (`r`) :
     0 = WIN0        rectangle 0      priorité la plus forte
     1 = WIN1        rectangle 1
     2 = WINR_OBJ    fenêtre-objet    découpée par les sprites en obj_mode 2
     3 = WINR_OUT    tout le reste    la plus faible
   Un pixel prend les droits de la première région qui le contient.

   Piège matériel : dès qu'UNE window est active, WINR_OUT régit tout le reste
   de l'écran. D'où le défaut posé par window_reset() — tout autorisé partout
   — pour qu'activer une window ne vide pas l'écran par surprise. */

/* Ids de région — préfixe WINR_ pour ne pas entrer en collision avec les
   WIN_* de libtonc (masques de bits, sémantique différente). */
#define WINR_0     0
#define WINR_1     1
#define WINR_OBJ   2
#define WINR_OUT   3

void window_show      (int n, int on);      /* n : 0=WIN0, 1=WIN1, 2=fenêtre-objet */
int  window_is_visible(int n);
void window_set       (int n, int x, int y, int w, int h);  /* n : 0 ou 1 */
void window_set_layer (int r, int bg, int on);
int  window_get_layer (int r, int bg);
void window_set_obj   (int r, int on);
void window_set_blend (int r, int on);

/* ── Blending (mélange de couleurs) ──────────────────────────────── */
/* Deux jeux de cibles, pas un : le **dessus** (`side` 0, ce qui est mélangé)
   et le **dessous** (`side` 1, ce avec quoi on mélange, situé DERRIÈRE selon
   les priorités). L'alpha ne se produit que là où un pixel du dessus a
   effectivement un pixel du dessous derrière lui — d'où les effets « qui ne
   marchent pas » quand on oublie de désigner le dessous.

   Modes : 0 = aucun, 1 = alpha (dessus × eva + dessous × evb),
           2 = éclaircir vers le blanc, 3 = assombrir vers le noir.
   Les modes 2 et 3 n'utilisent QUE le dessus, et l'intensité vient de
   blend_set_fade() — pas de blend_set_alpha().

   Deux portes en amont : un sprite en obj_mode 1 force l'alpha pour lui seul,
   quelles que soient les cibles ; et window_set_blend() décide des RÉGIONS où
   tout ceci s'applique. */

void blend_set_mode    (int mode);
int  blend_get_mode    (void);
void blend_set_layer   (int side, int bg, int on);
void blend_set_obj     (int side, int on);
void blend_set_backdrop(int side, int on);
void blend_set_alpha   (int eva, int evb);   /* 0-16 chacun, mode 1 */
void blend_set_fade    (int evy);            /* 0-16, modes 2 et 3 */

/* ── Shadow OAM ──────────────────────────────────────────────────── */
/* Déclarée ici et non en fin de fichier : le rendu de texte en sprites y écrit,
   et il est défini plus bas. */
static OBJATTR shadow_oam[128];

/* ── Texte ───────────────────────────────────────────────────────── */
/* Le texte vit sur LE layer d'UI de la scène (`Scene.text_bg`) et nulle part
   ailleurs : tuiles de glyphes comme surface de composition occupent le
   charblock de ce layer, et un charblock appartient à un layer. D'où l'absence
   de paramètre `layer` : il serait mensonger.

   `tx`/`ty` sont en TUILES dans toute l'API — l'ORIGINE d'un texte est
   alignée à la tuile. C'est le placement des glyphes ENTRE EUX qui devient
   pixellisé en proportionnel (cf. FontInfo.proportional). Garder l'origine en
   tuiles laisse `text_clear` et les windows raisonner sur les mêmes unités que
   le reste du moteur.

   Un texte est stocké en codepoints Unicode, pas en glyphes : la
   correspondance se fait à l'affichage via la police courante, ce qui rend un
   texte indépendant de la police (nécessaire en v0.8 pour les traductions). */

/* Un glyphe peut couvrir PLUSIEURS caractères (ligature : « ... » dessiné
   d'un bloc) et occuper PLUSIEURS tuiles (case 16×16 dans une planche 8×8).
   D'où les tables parallèles ci-dessous, une entrée par glyphe.

   `cp` porte le PREMIER codepoint de chaque glyphe et reste trié : la
   dichotomie y trouve un groupe de candidats partageant ce caractère
   d'attaque. Dans un groupe, l'émission range les séquences de la plus
   longue à la plus courte — la première correspondance complète trouvée en
   balayant est donc la plus longue, sans comparer les candidats entre eux. */
typedef struct FontInfo {
    const unsigned int*   tiles;    /* glyphes, 8 mots par tuile */
    int                   n_tiles;
    const unsigned short* pal;      /* 16 couleurs BGR555 */
    const unsigned short* cp;       /* 1er codepoint de chaque glyphe, TRIÉ */
    const unsigned short* slot;     /* index de 1ère tuile, parallèle à cp */
    const unsigned short* seq;      /* séquences de codepoints, concaténées */
    const unsigned short* seq_off;  /* offset de la séquence dans `seq` */
    const unsigned char*  seq_len;  /* longueur de la séquence (>= 1) */
    const unsigned char*  gw;       /* largeur du glyphe, en tuiles */
    const unsigned char*  gh;       /* hauteur du glyphe, en tuiles */
    int                   n_glyphs;
    int                   tiles_x;  /* cellule PAR DÉFAUT (avance de secours) */
    int                   tiles_y;  /* et interligne */
    /* Chasses, avance de secours et interligne sont émis DÉJÀ RÉSOLUS (en
       pixels) : le rendu les lit sans se demander quel chemin il suit. */
    const unsigned char*  adv;      /* chasse de chaque glyphe, en PIXELS */
    int                   cell_w;   /* avance d'un caractère absent, en px */
    int                   line_h;   /* interligne en px */
    int                   composited; /* 1 = composition pixel, 0 = tilemap */
} FontInfo;

extern const FontInfo g_fonts[];
extern const unsigned short* const g_texts[];
extern const unsigned short g_text_len[];

/* ── Balisage des textes ──────────────────────────────────────────
   Le langage d'écriture (`[speed=4]`, `[wave]…[/wave]`, `$score`) est résolu
   AU BUILD : le moteur n'embarque aucun parseur. Ce qu'il reçoit est déjà
   séparé — des codepoints d'un côté, une piste d'événements de l'autre.

   `at`/`end` sont des index dans les codepoints du texte, `end` exclu ; une
   balise ponctuelle a `end == at`. Les événements d'un texte sont triés par
   `at`, ce qui permet de les consommer avec un simple curseur pendant qu'on
   parcourt les codepoints.

   Une valeur interpolée occupe UN codepoint, TEXT_CP_VALUE — un non-caractère
   Unicode, donc jamais un vrai glyphe. L'événement TEXT_EV_VALUE qui lui
   correspond porte l'index de sa source dans `g_text_values`, un pointeur sur
   le global à lire. Les constantes, elles, n'arrivent jamais jusqu'ici : leurs
   chiffres sont cuits dans les codepoints. */
#define TEXT_CP_VALUE 0xFFFFu

enum {
    TEXT_EV_SPEED = 0,  /* value = frames par caractère */
    TEXT_EV_PAUSE,      /* value = frames d'attente     */
    TEXT_EV_WAVE,       /* portée                       */
    TEXT_EV_SHAKE,      /* portée                       */
    TEXT_EV_COLOR,      /* portée, value = index d'encre */
    TEXT_EV_VALUE       /* value = index dans g_text_values */
};

typedef struct TextEvent {
    unsigned short at, end;
    short          value;
    unsigned char  kind;
    unsigned char  pad;
} TextEvent;

extern const TextEvent* const g_text_events[];
extern const unsigned short   g_text_ev_count[];
/* INDEX de global, pas pointeur : chaque global garde son type C (un `u8` coûte
   un octet), donc aucun tableau de pointeurs ne peut les contenir tous sans
   mentir sur l'un d'eux. La lecture passe par l'accesseur généré avec
   `globals.h`, dont le switch convertit chaque cas. */
extern const unsigned short   g_text_values[];
extern int global_read(int i);

/* Une zone de texte AUTHORÉE dans le canvas de scène (cf. models/ui_region.py).
   Elle ne dessine rien : elle dit où le texte se pose, sa largeur de coupe et
   son alignement — ce que `text_draw_box` faisait passer en arguments, en
   moins visible.

   Coordonnées en PIXELS écran, déjà alignées à la tuile pour une cible BG
   (l'émetteur s'en charge). `font` vaut 255 quand la zone hérite de la police
   courante. `target` 1 = OBJ : le rendu sprite n'existe pas encore, ces zones
   ne s'affichent pas — le build le signale plutôt que de laisser chercher. */
typedef struct UIRegionInfo {
    short x, y, w, h;
    unsigned char align;    /* 0 gauche, 1 centre, 2 droite */
    unsigned char font;     /* index dans g_fonts, 255 = police courante */
    unsigned char target;   /* 0 = BG, 1 = OBJ */
    unsigned char anchor;   /* 0 écran, 1 monde, 2 acteur */
    /* Cible OBJ seulement — placement de la bande de sprites, calculé par le
       codegen. RELATIF à la mise en page : une même mise en page sert plusieurs
       scènes, qui n'ont pas le même nombre d'acteurs donc pas la même base.
       Même raisonnement que `FontInfo.slot`. */
    short actor;            /* index dans g_actors, -1 = aucun */
    short oam_rel;          /* 1er slot OAM, relatif à la base de la scène */
    short oam_count;        /* slots occupés par la bande */
    short tile_rel;         /* 1re tuile OBJ, relative à la base */
    short tiles_row;        /* tuiles par rangée de 8 px */
    short rows;             /* rangées de 8 px */
    short anim;             /* budget de glyphes animés (0 = bande seule) */
    unsigned char priority; /* priorité OBJ (0 = devant) */
    unsigned char pal_bank; /* banque de palette OBJ */
} UIRegionInfo;

extern const UIRegionInfo g_ui_regions[];

void text_set_layer(int bg);        /* posé par scene_init depuis Scene.text_bg */
void text_set_tile_base(int t);     /* posé par scene_init — cf. allocateur */
void text_set_font (int f);         /* charge glyphes + palette en VRAM */
int  text_length   (int id);
void text_clear    (int tx, int ty, int w, int h);
/* GRAMMAIRE : position ou conteneur d'abord, contenu ensuite — le même ordre
   qu'en Lua, `codegen._emit_api_call` étant positionnel. Une permutation entre
   les deux couches serait invisible à la relecture des deux côtés. */
void text_draw     (int tx, int ty, int id);
/* Rendu dans une zone authorée — remplace text_draw_box, dont la géométrie
   vivait dans le script.

   Toute primitive qui existe en version « libre » doit exister en version
   « dans une zone », sinon le premier besoin non couvert renvoie l'auteur aux
   coordonnées en tuiles — et il n'en revient pas, puisqu'il a alors deux
   géométries à tenir d'accord à la main. */
void text_draw_in     (int region, int id);
/* Groupe LECTURE — un texte à tempo introduit un état par zone, donc de quoi
   savoir où il en est. Ces trois-là ne dessinent rien de nouveau : la règle
   des deux primitives d'écriture tient. */
int  text_reading (int region);   /* 1 tant que le texte s'écrit */
void text_skip    (int region);   /* tout révéler d'un coup */
void text_update  (void);         /* une fois par frame, avant oam_update */
void text_clear_in    (int region);             /* vide une zone, BG ou OBJ */
void text_obj_set_base(int oam, int tile);   /* posé par scene_init */
void text_obj_set_actor_fn(int (*fx)(int), int (*fy)(int));

void tilemap_set        (int bg, int tx, int ty, int tile);
int  tilemap_get        (int bg, int tx, int ty);
void tilemap_set_palette(int bg, int tx, int ty, int bank);
void tilemap_set_flip   (int bg, int tx, int ty, int fh, int fv);
void tilemap_fill       (int bg, int tx, int ty, int w, int h, int tile);

#ifdef GBA_ENGINE_IMPL

static u16 g_dispcnt_sh;
static u16 g_bgcnt_sh[4];
static s16 g_bg_ofs_x[4], g_bg_ofs_y[4];

/* Remet les shadows à zéro — appelé en tête de scene_init, AVANT les
   bg_cnt_set/dispcnt_set de la scène (qui les repeuplent). */
static void window_reset(void);
static void blend_reset(void);

/* Remet tout l'état d'affichage à neuf : layers, windows, blending. Appelé en
   tête de scene_init, AVANT les bg_cnt_set/dispcnt_set de la scène — sinon une
   scène hériterait de l'état de la précédente. */
static void display_reset(void) {
    g_dispcnt_sh = 0;
    for (int i = 0; i < 4; i++) {
        g_bgcnt_sh[i] = 0;
        g_bg_ofs_x[i] = 0;
        g_bg_ofs_y[i] = 0;
    }
    window_reset();
    blend_reset();
}

static void bg_cnt_set(int bg, u16 val) {
    bg &= 3;
    g_bgcnt_sh[bg] = val;
    *((vu16*)(0x04000008 + bg*2)) = val;
}

static void dispcnt_set(u16 val) {
    g_dispcnt_sh = val;
    REG_DISPCNT  = val;
}

/* Adresse de la screen entry (tx,ty) d'un layer, en tuiles.
   Gère les 4 tailles de map régulières et le découpage en blocs 32×32
   (SBB contigus : +0x400 droite, +0x800 bas d'une map 64-large, +0xC00
   coin). Les coordonnées wrappent comme le hardware. */
static vu16* bg_se_addr(int bg, int tx, int ty) {
    u16 cnt = g_bgcnt_sh[bg & 3];
    int sbb = (cnt >> 8) & 0x1F;
    int ms  = (cnt >> 14) & 3;
    int gc  = (ms & 1) ? 64 : 32;
    int gr  = (ms & 2) ? 64 : 32;
    tx &= (gc - 1);
    ty &= (gr - 1);
    vu16 *d = MAP_RAM(sbb);
    if (tx >= 32 && ty >= 32) d += 0xC00;
    else if (ty >= 32)        d += (gc == 64) ? 0x800 : 0x400;
    else if (tx >= 32)        d += 0x400;
    return d + (ty & 31) * 32 + (tx & 31);
}

void layer_show(int bg, int on) {
    u16 bit = (u16)(0x0100 << (bg & 3));
    if (on) g_dispcnt_sh |=  bit;
    else    g_dispcnt_sh &= (u16)~bit;
    REG_DISPCNT = g_dispcnt_sh;
}

int layer_is_visible(int bg) {
    return (g_dispcnt_sh & (0x0100 << (bg & 3))) ? 1 : 0;
}

/* Priorité 0-3 : 0 = dessiné DEVANT (même convention que bg_slot). */
void layer_set_priority(int bg, int prio) {
    if (prio < 0) prio = 0;
    if (prio > 3) prio = 3;
    bg_cnt_set(bg, (u16)((g_bgcnt_sh[bg & 3] & ~0x0003) | prio));
}

int layer_get_priority(int bg) { return g_bgcnt_sh[bg & 3] & 3; }

void layer_set_scroll(int bg, int x, int y) {
    bg &= 3;
    g_bg_ofs_x[bg] = (s16)x;
    g_bg_ofs_y[bg] = (s16)y;
    BGOFS(bg)  = (u16)x;
    BGVOFS(bg) = (u16)y;
}

void layer_scroll_by(int bg, int dx, int dy) {
    bg &= 3;
    layer_set_scroll(bg, g_bg_ofs_x[bg] + dx, g_bg_ofs_y[bg] + dy);
}

int layer_get_scroll_x(int bg) { return g_bg_ofs_x[bg & 3]; }
int layer_get_scroll_y(int bg) { return g_bg_ofs_y[bg & 3]; }

/* Bascule de screenblock — double-buffering de tilemap : on prépare une
   carte dans un SBB libre, puis on l'affiche en une écriture (pas de
   tearing). Les tilemap_* suivantes visent le nouveau SBB. */
void layer_set_map(int bg, int sbb) {
    bg_cnt_set(bg, (u16)((g_bgcnt_sh[bg & 3] & ~0x1F00) | ((sbb & 0x1F) << 8)));
}

int layer_get_map(int bg) { return (g_bgcnt_sh[bg & 3] >> 8) & 0x1F; }

/* Écrit l'index de tuile en préservant flip + banque de palette de la
   cellule (repeindre ≠ redessiner, cf. inpainting). */
void tilemap_set(int bg, int tx, int ty, int tile) {
    vu16 *se = bg_se_addr(bg, tx, ty);
    *se = (u16)((*se & 0xFC00) | (tile & 0x03FF));
}

int tilemap_get(int bg, int tx, int ty) { return *bg_se_addr(bg, tx, ty) & 0x03FF; }

void tilemap_set_palette(int bg, int tx, int ty, int bank) {
    vu16 *se = bg_se_addr(bg, tx, ty);
    *se = (u16)((*se & 0x0FFF) | ((bank & 15) << 12));
}

void tilemap_set_flip(int bg, int tx, int ty, int fh, int fv) {
    vu16 *se = bg_se_addr(bg, tx, ty);
    u16 v = (u16)(*se & ~0x0C00);
    if (fh) v |= 0x0400;
    if (fv) v |= 0x0800;
    *se = v;
}

void tilemap_fill(int bg, int tx, int ty, int w, int h, int tile) {
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++)
            tilemap_set(bg, tx + c, ty + r, tile);
}

/* ── Windows ─────────────────────────────────────────────────────── */
/* WININ  : bits 0-5 = WIN0, bits 8-13 = WIN1
   WINOUT : bits 0-5 = extérieur, bits 8-13 = fenêtre-objet
   Dans chaque groupe de 6 : bits 0-3 = BG0-3, bit 4 = OBJ, bit 5 = blending. */

static u16 g_winin_sh, g_winout_sh;

/* Tout autorisé partout, aucune window active. Appelé par display_reset(). */
static void window_reset(void) {
    g_winin_sh  = 0x3F3F;
    g_winout_sh = 0x3F3F;
    REG_WININ   = g_winin_sh;
    REG_WINOUT  = g_winout_sh;
    REG_WIN0H   = 0; REG_WIN0V = 0;
    REG_WIN1H   = 0; REG_WIN1V = 0;
}

void window_show(int n, int on) {
    if (n < 0) n = 0;
    if (n > 2) n = 2;
    u16 bit = (u16)(0x2000 << n);          /* DISPCNT 13=WIN0, 14=WIN1, 15=OBJWIN */
    if (on) g_dispcnt_sh |=  bit;
    else    g_dispcnt_sh &= (u16)~bit;
    REG_DISPCNT = g_dispcnt_sh;
}

int window_is_visible(int n) {
    if (n < 0) n = 0;
    if (n > 2) n = 2;
    return (g_dispcnt_sh & (0x2000 << n)) ? 1 : 0;
}

/* Rectangle en pixels écran. Clampé à 240×160 et jamais inversé : le
   matériel se comporte de façon erratique sur X1>X2 ou X2>240, on ne
   laisse pas ces cas sortir d'ici. */
void window_set(int n, int x, int y, int w, int h) {
    n &= 1;
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (w < 0) w = 0;
    if (h < 0) h = 0;
    if (x > 240) x = 240;
    if (y > 160) y = 160;
    int x2 = x + w, y2 = y + h;
    if (x2 > 240) x2 = 240;
    if (y2 > 160) y2 = 160;
    *((vu16*)(0x04000040 + n*2)) = (u16)((x << 8) | x2);
    *((vu16*)(0x04000044 + n*2)) = (u16)((y << 8) | y2);
}

/* Shadow + décalage du groupe de 6 bits correspondant à la région. */
static u16* win_region_sh(int r, int *shift) {
    switch (r & 3) {
        case WINR_0:  *shift = 0; return &g_winin_sh;
        case WINR_1:  *shift = 8; return &g_winin_sh;
        case WINR_OBJ: *shift = 8; return &g_winout_sh;
        default:      *shift = 0; return &g_winout_sh;
    }
}

static void win_bit_set(int r, int bit, int on) {
    int shift;
    u16 *sh = win_region_sh(r, &shift);
    u16 m   = (u16)(1 << (bit + shift));
    if (on) *sh |=  m;
    else    *sh &= (u16)~m;
    if (sh == &g_winin_sh) REG_WININ  = g_winin_sh;
    else                   REG_WINOUT = g_winout_sh;
}

void window_set_layer(int r, int bg, int on) { win_bit_set(r, bg & 3, on); }

int window_get_layer(int r, int bg) {
    int shift;
    u16 *sh = win_region_sh(r, &shift);
    return (*sh & (1 << ((bg & 3) + shift))) ? 1 : 0;
}

void window_set_obj  (int r, int on) { win_bit_set(r, 4, on); }
void window_set_blend(int r, int on) { win_bit_set(r, 5, on); }

/* ── Texte ───────────────────────────────────────────────────────── */
/* Banque de palette des glyphes et première tuile occupée dans le charblock
   d'UI — mêmes constantes que codegen/font_emit.py (FONT_PAL_BANK,
   FONT_TILE_BASE). La tuile 0 reste vide : c'est elle que pose text_clear. */
#define FONT_PAL_BANK   15

/* Première tuile du charblock occupée par le texte. VARIABLE, posée par
   `scene_init` : le texte n'a pas besoin d'un charblock à lui (95 tuiles de
   glyphes pour 448 réservées), il doit pouvoir se loger APRÈS les tuiles d'un
   fond dans un charblock partagé. Les `slot[]` émis sont relatifs à cette base
   (cf. codegen/font_emit.py), donc rien n'est cuit à la compilation.

   Défaut 1 : la tuile 0 reste vide, c'est elle que pose `text_clear` en mono. */
#define FONT_TILE_BASE_DEFAULT  1

/* DEUX CHEMINS DE RENDU, choisis par la police (FontInfo.composited), jamais
   par un réglage — c'est l'émetteur qui décide (cf. font_emit.render_composited).

   • TILEMAP (composited == 0) — les tuiles de glyphes vivent en VRAM et le
     tilemap pointe dessus. Écrire du texte, c'est poser des index de tuiles :
     coût nul, aucune écriture de pixel. C'est le chemin d'origine.

   • COMPOSITION (composited == 1) — une tuile se pose à 8 px près, donc le
     tilemap ne sait pas placer un glyphe à x=13. On réserve à la place une
     SURFACE de tuiles vierges, le tilemap pointe dessus une fois, et les
     glyphes y sont COMPOSÉS pixel par pixel depuis la ROM. Les tuiles de
     glyphes ne vont alors jamais en VRAM : elles ne servent que de source.

   Ce second point vaut aussi pour une police MONO trop grosse : composer coûte
   la surface et RIEN de plus, quelle que soit la taille de la police. Une
   police de 2000 glyphes (64 Ko de tuiles — impossible, un charblock en fait
   16) devient affichable au prix de 240 tuiles. L'émetteur bascule donc de
   lui-même dès que les glyphes coûtent plus cher que la surface : on prend
   simplement le moins cher des deux.

   Adressage de la surface : déterministe à partir de la position écran,
   `base + (ty % TEXT_SURF_H) * TEXT_SURF_W + (tx % TEXT_SURF_W)`. Aucun état
   d'allocation, donc redessiner au même endroit réutilise les mêmes tuiles —
   c'est ce qui rend la lecture progressive stable, et ce qui
   permet à deux boîtes de coexister sans se marcher dessus. Limite assumée :
   deux boîtes distantes d'un multiple exact de TEXT_SURF_H rangées partagent
   leurs tuiles. 30×8 = 240 tuiles, soit moins de la moitié du charblock. */
#define TEXT_SURF_W  30   /* largeur d'écran en tuiles */
#define TEXT_SURF_H  8

/* Doit rester d'accord avec ALIGNS de core/models/ui_region.py — c'est
   l'émetteur qui écrit ces valeurs dans g_ui_regions. */
/* Plafond de glyphes animés par zone — tableaux de capture de taille fixe,
   pas d'allocation dynamique sur cible. Doit rester égal à ANIM_GLYPH_MAX de
   core/models/ui_region.py, qui dimensionne la réserve côté codegen. */
#define TEXT_ANIM_MAX 32

#define TEXT_ALIGN_LEFT   0
#define TEXT_ALIGN_CENTER 1
#define TEXT_ALIGN_RIGHT  2

static int g_text_layer = -1;
static int g_text_cbb   = 0;
static int g_text_tile_base = FONT_TILE_BASE_DEFAULT;
static const FontInfo *g_font = 0;

/* Le LAYER (0-3) où s'affiche le texte. Sert aux écritures de tilemap. */
void text_set_layer(int bg) {
    g_font = 0;            /* cf. text_set_font : la destination change */
    g_text_layer = (bg >= 0 && bg <= 3) ? bg : -1;
    g_text_cbb   = (bg >= 0 && bg <= 3) ? bg : 0;   /* défaut : CBB = layer */
}

/* Le CHARBLOCK où vivent les tuiles du texte — DISTINCT du layer. C'est ce qui
   permet au texte de squatter le charblock d'un fond au lieu d'en monopoliser
   un : le champ CharBlock de BGxCNT est indépendant du numéro de layer.
   À appeler APRÈS text_set_layer (qui repose le défaut) et AVANT text_set_font. */
void text_set_charblock(int cbb) {
    g_font = 0;            /* cf. text_set_font */
    g_text_cbb = (cbb >= 0 && cbb <= 3) ? cbb : 0;
}

/* Où commencent les tuiles du texte dans ce charblock. Posé par scene_init
   depuis l'allocateur ; à appeler AVANT text_set_font, qui copie les glyphes à
   cette adresse. La borne est la portée d'un index de map (10 bits) : le bloc
   du texte peut déborder sur le charblock suivant comme n'importe quel layer. */
void text_set_tile_base(int t) {
    g_font = 0;            /* cf. text_set_font */
    g_text_tile_base = (t > 0 && t < 1024) ? t : FONT_TILE_BASE_DEFAULT;
}

/* Charge la palette, et les glyphes SEULEMENT en mono : le chemin
   proportionnel compose depuis la ROM et n'a que faire de tuiles de glyphes en
   VRAM — les y copier gaspillerait la place que prend la surface. Une seule
   police résidente à la fois : rappeler cette fonction remplace la précédente
   (coût d'une copie VRAM, pas par frame). */
void text_set_font(int f) {
    const FontInfo *fi = &g_fonts[f];
    /* Idempotent : recharger la police DÉJÀ résidente ne fait rien. Sans cette
       garde, une zone qui déclare sa police (`text_draw_in`) recopierait tous
       ses glyphes en VRAM à chaque frame en chemin mono.

       « Résidente » veut dire : à CETTE adresse. `text_set_layer`,
       `text_set_charblock` et `text_set_tile_base` remettent donc `g_font` à
       zéro — sans quoi un changement de scène qui repose la base sauterait la
       recopie et laisserait le texte pointer des tuiles jamais écrites. */
    if (g_font == fi) return;
    g_font = fi;
    if (g_text_layer < 0 || !fi->tiles) return;
    if (!fi->composited)
        copy16(TILE_RAM(g_text_cbb) + g_text_tile_base * 16, fi->tiles, fi->n_tiles * 32);
    copy16(PAL_BG_RAM + FONT_PAL_BANK * 16, fi->pal, 32);
    /* Même palette côté sprites : une bande de texte OBJ lit PAL_OBJ_RAM, pas
       PAL_BG_RAM. La copier toujours (32 octets) coûte moins cher que de
       savoir si une zone OBJ existe. */
    copy16(PAL_OBJ_RAM + FONT_PAL_BANK * 16, fi->pal, 32);
}

/* Tuile de surface qui rend la case écran (tx, ty). */
/* ── Bloc de composition courant ──────────────────────────────────
   La surface BG et une bande de sprites ne diffèrent que par DEUX choses : où
   sont les tuiles, et comment on les indexe. Tout le reste — mise en page,
   chasses, ligatures, alignement, machine à écrire — est commun. D'où cette
   indirection plutôt qu'un second moteur de composition pour les OBJ : en
   écrire un deuxième, c'était garantir qu'un jour les deux ne coupent plus les
   lignes au même endroit.

   `h == 0` désigne la surface BG, adressée MODULO (elle est partagée par tout
   l'écran, d'où son aliasing). Une bande OBJ est un bloc privé de w×h tuiles,
   adressé directement. */
/* Piste d'événements du texte en cours de rendu. Posée par `text_render_region`
   le temps de l'appel : la mise en page a besoin de savoir, glyphe par glyphe,
   s'il tombe sous une portée animée, et lui passer un paramètre de plus aurait
   traversé quatre fonctions qui n'en ont que faire. */
static const TextEvent *g_ev  = 0;
static int              g_nev = 0;

/* Encre courante — index de couleur dans la sous-palette de la police.
   0 = l'encre d'origine du glyphe, c'est-à-dire aucun remappage. */
static int g_ink = 0;

/* La couleur qui couvre le caractère `i`, ou 0 (encre d'origine). */
static int text_color_at(int i) {
    if (!g_ev) return 0;
    for (int k = 0; k < g_nev; k++) {
        if (g_ev[k].kind != TEXT_EV_COLOR) continue;
        if (i >= g_ev[k].at && i < g_ev[k].end) return g_ev[k].value;
    }
    return 0;
}

/* L'effet qui couvre le caractère `i`, ou 0 s'il n'est pas animé. */
static int text_fx_at(int i) {
    if (!g_ev) return 0;
    for (int k = 0; k < g_nev; k++) {
        int kind = g_ev[k].kind;
        if (kind != TEXT_EV_WAVE && kind != TEXT_EV_SHAKE) continue;
        if (i >= g_ev[k].at && i < g_ev[k].end) return kind;
    }
    return 0;
}

/* Capture : quand `g_cap_max > 0`, la mise en page NE DESSINE PAS les glyphes
   couverts par une portée animée et note où ils tombaient. Ils sortent ainsi de
   la bande (qui garde un trou à leur place) pour recevoir chacun leur sprite —
   c'est ce qui rend un effet par caractère possible sans recomposer toute la
   zone à chaque frame.

   Ce sont bien les glyphes ANIMÉS qui sont capturés, pas les premiers venus :
   le budget `UIRegion.animated_glyphs` réserve de l'OAM pour un effet, pas pour
   un préfixe. Au-delà du budget la capture s'arrête et les glyphes suivants
   retombent dans la bande, en statique — l'écrêtage promis par le modèle. */
static int   g_cap_max = 0;
static int   g_cap_n   = 0;
static short g_cap_x[TEXT_ANIM_MAX], g_cap_y[TEXT_ANIM_MAX], g_cap_gi[TEXT_ANIM_MAX];
static short g_cap_fx[TEXT_ANIM_MAX];   /* TEXT_EV_WAVE | TEXT_EV_SHAKE */
static short g_cap_i [TEXT_ANIM_MAX];   /* rang du caractère — déphasage */
static short g_cap_ink[TEXT_ANIM_MAX];  /* encre au moment de la capture */

/* ── Effets par caractère ─────────────────────────────────────────
   Compteur PROPRE au texte, et non `_g_frame` : l'animation d'un texte ne
   dépend pas de la scène, et le moteur n'a pas à remonter jusqu'à une variable
   du code généré pour deux pixels de déplacement. */
static int g_text_frame = 0;

/* Une sinusoïde de 16 pas, amplitude 2 px. Une table plutôt qu'un calcul : le
   GBA n'a pas de flottant, et 16 octets valent mieux qu'une approximation. */
static const signed char g_wave_lut[16] =
    { 0, 1, 1, 2, 2, 2, 1, 1, 0, -1, -1, -2, -2, -2, -1, -1 };

/* Déplacement du glyphe `i` pour l'effet `fx`, à la frame courante.
   `i` est le RANG DU CARACTÈRE : c'est lui qui déphase, sinon toute la portée
   monterait et descendrait d'un bloc au lieu d'onduler. */
static void text_fx_offset(int fx, int i, int *dx, int *dy) {
    if (fx == TEXT_EV_WAVE) {
        *dy += g_wave_lut[((g_text_frame >> 1) + i) & 15];
    } else if (fx == TEXT_EV_SHAKE) {
        /* Pseudo-aléatoire pauvre mais suffisant : deux multiplicateurs
           premiers entre eux, donc pas de motif visible sur quelques dizaines
           de caractères. */
        *dx += (((g_text_frame * 7 + i * 13) >> 1) & 3) - 1;
        *dy += (((g_text_frame * 5 + i * 11) >> 1) & 3) - 1;
    }
}

static volatile u32 *g_blit_mem = 0;
static int g_blit_tile0 = 0;
static int g_blit_w  = TEXT_SURF_W;
static int g_blit_h  = 0;          /* 0 = surface BG (modulo) */
static int g_blit_ox = 0, g_blit_oy = 0;   /* origine du bloc, en TUILES */

static void blit_use_bg_surface(void) {
    g_blit_mem   = (volatile u32*)(TILE_RAM(g_text_cbb));
    g_blit_tile0 = g_text_tile_base;
    g_blit_w     = TEXT_SURF_W;
    g_blit_h     = 0;
    g_blit_ox    = g_blit_oy = 0;
}

/* Tuile du bloc courant couvrant la case écran (tx, ty), ou -1 si la case est
   HORS du bloc — seule une bande peut être débordée, la surface BG bouclant sur
   elle-même. Retourner -1 plutôt que de replier fait qu'un texte trop long pour
   sa zone est TRONQUÉ au lieu d'aller écrire dans le sprite du voisin. */
static int text_surf_tile(int tx, int ty) {
    if (g_blit_h == 0) {
        int cx = tx % TEXT_SURF_W, cy = ty % TEXT_SURF_H;
        if (cx < 0) cx += TEXT_SURF_W;
        if (cy < 0) cy += TEXT_SURF_H;
        return g_blit_tile0 + cy * TEXT_SURF_W + cx;
    }
    int cx = tx - g_blit_ox, cy = ty - g_blit_oy;
    if (cx < 0 || cy < 0 || cx >= g_blit_w || cy >= g_blit_h) return -1;
    return g_blit_tile0 + cy * g_blit_w + cx;
}

/* Masque des quartets NON NULS de `v` : 0xF là où le pixel est encré, 0 là où
   il est transparent (index 0). C'est ce qui permet d'écrire un glyphe sans
   effacer le voisin dont il chevauche la tuile — le cas normal dès que les
   chasses ne sont plus des multiples de 8.

   Les bits d'un quartet sont ramenés sur son bit 0 (les décalages ne dépassent
   jamais 3, donc aucun quartet ne contamine son voisin), puis `* 0xF` rétablit
   les quatre bits : les bits retenus étant espacés de 4, la multiplication ne
   propage aucune retenue. */
static inline u32 text_nib_mask(u32 v) {
    u32 m = v | (v >> 1);
    m |= m >> 2;
    return (m & 0x11111111u) * 0xFu;
}

/* Remappe toute l'encre d'une rangée de 8 pixels vers `g_ink`.

   `text_nib_mask` donne déjà 0xF par pixel NON transparent : la couleur
   demandée, répétée dans les huit nibbles et masquée, suffit. Le fond reste
   donc transparent — recolorer ne remplit pas la cellule.

   Conséquence assumée : une police à plusieurs encres (dégradé, contour) est
   APLATIE sur une seule couleur. `[color]` désigne une couleur, pas une
   transposition de rampe — supposer un rangement de palette en rampes aurait
   marché sur les polices qui l'ont et produit n'importe quoi sur les autres. */
static inline u32 text_recolor(u32 row) {
    if (!g_ink) return row;
    /* Borné à 15 : au-delà, `0x11111111 * n` déborde le mot de 32 bits et le
       dernier nibble sortirait d'une autre couleur que les sept autres. Le
       build refuse déjà la valeur — cette garde protège une ROM dont les
       données auraient été produites autrement. */
    u32 ink = (u32)(g_ink > 15 ? 15 : g_ink);
    return text_nib_mask(row) & (0x11111111u * ink);
}

/* Compose une rangée de 8 pixels 4bpp au point ÉCRAN (px, py), en pixels.
   `row` = un mot de tuile source (8 quartets, quartet i = pixel x+i).

   La rangée chevauche deux tuiles dès que px n'est pas un multiple de 8 : c'est
   le cas normal en proportionnel, d'où les deux écritures. La VRAM refuse les
   accès 8 bits, tout passe donc par des mots de 32. */
static void text_blit_row(int px, int py, u32 row) {
    if (!row) return;                       /* rangée entièrement transparente */
    volatile u32 *base = g_blit_mem;
    int shift = (px & 7) * 4;
    u32 m     = text_nib_mask(row);
    int t0    = text_surf_tile(px >> 3, py >> 3);
    if (t0 >= 0) {
        volatile u32 *w0 = base + t0 * 8 + (py & 7);
        *w0 = (*w0 & ~(m << shift)) | ((row << shift) & (m << shift));
    }
    /* Débord sur la tuile suivante — seulement si le glyphe n'est pas aligné.
       Le décalage inverse serait indéfini pour shift == 0, d'où le garde. */
    if (shift) {
        int rs = 32 - shift;
        u32 mh = m >> rs;
        int t1 = text_surf_tile((px >> 3) + 1, py >> 3);
        if (mh && t1 >= 0) {
            volatile u32 *w1 = base + t1 * 8 + (py & 7);
            *w1 = (*w1 & ~mh) | ((row >> rs) & mh);
        }
    }
}

/* Index du glyphe correspondant à s[i..len), au PLUS LONG. Retourne -1 si
   aucun ne correspond, sinon l'index dans les tables parallèles ; *consumed
   reçoit le nombre de codepoints avalés (1 pour un caractère simple, plus
   pour une ligature).

   Dichotomie sur le 1er codepoint, puis balayage du groupe. Comme l'émission
   trie les séquences longues d'abord DANS le groupe, la première qui
   correspond entièrement est la plus longue — c'est ce qui fait qu'une police
   contenant « . » et « ... » rend bien la ligature et non trois points. */
static int text_find(const unsigned short* s, int i, int len, int* consumed) {
    *consumed = 1;
    if (!g_font || g_font->n_glyphs <= 0) return -1;
    int cp = s[i];
    int lo = 0, hi = g_font->n_glyphs - 1, found = -1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        int v = g_font->cp[mid];
        if (v == cp) { found = mid; hi = mid - 1; }   /* remonter au 1er du groupe */
        else if (v < cp) lo = mid + 1;
        else hi = mid - 1;
    }
    if (found < 0) return -1;
    for (int k = found; k < g_font->n_glyphs && g_font->cp[k] == cp; k++) {
        int n = g_font->seq_len[k];
        if (i + n > len) continue;              /* déborde du texte */
        const unsigned short* q = g_font->seq + g_font->seq_off[k];
        int ok = 1;
        for (int j = 1; j < n; j++)             /* j=0 déjà vérifié par cp */
            if (s[i + j] != q[j]) { ok = 0; break; }
        if (ok) { *consumed = n; return k; }
    }
    return -1;
}

/* ── Matérialisation d'une entrée de la table ─────────────────────
   Un texte de la table est en ROM et peut porter des valeurs à interpoler
   (TEXT_CP_VALUE). Les substituer produit une suite de codepoints DIFFÉRENTE —
   « 0 » et « 128 » ne font pas la même longueur —, qui vit donc en RAM. Même
   procédé que la mise en forme d'un nombre : un seul chemin de rendu, une
   seule mise en page, un seul effacement.

   Les positions des ÉVÉNEMENTS se décalent d'autant : les recopier telles
   quelles ferait glisser un `[wave]` d'autant de caractères que les chiffres
   ajoutés. La piste est donc recopiée et décalée en même temps que le texte.

   Sans valeur à substituer — le cas courant — rien n'est copié : on rend les
   tableaux ROM tels quels. */
#define TEXT_MAT_MAX 192       /* codepoints matérialisés d'un texte */
#define TEXT_EV_MAX  24        /* événements d'un texte, après décalage */
#define TEXT_NUM_MAX 12        /* -2147483648 = 11 caractères */

static unsigned short g_mat_cp[TEXT_MAT_MAX];
static TextEvent      g_mat_ev[TEXT_EV_MAX];
/* Index source → index matérialisé. Une CARTE plutôt qu'un rattrapage des
   portées au fil de l'eau : `[wave]` peut couvrir une valeur, commencer avant
   et finir après, s'imbriquer — recaler ses bornes à la main demanderait de
   rejouer tous ces cas, alors que la carte les traite tous pareil. */
static short          g_mat_map[TEXT_MAT_MAX + 1];
static int text_num_cp(int value, unsigned short *buf);

/* La suite prête à rendre pour `id`. Renvoie sa longueur ; `*out` pointe la
   ROM ou le tampon, et `*ev`/`*nev` la piste correspondante. */
static int text_materialize(int id, const unsigned short **out,
                            const TextEvent **ev, int *nev) {
    const unsigned short *s = g_texts[id];
    const TextEvent *e = g_text_events[id];
    int len = g_text_len[id], ne = g_text_ev_count[id];

    int has_value = 0;
    for (int k = 0; k < ne; k++)
        if (e[k].kind == TEXT_EV_VALUE) { has_value = 1; break; }
    if (!has_value) { *out = s; *ev = e; *nev = ne; return len; }

    int lim = len < TEXT_MAT_MAX ? len : TEXT_MAT_MAX;
    int o = 0;
    for (int i = 0; i < lim; i++) {
        g_mat_map[i] = (short)o;
        if (s[i] != TEXT_CP_VALUE) {
            if (o < TEXT_MAT_MAX) g_mat_cp[o++] = s[i];
            continue;
        }
        int src = -1;
        for (int j = 0; j < ne; j++)
            if (e[j].kind == TEXT_EV_VALUE && e[j].at == i) { src = e[j].value; break; }
        unsigned short num[TEXT_NUM_MAX];
        int n = (src >= 0) ? text_num_cp(global_read(g_text_values[src]), num) : 0;
        for (int d = 0; d < n && o < TEXT_MAT_MAX; d++) g_mat_cp[o++] = num[d];
    }
    g_mat_map[lim] = (short)o;

    int nout = 0;
    for (int k = 0; k < ne && nout < TEXT_EV_MAX; k++) {
        if (e[k].kind == TEXT_EV_VALUE) continue;   /* consommé ci-dessus */
        g_mat_ev[nout] = e[k];
        g_mat_ev[nout].at  = (unsigned short)(e[k].at  <= lim ? g_mat_map[e[k].at]  : o);
        g_mat_ev[nout].end = (unsigned short)(e[k].end <= lim ? g_mat_map[e[k].end] : o);
        nout++;
    }
    *out = g_mat_cp; *ev = g_mat_ev; *nev = nout;
    return o;
}

/* Longueur AFFICHÉE, valeurs substituées — pas la taille du tableau ROM. */
int text_length(int id) {
    const unsigned short *s; const TextEvent *e; int n;
    return text_materialize(id, &s, &e, &n);
}

/* Vide la zone. En mono il suffit de remettre le tilemap sur la tuile 0 ; en
   proportionnel les pixels sont DANS les tuiles de surface, c'est donc elles
   qu'il faut remettre à zéro — sinon le texte suivant s'écrirait par-dessus
   l'ancien, la composition ne faisant que poser de l'encre. */
void text_clear(int tx, int ty, int w, int h) {
    if (g_text_layer < 0) return;
    int prop = g_font && g_font->composited;
    blit_use_bg_surface();          /* text_clear ne vide QUE la surface BG */
    volatile u32 *base = g_blit_mem;
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++) {
            if (prop) {
                volatile u32 *t = base + text_surf_tile(tx + c, ty + r) * 8;
                for (int k = 0; k < 8; k++) t[k] = 0;
            } else {
                tilemap_set(g_text_layer, tx + c, ty + r, 0);
            }
        }
}

/* Fait pointer le tilemap de la zone sur ses tuiles de surface, et les vide.
   Appelé avant toute composition : sans ça la zone montrerait les tuiles de la
   composition précédente, ou n'importe quel index laissé par le décor. */
static void text_surf_prepare(int tx, int ty, int w, int h) {
    volatile u32 *base = g_blit_mem;
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++) {
            int t = text_surf_tile(tx + c, ty + r);
            tilemap_set(g_text_layer, tx + c, ty + r, t);
            tilemap_set_palette(g_text_layer, tx + c, ty + r, FONT_PAL_BANK);
            volatile u32 *p = base + t * 8;
            for (int k = 0; k < 8; k++) p[k] = 0;
        }
}

/* Compose le glyphe `gi` au point ÉCRAN (px, py) en pixels. */
static void text_put_px(int gi, int px, int py) {
    if (!g_font || gi < 0) return;
    int tw = g_font->gw[gi], th = g_font->gh[gi];
    /* `slot` est RELATIF au bloc alloué au texte, donc directement l'offset
       de la source en ROM — plus de base à retrancher. */
    const unsigned int *src = g_font->tiles + g_font->slot[gi] * 8;
    for (int r = 0; r < th; r++)
        for (int c = 0; c < tw; c++) {
            const unsigned int *tile = src + (r * tw + c) * 8;
            for (int k = 0; k < 8; k++)
                text_blit_row(px + c * 8, py + r * 8 + k, text_recolor(tile[k]));
        }
}

/* Pose le glyphe `gi` par le TILEMAP, à la case (tx, ty) — chemin mono. Chaque
   glyphe porte sa taille : une case fusionnée 16×16 couvre 2×2 tuiles là où une
   case 8×8 en couvre une. */
static void text_put_tiles(int gi, int tx, int ty) {
    /* `slot` est relatif au bloc du texte : le tilemap, lui, veut un index
       ABSOLU dans le charblock — d'où la base. */
    int slot = g_text_tile_base + g_font->slot[gi];
    int txs  = g_font->gw[gi];
    int tys  = g_font->gh[gi];
    for (int r = 0; r < tys; r++)
        for (int c = 0; c < txs; c++) {
            int t = slot + r * txs + c;
            tilemap_set(g_text_layer, tx + c, ty + r, t);
            tilemap_set_palette(g_text_layer, tx + c, ty + r, FONT_PAL_BANK);
        }
}

/* ── Géométrie commune aux deux chemins ──────────────────────────── */
/* Tout se calcule en PIXELS, y compris en mono : là, les chasses valent
   gw*8 et l'interligne tiles_y*8, donc les positions retombent d'elles-mêmes
   sur des multiples de 8. Une seule mise en page pour les deux rendus — la
   coupe au mot et le filet de sécurité n'existent qu'en un exemplaire. */

static int text_adv_px(int gi) {
    return (gi < 0) ? g_font->cell_w : g_font->adv[gi];
}

static int text_line_px(void) { return g_font->line_h; }

/* Largeur en PIXELS du mot commençant en `i` (jusqu'à l'espace ou la fin) —
   mesurée en avançant glyphe par glyphe, puisque les chasses varient. */
static int text_word_width(const unsigned short* s, int i, int len) {
    int w = 0;
    while (i < len && s[i] != ' ' && s[i] != '\n') {
        int used, gi = text_find(s, i, len, &used);
        w += text_adv_px(gi);
        i += used;
    }
    return w;
}

/* Mise en page ET rendu, en un seul parcours.

   `measure` = 1 ne dessine rien et renvoie l'étendue occupée en TUILES : c'est
   ce que le chemin proportionnel doit connaître avant de composer, pour savoir
   quelles tuiles de surface préparer. Un seul algorithme sert les deux passes —
   mesurer avec un code différent de celui qui dessine, c'est se garantir un
   décalage entre la zone préparée et la zone écrite.

   `wrap` est en TUILES (contrat de l'API Lua, inchangé), converti ici en pixels.

   n < 0 = tout le texte ; sinon les n premiers caractères (machine à écrire).
   Le rythme appartient au script, pas au moteur : aucun réglage de vitesse
   ici, l'appelant fait varier n comme il veut. */
/* Où finit la ligne qui commence en `i`, et combien elle mesure.

   C'est le SEUL endroit qui décide d'une coupe. L'alignement a besoin de la
   largeur d'une ligne AVANT de la tracer ; la mesurer avec un second code
   aurait garanti qu'un jour les deux ne coupent plus au même endroit — le
   travers contre lequel `measure` existait déjà.

   *end  = premier codepoint qui n'est plus sur cette ligne (borne du tracé) ;
   *next = où reprendre (l'espace de coupe et le '\n' sont AVALÉS, pas tracés) ;
   *w    = largeur en pixels de la ligne. */
static void text_scan_line(const unsigned short* s, int i, int len, int wrap_px,
                           int* end, int* next, int* w) {
    int x = 0;
    while (i < len) {
        int cp = s[i];
        if (cp == '\n') { *end = i; *next = i + 1; *w = x; return; }
        if (wrap_px > 0 && cp == ' ') {
            /* Coupe au MOT : on mesure le mot qui suit l'espace ; s'il ne tient
               pas sur la ligne, on passe à la suivante et l'espace disparaît
               (pas d'espace parasite en début de ligne). */
            int used_sp, gsp = text_find(s, i, len, &used_sp);
            int wlen = text_word_width(s, i + used_sp, len);
            if (x + text_adv_px(gsp) + wlen > wrap_px) {
                *end = i; *next = i + used_sp; *w = x; return;
            }
        }
        int used, gi = text_find(s, i, len, &used);
        int a = text_adv_px(gi);
        /* Filet : un mot plus long que la boîte est coupé au glyphe. La garde
           `x > 0` est ce qui empêche une boîte plus étroite qu'un seul glyphe
           de ne jamais avancer — ce glyphe déborde, c'est le moindre mal. */
        if (wrap_px > 0 && x > 0 && x + a > wrap_px) { *end = i; *next = i; *w = x; return; }
        x += a;
        i += used;
    }
    *end = i; *next = i; *w = x;
}

/* Décalage d'une ligne dans sa boîte. Sans largeur de boîte, aligner ne veut
   rien dire : `wrap_px == 0` retombe donc à gauche quel que soit le réglage.
   Jamais négatif — une ligne plus large que sa boîte ne doit pas sortir à
   GAUCHE de son origine, où rien n'a été préparé ni effacé. */
static int text_align_off(int align, int wrap_px, int line_w) {
    if (wrap_px <= 0 || line_w >= wrap_px) return 0;
    int off = 0;
    if (align == TEXT_ALIGN_CENTER) off = (wrap_px - line_w) / 2;
    else if (align == TEXT_ALIGN_RIGHT) off = wrap_px - line_w;
    /* Chemin TILEMAP : un glyphe se pose à la tuile, pas au pixel. Un offset de
       76 px y deviendrait 72 en silence — et deux glyphes voisins pourraient
       viser la même case. On cale donc sur la grille, ce qui centre à la tuile
       près : sans effet visible pour une police mono, qui vit déjà sur cette
       grille. Les chemins composés (proportionnel, bande de sprites) gardent
       le pixel. */
    if (!g_font->composited && !g_blit_h) off &= ~7;
    return off;
}

static void text_layout(const unsigned short *s, int slen, int tx, int ty,
                        int wrap, int n, int measure, int align,
                        int *out_w, int *out_h) {
    /* `n` borne ce qu'on DESSINE, pas ce qu'on met en page.

       Tronquer la chaîne avant de la couper (ce que faisait la version
       précédente) fait re-composer le texte à chaque frame de la machine à
       écrire : un mot encore incomplet mesure moins large, tient donc sur la
       ligne courante, puis saute à la suivante en s'achevant. Sur un texte
       ferré ou centré, ce n'est plus un mot qui bouge mais la ligne entière.
       La mise en page se fait donc sur le texte FINAL, et la révélation n'est
       qu'un masque — ce qui rend aussi la surface préparée stable. */
    int len = slen;

    int line   = text_line_px();
    int wrap_px = wrap > 0 ? wrap * 8 : 0;
    int ox = tx * 8, oy = ty * 8;         /* origine ÉCRAN en pixels */
    int y = oy;
    int max_x = ox, i = 0;

    while (i < len) {
        int end, next, lw;
        text_scan_line(s, i, len, wrap_px, &end, &next, &lw);
        int x = ox + text_align_off(align, wrap_px, lw);
        while (i < end) {
            /* Correspondance au plus long : une ligature avale plusieurs
               codepoints d'un coup. */
            int used, gi = text_find(s, i, len, &used);
            if (!measure && gi >= 0 && (n < 0 || i < n)) {
                /* `[color]` ne vaut que sur un chemin COMPOSÉ : le chemin
                   tilemap pose une tuile déjà encrée, partagée par toutes ses
                   occurrences. Le build le signale plutôt que de laisser la
                   couleur disparaître en silence. */
                g_ink = text_color_at(i);
                int fx = g_cap_max ? text_fx_at(i) : 0;
                if (fx && g_cap_n < g_cap_max) {
                    /* Réservé au chemin par glyphe : noté, pas dessiné —
                       le dessiner aussi le ferait apparaître deux fois. */
                    g_cap_x[g_cap_n]  = (short)x;
                    g_cap_y[g_cap_n]  = (short)y;
                    g_cap_gi[g_cap_n] = (short)gi;
                    g_cap_fx[g_cap_n] = (short)fx;
                    g_cap_i[g_cap_n]  = (short)i;
                    g_cap_ink[g_cap_n] = (short)g_ink;
                    g_cap_n++;
                } else if (g_font->composited || g_blit_h) {
                    /* `g_blit_h` non nul = bloc PRIVÉ (bande de sprites). On y
                       compose toujours, même avec une police mono : poser des
                       tuiles irait écrire dans la tilemap du layer d'UI, qui
                       n'a rien à voir avec le sprite qu'on est en train de
                       remplir. Les glyphes se lisent en ROM dans les deux
                       modes, il n'y a donc rien de plus à charger. */
                    text_put_px(gi, x, y);
                } else text_put_tiles(gi, x >> 3, y >> 3);
                g_ink = 0;
            }
            x += text_adv_px(gi);
            i += used;
        }
        if (x > max_x) max_x = x;
        i = next;
        y += line;
    }
    y -= line;                 /* la dernière ligne tracée, pas la suivante */
    if (y < oy) y = oy;        /* texte vide : une ligne quand même */
    if (out_w) {
        /* Étendue en tuiles, bornes ARRONDIES : un glyphe posé à x=13 mord sur
           la tuile 1, elle doit être préparée. */
        int w = (max_x - ox + 7) / 8;
        *out_w = w > 0 ? w : 1;
    }
    if (out_h) {
        int h = (y + line - oy + 7) / 8;
        *out_h = h > 0 ? h : 1;
    }
}

/* Rend une SUITE DE CODEPOINTS. Les entrées de la table de textes n'en sont
   qu'une source parmi d'autres : une valeur interpolée fabrique la sienne en RAM et
   passe par le même chemin, donc par les mêmes chasses, la même surface et le
   même effacement. Dupliquer un mini-rendu pour les nombres aurait garanti
   qu'un jour l'un des deux dérive. */
static void text_render_cp_al(const unsigned short *s, int slen,
                              int tx, int ty, int wrap, int n, int align) {
    if (g_text_layer < 0 || !g_font) return;
    blit_use_bg_surface();
    if (g_font->composited) {
        /* Préparer AVANT de composer : la composition ne pose que de l'encre,
           elle n'efface pas ce qui était là. La zone préparée doit couvrir le
           texte ALIGNÉ, d'où le même `align` dans les deux passes. */
        int w = 1, h = 1;
        text_layout(s, slen, tx, ty, wrap, n, 1, align, &w, &h);
        text_surf_prepare(tx, ty, w, h);
    }
    text_layout(s, slen, tx, ty, wrap, n, 0, align, 0, 0);
}

static void text_render_cp(const unsigned short *s, int slen,
                           int tx, int ty, int wrap, int n) {
    text_render_cp_al(s, slen, tx, ty, wrap, n, TEXT_ALIGN_LEFT);
}

static void text_render(int id, int tx, int ty, int wrap, int n) {
    const unsigned short *s; const TextEvent *e; int ne;
    int len = text_materialize(id, &s, &e, &ne);
    /* `draw` ignore le tempo (une tête de lecture doit s'accrocher à quelque
       chose de NOMMÉ, et un couple (x, y) ne l'est pas) mais pas les valeurs :
       celles-ci marchent partout. */
    text_render_cp(s, len, tx, ty, wrap, n);
}

void text_draw     (int tx, int ty, int id)                 { text_render(id, tx, ty, 0, -1); }

/* ── Rendu dans une zone authorée ─────────────────────────────────
   Remplace `text_draw_box` : la géométrie ne vient plus des arguments mais de
   `g_ui_regions`, donc de ce que l'auteur a dessiné dans le canvas.

   La zone peut imposer sa police. Le faire à chaque appel serait ruineux en
   chemin mono (recopie des glyphes en VRAM) si `text_set_font` n'était pas
   idempotent — il l'est, cf. sa garde. */
static void text_render_obj(const unsigned short *s, int slen,
                            const UIRegionInfo *R, int n);

/* Prend une SUITE DE CODEPOINTS et non un id de table, pour la même raison que
   `text_render_cp` côté libre : la table n'est qu'une source parmi d'autres
   (une valeur interpolée fabrique la sienne en RAM). Un second chemin de rendu
   pour les nombres finirait par dériver de celui-ci — mêmes chasses, même
   alignement, même effacement, ou rien. */
static void text_render_region_cp(const unsigned short *s, int slen,
                                  int r, int n) {
    const UIRegionInfo *R = &g_ui_regions[r];
    if (R->font != 255) text_set_font(R->font);
    if (!g_font) return;
    if (R->target == 1) { text_render_obj(s, slen, R, n); return; }
    if (g_text_layer < 0) return;
    text_render_cp_al(s, slen, R->x >> 3, R->y >> 3, R->w >> 3, n, R->align);
}

static void text_render_region(int id, int r, int n) {
    const unsigned short *s; const TextEvent *e; int ne;
    int len = text_materialize(id, &s, &e, &ne);
    /* La piste accompagne le texte le temps du rendu : c'est elle qui dit
       quels glyphes sont animés. */
    g_ev = e; g_nev = ne;
    text_render_region_cp(s, len, r, n);
    g_ev = 0; g_nev = 0;
}

/* ── Tête de lecture ──────────────────────────────────────────────
   Un texte qui porte du TEMPO (`[speed=n]`, `[pause=n]`) ne s'affiche pas d'un
   coup : il se lit. La tête vit par ZONE et non par appel — c'est la raison
   pour laquelle le tempo est ignoré par `text_draw` : une tête doit s'accrocher
   à quelque chose de nommé, et un couple (x, y) ne l'est pas.

   Un texte SANS marqueur de tempo s'affiche entier, immédiatement. Le tempo
   s'écrit dans le texte, par l'auteur : ne pas en mettre est une décision, pas
   un oubli à compenser par une vitesse par défaut.

   Le plafond est fixe : le moteur ne connaît pas la taille de `g_ui_regions`,
   qui est générée. Une zone au-delà s'affiche d'un coup — dégradation visible
   et inoffensive, plutôt qu'un tableau dimensionné au hasard. */
#define TEXT_READ_MAX 8

typedef struct TextRead {
    short id;        /* texte en cours, -1 = aucune lecture */
    short n;         /* caractères révélés */
    short len;       /* longueur matérialisée, borne de la lecture */
    short wait;      /* frames restantes avant le prochain caractère */
    short speed;     /* frames par caractère, posé par [speed=n] */
    unsigned char active;
} TextRead;

static TextRead g_reads[TEXT_READ_MAX];
static int      g_reads_init = 0;

/* Le texte porte-t-il du tempo ? C'est ce qui décide entre lire et afficher. */
static int text_has_tempo(const TextEvent *e, int ne) {
    for (int k = 0; k < ne; k++)
        if (e[k].kind == TEXT_EV_SPEED || e[k].kind == TEXT_EV_PAUSE) return 1;
    return 0;
}

/* Applique les marqueurs de tempo posés EXACTEMENT au caractère `i`.
   Renvoie l'attente à observer avant de révéler le suivant. */
static int text_tempo_at(const TextEvent *e, int ne, int i, short *speed) {
    int wait = -1;
    for (int k = 0; k < ne; k++) {
        if (e[k].at != i) continue;
        if (e[k].kind == TEXT_EV_SPEED) *speed = e[k].value;
        else if (e[k].kind == TEXT_EV_PAUSE) wait = e[k].value;
    }
    /* Une pause s'AJOUTE à la cadence courante : « attends, puis reprends au
       même rythme ». La remplacer ferait d'un [pause=0] un accélérateur. */
    return wait < 0 ? *speed : wait + *speed;
}

static void text_read_reset(int r) {
    if (!g_reads_init) {
        for (int k = 0; k < TEXT_READ_MAX; k++) g_reads[k].id = -1;
        g_reads_init = 1;
    }
    if (r >= 0 && r < TEXT_READ_MAX) { g_reads[r].id = -1; g_reads[r].active = 0; }
}

void text_draw_in(int r, int id) {
    const unsigned short *s; const TextEvent *e; int ne;
    int len = text_materialize(id, &s, &e, &ne);
    /* Une lecture DÉJÀ en cours sur le même texte n'est pas relancée : un
       script appelle `draw_in` depuis `on_update`, donc à chaque frame. La
       relancer remettrait la tête à zéro soixante fois par seconde et le texte
       n'avancerait jamais — c'est la façon la plus naturelle de s'en servir,
       elle doit être la bonne. Pour recommencer, on vide la zone
       (`text.clear_in`) ou on y écrit autre chose. */
    if (r >= 0 && r < TEXT_READ_MAX && g_reads[r].active && g_reads[r].id == id)
        return;
    text_read_reset(r);
    if (r >= TEXT_READ_MAX || !text_has_tempo(e, ne)) {
        text_render_region(id, r, -1);
        return;
    }
    /* Lecture : la zone part vide et se remplit. La mise en page, elle, se fait
       sur le texte ENTIER (cf. text_layout) — révéler n'est qu'un masque, donc
       aucune ligne ne saute pendant que le texte s'écrit. */
    TextRead *R = &g_reads[r];
    R->id = (short)id; R->n = 0; R->len = (short)len;
    R->speed = 1; R->active = 1;
    R->wait  = (short)text_tempo_at(e, ne, 0, &R->speed);
    text_render_region(id, r, 0);
}

/* Lecture en cours dans cette zone ? Ce que le script attend pour enchaîner. */
int text_reading(int r) {
    return (r >= 0 && r < TEXT_READ_MAX && g_reads[r].active) ? 1 : 0;
}

/* Tout révéler d'un coup — le bouton « passer » de tous les jeux. */
void text_skip(int r) {
    if (r < 0 || r >= TEXT_READ_MAX || !g_reads[r].active) return;
    g_reads[r].active = 0;
    text_render_region(g_reads[r].id, r, -1);
}

/* Avance les têtes de lecture et rejoue les zones animées. Appelée une fois par
   frame par le code généré, avant `oam_update`.

   Une zone ANIMÉE est redessinée même quand sa lecture est finie : c'est
   l'effet qui bouge, pas le texte. Une zone sans effet ni lecture n'est jamais
   retouchée — le coût est proportionnel à ce qui remue à l'écran. */
void text_update(void) {
    g_text_frame++;
    if (!g_reads_init) return;
    for (int r = 0; r < TEXT_READ_MAX; r++) {
        TextRead *R = &g_reads[r];
        if (R->id < 0) continue;
        const unsigned short *s; const TextEvent *e; int ne;
        text_materialize(R->id, &s, &e, &ne);
        if (R->active) {
            if (R->wait > 0) R->wait--;
            /* `while` et non `if` : [speed=0] révèle tout d'un trait, ce qui
               est exactement ce qu'un auteur écrit pour couper le tempo au
               milieu d'un texte. */
            while (R->active && R->wait <= 0) {
                R->n++;
                if (R->n >= R->len) { R->n = R->len; R->active = 0; break; }
                R->wait = (short)text_tempo_at(e, ne, R->n, &R->speed);
            }
            text_render_region(R->id, r, R->active ? R->n : -1);
        } else if (g_ui_regions[r].anim > 0) {
            text_render_region(R->id, r, -1);
        }
    }
}

/* ── Bande de sprites ─────────────────────────────────────────────
   Une zone en cible OBJ est couverte par des sprites 64×8 (ou moins pour la
   dernière colonne) posés sur son rectangle, et le texte s'y compose par le
   MÊME chemin que sur la surface BG — seul le bloc de destination change.

   Pourquoi des blocs de 8 px de haut et pas un sprite par ligne de texte :
   l'interligne vient de la police, qui peut être changée par un script. Une
   allocation qui en dépendrait ne serait pas calculable au build. */

/* Position d'un acteur, fournie par le code généré. `gba_engine.h` ignore la
   structure `Actor` — elle vit dans actor_api_static.h, qui inclut celui-ci et
   non l'inverse. Un pointeur de fonction évite d'inverser cette dépendance
   pour deux entiers. */
static int (*g_actor_x_fn)(int) = 0;
static int (*g_actor_y_fn)(int) = 0;

void text_obj_set_actor_fn(int (*fx)(int), int (*fy)(int)) {
    g_actor_x_fn = fx;
    g_actor_y_fn = fy;
}

static int g_obj_oam_base  = -1;   /* 1er slot OAM réservé au texte */
static int g_obj_tile_base = 0;    /* 1re tuile OBJ réservée au texte */

/* Posés par scene_init depuis l'allocation du codegen. -1 = aucune place
   réservée : les zones OBJ ne s'affichent alors pas, plutôt que d'aller écrire
   dans les sprites des acteurs. */
void text_obj_set_base(int oam, int tile) {
    g_obj_oam_base  = oam;
    g_obj_tile_base = tile;
}

/* Largeur du n-ième sprite de la bande couvrant `w` px, et son décalage x.
   Reproduit `strip_columns()` de core/models/ui_region.py — l'émetteur et le
   moteur doivent découper pareil, sinon les tuiles allouées ne sont pas celles
   que le sprite lit. */
static int text_strip_col(int w, int i, int *out_x) {
    int x = 0, left = w < 8 ? 8 : w;
    for (int k = 0; ; k++) {
        int cw = left >= 32 ? 32 : left >= 16 ? 16 : 8;
        if (k == i) { if (out_x) *out_x = x; return cw; }
        x += cw; left -= cw;
        if (left <= 0) { if (out_x) *out_x = x; return 0; }
    }
}

/* Forme (attr0 bits 14-15) et taille (attr1 bits 14-15) d'une colonne `cw`×8.
   Le matériel n'offre, en forme « large », que 16×8, 32×8, 32×16 et 64×32 :
   **un 64×8 n'existe pas**, d'où le plafond à 32 px de `text_strip_col`. */
static int text_strip_size(int cw) { return cw == 32 ? 1 : 0; }   /* 8x8|16x8:0, 32x8:1 */
static int text_strip_shape(int cw) { return cw == 8 ? 0 : 1; }   /* 8x8 = carré */

static void text_render_obj(const unsigned short *s, int slen,
                            const UIRegionInfo *R, int n) {
    if (g_obj_oam_base < 0 || !g_font) return;

    /* Origine ÉCRAN. Une zone ancrée sur un acteur ajoute sa position — c'est
       ce que l'ancrage promet, et ce que la grille BG ne savait pas faire. */
    int ox = R->x, oy = R->y;
    if (R->anchor == 2 && R->actor >= 0 && g_actor_x_fn) {
        ox += g_actor_x_fn(R->actor);
        oy += g_actor_y_fn(R->actor);
    }

    int rows = R->rows, tiles_row = R->tiles_row;
    int tile0 = g_obj_tile_base + R->tile_rel;

    /* Le bloc est PRIVÉ : pas de modulo, et l'origine est celle de la zone.
       Composer en coordonnées écran laisserait `text_layout` calculer comme
       pour le BG, sans rien savoir de la bande. */
    g_blit_mem   = (volatile u32*)OBJ_VRAM;
    g_blit_tile0 = tile0;
    g_blit_w     = tiles_row;
    g_blit_h     = rows;
    g_blit_ox    = ox >> 3;
    g_blit_oy    = oy >> 3;

    /* Vider la bande : la composition ne pose que de l'encre. */
    for (int t = 0; t < tiles_row * rows; t++) {
        volatile u32 *p = (volatile u32*)OBJ_VRAM + (tile0 + t) * 8;
        for (int k = 0; k < 8; k++) p[k] = 0;
    }

    /* Les glyphes réservés sont CAPTURÉS (donc absents de la bande) plutôt que
       dessinés : ils reçoivent leur propre sprite juste après. Écrêtage naturel
       — au-delà du budget, la capture s'arrête et les glyphes suivants
       retombent dans la bande, en statique. */
    g_cap_max = R->anim > TEXT_ANIM_MAX ? TEXT_ANIM_MAX : R->anim;
    g_cap_n   = 0;
    text_layout(s, slen, ox >> 3, oy >> 3,
                R->w >> 3, n, 0, R->align, 0, 0);
    int captured = g_cap_n;
    g_cap_max = 0;

    /* Poser les sprites de la bande. */
    int slot = g_obj_oam_base + R->oam_rel;
    int strip_slots = 0;
    for (int r = 0; r < rows; r++) {
        int cx = 0, tcol = 0;
        for (int i = 0; ; i++) {
            int cw = text_strip_col(R->w, i, &cx);
            if (!cw) break;
            int sx = (ox + cx) & 0x1FF;
            int sy = (oy + r * 8) & 0xFF;
            shadow_oam[slot].attr0 = sy | (0 << 10) | (text_strip_shape(cw) << 14);
            shadow_oam[slot].attr1 = sx | (text_strip_size(cw) << 14);
            shadow_oam[slot].attr2 = ((tile0 + r * tiles_row + tcol) & 0x3FF)
                                   | (R->priority << 10) | (R->pal_bank << 12);
            slot++; strip_slots++;
            tcol += cw >> 3;
        }
    }

    /* ── Glyphes animés ───────────────────────────────────────────
       Chacun dans un OBJ 16×16 qui lui est propre : un glyphe 8×8 posé hors
       grille (chasse proportionnelle) chevauche jusqu'à 2×2 tuiles. Le sprite
       est ancré à la tuile et le glyphe composé au reste de la division —
       le placement reste donc exact au pixel.

       Avec un décalage nul, le rendu est indiscernable de celui de la bande :
       c'est ce qui permettra de vérifier l'effet quand il arrivera, et ce qui
       rend ce chemin sûr en attendant. */
    /* `text_layout` prend son origine en TUILES : l'espace de mise en page
       commence donc à `ox & ~7`, pas à `ox`. La bande compense ce décalage
       sans le savoir (son sprite est posé à `ox + cx` alors qu'il montre la
       tuile contenant le pixel `(ox & ~7) + cx` — les deux erreurs s'annulent).
       Le chemin par glyphe doit le faire EXPLICITEMENT, sinon son sprite est
       posé jusqu'à 7 px à côté, et l'écart change à chaque fois que la zone
       traverse une frontière de tuile — ce qui se voit comme un retard sur un
       ancrage qui bouge. */
    int sub_x = ox & 7, sub_y = oy & 7;
    int atile = tile0 + R->tiles_row * rows;
    for (int k = 0; k < captured; k++) {
        int gx = g_cap_x[k], gy = g_cap_y[k];
        /* Origine ÉCRAN de la tuile qui porte le glyphe. */
        int bx = (gx & ~7) + sub_x, by = (gy & ~7) + sub_y;
        /* L'effet déplace le SPRITE, jamais la composition : les 2×2 tuiles
           sont écrites une fois pour toutes et seuls deux mots d'OAM bougent
           d'une frame à l'autre. Recomposer aurait coûté le prix d'un rendu
           complet à chaque frame, pour un déplacement de deux pixels. */
        text_fx_offset(g_cap_fx[k], g_cap_i[k], &bx, &by);
        int t  = atile + k * 4;              /* 4 tuiles = un OBJ 16×16 */

        for (int q = 0; q < 4; q++) {
            volatile u32 *pz = (volatile u32*)OBJ_VRAM + (t + q) * 8;
            for (int w = 0; w < 8; w++) pz[w] = 0;
        }
        /* Bloc privé de 2×2 tuiles, dont l'origine écran est (bx, by). */
        g_blit_tile0 = t;
        g_blit_w = 2; g_blit_h = 2;
        g_blit_ox = bx >> 3; g_blit_oy = by >> 3;
        /* Composé APRÈS la bande, donc hors du parcours de mise en page :
           l'encre doit être reposée depuis la capture, sinon un glyphe animé
           dans une portée colorée sortirait à l'encre d'origine. */
        g_ink = g_cap_ink[k];
        text_put_px(g_cap_gi[k], gx, gy);
        g_ink = 0;

        shadow_oam[slot].attr0 = (by & 0xFF) | (0 << 14);      /* carré */
        shadow_oam[slot].attr1 = (bx & 0x1FF) | (1 << 14);     /* taille 1 = 16×16 */
        shadow_oam[slot].attr2 = (t & 0x3FF)
                               | (R->priority << 10) | (R->pal_bank << 12);
        slot++;
    }

    /* Masquer la réserve non utilisée : un texte plus court que le budget
       laisserait sinon les glyphes de l'appel précédent à l'écran. */
    for (int k = captured; k < R->anim; k++)
        shadow_oam[slot++].attr0 = 0x0200;
    (void)strip_slots;
}

/* Vide une zone, quelle que soit sa cible — le pendant exact de `text_draw_in`.

   La cible ne doit PAS remonter jusqu'à l'auteur : il a dessiné une zone, il
   l'efface. Que ce soit une bande de sprites à masquer ou des tuiles de BG à
   remettre à zéro est une conséquence de l'ancrage qu'il a choisi, et lui faire
   choisir la primitive selon la cible reviendrait à lui demander de refaire ce
   calcul à chaque fois qu'il déplace une zone. */
void text_clear_in(int r) {
    /* Vider, c'est aussi annuler la lecture : sans ça `text_update` la
       redessinerait à la frame suivante, et la zone se remplirait toute
       seule après avoir été effacée. */
    text_read_reset(r);
    const UIRegionInfo *R = &g_ui_regions[r];

    /* La zone peut imposer sa police, et l'effacement en DÉPEND : une police
       composée range ses pixels dans les tuiles de surface, une police mono
       pose des index dans le tilemap. Effacer avec la police d'à côté vide donc
       le mauvais des deux et laisse l'encre en place. Même garde que
       `text_render_region_cp`, et pour la même raison. */
    if (R->font != 255) text_set_font(R->font);

    if (R->target == 1) {
        if (g_obj_oam_base < 0) return;
        int slot = g_obj_oam_base + R->oam_rel;
        for (int k = 0; k < R->oam_count; k++)
            shadow_oam[slot + k].attr0 = 0x0200;   /* bit 9 = objet désactivé */
        /* oam_count couvre la bande ET la réserve animée : cacher la zone doit
           tout cacher, sinon un glyphe animé resterait seul à l'écran. */
        return;
    }

    /* Cible BG : le rectangle de la zone en tuiles. L'émetteur aligne déjà une
       zone BG sur la grille, donc le décalage est exact ; le plancher à 1 tuile
       couvre une zone plus étroite qu'un glyphe, qui déborde à l'affichage
       (cf. text_scan_line) et doit donc s'effacer sur au moins une case. */
    int w = R->w >> 3, h = R->h >> 3;
    text_clear(R->x >> 3, R->y >> 3, w > 0 ? w : 1, h > 0 ? h : 1);
}

/* ── Chiffres ─────────────────────────────────────────────────────
   Ce qui reste du rendu des nombres, maintenant que `text_draw_num` a disparu :
   une entrée de table porte sa propre valeur (« Score : $score »), et c'est
   `text_materialize` qui appelle ceci pour en fabriquer les chiffres.

   Un chiffre absent de la police laisse le trou d'une cellule, comme partout
   ailleurs (text_layout) : mieux qu'un nombre silencieusement faux. */

/* Entier → codepoints dans `buf` (au moins TEXT_NUM_MAX), longueur retournée. */
static int text_num_cp(int value, unsigned short *buf) {
    int n = 0;
    unsigned int mag = (value < 0) ? (unsigned int)(-(long)value) : (unsigned int)value;
    /* Chiffres produits à l'envers, puis retournés : pas de division par
       puissance de 10 à deviner, et 0 sort bien comme "0". */
    do { buf[n++] = (unsigned short)('0' + mag % 10u); mag /= 10u; } while (mag && n < 11);
    if (value < 0) buf[n++] = '-';
    for (int i = 0, j = n - 1; i < j; i++, j--) {
        unsigned short t = buf[i]; buf[i] = buf[j]; buf[j] = t;
    }
    return n;
}

/* ── Blending ────────────────────────────────────────────────────── */
/* BLDCNT : bits 0-5 = cibles du dessus (BG0-3, OBJ, backdrop),
            bits 6-7 = mode, bits 8-13 = cibles du dessous.
   BLDALPHA : bits 0-4 = eva (dessus), bits 8-12 = evb (dessous), 0-16.
   BLDY : bits 0-4 = evy, 0-16. Write-only, d'où la shadow des deux autres
   seulement — evy n'a pas de lecteur. */

static u16 g_bldcnt_sh, g_bldalpha_sh;

static void blend_reset(void) {
    g_bldcnt_sh   = 0;
    g_bldalpha_sh = 0;
    REG_BLDCNT    = 0;
    REG_BLDALPHA  = 0;
    REG_BLDY      = 0;
}

static void bld_target_set(int side, int bit, int on) {
    u16 m = (u16)(1 << (bit + ((side & 1) ? 8 : 0)));
    if (on) g_bldcnt_sh |=  m;
    else    g_bldcnt_sh &= (u16)~m;
    REG_BLDCNT = g_bldcnt_sh;
}

void blend_set_mode(int mode) {
    g_bldcnt_sh = (u16)((g_bldcnt_sh & ~0x00C0) | ((mode & 3) << 6));
    REG_BLDCNT  = g_bldcnt_sh;
}

int blend_get_mode(void) { return (g_bldcnt_sh >> 6) & 3; }

void blend_set_layer   (int side, int bg, int on) { bld_target_set(side, bg & 3, on); }
void blend_set_obj     (int side, int on)         { bld_target_set(side, 4, on); }
void blend_set_backdrop(int side, int on)         { bld_target_set(side, 5, on); }

/* eva/evb sont des seizièmes : 16 = pleine intensité. Au-delà, le matériel
   sature — on clampe pour que le comportement soit le même partout. */
static int ev_clamp(int v) { return v < 0 ? 0 : (v > 16 ? 16 : v); }

void blend_set_alpha(int eva, int evb) {
    g_bldalpha_sh = (u16)(ev_clamp(eva) | (ev_clamp(evb) << 8));
    REG_BLDALPHA  = g_bldalpha_sh;
}

void blend_set_fade(int evy) {
    REG_BLDY = (u16)ev_clamp(evy);
}

#endif /* GBA_ENGINE_IMPL */

/* ── Ancien système texte HUD (libtonc TTE) — RETIRÉ ─────────────
   `draw_printf` / `draw_clear` (Lua `display.print` / `display.clear`) sont
   partis avec libtonc. Deux raisons, la seconde étant la vraie :

   • TTE chargeait sa police à partir de la tuile 1 du charblock du layer d'UI,
     exactement où `text_set_font` pose la nôtre — les deux s'écrasaient, donc
     `display.print` rendait des glyphes corrompus dès qu'un projet avait une
     police. Deux systèmes de texte sur le même charblock, sans allocation.

   • Sa chaîne de format vivait dans le SCRIPT (`display.print(1,1,"P1: %d",s)`),
     donc hors de la table de textes : intraduisible. C'est précisément le trou
     que la table existe pour fermer (cf. models/text.py). Le garder, c'était
     maintenir une API qui contredit la règle de l'autre.

   Remplacements : `text.draw` pour un libellé (il vit dans la table, donc il se
   traduit) et `text.draw_num` pour une valeur (un nombre ne se traduit pas). */

/* ── Clear toutes les BG screenblocks ───────────────────────────── */
static void bg_maps_clear(void) {
    for (int sbb = 0; sbb < 32; sbb++) {
        vu16 *m = MAP_RAM(sbb);
        for (int j = 0; j < 1024; j++) m[j] = 0;
    }
}


static void oam_update(void) {
    CpuFastSet(shadow_oam, (void*)OAM, COPY32|(128*sizeof(OBJATTR)/4));
}

static void oam_hide_all(void) {
    for (int i = 0; i < 128; i++) {
        shadow_oam[i].attr0 = 0x0200;
        shadow_oam[i].attr1 = 0;
        shadow_oam[i].attr2 = 0;
    }
}

#endif /* GBA_ENGINE_H */
