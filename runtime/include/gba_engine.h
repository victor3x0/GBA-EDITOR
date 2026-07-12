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
