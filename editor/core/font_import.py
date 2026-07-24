"""Import de polices — déduction (PNG nu) et parsing (BMFont .fnt).

Deux points d'entrée seulement, volontairement : l'utilisateur vient avec sa
planche PNG ou son `.fnt`. Les deux remplissent le même sidecar `Font`
(cf. core/models/font.py) ; le reste de l'éditeur ne sait pas d'où vient une
police.

Le PNG nu est le **cas dégradé** : il ne porte aucun mapping, donc on déduit la
grille et on propose un charset, que l'utilisateur corrige case par case dans
l'écran Police. Le `.fnt` porte les codepoints et les avances : rien à deviner.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from core.models.font import Font, Glyph


# ── Charsets connus ───────────────────────────────────────────────
# Sert à départager les découpages candidats : un découpage qui tombe
# exactement sur un charset connu est presque sûrement le bon.

ASCII_PRINTABLE = "".join(chr(c) for c in range(32, 127))          # 95
_KNOWN_CHARSETS: dict[int, str] = {
    95: ASCII_PRINTABLE,
    96: ASCII_PRINTABLE + "",
    59: "".join(chr(c) for c in range(32, 91)),                     # espace → Z
    26: "".join(chr(c) for c in range(65, 91)),                     # A-Z
    36: "".join(chr(c) for c in range(65, 91)) + "0123456789",      # A-Z 0-9
    10: "0123456789",
}

# Bornes de taille de cellule explorées à la déduction.
_CELL_MIN, _CELL_MAX = 4, 32


def propose_charset(n_cells: int) -> str:
    """Charset proposé pour une planche de `n_cells` cases.

    Sur un nombre de cases connu, on renvoie le charset correspondant. Sinon on
    tronque ou complète l'ASCII imprimable : une proposition imparfaite mais
    corrigeable vaut mieux qu'un formulaire vide."""
    known = _KNOWN_CHARSETS.get(n_cells)
    if known:
        return known
    if n_cells <= len(ASCII_PRINTABLE):
        return ASCII_PRINTABLE[:n_cells]
    return ASCII_PRINTABLE + " " * (n_cells - len(ASCII_PRINTABLE))


# ── Analyse d'image ───────────────────────────────────────────────

def _ink_mask(img):
    """Matrice booléenne « ce pixel est de l'encre ».

    Avec un canal alpha, l'encre est ce qui est opaque. Sans alpha, on prend la
    couleur la plus fréquente pour le fond — une planche de police est très
    majoritairement composée de fond, l'hypothèse est sûre."""
    import numpy as np
    from PIL import Image

    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        return np.array(rgba)[:, :, 3] > 0

    rgb = np.array(img.convert("RGB"))
    flat = rgb.reshape(-1, 3)
    colors, counts = np.unique(flat, axis=0, return_counts=True)
    background = colors[counts.argmax()]
    return np.any(rgb != background, axis=2)


def detect_grid(img) -> tuple[int, int]:
    """Taille de cellule (largeur, hauteur) la plus probable pour une planche.

    On énumère les découpages réguliers possibles et on garde le mieux noté :
    tomber sur un nombre de cases d'un charset connu pèse le plus lourd, puis
    les cellules carrées, puis les multiples de 8 (la tuile GBA), puis les
    petites cellules. Sans indice, 8×8 est le défaut."""
    w, h = img.size
    best, best_score = (8, 8), -1.0

    for cw in range(_CELL_MIN, min(_CELL_MAX, w) + 1):
        if w % cw:
            continue
        for ch in range(_CELL_MIN, min(_CELL_MAX, h) + 1):
            if h % ch:
                continue
            cells = (w // cw) * (h // ch)
            if cells < 10:          # une police de moins de 10 glyphes n'existe pas
                continue
            score = 0.0
            if cells in _KNOWN_CHARSETS:
                score += 100.0
            if cw == ch:
                score += 10.0
            if cw % 8 == 0 and ch % 8 == 0:
                score += 5.0
            score -= (cw * ch) / 1000.0     # à égalité, la cellule la plus fine
            if score > best_score:
                best, best_score = (cw, ch), score
    return best


def _measure_advance(ink, x: int, y: int, w: int, h: int) -> int:
    """Largeur d'encre d'un glyphe : dernière colonne non vide + 1.

    Mesurée à l'import pour le rendu proportionnel futur ; le rendu v1 à chasse
    fixe l'ignore. Une case vide (l'espace) renvoie la largeur de cellule."""
    import numpy as np
    sub = ink[y:y + h, x:x + w]
    cols = np.any(sub, axis=0)
    if not cols.any():
        return w
    return int(np.nonzero(cols)[0][-1]) + 1


# ── Import PNG nu ─────────────────────────────────────────────────

def import_font_png(png_path: Path, cell: Optional[tuple[int, int]] = None) -> dict:
    """Analyse une planche PNG. Retourne les champs à poser sur le `Font`.

    Les cases entièrement vides en fin de planche sont du remplissage, pas des
    glyphes : on les retire plutôt que de leur attribuer un caractère."""
    from PIL import Image

    img = Image.open(png_path)
    cw, ch = cell or detect_grid(img)
    cols, rows = max(1, img.size[0] // cw), max(1, img.size[1] // ch)
    ink = _ink_mask(img)

    rects = [(c * cw, r * ch) for r in range(rows) for c in range(cols)]
    # Remplissage de fin : on coupe après le dernier glyphe encré. Une case vide
    # AU MILIEU est légitime (c'est l'espace), seule la queue est du bourrage.
    last = -1
    for i, (x, y) in enumerate(rects):
        if ink[y:y + ch, x:x + cw].any():
            last = i
    rects = rects[:last + 1] if last >= 0 else rects

    charset = propose_charset(len(rects))
    glyphs = [
        Glyph(char=charset[i] if i < len(charset) else " ",
              x=x, y=y, w=cw, h=ch,
              advance=_measure_advance(ink, x, y, cw, ch))
        for i, (x, y) in enumerate(rects)
    ]
    return {"cell_w": cw, "cell_h": ch, "line_height": ch,
            "glyphs": glyphs, "source_format": "png"}


# ── Import BMFont .fnt ────────────────────────────────────────────

_KV = re.compile(r'(\w+)=("[^"]*"|\S+)')


def _kv(line: str) -> dict[str, str]:
    return {k: v.strip('"') for k, v in _KV.findall(line)}


def parse_bmfont(text: str) -> dict:
    """Parse un descripteur BMFont, format texte ou XML.

    Le format binaire (fichier commençant par « BMF ») n'est pas géré : il est
    rare en export manuel et l'utilisateur peut réexporter en texte. On lève une
    erreur explicite plutôt que de produire une police silencieusement vide.

    Retourne {page, line_height, cell_w, cell_h, glyphs} — `page` est le nom de
    fichier de la planche, déclaré par le descripteur."""
    if text.lstrip().startswith("<"):
        return _parse_bmfont_xml(text)
    if text.startswith("BMF"):
        raise ValueError("BMFont binaire non géré — réexporte en format texte ou XML.")
    return _parse_bmfont_text(text)


def _glyph_from_fields(d: dict) -> Optional[Glyph]:
    """Une entrée `char` BMFont → Glyph. Ignore les codepoints hors Unicode."""
    try:
        cp = int(d.get("id", -1))
    except ValueError:
        return None
    if cp < 0 or cp > 0x10FFFF:
        return None
    w = int(d.get("width", 0) or 0)
    h = int(d.get("height", 0) or 0)
    return Glyph(
        char    = chr(cp),
        x       = int(d.get("x", 0) or 0),
        y       = int(d.get("y", 0) or 0),
        w       = w,
        h       = h,
        # xadvance est l'avance voulue par l'auteur : elle prime sur toute
        # mesure d'encre, c'est une décision typographique, pas un constat.
        advance = int(float(d.get("xadvance", w) or w)),
        ox      = int(d.get("xoffset", 0) or 0),
        oy      = int(d.get("yoffset", 0) or 0),
    )


def _finish(glyphs: list[Glyph], line_height: int, page: str) -> dict:
    cw = max((g.w for g in glyphs), default=8) or 8
    chh = max((g.h for g in glyphs), default=8) or 8
    return {"page": page, "line_height": line_height or chh,
            "cell_w": cw, "cell_h": chh, "glyphs": glyphs}


def _parse_bmfont_text(text: str) -> dict:
    glyphs: list[Glyph] = []
    line_height, page = 0, ""
    for line in text.splitlines():
        head = line.split(" ", 1)[0]
        if head == "char":
            g = _glyph_from_fields(_kv(line))
            if g:
                glyphs.append(g)
        elif head == "common":
            d = _kv(line)
            line_height = int(d.get("lineHeight", 0) or 0)
        elif head == "page":
            page = _kv(line).get("file", "")
    return _finish(glyphs, line_height, page)


def _parse_bmfont_xml(text: str) -> dict:
    root = ET.fromstring(text)
    glyphs: list[Glyph] = []
    for el in root.iter("char"):
        g = _glyph_from_fields(dict(el.attrib))
        if g:
            glyphs.append(g)
    common = root.find("common")
    line_height = int(common.get("lineHeight", 0)) if common is not None else 0
    page_el = root.find("./pages/page")
    page = page_el.get("file", "") if page_el is not None else ""
    return _finish(glyphs, line_height, page)


def import_font_fnt(fnt_path: Path) -> dict:
    """Lit un `.fnt` et localise sa planche. Retourne les champs du `Font`,
    plus `page_path` (la planche PNG à référencer comme `asset`).

    Si la page déclarée est introuvable, on retombe sur un PNG de même nom que
    le `.fnt` — le cas courant quand le descripteur a été renommé."""
    data = parse_bmfont(fnt_path.read_text(encoding="utf-8", errors="replace"))
    page = (fnt_path.parent / data["page"]) if data.get("page") else None
    if page is None or not page.exists():
        fallback = fnt_path.with_suffix(".png")
        page = fallback if fallback.exists() else None
    return {"cell_w": data["cell_w"], "cell_h": data["cell_h"],
            "line_height": data["line_height"], "glyphs": data["glyphs"],
            "source_format": "fnt", "page_path": page}


# ── Application au sidecar ────────────────────────────────────────

def apply_font_import(font: Font, fields: dict):
    """Pose un résultat d'import sur le `Font` (calcul/application séparés,
    comme apply_bg_encoding)."""
    for key in ("cell_w", "cell_h", "line_height", "source_format"):
        if key in fields:
            setattr(font, key, fields[key])
    if "glyphs" in fields:
        font.glyphs = fields["glyphs"]
