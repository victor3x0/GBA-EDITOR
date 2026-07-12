"""
GBA Editor — Scene Editor
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
from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from ui.common.theme import T
from core.sprite_compose import compose_frame_image
from codegen.asset_pipeline import quantize_asset, resolve_palette_bank, resolve_obj_palette_bank
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
    QGraphicsScene,
    QGraphicsTextItem,
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
from core.selection_bus import get_bus

# ── Constantes GBA ───────────────────────────────────────────────
GBA_W = 240
GBA_H = 160
MAX_CANVAS_W = 512  # limite hardware BG tuilé régulier
MAX_CANVAS_H = 512

_PLACEHOLDER_SIZE = 16


def _make_placeholder_pixmap() -> QPixmap:
    """Pixmap 16×16 pour les actors/prefabs sans sprite."""
    from ui.common.icons import get as _ico

    px = QPixmap(_PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.fillRect(0, 0, _PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE, QColor(30, 60, 90, 210))
    pen = QPen(QColor(100, 180, 255, 220), 1)
    p.setPen(pen)
    p.drawRect(0, 0, _PLACEHOLDER_SIZE - 1, _PLACEHOLDER_SIZE - 1)
    icon_px = _ico("actor_empty", "#88ccff").pixmap(QSize(12, 12))
    p.drawPixmap(2, 2, icon_px)
    p.end()
    return px


def _pil_rgba_to_pixmap(img) -> QPixmap:
    """PIL RGBA → QPixmap (fromImage copie les pixels : `data` peut être libéré)."""
    data = bytes(img.tobytes("raw", "RGBA"))
    qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


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
    (`layer.tile_palettes` → slot dans `scene.active_bg_palettes`) : on relit le
    MÊME index de pixel dans une autre banque de 16 couleurs (sémantique
    `SE_PALBANK` du GBA). Réversible — retirer l'override rend la palette
    d'origine. Patche un bloc 8×8 en place pendant la peinture."""

    TILE = 8

    def __init__(self, compiled: dict, bank_rgb_for):
        # compiled     : {tiles_w, tiles_h, tileset(list[hex]), tilemap(list[SE]),
        #                 palettes(list[list[int]] BGR555)} — palettes d'origine.
        # bank_rgb_for : callable(slot:int) -> list[(r,g,b)] (16) | None, banque
        #                active de la scène pour un override.
        from core.bg_compress import _hex_to_tile
        self.tiles_w = compiled["tiles_w"]
        self.tiles_h = compiled["tiles_h"]
        self._tiles = [_hex_to_tile(t) for t in compiled["tileset"]]
        self._tilemap = list(compiled["tilemap"])
        self._pal_rgb = [_pal_to_rgb16(pal) for pal in compiled["palettes"]]
        self._bank_rgb_for = bank_rgb_for
        self._qimg = QImage(self.tiles_w * self.TILE, self.tiles_h * self.TILE,
                            QImage.Format.Format_RGBA8888)

    # ── Décodage d'une cellule ────────────────────────────────────
    def _cell_grid(self, cell: int):
        """Grille d'index 8×8 (list[64]) de la cellule, flips appliqués."""
        from core.bg_compress import unpack_se, _flip_h, _flip_v
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
                if idx == 0:
                    continue
                r, g, b = pal_rgb[idx]
                px[x, y] = (r, g, b, 255)
        return blk

    def _pal_for(self, cell: int, slot):
        """Palette RGB à utiliser pour une cellule : override de scène si `slot`
        résolu, sinon la palette d'origine de la tuile."""
        if slot is not None:
            bank = self._bank_rgb_for(slot)
            if bank:
                return bank
        _, pb = self._cell_grid(cell)
        return self._pal_rgb[pb] if pb < len(self._pal_rgb) else self._pal_rgb[0]

    # ── Composition ───────────────────────────────────────────────
    def render(self, tile_palettes: dict):
        """Recompose tout le layer : palettes d'origine + overrides de scène."""
        from PIL import Image
        out = Image.new("RGBA", (self.tiles_w * self.TILE, self.tiles_h * self.TILE),
                        (0, 0, 0, 0))
        for cell in range(len(self._tilemap)):
            col, row = cell % self.tiles_w, cell // self.tiles_w
            slot = tile_palettes.get((col, row))
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


def _asset_compiled(p: Project, ba, ap) -> Optional[dict]:
    """Représentation compressée (palette d'origine) d'un layer : depuis le
    sidecar `ba` si compressé, sinon compressée à la volée depuis le PNG
    (fallback legacy rare). None si indisponible."""
    if ba and ba.tileset:
        return {"tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
                "tileset": ba.tileset, "tilemap": ba.tilemap,
                "palettes": ba.palettes}
    if ap and ap.is_file():
        from core.bg_compress import compress_background
        try:
            return compress_background(ap)
        except (ValueError, OSError):
            return None
    return None


def build_bg_raster(p: Project, scene, layer, ap) -> Optional["BgLayerRaster"]:
    """Construit le `BgLayerRaster` d'un layer depuis sa palette d'origine
    (représentation compressée de l'asset). Peignable pour TOUT layer ayant une
    image — indépendant de `layer.pal_bank` (plus de banque de base requise :
    c'est ça qui rend les layers « Sans palette » peignables). None si pas
    d'image/asset exploitable."""
    if not layer.image or not ap.is_file():
        return None
    ba = p.get_background(layer.image)
    compiled = _asset_compiled(p, ba, ap)
    if not compiled or not compiled.get("tilemap"):
        return None

    def _bank_rgb_for(slot: int):
        b = resolve_palette_bank(p, scene.active_bg_palettes, slot)
        return _pal_to_rgb16(b.colors) if b and b.colors else None

    raster = BgLayerRaster(compiled, _bank_rgb_for)
    raster.render(getattr(layer, "tile_palettes", {}) or {})
    return raster


def _bg_pixmap(p: Project, scene, layer, ap) -> Optional[QPixmap]:
    """Pixmap d'un layer BG pour le canvas — rendu PAR TUILE depuis la palette
    d'origine de l'asset + overrides de scène peints (`layer.tile_palettes`).
    Repli sur le PNG brut si l'asset n'a pas de représentation exploitable."""
    # layer.image vide -> `ap` pointe sur le DOSSIER background_images_dir
    # (pas un fichier) : ne rien afficher (l'ancien QPixmap(dir) échouait
    # silencieusement, mais Image.open(dir) lève PermissionError).
    if not layer.image or not ap.is_file():
        return None
    raster = build_bg_raster(p, scene, layer, ap)
    if raster is not None:
        return raster.to_pixmap()
    return QPixmap(str(ap))


def _quantize_preview(img, sprite, bank):
    """Aperçu acteur du canvas de scène, aligné sur le build INDEXÉ universel :
    l'image composée est rendue via la own_palette du sprite (compression
    stockée), puis ses index sont recolorés par la banque référencée
    (index i -> banque[i]) ou laissés en couleurs propres (OWN). WYSIWYG avec
    le build réel. Plus de match_mode."""
    from core.color_utils import render_indexed, recolor_indexed
    own_pal = list(getattr(sprite, "own_palette", []) or [])
    if not own_pal:
        return img
    p_img = render_indexed(img, own_pal)
    if bank and bank.colors:
        return recolor_indexed(p_img, bank.colors)
    return p_img.convert("RGBA")


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
        parent=None,
    ):
        super().__init__(pixmap, parent)
        self.scene_sprite = actor
        self.snap = snap
        # Initialisés avant setPos()/setFlags() plus bas : itemChange() peut être
        # appelé dès la construction (ItemSendsGeometryChanges) et les lit.
        self._drag_origin: tuple[int, int] | None = None
        self._drag_confirmed = False
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
        self.setPos(actor.x, actor.y)

    def set_canvas_size(self, w: int, h: int):
        self._canvas_w = w
        self._canvas_h = h

    # En-deçà de ce déplacement (px), on considère qu'il s'agit d'un simple
    # clic (jitter sous-pixel entre press/release) et pas d'un vrai drag —
    # sans ce garde-fou, itemChange() snappait la position au premier micro-
    # mouvement, faisant "sauter" l'acteur au clic (cf bug rapporté).
    _CLICK_THRESHOLD = 2

    def mousePressEvent(self, e):
        # Capturer la position avant le début du drag
        self._drag_origin = (self.scene_sprite.x, self.scene_sprite.y)
        self._drag_confirmed = False
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._drag_origin is not None:
            old_x, old_y = self._drag_origin
            new_x, new_y = self.scene_sprite.x, self.scene_sprite.y
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
        return float(self.scene_sprite.x), float(self.scene_sprite.y)

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

    def paint(self, painter, option, widget=None):
        # Supprimer le rendu de sélection Qt par défaut (dashed bleu)
        clean = QStyleOptionGraphicsItem(option)
        clean.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, clean, widget)
        # Outline vert propre quand sélectionné
        if self.isSelected():
            painter.save()
            painter.setPen(QPen(QColor("#4caf78"), 1, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self.boundingRect().adjusted(0, 0, -1, -1)
            painter.drawRect(r)
            # Petits coins pour renforcer la visibilité
            cs = 4
            painter.setPen(QPen(QColor("#4caf78"), 2))
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

        # Icône qtawesome — deux états (normal / sélectionné)
        from ui.common.icons import get as _ico

        sz = QSize(_CAM_ICO_SIZE, _CAM_ICO_SIZE)
        self._px_normal = _ico("camera", "#666666").pixmap(sz)
        self._px_selected = _ico("camera", "#ffdd44").pixmap(sz)

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
        # Icône UI (pas du pixel art de jeu) : lissée localement, sans affecter
        # le rendu nearest-neighbor des sprites/backgrounds ailleurs sur le canvas.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        px = self._px_selected if self.isSelected() else self._px_normal
        painter.drawPixmap(0, 0, px)

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
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # prepareGeometryChange() notifie Qt que la zone de dessin
            # effective change (icon seul → icon + viewport 240×160).
            self.prepareGeometryChange()
            self._view.setVisible(bool(value))
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
    _COLLISION_ICON_KEYS = {
        "collision_8": "tool_collision_8",
        "collision_16": "tool_collision_16",
        "collision_slope": "tool_collision_slope",
        "collision_slope_inv": "tool_collision_slope_inv",
    }

    # Sous-outils peinture palette BG — (id, icon_key, label, tooltip)
    _BG_PAINT_MODES = [
        ("bg_paint", "tool_bg_paint", "Pinceau palette",
         "Peindre la palette d'une tuile (pinceau 8×8)"),
        ("bg_rect", "tool_bg_rect", "Rectangle palette",
         "Peindre la palette sur une zone rectangulaire"),
    ]
    _BG_PAINT_ICON_KEYS = {
        "bg_paint": "tool_bg_paint",
        "bg_rect": "tool_bg_rect",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._dragging = False
        self._drag_offset = QPoint()
        self._current_tool = "select"
        self._current_collision = "collision_8"
        self._current_bg_paint = "bg_paint"

        self.setFixedWidth(46)
        self.setStyleSheet("""
            FloatingToolbar {
                background: #1c1c1c;
                border: 1px solid #333;
                border-radius: 8px;
            }
            QToolButton {
                border: none;
                background: transparent;
                border-radius: 5px;
            }
            QToolButton:hover   { background: #2a2a2a; }
            QToolButton:checked {
                background: #253525;
                border: 1px solid #3a6a3a;
            }
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
        self._btn_collision.setIcon(
            _ico(
                self._COLLISION_ICON_KEYS[self._current_collision],
                COLOR_DEFAULT,
                COLOR_ACTIVE,
            )
        )
        self._btn_collision.setIconSize(QSize(24, 24))
        self._btn_collision.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_collision.setToolTip("Édition de collisions  (C)")
        self._btn_collision.setCheckable(True)
        self._btn_collision.setFixedSize(36, 36)
        self._btn_collision.clicked.connect(self._on_collision_click)
        layout.addWidget(self._btn_collision, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["collision"] = self._btn_collision

        # ── Bouton peinture palette BG avec dropdown ──────────────
        self._btn_bg_paint = QToolButton()
        self._btn_bg_paint.setIcon(
            _ico(self._BG_PAINT_ICON_KEYS[self._current_bg_paint],
                 COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._btn_bg_paint.setIconSize(QSize(24, 24))
        self._btn_bg_paint.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_bg_paint.setToolTip("Peinture par palette BG  (B)")
        self._btn_bg_paint.setCheckable(True)
        self._btn_bg_paint.setFixedSize(36, 36)
        self._btn_bg_paint.clicked.connect(self._on_bg_paint_click)
        layout.addWidget(self._btn_bg_paint, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["bg_paint_btn"] = self._btn_bg_paint

        # ── Séparateur + outil palette ────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#2a2a2a; margin:3px 0;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        btn_pal = QToolButton()
        btn_pal.setIcon(_ico("tool_palette", COLOR_DEFAULT, COLOR_ACTIVE))
        btn_pal.setIconSize(QSize(20, 20))
        btn_pal.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn_pal.setToolTip("Palette couleurs  (P)")
        btn_pal.setCheckable(True)
        btn_pal.setFixedSize(34, 34)
        btn_pal.clicked.connect(lambda: self._set_tool("palette"))
        layout.addWidget(btn_pal, 0, Qt.AlignmentFlag.AlignHCenter)
        self._btns["palette"] = btn_pal

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
            QMenu::item:selected { background: #253525; color: #4caf78; }
            QMenu::item:checked  { color: #4caf78; }
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
        self._current_collision = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_collision.setIcon(
            _ico(self._COLLISION_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
        )
        self._set_tool(mode)

    # ── Peinture palette BG dropdown ──────────────────────────────

    def _on_bg_paint_click(self):
        self._show_bg_paint_menu()

    def _show_bg_paint_menu(self):
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setFont(QFont(T.MONO, T.MD))
        menu.setStyleSheet("""
            QMenu { background:#1e1e1e; color:#ccc; border:1px solid #3a3a3a;
                    border-radius:4px; padding:4px; }
            QMenu::item { padding:5px 14px 5px 8px; border-radius:3px; icon-size:20px; }
            QMenu::item:selected { background:#253525; color:#4caf78; }
            QMenu::item:checked  { color:#4caf78; }
        """)
        from ui.common.icons import COLOR_DEFAULT
        from ui.common.icons import get as _ico

        for mode_id, icon_key, label, tip in self._BG_PAINT_MODES:
            act = QAction(label, self)
            act.setIcon(_ico(icon_key, COLOR_DEFAULT))
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(self._current_bg_paint == mode_id)
            act.triggered.connect(lambda _, m=mode_id: self._select_bg_paint_mode(m))
            menu.addAction(act)

        btn_pos = self._btn_bg_paint.mapToGlobal(
            QPoint(self._btn_bg_paint.width() + 4, 0)
        )
        menu.exec(btn_pos)

    def _select_bg_paint_mode(self, mode: str):
        self._current_bg_paint = mode
        from ui.common.icons import COLOR_ACTIVE, COLOR_DEFAULT
        from ui.common.icons import get as _ico

        self._btn_bg_paint.setIcon(
            _ico(self._BG_PAINT_ICON_KEYS[mode], COLOR_DEFAULT, COLOR_ACTIVE)
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
                or (tid == "bg_paint_btn" and tool.startswith("bg_"))
            )
            btn.setChecked(is_active)
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._current_tool

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
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(160)
        self.setVisible(False)

    def set_actors(self, actors: list):
        self._actors = list(actors)
        self.setVisible(bool(self._actors))
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._canvas_w, self._canvas_h)

    def paint(self, painter: QPainter, option, widget=None):
        from core.project import CollisionBoxComponent

        pen_s = QPen(self._B_SOLID, 0)
        pen_t = QPen(self._B_TRIGGER, 0)
        for actor in self._actors:
            for comp in actor.components:
                if not isinstance(comp, CollisionBoxComponent) or not comp.active:
                    continue
                x = actor.x + comp.x
                y = actor.y + comp.y
                if comp.solid:
                    painter.fillRect(x, y, comp.w, comp.h, self._C_SOLID)
                    painter.setPen(pen_s)
                else:
                    painter.fillRect(x, y, comp.w, comp.h, self._C_TRIGGER)
                    painter.setPen(pen_t)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x, y, comp.w, comp.h)


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
        self._camera: Optional[CameraItem] = None
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

    def update_actor_boxes(self, actors: list):
        """Met à jour les boîtes de collision acteurs affichées."""
        self._actor_box_overlay.set_actors(actors)

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
        if self._camera:
            self._camera.set_canvas_size(w, h)
        for item in self._sprite_items:
            item.set_canvas_size(w, h)
        if self._grid_item:
            self._grid_item.resize(w, h)

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

    # ── BG layers ─────────────────────────────────────────────────

    def set_bg(self, bg_index: int, pixmap: Optional[QPixmap]):
        z = 3 - bg_index
        if self._bg_items[bg_index]:
            self.removeItem(self._bg_items[bg_index])
            self._bg_items[bg_index] = None
        if pixmap:
            item = QGraphicsPixmapItem(pixmap)
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
    ) -> SpriteItem:
        item = SpriteItem(
            pixmap, actor,
            self._canvas_w, self._canvas_h,
            snap=self._snap, save_fn=save_fn,
            origin_x=origin_x, origin_y=origin_y,
            scale_x=scale_x, scale_y=scale_y,
            rotation=rotation, flip_h=flip_h, flip_v=flip_v,
        )
        self.addItem(item)
        self._sprite_items.append(item)
        return item

    def clear_sprites(self):
        for item in self._sprite_items:
            self.removeItem(item)
        self._sprite_items.clear()

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

    def __init__(self, scene: GBAScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#111111"))
        self._zoom = 2.0
        self._apply_zoom()
        self.setAcceptDrops(True)
        # Outil actif — initialisé après import (évite la circularité)
        self._active_tool: "BaseTool | None" = None
        # Snap preview — 16×16, visible uniquement si snap actif
        self._snap_on = False
        self._snap_preview: "QGraphicsRectItem | None" = None
        # Contrôleur de peinture par palette BG (injecté par SceneEditor).
        self.bg_paint_controller: "Optional[BgPaintController]" = None

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
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_press(pos, e):
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
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
        if (
            _btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)
            and self._active_tool
        ):
            pos = self.mapToScene(e.position().toPoint())
            if self._active_tool.on_release(pos, e):
                e.accept()
                return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        """Empêche le menu contextuel du clic-droit — celui-ci est utilisé pour peindre."""
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
    ba = project.get_background(layer.image)
    png = ba.source if ba and ba.source else f"{layer.image}.png"
    return project.background_images_dir / png


# ──────────────────────────────────────────────────────────────────
#  Contrôleur de peinture par palette BG (SE_PALBANK par tuile)
# ──────────────────────────────────────────────────────────────────
class BgPaintController:
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

    def set_active_layer(self, bg_slot: Optional[int]):
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

    def set_active_bank(self, slot: Optional[int]):
        self._bank = slot

    def active_banks(self) -> list:
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
    def active_layer_slot(self) -> Optional[int]:
        return self._layer.bg_slot if self._layer is not None else None

    @property
    def active_bank(self) -> Optional[int]:
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

    def paint_tile(self, col: int, row: int, erase: bool = False):
        """Peint (ou efface) l'override d'une tuile ; met à jour le canvas en
        direct. Enregistre l'ancienne valeur dans le stroke courant."""
        if not self.ready or self._layer is None:
            return
        if not (0 <= col < self._raster.tiles_w and 0 <= row < self._raster.tiles_h):
            return
        key = (col, row)
        new = None if erase else self._bank
        old = self._layer.tile_palettes.get(key)
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
            self._layer.tile_palettes.pop(key, None)
        else:
            self._layer.tile_palettes[key] = slot
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
        from core.history import BgPaintCmd, get_history
        cmd = BgPaintCmd(self, self._layer, self._layer.bg_slot, dict(delta))
        h = get_history()
        h._undo.append(cmd)
        h._redo.clear()
        h.changed.emit()
        self._persist()

    # ── Undo/redo (appelé par BgPaintCmd) ────────────────────────
    def apply_layer_delta(self, layer, bg_slot: int, delta: dict, forward: bool):
        """Réapplique un delta sur un layer (forward=redo, sinon undo), rebâtit
        le pixmap de ce layer, et persiste. Robuste même si ce n'est plus le
        layer actif."""
        for key, (old, new) in delta.items():
            slot = new if forward else old
            if slot is None:
                layer.tile_palettes.pop(key, None)
            else:
                layer.tile_palettes[key] = slot
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
#  Bandeau flottant de sélection de la banque de peinture
# ──────────────────────────────────────────────────────────────────
class BgPaletteStrip(QFrame):
    """Bandeau flottant : pastilles des banques BG actives de la scène. Clic →
    banque de peinture active du BgPaintController. Visible seulement quand un
    outil de peinture BG est actif."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctrl: Optional[BgPaintController] = None
        self._btns: dict[int, QToolButton] = {}
        self.setStyleSheet("""
            BgPaletteStrip { background:#1c1c1c; border:1px solid #333;
                             border-radius:8px; }
            QToolButton { border:1px solid #2a2a2a; background:transparent;
                          border-radius:4px; padding:1px; }
            QToolButton:hover   { border-color:#4a4a4a; }
            QToolButton:checked { border:2px solid #4caf78; }
        """)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 5, 6, 5)
        self._layout.setSpacing(4)
        self._hint = QLabel("Aucune banque BG active")
        self._hint.setFont(QFont(T.MONO, T.SM))
        self._hint.setStyleSheet("color:#666;background:transparent;")
        self._layout.addWidget(self._hint)
        self.setVisible(False)

    def bind(self, ctrl: "BgPaintController"):
        self._ctrl = ctrl

    def refresh(self):
        # Vider
        for b in self._btns.values():
            b.setParent(None)
            b.deleteLater()
        self._btns.clear()
        banks = self._ctrl.active_banks() if self._ctrl else []
        self._hint.setVisible(not banks)
        from ui.common.palette_swatch import bank_icon
        active = self._ctrl.active_bank if self._ctrl else None
        for slot, bank in banks:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setIcon(bank_icon(bank, 22))
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(30, 30)
            btn.setToolTip(f"Banque {slot} — {bank.name}")
            btn.setChecked(slot == active)
            btn.clicked.connect(lambda _, s=slot: self._select(s))
            self._layout.addWidget(btn)
            self._btns[slot] = btn
        # Aucune banque active choisie encore → prendre la 1re dispo.
        if banks and (active is None or active not in self._btns):
            self._select(banks[0][0])
        self.adjustSize()

    def _select(self, slot: int):
        if self._ctrl:
            self._ctrl.set_active_bank(slot)
        for s, b in self._btns.items():
            b.setChecked(s == slot)


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

        # Bandeau flottant de sélection de la banque de peinture (bas-centre).
        self._bg_palette_strip = BgPaletteStrip(self)
        self._bg_palette_strip.raise_()

    def bind_bg_paint(self, ctrl: "BgPaintController"):
        self._bg_palette_strip.bind(ctrl)

    def refresh_bg_palette(self):
        self._bg_palette_strip.refresh()
        self._position_bg_strip()

    def set_bg_palette_visible(self, visible: bool):
        if visible:
            self._bg_palette_strip.refresh()
            self._position_bg_strip()
        self._bg_palette_strip.setVisible(visible)
        self._bg_palette_strip.raise_()

    def _position_bg_strip(self):
        strip = self._bg_palette_strip
        strip.adjustSize()
        x = max(0, (self.width() - strip.width()) // 2)
        y = max(0, self.height() - strip.height() - 12)
        strip.move(x, y)

    def _on_tool_changed(self, tool: str):
        self.tool_changed.emit(tool)

    @property
    def current_tool(self) -> str:
        return self._toolbar.current_tool

    def resizeEvent(self, e):
        super().resizeEvent(e)
        tb = self._toolbar
        x = max(0, min(tb.x(), self.width() - tb.width()))
        y = max(0, min(tb.y(), self.height() - tb.height()))
        tb.move(x, y)
        tb.raise_()
        if self._bg_palette_strip.isVisible():
            self._position_bg_strip()
            self._bg_palette_strip.raise_()


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
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar haut ──────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("background:#1e1e1e; border-bottom:1px solid #2a2a2a;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 0, 8, 0)
        tb_layout.setSpacing(12)
        font = QFont(T.MONO, T.MD)

        lbl_zoom = QLabel("Zoom :")
        lbl_zoom.setFont(font)
        lbl_zoom.setStyleSheet("color:#888;")
        tb_layout.addWidget(lbl_zoom)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setFixedSize(24, 24)
        self._btn_zoom_out.setFont(font)
        self._btn_zoom_out.clicked.connect(lambda: self._zoom_step(-1))
        tb_layout.addWidget(self._btn_zoom_out)

        self._zoom_label = QLabel("×2")
        self._zoom_label.setFont(font)
        self._zoom_label.setStyleSheet("color:#ccc;")
        self._zoom_label.setFixedWidth(36)
        tb_layout.addWidget(self._zoom_label)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedSize(24, 24)
        self._btn_zoom_in.setFont(font)
        self._btn_zoom_in.clicked.connect(lambda: self._zoom_step(+1))
        tb_layout.addWidget(self._btn_zoom_in)

        self._btn_fit = QPushButton("Fit")
        self._btn_fit.setFixedWidth(36)
        self._btn_fit.setFont(font)
        self._btn_fit.clicked.connect(self._fit)
        tb_layout.addWidget(self._btn_fit)

        tb_layout.addSpacing(16)

        self._chk_grid8 = QCheckBox("Grille 8px")
        self._chk_grid8.setFont(font)
        self._chk_grid8.setStyleSheet("color:#aaa;")
        self._chk_grid8.toggled.connect(self._on_grid8_toggle)
        tb_layout.addWidget(self._chk_grid8)

        self._chk_grid16 = QCheckBox("16px")
        self._chk_grid16.setFont(font)
        self._chk_grid16.setStyleSheet("color:#aaa;")
        self._chk_grid16.toggled.connect(self._on_grid16_toggle)
        tb_layout.addWidget(self._chk_grid16)

        self._chk_snap = QCheckBox("Snap")
        self._chk_snap.setFont(font)
        self._chk_snap.setStyleSheet("color:#aaa;")
        self._chk_snap.toggled.connect(self._on_snap_toggle)
        tb_layout.addWidget(self._chk_snap)

        tb_layout.addSpacing(16)

        self._chk_boxes_actors = QCheckBox("Boxes acteurs")
        self._chk_boxes_actors.setFont(font)
        self._chk_boxes_actors.setStyleSheet("color:#aaa;")
        self._chk_boxes_actors.toggled.connect(self._on_boxes_actors_toggle)
        tb_layout.addWidget(self._chk_boxes_actors)

        self._chk_collision_view = QCheckBox("Collisions scène")
        self._chk_collision_view.setFont(font)
        self._chk_collision_view.setStyleSheet("color:#aaa;")
        self._chk_collision_view.toggled.connect(self._on_collision_view_toggle)
        tb_layout.addWidget(self._chk_collision_view)

        tb_layout.addStretch()

        # Label taille canvas
        self._canvas_size_label = QLabel(f"{GBA_W}×{GBA_H}")
        self._canvas_size_label.setFont(font)
        self._canvas_size_label.setStyleSheet("color:#555;")
        tb_layout.addWidget(self._canvas_size_label)

        tb_layout.addSpacing(8)

        self._coord_label = QLabel("x:— y:—")
        self._coord_label.setFont(font)
        self._coord_label.setStyleSheet("color:#555;")
        tb_layout.addWidget(self._coord_label)

        layout.addWidget(toolbar)

        # ── Canvas ────────────────────────────────────────────────
        self._gba_scene = GBAScene()
        self._gba_view = GBAView(self._gba_scene)
        self._gba_view.setMouseTracking(True)
        self._gba_scene.selectionChanged.connect(self._on_selection_changed)
        self._gba_scene.changed.connect(self._on_scene_item_changed)
        self._gba_view.prefab_template_dropped.connect(self._on_prefab_template_dropped)
        get_bus().changed.connect(self.on_selection)

        self._canvas_container = CanvasContainer(self._gba_view)
        layout.addWidget(self._canvas_container, 1)

        self._gba_view.viewport().setMouseTracking(True)
        self._gba_view.viewport().installEventFilter(self)

        # Outil par défaut
        from core.canvas_tools import SelectTool

        self._gba_view.set_tool(SelectTool(self._gba_view))

        self._canvas_container.tool_changed.connect(self._on_tool_changed)
        self._gba_view.collision_painted.connect(self._on_collision_painted)

        # Contrôleur de peinture par palette BG + bandeau de palette flottant.
        self._bg_paint_ctrl = BgPaintController(self._gba_scene)
        self._gba_view.bg_paint_controller = self._bg_paint_ctrl
        self._canvas_container.bind_bg_paint(self._bg_paint_ctrl)

    # ── Événements ────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj == self._gba_view.viewport() and event.type() == QEvent.Type.MouseMove:
            pos = self._gba_view.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())
            if 0 <= x < self._canvas_w and 0 <= y < self._canvas_h:
                self._coord_label.setText(f"x:{x} y:{y}")
                self._coord_label.setStyleSheet("color:#aaa;")
            else:
                self._coord_label.setText("x:— y:—")
                self._coord_label.setStyleSheet("color:#555;")
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

    def _fit(self):
        self._gba_view.fit(self._canvas_w, self._canvas_h)
        self._update_zoom_label()

    def _update_zoom_label(self):
        z = self._gba_view._zoom
        self._zoom_label.setText(
            f"×{z:.1f}".rstrip("0").rstrip(".") if z != int(z) else f"×{int(z)}"
        )

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
        if self._show_all_boxes:
            self._gba_scene.update_actor_boxes(self._project.active_scene.actors)
        else:
            actors = [
                item.scene_sprite
                for item in self._gba_scene._sprite_items
                if item.isSelected()
            ]
            self._gba_scene.update_actor_boxes(actors)

    # ── Outil actif ───────────────────────────────────────────────

    def _on_tool_changed(self, tool_id: str):
        from core.canvas_tools import AddActorTool, CollisionTool, EraseTool, SelectTool

        match tool_id:
            case t if t.startswith("collision"):
                from core.canvas_tools import CollisionTool

                self._gba_view.set_tool(CollisionTool(self._gba_view, t))
            case t if t.startswith("bg_"):
                from core.canvas_tools import BgPaintTool

                self._gba_view.set_tool(BgPaintTool(self._gba_view, t))
            case "add":
                self._gba_view.set_tool(AddActorTool(self._gba_view))
            case "erase":
                self._gba_view.set_tool(EraseTool(self._gba_view))
            case _:
                self._gba_view.set_tool(SelectTool(self._gba_view))
        # Bandeau de palette visible seulement pour les outils de peinture BG.
        self._canvas_container.set_bg_palette_visible(tool_id.startswith("bg_"))

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
            if not layer.image:
                continue
            ba = project.get_background(layer.image)
            png = ba.source if ba and ba.source else f"{layer.image}.png"
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
        self._canvas_size_label.setText(f"{self._canvas_w}×{self._canvas_h}")

        # Collision map
        if scene:
            scene.ensure_collision_map(self._canvas_w, self._canvas_h)
            self._gba_scene.collision_overlay.load(scene.collision_map)

        # Caméra
        cam_x = scene.cam_x if scene else 0
        cam_y = scene.cam_y if scene else 0
        self._gba_scene.setup_camera(cam_x, cam_y)

        # BG layers (sans rescale — taille native)
        shown = set()
        for layer in (scene.background_layers if scene else []):
            if not layer.image:
                continue
            ba = project.get_background(layer.image)
            png = ba.source if ba and ba.source else f"{layer.image}.png"
            ap = project.background_images_dir / png
            self._gba_scene.set_bg(layer.bg_slot, _bg_pixmap(project, scene, layer, ap))
            self._gba_scene.set_bg_visible(layer.bg_slot, getattr(layer, "visible", True))
            shown.add(layer.bg_slot)
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # Contexte de peinture par palette + peuplement du bandeau de palettes.
        self._bg_paint_ctrl.set_context(project, scene)
        self._canvas_container.refresh_bg_palette()

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
                    img = _quantize_preview(img, sprite, bank)
                    if img.width > 0 and img.height > 0:
                        data = bytes(img.tobytes("raw", "RGBA"))
                        qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                        frame_px = QPixmap.fromImage(qi)
            if frame_px is None:
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
        if not selected:
            get_bus().clear()
            if not self._show_all_boxes:
                self._gba_scene.update_actor_boxes([])
            return
        first = selected[0]
        if isinstance(first, CameraItem):
            if self._project and self._project.active_scene:
                x, y = self._gba_scene.camera_pos()
                self._project.active_scene.cam_x = x
                self._project.active_scene.cam_y = y
                get_bus().select(self._project.active_scene)
        elif isinstance(first, SpriteItem):
            get_bus().select(first.scene_sprite)
        self._update_actor_box_overlay()

    def on_selection(self, obj):
        """Reçu du bus — sélectionner/désélectionner l'item canvas sans reboucler."""
        self._gba_scene.blockSignals(True)
        # Désélectionner tout d'abord
        for item in self._gba_scene.selectedItems():
            item.setSelected(False)
        if isinstance(obj, Actor):
            item = self._find_item(obj)
            if item:
                item.setSelected(True)
                self._gba_view.centerOn(item)
        self._gba_scene.blockSignals(False)

    def move_actor_item(self, actor: Actor):
        """Repositionne l'item Qt d'un actor sans recréer la scène (drag ou spinbox)."""
        item = self._find_item(actor)
        if item:
            item.setPos(actor.x, actor.y)

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
            if not layer.image:
                continue
            ba = self._project.get_background(layer.image)
            png = ba.source if ba and ba.source else f"{layer.image}.png"
            ap = self._project.background_images_dir / png
            self._gba_scene.set_bg(layer.bg_slot, _bg_pixmap(self._project, scene, layer, ap))
            self._gba_scene.set_bg_visible(layer.bg_slot, getattr(layer, "visible", True))
            shown.add(layer.bg_slot)
        for i in range(4):
            if i not in shown:
                self._gba_scene.set_bg(i, None)

        # La banque de base / les layers ont pu changer : resynchroniser le
        # contrôleur de peinture (raster du layer actif) et le bandeau.
        prev_slot = self._bg_paint_ctrl.active_layer_slot
        self._bg_paint_ctrl.set_context(self._project, scene)
        self._bg_paint_ctrl.set_active_layer(prev_slot)
        self._canvas_container.refresh_bg_palette()

    def set_paint_layer(self, bg_slot: int):
        """Choisit le layer BG peint par l'outil de peinture (via l'inspecteur)."""
        self._bg_paint_ctrl.set_active_layer(bg_slot)

    def set_layer_visible(self, bg_slot: int, visible: bool):
        """Masque/affiche un layer dans le canvas (visibilité viewport éditeur)."""
        self._gba_scene.set_bg_visible(bg_slot, visible)

    def update_actor_position(self, actor: Actor):
        item = self._find_item(actor)
        if item:
            item.setPos(actor.x, actor.y)
