"""PaletteBank — une banque de 16 (ou 256) couleurs GBA (pool illimité, catalogue projet)."""

from dataclasses import dataclass, field

from core.models.resource import Resource


@dataclass
class PaletteBank(Resource):
    """Une palette nommée de 16 couleurs, catalogue illimité et unifié au
    niveau projet (project/palettes/*.json, un fichier par palette — cf.
    ResourceManager) — partagé entre OBJ et BG, une même palette peut servir
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
            from core.color_utils import RESERVED_SLOT_COLOR
            self.colors[0] = RESERVED_SLOT_COLOR


# Sentinel Actor/Prefab.pal_bank et BackgroundLayer.pal_bank : "Sans palette"
# — l'asset utilise SA PROPRE palette (couleurs du PNG, index 0 transparent),
# extraite à la volée et auto-allouée à une banque libre de la scène au build
# (cf. codegen/palette_alloc.py). C'est le défaut : un asset affiche ses
# couleurs d'origine tant qu'aucune palette du catalogue n'est explicitement
# assignée à ce slot.
OWN_PAL_BANK = -1
