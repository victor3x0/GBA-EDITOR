"""UIRegion / UILayout — géométrie AUTHORÉE des zones de texte d'une scène.

**Une région ne dessine rien.** Elle dit *où* le texte se pose, jamais à quoi
il ressemble — même contrat que la window matérielle (`WindowSlot`), qui est un
pochoir et pas un cadre. C'est pour ça que le mot est « région » et non
« frame » : dans GB Studio, `frame.png` EST l'image de bordure 9-slice, et le
mot promettrait donc un dessin que le moteur ne fait pas. Le vocabulaire est
celui que fixe ROADMAP v0.3.2 (« région, layer, tilemap — jamais dialogue,
message, textbox ») ; `frame` collisionnerait de surcroît avec les frames
d'animation (`Sprite.frame_w`) et la frame vidéo.

**Ce qui reste au script.** La région porte la GÉOMÉTRIE, pas l'enchaînement :
rien ici ne dit quel texte s'affiche quand, ni sur quel événement. Le Lua
continue de décider (`text.draw("village_garde", "boite_bas")`) — c'est ce qui
empêche cet objet de devenir un éditeur de dialogue par accident, refus tenu
depuis ROADMAP v0.3.2.

**L'ancrage n'est pas un champ libre : il contraint la mémoire.**

  écran  — fixe sur 240×160. Cible BG. C'est ce que `Scene.text_bg` est déjà.
  monde  — défile avec la caméra. Cible BG, mais le cas le plus dur : la région
           entre et sort de la fenêtre de tilemap, il faut la réécrire au wrap.
  actor  — suit un acteur à l'offset près. **Cible OBJ, sans alternative** : un
           actor bouge au pixel, la grille BG avance par 8, une bulle en texte
           BG sauterait donc par crans de 8 px. Ce n'est pas une préférence de
           qualité, c'est une impossibilité — d'où `forced_target()`, et
           l'inspecteur affiche la cible dérivée au lieu de laisser composer une
           combinaison qui ne peut pas exister.

**Tout est stocké en PIXELS**, une seule unité, comme `WindowSlot`. Le BG exige
un alignement à la tuile : c'est `snap_to_tile()` qui le pose, pas le format de
stockage — sinon on aurait deux unités selon la cible et un champ dont il
faudrait deviner le sens.

**Pas de `FieldValue` ici, volontairement.** Les champs numériques de composant
acceptent une référence de variable (`{"var": ...}`) ; une région ne le peut
pas. Tout l'intérêt de déclarer la géométrie est que l'empreinte VRAM devienne
connue AVANT le build (cf. `font_emit.scene_text_tiles`) : une position qui ne
se connaît qu'au runtime rendrait ce chiffre faux, c'est-à-dire pire
qu'absent. Une position calculée reste possible — par `text.draw(tx, ty, id)`,
qui ne disparaît pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.resource import Resource

TILE = 8

# ── Ancrages ──────────────────────────────────────────────────────
ANCHOR_SCREEN = "screen"   # fixe sur l'écran (HUD, boîte de dialogue basse)
ANCHOR_WORLD  = "world"    # défile avec la caméra (panneau posé dans le décor)
ANCHOR_ACTOR  = "actor"    # suit un acteur (bulle) — impose la cible OBJ

ANCHORS = (ANCHOR_SCREEN, ANCHOR_WORLD, ANCHOR_ACTOR)

# ── Cibles de rendu ───────────────────────────────────────────────
# Deux budgets DISJOINTS en modes tuilés : la VRAM BG (64 Ko, arbitrée par
# codegen/vram_alloc) et la VRAM OBJ (32 Ko). Basculer une région d'une cible à
# l'autre transfère la charge, ce qui en fait l'échappatoire quand un charblock
# est plein.
TARGET_BG  = "bg"
TARGET_OBJ = "obj"

TARGETS = (TARGET_BG, TARGET_OBJ)

ALIGNS = ("left", "center", "right")

# Modes vidéo bitmap : la VRAM BG est un framebuffer, il n'y a plus de tilemap
# où écrire des glyphes. Le texte BG y est impossible — le texte sprite n'est
# pas une option, c'est le seul chemin (et l'espace OBJ y tombe à 512 tuiles).
BITMAP_MODES = (3, 4, 5)


def forced_target(anchor: str, render_mode: int = 0) -> str | None:
    """Cible imposée par le contexte, ou None si l'auteur a le choix.

    Deux contraintes, toutes deux matérielles :
      • ancrage sur un actor → OBJ (le BG ne sait pas se poser hors grille) ;
      • scène en mode bitmap → OBJ (plus de tilemap du tout).
    Retourner None est ce qui autorise l'inspecteur à proposer un menu ; sinon
    il affiche la valeur et sa raison."""
    if anchor == ANCHOR_ACTOR:
        return TARGET_OBJ
    if render_mode in BITMAP_MODES:
        return TARGET_OBJ
    return None


def forced_target_reason(anchor: str, render_mode: int = 0) -> str:
    """Pourquoi la cible est imposée — destiné à être affiché tel quel.
    Une contrainte muette se lit comme un bug de l'éditeur."""
    if anchor == ANCHOR_ACTOR:
        return ("ancrage sur un actor : un acteur bouge au pixel, "
                "la grille BG avance par 8")
    if render_mode in BITMAP_MODES:
        return f"scène en mode {render_mode} (bitmap) : il n'y a pas de tilemap"
    return ""


@dataclass
class UIRegion:
    """Une zone de texte de la mise en page.

    `w` est aussi la largeur de coupe : `text_draw_box` prend un `wrap`, et le
    dupliquer dans un champ séparé garantirait qu'un jour les deux divergent.
    """
    name:   str = "region"
    anchor: str = ANCHOR_SCREEN
    anchor_actor: str = ""   # nom de l'Actor suivi — seulement si anchor == actor
    # Géométrie en PIXELS. Pour un ancrage actor, x/y sont un OFFSET par rapport
    # à l'origine de l'acteur (donc signés) ; sinon une position absolue.
    x: int = 0
    y: int = 0
    w: int = 240
    h: int = 32
    # "" = police par défaut de la scène. Nommer une police ici est ce qui rend
    # l'empreinte VRAM de la scène calculable (cf. font_emit.scene_text_tiles).
    font_name: str = ""
    align: str = "left"
    # "" = cible dérivée de l'ancrage. Ne porte une valeur que lorsque l'auteur
    # a fait un choix RÉEL — donc jamais quand `forced_target()` tranche.
    target: str = ""
    # Clé d'une entrée de la table, affichée dans le canvas à la place du vide.
    # Sert à voir le débordement À LA CONCEPTION : le mesureur existe déjà
    # (FontScreenPreview rejoue text_layout avec les vrais glyphes), il ne lui
    # manquait qu'un rectangle contre lequel se mesurer.
    preview_text: str = ""
    # Budget de glyphes ANIMÉS — combien de caractères, au plus, cette zone peut
    # sortir de la bande pour recevoir un effet par caractère.
    #
    # DÉCLARÉ, jamais déduit : quel texte atterrit dans une zone est une décision
    # de script, prise au runtime, et une portée d'effet (`{wave}…{/wave}`) change
    # de longueur avec le texte. Le build ne peut donc pas les compter — il peut
    # seulement réserver ce que l'auteur annonce, et le runtime ÉCRÊTE au-delà
    # (les glyphes en trop rendent en statique dans la bande). Un effet qui
    # dégrade est une perte cosmétique ; un dépassement d'OAM corrompt les
    # sprites des acteurs.
    #
    # 0 = bande seule, c'est-à-dire exactement ce que fait le moteur aujourd'hui.
    animated_glyphs: int = 0

    # ── Cible ─────────────────────────────────────────────────────
    def resolved_target(self, render_mode: int = 0) -> str:
        forced = forced_target(self.anchor, render_mode)
        if forced:
            return forced
        return self.target if self.target in TARGETS else TARGET_BG

    def target_is_locked(self, render_mode: int = 0) -> bool:
        return forced_target(self.anchor, render_mode) is not None

    # ── Géométrie ─────────────────────────────────────────────────
    def snap_to_tile(self) -> None:
        """Aligne la région sur la grille 8×8. À appeler quand la cible résolue
        est BG : le moteur y écrit des entrées de tilemap, l'origine ne peut pas
        tomber entre deux tuiles. La taille est arrondie vers le HAUT — rogner
        reviendrait à couper du texte pour faire joli."""
        self.x -= self.x % TILE
        self.y -= self.y % TILE
        self.w = max(TILE, _ceil_tile(self.w) * TILE)
        self.h = max(TILE, _ceil_tile(self.h) * TILE)

    def tile_rect(self) -> tuple[int, int, int, int]:
        """(tx, ty, w, h) en TUILES, bornes arrondies vers l'extérieur.

        Un glyphe posé à x=13 mord sur la tuile 1 : elle fait partie de
        l'empreinte, exactement comme `text_layout` arrondit la sienne avant de
        préparer la surface."""
        tx = self.x // TILE
        ty = self.y // TILE
        tw = _ceil_tile(self.x % TILE + self.w)
        th = _ceil_tile(self.y % TILE + self.h)
        return tx, ty, max(1, tw), max(1, th)

    def footprint_tiles(self) -> int:
        _, _, tw, th = self.tile_rect()
        return tw * th

    def to_dict(self) -> dict:
        return {
            "name": self.name, "anchor": self.anchor,
            "anchor_actor": self.anchor_actor,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "font_name": self.font_name, "align": self.align,
            "target": self.target, "preview_text": self.preview_text,
            "animated_glyphs": self.animated_glyphs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UIRegion":
        anchor = d.get("anchor", ANCHOR_SCREEN)
        align  = d.get("align", "left")
        target = d.get("target", "")
        return cls(
            name         = str(d.get("name", "region")),
            anchor       = anchor if anchor in ANCHORS else ANCHOR_SCREEN,
            anchor_actor = str(d.get("anchor_actor", "")),
            x = int(d.get("x", 0)),   y = int(d.get("y", 0)),
            w = int(d.get("w", 240)), h = int(d.get("h", 32)),
            font_name    = str(d.get("font_name", "")),
            align        = align if align in ALIGNS else "left",
            target       = target if target in TARGETS else "",
            preview_text = str(d.get("preview_text", "")),
            animated_glyphs = max(0, min(ANIM_GLYPH_MAX,
                                         int(d.get("animated_glyphs", 0) or 0))),
        )


def _ceil_tile(px: int) -> int:
    return (max(0, int(px)) + TILE - 1) // TILE


# ── Aliasing de la surface de composition ─────────────────────────
# UNIQUEMENT en chemin composité. En mono, la tilemap pointe directement les
# glyphes en VRAM : il n'y a pas de surface, donc pas d'aliasing possible.
#
# En composité, la tuile de surface d'une case écran est adressée MODULO
# (TEXT_SURF_W × TEXT_SURF_H) — cf. `text_surf_tile` dans gba_engine.h. Deux
# régions distantes d'un multiple exact de TEXT_SURF_H rangées partagent donc
# physiquement leurs tuiles et se corrompent l'une l'autre. Invisible dans un
# script, évident dans un canvas : c'est précisément ce qu'une géométrie
# authorée permet enfin de vérifier.
SURF_W = 30   # doit rester égal à TEXT_SURF_W (gba_engine.h)
SURF_H = 8    # doit rester égal à TEXT_SURF_H


def surface_cells(region: UIRegion) -> set[tuple[int, int]]:
    """Cases de la surface de composition qu'occupe la région."""
    tx, ty, tw, th = region.tile_rect()
    return {((tx + c) % SURF_W, (ty + r) % SURF_H)
            for r in range(th) for c in range(tw)}


def surface_conflicts(regions) -> list[tuple[UIRegion, UIRegion]]:
    """Paires de régions BG qui se disputeraient les mêmes tuiles de surface.

    Ne filtre pas sur le mode de rendu de la police : l'appelant sait quelles
    régions sont compositées (`font_emit.render_composited`) et lui passe
    celles-là. Une région sans police nommée hérite de celle de la scène, que
    ce module ne connaît pas."""
    out: list[tuple[UIRegion, UIRegion]] = []
    cells = [(r, surface_cells(r)) for r in regions]
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            if cells[i][1] & cells[j][1]:
                out.append((cells[i][0], cells[j][0]))
    return out


# ── Bande OBJ : géométrie d'allocation ────────────────────────────
# Une zone en cible sprite est couverte par une BANDE de sprites : des OBJ de
# 64×8 px posés côte à côte sur le rectangle, dans lesquels le texte se compose
# exactement comme il se compose dans la surface BG.
#
# **La bande ne dépend pas de la police.** On aurait pu poser un OBJ par LIGNE
# de texte, mais l'interligne vient de la police, qui peut être choisie par la
# zone, héritée de la scène, ou changée par un script — l'allocation
# deviendrait alors indécidable au build. Un pavage en blocs de 8 px de haut
# donne le même compte d'OAM dans le cas courant (interligne 8) et reste vrai
# quelle que soit la police.
#
# **32 px est la largeur maximale d'un sprite de 8 px de haut.** Le matériel ne
# propose, en forme « large », que 16×8, 32×8, 32×16 et 64×32 : un 64×8 n'existe
# pas. Aller chercher les 64 px de large imposerait donc des blocs de 32 px de
# haut, qui arrondiraient la hauteur de la zone vers le haut et gâcheraient des
# tuiles (une zone de 40 px en réserverait 64). On paie en OAM ce qu'on refuse
# de gâcher en VRAM.
#
# La dernière colonne prend la plus grande taille qui rentre, pas 32
# systématiquement : sinon une zone de 40 px allouerait 64 px de tuiles et
# déborderait du rectangle que l'auteur a dessiné.
OBJ_WIDTHS = (32, 16, 8)
STRIP_ROW_H = 8

# Un glyphe animé sort de la bande et reçoit son propre sprite. On lui réserve
# un OBJ 16×16, soit 4 tuiles : un glyphe 8×8 posé à une position quelconque
# chevauche jusqu'à 2×2 tuiles (les chasses proportionnelles ne tombent pas sur
# la grille). Une taille uniforme garde l'allocation décidable sans connaître la
# police — le point qui avait déjà fait choisir un pavage de 8 px pour la bande.
ANIM_GLYPH_TILES = 4
# Plafond dur, aligné sur TEXT_ANIM_MAX du runtime (tableaux de capture de
# taille fixe : pas d'allocation dynamique sur cible).
ANIM_GLYPH_MAX = 32


def strip_columns(w: int) -> list[int]:
    """Largeurs (px) des OBJ couvrant `w`, de gauche à droite."""
    out, left = [], max(8, int(w))
    while left > 0:
        # La plus grande taille d'OBJ qui rentre ; 8 px en dernier recours,
        # quitte à dépasser de quelques pixels (une largeur qui n'est pas une
        # somme de puissances de deux ne peut pas être couverte exactement).
        out.append(next((c for c in OBJ_WIDTHS if c <= left), 8))
        left -= out[-1]
    return out


def strip_geometry(region: "UIRegion") -> dict:
    """Ce qu'une zone en cible OBJ consomme.

    `oam` = nombre de slots OAM, `tiles` = tuiles de VRAM OBJ. Les deux sont
    connus depuis la seule géométrie authorée — c'est ce qui rend la jauge
    exacte au lieu d'estimée."""
    cols = strip_columns(region.w)
    rows = max(1, _ceil_tile(region.y % STRIP_ROW_H + region.h))
    tiles_per_row = sum(c // 8 for c in cols)
    anim = max(0, min(ANIM_GLYPH_MAX, int(getattr(region, "animated_glyphs", 0) or 0)))
    return {
        "cols": cols,
        "rows": rows,
        "anim": anim,
        "strip_oam":   len(cols) * rows,
        "strip_tiles": tiles_per_row * rows,
        "oam":   len(cols) * rows + anim,
        "tiles": tiles_per_row * rows + anim * ANIM_GLYPH_TILES,
    }


def layout_obj_budget(layout: "UILayout", render_mode: int = 0) -> dict:
    """Budget OBJ d'une mise en page entière, et le placement RELATIF de chaque
    zone dedans.

    Relatif et non absolu : une même mise en page sert plusieurs scènes, qui
    n'ont pas le même nombre d'acteurs donc pas la même base. Seul le décalage
    interne est intrinsèque à la mise en page — exactement le raisonnement de
    `FontInfo.slot`, relatif au bloc alloué au texte."""
    place, oam, tiles = {}, 0, 0
    for r in layout.regions:
        if r.resolved_target(render_mode) != TARGET_OBJ:
            continue
        g = strip_geometry(r)
        place[r.name] = {"oam_rel": oam, "tile_rel": tiles, **g}
        oam += g["oam"]
        tiles += g["tiles"]
    return {"place": place, "oam": oam, "tiles": tiles}


# ── Mise en page ──────────────────────────────────────────────────

@dataclass
class UILayout(Resource):
    """Un jeu de régions, référencé par une scène via `Scene.ui_layout`.

    **Un asset, pas une donnée de scène.** Rangé dans `project/ui_layouts/` et
    référencé par NOM : une boîte de dialogue dessinée une fois sert les
    quarante scènes du jeu et se corrige en un endroit. Stockée dans la scène,
    elle serait à redessiner — et à recorriger — quarante fois.

    Contrepartie à assumer dans l'UI : éditer une région depuis le canvas d'une
    scène modifie un objet PARTAGÉ. Le dire à l'écran (« mise en page partagée
    — N scènes ») fait partie de la feature, sans quoi on casse N scènes en
    croyant en ajuster une.

    **Une seule mise en page par scène, contenant N régions** — pas une liste de
    mises en page. Passer de 1 à N plus tard est additif ; l'inverse ne l'est
    pas.

    `name` est la clé de référence, comme partout ailleurs dans le projet
    (`<asset>_name`), donc ce qui entre dans le graphe de dépendances.
    """
    name:    str = "ui_layout"
    regions: list = field(default_factory=list)   # list[UIRegion]
    notes:   str = ""

    def get(self, region_name: str) -> UIRegion | None:
        return next((r for r in self.regions if r.name == region_name), None)

    def region_names(self) -> list[str]:
        return [r.name for r in self.regions]

    def bg_regions(self, render_mode: int = 0) -> list[UIRegion]:
        return [r for r in self.regions
                if r.resolved_target(render_mode) == TARGET_BG]

    def obj_regions(self, render_mode: int = 0) -> list[UIRegion]:
        return [r for r in self.regions
                if r.resolved_target(render_mode) == TARGET_OBJ]

    def font_names(self) -> set[str]:
        """Polices explicitement nommées par les régions. Une région qui hérite
        de la scène n'apparaît PAS ici : c'est à l'appelant d'ajouter le défaut,
        lui seul connaît la scène."""
        return {r.font_name for r in self.regions if r.font_name}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "regions": [r.to_dict() for r in self.regions],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UILayout":
        return cls(
            name    = str(d.get("name", "ui_layout")),
            regions = [UIRegion.from_dict(r) for r in d.get("regions", [])],
            notes   = str(d.get("notes", "")),
        )


def unique_region_name(taken, base: str = "region") -> str:
    """Nom libre mais unique **dans tout le projet** — `taken` est l'ensemble
    des noms déjà pris (cf. `Project.region_names()`).

    Pourquoi projet et pas mise en page : le nom se résout en `REGION_<NOM>`,
    un index dans une table C plate, exactement comme une clé de texte ou un
    nom de police. Deux régions homonymes dans deux mises en page rendraient
    la constante indécidable.

    Conséquence assumée : deux mises en page ne peuvent pas avoir chacune leur
    « boite_bas » ; la seconde devient `boite_bas_02`. Le jour où l'on voudra
    qu'un même script vise « la boîte basse de la mise en page COURANTE », il
    faudra une indirection par scène — la constante ne bougerait pas, seule sa
    résolution changerait, donc ce n'est pas une impasse."""
    taken = set(taken)
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n:02d}" in taken:
        n += 1
    return f"{base}_{n:02d}"
