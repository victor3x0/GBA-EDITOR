"""PaletteBank — une banque de 16 (ou 256) couleurs GBA (pool illimité, catalogue projet)."""

from dataclasses import dataclass, field
from typing import NamedTuple

from core.models.resource import Resource


# Index 0 d'une PaletteBank est réservé — le hardware GBA traite toujours
# l'index de palette 0 comme transparent (OBJ comme BG), quelle que soit la
# couleur RGB qui y est stockée. La valeur exacte n'a donc aucune incidence
# visuelle pour une tuile normale (seul PAL_BG_RAM[0] — banque 0 — a un rôle
# supplémentaire de backdrop, géré séparément via Project/Scene.backdrop_color).
RESERVED_SLOT_COLOR = 0


class PaletteUsage(NamedTuple):
    """Un usage d'une PaletteBank dans le projet — produit par
    `Project.palette_usages()`, affiché par la carte « USAGE » du Palette
    Editor.

    `kind` ∈ {"sprite", "background", "prefab", "scene"} : c'est à la fois le
    type d'élément et la clé de navigation (quel écran ouvrir au clic).
    `detail` explique COMMENT la palette est utilisée (slot, banque, scène
    d'ancrage) — jamais un chemin de fichier."""
    kind: str
    name: str
    detail: str


@dataclass
class PaletteBank(Resource):
    """Une palette nommée de 16 couleurs, catalogue illimité et unifié au
    niveau projet (project/palettes/*.json, un fichier par palette — cf.
    ResourceStore) — partagé entre OBJ et BG, une même palette peut servir
    aux deux. Une Scene en active jusqu'à 16 par pool (Scene.active_obj_palettes
    / active_bg_palettes) ; c'est cette sélection, pas le catalogue, qui
    occupe les banques hardware (physiquement séparées OBJ/BG) au build."""
    name: str = ""
    colors: list[int] = field(default_factory=list)  # valeurs BGR555 GBA
    size: int = 16   # capacité de la palette : 16 (4bpp / une banque) ou 256 (8bpp).
                     # Persisté dans le .json ; absent d'un ancien fichier -> 16.

    def __post_init__(self):
        """Normalise `size` (16 ou 256) et force l'index 0 vers
        RESERVED_SLOT_COLOR — point d'application unique, déclenché à la fois par
        une construction directe (presets, "Ajouter palette" côté UI) et par le
        chargement depuis disque (Resource.from_dict construit via cls(**kwargs)).
        Pas besoin de pas de migration séparé : les anciens fichiers JSON gardent
        leur ancienne valeur d'index 0 tant qu'ils ne sont pas re-sauvegardés,
        mais cette valeur est de toute façon écrasée à chaque chargement — sans
        incidence puisqu'elle n'est jamais affichée pour une tuile (index de
        palette 0 = toujours transparent au niveau hardware, OBJ comme BG)."""
        if self.size not in (16, 256):
            self.size = 16
        if self.colors:
            # On tronque défensivement à la capacité de la banque (un fichier édité
            # à la main pourrait déborder) : en 16, garantit que grit
            # (quantification sur toutes les couleurs) et main_gen (`colors[:16]`)
            # ne divergent jamais (indices >15 impossibles en 4bpp -> tuiles
            # corrompues) ; en 256, borne au maximum 8bpp.
            if len(self.colors) > self.size:
                self.colors = self.colors[:self.size]
            self.colors[0] = RESERVED_SLOT_COLOR

    # ROADMAP v0.24 : les couleurs s'écrivent en #RRGGBB. Seule raison de
    # surcharger les deux méthodes génériques de Resource — le reste de la
    # palette (`name`, `size`) se sérialise très bien tout seul.
    # Une couleur par ligne, et non les seize sur une seule : deux personnes
    # qui retouchent deux couleurs d'une même palette doivent pouvoir fusionner.
    # L'import est LOCAL parce que `gba_color` importe RESERVED_SLOT_COLOR
    # d'ici : la règle de réserve de l'index 0 est une règle de palette et
    # reste chez elle (cf. l'en-tête de gba_color.py). Le cycle se coupe donc
    # du côté qui n'a besoin de l'autre qu'au moment de sérialiser.
    def to_dict(self) -> dict:
        from core.gba_color import write_colors
        d = super().to_dict()
        d["colors"] = write_colors(self.colors)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PaletteBank":
        from core.gba_color import read_colors
        return super().from_dict({**d, "colors": read_colors(d.get("colors", []))})


# Sentinel Actor/Prefab.pal_bank et BackgroundLayer.pal_bank : "Sans palette"
# — l'asset utilise SA PROPRE palette (couleurs du PNG, index 0 transparent),
# extraite à la volée et auto-allouée à une banque libre de la scène au build
# (cf. codegen/palette_alloc.py). C'est le défaut : un asset affiche ses
# couleurs d'origine tant qu'aucune palette du catalogue n'est explicitement
# assignée à ce slot.
OWN_PAL_BANK = -1
