"""
editor/core/color_utils.py — Conversions couleur GBA (BGR555) et quantification.

Format hardware GBA (confirmé par `grit --help`, "-gT{n} ... 16bit BGR hex") :
bits 0-4 = R, bits 5-9 = G, bits 10-14 = B, 5 bits par canal.
"""
from __future__ import annotations


def rgb888_to_bgr555(r: int, g: int, b: int) -> int:
    return ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def bgr555_to_rgb888(v: int) -> tuple[int, int, int]:
    r = (v & 0x1F) << 3
    g = ((v >> 5) & 0x1F) << 3
    b = ((v >> 10) & 0x1F) << 3
    return (r, g, b)


def bgr555_components(v: int) -> tuple[int, int, int]:
    """Retourne (r, g, b) en 0-31 (profondeur native GBA), sans passer par le 0-255."""
    return v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F


def components_to_bgr555(r5: int, g5: int, b5: int) -> int:
    return ((b5 & 0x1F) << 10) | ((g5 & 0x1F) << 5) | (r5 & 0x1F)


# Index 0 d'une PaletteBank est réservé — le hardware GBA traite toujours
# l'index de palette 0 comme transparent (OBJ comme BG), quelle que soit la
# couleur RGB qui y est stockée. La valeur exacte n'a donc aucune incidence
# visuelle pour une tuile normale (seul PAL_BG_RAM[0] — banque 0 — a un rôle
# supplémentaire de backdrop, géré séparément via Project/Scene.backdrop_color).
RESERVED_SLOT_COLOR = 0


def nearest_bank_color(rgb888: tuple[int, int, int], bank_colors: list[int]) -> int:
    """Retourne la valeur BGR555 de `bank_colors` la plus proche de `rgb888`
    (distance euclidienne dans l'espace 5-bit/canal). L'index 0 est exclu de
    la recherche : un pixel opaque n'a jamais le droit d'y être snappé (il
    deviendrait transparent au lieu d'afficher une couleur approximative)."""
    candidates = bank_colors[1:] if len(bank_colors) > 1 else bank_colors
    r, g, b = rgb888
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    best = candidates[0]
    best_dist = None
    for c in candidates:
        cr, cg, cb = bgr555_to_rgb888(c)
        cr5, cg5, cb5 = cr >> 3, cg >> 3, cb >> 3
        dist = (r5 - cr5) ** 2 + (g5 - cg5) ** 2 + (b5 - cb5) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = c
    return best


def quantize_image_to_bank(img: "Image.Image", bank_colors: list[int]) -> "Image.Image":
    """Snappe chaque pixel RGB(A) de `img` vers la couleur de banque la plus
    proche (alpha préservé, pixels transparents non touchés). `img` doit être
    en mode RGBA. `bank_colors` doit être non-vide."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    cache: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            key = (r, g, b)
            snapped = cache.get(key)
            if snapped is None:
                nearest = nearest_bank_color(key, bank_colors)
                snapped = bgr555_to_rgb888(nearest)
                cache[key] = snapped
            px[x, y] = (snapped[0], snapped[1], snapped[2], a)
    return img


def _luma(rgb888: tuple[int, int, int]) -> float:
    r, g, b = rgb888
    return 0.299 * r + 0.587 * g + 0.114 * b


def compress_colors(
    colors: list[tuple[int, int, int]], max_colors: int
) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """Réduit une liste de couleurs RGB distinctes à `max_colors` représentants
    (median-cut, PIL `Image.quantize`). Construit une image synthétique 1×N
    (une couleur par pixel, ordre préservé), quantifie, puis relit les
    valeurs de sortie pour bâtir couleur d'origine -> couleur réduite. No-op
    (identité) si `colors` tient déjà dans `max_colors`."""
    if len(colors) <= max_colors:
        return {c: c for c in colors}
    from PIL import Image
    n = len(colors)
    src = Image.new("RGB", (n, 1))
    src.putdata(colors)
    quantized = src.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    reduced = list(quantized.getdata())
    return dict(zip(colors, reduced))


def quantize_image_luminance_preserving(img: "Image.Image", bank_colors: list[int]) -> "Image.Image":
    """Alternative à `quantize_image_to_bank` : préserve l'information autant
    que possible. Si l'image référence N couleurs distinctes opaques et qu'il
    y a assez de slots éditables (<=15), chaque couleur distincte obtient un
    slot DIFFÉRENT de la banque (jamais de collision) — assignation par
    écartement régulier le long d'un tri par luminance croissante, couleurs
    et slots cibles. Si N > 15, `compress_colors` réduit d'abord à 15
    représentants (l'info se perd alors nécessairement, il n'y a pas assez
    de place). `img` doit être en mode RGBA. `bank_colors` doit être non-vide."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size

    editable = bank_colors[1:] if len(bank_colors) > 1 else bank_colors

    distinct: dict[tuple[int, int, int], None] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            distinct.setdefault((r, g, b), None)
    colors = list(distinct.keys())
    if not colors:
        return img

    color_map = compress_colors(colors, len(editable))
    reduced_distinct = sorted(set(color_map.values()), key=_luma)
    editable_sorted = sorted(editable, key=lambda c: _luma(bgr555_to_rgb888(c)))

    n, m = len(reduced_distinct), len(editable_sorted)
    assign: dict[tuple[int, int, int], int] = {}
    for i, c in enumerate(reduced_distinct):
        idx = round(i * (m - 1) / (n - 1)) if n > 1 else m // 2
        assign[c] = editable_sorted[idx]

    final_cache = {c: assign[color_map[c]] for c in colors}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            snapped = bgr555_to_rgb888(final_cache[(r, g, b)])
            px[x, y] = (snapped[0], snapped[1], snapped[2], a)
    return img


def extract_palette_from_image(path, max_colors: int = 15) -> list[int]:
    """Construit une palette (liste BGR555) depuis les couleurs opaques d'un
    PNG, pour le bouton "Extraire du PNG" du Sprite Editor. L'index 0 reste
    réservé (transparence), suivi des couleurs réelles triées de la plus
    sombre à la plus lumineuse (luminance croissante). Si le PNG référence
    plus de `max_colors` couleurs distinctes, `compress_colors` (median-cut)
    réduit d'abord — sinon toutes sont conservées telles quelles.
    Retourne `[RESERVED_SLOT_COLOR] + couleurs` (longueur 1 à max_colors+1)."""
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    px = img.load()
    w, h = img.size
    distinct: dict[tuple[int, int, int], None] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            distinct.setdefault((r, g, b), None)
    colors = list(distinct.keys())
    if not colors:
        return [RESERVED_SLOT_COLOR]
    if len(colors) > max_colors:
        color_map = compress_colors(colors, max_colors)
        # dict.fromkeys : dédup les représentants réduits en préservant l'ordre
        colors = list(dict.fromkeys(color_map.values()))
    # PAS de tri : l'ordre = ordre d'apparition des couleurs dans le PNG.
    # L'index de palette est le slot hardware réellement visible in-game ;
    # réordonner risquerait de désaligner les tuiles déjà quantifiées d'un
    # sprite. C'est à l'utilisateur d'organiser ses couleurs en amont.
    return [RESERVED_SLOT_COLOR] + [rgb888_to_bgr555(r, g, b) for r, g, b in colors]


def direct_index_to_bank(path, bank_colors: list[int]) -> "Image.Image":
    """Mode "indexation directe" : `path` doit être un PNG en mode `'P'`
    natif (palette + index par pixel) — pas de recherche de correspondance,
    les index du PNG se calent directement sur ceux de la banque. Convention
    fixe (pas une détection automatique) : l'index PNG 0 est toujours
    transparent, quel que soit l'éventuel tag `tRNS` du fichier — à
    l'appelant/au validateur de prévenir si le fichier semble mal préparé
    pour ce mode (transparence native à un autre index). Si plus de couleurs
    réelles (index 1+) que de slots éditables, `compress_colors` réduit
    d'abord — l'assignation elle-même reste dans l'ordre d'apparition des
    index PNG, sans tri ni recherche. Retourne une image RGBA, même forme de
    sortie que `quantize_image_to_bank`/`quantize_image_luminance_preserving`."""
    from PIL import Image
    img = Image.open(path)
    if img.mode != "P":
        raise ValueError(f"direct_index_to_bank: {path} n'est pas un PNG indexé (mode {img.mode!r})")

    palette = img.getpalette() or []
    used_indices = sorted(idx for _count, idx in img.getcolors(maxcolors=256))
    real_indices = [i for i in used_indices if i != 0]

    editable = bank_colors[1:] if len(bank_colors) > 1 else bank_colors
    index_to_bank_color: dict[int, int] = {}
    if real_indices and editable:
        real_colors_by_index = {
            i: (palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]) for i in real_indices
        }
        real_colors_list = [real_colors_by_index[i] for i in real_indices]
        color_map = compress_colors(real_colors_list, len(editable))

        ordered_reduced: list[tuple[int, int, int]] = []
        slot_of: dict[tuple[int, int, int], int] = {}
        for i in real_indices:
            reduced = color_map[real_colors_by_index[i]]
            if reduced not in slot_of:
                slot_of[reduced] = len(ordered_reduced)
                ordered_reduced.append(reduced)
            index_to_bank_color[i] = editable[slot_of[reduced]]

    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    src_px = img.load()
    dst_px = out.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            idx = src_px[x, y]
            bank_color = index_to_bank_color.get(idx)
            if bank_color is None:
                continue
            r, g, b = bgr555_to_rgb888(bank_color)
            dst_px[x, y] = (r, g, b, 255)
    return out
