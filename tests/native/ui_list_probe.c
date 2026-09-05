/* Sonde de NAVIGATION — fait parcourir une liste au vrai `ui_list_tick`.

   Même intention que `text_layout_probe.c` : ce que la liste calcule est de
   l'arithmétique entière qui ne se voit qu'une fois la ROM sur une console. Il
   n'y a pas de réimplémentation Python à comparer ici — c'est le comportement
   ATTENDU qui est écrit dans le test, sur les quatre points où une erreur d'un
   cran ne se relit pas : le pas en grille, le rebouclage, la garde du pas
   transverse (une liste à une colonne ne doit pas répondre à gauche/droite) et
   la fenêtre de défilement.

   **La FORME de la liste est posée à la compilation, pas à l'exécution.** Les
   tables du build sont `const` — elles vivent en ROM sur console et
   `gba_engine.h` les déclare ainsi —, et gcc remplace la lecture d'un objet
   const par son initialiseur, même à `-O0` : une sonde qui écrirait dans
   `g_ui_lists` verrait ses valeurs ignorées par le moteur, sans une erreur pour
   le dire (vérifié). Le pilote compile donc une sonde par forme testée, avec des
   `-D`. Ce qui reste variable à l'exécution — le nombre d'items et les appuis —
   vit dans l'état vivant, celui que le moteur écrit de toute façon.

   ENTRÉE (des entiers, séparés par des blancs) :
       total n_keys key[n_keys]
       (1 haut, 2 bas, 3 gauche, 4 droite, 0 relâché,
        5 la liste rend la main, 6 elle la reprend)

   SORTIE :
       STEP <n>  puis n lignes « <index> <first> »                            */

#include <stdio.h>

#define GBA_ENGINE_IMPL
#include "gba_engine.h"

/* Symboles que `main.c` fournit d'ordinaire. La navigation n'en lit aucun — ni
   texte, ni police, ni sauvegarde — mais le moteur est compilé en entier. */
vu16    gba_shim_registers[16];
OBJATTR gba_shim_oam[128];

void CpuFastSet(const void *source, void *dest, u32 mode) {
    (void)source; (void)dest; (void)mode;
}

const unsigned short g_palettes[1][16] = {{0}};
const int            g_palette_count = 0;
const unsigned int   g_save_id[1]  = {0};
const unsigned short g_save_idx[1] = {0};
const int            g_save_def[1] = {0};
const int            g_save_count = 0;
const int            g_save_slots = 0;
const int            g_save_slot_size = 0;
const FontInfo       g_fonts[1];
const int            g_font_count = 0;
const unsigned char  g_lang_font_0[1] = {0};
const unsigned char* const g_lang_font[1] = {g_lang_font_0};
int g_lang = 0;
int g_lang_reload = 0;
const int g_lang_count = 1;
const unsigned short* const g_texts_0[1] = {0};
const unsigned short* const* const g_texts[1] = {g_texts_0};
const unsigned short g_text_len_0[1] = {0};
const unsigned short* const g_text_len[1] = {g_text_len_0};
const TextEvent* const g_text_events_0[1] = {0};
const TextEvent* const* const g_text_events[1] = {g_text_events_0};
const unsigned short g_text_ev_count_0[1] = {0};
const unsigned short* const g_text_ev_count[1] = {g_text_ev_count_0};
const unsigned short g_text_values_0[1] = {0};
const unsigned short* const g_text_values[1] = {g_text_values_0};
const unsigned short g_save_len[1]  = {0};
const unsigned char  g_save_bits[1] = {0};
const UIImageInfo    g_ui_images[1];
const int            g_ui_image_count = 0;
const UIElementInfo  g_ui_elements[1];
const int            g_ui_element_count = 0;
int cam_x, cam_y;

int  global_read (int i)        { (void)i; return 0; }
void global_write(int i, int v) { (void)i; (void)v; }
int  global_read_at (int i, int k)        { (void)i; (void)k; return 0; }
void global_write_at(int i, int k, int v) { (void)i; (void)k; (void)v; }

/* ── La liste sous test ───────────────────────────────────────────
   Les défauts décrivent une liste verticale de quatre rangées qui reboucle ;
   le pilote surcharge par `-D`. Cadence NEUTRE (`rep_delay`/`rep_rate` à 0) :
   la sonde relâche entre deux appuis, un appui vaut donc un pas.

   Ni curseur (-1) ni style de sélection (0, 0) : `ui_list_cursor_follow` et
   `ui_list_sync_style` sortent alors sans rien lire, et ce qu'on interroge est
   la NAVIGATION seule — le reste demanderait un texte posé et de la VRAM. */
#define PROBE_ROWS_MAX 64

#ifndef PROBE_ROWS
#define PROBE_ROWS 4
#endif
#ifndef PROBE_COLUMNS
#define PROBE_COLUMNS 1
#endif
#ifndef PROBE_MAJOR
#define PROBE_MAJOR 0        /* 0 = colonne (W), 1 = rangée (Z) */
#endif
#ifndef PROBE_WRAP
#define PROBE_WRAP 1
#endif

const UIListInfo g_ui_lists[1] = {{
    PROBE_ROWS, PROBE_COLUMNS, PROBE_MAJOR, PROBE_WRAP,
    0, 0,        /* rep_delay, rep_rate */
    0,           /* row0 */
    -1, 0, 1,    /* cursor, cursor_mode, cursor_speed */
    0, 0,        /* selected_color, selected_highlight */
}};
/* Aucune rangée ne pointe de zone : la navigation n'en lit aucune. */
const short        g_ui_list_rows[PROBE_ROWS_MAX] = {0};
const int          g_ui_list_count = 1;
const UIRegionInfo g_ui_regions[PROBE_ROWS_MAX];
const int          g_ui_region_count = PROBE_ROWS_MAX;

/* État VIVANT — celui que main.c définit et que le moteur écrit chaque frame. */
short g_ui_list_row_text[PROBE_ROWS_MAX];
int   g_ui_list_index[1], g_ui_list_first[1], g_ui_list_total[1];
int   g_ui_list_timer[1], g_ui_list_active[1], g_ui_list_shown[1];
u32   _g_keys_held = 0;

int main(void) {
    int total, n_keys;
    if (scanf("%d %d", &total, &n_keys) != 2) return 1;

    for (int k = 0; k < PROBE_ROWS_MAX; k++) g_ui_list_row_text[k] = -1;
    g_ui_list_index[0] = 1;
    g_ui_list_first[0] = 1;
    g_ui_list_total[0] = total;
    g_ui_list_timer[0] = 0;
    g_ui_list_active[0] = 1;
    g_ui_list_shown[0] = 0;

    printf("STEP %d\n", n_keys);
    for (int k = 0; k < n_keys; k++) {
        int key;
        if (scanf("%d", &key) != 1) return 1;
        switch (key) {
            case 1:  _g_keys_held = KEY_UP;    break;
            case 2:  _g_keys_held = KEY_DOWN;  break;
            case 3:  _g_keys_held = KEY_LEFT;  break;
            case 4:  _g_keys_held = KEY_RIGHT; break;
            /* Rendre puis reprendre la main : la seule chose qu'`active`
               change, et elle se joue ici comme un appui de plus. */
            case 5:  _g_keys_held = 0; ui_list_set_active(0, 0); break;
            case 6:  _g_keys_held = 0; ui_list_set_active(0, 1); break;
            default: _g_keys_held = 0; break;
        }
        ui_list_tick();
        printf("%d %d\n", g_ui_list_index[0], g_ui_list_first[0]);
    }
    return 0;
}
