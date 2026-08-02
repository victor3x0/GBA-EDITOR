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

# ── Types d'élément ───────────────────────────────────────────────
# Une mise en page contient désormais PLUSIEURS types dans une seule liste
# ordonnée (`UILayout.elements`) — l'ordre fixe l'empilement (z-order) et l'ordre
# des frères dans l'arbre. Chaque type porte un `kind` (sérialisé) et une
# capacité `can_contain` : seul un conteneur accueille des enfants, une feuille
# (texte, zone) jamais. Le « root » n'est pas un type : c'est le RÔLE d'un
# élément de premier niveau, qui porte alors l'ancrage de son sous-arbre.
KIND_REGION = "region"   # zone de texte RUNTIME (script écrit dedans) — feuille
KIND_PANEL  = "panel"    # conteneur qui peut dessiner un FOND ; racine = ancrage
KIND_TEXT   = "text"     # texte AUTHORÉ (clé de table) — feuille

# ── Fonds de conteneur ────────────────────────────────────────────
# Le fond d'un `UIPanel` est un champ polymorphe (« à quoi ressemble la zone »),
# séparé de la géométrie (« où »). Un panel sans fond est un groupe invisible.
#   couleur     : une ENTRÉE DE PALETTE (nom + index), pas du RGB libre — c'est
#                 le hardware qui l'impose (cf. project_palette_system_design).
#   nine-slice  : un cadre tuilé (coins fixes, bords/centre répétés) — quasi
#                 gratuit sur GBA. L'asset dédié reste à créer.
#   background  : un fond tuilé référencé, rogné en bas/à droite si la zone est
#                 plus petite que l'asset.
FILL_NONE  = "none"
FILL_COLOR = "color"
FILL_NINE  = "nine_slice"
FILL_BG    = "background"
FILL_KINDS = (FILL_NONE, FILL_COLOR, FILL_NINE, FILL_BG)

# Fonds permis selon la CIBLE de rendu (dérivée du root). Un background n'est pas
# un sprite : interdit sur OBJ. Le reste passe partout (le nine-slice sur OBJ est
# possible mais cher — permis, l'éditeur pourra prévenir).
_FILL_TARGETS = {
    FILL_NONE:  (TARGET_BG, TARGET_OBJ),
    FILL_COLOR: (TARGET_BG, TARGET_OBJ),
    FILL_NINE:  (TARGET_BG, TARGET_OBJ),
    FILL_BG:    (TARGET_BG,),
}


def fill_allowed(fill_kind: str, target: str) -> bool:
    """Ce mode de fond est-il compatible avec cette cible de rendu ?"""
    return target in _FILL_TARGETS.get(fill_kind, ())

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
    kind = KIND_REGION       # attribut de classe (pas un champ dataclass)
    can_contain = False      # feuille : n'accueille jamais d'enfants
    name:   str = "region"
    # Nom de l'élément PARENT dans la même mise en page ("" = racine). L'arbre
    # d'UI se DÉRIVE de ces refs, il ne se stocke pas : la liste `regions` reste
    # plate, exactement comme la table de textes reste plate et l'arbre se
    # reconstruit des chemins (cf. TextTreePanel). Une ref pendante (parent
    # supprimé) est traitée comme racine, jamais comme une erreur. Le parent est
    # cité par NOM et non par index : renommer une zone doit donc retargetter les
    # enfants (`UILayout.retarget_parent`), comme un renommage de clé de texte.
    parent: str = ""
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
            "kind": KIND_REGION,
            "name": self.name, "parent": self.parent, "anchor": self.anchor,
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
            parent       = str(d.get("parent", "")),
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
        if layout.resolved_target(r, render_mode) != TARGET_OBJ:
            continue
        g = strip_geometry(r)
        place[r.name] = {"oam_rel": oam, "tile_rel": tiles, **g}
        oam += g["oam"]
        tiles += g["tiles"]
    return {"place": place, "oam": oam, "tiles": tiles}


# ── Mise en page ──────────────────────────────────────────────────

@dataclass
class UIPanel:
    """Conteneur, et seul type à pouvoir dessiner un FOND. Au premier niveau il
    joue le RÔLE de root et porte l'ancrage du sous-arbre. Sans fond
    (`fill_kind == FILL_NONE`), c'est un simple groupe invisible.

    **Le fond est un champ polymorphe**, séparé de la géométrie :
      couleur     → une ENTRÉE de palette : `fill_palette` (nom de PaletteBank) +
                    `fill_index` (0-15). Pas de RGB libre — le hardware l'impose.
      nine-slice  → `fill_asset` = un asset de cadre tuilé (à créer).
      background  → `fill_asset` = un fond tuilé, rogné bas/droite si la zone est
                    plus petite ; interdit sur cible OBJ (cf. `fill_allowed`).

    Géométrie en pixels comme la zone. `anchor`/`anchor_actor` ne comptent que
    lorsque le panel est racine."""
    kind = KIND_PANEL
    can_contain = True
    name: str = "panel"
    parent: str = ""
    x: int = 0
    y: int = 0
    w: int = 64
    h: int = 32
    anchor: str = ANCHOR_SCREEN
    anchor_actor: str = ""
    # ── Fond (polymorphe selon fill_kind) ─────────────────────────
    fill_kind: str = FILL_NONE
    fill_palette: str = ""   # nom de PaletteBank (fond couleur)
    fill_index: int = 0      # index 0-15 dans la palette (fond couleur)
    fill_asset: str = ""     # nom d'asset (nine-slice / background)

    def to_dict(self) -> dict:
        return {"kind": KIND_PANEL, "name": self.name, "parent": self.parent,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "anchor": self.anchor, "anchor_actor": self.anchor_actor,
                "fill_kind": self.fill_kind, "fill_palette": self.fill_palette,
                "fill_index": self.fill_index, "fill_asset": self.fill_asset}

    @classmethod
    def from_dict(cls, d: dict) -> "UIPanel":
        anchor = d.get("anchor", ANCHOR_SCREEN)
        fk = d.get("fill_kind", FILL_NONE)
        return cls(
            name=str(d.get("name", "panel")), parent=str(d.get("parent", "")),
            x=int(d.get("x", 0)), y=int(d.get("y", 0)),
            w=int(d.get("w", 64)), h=int(d.get("h", 32)),
            anchor=anchor if anchor in ANCHORS else ANCHOR_SCREEN,
            anchor_actor=str(d.get("anchor_actor", "")),
            fill_kind=fk if fk in FILL_KINDS else FILL_NONE,
            fill_palette=str(d.get("fill_palette", "")),
            fill_index=int(d.get("fill_index", 0) or 0),
            fill_asset=str(d.get("fill_asset", "")))


@dataclass
class UIText:
    """Texte AUTHORÉ — feuille (jamais parent). Le contenu ne vit pas dans
    l'élément : `text_key` pointe la table de textes (auto-enregistrée), pour ne
    pas dupliquer un littéral qui échapperait à l'édition centralisée
    ([[project-text-table]]). `wrap` bascule en multiligne ; c'est le même widget
    que le cas court, avec plus de champs exposés — pas un type séparé."""
    kind = KIND_TEXT
    can_contain = False
    name: str = "text"
    parent: str = ""
    x: int = 0
    y: int = 0
    w: int = 64
    h: int = 16
    anchor: str = ANCHOR_SCREEN
    anchor_actor: str = ""
    text_key: str = ""
    font_name: str = ""
    align: str = "left"
    wrap: bool = False

    def to_dict(self) -> dict:
        return {"kind": KIND_TEXT, "name": self.name, "parent": self.parent,
                "x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "anchor": self.anchor, "anchor_actor": self.anchor_actor,
                "text_key": self.text_key, "font_name": self.font_name,
                "align": self.align, "wrap": self.wrap}

    @classmethod
    def from_dict(cls, d: dict) -> "UIText":
        anchor = d.get("anchor", ANCHOR_SCREEN)
        align = d.get("align", "left")
        return cls(
            name=str(d.get("name", "text")), parent=str(d.get("parent", "")),
            x=int(d.get("x", 0)), y=int(d.get("y", 0)),
            w=int(d.get("w", 64)), h=int(d.get("h", 16)),
            anchor=anchor if anchor in ANCHORS else ANCHOR_SCREEN,
            anchor_actor=str(d.get("anchor_actor", "")),
            text_key=str(d.get("text_key", "")),
            font_name=str(d.get("font_name", "")),
            align=align if align in ALIGNS else "left",
            wrap=bool(d.get("wrap", False)))


# Registre kind → constructeur. Un dict sans `kind` = région (format hérité,
# d'avant la généralisation multi-types).
_ELEMENT_FROM_DICT = {
    KIND_REGION: UIRegion.from_dict,
    KIND_PANEL:  UIPanel.from_dict,
    KIND_TEXT:   UIText.from_dict,
}


def element_from_dict(d: dict):
    """Désérialise un élément selon son `kind` (région par défaut, format hérité)."""
    return _ELEMENT_FROM_DICT.get(d.get("kind", KIND_REGION),
                                  UIRegion.from_dict)(d)


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
    # Liste ordonnée de TOUS les éléments (régions, panels, textes…) — l'ordre
    # fixe l'empilement et l'ordre des frères. `regions` reste exposé (propriété)
    # pour les consommateurs qui ne veulent que les zones (codegen, VRAM).
    elements: list = field(default_factory=list)
    notes:   str = ""

    @property
    def regions(self) -> list:
        """Sous-ensemble des éléments de type ZONE de texte, en lecture seule.
        Le codegen et le budget VRAM n'émettent que ces éléments-là ; les mutations
        (ajout/suppression/reparentage) passent, elles, par `elements`."""
        return [e for e in self.elements if getattr(e, "kind", KIND_REGION) == KIND_REGION]

    def get(self, name: str):
        """N'importe quel élément par son nom (tous types confondus)."""
        return next((e for e in self.elements if e.name == name), None)

    def can_contain(self, name: str) -> bool:
        """Un élément existant et conteneur peut-il accueillir un enfant ?"""
        e = self.get(name)
        return e is not None and getattr(e, "can_contain", False)

    def region_names(self) -> list[str]:
        return [e.name for e in self.regions]

    def element_names(self) -> list[str]:
        """Noms de TOUS les éléments — l'espace de nommage à garder unique pour
        que les refs `parent` soient sans ambiguïté (un panel et une zone ne
        peuvent pas partager un nom)."""
        return [e.name for e in self.elements]

    # ── Hiérarchie (dérivée des refs `parent`) ────────────────────
    # L'arbre n'est jamais stocké : `elements` reste une liste plate et ces
    # helpers le reconstruisent, TOUS types confondus. L'ORDRE de la liste fixe
    # l'ordre des frères (et le z-order entre éléments qui dessinent). Une ref
    # `parent` pendante est traitée comme racine — supprimer un parent ne casse
    # rien, ses enfants remontent d'un cran à l'affichage.

    def children(self, name: str) -> list:
        """Enfants directs de `name`, dans l'ordre de la liste."""
        return [e for e in self.elements if e.parent == name]

    def roots(self) -> list:
        """Éléments de premier niveau : sans parent, ou parent pendant."""
        names = {e.name for e in self.elements}
        return [e for e in self.elements if not e.parent or e.parent not in names]

    def ancestors(self, name: str) -> list[str]:
        """Chaîne des parents en remontant, garde-fou anti-boucle inclus (des
        données corrompues ne doivent pas faire tourner l'éditeur à l'infini)."""
        out: list[str] = []
        seen: set[str] = {name}
        cur = self.get(name)
        while cur is not None and cur.parent and cur.parent not in seen:
            out.append(cur.parent)
            seen.add(cur.parent)
            cur = self.get(cur.parent)
        return out

    def would_cycle(self, name: str, new_parent: str) -> bool:
        """Vrai si parenter `name` sous `new_parent` fermerait une boucle : soit
        on se prend soi-même, soit la nouvelle cible est déjà un descendant."""
        if not new_parent or new_parent == name:
            return new_parent == name
        # boucle ⟺ `name` figure parmi les ancêtres de `new_parent`
        return name in self.ancestors(new_parent)

    def descendants(self, name: str) -> list:
        """Tout le sous-arbre sous `name` (DFS, ordre de liste), `name` exclu."""
        out: list = []
        for child in self.children(name):
            out.append(child)
            out.extend(self.descendants(child.name))
        return out

    def in_tree_order(self):
        """(profondeur, élément) en parcours préfixe, l'ordre de liste faisant foi
        entre frères — ce que consomme la vue arbre. Défensif contre les refs
        pendantes (racines) et les cycles (chaque nœud visité une fois)."""
        seen: set[str] = set()
        out: list = []

        def walk(node, depth: int) -> None:
            if node.name in seen:
                return
            seen.add(node.name)
            out.append((depth, node))
            for child in self.children(node.name):
                walk(child, depth + 1)

        for e in self.roots():
            walk(e, 0)
        # Nœuds jamais atteints (cycle pur entre eux) : rattachés en racine, pour
        # qu'aucun élément ne disparaisse de l'arbre.
        for e in self.elements:
            if e.name not in seen:
                walk(e, 0)
        return out

    # ── Ordre / z-order (réordonnancement des frères) ─────────────
    # L'ordre de `elements` EST le z-order (frère tardif = au-dessus) et l'ordre
    # des frères dans l'arbre. Trois consommateurs le lisent : l'arbre (via
    # `children`), le canvas (empilement) et le codegen (ordre de dessin des
    # fonds). Pour qu'ils s'accordent, un réordonnancement RÉÉCRIT `elements` en
    # DFS canonique — parent avant ses enfants, frères dans l'ordre voulu — via
    # `_flatten`. Une liste non canonique (héritée d'un reparentage qui ne
    # déplaçait pas dans la liste) est ainsi normalisée au passage.

    def _flatten(self, order_override: dict | None = None) -> list:
        """`elements` réordonné en DFS canonique. `order_override` :
        {nom_parent: [noms de frères...]} force l'ordre des enfants de ce parent
        ("" = racines) ; les frères non cités gardent leur ordre courant, à la
        suite. Défensif : cycles purs rattachés en fin, aucun élément perdu."""
        override = order_override or {}
        out: list = []
        seen: set[str] = set()

        def ordered(children_list, key):
            if key not in override:
                return children_list
            by_name = {c.name: c for c in children_list}
            forced = [by_name[n] for n in override[key] if n in by_name]
            rest = [c for c in children_list if c.name not in set(override[key])]
            return forced + rest

        def emit(node) -> None:
            if node.name in seen:
                return
            seen.add(node.name)
            out.append(node)
            for child in ordered(self.children(node.name), node.name):
                emit(child)

        for root in ordered(self.roots(), ""):
            emit(root)
        for e in self.elements:            # cycles purs : ne rien perdre
            if e.name not in seen:
                out.append(e)
                seen.add(e.name)
        return out

    def _parent_key(self, element) -> str:
        """Clé du parent pour `_flatten`/`children` : "" si racine (sans parent
        ou parent pendant), sinon le nom du parent."""
        p = getattr(element, "parent", "")
        return p if (p and self.get(p) is not None) else ""

    def _siblings(self, parent_key: str) -> list:
        """Frères sous `parent_key` dans l'ordre courant ("" = racines)."""
        return self.roots() if parent_key == "" else self.children(parent_key)

    def move_sibling(self, name: str, direction: str) -> bool:
        """Déplace `name` parmi ses frères : "up"/"down" d'un cran, "top"/"bottom"
        à une extrémité. Réécrit `elements` (DFS canonique) et renvoie True si ça
        a bougé, False sinon (introuvable, déjà en bout, direction inconnue)."""
        e = self.get(name)
        if e is None:
            return False
        key = self._parent_key(e)
        names = [s.name for s in self._siblings(key)]
        if name not in names:
            return False
        i, n = names.index(name), len(names)
        order = names[:]
        order.pop(i)
        if direction == "up":
            if i == 0:
                return False
            order.insert(i - 1, name)
        elif direction == "down":
            if i >= n - 1:
                return False
            order.insert(i + 1, name)
        elif direction == "top":
            if i == 0:
                return False
            order.insert(0, name)
        elif direction == "bottom":
            if i >= n - 1:
                return False
            order.append(name)
        else:
            return False
        self.elements[:] = self._flatten({key: order})
        return True

    def place_child(self, name: str, new_parent: str,
                    before_name: str | None = None) -> bool:
        """Rattache `name` à `new_parent` ("" = racine) et le pose JUSTE AVANT
        `before_name` parmi ses (nouveaux) frères, ou en dernier si `before_name`
        est None/absent. Refuse feuille-comme-parent et cycle (`can_contain`,
        `would_cycle`). Réécrit `elements` en DFS canonique. True si un changement
        a bien eu lieu — reparentage, repositionnement, ou les deux."""
        e = self.get(name)
        if e is None:
            return False
        if new_parent and not self.can_contain(new_parent):
            return False
        if self.would_cycle(name, new_parent):
            return False
        key = new_parent if (new_parent and self.get(new_parent) is not None) else ""
        before = [x.name for x in self.elements]      # pour détecter un no-op
        old_parent = e.parent
        e.parent = key
        names = [s.name for s in self._siblings(key) if s.name != name]
        if before_name and before_name in names and before_name != name:
            names.insert(names.index(before_name), name)
        else:
            names.append(name)
        new_flat = self._flatten({key: names})
        if [x.name for x in new_flat] == before and key == old_parent:
            e.parent = old_parent      # rien n'a changé : ne pas salir l'historique
            return False
        self.elements[:] = new_flat
        return True

    def retarget_parent(self, old: str, new: str) -> int:
        """Rebranche les enfants d'un élément renommé (`old` → `new`) et renvoie
        le nombre de refs mises à jour. À appeler par le flux de renommage, comme
        on met à jour les scripts qui citent une clé — sinon renommer un élément
        orphelinerait ses enfants (leur `parent` pointant l'ancien nom)."""
        n = 0
        for e in self.elements:
            if e.parent == old:
                e.parent = new
                n += 1
        return n

    # ── Ancrage & origine : remontée au ROOT ──────────────────────
    # L'ancrage n'est plus une propriété de chaque élément mais du ROOT (élément
    # top-level de la branche) : un enfant hérite du frame de son root et se
    # positionne en pixels RELATIFS à son parent. Ces helpers font la remontée ;
    # un élément sans parent est son propre root, donc le comportement d'avant
    # (tout est root) est un cas particulier — rien ne change pour les données
    # plates existantes.

    def root_of(self, name: str):
        """Élément top-level de la branche de `name` (remontée des parents, sûre
        face aux cycles et aux refs pendantes). C'est lui qui porte l'ancrage."""
        cur = self.get(name)
        seen: set[str] = set()
        while cur is not None and cur.parent and cur.name not in seen:
            seen.add(cur.name)
            nxt = self.get(cur.parent)
            if nxt is None:        # parent pendant → `cur` est le root effectif
                break
            cur = nxt
        return cur

    def effective_anchor(self, element) -> tuple[str, str]:
        """(anchor, anchor_actor) hérités du root de `element`."""
        r = self.root_of(element.name) or element
        return getattr(r, "anchor", ANCHOR_SCREEN), getattr(r, "anchor_actor", "")

    def resolved_target(self, element, render_mode: int = 0) -> str:
        """Cible BG/OBJ dérivée de l'ancrage du ROOT — plus de l'élément
        lui-même : un enfant hérite du frame de son root."""
        r = self.root_of(element.name) or element
        forced = forced_target(getattr(r, "anchor", ANCHOR_SCREEN), render_mode)
        if forced:
            return forced
        t = getattr(r, "target", "")
        return t if t in TARGETS else TARGET_BG

    def absolute_origin(self, element, actor_pos) -> tuple[int, int, bool]:
        """(x, y, resolved) : position ÉCRAN de l'origine de `element`, en sommant
        les offsets jusqu'au root, puis en ajoutant le socle du frame — (0,0) en
        écran/monde, la position de l'acteur en ancrage actor. `actor_pos` =
        callable nom→(x,y) ou None. `resolved` est faux si l'acteur du root est
        introuvable (la position affichée n'est alors pas celle du jeu)."""
        chain = [element] + [self.get(a) for a in self.ancestors(element.name)]
        chain = [e for e in chain if e is not None]
        ox = sum(int(e.x) for e in chain)
        oy = sum(int(e.y) for e in chain)
        root = chain[-1] if chain else element
        resolved = True
        if getattr(root, "anchor", "") == ANCHOR_ACTOR:
            ap = actor_pos(getattr(root, "anchor_actor", "")) if actor_pos else None
            if ap is None:
                resolved = False
            else:
                ox += ap[0]
                oy += ap[1]
        return ox, oy, resolved

    def parent_origin(self, element, actor_pos) -> tuple[int, int]:
        """(x, y) écran de l'origine du PARENT de `element` — ou le socle du
        frame si `element` est un root. Sert à reconvertir une position absolue
        du canvas en coordonnées RELATIVES au parent, au relâchement d'un geste."""
        parent = self.get(element.parent) if element.parent else None
        if parent is None:
            if getattr(element, "anchor", "") == ANCHOR_ACTOR:
                ap = actor_pos(getattr(element, "anchor_actor", "")) if actor_pos else None
                return (ap[0], ap[1]) if ap else (0, 0)
            return (0, 0)
        ax, ay, _ = self.absolute_origin(parent, actor_pos)
        return ax, ay

    def bg_regions(self, render_mode: int = 0) -> list[UIRegion]:
        return [r for r in self.regions
                if self.resolved_target(r, render_mode) == TARGET_BG]

    def obj_regions(self, render_mode: int = 0) -> list[UIRegion]:
        return [r for r in self.regions
                if self.resolved_target(r, render_mode) == TARGET_OBJ]

    def font_names(self) -> set[str]:
        """Polices explicitement nommées par les régions. Une région qui hérite
        de la scène n'apparaît PAS ici : c'est à l'appelant d'ajouter le défaut,
        lui seul connaît la scène."""
        return {r.font_name for r in self.regions if r.font_name}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "elements": [e.to_dict() for e in self.elements],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UILayout":
        # `elements` (nouveau, multi-types) ou `regions` (hérité : que des zones,
        # sans `kind`). `element_from_dict` retombe sur la région par défaut.
        raw = d.get("elements")
        if raw is None:
            raw = d.get("regions", [])
        return cls(
            name     = str(d.get("name", "ui_layout")),
            elements = [element_from_dict(e) for e in raw],
            notes    = str(d.get("notes", "")),
        )


def unique_element_name(taken, base: str = "element") -> str:
    """Nom d'élément libre mais unique dans `taken` — générique, tous types
    (alias de `unique_region_name`, dont la logique ne dépend pas du type)."""
    return unique_region_name(taken, base)


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
