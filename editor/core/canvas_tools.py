"""
editor/canvas_tools.py — Outils du canvas (pattern Strategy).

Chaque outil gère ses propres événements souris et son état.
GBAView délègue on_press/on_move/on_release à l'outil actif.

Cycle de vie :
    view.set_tool(tool)
        → ancien_tool.deactivate()   (curseur, drag mode)
        → nouveau_tool.activate()
    mouse events → tool.on_press / on_move / on_release
        → retourne True si l'event est consommé (évite super() dans View)
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Optional

from core.project import (
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
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsView

if TYPE_CHECKING:
    from core.scene_editor import GBAView


# ──────────────────────────────────────────────────────────────────
#  Base
# ──────────────────────────────────────────────────────────────────


class BaseTool(ABC):
    def __init__(self, view: GBAView):
        self._view = view

    def activate(self):
        """Appelé à l'activation : curseur, drag mode, overlays."""

    def deactivate(self):
        """Appelé avant le changement d'outil : nettoyage."""

    def on_press(self, pos: QPointF, e) -> bool:
        """Retourne True si l'event est consommé."""
        return False

    def on_move(self, pos: QPointF, e) -> bool:
        return False

    def on_release(self, pos: QPointF, e) -> bool:
        return False

    def on_leave(self):
        """Appelé quand la souris quitte le viewport."""


# ──────────────────────────────────────────────────────────────────
#  Ajout d'actor — snap 8px + surbrillance de cellule
# ──────────────────────────────────────────────────────────────────


class AddActorTool(BaseTool):
    """
    Snap obligatoire à la grille 8px.
    La cellule survolée est mise en surbrillance.
    Clic → crée un actor nommé Actor_X_Y aux coordonnées snappées.
    """

    _CELL = 16
    _FILL = QColor(100, 255, 120, 70)
    _BORDER = QColor(100, 255, 120, 220)

    def __init__(self, view):
        super().__init__(view)
        self._preview: QGraphicsRectItem | None = None

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._preview = QGraphicsRectItem(0, 0, self._CELL, self._CELL)
        self._preview.setBrush(QBrush(self._FILL))
        self._preview.setPen(QPen(self._BORDER, 0))
        self._preview.setZValue(50)
        self._preview.setVisible(False)
        self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    def on_move(self, pos: QPointF, e) -> bool:
        sx = int(pos.x() // self._CELL) * self._CELL
        sy = int(pos.y() // self._CELL) * self._CELL
        self._preview.setPos(sx, sy)
        self._preview.setVisible(True)
        return True

    def on_press(self, pos: QPointF, e) -> bool:
        sx = int(pos.x() // self._CELL) * self._CELL
        sy = int(pos.y() // self._CELL) * self._CELL
        from core.command_dispatcher import get_dispatcher

        proj = get_dispatcher().project
        scene = proj.active_scene if proj else None
        if scene:
            existing = {a.name for a in scene.actors}
            n = 0
            while f"Actor_{n}" in existing:
                n += 1
            name = f"Actor_{n}"
        else:
            name = "Actor_0"
        get_dispatcher().add_actor(name, x=sx, y=sy)
        return True

    def on_leave(self):
        if self._preview:
            self._preview.setVisible(False)


# ──────────────────────────────────────────────────────────────────
#  Sélection / déplacement (comportement Qt par défaut)
# ──────────────────────────────────────────────────────────────────


class SelectTool(BaseTool):
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.unsetCursor()

    # Aucun on_press/on_move/on_release : Qt gère rubber band + item drag.


# ──────────────────────────────────────────────────────────────────
#  Gomme — supprime l'actor cliqué
# ──────────────────────────────────────────────────────────────────


class EraseTool(BaseTool):
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.ForbiddenCursor)

    def deactivate(self):
        self._view.unsetCursor()

    def on_press(self, pos: QPointF, e) -> bool:
        from core.command_dispatcher import get_dispatcher
        from core.scene_editor import SpriteItem

        items = self._view.scene().items(pos)
        for item in items:
            if isinstance(item, SpriteItem):
                get_dispatcher().delete_actor(item.scene_sprite)
                break
        return True  # toujours consommé — évite le rubber band


# ──────────────────────────────────────────────────────────────────
#  Collision — pinceau 8px, 16px, slope sol, slope plafond (inversé)
# ──────────────────────────────────────────────────────────────────

_SLOPE_MODES = ("collision_slope", "collision_slope_inv")


class CollisionTool(BaseTool):
    """
    mode : "collision_8" | "collision_16" | "collision_slope" | "collision_slope_inv"

    Clic droit = peindre / appliquer.
    Clic gauche = effacer (TILE_EMPTY).
    """

    def __init__(self, view: GBAView, mode: str):
        super().__init__(view)
        self._mode = mode
        self._paint_mode: bool = True  # True=peindre, False=effacer
        self._slope_start: Optional[tuple[int, int]] = None
        self._dirty = False
        self._stroke_delta: dict[tuple[int, int], tuple[int, int]] = {}

    # ── Cycle de vie ─────────────────────────────────────────────

    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        ov = self._view.collision_overlay
        if ov:
            ov.setVisible(True)

    def deactivate(self):
        self._view.unsetCursor()
        ov = self._view.collision_overlay
        if ov:
            ov.set_preview(None)
            sc = self._view.scene()
            keep_visible = getattr(sc, "_collision_view", False)
            if not keep_visible:
                ov.setVisible(False)

    # ── Événements ───────────────────────────────────────────────

    def on_press(self, pos: QPointF, e) -> bool:
        self._stroke_delta = {}
        self._paint_mode = e.button() == Qt.MouseButton.LeftButton
        ov = self._view.collision_overlay
        if not ov:
            return True
        if self._mode in _SLOPE_MODES:
            col, row = ov.scene_to_tile(pos.x(), pos.y())
            self._slope_start = (col, row)
            if self._paint_mode:
                ov.set_preview(self._slope_tiles_for(col, row, col, row))
        elif self._mode == "collision_8":
            self._paint_brush(pos, 1)
            self._dirty = True
        elif self._mode == "collision_16":
            self._paint_brush(pos, 2)
            self._dirty = True
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        ov = self._view.collision_overlay
        if not ov:
            return True
        # Brush : seulement si le bouton correspondant est enfoncé
        buttons = e.buttons()
        active = (self._paint_mode and buttons & Qt.MouseButton.LeftButton) or (
            not self._paint_mode and buttons & Qt.MouseButton.RightButton
        )
        if self._mode == "collision_8" and active:
            self._paint_brush(pos, 1)
        elif self._mode == "collision_16" and active:
            self._paint_brush(pos, 2)
        elif self._mode in _SLOPE_MODES and self._slope_start and self._paint_mode:
            sc, sr = self._slope_start
            ec, er = ov.scene_to_tile(pos.x(), pos.y())
            ov.set_preview(self._slope_tiles_for(sc, sr, ec, er))
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        ov = self._view.collision_overlay
        if ov and self._mode in _SLOPE_MODES and self._slope_start:
            sc, sr = self._slope_start
            ec, er = ov.scene_to_tile(pos.x(), pos.y())
            tiles = self._slope_tiles_for(sc, sr, ec, er)
            for col, row, t in tiles:
                old = ov.tile_at(col, row)
                new = t if self._paint_mode else TILE_EMPTY
                self._stroke_delta[(col, row)] = (old, new)
                ov.set_tile(col, row, new)
            ov.set_preview(None)
            self._slope_start = None
            self._dirty = True

        if self._stroke_delta:
            from core.history import CollisionPaintCmd, get_history

            cmd = CollisionPaintCmd(
                ov,
                dict(self._stroke_delta),
                persist_fn=lambda: self._view.collision_painted.emit(),
            )
            h = get_history()
            h._undo.append(cmd)
            h._redo.clear()
            h.changed.emit()
            self._stroke_delta = {}

        if self._dirty:
            self._view.collision_painted.emit()
            self._dirty = False
        return True

    # ── Logique interne ───────────────────────────────────────────

    def _paint_brush(self, scene_pos: QPointF, brush_tiles: int):
        ov = self._view.collision_overlay
        if not ov:
            return
        col, row = ov.scene_to_tile(scene_pos.x(), scene_pos.y())
        new_type = TILE_SOLID if self._paint_mode else TILE_EMPTY
        for dr in range(brush_tiles):
            for dc in range(brush_tiles):
                c, r = col + dc, row + dr
                old = ov.tile_at(c, r)
                ov.set_tile(c, r, new_type)
                if (c, r) not in self._stroke_delta:
                    self._stroke_delta[(c, r)] = (old, new_type)
                else:
                    self._stroke_delta[(c, r)] = (
                        self._stroke_delta[(c, r)][0],
                        new_type,
                    )

    # ── Slope : génération de tiles ──────────────────────────────

    def _slope_tiles_for(
        self,
        sc: int,
        sr: int,
        ec: int,
        er: int,
    ) -> list[tuple[int, int, int]]:
        """
        Génère les tiles le long du segment (sc,sr)→(ec,er).

        Angle du drag         Résultat
        ───────────────────── ────────────────────────────────
        Point (dx=dy=0)       TILE_SOLID (clic simple)
        Horizontal (dy=0)     ligne TILE_SOLID (sol/plafond plat)
        Vertical pur (dx=0)   colonne TILE_SOLID (mur)
        Doux (|dx| > |dy|)    paires LO/HI (pente ~26°)
        45° (|dx| == |dy|)    SLOPE_L / SLOPE_R selon direction
        Raide (|dy| > |dx|)   paires HI/LO par colonne (~63°)
        """
        inv = self._mode == "collision_slope_inv"
        dx, dy = ec - sc, er - sr

        if dx == 0 and dy == 0:
            return [(sc, sr, TILE_SOLID)]

        adx, ady = abs(dx), abs(dy)
        going_right = dx >= 0
        going_up = dy < 0  # Y croît vers le bas en coords écran

        # ── Sol/plafond plat → SOLID ──────────────────────────────
        if dy == 0:
            return _bresenham(sc, sr, ec, er, TILE_SOLID)

        # ── Mur vertical pur → SOLID ──────────────────────────────
        if dx == 0:
            return _bresenham(sc, sr, ec, er, TILE_SOLID)

        # Tile 45° sélectionné selon la direction
        if not inv:
            base45 = (
                (TILE_SLOPE_L if going_up else TILE_SLOPE_R)
                if going_right
                else (TILE_SLOPE_R if going_up else TILE_SLOPE_L)
            )
        else:
            base45 = (
                (TILE_SLOPE_L_INV if going_up else TILE_SLOPE_R_INV)
                if going_right
                else (TILE_SLOPE_R_INV if going_up else TILE_SLOPE_L_INV)
            )

        # ── Pente douce ~26° : |dx| > |dy| → paires LO/HI ────────
        if adx > ady:
            return _gentle_slope_rows(
                sc, sr, ec, er, going_right, going_up, inv, base45
            )

        # ── Pente 45° : |dx| == |dy| → Bresenham diag ────────────
        if adx == ady:
            return _bresenham(sc, sr, ec, er, base45)

        # ── Pente raide : |dy| > |dx| → paires HI/LO par colonne ──
        if not inv:
            if going_right:
                hi = TILE_SLOPE_L_STEEP_HI if going_up else TILE_SLOPE_R_STEEP_HI
                lo = TILE_SLOPE_L_STEEP_LO if going_up else TILE_SLOPE_R_STEEP_LO
            else:
                hi = TILE_SLOPE_R_STEEP_HI if going_up else TILE_SLOPE_L_STEEP_HI
                lo = TILE_SLOPE_R_STEEP_LO if going_up else TILE_SLOPE_L_STEEP_LO
        else:
            # INV : HI_INV = petit triangle en BAS de la paire plafond,
            #       LO_INV = grand quad en HAUT → rôles HI/LO inversés vs non-INV.
            # Le miroir vertical inverse aussi la famille L/R (comme dans _gentle_slope_rows) :
            #   non-INV right+up → L  |  INV right+up → R
            if going_right:
                hi = (
                    TILE_SLOPE_R_STEEP_LO_INV if going_up else TILE_SLOPE_L_STEEP_LO_INV
                )
                lo = (
                    TILE_SLOPE_R_STEEP_HI_INV if going_up else TILE_SLOPE_L_STEEP_HI_INV
                )
            else:
                hi = (
                    TILE_SLOPE_L_STEEP_LO_INV if going_up else TILE_SLOPE_R_STEEP_LO_INV
                )
                lo = (
                    TILE_SLOPE_L_STEEP_HI_INV if going_up else TILE_SLOPE_R_STEEP_HI_INV
                )
        return _steep_slope(sc, sr, ec, er, hi, lo)


_BG_TILE = 8


class SceneInpaintingTool(BaseTool):
    """Peinture par palette d'un layer BG (réassignation SE_PALBANK par tuile).

    mode : "inpaint_brush" (pinceau 8×8) | "inpaint_rect" (sélection rectangulaire).
    Clic gauche = peindre la banque active ; clic droit = effacer l'override.
    L'état (layer actif, banque de peinture, raster) vit dans
    `view.inpainting_controller`.
    """

    _PREVIEW_FILL = QColor(120, 180, 255, 60)
    _PREVIEW_BORDER = QColor(120, 180, 255, 220)

    def __init__(self, view: GBAView, mode: str):
        super().__init__(view)
        self._mode = mode
        self._erase = False
        self._anchor: Optional[tuple[int, int]] = None  # (col,row) pour le rect
        self._preview: QGraphicsRectItem | None = None

    # ── Cycle de vie ─────────────────────────────────────────────
    def activate(self):
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        if self._mode == "inpaint_rect":
            self._preview = QGraphicsRectItem(0, 0, 0, 0)
            self._preview.setBrush(QBrush(self._PREVIEW_FILL))
            self._preview.setPen(QPen(self._PREVIEW_BORDER, 0))
            self._preview.setZValue(60)
            self._preview.setVisible(False)
            self._view.scene().addItem(self._preview)

    def deactivate(self):
        self._view.unsetCursor()
        if self._preview and self._preview.scene():
            self._preview.scene().removeItem(self._preview)
        self._preview = None

    # ── Helpers ──────────────────────────────────────────────────
    def _ctrl(self):
        return getattr(self._view, "inpainting_controller", None)

    @staticmethod
    def _tile(pos: QPointF) -> tuple[int, int]:
        return int(pos.x() // _BG_TILE), int(pos.y() // _BG_TILE)

    # ── Événements ───────────────────────────────────────────────
    def on_press(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True  # consommé (évite le rubber band) même si rien à peindre
        self._erase = e.button() == Qt.MouseButton.RightButton
        ctrl.begin_stroke()
        col, row = self._tile(pos)
        if self._mode == "inpaint_rect":
            self._anchor = (col, row)
            self._update_preview(col, row)
        else:
            ctrl.inpaint_tile(col, row, erase=self._erase)
        return True

    def on_move(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True
        buttons = e.buttons()
        pressing = buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        col, row = self._tile(pos)
        if self._mode == "inpaint_rect" and self._anchor is not None:
            self._update_preview(col, row)
        elif self._mode == "inpaint_brush" and pressing:
            ctrl.inpaint_tile(col, row, erase=self._erase)
        return True

    def on_release(self, pos: QPointF, e) -> bool:
        ctrl = self._ctrl()
        if not ctrl or not ctrl.ready:
            return True
        if self._mode == "inpaint_rect" and self._anchor is not None:
            ac, ar = self._anchor
            ec, er = self._tile(pos)
            for r in range(min(ar, er), max(ar, er) + 1):
                for c in range(min(ac, ec), max(ac, ec) + 1):
                    ctrl.inpaint_tile(c, r, erase=self._erase)
            self._anchor = None
            if self._preview:
                self._preview.setVisible(False)
        ctrl.end_stroke()
        return True

    def _update_preview(self, col: int, row: int):
        if not self._preview or self._anchor is None:
            return
        ac, ar = self._anchor
        x0, y0 = min(ac, col) * _BG_TILE, min(ar, row) * _BG_TILE
        w = (abs(col - ac) + 1) * _BG_TILE
        h = (abs(row - ar) + 1) * _BG_TILE
        self._preview.setRect(x0, y0, w, h)
        self._preview.setVisible(True)

    def on_leave(self):
        if self._preview and self._anchor is None:
            self._preview.setVisible(False)


def _gentle_slope_rows(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    going_right: bool,
    going_up: bool,
    inv: bool,
    corner_tile: int,  # tile 45° utilisé pour les rangées à 1 col et le 3e col
) -> list[tuple[int, int, int]]:
    """
    Slope douce (|dx| > |dy| > 0) : paires LO/HI groupées par rangée.

    Vue de gauche à droite :
      SLOPE_L (ascendant L→R)  : col gauche = LO (petit), col droite = HI (grand)
      SLOPE_R (descendant L→R) : col gauche = HI (grand), col droite = LO (petit)

    Rangée 1 col  → corner_tile (tile 45°, jamais de demi-paire seule)
    Rangée 2 cols → LO + HI
    Rangée 3 cols → LO + HI + corner_tile
    Rangée 4+     → LO + HI + corner_tile (cols supplémentaires ignorées)
    """
    is_l = (going_right and going_up) or (not going_right and not going_up)

    if not inv:
        left_t = TILE_SLOPE_L_LO if is_l else TILE_SLOPE_R_HI
        right_t = TILE_SLOPE_L_HI if is_l else TILE_SLOPE_R_LO
    else:
        # Plafond : familles L/R échangées — SR_HI+SR_LO ascendant, SL_LO+SL_HI descendant
        left_t = TILE_SLOPE_R_HI_INV if is_l else TILE_SLOPE_L_LO_INV
        right_t = TILE_SLOPE_R_LO_INV if is_l else TILE_SLOPE_L_HI_INV

    # Bresenham → regrouper par rangée
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    rows: dict[int, list[int]] = {}
    while True:
        rows.setdefault(y, []).append(x)
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy

    sorted_rows = sorted(rows.keys())
    tiles: list[tuple[int, int, int]] = []

    for row_y in sorted_rows:
        cols = sorted(set(rows[row_y]))
        n = len(cols)
        if n == 1:
            # Impossible de placer une paire complète → tile 45° propre
            tiles.append((cols[0], row_y, corner_tile))
        elif n == 2:
            tiles.append((cols[0], row_y, left_t))
            tiles.append((cols[1], row_y, right_t))
        else:
            # 1 seule paire LO+HI + 1 tile 45° max — jamais de SOLID, jamais 2 paires
            tiles.append((cols[0], row_y, left_t))
            tiles.append((cols[1], row_y, right_t))
            tiles.append((cols[2], row_y, corner_tile))
            # cols[3+] volontairement ignorées

    return tiles


def _steep_slope(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    tile_hi: int,
    tile_lo: int,
) -> list[tuple[int, int, int]]:
    """
    Pente raide (|dy| > |dx|) : paires HI/LO par colonne.
    HI = petit triangle (tête visuelle de la colonne).
    LO = grand quadrilatère (queue visuelle).
    Bresenham axe Y : garantit que chaque colonne accumule ses rangées
    avant de passer à la suivante (ex. ratio 1:2 → col 0 = HI+LO, col 1 = HI).
    """
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    tiles: list[tuple[int, int, int]] = []
    prev_col: int | None = None
    row_in_col = 0
    while True:
        if x != prev_col:
            row_in_col = 0
        # HI = tile du haut visuel, LO = tile du bas visuel
        # going down (sy>0) : row_in_col==0 = haut → HI
        # going up  (sy<0) : row_in_col==0 = bas  → LO
        tile = tile_hi if (row_in_col == 0) == (sy > 0) else tile_lo
        tiles.append((x, y, tile))
        row_in_col += 1
        prev_col = x
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy
    return tiles


def _bresenham(
    sc: int,
    sr: int,
    ec: int,
    er: int,
    tile_type: int,
) -> list[tuple[int, int, int]]:
    """Ligne de Bresenham → liste (col, row, tile_type)."""
    adx = abs(ec - sc)
    ady = abs(er - sr)
    sx = 1 if ec >= sc else -1
    sy = 1 if er >= sr else -1
    err = adx - ady
    x, y = sc, sr
    seen: set[tuple[int, int]] = set()
    tiles: list[tuple[int, int, int]] = []
    while True:
        if (x, y) not in seen:
            seen.add((x, y))
            tiles.append((x, y, tile_type))
        if x == ec and y == er:
            break
        e2 = 2 * err
        if e2 > -ady:
            err -= ady
            x += sx
        if e2 < adx:
            err += adx
            y += sy
    return tiles
