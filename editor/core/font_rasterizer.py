"""Rasterisation éphémère des sources vectorielles.

Ce module est le seul endroit où une fonte TTF/OTF devient une grille de
couverture. Il ne connaît ni tuiles, ni palette, ni Qt : la même sortie peut
donc être consommée par le build et par l'aperçu de l'éditeur.

Rien n'est écrit sur disque. Les fichiers vectoriels restent des sources dans
``assets/fonts/`` ; le sous-ensemble de glyphes ne sera matérialisé qu'au
moment de l'export GBA.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class FontRasterizerError(RuntimeError):
    """Une source vectorielle ne peut pas être rasterisée."""


class FontRasterizerUnavailable(FontRasterizerError):
    """La dépendance FreeType de build n'est pas installée."""


@dataclass(frozen=True)
class RasterGlyph:
    """Un glyphe raster, avant toute décision propre à la GBA.

    ``coverage`` contient ``width * height`` octets, de 0 (transparent) à 255
    (encre pleine), rangés par lignes. ``bearing_y`` est mesuré au-dessus de la
    ligne de base : il permet d'aligner des sources de repli sans que le
    rasterizer ne connaisse le layout qui les emploie.
    """

    char: str
    width: int
    height: int
    coverage: bytes
    advance: int
    bearing_x: int
    bearing_y: int
    source_name: str = ""
    # RGB source, trois octets par pixel, facultatif pour les fontes
    # vectorielles. Une planche bitmap le renseigne afin que l'encodage conserve
    # ses indices/couleurs de palette au lieu de la réduire à un masque alpha.
    colors: bytes = b""

    def __post_init__(self):
        if len(self.char) != 1:
            raise ValueError("RasterGlyph attend exactement un caractère")
        if self.width < 0 or self.height < 0:
            raise ValueError("les dimensions d'un RasterGlyph sont positives")
        if len(self.coverage) != self.width * self.height:
            raise ValueError("la couverture ne correspond pas aux dimensions")
        if self.colors and len(self.colors) != self.width * self.height * 3:
            raise ValueError("les couleurs ne correspondent pas aux pixels")

    def coverage_at(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
        return self.coverage[y * self.width + x]

    def color_at(self, x: int, y: int) -> tuple[int, int, int] | None:
        """Couleur source d'un pixel bitmap, ou ``None`` pour une couverture
        vectorielle (qui sera mise en palette par l'encodeur)."""
        if not self.colors or not (0 <= x < self.width and 0 <= y < self.height):
            return None
        offset = (y * self.width + x) * 3
        return tuple(self.colors[offset:offset + 3])


def _freetype():
    try:
        import freetype
    except ImportError as exc:
        raise FontRasterizerUnavailable(
            "La rasterisation vectorielle requiert freetype-py. "
            "Installe les dépendances de l'éditeur."
        ) from exc
    return freetype


def _load_flags(freetype, hinting: str, *, grid_fit: bool = False) -> int:
    """Traduit le vocabulaire persistant en choix FreeType, localement."""
    flags = freetype.FT_LOAD_RENDER
    if hinting == "none":
        return flags | freetype.FT_LOAD_NO_HINTING
    if hinting == "light":
        return flags | freetype.FT_LOAD_TARGET_LIGHT
    if hinting == "mono" or grid_fit:
        return flags | freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_MONOCHROME
    return flags


def resolved_pixel_fit(pixel_fit: str, pixel_height: int, *, has_bitmap_strike: bool) -> str:
    """Résout la recette demandée en une opération réalisable par FreeType.

    À très petite taille, l'alignement mono est plus prévisible qu'une simple
    réduction de contours anti-crénelés. Une strike exactement à la taille
    demandée reste toutefois la meilleure réponse quand la fonte en propose.
    """
    if pixel_fit == "bitmap_strike" and has_bitmap_strike:
        return "bitmap_strike"
    if pixel_fit == "auto" and has_bitmap_strike:
        return "bitmap_strike"
    if pixel_fit == "grid_fit" or (pixel_fit == "auto" and pixel_height <= 6):
        return "grid_fit"
    return "native"


def _select_embedded_strike(face, pixel_height: int) -> bool:
    """Choisit seulement une strike dont la taille correspond exactement.

    Une strike proche modifierait la recette demandée par l'auteur. Sans
    équivalent exact, ``set_pixel_sizes`` laisse FreeType vectoriser la face.
    """
    for index, size in enumerate(getattr(face, "available_sizes", ())):
        y_ppem = getattr(size, "y_ppem", 0)
        height = getattr(size, "height", 0)
        if y_ppem == pixel_height * 64 or height == pixel_height:
            face.select_size(index)
            return True
    return False


def _has_embedded_strike(face, pixel_height: int) -> bool:
    """Une strike exacte existe-t-elle, sans changer la taille active ?"""
    return any(
        getattr(size, "y_ppem", 0) == pixel_height * 64
        or getattr(size, "height", 0) == pixel_height
        for size in getattr(face, "available_sizes", ())
    )


def _coverage(bitmap, freetype) -> bytes:
    """Normalise les bitmaps Gray ou mono de FreeType en 0..255."""
    width, rows, pitch = int(bitmap.width), int(bitmap.rows), int(bitmap.pitch)
    if not width or not rows:
        return b""
    data = bytes(bitmap.buffer)
    stride = abs(pitch)
    out = bytearray(width * rows)
    mono = bitmap.pixel_mode == freetype.FT_PIXEL_MODE_MONO
    for y in range(rows):
        source_y = y if pitch >= 0 else rows - 1 - y
        row = data[source_y * stride:(source_y + 1) * stride]
        for x in range(width):
            if mono:
                out[y * width + x] = 255 if row[x // 8] & (0x80 >> (x % 8)) else 0
            else:
                value = row[x] if x < len(row) else 0
                # FT_GRAY_NUM_GRAYS vaut normalement 256, mais cette formule
                # garde la sortie correcte pour une strike à autre profondeur.
                grays = max(2, int(getattr(bitmap, "num_grays", 256)))
                out[y * width + x] = round(value * 255 / (grays - 1))
    return bytes(out)


def glyph_exists(source_path: Path, char: str) -> bool:
    """Vrai si la face possède réellement ce caractère, hors .notdef."""
    if len(char) != 1:
        return False
    freetype = _freetype()
    try:
        face = freetype.Face(str(source_path))
        return bool(face.get_char_index(ord(char)))
    except Exception as exc:  # FreeType expose plusieurs classes d'erreur.
        raise FontRasterizerError(f"Lecture impossible de « {source_path.name} » : {exc}") from exc


def rasterize_vector_glyph(
    source_path: Path,
    char: str,
    *,
    pixel_height: int,
    hinting: str = "normal",
    pixel_fit: str = "auto",
    prefer_bitmap_strike: bool = True,
    offset_x: int = 0,
    offset_y: int = 0,
    source_name: str = "",
) -> RasterGlyph:
    """Rastérise un caractère TTF/OTF en couverture, sans effet de bord."""
    if len(char) != 1:
        raise ValueError("rasterize_vector_glyph attend exactement un caractère")
    if pixel_height < 1:
        raise ValueError("pixel_height doit être positif")
    freetype = _freetype()
    try:
        face = freetype.Face(str(source_path))
        fit = resolved_pixel_fit(
            pixel_fit, pixel_height,
            has_bitmap_strike=(pixel_fit == "bitmap_strike" or prefer_bitmap_strike)
            and _has_embedded_strike(face, pixel_height),
        )
        used_strike = fit == "bitmap_strike" and _select_embedded_strike(face, pixel_height)
        if not used_strike:
            face.set_pixel_sizes(0, pixel_height)
        if not face.get_char_index(ord(char)):
            raise FontRasterizerError(f"« {char} » n'est pas couvert par {source_path.name}")
        face.load_char(ord(char), _load_flags(freetype, hinting, grid_fit=fit == "grid_fit"))
        slot, bitmap = face.glyph, face.glyph.bitmap
    except FontRasterizerError:
        raise
    except Exception as exc:
        raise FontRasterizerError(f"Rasterisation impossible de « {source_path.name} » : {exc}") from exc

    return RasterGlyph(
        char=char,
        width=int(bitmap.width), height=int(bitmap.rows),
        coverage=_coverage(bitmap, freetype),
        advance=round(slot.advance.x / 64),
        bearing_x=int(slot.bitmap_left) + offset_x,
        bearing_y=int(slot.bitmap_top) + offset_y,
        source_name=source_name,
    )


_BAYER_2X2 = ((0, 2), (3, 1))
_BAYER_4X4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def display_coverage(value: int, x: int, y: int, *, raster_mode: str,
                     threshold: int, dither_pattern: str) -> int:
    """Applique la recette de sortie à un pixel, pour preview ou export.

    Le mode ``coverage`` conserve l'anti-crénelage. Les deux autres donnent
    une encre binaire ; le dither déplace localement le seuil, pas le glyphe.
    """
    value = max(0, min(255, int(value)))
    if raster_mode == "coverage":
        return value
    if raster_mode == "dither" and dither_pattern != "none":
        matrix = _BAYER_2X2 if dither_pattern == "bayer_2x2" else _BAYER_4X4
        size = len(matrix)
        # ± la moitié d'un pas : un seuil 128 garde la couverture moyenne.
        threshold += round(((matrix[y % size][x % size] + .5) / (size * size) - .5) * 255)
    return 255 if value >= max(0, min(255, threshold)) else 0


def _asset_source_names(asset, variant: str, weight: int | None = None,
                        italic: bool | None = None) -> list[str]:
    """La chaîne explicite a priorité ; les faces auto servent de défaut."""
    names = asset.source_names(variant)
    # Une chaîne regular configurée à la main est la réponse explicite pour
    # Regular. Pour un autre poids, les faces de famille sont prioritaires :
    # sélectionner Bold ne doit jamais rasteriser Regular par accident.
    if names and (weight is None or weight == 400) and (italic is None or not italic):
        return names
    wanted = {
        "regular": (400, False), "bold": (700, False),
        "italic": (400, True), "bold_italic": (700, True),
    }.get(variant, (400, False))
    target_weight = wanted[0] if weight is None else weight
    target_italic = wanted[1] if italic is None else italic
    return [face.source_name for face in asset.faces
            if face.weight == target_weight and face.italic == target_italic]


def rasterize_asset_glyph(project, asset, char: str, variant: str = "regular",
                           weight: int | None = None, italic: bool | None = None) -> RasterGlyph:
    """Résout la couverture d'un ``FontAsset`` dans l'ordre de ses sources.

    L'accès au projet sert uniquement à résoudre les noms et chemins. Dès que
    la source est choisie, l'opération délègue à ``rasterize_vector_glyph``, la
    fonction pure que le build utilisera également.
    """
    names = _asset_source_names(asset, variant, weight, italic)
    if not names:
        raise FontRasterizerError("Cet asset ne possède aucune source pour cette variante.")
    problems: list[str] = []
    for name in names:
        source = project.fonts.get(name)
        if source is None:
            problems.append(f"{name} est introuvable")
            continue
        path = project.asset_abs(source.asset)
        if not path or not path.exists():
            problems.append(f"le fichier de {name} est introuvable")
            continue
        if source.source_format in ("png", "fnt"):
            glyph = source.glyph(char)
            if glyph is None:
                problems.append(f"{name} ne couvre pas ce caractère")
                continue
            try:
                from PIL import Image
                image = Image.open(path).convert("RGBA")
                pixels = image.load()
                coverage = bytearray(glyph.w * glyph.h)
                colors = bytearray(glyph.w * glyph.h * 3)
                keys = {tuple(c) for c in source.key_colors()}
                for y in range(glyph.h):
                    for x in range(glyph.w):
                        if x + glyph.x >= image.width or y + glyph.y >= image.height:
                            continue
                        r, g, b, a = pixels[x + glyph.x, y + glyph.y]
                        pos = y * glyph.w + x
                        coverage[pos] = 0 if (r, g, b) in keys else a
                        colors[pos * 3:pos * 3 + 3] = bytes((r, g, b))
                return RasterGlyph(char, glyph.w, glyph.h, bytes(coverage),
                                   glyph.advance, glyph.ox, glyph.h - glyph.oy,
                                   source_name=name, colors=bytes(colors))
            except Exception as exc:
                problems.append(f"lecture bitmap de {name} impossible ({exc})")
                continue
        if source.source_format not in ("ttf", "otf"):
            problems.append(f"{name} a un format non rendu")
            continue
        if glyph_exists(path, char):
            return rasterize_vector_glyph(
                path, char, pixel_height=asset.pixel_height, hinting=asset.hinting,
                pixel_fit=asset.pixel_fit,
                prefer_bitmap_strike=asset.prefer_bitmap_strike,
                offset_x=asset.offset_x, offset_y=asset.offset_y, source_name=name,
            )
    detail = " ; ".join(problems) or "aucune source ne couvre ce caractère"
    raise FontRasterizerError(f"« {char} » ne peut pas être rendu : {detail}.")
