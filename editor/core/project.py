"""
GBA Editor — gestion de projet

Structure de projet :

  assets/              ← géré par l'utilisateur
    sprites/           ← PNG + JSON sidecar (auto-créé au dépôt)
    backgrounds/       ← PNG + JSON sidecar
    sounds/            ← WAV, MOD
    sfx/               ← effets sonores
    music/             ← musiques
    fonts/             ← polices
    scripts/           ← Lua (pas de sidecar)
      actors/
      scenes/
      behaviors/

  project/             ← géré exclusivement par l'éditeur
    scenes/            ← une scène par JSON (actors inline)
    prefab/            ← templates d'actors (jamais compilés directement)

  project.json         ← settings globaux (nom, scène de démarrage, auteur)
  build/               ← 100 % jetable (regénéré à chaque build)
"""

import json
import shutil
import copy
import dataclasses
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Optional, Generic, TypeVar, Type, Iterator


_WIN_FORBIDDEN = str.maketrans({c: "_" for c in r'\/:*?"<>|'})

def safe_filename(name: str) -> str:
    """Remplace les caractères interdits dans un nom de fichier Windows."""
    return name.translate(_WIN_FORBIDDEN).strip() or "_"


def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique (tmp → rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)   # atomique sur NTFS/ext4
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ──────────────────────────────────────────────────────────────────
#  Resource — base commune à tous les objets moteur
# ──────────────────────────────────────────────────────────────────

@dataclass
class Resource:
    """
    Base pour tout objet identifié par un nom et stocké en JSON.
    to_dict/from_dict génériques via dataclasses ; les types avec des
    champs imbriqués non-dataclass-natifs (listes d'autres dataclasses)
    peuvent surcharger ces deux méthodes.
    """
    name: str = "resource"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})


T = TypeVar("T", bound=Resource)


# Mime types pour le drag&drop interne à l'éditeur (utilisés par window.py
# et scene_editor.py — définis ici pour éviter un import circulaire entre eux).
MIME_PREFAB_TEMPLATE = "application/x-gba-prefab-template"  # drag Prefab → instancier + placer dans scène
MIME_SCRIPT          = "application/x-gba-script"


# ──────────────────────────────────────────────────────────────────
#  ResourceManager — collection générique de Resource sur disque
# ──────────────────────────────────────────────────────────────────

class ResourceManager(Generic[T]):
    """
    Gère une collection de Resource d'un type donné, persistée dans
    `directory/<name>.json`. Se comporte comme une liste (itération,
    len, indexation, append) pour rester un drop-in replacement des
    anciennes `list[Actor]` / `list[Background]` etc.
    """

    def __init__(self, directory: Path, cls: Type[T]):
        self.dir = directory
        self.cls = cls
        self.items: list[T] = []
        self._pending_delete: list[T] = []

    # -- accès liste --
    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx) -> T:
        return self.items[idx]

    def append(self, item: T) -> T:
        self.items.append(item)
        return item

    def remove(self, item: T):
        if item in self.items:
            self.items.remove(item)

    def __contains__(self, item) -> bool:
        return item in self.items

    # -- lookup --
    def get(self, name: str) -> Optional[T]:
        return next((i for i in self.items if i.name == name), None)

    # -- I/O --
    def _path(self, name: str) -> Path:
        return self.dir / f"{safe_filename(name)}.json"

    def save(self, item: T):
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self._path(item.name), json.dumps(item.to_dict(), indent=2, ensure_ascii=False))

    def save_all(self):
        for item in self.items:
            self.save(item)

    def load(self):
        self.items = []
        if not self.dir.exists():
            return
        for f in sorted(self.dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                self.items.append(self.cls.from_dict(d))
            except Exception as e:
                print(f"[project] erreur lecture {self.cls.__name__} {f.name}: {e}")

    def load_one(self, name: str) -> Optional[T]:
        """Recharge un seul item depuis le disque et met à jour la liste en place."""
        path = self._path(name)
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            new_item = self.cls.from_dict(d)
            for i, item in enumerate(self.items):
                if item.name == name:
                    self.items[i] = new_item
                    return new_item
            self.items.append(new_item)
            return new_item
        except Exception as e:
            print(f"[project] erreur reload {self.cls.__name__} {name}: {e}")
            return None

    def delete(self, item: T):
        """Suppression immédiate (JSON effacé maintenant)."""
        path = self._path(item.name)
        if path.exists():
            path.unlink()
        self.remove(item)
        self._pending_delete = [x for x in self._pending_delete if x is not item]

    def soft_delete(self, item: T):
        """Suppression différée : retire de la liste en mémoire, JSON effacé à la fermeture."""
        self.remove(item)
        if item not in self._pending_delete:
            self._pending_delete.append(item)

    def restore(self, item: T):
        """Annule un soft_delete : remet l'item dans la liste et le resauvegarde."""
        self._pending_delete = [x for x in self._pending_delete if x is not item]
        if item not in self.items:
            self.items.append(item)
        self.save(item)

    def commit_deletes(self):
        """Efface définitivement les JSONs en attente (appeler à la fermeture)."""
        for item in self._pending_delete:
            path = self._path(item.name)
            if path.exists():
                path.unlink()
        self._pending_delete.clear()

    def rename(self, item: T, new_name: str):
        old_path = self._path(item.name)
        if old_path.exists():
            old_path.unlink()
        item.name = new_name
        self.save(item)


# ──────────────────────────────────────────────────────────────────
#  Settings globaux du projet
# ──────────────────────────────────────────────────────────────────

@dataclass
class ProjectSettings:
    name: str = "mon_jeu"
    start_scene: str = ""
    author: str = ""
    version: str = "0.1"
    # Réservoir auto-import (cf. ROADMAP.md v0.2) — réglage projet, pas éditeur.
    palette_auto_import_enabled: bool = True
    # Couleur de backdrop par défaut (BGR555) — PAL_BG_RAM[0], affichée quand
    # rien d'opaque n'est dessiné nulle part. Scene.backdrop_color peut la
    # surcharger par scène. Pas d'écran dédié pour l'instant (même traitement
    # que palette_auto_import_enabled) — édition JSON manuelle en attendant.
    backdrop_color: int = 0


# ──────────────────────────────────────────────────────────────────
#  PaletteBank — une banque de 16 couleurs (pool OBJ, GBA hardware)
# ──────────────────────────────────────────────────────────────────

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

    def __post_init__(self):
        """Force l'index 0 vers RESERVED_SLOT_COLOR — point d'application
        unique, déclenché à la fois par une construction directe (presets,
        "Ajouter palette" côté UI) et par le chargement depuis disque
        (Resource.from_dict construit via cls(**kwargs)). Pas besoin de pas
        de migration séparé : les anciens fichiers JSON gardent leur ancienne
        valeur d'index 0 tant qu'ils ne sont pas re-sauvegardés, mais cette
        valeur est de toute façon écrasée à chaque chargement — sans
        incidence puisqu'elle n'est jamais affichée pour une tuile (index de
        palette 0 = toujours transparent au niveau hardware, OBJ comme BG)."""
        if self.colors:
            # Une banque matérielle = 16 couleurs max (4bpp). Un fichier édité à
            # la main pourrait en contenir davantage ; on tronque défensivement
            # pour que grit (quantification sur toutes les couleurs) et main_gen
            # (`colors[:16]`) ne divergent jamais (indices >15 impossibles en
            # 4bpp -> tuiles corrompues).
            if len(self.colors) > 16:
                self.colors = self.colors[:16]
            from core.color_utils import RESERVED_SLOT_COLOR
            self.colors[0] = RESERVED_SLOT_COLOR


# Sentinel Actor/Prefab.pal_bank et BackgroundLayer.pal_bank : "Sans palette"
# — l'asset utilise SA PROPRE palette (couleurs du PNG, index 0 transparent),
# extraite à la volée et auto-allouée à une banque libre de la scène au build
# (cf. codegen/palette_alloc.py). C'est le défaut : un asset affiche ses
# couleurs d'origine tant qu'aucune palette du catalogue n'est explicitement
# assignée à ce slot.
OWN_PAL_BANK = -1


# ──────────────────────────────────────────────────────────────────
#  GlobalVar — variable globale déclarée explicitement
# ──────────────────────────────────────────────────────────────────

@dataclass
class GlobalVar:
    """Variable globale déclarée explicitement dans le projet."""
    name:    str  = "var"
    type:    str  = "int"   # "int" | "bool"
    default: int  = 0
    desc:    str  = ""      # description optionnelle


# ──────────────────────────────────────────────────────────────────
#  Constant — constante déclarée explicitement (lecture seule)
# ──────────────────────────────────────────────────────────────────

@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle


# ──────────────────────────────────────────────────────────────────
#  BackgroundLayer / BackgroundAsset
#  BackgroundImage = simple PNG dans assets/backgrounds/ (pas de JSON)
#  BackgroundAsset = asset moteur dans project/backgrounds/{name}.json
# ──────────────────────────────────────────────────────────────────

@dataclass
class BackgroundLayer:
    """Une couche d'un BackgroundAsset : image + slot GBA + vitesse de défilement."""
    image:        str   = ""   # nom du fichier PNG dans assets/backgrounds/ (ex: "Sky.png")
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
class BackgroundAsset(Resource):
    """Sidecar de compression d'UNE image de fond — project/backgrounds/{stem}.json,
    keyé par le nom du PNG (comme SpriteAsset). Le PNG source n'est jamais modifié.
    C'est la SCÈNE qui possède ses layers (Scene.background_layers) et référence
    ce fond par nom — plus de composition multi-layer réutilisable ici."""
    name:   str  = "background"                     # = stem du PNG source
    source:  str  = ""                              # PNG dans assets/backgrounds/
    palettes: list = field(default_factory=list)    # list[list[int]] BGR555 (≤16×≤16)
    tileset:  list = field(default_factory=list)    # list[str] (64 nibbles hex/tuile)
    tilemap:  list = field(default_factory=list)    # list[int] (screen entries GBA)
    tiles_w:  int = 0
    tiles_h:  int = 0
    compress_method: str = "median_cut"
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
    # la compression, cf. bg_compress.compress_background. Le PNG reste intact.
    diagnostics: dict = field(default_factory=dict)

    def image_name(self) -> str:
        return self.source

    def effective_tilemap(self) -> list[int]:
        """Tilemap avec les overrides d'inpainting asset appliqués (pal_bank par
        tuile). La baseline `tilemap` n'est jamais modifiée — c'est ce helper que
        consomment le canvas de scène, le canvas du Background Editor et le build,
        pour que l'inpainting soit partagé partout."""
        if not self.tile_palette_overrides:
            return list(self.tilemap)
        from core.bg_compress import unpack_se, pack_se
        tw = self.tiles_w or 1
        out: list[int] = []
        for cell, se in enumerate(self.tilemap):
            tid, pb, fh, fv = unpack_se(se)
            ov = self.tile_palette_overrides.get((cell % tw, cell // tw))
            out.append(pack_se(tid, pb if ov is None else ov, fh, fv))
        return out

    def add_palette_colors(self, colors: list) -> int:
        """Ajoute une sous-palette (copie de ≤16 couleurs BGR555, ex: depuis une
        PaletteBank du catalogue). Retourne son index, ou -1 si déjà 16 palettes."""
        if len(self.palettes) >= 16:
            return -1
        pal = list(colors[:16])
        pal += [0] * (16 - len(pal))
        self.palettes.append(pal)
        return len(self.palettes) - 1

    def replace_palette(self, idx: int, colors: list) -> None:
        """Remplace les couleurs de la sous-palette `idx`."""
        if 0 <= idx < len(self.palettes):
            pal = list(colors[:16])
            pal += [0] * (16 - len(pal))
            self.palettes[idx] = pal

    def clear_palette(self, idx: int) -> None:
        """Vide la sous-palette `idx` (ne garde que l'index 0 réservé) — les
        tuiles qui l'utilisent deviennent transparentes. Ne retire pas la
        palette (indices inchangés), contrairement à remove_palette."""
        if 0 <= idx < len(self.palettes):
            from core.color_utils import RESERVED_SLOT_COLOR
            self.palettes[idx] = [RESERVED_SLOT_COLOR] + [0] * 15

    def remove_palette(self, idx: int) -> None:
        """Supprime la sous-palette `idx` et réconcilie les références : toute
        tuile/override pointant sur `idx` retombe sur 0, les index `> idx` sont
        décrémentés — dans les overrides ET dans les pal_bank de la baseline."""
        if not (0 <= idx < len(self.palettes)):
            return
        self.palettes.pop(idx)

        def _remap(v: int) -> int:
            return 0 if v == idx else (v - 1 if v > idx else v)

        self.tile_palette_overrides = {
            k: _remap(s) for k, s in self.tile_palette_overrides.items()
        }
        from core.bg_compress import unpack_se, pack_se
        for cell, se in enumerate(self.tilemap):
            tid, pb, fh, fv = unpack_se(se)
            self.tilemap[cell] = pack_se(tid, _remap(pb), fh, fv)

    def to_dict(self) -> dict:
        d = {"name": self.name}
        if self.source:
            d["source"] = self.source
        if self.tileset:
            d.update({
                "palettes": self.palettes, "tileset": self.tileset,
                "tilemap": self.tilemap, "tiles_w": self.tiles_w,
                "tiles_h": self.tiles_h, "compress_method": self.compress_method,
            })
            if self.tile_palette_overrides:
                d["tile_palette_overrides"] = {
                    f"{c},{r}": s for (c, r), s in self.tile_palette_overrides.items()
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
            source=d.get("source", ""),
            palettes=list(d.get("palettes", [])),
            tileset=list(d.get("tileset", [])),
            tilemap=list(d.get("tilemap", [])),
            tiles_w=d.get("tiles_w", 0), tiles_h=d.get("tiles_h", 0),
            compress_method=d.get("compress_method", "median_cut"),
            tile_palette_overrides=_decode_tile_palette_overrides(
                d.get("tile_palette_overrides")),
            diagnostics=dict(d.get("diagnostics") or {}),
            bpp=int(d.get("bpp", 4)),
            dither=bool(d.get("dither", False)),
            mode=d.get("mode", "tiled"),
            bitmap=d.get("bitmap", ""),
            out_w=int(d.get("out_w", 0)), out_h=int(d.get("out_h", 0)),
        )
        # Anciens layers (format multi-layer) — transitoire, lus pour migrer vers
        # Scene.background_layers puis abandonnés (to_dict ne les émet plus).
        ba._legacy_layers = [
            BackgroundLayer(image=L.get("image", ""), bg_slot=L.get("bg_slot", i),
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


# ──────────────────────────────────────────────────────────────────
#  SpriteAsset — spritesheet + animations, réutilisable par les Actors
# ──────────────────────────────────────────────────────────────────

@dataclass
class TilePlacement:
    """Une tuile 8×8 du spritesheet source placée à une position dans la frame.
    src_col/src_row : position de la tuile source (grille 8px du PNG).
    dst_col/dst_row : position dans la frame composée (grille 8px de la frame).
    flip_h/flip_v : miroir du contenu de la tuile (pas juste sa position) —
    la GBA n'a pas de flip matériel par tuile au sein d'un OBJ composé, donc
    une version retournée est physiquement générée dans le tileset au build.
    """
    src_col: int = 0
    src_row: int = 0
    dst_col: int = 0
    dst_row: int = 0
    flip_h:  bool = False
    flip_v:  bool = False


@dataclass
class AnimFrame:
    """Une frame = composition de tuiles 8×8 peintes depuis le spritesheet source."""
    tiles: list[TilePlacement] = field(default_factory=list)


@dataclass
class StateDirection:
    """Une séquence de frames pour une direction donnée d'un AnimState.
    dir=0 : override / omnidirectionnel (affiché quelle que soit la direction).
    dir=1..8 : N, NE, E, SE, S, SW, W, NW.
    mirror_of : si défini, hérite les frames de la direction source + applique flip_h/flip_v.
    """
    dir:       int           = 0
    frames:    list[AnimFrame] = field(default_factory=lambda: [AnimFrame()])
    flip_h:    bool          = False
    flip_v:    bool          = False
    mirror_of: Optional[int] = None


@dataclass
class AnimState:
    name: str = "Idle"
    directions: list[StateDirection] = field(
        default_factory=lambda: [StateDirection()]
    )
    speed: int = 8        # ticks GBA (60fps) entre deux frames
    loop: bool = True


@dataclass
class SpriteAsset(Resource):
    """
    Spritesheet PNG + découpage en frames + états d'animation.
    Stocké dans project/sprites/{name}.json
    Référencé par nom depuis Actor.sprite_name.

    Pas de collision ici : la hitbox est portée par CollisionBoxComponent
    sur l'Actor, pas par le sprite (un même sprite peut être utilisé par
    des actors avec des hitbox différentes).
    """
    name: str = "sprite"
    asset: Optional[str] = None
    frame_w: int = 16
    frame_h: int = 16
    states: list[AnimState] = field(default_factory=lambda: [AnimState()])
    # Palette de preview du Sprite Editor mémorisée par sprite (nom de
    # PaletteBank). Purement éditeur — n'affecte pas le build. None = repli DMG.
    preview_palette: Optional[str] = None
    # Compression NON-DESTRUCTIVE du sprite : palette propre (couleurs BGR555
    # ordonnées, index 1..N ; index 0 transparent implicite) dérivée du PNG
    # source SANS le modifier, + l'algo qui l'a produite. Source de vérité de
    # l'indexation (preview + build) — cf. core/color_utils.own_palette_from_source.
    # [] = pas encore calculée (migration au chargement).
    own_palette: list = field(default_factory=list)   # list[int] BGR555
    compress_method: str = "median_cut"

    @property
    def tile_w(self) -> int:
        return max(1, self.frame_w // 8)

    @property
    def tile_h(self) -> int:
        return max(1, self.frame_h // 8)

    @property
    def tiles_per_frame(self) -> int:
        return self.tile_w * self.tile_h

    @property
    def oam_shape(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if fw == fh: return 0
        return 1 if fw > fh else 2

    @property
    def oam_size(self) -> int:
        fw, fh = self.frame_w, self.frame_h
        if self.oam_shape == 0:
            return {8: 0, 16: 1, 32: 2, 64: 3}.get(fw, 1)
        if self.oam_shape == 1:
            return {(16, 8): 0, (32, 8): 1, (32, 16): 2, (64, 32): 3}.get((fw, fh), 0)
        return {(8, 16): 0, (8, 32): 1, (16, 32): 2, (32, 64): 3}.get((fw, fh), 0)

    @property
    def oam_dims(self) -> tuple[int, int]:
        """Retourne (oam_w, oam_h) : taille OAM valide qui contient ce sprite."""
        sh, sz = self.oam_shape, self.oam_size
        if sh == 0:
            s = [8, 16, 32, 64][sz]
            return (s, s)
        if sh == 1:
            return [(16, 8), (32, 8), (32, 16), (64, 32)][sz]
        return [(8, 16), (8, 32), (16, 32), (32, 64)][sz]

    def to_dict(self) -> dict:
        return {
            "name":    self.name,
            "asset":   self.asset,
            "frame_w": self.frame_w,
            "frame_h": self.frame_h,
            **({"preview_palette": self.preview_palette} if self.preview_palette else {}),
            **({"own_palette": self.own_palette,
                "compress_method": self.compress_method} if self.own_palette else {}),
            "states": [
                {
                    "name":  s.name,
                    "speed": s.speed,
                    "loop":  s.loop,
                    "directions": [
                        {
                            "dir":    sd.dir,
                            "frames": [
                                {
                                    "tiles": [
                                        {"src_col": t.src_col, "src_row": t.src_row,
                                         "dst_col": t.dst_col, "dst_row": t.dst_row,
                                         **({"flip_h": True} if t.flip_h else {}),
                                         **({"flip_v": True} if t.flip_v else {})}
                                        for t in f.tiles
                                    ]
                                }
                                for f in sd.frames
                            ],
                            **({"flip_h":    True} if sd.flip_h    else {}),
                            **({"flip_v":    True} if sd.flip_v    else {}),
                            **({"mirror_of": sd.mirror_of} if sd.mirror_of is not None else {}),
                        }
                        for sd in s.directions
                    ],
                }
                for s in self.states
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpriteAsset":
        frame_w = d.get("frame_w", 16)
        frame_h = d.get("frame_h", 16)
        tile_w  = max(1, frame_w // 8)
        tile_h  = max(1, frame_h // 8)

        def _parse_frame(f: dict) -> AnimFrame:
            if "tiles" in f:
                return AnimFrame(tiles=[
                    TilePlacement(
                        src_col=t.get("src_col", 0), src_row=t.get("src_row", 0),
                        dst_col=t.get("dst_col", 0), dst_row=t.get("dst_row", 0),
                        flip_h=t.get("flip_h", False), flip_v=t.get("flip_v", False),
                    )
                    for t in f["tiles"]
                ])
            # Migration ancien format {col, row} → bloc plein de tuiles 8×8
            old_col, old_row = f.get("col", 0), f.get("row", 0)
            return AnimFrame(tiles=[
                TilePlacement(
                    src_col=old_col * tile_w + tx, src_row=old_row * tile_h + ty,
                    dst_col=tx, dst_row=ty,
                )
                for ty in range(tile_h) for tx in range(tile_w)
            ])

        def _parse_state(s: dict) -> AnimState:
            if "directions" in s:
                directions = [
                    StateDirection(
                        dir       = sd.get("dir", 0),
                        frames    = [_parse_frame(f)
                                     for f in sd.get("frames", [{}])] or [AnimFrame()],
                        flip_h    = sd.get("flip_h", False),
                        flip_v    = sd.get("flip_v", False),
                        mirror_of = sd.get("mirror_of", None),
                    )
                    for sd in s["directions"]
                ] or [StateDirection()]
            else:
                directions = [StateDirection(
                    dir    = 0,
                    frames = [_parse_frame(f) for f in s.get("frames", [{}])] or [AnimFrame()],
                )]
            return AnimState(
                name       = s.get("name", "Idle"),
                directions = directions,
                speed      = s.get("speed", 8),
                loop       = s.get("loop", True),
            )

        states = [_parse_state(s) for s in d.get("states", [])] or [AnimState()]
        return cls(
            name      = d.get("name", "sprite"),
            asset     = d.get("asset"),
            frame_w   = frame_w,
            frame_h   = frame_h,
            states    = states,
            preview_palette = d.get("preview_palette"),
            own_palette     = list(d.get("own_palette", [])),
            compress_method = d.get("compress_method", "median_cut"),
        )


# ──────────────────────────────────────────────────────────────────
#  Sfx — effet sonore court
#  Stocké dans project/sfx/{name}.json
#  TODO: champs à définir ensemble (format wav/source brut vs converti
#  Maxmod, volume, pitch...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Sfx(Resource):
    name: str = "sfx"
    asset: Optional[str] = None
    volume: int = 255


# Extensions reconnues dans assets/sfx/ et assets/music/ (fichiers bruts
# sans sidecar) — utilisées à la fois par la resynchronisation au chargement
# du projet (Project.load) et par le ProjectWatcher pour le live-reload.
SFX_FILE_EXTS   = {".wav", ".ogg", ".mp3"}
MUSIC_FILE_EXTS = {".wav", ".mod", ".xm", ".s3m", ".it", ".mp3"}


# ──────────────────────────────────────────────────────────────────
#  Music — piste musicale (boucle de fond)
#  Stocké dans project/music/{name}.json
#  TODO: champs à définir ensemble (module tracker .mod/.s3m via Maxmod,
#  loop point, volume...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Music(Resource):
    name: str = "music"
    asset: Optional[str] = None
    loop: bool = True
    volume: int = 255


# ──────────────────────────────────────────────────────────────────
#  Font — police bitmap pour l'affichage de texte
#  Stocké dans project/fonts/{name}.json
#  TODO: champs à définir ensemble (charset, largeur fixe/variable,
#  spritesheet glyphes...).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Font(Resource):
    name: str = "font"
    asset: Optional[str] = None


# ──────────────────────────────────────────────────────────────────
#  Components — briques attachables à un Actor (système type ECS)
#  Un Actor a une liste de composants ; plusieurs instances du même
#  type sont autorisées (ex: CollisionBox "ground_check" + "sword_hitbox").
#  Chaque composant a un `id` (label libre, unique au sein de l'actor)
#  et un flag `active` pour le désactiver sans le retirer.
# ──────────────────────────────────────────────────────────────────

@dataclass
class CollisionBoxComponent:
    """
    Boîte de collision AABB attachée à un Actor.

    solid=True  → résolution physique (repousse les autres actors solides)
    solid=False → trigger pur : détecte les overlaps sans bloquer

    Callbacks Lua appelés par le runtime C :
        onCollisionEnter(other_id)  — actor solide entre en contact
        onCollisionExit(other_id)   — contact rompu
        onTriggerEnter(other_id)    — actor entre dans la zone trigger
        onTriggerExit(other_id)     — actor quitte la zone trigger

    other_id = index de l'actor dans actors[] (table Lua de la scène).

    tag : label libre pour que le script distingue plusieurs colliders
          sur un même actor (ex: "body", "sword_hitbox", "ground_check").
    """
    id: str = "collision"
    active: bool = True
    solid: bool = True      # True = physique, False = trigger
    tag: str = "body"       # ex: "body", "ground_check", "hitbox", "hurtbox"
    x: int = 0              # offset relatif au pivot du sprite (pixels)
    y: int = 0
    w: int = 16
    h: int = 16
    # Callbacks Lua à déclencher (chaîne vide = pas de callback)
    on_collision_enter: str = "onCollisionEnter"
    on_collision_exit:  str = "onCollisionExit"
    on_trigger_enter:   str = "onTriggerEnter"
    on_trigger_exit:    str = "onTriggerExit"


@dataclass
class SpriteComponent:
    id: str = "sprite"
    active: bool = True
    sprite_name: Optional[str] = None   # référence SpriteAsset.name
    initial_state: str = "Idle"         # nom de l'AnimState joué au démarrage
    auto_dir: bool = True               # calcule dir depuis vélocité automatiquement
    scale_x: float = 1.0               # affine OAM (1.0 = normal)
    scale_y: float = 1.0
    rotation: int = 0                  # degrés 0–359 (OAM affine)

    def __post_init__(self):
        self.scale_x  = float(self.scale_x)
        self.scale_y  = float(self.scale_y)
        self.rotation = int(self.rotation)


@dataclass
class SoundFxComponent:
    """
    Associe un Sfx à un actor.
    trigger="manual"   : ne joue rien automatiquement — appeler self:play_sfx() depuis un script.
    trigger="on_spawn" : joue automatiquement au démarrage de l'actor (on_start), sans script.
    """
    id: str = "sound_fx"
    active: bool = True
    sfx_name: Optional[str] = None      # référence Sfx.name
    trigger: str = "manual"             # "manual" | "on_spawn"


@dataclass
class ScriptComponent:
    id: str = "script"
    active: bool = True
    script: Optional[str] = None        # chemin relatif vers le .lua
    exports_values: dict = field(default_factory=dict)  # valeurs overrides par instance


# Registre type-name -> classe, utilisé pour la (dé)sérialisation
# polymorphe et pour piloter le menu "+ Component" de l'UI.
COMPONENT_REGISTRY: dict = {
    "collision_box": CollisionBoxComponent,
    "sprite":        SpriteComponent,
    "sound_fx":      SoundFxComponent,
    "script":        ScriptComponent,
}


def component_type_name(comp) -> str:
    """Nom de type (clé COMPONENT_REGISTRY) d'une instance de composant."""
    for type_name, klass in COMPONENT_REGISTRY.items():
        if isinstance(comp, klass):
            return type_name
    raise ValueError(f"Composant de type inconnu : {comp!r}")



def _components_to_list(components: list) -> list[dict]:
    """Sérialise une liste de Component polymorphes (utilisé par Actor ET Prefab)."""
    return [
        {"component_type": component_type_name(c), **dataclasses.asdict(c)}
        for c in components
    ]


def _components_from_list(data: list) -> list:
    """Inverse de _components_to_list."""
    components = []
    for cd in data:
        cd = dict(cd)
        type_name = cd.pop("component_type", None)
        klass = COMPONENT_REGISTRY.get(type_name)
        if not klass:
            continue
        valid = {f.name for f in fields(klass)}
        components.append(klass(**{k: v for k, v in cd.items() if k in valid}))
    return components


class ComponentOwnerMixin:
    """
    Mixin pour tout objet possédant une liste `components` de type ECS
    (Actor et Prefab). Fournit la manipulation des composants ; chaque
    classe garde son propre to_dict/from_dict (chemins/dossiers différents).
    """

    def get_component(self, comp_type: str):
        """Premier composant du type donné (ou None)."""
        klass = COMPONENT_REGISTRY[comp_type]
        return next((c for c in self.components if isinstance(c, klass)), None)

    def add_component(self, comp_type: str, **kwargs):
        klass = COMPONENT_REGISTRY[comp_type]
        comp = klass(**kwargs)
        # Garantir un id unique au sein de l'actor (ex: "collision", "collision_2", ...)
        existing_ids = {c.id for c in self.components}
        if comp.id in existing_ids:
            n = 2
            base = comp.id
            while f"{base}_{n}" in existing_ids:
                n += 1
            comp.id = f"{base}_{n}"
        self.components.append(comp)
        return comp


# ──────────────────────────────────────────────────────────────────
#  Prefab — template réutilisable. Stocké dans project/prefab/{name}.json.
#  Jamais compilé ni placé directement dans une scène.
#  Instancier un Prefab = copie ponctuelle de ses Components dans un
#  nouvel Actor inline (aucun lien vivant après la création).
# ──────────────────────────────────────────────────────────────────

@dataclass
class Prefab(Resource, ComponentOwnerMixin):
    name: str = "Prefab"
    components: list = field(default_factory=list)
    pal_bank: int = OWN_PAL_BANK   # -1 = palette propre du sprite (défaut)
    max_instances: int = 0   # 0 = non-spawnable ; N = copies simultanées max

    def to_dict(self) -> dict:
        return {
            "name":          self.name,
            "components":    _components_to_list(self.components),
            "pal_bank":      self.pal_bank,
            "max_instances": self.max_instances,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Prefab":
        return cls(
            name          = d.get("name", "Prefab"),
            components    = _components_from_list(d.get("components", [])),
            pal_bank      = d.get("pal_bank", OWN_PAL_BANK),
            max_instances = d.get("max_instances", d.get("pool_size", 0)),  # compat anciens JSON
        )


# ──────────────────────────────────────────────────────────────────
#  Actor — entité inline dans une scène.
#  Stocké directement dans le JSON de la scène (pas de fichier séparé).
#  Porte ses Components (sprite, collision, script…) ET son transform
#  de placement dans la scène (x, y, flip, priority…).
#  prefab_name est purement informatif : si l'actor a été créé depuis
#  un Prefab, il indique lequel — aucun lien vivant après la création.
# ──────────────────────────────────────────────────────────────────

@dataclass
class Actor(ComponentOwnerMixin):
    name: str = "Actor"
    prefab_name: Optional[str] = None
    active: bool = True
    components: list = field(default_factory=list)
    # Transform / placement dans la scène
    x: int = 112
    y: int = 72
    flip_h: bool = False
    flip_v: bool = False
    priority: int = 0
    pal_bank: int = OWN_PAL_BANK   # -1 = palette propre du sprite (défaut)
    visible: bool = True
    # Direction initiale discrète (-1|0|1 × -1|0|1) : oriente le sprite affiché
    # dans l'éditeur et initialise dir_x/dir_y de l'Actor au runtime. (0,0)=omni.
    dir_x: int = 0
    dir_y: int = 0

    def to_dict(self) -> dict:
        return {
            "name":        self.name,
            "prefab_name": self.prefab_name,
            "active":      self.active,
            "components":  _components_to_list(self.components),
            "x":           self.x,
            "y":           self.y,
            "flip_h":      self.flip_h,
            "flip_v":      self.flip_v,
            "priority":    self.priority,
            "pal_bank":    self.pal_bank,
            "visible":     self.visible,
            "dir_x":       self.dir_x,
            "dir_y":       self.dir_y,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Actor":
        return cls(
            name        = d.get("name", "Actor"),
            prefab_name = d.get("prefab_name"),
            active      = d.get("active", True),
            components  = _components_from_list(d.get("components", [])),
            x           = d.get("x", 112),
            y           = d.get("y", 72),
            flip_h      = d.get("flip_h", False),
            flip_v      = d.get("flip_v", False),
            priority    = d.get("priority", 0),
            pal_bank    = d.get("pal_bank", OWN_PAL_BANK),
            visible     = d.get("visible", True),
            dir_x       = d.get("dir_x", 0),
            dir_y       = d.get("dir_y", 0),
        )


# ──────────────────────────────────────────────────────────────────
#  SceneLayer — un BG layer dans une scène
# ──────────────────────────────────────────────────────────────────
#  Collision map — types de tiles 8×8
# ──────────────────────────────────────────────────────────────────

TILE_EMPTY      = 0   # passable
TILE_SOLID      = 1   # bloc plein
TILE_SLOPE_L    = 2   # ◥  45° sol montant  L→R
TILE_SLOPE_R    = 3   # ◤  45° sol descendant L→R
TILE_SLOPE_L_LO = 4   # ◢  ~26° sol montant, tile gauche (bas)
TILE_SLOPE_L_HI = 5   # ◥½ ~26° sol montant, tile droite (haut)
TILE_SLOPE_R_LO = 6   # ◣  ~26° sol descendant, tile droite (bas)
TILE_SLOPE_R_HI = 7   # ◤½ ~26° sol descendant, tile gauche (haut)
# Plafond — miroir vertical des sols
TILE_SLOPE_L_INV    = 8   # ◣  45° plafond montant  L→R
TILE_SLOPE_R_INV    = 9   # ◢  45° plafond descendant L→R
TILE_SLOPE_L_LO_INV = 10  # ~26° plafond montant, tile gauche
TILE_SLOPE_L_HI_INV = 11  # ~26° plafond montant, tile droite
TILE_SLOPE_R_LO_INV = 12  # ~26° plafond descendant, tile droite
TILE_SLOPE_R_HI_INV = 13  # ~26° plafond descendant, tile gauche
# Pentes raides sol (>45°, X=1 Y=2) — paires HI (petit triangle) + LO (grand quadrilatère)
TILE_SLOPE_R_STEEP_HI     = 14  # ~63° sol descendant L→R, tile haut (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO     = 15  # ~63° sol descendant L→R, tile bas  (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI     = 16  # ~63° sol montant  L→R, tile haut (petit triangle droit)
TILE_SLOPE_L_STEEP_LO     = 17  # ~63° sol montant  L→R, tile bas  (grand quadrilatère droit)
# Pentes raides plafond (miroir vertical)
TILE_SLOPE_R_STEEP_HI_INV = 18  # ~63° plafond descendant L→R, tile bas  (petit triangle gauche)
TILE_SLOPE_R_STEEP_LO_INV = 19  # ~63° plafond descendant L→R, tile haut (grand quadrilatère gauche)
TILE_SLOPE_L_STEEP_HI_INV = 20  # ~63° plafond montant  L→R, tile bas  (petit triangle droit)
TILE_SLOPE_L_STEEP_LO_INV = 21  # ~63° plafond montant  L→R, tile haut (grand quadrilatère droit)

COLLISION_TILE_SIZE = 8   # pixels par tile de collision

def make_collision_map(width_px: int, height_px: int) -> list[list[int]]:
    """Crée une grille vide (TILE_EMPTY) aux dimensions de la scène en pixels."""
    cols = max(1, (width_px  + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    rows = max(1, (height_px + COLLISION_TILE_SIZE - 1) // COLLISION_TILE_SIZE)
    return [[TILE_EMPTY] * cols for _ in range(rows)]


# ──────────────────────────────────────────────────────────────────

# Stub rétrocompat
@dataclass
class SceneLayer:
    bg: int = 0
    background_name: str = ""
    scroll_speed: float = 1.0


# ──────────────────────────────────────────────────────────────────
#  Scene — une scène complète
# ──────────────────────────────────────────────────────────────────

@dataclass
class Scene(Resource):
    name: str = "Scene"
    # Layers de fond de CETTE scène (inline dans le JSON) — chaque layer référence
    # un BackgroundAsset (sidecar de compression) par son nom d'image.
    background_layers: list = field(default_factory=list)  # list[BackgroundLayer]
    actors: list = field(default_factory=list)  # list[Actor], inline dans le JSON
    cam_x: int = 0
    cam_y: int = 0
    cam_follow: str = ""   # nom de l'Actor à suivre ("" = caméra libre)
    scroll_h: bool = True  # défilement horizontal activé
    scroll_v: bool = False # défilement vertical activé
    # Mode vidéo GBA de la scène (0-5). 0 = 4 fonds tuilés réguliers (défaut) ;
    # 1/2 = tuilé + affine ; 3/4/5 = un fond bitmap plein écran (BG2). Pilote
    # l'inspecteur (zones background/palettes). cf. ui MODE_INFO.
    render_mode: int = 0
    script: str = ""       # chemin relatif vers le script Lua de la scène ("" = aucun)
    text_bg: int = 1       # BG hardware (0-3) utilisé pour le calque texte TTE
    collision_layer: int = 0  # index BG (0-3) portant la carte de collisions
    # Grille de collision en tiles 8×8 — list[row][col] de TILE_* constants
    collision_map: list = field(default_factory=list)
    # Palettes actives de cette scène — noms référençant project.obj_palettes/
    # bg_palettes (catalogue illimité). Ordre = index de banque hardware
    # (slot 0 = 1er élément). Actor/Prefab.pal_bank indexe dans CETTE liste,
    # pas directement le catalogue projet.
    active_obj_palettes: list = field(default_factory=list)  # list[str]
    active_bg_palettes:  list = field(default_factory=list)  # list[str]
    # Override de ProjectSettings.backdrop_color pour cette scène (BGR555) ;
    # None = hérite du défaut projet.
    backdrop_color: Optional[int] = None

    def ensure_collision_map(self, width_px: int = 240, height_px: int = 160):
        """Initialise ou redimensionne la collision_map si vide."""
        if not self.collision_map:
            self.collision_map = make_collision_map(width_px, height_px)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background_layers": [
                {"image": L.image, "bg_slot": L.bg_slot,
                 "scroll_speed": L.scroll_speed, "pal_bank": L.pal_bank,
                 **({"tile_palette_overrides": {f"{c},{r}": s
                                       for (c, r), s in L.tile_palette_overrides.items()}}
                    if L.tile_palette_overrides else {}),
                 **({} if L.visible else {"visible": False})}
                for L in self.background_layers
            ],
            "actors": [a.to_dict() for a in self.actors],
            "cam_x": self.cam_x,
            "cam_y": self.cam_y,
            "cam_follow": self.cam_follow,
            "render_mode": self.render_mode,
            "scroll_h": self.scroll_h,
            "scroll_v": self.scroll_v,
            "script": self.script,
            "text_bg": self.text_bg,
            "collision_layer": self.collision_layer,
            "collision_map": self.collision_map,
            "active_obj_palettes": self.active_obj_palettes,
            "active_bg_palettes": self.active_bg_palettes,
            "backdrop_color": self.backdrop_color,
        }

    @classmethod
    def from_dict(cls, d: dict, legacy_actors: dict = None) -> "Scene":
        """
        legacy_actors : dict nom→Actor chargé depuis project/actors/ (anciens projets).
        Si présent, les entrées `instances[actor_name]` sont converties en Actor inline.
        """
        # Layers de la scène (nouveau format). L'ancien `background_asset` (nom
        # d'un BackgroundAsset multi-layer) est migré au niveau projet
        # (Project._migrate_scene_backgrounds) car il faut lire cet asset.
        bg_layers = [
            BackgroundLayer(
                image        = L.get("image", ""),
                bg_slot      = L.get("bg_slot", i),
                scroll_speed = L.get("scroll_speed", 1.0),
                pal_bank     = L.get("pal_bank", OWN_PAL_BANK),
                # Migration : ancienne clé "tile_palettes" (avant l'harmonisation
                # de nomenclature) relue pour préserver les scènes déjà peintes.
                tile_palette_overrides= _decode_tile_palette_overrides(
                    L.get("tile_palette_overrides") or L.get("tile_palettes")),
                visible      = L.get("visible", True),
            )
            for i, L in enumerate(d.get("background_layers", []))
        ]

        # Nouveau format : acteurs inline
        if "actors" in d:
            actors = [Actor.from_dict(a) for a in d["actors"]]
        else:
            # Ancien format : instances avec actor_name → migration automatique
            actors = []
            for sa in d.get("instances", []):
                name = sa.get("actor_name", "") or sa.get("name", "Actor")
                base = (legacy_actors or {}).get(name)
                actors.append(Actor(
                    name        = name,
                    prefab_name = base.prefab_name if base else None,
                    active      = base.active if base else True,
                    components  = copy.deepcopy(base.components) if base else [],
                    x           = sa.get("x", 112),
                    y           = sa.get("y", 72),
                    flip_h      = sa.get("flip_h", False),
                    flip_v      = sa.get("flip_v", False),
                    priority    = sa.get("priority", 0),
                    pal_bank    = sa.get("pal_bank", OWN_PAL_BANK),
                    visible     = sa.get("visible", True),
                ))

        scene = cls(
            name=d.get("name", "Scene"),
            background_layers=bg_layers,
            actors=actors,
            cam_x=d.get("cam_x", 0),
            cam_y=d.get("cam_y", 0),
            cam_follow=d.get("cam_follow", ""),
            render_mode=int(d.get("render_mode", 0)),
            scroll_h=d.get("scroll_h", True),
            scroll_v=d.get("scroll_v", False),
            script=d.get("script", ""),
            text_bg=d.get("text_bg", 1),
            collision_layer=d.get("collision_layer", 0),
            collision_map=d.get("collision_map", []),
            active_obj_palettes=d.get("active_obj_palettes", []),
            active_bg_palettes=d.get("active_bg_palettes", []),
            backdrop_color=d.get("backdrop_color"),
        )
        # Ancien nom de BackgroundAsset (migré au load si background_layers vide).
        scene._legacy_bg_asset = d.get("background_asset", "")
        if not scene._legacy_bg_asset and "bg_layers" in d:   # très ancien format
            for L in d["bg_layers"]:
                if L.get("background_name"):
                    scene._legacy_bg_asset = L["background_name"]
                    break
        scene.ensure_collision_map()
        return scene


# ──────────────────────────────────────────────────────────────────
#  Project — conteneur principal
# ──────────────────────────────────────────────────────────────────

class Project:
    """
    Représente un projet GBA ouvert.
    Chemins canoniques et I/O vers le disque.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.settings = ProjectSettings(name=root.name)

        self.backgrounds: ResourceManager[BackgroundAsset] = ResourceManager(self.backgrounds_dir, BackgroundAsset)
        self.sprites:     ResourceManager[SpriteAsset]     = ResourceManager(self.sprites_dir, SpriteAsset)
        self.prefabs:     ResourceManager[Prefab]      = ResourceManager(self.prefab_dir, Prefab)
        self.scenes:      ResourceManager[Scene]       = ResourceManager(self.scenes_dir, Scene)
        self.sfx:         ResourceManager[Sfx]         = ResourceManager(self.sfx_dir, Sfx)
        self.music:       ResourceManager[Music]       = ResourceManager(self.music_dir, Music)
        self.fonts:       ResourceManager[Font]        = ResourceManager(self.fonts_dir, Font)
        self.palettes: ResourceManager[PaletteBank] = ResourceManager(self.palettes_dir, PaletteBank)

        # Variables globales déclarées explicitement dans le projet
        self.globals:     list[GlobalVar] = []

        # Constantes déclarées explicitement dans le projet (lecture seule)
        self.constants:   list[Constant] = []

        # Scène active (index dans self.scenes)
        self._active_scene_idx: int = 0

    # ── Chemins canoniques ────────────────────────────────────────

    @property
    def assets_dir(self) -> Path:
        """Espace libre utilisateur — PNGs bruts, sons..."""
        return self.root / "assets"

    @property
    def project_dir(self) -> Path:
        """Objets moteur (scenes, actors, sprites, tilesets, backgrounds, scripts)."""
        return self.root / "project"

    @property
    def scenes_dir(self) -> Path:
        return self.project_dir / "scenes"

    @property
    def prefab_dir(self) -> Path:
        return self.project_dir / "prefab"

    @property
    def variables_file(self) -> Path:
        """Globals + constants du projet — project/variables.json (pas de dépendance externe)."""
        return self.project_dir / "variables.json"

    @property
    def legacy_palettes_file(self) -> Path:
        """Ancien catalogue monolithique (pré-migration) — project/palettes.json."""
        return self.project_dir / "palettes.json"

    @property
    def palettes_dir(self) -> Path:
        """Catalogue de palettes unifié (illimité, partagé OBJ/BG) — project/palettes/*.json."""
        return self.project_dir / "palettes"

    @property
    def legacy_obj_palettes_dir(self) -> Path:
        """Ancien pool OBJ séparé (pré-fusion) — project/palettes/obj/."""
        return self.project_dir / "palettes" / "obj"

    @property
    def legacy_bg_palettes_dir(self) -> Path:
        """Ancien pool BG séparé (pré-fusion) — project/palettes/bg/."""
        return self.project_dir / "palettes" / "bg"

    @property
    def sprites_dir(self) -> Path:
        return self.assets_dir / "sprites"

    @property
    def tilesets_dir(self) -> Path:
        return self.assets_dir / "backgrounds"

    @property
    def backgrounds_dir(self) -> Path:
        """Dossier des BackgroundAssets (JSON moteur)."""
        return self.project_dir / "backgrounds"

    @property
    def background_images_dir(self) -> Path:
        """Dossier des images brutes PNG background."""
        return self.assets_dir / "backgrounds"

    @property
    def sfx_dir(self) -> Path:
        return self.assets_dir / "sfx"

    @property
    def music_dir(self) -> Path:
        return self.assets_dir / "music"

    @property
    def fonts_dir(self) -> Path:
        return self.assets_dir / "fonts"

    @property
    def scripts_dir(self) -> Path:
        return self.assets_dir / "scripts"

    @property
    def scripts_actors_dir(self) -> Path:
        return self.scripts_dir / "actors"

    @property
    def scripts_behaviors_dir(self) -> Path:
        return self.scripts_dir / "behaviors"

    @property
    def scripts_scenes_dir(self) -> Path:
        return self.scripts_dir / "scenes"

    @property
    def build_dir(self) -> Path:
        return self.root / "build"

    @property
    def grit_out_dir(self) -> Path:
        return self.build_dir / "grit_out"

    @property
    def src_dir(self) -> Path:
        return self.build_dir / "src"

    @property
    def obj_dir(self) -> Path:
        return self.build_dir / "obj"

    @property
    def makefile_path(self) -> Path:
        return self.build_dir / "Makefile"

    @property
    def rom_path(self) -> Path:
        return self.build_dir / "rom.gba"

    @property
    def project_file(self) -> Path:
        return self.root / "project.json"

    # ── Scène active ──────────────────────────────────────────────

    @property
    def active_scene(self) -> Optional[Scene]:
        if not self.scenes:
            return None
        idx = max(0, min(self._active_scene_idx, len(self.scenes) - 1))
        return self.scenes[idx]

    def set_active_scene(self, index: int):
        self._active_scene_idx = max(0, min(index, len(self.scenes) - 1))
        if self.active_scene:
            self.settings.start_scene = self.active_scene.name
            self.save_settings()

    # ── Résolution des assets ─────────────────────────────────────

    def asset_abs(self, rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        p = Path(rel)
        return (self.root / p).resolve() if not p.is_absolute() else p

    def asset_rel(self, abs_path: Path) -> str:
        try:
            return str(abs_path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return f"assets/{abs_path.name}"

    def import_asset(self, src: Path, subdir: str = "") -> Path:
        """
        Copie un fichier dans assets/{subdir}/.
        Retourne le chemin absolu dans le projet.
        """
        dst_dir = self.assets_dir / subdir if subdir else self.assets_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    def sync_sprite_png(self, png_path: Path) -> "SpriteAsset":
        """
        Appelé quand un PNG apparaît dans assets/sprites/.
        Crée le sidecar JSON à côté si absent, l'ajoute à self.sprites si nécessaire.
        Retourne le SpriteAsset correspondant.
        """
        name = png_path.stem
        sprite = self.sprites.get(name)
        if sprite is None:
            sprite = SpriteAsset(
                name=name,
                asset=self.asset_rel(png_path),
                frame_w=8,
                frame_h=8,
            )
            # Nouveau dépôt uniquement : on calcule la compression (palette propre)
            # en MÉTADONNÉES, sans jamais toucher le PNG source (cap non-destructif).
            # Un sprite déjà connu n'est jamais recompressé automatiquement.
            sprite.own_palette = self._derive_own_palette(png_path, sprite.compress_method)
            self.sprites.append(sprite)
        sidecar = png_path.with_suffix(".json")
        if not sidecar.exists():
            self.sprites.save(sprite)
        return sprite

    @staticmethod
    def _derive_own_palette(png_path, method: str = "median_cut") -> list:
        """Palette propre (compression BGR555 ordonnée) d'un PNG source, calculée
        SANS modifier le fichier. [] si illisible. cf.
        core/color_utils.own_palette_from_source."""
        try:
            from core.color_utils import own_palette_from_source
            return own_palette_from_source(png_path, method=method)
        except Exception:
            return []

    def remove_sprite_png(self, png_path: Path):
        """PNG supprimé de assets/sprites/ : suppression différée du JSON."""
        sprite = self.sprites.get(png_path.stem)
        if sprite:
            self.sprites.soft_delete(sprite)

    def remove_background_png(self, png_path: Path):
        """PNG supprimé de assets/backgrounds/ : suppression différée du JSON."""
        bg = self.backgrounds.get(png_path.stem)
        if bg:
            self.backgrounds.soft_delete(bg)

    def remove_sfx_file(self, path: Path):
        """Fichier audio supprimé de assets/sfx/ : suppression différée du JSON."""
        sfx = self.sfx.get(path.stem)
        if sfx:
            self.sfx.soft_delete(sfx)

    def remove_music_file(self, path: Path):
        """Fichier audio supprimé de assets/music/ : suppression différée du JSON."""
        music = self.music.get(path.stem)
        if music:
            self.music.soft_delete(music)

    def sync_sfx_file(self, path: Path) -> "Sfx":
        """
        Appelé quand un fichier audio apparaît dans assets/sfx/.
        Crée le sidecar JSON à côté si absent, l'ajoute à self.sfx si nécessaire.
        """
        name = path.stem
        sfx = self.sfx.get(name)
        if sfx is None:
            sfx = Sfx(name=name, asset=self.asset_rel(path))
            self.sfx.append(sfx)
        sidecar = path.with_suffix(".json")
        if not sidecar.exists():
            self.sfx.save(sfx)
        return sfx

    def sync_music_file(self, path: Path) -> "Music":
        """
        Appelé quand un fichier audio apparaît dans assets/music/.
        Crée le sidecar JSON à côté si absent, l'ajoute à self.music si nécessaire.
        """
        name = path.stem
        music = self.music.get(name)
        if music is None:
            music = Music(name=name, asset=self.asset_rel(path))
            self.music.append(music)
        sidecar = path.with_suffix(".json")
        if not sidecar.exists():
            self.music.save(music)
        return music

    def commit_all_removals(self):
        """Efface définitivement tous les JSONs en attente (appeler à la fermeture)."""
        for mgr in (self.sprites, self.backgrounds, self.sfx, self.music,
                    self.fonts, self.scenes, self.prefabs):
            mgr.commit_deletes()

    def sync_background_png(self, png_path: Path):
        """Crée un BackgroundAsset (sidecar de compression par image, keyé par le
        stem du PNG) quand un PNG apparaît dans assets/backgrounds/. Ne modifie
        pas un asset existant. C'est la scène qui possède ses layers."""
        name = png_path.stem
        if self.backgrounds.get(name) is None:
            ba = BackgroundAsset(name=name, source=png_path.name)
            # Nouveau dépôt : compression (métadonnées) sans toucher le PNG.
            self._compress_background_asset(ba, png_path)
            self.backgrounds.append(ba)
            self.backgrounds.save(ba)

    @staticmethod
    def apply_bg_compression(ba: "BackgroundAsset", source_name: str, c: dict):
        """Applique un résultat de compression (dict de bg_compress.compress_background)
        à un BackgroundAsset. Séparé du calcul pour permettre une compression
        hors-thread : le worker calcule `c`, le thread UI applique via ce helper."""
        ba.source = source_name
        ba.palettes = c["palettes"]
        ba.diagnostics = c.get("diagnostics", {})
        ba.bpp = c.get("bpp", 4)
        ba.mode = c.get("mode", "tiled")
        if ba.mode == "bitmap":
            ba.bitmap = c["bitmap"]
            ba.out_w = c["out_w"]
            ba.out_h = c["out_h"]
            # Pas de représentation tuilée en bitmap.
            ba.tileset = []
            ba.tilemap = []
            ba.tiles_w = 0
            ba.tiles_h = 0
            ba.tile_palette_overrides = {}
        else:
            ba.tileset = c["tileset"]
            ba.tilemap = c["tilemap"]
            ba.tiles_w = c["tiles_w"]
            ba.tiles_h = c["tiles_h"]
            ba.compress_method = c["compress_method"]
            ba.bitmap = ""
            ba.out_w = 0
            ba.out_h = 0

    @staticmethod
    def _compress_background_asset(ba: "BackgroundAsset", png_path: Path, method: str = None):
        """Calcule et stocke la compression GBA d'un fond (palettes/tileset/tilemap)
        depuis son PNG — sans modifier le fichier. cf. core/bg_compress. No-op si
        illisible. Chemin SYNCHRONE (import via watcher, reconcile au chargement)."""
        try:
            from core.bg_compress import compress_background
            c = compress_background(png_path, method=method or ba.compress_method)
            Project.apply_bg_compression(ba, png_path.name, c)
        except Exception:
            pass

    # ── Helpers de lookup ────────────────────────────────────────

    def get_background(self, name: str) -> Optional[BackgroundAsset]:
        return self.backgrounds.get(name)

    def get_sprite(self, name: str) -> Optional[SpriteAsset]:
        return self.sprites.get(name)

    def get_prefab(self, name: str) -> Optional[Prefab]:
        return self.prefabs.get(name)

    def get_palette(self, name: str) -> Optional[PaletteBank]:
        return self.palettes.get(name)

    def instantiate_actor_from_prefab(self, prefab: Prefab, name: str,
                                       x: int = 112, y: int = 72) -> Actor:
        """Crée un Actor inline depuis un Prefab (copie des Components, aucun lien vivant)."""
        return Actor(
            name        = name,
            prefab_name = prefab.name,
            active      = True,
            components  = copy.deepcopy(prefab.components),
            x=x, y=y,
        )

    # ── Build ─────────────────────────────────────────────────────

    def prepare_build(self):
        for d in (self.grit_out_dir, self.src_dir):
            if d.exists():
                shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
        self.obj_dir.mkdir(parents=True, exist_ok=True)

    # ── I/O settings globaux ──────────────────────────────────────

    def save_settings(self):
        data = {
            "name":        self.settings.name,
            "start_scene": self.settings.start_scene,
            "author":      self.settings.author,
            "version":     self.settings.version,
            "palette_auto_import_enabled": self.settings.palette_auto_import_enabled,
            "backdrop_color": self.settings.backdrop_color,
        }
        _atomic_write(self.project_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_settings(self):
        if not self.project_file.exists():
            return
        d = json.loads(self.project_file.read_text(encoding="utf-8"))
        self.settings.name        = d.get("name", self.root.name)
        self.settings.start_scene = d.get("start_scene", "")
        self.settings.author      = d.get("author", "")
        self.settings.version     = d.get("version", "0.1")
        self.settings.palette_auto_import_enabled = d.get("palette_auto_import_enabled", True)
        self.settings.backdrop_color = d.get("backdrop_color", 0)

    # ── I/O variables (globals + constants) ─────────────────────────
    # Assets côté éditeur sans dépendance externe -> project/variables.json,
    # pas project.json (config racine uniquement, cf. ARCHITECTURE.md).

    def save_variables(self):
        data = {
            "globals": [
                {"name": g.name, "type": g.type, "default": g.default, "desc": g.desc}
                for g in self.globals
            ],
            "constants": [
                {"name": c.name, "type": c.type, "value": c.value, "desc": c.desc}
                for c in self.constants
            ],
        }
        self.project_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.variables_file, json.dumps(data, indent=2, ensure_ascii=False))

    def load_variables(self):
        self.globals = []
        self.constants = []
        if not self.variables_file.exists():
            return
        d = json.loads(self.variables_file.read_text(encoding="utf-8"))
        self.globals = [
            GlobalVar(
                name    = g.get("name", "var"),
                type    = g.get("type", "int"),
                default = g.get("default", 0),
                desc    = g.get("desc", ""),
            )
            for g in d.get("globals", [])
        ]
        self.constants = [
            Constant(
                name  = c.get("name", "const"),
                type  = c.get("type", "int"),
                value = c.get("value", 0),
                desc  = c.get("desc", ""),
            )
            for c in d.get("constants", [])
        ]

    # ── I/O palettes (catalogue illimité, un fichier par palette) ───────

    def _seed_or_migrate_palettes(self):
        """Appelé après self.palettes.load(). Priorité :
        (1) ancien catalogue monolithique project/palettes.json (pré-catalogue-
            illimité, deux pools 16+16 dans un seul fichier) ;
        (2) anciens pools séparés project/palettes/obj/ + bg/ (catalogue
            illimité mais encore scindé OBJ/BG, une session avant la fusion) ;
        (3) projet neuf sans aucune trace de ce qui précède -> seed avec les
            presets par défaut.
        Aux étapes (1)/(2), les collisions de nom entre OBJ et BG sont
        résolues : couleurs identiques -> dédupliquées (une seule entrée
        gardée) ; couleurs différentes -> le doublon BG est suffixé " (BG)"."""
        if self.palettes.items:
            return

        def _merge(name: str, colors: list, is_bg: bool):
            if not name:
                return
            existing = self.palettes.get(name)
            if existing is None:
                self.palettes.append(PaletteBank(name=name, colors=colors))
                return
            if existing.colors == colors:
                return  # doublon identique entre pools -> rien à faire
            final_name = f"{name} (BG)" if is_bg else name
            if self.palettes.get(final_name) is None:
                self.palettes.append(PaletteBank(name=final_name, colors=colors))

        if self.legacy_palettes_file.exists():
            d = json.loads(self.legacy_palettes_file.read_text(encoding="utf-8"))
            for b in d.get("obj_banks", []):
                _merge(b.get("name", ""), list(b.get("colors", [])), is_bg=False)
            for b in d.get("bg_banks", []):
                _merge(b.get("name", ""), list(b.get("colors", [])), is_bg=True)
            self.palettes.save_all()
            self.legacy_palettes_file.rename(
                self.legacy_palettes_file.parent / (self.legacy_palettes_file.name + ".migrated"))
            return

        legacy_obj_files = sorted(self.legacy_obj_palettes_dir.glob("*.json")) \
            if self.legacy_obj_palettes_dir.exists() else []
        legacy_bg_files = sorted(self.legacy_bg_palettes_dir.glob("*.json")) \
            if self.legacy_bg_palettes_dir.exists() else []
        if legacy_obj_files or legacy_bg_files:
            for f in legacy_obj_files:
                d = json.loads(f.read_text(encoding="utf-8"))
                _merge(d.get("name", ""), list(d.get("colors", [])), is_bg=False)
            for f in legacy_bg_files:
                d = json.loads(f.read_text(encoding="utf-8"))
                _merge(d.get("name", ""), list(d.get("colors", [])), is_bg=True)
            self.palettes.save_all()
            if self.legacy_obj_palettes_dir.exists():
                self.legacy_obj_palettes_dir.rename(
                    self.legacy_obj_palettes_dir.parent / "obj.migrated")
            if self.legacy_bg_palettes_dir.exists():
                self.legacy_bg_palettes_dir.rename(
                    self.legacy_bg_palettes_dir.parent / "bg.migrated")
            return

        from core.palette_presets import generate_default_banks
        for bank in generate_default_banks():
            self.palettes.append(bank)
        self.palettes.save_all()

    # ── I/O scenes (restaure aussi la scène active) ────────────────

    def _load_scenes_with_migration(self):
        """
        Charge les scènes en gérant la migration automatique de l'ancien
        format (instances[actor_name] → Actor inline).  Si le dossier
        project/actors/ existe encore, ses fichiers servent de référence
        pour copier les Components lors de la migration, puis sont ignorés.
        """
        legacy_actors: dict[str, "Actor"] = {}
        old_actors_dir = self.project_dir / "actors"
        if old_actors_dir.exists():
            for f in sorted(old_actors_dir.glob("*.json")):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                    # Reconstituer un Actor partiel (components seulement) pour la migration
                    a = Actor(
                        name        = d.get("name", f.stem),
                        prefab_name = d.get("prefab_name"),
                        active      = d.get("active", True),
                        components  = _components_from_list(d.get("components", [])),
                    )
                    legacy_actors[a.name] = a
                except Exception:
                    pass

        self.scenes.items = []
        scenes_dir = self.scenes_dir
        if not scenes_dir.exists():
            return
        for f in sorted(scenes_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                scene = Scene.from_dict(d, legacy_actors=legacy_actors if legacy_actors else None)
                self.scenes.items.append(scene)
                # Si migration détectée (format instances → actors), re-sauvegarder
                if "instances" in d and "actors" not in d:
                    self.save_scene(scene)
            except Exception as e:
                print(f"[project] erreur lecture Scene {f.name}: {e}")

        if self.settings.start_scene:
            for i, s in enumerate(self.scenes):
                if s.name == self.settings.start_scene:
                    self._active_scene_idx = i
                    break

    # ── Renommage (supprime l'ancien fichier + répare les références) ──
    # ResourceManager.rename() seul ne suffit pas : il faut aussi mettre à
    # jour tout ce qui référence l'ancien nom ailleurs dans le projet.

    def rename_background(self, bg: BackgroundAsset, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == bg.name:
            return
        old_name = bg.name
        # Renommer aussi le PNG source : un BackgroundAsset est keyé par le stem
        # de son PNG (name == stem(source)). Sans ça, _reconcile_backgrounds
        # recréerait un asset orphelin depuis l'ancien PNG au prochain chargement.
        old_png = (self.background_images_dir / bg.source) if bg.source else None
        if old_png and old_png.exists():
            new_png = old_png.with_name(f"{new_name}{old_png.suffix}")
            if not new_png.exists():
                old_png.rename(new_png)
                bg.source = new_png.name
        self.backgrounds.rename(bg, new_name)
        # Met à jour les layers des scènes qui référencent ce fond par nom.
        for scene in self.scenes:
            touched = False
            for L in scene.background_layers:
                if L.image == old_name:
                    L.image = new_name
                    touched = True
            if touched:
                self.save_scene(scene)

    def rename_scene(self, scene: Scene, new_name: str):
        new_name = new_name.strip()
        if not new_name or new_name == scene.name:
            return
        old_name = scene.name
        self.scenes.rename(scene, new_name)
        if self.settings.start_scene == old_name:
            self.settings.start_scene = new_name
            self.save_settings()

    # ── CRUD variables (globals / constants) ────────────────────────
    # Unicité vérifiée PAR TYPE uniquement : un global et une constante
    # peuvent partager un nom (préfixes C distincts : g_<nom> / CONST_<NOM>).

    def _variable_list(self, kind: str) -> list:
        """kind: "global" | "const" """
        return self.constants if kind == "const" else self.globals

    def variable_name_taken(self, kind: str, name: str, *, exclude=None) -> bool:
        return any(e is not exclude and e.name == name for e in self._variable_list(kind))

    def add_variable(self, kind: str, name: str):
        """Ajoute un global ou une constante. Retourne None si le nom est vide ou déjà pris (par type)."""
        name = name.strip()
        if not name or self.variable_name_taken(kind, name):
            return None
        entry = Constant(name=name) if kind == "const" else GlobalVar(name=name)
        self._variable_list(kind).append(entry)
        self.save_variables()
        return entry

    def rename_variable(self, kind: str, entry, new_name: str) -> bool:
        """Renomme en place. Retourne False (no-op) si le nom est vide/inchangé/déjà pris."""
        new_name = new_name.strip()
        if not new_name or new_name == entry.name:
            return False
        if self.variable_name_taken(kind, new_name, exclude=entry):
            return False
        entry.name = new_name
        self.save_variables()
        return True

    # ── Raccourcis de sauvegarde par objet (delegue au ResourceManager) ──

    def save_scene(self, scene: Scene):                    self.scenes.save(scene)
    def save_prefab(self, prefab: Prefab):                 self.prefabs.save(prefab)
    def save_sprite(self, sprite: SpriteAsset):           self.sprites.save(sprite)
    def save_background(self, bg: BackgroundAsset):       self.backgrounds.save(bg)
    def save_sfx(self, sfx: Sfx):                         self.sfx.save(sfx)
    def save_music(self, music: Music):                   self.music.save(music)
    def save_tileset(self, tileset):                      pass  # stub rétrocompat

    # ── Sauvegarde / chargement global ────────────────────────────

    def save(self):
        self.save_settings()
        self.save_variables()
        self.sprites.save_all()
        self.sfx.save_all()
        self.music.save_all()
        self.fonts.save_all()
        self.backgrounds.save_all()
        self.prefabs.save_all()
        self.scenes.save_all()

    def _migrate_on_load(self):
        """Migrations automatiques à l'ouverture d'un projet ancien."""
        # script paths : project/scripts/ → assets/scripts/ (scènes + prefabs)
        for f in list(self.scenes_dir.glob("*.json")) + list(self.prefab_dir.glob("*.json")):
            text = f.read_text(encoding="utf-8")
            migrated = text.replace("project/scripts/", "assets/scripts/")
            if migrated != text:
                f.write_text(migrated, encoding="utf-8")

        pass

    def load(self):
        # S'assurer que tous les sous-dossiers existent
        for sub in ("project/scenes", "project/prefab", "project/backgrounds",
                    "project/palettes",
                    "assets/sprites", "assets/backgrounds",
                    "assets/scripts", "assets/scripts/actors",
                    "assets/scripts/scenes", "assets/scripts/behaviors",
                    "assets/sfx", "assets/music", "assets/fonts"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        self._migrate_on_load()
        self.load_settings()
        self.load_variables()
        self.palettes.load()
        self._seed_or_migrate_palettes()
        self.sprites.load()
        self._migrate_sprite_palettes()
        self.sfx.load()
        self.music.load()
        self.fonts.load()
        self.backgrounds.load()
        self._reconcile_backgrounds()
        self.prefabs.load()
        self._reconcile_sfx_and_music()
        self._load_scenes_with_migration()
        self._migrate_scene_backgrounds()

    def _migrate_scene_backgrounds(self):
        """Migration : ancien `scene.background_asset` (BackgroundAsset multi-layer)
        -> `scene.background_layers`. Chaque layer référence l'image par son STEM ;
        on s'assure qu'un BackgroundAsset (sidecar de compression) existe par image.
        Idempotent (ne fait rien si background_layers déjà rempli). PNG intacts."""
        for scene in self.scenes:
            legacy = getattr(scene, "_legacy_bg_asset", "")
            if scene.background_layers or not legacy:
                continue
            old = self.get_background(legacy)
            for L in getattr(old, "_legacy_layers", []) if old else []:
                stem = Path(L.image).stem if L.image else ""
                if not stem:
                    continue
                ap = self.background_images_dir / L.image
                if ap.exists() and self.get_background(stem) is None:
                    self.sync_background_png(ap)   # sidecar de compression par image
                scene.background_layers.append(BackgroundLayer(
                    image=stem, bg_slot=L.bg_slot,
                    scroll_speed=L.scroll_speed, pal_bank=L.pal_bank))
            scene._legacy_bg_asset = ""
            if scene.background_layers:
                self.save_scene(scene)

    def _reconcile_backgrounds(self):
        """(1) PNG déposés hors éditeur dans assets/backgrounds/ → crée le
        BackgroundAsset + sa compression (comme sync_background_png). (2) Fonds
        existants sans tileset → compression calculée. NON-DESTRUCTIF (PNG jamais
        modifié), idempotent."""
        d = self.background_images_dir
        for f in (sorted(d.glob("*")) if d.exists() else []):
            if f.is_file() and f.suffix.lower() in (".png", ".bmp"):
                self.sync_background_png(f)
        for ba in list(self.backgrounds):
            if ba.tileset:
                continue
            img = ba.image_name()
            ap = self.background_images_dir / img if img else None
            if ap and ap.exists():
                self._compress_background_asset(ba, ap)
                if ba.tileset:
                    self.backgrounds.save(ba)

    def _migrate_sprite_palettes(self):
        """Normalisation NON-DESTRUCTIVE des sprites existants : tout SpriteAsset
        sans `own_palette` se voit calculer sa compression depuis son PNG source
        (écrit en métadonnées JSON, PNG jamais touché). Idempotent — une fois
        `own_palette` présente, la passe la saute (aucune réécriture)."""
        for sp in list(self.sprites):
            if sp.own_palette or not sp.asset:
                continue
            ap = self.asset_abs(sp.asset)
            if not ap or not ap.exists():
                continue
            pal = self._derive_own_palette(ap, sp.compress_method)
            if pal:
                sp.own_palette = pal
                self.sprites.save(sp)

    def _reconcile_sfx_and_music(self):
        """
        Crée les sidecars manquants pour les fichiers audio bruts déjà présents
        dans assets/sfx/ et assets/music/ (déposés via l'explorateur pendant
        que l'éditeur était fermé — le ProjectWatcher ne peut pas les avoir vus).
        """
        for f in sorted(self.sfx_dir.glob("*")) if self.sfx_dir.exists() else []:
            if f.is_file() and f.suffix.lower() in SFX_FILE_EXTS:
                self.sync_sfx_file(f)
        for f in sorted(self.music_dir.glob("*")) if self.music_dir.exists() else []:
            if f.is_file() and f.suffix.lower() in MUSIC_FILE_EXTS:
                self.sync_music_file(f)

    # ── Création / ouverture ──────────────────────────────────────

    @classmethod
    def create(cls, root: Path, name: str) -> "Project":
        """Crée un nouveau projet vide avec la structure de dossiers."""
        root.mkdir(parents=True, exist_ok=True)
        for sub in (
            "assets/sprites",
            "assets/backgrounds",
            "assets/sounds",
            "assets/sfx",
            "assets/music",
            "assets/fonts",
            "assets/scripts",
            "assets/scripts/actors",
            "assets/scripts/scenes",
            "assets/scripts/behaviors",
            "project/scenes",
            "project/prefab",
        ):
            (root / sub).mkdir(parents=True, exist_ok=True)

        proj = cls(root)
        proj.settings.name = name

        # Peupler le catalogue de palettes par défaut dès la création (sinon
        # le seeding n'a lieu qu'au prochain load() et les palettes n'apparaissent
        # qu'après un redémarrage). Réutilise la logique de seed/migration :
        # palettes.items étant vide, on retombe sur les presets par défaut.
        proj._seed_or_migrate_palettes()

        # Créer une scène de démarrage par défaut
        default_scene = Scene(name="Scene_01")
        proj.scenes.append(default_scene)
        proj.settings.start_scene = "Scene_01"

        proj.save()

        # Launcher .bat — ouvre l'éditeur directement sur ce projet
        editor_dir = Path(__file__).parent
        editor_root = editor_dir.parent
        bat_path = root / f"{name}.bat"
        bat_path.write_text(
            f"@echo off\r\n"
            f"cd /d \"{editor_root}\"\r\n"
            f"python editor\\main.py --project \"{root}\"\r\n",
            encoding="utf-8"
        )

        return proj

    @classmethod
    def open(cls, root: Path) -> "Project":
        """Ouvre un projet existant."""
        proj = cls(root)
        proj.load()
        return proj
