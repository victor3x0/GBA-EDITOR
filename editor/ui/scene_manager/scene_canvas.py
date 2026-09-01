"""
GBA Editor — Scene Canvas
Canvas dynamique (plafond monde 32767×32767) avec caméra 240×160 déplaçable.

Layers (z-order) :
  z=0..3   → BG3..BG0 (PNG composités)
  z=10+n   → sprites placés (draggables)
  z=100    → grille 8px (optionnelle)
  z=150    → rectangle caméra (draggable)
  z=200    → bordure canvas
"""

import copy
from typing import Optional

from core.command_dispatcher import get_dispatcher
from core.models.tile_codec import unpack_se, hex_to_tile, hex_to_tile8, flip_h, flip_v

# Les constantes slope sont aussi importées par canvas_tools — on les garde
# ici uniquement pour CollisionOverlay._slope_path et _draw_tile.
from core.history import MoveActorCmd, MoveActorGroupCmd, get_history
from core.models.resource import MIME_PREFAB_TEMPLATE
from core.models.scene import Actor
from core.models import collision_tiles as CT
from core.models.collision_tiles import (
    COLLISION_TILE_SIZE,
    TILE_EMPTY,
    TILE_SLOPE_L,
    TILE_SLOPE_L_HI,
    TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_L_INV,
    TILE_SLOPE_L_LO,
    TILE_SLOPE_L_LO_INV,
    TILE_SLOPE_L_STEEP_HI,
    TILE_SLOPE_L_STEEP_HI_INV,
    TILE_SLOPE_L_STEEP_LO,
    TILE_SLOPE_L_STEEP_LO_INV,
    TILE_SLOPE_R,
    TILE_SLOPE_R_HI,
    TILE_SLOPE_R_HI_INV,
    TILE_SLOPE_R_INV,
    TILE_SLOPE_R_LO,
    TILE_SLOPE_R_LO_INV,
    TILE_SLOPE_R_STEEP_HI,
    TILE_SLOPE_R_STEEP_HI_INV,
    TILE_SLOPE_R_STEEP_LO,
    TILE_SLOPE_R_STEEP_LO_INV,
    TILE_SOLID,
)
from core.project import Project
from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from ui.common.theme import T, QSS, C
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.canvas_top_bar import CanvasTopBar
from core.sprite_compose import compose_frame_image
from core.gba_color import quantize_preview
from codegen.grit_conversion import resolve_palette_bank, resolve_obj_palette_bank
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionGraphicsItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from core.selection_bus import get_bus, CameraSelection
from ui.scene_manager.align_snap import (
    candidate_lines, collect_targets, snap as _align_snap, SNAP_PX as _ALIGN_SNAP_PX,
)

# ── Constantes GBA ───────────────────────────────────────────────
GBA_W = 240
GBA_H = 160
# Plafond MONDE : les coordonnées de la caméra sont des s16 (bounds jusqu'à
# 32767), donc un monde au-delà de 32767 ne serait pas scrollable. Le scroll
# caméra max vaut alors 32767 - screen.width. Ce n'est PAS
# une limite de carte : un axe de map > 64 tuiles est streamé au build
# (main_gen.py), le monde peut être bien plus grand que 512×512.
MAX_CANVAS_W = 32767
MAX_CANVAS_H = 32767

# Aperçu des windows matérielles — une teinte par région (WIN0, WIN1), reprise
# du bleu de la carte WINDOWS de l'inspecteur de scène.
_WIN_COLORS = (C.ACCENT_BLU, C.ACCENT_ORG)

_PLACEHOLDER_SIZE = 16
_PLACEHOLDER_ICO = 12


def _screen_scale(painter: QPainter, widget=None) -> float:
    """Combien de pixels ÉCRAN vaut une unité de scène pour ce painter — zoom de
    la vue (et transform de l'item) × devicePixelRatio de l'écran. Les icônes
    d'UI du canvas s'en servent pour se faire rendre à la bonne résolution au
    lieu d'être un pixmap agrandi."""
    lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
    return lod * (widget.devicePixelRatioF() if widget is not None else 1.0)


def _draw_placeholder(painter: QPainter, scale: float = 1.0) -> None:
    """Repère 16×16 des actors/prefabs sans sprite, dessiné dans le repère
    courant du painter. `scale` = facteur d'échelle écran effectif : le glyphe
    est demandé à cette résolution pour rester net quand la vue est zoomée."""
    from ui.common.icons import scaled_pixmap

    s = _PLACEHOLDER_SIZE
    painter.fillRect(QRectF(0, 0, s, s), QColor(30, 60, 90, 210))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(QPen(QColor(100, 180, 255, 220), 1))
    painter.drawRect(QRectF(0, 0, s - 1, s - 1))
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    px = scaled_pixmap("actor_empty", "#88ccff", _PLACEHOLDER_ICO, scale)
    painter.drawPixmap(
        QRectF(2, 2, _PLACEHOLDER_ICO, _PLACEHOLDER_ICO), px, QRectF(px.rect())
    )


def _make_placeholder_pixmap() -> QPixmap:
    """Pixmap 16×16 pour les actors/prefabs sans sprite.

    Porte la GÉOMÉTRIE de l'item (boundingRect, hit-test) ; à l'écran c'est
    `_draw_placeholder()` qui redessine le repère au zoom courant
    (cf. SpriteItem.paint) — un pixmap figé serait flou dès le zoom ×2."""
    px = QPixmap(_PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    _draw_placeholder(p)
    p.end()
    return px


def _pal_to_rgb16(colors_bgr555: list) -> list:
    """Banque BGR555 → 16 triplets (r,g,b), complétée à 16 (index manquants →
    noir). L'index 0 reste dans la liste mais est traité comme transparent au
    rendu (cf. BgLayerRaster)."""
    from core.gba_color import bgr555_to_rgb888
    out = []
    for i in range(16):
        out.append(bgr555_to_rgb888(colors_bgr555[i]) if i < len(colors_bgr555) else (0, 0, 0))
    return out


class BgLayerRaster:
    """État de rendu PAR TUILE d'un layer BG dans le canvas de scène.

    Base = **palette d'origine** de l'asset : chaque tuile est rendue depuis la
    représentation compressée (`tileset` + `tilemap` + `palettes` du
    BackgroundAsset), exactement comme le build. L'asset n'est JAMAIS modifié.

    Par-dessus, des **overrides de scène** réassignent la palette d'une tuile
    (`layer.tile_palette_overrides` → slot dans `scene.active_bg_palettes`) : on relit le
    MÊME index de pixel dans une autre banque de 16 couleurs (sémantique
    `SE_PALBANK` du GBA). Réversible — retirer l'override rend la palette
    d'origine. Patche un bloc 8×8 en place pendant la peinture."""

    TILE = 8

    def __init__(self, compiled: dict, bank_rgb_for):
        # compiled     : {tiles_w, tiles_h, tileset(list[hex]), tilemap(list[SE]),
        #                 palettes(list[list[int]] BGR555)} — palettes d'origine.
        # bank_rgb_for : callable(slot:int) -> list[(r,g,b)] (16) | None, banque
        #                active de la scène pour un override.
        self.tiles_w = compiled["tiles_w"]
        self.tiles_h = compiled["tiles_h"]
        self._tilemap = list(compiled["tilemap"])
        self._bpp = compiled.get("bpp", 4)
        if self._bpp == 8:
            # 8bpp : tuiles en octets, UNE palette de 256 couleurs (pas de banques,
            # pas d'override de scène — cf. _pal_for).
            from core.gba_color import bgr555_to_rgb888
            self._tiles = [hex_to_tile8(t) for t in compiled["tileset"]]
            pal = compiled["palettes"][0] if compiled["palettes"] else []
            self._pal_rgb = [[bgr555_to_rgb888(c) for c in pal]]
        else:
            self._tiles = [hex_to_tile(t) for t in compiled["tileset"]]
            self._pal_rgb = [_pal_to_rgb16(pal) for pal in compiled["palettes"]]
        self._bank_rgb_for = bank_rgb_for
        self._qimg = QImage(self.tiles_w * self.TILE, self.tiles_h * self.TILE,
                            QImage.Format.Format_RGBA8888)

    # ── Décodage d'une cellule ────────────────────────────────────
    def _cell_grid(self, cell: int):
        """Grille d'index 8×8 (list[64]) de la cellule, flips appliqués."""
        tid, pb, fh, fv = unpack_se(self._tilemap[cell])
        grid = tuple(self._tiles[tid]) if tid < len(self._tiles) else tuple([0] * 64)
        if fh:
            grid = flip_h(grid)
        if fv:
            grid = flip_v(grid)
        return grid, pb

    def _cell_block(self, cell: int, pal_rgb):
        """Bloc PIL RGBA 8×8 de la cellule avec la palette `pal_rgb` (index 0 =
        transparent)."""
        from PIL import Image
        grid, _ = self._cell_grid(cell)
        blk = Image.new("RGBA", (self.TILE, self.TILE), (0, 0, 0, 0))
        px = blk.load()
        for y in range(self.TILE):
            for x in range(self.TILE):
                idx = grid[y * self.TILE + x]
                if idx == 0 or idx >= len(pal_rgb):
                    continue
                r, g, b = pal_rgb[idx]
                px[x, y] = (r, g, b, 255)
        return blk

    def _pal_for(self, cell: int, slot):
        """Palette RGB à utiliser pour une cellule : override de scène si `slot`
        résolu (4bpp uniquement), sinon la palette d'origine de la tuile. En 8bpp,
        pas de banques ni d'override : toujours l'unique palette de 256."""
        if self._bpp != 8 and slot is not None:
            bank = self._bank_rgb_for(slot)
            if bank:
                return bank
        _, pb = self._cell_grid(cell)
        return self._pal_rgb[pb] if pb < len(self._pal_rgb) else self._pal_rgb[0]

    # ── Composition ───────────────────────────────────────────────
    def render(self, tile_palette_overrides: dict):
        """Recompose tout le layer : palettes d'origine + overrides de scène."""
        from PIL import Image
        out = Image.new("RGBA", (self.tiles_w * self.TILE, self.tiles_h * self.TILE),
                        (0, 0, 0, 0))
        for cell in range(len(self._tilemap)):
            col, row = cell % self.tiles_w, cell // self.tiles_w
            slot = tile_palette_overrides.get((col, row))
            blk = self._cell_block(cell, self._pal_for(cell, slot))
            out.paste(blk, (col * self.TILE, row * self.TILE))
        self._qimg = _pil_to_qimage(out)

    def patch_tile(self, col: int, row: int, slot):
        """Recolorise le bloc 8×8 (col,row) : override `slot`, ou palette
        d'origine si slot None."""
        if not (0 <= col < self.tiles_w and 0 <= row < self.tiles_h):
            return
        cell = row * self.tiles_w + col
        blk = self._cell_block(cell, self._pal_for(cell, slot))
        block_qimg = _pil_to_qimage(blk)
        painter = QPainter(self._qimg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(col * self.TILE, row * self.TILE, block_qimg)
        painter.end()

    def to_pixmap(self) -> QPixmap:
        return QPixmap.fromImage(self._qimg)


def _pil_to_qimage(img) -> QImage:
    """PIL RGBA → QImage indépendant (copié, buffer non partagé)."""
    data = bytes(img.tobytes("raw", "RGBA"))
    return QImage(data, img.width, img.height,
                  QImage.Format.Format_RGBA8888).copy()


def build_bg_raster(p: Project, scene, layer, ap) -> Optional["BgLayerRaster"]:
    """Construit le `BgLayerRaster` d'un layer depuis sa palette d'origine
    (représentation compressée de l'asset). Peignable pour TOUT layer ayant une
    image — indépendant de `layer.pal_bank` (plus de banque de base requise :
    c'est ça qui rend les layers « Sans palette » peignables). None si pas
    d'image/asset exploitable."""
    if not layer.background_name or not ap.is_file():
        return None
    ba = p.get_background(layer.background_name)
    from core.bg_import import compiled_background
    # `p` transmis : le canvas montre aussi les fonds animés posés sur ce fond
    # dans le Background Editor, figés sur leur première image.
    compiled = compiled_background(ba, ap, p)
    if not compiled or not compiled.get("tilemap"):
        return None

    def _bank_rgb_for(slot: int):
        b = resolve_palette_bank(p, scene.active_bg_palettes, slot)
        return _pal_to_rgb16(b.colors) if b and b.colors else None

    raster = BgLayerRaster(compiled, _bank_rgb_for)
    raster.render(getattr(layer, "tile_palette_overrides", {}) or {})
    return raster


def _bg_pixmap(p: Project, scene, layer, ap) -> Optional[QPixmap]:
    """Pixmap d'un layer BG pour le canvas — rendu PAR TUILE depuis la palette
    d'origine de l'asset + overrides de scène peints (`layer.tile_palette_overrides`).
    Repli sur le PNG brut si l'asset n'a pas de représentation exploitable."""
    # layer.background_name vide -> `ap` pointe sur le DOSSIER background_images_dir
    # (pas un fichier) : ne rien afficher (l'ancien QPixmap(dir) échouait
    # silencieusement, mais Image.open(dir) lève PermissionError).
    if not layer.background_name or not ap.is_file():
        return None
    raster = build_bg_raster(p, scene, layer, ap)
    if raster is not None:
        return raster.to_pixmap()
    return QPixmap(str(ap))


# dir_x/dir_y (-1|0|1) → dir id 1-8, identique au _dlut du runtime
# (NW=8,N=1,NE=2,W=7,omni=0,E=3,SW=6,S=5,SE=4).
_DIR_ID_LUT = {
    (-1, -1): 8, (0, -1): 1, (1, -1): 2,
    (-1,  0): 7, (0,  0): 0, (1,  0): 3,
    (-1,  1): 6, (0,  1): 5, (1,  1): 4,
}


def _preview_frame_for_actor(sprite, sprite_comp, actor):
    """
    Frame statique + flip à afficher pour un actor dans le canvas de scène.
    Choisit la direction correspondant à dir_x/dir_y de l'actor (comme le
    runtime) ; pour une direction miroir, retourne la frame de la direction
    source + le flip du miroir (à composer avec le flip du component).
    Repli identique au runtime : direction demandée absente → omni (dir 0) →
    première direction. Retourne (frame|None, flip_h, flip_v).
    """
    state_name = getattr(sprite_comp, "initial_state", None) if sprite_comp else None
    state = next((s for s in sprite.states if s.name == state_name), None)
    state = state or (sprite.states[0] if sprite.states else None)
    if not state or not state.directions:
        return None, False, False
    dir_map = {sd.dir: sd for sd in state.directions}
    dx = max(-1, min(1, getattr(actor, "dir_x", 0)))
    dy = max(-1, min(1, getattr(actor, "dir_y", 0)))
    want = _DIR_ID_LUT.get((dx, dy), 0)
    sd = dir_map.get(want) or dir_map.get(0) or state.directions[0]
    if sd.mirror_of is not None:
        # Miroir : les frames vivent sur la direction source, retournées.
        src = dir_map.get(sd.mirror_of, sd)
        frame = src.frames[0] if src.frames else None
        return frame, sd.flip_h, sd.flip_v
    return (sd.frames[0] if sd.frames else None), False, False


# ──────────────────────────────────────────────────────────────────
#  Ordre de composition — UNE règle, celle du hardware, jamais un empilement
#  choisi pour le confort de l'édition.
#
#  Priorité GBA = bg_slot directement pour un fond ET pour le layer d'UI
#  (0 = devant, 3 = derrière — cf. `main_gen._gen_scene_init`, le commentaire
#  au-dessus de `bg_cnt_set`). Un acteur (OBJ) porte sa PROPRE priorité
#  (`Actor.priority`, 0-3, mêmes bornes) — et à priorité ÉGALE entre un OBJ et
#  un BG, c'est l'OBJ qui passe DEVANT (règle documentée du hardware GBA, pas
#  un choix de l'éditeur). D'où deux crans par niveau de priorité : le BG,
#  puis l'OBJ juste au-dessus.
#
#  Avant cette fonction, un acteur avait un zValue FIXE (10) et une zone
#  d'interface un zValue FIXE (120) : l'acteur passait donc TOUJOURS sous
#  l'interface dans le canvas, quelle que soit la priorité réelle — le
#  contraire de ce que montre la ROM dès que l'UI vit sur un BG de priorité
#  supérieure à 0 (le cas courant : text_bg vaut rarement 0).
# ──────────────────────────────────────────────────────────────────

def _hw_layer_z(priority: int, is_obj: bool) -> float:
    """zValue Qt qui REPRODUIT l'ordre de composition du hardware, jamais un
    empilement approché. `priority` est déjà l'échelle GBA (0 devant, 3
    derrière) — bg_slot pour un fond ou le layer d'UI, `Actor.priority` pour
    un acteur."""
    p = max(0, min(3, int(priority)))
    return float((3 - p) * 2 + (1 if is_obj else 0))


# ──────────────────────────────────────────────────────────────────
#  Item sprite draggable
# ──────────────────────────────────────────────────────────────────
class SpriteItem(QGraphicsPixmapItem):
    def __init__(
        self,
        pixmap: QPixmap,
        actor: Actor,
        canvas_w: int,
        canvas_h: int,
        snap: bool = False,
        save_fn=None,
        origin_x: int = 0,
        origin_y: int = 0,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        rotation: float = 0.0,
        flip_h: bool = False,
        flip_v: bool = False,
        resolver=None,
        placeholder: bool = False,
        parent=None,
    ):
        super().__init__(pixmap, parent)
        self.scene_sprite = actor
        # Actor sans sprite : le pixmap ne sert que de géométrie, le repère est
        # redessiné à chaque paint() au zoom courant (cf. _paint_content).
        self._placeholder = placeholder
        # Résout une position x/y (px littéral, tile, ou réf de variable) en
        # pixels concrets pour l'affichage — cf. core.models.field_value.
        self._pos_resolver = resolver
        self.snap = snap
        # Initialisés avant setPos()/setFlags() plus bas : itemChange() peut être
        # appelé dès la construction (ItemSendsGeometryChanges) et les lit.
        self._drag_origin: tuple[int, int] | None = None
        self._drag_confirmed = False
        # Sous-arbre (Actor.parent, ROADMAP v0.23) capturé au press, pour le
        # faire suivre en translation groupée pendant le drag — cf. itemChange.
        self._drag_descendants: list = []
        self._drag_desc_origin: list = []
        self._mask_rects: list = []   # découpe par les windows (cf. set_mask_rects)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._save_fn = save_fn
        self._origin_x = origin_x
        self._origin_y = origin_y

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        # OBJ, priorité de CET acteur — pas un zValue fixe : deux acteurs de
        # priorités différentes doivent s'empiler comme le hardware le ferait.
        self.setZValue(_hw_layer_z(getattr(actor, "priority", 0), is_obj=True))

        # Décaler le pixmap dans le repère local pour que (0,0) = ancrage (origine)
        self.setOffset(-origin_x, -origin_y)

        # Transform : scale+flip EN PREMIER (espace objet), puis rotation — pivot = (0,0) = ancrage
        sx_eff = scale_x * (-1.0 if flip_h else 1.0)
        sy_eff = scale_y * (-1.0 if flip_v else 1.0)
        has_transform = (
            abs(sx_eff - 1.0) > 1e-4 or abs(sy_eff - 1.0) > 1e-4
            or abs(rotation) > 1e-4
        )
        if has_transform:
            t = QTransform()
            t.scale(sx_eff, sy_eff)
            if abs(rotation) > 1e-4:
                t.rotate(rotation)
            self.setTransform(t)

        # Item (0,0) = position logique de l'acteur — la caméra suit directement
        self.setPos(*self.pos_px())

    def pos_px(self) -> tuple[int, int]:
        """Position logique de l'acteur résolue en pixels (px/tile/réf variable)."""
        from core.models.field_value import FieldValue
        a = self.scene_sprite
        return (FieldValue.parse(a.x).px(self._pos_resolver),
                FieldValue.parse(a.y).px(self._pos_resolver))

    def sync_pos(self):
        """Repositionne l'item Qt depuis le modèle (setPos programmatique)."""
        self.setPos(*self.pos_px())

    def set_canvas_size(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h

    # En-deçà de ce déplacement (px), on considère qu'il s'agit d'un simple
    # clic (jitter sous-pixel entre press/release) et pas d'un vrai drag —
    # sans ce garde-fou, itemChange() snappait la position au premier micro-
    # mouvement, faisant "sauter" l'acteur au clic (cf bug rapporté).
    _CLICK_THRESHOLD = 2

    def mousePressEvent(self, e):
        # Capturer la position (résolue en px) avant le début du drag
        self._drag_origin = self.pos_px()
        self._drag_confirmed = False
        sc = self.scene()
        self._drag_descendants = sc.descendant_sprite_items(self) if sc is not None else []
        self._drag_desc_origin = [(it, *it.pos_px()) for it in self._drag_descendants]
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._drag_origin is not None:
            old_x, old_y = self._drag_origin
            new_x, new_y = self.pos_px()
            if (old_x, old_y) != (new_x, new_y):
                # Le sous-arbre a suivi en direct (itemChange) : réunir ses
                # déplacements dans la MÊME entrée d'historique que le parent.
                items = [(self.scene_sprite, old_x, old_y, new_x, new_y)]
                for it, ox, oy in self._drag_desc_origin:
                    nx, ny = it.pos_px()
                    if (ox, oy) != (nx, ny):
                        items.append((it.scene_sprite, ox, oy, nx, ny))
                cmd = (MoveActorGroupCmd(items) if len(items) > 1 else
                       MoveActorCmd(self.scene_sprite, old_x, old_y, new_x, new_y))
                # Pousser la commande SANS re-exécuter (le drag a déjà modifié actor)
                h = get_history()
                h._undo.append(cmd)  # bypass execute() — déjà fait par le drag
                h._redo.clear()
                h.changed.emit()
                if self._save_fn:
                    self._save_fn()
            self._drag_origin = None
            self._drag_confirmed = False
            self._drag_descendants = []
            self._drag_desc_origin = []

    def item_pos(self) -> tuple[float, float]:
        """Position Qt de l'item = position logique de l'acteur (item origin = ancrage)."""
        px, py = self.pos_px()
        return float(px), float(py)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            x, y = p.x(), p.y()
            if self._drag_origin is None:
                # setPos() programmatique hors drag (construction, sync depuis
                # l'inspector via move_actor_item…) — le modèle est déjà
                # à jour, ne pas le réécrire (donc ne pas re-snapper une
                # valeur hors-grille saisie volontairement au clavier).
                return QPointF(x, y)
            if not self._drag_confirmed:
                ox, oy = self._drag_origin
                if abs(x - ox) < self._CLICK_THRESHOLD and abs(y - oy) < self._CLICK_THRESHOLD:
                    # Jitter de clic, pas un vrai drag : ignorer le mouvement.
                    return QPointF(ox, oy)
                self._drag_confirmed = True
            if self.snap:
                x = round(x / 8) * 8
                y = round(y / 8) * 8
            # L'item (0,0) est directement la position logique de l'acteur
            self.scene_sprite.x = int(x)
            self.scene_sprite.y = int(y)
            if self._drag_desc_origin:
                # Translation groupée du sous-arbre (ROADMAP v0.23) : delta
                # depuis le DÉBUT du drag, pas depuis l'appel précédent — évite
                # toute dérive par accumulation d'arrondis de snap.
                ox0, oy0 = self._drag_origin
                dx, dy = int(x) - ox0, int(y) - oy0
                for it, ox, oy in self._drag_desc_origin:
                    it.scene_sprite.x = ox + dx
                    it.scene_sprite.y = oy + dy
                    it.setPos(*it.pos_px())
            if self.scene() is not None:
                self.scene().sprite_moved.emit()
            return QPointF(x, y)
        return super().itemChange(change, value)

    def set_mask_rects(self, rects: list):
        """Régions (coordonnées de SCÈNE) où ce sprite ne s'affiche pas —
        windows actives dont le bit OBJ est coupé. Cf. GBAScene.update_window_masks."""
        if rects == self._mask_rects:
            return
        self._mask_rects = list(rects)
        self.update()

    def _paint_content(self, painter, option, widget):
        """Le sprite lui-même : pixmap du jeu (nearest-neighbor, c'est du pixel
        art), ou repère d'actor sans sprite — une icône d'UI, redessinée à la
        résolution écran pour ne pas devenir floue au zoom."""
        if not self._placeholder:
            super().paint(painter, option, widget)
            return
        painter.save()
        painter.translate(self.offset())
        _draw_placeholder(painter, _screen_scale(painter, widget))
        painter.restore()

    def paint(self, painter, option, widget=None):
        # Supprimer le rendu de sélection Qt par défaut (dashed bleu)
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.StateFlag.State_Selected
        if self._mask_rects:
            # Clip limité au PIXMAP : l'outline de sélection et le repère
            # d'origine ci-dessous restent visibles, sinon un acteur masqué
            # deviendrait impossible à repérer et à manipuler dans l'éditeur.
            # mapFromScene : l'item porte scale/flip/rotation et un offset,
            # les rects arrivent en coordonnées de scène.
            painter.save()
            path = QPainterPath()
            path.addRect(self.boundingRect())
            for r in self._mask_rects:
                cut = QPainterPath()
                cut.addPolygon(self.mapFromScene(r))
                path = path.subtracted(cut)
            painter.setClipPath(path)
            self._paint_content(painter, clean, widget)
            painter.restore()
        else:
            self._paint_content(painter, clean, widget)
        # Outline quand sélectionné : périwinkle pour un MEMBRE de la sélection,
        # blanc pour l'item ACTIF (celui que l'inspecteur détaille) — même
        # grammaire que la grille du Palette Editor.
        if self.isSelected():
            sc = self.scene()
            is_active = getattr(sc, "active_item", None) is self
            ring = QColor("#ffffff") if is_active else QColor(C.ACCENT)
            painter.save()
            painter.setPen(QPen(ring, 1, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self.boundingRect().adjusted(0, 0, -1, -1)
            painter.drawRect(r)
            # Petits coins pour renforcer la visibilité
            painter.setPen(QPen(ring, 2))
            for cx, cy in [
                (r.left(), r.top()),
                (r.right(), r.top()),
                (r.left(), r.bottom()),
                (r.right(), r.bottom()),
            ]:
                painter.drawPoint(int(cx), int(cy))
            painter.restore()

        # Repère d'origine (point d'ancrage) — toujours visible
        painter.save()
        painter.setPen(QPen(QColor(C.ACCENT_RED), 1, Qt.PenStyle.SolidLine))
        painter.drawLine(-4, 0, 4, 0)
        painter.drawLine(0, -4, 0, 4)
        painter.setPen(QPen(QColor(C.ACCENT_RED), 1))
        painter.setBrush(QColor(C.ACCENT_RED))
        painter.drawEllipse(-2, -2, 4, 4)
        painter.restore()

    def set_snap(self, snap: bool):
        self.snap = snap


# ──────────────────────────────────────────────────────────────────
#  Item caméra — icône draggable + zone de vision
# ──────────────────────────────────────────────────────────────────
_CAM_ICO_SIZE = 20  # px, carré


class _MaskablePixmapItem(QGraphicsPixmapItem):
    """Layer BG dont des régions peuvent être découpées à l'affichage.

    Sert à refléter dans le canvas ce que les windows matérielles font
    réellement à l'écran : une window active dont `layers_shown[bg]` est faux
    empêche ce layer de s'afficher DANS son rectangle (registre WININ). Les
    rects sont donnés en coordonnées de scène — l'item étant posé à l'origine,
    coordonnées d'item et de scène coïncident."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(pixmap, parent)
        self._mask_rects: list[QRectF] = []

    def set_mask_rects(self, rects: list):
        if rects == self._mask_rects:
            return
        self._mask_rects = list(rects)
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        if self._mask_rects:
            path = QPainterPath()
            path.addRect(self.boundingRect())
            for r in self._mask_rects:
                cut = QPainterPath()
                cut.addRect(r)
                path = path.subtracted(cut)
            painter.setClipPath(path)
        super().paint(painter, option, widget)


class CameraItem(QGraphicsItem):
    """
    Icône caméra draggable positionnée en haut-gauche de la zone de vue.
    La zone de vision 240×160 est un enfant non-interactif, visible quand sélectionnée.

    boundingRect() couvre toujours GBA_W×GBA_H : Qt sait ainsi quelle zone
    nettoyer quand l'item se déplace, même quand le rectangle de vision est affiché.
    """

    def __init__(
        self, canvas_w: int, canvas_h: int, cam_x: int = 0, cam_y: int = 0,
        frame_w: int = GBA_W, frame_h: int = GBA_H, camera=None, parent=None,
    ):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        # La caméra (modèle) que cet item représente — `None` = état implicite
        # (scène sans caméra encore créée, cf. Project.ensure_scene_camera).
        # Une scène peut en posséder plusieurs (révisé 2026-08-24) : chaque
        # CameraItem porte donc SA référence, distincte du singleton d'avant.
        self.camera = camera

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(150)
        self.setPos(cam_x, cam_y)
        self.setAcceptHoverEvents(True)
        self._hovered = False

        # Zone de vision — enfant non-interactif. Sa taille EST le frame de la
        # caméra (Camera.frame_w/h, réglé le 2026-08-24) — plus petite que
        # GBA_W×GBA_H quand la caméra pilote WIN0 (cf. set_frame_size).
        self._frame_w = frame_w
        self._frame_h = frame_h
        pen = QPen(QColor("#ffdd44"))
        pen.setWidth(0)
        pen.setCosmetic(True)  # sans ça, seule l'épaisseur du trait ignore le zoom —
                                # le motif de tirets s'étire quand même avec la vue
        pen.setStyle(Qt.PenStyle.DashLine)
        self._view = QGraphicsRectItem(0, 0, frame_w, frame_h, self)
        self._view.setPen(pen)
        self._view.setBrush(QBrush(QColor(255, 221, 68, 12)))
        self._view.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._view.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._view.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._view.setAcceptHoverEvents(False)
        self._view.setVisible(False)

        # Windows (WIN0/WIN1) — enfants de la caméra : une window est en espace
        # ÉCRAN, elle suit donc la vue automatiquement (position locale = position
        # dans l'écran GBA), sans recalcul à chaque déplacement de caméra.
        self._window_items: list[QGraphicsRectItem] = []
        # setToolTip après construction : le tooltip se base sur self.camera,
        # déjà posé plus haut.
        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        name = self.camera.name if self.camera else "(default)"
        return f"GBA Camera — {name} — {self._frame_w}×{self._frame_h} px\nDrag to move the view"

    def set_frame_size(self, w: int, h: int):
        """Redimensionne le rectangle de vue — c'est le frame écran de la
        caméra (`Camera.frame_w/h`), pas juste un aperçu : plus petit que
        240×160, la caméra pilote WIN0 à l'activation (cf. camera_switch())."""
        self._frame_w, self._frame_h = w, h
        self.prepareGeometryChange()
        self._view.setRect(0, 0, w, h)
        self.setToolTip(self._tooltip())

    # ── Windows (aperçu) ──────────────────────────────────────────

    def set_windows(self, windows: list):
        """Dessine l'aperçu des WindowSlot de la scène dans le cadre écran.

        Le rectangle est clampé à 240×160 comme le fait `window_set()` au
        runtime — l'aperçu montre donc la zone RÉELLEMENT obtenue sur console,
        pas la saisie brute (une window plus large que l'écran est tronquée)."""
        for it in self._window_items:
            it.setParentItem(None)
            if it.scene():
                it.scene().removeItem(it)
        self._window_items = []

        for i, ws in enumerate(w for w in (windows or []) if not w.is_obj):
            # Fenêtre-objet : pas de rectangle — sa forme vient des pixels
            # opaques des sprites en obj_mode=2, non prévisualisable ici.
            # Quel rang matériel (WIN0/WIN1) chaque window nommée reçoit est
            # décidé par l'allocateur au build (`window_alloc.py`) — sans
            # incidence sur cet aperçu, qui montre la géométrie AUTHORÉE.
            x0 = max(0, min(int(ws.x), GBA_W))
            y0 = max(0, min(int(ws.y), GBA_H))
            x1 = max(x0, min(int(ws.x) + int(ws.w), GBA_W))
            y1 = max(y0, min(int(ws.y) + int(ws.h), GBA_H))

            color = QColor(_WIN_COLORS[i % len(_WIN_COLORS)])
            pen = QPen(color)
            pen.setWidth(0)
            pen.setCosmetic(True)
            # Trait plein = window active au runtime ; pointillé = authorée mais
            # window_show(…, 0) → invisible sur console.
            pen.setStyle(Qt.PenStyle.SolidLine if ws.visible else Qt.PenStyle.DotLine)

            rect = QGraphicsRectItem(x0, y0, x1 - x0, y1 - y0, self)
            rect.setPen(pen)
            fill = QColor(color)
            fill.setAlpha(40 if ws.visible else 16)
            rect.setBrush(QBrush(fill))
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            rect.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            rect.setAcceptHoverEvents(False)
            rect.setToolTip(
                f"{ws.name or '(unnamed window)'} — {x1 - x0}×{y1 - y0} px at ({x0}, {y0})"
                + ("" if ws.visible else "\n(inactive — window_show at 0)")
            )
            self._window_items.append(rect)

        self._sync_view_visibility()

    # ── QGraphicsItem interface ───────────────────────────────────

    def boundingRect(self) -> QRectF:
        # Grand rect pour que Qt efface correctement lors du déplacement.
        return QRectF(0, 0, GBA_W, GBA_H)

    def shape(self) -> "QPainterPath":
        # Hit-test limité à l'icône seule — les actors en-dessous restent cliquables.
        path = QPainterPath()
        path.addRect(QRectF(0, 0, _CAM_ICO_SIZE, _CAM_ICO_SIZE))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        # Icône UI (pas du pixel art de jeu) : rendue à la résolution écran du
        # zoom courant plutôt qu'agrandie depuis un pixmap de 20 px — sinon elle
        # est floue dès le zoom ×2 (le canvas s'ouvre déjà à ×2). Lissage local,
        # sans affecter le nearest-neighbor des sprites/BG ailleurs sur le canvas.
        from ui.common.icons import scaled_pixmap

        # Sélectionnée / survolée / au repos.
        if self.isSelected():
            color = "#ffdd44"
        elif self._hovered:
            color = "#f5f0d8"
        else:
            color = "#666666"
        px = scaled_pixmap("camera", color, _CAM_ICO_SIZE,
                           _screen_scale(painter, widget))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPixmap(
            QRectF(0, 0, _CAM_ICO_SIZE, _CAM_ICO_SIZE), px, QRectF(px.rect())
        )

    # ── Canvas resize ─────────────────────────────────────────────

    def set_canvas_size(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h

    # ── itemChange ────────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            p: QPointF = value
            x = max(0, min(p.x(), self._canvas_w - GBA_W))
            y = max(0, min(p.y(), self._canvas_h - GBA_H))
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Les windows sont en espace écran : leur découpe des layers BG
            # (espace monde) doit suivre la caméra.
            sc = self.scene()
            if sc is not None and hasattr(sc, "update_window_masks"):
                sc.update_window_masks()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # prepareGeometryChange() notifie Qt que la zone de dessin
            # effective change (icon seul → icon + viewport 240×160).
            self.prepareGeometryChange()
            self._sync_view_visibility()
        return super().itemChange(change, value)

    def _sync_view_visibility(self):
        """Aperçu 240×160 visible seulement sélectionnée ou survolée."""
        self._view.setVisible(self.isSelected() or self._hovered)

    def hoverEnterEvent(self, e):
        self._hovered = True
        self._sync_view_visibility()
        self.update()
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._hovered = False
        self._sync_view_visibility()
        self.update()
        super().hoverLeaveEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Toolbar flottante
# ──────────────────────────────────────────────────────────────────
class FloatingToolbar(QFrame):
    """
    Palette d'outils flottante et déplaçable superposée au canvas.

    Outils :
        select    — Sélection / déplacement d'actors   (S)
        add       — Ajouter un actor au clic           (A)
        erase     — Supprimer un actor au clic         (E)
        collision — Édition de collisions (dropdown)   (C)
        palette   — Éditeur de palette couleurs        (P)

    Le bouton collision ouvre un dropdown avec 3 modes :
        collision_8    — Pinceau  8×8 px
        collision_16   — Pinceau 16×16 px
        collision_slope— Slope (triangle)
    """

    tool_changed = pyqtSignal(str)  # ex. "select", "collision_8", "collision_slope"…

    # Outils principaux — (id, icon_key, tooltip)
    _MAIN_TOOLS = [
        ("select", "tool_select", "Select  (S)"),
        ("add", "tool_add", "Add actor  (A)"),
        ("erase", "tool_erase", "Eraser  (E)"),
    ]

    # Sous-outils collision — (id, icon_key, label, tooltip)
    _COLLISION_MODES = [
        (
            "collision_8",
            "tool_collision_8",
            "8×8 px brush",
            "Collision brush  8×8 px",
        ),
        (
            "collision_16",
            "tool_collision_16",
            "16×16 px brush",
            "Collision brush 16×16 px",
        ),
        (
            "collision_slope",
            "tool_collision_slope",
            "Floor slope",
            "Floor slope (triangle, Bresenham)",
        ),
        (
            "collision_slope_inv",
            "tool_collision_slope_inv",
            "Ceiling slope",
            "Inverted floor slope (triangle, Bresenham)",
        ),
    ]

    # Sous-outils inpainting de scène — (id, icon_key, label, tooltip)
    _INPAINT_MODES = [
        ("inpaint_brush", "tool_inpaint_brush", "Brush",
         "Inpainting: repaint a tile's palette (8×8 brush)"),
        ("inpaint_rect", "tool_inpaint_rect", "Rectangle",
         "Inpainting: repaint the palette over a rectangular area"),
    ]
    _INPAINT_ICON_KEYS = {
        "inpaint_brush": "tool_inpaint_brush",
        "inpaint_rect": "tool_inpaint_rect",
    }

    # Sous-outils UI — (id, icon_key, label, tooltip). Un seul bouton, le type
    # se choisit au dropdown (comme collision/inpaint) ; le geste rectangle est
    # le même pour les trois. Icônes = formes de la famille Interface.
    _UI_MODES = [
        ("ui_text", "ui_text", "Text",
         "Text — authored here, or left empty for a script to write into"),
        ("ui_panel", "ui_panel", "Container",
         "Container / group — anchor root, can draw a background"),
        ("ui_image", "ui_image", "Image",
         "Image — a sprite whose state a script can switch"),
    ]
    _UI_ICON_KEYS = {
        "ui_text": "ui_text",
        "ui_panel": "ui_panel",
        "ui_image": "ui_image",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._dragging = False
        self._drag_offset = QPoint()
        self._current_tool = "select"
        self._current_collision = "collision_8"
        self._current_inpaint = "inpaint_brush"
        self._current_ui = "ui_text"

        self.setFixedWidth(46)
        self.setStyleSheet(f"""
            FloatingToolbar {{
                background: {C.BG_RAISED};
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: 5px;
            }}
            QToolButton:hover   {{ background: {C.BG_HOVER}; }}
            QToolButton:checked {{
                background: {C.BG_SEL};
                border: 1px solid {C.ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(2)

        handle = QLabel("⋮⋮")
        handle.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        handle.setStyleSheet("color:#3a3a3a; font-size:10px; letter-spacing:-2px;")
        handle.setFixedHeight(12)
        layout.addWidget(handle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a2a2a; margin:2px 0;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._btns: dict[str, QToolButton] = {}

        # ── Outils principaux ─────────────────────────────────────
        for tool_id, icon_key, tip in self._MAIN_TOOLS:
            btn = QToolButton()
            btn.setIcon(_ico(icon_key, COLOR_DEFAULT, COLOR_ACTIVE))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setChecked(tool_id == "select")
            btn.setFixedSize(36, 36)
            btn.clicked.connect(lambda _, t=tool_id: self._set_tool(t))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._btns[tool_id] = btn

        # ── Bouton collision avec dropdown ────────────────────────
        self._btn_collision = QToolButton()
        # Icône « mur » partagée avec le toggle « Collisions scène » de la
        # toolbar haute : une seule identité visuelle pour la collision. Le
        # sous-mode actif (8/16/slope) se choisit dans le menu déroulant.
        self._btn_collision.setIcon(_ico("view_collision", COLOR_DEFAULT, COLOR_ACTIVE))
        self._btn_collision.setIconSize(QSize(24, 24))
        self._btn_collision.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_collision.setToolTip("Édition de collisions  (C)")
        self._btn_collision.setCheckable(True)
        self._btn_collision.setFixedSize(36, 36)
        self._btn_collision.clicked.connect(self._on_collision_click)
        layout.addWidget(self._btn_collision, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["collision"] = self._btn_collision

        # ── Bouton peinture palette BG avec dropdown ──────────────
        self._btn_inpaint = QToolButton()
        self._btn_inpaint.setIcon(
            _ico(self._INPAINT_ICON_KEYS[self._current_inpaint],
                 COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._btn_inpaint.setIconSize(QSize(24, 24))
        self._btn_inpaint.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_inpaint.setToolTip("Scene inpainting  (B)")
        self._btn_inpaint.setCheckable(True)
        self._btn_inpaint.setFixedSize(36, 36)
        self._btn_inpaint.clicked.connect(self._on_inpaint_click)
        layout.addWidget(self._btn_inpaint, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["inpaint_btn"] = self._btn_inpaint

        # ── Séparateur + outil palette ────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#2a2a2a; margin:3px 0;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Widgets d'interface. Un bouton, trois types au dropdown (zone,
        # conteneur, texte) — l'icône du bouton reflète le type courant, T
        # reprend le dernier utilisé, comme collision (C) et inpainting (B).
        self._btn_ui = QToolButton()
        self._btn_ui.setIcon(
            _ico(self._UI_ICON_KEYS[self._current_ui], COLOR_DEFAULT, COLOR_ACTIVE))
        self._btn_ui.setIconSize(QSize(20, 20))
        self._btn_ui.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_ui.setToolTip("Widget d'interface  (T)")
        self._btn_ui.setCheckable(True)
        self._btn_ui.setFixedSize(34, 34)
        self._btn_ui.clicked.connect(self._on_ui_click)
        layout.addWidget(self._btn_ui, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["ui_btn"] = self._btn_ui

        layout.addStretch()
        self.adjustSize()

    # ── Collision dropdown ────────────────────────────────────────

    def _on_collision_click(self):
        self._show_collision_menu()

    def _show_collision_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{
                background: {C.BG_RAISED};
                color: {C.TEXT_NORM};
                border: 1px solid {C.BORDER_MID};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{ padding: 5px 14px 5px 8px; border-radius: 3px; icon-size: 20px; }}
            QMenu::item:selected {{ background: {C.BG_SEL}; color: {C.ACCENT}; }}
            QMenu::item:checked  {{ color: {C.ACCENT}; }}
        """)

        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, label, tip in self._COLLISION_MODES:
            act = QAction(label, self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(self._current_collision == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_collision_mode(m))
            menu.addAction(act)

        # Positionner le menu à droite du bouton
        btn_pos = self._btn_collision.mapToGlobal(
            QPoint(self._btn_collision.width() + 4, 0)
        )
        menu.exec(btn_pos)

    def _select_collision_mode(self, mode: str):
        # Le bouton garde l'icône « mur » (identité collision partagée) ; le
        # sous-mode choisi est indiqué par la coche du menu déroulant.
        self._current_collision = mode
        self._set_tool(mode)

    # ── Peinture palette BG dropdown ──────────────────────────────

    def _on_inpaint_click(self):
        self._show_inpaint_menu()

    def _show_inpaint_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.BORDER_MID};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, label, tip in self._INPAINT_MODES:
            act = QAction(label, self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(self._current_inpaint == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_inpaint_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_inpaint.mapToGlobal(
            QPoint(self._btn_inpaint.width() + 4, 0)
        )
        menu.exec(btn_pos)

    def _select_inpaint_mode(self, mode: str):
        self._current_inpaint = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_inpaint.setIcon(
            _ico(self._INPAINT_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    # ── Widgets d'interface dropdown ──────────────────────────────

    def _on_ui_click(self):
        self._show_ui_menu()

    def _show_ui_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(f"""
            QMenu {{ background:{C.BG_RAISED}; color:{C.TEXT_NORM}; border:1px solid {C.BORDER_MID};
                    border-radius:4px; padding:4px; }}
            QMenu::item {{ padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }}
            QMenu::item:selected {{ background:{C.BG_SEL}; color:{C.ACCENT}; }}
            QMenu::item:checked  {{ color:{C.ACCENT}; }}
        """)
        from ui.common.icons import COLOR_UI
        from ui.common.icons import get as _ico

        for mode_id, icon_key, label, tip in self._UI_MODES:
            act = QAction(label, self)
            act.setIcon(_ico(icon_key, COLOR_UI))
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(self._current_ui == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_ui_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_ui.mapToGlobal(QPoint(self._btn_ui.width() + 4, 0))
        menu.exec(btn_pos)

    def _select_ui_mode(self, mode: str):
        self._current_ui = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_ui.setIcon(
            _ico(self._UI_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    # ── Outil actif ───────────────────────────────────────────────

    def _set_tool(self, tool: str):
        self._current_tool = tool
        # Mettre à jour le visuel de tous les boutons
        for tid, btn in self._btns.items():
            is_active = (
                tid == tool
                or (tid == "collision" and tool.startswith("collision"))
                or (tid == "inpaint_btn" and tool.startswith("inpaint"))
                or (tid == "ui_btn" and tool.startswith("ui_"))
            )
            btn.setChecked(is_active)
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._current_tool

    def activate_shortcut(self, group: str):
        """Active un outil depuis un raccourci clavier. Pour 'collision' /
        'inpaint', reprend le dernier sous-mode utilisé (comme un clic ré-active
        le mode courant). Passe par _set_tool → boutons + signal synchronisés."""
        if group == "collision":
            self._set_tool(self._current_collision)
        elif group == "inpaint":
            self._set_tool(self._current_inpaint)
        elif group == "ui":
            self._set_tool(self._current_ui)
        else:
            self._set_tool(group)

    # ── Drag ──────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and self.parent():
            new_pos = self.mapToParent(e.pos()) - self._drag_offset
            p = self.parent()
            x = max(0, min(new_pos.x(), p.width() - self.width()))
            y = max(0, min(new_pos.y(), p.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Bezel d'écran — cadre de l'espace authorable : trait périwinkle + lueur,
#  pour marquer l'écran sans se lire comme une erreur. AA activée localement
#  (la vue la désactive globalement pour le pixel art), sinon les coins
#  arrondis crénèlent.
# ──────────────────────────────────────────────────────────────────
class ScreenBezelItem(QGraphicsItem):
    _RADIUS = 5.0
    _COLOR = QColor(C.ACCENT)

    def __init__(self, w: int, h: int, parent=None):
        super().__init__(parent)
        self._w = w
        self._h = h
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w = w
        self._h = h

    def boundingRect(self) -> QRectF:
        m = 5.0   # marge pour le trait + halo peint (sinon Qt rogne au bord)
        return QRectF(-m, -m, self._w + 2 * m, self._h + 2 * m)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0, 0, self._w, self._h)
        # Halo peint à la main : QGraphicsDropShadowEffect plante sous le
        # backend offscreen (crash natif en capture headless, 0xC0000409).
        for i, alpha in ((3, 18), (2, 34), (1, 55)):
            glow_pen = QPen(self._COLOR)
            glow_pen.setWidthF(1.4 + i * 1.3)
            glow_pen.setCosmetic(True)
            c = QColor(self._COLOR)
            c.setAlpha(alpha)
            glow_pen.setColor(c)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r, self._RADIUS, self._RADIUS)
        pen = QPen(self._COLOR)
        pen.setWidthF(1.4)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r, self._RADIUS, self._RADIUS)


# ──────────────────────────────────────────────────────────────────
#  Grille 8px — item unique (évite N QGraphicsLineItem)
# ──────────────────────────────────────────────────────────────────
class GridItem(QGraphicsItem):
    def __init__(self, w: int, h: int, cell: int = 8, parent=None):
        super().__init__(parent)
        self._w = w
        self._h = h
        self._cell = cell
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def resize(self, w: int, h: int):
        self.prepareGeometryChange()
        self._w = w
        self._h = h

    def set_cell(self, cell: int):
        self._cell = cell
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        # Grille fine 8px
        pen8 = QPen(QColor(255, 255, 255, 22))
        pen8.setWidth(0)
        # Grille large 16px (toujours visible au-dessus de la fine)
        pen16 = QPen(QColor(255, 255, 255, 55))
        pen16.setWidth(0)
        for x in range(0, self._w + 1, self._cell):
            painter.setPen(pen8 if self._cell == 8 and x % 16 != 0 else pen16)
            painter.drawLine(x, 0, x, self._h)
        for y in range(0, self._h + 1, self._cell):
            painter.setPen(pen8 if self._cell == 8 and y % 16 != 0 else pen16)
            painter.drawLine(0, y, self._w, y)


# ──────────────────────────────────────────────────────────────────
#  Overlay boîtes de collision acteurs
# ──────────────────────────────────────────────────────────────────


class ActorBoxOverlay(QGraphicsItem):
    """
    Dessine les CollisionBoxComponent des acteurs passés via set_actors().
    Solid → rouge,  trigger → vert.
    z=160 (au-dessus des sprites, sous la caméra).
    """

    _C_SOLID = QColor(255, 70, 70, 100)
    _C_TRIGGER = QColor(70, 220, 120, 100)
    _B_SOLID = QColor(255, 90, 90, 240)
    _B_TRIGGER = QColor(90, 240, 140, 240)

    def __init__(self, canvas_w: int, canvas_h: int, parent=None):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._actors: list = []
        self._var_defaults: dict = {}   # (src, name) -> valeur par défaut (aperçu des refs)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(160)
        self.setVisible(False)

    def set_actors(self, actors: list, var_defaults: dict | None = None):
        self._actors = list(actors)
        if var_defaults is not None:
            self._var_defaults = var_defaults
        self.setVisible(bool(self._actors))
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._canvas_w, self._canvas_h)

    def paint(self, painter: QPainter, option, widget=None):
        from core.models.components import CollisionBoxComponent
        from core.models.field_value import FieldValue

        # Un champ peut être une référence de variable : on résout à la valeur
        # par défaut de la variable pour dessiner une box représentative.
        resolve = lambda src, name: self._var_defaults.get((src, name))

        pen_s = QPen(self._B_SOLID, 0)
        pen_t = QPen(self._B_TRIGGER, 0)
        for actor in self._actors:
            for comp in actor.components:
                if not isinstance(comp, CollisionBoxComponent) or not comp.active:
                    continue
                x = FieldValue.parse(actor.x).px(resolve) + FieldValue.parse(comp.x).px(resolve)
                y = FieldValue.parse(actor.y).px(resolve) + FieldValue.parse(comp.y).px(resolve)
                w = FieldValue.parse(comp.w).px(resolve)
                h = FieldValue.parse(comp.h).px(resolve)
                if comp.solid:
                    painter.fillRect(x, y, w, h, self._C_SOLID)
                    painter.setPen(pen_s)
                else:
                    painter.fillRect(x, y, w, h, self._C_TRIGGER)
                    painter.setPen(pen_t)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, w, h)


# ──────────────────────────────────────────────────────────────────
#  Scène GBA
# ──────────────────────────────────────────────────────────────────
class _GuideLine(QGraphicsLineItem):
    """Guide d'alignement, élargi de la marge de repeinte que Qt ne calcule pas.

    Trait cosmétique (largeur 0) : Qt efface une zone de largeur nulle, donc le
    guide laisse une traînée en se déplaçant. Même piège que
    `UIRegionItem.boundingRect`."""

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-6.0, -6.0, 6.0, 6.0)


class GBAScene(QGraphicsScene):
    sprite_moved = pyqtSignal()

    def __init__(self, canvas_w: int = GBA_W, canvas_h: int = GBA_H, parent=None):
        super().__init__(0, 0, canvas_w, canvas_h, parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._bg_items: list[Optional[QGraphicsPixmapItem]] = [None] * 4
        self._sprite_items: list[SpriteItem] = []
        self._grid_item: Optional[GridItem] = None
        self._border: Optional[ScreenBezelItem] = None
        self._backdrop: Optional[QGraphicsRectItem] = None
        self._camera: Optional[CameraItem] = None   # caméra DE DÉMARRAGE (screen-space, windows)
        self._extra_cameras: list[CameraItem] = []  # les AUTRES caméras de la scène
        self._windows: list = []   # WindowSlot de la scène (aperçu + masquage BG)
        self._obj_mask_rects: list = []   # découpe OBJ courante (sprites)
        self._ui_region_items: list = []  # zones de texte (UILayout de la scène)
        self._ui_elements_visible = True  # toggle "Interface elements" (top bar)
        # Guides d'alignement : deux lignes (une verticale, une horizontale)
        # créées à la demande, affichées le temps d'un drag/resize de zone.
        self._align_guide_v: Optional[QGraphicsLineItem] = None
        self._align_guide_h: Optional[QGraphicsLineItem] = None
        # Item ACTIF de la sélection : celui dont l'inspecteur montre le
        # contenu. Une multi-sélection en a toujours exactement un (le premier
        # sélectionné), redéfinissable au Ctrl+Shift+clic.
        self._active_item = None
        self._snap = False
        self._collision_view = False  # toggle "Collisions scène"
        self._setup_border()
        self._collision_overlay = CollisionOverlay()
        self.addItem(self._collision_overlay)
        self._actor_box_overlay = ActorBoxOverlay(canvas_w, canvas_h)
        self.addItem(self._actor_box_overlay)
        # Rafraîchit les boîtes de collision pendant un drag (sinon l'ancienne
        # position reste peinte — "traînée" visuelle tant que set_actors()
        # n'est pas rappelé explicitement).
        self.sprite_moved.connect(self._actor_box_overlay.update)

    @property
    def collision_overlay(self) -> "CollisionOverlay":
        return self._collision_overlay

    def descendant_sprite_items(self, item: "SpriteItem") -> list:
        """SpriteItem des acteurs qui descendent de `item.scene_sprite`
        (`Actor.parent`, ROADMAP v0.23) — pour faire suivre tout le
        sous-arbre quand on déplace un parent dans le canvas."""
        from core.models.scene import actor_descendant_names
        names = actor_descendant_names(
            [it.scene_sprite for it in self._sprite_items], item.scene_sprite.name)
        return [it for it in self._sprite_items
                if it is not item and it.scene_sprite.name in names]

    # ── Sélection multiple : membres + item ACTIF ─────────────────
    # Un item sélectionné est « membre » ; parmi eux, un seul est ACTIF —
    # c'est lui que l'inspecteur détaille et lui que les gestes visant « un »
    # item prennent pour cible. Les deux états se peignent différemment
    # (accent = membre, blanc = actif), même grammaire que la grille du
    # Palette Editor.

    def selectable_items(self) -> list:
        """Items sélectionnés éligibles à la multi-sélection : acteurs et zones
        de texte (la caméra est un singleton, elle n'en fait pas partie)."""
        try:
            selected = self.selectedItems()
        except RuntimeError:      # scène Qt détruite en cours de rebuild
            return []
        return [it for it in selected if isinstance(it, (SpriteItem, UIRegionItem))]

    @property
    def active_item(self):
        return self._active_item

    def set_active_item(self, item) -> bool:
        """Désigne l'item actif. Retourne True s'il a changé (l'appelant peut
        alors prévenir le bus). Repeint l'ancien et le nouveau."""
        if item is self._active_item:
            return False
        old, self._active_item = self._active_item, item
        for it in (old, item):
            if it is None:
                continue
            try:
                if it.scene() is self:
                    it.update()
            except RuntimeError:
                pass              # item C++ déjà détruit
        return True

    def reconcile_active(self):
        """Garde l'item actif cohérent avec la sélection : il doit toujours en
        être membre. Sinon → le PREMIER membre (règle « le premier item
        sélectionné est l'actif »), ou aucun si la sélection est vide."""
        members = self.selectable_items()
        if self._active_item in members:
            return False
        return self.set_active_item(members[0] if members else None)

    # ── Guides d'alignement des zones de texte ────────────────────
    def ui_align_segments(self, exclude_item):
        """Segments-cibles (start, size) des AUTRES zones, par axe, en
        coordonnées scène — lus tels qu'ils sont dessinés (offset d'actor
        compris). Retourne (xs, ys) où chaque élément est un (start, size)."""
        xs, ys = [], []
        for it in self._ui_region_items:
            if it is exclude_item:
                continue
            try:
                r, p = it.rect(), it.pos()
            except RuntimeError:
                continue
            xs.append((p.x() + r.left(), r.width()))
            ys.append((p.y() + r.top(),  r.height()))
        return xs, ys

    def _guide_pen(self) -> "QPen":
        """Guide d'alignement : semi-transparent et en tirets, pour se lire
        comme un repère et non comme une alarme."""
        c = QColor("#ff45d0")
        c.setAlpha(150)
        pen = QPen(c)
        pen.setCosmetic(True)           # 1 px écran quel que soit le zoom
        pen.setWidth(0)
        pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def show_align_guides(self, gx, gy):
        """Trace une ligne verticale à x=`gx` et/ou horizontale à y=`gy` (None =
        masquée). Les lignes courent sur toute l'étendue de la scène : un guide
        qui s'arrêterait au bord de la zone n'aiderait pas à viser une cible
        lointaine."""
        w, h = self._canvas_w, self._canvas_h
        if gx is not None:
            if self._align_guide_v is None:
                self._align_guide_v = _GuideLine()
                self._align_guide_v.setPen(self._guide_pen())
                self._align_guide_v.setZValue(130)   # au-dessus des zones (120)
                self._align_guide_v.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.addItem(self._align_guide_v)
            self._align_guide_v.setLine(gx, 0, gx, h)
            self._align_guide_v.setVisible(True)
        elif self._align_guide_v:
            self._align_guide_v.setVisible(False)
        if gy is not None:
            if self._align_guide_h is None:
                self._align_guide_h = _GuideLine()
                self._align_guide_h.setPen(self._guide_pen())
                self._align_guide_h.setZValue(130)
                self._align_guide_h.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.addItem(self._align_guide_h)
            self._align_guide_h.setLine(0, gy, w, gy)
            self._align_guide_h.setVisible(True)
        elif self._align_guide_h:
            self._align_guide_h.setVisible(False)

    def clear_align_guides(self):
        for g in (self._align_guide_v, self._align_guide_h):
            if g:
                g.setVisible(False)

    def update_actor_boxes(self, actors: list, var_defaults: dict | None = None):
        """Met à jour les boîtes de collision acteurs affichées."""
        self._actor_box_overlay.set_actors(actors, var_defaults)

    def set_collision_view(self, visible: bool):
        """Toggle 'Collisions scène' — indépendant de l'outil CollisionTool."""
        self._collision_view = visible
        self._collision_overlay.setVisible(visible)
        self._collision_overlay.update()

    def set_ui_elements_view(self, visible: bool):
        """Toggle 'Interface elements' — zones/conteneurs/textes de la mise en
        page. Mémorisé pour s'appliquer aussi aux items recréés par un futur
        set_ui_regions (rebuild sur chaque édition de la mise en page)."""
        self._ui_elements_visible = visible
        for it in self._ui_region_items:
            it.setVisible(visible)

    def resize_canvas(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h
        self.setSceneRect(0, 0, w, h)
        if self._border:
            self._border.resize(w, h)
        if self._backdrop:
            self._backdrop.setRect(0, 0, w, h)
        if self._camera:
            self._camera.set_canvas_size(w, h)
        for it in self._extra_cameras:
            it.set_canvas_size(w, h)
        for item in self._sprite_items:
            item.set_canvas_size(w, h)
        if self._grid_item:
            self._grid_item.resize(w, h)

    def set_backdrop(self, bgr555: int):
        """Couleur du backdrop (index 0 de PAL_BG_RAM) — peinte SOUS tous les
        layers (z=-1). C'est ce que le hardware affiche là où rien n'est dessiné :
        une window qui masque tout laisse donc apparaître cette couleur, et le
        canvas le reflète."""
        from core.gba_color import bgr555_to_rgb888
        r, g, b = bgr555_to_rgb888(int(bgr555) & 0x7FFF)
        if self._backdrop is None:
            self._backdrop = QGraphicsRectItem(0, 0, self._canvas_w, self._canvas_h)
            self._backdrop.setPen(QPen(Qt.PenStyle.NoPen))
            self._backdrop.setZValue(-1)
            self._backdrop.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self._backdrop.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            self._backdrop.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.addItem(self._backdrop)
        self._backdrop.setRect(0, 0, self._canvas_w, self._canvas_h)
        self._backdrop.setBrush(QBrush(QColor(r, g, b)))

    def _setup_border(self):
        self._border = ScreenBezelItem(self._canvas_w, self._canvas_h)
        self._border.setZValue(200)
        self.addItem(self._border)

    # ── Caméra ────────────────────────────────────────────────────

    def setup_camera(self, cam_x: int = 0, cam_y: int = 0, camera=None):
        """(Re)crée l'item de la caméra DE DÉMARRAGE — celle qui porte les
        sprites en espace écran et l'aperçu des windows. `camera` est l'objet
        modèle qu'elle représente (`None` = état implicite)."""
        if self._camera:
            # Détacher d'abord les sprites d'écran : retirer la caméra de la
            # scène emporterait ses enfants avec elle.
            for it in self._sprite_items:
                if it.parentItem() is self._camera:
                    it.setParentItem(None)
                    if it.scene() is None:
                        self.addItem(it)
            self.removeItem(self._camera)
        fw = camera.frame_w if camera else GBA_W
        fh = camera.frame_h if camera else GBA_H
        self._camera = CameraItem(self._canvas_w, self._canvas_h, cam_x, cam_y,
                                  frame_w=fw, frame_h=fh, camera=camera)
        self.addItem(self._camera)
        for it in self._sprite_items:
            self.sync_sprite_space(it)

    def setup_extra_cameras(self, cameras: list):
        """(Re)crée les items des AUTRES caméras de la scène — rectangles
        déplaçables/sélectionnables comme la caméra de démarrage, mais sans
        rôle dans le rendu écran (pas de sprites, pas de windows) : la scène
        n'a qu'UN écran, une seule caméra pilote son espace à la fois."""
        for it in self._extra_cameras:
            self.removeItem(it)
        self._extra_cameras = []
        for cam in cameras:
            it = CameraItem(self._canvas_w, self._canvas_h, cam.x, cam.y,
                            frame_w=cam.frame_w, frame_h=cam.frame_h, camera=cam)
            self.addItem(it)
            self._extra_cameras.append(it)

    def camera_pos(self) -> tuple[int, int]:
        if self._camera:
            p = self._camera.pos()
            return int(p.x()), int(p.y())
        return 0, 0

    def camera_items(self) -> list:
        """Tous les items caméra de la scène (démarrage + autres)."""
        return ([self._camera] if self._camera else []) + list(self._extra_cameras)

    def set_windows(self, windows: list):
        """Aperçu des WindowSlot dans le cadre écran (porté par la caméra)."""
        self._windows = list(windows or [])
        if self._camera:
            self._camera.set_windows(self._windows)
        self.update_window_masks()

    def update_window_masks(self):
        """Applique aux layers BG le découpage des windows ACTIVES.

        Seule une window `visible` compte : une window authorée mais laissée à
        `window_show(region, 0)` n'a aucun effet sur console, elle ne doit donc
        rien masquer ici non plus. Recalculé au déplacement de la caméra, les
        rects étant en espace écran."""
        cam = self._camera.pos() if self._camera else QPointF(0, 0)

        def _screen_rect(ws) -> Optional[QRectF]:
            """Rect de la window en coordonnées de scène, clampé à l'écran."""
            x0 = max(0, min(int(ws.x), GBA_W))
            y0 = max(0, min(int(ws.y), GBA_H))
            x1 = max(x0, min(int(ws.x) + int(ws.w), GBA_W))
            y1 = max(y0, min(int(ws.y) + int(ws.h), GBA_H))
            if x1 <= x0 or y1 <= y0:
                return None
            return QRectF(cam.x() + x0, cam.y() + y0, x1 - x0, y1 - y0)

        # Windows actives et rectangulaires (la fenêtre-objet n'a pas de rect).
        active = [ws for ws in self._windows if ws.visible and not ws.is_obj]

        # Layers BG — bit par layer (WININ bits 0-3).
        for bg_index, item in enumerate(self._bg_items):
            if not isinstance(item, _MaskablePixmapItem):
                continue
            rects = []
            for ws in active:
                shown = getattr(ws, "layers_shown", [True] * 4)
                if bg_index < len(shown) and shown[bg_index]:
                    continue   # ce layer traverse la window : rien à découper
                r = _screen_rect(ws)
                if r is not None:
                    rects.append(r)
            item.set_mask_rects(rects)

        # Sprites — bit OBJ commun à tous (WININ bit 4), pas par acteur.
        obj_rects = []
        for ws in active:
            if getattr(ws, "obj_shown", True):
                continue   # les sprites traversent cette window
            r = _screen_rect(ws)
            if r is not None:
                obj_rects.append(r)
        self._obj_mask_rects = obj_rects
        for sp in self._sprite_items:
            sp.set_mask_rects(obj_rects)

    # ── BG layers ─────────────────────────────────────────────────

    def set_bg(self, bg_index: int, pixmap: Optional[QPixmap]):
        # Priorité GBA = bg_slot directement (cf. `_hw_layer_z`) : un fond
        # n'est jamais OBJ, donc toujours le cran BG de sa priorité.
        z = _hw_layer_z(bg_index, is_obj=False)
        if self._bg_items[bg_index]:
            self.removeItem(self._bg_items[bg_index])
            self._bg_items[bg_index] = None
        if pixmap:
            item = _MaskablePixmapItem(pixmap)
            item.setZValue(z)
            # OPACITÉ PLEINE, toujours. Les layers derrière BG0 étaient dessinés
            # à 90 % — une commodité d'édition (voir les couches empilées) qui
            # n'existe pas sur la console : le backdrop, et tout ce qui est
            # derrière, transparaissaient donc EN PERMANENCE à travers un décor
            # que la ROM affiche plein. Un fond uni un peu vif teintait tout
            # l'écran, et l'aperçu ne pouvait plus servir à juger une couleur.
            #
            # Pour regarder dessous, l'œil de la ligne de layer masque
            # franchement ce qu'on veut, sans mentir sur le reste du temps.
            item.setOpacity(1.0)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.addItem(item)
            self._bg_items[bg_index] = item

    def set_bg_visible(self, bg_index: int, visible: bool):
        """Masque/affiche un layer BG dans le canvas SANS détruire son pixmap
        (visibilité viewport éditeur seule — cf. BackgroundLayer.visible)."""
        if 0 <= bg_index < len(self._bg_items) and self._bg_items[bg_index]:
            self._bg_items[bg_index].setVisible(visible)

    # ── Sprites ───────────────────────────────────────────────────

    def add_sprite(
        self, pixmap: QPixmap, actor: Actor, save_fn=None,
        origin_x: int = 0, origin_y: int = 0,
        scale_x: float = 1.0, scale_y: float = 1.0,
        rotation: float = 0.0,
        flip_h: bool = False, flip_v: bool = False,
        resolver=None, placeholder: bool = False,
    ) -> SpriteItem:
        item = SpriteItem(
            pixmap, actor,
            self._canvas_w, self._canvas_h,
            snap=self._snap, save_fn=save_fn,
            origin_x=origin_x, origin_y=origin_y,
            scale_x=scale_x, scale_y=scale_y,
            rotation=rotation, flip_h=flip_h, flip_v=flip_v,
            resolver=resolver, placeholder=placeholder,
        )
        self.addItem(item)
        self._sprite_items.append(item)
        self.sync_sprite_space(item)
        # Sprite créé après le calcul des masques (rechargement de scène) :
        # lui appliquer la découpe courante sans attendre le prochain recalcul.
        if self._obj_mask_rects:
            item.set_mask_rects(self._obj_mask_rects)
        return item

    def sync_sprite_space(self, item: SpriteItem):
        """Range l'item dans le bon repère selon `Actor.screen_space`.

        Un acteur ancré à l'écran devient ENFANT de la caméra — exactement ce
        que font déjà les windows (cf. CameraItem.set_windows) : sa position
        locale EST sa position dans l'écran GBA, elle suit la vue sans le
        moindre recalcul, et un déplacement à la souris rend directement des
        coordonnées d'écran à écrire dans le modèle (`itemChange` lit une
        position relative au parent).

        Idempotent : appelé à la création, au changement de caméra et à chaque
        modification de l'inspecteur, sans avoir à savoir ce qui a changé."""
        want = self._camera if getattr(item.scene_sprite, "screen_space", False) else None
        if item.parentItem() is not want:
            item.setParentItem(want)
            if want is None and item.scene() is None:
                # Détaché d'un parent qui n'était plus dans la scène : Qt l'a
                # sorti avec lui, il faut le remettre pour qu'il reste dessinable.
                self.addItem(item)
        # Toujours repositionner : c'est aussi le chemin d'un simple déplacement
        # (spinbox de l'inspecteur), où le repère n'a pas bougé.
        item.sync_pos()

    def clear_sprites(self):
        for item in self._sprite_items:
            self.removeItem(item)
        self._sprite_items.clear()

    # ── Zones de texte ────────────────────────────────────────────

    def set_ui_regions(self, layout_asset, project, scene, save_fn=None):
        """Redessine les zones de la mise en page référencée par la scène.

        Reconstruction complète plutôt que mise à jour en place : une zone peut
        avoir changé d'ancrage (donc d'origine), de taille ou de cible, et
        recalculer chaque cas séparément multiplierait les chemins pour un
        nombre d'items qui se compte sur les doigts.

        La reconstruction ne doit PAS coûter la sélection : détruire l'item
        sélectionné fait émettre à Qt une sélection vide, que le canvas traduit
        en « clic dans le vide » → l'inspecteur de la zone se refermait à chaque
        frappe dans une spinbox. On note la zone sélectionnée, on tait les
        signaux le temps du remplacement, et on la re-sélectionne sur son
        nouvel item."""
        # Identité, pas égalité : deux zones peuvent avoir les mêmes champs.
        kept = [it._region for it in self._ui_region_items if it.isSelected()]
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            for it in self._ui_region_items:
                if it.scene():
                    self.removeItem(it)
            self._ui_region_items = []
            if layout_asset is None:
                return
            # TOUS les éléments (zones, conteneurs, textes), pas seulement les
            # zones : chacun a une géométrie à dessiner et à manipuler.
            #
            # Le z-order suit l'ORDRE D'ARBRE (DFS) : un parent sous ses enfants
            # (le texte au-dessus du fond de son conteneur), un frère tardif
            # au-dessus du précédent. On le pose explicitement — sans ça tous les
            # items partageraient un z constant et l'empilement dépendrait du seul
            # ordre d'insertion, invisible à réordonner.
            z_of = {r.name: i for i, (_d, r) in enumerate(layout_asset.in_tree_order())}
            for r in layout_asset.elements:
                item = UIRegionItem(layout_asset, r, project, scene, save_fn=save_fn)
                # La base (`_hw_layer_z`, posée au constructeur) place la zone
                # sur son VRAI layer hardware ; l'offset ici ne fait plus que
                # départager les zones d'un MÊME layer entre elles — trop petit
                # pour jamais déborder sur le cran suivant (pas 2.0 d'écart).
                item.setZValue(item.zValue() + z_of.get(r.name, 0) / 1000.0)
                item.setVisible(self._ui_elements_visible)
                self.addItem(item)
                self._ui_region_items.append(item)
                if any(r is k for k in kept):
                    item.setSelected(True)
        finally:
            self.blockSignals(was_blocked)

    def set_snap(self, snap: bool):
        self._snap = snap
        for item in self._sprite_items:
            item.set_snap(snap)

    # ── Grille ────────────────────────────────────────────────────

    def set_grid(self, visible: bool, cell: int = 8):
        if self._grid_item is None:
            self._grid_item = GridItem(self._canvas_w, self._canvas_h, cell)
            self._grid_item.setZValue(100)
            self.addItem(self._grid_item)
        else:
            self._grid_item.set_cell(cell)
        self._grid_item.setVisible(visible)

    # ── Fond damier ───────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor("#1a1a1a"))
        size = 8
        c1, c2 = QColor("#222222"), QColor("#2a2a2a")
        x0 = int(rect.left() / size) * size
        y0 = int(rect.top() / size) * size
        x1 = int(rect.right() / size + 1) * size
        y1 = int(rect.bottom() / size + 1) * size
        for x in range(x0, x1, size):
            for y in range(y0, y1, size):
                c = c1 if (x // size + y // size) % 2 == 0 else c2
                painter.fillRect(x, y, size, size, c)


# ──────────────────────────────────────────────────────────────────
#  Vue zoomable
# ──────────────────────────────────────────────────────────────────
class GBAView(QGraphicsView):
    prefab_template_dropped = pyqtSignal(str, QPointF)
    # Émis après CHAQUE clic gauche traité par Qt (RubberBandDrag), qu'il ait
    # ou non changé la sélection — Qt.selectionChanged ne se déclenche QUE si
    # l'ensemble sélectionné change réellement : un clic répété en dehors du
    # canvas alors que la sélection est déjà vide, ou un 2e clic dans la zone
    # active alors qu'une actor était déjà désélectionné, ne le ferait jamais
    # fire, et l'inspecteur resterait figé sur son panneau précédent. Ce signal
    # force une réévaluation à chaque clic, indépendamment de tout changement.
    left_click_settled = pyqtSignal()

    def __init__(self, scene: GBAScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(C.BG_DEEP))
        # Focus clavier : nécessaire pour que les raccourcis du canvas (contexte
        # WidgetWithChildren de SceneEditor) se déclenchent quand la vue est active.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._zoom = 2.0
        self._apply_zoom()
        self.setAcceptDrops(True)
        # Outil actif — initialisé après import (évite la circularité)
        self._active_tool: "BaseTool | None" = None
        # Snap preview — 16×16, visible uniquement si snap actif
        self._snap_on = False
        self._snap_preview: "QGraphicsRectItem | None" = None
        # Contrôleur de peinture par palette BG (injecté par SceneEditor).
        self.inpainting_controller: "Optional[SceneInpaintingController]" = None
        self.ui_region_controller: "Optional[UIRegionController]" = None
        # Pan au clic-central — agit sur les scrollbars, donc indépendant de
        # l'outil actif et du zoom. `_pan_last` = dernière position viewport (px).
        self._panning = False
        self._pan_last: "Optional[QPointF]" = None
        self._pan_prev_cursor = None
        # Un Shift+clic (multi-sélection) est traité ici sans passer à Qt : le
        # relâchement correspondant doit l'être aussi, d'où ce drapeau.
        self._swallow_left_release = False
        # Position (coords scène) du dernier clic gauche non consommé par l'outil
        # actif — lu par SceneEditor._on_selection_changed pour distinguer un clic
        # dans la zone active du canvas (→ re-sélectionne la scène) d'un clic en
        # dehors (→ désélectionne tout). Valide uniquement PENDANT l'appel à
        # super().mousePressEvent() ci-dessous (remis à None juste après) : ça
        # évite qu'une valeur périmée soit relue par un _on_selection_changed
        # déclenché plus tard pour une tout autre raison (Échap, clic droit…).
        self._last_click_scene_pos: "Optional[QPointF]" = None
        # Alt+glisser = dupliquer : instantané des items glissés, pris au press
        # (cf. _arm_alt_duplicate). None = geste ordinaire.
        self._alt_drag: "Optional[list]" = None

    def leaveEvent(self, e):
        if self._snap_preview:
            self._snap_preview.setVisible(False)
        if self._active_tool:
            self._active_tool.on_leave()
        super().leaveEvent(e)

    def dragLeaveEvent(self, e):
        e.accept()  # supprime le warning Qt "drag leave before drag enter"

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_PREFAB_TEMPLATE):
            name = bytes(e.mimeData().data(MIME_PREFAB_TEMPLATE)).decode("utf-8")
            pos = self.mapToScene(e.position().toPoint())
            self.prefab_template_dropped.emit(name, pos)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def _apply_zoom(self):
        t = QTransform()
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.5, min(self._zoom * factor, 8.0))
        self._apply_zoom()

    def fit(self, w: int = GBA_W, h: int = GBA_H):
        self.fitInView(0, 0, w, h, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def zoom_to(self, level: float):
        self._zoom = max(0.5, min(level, 8.0))
        self._apply_zoom()

    # ── Outil actif ───────────────────────────────────────────────

    collision_painted = pyqtSignal()
    # Clic-droit sur un actor en mode Sélection → (SpriteItem, QPoint global).
    actor_context_requested = pyqtSignal(object, object)
    # Alt+glisser relâché → (dx, dy) du geste, en px de scène. Les originaux
    # ont déjà été remis en place ; il reste à créer les copies à ce décalage.
    duplicate_drag_finished = pyqtSignal(int, int)

    @property
    def collision_overlay(self) -> Optional["CollisionOverlay"]:
        s = self.scene()
        return s.collision_overlay if isinstance(s, GBAScene) else None

    def set_tool(self, tool: "BaseTool") -> None:
        if self._active_tool is not None:
            self._active_tool.deactivate()
        self._active_tool = tool
        tool.activate()

    def set_snap(self, enabled: bool) -> None:
        self._snap_on = enabled
        if not enabled and self._snap_preview:
            self._snap_preview.setVisible(False)

    def _ensure_snap_preview(self):
        if self._snap_preview is None:
            item = QGraphicsRectItem(0, 0, 16, 16)
            item.setBrush(QBrush(QColor(100, 255, 120, 55)))
            item.setPen(QPen(QColor(100, 255, 120, 210), 0))
            item.setZValue(49)  # sous le preview AddActorTool (z=50)
            item.setVisible(False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene().addItem(item)
            self._snap_preview = item

    # ── Délégation souris → outil actif ──────────────────────────

    def mousePressEvent(self, e):
        _btn = e.button()
        if _btn == Qt.MouseButton.MiddleButton:
            self._start_pan(e.position())
            e.accept()
            return
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_press(pos, e):
                e.accept()
                return
        # En mode Sélection, le bouton droit ne sert QU'AU menu contextuel : on
        # ne le passe pas à QGraphicsView, qui viderait la sélection dès que le
        # clic tombe à côté d'un actor — or c'est justement cette sélection que
        # le menu doit pouvoir viser (cf. contextMenuEvent).
        if _btn == Qt.MouseButton.RightButton and self._is_select_tool():
            e.accept()
            return
        # Multi-sélection au clavier+souris (mode Sélection) : Shift = ajouter /
        # retirer un item, Ctrl+Shift = redéfinir l'item ACTIF. Traité ICI et pas
        # par Qt, dont le modificateur natif de multi-sélection est Ctrl et qui
        # ne connaît pas la notion d'item actif.
        if (_btn == Qt.MouseButton.LeftButton and self._is_select_tool()
                and (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self._multi_select_press(self.mapToScene(e.position().toPoint()),
                                     e.modifiers())
            # Le relâchement qui suit doit être avalé lui aussi : un press que Qt
            # n'a pas vu suivi d'un release qu'il voit laisse sa machinerie de
            # grab de souris dans un état incohérent (les clics suivants
            # repartent alors vers le dernier item saisi, où qu'on clique).
            self._swallow_left_release = True
            e.accept()
            return
        if _btn == Qt.MouseButton.LeftButton:
            self._last_click_scene_pos = self.mapToScene(e.position().toPoint())
        super().mousePressEvent(e)
        if _btn == Qt.MouseButton.LeftButton:
            # APRÈS Qt : c'est lui qui vient d'arrêter la sélection que le geste
            # va déplacer (un clic sur un item hors sélection la remplace).
            if (self._is_select_tool()
                    and (e.modifiers() & Qt.KeyboardModifier.AltModifier)):
                self._arm_alt_duplicate(self._last_click_scene_pos)
            self.left_click_settled.emit()
        self._last_click_scene_pos = None

    def mouseMoveEvent(self, e):
        # Pan au clic-central : translate la vue via les scrollbars, avant toute
        # autre logique (snap preview, délégation outil).
        if self._panning and (e.buttons() & Qt.MouseButton.MiddleButton):
            delta = e.position() - self._pan_last
            self._pan_last = e.position()
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - round(delta.x()))
            vbar.setValue(vbar.value() - round(delta.y()))
            e.accept()
            return
        pos = self.mapToScene(e.position().toPoint())
        # Snap preview — indépendant de l'outil actif
        if self._snap_on:
            self._ensure_snap_preview()
            sx = int(pos.x() // 16) * 16
            sy = int(pos.y() // 16) * 16
            self._snap_preview.setPos(sx, sy)
            self._snap_preview.setVisible(True)
        # Délégation à l'outil (hover + drag)
        if self._active_tool:
            if self._active_tool.on_move(pos, e):
                e.accept()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        _btn = e.button()
        # Repris ici quoi qu'il arrive : un geste avorté (pan, outil qui prend
        # la main) ne doit pas laisser un instantané périmé armer le prochain.
        alt_drag, self._alt_drag = self._alt_drag, None
        if _btn == Qt.MouseButton.MiddleButton and self._panning:
            self._end_pan()
            e.accept()
            return
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_release(pos, e):
                e.accept()
                return
        if _btn == Qt.MouseButton.RightButton and self._is_select_tool():
            e.accept()              # symétrique du press : le droit est au menu
            return
        if _btn == Qt.MouseButton.LeftButton and self._swallow_left_release:
            self._swallow_left_release = False   # pendant du Shift+clic ci-dessus
            e.accept()
            return
        if alt_drag is not None and _btn == Qt.MouseButton.LeftButton:
            # Neutraliser AVANT que Qt ne distribue le relâchement aux items :
            # c'est là qu'ils poussent leur commande de déplacement. En
            # Alt+glisser l'original ne bouge pas — seule la copie naît.
            for it, _origin, _model in alt_drag:
                if isinstance(it, SpriteItem):
                    it._drag_origin = None
                else:
                    it._press_pos = None
            super().mouseReleaseEvent(e)
            self._commit_alt_duplicate(alt_drag)
            return
        super().mouseReleaseEvent(e)

    # ── Alt+glisser = dupliquer ───────────────────────────────────

    # En deçà (px scène) c'est un clic Alt, pas un glisser : sinon un
    # frémissement de souris crée une copie invisible sous l'original.
    # Même seuil que SpriteItem._CLICK_THRESHOLD.
    _ALT_DRAG_THRESHOLD = 2

    def _arm_alt_duplicate(self, scene_pos):
        """Mémorise les items que le glisser va emporter, pour les remettre en
        place au relâchement et ne garder que la copie.

        Position Qt (le geste s'y mesure) ET position MODÈLE d'un acteur : le
        drag réécrit `actor.x/y` à chaque frame et perdrait l'expression
        d'origine (« 4t », une réf de variable)."""
        sc = self.scene()
        if scene_pos is None or not hasattr(sc, "selectable_items"):
            return
        if self._selectable_item_at(scene_pos) is None:
            return          # Alt dans le vide : rubber band, rien à dupliquer
        entries = []
        for it in sc.selectable_items():
            actor = getattr(it, "scene_sprite", None)
            model = (actor.x, actor.y) if actor is not None else None
            entries.append((it, QPointF(it.pos()), model))
        self._alt_drag = entries or None

    def _commit_alt_duplicate(self, entries: list):
        """Remet les originaux en place et annonce le décalage du geste — la
        duplication elle-même appartient au SceneEditor, qui traite acteurs et
        éléments d'interface d'un même mouvement."""
        dx = dy = 0
        for it, origin, model in entries:
            try:
                cur = it.pos()
            except RuntimeError:
                continue                      # item C++ détruit entre-temps
            if not dx and not dy:
                dx = int(round(cur.x() - origin.x()))
                dy = int(round(cur.y() - origin.y()))
            if model is not None:
                it.scene_sprite.x, it.scene_sprite.y = model
                it.sync_pos()
            else:
                # Un conteneur a emmené ses descendants à l'écran (leur modèle
                # est relatif au parent, il n'a pas bougé) : même delta retour.
                if hasattr(it, "_move_descendants"):
                    it._move_descendants(origin.x() - cur.x(), origin.y() - cur.y())
                it.setPos(origin)
        if abs(dx) < self._ALT_DRAG_THRESHOLD and abs(dy) < self._ALT_DRAG_THRESHOLD:
            return
        self.duplicate_drag_finished.emit(dx, dy)

    # ── Pan clic-central ──────────────────────────────────────────

    def _start_pan(self, viewport_pos: "QPointF"):
        self._panning = True
        self._pan_last = viewport_pos
        self._pan_prev_cursor = self.cursor()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan(self):
        self._panning = False
        self._pan_last = None
        if self._pan_prev_cursor is not None:
            self.setCursor(self._pan_prev_cursor)
            self._pan_prev_cursor = None

    def _actor_item_at(self, scene_pos) -> "Optional[SpriteItem]":
        """Premier SpriteItem sous la position (scène) donnée, sinon None."""
        for it in self.scene().items(scene_pos):
            if isinstance(it, SpriteItem):
                return it
        return None

    def _is_select_tool(self) -> bool:
        # Import local : canvas_tools importe ce module (cycle à l'import).
        from ui.scene_manager.canvas_tools import SelectTool
        return isinstance(self._active_tool, SelectTool)

    def _selectable_item_at(self, scene_pos):
        """Premier item éligible à la multi-sélection sous la position :
        acteur ou zone de texte."""
        for it in self.scene().items(scene_pos):
            if isinstance(it, (SpriteItem, UIRegionItem)):
                return it
        return None

    def _multi_select_press(self, scene_pos, modifiers):
        """Shift+clic = bascule l'appartenance à la sélection ; Ctrl+Shift+clic =
        désigne l'item ACTIF (et l'ajoute s'il n'était pas encore membre).

        L'item actif n'est PAS déplacé par un simple Shift+clic : on ajoute des
        items autour de lui sans perdre ce que montre l'inspecteur. C'est le
        Ctrl+Shift qui sert à changer de point de vue."""
        sc = self.scene()
        item = self._selectable_item_at(scene_pos)
        if item is None:
            return                       # Shift dans le vide : ne rien casser
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if not item.isSelected():
                item.setSelected(True)
            sc.set_active_item(item)
        else:
            item.setSelected(not item.isSelected())
            if item.isSelected() and sc.active_item is None:
                sc.set_active_item(item)   # 1er membre = actif
            sc.reconcile_active()          # actif retiré → premier membre restant
        # Même signal que tout clic gauche : il porte déjà « la sélection a
        # peut-être bougé, resynchronise » — indispensable pour le Ctrl+Shift,
        # qui ne change pas l'appartenance donc n'émet pas selectionChanged.
        self.left_click_settled.emit()

    def contextMenuEvent(self, e):
        """En mode Sélection : clic-droit → menu contextuel (Renommer /
        Dupliquer / Supprimer).

        La cible est, dans l'ordre : l'actor sous le curseur, sinon la SÉLECTION
        COURANTE — dès qu'un actor est sélectionné, le clic-droit ouvre donc son
        menu même à côté de lui, sans avoir à viser le sprite. Deux règles de
        sélection : un actor cliqué HORS sélection la remplace (le menu agit sur
        ce qu'on montre), un actor cliqué DANS une multi-sélection la préserve
        (sinon un clic-droit réduirait silencieusement la sélection à un seul).
        Pour les autres outils, le clic-droit sert à peindre ou à l'outil — pas
        de menu OS."""
        if self._is_select_tool():
            item = self._actor_item_at(self.mapToScene(e.pos()))
            if item is not None:
                if not item.isSelected():
                    self.scene().clearSelection()
                    item.setSelected(True)
            else:
                item = next((it for it in self.scene().selectedItems()
                             if isinstance(it, SpriteItem)), None)
            if item is not None:
                self.actor_context_requested.emit(item, e.globalPos())
            e.accept()
            return
        if self._active_tool:
            e.accept()
            return
        super().contextMenuEvent(e)


# ──────────────────────────────────────────────────────────────────
#  Overlay de collision (z=300)
# ──────────────────────────────────────────────────────────────────
_T = COLLISION_TILE_SIZE  # 8

_C_SOLID = QColor(255, 60, 60, 130)
_C_STEEP = QColor(255, 160, 30, 150)
_C_GENTLE = QColor(255, 200, 80, 150)
_B_SOLID = QColor(255, 80, 80, 220)
_B_STEEP = QColor(255, 180, 50, 230)
_B_GENTLE = QColor(255, 210, 100, 230)
# Plafond — teinte bleue/violette pour distinguer visuellement
_C_STEEP_INV = QColor(80, 140, 255, 150)
_C_GENTLE_INV = QColor(120, 180, 255, 150)
_B_STEEP_INV = QColor(100, 160, 255, 230)
_B_GENTLE_INV = QColor(140, 200, 255, 230)

_FLOOR_SLOPES = (
    TILE_SLOPE_L,
    TILE_SLOPE_R,
    TILE_SLOPE_R_STEEP_HI,
    TILE_SLOPE_R_STEEP_LO,
    TILE_SLOPE_L_STEEP_HI,
    TILE_SLOPE_L_STEEP_LO,
)
_FLOOR_GENTLE = (TILE_SLOPE_L_LO, TILE_SLOPE_L_HI, TILE_SLOPE_R_LO, TILE_SLOPE_R_HI)
_CEIL_SLOPES = (
    TILE_SLOPE_L_INV,
    TILE_SLOPE_R_INV,
    TILE_SLOPE_R_STEEP_HI_INV,
    TILE_SLOPE_R_STEEP_LO_INV,
    TILE_SLOPE_L_STEEP_HI_INV,
    TILE_SLOPE_L_STEEP_LO_INV,
)
_CEIL_GENTLE = (
    TILE_SLOPE_L_LO_INV,
    TILE_SLOPE_L_HI_INV,
    TILE_SLOPE_R_LO_INV,
    TILE_SLOPE_R_HI_INV,
)


def _slope_path(x: int, y: int, tile_type: int) -> QPainterPath:
    """Le contour de la matière d'une tuile de collision, posé en (x, y).

    Dérivé de `collision_tiles.polygon()` : la forme est décrite UNE fois, là où
    le codegen la lit aussi pour émettre la table du runtime. La physique du jeu
    et ce dessin ne peuvent donc plus diverger."""
    p = QPainterPath()
    poly = CT.polygon(tile_type)
    if not poly:
        return p
    p.moveTo(x + poly[0][0], y + poly[0][1])
    for px, py in poly[1:]:
        p.lineTo(x + px, y + py)
    p.closeSubpath()
    return p


class CollisionOverlay(QGraphicsItem):
    """
    Affiche la collision_map d'une scène par-dessus le canvas.
    Visible uniquement quand l'outil collision est actif.
    Ne reçoit pas les événements souris (géré par GBAView).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._map: list[list[int]] = []
        self._rows = 0
        self._cols = 0
        self._preview: Optional[list[tuple[int, int, int]]] = None
        self._cache: Optional[QPixmap] = None  # cache rendu hors-écran (map seule)
        self.setZValue(300)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

    # ── Données ───────────────────────────────────────────────────

    def load(self, collision_map: list[list[int]]):
        self.prepareGeometryChange()
        self._map = collision_map
        self._rows = len(collision_map)
        self._cols = len(collision_map[0]) if self._rows else 0
        self._cache = None
        self.update()

    def get_map(self) -> list[list[int]]:
        return self._map

    def set_tile(self, col: int, row: int, tile_type: int):
        if 0 <= row < self._rows and 0 <= col < self._cols:
            self._map[row][col] = tile_type
            self._cache = None
            self.update()

    def tile_at(self, col: int, row: int) -> int:
        if 0 <= row < self._rows and 0 <= col < self._cols:
            return self._map[row][col]
        return TILE_EMPTY

    def set_preview(self, tiles: Optional[list[tuple[int, int, int]]]):
        """Mise à jour légère : le cache de base reste valide, on redessine juste le preview."""
        self._preview = tiles
        self.update()

    def scene_to_tile(self, scene_x: float, scene_y: float) -> tuple[int, int]:
        return int(scene_x // _T), int(scene_y // _T)

    # ── Dessin ────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, max(1, self._cols) * _T, max(1, self._rows) * _T)

    def paint(self, painter: QPainter, option, widget=None):
        # Reconstruire le cache si invalidé
        w = max(1, self._cols) * _T
        h = max(1, self._rows) * _T
        if self._cache is None or self._cache.width() != w or self._cache.height() != h:
            self._cache = QPixmap(w, h)
            self._cache.fill(Qt.GlobalColor.transparent)
            cp = QPainter(self._cache)
            cp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for row in range(self._rows):
                for col in range(self._cols):
                    self._draw_tile(cp, col, row, self._map[row][col], alpha_mul=1.0)
            cp.end()

        # Le cache est construit lissé à sa résolution native ; sans ce hint,
        # le blit vers l'écran repasse en nearest-neighbor dès que la vue est
        # zoomée et le crénelage réapparaît.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self._cache)

        # Preview slope au-dessus du cache (pas mis en cache — éphémère)
        if self._preview:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for col, row, t in self._preview:
                self._draw_tile(painter, col, row, t, alpha_mul=0.5)
            painter.restore()

    def _draw_tile(
        self, painter: QPainter, col: int, row: int, t: int, alpha_mul: float
    ):
        if t == TILE_EMPTY:
            return
        x, y = col * _T, row * _T

        def _colored(base_fill, base_bord):
            f = QColor(base_fill)
            f.setAlpha(int(base_fill.alpha() * alpha_mul))
            b = QColor(base_bord)
            b.setAlpha(int(base_bord.alpha() * alpha_mul))
            return f, b

        if t == TILE_SOLID:
            fill, bord = _colored(_C_SOLID, _B_SOLID)
            painter.fillRect(x, y, _T, _T, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawRect(x, y, _T - 1, _T - 1)
        elif t in _FLOOR_SLOPES:
            fill, bord = _colored(_C_STEEP, _B_STEEP)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _FLOOR_GENTLE:
            fill, bord = _colored(_C_GENTLE, _B_GENTLE)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _CEIL_SLOPES:
            fill, bord = _colored(_C_STEEP_INV, _B_STEEP_INV)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)
        elif t in _CEIL_GENTLE:
            fill, bord = _colored(_C_GENTLE_INV, _B_GENTLE_INV)
            path = _slope_path(x, y, t)
            painter.fillPath(path, fill)
            painter.setPen(QPen(bord, 0))
            painter.drawPath(path)


def _layer_png_path(project: Project, layer):
    """Chemin du PNG source d'un layer (via son BackgroundAsset sidecar)."""
    ba = project.get_background(layer.background_name)
    png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
    return project.background_images_dir / png


# ──────────────────────────────────────────────────────────────────
#  Contrôleur de peinture par palette BG (SE_PALBANK par tuile)
# ──────────────────────────────────────────────────────────────────
# Poignées de redimensionnement — chaque nom porte les bords qu'il déplace
# (left, top, right, bottom). Les coins bougent deux bords, les milieux un seul.
_HANDLE_EDGES = {
    "nw": (True,  True,  False, False),
    "n":  (False, True,  False, False),
    "ne": (False, True,  True,  False),
    "e":  (False, False, True,  False),
    "se": (False, False, True,  True),
    "s":  (False, False, False, True),
    "sw": (True,  False, False, True),
    "w":  (True,  False, False, False),
}
_HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n":  Qt.CursorShape.SizeVerCursor,   "s":  Qt.CursorShape.SizeVerCursor,
    "e":  Qt.CursorShape.SizeHorCursor,   "w":  Qt.CursorShape.SizeHorCursor,
}
# Demi-côté du carré de poignée dessiné, et tolérance de préhension, en pixels
# ÉCRAN : convertis en unités scène via le zoom courant pour rester constants à
# l'affichage quel que soit le niveau de zoom.
_HANDLE_HALF_PX = 3.5
_HANDLE_GRAB_PX = 6.0

# Planches de glyphes trouées : {(chemin, mtime, taille): QPixmap | None}.
# Au niveau du module, pas de l'item — les items sont reconstruits à chaque
# sauvegarde et retrouer une planche (numpy) à ce rythme se sentirait.
_TEXT_SHEETS: dict = {}


class UIRegionItem(QGraphicsRectItem):
    """Une zone de texte dessinée dans le canvas — sélectionnable, déplaçable,
    redimensionnable par ses poignées.

    Le rectangle est en coordonnées LOCALES (0,0,w,h) et la position porte x/y :
    sans ça, déplacer l'item ne changerait pas `pos()` et il n'y aurait rien à
    relire au relâchement.

    Déplacement ET redimensionnement sont validés au RELÂCHEMENT, pas à chaque
    pixel : pousser une commande d'historique par événement de souris remplirait
    la pile de cent entrées pour un seul geste. Même raison que pour le drag d'un
    actor. Le geste vit en flottant dans le canvas ; le snap à la tuile (cible
    BG) et l'arrondi de taille ne tombent qu'à la fin, exactement comme le move.

    Une zone ancrée sur un actor est dessinée à l'offset près de son acteur si
    on le trouve — sinon à l'origine de l'écran, avec un liseré discontinu qui
    dit que la position affichée n'est pas celle du jeu."""

    # Exception canvas-only à la règle « forme, pas teinte » (icons.py) :
    # pendant un drag, la couleur se lit plus vite qu'une icône de 6 px.
    # Ailleurs (arbre, finders) le type reste porté par la FORME.
    _KIND_COLORS = {
        "text":   "#4f8ff7",   # texte (bleu, famille Interface)
        "panel":  "#b388ff",   # conteneur (lavande — structure/groupe)
        "image":  "#ffb454",   # image (ambre — un dessin, pas une structure)
    }
    _KIND_ICONS = {"panel": "ui_panel", "text": "ui_text", "image": "ui_image"}

    def __init__(self, layout_asset, region, project, scene, save_fn=None, parent=None):
        super().__init__(0, 0, max(8, region.w), max(8, region.h), parent)
        self._layout, self._region = layout_asset, region
        self._project, self._scene = project, scene
        self._save = save_fn
        self._press_pos = None
        from ui.common import icons as _icons
        self._COLOR = QColor(self._KIND_COLORS.get(getattr(region, "kind", "region"),
                                                    _icons.COLOR_UI))
        # Poignée en cours de traction (None = déplacement/simple sélection) et
        # géométrie de départ du geste, figée au press pour que chaque mouvement
        # se calcule depuis l'origine et non depuis l'image précédente.
        self._resize_handle: "str | None" = None
        self._resize_start: "tuple | None" = None
        # Vrai le temps d'un déplacement à la souris — le seul cas où l'on veut
        # aimanter la position et tracer des guides. Sans ce drapeau, les setPos
        # internes (rebuild, snap au relâchement, commit d'un resize) passeraient
        # aussi dans le chemin d'aimantation d'`itemChange`.
        self._moving = False
        # Dernière position vue pendant le geste — sert à calculer le delta à
        # rejouer sur les DESCENDANTS (leur x/y modèle est relatif au parent :
        # rien à réécrire chez eux, mais l'écran doit les faire suivre).
        self._last_pos = None
        self.setAcceptHoverEvents(True)

        ox, oy, anchored = self._origin()
        self.setPos(ox, oy)

        # Tout le dessin passe par `paint` : l'item lui-même ne porte ni trait ni
        # remplissage. Sans ça `super().paint()` reposerait le style de repos
        # par-dessus l'état (survol, sélection) que `paint` vient de calculer.
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._anchored = anchored
        self._hovered = False
        # CONTENU (ce que la GBA affichera : couleur de palette, hachures d'un
        # asset pas encore rendu) — à distinguer du CHROME d'édition (voile,
        # contour, poignées), qui lui dépend de l'état.
        self._content_brush = self._fill_brush()
        # Nine-slice / background : si l'image source charge, elle est peinte
        # dans `paint` et REMPLACE le pinceau ; sinon on garde les hachures.
        self._ns_pixmap = None
        self._ns = None
        self._bg_pixmap = None
        # Image : la frame RÉELLE du sprite, peinte comme le sera la ROM. Un
        # rectangle nommé ne dirait pas si l'icône est la bonne ni si elle
        # déborde du conteneur — or c'est exactement pour ça qu'on la pose dans
        # un canvas plutôt que dans un formulaire.
        self._img_pixmap = None
        # Fond sprite d'un conteneur : la MÊME frame que `_img_pixmap`, mais
        # répétée sur le rectangle (cf. `_paint_sprite_fill`). Le drapeau tient
        # la différence, la source du dessin étant identique.
        self._tile_fill = False
        from core.models.ui_region import FILL_NINE, FILL_BG, FILL_SPRITE
        _fk = getattr(region, "fill_kind", "")
        if getattr(region, "kind", "") == "panel":
            if _fk == FILL_NINE:
                pix, ns = self._load_nine_slice()
                if pix is not None and not pix.isNull():
                    self._ns_pixmap, self._ns = pix, ns
                    self._content_brush = None
            elif _fk == FILL_BG:
                pix = self._load_bg_fill()
                if pix is not None and not pix.isNull():
                    self._bg_pixmap = pix
                    self._content_brush = None
            elif _fk == FILL_SPRITE:
                # `_load_image_frame` lit `sprite_name`/`state_index`, que
                # `UIPanel` expose comme `UIImage` — rien à dupliquer.
                pix = self._load_image_frame()
                if pix is not None and not pix.isNull():
                    self._img_pixmap = pix
                    self._tile_fill = True
                    self._content_brush = None
        elif getattr(region, "kind", "") == "image":
            pix = self._load_image_frame()
            if pix is not None and not pix.isNull():
                self._img_pixmap = pix
                self._content_brush = None
        rm = int(getattr(scene, "render_mode", 0) or 0)
        is_obj_target = self._layout.resolved_target(region, rm) == "obj"
        target = "sprite (OBJ)" if is_obj_target else "fond (BG)"
        # Même échelle que les fonds et les acteurs (`_hw_layer_z`) : une zone
        # OBJ (image, panneau à fond sprite) porte SA priorité (`.priority`,
        # 0-3, absente = 0 = devant) ; une zone BG vit sur le layer d'UI de la
        # scène (`text_bg`), à SA priorité — jamais un zValue fixe qui la
        # placerait toujours devant les acteurs, contrairement à la ROM.
        # `set_ui_regions` affine ensuite l'ordre ENTRE zones du même layer.
        if is_obj_target:
            base_z = _hw_layer_z(getattr(region, "priority", 0), is_obj=True)
        else:
            text_bg = getattr(scene, "text_bg", -1)
            base_z = _hw_layer_z(text_bg if text_bg in (0, 1, 2, 3) else 0, is_obj=False)
        self.setZValue(base_z)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        # L'empreinte en tuiles n'a de sens que pour une zone de texte ; un
        # conteneur ou un texte authoré n'expose pas `tile_rect`.
        tiles = ""
        if hasattr(region, "tile_rect"):
            _, _, tw, th = region.tile_rect()
            tiles = f"{tw}×{th} tiles · "
        self.setToolTip(f"“{region.name}” — {self._layout.name}\n"
                        f"{tiles}target {target}\n"
                        f"Drag to move · handles to resize · Alt-drag to duplicate")

        # Étiquette : icône de type + le nom que cite le script, lisibles sans
        # passer par l'inspecteur.
        icon = _icons.get(self._KIND_ICONS.get(getattr(region, "kind", "text"),
                                               "ui_text"), self._COLOR.name())
        self._kind_icon = QGraphicsPixmapItem(icon.pixmap(32, 32), self)
        self._kind_icon.setScale(6.0 / 32.0)      # ≈ 6 px GBA, net à tout zoom
        self._label = QGraphicsSimpleTextItem(region.name, self)
        self._label.setBrush(QBrush(self._COLOR))
        fnt = self._label.font()
        fnt.setPointSizeF(5.0)
        self._label.setFont(fnt)
        self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self._sync_chrome()

    def _actor_pos(self, name: str):
        """(x, y) de l'acteur nommé, ou None. Passé aux helpers d'ancrage du
        modèle qui, eux, ne connaissent pas la scène."""
        for a in getattr(self._scene, "actors", []):
            if a.name == name:
                return (a.x, a.y)
        return None

    def _origin(self) -> tuple[int, int, bool]:
        """Position ÉCRAN de l'origine + « l'ancre du root est-elle résolue ? ».
        Délègue au modèle : la position d'un élément se lit en remontant à son
        root (offsets cumulés + socle du frame), plus seulement de son ancrage
        propre — un enfant est pixel-relatif à son parent."""
        return self._layout.absolute_origin(self._region, self._actor_pos)

    def _fill_brush(self):
        """Pinceau d'aperçu du fond d'un conteneur, ou None (autre type / sans
        fond). Une couleur = une entrée de PALETTE, résolue en RGB PLEIN pour
        l'écran — exactement la teinte que le hardware affichera, jamais une
        teinte d'édition translucide qui mentirait sur le rendu compilé ; un
        fond d'asset (nine-slice / background) est hachuré en attendant son
        vrai rendu."""
        el = self._region
        if getattr(el, "kind", "") != "panel":
            return None
        from core.models.ui_region import FILL_NONE, FILL_COLOR
        fk = getattr(el, "fill_kind", FILL_NONE)
        if fk == FILL_NONE:
            return None
        if fk == FILL_COLOR and self._project is not None:
            bank = self._project.get_palette(getattr(el, "fill_palette", ""))
            idx = int(getattr(el, "fill_index", 0) or 0)
            if bank and 0 <= idx < len(bank.colors):
                from core.gba_color import bgr555_to_rgb888
                r, g, b = bgr555_to_rgb888(bank.colors[idx])
                return QBrush(QColor(r, g, b))
        # Fond d'asset (ou couleur non résolue) : hachures dans la couleur du type.
        return QBrush(QColor(self._COLOR), Qt.BrushStyle.BDiagPattern)

    def _load_nine_slice(self):
        """(QPixmap, BackgroundAsset) du cadre référencé, ou (None, bg/None).

        Le cadre EST un fond d'interface (`kind == "ui"`) : il porte son image
        et ses marges de découpe, il n'y a rien à déréférencer entre les deux."""
        get_bg = getattr(self._project, "get_background", None)
        if not get_bg:
            return None, None
        bg = get_bg(getattr(self._region, "fill_asset", ""))
        if bg is None or not getattr(bg, "asset", ""):
            return None, bg
        path = self._project.background_images_dir / bg.asset
        return QPixmap(str(path)), bg

    def _load_image_frame(self):
        """QPixmap de la 1re frame de l'état déclaré par un `UIImage`, ou None.

        La PREMIÈRE frame et pas une animation vivante : le canvas est un plan,
        pas un aperçu de jeu. Faire tourner les images ferait bouger le décor
        sous la souris pendant qu'on le compose — et masquerait le seul défaut
        qu'on cherche ici, un cadrage faux.

        Même chaîne que les acteurs (`compose_frame_image`), pour que ce que
        montre le canvas soit ce que le build assemblera : une seconde façon de
        composer une frame divergerait au premier flip."""
        el = self._region
        name = getattr(el, "sprite_name", "") or ""
        if not (self._project and name):
            return None
        sprite = self._project.get_sprite(name)
        if sprite is None or not getattr(sprite, "asset", ""):
            return None
        states = list(getattr(sprite, "states", []) or [])
        if not states:
            return None
        st = states[el.state_index(sprite)]
        # Direction 0 (omni) si elle existe, sinon la première déclarée — la
        # même règle de repli que la boucle d'animation du runtime.
        dirs = list(getattr(st, "directions", []) or [])
        if not dirs:
            return None
        d = next((x for x in dirs if getattr(x, "dir", 0) == 0), dirs[0])
        frames = list(getattr(d, "frames", []) or [])
        if not frames:
            return None
        ap = self._project.asset_abs(sprite.asset)
        if ap is None or not ap.exists():
            return None
        try:
            img = compose_frame_image(ap, frames[0], sprite.frame_w, sprite.frame_h)
            if img.width <= 0 or img.height <= 0:
                return None
            data = bytes(img.tobytes("raw", "RGBA"))
            qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            return QPixmap.fromImage(qi)
        except Exception:
            return None      # un asset illisible se dessine en hachures, pas en trace

    def _load_bg_fill(self):
        """QPixmap du background référencé par un fond `background`, ou None."""
        get_bg = getattr(self._project, "get_background", None)
        if not get_bg:
            return None
        bg = get_bg(getattr(self._region, "fill_asset", ""))
        if bg is None or not getattr(bg, "asset", ""):
            return None
        return QPixmap(str(self._project.background_images_dir / bg.asset))

    def _paint_background(self, painter):
        """Peint le background à taille NATURELLE, calé en haut-gauche, ROGNÉ en
        bas/à droite si la zone est plus petite que l'image (pas d'étirement —
        c'est une fenêtre sur le fond)."""
        if self._bg_pixmap is None:
            return
        pix = self._bg_pixmap
        r = self.rect()
        w = min(int(r.width()), pix.width())
        h = min(int(r.height()), pix.height())
        if w <= 0 or h <= 0:
            return
        painter.save()
        painter.drawPixmap(QRectF(r.left(), r.top(), w, h), pix, QRectF(0, 0, w, h))
        painter.restore()

    def _paint_image(self, painter):
        """Peint la frame du sprite, à taille NATURELLE et jamais étirée.

        Le rectangle vaut déjà la frame (`UIImage.sync_size_from`), donc les
        deux coïncident dans le cas normal ; dessiner à taille naturelle plutôt
        qu'au rectangle est ce qui rend VISIBLE le cas anormal — un sprite
        échangé hors de l'éditeur, dont la frame a changé de taille."""
        if self._img_pixmap is None:
            return
        pix, r = self._img_pixmap, self.rect()
        painter.save()
        if self._tile_fill:
            # Fond de conteneur : la frame se RÉPÈTE, exactement comme le
            # runtime pose un OBJ par case (cf. `sprite_grid`). La dernière
            # colonne/rangée déborde plutôt que d'être rognée — le matériel ne
            # sait pas couper un sprite, et l'aperçu doit le montrer plutôt que
            # de laisser croire à un cadrage propre.
            fw, fh = max(1, pix.width()), max(1, pix.height())
            cols = max(1, -(-int(r.width()) // fw))
            rows = max(1, -(-int(r.height()) // fh))
            for cy in range(rows):
                for cx in range(cols):
                    painter.drawPixmap(
                        QRectF(r.left() + cx * fw, r.top() + cy * fh, fw, fh),
                        pix, QRectF(0, 0, fw, fh))
        else:
            painter.drawPixmap(QRectF(r.left(), r.top(), pix.width(), pix.height()),
                               pix, QRectF(0, 0, pix.width(), pix.height()))
        painter.restore()

    def _paint_nine_slice(self, painter):
        """Peint le cadre : chaque case via `nine_slice_rects` — coins 1:1,
        bords/centre TUILÉS pour remplir sans déformer."""
        if self._ns_pixmap is None or self._ns is None:
            return
        from core.nine_slice import nine_slice_rects
        pix, ns = self._ns_pixmap, self._ns
        r = self.rect()
        left, right, top, bottom = ns.slice_margins()
        cells = nine_slice_rects(pix.width(), pix.height(),
                                 left, right, top, bottom,
                                 int(r.width()), int(r.height()))
        painter.save()
        for c in cells:
            sx, sy, sw, sh = c["src"]
            dx, dy, dw, dh = c["dst"]
            dst = QRectF(r.left() + dx, r.top() + dy, dw, dh)
            if c["tile"]:
                painter.drawTiledPixmap(dst, pix.copy(sx, sy, sw, sh))
            else:
                painter.drawPixmap(dst, pix, QRectF(sx, sy, sw, sh))
        painter.restore()

    # ── Texte réel ───────────────────────────────────────────────
    # Aperçu des vrais glyphes dans la boîte : `text_layout` les place comme le
    # moteur, `display_text` résout balises et `$valeurs`.

    def _text_content(self) -> str:
        """Ce que cet élément AFFICHE, balisage résolu.

        Un texte authoré montre SON contenu (celui que la ROM écrira) ; une zone
        montre son `preview_text`, simple étalon d'éditeur — le script décidera.
        Les deux passent par `display_text`, sinon l'aperçu montrerait les
        crochets d'un `[speed=6]` que le joueur ne verra jamais."""
        el, p = self._region, self._project
        if p is None:
            return ""
        kind = getattr(el, "kind", "region")
        key = (getattr(el, "text_key", "") if kind == "text"
               else getattr(el, "preview_text", "")) or ""
        get_text = getattr(p, "get_text", None)
        t = get_text(key) if (key and get_text) else None
        if t is None:
            return ""
        from core.text_markup import display_text
        values = p.text_values() if hasattr(p, "text_values") else {}
        return display_text(t.content or "", values)

    def _text_font(self):
        """Police de l'élément, ou celle que la SCÈNE charge par défaut.

        Le défaut passe par `font_emit.scene_default_font` — le même calcul que
        l'émission, la réservation VRAM et le validateur. Mesurer l'aperçu avec
        une autre police que celle du build ferait mentir le débordement montré
        au canvas, qui est tout l'intérêt du `preview_text`."""
        p = self._project
        named = getattr(self._region, "font_name", "") or ""
        fonts = list(getattr(p, "fonts", []) or []) if p else []
        if named:
            return next((f for f in fonts if f.name == named), None)
        try:
            from codegen.font_emit import scene_default_font
            name = scene_default_font(p, self._scene)[1]
            return next((f for f in fonts if f.name == name), None)
        except Exception:
            # Stub de test, ou chaîne codegen indisponible.
            return fonts[0] if fonts else None

    def _composited(self) -> bool:
        """Le texte se COMPOSE-t-il (pixel) plutôt que de se poser à la tuile ?

        Délègue à `main_gen.region_is_composited` — même règle que le
        validateur (`_check_ui_text_surf_alias`) : les laisser diverger
        risquerait qu'un aperçu dise « pas de conflit » sur un cas que le
        build compose bel et bien. Seul l'offset de ferrage change ici, mais
        7 px de décalage sur un titre centré se voient."""
        from codegen.runtime_codegen.main_gen import region_is_composited
        try:
            from codegen.font_emit import scene_default_font
            default_name = scene_default_font(self._project, self._scene)[1]
        except Exception:
            default_name = ""
        return region_is_composited(self._project, self._layout, self._region, default_name)

    def _highlight_color(self):
        """QColor du surlignement de cette zone, ou None. La couleur est un
        index dans la banque d'UI de la scène — la même que l'encre, le matériel
        n'offrant qu'une banque par tuile. Sans banque désignée
        (`ui_pal_bank` < 0), la police impose la sienne et le canvas n'a rien à
        résoudre : il ne montre alors aucune couleur plutôt qu'une fausse."""
        idx = int(getattr(self._region, "highlight_color", 0) or 0)
        if not idx or self._project is None or self._scene is None:
            return None
        active = list(getattr(self._scene, "active_bg_palettes", []) or [])
        slot = int(getattr(self._scene, "ui_pal_bank", -1))
        if not 0 <= slot < len(active):
            return None
        bank = self._project.get_palette(active[slot])
        if not bank or idx >= len(bank.colors):
            return None
        from core.gba_color import bgr555_to_rgb888
        r, g, b = bgr555_to_rgb888(bank.colors[idx])
        return QColor(r, g, b)

    def _load_text_sheet(self, font):
        """Planche de glyphes TROUÉE, mise en cache par (chemin, empreinte).

        Cache au niveau du MODULE (cf. `_TEXT_SHEETS`). La clé porte l'empreinte
        disque, pour qu'une planche retouchée dans l'éditeur de police
        apparaisse quand même."""
        p = self._project
        if not font or not getattr(font, "asset", "") or p is None:
            return None
        path = p.asset_abs(font.asset)
        if not path or not path.exists():
            return None
        try:
            st = path.stat()
            key = (str(path), st.st_mtime_ns, st.st_size)
        except OSError:
            return None
        if key in _TEXT_SHEETS:
            return _TEXT_SHEETS[key]
        px = QPixmap(str(path))
        from ui.text_editor.glyph_paint import key_out
        sheet = None if px.isNull() else key_out(px, font.key_colors())
        if len(_TEXT_SHEETS) > 16:      # une poignée de polices suffit
            _TEXT_SHEETS.clear()
        _TEXT_SHEETS[key] = sheet
        return sheet

    def _paint_text(self, painter) -> bool:
        """Dessine les VRAIS glyphes dans le rectangle. Retourne True si le texte
        déborde (tronqué par le moteur au dernier glyphe qui tient).

        Pas de repli « faux texte » si la police manque : une approximation Qt
        donnerait une idée fausse de l'encombrement."""
        text = self._text_content()
        if not text:
            return False
        font = self._text_font()
        sheet = self._load_text_sheet(font)
        if sheet is None:
            return False
        from core.engine_emulation.text_layout import layout_text
        r = self.rect()
        placed, over = layout_text(font, text, int(r.width()), int(r.height()),
                                   align=getattr(self._region, "align", "left"),
                                   composited=self._composited())
        if not placed:
            return over
        painter.save()
        # Pixel art : jamais d'interpolation, à aucun zoom.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Surlignement SOUS les glyphes, sur l'étendue rendue arrondie à la
        # TUILE — le moteur peint des tuiles de surface, pas des pixels libres
        # (cf. `text_surf_seed`). Bornes prises comme les siennes : la plume
        # (donc la CHASSE, pas la largeur d'encre) à droite, l'INTERLIGNE en
        # bas. Les mesurer autrement donnerait une tuile d'écart avec la ROM sur
        # une police dont les glyphes sont plus petits que leur cellule.
        hl = self._highlight_color()
        if hl is not None:
            from codegen.font_emit import glyph_advance_px, font_line_px
            line = font_line_px(font)
            x0 = min(gx for _g, gx, _gy in placed) // 8 * 8
            y0 = min(gy for _g, _gx, gy in placed) // 8 * 8
            x1 = -(-max(gx + glyph_advance_px(g, font) for g, gx, _gy in placed) // 8) * 8
            y1 = -(-(max(gy for _g, _gx, gy in placed) + line) // 8) * 8
            painter.fillRect(QRectF(r.left() + x0, r.top() + y0, x1 - x0, y1 - y0), hl)
        for g, gx, gy in placed:
            painter.drawPixmap(QRectF(r.left() + gx, r.top() + gy, g.w, g.h),
                               sheet, QRectF(g.x, g.y, g.w, g.h))
        painter.restore()
        return over

    # ── Peinture ─────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        """Rectangle ÉLARGI d'une marge.

        Contour et poignées sont au pinceau COSMÉTIQUE (largeur 0), or Qt calcule
        sa zone à repeindre depuis `pen().widthF()` : le trait déborde de ce que
        Qt efface et le déplacement laisse des traînées. Marge en unités de
        SCÈNE, dimensionnée sur le pire cas (zoom 0.5). Fixe et non dérivée du
        zoom : Qt met `boundingRect` en cache."""
        m = 6.0
        return self.rect().adjusted(-m, -m, m, m)

    def _sync_chrome(self):
        """Visibilité et position du libellé selon l'état.

        Le NOM ne s'affiche qu'au survol ou à la sélection, sinon cinq zones
        imbriquées recouvrent le jeu (l'arbre donne déjà l'inventaire). L'icône
        de type, elle, reste toujours visible.

        Le libellé se pose AU-DESSUS du rectangle, et retombe à l'intérieur
        quand la zone touche le haut de l'écran."""
        show = self.isSelected() or self._hovered
        self._label.setVisible(show)
        y = -7.5 if self.pos().y() >= 9 else 1.0
        self._kind_icon.setPos(1, y)
        self._label.setPos(8.5, y)

    def paint(self, painter, option, widget=None):
        """Le CONTENU réel (couleur de palette PLEINE, nine-slice, background)
        — exactement ce que le build affichera, jamais une teinte d'édition ;
        sans contenu déclaré, rien n'est peint que le contour (pas de bulle de
        remplissage). Coins droits, comme le rendu compilé — le hardware n'a
        pas de rectangle arrondi."""
        r = self.rect()
        sel = self.isSelected()
        active = getattr(self.scene(), "active_item", None) is self
        path = QPainterPath()
        path.addRect(r)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.save()

        # 1. Contenu réel seulement — un conteneur SANS fond déclaré ne peint
        #    rien ici, juste son contour (étape 2 plus bas).
        painter.save()
        painter.setClipPath(path)
        self._paint_nine_slice(painter)
        self._paint_background(painter)
        self._paint_image(painter)
        if self._content_brush is not None:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(self._content_brush)
            painter.drawRect(r)
        # Le TEXTE en dernier, et sous le clip : le moteur borne le rendu au
        # rectangle (`text_clip_set`), l'aperçu doit couper au même endroit.
        overflows = self._paint_text(painter)
        painter.restore()   # lève le clip avant le contour (sinon la moitié du trait est rognée)

        # Débordement : liseré ambre en bas. Le moteur tronque au dernier glyphe
        # qui tient sans rien dire, et c'est ici qu'on peut encore agrandir.
        if overflows:
            warn = QPen(QColor(C.ACCENT_YLW))
            warn.setWidthF(2.0)
            warn.setCosmetic(True)
            painter.setPen(warn)
            painter.drawLine(QPointF(r.left(), r.bottom()),
                             QPointF(r.right(), r.bottom()))

        # 2. Contour — la COULEUR porte le type (cf. _KIND_COLORS). Un
        #    CONTENEUR est un cadre : tirets au repos. Une ancre non résolue
        #    reste en pointillés (position affichée ≠ position du jeu), et ce
        #    signal prime sur le reste.
        col = QColor("#ffffff") if (sel and active) else QColor(self._COLOR)
        col.setAlpha(255 if sel else (230 if self._hovered else 150))
        pen = QPen(col)
        pen.setWidthF(1.4)
        pen.setCosmetic(True)
        if not self._anchored:
            pen.setStyle(Qt.PenStyle.DotLine)
        elif getattr(self._region, "can_contain", False) and not sel:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawPath(path)

        # 3. Poignées — sélection seule.
        if sel:
            half = _HANDLE_HALF_PX / self._view_scale()
            painter.setPen(QPen(QColor("#ffffff"), 0))
            painter.setBrush(QBrush(self._COLOR))
            for hx, hy in self._handle_points().values():
                painter.drawRect(QRectF(hx - half, hy - half, 2 * half, 2 * half))
        painter.restore()

    # ── Poignées ─────────────────────────────────────────────────
    def _view_scale(self) -> float:
        """Facteur de zoom de la vue (m11), 1.0 s'il n'y a pas encore de vue."""
        sc = self.scene()
        views = sc.views() if sc else []
        return views[0].transform().m11() if views else 1.0

    def _handle_points(self) -> dict:
        """Centre de chaque poignée en coordonnées LOCALES.

        Rentrées d'un demi-côté vers l'INTÉRIEUR : centrées sur le bord, elles
        déborderaient du `boundingRect` et laisseraient des rémanences."""
        r = self.rect()
        d = _HANDLE_HALF_PX / self._view_scale()
        l, t, rt, b = r.left() + d, r.top() + d, r.right() - d, r.bottom() - d
        mx, my = (r.left() + r.right()) / 2, (r.top() + r.bottom()) / 2
        return {
            "nw": (l, t), "n": (mx, t), "ne": (rt, t), "e": (rt, my),
            "se": (rt, b), "s": (mx, b), "sw": (l, b), "w": (l, my),
        }

    def _handle_at(self, local_pos) -> "str | None":
        """Nom de la poignée sous `local_pos`, ou None. La tolérance est en
        pixels écran : une poignée reste attrapable même très dézoomée."""
        tol = _HANDLE_GRAB_PX / self._view_scale()
        for name, (hx, hy) in self._handle_points().items():
            if abs(local_pos.x() - hx) <= tol and abs(local_pos.y() - hy) <= tol:
                return name
        return None

    # ── Aimantation d'alignement ─────────────────────────────────
    def _snap_step(self) -> int:
        """Pas de grille de cette zone : 8 px (tuile) pour une cible BG — le
        moteur y écrit des entrées de tilemap, l'origine ne peut pas tomber
        entre deux tuiles — 1 px (libre) pour une cible OBJ composée pixel par
        pixel. Recalculé à chaque appel : `render_mode` peut changer sous
        l'édition."""
        rm = int(getattr(self._scene, "render_mode", 0) or 0)
        return 8 if self._layout.resolved_target(self._region, rm) == "bg" else 1

    def _axis_snap(self, moving_vals, is_x: bool):
        """(delta, ligne-guide) pour aimanter `moving_vals` (positions scène sur
        un axe) aux bords/centres des autres zones et au cadre écran. Le seuil
        est en pixels écran, converti via le zoom courant."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "ui_align_segments"):
            return 0.0, None
        xs, ys = sc.ui_align_segments(self)
        targets = collect_targets(xs if is_x else ys, GBA_W if is_x else GBA_H)
        thr = _ALIGN_SNAP_PX / self._view_scale()
        return _align_snap(moving_vals, targets, thr)

    def _descendant_items(self) -> list:
        """Items du canvas portant les DESCENDANTS de cet élément (tout le
        sous-arbre). Sert au suivi visuel pendant un drag de conteneur."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "_ui_region_items"):
            return []
        names = {d.name for d in self._layout.descendants(self._region.name)}
        return [it for it in sc._ui_region_items
                if it is not self and it._region.name in names]

    def _move_descendants(self, dx: float, dy: float):
        if dx or dy:
            for it in self._descendant_items():
                it.moveBy(dx, dy)

    def itemChange(self, change, value):
        # Aimante la position PROPOSÉE pendant un déplacement souris (et trace
        # les guides). Uniquement en sélection simple : en groupe, Qt translate
        # tous les items du même delta, dévier celui-ci désynchroniserait le lot.
        sc = self.scene()
        single = (sc is not None and hasattr(sc, "selectable_items")
                  and len(sc.selectable_items()) == 1)
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._moving and single):
            nx, ny = value.x(), value.y()
            w, h = self.rect().width(), self.rect().height()
            dx, gx = self._axis_snap(candidate_lines(nx, w), True)
            dy, gy = self._axis_snap(candidate_lines(ny, h), False)
            sc.show_align_guides(gx, gy)
            nx, ny = nx + dx, ny + dy
            # Aimantation à la grille EN COURS de geste : la boîte reste figée
            # sur sa case tant que la souris n'a pas franchi la suivante, au
            # lieu de suivre le pixel puis sauter d'un coup au relâchement.
            step = self._snap_step()
            if step > 1:
                nx = (int(nx) // step) * step
                ny = (int(ny) // step) * step
            return QPointF(nx, ny)
        # Position APPLIQUÉE pendant le geste : les enfants suivent du même
        # delta. Leur modèle est relatif au parent, il n'y a donc rien à
        # committer chez eux — c'est un suivi d'écran, pas une écriture.
        # Sélection simple seulement : en groupe, Qt déplace déjà chaque item.
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._moving and single):
            if self._last_pos is not None:
                self._move_descendants(value.x() - self._last_pos.x(),
                                       value.y() - self._last_pos.y())
            self._last_pos = QPointF(value)
        # Le libellé passe au-dessus ou à l'intérieur selon la place disponible,
        # et le chrome change avec la sélection : les deux se resynchronisent ici.
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged):
            self._sync_chrome()
        return super().itemChange(change, value)

    # ── Interaction ──────────────────────────────────────────────
    def hoverMoveEvent(self, e):
        if not self._hovered:
            self._hovered = True
            self._sync_chrome()
            self.update()
        name = self._handle_at(e.pos()) if self.isSelected() else None
        if name:
            self.setCursor(_HANDLE_CURSORS[name])
        elif self.isSelected():
            self.setCursor(Qt.CursorShape.SizeAllCursor)   # rappel : déplaçable
        else:
            self.unsetCursor()
        super().hoverMoveEvent(e)

    def hoverLeaveEvent(self, e):
        self.unsetCursor()
        self._hovered = False
        self._sync_chrome()
        self.update()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        self._press_pos = self.pos()
        # Figé AVANT le select : le bus resélectionne synchroniquement, donc
        # `isSelected()` serait déjà vrai juste après. Une poignée n'est dessinée
        # que sur une zone sélectionnée — le premier clic doit donc sélectionner,
        # et seul le geste SUIVANT sur une poignée redimensionne.
        was_selected = self.isSelected()
        from core.selection_bus import get_bus, UIRegionSelection
        get_bus().select(UIRegionSelection(self._layout, self._region))
        if (e.button() == Qt.MouseButton.LeftButton and was_selected):
            handle = self._handle_at(e.pos())
            if handle:
                self._resize_handle = handle
                self._resize_start = (QPointF(self.pos()), QRectF(self.rect()))
                e.accept()   # on ne passe PAS à Qt : sinon l'item se déplacerait
                return
        # Pas une poignée → déplacement : autoriser l'aimantation d'`itemChange`
        # et armer le suivi des descendants (delta depuis la position de départ).
        if e.button() == Qt.MouseButton.LeftButton:
            self._moving = True
            self._last_pos = QPointF(self.pos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resize_handle:
            self._drag_resize(e.scenePos())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._resize_handle:
            self._resize_handle = None
            self._resize_start = None
            self._press_pos = None
            self._commit_resize()
            sc = self.scene()
            if sc is not None and hasattr(sc, "clear_align_guides"):
                sc.clear_align_guides()
            e.accept()
            return
        super().mouseReleaseEvent(e)
        # Fin du déplacement : couper l'aimantation AVANT le snap tuile ci-dessous
        # (un setPos passerait sinon de nouveau par `itemChange`) et retirer les
        # guides.
        self._moving = False
        sc = self.scene()
        if sc is not None and hasattr(sc, "clear_align_guides"):
            sc.clear_align_guides()
        if self._press_pos is None:
            return
        start, self._press_pos = self._press_pos, None
        # Filet de sécurité : `itemChange` aimante déjà à la grille pendant le
        # geste (cf. `_snap_step`), donc ce re-snap est normalement un no-op —
        # sauf pour un setPos programmatique qui aurait contourné `_moving`.
        step = self._snap_step()
        pre = self.pos()
        nx = int(pre.x()) // step * step
        ny = int(pre.y()) // step * step
        self.setPos(nx, ny)
        # Le snap final doit aussi emporter les descendants — `_moving` est déjà
        # retombé, le suivi d'`itemChange` ne le fait plus. Sélection simple
        # seulement, comme le suivi lui-même (en groupe, chaque item gère le sien).
        if (sc is not None and hasattr(sc, "selectable_items")
                and len(sc.selectable_items()) == 1):
            self._move_descendants(nx - pre.x(), ny - pre.y())
        self._last_pos = None
        if (nx, ny) == (int(start.x()), int(start.y())):
            return
        # Un ancrage actor stocke un OFFSET : c'est lui qu'il faut réécrire,
        # pas la position absolue lue dans le canvas.
        ax, ay = self._parent_origin()
        from core.history import get_history, MoveUIRegionCmd
        get_history().push(MoveUIRegionCmd(
            self._region, self._region.x, self._region.y,
            nx - ax, ny - ay, persist_fn=self._save))

    # ── Redimensionnement ────────────────────────────────────────
    def _parent_origin(self) -> tuple[int, int]:
        """Origine ÉCRAN du PARENT (ou socle du frame si root). Sert à
        retrancher pour restocker x/y RELATIFS au parent : un enfant est
        pixel-relatif à son conteneur, un root à son socle d'ancrage."""
        return self._layout.parent_origin(self._region, self._actor_pos)

    def _drag_resize(self, scene_pos):
        """Déplace le(s) bord(s) de la poignée tirée vers la souris. Aimante à
        la grille de la cible (`_snap_step`) PENDANT le geste : le bord suivi
        reste sur sa case tant que la souris n'a pas franchi la suivante,
        `_commit_resize` ne fait plus alors qu'appliquer les bornes finales."""
        start_pos, start_rect = self._resize_start
        l = start_pos.x() + start_rect.left()
        t = start_pos.y() + start_rect.top()
        rt = start_pos.x() + start_rect.right()
        b = start_pos.y() + start_rect.bottom()
        ml, mt, mr, mb = _HANDLE_EDGES[self._resize_handle]
        if ml: l = scene_pos.x()
        if mt: t = scene_pos.y()
        if mr: rt = scene_pos.x()
        if mb: b = scene_pos.y()
        # Aimantation d'alignement sur le(s) SEUL(S) bord(s) que la poignée
        # déplace — un coin bouge un bord par axe, un milieu un seul.
        gx = gy = None
        if ml:
            dx, gx = self._axis_snap([l], True);  l += dx
        elif mr:
            dx, gx = self._axis_snap([rt], True); rt += dx
        if mt:
            dy, gy = self._axis_snap([t], False); t += dy
        elif mb:
            dy, gy = self._axis_snap([b], False); b += dy
        sc = self.scene()
        if sc is not None and hasattr(sc, "show_align_guides"):
            sc.show_align_guides(gx, gy)
        # Snap à la grille des SEULS bords tirés — les bords fixes viennent de
        # `_resize_start`, déjà sur la grille depuis le geste précédent. Les
        # quatre bords arrondissent vers l'EXTÉRIEUR de la boîte (floor à
        # gauche/haut, ceil à droite/bas) : rogner couperait du texte pour
        # faire joli, comme `_commit_resize`.
        step = self._snap_step()
        if step > 1:
            if ml: l = (int(l) // step) * step
            elif mr: rt = ((int(rt) + step - 1) // step) * step
            if mt: t = (int(t) // step) * step
            elif mb: b = ((int(b) + step - 1) // step) * step
        # Plancher de 8 px : le bord tiré s'arrête, le bord opposé ne bouge pas.
        if rt - l < 8:
            if ml: l = rt - 8
            else:  rt = l + 8
        if b - t < 8:
            if mt: t = b - 8
            else:  b = t + 8
        self.setPos(l, t)
        self.setRect(0, 0, rt - l, b - t)

    def _commit_resize(self):
        """Fige le geste : bornes, puis une seule commande d'historique. Le
        snap à la grille est déjà fait en LIVE par `_drag_resize` — ce re-snap
        est un filet de sécurité (no-op en pratique), comme dans
        `mouseReleaseEvent` pour le déplacement."""
        step = self._snap_step()
        l = int(self.pos().x())
        t = int(self.pos().y())
        rt = l + int(self.rect().width())
        b = t + int(self.rect().height())
        l = (l // step) * step
        t = (t // step) * step
        rt = ((rt + step - 1) // step) * step
        b = ((b + step - 1) // step) * step
        w = max(8, min(512, rt - l))
        h = max(8, min(512, b - t))
        self.setPos(l, t)
        self.setRect(0, 0, w, h)
        ax, ay = self._parent_origin()
        old = (self._region.x, self._region.y, self._region.w, self._region.h)
        new = (l - ax, t - ay, w, h)
        if old == new:
            return
        from core.history import get_history, ResizeUIRegionCmd
        get_history().push(ResizeUIRegionCmd(
            self._region, old, new, persist_fn=self._save))


class UIRegionController(QObject):
    """Crée et persiste les zones de texte dessinées dans le canvas.

    Analogue à `SceneInpaintingController` : détient le contexte (projet,
    scène) et applique le geste de l'outil au modèle.

    **Crée la mise en page à la demande.** Dessiner une zone dans une scène qui
    n'en référence aucune en fabrique une, nommée d'après la scène. Obliger à
    créer d'abord une mise en page vide, puis à la référencer, puis à dessiner,
    ferait payer trois gestes pour une intention — alors que le cas courant est
    « une mise en page par scène » et qu'elle reste partageable ensuite.

    L'unicité du nom est cherchée sur TOUT le projet : c'est l'espace de noms
    des constantes `REGION_*` (cf. models/ui_region.py)."""

    # Deux signaux et pas un : `persist_fn` d'une commande d'historique est
    # rappelé à l'ANNULATION comme à l'exécution. Confondre les deux ferait
    # annoncer « zone créée » en annulant sa création, et resélectionnerait une
    # zone qui vient d'être retirée.
    regions_changed = pyqtSignal()                # sauver + redessiner
    region_created  = pyqtSignal(object, object)  # (UILayout, UIRegion) — une fois

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._scene = None

    def set_context(self, project: Optional[Project], scene):
        self._project, self._scene = project, scene

    @property
    def ready(self) -> bool:
        return self._project is not None and self._scene is not None

    def _ensure_layout(self):
        from core.models.ui_region import UILayout
        lay = self._project.scene_ui_layout(self._scene)
        if lay is not None:
            return lay
        base = getattr(self._scene, "name", "") or "ui"
        name, n = base, 2
        while self._project.get_ui_layout(name) is not None:
            name = f"{base}_{n:02d}"; n += 1
        lay = UILayout(name=name)
        self._project.ui_layouts.append(lay)
        self._scene.ui_layout = name
        return lay

    def create_element(self, kind: str, x: int, y: int, w: int, h: int):
        """Crée un élément du `kind` demandé (texte, conteneur, image) au
        rectangle dessiné — même flux pour les trois types, seule la fabrique
        change. L'unicité se cherche sur TOUT le projet, quel que soit le type
        (cf. `Project.ui_element_names`).

        Une image neuve n'a pas de sprite : elle garde le rectangle dessiné
        jusqu'à ce qu'on lui en donne un, et l'inspecteur la redimensionnera
        alors sur sa frame. Lui en attribuer un d'office (« le premier du
        projet ») poserait un dessin que personne n'a demandé."""
        from core.models.ui_region import (
            UIPanel, UIText, UIImage, KIND_PANEL, KIND_IMAGE, unique_element_name,
        )
        from core.history import get_history, AddListItemCmd
        if not self.ready:
            return None
        lay = self._ensure_layout()
        x, y, w, h = int(x), int(y), int(w), int(h)
        taken = set(lay.element_names()) | set(self._project.ui_element_names())
        if kind == KIND_PANEL:
            el = UIPanel(name=unique_element_name(taken, "container"),
                         x=x, y=y, w=w, h=h)
            label = "container"
        elif kind == KIND_IMAGE:
            el = UIImage(name=unique_element_name(taken, "image"),
                         x=x, y=y, w=w, h=h)
            label = "image"
        else:
            el = UIText(name=unique_element_name(taken, "text"),
                        x=x, y=y, w=w, h=h)
            label = "text"
        # Par l'historique : dessiner un élément est une modification comme une
        # autre, elle doit s'annuler. `_ensure_layout` reste hors historique —
        # une mise en page vide et non référencée ne gêne personne, alors qu'un
        # undo qui la retire casserait les éléments créés ensuite.
        get_history().push(AddListItemCmd(
            lay.elements, el, persist_fn=self.regions_changed.emit,
            label=f"Add {label} {el.name}"))
        self.region_created.emit(lay, el)
        return el

    def create_region(self, x: int, y: int, w: int, h: int):
        """Alias historique — un emplacement de texte."""
        from core.models.ui_region import KIND_TEXT
        return self.create_element(KIND_TEXT, x, y, w, h)

    # ── Dupliquer / coller ────────────────────────────────────────

    def subtree_of(self, element) -> list:
        """L'élément et TOUT son sous-arbre, racine en tête — l'unité que
        copient le presse-papier et le dupliquer."""
        lay = self._project.scene_ui_layout(self._scene) if self.ready else None
        if lay is None:
            return [element]
        return [element] + lay.descendants(element.name)

    def duplicate_elements(self, elements: list, dx: int = 8, dy: int = 8) -> list:
        """Duplique des éléments de la mise en page de la scène, sous-arbres
        compris, décalés de (dx, dy). Une seule entrée d'historique.

        Un élément dont un ANCÊTRE est du lot est ignoré : son sous-arbre est
        déjà emporté par la copie de cet ancêtre."""
        if not self.ready or not elements:
            return []
        lay = self._project.scene_ui_layout(self._scene)
        if lay is None:
            return []
        picked = {e.name for e in elements}
        roots = [e for e in elements if not (set(lay.ancestors(e.name)) & picked)]
        groups = [self.subtree_of(e) for e in roots]
        return self._add_element_copies(lay, groups, dx, dy, "Duplicated")

    def paste_elements(self, groups: list, dx: int = 0, dy: int = 0) -> list:
        """Colle des sous-arbres venus du presse-papier du canvas (chacun sa
        racine en tête). Crée la mise en page de la scène si elle n'en a pas :
        coller dans une scène vierge est le cas d'usage principal."""
        if not self.ready or not groups:
            return []
        return self._add_element_copies(self._ensure_layout(), groups, dx, dy,
                                        "Pasted")

    def delete_elements(self, elements: list) -> list:
        """Supprime des éléments d'interface et TOUT leur sous-arbre, en une
        seule entrée d'historique.

        Le sous-arbre part avec le parent, comme il le suit à la duplication —
        et pour une raison plus dure qu'une symétrie : la position d'un enfant
        est RELATIVE à son conteneur. Laisser les orphelins derrière ne les
        laisserait pas en place, ça les ferait sauter ailleurs à l'écran (leur
        origine redevient celle du socle d'ancrage)."""
        from core.history import get_history, RemoveListItemsCmd
        if not self.ready or not elements:
            return []
        lay = self._project.scene_ui_layout(self._scene)
        if lay is None:
            return []
        victims: list = []
        for el in elements:
            for e in [el] + lay.descendants(el.name):
                if not any(v is e for v in victims):
                    victims.append(e)
        if not victims:
            return []
        n = len(elements)
        get_history().push(RemoveListItemsCmd(
            lay.elements, victims, persist_fn=self.regions_changed.emit,
            label=f"Deleted {n} interface element{'s' if n > 1 else ''}"))
        return victims

    def _add_element_copies(self, lay, groups: list, dx: int, dy: int,
                            verb: str) -> list:
        """Cœur commun : copie profonde de chaque sous-arbre, noms uniques,
        refs `parent` réécrites vers les copies, décalage sur la seule RACINE
        (les enfants sont positionnés relativement à leur parent, les décaler
        aussi les ferait glisser deux fois)."""
        from core.models.ui_region import unique_element_name
        from core.history import get_history, AddListItemsCmd
        taken = set(lay.element_names()) | set(self._project.ui_element_names())
        copies: list = []
        roots: list = []
        for group in groups:
            if not group:
                continue
            rename: dict[str, str] = {}
            pairs: list = []
            for src in group:
                new = copy.deepcopy(src)
                # Espace de noms : le projet entier, tous types confondus (cf.
                # Project.ui_element_names) — les refs `parent` restent ainsi
                # sans ambiguïté et les constantes C ne collisionnent pas.
                new.name = unique_element_name(taken, src.name)
                taken.add(new.name)
                rename[src.name] = new.name
                pairs.append((src, new))
            for src, new in pairs:
                if src.parent in rename:
                    # Parent copié avec le lot : l'enfant suit SA copie, sinon
                    # le sous-arbre se rebrancherait sur le conteneur d'origine.
                    new.parent = rename[src.parent]
                elif lay.get(src.parent) is not None:
                    new.parent = src.parent      # parent resté en place
                else:
                    # Collée dans une mise en page qui ne connaît pas son parent
                    # (autre scène) : redevient racine, pas de ref pendante.
                    new.parent = ""
            root = pairs[0][1]
            root.x = int(root.x) + int(dx)
            root.y = int(root.y) + int(dy)
            roots.append(root)
            copies.extend(new for _s, new in pairs)
        if not copies:
            return []
        n = len(roots)
        get_history().push(AddListItemsCmd(
            lay.elements, copies, persist_fn=self.regions_changed.emit,
            label=f"{verb} {n} interface element{'s' if n > 1 else ''}"))
        return roots


class SceneInpaintingController:
    """Pilote la peinture par palette d'un layer BG dans le canvas de scène.

    Analogue au couple collision_overlay/collision_painted : détient l'état
    (projet, scène, layer actif, banque de peinture active, raster du layer
    actif) et applique/persiste les overrides `SE_PALBANK` tuile par tuile.
    Peignable dès que le layer a une image exploitable (la palette d'origine
    de l'asset sert de base) — indépendant de `layer.pal_bank`."""

    def __init__(self, gba_scene: "GBAScene"):
        self._gfx = gba_scene
        self._project: Optional[Project] = None
        self._scene = None
        self._layer = None          # BackgroundLayer actif (peint)
        self._raster: Optional[BgLayerRaster] = None
        self._bank: Optional[int] = None   # slot (0-15) de la banque de peinture
        self._stroke: Optional[dict] = None  # delta en cours {(c,r): (old,new)}

    # ── Contexte ─────────────────────────────────────────────────
    def set_context(self, project: Optional[Project], scene):
        self._project = project
        self._scene = scene
        self._layer = None
        self._raster = None
        self._stroke = None
        # Banque de peinture par défaut = 1re banque BG active (si présente).
        actives = getattr(scene, "active_bg_palettes", []) if scene else []
        self._bank = 0 if actives else None

    def set_inpaint_layer(self, bg_slot: Optional[int]):
        """Choisit le layer peint (par bg_slot). Construit son raster."""
        self._layer = None
        self._raster = None
        if bg_slot is None or not self._scene:
            return
        for L in self._scene.background_layers:
            if L.bg_slot == bg_slot:
                self._layer = L
                break
        if self._layer is not None and self._project:
            ap = _layer_png_path(self._project, self._layer)
            self._raster = build_bg_raster(self._project, self._scene, self._layer, ap)

    def set_inpaint_bank(self, slot: Optional[int]):
        self._bank = slot

    def scene_bg_banks(self) -> list:
        """Liste (slot, PaletteBank) des banques BG actives résolues de la scène
        — source du bandeau de sélection de peinture."""
        out: list = []
        if not self._scene or not self._project:
            return out
        names = getattr(self._scene, "active_bg_palettes", [])
        for slot in range(len(names)):
            b = resolve_palette_bank(self._project, names, slot)
            if b and b.colors:
                out.append((slot, b))
        return out

    @property
    def inpaint_layer_slot(self) -> Optional[int]:
        return self._layer.bg_slot if self._layer is not None else None

    @property
    def inpaint_bank(self) -> Optional[int]:
        return self._bank

    @property
    def ready(self) -> bool:
        """Peinture possible : layer avec image exploitable (raster construit
        depuis la palette d'origine) + banque de peinture choisie."""
        return self._raster is not None and self._bank is not None

    def tiles_size(self) -> tuple[int, int]:
        if self._raster is None:
            return (0, 0)
        return (self._raster.tiles_w, self._raster.tiles_h)

    # ── Peinture ─────────────────────────────────────────────────
    def begin_stroke(self):
        self._stroke = {}

    def inpaint_tile(self, col: int, row: int, erase: bool = False):
        """Peint (ou efface) l'override d'une tuile ; met à jour le canvas en
        direct. Enregistre l'ancienne valeur dans le stroke courant."""
        if not self.ready or self._layer is None:
            return
        if not (0 <= col < self._raster.tiles_w and 0 <= row < self._raster.tiles_h):
            return
        key = (col, row)
        new = None if erase else self._bank
        old = self._layer.tile_palette_overrides.get(key)
        if old == new:
            return
        if self._stroke is not None:
            if key not in self._stroke:
                self._stroke[key] = (old, new)
            else:
                self._stroke[key] = (self._stroke[key][0], new)
        self._apply_tile(key, new)
        self._refresh()

    def _apply_tile(self, key: tuple[int, int], slot: Optional[int]):
        if slot is None:
            self._layer.tile_palette_overrides.pop(key, None)
        else:
            self._layer.tile_palette_overrides[key] = slot
        if self._raster is not None:
            self._raster.patch_tile(key[0], key[1], slot)

    def _refresh(self):
        if self._raster is not None and self._layer is not None:
            self._gfx.set_bg(self._layer.bg_slot, self._raster.to_pixmap())

    def end_stroke(self):
        """Clôt le stroke : pousse la commande d'historique + persiste."""
        delta = self._stroke or {}
        self._stroke = None
        if not delta or self._layer is None:
            return
        from core.history import SceneInpaintingCmd, get_history
        cmd = SceneInpaintingCmd(self, self._layer, self._layer.bg_slot, dict(delta))
        h = get_history()
        h._undo.append(cmd)
        h._redo.clear()
        h.changed.emit()
        self._persist()

    # ── Undo/redo (appelé par SceneInpaintingCmd) ────────────────────────
    def apply_override_delta(self, layer, bg_slot: int, delta: dict, forward: bool):
        """Réapplique un delta sur un layer (forward=redo, sinon undo), rebâtit
        le pixmap de ce layer, et persiste. Robuste même si ce n'est plus le
        layer actif."""
        for key, (old, new) in delta.items():
            slot = new if forward else old
            if slot is None:
                layer.tile_palette_overrides.pop(key, None)
            else:
                layer.tile_palette_overrides[key] = slot
        self.rebuild_layer_pixmap(bg_slot)
        self._persist()

    def rebuild_layer_pixmap(self, bg_slot: int):
        """Reconstruit le raster + pixmap d'un layer depuis son état courant."""
        if not self._scene or not self._project:
            return
        layer = next((L for L in self._scene.background_layers
                      if L.bg_slot == bg_slot), None)
        if layer is None:
            return
        ap = _layer_png_path(self._project, layer)
        raster = build_bg_raster(self._project, self._scene, layer, ap)
        if raster is not None:
            self._gfx.set_bg(bg_slot, raster.to_pixmap())
            if self._layer is layer:
                self._raster = raster

    def _persist(self):
        if not self._project or not self._scene:
            return
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().save_scene()


# ──────────────────────────────────────────────────────────────────
#  Wrapper canvas + toolbar flottante
# ──────────────────────────────────────────────────────────────────
class CanvasContainer(QWidget):
    """QWidget superposant GBAView et FloatingToolbar."""

    tool_changed = pyqtSignal(str)

    def __init__(self, view: GBAView, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        self._toolbar = FloatingToolbar(self)
        self._toolbar.move(10, 10)
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.raise_()

        # Bandeau flottant de sélection de la banque de peinture (bas-centre,
        # même widget que Sprite Editor/Background Editor — cf. palette_bank_strip).
        self._inpaint_ctrl: Optional[SceneInpaintingController] = None
        self._inpaint_bank_strip = PaletteBankStrip("Aucune banque BG active", self)
        self._inpaint_bank_strip.selected.connect(self._on_inpaint_bank_selected)
        self._inpaint_bank_strip.raise_()

    def bind_inpainting(self, ctrl: "SceneInpaintingController"):
        self._inpaint_ctrl = ctrl

    def _on_inpaint_bank_selected(self, slot: int):
        if self._inpaint_ctrl:
            self._inpaint_ctrl.set_inpaint_bank(slot)

    def refresh_inpaint_banks(self):
        ctrl = self._inpaint_ctrl
        banks = ctrl.scene_bg_banks() if ctrl else []
        entries = [(slot, f"Banque {slot} — {bank.name}", bank.colors) for slot, bank in banks]
        self._inpaint_bank_strip.load(entries, active=ctrl.inpaint_bank if ctrl else None)
        if ctrl:
            ctrl.set_inpaint_bank(self._inpaint_bank_strip.active())
        self._position_inpaint_strip()

    def set_inpaint_strip_visible(self, visible: bool):
        if visible:
            self.refresh_inpaint_banks()
        self._inpaint_bank_strip.setVisible(visible)
        self._inpaint_bank_strip.raise_()

    def _position_inpaint_strip(self):
        strip = self._inpaint_bank_strip
        strip.reflow()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(0, self.height() - strip.height() - 12)
        strip.move(x, y)

    def _on_tool_changed(self, tool: str):
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._toolbar.current_tool

    def activate_tool_shortcut(self, group: str):
        """Relais des raccourcis clavier d'outil vers la toolbar flottante."""
        self._toolbar.activate_shortcut(group)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self._toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        if self._inpaint_bank_strip.isVisible():
            self._position_inpaint_strip()
            self._inpaint_bank_strip.raise_()


# ──────────────────────────────────────────────────────────────────
#  Widget éditeur de scène complet
# ──────────────────────────────────────────────────────────────────
def _tile_snap(v: int) -> int:
    """Décalage aimanté à la tuile 8 px — appliqué aux copies d'éléments
    d'interface : une zone en cible BG occupe des entrées de tilemap, son
    origine ne peut pas tomber entre deux tuiles (cf. UIRegionItem)."""
    return int(round(v / 8.0)) * 8


class _CanvasClipboard:
    """Presse-papier INTERNE du canvas (Ctrl+C / Ctrl+V).

    Interne et pas le presse-papier système : ce qu'on copie est un graphe
    d'objets du projet (composants, sous-arbre d'interface), pas du texte.

    Au niveau du MODULE et pas de l'écran : changer de scène reconstruit
    l'éditeur, or coller dans une AUTRE scène est tout l'intérêt face au Ctrl+D.

    Le contenu est une copie profonde : modifier ou supprimer la source après
    la copie ne change pas ce qui sera collé."""

    def __init__(self):
        self.actors: list = []
        self.ui_groups: list = []   # sous-arbres d'interface, racine en tête
        self.scene_name: str = ""   # scène d'origine (cf. paste_offset)
        self.pastes: int = 0

    @property
    def empty(self) -> bool:
        return not self.actors and not self.ui_groups

    def take(self, actors: list, ui_groups: list, scene_name: str):
        self.actors = copy.deepcopy(actors)
        self.ui_groups = copy.deepcopy(ui_groups)
        self.scene_name = scene_name
        self.pastes = 0

    def paste_offset(self, scene_name: str) -> int:
        """Décalage du prochain collage, en px.

        Dans la scène d'origine on décale de 8 px de plus à chaque collage,
        sinon la copie se cache sous l'original. Dans une AUTRE scène, le
        premier collage garde la position exacte : c'est « reproduire cette
        mise en place ailleurs »."""
        self.pastes += 1
        n = self.pastes if scene_name == self.scene_name else self.pastes - 1
        return 8 * n


_clipboard = _CanvasClipboard()


class SceneEditor(QWidget):
    scene_changed = pyqtSignal()  # fin de drag / déplacement caméra → sauvegarder
    # Position d'une caméra changée PAR DRAG dans le canvas — l'inspecteur
    # doit suivre (cf. window.py, symétrique de CameraInspector.camera_moved
    # qui fait le chemin inverse).
    camera_position_changed = pyqtSignal(object, int, int)   # Camera|None, x, y
    # `_reload_ui_regions` est le point de convergence des TROIS origines d'une
    # mise en page modifiée (dessin/suppression/collage au canvas, édition dans
    # l'inspecteur, opération depuis l'arbre de scène — cf. les branchements de
    # `regions_changed`/`ui_regions_changed`/`ui_layout_changed` dans window.py)
    # : un conteneur qui change de fond (nine-slice/background) change
    # l'occupation des banques de palette (cf. codegen/palette_alloc.
    # scene_palette_view). window.py y branche le rafraîchissement de la carte
    # Palettes, une fois pour les trois origines au lieu de trois branchements.
    ui_regions_reloaded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._sprite_pixmaps: dict[int, QPixmap] = {}
        # Frames AVANT mélange — cf. `refresh_blend`.
        self._raw_sprite: dict[int, QPixmap] = {}
        # Layers AVANT mélange — idem.
        self._raw_bg: dict[int, QPixmap] = {}
        # Ce qui est derrière les sprites — un BottomLayer
        # (couleurs + masque des secondes cibles), cf. blend_preview.
        self._blend_bottom = None
        self._canvas_w = GBA_W
        self._canvas_h = GBA_H
        self._show_all_boxes = False
        # Sauvegarde coalescée : un nudge clavier maintenu (auto-repeat) ne doit
        # pas écrire la scène sur disque à chaque frappe — on ne persiste qu'une
        # fois l'utilisateur arrêté, ce qui évite la rafale d'écritures atomiques
        # (source des verrous transitoires Windows) et réduit l'I/O.
        from PyQt6.QtCore import QTimer
        self._nudge_save_timer = QTimer(self)
        self._nudge_save_timer.setSingleShot(True)
        self._nudge_save_timer.setInterval(180)
        self._nudge_save_timer.timeout.connect(self._flush_nudge_save)
        self._setup_ui()

    def _flush_nudge_save(self):
        from core.command_dispatcher import get_dispatcher
        get_dispatcher().save_scene()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Barre haut — composant partagé (cf. ui/common/canvas_top_bar) ──
        self._bar = CanvasTopBar("Fit scene to view  (F)")
        self._bar.zoom_step_asked.connect(self._zoom_step)
        self._bar.fit_asked.connect(self._fit)
        self._bar.set_canvas_size(GBA_W, GBA_H)

        # ── Toggles d'affichage iconifiés (remplacent les cases texte) ──
        self._chk_grid8 = self._bar.add_toggle(
            "view_grid", "8 px grid (GBA tile)", self._on_grid8_toggle)
        self._chk_grid16 = self._bar.add_toggle(
            "view_grid_large", "16 px grid", self._on_grid16_toggle)
        self._chk_snap = self._bar.add_toggle(
            "view_snap", "Snap — align actors to the grid while moving",
            self._on_snap_toggle)
        self._bar.add_spacing(10)
        self._chk_boxes_actors = self._bar.add_toggle(
            "view_boxes", "Actor boxes — collision boxes of all actors",
            self._on_boxes_actors_toggle)
        self._chk_collision_view = self._bar.add_toggle(
            "view_collision", "Scene collisions — painted collision map",
            self._on_collision_view_toggle)
        self._bar.add_spacing(10)
        self._chk_ui_elements = self._bar.add_toggle(
            "ui_layout", "Interface elements — text zones, containers, texts",
            self._on_ui_elements_toggle)
        # blockSignals : self._gba_scene est créé plus bas, et le `toggled`
        # SYNCHRONE de setChecked ferait planter _on_ui_elements_toggle dessus
        # (AttributeError dans un slot appelé depuis C++ = plantage natif). Le
        # défaut True est déjà celui de GBAScene._ui_elements_visible.
        self._chk_ui_elements.blockSignals(True)
        self._chk_ui_elements.setChecked(True)
        self._chk_ui_elements.blockSignals(False)

        layout.addWidget(self._bar)

        # ── Canvas ────────────────────────────────────────────────
        self._gba_scene = GBAScene()
        self._gba_view = GBAView(self._gba_scene)
        self._gba_view.setMouseTracking(True)
        self._gba_scene.selectionChanged.connect(self._on_selection_changed)
        # Filet de sécurité : Qt.selectionChanged ne fire que si l'ensemble
        # sélectionné change réellement — un clic répété dans le même état
        # (déjà vide, dedans ou dehors) ne le déclenche pas, et l'inspecteur ne
        # se met jamais à jour. left_click_settled force la réévaluation après
        # CHAQUE clic gauche (cf. GBAView.mousePressEvent).
        self._gba_view.left_click_settled.connect(self._on_selection_changed)
        self._gba_scene.changed.connect(self._on_scene_item_changed)
        self._gba_view.prefab_template_dropped.connect(self._on_prefab_template_dropped)
        get_bus().changed.connect(self.on_selection)

        self._canvas_container = CanvasContainer(self._gba_view)
        layout.addWidget(self._canvas_container, 1)

        self._gba_view.viewport().setMouseTracking(True)
        self._gba_view.viewport().installEventFilter(self)

        # Outil par défaut
        from ui.scene_manager.canvas_tools import SelectTool

        self._gba_view.set_tool(SelectTool(self._gba_view))

        self._canvas_container.tool_changed.connect(self._on_tool_changed)
        self._gba_view.collision_painted.connect(self._on_collision_painted)
        self._gba_view.actor_context_requested.connect(self._on_actor_context_menu)
        self._gba_view.duplicate_drag_finished.connect(self._on_duplicate_drag)

        self._setup_shortcuts()

        # Contrôleur de peinture par palette BG + bandeau de palette flottant.
        self._inpainting_ctrl = SceneInpaintingController(self._gba_scene)
        self._gba_view.inpainting_controller = self._inpainting_ctrl
        self._canvas_container.bind_inpainting(self._inpainting_ctrl)

        # Contrôleur des zones de texte (outil « Zone de texte »).
        self._ui_region_ctrl = UIRegionController(self)
        self._gba_view.ui_region_controller = self._ui_region_ctrl
        self._ui_region_ctrl.region_created.connect(self._on_region_created)
        # Sauver PUIS redessiner : la zone créée (ou remise par un redo) n'a pas
        # encore d'item. Le redessin n'est pas branché sur le drag d'une zone
        # existante — détruire un item depuis son propre mouseReleaseEvent est
        # ce qui faisait planter le rechargement par le watcher.
        self._ui_region_ctrl.regions_changed.connect(self._save_ui_regions)
        self._ui_region_ctrl.regions_changed.connect(self._reload_ui_regions)

        self._update_zoom_label()

    # ── Événements ────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj == self._gba_view.viewport() and event.type() == QEvent.Type.MouseMove:
            pos = self._gba_view.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())
            inside = 0 <= x < self._canvas_w and 0 <= y < self._canvas_h
            self._bar.set_cursor_px(x if inside else None, y if inside else None)
        return False

    # ── Zoom ──────────────────────────────────────────────────────

    _ZOOM_LEVELS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]

    def _zoom_step(self, direction: int):
        current = self._gba_view._zoom
        levels = self._ZOOM_LEVELS
        idx = min(range(len(levels)), key=lambda i: abs(levels[i] - current))
        idx = max(0, min(idx + direction, len(levels) - 1))
        self._gba_view.zoom_to(levels[idx])
        self._update_zoom_label()

    # ── Raccourcis clavier ────────────────────────────────────────

    def _setup_shortcuts(self):
        """Raccourcis clavier du canvas. Contexte WidgetWithChildrenShortcut :
        actifs seulement quand le focus est dans le SceneEditor (donc pas quand
        on tape dans un champ d'un autre panneau)."""
        from PyQt6.QtGui import QShortcut, QKeySequence
        from core.keybindings import bind

        def mk(seq, slot):
            """Raccourci NON remappable — touche positionnelle (nudge) ou
            simple alias secondaire (Backspace = Suppr), jamais montré à
            l'écran Réglages. Cf. core/keybindings.py, tête de fichier."""
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            return sc

        def mkb(binding_id, slot):
            """Raccourci REMAPPABLE — touche posée par core/keybindings.py,
            éditable depuis Réglages → Shortcuts."""
            sc = QShortcut(QKeySequence(), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            bind(binding_id, sc)
            return sc

        # Bascule d'outil — mêmes lettres que les tooltips de la toolbar
        mkb("canvas.tool_select",    lambda: self._shortcut_tool("select"))
        mkb("canvas.tool_add",       lambda: self._shortcut_tool("add"))
        mkb("canvas.tool_erase",     lambda: self._shortcut_tool("erase"))
        mkb("canvas.tool_collision", lambda: self._shortcut_tool("collision"))
        mkb("canvas.tool_inpaint",   lambda: self._shortcut_tool("inpaint"))
        mkb("canvas.tool_ui",        lambda: self._shortcut_tool("ui"))
        # Vue
        mkb("canvas.fit", self._fit)
        # Sélection / édition
        mkb("canvas.cancel", self._shortcut_escape)
        mkb("canvas.delete", self._shortcut_delete)
        mk("Backspace", self._shortcut_delete)   # alias fixe, cf. mk() ci-dessus
        mkb("canvas.duplicate", self._shortcut_duplicate)
        mkb("canvas.copy", self._shortcut_copy)
        mkb("canvas.paste", self._shortcut_paste)
        # Nudge de la sélection : 1 px, Shift = 8 px (cran de grille) — touches
        # positionnelles, hors du registre remappable (cf. core/keybindings.py)
        for seq, (dx, dy) in {
            "Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1),
            "Shift+Left": (-8, 0), "Shift+Right": (8, 0),
            "Shift+Up": (0, -8), "Shift+Down": (0, 8),
        }.items():
            mk(seq, lambda dx=dx, dy=dy: self._shortcut_nudge(dx, dy))

    def _selected_sprite_items(self) -> list:
        return [it for it in self._gba_scene.selectedItems()
                if isinstance(it, SpriteItem)]

    def _selected_ui_items(self) -> list:
        return [it for it in self._gba_scene.selectedItems()
                if isinstance(it, UIRegionItem)]

    # ── Menu contextuel actor (clic-droit en mode Sélection) ──────

    def _on_actor_context_menu(self, item: "SpriteItem", global_pos):
        """Le menu agit sur TOUTE la sélection — même règle que Suppr et Ctrl+D,
        sinon un clic-droit sur 3 actors sélectionnés n'en supprimerait qu'un.
        `item` sert de repli quand il vient d'un clic hors sélection. Renommer
        reste réservé à un actor unique (un seul nom à saisir)."""
        from PyQt6.QtWidgets import QMenu
        from core.command_dispatcher import get_dispatcher
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        if item.scene_sprite not in actors:
            actors = [item.scene_sprite]
        n = len(actors)

        menu = QMenu(self)
        menu.setFont(QFont(T.UI, T.MD))
        menu.setStyleSheet(QSS.menu)
        act_rename = menu.addAction("Rename…")
        act_rename.setEnabled(n == 1)
        act_dup = menu.addAction("Duplicate" if n == 1 else f"Duplicate ({n})")
        menu.addSeparator()
        act_del = menu.addAction("Delete" if n == 1 else f"Delete ({n})")
        chosen = menu.exec(global_pos)
        if chosen is act_rename:
            self._rename_actor(actors[0])
        elif chosen is act_dup:
            # Par la sélection : le menu vise déjà tout le lot, et les copies
            # doivent hériter de la sélection comme après un Ctrl+D.
            self._select_copies(get_dispatcher().duplicate_actors(actors),
                                [], "Duplicated")
        elif chosen is act_del:
            get_dispatcher().delete_actors(actors)

    def _rename_actor(self, actor):
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename actor", "Name:", text=actor.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == actor.name:
            return
        from core.command_dispatcher import get_dispatcher
        disp = get_dispatcher()
        # Via le projet : réécrit les get_actor("…") des scripts et poste le
        # message de statut (même chemin que le renommage par l'en-tête).
        if self._project:
            self._project.rename_actor(actor, new_name)
        else:
            actor.name = new_name
        disp.save_scene()
        disp._emit("actors_list_changed")
        disp._emit("scene_sprites_changed")
        get_bus().select(actor)   # rafraîchit l'inspecteur / l'en-tête

    def _shortcut_tool(self, group: str):
        self._canvas_container.activate_tool_shortcut(group)

    def _shortcut_escape(self):
        self._gba_scene.clearSelection()
        self._canvas_container.activate_tool_shortcut("select")

    def _shortcut_delete(self):
        """Suppr — sur TOUTE la sélection, acteurs et éléments d'interface
        confondus (même portée que Ctrl+D, Alt+glisser et Ctrl+C/V)."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        # Vider le bus AVANT la suppression : la persistance des zones réémet
        # la sélection courante vers l'inspecteur, qui rechargerait un élément
        # déjà retiré de la mise en page.
        get_bus().clear()
        get_dispatcher().delete_actors(actors)
        gone = self._ui_region_ctrl.delete_elements(elements)
        n = len(actors) + len(elements)
        if gone or actors:
            get_dispatcher().status(f"Deleted {n} element{'s' if n > 1 else ''}")

    def _shortcut_duplicate(self):
        self._duplicate_selection(8, 8)

    # ── Dupliquer / copier / coller ───────────────────────────────
    # Ctrl+D, Alt+glisser et Ctrl+V passent par le même chemin, seule l'origine
    # du décalage change. Acteurs ET éléments d'interface.

    def _duplicate_selection(self, dx: int, dy: int):
        """Duplique la sélection courante, décalée de (dx, dy)."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        new_actors = get_dispatcher().duplicate_actors(actors, dx, dy)
        # Une zone en cible BG s'écrit dans une tilemap : son origine ne peut
        # pas tomber entre deux tuiles, donc décalage aimanté.
        edx, edy = _tile_snap(dx), _tile_snap(dy)
        if elements and not edx and not edy:
            # Geste plus court qu'une demi-tuile : la copie tomberait pile sur
            # l'original, donc invisible. Un cran de grille, comme au Ctrl+D.
            edx = edy = 8
        new_elements = self._ui_region_ctrl.duplicate_elements(elements, edx, edy)
        self._select_copies(new_actors, new_elements, "Duplicated")

    def _on_duplicate_drag(self, dx: int, dy: int):
        """Alt+glisser relâché : la vue a déjà remis les originaux en place."""
        self._duplicate_selection(dx, dy)

    def _shortcut_copy(self):
        """Ctrl+C — met la sélection dans le presse-papier du canvas.

        Une sélection vide ne VIDE pas le presse-papier : un Ctrl+C manqué (clic
        à côté puis raccourci) perdrait sinon ce qu'on s'apprêtait à coller."""
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        elements = [it._region for it in self._selected_ui_items()]
        if not actors and not elements:
            return
        # Même règle qu'à la duplication : un élément dont un ancêtre est du
        # lot voyage dans le sous-arbre de celui-ci, pas en double.
        lay = (self._project.scene_ui_layout(self._project.active_scene)
               if self._project else None)
        groups = []
        if lay is not None and elements:
            picked = {e.name for e in elements}
            for e in elements:
                if set(lay.ancestors(e.name)) & picked:
                    continue
                groups.append([e] + lay.descendants(e.name))
        scene = self._project.active_scene if self._project else None
        _clipboard.take(actors, groups, getattr(scene, "name", ""))
        n = len(actors) + len(groups)
        get_dispatcher().status(
            f"Copied {n} element{'s' if n > 1 else ''}")

    def _shortcut_paste(self):
        """Ctrl+V — colle le presse-papier dans la scène ACTIVE (pas forcément
        celle où la copie a été faite : c'est tout l'intérêt du geste)."""
        if _clipboard.empty or not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        d = _clipboard.paste_offset(getattr(scene, "name", ""))
        new_actors = get_dispatcher().paste_actors(_clipboard.actors, d, d)
        new_elements = self._ui_region_ctrl.paste_elements(
            _clipboard.ui_groups, _tile_snap(d), _tile_snap(d))
        self._select_copies(new_actors, new_elements, "Pasted")

    def _select_copies(self, actors: list, elements: list, verb: str):
        """Donne la sélection aux copies fraîches : c'est sur elles que porte le
        geste suivant, jamais sur les originaux.

        Signaux tus pendant la bascule — chaque setSelected() ferait transiter
        le bus par un état « plus rien de sélectionné » que l'inspecteur
        traduirait par un retour à l'aperçu."""
        if not actors and not elements:
            return
        self._gba_scene.blockSignals(True)
        for item in self._gba_scene.selectedItems():
            item.setSelected(False)
        first = None
        for a in actors:
            it = self._find_item(a)
            if it is not None:
                it.setSelected(True)
                first = first or it
        for el in elements:
            for it in self._gba_scene._ui_region_items:
                if it._region is el:
                    it.setSelected(True)
                    first = first or it
                    break
        self._gba_scene.blockSignals(False)
        self._gba_scene.set_active_item(first)
        # L'inspecteur suit l'item ACTIF : on l'annonce sur le bus, qui sait ne
        # pas réduire la sélection quand l'objet en est déjà membre.
        if first is not None:
            if isinstance(first, SpriteItem):
                get_bus().select(first.scene_sprite)
            else:
                from core.selection_bus import UIRegionSelection
                get_bus().select(UIRegionSelection(first._layout, first._region))
        n = len(actors) + len(elements)
        get_dispatcher().status(f"{verb} {n} element{'s' if n > 1 else ''}")

    def _shortcut_nudge(self, dx: int, dy: int):
        items = self._selected_sprite_items()
        if not items:
            return
        from core.history import get_history, MoveActorCmd
        for it in items:
            a = it.scene_sprite
            ox, oy = it.pos_px()   # résout px/tile/réf avant d'ajouter le delta

            def persist(it=it):
                # Le garde-fou itemChange (_drag_origin is None) empêche le
                # re-snap et la réécriture du modèle sur ce setPos programmatique.
                it.sync_pos()
                self._update_actor_box_overlay()

            get_history().push(
                MoveActorCmd(a, ox, oy, ox + dx, oy + dy, persist_fn=persist))
        # Persistance différée/coalescée (cf. _nudge_save_timer) : un maintien de
        # flèche déclenche une seule sauvegarde après relâchement, pas une par
        # frappe. Le modèle en mémoire est déjà à jour pour l'affichage.
        self._nudge_save_timer.start()

    def _fit(self):
        self._gba_view.fit(self._canvas_w, self._canvas_h)
        self._update_zoom_label()

    def _update_zoom_label(self):
        self._bar.set_zoom(self._gba_view._zoom)

    def _on_grid8_toggle(self, checked: bool):
        if checked:
            self._chk_grid16.blockSignals(True)
            self._chk_grid16.setChecked(False)
            self._chk_grid16.blockSignals(False)
        self._gba_scene.set_grid(checked, cell=8)

    def _on_grid16_toggle(self, checked: bool):
        if checked:
            self._chk_grid8.blockSignals(True)
            self._chk_grid8.setChecked(False)
            self._chk_grid8.blockSignals(False)
        self._gba_scene.set_grid(checked, cell=16)

    def _on_snap_toggle(self, checked: bool):
        self._gba_scene.set_snap(checked)
        self._gba_view.set_snap(checked)

    def _on_boxes_actors_toggle(self, checked: bool):
        self._show_all_boxes = checked
        self._update_actor_box_overlay()

    def _on_collision_view_toggle(self, checked: bool):
        self._gba_scene.set_collision_view(checked)

    def _on_ui_elements_toggle(self, checked: bool):
        self._gba_scene.set_ui_elements_view(checked)

    def _update_actor_box_overlay(self):
        if not self._project:
            self._gba_scene.update_actor_boxes([])
            return
        # Valeurs par défaut des variables déclarées — pour dessiner les box
        # dont un champ (x/y/w/h) référence un global/const plutôt qu'un littéral.
        from core.models.field_value import var_defaults_from_project
        var_defaults = var_defaults_from_project(self._project)
        if self._show_all_boxes:
            self._gba_scene.update_actor_boxes(self._project.active_scene.actors, var_defaults)
        else:
            actors = [
                item.scene_sprite
                for item in self._gba_scene._sprite_items
                if item.isSelected()
            ]
            self._gba_scene.update_actor_boxes(actors, var_defaults)

    # ── Outil actif ───────────────────────────────────────────────

    def _on_tool_changed(self, tool_id: str):
        from ui.scene_manager.canvas_tools import AddActorTool, CollisionTool, EraseTool, SelectTool

        match tool_id:
            case t if t.startswith("collision"):
                from ui.scene_manager.canvas_tools import CollisionTool

                self._gba_view.set_tool(CollisionTool(self._gba_view, t))
            case t if t.startswith("inpaint"):
                from ui.scene_manager.canvas_tools import SceneInpaintingTool

                self._gba_view.set_tool(SceneInpaintingTool(self._gba_view, t))
            case "add":
                self._gba_view.set_tool(AddActorTool(self._gba_view))
            case "erase":
                self._gba_view.set_tool(EraseTool(self._gba_view))
            case t if t.startswith("ui_"):
                from ui.scene_manager.canvas_tools import UIWidgetTool

                # "ui_text" | "ui_panel" | "ui_image" → kind du modèle
                self._gba_view.set_tool(UIWidgetTool(self._gba_view, t[3:]))
            case _:
                self._gba_view.set_tool(SelectTool(self._gba_view))
        # Bandeau de palette visible seulement pour les outils de peinture BG.
        self._canvas_container.set_inpaint_strip_visible(tool_id.startswith("inpaint"))

    def _reload_ui_regions(self):
        """(Re)dessine les zones de la scène active."""
        scene = self._project.active_scene if self._project else None
        lay = self._project.scene_ui_layout(scene) if (self._project and scene) else None
        self._gba_scene.set_ui_regions(lay, self._project, scene,
                                       save_fn=self._save_ui_regions)
        self.ui_regions_reloaded.emit()

    def _save_ui_regions(self):
        """Persiste après un déplacement de zone au canvas, et recharge
        l'inspecteur : ses spinbox montreraient sinon l'ancienne position."""
        if not self._project:
            return
        # Écriture par le dispatcher (watcher suspendu) — cf. la même règle dans
        # UIRegionInspector._persist : une écriture nue passe pour une édition
        # externe et déclenche un rechargement de scène en plein geste.
        get_dispatcher().save_all()
        self.scene_changed.emit()
        from core.selection_bus import get_bus, UIRegionSelection
        cur = get_bus().current
        if isinstance(cur, UIRegionSelection):
            get_bus().changed.emit(cur)

    def _on_region_created(self, layout, region):
        """Sélectionne la zone et l'annonce. La sauvegarde et le redessin
        passent par `regions_changed` — eux doivent aussi jouer à l'annulation.

        La mise en page est un asset PARTAGÉ : le message dit combien de scènes
        la référencent, sinon on ajoute une zone à douze scènes en croyant
        l'ajouter à une."""
        if not self._project:
            return
        from core.selection_bus import get_bus, UIRegionSelection
        get_bus().select(UIRegionSelection(layout, region))
        users = self._project.ui_layout_users(layout.name)
        shared = f" — shared by {len(users)} scenes" if len(users) > 1 else ""
        kind_label = {"panel": "Container", "image": "Image"}.get(
            getattr(region, "kind", "text"), "Text")
        # L'empreinte en tuiles ne se dit que pour ce qui occupe la tilemap ;
        # une image l'annonce dans son inspecteur, d'après son sprite.
        tiles = ""
        if getattr(region, "kind", "") != "image" and hasattr(region, "tile_rect"):
            tw, th = region.tile_rect()[2:]
            tiles = f" · {tw}×{th} tiles"
        get_dispatcher().status(
            f"{kind_label} “{region.name}” created in “{layout.name}”"
            f"{shared}{tiles}")

    def _on_collision_painted(self):
        """Persiste la collision_map après chaque stroke."""
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        scene.collision_map = self._gba_scene.collision_overlay.get_map()
        from core.command_dispatcher import get_dispatcher

        get_dispatcher().save_scene()

    # ── Chargement projet ─────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._sprite_pixmaps.clear()
        self._raw_sprite.clear()

        scene = project.active_scene

        # Calculer la taille du canvas à partir des BG PNG réels
        max_w, max_h = GBA_W, GBA_H
        for layer in (scene.background_layers if scene else []):
            if not layer.background_name:
                continue
            ba = project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = project.background_images_dir / png
            if ap.exists():
                px = QPixmap(str(ap))
                if not px.isNull():
                    max_w = max(max_w, px.width())
                    max_h = max(max_h, px.height())

        # Clamper au plafond monde (32767, coordonnées s16 de la caméra) — pas à
        # 512 : une carte plus grande est streamée au build, pas interdite.
        self._canvas_w = min(max_w, MAX_CANVAS_W)
        self._canvas_h = min(max_h, MAX_CANVAS_H)
        self._gba_scene.resize_canvas(self._canvas_w, self._canvas_h)
        self._bar.set_canvas_size(self._canvas_w, self._canvas_h)

        # Collision map
        if scene:
            scene.ensure_collision_map(self._canvas_w, self._canvas_h)
            self._gba_scene.collision_overlay.load(scene.collision_map)

        # Backdrop (sous tous les layers)
        self.refresh_backdrop()

        self._setup_cameras(scene)

        # BG layers (sans rescale — taille native)
        shown = set()
        raw_layers: dict[int, QPixmap] = {}
        for layer in (scene.background_layers if scene else []):
            if not layer.background_name:
                continue
            ba = project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = project.background_images_dir / png
            raw_layers[layer.bg_slot] = _bg_pixmap(project, scene, layer, ap)
            shown.add(layer.bg_slot)
        # Pixmaps BRUTS, avant tout mélange : c'est eux que `refresh_blend()`
        # recompose quand on tire sur un réglage. Les garder évite de relire les
        # PNG et de requantifier à chaque cran du curseur — la différence entre
        # un aperçu qui suit la souris et un aperçu qui la subit.
        self._raw_bg = dict(raw_layers)
        self._apply_blend_to_canvas()
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # Windows — APRÈS les layers BG : le masquage s'applique aux items
        # fraîchement créés ci-dessus.
        self._gba_scene.set_windows(getattr(scene, "windows", []) if scene else [])

        # Contexte de peinture par palette + peuplement du bandeau de palettes.
        self._inpainting_ctrl.set_context(project, scene)
        self._ui_region_ctrl.set_context(project, scene)
        self._reload_ui_regions()
        self._canvas_container.refresh_inpaint_banks()

        self._reload_sprites()

    def _apply_blend_to_canvas(self):
        """Recompose les layers depuis les pixmaps BRUTS et les repose.

        Séparé du chargement pour être rappelable seul : c'est ce qui rend
        l'aperçu vivant. Rien ici ne touche le disque — le coût est celui de la
        composition, pas celui de la lecture d'un PNG."""
        scene = self._project.active_scene if self._project else None
        raw = dict(getattr(self, "_raw_bg", {}) or {})
        self._blend_bottom = self._apply_layer_blend(scene, raw)
        for slot, px in raw.items():
            self._gba_scene.set_bg(slot, px)
            layer = next((L for L in (scene.background_layers if scene else [])
                          if L.bg_slot == slot), None)
            self._gba_scene.set_bg_visible(slot, getattr(layer, "visible", True))

    def refresh_blend(self):
        """Rejoue le mélange sur les layers ET les sprites, sans rien relire.

        Appelée quand un réglage de mélange change (effet, pourcentage, rôle
        d'un layer). Les items ne sont pas reconstruits : seuls leurs pixmaps
        changent, donc la sélection, le drag en cours et les poignées survivent
        — ce qui compte quand on tire sur un curseur en regardant le résultat.

        Les windows sont réappliquées après coup : `set_bg` recrée les items de
        layer, et leur masquage vit sur l'item, pas sur la scène."""
        if not self._project or not self._project.active_scene:
            return
        self._apply_blend_to_canvas()
        for item in self._gba_scene._sprite_items:
            raw = self._raw_sprite.get(id(item.scene_sprite))
            if raw is not None:
                item.setPixmap(self._blend_sprite(item.scene_sprite, raw))
        scene = self._project.active_scene
        self._gba_scene.set_windows(getattr(scene, "windows", []))

    def _apply_layer_blend(self, scene, raw_layers: dict) -> Optional[QPixmap]:
        """Remplace SUR PLACE les pixmaps des layers « dessus » par leur version
        mélangée, et rend ce qui se trouve derrière les SPRITES.

        Le dessous d'une couche, c'est la **première couche visible derrière
        elle, quelle qu'elle soit** — pas la première seconde cible. Une couche
        opaque hors du set occulte quand même ce qui est derrière et empêche
        donc le mélange à cet endroit (« le blending ne saute pas une couche »).
        Ne collecter que les secondes cibles faisait traverser le backdrop à
        travers un décor plein, et teintait tout l'écran en permanence.

        L'ordre de priorité GBA suit le numéro de BG : le codegen émet
        `pri = bg` et 0 est DEVANT, donc « derrière BG_n » = les slots de numéro
        SUPÉRIEUR, puis le backdrop.

        Rend None quand la scène ne mélange rien : l'appelant saute alors tout
        le chemin, et le canvas se comporte exactement comme avant."""
        from core.engine_emulation.blend_preview import blend_images, resolve_bottom, scene_blend_plan
        from core.models.scene import BLEND_BOTTOM
        if scene is None:
            return None
        plan = scene_blend_plan(scene)
        if plan is None:
            return None
        w, h = self._canvas_w, self._canvas_h
        bd = self._backdrop_qcolor()
        bd_rgb = (bd.red(), bd.green(), bd.blue())
        bd_target = plan["backdrop_role"] == BLEND_BOTTOM

        source = dict(raw_layers)

        def bottom_of(behind_of: Optional[int]):
            """Ce qui est immédiatement derrière `behind_of`, du plus AVANT au
            plus arrière. `None` = derrière les sprites, qui passent devant
            tous les layers — leur dessous est donc la pile entière."""
            slots = sorted(s for s in source
                           if behind_of is None or s > behind_of)
            entries = [(source[s].toImage(),
                        s in plan["bottom_slots"]) for s in slots]
            return resolve_bottom(entries, w, h, bd_rgb, bd_target)

        for slot in plan["top_slots"]:
            px = raw_layers.get(slot)
            if px is None or px.isNull():
                continue
            raw_layers[slot] = QPixmap.fromImage(blend_images(
                px.toImage(), bottom_of(slot),
                plan["mode"], plan["eva"], plan["evb"], plan["evy"]))
        return bottom_of(None)

    def _blend_sprite(self, actor, px: QPixmap) -> QPixmap:
        """Frame d'un acteur, mélangée si elle est une première cible.

        **Deux portes distinctes**, et c'est la source de confusion la plus
        commune du blending GBA :
          • `Scene.blend_obj_role == "top"` met TOUS les sprites dans la
            première cible, via BLDCNT comme un layer ;
          • `Actor.obj_mode == 1` (semi-transparent) force l'alpha pour CE
            sprite seul, quelles que soient les cibles de BLDCNT — mais il
            emploie quand même EVA/EVB, et il ne fait rien sans seconde cible.
        Un sprite peut donc être mélangé alors qu'aucun layer ne l'est.

        Le « dessous » est le composite des secondes cibles calculé au chargement
        des layers : un sprite est devant tous les layers, il n'y a donc pas de
        sous-ensemble à choisir selon sa position. Le découpage à sa POSITION
        n'est pas fait — le mélange est calculé contre le dessous entier, ce qui
        est exact tant que le dessous est uniforme sous le sprite. Un dessous
        qui varie sous le sprite demanderait de recomposer à chaque déplacement ;
        c'est la limite assumée de l'aperçu, pas du moteur."""
        from core.engine_emulation.blend_preview import blend_images, scene_blend_plan
        from core.models.scene import BLEND_TOP, BLEND_ALPHA
        scene = self._project.active_scene if self._project else None
        plan = scene_blend_plan(scene) if scene else None
        obj_semi = int(getattr(actor, "obj_mode", 0) or 0) == 1
        if plan is None and not obj_semi:
            return px
        if plan is None:
            return px          # obj_mode 1 sans mode de scène : rien à mélanger
        if plan["obj_role"] != BLEND_TOP and not obj_semi:
            return px
        # Un sprite semi-transparent est en ALPHA par construction, même si la
        # scène est réglée sur un fondu : le mode OAM ne lit pas BLDCNT.
        mode = BLEND_ALPHA if obj_semi else plan["mode"]
        return QPixmap.fromImage(blend_images(
            px.toImage(), getattr(self, "_blend_bottom", None),
            mode, plan["eva"], plan["evb"], plan["evy"]))

    def _backdrop_qcolor(self) -> QColor:
        """Couleur du backdrop de la scène, résolue comme le canvas la peint."""
        scene = self._project.active_scene if self._project else None
        raw = getattr(scene, "backdrop_color", None)
        if raw is None and self._project:
            raw = getattr(self._project.settings, "backdrop_color", 0)
        from core.gba_color import bgr555_to_rgb888
        r, g, b = bgr555_to_rgb888(int(raw or 0))
        return QColor(r, g, b)

    def _reload_sprites(self):
        if not self._project:
            return
        # Mémoriser la sélection avant le rebuild (par id, Actor est unhashable)
        prev_selected_ids = {
            id(item.scene_sprite)
            for item in self._gba_scene._sprite_items
            if item.isSelected()
        }
        # Bloquer les signaux AVANT clear pour que selectionChanged ne fire pas
        # pendant le rebuild et ne vide pas l'inspector via get_bus().clear()
        self._gba_scene.blockSignals(True)
        self._gba_scene.clear_sprites()
        p = self._project

        # Résolveur des positions référençant une variable (défaut de la var).
        from core.models.field_value import make_resolver
        _pos_resolver = make_resolver(p)

        scene = p.active_scene
        _placeholder: QPixmap | None = None
        for actor in scene.actors:
            sprite_comp = actor.get_component("sprite")
            sprite = (
                p.get_sprite(sprite_comp.sprite_name)
                if sprite_comp and sprite_comp.sprite_name
                else None
            )
            ap = p.asset_abs(sprite.asset) if sprite and sprite.asset else None
            frame_px = None
            dir_fh = dir_fv = False
            if sprite and ap and ap.exists():
                preview_frame, dir_fh, dir_fv = _preview_frame_for_actor(
                    sprite, sprite_comp, actor)
                if preview_frame is not None:
                    img = compose_frame_image(ap, preview_frame, sprite.frame_w, sprite.frame_h)
                    bank = resolve_obj_palette_bank(p, actor, scene)
                    img = quantize_preview(img, sprite, bank)
                    if img.width > 0 and img.height > 0:
                        data = bytes(img.tobytes("raw", "RGBA"))
                        qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                        frame_px = QPixmap.fromImage(qi)
            is_placeholder = frame_px is None
            if is_placeholder:
                if _placeholder is None:
                    _placeholder = _make_placeholder_pixmap()
                frame_px = _placeholder
            else:
                # La frame BRUTE est gardée à part : `refresh_blend()` rejoue le
                # mélange dessus sans recomposer la frame depuis son PNG. Un
                # placeholder n'y entre pas — il ne représente aucun pixel réel.
                self._raw_sprite[id(actor)] = frame_px
                frame_px = self._blend_sprite(actor, frame_px)
            self._sprite_pixmaps[id(actor)] = frame_px
            save_fn = lambda _s=self: _s.scene_changed.emit()
            ox  = getattr(sprite_comp, "origin_x", 0)   if sprite_comp else 0
            oy  = getattr(sprite_comp, "origin_y", 0)   if sprite_comp else 0
            # Transform affine MONDE (Actor) × LOCAL (SpriteComponent), comme au
            # runtime : le sprite hérite scale (produit) et rotation (somme) de
            # son actor, et se place en offset dans le repère local de l'actor.
            # Sans "Affine transform" sur le SPRITE, aucun slot n'est réservé au
            # build : rien de tout ça ne s'affiche, ni le transform de l'actor ni
            # celui du sprite — le canvas montre donc l'identité (0°/100%), comme
            # la ROM.
            _aff = bool(getattr(sprite_comp, "affine_transform", False)) if sprite_comp else False
            asx = getattr(actor, "scale_x", 1.0)  if _aff else 1.0
            asy = getattr(actor, "scale_y", 1.0)  if _aff else 1.0
            arot = getattr(actor, "rotation", 0)  if _aff else 0
            sx  = (getattr(sprite_comp, "scale_x",  1.0) if _aff else 1.0) * asx
            sy  = (getattr(sprite_comp, "scale_y",  1.0) if _aff else 1.0) * asy
            rot = (getattr(sprite_comp, "rotation", 0.0) if _aff else 0.0) + arot
            off_x = getattr(sprite_comp, "offset_x", 0) if (sprite_comp and _aff) else 0
            off_y = getattr(sprite_comp, "offset_y", 0) if (sprite_comp and _aff) else 0
            # Flip effectif = flip du component XOR flip de la direction miroir
            # (ex. Ouest = miroir horizontal de l'Est).
            fh  = bool(getattr(sprite_comp, "flip_h", False) if sprite_comp else False) ^ dir_fh
            fv  = bool(getattr(sprite_comp, "flip_v", False) if sprite_comp else False) ^ dir_fv
            item = self._gba_scene.add_sprite(
                frame_px, actor, save_fn=save_fn,
                origin_x=ox + off_x, origin_y=oy + off_y, scale_x=sx, scale_y=sy,
                rotation=rot, flip_h=fh, flip_v=fv,
                resolver=_pos_resolver, placeholder=is_placeholder,
            )
            item.scene_sprite = actor

        # Restaurer la sélection, puis débloquer
        for item in self._gba_scene._sprite_items:
            if id(item.scene_sprite) in prev_selected_ids:
                item.setSelected(True)
        self._gba_scene.blockSignals(False)

        if prev_selected_ids:
            self._update_actor_box_overlay()

    # ── Changements items ─────────────────────────────────────────

    def _on_scene_item_changed(self):
        """Appelé quand n'importe quel item de la scène change (position, etc.)."""
        if not self._project or not self._project.active_scene:
            return
        # Si une caméra est sélectionnée, mettre à jour l'inspecteur avec sa
        # nouvelle position — n'importe laquelle des caméras de la scène.
        for item in self._gba_scene.camera_items():
            if item.isSelected():
                x, y = int(item.pos().x()), int(item.pos().y())
                self._write_camera_pos(x, y, item)
                self.camera_position_changed.emit(item.camera, x, y)
                self.scene_changed.emit()

    # ── Sélection ─────────────────────────────────────────────────

    def _on_selection_changed(self):
        """Qt selectionChanged → émettre vers le bus (jamais vers les autres panels)."""
        try:
            selected = self._gba_scene.selectedItems()
        except RuntimeError:
            # La scène Qt sous-jacente a été détruite entre l'émission du
            # signal et le traitement de ce slot (rebuild de la scène en
            # cours) — rien à traiter, elle n'existe déjà plus.
            return
        # L'item ACTIF doit rester membre de la sélection : un rubber band ou
        # une suppression peut l'avoir laissé de côté (règle : à défaut, le
        # premier membre devient actif).
        self._gba_scene.reconcile_active()
        if not selected:
            # Clic dans la zone active du canvas (sceneRect, cf. GBAScene) sans
            # rien toucher → sélection de la SCÈNE elle-même (SceneInspector,
            # comme Actor/Prefab affichent leur propre inspecteur). Ceci est
            # DISTINCT d'un clic sur l'icône caméra (ci-dessous, marqué
            # CameraSelection) : le rectangle de vue 240×160 n'est qu'un retour
            # visuel, il ne doit pas « prendre » le clic ni ouvrir l'inspecteur
            # caméra à la place. Clic en dehors — ou toute autre cause de
            # désélection (Échap, suppression du dernier actor…) où aucune
            # position de clic n'est disponible — → tout désélectionner,
            # l'inspecteur retombe sur son mode par défaut (aperçu du projet).
            pos = self._gba_view._last_click_scene_pos
            in_canvas = pos is not None and self._gba_scene.sceneRect().contains(pos)
            if in_canvas and self._project and self._project.active_scene:
                get_bus().select(self._project.active_scene)
            else:
                get_bus().clear()
            if not self._show_all_boxes:
                self._gba_scene.update_actor_boxes([])
            return
        # Le bus transporte l'item ACTIF (pas « le premier de la liste Qt ») :
        # c'est lui que l'inspecteur détaille. La caméra n'entre pas dans la
        # multi-sélection, elle garde son chemin propre.
        target = self._gba_scene.active_item or selected[0]
        if isinstance(target, CameraItem):
            if self._project and self._project.active_scene:
                # Sélectionner n'est pas régler : on ne matérialise pas la
                # caméra par défaut ici, seulement au premier vrai déplacement.
                get_bus().select(CameraSelection(self._project.active_scene, target.camera))
        elif isinstance(target, SpriteItem):
            get_bus().select(target.scene_sprite)
        elif isinstance(target, UIRegionItem):
            from core.selection_bus import UIRegionSelection
            get_bus().select(UIRegionSelection(target._layout, target._region))
        self._update_actor_box_overlay()

    def _item_for_selection(self, obj):
        """Item canvas correspondant à un objet du bus (Actor / zone de texte),
        ou None. La caméra a son propre chemin (elle n'entre pas dans la
        multi-sélection)."""
        from core.selection_bus import UIRegionSelection
        if isinstance(obj, Actor):
            return self._find_item(obj)
        if isinstance(obj, UIRegionSelection):
            for it in self._gba_scene._ui_region_items:
                if it._region is obj.region:
                    return it
        return None

    def on_selection(self, obj):
        """Reçu du bus — aligner le canvas sans reboucler.

        Si l'objet reçu est DÉJÀ membre de la sélection courante, la sélection
        n'est pas touchée : on se contente de le désigner ACTIF. Sans ce cas,
        n'importe quel aller-retour du bus (clic dans un autre panneau,
        rafraîchissement d'inspecteur, resynchro d'une multi-sélection) ramenait
        la sélection à un seul item."""
        target = self._item_for_selection(obj)
        if target is not None and target.isSelected():
            self._gba_scene.set_active_item(target)
            return

        self._gba_scene.blockSignals(True)
        # Désélectionner tout d'abord
        for item in self._gba_scene.selectedItems():
            item.setSelected(False)
        if isinstance(obj, Actor):
            item = self._find_item(obj)
            if item:
                item.setSelected(True)
                self._gba_view.centerOn(item)
        elif isinstance(obj, CameraSelection):
            # Re-sélectionner l'item caméra pour cet aller-retour bus : sans ce
            # cas, le clic sur l'icône (qui sélectionne nativement la caméra
            # via Qt AVANT même d'émettre CameraSelection sur le bus) se faisait
            # aussitôt désélectionner par la boucle ci-dessus — l'overlay jaune
            # (self._view) clignotait et restait dans un état incohérent avec
            # isSelected(). En NE traitant PAS ce cas ici (tout autre obj), la
            # caméra reste déselectionnée et son overlay disparaît fiablement.
            item = next((it for it in self._gba_scene.camera_items()
                        if it.camera is obj.camera), None)
            if item:
                item.setSelected(True)
        else:
            # Même raison que la caméra : la zone s'annonce sur le bus AVANT que
            # Qt ne la sélectionne (cf. UIRegionItem.mousePressEvent), et le bus
            # est réémis après un drag ou une édition. Sans ce cas, la boucle de
            # désélection ci-dessus effaçait le liseré d'une zone que
            # l'inspecteur montre pourtant comme sélectionnée.
            from core.selection_bus import UIRegionSelection
            if isinstance(obj, UIRegionSelection):
                for it in self._gba_scene._ui_region_items:
                    if it._region is obj.region:
                        it.setSelected(True)
                        break
        self._gba_scene.blockSignals(False)
        # Sélection ramenée à un seul item : c'est lui l'actif (sinon plus
        # aucun — la caméra et la scène « nue » n'en ont pas).
        self._gba_scene.set_active_item(self._item_for_selection(obj))

    def move_actor_item(self, actor: Actor):
        """Repositionne l'item Qt d'un actor sans recréer la scène (drag ou spinbox)."""
        item = self._find_item(actor)
        if item:
            # Bascule de `screen_space` : le repère change, pas seulement la
            # position — sync_sprite_space repositionne aussi.
            self._gba_scene.sync_sprite_space(item)

    def _find_item(self, actor: Actor) -> Optional[SpriteItem]:
        for item in self._gba_scene._sprite_items:
            if item.scene_sprite is actor:
                return item
        return None

    def move_camera_item(self, camera):
        """Repositionne/redimensionne l'item Qt d'une caméra sans recréer la
        scène — appelé quand la position ou le frame ont été édités dans
        l'inspecteur (cf. CameraInspector.camera_moved), symétrique de
        `move_actor_item`."""
        for item in self._gba_scene.camera_items():
            if item.camera is camera:
                item.setPos(camera.x, camera.y)
                item.set_frame_size(camera.frame_w, camera.frame_h)
                return

    # ── Caméras : (re)construction et sauvegarde de position ───────

    def _setup_cameras(self, scene):
        """(Re)construit tous les items caméra de `scene` : celle de
        démarrage (`scene.camera` — porte sprites écran + windows) et les
        autres (rectangles indépendants). Factorisé pour servir à la fois au
        rechargement complet (`load_project`) et au rafraîchissement léger
        après ajout/suppression/renommage depuis le scene tree
        (`refresh_cameras`)."""
        _cam = self._project.scene_camera(scene) if (self._project and scene) else None
        self._gba_scene.setup_camera(_cam.x if _cam else 0, _cam.y if _cam else 0, camera=_cam)
        _others = [c for c in (scene.cameras if scene else []) if c is not _cam]
        self._gba_scene.setup_extra_cameras(_others)

    def refresh_cameras(self):
        """Reconstruit uniquement les items caméra — appelé après
        add_camera/delete_camera/rename_camera (événement
        `cameras_list_changed`), sans recharger tout le reste de la scène."""
        if self._project and self._project.active_scene:
            self._setup_cameras(self._project.active_scene)

    def flush_camera_pos(self):
        """Appelé avant save_scene pour persister le cadrage de TOUTES les
        caméras dont l'item a bougé (démarrage + autres)."""
        if not self._project or not self._project.active_scene:
            return
        for item in self._gba_scene.camera_items():
            x, y = int(item.pos().x()), int(item.pos().y())
            self._write_camera_pos(x, y, item)

    def _write_camera_pos(self, x: int, y: int, item):
        """Écrit le cadrage dans la caméra possédée par la scène active.

        `item.camera is None` désigne l'item de démarrage à l'état implicite :
        déplacer le cadre est un réglage, c'est ici qu'une vraie caméra naît
        (`ensure_scene_camera`) — l'item est alors rebranché sur l'objet réel,
        sinon un second déplacement dans le même geste la matérialiserait à
        chaque fois sans jamais reconnaître qu'elle existe déjà. Ne rien faire
        quand la position est déjà celle du défaut évite d'en créer une au
        premier clic sur le rectangle. Une caméra déjà réelle (démarrage ou
        non) s'écrit directement, sans matérialisation."""
        scene = self._project.active_scene if self._project else None
        if scene is None:
            return
        cam = item.camera
        if cam is None:
            if x == 0 and y == 0:
                return
            cam = self._project.ensure_scene_camera(scene)
            item.camera = cam
        if (cam.x, cam.y) == (x, y):
            return
        cam.x, cam.y = x, y
        self._project.save_scene(scene)

    def _on_prefab_template_dropped(self, prefab_name: str, pos: QPointF):
        if not self._project or not self._project.active_scene:
            return
        x = max(0, min(int(pos.x()), self._canvas_w))
        y = max(0, min(int(pos.y()), self._canvas_h))
        get_dispatcher().instantiate_prefab(prefab_name, x, y)

    def refresh_bg(self, bg_index: int = 0):
        """Recharge tous les BG depuis le BackgroundAsset actif de la scène."""
        if not self._project or not self._project.active_scene:
            return
        scene = self._project.active_scene
        shown = set()
        for layer in scene.background_layers:
            if not layer.background_name:
                continue
            ba = self._project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = self._project.background_images_dir / png
            self._gba_scene.set_bg(layer.bg_slot, _bg_pixmap(self._project, scene, layer, ap))
            self._gba_scene.set_bg_visible(layer.bg_slot, getattr(layer, "visible", True))
            shown.add(layer.bg_slot)
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # Les items BG viennent d'être recréés : réappliquer le découpage des
        # windows, sinon il est perdu à chaque rafraîchissement de fond.
        self._gba_scene.update_window_masks()

        # La banque de base / les layers ont pu changer : resynchroniser le
        # contrôleur de peinture (raster du layer actif) et le bandeau.
        prev_slot = self._inpainting_ctrl.inpaint_layer_slot
        self._inpainting_ctrl.set_context(self._project, scene)
        self._ui_region_ctrl.set_context(self._project, scene)
        self._reload_ui_regions()
        self._inpainting_ctrl.set_inpaint_layer(prev_slot)
        self._canvas_container.refresh_inpaint_banks()

    def set_inpaint_layer(self, bg_slot: int):
        """Choisit le layer BG peint par l'outil de peinture (via l'inspecteur)."""
        self._inpainting_ctrl.set_inpaint_layer(bg_slot)

    def set_layer_visible(self, bg_slot: int, visible: bool):
        """Masque/affiche un layer dans le canvas (visibilité viewport éditeur)."""
        self._gba_scene.set_bg_visible(bg_slot, visible)

    def refresh_windows(self):
        """Redessine l'aperçu des windows (après édition dans l'inspecteur)."""
        scene = self._project.active_scene if self._project else None
        self._gba_scene.set_windows(getattr(scene, "windows", []) if scene else [])

    def refresh_backdrop(self):
        """Réapplique la couleur de backdrop (override de scène, sinon projet)."""
        if not self._project:
            return
        scene = self._project.active_scene
        v = getattr(scene, "backdrop_color", None) if scene else None
        if v is None:
            v = self._project.settings.backdrop_color
        self._gba_scene.set_backdrop(v)

    def update_actor_position(self, actor: Actor):
        item = self._find_item(actor)
        if item:
            item.sync_pos()
