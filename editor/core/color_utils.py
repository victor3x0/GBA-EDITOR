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


def nearest_bank_color(rgb888: tuple[int, int, int], bank_colors: list[int]) -> int:
    """Retourne la valeur BGR555 de `bank_colors` la plus proche de `rgb888`
    (distance euclidienne dans l'espace 5-bit/canal)."""
    r, g, b = rgb888
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    best = bank_colors[0]
    best_dist = None
    for c in bank_colors:
        cr, cg, cb = bgr555_to_rgb888(c)
        cr5, cg5, cb5 = cr >> 3, cg >> 3, cb >> 3
        dist = (r5 - cr5) ** 2 + (g5 - cg5) ** 2 + (b5 - cb5) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = c
    return best


def tint_image_with_bank(img: "Image.Image", bank_colors: list[int]) -> "Image.Image":
    """Reteinte `img` (RGBA) selon la luminance de chaque pixel, mappée sur la
    rampe clair->sombre d'une banque (aperçu uniquement — ne modifie ni les
    pixels sources ni la palette assignée). Ne mute pas `img`. Pas d'effet si
    `bank_colors` est vide (banque réservée non alimentée)."""
    if not bank_colors:
        return img
    n = len(bank_colors)
    ramp = [bgr555_to_rgb888(c) for c in bank_colors]

    def _band_lut(channel: int) -> list[int]:
        lut = []
        for gray in range(256):
            t = 1.0 - gray / 255.0
            idx = min(n - 1, max(0, round(t * (n - 1))))
            lut.append(ramp[idx][channel])
        return lut

    from PIL import Image
    gray = img.convert("L")   # luma standard PIL : 0.299R + 0.587G + 0.114B
    r = gray.point(_band_lut(0))
    g = gray.point(_band_lut(1))
    b = gray.point(_band_lut(2))
    out = Image.merge("RGB", (r, g, b)).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


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
