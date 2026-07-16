"""BackgroundLayer / BackgroundAsset.
BackgroundImage = simple PNG dans assets/backgrounds/ (pas de JSON).
BackgroundAsset = sidecar d'import dans assets/backgrounds/{name}.json (à côté du PNG)."""

from dataclasses import dataclass, field
from typing import Optional

from core.models.resource import Resource
from core.models.palette import OWN_PAL_BANK
from core.models.sub_palette import SubPaletteAssetMixin, _decode_palette_overrides


@dataclass
class BackgroundLayer:
    """Une couche de fond d'une scène : référence un BackgroundAsset (par nom) +
    slot GBA + vitesse de défilement."""
    background_name: str = ""  # nom du BackgroundAsset référencé (= stem du PNG) ;
                               # le fichier PNG vit sur BackgroundAsset.asset, pas ici
                               # (convention : cf. SpriteComponent.sprite_name)
    bg_slot:      int   = 0    # slot hardware GBA (0-3)
    scroll_speed: float = 1.0  # vitesse relative (1.0 = défilement normal)
    pal_bank:     int   = OWN_PAL_BANK  # slot (0-15) dans scene.active_bg_palettes,
                               # ou OWN_PAL_BANK (-1, défaut) = palette propre du PNG.
                               # Même mécanisme que Actor.pal_bank/Prefab.pal_bank,
                               # mais BG plutôt qu'OBJ ; chaque layer choisit sa
                               # propre banque, indépendamment des autres layers.
    # Overrides de palette PAR TUILE 8×8 (champ SE_PALBANK du hardware GBA) :
    # (col, row) -> slot (0-15) dans scene.active_bg_palettes. Absent = utilise
    # pal_bank (banque de base du layer). Peint depuis le canvas du Scene Manager.
    tile_palette_overrides: dict = field(default_factory=dict)  # dict[tuple[int,int], int]
    visible:      bool  = True   # visibilité VIEWPORT éditeur seule — le codegen
                               # l'ignore (le layer est toujours compilé).


def _decode_tile_palette_overrides(raw) -> dict:
    """Relit tile_palette_overrides du JSON ({"col,row": slot}) en dict[(col,row), slot].
    Tolère l'absence (None) et les clés mal formées (ignorées)."""
    out: dict[tuple[int, int], int] = {}
    if not raw:
        return out
    for key, slot in raw.items():
        try:
            c, r = key.split(",")
            out[(int(c), int(r))] = int(slot)
        except (ValueError, AttributeError):
            continue
    return out


@dataclass
class BackgroundAsset(SubPaletteAssetMixin, Resource):
    """Sidecar d'import d'UNE image de fond — assets/backgrounds/{stem}.json, à côté
    du PNG et keyé par son nom (comme SpriteAsset). Le PNG source n'est jamais modifié.
    C'est la SCÈNE qui possède ses layers (Scene.background_layers) et référence
    ce fond par nom — plus de composition multi-layer réutilisable ici."""
    name:   str  = "background"                     # = stem du PNG source
    asset:   str  = ""                              # PNG dans assets/backgrounds/ (convention .asset, cf. SpriteAsset)
    palettes: list = field(default_factory=list)    # list[list[int]] BGR555 (≤16×≤16)
    tileset:  list = field(default_factory=list)    # list[str] (64 nibbles hex/tuile)
    tilemap:  list = field(default_factory=list)    # list[int] (screen entries GBA)
    tiles_w:  int = 0
    tiles_h:  int = 0
    quantize_method: str = "median_cut"
    # Mode couleur GBA du fond : 4 (jusqu'à 16 sous-palettes de 16, pal_bank par
    # tuile — défaut) ou 8 (une seule palette de 256 couleurs, tuiles en octets,
    # pas d'inpainting). Auto-détecté à l'import (> 256 couleurs -> 8bpp).
    bpp: int = 4
    dither: bool = False   # 8bpp uniquement : dithering du quantifieur (OFF par défaut)
    # Type de fond : "tiled" (Mode 0, tuilé — défaut, cf. bpp) ou "bitmap" (Mode 4,
    # plein écran 240×160, 256 couleurs, SANS tuiles — pour les photos/écrans-titre).
    mode: str = "tiled"
    bitmap: str = ""       # mode bitmap : index 8bpp du buffer (hex, out_w*out_h octets)
    out_w: int = 0         # dimensions du bitmap après ajustement à ≤240×160
    out_h: int = 0
    # BackgroundInpainting (niveau ÉDITEUR, partagé entre scènes) : réassigne la
    # palette (pal_bank local, index dans `palettes`) d'une tuile 8×8. La baseline
    # `tilemap` reste intacte ; `effective_tilemap()` applique ces overrides.
    # Analogue à BackgroundLayer.tile_palette_overrides mais au niveau de l'asset.
    tile_palette_overrides: dict = field(default_factory=dict)  # dict[(col,row), pal_index]
    # Diagnostics de compression (validateur éditeur, non-bloquant) — calculés à
    # la compression, cf. bg_import.encode_background. Le PNG reste intact.
    diagnostics: dict = field(default_factory=dict)
    # Origine des sous-palettes pour l'éditeur (modèle scène : grisé + override).
    # `source_palettes` = snapshot des palettes DÉRIVÉES du PNG à la compression
    # (baseline restaurable). Les indices < len(source_palettes) sont dérivés
    # (grisés/overridables) ; les suivants sont ajoutés depuis le catalogue
    # (éditables). `ba.palettes` reste les couleurs EFFECTIVES (rendu/build
    # inchangés) : une dérivée overridée a ses couleurs = celles du catalogue et
    # son index figure dans `palette_overrides` (idx -> nom de banque catalogue).
    source_palettes: list = field(default_factory=list)    # list[list[int]] BGR555
    palette_overrides: dict = field(default_factory=dict)  # dict[int, str]

    def image_name(self) -> str:
        return self.asset

    def effective_tilemap(self) -> list[int]:
        """Tilemap avec les overrides d'inpainting asset appliqués (pal_bank par
        tuile). La baseline `tilemap` n'est jamais modifiée — c'est ce helper que
        consomment le canvas de scène, le canvas du Background Editor et le build,
        pour que l'inpainting soit partagé partout."""
        if not self.tile_palette_overrides:
            return list(self.tilemap)
        from core.bg_import import unpack_se, pack_se
        tw = self.tiles_w or 1
        out: list[int] = []
        for cell, se in enumerate(self.tilemap):
            tid, pb, fh, fv = unpack_se(se)
            ov = self.tile_palette_overrides.get((cell % tw, cell // tw))
            out.append(pack_se(tid, pb if ov is None else ov, fh, fv))
        return out

    def to_dict(self) -> dict:
        d = {"name": self.name}
        if self.asset:
            d["asset"] = self.asset
        if self.tileset:
            d.update({
                "palettes": self.palettes, "tileset": self.tileset,
                "tilemap": self.tilemap, "tiles_w": self.tiles_w,
                "tiles_h": self.tiles_h, "quantize_method": self.quantize_method,
            })
            if self.tile_palette_overrides:
                d["tile_palette_overrides"] = {
                    f"{c},{r}": s for (c, r), s in self.tile_palette_overrides.items()
                }
            if self.source_palettes:
                d["source_palettes"] = self.source_palettes
            if self.palette_overrides:
                d["palette_overrides"] = {
                    str(i): n for i, n in self.palette_overrides.items()
                }
            if self.diagnostics:
                d["diagnostics"] = self.diagnostics
            if self.bpp != 4:
                d["bpp"] = self.bpp
            if self.dither:
                d["dither"] = True
        if self.mode == "bitmap" and self.bitmap:
            d.update({
                "mode": "bitmap", "bitmap": self.bitmap,
                "out_w": self.out_w, "out_h": self.out_h,
                "palettes": self.palettes,
            })
            if self.diagnostics:
                d["diagnostics"] = self.diagnostics
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BackgroundAsset":
        ba = cls(
            name=d.get("name", "background"),
            asset=d.get("asset", d.get("source", "")),   # rétro-compat: ancienne clé "source"
            palettes=list(d.get("palettes", [])),
            tileset=list(d.get("tileset", [])),
            tilemap=list(d.get("tilemap", [])),
            tiles_w=d.get("tiles_w", 0), tiles_h=d.get("tiles_h", 0),
            quantize_method=d.get("quantize_method", d.get("compress_method", "median_cut")),
            tile_palette_overrides=_decode_tile_palette_overrides(
                d.get("tile_palette_overrides")),
            diagnostics=dict(d.get("diagnostics") or {}),
            bpp=int(d.get("bpp", 4)),
            dither=bool(d.get("dither", False)),
            mode=d.get("mode", "tiled"),
            bitmap=d.get("bitmap", ""),
            out_w=int(d.get("out_w", 0)), out_h=int(d.get("out_h", 0)),
            source_palettes=list(d.get("source_palettes", [])),
            palette_overrides=_decode_palette_overrides(d.get("palette_overrides")),
        )
        # Migration : un fond tuilé sans `source_palettes` (antérieur à l'origine
        # des palettes) prend ses palettes courantes comme baseline dérivée —
        # toutes deviennent grisées/overridables. Idempotent (persisté au save).
        if ba.tileset and not ba.source_palettes and ba.palettes:
            ba.source_palettes = [list(p) for p in ba.palettes]
        # Anciens layers (format multi-layer) — transitoire, lus pour migrer vers
        # Scene.background_layers puis abandonnés (to_dict ne les émet plus).
        ba._legacy_layers = [
            BackgroundLayer(background_name=L.get("image", ""), bg_slot=L.get("bg_slot", i),
                            scroll_speed=L.get("scroll_speed", 1.0),
                            pal_bank=L.get("pal_bank", OWN_PAL_BANK))
            for i, L in enumerate(d.get("layers", []))
        ]
        return ba


# Stub rétrocompat (importé par d'anciens modules)
@dataclass
class Tileset(Resource):
    name: str = "tileset"
    asset: Optional[str] = None
