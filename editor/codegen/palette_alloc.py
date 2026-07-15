"""editor/codegen/palette_alloc.py — allocation des banques de palette par scène.

Source de vérité UNIQUE (pipeline grit + main_gen) pour :
- quelles couleurs occupent chacune des 16 banques matérielles d'un pool
  (OBJ / BG) d'une scène,
- l'index de banque de chaque asset : palette RÉFÉRENCÉE (pal_bank 0-15) ->
  son slot ; palette PROPRE (pal_bank == OWN_PAL_BANK) -> slot libre
  auto-alloué à sa palette d'origine.

La palette propre d'un asset = couleurs du PNG (index 0 transparent), extraite
à la volée via extract_palette_from_image, mémoïsée par (chemin, mtime).

Déterministe : les mêmes (project, scene, pool) donnent toujours le même
layout, donc pipeline.py (grit -mp) et main_gen.py (g_pal_* + g_actors) restent
cohérents sans se coordonner explicitement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.project import Project, Scene, OWN_PAL_BANK
from core.color_utils import extract_palette_from_image, RESERVED_SLOT_COLOR
from core.palette_presets import DEFAULT_PAL_BANK_COLORS

# Cache des palettes propres, invalidé par mtime du PNG.
_own_cache: dict[tuple[str, float], list[int]] = {}


def own_palette(png_path) -> list[int]:
    """Palette propre d'un PNG (couleurs d'origine, index 0 transparent),
    mémoïsée par chemin+mtime. [] si le fichier est absent/illisible."""
    p = Path(png_path)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return []
    cached = _own_cache.get(key)
    if cached is None:
        try:
            cached = extract_palette_from_image(p)
        except Exception:
            cached = []
        _own_cache[key] = cached
    return cached


class SceneBankLayout:
    """Résultat de l'allocation pour une scène + un pool."""

    def __init__(self, slot_colors: list[Optional[list[int]]],
                 own_slot: dict[tuple, Optional[int]],
                 bg_block: Optional[dict[tuple, Optional[int]]] = None):
        self.slot_colors = slot_colors      # 16 entrées : couleurs BGR555 ou None
        self._own_slot   = own_slot          # tuple(colors) -> index de banque (None si débordement)
        self._bg_block   = bg_block or {}    # clé palettes fond compressé -> offset de bloc (None si débordement)

    def bank_index(self, pal_bank: int, own_colors: Optional[list[int]]) -> Optional[int]:
        """Index de banque hardware d'un asset :
        - référencé (0-15) -> pal_bank tel quel ;
        - OWN -> slot alloué à sa palette propre (None si débordement >16)."""
        if pal_bank != OWN_PAL_BANK:
            return pal_bank if 0 <= pal_bank < 16 else None
        if not own_colors:
            return None
        return self._own_slot.get(tuple(own_colors))

    def bg_block_offset(self, ba) -> Optional[int]:
        """Offset (première banque) du bloc alloué à un BackgroundAsset
        compressé (ses N sous-palettes occupent des banques contiguës) —
        None si débordement (pas assez de banques libres contiguës)."""
        key = _bg_palettes_key(ba)
        return self._bg_block.get(key)

    def bank_count(self) -> int:
        """Nombre de banques réellement occupées (référencées + propres)."""
        return sum(1 for c in self.slot_colors if c)

    def overflow(self) -> bool:
        """True si au moins une palette propre (ou un bloc de fond compressé)
        n'a pas trouvé de place libre."""
        return (any(v is None for v in self._own_slot.values())
                or any(v is None for v in self._bg_block.values()))


def effective_palette_colors(p: Project, pal_bank: int, png_path,
                             active_names: list, own_pal=None) -> Optional[list[int]]:
    """Couleurs vers lesquelles quantifier un asset (grit) :
    - OWN -> sa palette propre (`own_pal` = métadonnées sprite si fournies ;
      sinon extraction du PNG, cas BG) ;
    - référencé -> les couleurs de la banque nommée du slot ;
    - None si rien de résoluble (slot vide / palette absente)."""
    if pal_bank == OWN_PAL_BANK:
        # `own_pal` (sprite.own_palette) est stocké SANS le slot 0 réservé (cf.
        # own_palette_from_source) — on le préfixe ici pour obtenir la forme
        # 16-slots attendue par GritSprites.run() (quantize_asset direct_index
        # + remap_tiles_to_bank). `own_palette(png_path)` (fallback BG) inclut
        # déjà ce slot (extract_palette_from_image) — pas de double préfixe.
        if own_pal:
            return [RESERVED_SLOT_COLOR] + list(own_pal)
        return own_palette(png_path) or None
    if 0 <= pal_bank < len(active_names):
        name = active_names[pal_bank]
        bank = p.get_palette(name) if name else None
        return list(bank.colors) if bank and bank.colors else None
    return None


# ── Sources d'assets « palette propre » d'une scène ──────────────────────────

def _prefab_sprite(p: Project, pf):
    from core.project import SpriteComponent
    comp = next((c for c in pf.components
                 if isinstance(c, SpriteComponent) and c.sprite_name), None)
    return p.get_sprite(comp.sprite_name) if comp else None


def _sprite_own_palette(sp) -> list[int]:
    """Palette propre (compression) d'un sprite = ses métadonnées
    `own_palette` (BGR555), source de vérité du modèle non-destructif. []
    si absent."""
    return list(getattr(sp, "own_palette", None) or []) if sp else []


def _actor_own_palettes(p: Project, scene: Scene) -> list[list[int]]:
    """Palettes propres des ACTEURS de la scène en mode OWN (métadonnées
    sprite.own_palette ; pas les prefabs — alloués globalement, cf.
    prefab_own_slots)."""
    out: list[list[int]] = []
    for a in scene.actors:
        if not a.active or getattr(a, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        comp = a.get_component("sprite")
        sp = (p.get_sprite(comp.sprite_name)
              if comp and comp.active and comp.sprite_name else None)
        cols = _sprite_own_palette(sp)
        if cols:
            out.append(cols)
    return out


def _prefab_own_palettes(p: Project) -> list[list[int]]:
    """Palettes propres distinctes des prefabs poolés en mode OWN (métadonnées ;
    ordre déterministe par ordre du catalogue de prefabs)."""
    out: list[list[int]] = []
    seen: set[tuple] = set()
    for pf in p.prefabs:
        if getattr(pf, "max_instances", 0) <= 0 or getattr(pf, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        cols = _sprite_own_palette(_prefab_sprite(p, pf))
        key = tuple(cols)
        if cols and key not in seen:
            seen.add(key)
            out.append(cols)
    return out


def prefab_own_slots(p: Project) -> dict[tuple, Optional[int]]:
    """Un prefab poolé peut spawner dans N'IMPORTE QUELLE scène (spawn_X est
    global) : sa palette propre doit occuper le MÊME slot matériel partout.
    On assigne donc chaque palette propre de prefab à un slot libre DANS
    TOUTES les scènes (les plus bas d'abord). None si aucun slot commun libre
    (débordement -> avertissement validateur + fallback banque 0)."""
    scene_named: list[set[int]] = []
    for scene in p.scenes:
        occ = set()
        for i, name in enumerate(getattr(scene, "active_obj_palettes", [])[:16]):
            if name and p.get_palette(name):
                occ.add(i)
        scene_named.append(occ)
    # PAS de fallback `or list(range(16))` ici : si aucun slot n'est libre dans
    # TOUTES les scènes, assigner quand même des slots (0-15) placerait la
    # palette du prefab sur une banque occupée par une palette référencée dans
    # certaines scènes -> mauvaises couleurs silencieuses. On laisse plutôt
    # `next(it, None)` renvoyer None (débordement) : bank_index retombe sur la
    # banque 0 et le validateur avertit (_check_palette_bank_overflow).
    globally_free = [j for j in range(16)
                     if all(j not in occ for occ in scene_named)]
    it = iter(globally_free)
    return {tuple(cols): next(it, None) for cols in _prefab_own_palettes(p)}


def _bg_own_sources(p: Project, scene: Scene) -> list[Path]:
    """PNG des layers BG en mode OWN de la scène, hors fonds COMPRESSÉS
    (ceux-ci ont déjà leurs propres sous-palettes en métadonnées — gérés à
    part par `_bg_encoded_sources`/allocation par bloc, cf.
    [[project_palette_system_design]])."""
    srcs: list[Path] = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name or getattr(layer, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            continue
        png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
        srcs.append(p.background_images_dir / png)
    return srcs


def _bg_encoded_sources(p: Project, scene: Scene) -> list:
    """BackgroundAsset compressés (mode OWN) des layers de la scène, dans
    l'ordre des layers. Chacun peut avoir jusqu'à 16 sous-palettes (une par
    groupe de tuiles) — il lui faut un BLOC de banques contiguës, pas un slot
    unique (cf. `_find_free_block`)."""
    out = []
    for layer in getattr(scene, "background_layers", []):
        if not layer.background_name or getattr(layer, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            out.append(ba)
    return out


def _bg_palettes_key(ba) -> tuple:
    """Clé de dédup d'un fond compressé = contenu exact de ses sous-palettes
    (deux fonds avec les mêmes couleurs partagent le même bloc de banques)."""
    return tuple(tuple(pal) for pal in getattr(ba, "palettes", None) or [])


def _find_free_block(slots: list, n: int) -> Optional[int]:
    """Premier offset (0-15) tel que les n banques [offset, offset+n) soient
    toutes libres — None si aucun bloc contigu de cette taille n'existe."""
    n = max(1, n)
    for start in range(0, 17 - n):
        if all(slots[start + i] is None for i in range(n)):
            return start
    return None


def _own_bank_content(cols, pool: str) -> list[int]:
    """Contenu à écrire dans une banque matérielle pour une palette propre.
    `sprite.own_palette` (pool OBJ) est stocké SANS le slot 0 réservé (cf.
    own_palette_from_source : "index 1..N, index 0 transparent implicite, pas
    inclus") — il faut le préfixer ici, sous peine que la 1ère couleur du sprite
    atterrisse en position 0 de la banque, où le hardware OBJ la rend
    transparente quoi qu'il arrive (couleur jamais affichée). Le BG legacy
    (`own_palette()`, extract_palette_from_image) inclut déjà ce slot — ne pas
    le préfixer une 2e fois."""
    return [RESERVED_SLOT_COLOR] + list(cols) if pool == "obj" else list(cols)


def scene_bank_layout(p: Project, scene: Scene, pool: str) -> SceneBankLayout:
    """Alloue les 16 banques d'un pool ("obj"|"bg") pour une scène :
    (1) palettes référencées à leur index fixe ; (2) pour OBJ, palettes propres
    des prefabs poolés à leur slot GLOBAL (cf. prefab_own_slots — même partout
    car spawn_X est global) ; (3) palettes propres des acteurs/layers de la
    scène dans les slots restants (dédup par couleurs)."""
    if pool == "obj":
        active = list(getattr(scene, "active_obj_palettes", []))[:16]
        own_color_lists = _actor_own_palettes(p, scene)          # métadonnées sprite
        pf_slots = prefab_own_slots(p)
        encoded_assets = []
    else:
        active = list(getattr(scene, "active_bg_palettes", []))[:16]
        own_color_lists = [own_palette(png) for png in _bg_own_sources(p, scene)]  # BG legacy: extraction
        pf_slots = {}
        encoded_assets = _bg_encoded_sources(p, scene)      # BG encodé: métadonnées

    slots: list[Optional[list[int]]] = [None] * 16
    for i, name in enumerate(active):
        bank = p.get_palette(name) if name else None
        if bank and bank.colors:
            slots[i] = list(bank.colors)

    own_slot: dict[tuple, Optional[int]] = {}
    # Prefabs poolés : slot global (réservé dans cette scène aussi).
    for key, slot in pf_slots.items():
        own_slot[key] = slot
        if slot is not None and slots[slot] is None:
            slots[slot] = _own_bank_content(key, pool)

    # Fonds compressés (OWN) : bloc de banques CONTIGUËS par asset (N sous-
    # palettes), dédupliqué par contenu exact. Alloué avant les palettes
    # propres à slot unique ci-dessous (moins de fragmentation, les blocs sont
    # plus gros et plus contraints).
    bg_block: dict[tuple, Optional[int]] = {}
    for ba in encoded_assets:
        key = _bg_palettes_key(ba)
        if key in bg_block:
            continue
        if getattr(ba, "bpp", 4) == 8:
            # 8bpp : UNE palette de 256 couleurs qui occupe LES 16 banques de
            # PAL_BG_RAM (le pal_bank des SE est ignoré par le hardware). Ne peut
            # donc PAS cohabiter avec d'autres palettes BG : si des banques sont
            # déjà prises (référencées / autre asset), c'est un débordement.
            pal256 = list(key[0]) if key else []
            if all(s is None for s in slots):
                for i in range(16):
                    chunk = pal256[i * 16:(i + 1) * 16]
                    slots[i] = list(chunk) + [0] * (16 - len(chunk))
                bg_block[key] = 0
            else:
                bg_block[key] = None   # débordement (cohabitation impossible)
            continue
        n = min(len(key), 16)
        start = _find_free_block(slots, n)
        bg_block[key] = start
        if start is not None:
            for i in range(n):
                slots[start + i] = list(key[i])

    # Acteurs/layers de la scène : slots restants.
    for cols in own_color_lists:
        if not cols:
            continue
        key = tuple(cols)
        if key in own_slot:
            continue
        free = next((j for j in range(16) if slots[j] is None), None)
        own_slot[key] = free
        if free is not None:
            slots[free] = _own_bank_content(cols, pool)

    # Banque 0 de secours : si la scène a du contenu palette mais que le slot 0
    # est resté vide, on le remplit d'une palette déterministe — un asset
    # retombant sur la banque 0 (référence cassée / débordement) affiche alors
    # des couleurs prévisibles. `any(slots)` : on n'invente rien pour une scène
    # vide (émission main_gen reste optimale).
    if slots[0] is None and any(slots):
        slots[0] = list(DEFAULT_PAL_BANK_COLORS)

    return SceneBankLayout(slots, own_slot, bg_block)


# ─────────────────────────────────────────────────────────────────────────────
#  Vue éditeur — surface l'allocation par scène dans l'inspecteur
# ─────────────────────────────────────────────────────────────────────────────
# `scene_bank_layout` (ci-dessus) résout l'allocation AU BUILD, en silence. Ces
# structures remontent la MÊME information dans l'éditeur (carte PALETTES
# ACTIVES) : les palettes de la scène (éditables) suivies des palettes propres
# des assets (grisées), pour que l'utilisateur voie et pilote les 16 banques au
# lieu d'une boîte noire. Aucun champ de modèle nouveau : l'état « override » se
# lit dans `pal_bank` (OWN vs slot référencé), la palette propre reste toujours
# disponible (`sprite.own_palette`, modèle non-destructif).


@dataclass
class InstanceRef:
    """Une instance de scène (acteur ou layer BG) qui apporte une palette
    propre. `obj` est l'Actor / BackgroundLayer réel — muter `obj.pal_bank`
    override (ou restaure) cette instance."""
    kind: str          # "actor" | "bg_layer"
    obj: object
    label: str         # nom lisible (acteur / "BG{slot}")
    pal_bank: int      # état courant : OWN_PAL_BANK ou slot scène référencé


@dataclass
class ScenePaletteEntry:
    """Une palette ACTIVE de la scène (éditable). `slot` = index de banque
    hardware (== index dans active_*_palettes, valeur de pal_bank pour la
    référencer)."""
    slot: int
    name: str
    colors: list


@dataclass
class AssetPaletteEntry:
    """Une palette PROPRE d'asset partagée par ≥1 instance de la scène,
    dédupliquée par couleurs. `state` :
    - "own"      → aucune instance overridée : occupe une banque libre (grisée) ;
    - "override" → toutes les instances pointent vers une palette de scène
      (`ref_slot`) : ne consomme PAS de banque en plus (pointeur)."""
    own_colors: list               # forme banque hardware (clé de dédup + rendu grisé)
    instances: list                # list[InstanceRef]
    state: str = "own"             # "own" | "override"
    ref_slot: Optional[int] = None # override : slot scène ciblé
    bank_span: int = 1             # nb de banques occupées (>1 pour fonds compressés)
    overridable: bool = True       # False pour fonds compressés/bitmap (bloc multi-banques)


@dataclass
class ScenePaletteView:
    """Vue ordonnée d'un pool ("obj"|"bg") pour une scène : palettes de scène
    (contiguës depuis slot 0) puis palettes propres d'asset (grisées/override).
    `banks_used` = banques réellement occupées (scène + assets « own », spans
    compris) — le bouton « + » n'apparaît que s'il reste de la place."""
    pool: str
    scene_entries: list            # list[ScenePaletteEntry]
    asset_entries: list            # list[AssetPaletteEntry]
    banks_used: int

    def can_add(self) -> bool:
        return self.banks_used < 16


def _obj_instance_pairs(p: Project, scene: Scene) -> list[tuple[tuple, InstanceRef]]:
    """(clé couleurs, InstanceRef) pour chaque acteur actif à composant sprite
    ayant une palette propre. La clé est la forme banque hardware (préfixe slot
    0 réservé) — cohérente avec scene_bank_layout."""
    out: list[tuple[tuple, InstanceRef]] = []
    for a in scene.actors:
        if not getattr(a, "active", True):
            continue
        comp = a.get_component("sprite")
        if not (comp and getattr(comp, "active", True) and getattr(comp, "sprite_name", "")):
            continue
        cols = _sprite_own_palette(p.get_sprite(comp.sprite_name))
        if not cols:
            continue
        key = tuple(_own_bank_content(cols, "obj"))
        out.append((key, InstanceRef("actor", a, a.name,
                                     getattr(a, "pal_bank", OWN_PAL_BANK))))
    return out


def _bg_instance_pairs(p: Project, scene: Scene) -> list[tuple[tuple, InstanceRef]]:
    """(clé couleurs, InstanceRef) pour chaque layer BG legacy (non compressé)
    ayant une palette propre extractible. Les fonds compressés/bitmap sont
    exclus ici — ils occupent un BLOC de banques et sont remontés à part
    (non-overridables pour l'instant, cf. scene_palette_view)."""
    out: list[tuple[tuple, InstanceRef]] = []
    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        ba = p.get_background(layer.background_name)
        if ba and getattr(ba, "tileset", None):
            continue   # compressé : géré comme entrée de bloc
        png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
        cols = own_palette(p.background_images_dir / png)
        if not cols:
            continue
        key = tuple(_own_bank_content(cols, "bg"))
        out.append((key, InstanceRef("bg_layer", layer, f"BG{layer.bg_slot}",
                                     getattr(layer, "pal_bank", OWN_PAL_BANK))))
    return out


def _bg_encoded_entries(p: Project, scene: Scene) -> list[AssetPaletteEntry]:
    """Entrées d'asset pour les fonds COMPRESSÉS des layers de la scène : chacun
    occupe un BLOC de N banques contiguës (ses N sous-palettes, SE_PALBANK par
    tuile) — pas un slot unique. Non-overridables (on ne remappe pas un bloc
    vers une seule palette de scène). Dédupliqués par contenu exact des
    sous-palettes ; l'affichage échantillonne la 1ère sous-palette."""
    groups: dict[tuple, tuple] = {}   # key -> (ba, [InstanceRef])
    order: list[tuple] = []
    for layer in getattr(scene, "background_layers", []):
        if not getattr(layer, "background_name", ""):
            continue
        ba = p.get_background(layer.background_name)
        if not (ba and getattr(ba, "tileset", None)):
            continue
        key = _bg_palettes_key(ba)
        if key not in groups:
            groups[key] = (ba, [])
            order.append(key)
        groups[key][1].append(InstanceRef(
            "bg_layer", layer, f"BG{layer.bg_slot} ({layer.background_name})",
            getattr(layer, "pal_bank", OWN_PAL_BANK)))
    out: list[AssetPaletteEntry] = []
    for key in order:
        ba, refs = groups[key]
        pals = getattr(ba, "palettes", None) or []
        out.append(AssetPaletteEntry(
            own_colors=list(pals[0]) if pals else [],
            instances=refs, state="own", ref_slot=None,
            bank_span=max(1, len(pals)), overridable=False,
        ))
    return out


def scene_palette_view(p: Project, scene: Scene, pool: str) -> ScenePaletteView:
    """Construit la vue éditeur d'un pool pour une scène (cf. ScenePaletteView).

    Dérivé du modèle, sans mutation : énumère les instances de la scène,
    regroupe par palette propre (dédup couleurs) et lit `pal_bank` pour l'état
    own/override. Ordre stable (première apparition)."""
    active = list(getattr(scene, f"active_{pool}_palettes", []))

    scene_entries: list[ScenePaletteEntry] = []
    for i, name in enumerate(active):
        if not name:
            continue
        bank = p.get_palette(name)
        scene_entries.append(ScenePaletteEntry(
            slot=i, name=name,
            colors=list(bank.colors) if bank and bank.colors else [],
        ))

    pairs = _obj_instance_pairs(p, scene) if pool == "obj" else _bg_instance_pairs(p, scene)

    groups: dict[tuple, list[InstanceRef]] = {}
    order: list[tuple] = []
    for key, ref in pairs:
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(ref)

    asset_entries: list[AssetPaletteEntry] = []
    for key in order:
        refs = groups[key]
        own_refs = [r for r in refs if r.pal_bank == OWN_PAL_BANK]
        if own_refs:
            state, ref_slot = "own", None
        else:
            # Toutes overridées : slot de référence commun (elles partagent la
            # même palette propre, donc convergent normalement vers le même).
            state, ref_slot = "override", refs[0].pal_bank
        asset_entries.append(AssetPaletteEntry(
            own_colors=list(key), instances=refs, state=state, ref_slot=ref_slot,
        ))

    # BG compressé : blocs de banques (non-overridables) après les entrées à
    # slot unique, dans l'ordre des layers.
    if pool == "bg":
        asset_entries += _bg_encoded_entries(p, scene)

    banks_used = (len(scene_entries)
                  + sum(e.bank_span for e in asset_entries if e.state == "own"))
    return ScenePaletteView(pool, scene_entries, asset_entries, banks_used)
