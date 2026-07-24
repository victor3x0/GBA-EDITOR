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
#include "tonc_tte.h"

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

/* ── Texte ───────────────────────────────────────────────────────── */
/* Un glyphe = une (ou plusieurs) tuile(s) : écrire du texte, c'est poser des
   index de tuiles. Le texte vit donc sur LE layer d'UI de la scène
   (`Scene.text_bg`) et nulle part ailleurs — les glyphes sont chargés dans le
   charblock de ce layer, et un charblock appartient à un layer. D'où l'absence
   de paramètre `layer` : il serait mensonger.

   Un texte est stocké en codepoints Unicode, pas en glyphes : la
   correspondance se fait à l'affichage via la police courante, ce qui rend un
   texte indépendant de la police (nécessaire en v0.8 pour les traductions). */

typedef struct FontInfo {
    const unsigned int*   tiles;    /* glyphes, 8 mots par tuile */
    int                   n_tiles;
    const unsigned short* pal;      /* 16 couleurs BGR555 */
    const unsigned short* cp;       /* codepoints TRIÉS */
    const unsigned short* slot;     /* index de 1ère tuile, parallèle à cp */
    int                   n_glyphs;
    int                   tiles_x;  /* cellule du glyphe, en tuiles */
    int                   tiles_y;
} FontInfo;

extern const FontInfo g_fonts[];
extern const unsigned short* const g_texts[];
extern const unsigned short g_text_len[];

void text_set_layer(int bg);        /* posé par scene_init depuis Scene.text_bg */
void text_set_font (int f);         /* charge glyphes + palette en VRAM */
int  text_length   (int id);
void text_clear    (int tx, int ty, int w, int h);
void text_draw     (int id, int tx, int ty);
void text_draw_upto(int id, int tx, int ty, int n);   /* machine à écrire */
void text_draw_box (int id, int tx, int ty, int w, int n);

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
#define FONT_TILE_BASE  1

static int g_text_layer = -1;
static const FontInfo *g_font = 0;

void text_set_layer(int bg) { g_text_layer = (bg >= 0 && bg <= 3) ? bg : -1; }

/* Charge les glyphes dans le charblock du layer d'UI et la palette dans sa
   banque réservée. Une seule police résidente à la fois : rappeler cette
   fonction remplace la précédente (coût d'une copie VRAM, pas par frame). */
void text_set_font(int f) {
    const FontInfo *fi = &g_fonts[f];
    g_font = fi;
    if (g_text_layer < 0 || !fi->tiles) return;
    copy16(TILE_RAM(g_text_layer) + FONT_TILE_BASE * 16, fi->tiles, fi->n_tiles * 32);
    copy16(PAL_BG_RAM + FONT_PAL_BANK * 16, fi->pal, 32);
}

/* Codepoint → 1ère tuile du glyphe. Dichotomie : la table est triée à
   l'émission. -1 si le caractère n'existe pas dans la police. */
static int text_slot(int cp) {
    if (!g_font || g_font->n_glyphs <= 0) return -1;
    int lo = 0, hi = g_font->n_glyphs - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        int v = g_font->cp[mid];
        if (v == cp) return g_font->slot[mid];
        if (v < cp) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

int text_length(int id) { return g_text_len[id]; }

void text_clear(int tx, int ty, int w, int h) {
    if (g_text_layer < 0) return;
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++)
            tilemap_set(g_text_layer, tx + c, ty + r, 0);
}

/* Pose un glyphe et retourne sa largeur en tuiles (l'avance reste fixe en
   v1 : une cellule). Un caractère absent de la police laisse un trou plutôt
   que de décaler tout le reste de la ligne. */
static int text_put(int cp, int tx, int ty) {
    int slot = text_slot(cp);
    int txs = g_font ? g_font->tiles_x : 1;
    int tys = g_font ? g_font->tiles_y : 1;
    if (slot >= 0) {
        for (int r = 0; r < tys; r++)
            for (int c = 0; c < txs; c++) {
                int t = slot + r * txs + c;
                tilemap_set(g_text_layer, tx + c, ty + r, t);
                tilemap_set_palette(g_text_layer, tx + c, ty + r, FONT_PAL_BANK);
            }
    }
    return txs;
}

/* n < 0 = tout le texte ; sinon les n premiers caractères (machine à écrire).
   Le rythme appartient au script, pas au moteur : aucun réglage de vitesse
   ici, l'appelant fait varier n comme il veut. */
static void text_render(int id, int tx, int ty, int wrap, int n) {
    if (g_text_layer < 0 || !g_font) return;
    const unsigned short *s = g_texts[id];
    int len = g_text_len[id];
    if (n >= 0 && n < len) len = n;
    int txs = g_font->tiles_x, tys = g_font->tiles_y;
    int x = tx, y = ty;
    for (int i = 0; i < len; i++) {
        int cp = s[i];
        if (cp == '\n') { x = tx; y += tys; continue; }
        if (wrap > 0 && cp == ' ') {
            /* Coupe au MOT : on mesure le mot qui suit l'espace ; s'il ne tient
               pas sur la ligne, on passe à la suivante et l'espace disparaît
               (pas d'espace parasite en début de ligne). */
            int wlen = 0;
            for (int j = i + 1; j < len && s[j] != ' ' && s[j] != '\n'; j++) wlen++;
            if ((x - tx) + (1 + wlen) * txs > wrap) { x = tx; y += tys; continue; }
        }
        /* Filet : un mot plus long que la boîte est coupé au caractère, sinon
           il déborderait indéfiniment. */
        if (wrap > 0 && (x - tx) + txs > wrap) { x = tx; y += tys; }
        x += text_put(cp, x, y);
    }
}

void text_draw     (int id, int tx, int ty)                 { text_render(id, tx, ty, 0, -1); }
void text_draw_upto(int id, int tx, int ty, int n)          { text_render(id, tx, ty, 0, n); }
void text_draw_box (int id, int tx, int ty, int w, int n)   { text_render(id, tx, ty, w, n); }

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

/* ── Système texte HUD (via libtonc TTE, CBB3/SBB31) ────────────── */
/* Le BG hardware utilisé est configuré par scène (défaut BG3). CBB=3, SBB=31.  */
/* se0=0xF001 : glyphes démarrent à la tuile 1, tuile 0 reste transparente. */

void draw_printf(int col, int row, const char *fmt, ...);
void draw_clear (int col, int row, int len);

#ifdef GBA_ENGINE_IMPL
#include <stdarg.h>

void draw_printf(int col, int row, const char *fmt, ...) {
    char buf[64];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    tte_set_pos(col * 8, row * 8);
    tte_write(buf);
}

void draw_clear(int col, int row, int len) {
    tte_erase_rect(col * 8, row * 8, (col + len) * 8, (row + 1) * 8);
}

#endif /* GBA_ENGINE_IMPL */

/* ── Clear toutes les BG screenblocks ───────────────────────────── */
static void bg_maps_clear(void) {
    for (int sbb = 0; sbb < 32; sbb++) {
        vu16 *m = MAP_RAM(sbb);
        for (int j = 0; j < 1024; j++) m[j] = 0;
    }
}

/* ── Shadow OAM ──────────────────────────────────────────────────── */
static OBJATTR shadow_oam[128];

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
