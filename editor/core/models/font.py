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

**`advance` est renseigné dès l'import mais ignoré au rendu v1**, qui est à
chasse fixe (un glyphe = une tuile 8×8, cf. ROADMAP v0.3.2). Le jour où le rendu
proportionnel arrive, aucune police n'est à réimporter — c'est tout l'intérêt
de le stocker maintenant.

**La chasse est DÉCLARÉE, jamais devinée.** Trois sources, par ordre d'autorité :
le `xadvance` d'un `.fnt` (décision typographique de l'auteur) ; sinon le
marqueur d'espacement de la planche s'il a été désigné (`space_color` — la
couleur dit où finit le caractère) ; sinon **mono**, chasse = largeur de cellule.
Pas de repli sur une mesure d'encre : une chasse proportionnelle déduite du
dessin n'a pas de flanc, elle colle les lettres et produit un texte irrégulier
que l'utilisateur devrait rattraper case par case — alors que du mono régulier
est toujours lisible.

Le charset n'est pas un champ : c'est `"".join(g.char for g in glyphs)`. Une
seule source de vérité, et l'écran Police édite directement `Glyph.char` case
par case plutôt qu'une chaîne de 95 caractères.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource


# ── Couleurs-clés ─────────────────────────────────────────────────
# Une planche de police venue d'ailleurs (GB Studio, itch.io) est très souvent
# OPAQUE : pas de canal alpha, un fond plein et parfois une seconde couleur qui
# marque l'espacement entre glyphes. Sans désignation, l'encodeur prend tout
# pour de l'encre et la police sort en pavés pleins.
#
# Stockées en "#RRGGBB" dans le sidecar : un humain relit et corrige un hex,
# pas un triplet d'entiers.

def color_to_hex(rgb: Optional[tuple]) -> Optional[str]:
    if rgb is None:
        return None
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def color_from_hex(s) -> Optional[tuple]:
    """Tolérant : une valeur illisible vaut « pas de couleur-clé » plutôt
    qu'un sidecar qui refuse de se charger."""
    if not isinstance(s, str):
        return tuple(s) if isinstance(s, (list, tuple)) and len(s) == 3 else None
    t = s.strip().lstrip("#")
    if len(t) != 6:
        return None
    try:
        return (int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16))
    except ValueError:
        return None


@dataclass
class Glyph:
    """Un caractère et son rectangle dans la planche."""
    char:    str = " "
    x:       int = 0
    y:       int = 0
    w:       int = 8
    h:       int = 8
    advance: int = 8   # chasse — pour le rendu proportionnel futur (cf. font_import)
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

    # Couleurs de la planche à traiter comme transparentes. Deux champs et non
    # une liste : ils ne se désignent pas au même moment ni pour la même raison
    # (le fond saute aux yeux, l'espacement se découvre en regardant une case),
    # et les nommer permet de les repiquer indépendamment.
    bg_color:    Optional[tuple] = None   # fond de la planche
    space_color: Optional[tuple] = None   # marqueur d'espacement (GB Studio…)

    # ── Charset — dérivé, jamais stocké ──────────────────────────

    @property
    def charset(self) -> str:
        return "".join(g.char for g in self.glyphs)

    # ── Couleurs-clés ────────────────────────────────────────────

    def key_colors(self) -> list[tuple]:
        """Couleurs à rendre transparentes, sans doublon ni None. Point unique
        pour l'éditeur (aperçu), l'import (mesure de chasse) et l'encodeur —
        les trois doivent voir exactement la même transparence, sinon l'aperçu
        ment sur ce qui sortira en ROM."""
        out: list[tuple] = []
        for c in (self.bg_color, self.space_color):
            if c is not None and tuple(c) not in out:
                out.append(tuple(c))
        return out

    def glyph(self, ch: str) -> Optional[Glyph]:
        return next((g for g in self.glyphs if g.char == ch), None)

    # ── Correspondance texte → glyphe ────────────────────────────
    # Un glyphe peut porter PLUSIEURS caractères (ligature : « ... » dessiné
    # d'un bloc). La correspondance se fait donc au PLUS LONG, comme au
    # runtime — sinon « ... » serait rendu par trois points successifs et la
    # ligature ne servirait jamais.

    def match_at(self, text: str, i: int) -> Optional[Glyph]:
        """Glyphe couvrant `text` à partir de `i`, le plus long d'abord."""
        best = None
        for g in self.glyphs:
            if not g.char or not text.startswith(g.char, i):
                continue
            if best is None or len(g.char) > len(best.char):
                best = g
        return best

    def missing_chars(self, text: str) -> list[str]:
        """Caractères de `text` que la police ne sait pas rendre.

        Le retour à la ligne n'est pas un glyphe : il est traité par le rendu.
        C'est ce qui permet de croiser la police avec la table de textes et de
        signaler les manques AVANT de découvrir le problème sur la console.

        Le parcours consomme les ligatures : une police qui a « ... » sans
        avoir « . » couvre bien le texte « ... », et ne doit pas signaler le
        point comme manquant."""
        out: list[str] = []
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch in "\n\r":
                i += 1
                continue
            g = self.match_at(text, i)
            if g is None:
                if ch not in out:
                    out.append(ch)
                i += 1
            else:
                i += len(g.char)
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
            **({"bg_color": color_to_hex(self.bg_color)} if self.bg_color else {}),
            **({"space_color": color_to_hex(self.space_color)} if self.space_color else {}),
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
            bg_color    = color_from_hex(d.get("bg_color")),
            space_color = color_from_hex(d.get("space_color")),
            glyphs      = [Glyph.from_dict(g) for g in d.get("glyphs", [])],
        )


# Extensions reconnues dans assets/fonts/ — la planche seule, ou le descripteur
# BMFont (dont la page PNG est référencée à l'intérieur).
FONT_FILE_EXTS = {".png", ".fnt"}
