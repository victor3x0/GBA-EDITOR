/* gba_engine.h — fonctions utilitaires GBA bas-niveau (statiques, non générées).
   Inclus UNE SEULE FOIS depuis main.c. */
#ifndef GBA_ENGINE_H
#define GBA_ENGINE_H

#include <gba_video.h>
#include <gba_sprites.h>
#include <gba_dma.h>
#include "tonc_tte.h"

/* ── Accès mémoire GBA ──────────────────────────────────────────── */
#define TILE_RAM(cbb)  ((vu16*)(0x06000000+(cbb)*0x4000))
#define MAP_RAM(sbb)   ((vu16*)(0x06000000+(sbb)*0x800))
#define PAL_BG_RAM     ((vu16*)0x05000000)
#define OBJ_VRAM       ((vu16*)0x06010000)
#define PAL_OBJ_RAM    ((vu16*)0x05000200)
#define BGOFS(n)       (*((vu16*)(0x04000010+(n)*4)))

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
