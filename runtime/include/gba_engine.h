/* SPDX-License-Identifier: Zlib
   Copyright (c) 2026 Yasor Rovic

   Licence zlib — PAS la GPL de l'éditeur (cf. runtime/LICENSE). Ce fichier est
   recopié dans le projet de l'utilisateur au build, puis compilé dans sa ROM :
   le jeu produit lui appartient entièrement, il peut le vendre, et il n'a
   aucune notice à joindre à sa ROM. */
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
/* Décalage de screenblock d'une case (c,r) dans une carte large de `gcols`.
   Les blocs d'une carte multi-blocs se suivent : +0x400 u16 par bloc. Une carte
   64-large en aligne deux par rangée (droite = +1 bloc, bas = +2) ; une carte
   32-large n'en a qu'un par rangée, son bas est donc le bloc SUIVANT — pas deux
   plus loin. Point de vérité UNIQUE : chargement initial, streaming et fonds
   animés passent tous par ici. */
static int bg_block_ofs(int gcols, int c, int r) {
    if (gcols > 32) {
        if (c >= 32 && r >= 32) return 0xC00;
        if (r >= 32)            return 0x800;
        if (c >= 32)            return 0x400;
        return 0;
    }
    return r >= 32 ? 0x400 : 0;
}

static void load_map(vu16*dst, const void*src,
                     int tw, int th, int gcols, int grows) {
    const u16*m = (const u16*)src;
    for (int y = 0; y < grows; y++) {
        for (int x = 0; x < gcols; x++) {
            u16 t = (x < tw && y < th) ? m[y*tw + x] : 0;
            dst[bg_block_ofs(gcols, x, y) + (y & 31)*32 + (x & 31)] = t;
        }
    }
}

/* ── Streaming de map 2D (grands niveaux qui défilent) ────────────── */
/* Fenêtre VRAM win_w×win_h (≤64) qui wrappe ; bg_base_col/row = coin haut-gauche
   monde chargé. Au scroll, on recopie la colonne/ligne entrante dans sa case
   VRAM (world & 63). `map` = tilemap COMPLÈTE en ROM (tiles_w×tiles_h SE, row-
   major). `dst` = MAP_RAM(sbb). Un seul fond streamé par scène. Pattern Tonc. */
static int bg_base_col, bg_base_row;

/* Écrit une SE à (c,r) dans une carte large de `gcols` (cf. bg_block_ofs). */
static void bg_se_write(vu16 *dst, int gcols, int c, int r, u16 se) {
    dst[bg_block_ofs(gcols, c, r) + (r & 31)*32 + (c & 31)] = se;
}

static void bg_load_col(vu16 *dst, const unsigned short *map,
                        int tiles_w, int tiles_h, int win_w, int win_h, int wc) {
    for (int r = bg_base_row; r < bg_base_row + win_h; r++) {
        u16 se = (wc < tiles_w && r < tiles_h) ? map[r*tiles_w + wc] : 0;
        bg_se_write(dst, win_w, wc & 63, r & 63, se);
    }
}

static void bg_load_row(vu16 *dst, const unsigned short *map,
                        int tiles_w, int tiles_h, int win_w, int wr) {
    for (int c = bg_base_col; c < bg_base_col + win_w; c++) {
        u16 se = (c < tiles_w && wr < tiles_h) ? map[wr*tiles_w + c] : 0;
        bg_se_write(dst, win_w, c & 63, wr & 63, se);
    }
}

static void __attribute__((unused)) bg_stream_init(
        vu16 *dst, const unsigned short *map,
        int tiles_w, int tiles_h, int win_w, int win_h) {
    bg_base_col = 0; bg_base_row = 0;
    for (int r = 0; r < win_h; r++)
        for (int c = 0; c < win_w; c++) {
            u16 se = (c < tiles_w && r < tiles_h) ? map[r*tiles_w + c] : 0;
            bg_se_write(dst, win_w, c, r, se);
        }
}

/* Horizontal AVANT vertical : la ligne entrante (load_row) utilise le
   bg_base_col déjà mis à jour et corrige la case-coin. */
static void __attribute__((unused)) bg_stream_update(
        vu16 *dst, const unsigned short *map, int tiles_w, int tiles_h,
        int win_w, int win_h, int stream_h, int stream_v, int cam_x, int cam_y) {
    if (stream_h) {
        int cc = cam_x >> 3;
        while (bg_base_col < cc) { bg_load_col(dst, map, tiles_w, tiles_h, win_w, win_h, bg_base_col + 64); bg_base_col++; }
        while (bg_base_col > cc) { bg_base_col--; bg_load_col(dst, map, tiles_w, tiles_h, win_w, win_h, bg_base_col); }
    }
    if (stream_v) {
        int cr = cam_y >> 3;
        while (bg_base_row < cr) { bg_load_row(dst, map, tiles_w, tiles_h, win_w, bg_base_row + 64); bg_base_row++; }
        while (bg_base_row > cr) { bg_base_row--; bg_load_row(dst, map, tiles_w, tiles_h, win_w, bg_base_row); }
    }
}

/* ── Fonds ANIMÉS posés sur un fond hôte ─────────────────────────── */
/* Mode `instance` : on réécrit les ENTRÉES DE CARTE du rectangle, les tuiles de
   toutes les images restant résidentes dans le charblock de l'hôte. Chaque
   placement a donc son propre compteur — deux copies du même animé peuvent être
   à des moments différents de leur boucle.

   `frames` = toutes les images à la suite (cols×rows entrées chacune), déjà
   décalées en tuile et en banque par le build : ici on ne fait que recopier. */

typedef struct {
    const unsigned short *frames;
    u16 sbb;            /* screenblock de la carte du calque hôte */
    u8  ms;             /* taille de cette carte (bits map_size) */
    u8  col, row;       /* coin haut-gauche du rectangle, en tuiles */
    u8  cols, rows;     /* taille du rectangle, en tuiles */
    u8  nframes, speed, loop;
    u8  f0, t0;         /* départ authoré (décalage de phase de CETTE copie) */
    u8  f, t;           /* image courante, ticks écoulés dans cette image */
} BgAnim;

static void bg_anim_draw(BgAnim *a) {
    const unsigned short *se = a->frames + (u32)a->f * a->cols * a->rows;
    vu16 *dst = MAP_RAM(a->sbb);
    int gcols = (a->ms & 1) ? 64 : 32;   /* bit 0 de map_size = 64 colonnes */
    for (int r = 0; r < a->rows; r++)
        for (int c = 0; c < a->cols; c++)
            bg_se_write(dst, gcols, a->col + c, a->row + r, se[r*a->cols + c]);
}

/* Pose la 1ère image. Appelé APRÈS le chargement de la carte de l'hôte, qu'il
   recouvre : l'animé n'existe pas dans la carte en ROM, il est toujours posé
   par-dessus — c'est ce qui permet au même hôte de servir des scènes qui ne
   posent pas les mêmes animés. */
/* Repart du décalage AUTHORÉ et non de zéro : deux copies posées à des moments
   différents de leur boucle doivent se retrouver comme l'auteur les a réglées à
   chaque entrée dans la scène, pas là où la visite précédente les avait
   laissées. */
static void __attribute__((unused)) bg_anim_init(BgAnim *list, int n) {
    for (int i = 0; i < n; i++) {
        list[i].f = list[i].f0; list[i].t = list[i].t0;
        bg_anim_draw(&list[i]);
    }
}

/* Mode `shared` : c'est la TUILE qu'on réécrit, pas la carte. Une seule image
   est résidente, dans un bloc réservé du charblock de l'hôte, et toute case qui
   l'utilise change avec elle — d'où le nom. La carte, elle, est cuite en ROM et
   ne bouge jamais : rien à écrire de ce côté au runtime.

   `frames` = toutes les images à la suite, `words` mots de 32 bits chacune. */
typedef struct {
    const unsigned int *frames;
    u16 cbb;            /* charblock du calque hôte */
    u16 vram_ofs;       /* décalage du bloc réservé, en u16 depuis la base */
    u16 words;          /* mots de 32 bits par image */
    u8  nframes, speed, loop;
    u8  f, t;
} BgTileAnim;

static void bg_tileanim_draw(BgTileAnim *a) {
    copy16(TILE_RAM(a->cbb) + a->vram_ofs,
           a->frames + (u32)a->f * a->words, (u32)a->words * 4);
}

static void __attribute__((unused)) bg_tileanim_init(BgTileAnim *list, int n) {
    for (int i = 0; i < n; i++) { list[i].f = 0; list[i].t = 0; }
    /* Pas de dessin ici : l'image 0 est DÉJÀ dans le bloc réservé du tileset
       chargé juste avant — la recopier ne ferait qu'écrire les mêmes octets. */
}

static void __attribute__((unused)) bg_tileanim_update(BgTileAnim *list, int n) {
    for (int i = 0; i < n; i++) {
        BgTileAnim *a = &list[i];
        if (a->nframes <= 1) continue;
        if (++a->t < a->speed) continue;
        a->t = 0;
        if (a->f + 1 < a->nframes)      a->f++;
        else if (a->loop)               a->f = 0;
        else                            continue;
        bg_tileanim_draw(a);
    }
}

static void __attribute__((unused)) bg_anim_update(BgAnim *list, int n) {
    for (int i = 0; i < n; i++) {
        BgAnim *a = &list[i];
        if (a->nframes <= 1) continue;
        if (++a->t < a->speed) continue;
        a->t = 0;
        if (a->f + 1 < a->nframes)      a->f++;
        else if (a->loop)               a->f = 0;
        else                            continue;   /* figé sur la dernière */
        bg_anim_draw(a);
    }
}

/* ── Palettes au runtime ─────────────────────────────────────────── */
/* Remplacer les seize couleurs d'une banque matérielle : c'est ce qui permet de
   changer l'ambiance d'un décor en cours de jeu — la nuit qui tombe, une saison
   qui vire, une salle qui passe au rouge.

   Le MÉLANGE (blend_*) ne couvre pas ce besoin : il assombrit ou éclaircit vers
   le noir ou le blanc, uniformément, et sa granularité est le CALQUE (BLDCNT ne
   cible que BG0-3, OBJ et le backdrop). Une banque, elle, ne concerne que les
   tuiles qui la citent — on peut donc refroidir un décor en gardant ses
   lanternes allumées, ce que le mélange ne sait pas faire.

   `g_palettes` est émis par main_gen : le catalogue entier du projet, 16
   couleurs par entrée. Les deux pools sont physiquement distincts, d'où deux
   fonctions plutôt qu'un argument de cible. */

extern const unsigned short g_palettes[][16];

extern const int g_palette_count;

/* Bornés des DEUX côtés : une banque hors 0-15 écrirait dans la palette
   voisine, un index hors table lirait des couleurs au hasard. Le nom vient
   d'une constante générée, donc l'index est juste par construction — sauf si
   la palette a été supprimée du catalogue entre deux builds. */
void palette_set_bg(int bank, int idx) {
    if (bank < 0 || bank > 15 || idx < 0 || idx >= g_palette_count) return;
    copy16(PAL_BG_RAM + bank * 16, g_palettes[idx], 32);
}

void palette_set_obj(int bank, int idx) {
    if (bank < 0 || bank > 15 || idx < 0 || idx >= g_palette_count) return;
    copy16(PAL_OBJ_RAM + bank * 16, g_palettes[idx], 32);
}

/* ── Sauvegarde (SRAM) ───────────────────────────────────────────── */
/* 32 Kio de mémoire sauvegardée à 0x0E000000, alimentés par la pile de la
   cartouche. Deux règles matérielles, non négociables :

     - l'accès se fait OCTET PAR OCTET. Un `memcpy` ou un accès 16/32 bits y
       lit et écrit du n'importe quoi — d'où les quatre écritures explicites de
       `sram_put32` plutôt qu'un cast de pointeur, que le compilateur ne pourra
       pas recombiner (le pointeur est volatile) ;
     - le bus SRAM est lent : ses waitstates doivent être posés une fois au
       démarrage, sinon la lecture rend des octets faux sur matériel réel là où
       l'émulateur, lui, ne dira rien.

   Ce que le moteur sauve, ce sont les variables globales MARQUÉES persistantes
   dans l'éditeur. Il ne connaît ni la scène courante, ni aucun état interne :
   reprendre une partie est un aiguillage que l'auteur écrit (cf. ROADMAP v0.5).

   Le format est TOLÉRANT à l'évolution du jeu : chaque valeur est rangée avec
   l'id opaque de sa variable, pas à un rang. Ajouter, retirer ou réordonner une
   variable laisse donc les sauvegardes existantes lisibles, là où un tableau
   positionnel aurait fait lire à `score` la valeur de `vies`. Une variable
   absente du fichier reprend sa valeur par défaut : une lecture rend un état
   COMPLET, jamais un mélange entre le fichier et la partie en cours.

   Les tables ci-dessous sont émises par main_gen — trois tableaux parallèles,
   une entrée par variable persistante. Un projet qui n'en a aucune reçoit
   `g_save_count == 0`, et rien ici ne touche la SRAM. */

#define SRAM_MEM       ((vu8*)0x0E000000)
#define SRAM_SIZE      32768
#define REG_WAITCNT   (*(vu16*)0x04000204)

/* En-tête d'un emplacement, 12 octets :
     0  'G','B','S','V'   marque de reconnaissance
     4  u16 version du format
     6  u16 nombre d'enregistrements qui suivent
     8  u32 somme de contrôle des enregistrements
   Puis `n` enregistrements de TAILLE VARIABLE (ROADMAP v0.20) :
     0  u32 id de la variable
     4  u32 taille de la charge utile, en octets (multiple de 4)
     8  la charge utile

   Une variable y écrit ses cases les unes derrière les autres, chacune sur
   `bits` bits — 1 pour un booléen, 32 pour un int. Un tableau de 400 coffres
   tient donc en 50 octets et non en 1 600 : c'est le codegen qui décide du
   paquetage, l'auteur n'en entend jamais parler (décision verrouillée v0.20).

   Un scalaire n'est que le cas `count == 1` : sa charge utile fait 4 octets,
   exactement la valeur qu'écrivait le format v1. Seul l'en-tête d'enregistrement
   grandit de 4 octets, d'où la version 2 — un emplacement écrit par une version
   antérieure est REFUSÉ proprement plutôt que relu de travers. */
#define SAVE_MAGIC0    'G'
#define SAVE_MAGIC1    'B'
#define SAVE_MAGIC2    'S'
#define SAVE_MAGIC3    'V'
#define SAVE_VERSION   2
#define SAVE_HEADER    12
#define SAVE_REC_HEAD  8

extern const unsigned int   g_save_id[];    /* id opaque de la variable, replié sur 32 bits */
extern const unsigned short g_save_idx[];   /* son index GLOBAL_* — l'entrée de global_read/write */
extern const int            g_save_def[];   /* sa valeur par défaut, la même pour toutes ses cases */
extern const unsigned short g_save_len[];   /* son nombre de CASES (1 = scalaire) */
extern const unsigned char  g_save_bits[];  /* ce qu'une case coûte en SRAM, en bits */
extern const int            g_save_count;
extern const int            g_save_slots;
extern const int            g_save_slot_size;

extern int  global_read (int i);
extern void global_write(int i, int v);
extern int  global_read_at (int i, int k);
extern void global_write_at(int i, int k, int v);

/* Waitstates SRAM à 8 cycles — la valeur sûre pour toutes les cartouches.
   Appelée une fois par main() avant toute lecture. */
static void sram_init(void) {
    REG_WAITCNT = (REG_WAITCNT & ~3) | 3;
}

static unsigned int sram_get32(int off) {
    return  (unsigned int)SRAM_MEM[off]
         | ((unsigned int)SRAM_MEM[off + 1] << 8)
         | ((unsigned int)SRAM_MEM[off + 2] << 16)
         | ((unsigned int)SRAM_MEM[off + 3] << 24);
}

static void sram_put32(int off, unsigned int v) {
    SRAM_MEM[off]     = (u8)(v);
    SRAM_MEM[off + 1] = (u8)(v >> 8);
    SRAM_MEM[off + 2] = (u8)(v >> 16);
    SRAM_MEM[off + 3] = (u8)(v >> 24);
}

/* Décalage du début d'un emplacement, ou -1 s'il n'existe pas. Le second test
   n'est pas redondant avec le garde-fou du build : `slot` peut venir d'une
   variable, donc de n'importe quoi. */
static int save_slot_base(int slot) {
    if (g_save_count <= 0 || slot < 0 || slot >= g_save_slots) return -1;
    int base = slot * g_save_slot_size;
    if (base + g_save_slot_size > SRAM_SIZE) return -1;
    return base;
}

static unsigned int save_sum(int base, int nbytes) {
    unsigned int s = 0;
    for (int i = 0; i < nbytes; i++)
        s = s * 31u + SRAM_MEM[base + SAVE_HEADER + i];
    return s;
}

/* ── Cases empaquetées ────────────────────────────────────────────
   Bit à bit, et non par mots : une case fait 1, 8, 16 ou 32 bits, donc elle
   ne s'aligne pas. C'est lent (32 opérations par case au pire) et ça n'a
   aucune importance — on sauvegarde une fois, à la demande du joueur, pas
   soixante fois par seconde. La clarté vaut mieux ici que la ruse. */
static void save_put_bits(int byte_base, int bit_pos, int bits, unsigned int v) {
    for (int b = 0; b < bits; b++) {
        int p = bit_pos + b;
        int o = byte_base + (p >> 3);
        u8 m = (u8)(1 << (p & 7));
        SRAM_MEM[o] = (u8)(((v >> b) & 1u) ? (SRAM_MEM[o] | m)
                                           : (SRAM_MEM[o] & (u8)~m));
    }
}

static unsigned int save_get_bits(int byte_base, int bit_pos, int bits) {
    unsigned int v = 0;
    for (int b = 0; b < bits; b++) {
        int p = bit_pos + b;
        if (SRAM_MEM[byte_base + (p >> 3)] & (1 << (p & 7))) v |= 1u << b;
    }
    return v;
}

/* Une valeur relue occupe `bits` bits ; si son type est signé, le bit de poids
   fort est un signe qu'il faut étendre. On l'étend SANS savoir si le type l'est
   — pour un type non signé, `global_write_at` recoupe à sa largeur et retrouve
   la valeur d'origine. Un booléen (1 bit) est laissé tel quel : l'étendre
   donnerait -1, vrai lui aussi, mais illisible en débogage. */
static int save_signed(unsigned int v, int bits) {
    if (bits >= 32 || bits == 1) return (int)v;
    unsigned int sign = 1u << (bits - 1);
    return (int)((v ^ sign) - sign);
}

/* La taille en octets de la charge utile d'une variable — ses cases empaquetées,
   arrondies au mot de 32 bits pour que l'enregistrement suivant reste aligné. */
static int save_payload_bytes(int len, int bits) {
    return ((len * bits + 31) / 32) * 4;
}

/* Longueur totale des `n` enregistrements présents, ou -1 si le parcours sort
   de l'emplacement — une SRAM à pile vide rend des tailles arbitraires, et
   les suivre à l'aveugle ferait lire l'emplacement voisin. */
static int save_records_bytes(int base, int n) {
    int room = g_save_slot_size - SAVE_HEADER, off = 0;
    for (int r = 0; r < n; r++) {
        if (off + SAVE_REC_HEAD > room) return -1;
        unsigned int sz = sram_get32(base + SAVE_HEADER + off + 4);
        if (sz > (unsigned int)room) return -1;
        off += SAVE_REC_HEAD + (int)sz;
        if (off > room) return -1;
    }
    return off;
}

/* Vrai si l'emplacement porte une sauvegarde LISIBLE : marque, version et somme
   de contrôle. Une cartouche à pile vide rend des octets plausibles — sans ces
   trois tests, le jeu restaurerait un état inventé sans un mot. */
int save_exists(int slot) {
    int base = save_slot_base(slot);
    if (base < 0) return 0;
    if (SRAM_MEM[base]     != SAVE_MAGIC0 || SRAM_MEM[base + 1] != SAVE_MAGIC1 ||
        SRAM_MEM[base + 2] != SAVE_MAGIC2 || SRAM_MEM[base + 3] != SAVE_MAGIC3)
        return 0;
    if ((SRAM_MEM[base + 4] | (SRAM_MEM[base + 5] << 8)) != SAVE_VERSION) return 0;
    int n = SRAM_MEM[base + 6] | (SRAM_MEM[base + 7] << 8);
    if (n < 0) return 0;
    /* Des enregistrements qui débordent de l'emplacement feraient lire
       l'emplacement suivant : la sauvegarde est alors tenue pour illisible. */
    int len = save_records_bytes(base, n);
    if (len < 0) return 0;
    return sram_get32(base + 8) == save_sum(base, len);
}

int save_write(int slot) {
    int base = save_slot_base(slot);
    if (base < 0) return 0;
    int n = g_save_count, off = 0;
    for (int i = 0; i < n; i++) {
        int len = g_save_len[i], bits = g_save_bits[i];
        int sz  = save_payload_bytes(len, bits);
        int rec = base + SAVE_HEADER + off;
        sram_put32(rec,     g_save_id[i]);
        sram_put32(rec + 4, (unsigned int)sz);
        /* La charge est mise à zéro avant d'être remplie : les bits de
           bourrage du dernier mot n'appartiennent à aucune case, et sans ça
           ils garderaient ce que la SRAM contenait — donc une somme de
           contrôle qui change sans que rien n'ait changé. */
        for (int b = 0; b < sz; b++) SRAM_MEM[rec + SAVE_REC_HEAD + b] = 0;
        for (int k = 0; k < len; k++)
            save_put_bits(rec + SAVE_REC_HEAD, k * bits, bits,
                          (unsigned int)global_read_at(g_save_idx[i], k));
        off += SAVE_REC_HEAD + sz;
    }
    SRAM_MEM[base]     = SAVE_MAGIC0;
    SRAM_MEM[base + 1] = SAVE_MAGIC1;
    SRAM_MEM[base + 2] = SAVE_MAGIC2;
    SRAM_MEM[base + 3] = SAVE_MAGIC3;
    SRAM_MEM[base + 4] = SAVE_VERSION & 0xFF;
    SRAM_MEM[base + 5] = (SAVE_VERSION >> 8) & 0xFF;
    SRAM_MEM[base + 6] = n & 0xFF;
    SRAM_MEM[base + 7] = (n >> 8) & 0xFF;
    /* La somme est écrite EN DERNIER : une coupure de courant en plein milieu
       laisse alors un emplacement qui ne se relit pas, plutôt qu'une sauvegarde
       à moitié écrite qui se relit très bien. */
    sram_put32(base + 8, save_sum(base, off));
    return 1;
}

int save_read(int slot) {
    if (!save_exists(slot)) return 0;
    int base = save_slot_base(slot);
    /* Les défauts d'abord : ce qui manque au fichier ne doit pas hériter de la
       valeur qu'avait la partie en cours. Toutes les CASES, pas seulement la
       première — c'est ce qui fait qu'un tableau agrandi depuis la dernière
       sauvegarde du joueur voit ses cases neuves partir du défaut. */
    for (int i = 0; i < g_save_count; i++)
        for (int k = 0; k < g_save_len[i]; k++)
            global_write_at(g_save_idx[i], k, g_save_def[i]);
    int n = SRAM_MEM[base + 6] | (SRAM_MEM[base + 7] << 8);
    int off = 0;
    for (int r = 0; r < n; r++) {
        int rec = base + SAVE_HEADER + off;
        unsigned int id = sram_get32(rec);
        int sz = (int)sram_get32(rec + 4);
        for (int i = 0; i < g_save_count; i++)
            if (g_save_id[i] == id) {
                int bits = g_save_bits[i];
                /* Ce que le FICHIER contient, borné par ce que le jeu attend
                   AUJOURD'HUI : un tableau qui a rétréci se tronque, un
                   tableau qui a grandi garde ses défauts au-delà. Même
                   tolérance que pour un scalaire absent (v0.5) — c'est elle
                   qui garantit qu'ajouter dix coffres n'efface pas les parties
                   déjà commencées. */
                int stored = bits ? (sz * 8) / bits : 0;
                if (stored > g_save_len[i]) stored = g_save_len[i];
                for (int k = 0; k < stored; k++)
                    global_write_at(g_save_idx[i], k,
                        save_signed(save_get_bits(rec + SAVE_REC_HEAD,
                                                  k * bits, bits), bits));
                break;   /* les ids sont uniques — le build le vérifie */
            }
        /* Un id inconnu est une variable retirée du jeu depuis : on l'ignore. */
        off += SAVE_REC_HEAD + sz;
    }
    return 1;
}

/* Efface la MARQUE, pas les octets : l'emplacement redevient « vide » pour
   save_exists, et la réécriture suivante repasse dessus de toute façon. */
int save_erase(int slot) {
    int base = save_slot_base(slot);
    if (base < 0) return 0;
    for (int i = 0; i < SAVE_HEADER; i++) SRAM_MEM[base + i] = 0;
    return 1;
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

/* Modes et côtés, nommés — le Lua les cite par leur nom (`blend.set_mode
   ("alpha")`), le codegen émet ces constantes. Voir scripting/api.py,
   « Énumérations matérielles ». */
#define BLD_MODE_NONE       0
#define BLD_MODE_ALPHA      1
#define BLD_MODE_BRIGHTEN   2
#define BLD_MODE_DARKEN     3

#define BLD_SIDE_TOP        0   /* la source du mélange */
#define BLD_SIDE_BOTTOM     1   /* ce sur quoi elle se mélange */

void blend_set_mode    (int mode);
int  blend_get_mode    (void);
void blend_set_layer   (int side, int bg, int on);
void blend_set_obj     (int side, int on);
void blend_set_backdrop(int side, int on);
void blend_set_alpha   (int eva, int evb);   /* 0-16 chacun, mode 1 */
void blend_set_fade    (int evy);            /* 0-16, modes 2 et 3 */

/* ── Transition de scène ─────────────────────────────────────────── */
/* Un fondu de transition prend le blending POUR LUI le temps de la bascule :
   BLDCNT n'a qu'un champ mode, il n'existe pas de fondu par-dessus une
   translucidité (cf. ROADMAP v0.6.2). D'où l'instantané — le réglage authoré
   de la scène est repris tel quel à la fin.

   `mode` vaut 2 (vers le blanc) ou 3 (vers le noir). Entre begin et end, les
   registres appartiennent au fondu : le display_reset() de scene_init écrit
   alors dans les shadows sans rallumer l'écran, et le réglage de la scène
   entrante prend effet d'un coup à la fin. Appelées par la boucle principale
   générée, jamais par un script. */
void transition_begin(int mode);
void transition_fade (int evy);   /* 0-16, sans toucher au réglage de la scène */
void transition_end  (void);

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

/* Sous-ensemble de glyphes chargé pour UNE scène.

   La police est complète en ROM, mais une scène n'affiche qu'une poignée de
   caractères et le build sait lesquels : inutile de copier la planche entière
   en VRAM (95 glyphes tombent à la quarantaine qu'un écran emploie).

   Deux tableaux, deux questions : `load` dit QUOI copier et dans quel ordre,
   `slot` dit OÙ un glyphe a atterri. Les émettre coûte quelques centaines
   d'octets de ROM ; les calculer au runtime coûterait de la RAM par police.

   Chemin tilemap uniquement : une police composée ne charge aucun glyphe. */
typedef struct FontSubset {
    const unsigned short* slot;    /* par glyphe : sa 1re tuile en VRAM,
                                      0xFFFF = pas chargé */
    const unsigned short* load;    /* tuiles ROM à copier, en ordre VRAM */
    unsigned short        n_load;  /* tuiles d'UNE variante */
    /* Variantes de COULEUR. Le sous-ensemble est chargé une fois par couleur
       employée dans la scène, chacune recolorée pendant la copie : la variante
       v occupe [v*n_load, (v+1)*n_load).
       `var_color[v]` = l'index de couleur de la variante, 0 = encre d'ORIGINE
       (aucune recolorisation, la police garde ses teintes).

       Des copies plutôt qu'une palette par couleur : sur le chemin tilemap une
       tuile porte des index de pixels FIGÉS, et `SE_PALBANK` ne choisit que la
       banque — colorer à l'unité demande donc des tuiles distinctes. Abordable
       grâce au sous-ensemble par scène. */
    unsigned char         n_var;
    const unsigned char*  var_color;
} FontSubset;

/* Posés par scene_init AVANT le premier text_set_font. Une police sans
   sous-ensemble déclaré se charge entière — c'est le repli quand le build n'a
   pas pu établir ce que la scène affiche. */
void text_clear_subsets(void);
void text_set_subset(int font, const FontSubset *sub);

/* Où la police `font` se charge, en tuiles RELATIVES au bloc du texte.

   Permet à un titre et à un corps de texte de coexister à l'écran : à base
   commune, la seconde police écrase les tuiles de la première. Les bases
   viennent du même calcul que la réservation de place
   (main_gen.scene_text_reservation). */
void text_set_font_base(int font, int base);

/* Banque de palette où le texte lit ses couleurs, posée par scene_init.

   `bg`/`obj` sont des SLOTS de la sélection de la scène — les deux pools sont
   distincts sur GBA (une bande de texte OBJ lit `PAL_OBJ_RAM`, un glyphe de
   tilemap `PAL_BG_RAM`). Négatif = comportement historique : la police charge
   sa PROPRE palette dans `FONT_PAL_BANK`.

   Au RUNTIME et pas dans `g_ui_regions`, table partagée par toutes les scènes :
   la même zone peut servir deux scènes aux palettes différentes. */
void text_set_pal_bank(int bg, int obj);

extern const FontInfo g_fonts[];
extern const int      g_font_count;   /* taille de g_fonts, émise */
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
    /* Fond de la zone : index dans la palette de la police (FONT_PAL_BANK) que
       la surface composée reçoit en fond, ou -1 = transparent (défaut). Posé par
       le codegen quand la zone est enfant d'un panel à fond couleur — le texte
       se COMPOSE alors (même en police mono) sur cette couleur, cf. g_ui_fill_bg. */
    signed char bg_fill;
    /* Couleur du texte : index dans la banque d'UI, 0 = encre d'origine de la
       police. Résolu en VARIANTE au rendu (cf. text_var_for) plutôt que stocké
       comme tel : `g_ui_regions` est partagée entre scènes, et deux scènes
       n'ont pas chargé les mêmes variantes. */
    unsigned char color;
    /* Index dans `g_ui_elements` (visibilité) — cf. plus bas. Une zone existe
       toujours comme élément, donc toujours >= 0 en pratique. */
    short elem;
} UIRegionInfo;

extern const UIRegionInfo g_ui_regions[];
extern const int g_ui_region_count;

/* ── Listes d'interface (ROADMAP v0.22) ───────────────────────────
   Le moteur prend la NAVIGATION, pas la mise en page : une liste est un panneau
   de la mise en page dont on suit l'index courant. Ses RANGÉES sont ses zones
   de texte enfants, dans l'ordre de l'arbre — rien à déclarer de plus, et ce
   qu'on voit dans l'éditeur est ce que la liste parcourt.

   Le nombre d'ITEMS n'est pas ici : c'est de la donnée, et un inventaire ne
   connaît sa longueur qu'en jeu. Le script le pose (`list.set_count`). Tant
   qu'il vaut 0, la liste ne bouge pas — il n'y a rien à parcourir.

   Ce que la liste NE fait pas : dessiner. Elle dit quel item est sélectionné et
   lequel s'affiche sur quelle rangée ; c'est le script qui écrit le contenu,
   avec `text.draw_in` et les outils de texte qui existent déjà. */
typedef struct UIListInfo {
    unsigned char rows;        /* rangées visibles = zones de texte enfants */
    unsigned char axis;        /* 0 = vertical, 1 = horizontal */
    unsigned char wrap;        /* le curseur repasse-t-il du dernier au premier ? */
    unsigned char rep_delay;   /* frames avant le premier renvoi */
    unsigned char rep_rate;    /* frames entre les renvois suivants */
    short row0;                /* décalage dans g_ui_list_rows */
} UIListInfo;

/* Posé par la boucle de frame de main.c, une fois par frame. */
extern u32 _g_keys_held;

extern const UIListInfo g_ui_lists[];
extern const short      g_ui_list_rows[];   /* index de région, à plat */
extern const int        g_ui_list_count;

/* État vivant, une entrée par liste — défini par main.c (le compte est une
   constante du build). Index et premier visible sont comptés À PARTIR DE 1,
   comme tout ce qui s'indexe dans ce logiciel. */
extern int g_ui_list_index[];
extern int g_ui_list_first[];
extern int g_ui_list_total[];
extern int g_ui_list_timer[];

int  ui_list_count    (int l);
void ui_list_set_count(int l, int n);
int  ui_list_index    (int l);
void ui_list_set_index(int l, int i);
int  ui_list_first    (int l);
int  ui_list_row      (int l, int r);
void ui_list_tick     (void);

/* ── Images d'interface ───────────────────────────────────────────
   Un SPRITE À ÉTAT posé sur la mise en page. L'élément DÉSIGNE un sprite et
   l'un de ses états ; il ne redéfinit ni la vitesse ni les frames, d'où les
   POINTEURS vers les tables d'animation du sprite — exactement celles que la
   boucle des acteurs consomme (`sprite_X_anim_dirs`, `_state_start`,
   `_state_speed`, `_state_loop`). Deux jeux de tables pour un même dessin
   auraient fini par ne plus dire la même chose.

   La DIRECTION n'entre pas ici : un élément d'interface n'a pas de cap. Le
   runtime prend la direction 0 (omnidirectionnelle), celle-là même que la
   boucle des acteurs prend en repli.

   `dirs` == 0 signale une image sans sprite résoluble : elle garde son index
   (sinon `IMAGE_*` désignerait l'élément d'à côté) et ne dessine rien. */
typedef struct UIImageInfo {
    short x, y;             /* origine, déjà alignée si la cible est BG */
    unsigned char w, h;     /* taille de la frame, en pixels */
    unsigned char target;   /* 0 = BG (tilemap), 1 = OBJ (sprite) */
    unsigned char anchor;   /* 0 écran, 1 monde, 2 acteur */
    short actor;            /* index dans g_actors, -1 = aucun */
    /* Tables d'animation du sprite — cf. ci-dessus. */
    const unsigned char (*dirs)[3];    /* {dir, frame_start, frame_count}, 255 = fin */
    const unsigned char *state_start;  /* 1re entrée de `dirs` par état */
    const unsigned char *state_speed;  /* ticks entre deux frames */
    const unsigned char *state_loop;   /* 1 = boucle */
    unsigned char n_states;
    unsigned char state0;   /* état posé par scene_init */
    unsigned char playing;  /* 0 = figée sur la 1re frame de l'état */
    /* Placement VRAM. `tile_base` est la base OBJ du sprite, valable en cible
       OBJ ; une image BG en reçoit une AUTRE, posée par scene_init
       (`ui_image_set_bg_base`) — elle dépend du charblock alloué à la scène,
       alors que cette table est partagée par toutes les scènes. */
    short tile_base;
    unsigned char tiles_per_frame;
    short oam_rel;          /* cible OBJ : slot OAM relatif à la base de la scène */
    unsigned char priority;
    /* PAVAGE — un fond de panneau répète la même frame pour couvrir un
       rectangle plus grand qu'elle (un OBJ ne s'étire pas sans mode affine).
       Une image vaut toujours 1×1. Les N sprites pointent la MÊME frame : le
       pavage coûte des slots OAM, pas une tuile de plus. */
    unsigned char cols, rows;
    /* Surcharge de `state_speed[state]`, en ticks entre deux frames. 0 = la
       vitesse du sprite, qui reste la source de vérité. */
    unsigned char speed;
    /* Index dans `g_ui_elements` (visibilité) — cf. plus bas. */
    short elem;
} UIImageInfo;

extern const UIImageInfo g_ui_images[];
extern const int g_ui_image_count;

/* ── Visibilité des éléments d'interface ────────────────────────────
   Table PLATE, PROJET-GLOBALE, qui couvre TOUS les éléments d'une mise en
   page — texte, panel, image confondus — contrairement à g_ui_regions/
   g_ui_images qui n'indexent que ce qui DESSINE. Un panel-groupe pur (fond
   `none`) n'a sinon aucune identité runtime.

   `visible` est l'état AUTHORÉ de départ (`ui.get(...):show()/:hide()` le
   bascule au script). `parent` est l'index du parent dans CETTE MÊME
   table, -1 = racine. La visibilité EFFECTIVE n'est JAMAIS stockée : elle
   remonte la chaîne des parents à la lecture (`ui_element_is_visible`),
   exactement comme le modèle Python (`UILayout.is_visible`) — cacher un
   enfant puis remontrer son parent laisse l'enfant caché, sans qu'aucune
   propagation n'ait à s'écrire ici non plus. */
typedef struct UIElementInfo {
    short parent;
    unsigned char visible;
} UIElementInfo;

extern const UIElementInfo g_ui_elements[];
extern const int g_ui_element_count;

#define UI_ELEMENT_MAX 64

void ui_elements_reset(void);          /* repose les bits authorés (par scène) */
int  ui_element_is_visible(int idx);   /* remonte la chaîne des parents */
void ui_element_show(int idx, int on); /* self:show() / self:hide() */

/* Posés par scene_init, AVANT le premier ui_image_update. Les trois dépendent
   de la SCÈNE (charblock alloué, sélection de palettes) alors que `g_ui_images`
   est partagée par toutes — d'où le réglage au runtime plutôt qu'en table. */
void ui_images_reset(void);              /* ferme les images de la scène précédente */
void ui_image_set_bg_base(int img, int tile);   /* cible BG : base dans le charblock d'UI */
/* Banque de palette PAR IMAGE, et non par scène : deux images peuvent afficher
   des sprites aux palettes distinctes, et une banque commune les repeindrait
   l'une avec les couleurs de l'autre. */
void ui_image_set_bank(int img, int bank);

/* Groupe ÉCRITURE — le pendant exact de `text_draw_in` pour un sprite. Aucune
   fonction ne crée ni ne déplace une image : la géométrie est authorée, et la
   rouvrir au runtime reprendrait ce que la mise en page existe pour fermer. */
void ui_image_set_state(int img, int state);
void ui_image_play(int img, int on);
/* Visibilité : ui_element_show(idx, on), cf. plus haut — plus de fonction
   par type, une image partage l'index avec le texte et les panels. */
int  ui_image_state(int img);
void ui_image_update(void);   /* une fois par frame, avant oam_update */

void text_set_layer(int bg);        /* posé par scene_init depuis Scene.text_bg */
void text_set_tile_base(int t);     /* posé par scene_init — cf. allocateur */
void text_set_surf_base(int t);     /* posé par scene_init SI la scène a un
                                        fond de zone — bloc dédié à la surface
                                        composée, distinct des glyphes mono */
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
void text_read_reset_all(void);   /* posé par scene_init — ferme les lectures
                                      de la scène précédente */
void text_update  (void);         /* une fois par frame, avant oam_update */
void text_clear_in    (int region);             /* vide une zone, BG ou OBJ */

/* Fond nine-slice/background d'une zone composée — posés par scene_init,
   AVANT les postes de texte (cf. `_gen_scene_init`). `text_clear_region_
   backdrops` vide la table de la scène précédente ; `text_set_region_
   backdrop` y enregistre une zone : `se`/`stride` sont ceux du PANEL entier
   émis pour cette scène, `(dx, dy)` recale sur le coin de la zone, `tile_
   base` est la base VRAM où l'asset source a été copié CETTE scène. */
void text_clear_region_backdrops(void);
void text_set_region_backdrop(int region, const unsigned short *se, int stride,
                              int dx, int dy, int tile_base);
void text_obj_set_base(int oam, int tile);   /* posé par scene_init */
void text_obj_set_actor_fn(int (*fx)(int), int (*fy)(int));

void tilemap_set        (int bg, int tx, int ty, int tile);
int  tilemap_get        (int bg, int tx, int ty);
void tilemap_set_palette(int bg, int tx, int ty, int bank);
void tilemap_set_flip   (int bg, int tx, int ty, int fh, int fv);
void tilemap_fill       (int bg, int tx, int ty, int w, int h, int tile);

/* Fond de conteneur d'UI (UIPanel) — statique, posé par scene_init sur le calque
   UI, AVANT que les scripts ne posent le texte par-dessus.
   `ui_fill_load_solid` grave une tuile PLEINE (64 px d'un même index de palette)
   dans le charblock UI ; `ui_fill_rect` la repose sur un rectangle de tuiles avec
   la banque de palette voulue. La couleur vient donc de (banque, index), pas de
   la tuile — d'où une tuile pleine par index distinct. */
void ui_fill_load_solid(int cbb, int tile, int index);
void ui_fill_rect      (int bg, int tx, int ty, int w, int h, int tile, int bank);
/* Fond IMAGE (nine-slice, background) : `se` est une carte w×h de screen
   entries préparée par le codegen — palette déjà rebasée sur les banques
   matérielles, index de tuile LOCAL à l'asset. `tile_base` est l'endroit où ses
   tuiles ont été copiées dans le charblock d'UI. `UI_SE_EMPTY` = case à laisser
   vide (hors de l'image source, ou centre d'un cadre ajouré). */
#define UI_SE_EMPTY 0xFFFF
void ui_fill_map       (int bg, int tx, int ty, int w, int h,
                        const unsigned short *se, int tile_base);

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

/* Tuile pleine : chaque nibble = index → un mot u16 = l'index répété 4 fois. */
void ui_fill_load_solid(int cbb, int tile, int index) {
    u16 w = (u16)((index & 0xF) * 0x1111);
    vu16 *dst = TILE_RAM(cbb) + tile * 16;
    for (int i = 0; i < 16; i++) dst[i] = w;
}

void ui_fill_rect(int bg, int tx, int ty, int w, int h, int tile, int bank) {
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++) {
            tilemap_set(bg, tx + c, ty + r, tile);
            tilemap_set_palette(bg, tx + c, ty + r, bank);
        }
}

void ui_fill_map(int bg, int tx, int ty, int w, int h,
                 const unsigned short *se, int tile_base) {
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++) {
            u16 e = se[r * w + c];
            vu16 *d = bg_se_addr(bg, tx + c, ty + r);
            /* La SE porte déjà sa banque de palette et ses drapeaux de miroir ;
               seul l'index de tuile est local à l'asset, d'où la rebase. */
            *d = (e == UI_SE_EMPTY)
               ? 0
               : (u16)((e & 0xFC00) | (((e & 0x03FF) + tile_base) & 0x03FF));
        }
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

/* Sous-ensembles déclarés par la scène courante. Plafond fixe : le moteur ne
   connaît pas la taille de `g_fonts`, qui est générée. Au-delà, la police se
   charge entière — dégradation visible en VRAM, jamais un rendu faux. */
#define TEXT_MAX_FONTS 16
static const FontSubset *g_subsets[TEXT_MAX_FONTS];
/* Sous-ensemble de la police RÉSIDENTE, ou 0 si elle est chargée entière. */
static const FontSubset *g_font_sub = 0;

/* Banque où le texte lit ses couleurs. Négatif = mode AUTOMATIQUE : la police
   charge sa propre palette dans FONT_PAL_BANK. C'est le défaut, le retirer
   d'office changerait la couleur du texte de tout projet existant. */
static int g_pal_bank_bg  = FONT_PAL_BANK;
static int g_pal_bank_obj = FONT_PAL_BANK;
static int g_pal_own      = 1;   /* 1 = la police impose ses couleurs */

void text_set_pal_bank(int bg, int obj) {
    g_pal_own     = (bg < 0);
    g_pal_bank_bg  = (bg  >= 0 && bg  < 16) ? bg  : FONT_PAL_BANK;
    g_pal_bank_obj = (obj >= 0 && obj < 16) ? obj : g_pal_bank_bg;
    g_font = 0;   /* la palette change : cf. text_set_font */
}

/* Base de chaque police dans le bloc du texte, et lesquelles y sont DÉJÀ.
   Le masque est ce qui rend l'alternance titre/corps gratuite : une police
   chargée à sa propre base y reste valide, plus rien à recopier. Avant, chaque
   `set_font` recopiait toute la planche. */
static short g_font_base[TEXT_MAX_FONTS];
static unsigned short g_font_loaded = 0;
static int g_base_cur = 0;      /* base de la police RÉSIDENTE */

void text_set_font_base(int font, int base) {
    if (font >= 0 && font < TEXT_MAX_FONTS) g_font_base[font] = (short)base;
    g_font_loaded = 0;          /* la géographie change : tout est à recharger */
    g_font = 0;
}

/* Les deux remettent `g_font` à zéro, comme `text_set_tile_base` : changer le
   sous-ensemble change CE QUI EST en VRAM, et la garde d'idempotence de
   `text_set_font` sauterait sinon la recopie. */
void text_clear_subsets(void) {
    for (int i = 0; i < TEXT_MAX_FONTS; i++) { g_subsets[i] = 0; g_font_base[i] = 0; }
    g_font_loaded = 0;
    g_font = 0;
}

void text_set_subset(int font, const FontSubset *sub) {
    if (font >= 0 && font < TEXT_MAX_FONTS) g_subsets[font] = sub;
    g_font = 0;
}

/* Variante de couleur en cours — index dans `FontSubset.var_color`, posé par
   zone au moment du rendu. 0 = encre d'origine, et c'est aussi ce que voit
   `text_draw` : une écriture libre n'a pas de zone où déclarer une couleur. */
static int g_var_cur = 0;

/* Première tuile VRAM du glyphe `gi`, ou -1 s'il n'a pas été chargé.

   -1 n'est pas une erreur : un glyphe hors du sous-ensemble est traité comme un
   caractère absent, la mise en page avance de sa chasse sans rien poser. */
static int text_glyph_slot(int gi) {
    if (!g_font_sub) return g_font->slot[gi];
    unsigned short s = g_font_sub->slot[gi];
    if (s == 0xFFFF) return -1;
    return (int)s + g_var_cur * g_font_sub->n_load;
}

/* Variante portant la couleur `color`, ou 0 (encre d'origine) si la police n'en
   a pas chargé — une zone peut demander une couleur qu'une AUTRE police de la
   scène n'emploie pas. Balayage linéaire sur au plus 16 entrées, une fois par
   appel de dessin et non par glyphe. */
static int text_var_for(int color) {
    if (!g_font_sub || color <= 0) return 0;
    for (int v = 0; v < g_font_sub->n_var; v++)
        if (g_font_sub->var_color[v] == color) return v;
    return 0;
}

/* ── Encre et remappage ─────────────────────────────────────────
   Remontés ici : `text_set_font` recolore les glyphes PENDANT la copie
   des variantes de couleur, donc avant tout ce qui compose des pixels. */
/* Encre courante — index de couleur dans la sous-palette de la police.
   0 = l'encre d'origine du glyphe, c'est-à-dire aucun remappage. */
static int g_ink = 0;

/* Masque des quartets NON NULS de `v` : 0xF là où le pixel est encré, 0 là où
   il est transparent (index 0). C'est ce qui permet d'écrire un glyphe sans
   effacer le voisin dont il chevauche la tuile — le cas normal dès que les
   chasses ne sont plus des multiples de 8.

   Les bits d'un quartet sont ramenés sur son bit 0 (décalages ≤ 3, aucun
   quartet ne contamine son voisin), puis `* 0xF` rétablit les quatre bits sans
   retenue, les bits retenus étant espacés de 4. */
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
   transposition de rampe — laquelle supposerait une palette rangée en rampes. */
static inline u32 text_recolor(u32 row) {
    if (!g_ink) return row;
    /* Borné à 15 : au-delà, `0x11111111 * n` déborde le mot de 32 bits et le
       dernier nibble sortirait d'une autre couleur. Le build refuse déjà la
       valeur — garde pour une ROM produite autrement. */
    u32 ink = (u32)(g_ink > 15 ? 15 : g_ink);
    return text_nib_mask(row) & (0x11111111u * ink);
}

void text_set_font(int f) {
    /* Borné sur le compte ÉMIS : `g_fonts` est générée, et un index hors table
       lirait un pointeur de tuiles au hasard, copié en VRAM. */
    if (f < 0 || f >= g_font_count) return;
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
    g_font_sub  = (f >= 0 && f < TEXT_MAX_FONTS) ? g_subsets[f] : 0;
    g_base_cur  = (f >= 0 && f < TEXT_MAX_FONTS) ? g_font_base[f] : 0;
    if (g_text_layer < 0 || !fi->tiles) return;
    /* Déjà à sa base : rien à recopier. Chaque police ayant sa propre place,
       revenir à la précédente ne coûte plus que ce test. */
    int done = (f >= 0 && f < TEXT_MAX_FONTS) && (g_font_loaded & (1u << f));
    if (!fi->composited && !done) {
        volatile u16 *dst = TILE_RAM(g_text_cbb) + (g_text_tile_base + g_base_cur) * 16;
        if (f >= 0 && f < TEXT_MAX_FONTS) g_font_loaded |= (unsigned short)(1u << f);
        if (g_font_sub) {
            /* Copie GLANÉE : seulement les tuiles que la scène peut afficher,
               dans l'ordre où `slot` les attend. Une fois par VARIANTE de
               couleur, l'encre remappée au passage — recolorer ici plutôt que
               d'émettre des tuiles en double ne coûte pas un octet de ROM. */
            const unsigned char n_var = g_font_sub->n_var ? g_font_sub->n_var : 1;
            volatile u32 *w32 = (volatile u32*)dst;
            for (int v = 0; v < n_var; v++) {
                int col = g_font_sub->var_color ? g_font_sub->var_color[v] : 0;
                for (int k = 0; k < g_font_sub->n_load; k++) {
                    const unsigned int *src = fi->tiles + g_font_sub->load[k] * 8;
                    volatile u32 *d = w32 + (v * g_font_sub->n_load + k) * 8;
                    if (!col) {
                        for (int q = 0; q < 8; q++) d[q] = src[q];
                    } else {
                        g_ink = col;
                        for (int q = 0; q < 8; q++) d[q] = text_recolor(src[q]);
                        g_ink = 0;
                    }
                }
            }
        } else {
            copy16(dst, fi->tiles, fi->n_tiles * 32);
        }
    }
    /* La police n'impose ses couleurs QUE si la scène n'a désigné aucune
       banque : sinon écraser la banque ici y remettrait les couleurs du PNG,
       et la seconde police chargée repeindrait la première. */
    if (g_pal_own) {
        copy16(PAL_BG_RAM + g_pal_bank_bg * 16, fi->pal, 32);
        /* Même palette côté sprites : une bande de texte OBJ lit PAL_OBJ_RAM.
           32 octets copiés toujours, moins cher que de savoir si une zone
           OBJ existe. */
        copy16(PAL_OBJ_RAM + g_pal_bank_obj * 16, fi->pal, 32);
    }
}

/* Piste d'événements du texte en cours de rendu. Posée par `text_render_region`
   le temps de l'appel : la mise en page doit savoir, glyphe par glyphe, s'il
   tombe sous une portée animée, et le passer en paramètre aurait traversé
   quatre fonctions qui n'en ont que faire. */
static const TextEvent *g_ev  = 0;
static int              g_nev = 0;


/* Couleur du SLOT en cours de rendu (0 = encre d'origine). Sur le chemin
   tilemap elle choisit une variante de glyphes ; sur le chemin composé, où les
   pixels sont écrits un à un, elle sert d'encre par défaut — sans quoi la même
   donnée donnerait deux rendus selon le chemin. */
static int g_zone_ink = 0;

/* La couleur qui couvre le caractère `i`, ou 0 (encre d'origine). */
static int text_color_at(int i) {
    if (!g_ev) return g_zone_ink;
    for (int k = 0; k < g_nev; k++) {
        if (g_ev[k].kind != TEXT_EV_COLOR) continue;
        if (i >= g_ev[k].at && i < g_ev[k].end) return g_ev[k].value;
    }
    /* La balise l'emporte sur la couleur du slot : elle est plus précise, et
       c'est l'auteur qui l'a posée à cet endroit-là du texte. */
    return g_zone_ink;
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

   Seuls les glyphes ANIMÉS sont capturés : `UIRegion.animated_glyphs` réserve
   de l'OAM pour un effet, pas pour un préfixe. Au-delà du budget la capture
   s'arrête et les suivants retombent dans la bande, en statique. */
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

/* ── Bloc de composition courant ──────────────────────────────────
   La surface BG et une bande de sprites ne diffèrent que par deux choses : où
   sont les tuiles, et comment on les indexe. Tout le reste — mise en page,
   chasses, ligatures, alignement, machine à écrire — est commun, d'où cette
   indirection plutôt qu'un second moteur de composition pour les OBJ.

   `h == 0` désigne la surface BG, adressée MODULO (partagée par tout l'écran,
   d'où son aliasing) ; une bande OBJ est un bloc privé de w×h tuiles, adressé
   directement. */
static volatile u32 *g_blit_mem = 0;
static int g_blit_tile0 = 0;
static int g_blit_w  = TEXT_SURF_W;
static int g_blit_h  = 0;          /* 0 = surface BG (modulo) */
static int g_blit_ox = 0, g_blit_oy = 0;   /* origine du bloc, en TUILES */

/* Base VRAM de la SURFACE composée — SÉPARÉE de `g_text_tile_base` (glyphes
   statiques mono). Les deux ne peuvent PAS partager une adresse : la surface
   se réécrit en pixels à chaque composition, ce qui corromprait des glyphes
   mono résidents lus par une AUTRE zone de la même scène. 0 = pas de surface
   réservée (scène sans aucune zone à fond) → repli sur `g_text_tile_base`,
   comportement d'avant pour une police proportionnelle seule. Posée par
   scene_init via `text_set_surf_base`, à appeler APRÈS text_set_tile_base. */
static int g_surf_tile_base = 0;
void text_set_surf_base(int t) { g_surf_tile_base = (t > 0 && t < 1024) ? t : 0; }

static void blit_use_bg_surface(void) {
    g_blit_mem   = (volatile u32*)(TILE_RAM(g_text_cbb));
    g_blit_tile0 = g_surf_tile_base ? g_surf_tile_base : g_text_tile_base;
    g_blit_w     = TEXT_SURF_W;
    g_blit_h     = 0;
    g_blit_ox    = g_blit_oy = 0;
}

/* Fond de la ZONE en cours de rendu : index dans FONT_PAL_BANK que la surface
   composée reçoit en fond (-1 = transparent). Posé par `text_render_region_cp`
   depuis `UIRegionInfo.bg_fill`, remis à -1 après. */
static int g_ui_fill_bg = -1;

/* Vrai quand la zone courante doit se COMPOSER plutôt que poser des tuiles :
   police proportionnelle, bloc privé (bande OBJ), ou CETTE zone a un fond
   (`g_ui_fill_bg >= 0`, posé par `text_render_region_cp`). PAR ZONE et non par
   scène : une zone sans fond garde le tilemap, moins cher et sans conflit
   d'adresse avec la surface de ses voisines. */
static int text_is_composited(void) {
    return (g_font && g_font->composited) || g_blit_h || g_ui_fill_bg >= 0;
}

/* ── Fond NINE-SLICE/BACKGROUND recomposé sous un texte ──────────────
   Un panel Color donne à ses zones enfant un simple APLAT (`g_ui_fill_bg`,
   ci-dessus) : une couleur suffit à la surface composée. Un panel Nine-slice
   ou Background n'a pas d'aplat qui vaille — il faut les VRAIS pixels du
   cadre à cet endroit, faute de quoi composer une zone REMPLACE le cadre par
   du transparent au lieu de se poser dessus.

   Posé par `scene_init` (donc scène-spécifique, comme la base VRAM où
   l'asset source a été copié cette scène-ci) — contrairement à
   `UIRegionInfo`, table PROJET-GLOBALE incapable de porter une base qui
   varie d'une scène à l'autre. Table scannée linéairement plutôt qu'indexée
   par région : peu de zones composent sur un fond image à la fois dans une
   scène, un tableau à la taille de `g_ui_regions` gaspillerait pour rien.

   Un seul mot par pixel : la tuile de surface reçoit la MÊME banque de
   palette pour le cadre recopié et pour l'encre du glyphe
   (`g_pal_bank_bg`) — le hardware n'en offre qu'une par tuile. C'est un
   contrat d'auteur (le build le vérifie) : `scene.ui_pal_bank` doit désigner
   la banque de l'asset nine-slice/background, et l'encre du texte doit être
   une couleur déjà présente dans cette même banque. */
#define TEXT_REGION_BACKDROP_MAX 8

typedef struct {
    short region;                 /* index dans g_ui_regions */
    const unsigned short *se;     /* carte du PANEL ENTIER (pas dupliquée) */
    short stride;                 /* largeur du panel, en tuiles */
    short dx, dy;                 /* coin de la zone DANS le panel, en tuiles */
    short tile_base;              /* où l'asset source a été copié cette scène */
} RegionBackdrop;

static RegionBackdrop g_region_backdrop[TEXT_REGION_BACKDROP_MAX];
static int g_region_backdrop_n = 0;
/* Fond de la zone EN COURS de composition — posé par `text_render_region_cp`
   (et par `text_clear_region_at`, son pendant à l'effacement) depuis une
   recherche dans la table ci-dessus, remis à NULL après. NULL = zone sans
   fond image, `text_surf_prepare`/`text_clear` retombent sur `g_ui_fill_bg`. */
static const RegionBackdrop *g_ui_backdrop = 0;

/* Vide la table — posé par `scene_init`, au même titre que
   `text_read_reset_all` : sans lui une zone de la scène PRÉCÉDENTE resterait
   enregistrée sous le même index et prêterait sa carte à une zone qui n'a
   plus rien à voir avec elle. */
void text_clear_region_backdrops(void) { g_region_backdrop_n = 0; }

void text_set_region_backdrop(int r, const unsigned short *se, int stride,
                              int dx, int dy, int tile_base) {
    if (g_region_backdrop_n >= TEXT_REGION_BACKDROP_MAX) return;
    RegionBackdrop *b = &g_region_backdrop[g_region_backdrop_n++];
    b->region = (short)r; b->se = se; b->stride = (short)stride;
    b->dx = (short)dx;    b->dy = (short)dy;    b->tile_base = (short)tile_base;
}

static const RegionBackdrop *text_region_backdrop(int r) {
    for (int i = 0; i < g_region_backdrop_n; i++)
        if (g_region_backdrop[i].region == r) return &g_region_backdrop[i];
    return 0;
}

/* Inverse l'ordre des 8 nibbles d'un mot — un flip HORIZONTAL de tuile,
   baké en pixels puisque la tuile de surface ne porte pas son propre
   drapeau de miroir (elle est composée une fois, pas relue par le hardware
   avec la SE d'origine). */
static u32 text_nibble_hflip(u32 row) {
    u32 out = 0;
    for (int i = 0; i < 8; i++)
        out |= ((row >> (i * 4)) & 0xF) << ((7 - i) * 4);
    return out;
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



/* ── Cadre de clip ────────────────────────────────────────────────
   En PIXELS écran, posé par chaque entrée de rendu : le rectangle de la zone
   pour `draw_in`, l'écran pour `draw`. Ce qui n'y tient pas n'est pas POSÉ —
   la coupe se fait au dernier glyphe entier, jamais au milieu d'un.

   Seul endroit qui empêche un débordement d'écrire ailleurs : `tilemap_set` ne
   borne rien, et `text_surf_tile` REPLIE (modulo) sur la surface BG partagée au
   lieu de refuser. Un texte trop long repeindrait le décor ou la zone voisine.

   La mesure passe par le même cadre, donc la surface préparée ne dépasse pas la
   zone non plus : le charblock ne paie pas des tuiles invisibles. */
static int g_clip_x = 0, g_clip_y = 0, g_clip_w = 240, g_clip_h = 160;

static void text_clip_set(int x, int y, int w, int h) {
    g_clip_x = x; g_clip_y = y; g_clip_w = w; g_clip_h = h;
}

static void text_clip_screen(void) { text_clip_set(0, 0, 240, 160); }

/* Le glyphe tient-il dans le cadre ? Décidé sur sa CHASSE, pas sur sa cellule :
   c'est la mesure de la coupe au mot, et celle que rejoue l'aperçu de l'éditeur
   (core/text_layout.py). Juger sur la cellule ferait tomber le dernier glyphe
   d'une ligne dès qu'une chasse de 3 px vit dans une cellule de 8.

   Verticalement, la hauteur dessinée : une case fusionnée 16×16 sur la dernière
   rangée d'une zone de 16 px n'a pas de demi-version acceptable.

   Ce test DÉCIDE, il ne protège pas — l'encre qui déborde de sa chasse est
   arrêtée au site d'écriture (`text_tile_in_clip`). */
static int text_glyph_fits(int gi, int x, int y) {
    if (gi < 0) return 0;
    int h = g_font->gh[gi] * 8;
    return x >= g_clip_x && y >= g_clip_y
        && x + g_font->adv[gi] <= g_clip_x + g_clip_w
        && y + h <= g_clip_y + g_clip_h;
}

/* Dernier rempart, à la CASE. Exact et non prudent : les cadres sont alignés à
   la tuile (`UIRegion.snap_to_tile` côté émetteur, l'écran par nature).

   Il rattrape ce que le test ci-dessus laisse passer : l'encre d'un glyphe qui
   déborde de sa chasse sur son voisin de droite, cas normal en proportionnel.
   Sans lui elle irait dans une case non préparée — c'est-à-dire n'importe où,
   `text_surf_tile` repliant modulo sur la surface partagée. */
static int text_tile_in_clip(int tx, int ty) {
    return tx >= (g_clip_x >> 3) && ty >= (g_clip_y >> 3)
        && tx <  ((g_clip_x + g_clip_w + 7) >> 3)
        && ty <  ((g_clip_y + g_clip_h + 7) >> 3);
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
    if (t0 >= 0 && text_tile_in_clip(px >> 3, py >> 3)) {
        volatile u32 *w0 = base + t0 * 8 + (py & 7);
        *w0 = (*w0 & ~(m << shift)) | ((row << shift) & (m << shift));
    }
    /* Débord sur la tuile suivante — seulement si le glyphe n'est pas aligné.
       Le décalage inverse serait indéfini pour shift == 0, d'où le garde. */
    if (shift) {
        int rs = 32 - shift;
        u32 mh = m >> rs;
        int t1 = text_surf_tile((px >> 3) + 1, py >> 3);
        if (mh && t1 >= 0 && text_tile_in_clip((px >> 3) + 1, py >> 3)) {
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

/* Écrit les 8 mots u32 d'une tuile de surface pour la case LOCALE (lc, lr)
   de la zone en cours de composition — c'est-à-dire l'offset depuis l'ORIGINE
   de la zone (le même `(0,0)` que `dx,dy` dans `RegionBackdrop`).

   Avec un fond image enregistré (`g_ui_backdrop`), recopie les VRAIS pixels
   du cadre à cet endroit (flip de la SE source baké en pixels, la tuile de
   surface elle-même n'en portant pas) ; sinon retombe sur l'aplat
   `g_ui_fill_bg` (ou transparent). Partagée par `text_clear` et
   `text_surf_prepare` : effacer et préparer doivent revenir au MÊME fond,
   sinon l'un des deux referait apparaître le mauvais. */
static void text_surf_seed(volatile u32 *p, int lc, int lr) {
    const RegionBackdrop *bd = g_ui_backdrop;
    if (bd) {
        unsigned short e = bd->se[(bd->dy + lr) * bd->stride + (bd->dx + lc)];
        if (e != UI_SE_EMPTY) {
            int local = (int)(e & 0x03FF);
            int fh = e & 0x0400, fv = e & 0x0800;
            const volatile u32 *sp =
                (const volatile u32*)(TILE_RAM(g_text_cbb)) + (bd->tile_base + local) * 8;
            for (int k = 0; k < 8; k++) {
                u32 row = sp[fv ? (7 - k) : k];
                p[k] = fh ? text_nibble_hflip(row) : row;
            }
            return;
        }
    }
    u32 bg = (g_ui_fill_bg >= 0) ? (u32)(g_ui_fill_bg & 0xF) * 0x11111111u : 0u;
    for (int k = 0; k < 8; k++) p[k] = bg;
}

/* Vide la zone. En mono il suffit de remettre le tilemap sur la tuile 0 ; en
   proportionnel les pixels sont DANS les tuiles de surface, c'est donc elles
   qu'il faut remettre à zéro — sinon le texte suivant s'écrirait par-dessus
   l'ancien, la composition ne faisant que poser de l'encre. */
void text_clear(int tx, int ty, int w, int h) {
    if (g_text_layer < 0) return;
    int prop = text_is_composited();
    blit_use_bg_surface();          /* text_clear ne vide QUE la surface BG */
    volatile u32 *base = g_blit_mem;
    /* Effacer prend des coordonnées LIBRES, comme `draw` : son cadre est donc
       l'écran. Sinon un rectangle trop grand viderait des cases qui ne lui
       appartiennent pas — sur la surface partagée, n'importe lesquelles. */
    text_clip_screen();
    for (int r = 0; r < h; r++)
        for (int c = 0; c < w; c++) {
            if (!text_tile_in_clip(tx + c, ty + r)) continue;
            if (prop) {
                volatile u32 *t = base + text_surf_tile(tx + c, ty + r) * 8;
                text_surf_seed(t, c, r);
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
            tilemap_set_palette(g_text_layer, tx + c, ty + r, g_pal_bank_bg);
            /* La tuile de surface ne porte pas de flip propre : le fond
               image y a déjà été baké par `text_surf_seed`. */
            tilemap_set_flip(g_text_layer, tx + c, ty + r, 0, 0);
            volatile u32 *p = base + t * 8;
            text_surf_seed(p, c, r);
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
    int rel = text_glyph_slot(gi);
    if (rel < 0) return;          /* hors du sous-ensemble chargé */
    int slot = g_text_tile_base + g_base_cur + rel;
    int txs  = g_font->gw[gi];
    int tys  = g_font->gh[gi];
    for (int r = 0; r < tys; r++)
        for (int c = 0; c < txs; c++) {
            int t = slot + r * txs + c;
            /* Même rempart que sur le chemin composé : `tilemap_set` ne borne
               rien, une case hors cadre repeindrait le décor (ou la rangée
               suivante, la carte faisant 32 cases de large). */
            if (!text_tile_in_clip(tx + c, ty + r)) continue;
            tilemap_set(g_text_layer, tx + c, ty + r, t);
            tilemap_set_palette(g_text_layer, tx + c, ty + r, g_pal_bank_bg);
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
       grille. Les chemins composés (proportionnel, bande de sprites, zone à
       fond) gardent le pixel. */
    if (!text_is_composited()) off &= ~7;
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
        /* Coupe VERTICALE : une ligne qui ne tient pas entière arrête la mise
           en page. Rien ne la suit — les lignes d'après ne tiendraient pas
           davantage, et continuer à mesurer gonflerait la surface préparée. */
        if (y + line > g_clip_y + g_clip_h) break;
        int end, next, lw;
        text_scan_line(s, i, len, wrap_px, &end, &next, &lw);
        int x = ox + text_align_off(align, wrap_px, lw);
        while (i < end) {
            /* Correspondance au plus long : une ligature avale plusieurs
               codepoints d'un coup. */
            int used, gi = text_find(s, i, len, &used);
            if (!measure && gi >= 0 && text_glyph_fits(gi, x, y)
                    && (n < 0 || i < n)) {
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
                } else if (text_is_composited()) {
                    /* Compose (pixel) plutôt que poser une tuile : police
                       proportionnelle, bloc PRIVÉ (bande de sprites, `g_blit_h`),
                       ou CETTE zone a un fond (`g_ui_fill_bg`) — dans tous ces
                       cas poser une tuile serait faux ou impossible. Les glyphes
                       se lisent en ROM, rien de plus à charger. */
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
    /* Étendue RENDUE, donc bornée par le cadre : `max_x` suit la plume, qui
       continue d'avancer alors que `text_glyph_fits` a déjà coupé. Sans ce
       plafond, la surface préparée couvrirait ce qui n'est pas écrit. */
    if (max_x > g_clip_x + g_clip_w) max_x = g_clip_x + g_clip_w;
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
                              int tx, int ty, int wrap, int n, int align,
                              int box_h) {
    if (g_text_layer < 0 || !g_font) return;
    blit_use_bg_surface();
    if (text_is_composited()) {
        /* Préparer AVANT de composer : la composition ne pose que de l'encre,
           elle n'efface pas ce qui était là. La zone préparée doit couvrir le
           texte ALIGNÉ, d'où le même `align` dans les deux passes. Zone à
           fond, on prépare même en police mono (le texte s'y compose).

           `box_h` > 0 = la zone a une boîte AUTEUR connue (cf.
           `text_render_region_cp`) : on prépare TOUTE la boîte — largeur ET
           hauteur — plutôt que la seule étendue de CE texte. Sans ça, un
           texte plus court que le précédent (ligne de dialogue suivante)
           laisserait l'encre de l'ancien rendu hors de la nouvelle étendue
           mesurée : la zone semblerait mal peinte là où elle n'a plus de
           texte. `box_h == 0` (écriture LIBRE, `text_draw`) garde l'ancien
           comportement : sans boîte auteure à reboucher, rien à
           sur-préparer. */
        int w = 1, h = 1;
        text_layout(s, slen, tx, ty, wrap, n, 1, align, &w, &h);
        if (box_h > 0) {
            if (wrap > 0) w = wrap;
            h = box_h;
        }
        text_surf_prepare(tx, ty, w, h);
    }
    text_layout(s, slen, tx, ty, wrap, n, 0, align, 0, 0);
}

static void text_render_cp(const unsigned short *s, int slen,
                           int tx, int ty, int wrap, int n) {
    /* Écriture LIBRE : le seul cadre qui ait un sens est l'écran. `draw` ne
       renvoie pas à la ligne tout seul, donc sans lui une ligne trop longue
       continuerait dans la tilemap et repeindrait la rangée suivante. */
    text_clip_screen();
    /* Écriture LIBRE : aucune zone où déclarer une couleur, donc l'encre
       d'origine de la police — la variante 0. */
    g_var_cur = 0;
    g_zone_ink = 0;
    text_render_cp_al(s, slen, tx, ty, wrap, n, TEXT_ALIGN_LEFT, 0);
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
/* Position d'un acteur, fournie par le code généré. `gba_engine.h` ignore la
   structure `Actor` — elle vit dans actor_api_static.h, qui inclut celui-ci et
   non l'inverse. Un pointeur de fonction évite d'inverser cette dépendance
   pour deux entiers. */
static int (*g_actor_x_fn)(int) = 0;
static int (*g_actor_y_fn)(int) = 0;

/* Caméra — définies dans le main.c généré, déjà déclarées par
   actor_api_static.h pour l'API `camera.*`. Deux entiers, pas un type généré :
   le détour par pointeur de fonction qu'imposent les acteurs ne se justifie
   pas ici. */
extern int cam_x, cam_y;

/* Origine ÉCRAN d'une zone. C'est le seul endroit qui lit l'ancrage, et donc
   le seul à savoir qu'une zone MONDE est posée en coordonnées de niveau : la
   caméra la ramène à l'écran, exactement comme pour un acteur.

   Cible BG, la position retombe sur la grille : une zone ancrée monde se
   déplace par pas de 8 px. C'est aussi pourquoi un ancrage sur ACTEUR impose
   l'OBJ (`forced_target`) — un acteur, lui, bouge au pixel. */
static void text_region_origin(const UIRegionInfo *R, int *ox, int *oy) {
    *ox = R->x; *oy = R->y;
    if (R->anchor == 1) { *ox -= cam_x; *oy -= cam_y; }
    else if (R->anchor == 2 && R->actor >= 0 && g_actor_x_fn) {
        *ox += g_actor_x_fn(R->actor);
        *oy += g_actor_y_fn(R->actor);
    }
}

/* ── Tête de lecture ──────────────────────────────────────────────
   Un texte qui porte du TEMPO (`[speed=n]`, `[pause=n]`) ne s'affiche pas d'un
   coup : il se lit. La tête vit par ZONE et non par appel — d'où le tempo
   ignoré par `text_draw`, un couple (x, y) n'étant pas nommable.

   Sans marqueur de tempo, le texte s'affiche entier et tout de suite : ne pas
   en mettre est une décision de l'auteur, pas un oubli à compenser.

   Plafond fixe : le moteur ne connaît pas la taille de `g_ui_regions`, qui est
   générée. Une zone au-delà s'affiche d'un coup. */
#define TEXT_READ_MAX 8

typedef struct TextRead {
    short id;        /* texte en cours, -1 = aucune lecture */
    short n;         /* caractères révélés */
    short len;       /* longueur matérialisée, borne de la lecture */
    short wait;      /* frames restantes avant le prochain caractère */
    short speed;     /* frames par caractère, posé par [speed=n] */
    unsigned char active;
    /* Origine ÉCRAN du dernier rendu. Sert à l'ancrage MONDE : effacer le texte
       là où il EST avant de le reposer ailleurs, la caméra ayant bougé entre
       les deux. Inutilisé en ancrage écran, où l'origine ne change pas. */
    short sx, sy;
    /* Dernière visibilité EFFECTIVE connue de cette zone (cf. `ui_element_
       is_visible`) — posée par `text_draw_in` et par le balayage de
       `ui_element_show`. Sert à ne redessiner/effacer QUE ce qui a
       réellement changé quand un panel ancêtre bascule. */
    unsigned char last_visible;
} TextRead;

static TextRead g_reads[TEXT_READ_MAX];
static int      g_reads_init = 0;

/* ── Visibilité des éléments d'interface ────────────────────────────
   État MUTABLE, propre bit de chaque élément — le seul que `ui_element_show`
   écrit. La visibilité EFFECTIVE (cf. `ui_element_is_visible`) n'est jamais
   stockée : elle se recalcule à la lecture en remontant `g_ui_elements[].
   parent`, jusqu'à la racine. */
static unsigned char g_ui_element_vis[UI_ELEMENT_MAX];

void ui_elements_reset(void) {
    int n = g_ui_element_count < UI_ELEMENT_MAX ? g_ui_element_count : UI_ELEMENT_MAX;
    for (int i = 0; i < n; i++) g_ui_element_vis[i] = g_ui_elements[i].visible;
}

int ui_element_is_visible(int idx) {
    /* `guard` borne la remontée : une chaîne de parents corrompue (donnée
       externe, jamais censée arriver) ne doit pas tourner en boucle infinie
       sur du matériel sans protection mémoire. */
    for (int guard = 0; idx >= 0 && idx < UI_ELEMENT_MAX && guard < UI_ELEMENT_MAX; guard++) {
        if (!g_ui_element_vis[idx]) return 0;
        idx = (idx < g_ui_element_count) ? g_ui_elements[idx].parent : -1;
    }
    return 1;
}

/* Vide le rectangle d'une zone posée à une origine DONNÉE.

   L'origine est un paramètre plutôt que `R->x`/`R->y` : après un déplacement de
   caméra, une zone ancrée monde doit s'effacer là où le texte EST, sinon on
   gomme du décor et on laisse une traînée. */
static void text_clear_region_at(const UIRegionInfo *R, int r, int ox, int oy) {
    /* Fond de la zone le temps de l'effacement : sans lui, `text_clear`
       remettrait du transparent au lieu de la couleur du panel — ou, sous un
       panel nine-slice/background, plutôt que le cadre en dessous. */
    int w = R->w >> 3, h = R->h >> 3;
    g_ui_fill_bg = R->bg_fill;
    g_ui_backdrop = text_region_backdrop(r);
    text_clear(ox >> 3, oy >> 3, w > 0 ? w : 1, h > 0 ? h : 1);
    g_ui_fill_bg = -1;
    g_ui_backdrop = 0;
}

static void text_render_region_cp(const unsigned short *s, int slen,
                                  int r, int n) {
    const UIRegionInfo *R = &g_ui_regions[r];
    if (R->font != 255) text_set_font(R->font);
    if (!g_font) return;
    /* Variante de couleur DE CE SLOT — résolue après `text_set_font`, qui vient
       de poser le sous-ensemble dont dépend la correspondance couleur→variante. */
    g_var_cur = text_var_for(R->color);
    /* Chemin composé : la couleur du slot devient l'encre par défaut. Une
       police mono, elle, la reçoit par sa variante — d'où les deux lignes. */
    g_zone_ink = (g_var_cur || !g_font_sub) ? R->color : 0;
    int ox, oy;
    text_region_origin(R, &ox, &oy);
    /* Retenu AVANT de dessiner, pour les deux cibles : une fois la caméra ou
       l'acteur déplacé, R->x/R->y ne diront plus où le texte est. C'est ce qui
       permet à `text_update` d'effacer au bon endroit. */
    if (r >= 0 && r < TEXT_READ_MAX) {
        g_reads[r].sx = (short)ox; g_reads[r].sy = (short)oy;
    }
    if (R->target == 1) { text_render_obj(s, slen, R, n); return; }
    if (g_text_layer < 0) return;
    /* Le cadre EST la zone — ce que l'auteur a dessiné, et ce contre quoi
       l'aperçu de l'éditeur mesure le débordement. Il suit l'origine, donc une
       zone ancrée monde se coupe sur elle-même, pas sur sa position de départ. */
    text_clip_set(ox, oy, R->w, R->h);
    /* Fond de la zone le temps du rendu : la surface se compose sur cette
       couleur — ou, sous un panel nine-slice/background, sur ces tuiles
       (cf. text_surf_prepare/text_clear) — puis on remet les deux à vide. */
    g_ui_fill_bg = R->bg_fill;
    g_ui_backdrop = text_region_backdrop(r);
    text_render_cp_al(s, slen, ox >> 3, oy >> 3, R->w >> 3, n, R->align, R->h >> 3);
    g_ui_fill_bg = -1;
    g_ui_backdrop = 0;
}

static void text_render_region(int id, int r, int n) {
    const unsigned short *s; const TextEvent *e; int ne;
    int len = text_materialize(id, &s, &e, &ne);
    /* La piste accompagne le texte le temps du rendu : elle dit quels glyphes
       sont animés. */
    g_ev = e; g_nev = ne;
    text_render_region_cp(s, len, r, n);
    g_ev = 0; g_nev = 0;
}


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

/* Ferme TOUTES les têtes de lecture — posé par `scene_init`, au même titre que
   `bg_maps_clear` ou `oam_hide_all`.

   Sans lui, une zone lue dans la scène PRÉCÉDENTE garde son slot ouvert
   (`id >= 0`), et `text_update` — qui balaie les slots sans savoir à quelle
   mise en page ils appartiennent — continue de la rendre dans la nouvelle
   scène : le texte de l'écran d'avant réapparaît, et son tempo se rejoue.
   Les index de zone sont PROJET-GLOBAUX (g_ui_regions est une table plate),
   donc le slot reste parfaitement « valide » — rien ne signalait l'erreur. */
void text_read_reset_all(void) {
    for (int k = 0; k < TEXT_READ_MAX; k++) { g_reads[k].id = -1; g_reads[k].active = 0; }
    g_reads_init = 1;
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
    /* Visible ? Si non, rien ne se pose à l'écran — mais le CONTENU est
       quand même retenu (au moins pour les TEXT_READ_MAX premières zones,
       cf. `ui_element_show`) : c'est ce qui permet à `self:show()` de
       révéler exactement ce qui aurait dû s'afficher, sans qu'un script
       ait à rappeler `text.draw_in` après coup. */
    int elem = (r >= 0) ? g_ui_regions[r].elem : -1;
    int vis  = ui_element_is_visible(elem);
    if (r >= 0 && r < TEXT_READ_MAX) {
        g_reads[r].id = (short)id;
        g_reads[r].last_visible = (unsigned char)vis;
    }
    if (!vis) return;
    if (r >= TEXT_READ_MAX || !text_has_tempo(e, ne)) {
        text_render_region(id, r, -1);
        return;
    }
    /* Lecture : la zone part vide et se remplit. La mise en page, elle, se fait
       sur le texte ENTIER (cf. text_layout) — révéler n'est qu'un masque, donc
       aucune ligne ne saute pendant que le texte s'écrit. */
    TextRead *R = &g_reads[r];
    R->n = 0; R->len = (short)len;
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
        const UIRegionInfo *RI = &g_ui_regions[r];
        /* Caché (soi-même ou par un ancêtre) : la lecture et le suivi d'ancre
           sont en PAUSE, pas annulés — `ui_element_show` reprend exactement là
           où c'était resté, via `text_hide_region_visual`/le balayage qui
           l'accompagne. Rien à effacer ici, c'est déjà fait (ou jamais posé). */
        if (!ui_element_is_visible(RI->elem)) continue;
        const unsigned short *s; const TextEvent *e; int ne;
        text_materialize(R->id, &s, &e, &ne);
        /* Une zone ANCRÉE (monde ou acteur) suit son ancre. Redessin seulement
           quand l'ancre a bougé, donc une bulle immobile ne coûte rien.
           Cible BG, effacer d'abord à l'ANCIENNE origine : les tuiles déjà
           écrites ne s'en vont pas seules. En OBJ, reposer les sprites suffit. */
        int ox, oy;
        text_region_origin(RI, &ox, &oy);
        int moved = RI->anchor != 0 && (ox != R->sx || oy != R->sy);
        if (moved && RI->target == 0)
            text_clear_region_at(RI, r, R->sx, R->sy);
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
        } else if (RI->anim > 0 || moved) {
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

/* Injecté par le code généré au démarrage — cf. `g_actor_x_fn`. */
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

    /* Origine ÉCRAN — acteur suivi ou caméra, selon l'ancrage. */
    int ox, oy;
    text_region_origin(R, &ox, &oy);

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

    /* Les glyphes réservés sont CAPTURÉS plutôt que dessinés dans la bande :
       ils reçoivent leur propre sprite juste après (cf. `g_cap_max`). */
    g_cap_max = R->anim > TEXT_ANIM_MAX ? TEXT_ANIM_MAX : R->anim;
    g_cap_n   = 0;
    /* Le cadre est la BANDE, pas l'écran : une bulle qui suit son acteur en
       sort par moments, et c'est l'OAM qui s'en occupe. Le poser explicitement
       évite aussi d'hériter du cadre du rendu précédent. */
    text_clip_set(ox, oy, R->w, rows * 8);
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
                                   | (R->priority << 10) | (g_pal_bank_obj << 12);
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
                               | (R->priority << 10) | (g_pal_bank_obj << 12);
        slot++;
    }

    /* Masquer la réserve non utilisée : un texte plus court que le budget
       laisserait sinon les glyphes de l'appel précédent à l'écran. */
    for (int k = captured; k < R->anim; k++)
        shadow_oam[slot++].attr0 = 0x0200;
    (void)strip_slots;
}

/* Efface VISUELLEMENT une zone (bande OAM ou tuiles BG) SANS toucher à la
   lecture — contrairement à `text_clear_in`. C'est ce qui permet à
   `ui_element_show` de cacher puis remontrer la même zone : son contenu
   (`g_reads[r].id`) reste connu pendant qu'elle est invisible. */
static void text_hide_region_visual(int r) {
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
    /* Fond de la zone le temps de l'effacement : sans lui, `text_clear`
       remettrait du transparent au lieu de la couleur du panel — même garde
       que `text_render_region_cp`. */
    int ox, oy;
    text_region_origin(R, &ox, &oy);
    text_clear_region_at(R, r, ox, oy);
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
       seule après avoir été effacée. Contrairement à `ui_element_show(idx,
       0)`, on ne cherche PAS à se souvenir du contenu : l'auteur a demandé
       à vider, pas à cacher temporairement. */
    text_read_reset(r);
    text_hide_region_visual(r);
}

/* self:show() / self:hide() — bascule le bit PROPRE de l'élément, puis
   resynchronise les zones de texte dont la visibilité EFFECTIVE en dépend
   (cf. `ui_element_sync_text`). Les images n'ont rien à resynchroniser ici :
   `ui_image_update` consulte `ui_element_is_visible` à CHAQUE frame, la
   cascade s'y résout donc d'elle-même, avec au plus une frame de latence —
   comme `ui_image_play` avant elle. */
static void ui_element_sync_text(void) {
    int n = g_ui_region_count < TEXT_READ_MAX ? g_ui_region_count : TEXT_READ_MAX;
    for (int r = 0; r < n; r++) {
        const UIRegionInfo *R = &g_ui_regions[r];
        int vis = ui_element_is_visible(R->elem);
        if (vis == g_reads[r].last_visible) continue;   /* pas concernée */
        g_reads[r].last_visible = (unsigned char)vis;
        if (vis) {
            /* Rien n'a jamais été dessiné ici (id encore -1) : aucune
               reveal à faire, `text_draw_in` s'en chargera le jour où un
               script (ou scene_init) y écrit quelque chose. */
            if (g_reads[r].id >= 0)
                text_render_region(g_reads[r].id, r,
                                   g_reads[r].active ? g_reads[r].n : -1);
        } else {
            text_hide_region_visual(r);
        }
    }
}

void ui_element_show(int idx, int on) {
    if (idx < 0 || idx >= UI_ELEMENT_MAX) return;
    g_ui_element_vis[idx] = on ? 1 : 0;
    ui_element_sync_text();
}

/* ── Listes : la navigation, et rien d'autre (ROADMAP v0.22) ──────
   `l` est un index de `g_ui_lists`, résolu au build depuis le nom du panneau.
   Hors bornes, tout rend 0 et n'écrit rien : `l` peut venir d'une variable. */
static int ui_list_ok(int l) { return l >= 0 && l < g_ui_list_count; }

int ui_list_count(int l) { return ui_list_ok(l) ? g_ui_list_total[l] : 0; }

void ui_list_set_count(int l, int n) {
    if (!ui_list_ok(l)) return;
    if (n < 0) n = 0;
    g_ui_list_total[l] = n;
    /* Une liste qui rétrécit ne doit pas garder un curseur au-delà de sa fin —
       c'est le cas d'un inventaire dont on jette le dernier objet. */
    if (g_ui_list_index[l] > n) g_ui_list_index[l] = n;
    if (g_ui_list_index[l] < 1 && n > 0) g_ui_list_index[l] = 1;
    if (g_ui_list_first[l] > n) g_ui_list_first[l] = n > 0 ? n : 1;
    if (g_ui_list_first[l] < 1) g_ui_list_first[l] = 1;
}

int ui_list_index(int l) { return ui_list_ok(l) ? g_ui_list_index[l] : 0; }

/* Repose la fenêtre pour que l'item courant y soit — la seule chose que le
   défilement fait, et il la fait À LA LIGNE : le texte reste sur la grille de
   tuiles, et rien n'est redessiné qui n'ait changé. */
static void ui_list_reveal(int l) {
    int rows = g_ui_lists[l].rows;
    if (rows < 1) rows = 1;
    if (g_ui_list_index[l] < g_ui_list_first[l])
        g_ui_list_first[l] = g_ui_list_index[l];
    if (g_ui_list_index[l] > g_ui_list_first[l] + rows - 1)
        g_ui_list_first[l] = g_ui_list_index[l] - rows + 1;
    if (g_ui_list_first[l] < 1) g_ui_list_first[l] = 1;
}

void ui_list_set_index(int l, int i) {
    if (!ui_list_ok(l)) return;
    int n = g_ui_list_total[l];
    if (n <= 0) { g_ui_list_index[l] = 0; return; }
    if (i < 1) i = 1;
    if (i > n) i = n;
    g_ui_list_index[l] = i;
    ui_list_reveal(l);
}

int ui_list_first(int l) { return ui_list_ok(l) ? g_ui_list_first[l] : 0; }

/* La zone de texte qui porte la rangée `r` (1 = la première visible). C'est ce
   que le script passe à `text.draw_in` pour écrire le contenu de l'item. */
int ui_list_row(int l, int r) {
    if (!ui_list_ok(l)) return -1;
    if (r < 1 || r > g_ui_lists[l].rows) return -1;
    return g_ui_list_rows[g_ui_lists[l].row0 + r - 1];
}

/* Un pas dans la liste, répétition comprise. Le compteur est NÉGATIF pendant le
   délai initial et positif ensuite : un seul entier porte les deux cadences,
   sans drapeau à côté qui pourrait mentir sur l'état. */
static void ui_list_step(int l, int dir) {
    int n = g_ui_list_total[l];
    if (n <= 0) return;
    int i = g_ui_list_index[l] + dir;
    if (i < 1)  i = g_ui_lists[l].wrap ? n : 1;
    if (i > n)  i = g_ui_lists[l].wrap ? 1 : n;
    g_ui_list_index[l] = i;
    ui_list_reveal(l);
}

void ui_list_tick(void) {
    for (int l = 0; l < g_ui_list_count; l++) {
        if (g_ui_list_total[l] <= 0) { g_ui_list_timer[l] = 0; continue; }
        /* Les constantes de libgba, et non les `BTN_*` du script : ce sont
           les MÊMES bits du registre de touches, mais `actor_types_static.h`
           n'est pas visible d'ici — le moteur n'est inclus que par main.c. */
        int neg, pos;
        if (g_ui_lists[l].axis) { neg = KEY_LEFT; pos = KEY_RIGHT; }
        else                    { neg = KEY_UP;   pos = KEY_DOWN;  }
        int dir = ((_g_keys_held & (u32)pos) ? 1 : 0)
                - ((_g_keys_held & (u32)neg) ? 1 : 0);
        if (dir == 0) { g_ui_list_timer[l] = 0; continue; }
        if (g_ui_list_timer[l] == 0) {
            /* Premier appui : on bouge tout de suite, puis on attend le délai. */
            ui_list_step(l, dir);
            g_ui_list_timer[l] = -(int)g_ui_lists[l].rep_delay - 1;
            continue;
        }
        if (g_ui_list_timer[l] < 0) {
            g_ui_list_timer[l]++;
            if (g_ui_list_timer[l] == 0) g_ui_list_timer[l] = 1;   /* délai écoulé */
            continue;
        }
        g_ui_list_timer[l]++;
        if (g_ui_list_timer[l] > (int)g_ui_lists[l].rep_rate) {
            ui_list_step(l, dir);
            g_ui_list_timer[l] = 1;
        }
    }
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

/* ── Images d'interface ───────────────────────────────────────────
   Le pendant, pour un sprite, de ce que `text_draw_in` fait pour du texte : la
   géométrie est AUTHORÉE (`g_ui_images`), le script ne change que l'état.

   Deux chemins de rendu, choisis par la CIBLE dérivée du root — le même
   partage que pour le texte :

   • OBJ — un slot OAM, reposé à chaque frame. Les tuiles sont déjà en VRAM OBJ
     (le sprite y est chargé au démarrage comme pour un acteur), donc changer de
     frame ne coûte qu'un index dans attr2 : rien à recopier.

   • BG — la frame est ÉCRITE dans la tilemap. Les tuiles vivent alors dans le
     charblock d'UI, recopiées là par `scene_init` (toutes les frames, cf.
     `ui_image_set_bg_base`), et changer de frame réécrit `w/8 × h/8` entrées.
     Zéro OAM, mais une origine calée sur la grille de 8 px.

   L'état RAM est un tableau à plafond fixe, comme les têtes de lecture du
   texte : le moteur ne connaît pas la taille de `g_ui_images`, qui est générée.
   Au-delà, l'image ne s'anime pas — dégradation visible, jamais un rendu faux. */
#define UI_IMAGE_MAX 16

typedef struct UIImageState {
    unsigned char state;    /* index d'AnimState courant */
    unsigned char frame;    /* index ABSOLU de frame dans le sheet */
    unsigned char timer;    /* ticks depuis la dernière frame */
    unsigned char playing;
    /* Plus de bit `visible` ici : la visibilité vient de `g_ui_element_vis`
       via `I->elem` (cf. `ui_element_is_visible`), une seule fois pour les
       trois types d'élément — ce champ dupliquait ce que `self:hide()`
       écrit maintenant ailleurs. */
    short         bg_base;  /* cible BG : 1re tuile dans le charblock d'UI */
    short         sx, sy;   /* dernière origine écran dessinée (cible BG) */
    unsigned char drawn;    /* 1 = des tuiles sont posées à (sx, sy) */
    unsigned char last;     /* dernière frame POSÉE — évite de réécrire pour rien */
    unsigned char bank;     /* banque de palette, posée par scene_init */
} UIImageState;

static UIImageState g_ui_img[UI_IMAGE_MAX];

void ui_image_set_bank(int img, int bank) {
    if (img < 0 || img >= UI_IMAGE_MAX) return;
    g_ui_img[img].bank = (unsigned char)((bank >= 0 && bank < 16) ? bank : 0);
    g_ui_img[img].last = 255;    /* la couleur change : reposer la carte */
}

/* 1re frame et longueur de la séquence d'un état, direction 0 (omni) ou, à
   défaut, la première déclarée. Reproduit le repli de la boucle des acteurs :
   les deux lisent la MÊME table, elles doivent la lire pareil. */
static void ui_image_seq(const UIImageInfo *I, int state, int *fs, int *fc) {
    *fs = 0; *fc = 1;
    if (!I->dirs || !I->state_start || state < 0 || state >= I->n_states) return;
    int b = I->state_start[state];
    int fb = -1, fbc = 1;
    for (int e = b; I->dirs[e][0] != 255; e++) {
        if (I->dirs[e][0] == 0) { fb = I->dirs[e][1]; fbc = I->dirs[e][2]; break; }
        if (fb < 0) { fb = I->dirs[e][1]; fbc = I->dirs[e][2]; }
    }
    if (fb >= 0) { *fs = fb; *fc = fbc; }
}

void ui_images_reset(void) {
    for (int i = 0; i < UI_IMAGE_MAX; i++) {
        const UIImageInfo *I = (i < g_ui_image_count) ? &g_ui_images[i] : 0;
        int fs = 0, fc = 1;
        int st = I ? I->state0 : 0;
        if (I) ui_image_seq(I, st, &fs, &fc);
        g_ui_img[i].state   = (unsigned char)st;
        g_ui_img[i].frame   = (unsigned char)fs;
        g_ui_img[i].timer   = 0;
        g_ui_img[i].playing = I ? I->playing : 0;
        g_ui_img[i].bg_base = 0;
        g_ui_img[i].bank = 0;
        g_ui_img[i].sx = g_ui_img[i].sy = 0;
        g_ui_img[i].drawn = 0;
        /* 255 et non `fs` : « aucune frame posée ». Sans ça, revenir dans une
           scène retrouverait `last == frame` et sauterait le premier dessin. */
        g_ui_img[i].last = 255;
    }
}

void ui_image_set_bg_base(int img, int tile) {
    if (img < 0 || img >= UI_IMAGE_MAX) return;
    g_ui_img[img].bg_base = (short)tile;
    g_ui_img[img].last = 255;     /* la géographie change : tout est à reposer */
}

void ui_image_set_state(int img, int state) {
    if (img < 0 || img >= UI_IMAGE_MAX || img >= g_ui_image_count) return;
    const UIImageInfo *I = &g_ui_images[img];
    if (state < 0 || state >= I->n_states || g_ui_img[img].state == state) return;
    int fs = 0, fc = 1;
    ui_image_seq(I, state, &fs, &fc);
    g_ui_img[img].state = (unsigned char)state;
    g_ui_img[img].frame = (unsigned char)fs;   /* un état commence à sa 1re frame */
    g_ui_img[img].timer = 0;
}

void ui_image_play(int img, int on) {
    if (img >= 0 && img < UI_IMAGE_MAX) g_ui_img[img].playing = on ? 1 : 0;
}

int ui_image_state(int img) {
    return (img >= 0 && img < UI_IMAGE_MAX) ? g_ui_img[img].state : 0;
}

/* Origine ÉCRAN — même règle que `text_region_origin`, et pour la même raison :
   monde = décalé de la caméra, acteur = suivi au pixel. */
static void ui_image_origin(const UIImageInfo *I, int *ox, int *oy) {
    *ox = I->x; *oy = I->y;
    if (I->anchor == 1) { *ox -= cam_x; *oy -= cam_y; }
    else if (I->anchor == 2 && I->actor >= 0 && g_actor_x_fn) {
        *ox += g_actor_x_fn(I->actor);
        *oy += g_actor_y_fn(I->actor);
    }
}

/* Efface les tuiles d'une image BG à une origine donnée. Nécessaire avant tout
   déplacement : la tilemap ne s'efface pas seule, et une image ancrée au monde
   laisserait sa traînée derrière elle. */
static void ui_image_clear_bg(const UIImageInfo *I, int sx, int sy) {
    if (g_text_layer < 0) return;
    int tw = (I->w + 7) >> 3, th = (I->h + 7) >> 3;
    int tx = sx >> 3, ty = sy >> 3;
    for (int r = 0; r < th; r++)
        for (int c = 0; c < tw; c++)
            tilemap_set(g_text_layer, tx + c, ty + r, 0);
}

static void ui_image_draw_bg(const UIImageInfo *I, UIImageState *S, int sx, int sy) {
    if (g_text_layer < 0) return;
    int tw = (I->w + 7) >> 3, th = (I->h + 7) >> 3;
    int tx = sx >> 3, ty = sy >> 3;
    /* Les tuiles d'une frame se suivent dans l'ordre du sheet, ligne par ligne
       — c'est le découpage que `grit` produit et que l'OBJ lit en mode 1D. */
    int t0 = S->bg_base + S->frame * I->tiles_per_frame;
    for (int r = 0; r < th; r++) {
        for (int c = 0; c < tw; c++) {
            tilemap_set(g_text_layer, tx + c, ty + r, t0 + r * tw + c);
            tilemap_set_palette(g_text_layer, tx + c, ty + r, S->bank);
        }
    }
}

/* Forme/taille OAM d'une frame w×h. Les couples légaux sont ceux de
   VALID_FRAME_SIZES (models/sprite.py), que le Sprite Editor impose déjà : une
   frame est donc toujours affichable, et le défaut ne sert qu'à une donnée
   produite autrement. */
static int ui_image_shape(int w, int h) {
    if (w == h) return 0;            /* carré */
    return (w > h) ? 1 : 2;          /* large / haut */
}

static int ui_image_size(int w, int h) {
    int m = (w > h) ? w : h;
    return m >= 64 ? 3 : m >= 32 ? 2 : m >= 16 ? 1 : 0;
}

void ui_image_update(void) {
    int n = g_ui_image_count < UI_IMAGE_MAX ? g_ui_image_count : UI_IMAGE_MAX;
    for (int i = 0; i < n; i++) {
        const UIImageInfo *I = &g_ui_images[i];
        UIImageState *S = &g_ui_img[i];
        if (!I->dirs) continue;              /* image sans sprite : rien à poser */

        /* 1. Tick d'animation — la même arithmétique que la boucle des acteurs.
              `fc > 1` : un état d'une seule frame ne consomme pas de timer. */
        int fs = 0, fc = 1;
        ui_image_seq(I, S->state, &fs, &fc);
        if (S->playing && fc > 1 && I->state_speed) {
            /* `speed` surcharge la vitesse de l'état ; 0 = celle du sprite. */
            int sp = I->speed ? I->speed : I->state_speed[S->state];
            if (++S->timer >= sp) {
                S->timer = 0;
                int fi = S->frame - fs;
                if (I->state_loop && I->state_loop[S->state])
                    S->frame = (unsigned char)(fs + (fi + 1) % fc);
                else if (fi < fc - 1)
                    S->frame = (unsigned char)(fs + fi + 1);
            }
        }

        /* Visibilité EFFECTIVE (soi-même ET tous les ancêtres) — consultée
           CHAQUE frame, donc une image dont le panel parent bascule suit
           sans qu'aucune propagation n'ait eu à s'écrire au moment du
           `self:hide()`. Au plus une frame de latence, comme `ui_image_
           play` avant elle. */
        int visible = ui_element_is_visible(I->elem);

        int sx, sy;
        ui_image_origin(I, &sx, &sy);

        if (I->target == 0) {
            /* Cible BG : n'écrire que si quelque chose a CHANGÉ. Une icône de
               HUD figée ne coûte alors pas une seule écriture par frame. */
            if (!visible) {
                if (S->drawn) { ui_image_clear_bg(I, S->sx, S->sy); S->drawn = 0; }
                continue;
            }
            sx -= sx % 8;      /* la tilemap ne se pose pas entre deux tuiles */
            sy -= sy % 8;
            int moved = S->drawn && (sx != S->sx || sy != S->sy);
            if (moved) ui_image_clear_bg(I, S->sx, S->sy);
            if (moved || !S->drawn || S->last != S->frame) {
                S->sx = (short)sx; S->sy = (short)sy;
                ui_image_draw_bg(I, S, sx, sy);
                S->drawn = 1;
                S->last = S->frame;
            }
        } else {
            /* Cible OBJ : un slot PAR CASE du pavage (1×1 pour une image),
               reposés à chaque frame. `g_obj_oam_base` est la base que
               scene_init réserve à l'interface — la même que la bande de texte,
               dont l'allocation chaîne les deux.

               Tous les slots lisent la MÊME frame : le fond d'un panneau est un
               motif répété, pas N animations indépendantes. Une case décalée
               d'une frame donnerait une vague, ce que personne n'a demandé. */
            if (g_obj_oam_base < 0) continue;
            int cols = I->cols ? I->cols : 1;
            int rows = I->rows ? I->rows : 1;
            u16 ti = (u16)(I->tile_base + S->frame * I->tiles_per_frame);
            for (int cy = 0; cy < rows; cy++) {
                for (int cx = 0; cx < cols; cx++) {
                    int slot = g_obj_oam_base + I->oam_rel + cy * cols + cx;
                    if (slot < 0 || slot >= 128) continue;
                    if (!visible) { shadow_oam[slot].attr0 = 0x0200; continue; }
                    int px = sx + cx * I->w, py = sy + cy * I->h;
                    shadow_oam[slot].attr0 = (u16)((py & 0xFF)
                                           | (ui_image_shape(I->w, I->h) << 14));
                    shadow_oam[slot].attr1 = (u16)((px & 0x1FF)
                                           | (ui_image_size(I->w, I->h) << 14));
                    shadow_oam[slot].attr2 = (u16)((ti & 0x3FF)
                                           | ((I->priority & 3) << 10)
                                           | ((S->bank & 15) << 12));
                }
            }
        }
    }
}

/* ── Blending ────────────────────────────────────────────────────── */
/* BLDCNT : bits 0-5 = cibles du dessus (BG0-3, OBJ, backdrop),
            bits 6-7 = mode, bits 8-13 = cibles du dessous.
   BLDALPHA : bits 0-4 = eva (dessus), bits 8-12 = evb (dessous), 0-16.
   BLDY : bits 0-4 = evy, 0-16. Les trois registres sont shadowés — BLDY est
   write-only et n'avait pas de lecteur jusqu'à ce qu'une transition de scène
   ait besoin de RENDRE son intensité à la scène après le fondu. */

static u16 g_bldcnt_sh, g_bldalpha_sh, g_bldy_sh;
static int g_trans_owns;   /* 1 = une transition possède les registres */

/* Le SEUL endroit qui écrive les trois registres de mélange. Pendant une
   transition, le fondu les possède : les shadows continuent d'enregistrer le
   réglage authoré de la scène (y compris celui que scene_init pose derrière
   l'écran éteint), mais rien ne descend au matériel avant transition_end().
   Sans ce point unique, le display_reset() de scene_init rallumerait l'écran
   au milieu du fondu. */
static void blend_flush(void) {
    if (g_trans_owns) return;
    REG_BLDCNT   = g_bldcnt_sh;
    REG_BLDALPHA = g_bldalpha_sh;
    REG_BLDY     = g_bldy_sh;
}

static void blend_reset(void) {
    g_bldcnt_sh   = 0;
    g_bldalpha_sh = 0;
    g_bldy_sh     = 0;
    blend_flush();
}

static void bld_target_set(int side, int bit, int on) {
    u16 m = (u16)(1 << (bit + ((side & 1) ? 8 : 0)));
    if (on) g_bldcnt_sh |=  m;
    else    g_bldcnt_sh &= (u16)~m;
    blend_flush();
}

void blend_set_mode(int mode) {
    g_bldcnt_sh = (u16)((g_bldcnt_sh & ~0x00C0) | ((mode & 3) << 6));
    blend_flush();
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
    blend_flush();
}

void blend_set_fade(int evy) {
    g_bldy_sh = (u16)ev_clamp(evy);
    blend_flush();
}

/* ── Transition de scène ─────────────────────────────────────────── */

void transition_begin(int mode) {
    g_trans_owns = 1;
    /* Tout l'écran est première cible (BG0-3, OBJ, backdrop = bits 0-5).
       Oublier le backdrop laisserait les zones vides allumées pendant que le
       reste s'éteint — la panne classique du fondu, et justement ce que
       l'écran montre pendant que scene_init recharge ses layers. */
    REG_BLDCNT = (u16)(0x003F | ((mode & 3) << 6));
}

/* Intensité du fondu, 0-16. Distincte de blend_set_fade() : celle-ci ne touche
   pas au réglage de la scène, qui doit revenir intact à la fin. */
void transition_fade(int evy) {
    REG_BLDY = (u16)ev_clamp(evy);
}

/* Rend les registres au réglage de la scène. Sans effet si aucune transition
   n'était en cours — l'appeler est toujours sûr. */
void transition_end(void) {
    g_trans_owns = 0;
    blend_flush();
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
