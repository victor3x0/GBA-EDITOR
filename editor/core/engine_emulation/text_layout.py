"""
core/text_layout.py — où atterrit chaque glyphe d'un texte, en pixels.

Miroir de `text_layout` (runtime/include/gba_engine.h) : correspondance au plus
long (ligatures), avance par la chasse de chaque glyphe, coupe au mot, repli au
glyphe pour un mot trop long. Ce que cette fonction place est ce que la console
placera.

Tout se calcule en PIXELS, comme au runtime : une police proportionnelle pose
ses glyphes à x=13 ou x=21, ce qu'une grille de tuiles ne saurait montrer. En
mono, les chasses valant gw*8, les positions retombent d'elles-mêmes sur des
multiples de 8 — un seul code pour les deux rendus.

Les chasses viennent de `codegen.font_emit` (import tardif, comme
core/validator.py) : c'est la règle que suit l'ÉMETTEUR, pas un second critère
qui pourrait en diverger. Vue d'ici la dépendance remonte d'une couche, mais la
partager est justement ce qui empêche l'aperçu de promettre un placement que la
ROM ne tiendra pas.
"""
from __future__ import annotations

# Écran GBA — cadre de mise en page par défaut.
SCREEN_W, SCREEN_H = 240, 160


ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT = "left", "center", "right"


def _align_off(align: str, wrap_px: int, line_w: int, snap_to_tile: bool) -> int:
    """Décalage horizontal d'une ligne — miroir de `text_align_off`
    (gba_engine.h).

    `snap_to_tile` n'est pas un raffinement : sur le chemin TILEMAP un glyphe se
    pose à la tuile, donc le moteur cale l'offset sur la grille (`off &= ~7`).
    Sans lui, l'aperçu centrerait au pixel ce que la ROM centre à la tuile —
    jusqu'à 7 px d'écart."""
    if wrap_px <= 0 or line_w >= wrap_px:
        return 0
    off = 0
    if align == ALIGN_CENTER:
        off = (wrap_px - line_w) // 2
    elif align == ALIGN_RIGHT:
        off = wrap_px - line_w
    return (off & ~7) if snap_to_tile else off


def layout_text(font, text: str, width: int = SCREEN_W,
                height: int = SCREEN_H, align: str = ALIGN_LEFT,
                composited: bool | None = None) -> tuple[list[tuple], bool]:
    """Pose `text` avec `font` dans un cadre `width`×`height`.

    Retourne ([(glyphe, x, y) en pixels], débordement vertical). Les caractères
    que la police ne sait pas rendre avancent de la chasse de secours sans rien
    poser — comme au runtime, qui laisse un trou plutôt que de décaler la suite.

    `align` reproduit le ferrage du moteur (`UIRegion.align`, émis dans
    `g_ui_regions`) et n'agit que sur les positions, ni sur la coupe ni sur le
    débordement — d'où un défaut à gauche, neutre pour la mesure.

    `composited` force le chemin de rendu supposé pour le calage de l'offset ;
    None = déduit de la police. Une zone à FOND compose même en police mono (cf.
    `g_ui_fill_bg`), et l'appelant qui le sait peut donc le dire.
    """
    if not font or not getattr(font, "glyphs", None) or not text:
        return [], False
    from codegen.font_emit import (glyph_advance_px, font_line_px,
                                   font_fallback_adv_px, render_composited)
    line = font_line_px(font)
    fallback = font_fallback_adv_px(font)
    # Largeur ATTEINTE par ligne (y → x final), pour ferrer à la fin. L'espace
    # qui provoque la coupe n'y entre pas : elle n'est pas posée, et le moteur
    # ne la compte pas davantage dans `lw`.
    line_w: dict[int, int] = {}

    def adv(g):
        return fallback if g is None else glyph_advance_px(g, font)

    def word_width(i):
        w, n = 0, len(text)
        while i < n and text[i] not in " \n":
            g = font.match_at(text, i)
            w += adv(g)
            i += len(g.char) if g else 1
        return w

    out, over = [], False
    x = y = 0
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            x, y, i = 0, y + line, i + 1
            continue
        if ch == " ":
            gsp = font.match_at(text, i)
            used_sp = len(gsp.char) if gsp else 1
            if x + adv(gsp) + word_width(i + used_sp) > width:
                x, y, i = 0, y + line, i + used_sp
                continue
        g = font.match_at(text, i)
        a = adv(g)
        if x + a > width:
            x, y = 0, y + line
        if y + line > height:
            over = True
            break
        if g:
            out.append((g, x, y))
        x += a
        line_w[y] = x
        i += len(g.char) if g else 1

    if align in (ALIGN_CENTER, ALIGN_RIGHT) and out:
        snap = not (render_composited(font) if composited is None else composited)
        out = [(g, gx + _align_off(align, width, line_w.get(gy, 0), snap), gy)
               for g, gx, gy in out]
    return out, over


def layout_marked_text(font, source: str, fonts: dict[str, object], values=None,
                       width: int = SCREEN_W, height: int = SCREEN_H,
                       align: str = ALIGN_LEFT, composited: bool = True):
    """Mise en page d'un texte balisé, avec la police active par position.

    Le retour ajoute la police au placement : ``(font, glyph, x, y)``. C'est
    le pendant éditeur de ``TEXT_EV_FONT`` ; le canvas peut ainsi choisir la
    bonne planche pour chaque glyphe sans posséder sa propre grammaire.
    """
    from core.text_markup import parse, resolve, KIND_VALUE, SENTINEL
    from codegen.font_emit import glyph_advance_px, font_fallback_adv_px, font_line_px

    parsed = parse(source or "")
    text = resolve(parsed, values or {})
    if not font or not text:
        return [], False
    # Positions dans `parsed.display` → positions après résolution des valeurs.
    pos, out_pos = [0] * (len(parsed.display) + 1), 0
    value_at = {m.at: str((values or {}).get(m.value, f"${m.value}"))
                for m in parsed.markers if m.kind == KIND_VALUE}
    for i, ch in enumerate(parsed.display):
        pos[i] = out_pos
        out_pos += len(value_at[i]) if ch == SENTINEL and i in value_at else 1
    pos[len(parsed.display)] = out_pos
    ranges = [(pos[m.at], pos[m.end], fonts.get(str(m.value), font))
              for m in parsed.of_kind("font")]

    def active(i):
        return next((f for start, end, f in reversed(ranges) if start <= i < end), font)

    def match(i):
        current = active(i)
        glyph = current.match_at(text, i)
        if glyph and any(active(i + j) is not current for j in range(1, len(glyph.char))):
            glyph = None
        return current, glyph

    def advance(current, glyph):
        return font_fallback_adv_px(current) if glyph is None else glyph_advance_px(glyph, current)

    line = font_line_px(font)  # interligne de la zone, comme le runtime
    out, widths, x, y, i, over = [], {}, 0, 0, 0, False
    while i < len(text):
        if text[i] == "\n":
            x, y, i = 0, y + line, i + 1; continue
        current, glyph = match(i)
        used, adv = (len(glyph.char), advance(current, glyph)) if glyph else (1, advance(current, None))
        if text[i] == " ":
            j, word = i + used, 0
            while j < len(text) and text[j] not in " \n":
                wf, wg = match(j); wu = len(wg.char) if wg else 1
                word += advance(wf, wg); j += wu
            if x + adv + word > width:
                x, y, i = 0, y + line, i + used; continue
        if x and x + adv > width:
            x, y = 0, y + line
        if y + line > height:
            over = True; break
        if glyph:
            out.append((current, glyph, x, y))
        x += adv; widths[y] = x; i += used
    if align in (ALIGN_CENTER, ALIGN_RIGHT):
        out = [(f, g, gx + _align_off(align, width, widths.get(gy, 0), not composited), gy)
               for f, g, gx, gy in out]
    return out, over

