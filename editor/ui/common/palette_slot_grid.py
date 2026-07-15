"""editor/ui/common/palette_slot_grid.py — grille de banques de palettes partagée.

`PaletteSlotGridAsset` matérialise l'allocation de palettes d'un pool (jusqu'à 16
banques) sous forme de grille compacte de swatches, sur le **modèle du Scene
Inspector** :

  [ palettes éditables (catalogue) ][ palettes propres (grisées / override) ]
  [ bouton + ][ banques libres (noires) ]

Consommateurs (une même vue duck-typée, cf. `codegen.palette_alloc.ScenePaletteView`
ou toute vue équivalente au tier asset) :
- Scene Inspector (palettes actives OBJ/BG d'une scène) ;
- (à venir) Background Editor / Sprite Editor au tier asset (PAL_BANK de l'objet).

La vue fournie expose : `scene_entries`, `asset_entries`, `can_add()`. Les entrées
sont duck-typées (cf. `ScenePaletteEntry` / `AssetPaletteEntry`). Le widget est
purement une vue : il émet des signaux, le consommateur mute son modèle et
recharge.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QPushButton, QGridLayout
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.common.theme import C
from ui.common.widgets import ScriptPickerPopup
from ui.common.palette_swatch import (
    bank_icon as _bank_icon, swatch_icon as _swatch_icon, plus_icon as _plus_icon,
)


# ──────────────────────────────────────────────────────────────────
#  PaletteSlotGridAsset — vue live des 16 banques d'un pool (cf. palette_alloc)
# ──────────────────────────────────────────────────────────────────
class PaletteSlotGridAsset(QWidget):
    """
    Grille compacte 2 lignes x 8 colonnes qui matérialise l'allocation d'une
    scène (ScenePaletteView), dans l'ordre :

      [ palettes de scène (éditables) ][ palettes d'asset (grisées / override) ]
      [ bouton + ][ banques libres (noires) ]

    - palette de scène : clic = remplacer (catalogue), clic droit = retirer ;
    - palette d'asset « own » (grisée) : clic = override par une palette de
      scène ; « override » (marqueur d'angle) : clic droit = revenir à la
      palette d'origine de l'asset ;
    - « + » : ajoute une palette de scène (masqué quand les 16 banques sont
      pleines).
    """

    scene_replace  = pyqtSignal(int, str)        # slot hardware, nouveau nom
    scene_add      = pyqtSignal(str)             # nouveau nom de palette de scène
    scene_remove   = pyqtSignal(int)             # slot hardware à retirer
    # AssetPaletteEntry, cible : slot scène (int) en mode scène, nom de banque
    # catalogue (str) en mode `override_catalog` (tier asset).
    asset_override = pyqtSignal(object, object)
    asset_restore  = pyqtSignal(object)          # AssetPaletteEntry

    _COLS = 8   # 2 barres horizontales de 8 (row = i//8, col = i%8)
    _ICON_SIZE = 28

    def __init__(self, accent: str, parent=None, *, override_catalog: bool = False):
        super().__init__(parent)
        self._accent = accent
        # override_catalog=False (défaut, scène) : override une palette d'asset
        # vers une palette ACTIVE de la scène (slot). True (tier asset) : override
        # vers une banque du CATALOGUE (nom) — cf. Background/Sprite Editor.
        self._override_catalog = override_catalog
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._buttons: list[QPushButton] = []
        self._catalog: list = []
        self._scene_entries: list = []   # pour le picker d'override

    # ── Styles de cellule ─────────────────────────────────────────
    def _style(self, *, bg: str, border: str, dashed: bool = False, width: int = 1) -> str:
        b = "dashed" if dashed else "solid"
        return (f"QPushButton{{background:{bg};border:{width}px {b} {border};border-radius:4px;}}"
                f"QPushButton:hover{{border-color:{self._accent};}}")

    def load(self, view, catalog: list):
        """view : ScenePaletteView ; catalog : list[PaletteBank] (choix +/replace)."""
        for b in self._buttons:
            self._layout.removeWidget(b)
            b.deleteLater()
        self._buttons.clear()
        self._catalog = catalog
        self._scene_entries = list(view.scene_entries)

        # Ordre : palettes de scène → bouton « + » (séparateur) → palettes
        # d'asset (grisées) → banques libres. Le « + » sépare l'éditable du
        # grisé ; ajouter une palette de scène le décale (ainsi que les assets)
        # vers la droite. Le « + » n'occupe pas de banque : il disparaît quand
        # les 16 sont pleines, et scène/assets redeviennent contigus.
        cells: list[tuple[str, object]] = []
        for e in view.scene_entries:
            cells.append(("scene", e))
        if view.can_add():
            cells.append(("plus", None))
        for e in view.asset_entries:
            # Un fond compressé occupe un BLOC de N banques → N cellules
            # (même swatch), pour que la grille reflète les banques consommées.
            for _ in range(max(1, getattr(e, "bank_span", 1))):
                cells.append(("asset", e))
        while len(cells) < 16:
            cells.append(("empty", None))

        for pos, (kind, entry) in enumerate(cells[:16]):
            btn = self._make_cell(kind, entry, view)
            row, col = divmod(pos, self._COLS)
            self._layout.addWidget(btn, row, col)
            self._buttons.append(btn)

    def _make_cell(self, kind: str, entry, view) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(self._ICON_SIZE + 10, self._ICON_SIZE + 10)
        btn.setIconSize(QSize(self._ICON_SIZE, self._ICON_SIZE))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        if kind == "scene":
            btn.setIcon(_swatch_icon(entry.colors, self._ICON_SIZE))
            btn.setToolTip(f"Slot {entry.slot} — {entry.name}\n"
                           f"Clic : remplacer · Clic droit : retirer")
            btn.setStyleSheet(self._style(bg=C.BG_INPUT, border=C.BORDER_MID))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_scene(b, e.slot))
            btn.customContextMenuRequested.connect(
                lambda _p, e=entry: self.scene_remove.emit(e.slot))

        elif kind == "asset":
            names = ", ".join(i.label for i in entry.instances)
            if entry.state == "override":
                # Tier asset : l'entrée porte directement ses couleurs/nom de
                # cible (ref_colors/ref_name) — pas besoin d'un scene_entry cible.
                # Tier scène : on résout la cible par slot dans scene_entries.
                target = next((s for s in view.scene_entries
                               if s.slot == entry.ref_slot), None)
                cols = (getattr(entry, "ref_colors", None)
                        or (target.colors if target else entry.own_colors))
                btn.setIcon(_swatch_icon(cols, self._ICON_SIZE,
                                         override=True, marker_color=self._accent))
                tgt = (getattr(entry, "ref_name", None)
                       or (target.name if target else "?"))
                btn.setToolTip(f"{names} → {tgt} (override)\n"
                               f"Clic : changer · Clic droit : palette d'origine")
                btn.setStyleSheet(self._style(bg=C.BG_INPUT, border=self._accent))
                btn.customContextMenuRequested.connect(
                    lambda _p, e=entry: self.asset_restore.emit(e))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_override(b, e))
            elif not getattr(entry, "overridable", True):
                # Bloc compressé : palette d'asset fixe, non remappable.
                btn.setIcon(_swatch_icon(entry.own_colors, self._ICON_SIZE, greyed=True))
                span = getattr(entry, "bank_span", 1)
                span_txt = f" — bloc de {span} banques" if span > 1 else ""
                btn.setToolTip(f"{names} — fond compressé{span_txt}\n(palette non éditable)")
                btn.setStyleSheet(
                    f"QPushButton{{background:{C.BG_BASE};"
                    f"border:1px solid {C.BORDER_DARK};border-radius:4px;}}")
            else:  # own — palette propre grisée (overridable)
                btn.setIcon(_swatch_icon(entry.own_colors, self._ICON_SIZE, greyed=True))
                btn.setToolTip(f"{names} — palette propre (non éditable)\n"
                               f"Clic : override avec une palette de scène")
                btn.setStyleSheet(self._style(bg=C.BG_BASE, border=C.BORDER_MID, dashed=True))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c, e=entry, b=btn: self._pick_override(b, e))

        elif kind == "plus":
            btn.setIcon(_plus_icon(self._ICON_SIZE, self._accent))
            btn.setToolTip("Ajouter une palette de scène")
            btn.setStyleSheet(
                f"QPushButton{{background:#000000;"
                f"border:1px dashed {self._accent};border-radius:4px;}}"
                f"QPushButton:hover{{background:{C.SEL_BG};}}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, b=btn: self._pick_add(b))

        else:  # empty — banque libre
            btn.setEnabled(False)
            btn.setToolTip("Banque libre")
            btn.setStyleSheet(self._style(bg="#000000", border=C.BORDER_DARK))

        return btn

    # ── Pickers ───────────────────────────────────────────────────
    def _catalog_entries(self) -> list:
        return [(b.name, b.name, _bank_icon(b)) for b in self._catalog]

    def _pick_scene(self, anchor: QPushButton, slot: int):
        popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(lambda name, s=slot: self.scene_replace.emit(s, name))
        popup.show_below(anchor)

    def _pick_add(self, anchor: QPushButton):
        popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                  parent=self, new_label=None)
        popup.picked.connect(lambda name: self.scene_add.emit(name))
        popup.show_below(anchor)

    def _pick_override(self, anchor: QPushButton, entry):
        """Popup de choix de la cible d'override.
        - tier asset (`override_catalog`) : banques du CATALOGUE → emit (entry, nom:str) ;
        - tier scène : palettes ACTIVES de la scène → emit (entry, slot:int)."""
        if self._override_catalog:
            if not self._catalog:
                return
            popup = ScriptPickerPopup(self._catalog_entries(), self._accent,
                                      parent=self, new_label=None)
            popup.picked.connect(lambda name, e=entry: self.asset_override.emit(e, name))
            popup.show_below(anchor)
            return
        if not self._scene_entries:
            return
        entries = [(s.name, str(s.slot), _swatch_icon(s.colors))
                   for s in self._scene_entries]
        popup = ScriptPickerPopup(entries, self._accent, parent=self, new_label=None)
        popup.picked.connect(lambda val, e=entry: self.asset_override.emit(e, int(val)))
        popup.show_below(anchor)
