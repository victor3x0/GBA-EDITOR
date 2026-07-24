"""Font — police bitmap du jeu, stockée en sidecar à côté de sa planche PNG.

**Un asset, plusieurs points d'entrée.** Deux formats sont acceptés en import :
une planche PNG nue (la grille et le charset sont alors déduits, corrigeables
dans l'éditeur) ou un descripteur BMFont `.fnt` + sa page PNG (qui apporte le
mapping, donc supprime la déduction). Les deux remplissent le MÊME sidecar :
un format d'entrée n'est qu'une façade, comme `detect_import_mode` pour les
fonds.

**Le modèle est à rectangles, pas à grille.** Chaque glyphe porte son propre
rectangle dans la planche — c'est ce qui permet d'accueillir BMFont, dont les
glyphes sont posés librement dans la page. Une planche PNG régulière n'est que
le cas particulier où tous les rectangles font la même taille. La grille
(`cell_w`/`cell_h`) ne reste qu'une aide à la déduction et à l'affichage.

**`advance` est mesuré dès l'import mais ignoré au rendu v1**, qui est à chasse
fixe (un glyphe = une tuile 8×8, cf. ROADMAP v0.3.2). Le jour où le rendu
proportionnel arrive, aucune police n'est à réimporter — c'est tout l'intérêt
de le stocker maintenant.

Le charset n'est pas un champ : c'est `"".join(g.char for g in glyphs)`. Une
seule source de vérité, et l'écran Police édite directement `Glyph.char` case
par case plutôt qu'une chaîne de 95 caractères.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource


@dataclass
class Glyph:
    """Un caractère et son rectangle dans la planche."""
    char:    str = " "
    x:       int = 0
    y:       int = 0
    w:       int = 8
    h:       int = 8
    advance: int = 8   # largeur d'encre mesurée — pour le rendu proportionnel futur
    ox:      int = 0   # décalage de dessin (BMFont xoffset)
    oy:      int = 0   # décalage de dessin (BMFont yoffset)

    def to_dict(self) -> dict:
        return {"char": self.char, "x": self.x, "y": self.y, "w": self.w,
                "h": self.h, "advance": self.advance, "ox": self.ox, "oy": self.oy}

    @classmethod
    def from_dict(cls, d: dict) -> "Glyph":
        return cls(
            char    = d.get("char", " "),
            x       = int(d.get("x", 0)),
            y       = int(d.get("y", 0)),
            w       = int(d.get("w", 8)),
            h       = int(d.get("h", 8)),
            advance = int(d.get("advance", d.get("w", 8))),
            ox      = int(d.get("ox", 0)),
            oy      = int(d.get("oy", 0)),
        )


@dataclass
class Font(Resource):
    name:  str = "font"
    asset: Optional[str] = None          # planche PNG (relative au projet)
    descriptor: Optional[str] = None     # .fnt BMFont d'origine, si import .fnt
    source_format: str = "png"           # "png" | "fnt" — provenance, affichée à l'écran
    cell_w: int = 8
    cell_h: int = 8
    line_height: int = 8                 # interligne conseillé (BMFont lineHeight)
    glyphs: list[Glyph] = field(default_factory=list)

    # ── Charset — dérivé, jamais stocké ──────────────────────────

    @property
    def charset(self) -> str:
        return "".join(g.char for g in self.glyphs)

    def glyph(self, ch: str) -> Optional[Glyph]:
        return next((g for g in self.glyphs if g.char == ch), None)

    def missing_chars(self, text: str) -> list[str]:
        """Caractères de `text` absents de la police, dédupliqués et ordonnés.

        Le retour à la ligne n'est pas un glyphe : il est traité par le rendu.
        C'est ce qui permet de croiser la police avec la table de textes et de
        signaler les manques AVANT de découvrir le problème sur la console."""
        have = {g.char for g in self.glyphs}
        out: list[str] = []
        for ch in text:
            if ch not in have and ch not in out and ch not in "\n\r":
                out.append(ch)
        return out

    # ── Coût VRAM ────────────────────────────────────────────────

    def tile_count(self) -> int:
        """Nombre de tuiles 8×8 occupées dans le charblock du layer d'UI.

        Un glyphe plus haut ou plus large que 8 px en occupe plusieurs — c'est
        le chiffre à montrer dans l'écran Police, puisque ces tuiles sont en
        concurrence directe avec le décor."""
        total = 0
        for g in self.glyphs:
            total += max(1, (g.w + 7) // 8) * max(1, (g.h + 7) // 8)
        return total

    # ── Persistance ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name":   self.name,
            "asset":  self.asset,
            **({"descriptor": self.descriptor} if self.descriptor else {}),
            "source_format": self.source_format,
            "cell_w": self.cell_w,
            "cell_h": self.cell_h,
            "line_height": self.line_height,
            "glyphs": [g.to_dict() for g in self.glyphs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Font":
        return cls(
            name        = d.get("name", "font"),
            asset       = d.get("asset"),
            descriptor  = d.get("descriptor"),
            source_format = d.get("source_format", "png"),
            cell_w      = int(d.get("cell_w", 8)),
            cell_h      = int(d.get("cell_h", 8)),
            line_height = int(d.get("line_height", d.get("cell_h", 8))),
            glyphs      = [Glyph.from_dict(g) for g in d.get("glyphs", [])],
        )


# Extensions reconnues dans assets/fonts/ — la planche seule, ou le descripteur
# BMFont (dont la page PNG est référencée à l'intérieur).
FONT_FILE_EXTS = {".png", ".fnt"}
