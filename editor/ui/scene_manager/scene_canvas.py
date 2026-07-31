"""
GBA Editor — Scene Canvas
Canvas dynamique (max 512×512) avec caméra 240×160 déplaçable.

Layers (z-order) :
  z=0..3   → BG3..BG0 (PNG composités)
  z=10+n   → sprites placés (draggables)
  z=100    → grille 8px (optionnelle)
  z=150    → rectangle caméra (draggable)
  z=200    → bordure canvas
"""

from typing import Optional

from core.command_dispatcher import get_dispatcher

# Les constantes slope sont aussi importées par canvas_tools — on les garde
# ici uniquement pour CollisionOverlay._slope_path et _draw_tile.
from core.history import MoveActorCmd, get_history
from core.project import (
    COLLISION_TILE_SIZE,
    MIME_PREFAB_TEMPLATE,
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
    Actor,
    Project,
)
from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from ui.common.theme import T, QSS, C
from ui.common.palette_bank_strip import PaletteBankStrip
from ui.common.canvas_top_bar import CanvasTopBar
from core.sprite_compose import compose_frame_image
from core.color_utils import quantize_preview
from codegen.asset_pipeline import resolve_palette_bank, resolve_obj_palette_bank
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

# ── Constantes GBA ───────────────────────────────────────────────
GBA_W = 240
GBA_H = 160
MAX_CANVAS_W = 512  # limite hardware BG tuilé régulier
MAX_CANVAS_H = 512

# Aperçu des windows matérielles — une teinte par région (WIN0, WIN1), reprise
# du bleu de la carte WINDOWS de l'inspecteur de scène.
_WIN_COLORS = ("#82aaff", "#c48b3c")

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
    from core.color_utils import bgr555_to_rgb888
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
            from core.bg_import import _hex_to_tile8
            from core.color_utils import bgr555_to_rgb888
            self._tiles = [_hex_to_tile8(t) for t in compiled["tileset"]]
            pal = compiled["palettes"][0] if compiled["palettes"] else []
            self._pal_rgb = [[bgr555_to_rgb888(c) for c in pal]]
        else:
            from core.bg_import import _hex_to_tile
            self._tiles = [_hex_to_tile(t) for t in compiled["tileset"]]
            self._pal_rgb = [_pal_to_rgb16(pal) for pal in compiled["palettes"]]
        self._bank_rgb_for = bank_rgb_for
        self._qimg = QImage(self.tiles_w * self.TILE, self.tiles_h * self.TILE,
                            QImage.Format.Format_RGBA8888)

    # ── Décodage d'une cellule ────────────────────────────────────
    def _cell_grid(self, cell: int):
        """Grille d'index 8×8 (list[64]) de la cellule, flips appliqués."""
        from core.bg_import import unpack_se, _flip_h, _flip_v
        tid, pb, fh, fv = unpack_se(self._tilemap[cell])
        grid = tuple(self._tiles[tid]) if tid < len(self._tiles) else tuple([0] * 64)
        if fh:
            grid = _flip_h(grid)
        if fv:
            grid = _flip_v(grid)
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
    compiled = compiled_background(ba, ap)
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
        self.setZValue(10)

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
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._drag_origin is not None:
            old_x, old_y = self._drag_origin
            new_x, new_y = self.pos_px()
            if (old_x, old_y) != (new_x, new_y):
                # Pousser la commande SANS re-exécuter (le drag a déjà modifié actor)
                cmd = MoveActorCmd(self.scene_sprite, old_x, old_y, new_x, new_y)
                h = get_history()
                h._undo.append(cmd)  # bypass execute() — déjà fait par le drag
                h._redo.clear()
                h.changed.emit()
                if self._save_fn:
                    self._save_fn()
            self._drag_origin = None
            self._drag_confirmed = False

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
            ring = QColor("#ffffff") if is_active else QColor("#9b8cff")
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
        painter.setPen(QPen(QColor("#e05050"), 1, Qt.PenStyle.SolidLine))
        painter.drawLine(-4, 0, 4, 0)
        painter.drawLine(0, -4, 0, 4)
        painter.setPen(QPen(QColor("#e05050"), 1))
        painter.setBrush(QColor("#e05050"))
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
        self, canvas_w: int, canvas_h: int, cam_x: int = 0, cam_y: int = 0, parent=None
    ):
        super().__init__(parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(150)
        self.setPos(cam_x, cam_y)
        self.setToolTip("Caméra GBA — 240×160 px\nGlisser pour déplacer la vue")

        # Zone de vision — enfant non-interactif
        pen = QPen(QColor("#ffdd44"))
        pen.setWidth(0)
        pen.setCosmetic(True)  # sans ça, seule l'épaisseur du trait ignore le zoom —
                                # le motif de tirets s'étire quand même avec la vue
        pen.setStyle(Qt.PenStyle.DashLine)
        self._view = QGraphicsRectItem(0, 0, GBA_W, GBA_H, self)
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

        for ws in sorted(windows or [], key=lambda w: w.region):
            # Fenêtre-objet (région 2) : pas de rectangle — sa forme vient des
            # pixels opaques des sprites en obj_mode=2, non prévisualisable ici.
            if int(ws.region) not in (0, 1):
                continue
            x0 = max(0, min(int(ws.x), GBA_W))
            y0 = max(0, min(int(ws.y), GBA_H))
            x1 = max(x0, min(int(ws.x) + int(ws.w), GBA_W))
            y1 = max(y0, min(int(ws.y) + int(ws.h), GBA_H))

            color = QColor(_WIN_COLORS[int(ws.region) % len(_WIN_COLORS)])
            pen = QPen(color)
            pen.setWidth(0)
            pen.setCosmetic(True)
            # Trait plein = window active au runtime ; pointillé = authorée mais
            # window_show(region, 0) → invisible sur console.
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
                f"WIN{ws.region} — {x1 - x0}×{y1 - y0} px à ({x0}, {y0})"
                + ("" if ws.visible else "\n(inactive — window_show à 0)")
            )
            self._window_items.append(rect)

        # Le cadre écran sert de contexte à l'aperçu : sans lui, des rectangles
        # flottent sans repère. On le force donc dès qu'une window existe, même
        # caméra non sélectionnée.
        self._view.setVisible(bool(self._window_items) or self.isSelected())

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

        color = "#ffdd44" if self.isSelected() else "#666666"
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
            # Le cadre reste affiché à la désélection s'il sert de contexte à
            # l'aperçu des windows (cf. set_windows).
            self._view.setVisible(bool(value) or bool(self._window_items))
        return super().itemChange(change, value)


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
        ("select", "tool_select", "Sélection  (S)"),
        ("add", "tool_add", "Ajouter actor  (A)"),
        ("erase", "tool_erase", "Gomme  (E)"),
    ]

    # Sous-outils collision — (id, icon_key, label, tooltip)
    _COLLISION_MODES = [
        (
            "collision_8",
            "tool_collision_8",
            "Pinceau 8×8 px",
            "Pinceau de collision  8×8 px",
        ),
        (
            "collision_16",
            "tool_collision_16",
            "Pinceau 16×16 px",
            "Pinceau de collision 16×16 px",
        ),
        (
            "collision_slope",
            "tool_collision_slope",
            "Slope sol",
            "Slope sol (triangle, Bresenham)",
        ),
        (
            "collision_slope_inv",
            "tool_collision_slope_inv",
            "Slope plafond",
            "Slope sol inversé (triangle, Bresenham)",
        ),
    ]

    # Sous-outils inpainting de scène — (id, icon_key, label, tooltip)
    _INPAINT_MODES = [
        ("inpaint_brush", "tool_inpaint_brush", "Pinceau",
         "Inpainting : repeindre la palette d'une tuile (pinceau 8×8)"),
        ("inpaint_rect", "tool_inpaint_rect", "Rectangle",
         "Inpainting : repeindre la palette sur une zone rectangulaire"),
    ]
    _INPAINT_ICON_KEYS = {
        "inpaint_brush": "tool_inpaint_brush",
        "inpaint_rect": "tool_inpaint_rect",
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
        self._btn_inpaint.setToolTip("Inpainting de scène  (B)")
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

        # Zone de texte. Occupe le slot de l'ancien bouton « Palette couleurs »,
        # qui appelait `_set_tool("palette")` — un tool_id qu'aucun cas de
        # `_on_tool_changed` ne reconnaissait, donc un bouton cochable sans
        # effet, et un raccourci P mort avec lui.
        btn_region = QToolButton()
        btn_region.setIcon(_ico("tool_text_region", COLOR_DEFAULT, COLOR_ACTIVE))
        btn_region.setIconSize(QSize(20, 20))
        btn_region.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_region.setToolTip("Zone de texte  (T)")
        btn_region.setCheckable(True)
        btn_region.setFixedSize(34, 34)
        btn_region.clicked.connect(lambda: self._set_tool("ui_region"))
        layout.addWidget(btn_region, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["ui_region"] = btn_region

        layout.addStretch()
        self.adjustSize()

    # ── Collision dropdown ────────────────────────────────────────

    def _on_collision_click(self):
        self._show_collision_menu()

    def _show_collision_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))
        menu.setStyleSheet("""
            QMenu {
                background: #1e1e1e;
                color: #ccc;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item { padding: 5px 14px 5px 8px; border-radius: 3px; icon-size: 20px; }
            QMenu::item:selected { background: #241f3a; color: #9b8cff; }
            QMenu::item:checked  { color: #9b8cff; }
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
        menu.setFont(QFont(T.MONO, T.MD))
        menu.setStyleSheet("""
            QMenu { background:#1e1e1e; color:#ccc; border:1px solid #3a3a3a;
                    border-radius:4px; padding:4px; }
            QMenu::item { padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }
            QMenu::item:selected { background:#241f3a; color:#9b8cff; }
            QMenu::item:checked  { color:#9b8cff; }
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

    # ── Outil actif ───────────────────────────────────────────────

    def _set_tool(self, tool: str):
        self._current_tool = tool
        # Mettre à jour le visuel de tous les boutons
        for tid, btn in self._btns.items():
            is_active = (
                tid == tool
                or (tid == "collision" and tool.startswith("collision"))
                or (tid == "inpaint_btn" and tool.startswith("inpaint"))
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
        from core.project import CollisionBoxComponent
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
class GBAScene(QGraphicsScene):
    sprite_moved = pyqtSignal()
    camera_moved = pyqtSignal(int, int)  # cam_x, cam_y

    def __init__(self, canvas_w: int = GBA_W, canvas_h: int = GBA_H, parent=None):
        super().__init__(0, 0, canvas_w, canvas_h, parent)
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h
        self._bg_items: list[Optional[QGraphicsPixmapItem]] = [None] * 4
        self._sprite_items: list[SpriteItem] = []
        self._grid_item: Optional[GridItem] = None
        self._border: Optional[QGraphicsRectItem] = None
        self._backdrop: Optional[QGraphicsRectItem] = None
        self._camera: Optional[CameraItem] = None
        self._windows: list = []   # WindowSlot de la scène (aperçu + masquage BG)
        self._obj_mask_rects: list = []   # découpe OBJ courante (sprites)
        self._ui_region_items: list = []  # zones de texte (UILayout de la scène)
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

    def update_actor_boxes(self, actors: list, var_defaults: dict | None = None):
        """Met à jour les boîtes de collision acteurs affichées."""
        self._actor_box_overlay.set_actors(actors, var_defaults)

    def set_collision_view(self, visible: bool):
        """Toggle 'Collisions scène' — indépendant de l'outil CollisionTool."""
        self._collision_view = visible
        self._collision_overlay.setVisible(visible)
        self._collision_overlay.update()

    def resize_canvas(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h
        self.setSceneRect(0, 0, w, h)
        if self._border:
            self._border.setRect(0, 0, w, h)
        if self._backdrop:
            self._backdrop.setRect(0, 0, w, h)
        if self._camera:
            self._camera.set_canvas_size(w, h)
        for item in self._sprite_items:
            item.set_canvas_size(w, h)
        if self._grid_item:
            self._grid_item.resize(w, h)

    def set_backdrop(self, bgr555: int):
        """Couleur du backdrop (index 0 de PAL_BG_RAM) — peinte SOUS tous les
        layers (z=-1). C'est ce que le hardware affiche là où rien n'est dessiné :
        une window qui masque tout laisse donc apparaître cette couleur, et le
        canvas le reflète."""
        from core.color_utils import bgr555_to_rgb888
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
        pen = QPen(QColor("#ff6b6b"))
        pen.setWidth(0)
        self._border = QGraphicsRectItem(0, 0, self._canvas_w, self._canvas_h)
        self._border.setPen(pen)
        self._border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._border.setZValue(200)
        self._border.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._border.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.addItem(self._border)

    # ── Caméra ────────────────────────────────────────────────────

    def setup_camera(self, cam_x: int = 0, cam_y: int = 0):
        if self._camera:
            self.removeItem(self._camera)
        self._camera = CameraItem(self._canvas_w, self._canvas_h, cam_x, cam_y)
        self.addItem(self._camera)

    def camera_pos(self) -> tuple[int, int]:
        if self._camera:
            p = self._camera.pos()
            return int(p.x()), int(p.y())
        return 0, 0

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
        active = [ws for ws in self._windows
                  if ws.visible and int(ws.region) in (0, 1)]

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
        z = 3 - bg_index
        if self._bg_items[bg_index]:
            self.removeItem(self._bg_items[bg_index])
            self._bg_items[bg_index] = None
        if pixmap:
            item = _MaskablePixmapItem(pixmap)
            item.setZValue(z)
            item.setOpacity(0.9 if bg_index > 0 else 1.0)
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
        # Sprite créé après le calcul des masques (rechargement de scène) :
        # lui appliquer la découpe courante sans attendre le prochain recalcul.
        if self._obj_mask_rects:
            item.set_mask_rects(self._obj_mask_rects)
        return item

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
            for r in layout_asset.regions:
                item = UIRegionItem(layout_asset, r, project, scene, save_fn=save_fn)
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
        super().mouseReleaseEvent(e)

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
    """Retourne le QPainterPath du triangle de collision pour un tile slope."""
    T = _T
    H = T // 2  # demi-tile = 4 px
    p = QPainterPath()
    # ── Sol (partie inférieure du tile) ──────────────────────────
    if tile_type == TILE_SLOPE_L:
        p.moveTo(x, y + T)
        p.lineTo(x + T, y)
        p.lineTo(x + T, y + T)
    elif tile_type == TILE_SLOPE_R:
        p.moveTo(x, y)
        p.lineTo(x, y + T)
        p.lineTo(x + T, y + T)
    elif tile_type == TILE_SLOPE_L_LO:
        p.moveTo(x, y + T)
        p.lineTo(x + T, y + H)
        p.lineTo(x + T, y + T)
    elif tile_type == TILE_SLOPE_L_HI:
        p.moveTo(x, y + H)
        p.lineTo(x + T, y)
        p.lineTo(x + T, y + T)
        p.lineTo(x, y + T)
    elif tile_type == TILE_SLOPE_R_LO:
        p.moveTo(x, y + H)
        p.lineTo(x + T, y + T)
        p.lineTo(x, y + T)
    elif tile_type == TILE_SLOPE_R_HI:
        p.moveTo(x, y)
        p.lineTo(x + T, y + H)
        p.lineTo(x + T, y + T)
        p.lineTo(x, y + T)
    # ── Plafond (miroir vertical — partie supérieure du tile) ────
    elif tile_type == TILE_SLOPE_L_INV:  # ◣ plafond montant L→R
        p.moveTo(x, y)
        p.lineTo(x + T, y)
        p.lineTo(x, y + T)
    elif tile_type == TILE_SLOPE_R_INV:  # ◢ plafond descendant L→R
        p.moveTo(x, y)
        p.lineTo(x + T, y)
        p.lineTo(x + T, y + T)
    elif (
        tile_type == TILE_SLOPE_L_LO_INV
    ):  # plafond montant, tile gauche (petit triangle haut-droite)
        p.moveTo(x, y)
        p.lineTo(x + T, y + H)
        p.lineTo(x + T, y)
    elif (
        tile_type == TILE_SLOPE_L_HI_INV
    ):  # plafond montant, tile droite (trapèze haut-gauche)
        p.moveTo(x, y)
        p.lineTo(x, y + H)
        p.lineTo(x + T, y + T)
        p.lineTo(x + T, y)
    elif (
        tile_type == TILE_SLOPE_R_HI_INV
    ):  # plafond descendant, tile gauche (trapèze haut-droite)
        p.moveTo(x, y)
        p.lineTo(x, y + T)
        p.lineTo(x + T, y + H)
        p.lineTo(x + T, y)
    elif (
        tile_type == TILE_SLOPE_R_LO_INV
    ):  # plafond descendant, tile droite (petit triangle haut-gauche)
        p.moveTo(x, y)
        p.lineTo(x, y + H)
        p.lineTo(x + T, y)
    # ── Pentes raides sol (>45°, X=1 Y=2) ──────────────────────
    elif tile_type == TILE_SLOPE_R_STEEP_HI:  # tile haut : petit triangle gauche
        p.moveTo(x, y)
        p.lineTo(x + H, y + T)
        p.lineTo(x, y + T)
    elif tile_type == TILE_SLOPE_R_STEEP_LO:  # tile bas  : grand quadrilatère gauche
        p.moveTo(x, y)
        p.lineTo(x + H, y)
        p.lineTo(x + T, y + T)
        p.lineTo(x, y + T)
    elif tile_type == TILE_SLOPE_L_STEEP_HI:  # tile haut : petit triangle droit
        p.moveTo(x + T, y)
        p.lineTo(x + H, y + T)
        p.lineTo(x + T, y + T)
    elif tile_type == TILE_SLOPE_L_STEEP_LO:  # tile bas  : grand quadrilatère droit
        p.moveTo(x + H, y)
        p.lineTo(x + T, y)
        p.lineTo(x + T, y + T)
        p.lineTo(x, y + T)
    # ── Pentes raides plafond (miroir vertical) ──────────────────
    elif (
        tile_type == TILE_SLOPE_R_STEEP_HI_INV
    ):  # tile bas (plafond) : petit triangle gauche haut
        p.moveTo(x, y + T)
        p.lineTo(x + H, y)
        p.lineTo(x, y)
    elif (
        tile_type == TILE_SLOPE_R_STEEP_LO_INV
    ):  # tile haut (plafond) : grand quadrilatère gauche haut
        p.moveTo(x, y)
        p.lineTo(x + T, y)
        p.lineTo(x + H, y + T)
        p.lineTo(x, y + T)
    elif (
        tile_type == TILE_SLOPE_L_STEEP_HI_INV
    ):  # tile bas (plafond) : petit triangle droit haut
        p.moveTo(x + T, y + T)
        p.lineTo(x + H, y)
        p.lineTo(x + T, y)
    elif (
        tile_type == TILE_SLOPE_L_STEEP_LO_INV
    ):  # tile haut (plafond) : grand quadrilatère droit haut
        p.moveTo(x, y)
        p.lineTo(x + T, y)
        p.lineTo(x + T, y + T)
        p.lineTo(x + H, y + T)
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
class UIRegionItem(QGraphicsRectItem):
    """Une zone de texte dessinée dans le canvas — sélectionnable, déplaçable.

    Le rectangle est en coordonnées LOCALES (0,0,w,h) et la position porte x/y :
    sans ça, déplacer l'item ne changerait pas `pos()` et il n'y aurait rien à
    relire au relâchement.

    Le déplacement est validé au RELÂCHEMENT, pas à chaque pixel : pousser une
    commande d'historique par événement de souris remplirait la pile de cent
    entrées pour un seul geste. Même raison que pour le drag d'un actor.

    Une zone ancrée sur un actor est dessinée à l'offset près de son acteur si
    on le trouve — sinon à l'origine de l'écran, avec un liseré discontinu qui
    dit que la position affichée n'est pas celle du jeu."""

    _COLOR = QColor(150, 140, 255)

    def __init__(self, layout_asset, region, project, scene, save_fn=None, parent=None):
        super().__init__(0, 0, max(8, region.w), max(8, region.h), parent)
        self._layout, self._region = layout_asset, region
        self._project, self._scene = project, scene
        self._save = save_fn
        self._press_pos = None

        ox, oy, anchored = self._origin()
        self.setPos(ox, oy)

        pen = QPen(self._COLOR)
        pen.setWidth(0)
        pen.setCosmetic(True)
        if not anchored:
            pen.setStyle(Qt.PenStyle.DotLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(150, 140, 255, 38)))
        self.setZValue(120)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        rm = int(getattr(scene, "render_mode", 0) or 0)
        tx, ty, tw, th = region.tile_rect()
        target = "sprite (OBJ)" if region.resolved_target(rm) == "obj" else "fond (BG)"
        self.setToolTip(f"Zone « {region.name} » — {self._layout.name}\n"
                        f"{tw}×{th} tuiles · cible {target}\n"
                        f"Glisser pour déplacer")

        # Étiquette : le nom est ce que cite le script, il doit être lisible
        # sans passer par l'inspecteur.
        self._label = QGraphicsSimpleTextItem(region.name, self)
        self._label.setBrush(QBrush(self._COLOR))
        fnt = self._label.font()
        fnt.setPointSizeF(5.0)
        self._label.setFont(fnt)
        self._label.setPos(1, 1)
        self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)

    def _origin(self) -> tuple[int, int, bool]:
        """Position à l'écran + « l'ancre a-t-elle été résolue ? »."""
        r = self._region
        if r.anchor != "actor":
            return r.x, r.y, True
        for a in getattr(self._scene, "actors", []):
            if a.name == r.anchor_actor:
                return a.x + r.x, a.y + r.y, True
        return r.x, r.y, False

    # ── Peinture ─────────────────────────────────────────────────
    def paint(self, painter, option, widget=None):
        """Rectangle + liseré de sélection maison : Qt dessine sinon son cadre
        pointillé bleu, qui ne distingue pas MEMBRE d'une multi-sélection et
        item ACTIF (blanc), contrairement aux acteurs."""
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, clean, widget)
        if not self.isSelected():
            return
        sc = self.scene()
        is_active = getattr(sc, "active_item", None) is self
        pen = QPen(QColor("#ffffff") if is_active else self._COLOR, 0)
        pen.setCosmetic(True)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())
        painter.restore()

    # ── Interaction ──────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._press_pos = self.pos()
        from core.selection_bus import get_bus, UIRegionSelection
        get_bus().select(UIRegionSelection(self._layout, self._region))
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._press_pos is None:
            return
        start, self._press_pos = self._press_pos, None
        # Snap tuile pour une cible BG — le moteur y écrit des entrées de
        # tilemap, l'origine ne peut pas tomber entre deux tuiles.
        rm = int(getattr(self._scene, "render_mode", 0) or 0)
        step = 8 if self._region.resolved_target(rm) == "bg" else 1
        nx = int(self.pos().x()) // step * step
        ny = int(self.pos().y()) // step * step
        self.setPos(nx, ny)
        if (nx, ny) == (int(start.x()), int(start.y())):
            return
        # Un ancrage actor stocke un OFFSET : c'est lui qu'il faut réécrire,
        # pas la position absolue lue dans le canvas.
        ax = ay = 0
        if self._region.anchor == "actor":
            for a in getattr(self._scene, "actors", []):
                if a.name == self._region.anchor_actor:
                    ax, ay = a.x, a.y
                    break
        from core.history import get_history, MoveUIRegionCmd
        get_history().push(MoveUIRegionCmd(
            self._region, self._region.x, self._region.y,
            nx - ax, ny - ay, persist_fn=self._save))


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

    def create_region(self, x: int, y: int, w: int, h: int):
        from core.models.ui_region import UIRegion, unique_region_name
        from core.history import get_history, AddListItemCmd
        if not self.ready:
            return None
        lay = self._ensure_layout()
        r = UIRegion(name=unique_region_name(self._project.region_names(), "zone"),
                     x=int(x), y=int(y), w=int(w), h=int(h))
        # Par l'historique : dessiner une zone est une modification comme une
        # autre, elle doit s'annuler. `_ensure_layout` reste hors historique —
        # une mise en page vide et non référencée ne gêne personne, alors qu'un
        # undo qui la retire casserait les zones créées ensuite.
        get_history().push(AddListItemCmd(
            lay.regions, r, persist_fn=self.regions_changed.emit,
            label=f"Ajouter zone {r.name}"))
        self.region_created.emit(lay, r)
        return r


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
class SceneEditor(QWidget):
    scene_changed = pyqtSignal()  # fin de drag / déplacement caméra → sauvegarder

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._sprite_pixmaps: dict[int, QPixmap] = {}
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
        self._bar = CanvasTopBar("Ajuster la scène à la vue  (F)")
        self._bar.zoom_step_asked.connect(self._zoom_step)
        self._bar.fit_asked.connect(self._fit)
        self._bar.set_canvas_size(GBA_W, GBA_H)

        # ── Toggles d'affichage iconifiés (remplacent les cases texte) ──
        self._chk_grid8 = self._bar.add_toggle(
            "view_grid", "Grille 8 px (tuile GBA)", self._on_grid8_toggle)
        self._chk_grid16 = self._bar.add_toggle(
            "view_grid_large", "Grille 16 px", self._on_grid16_toggle)
        self._chk_snap = self._bar.add_toggle(
            "view_snap", "Snap — aligner les acteurs sur la grille au déplacement",
            self._on_snap_toggle)
        self._bar.add_spacing(10)
        self._chk_boxes_actors = self._bar.add_toggle(
            "view_boxes", "Boxes acteurs — boîtes de collision de tous les acteurs",
            self._on_boxes_actors_toggle)
        self._chk_collision_view = self._bar.add_toggle(
            "view_collision", "Collisions scène — carte de collisions peinte",
            self._on_collision_view_toggle)

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

        def mk(seq, slot):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            return sc

        # Bascule d'outil — mêmes lettres que les tooltips de la toolbar
        mk("S", lambda: self._shortcut_tool("select"))
        mk("A", lambda: self._shortcut_tool("add"))
        mk("E", lambda: self._shortcut_tool("erase"))
        mk("C", lambda: self._shortcut_tool("collision"))
        mk("B", lambda: self._shortcut_tool("inpaint"))
        mk("T", lambda: self._shortcut_tool("ui_region"))
        # Vue
        mk("F", self._fit)
        # Sélection / édition
        mk("Escape", self._shortcut_escape)
        mk("Del", self._shortcut_delete)
        mk("Backspace", self._shortcut_delete)
        mk("Ctrl+D", self._shortcut_duplicate)
        # Nudge de la sélection : 1 px, Shift = 8 px (cran de grille)
        for seq, (dx, dy) in {
            "Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1),
            "Shift+Left": (-8, 0), "Shift+Right": (8, 0),
            "Shift+Up": (0, -8), "Shift+Down": (0, 8),
        }.items():
            mk(seq, lambda dx=dx, dy=dy: self._shortcut_nudge(dx, dy))

    def _selected_sprite_items(self) -> list:
        return [it for it in self._gba_scene.selectedItems()
                if isinstance(it, SpriteItem)]

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
        menu.setFont(QFont(T.MONO, T.MD))
        menu.setStyleSheet(QSS.menu)
        act_rename = menu.addAction("Renommer…")
        act_rename.setEnabled(n == 1)
        act_dup = menu.addAction("Dupliquer" if n == 1 else f"Dupliquer ({n})")
        menu.addSeparator()
        act_del = menu.addAction("Supprimer" if n == 1 else f"Supprimer ({n})")
        chosen = menu.exec(global_pos)
        if chosen is act_rename:
            self._rename_actor(actors[0])
        elif chosen is act_dup:
            disp = get_dispatcher()
            for actor in actors:
                disp.duplicate_actor(actor)
        elif chosen is act_del:
            disp = get_dispatcher()
            for actor in actors:
                disp.delete_actor(actor)

    def _rename_actor(self, actor):
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Renommer l'acteur", "Nom :", text=actor.name)
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
        actors = [it.scene_sprite for it in self._selected_sprite_items()]
        if not actors:
            return
        from core.command_dispatcher import get_dispatcher
        disp = get_dispatcher()
        for a in actors:
            disp.delete_actor(a)

    def _shortcut_duplicate(self):
        items = self._selected_sprite_items()
        if not items:
            return
        from core.command_dispatcher import get_dispatcher
        disp = get_dispatcher()
        for it in items:
            disp.duplicate_actor(it.scene_sprite)

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
            case "ui_region":
                from ui.scene_manager.canvas_tools import UIRegionTool

                self._gba_view.set_tool(UIRegionTool(self._gba_view))
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
        shared = f" — partagée par {len(users)} scènes" if len(users) > 1 else ""
        tw, th = region.tile_rect()[2:]
        get_dispatcher().status(
            f"Zone « {region.name} » créée dans « {layout.name} »"
            f"{shared} · {tw}×{th} tuiles")

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

        # Clamper au maximum hardware GBA
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

        # Caméra
        cam_x = scene.cam_x if scene else 0
        cam_y = scene.cam_y if scene else 0
        self._gba_scene.setup_camera(cam_x, cam_y)

        # BG layers (sans rescale — taille native)
        shown = set()
        for layer in (scene.background_layers if scene else []):
            if not layer.background_name:
                continue
            ba = project.get_background(layer.background_name)
            png = ba.asset if ba and ba.asset else f"{layer.background_name}.png"
            ap = project.background_images_dir / png
            self._gba_scene.set_bg(layer.bg_slot, _bg_pixmap(project, scene, layer, ap))
            self._gba_scene.set_bg_visible(layer.bg_slot, getattr(layer, "visible", True))
            shown.add(layer.bg_slot)
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
            self._sprite_pixmaps[id(actor)] = frame_px
            save_fn = lambda _s=self: _s.scene_changed.emit()
            ox  = getattr(sprite_comp, "origin_x", 0)   if sprite_comp else 0
            oy  = getattr(sprite_comp, "origin_y", 0)   if sprite_comp else 0
            sx  = getattr(sprite_comp, "scale_x",  1.0) if sprite_comp else 1.0
            sy  = getattr(sprite_comp, "scale_y",  1.0) if sprite_comp else 1.0
            rot = getattr(sprite_comp, "rotation", 0.0) if sprite_comp else 0.0
            # Flip effectif = flip du component XOR flip de la direction miroir
            # (ex. Ouest = miroir horizontal de l'Est).
            fh  = bool(getattr(sprite_comp, "flip_h", False) if sprite_comp else False) ^ dir_fh
            fv  = bool(getattr(sprite_comp, "flip_v", False) if sprite_comp else False) ^ dir_fv
            item = self._gba_scene.add_sprite(
                frame_px, actor, save_fn=save_fn,
                origin_x=ox, origin_y=oy, scale_x=sx, scale_y=sy,
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
        # Si la caméra est sélectionnée, mettre à jour l'inspecteur avec la nouvelle position
        if self._gba_scene._camera and self._gba_scene._camera.isSelected():
            x, y = self._gba_scene.camera_pos()
            self._project.active_scene.cam_x = x
            self._project.active_scene.cam_y = y
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
                x, y = self._gba_scene.camera_pos()
                self._project.active_scene.cam_x = x
                self._project.active_scene.cam_y = y
                get_bus().select(CameraSelection(self._project.active_scene))
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
            cam = self._gba_scene._camera
            if cam:
                cam.setSelected(True)
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
            item.sync_pos()

    def _find_item(self, actor: Actor) -> Optional[SpriteItem]:
        for item in self._gba_scene._sprite_items:
            if item.scene_sprite is actor:
                return item
        return None

    # ── Sauvegarde position caméra ────────────────────────────────

    def flush_camera_pos(self):
        """Appelé avant save_scene pour persister la position de la caméra."""
        if self._project and self._project.active_scene and self._gba_scene._camera:
            x, y = self._gba_scene.camera_pos()
            self._project.active_scene.cam_x = x
            self._project.active_scene.cam_y = y

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
