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


def layout_text(font, text: str, width: int = SCREEN_W,
                height: int = SCREEN_H) -> tuple[list[tuple], bool]:
    """Pose `text` avec `font` dans un cadre `width`×`height`.

    Retourne ([(glyphe, x, y) en pixels], débordement vertical). Les caractères
    que la police ne sait pas rendre avancent de la chasse de secours sans rien
    poser — comme au runtime, qui laisse un trou plutôt que de décaler la suite.
    """
    if not font or not getattr(font, "glyphs", None) or not text:
        return [], False
    from codegen.font_emit import (glyph_advance_px, font_line_px,
                                   font_fallback_adv_px)
    line = font_line_px(font)
    fallback = font_fallback_adv_px(font)

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
        i += len(g.char) if g else 1
    return out, over


def text_extent(font, text: str, width: int = SCREEN_W,
                height: int = SCREEN_H) -> tuple[int, int]:
    """Encombrement (largeur, hauteur) du texte posé — ce qu'il faut pour le
    confronter au rectangle d'une `UIRegion`."""
    placed, _ = layout_text(font, text, width, height)
    if not placed:
        return 0, 0
    return (max(x + g.w for g, x, _y in placed),
            max(y + g.h for g, _x, y in placed))
