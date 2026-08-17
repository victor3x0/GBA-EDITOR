"""ui/background_editor/background_editor_screen.py — écran Background Editor.

3 colonnes : finder (backgrounds) · canvas d'inpainting (BackgroundInpainting :
repeindre la palette par tuile 8×8, partagé entre scènes, cf. bg_inpaint_canvas) ·
inspecteur (dimensions, budget tuiles, liste des palettes éditables, algo de
compression). La compression est non-destructive (cf. core/bg_import) — le PNG
n'est jamais modifié, tout vit en métadonnées dans le .json du BackgroundAsset.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QFileDialog, QLabel, QSpinBox,
    QMenu, QMessageBox, QAbstractItemView, QPushButton, QGridLayout, QCheckBox,
)
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtCore import (
    Qt, QSize, QMimeData, QObject, QRunnable, QThreadPool, pyqtSignal,
)

from ui.common.theme import C, T, QSS, ui_font
from ui.common.widgets import W, FinderSection, AssetHeaderBar
from ui.common.icons import COLOR_BACKGROUND, COLOR_UI
from ui.common.palette_slot_grid import PaletteSlotGridAsset
from ui.common.asset_palette_view import background_palette_view
from core.models.palette import PaletteBank
from core.models.resource import MIME_ANIMATED_BG
from core.models.background import (
    KIND_SCENE, KIND_UI, KIND_ANIMATED, BG_KINDS, BG_KIND_LABELS,
    UI_ROLE_NINE, UI_ROLE_BG, ANIM_INSTANCE, ANIM_SHARED,
)
from core.command_dispatcher import get_dispatcher
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import (
    BACKGROUNDS_SCENE, BACKGROUNDS_UI, BACKGROUNDS_ANIM,
)

# Section du finder <-> `kind` du modèle. Le composant partagé ne parle que de
# libellés de famille ; l'écran, lui, raisonne en `kind`.
_LABEL_OF_KIND = {KIND_SCENE:    BACKGROUNDS_SCENE.label,
                  KIND_UI:       BACKGROUNDS_UI.label,
                  KIND_ANIMATED: BACKGROUNDS_ANIM.label}
_KIND_OF_LABEL = {v: k for k, v in _LABEL_OF_KIND.items()}
from core.history import get_history, DeleteResourceCmd
from core.bg_import import bg_fits_vram
from .bg_inpaint_canvas import BgInpaintCanvas

_BG_COLOR = COLOR_BACKGROUND

# Un fond d'interface appartient à la famille INTERFACE, pas à la famille monde :
# la teinte dit à quoi sert l'asset, et c'est la seule chose qui distingue à
# l'œil un cadre de dialogue d'un décor dans la même liste (règle « une famille,
# une couleur » — cf. ui/common/icons.py).
_KIND_COLOR = {KIND_SCENE: COLOR_BACKGROUND, KIND_UI: COLOR_UI,
               KIND_ANIMATED: COLOR_BACKGROUND}

# Titre de section + libellé du bouton « + », par type.
_KIND_SECTION = {
    KIND_SCENE:    ("Backgrounds",    "Import a PNG"),
    KIND_UI:       ("UI backgrounds", "Import a UI frame or panel PNG"),
    KIND_ANIMATED: ("Animated",       "Import an animation sheet PNG"),
}


# ── Compression hors-thread ─────────────────────────────────────────────────
# La compression (bg_import) peut prendre plusieurs secondes sur un grand fond
# ou une photo : on la lance dans un worker du QThreadPool pour ne JAMAIS geler
# l'éditeur. Le worker calcule le dict de compression ; le thread UI l'applique
# à l'asset (asset_encoding.apply_bg_encoding) puis rafraîchit.

class _CompressSignals(QObject):
    done   = pyqtSignal(int, str, dict)   # token, source_name, résultat
    failed = pyqtSignal(int, str)          # token, message


class _EncodeTask(QRunnable):
    def __init__(self, token: int, png_path: Path, mode: str, method: str, dither: bool):
        super().__init__()
        self._token = token
        self._png = str(png_path)
        self._name = Path(png_path).name
        self._mode = mode           # "tiled4" | "tiled8" | "bitmap"
        self._method = method
        self._dither = dither
        self.signals = _CompressSignals()

    def run(self):
        try:
            from core.bg_import import encode_by_mode
            c = encode_by_mode(self._png, self._mode, self._method, self._dither)
            self.signals.done.emit(self._token, self._name, c)
        except Exception as e:  # noqa: BLE001 — remonté à l'UI, pas avalé
            self.signals.failed.emit(self._token, str(e))


# ── Finder (gauche) ─────────────────────────────────────────────────────────

class _BgList(QListWidget):
    """Liste d'UNE section du finder.

    Sous-classe seulement pour le DRAG : les fonds animés se posent sur le
    canvas d'un fond hôte, et Qt ne démarre un drag qu'à partir du widget
    source. Tout le reste (renommage, menu contextuel) est piloté par le
    panneau, qui seul connaît le projet.

    **Le choix d'un asset attend le relâchement**, il ne suit pas
    `currentItemChanged`. Qt fixe l'item courant dès l'APPUI, or un appui sur une
    liste glissable peut devenir un glissement : charger l'asset à ce moment-là
    faisait changer le canvas sous le curseur, et le fond hôte qu'on visait
    disparaissait avant même d'avoir bougé la souris. Le geste était donc
    impossible à terminer. D'où `chosen`, émis seulement quand l'utilisateur a
    vraiment choisi — au clavier, par programme, ou au relâchement d'un clic qui
    n'a pas tourné en glissement."""

    chosen = pyqtSignal(object)   # QListWidgetItem | None

    def __init__(self, color: str, draggable: bool, parent=None):
        super().__init__(parent)
        self._draggable = draggable
        self._mouse_select = False   # l'item courant change sous un appui souris
        self._drag_started = False
        self.currentItemChanged.connect(self._on_current)
        self.setStyleSheet(
            QSS.finder_list(color)
            # Éditeur de renommage en place : mêmes police/taille que la ligne,
            # sinon le QLineEdit s'ouvre avec la police par défaut (plus grande)
            # et le texte est rogné verticalement.
            + f"QListWidget QLineEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
              f"border:1px solid {color}; padding:0 4px; margin:0;"
              f"font-family:{T.MONO}; font-size:{T.MD}px;}}"
        )
        # Renommage en place : clic sur un item déjà sélectionné (même mécanisme
        # que les autres finders — sprite/scene/prefab).
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        if draggable:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def _on_current(self, cur, _prev=None):
        # Sous un appui souris, on ne tranche pas : le relâchement dira si
        # c'était un clic (donc un choix) ou le début d'un glissement.
        if not self._mouse_select:
            self.chosen.emit(cur)

    def mousePressEvent(self, e):
        self._mouse_select = self._draggable
        self._drag_started = False
        super().mousePressEvent(e)
        self._mouse_select = False

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        # Après un glissement, Qt ne livre pas toujours le relâchement — et s'il
        # le livre, l'asset ne doit pas changer pour autant : le geste visait le
        # canvas, pas la liste.
        if self._draggable and not self._drag_started:
            self.chosen.emit(self.currentItem())

    def startDrag(self, actions):
        if not self._draggable:
            return
        self._drag_started = True
        item = self.currentItem()
        ba = item.data(Qt.ItemDataRole.UserRole) if item else None
        if ba is None:
            return
        mime = QMimeData()
        mime.setData(MIME_ANIMATED_BG, ba.name.encode("utf-8"))
        # Le texte accompagne le mime maison : un drop hors canvas (barre de
        # recherche, éditeur externe) écrit alors le NOM, jamais un binaire.
        mime.setText(ba.name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class _AnimatedSourceList(_BgList):
    """Les animés du projet, à glisser sur le canvas du fond courant.

    Doublon apparent avec la section ANIMATED du finder, mais celle-ci ne peut
    pas servir de source : y presser un item change l'asset ÉDITÉ (elle pilote la
    sélection), si bien qu'au relâchement le canvas n'affiche plus le fond hôte
    mais l'animé qu'on croyait déposer. Une source qui ne possède aucune
    sélection n'a pas ce problème.

    Hérite de `_BgList` pour que `startDrag` — et donc le format d'échange —
    reste écrit à un seul endroit."""

    ROW_H = 22

    def __init__(self, parent=None):
        super().__init__(COLOR_BACKGROUND, draggable=True, parent=parent)
        # Ni renommage ni menu : ce n'est pas un finder, c'est une réserve.
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setFont(QFont(T.MONO, T.SM))

    def set_assets(self, assets: list):
        self.clear()
        for ba in assets:
            it = QListWidgetItem(ba.name)
            it.setData(Qt.ItemDataRole.UserRole, ba)
            n = ba.frame_count()
            it.setToolTip(f"{ba.name} — {n} frame{'s' if n > 1 else ''}. "
                          f"Drag onto the canvas to place it.")
            self.addItem(it)
        # Assez haute pour montrer jusqu'à quatre entrées, puis on défile : la
        # réserve ne doit pas repousser les palettes hors de l'écran.
        rows = min(max(len(assets), 1), 4)
        self.setFixedHeight(rows * self.ROW_H + 8)



# ── Propriétés (droite) ─────────────────────────────────────────────────────

class BgPropertiesPanel(QWidget):
    changed = pyqtSignal()          # compression recalculée → re-render du canvas
    renamed = pyqtSignal()          # fond renommé depuis l'en-tête → rafraîchir le finder
    kind_changed = pyqtSignal()     # type du fond changé → re-trier le finder
    palettes_changed = pyqtSignal()     # liste des palettes mutée → re-render du canvas
    geometry_changed = pyqtSignal()  # marges de coupe / découpe de frames → canvas
    recompress_requested = pyqtSignal(object, object, str, bool)  # (ba, png, mode_token, dither) → hors-thread
    overlays_changed = pyqtSignal(list, list)  # (info_lines, warning_lines) → overlays du canvas
    placement_changed = pyqtSignal()  # cadence / image de départ d'une copie → rejouer le canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220); self.setMaximumWidth(440)
        self.setStyleSheet(f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};")
        self._project = None
        self._ba = None
        self._blocking = False

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # ── En-tête : nom du fond — composant partagé (même template/couleurs/
        # renommage que Scene Manager, Sprite Editor, Sound Mixer, Script Editor).
        self._header = AssetHeaderBar()
        self._header.renamed.connect(self._on_rename)
        outer.addWidget(self._header)

        body = QWidget(); body.setStyleSheet(f"background:{C.BG_PANEL};")
        outer.addWidget(body, 1)
        root = QVBoxLayout(body); root.setContentsMargins(10, 8, 10, 8); root.setSpacing(2)

        # ── TYPE : à quoi sert l'image. Trois emplois d'un même asset (cf.
        #    core/models/background.BG_KINDS) — le type gouverne les sections
        #    ci-dessous et ce que le canvas superpose. Convertible sur place :
        #    un décor qu'on décide d'employer en cadre est le même PNG.
        kind_row = QHBoxLayout(); kind_row.setContentsMargins(0, 2, 0, 2); kind_row.setSpacing(6)
        self._kind_btns: dict[str, QPushButton] = {}
        for k, tip in ((KIND_SCENE, "Scene decor — placed as a layer, repainted per tile"),
                       (KIND_UI, "Interface — fills a UI panel as a stretchable frame "
                                 "or a plain image"),
                       (KIND_ANIMATED, "Animation sheet — cut into frames and dropped "
                                       "onto another background")):
            b = self._mode_btn({KIND_SCENE: "Scene", KIND_UI: "UI",
                                KIND_ANIMATED: "Animated"}[k], tip)
            b.clicked.connect(lambda _=False, kk=k: self._set_kind(kk))
            kind_row.addWidget(b, 1)
            self._kind_btns[k] = b
        root.addLayout(kind_row)
        W.separator(root)

        # ── MODE COULEUR : deux axes ORTHOGONAUX. Layout (tuilé/bitmap) ×
        #    profondeur (4/8/16 bpp) ; certaines combinaisons n'existent pas sur
        #    GBA → boutons profondeur filtrés selon le layout (cf. _refresh_mode_buttons).
        #    Changer d'axe recompresse le fond (hors-thread).
        lay_row = QHBoxLayout(); lay_row.setContentsMargins(0, 2, 0, 0); lay_row.setSpacing(6)
        self._btn_tiled = self._mode_btn("Tiled", "Tiled background (Mode 0) — tileset + tilemap, scroll, inpainting")
        self._btn_bitmap = self._mode_btn("Bitmap", "Full-screen bitmap ≤240×160, no tiles (photos / title screens)")
        self._btn_tiled.clicked.connect(lambda: self._set_layout("tiled"))
        self._btn_bitmap.clicked.connect(lambda: self._set_layout("bitmap"))
        lay_row.addWidget(self._btn_tiled, 1); lay_row.addWidget(self._btn_bitmap, 1)
        root.addLayout(lay_row)

        dep_row = QHBoxLayout(); dep_row.setContentsMargins(0, 2, 0, 2); dep_row.setSpacing(6)
        self._d4 = self._mode_btn("4bpp", "16 colors × 16 palettes · inpainting (pixel-art) — tiled only")
        self._d8 = self._mode_btn("8bpp", "256 colors, one palette (rich pixel-art / bitmap Mode 4)")
        self._d16 = self._mode_btn("16bpp", "15-bit direct color (true-color photos) — coming soon, falls back to Mode 4")
        self._d4.clicked.connect(lambda: self._set_depth(4))
        self._d8.clicked.connect(lambda: self._set_depth(8))
        self._d16.clicked.connect(lambda: self._set_depth(16))
        dep_row.addWidget(self._d4, 1); dep_row.addWidget(self._d8, 1); dep_row.addWidget(self._d16, 1)
        root.addLayout(dep_row)
        self._chk_dither = QCheckBox("Dithering")
        self._chk_dither.setFont(QFont(T.UI, T.SM))
        self._chk_dither.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_dither.toggled.connect(self._on_dither_toggled)
        root.addWidget(self._chk_dither)

        # NB : les infos read-only (dimensions, origine palette, tuiles/palettes) et
        # les alertes de validation NON-BLOQUANTES ne vivent plus dans l'inspecteur —
        # elles sont poussées via `overlays_changed` sur des overlays du canvas
        # (infos bas-gauche, warnings haut-droite). cf. _emit_overlays / _info_lines /
        # _validation_lines. Le PNG source n'est jamais modifié : ces messages
        # décrivent seulement la représentation GBA.
        W.separator(root)

        # ── UI ROLE (kind == ui) : comment le panneau étale l'image ──
        #    Deux façons, et une seule paire de valeurs pour les deux côtés :
        #    ce champ EST `UIPanel.fill_kind` (cf. UI_ROLES). Les marges ne
        #    comptent qu'en cadre étirable, et se règlent aussi au canvas — les
        #    champs et les guides écrivent le même modèle.
        self._ui_widgets: list = []
        self._ui_sep = W.separator(root)
        self._ui_title = W.section("UI role", root)
        role_row = QHBoxLayout(); role_row.setContentsMargins(0, 2, 0, 2); role_row.setSpacing(6)
        self._btn_nine = self._mode_btn(
            "Nine-slice", "Stretchable frame: fixed corners, repeated edges and center")
        self._btn_plain = self._mode_btn(
            "Background", "Plain image, laid top-left and cropped to the panel")
        self._btn_nine.clicked.connect(lambda: self._set_ui_role(UI_ROLE_NINE))
        self._btn_plain.clicked.connect(lambda: self._set_ui_role(UI_ROLE_BG))
        role_row.addWidget(self._btn_nine, 1); role_row.addWidget(self._btn_plain, 1)
        # Dans un conteneur et non posée en layout nu : `_refresh_kind_sections`
        # ne sait masquer que des widgets, et une ligne posée en layout restait
        # donc visible sur un décor — deux boutons de rôle d'interface offerts
        # sur une image qui n'en a pas.
        role_host = QWidget(); role_host.setStyleSheet("background:transparent;")
        role_host.setLayout(role_row)
        root.addWidget(role_host)
        self._ui_role_row = role_host

        self._slice_spins: dict[str, QSpinBox] = {}
        slice_host = QWidget(); slice_host.setStyleSheet("background:transparent;")
        srow = QHBoxLayout(slice_host); srow.setContentsMargins(0, 0, 0, 0); srow.setSpacing(4)
        for field_name, lab in (("slice_left", "L"), ("slice_right", "R"),
                                ("slice_top", "T"), ("slice_bottom", "B")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 512)
            sp.setSingleStep(8)      # une tuile : le pas où la coupe existe vraiment
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda v, f=field_name: self._on_slice(f, v))
            srow.addWidget(t); srow.addWidget(sp, 1)
            self._slice_spins[field_name] = sp
        self._slice_row = W.row("Margins", slice_host, root).parentWidget()
        self._ui_widgets = [self._ui_sep, self._ui_title, self._ui_role_row,
                            self._slice_row]

        # ── ANIMATION (kind == animated) ─────────────────────────────
        #    Découpe en GRILLE + vitesse en ticks 60 Hz (l'unité de
        #    `AnimState.speed` — animer un décor se lit comme animer un sprite).
        self._anim_sep = W.separator(root)
        self._anim_title = W.section("Animation", root)
        frame_host = QWidget(); frame_host.setStyleSheet("background:transparent;")
        frow = QHBoxLayout(frame_host); frow.setContentsMargins(0, 0, 0, 0); frow.setSpacing(4)
        self._frame_spins: dict[str, QSpinBox] = {}
        for field_name, lab in (("frame_w", "W"), ("frame_h", "H")):
            t = QLabel(lab)
            t.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
            t.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent; border:none;")
            t.setFixedWidth(14)
            sp = QSpinBox()
            sp.setFont(QFont(T.MONO, T.SM))
            sp.setStyleSheet(QSS.spinbox)
            sp.setRange(0, 1024)
            sp.setSingleStep(8)
            sp.setSpecialValueText("full")   # 0 = pas de découpe : une seule frame
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda v, f=field_name: self._on_frame_size(f, v))
            frow.addWidget(t); frow.addWidget(sp, 1)
            self._frame_spins[field_name] = sp
        self._frame_row = W.row("Frame", frame_host, root).parentWidget()

        self._speed = QSpinBox()
        self._speed.setFont(QFont(T.MONO, T.SM))
        self._speed.setStyleSheet(QSS.spinbox)
        self._speed.setRange(1, 255)
        self._speed.setSuffix(" ticks")
        self._speed.setToolTip("Ticks (1/60 s) between two frames — same unit as a "
                               "sprite animation speed.")
        self._speed.setKeyboardTracking(False)
        self._speed.valueChanged.connect(self._on_speed)
        self._speed_row = W.row("Speed", self._speed, root).parentWidget()

        self._chk_loop = QCheckBox("Loop")
        self._chk_loop.setFont(QFont(T.UI, T.SM))
        self._chk_loop.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._chk_loop.toggled.connect(self._on_loop)
        root.addWidget(self._chk_loop)

        # Mode de lecture — nommé par ce que l'auteur VOIT (les copies bougent
        # chacune pour soi, ou toutes ensemble), jamais par le procédé.
        mode_host = QWidget(); mode_host.setStyleSheet("background:transparent;")
        mrow = QHBoxLayout(mode_host); mrow.setContentsMargins(0, 0, 0, 0); mrow.setSpacing(6)
        self._anim_mode_btns: dict[str, QPushButton] = {}
        for mode, label, tip in (
            (ANIM_INSTANCE, "Per instance",
             "Each copy placed on a background animates on its own."),
            (ANIM_SHARED, "Shared",
             "Every copy animates together, in step."),
        ):
            b = self._mode_btn(label, tip)
            b.clicked.connect(lambda _=False, m=mode: self._set_animation_mode(m))
            mrow.addWidget(b, 1)
            self._anim_mode_btns[mode] = b
        self._anim_mode_row = W.row("Playback", mode_host, root).parentWidget()

        self._anim_widgets = [self._anim_sep, self._anim_title, self._frame_row,
                              self._speed_row, self._chk_loop, self._anim_mode_row]

        # ── ANIMATIONS À POSER ────────────────────────────────────────
        #    Réserve de glissement vers le canvas. Dans l'inspecteur et non dans
        #    le finder : celui-ci pilote l'asset édité, y presser un item ferait
        #    changer le canvas sous le drag (cf. _AnimatedSourceList).
        self._src_sep = W.separator(root)
        self._src_title = W.section("Animations", root)
        self._src_hint = QLabel("Drag onto the canvas to place")
        self._src_hint.setFont(QFont(T.UI, T.SM))
        self._src_hint.setStyleSheet(f"color:{C.TEXT_MUTED}; background:transparent;")
        root.addWidget(self._src_hint)
        self._src_list = _AnimatedSourceList()
        root.addWidget(self._src_list)
        self._src_widgets = [self._src_sep, self._src_title, self._src_hint,
                             self._src_list]

        # ── PLACEMENT (un animé sélectionné sur le canvas) ────────────
        #    Section pilotée par la SÉLECTION et non par le type de l'asset :
        #    elle décrit une copie posée, pas l'image courante.
        self._pl_sep = W.separator(root)
        self._pl_title = W.section("Placement", root)
        self._pl_name = QLabel("")
        self._pl_name.setFont(QFont(T.MONO, T.SM))
        self._pl_name.setStyleSheet(f"color:{C.TEXT_DIM}; background:transparent;")
        root.addWidget(self._pl_name)
        self._pl_start = QSpinBox()
        self._pl_start.setFont(QFont(T.MONO, T.SM))
        self._pl_start.setStyleSheet(QSS.spinbox)
        self._pl_start.setRange(0, 255)
        self._pl_start.setToolTip(
            "Which frame this copy starts on. Lets two copies of the same "
            "animation sit at different points of the loop.")
        self._pl_start.setKeyboardTracking(False)
        self._pl_start.valueChanged.connect(self._on_placement_start)
        self._pl_start_row = W.row("Start frame", self._pl_start, root).parentWidget()

        self._pl_speed = QSpinBox()
        self._pl_speed.setFont(QFont(T.MONO, T.SM))
        self._pl_speed.setStyleSheet(QSS.spinbox)
        self._pl_speed.setRange(0, 255)
        self._pl_speed.setSuffix(" ticks")
        self._pl_speed.setSpecialValueText("default")   # 0 = cadence de l'animé
        self._pl_speed.setToolTip(
            "Ticks between two frames for this copy only. Leave at default to "
            "follow the animation's own speed.")
        self._pl_speed.setKeyboardTracking(False)
        self._pl_speed.valueChanged.connect(self._on_placement_speed)
        self._pl_speed_row = W.row("Speed", self._pl_speed, root).parentWidget()

        self._pl_widgets = [self._pl_sep, self._pl_title, self._pl_name,
                            self._pl_start_row, self._pl_speed_row]
        self._placement = None
        for w in self._pl_widgets:
            w.setVisible(False)

        # ── PALETTES : grille unifiée (modèle Scene Inspector). Palettes dérivées
        #    du PNG grisées + overridables (clic = pointer une banque du catalogue,
        #    clic droit = restaurer l'origine) ; « + » ajoute une palette du
        #    catalogue (éditable, clic = remplacer, clic droit = retirer). La
        #    palette active de PEINTURE se choisit dans la bande en haut du canvas.
        W.separator(root); W.section("Palettes", root)
        self._pal_grid = PaletteSlotGridAsset(_BG_COLOR)
        self._pal_grid.scene_add.connect(self._on_pal_add)
        self._pal_grid.scene_replace.connect(self._on_pal_replace)
        self._pal_grid.scene_remove.connect(self._on_pal_remove)
        self._pal_grid.asset_override.connect(self._on_pal_override)
        self._pal_grid.asset_restore.connect(self._on_pal_restore)
        root.addWidget(self._pal_grid)

        self._btn = W.btn_accent("⟐  Import / replace image…")
        self._btn.clicked.connect(self._on_replace)
        root.addWidget(self._btn)

        self._btn_restore = self._mini_btn(
            "↺  Restore original…",
            "Resets the background to its first import (PNG re-compression) — "
            "added palettes and painting will be lost.")
        self._btn_restore.clicked.connect(self._on_restore)
        root.addWidget(self._btn_restore)
        root.addStretch()

        # ── EXTRACT PALETTE — ferré en bas de l'inspecteur. Promeut les
        #    sous-palettes déduites du PNG en PaletteBank partagées du catalogue
        #    (visibles/éditables depuis le Palette Editor) et les assigne à ce fond.
        self._btn_extract = QPushButton("⤓  EXTRACT PALETTE")
        self._btn_extract.setToolTip(
            "Promotes palettes deduced from the PNG into shared catalog "
            "palettes (visible and editable from the Palette Editor). "
            "Created palettes are assigned to this background.")
        self._btn_extract.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        self._btn_extract.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_extract.setFixedHeight(38)
        self._btn_extract.setStyleSheet(
            f"QPushButton{{color:{_BG_COLOR}; background:transparent;"
            f"border:2px solid {_BG_COLOR}; border-radius:5px; letter-spacing:1px;"
            f"padding:4px 10px;}}"
            f"QPushButton:hover{{color:{C.BG_DEEP}; background:{_BG_COLOR};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:transparent;}}"
        )
        self._btn_extract.clicked.connect(self._on_extract_palette)
        root.addWidget(self._btn_extract)

    def _mini_btn(self, text: str, tip: str = "") -> QPushButton:
        b = QPushButton(text); b.setToolTip(tip)
        b.setFont(QFont(T.UI, T.SM))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:3px 8px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI}; background:{C.BG_HOVER};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};}}"
        )
        return b

    def _mode_btn(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text); b.setToolTip(tip)
        b.setCheckable(True)
        b.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM}; background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER_MID}; border-radius:4px; padding:2px 10px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            f"QPushButton:checked{{color:{_BG_COLOR}; border:2px solid {_BG_COLOR};"
            f"background:{C.BG_SEL};}}"
            f"QPushButton:disabled{{color:{C.TEXT_MUTED}; border-color:{C.BORDER_DARK};"
            f"background:{C.BG_INPUT};}}"
        )
        return b

    # ── Mode couleur : 2 axes (layout × profondeur) ───────────────
    #    Combinaisons valides GBA : tuilé→{4,8}, bitmap→{8,16}. Le 16bpp direct
    #    n'est pas encore implémenté (repli Mode 4) → bouton visible mais désactivé.

    def _cur_axes(self) -> tuple[str, int]:
        """(layout, profondeur) courant de l'asset. Le bitmap est du Mode 4 (8bpp) :
        le 16bpp direct n'étant pas persisté, on le lit toujours comme 8."""
        if not self._ba:
            return ("tiled", 4)
        if self._ba.mode == "bitmap":
            return ("bitmap", 8)
        return ("tiled", 8 if self._ba.bpp == 8 else 4)

    @staticmethod
    def _axes_token(layout: str, depth: int) -> str:
        if layout == "tiled":
            return "tiled8" if depth == 8 else "tiled4"
        return "bitmap16" if depth == 16 else "bitmap"

    def _cur_mode_token(self) -> str:
        return self._axes_token(*self._cur_axes())

    def _refresh_mode_buttons(self):
        layout, depth = self._cur_axes()
        tok = self._axes_token(layout, depth)
        tiled = layout == "tiled"
        base = bool(self._ba and (self._ba.tileset or self._ba.bitmap))
        self._blocking = True
        self._btn_tiled.setChecked(tiled)
        self._btn_bitmap.setChecked(not tiled)
        self._d4.setChecked(tiled and depth == 4)
        self._d8.setChecked(depth == 8)
        self._d16.setChecked(not tiled and depth == 16)
        # Filtre des profondeurs valides selon le layout.
        self._btn_tiled.setEnabled(base); self._btn_bitmap.setEnabled(base)
        self._d4.setEnabled(base and tiled)          # 4bpp : tuilé uniquement
        self._d8.setEnabled(base)                    # 8bpp : toujours
        self._d16.setEnabled(False)                  # 16bpp direct : à venir
        self._chk_dither.setVisible(tok != "tiled4")
        self._chk_dither.setChecked(bool(self._ba and self._ba.dither))
        self._blocking = False

    def _apply_axes(self, layout: str, depth: int):
        """Recompresse vers (layout, depth) si le token change ; sinon réaligne l'UI."""
        if self._blocking or not self._ba or not self._project:
            self._refresh_mode_buttons(); return
        token = self._axes_token(layout, depth)
        if token == self._cur_mode_token():
            self._refresh_mode_buttons(); return
        ap = self._png_path()
        if not ap or not ap.exists():
            self._refresh_mode_buttons(); return
        self.recompress_requested.emit(self._ba, ap, token, self._ba.dither)

    def _set_layout(self, layout: str):
        # Bascule d'axe : on snappe la profondeur sur une valeur valide du layout
        # cible (tuilé→{4,8}, bitmap→{8,16}), en gardant l'actuelle si possible.
        _, depth = self._cur_axes()
        valid = (4, 8) if layout == "tiled" else (8, 16)
        self._apply_axes(layout, depth if depth in valid else 8)

    def _set_depth(self, depth: int):
        layout, _ = self._cur_axes()
        self._apply_axes(layout, depth)

    def _on_dither_toggled(self, on: bool):
        tok = self._cur_mode_token()
        if self._blocking or not self._ba or tok == "tiled4":
            return
        ap = self._png_path()
        if not ap or not ap.exists():
            return
        self._ba.dither = on
        self.recompress_requested.emit(self._ba, ap, tok, on)

    # ── Type de fond & sections dépendantes ───────────────────────

    def _set_kind(self, kind: str):
        """Convertit l'asset — même PNG, même compression, autre emploi. Le
        finder re-trie (l'asset change de section) et le canvas change ce qu'il
        superpose."""
        if self._blocking or not self._ba or not self._project:
            self._refresh_kind_buttons(); return
        if self._ba.kind == kind:
            self._refresh_kind_buttons(); return
        self._ba.kind = kind
        self._persist_bg()
        self.kind_changed.emit()

    def _refresh_kind_buttons(self):
        kind = self._ba.kind if self._ba else KIND_SCENE
        self._blocking = True
        for k, b in self._kind_btns.items():
            b.setChecked(k == kind)
            b.setEnabled(self._ba is not None)
        self._blocking = False

    def _refresh_kind_sections(self):
        """Montre la section propre au type courant. Un fond n'a qu'un emploi :
        empiler les trois panneaux ferait chercher lequel s'applique."""
        kind = self._ba.kind if self._ba else KIND_SCENE
        is_ui = self._ba is not None and kind == KIND_UI
        is_anim = self._ba is not None and kind == KIND_ANIMATED
        for w in self._ui_widgets:
            w.setVisible(is_ui)
        # Les marges ne veulent rien dire pour une image simplement posée.
        self._slice_row.setVisible(is_ui and self._ba.ui_role == UI_ROLE_NINE)
        for w in self._anim_widgets:
            w.setVisible(is_anim)
        self._blocking = True
        if is_ui:
            self._btn_nine.setChecked(self._ba.ui_role == UI_ROLE_NINE)
            self._btn_plain.setChecked(self._ba.ui_role == UI_ROLE_BG)
            for f, sp in self._slice_spins.items():
                sp.setValue(int(getattr(self._ba, f, 0)))
        if is_anim:
            for f, sp in self._frame_spins.items():
                sp.setValue(int(getattr(self._ba, f, 0)))
            self._speed.setValue(max(1, int(self._ba.speed)))
            self._chk_loop.setChecked(bool(self._ba.loop))
        self._blocking = False
        if is_anim:
            self._refresh_anim_mode_buttons()
        self._refresh_animation_sources()

    def _refresh_animation_sources(self):
        """Réserve d'animés à poser — cachée quand elle ne mènerait à rien.

        Absente sur un animé lui-même : le modèle permet d'en poser un sur un
        autre (une planche reste une image), mais l'éditeur ne le propose pas,
        et une réserve visible là inviterait à un montage que rien ne réclame.
        Absente aussi tant que le projet n'a aucun animé — une liste vide ne
        s'explique pas toute seule."""
        assets = [b for b in (self._project.backgrounds if self._project else [])
                  if b.kind == KIND_ANIMATED]
        show = bool(assets) and self._ba is not None and self._ba.kind != KIND_ANIMATED
        for w in self._src_widgets:
            w.setVisible(show)
        if show:
            self._src_list.set_assets(assets)

    # ── kind == ui ────────────────────────────────────────────────

    def _set_ui_role(self, role: str):
        if self._blocking or not self._ba:
            self._refresh_kind_sections(); return
        if self._ba.ui_role != role:
            self._ba.ui_role = role
            self._persist_bg()
        self._refresh_kind_sections()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_slice(self, field_name: str, value: int):
        if self._blocking or not self._ba:
            return
        setattr(self._ba, field_name, int(value))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def set_slice_margins(self, margins: dict):
        """Marges posées depuis le CANVAS (glissement d'un guide). Le canvas a
        déjà écrit le modèle : on ne fait que réaligner les champs, sans
        repersister ni réémettre — sinon chaque pixel de glissement rebouclerait
        sur le canvas qui l'a produit."""
        self._blocking = True
        for f, v in margins.items():
            sp = self._slice_spins.get(f)
            if sp is not None:
                sp.setValue(int(v))
        self._blocking = False
        self._emit_overlays()

    # ── kind == animated ──────────────────────────────────────────

    def _on_frame_size(self, field_name: str, value: int):
        if self._blocking or not self._ba:
            return
        setattr(self._ba, field_name, max(0, int(value)))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_speed(self, value: int):
        if self._blocking or not self._ba:
            return
        self._ba.speed = max(1, int(value))
        self._persist_bg()
        self._emit_overlays()
        self.geometry_changed.emit()

    def _on_loop(self, on: bool):
        if self._blocking or not self._ba:
            return
        self._ba.loop = bool(on)
        self._persist_bg()
        self.geometry_changed.emit()

    def _set_animation_mode(self, mode: str):
        """Le mode vit sur l'ANIMÉ : le changer ici le change pour tous les fonds
        qui posent cette animation. Rien à réémettre côté canvas — les deux modes
        se jouent pareil dans l'éditeur, ils ne divergent qu'en ROM."""
        if self._blocking or not self._ba:
            self._refresh_anim_mode_buttons(); return
        if self._ba.animation_mode != mode:
            self._ba.animation_mode = mode
            self._persist_bg()
        self._refresh_anim_mode_buttons()

    def set_placement(self, pl):
        """Copie posée sélectionnée au canvas — None pour refermer la section.

        Masquée en mode `shared` plutôt que grisée : là-bas toutes les copies
        partagent un unique compteur, un décalage par copie n'y décrit rien. Un
        champ sans effet vaut moins qu'un champ absent."""
        ba = None
        if pl is not None and self._project is not None:
            ba = self._project.get_background(getattr(pl, "animated_name", ""))
        show = (pl is not None and ba is not None
                and getattr(ba, "animation_mode", ANIM_INSTANCE) != ANIM_SHARED)
        self._placement = pl if show else None
        for w in self._pl_widgets:
            w.setVisible(show)
        if not show:
            return
        self._blocking = True
        self._pl_name.setText(ba.name)
        # Plafond = la dernière image de la planche : au-delà ça reboucle, et un
        # nombre sans effet visible ne se règle pas.
        self._pl_start.setMaximum(max(0, ba.frame_count() - 1))
        self._pl_start.setValue(int(getattr(pl, "start_frame", 0) or 0))
        self._pl_speed.setValue(int(getattr(pl, "speed", 0) or 0))
        self._blocking = False

    def _on_placement_start(self, value: int):
        if self._blocking or self._placement is None:
            return
        self._placement.start_frame = max(0, int(value))
        self._persist_bg()
        self.placement_changed.emit()

    def _on_placement_speed(self, value: int):
        if self._blocking or self._placement is None:
            return
        self._placement.speed = max(0, int(value))
        self._persist_bg()
        self.placement_changed.emit()

    def _refresh_anim_mode_buttons(self):
        mode = getattr(self._ba, "animation_mode", ANIM_INSTANCE) if self._ba else ANIM_INSTANCE
        self._blocking = True
        for m, b in self._anim_mode_btns.items():
            b.setChecked(m == mode)
            b.setEnabled(self._ba is not None)
        self._blocking = False

    def load(self, ba, project):
        self._project, self._ba = project, ba
        self._blocking = True
        if ba:
            self._header.set_header("background", ba.kind_label(), ba.name)
        else:
            self._header.set_header("empty", "", "")
        self._blocking = False
        self._refresh_kind_buttons()
        self._refresh_kind_sections()
        self._refresh_mode_buttons()
        self._reload_palettes()   # émet aussi les overlays (infos + warnings)

    def _emit_overlays(self):
        """Pousse les infos read-only + les warnings vers les overlays du canvas."""
        ba = self._ba
        info = self._info_lines(ba) if ba else []
        warns = self._validation_lines(ba) if ba else []
        self.overlays_changed.emit(info, warns)

    def _info_lines(self, ba) -> list:
        """Lignes descriptives read-only (dims, origine palette, tuiles, palettes)
        pour l'overlay bas-gauche du canvas."""
        if not ba or not (ba.tileset or ba.bitmap):
            return []
        lines: list = []
        if ba.mode == "bitmap" and ba.bitmap:
            lines.append(f"{ba.out_w}×{ba.out_h} px  ·  bitmap ≤240×160")
        elif ba.tileset:
            lines.append(f"{ba.tiles_w*8}×{ba.tiles_h*8} px  ·  {ba.tiles_w}×{ba.tiles_h} tuiles")
        indexed, ncol, capped = self._source_info(ba)
        origin = "indexed (original palette)" if indexed else "inferred"
        ncol_s = "256+" if capped else str(ncol)
        lines.append(f"Source: {origin} · {ncol_s} colors")
        if ba.mode == "bitmap":
            lines.append("Mode 4 — full screen, no tiles")
            lines.append("Palette: 256 colors (1)")
        else:
            budget = 256 if ba.bpp == 8 else 512
            lines.append(f"Unique tiles: {len(ba.tileset)} / {budget}  ({ba.bpp}bpp)")
            lines.append("Palette: 256 colors (1)" if ba.bpp == 8
                         else f"Palettes: {len(ba.palettes)} / 16")
        lines += self._kind_info_lines(ba)
        return lines

    def _kind_info_lines(self, ba) -> list:
        """Ce que le TYPE ajoute à la description. Les grandeurs dérivées vivent
        ici plutôt que dans un champ grisé de l'inspecteur : elles se recalculent
        à chaque frappe, et un champ qu'on ne peut pas éditer n'a rien à faire
        au milieu de ceux qu'on édite."""
        if ba.kind == KIND_UI:
            if ba.ui_role != UI_ROLE_NINE:
                return ["UI: plain background — laid top-left, cropped to the panel"]
            l, r, t, b = ba.slice_margins()
            tl, tr, tt, tb = ba.slice_margins_tiles()
            return [f"UI: nine-slice — margins {l}/{r}/{t}/{b} px",
                    f"At build: {tl}/{tr}/{tt}/{tb} tiles"]
        if ba.kind == KIND_ANIMATED:
            cols, rows = ba.frame_grid()
            fw, fh = ba.frame_size()
            n = ba.frame_count()
            secs = ba.duration_frames() / 60.0
            return [f"Frames: {n}  ({cols}×{rows} grid of {fw}×{fh} px)",
                    f"Cycle: {ba.speed} ticks/frame · {secs:.2f}s"
                    + ("" if ba.loop else " · once")]
        if ba.animations:
            n = len(ba.animations)
            return [f"Animations placed: {n}"]
        return []

    def _source_info(self, ba) -> tuple[bool, int, bool]:
        """(indexed, n_colors, capped) du PNG source — mis en cache dans
        `ba.diagnostics` pour ne pas relire l'image à chaque sélection."""
        d = ba.diagnostics if isinstance(ba.diagnostics, dict) else {}
        if "src_indexed" in d and "src_colors" in d:
            return d["src_indexed"], d["src_colors"], bool(d.get("src_capped"))
        ap = self._png_path()
        if not ap or not ap.exists():
            return False, 0, False
        try:
            from core.bg_import import source_palette_info
            indexed, ncol, capped = source_palette_info(ap)
        except Exception:
            return False, 0, False
        if not isinstance(ba.diagnostics, dict):
            ba.diagnostics = {}
        ba.diagnostics.update(src_indexed=indexed, src_colors=ncol, src_capped=capped)
        return indexed, ncol, capped

    # ── Validation (non-bloquante) ────────────────────────────────

    def _diag_for(self, ba) -> dict:
        """Diagnostics de compression : depuis l'asset, sinon calculés à la volée
        pour les fonds importés avant le validateur (mémorisés sur l'asset)."""
        if not ba:
            return {}
        if ba.diagnostics:
            return ba.diagnostics
        ap = self._png_path()
        if ap and ap.exists():
            try:
                from core.bg_import import analyze_background_source
                ba.diagnostics = analyze_background_source(ap, method=ba.quantize_method)
            except Exception:
                ba.diagnostics = {}
        return ba.diagnostics or {}

    def _kind_validation_lines(self, ba) -> list:
        """Alertes que le TYPE ajoute — toutes non bloquantes, et toutes portant
        sur un écart entre ce que l'auteur a réglé et ce que le matériel rendra."""
        warn, err = C.ACCENT_YLW, C.ACCENT_RED
        out: list = []
        if ba.kind in (KIND_UI, KIND_ANIMATED) and ba.mode == "bitmap":
            out.append((f"⚠ Bitmap (Mode 4) — a {ba.kind_label().lower()} needs "
                        "tiles; switch to Tiled.", err))
            return out
        if ba.kind == KIND_UI and ba.ui_role == UI_ROLE_NINE:
            odd = [n for n, m in zip("LRTB", ba.slice_margins()) if m % 8]
            if odd:
                out.append(("⚠ Margin " + "/".join(odd) + " is not a multiple of 8 — "
                            "rounded down to the tile at build.", warn))
            l, r, t, b = ba.slice_margins()
            iw, ih = ba.pixel_size()
            if iw and (l + r > iw or t + b > ih):
                out.append(("⚠ Opposite margins overlap — corners will be "
                            "squeezed on small panels.", warn))
        if ba.kind == KIND_ANIMATED:
            if ba.frame_count() <= 0:
                out.append(("⚠ Frame larger than the sheet — no frame to play.", err))
            elif not ba.frame_grid_is_exact():
                cols, rows = ba.frame_grid()
                fw, fh = ba.frame_size()
                iw, ih = ba.pixel_size()
                out.append((f"⚠ {iw}×{ih} not divisible by {fw}×{fh} — "
                            f"{iw - cols * fw}×{ih - rows * fh} px left out.", warn))
        return out

    def _validation_lines(self, ba) -> list:
        if not ba or not (ba.tileset or ba.bitmap):
            return [("⚠ Compression impossible — unreadable or empty image.", C.ACCENT_RED)]
        warn, err, ok = C.ACCENT_YLW, C.ACCENT_RED, C.POWER
        kind_lines = self._kind_validation_lines(ba)
        if ba.mode == "bitmap":
            diag = self._diag_for(ba)
            lines: list = []
            if diag.get("scaled"):
                lines.append((f"⚠ Image scaled → {ba.out_w}×{ba.out_h} (≤ 240×160).", warn))
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append(("⚠ &gt; 256 colors — reduced to 256 (lossy).", warn))
            if not lines and not kind_lines:
                lines.append(("✓ GBA bitmap (Mode 4) — full screen, no tile loss.", ok))
            return kind_lines + lines
        diag = self._diag_for(ba)
        lines: list = []
        if diag and not diag.get("multiple_of_8", True):
            w, h = diag.get("src_w"), diag.get("src_h")
            lines.append((f"⚠ {w}×{h} px not a multiple of 8 — padded with transparency "
                          f"({ba.tiles_w*8}×{ba.tiles_h*8}).", warn))
        if ba.bpp == 8:
            # 8bpp : une seule palette de 256 ; perte si le source en avait plus.
            tc = diag.get("total_colors", 0)
            if tc == -1 or tc > 255:
                lines.append(("⚠ &gt; 256 colors — reduced to 256 (lossy, 8bpp mode).", warn))
            budget = 256
        else:
            mtc = diag.get("max_tile_colors", 0)
            if mtc > 15:
                n = diag.get("tiles_reduced", 0)
                lines.append((f"⚠ {n} tile(s) &gt; 15 colors (max {mtc}) — colors reduced (lossy).", warn))
            pre = diag.get("pre_merge_palettes")
            if pre and pre > 16:
                lines.append((f"⚠ {pre} palettes needed &gt; 16 — merged into {len(ba.palettes)} (lossy).", warn))
            budget = 512
        fits, bud = bg_fits_vram(ba.tileset, budget=budget)
        if not fits:
            lines.append((f"⚠ {len(ba.tileset)} unique tiles &gt; {bud} — exceeds VRAM ({ba.bpp}bpp).", err))
        if not lines and not kind_lines:
            lines.append((f"✓ GBA-compatible ({ba.bpp}bpp) — compressed losslessly.", ok))
        # Les alertes du TYPE d'abord : elles portent sur un réglage que l'auteur
        # vient de poser, celles de la compression sur ce que le PNG impose.
        return kind_lines + lines

    # ── Section PALETTES ──────────────────────────────────────────

    def _reload_palettes(self, select: int = 0):
        # Grille unifiée : palettes dérivées grisées/overridables + palettes
        # ajoutées du catalogue. La palette de PEINTURE active vit désormais dans
        # la bande en haut du canvas (rebâtie via palettes_changed → canvas.reload).
        # `select` est conservé pour la compat d'appel mais n'est plus consommé ici.
        read_only = bool(self._ba and (self._ba.mode == "bitmap" or self._ba.bpp == 8))
        view = background_palette_view(self._ba, read_only=read_only)
        catalog = list(self._project.palettes) if self._project else []
        self._pal_grid.load(view, catalog)
        self._btn_extract.setEnabled(bool(self._ba and self._ba.palettes))
        self._emit_overlays()

    def _refresh_pal_count(self):
        self._emit_overlays()

    def _persist_bg(self):
        if self._project and self._ba:
            with get_dispatcher().suspended():
                self._project.backgrounds.save(self._ba)
            get_dispatcher().notify_background_changed(self._ba)

    def _on_pal_add(self, name: str):
        """« + » : ajoute une palette du catalogue (banque `name`)."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        idx = self._ba.add_palette_colors(bank.colors)
        if idx < 0:
            QMessageBox.warning(self, "Limite atteinte",
                                "Un fond ne peut avoir que 16 palettes.")
            return
        self._persist_bg()
        self._reload_palettes()
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_pal_replace(self, idx: int, name: str):
        """Remplace une palette AJOUTÉE (index réel `idx`) par la banque `name`."""
        if not self._ba or not self._project or not (0 <= idx < len(self._ba.palettes)):
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        self._ba.replace_palette(idx, bank.colors)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_override(self, entry, name: str):
        """Override une palette DÉRIVÉE (grisée) par la banque catalogue `name` :
        ses couleurs effectives sont remplacées, l'origine PNG reste restaurable."""
        if not self._ba or not self._project:
            return
        bank = self._project.get_palette(name)
        if not bank:
            return
        self._ba.override_palette(entry.idx, name, bank.colors)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_restore(self, entry):
        """Restaure une palette dérivée overridée à ses couleurs PNG d'origine."""
        if not self._ba:
            return
        self._ba.restore_palette(entry.idx)
        self._persist_bg()
        self._reload_palettes()
        self.palettes_changed.emit()

    def _on_pal_remove(self, idx: int):
        """Retire une palette AJOUTÉE (index réel `idx`). Les tuiles qui la
        référencent retombent sur la palette 0."""
        if not self._ba or not (0 <= idx < len(self._ba.palettes)) or len(self._ba.palettes) <= 1:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la palette {idx} ?\n"
            "Les tuiles qui l'utilisent repasseront sur la palette 0.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._ba.remove_palette(idx)
        self._persist_bg()
        self._reload_palettes()
        self._refresh_pal_count()
        self.palettes_changed.emit()

    def _on_restore(self):
        if not self._project or not self._ba:
            return
        if QMessageBox.question(
            self, "Restore original",
            "Reset this background to its very first import?\n"
            "Added palettes and painting (inpainting) will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        png = self._png_path()
        if not png or not png.exists():
            QMessageBox.warning(self, "Not possible",
                                "Source PNG not found — restoration impossible.")
            return
        # Purge l'inpainting ; palettes/tileset/tilemap sont régénérés par la
        # recompression (hors-thread) depuis le PNG, dans le mode courant.
        self._ba.tile_palette_overrides = {}
        self.recompress_requested.emit(self._ba, png, self._cur_mode_token(), self._ba.dither)

    def _on_rename(self, new_name: str):
        if self._blocking or not self._ba or not self._project:
            return
        new_name = new_name.strip()
        if not new_name or new_name == self._ba.name:
            return
        if self._project.get_background(new_name):
            QMessageBox.warning(self, "Name already used",
                                f"A background named “{new_name}” already exists.")
            self._header.set_name(self._ba.name)
            return
        with get_dispatcher().suspended():
            self._project.rename_background(self._ba, new_name)
        self._header.set_name(self._ba.name)
        self.renamed.emit()

    def _png_path(self):
        img = self._ba.image_name() if self._ba else ""
        return (self._project.background_images_dir / img) if (self._project and img) else None

    def _on_extract_palette(self):
        """Promeut les sous-palettes déduites (`ba.palettes`) en PaletteBank
        partagées du catalogue projet, sous un nom stable dérivé du fond. Les
        palettes créées deviennent visibles/éditables depuis le Palette Editor
        et restent celles utilisées par ce fond (elles EN sont l'origine — le
        rendu du fond est inchangé). Une ré-extraction (après recompression)
        met à jour les mêmes banques."""
        if not self._project or not self._ba:
            return
        ba = self._ba
        pals = [list(p) for p in ba.palettes]
        if not pals:
            QMessageBox.information(
                self, "Extraction not possible",
                "This background doesn't have a palette to extract yet "
                "(uncompressed or unreadable image).")
            return
        # 256 couleurs (une banque unique) en 8bpp / bitmap ; 16 en 4bpp tuilé.
        size = 256 if (ba.mode == "bitmap" or ba.bpp == 8) else 16
        single = len(pals) == 1
        created: list[str] = []
        for i, cols in enumerate(pals):
            name = f"pal_{ba.name}" if single else f"pal_{ba.name}_{i}"
            existing = self._project.palettes.get(name)
            if existing:
                # Ré-extraction : on écrase les couleurs de la banque déjà générée
                # (action explicite, régénération attendue — cf. Sprite Editor).
                existing.colors = list(cols)
                existing.size = size
                bank = existing
            else:
                bank = PaletteBank(name=name, colors=list(cols), size=size)
            # Passe par le dispatcher : persistance (watcher suspendu) + événement
            # « palettes_changed » pour rafraîchir le Palette Editor / les finders.
            get_dispatcher().save_palette(bank)
            created.append(bank.name)
        noun = "palette" if single else "palettes"
        QMessageBox.information(
            self, "Palette extracted",
            f"{len(created)} {noun} added to the catalog and assigned to "
            f"“{ba.name}”:\n  " + "\n  ".join(created) + "\n\n"
            "They are now visible and editable from the Palette Editor.")

    def _on_replace(self):
        if not self._project or not self._ba:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "", "Images (*.png *.bmp)")
        if not path:
            return
        import shutil
        dst = self._project.background_images_dir / f"{self._ba.name}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        self._ba.asset = dst.name
        # Ré-auto-détecter le mode pour la nouvelle image (pivot indexé/non-indexé).
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, "Import", d["warning"])
        except Exception:
            token = self._cur_mode_token()
        self.recompress_requested.emit(self._ba, dst, token, self._ba.dither)


# ── Écran ───────────────────────────────────────────────────────────────────

class BackgroundEditorScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project = None
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{_BG_COLOR};}}"
        )
        # Trois sections, une par `kind` : chacune a son propre import (un PNG,
        # un cadre d'UI, une planche d'animation). Cf. ui/common/asset_kinds.py.
        self._finder = AssetFinder(
            "Background finder",
            [BACKGROUNDS_SCENE, BACKGROUNDS_UI, BACKGROUNDS_ANIM],
            min_width=180, max_width=420)
        self._canvas = BgInpaintCanvas()
        self._props = BgPropertiesPanel()
        split.addWidget(self._finder); split.addWidget(self._canvas); split.addWidget(self._props)
        split.setSizes([240, 800, 300])
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setStretchFactor(2, 0)
        root.addWidget(split)

        self._finder.selected.connect(lambda _kind, ba: self._on_selected(ba))
        self._finder.add_requested.connect(
            lambda label: self._on_import(_KIND_OF_LABEL[label]))
        self._props.changed.connect(self._canvas.reload)
        self._props.renamed.connect(self._on_renamed)
        # Mutation de la liste des palettes → re-render du canvas (sa bande de
        # peinture en tête se reconstruit alors depuis ba.palettes).
        self._props.palettes_changed.connect(self._canvas.reload)
        # Type changé : l'asset passe d'une section du finder à l'autre, et le
        # canvas change ce qu'il superpose (guides de coupe / grille de frames).
        self._props.kind_changed.connect(self._on_kind_changed)
        # Découpe (marges de coupe, taille de frame, vitesse) → le canvas
        # redessine ses guides et rejoue l'animation au nouveau rythme.
        self._props.geometry_changed.connect(self._canvas.reload_geometry)
        # Chemin INVERSE : un guide glissé au canvas écrit le modèle, l'inspecteur
        # ne fait que réaligner ses champs (cf. set_slice_margins).
        self._canvas.slices_dragged.connect(self._props.set_slice_margins)
        self._canvas.placements_changed.connect(self._on_placements_changed)
        # Sélection d'une copie posée → section PLACEMENT de l'inspecteur (même
        # bus que le reste : c'est la sélection qui décide du contexte).
        self._canvas.placement_selected.connect(self._props.set_placement)
        # Chemin inverse : régler la cadence ou l'image de départ d'une copie
        # doit se voir tout de suite — c'est la seule raison de la régler ici
        # plutôt que dans un fichier.
        self._props.placement_changed.connect(self._canvas.reload_geometry)
        # Infos read-only + warnings → overlays du canvas (bas-gauche / haut-droite).
        self._props.overlays_changed.connect(self._canvas.set_overlays)
        # (Re)compression demandée par l'inspecteur (algo / remplacer / restaurer)
        # → exécutée hors-thread par l'écran.
        self._props.recompress_requested.connect(self._on_recompress)

        # Compression hors-thread : jeton pour ignorer les résultats périmés
        # (l'utilisateur peut relancer avant la fin), + refs pour éviter le GC.
        self._compress_token = 0
        self._compress_tasks: set = set()

    def load_project(self, project):
        self._project = project
        self._finder.load_project(project)
        self._refresh_finder()

    def select_background(self, name: str):
        """Ouvre le fond `name` — navigation entrante depuis un autre écran
        (ex. carte « Utilisations » du Palette Editor)."""
        self._refresh_finder(select=name)

    def _refresh_finder(self, select: str = None):
        """Repeuple les trois sections et met à l'écran le fond `select` — ou le
        premier trouvé, à défaut. La sélection est posée SIGNAUX COUPÉS puis
        notifiée à la main : `select()` ne réémet rien si la ligne était déjà
        courante, alors que l'appelant attend un rafraîchissement (renommage,
        recompression)."""
        self._finder.refresh()
        bgs = list(self._project.backgrounds) if self._project else []
        target = next((b for b in bgs if b.name == select), None)
        if target is None:
            target = bgs[0] if bgs else None
        if target is None:
            self._finder.clear_selection()
            self._on_selected(None)
            return
        self._finder.blockSignals(True)
        self._finder.select(_LABEL_OF_KIND.get(target.kind, ""), target)
        self._finder.blockSignals(False)
        self._on_selected(target)

    # ── Compression hors-thread ───────────────────────────────────

    def _compress_async(self, ba, png_path, mode, method, dither, then=None):
        """Compresse `png_path` dans un worker (mode token tiled4/tiled8/bitmap)
        puis applique le résultat à `ba` sur le thread UI. Non-bloquant."""
        if not self._project or not png_path or not Path(png_path).exists():
            return
        self._compress_token += 1
        token = self._compress_token
        self._canvas.set_busy(True)

        task = _EncodeTask(token, Path(png_path), mode, method or ba.quantize_method, dither)

        def _done(tok, name, c):
            self._compress_tasks.discard(task)
            if tok != self._compress_token:
                return  # résultat périmé (une compression plus récente a été lancée)
            from core import asset_encoding
            asset_encoding.apply_bg_encoding(ba, name, c)
            with get_dispatcher().suspended():
                self._project.backgrounds.save(ba)
            get_dispatcher().notify_background_changed(ba)
            self._canvas.set_busy(False)
            if then:
                then()

        def _failed(tok, msg):
            self._compress_tasks.discard(task)
            if tok != self._compress_token:
                return
            self._canvas.set_busy(False)
            QMessageBox.warning(self, "Compression failed",
                                f"Could not compress the background:\n{msg}")

        task.signals.done.connect(_done)
        task.signals.failed.connect(_failed)
        self._compress_tasks.add(task)
        QThreadPool.globalInstance().start(task)

    def _on_recompress(self, ba, png_path, mode, dither):
        self._compress_async(
            ba, png_path, mode, ba.quantize_method, dither,
            then=lambda: (self._props.load(ba, self._project), self._canvas.reload()))

    def _on_selected(self, ba):
        # Charger le canvas AVANT l'inspecteur : le canvas bâtit sa bande de
        # peinture depuis `ba` (palette active de peinture) ; l'inspecteur suit.
        self._canvas.load(self._project, ba)
        self._props.load(ba, self._project)

    def _on_renamed(self):
        # Renommage validé depuis l'en-tête de l'inspecteur : réaligner le finder
        # sur le nouveau nom (il émettra bg_selected → recharge preview + props).
        ba = self._props._ba
        if ba:
            self._refresh_finder(select=ba.name)

    def _on_kind_changed(self):
        ba = self._props._ba
        if ba:
            self._refresh_finder(select=ba.name)

    def _on_placements_changed(self):
        """Un fond animé posé, déplacé ou retiré : l'inspecteur n'en montre que
        le compte, mais c'est ce compte qui dit à l'auteur que son geste a pris."""
        self._props._emit_overlays()

    def _on_import(self, kind: str = KIND_SCENE):
        if not self._project:
            return
        title = {KIND_SCENE: "Import a background",
                 KIND_UI: "Import a UI background",
                 KIND_ANIMATED: "Import an animation sheet"}.get(kind, "Import a background")
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Images (*.png *.bmp)")
        if not path:
            return
        dst = self._project.import_asset(Path(path), "backgrounds")
        name = dst.stem
        ba = self._project.get_background(name)
        if ba is None:
            from core.models.background import BackgroundAsset
            ba = BackgroundAsset(name=name, asset=dst.name)
            self._project.backgrounds.append(ba)
        # Le type vient du « + » sur lequel on a cliqué : la section où l'auteur
        # range l'image dit son emploi mieux que n'importe quelle heuristique
        # (rien dans les pixels ne distingue un cadre de dialogue d'un décor).
        ba.kind = kind
        # Auto-détection unifiée (pivot indexé/non-indexé) : profondeur ← couleurs,
        # layout tuilé/bitmap ← unicité des tuiles.
        from core.bg_import import detect_import_mode
        try:
            d = detect_import_mode(dst)
            token = d["token"]
            if d["warning"]:
                QMessageBox.information(self, "Import", d["warning"])
        except Exception:
            token = "tiled4"
        if kind != KIND_SCENE and token.startswith("bitmap"):
            # Un cadre et une planche de frames sont des TUILES : le Mode 4 n'a
            # pas de tilemap où répéter un bord ni où poser une frame. On garde
            # la profondeur détectée et on retombe sur le layout tuilé, plutôt
            # que d'importer un asset que rien ne saura dessiner.
            token = "tiled8"
        # Sélectionner immédiatement (canvas vide + « Compression… ») puis
        # compresser hors-thread — l'éditeur n'est jamais bloqué.
        self._refresh_finder(select=ba.name)
        self._compress_async(
            ba, dst, token, ba.quantize_method, ba.dither,
            then=lambda: self._after_import(ba))

    def _after_import(self, ba):
        """Réglages qui ne peuvent se poser qu'une fois la taille CONNUE — donc
        après la compression, qui est ce qui la fixe."""
        if ba.kind == KIND_ANIMATED and not (ba.frame_w or ba.frame_h):
            from core.models.background import guess_frame_size
            ba.frame_w, ba.frame_h = guess_frame_size(*ba.pixel_size())
            with get_dispatcher().suspended():
                self._project.backgrounds.save(ba)
        self._on_selected(ba)
