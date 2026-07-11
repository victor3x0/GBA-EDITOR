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

from pathlib import Path
from typing import Optional

from core.project import Project, Scene, OWN_PAL_BANK
from core.color_utils import extract_palette_from_image
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
                 own_slot: dict[tuple, Optional[int]]):
        self.slot_colors = slot_colors      # 16 entrées : couleurs BGR555 ou None
        self._own_slot   = own_slot          # tuple(colors) -> index de banque (None si débordement)

    def bank_index(self, pal_bank: int, own_colors: Optional[list[int]]) -> Optional[int]:
        """Index de banque hardware d'un asset :
        - référencé (0-15) -> pal_bank tel quel ;
        - OWN -> slot alloué à sa palette propre (None si débordement >16)."""
        if pal_bank != OWN_PAL_BANK:
            return pal_bank if 0 <= pal_bank < 16 else None
        if not own_colors:
            return None
        return self._own_slot.get(tuple(own_colors))

    def bank_count(self) -> int:
        """Nombre de banques réellement occupées (référencées + propres)."""
        return sum(1 for c in self.slot_colors if c)

    def overflow(self) -> bool:
        """True si au moins une palette propre n'a pas trouvé de slot libre."""
        return any(v is None for v in self._own_slot.values())


def effective_palette_colors(p: Project, pal_bank: int, png_path,
                             active_names: list, own_pal=None) -> Optional[list[int]]:
    """Couleurs vers lesquelles quantifier un asset (grit) :
    - OWN -> sa palette propre (`own_pal` = métadonnées sprite si fournies ;
      sinon extraction du PNG, cas BG) ;
    - référencé -> les couleurs de la banque nommée du slot ;
    - None si rien de résoluble (slot vide / palette absente)."""
    if pal_bank == OWN_PAL_BANK:
        return (list(own_pal) if own_pal else own_palette(png_path)) or None
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
    """PNG des layers BG en mode OWN de la scène."""
    srcs: list[Path] = []
    ba = p.get_background(scene.background_asset) if scene.background_asset else None
    for layer in (ba.layers if ba else []):
        if not layer.image or getattr(layer, "pal_bank", OWN_PAL_BANK) != OWN_PAL_BANK:
            continue
        srcs.append(p.background_images_dir / layer.image)
    return srcs


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
    else:
        active = list(getattr(scene, "active_bg_palettes", []))[:16]
        own_color_lists = [own_palette(png) for png in _bg_own_sources(p, scene)]  # BG: extraction
        pf_slots = {}

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
            slots[slot] = list(key)

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
            slots[free] = list(cols)

    # Banque 0 de secours : si la scène a du contenu palette mais que le slot 0
    # est resté vide, on le remplit d'une palette déterministe — un asset
    # retombant sur la banque 0 (référence cassée / débordement) affiche alors
    # des couleurs prévisibles. `any(slots)` : on n'invente rien pour une scène
    # vide (émission main_gen reste optimale).
    if slots[0] is None and any(slots):
        slots[0] = list(DEFAULT_PAL_BANK_COLORS)

    return SceneBankLayout(slots, own_slot)
