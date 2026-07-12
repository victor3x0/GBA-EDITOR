"""ui/background_editor/background_editor_screen.py — écran Background Editor.

3 colonnes : finder (assets/backgrounds) · preview de l'image compressée ·
propriétés (dimensions, tuiles uniques/budget, palettes, algo de compression).
La compression est non-destructive (cf. core/bg_compress) — le PNG n'est jamais
modifié, tout vit en métadonnées dans le .json du BackgroundAsset.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QComboBox, QFileDialog, QFrame,
)
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import W, FinderSection
from core.command_dispatcher import get_dispatcher
from core.color_utils import COMPRESSION_METHODS
from core.bg_compress import render_bg_preview, bg_fits_vram, TILE_BUDGET

_BG_COLOR = C.ACCENT_BLU


def _ba_pixmap(ba) -> Optional[QPixmap]:
    if not ba or not ba.tileset:
        return None
    img = render_bg_preview({
        "tiles_w": ba.tiles_w, "tiles_h": ba.tiles_h,
        "tileset": ba.tileset, "palettes": ba.palettes, "tilemap": ba.tilemap,
    })
    data = img.tobytes("raw", "RGBA")
    qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)


def import_background(project, parent=None):
    """Choisit un PNG, le copie dans assets/backgrounds/ (intact) et crée le
    BackgroundAsset (compression calculée). Retourne le BA ou None."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Importer un fond", "", "Images (*.png *.bmp)")
    if not path:
        return None
    dst = project.import_asset(Path(path), "backgrounds")
    project.sync_background_png(dst)
    return project.get_background(Path(dst).stem)


# ── Finder (gauche) ─────────────────────────────────────────────────────────

class BgFinderPanel(QWidget):
    bg_selected  = pyqtSignal(object)   # BackgroundAsset
    import_asked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180); self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        hdr = QFrame(); hdr.setFixedHeight(20)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(8, 0, 0, 0)
        lbl = QLabel("BACKGROUND FINDER")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        hl.addWidget(lbl); root.addWidget(hdr)

        sec = FinderSection("BACKGROUNDS", _BG_COLOR)
        sec.set_add_tooltip("Importer un PNG")
        sec.add_clicked.connect(self.import_asked)
        root.addWidget(sec, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
            f"QListWidget::item{{padding:4px 6px;}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL}; color:{_BG_COLOR};"
            f"border-left:2px solid {_BG_COLOR};}}"
        )
        self._list.currentItemChanged.connect(self._on_sel)
        sec.set_widget(self._list)

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self, select: str = None):
        self._list.blockSignals(True)
        self._list.clear()
        for ba in (list(self._project.backgrounds) if self._project else []):
            it = QListWidgetItem(ba.name)
            it.setData(Qt.ItemDataRole.UserRole, ba)
            self._list.addItem(it)
        self._list.blockSignals(False)
        target = select or (self._list.item(0).text() if self._list.count() else None)
        for i in range(self._list.count()):
            if self._list.item(i).text() == target:
                self._list.setCurrentRow(i); break

    def _on_sel(self, cur, _prev):
        if cur:
            self.bg_selected.emit(cur.data(Qt.ItemDataRole.UserRole))


# ── Preview (centre) ────────────────────────────────────────────────────────

class BgPreviewPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet(f"QScrollArea{{background:{C.BG_DEEP}; border:none;}}")
        self._label = QLabel(); self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"background:{C.BG_DEEP}; color:{C.TEXT_DIM};")
        self.setWidget(self._label)

    def load(self, ba):
        pm = _ba_pixmap(ba)
        if pm is None:
            self._label.setText("Aucun fond compressé.\nImporte un PNG.")
            self._label.setPixmap(QPixmap())
        else:
            self._label.setText("")
            self._label.setPixmap(pm)
            self._label.resize(pm.size())


# ── Propriétés (droite) ─────────────────────────────────────────────────────

class BgPropertiesPanel(QWidget):
    changed = pyqtSignal()   # compression recalculée → rafraîchir la preview

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220); self.setMaximumWidth(440)
        self.setStyleSheet(f"background:{C.BG_PANEL}; border-left:1px solid {C.BORDER_DARK};")
        self._project = None
        self._ba = None
        self._blocking = False

        root = QVBoxLayout(self); root.setContentsMargins(10, 8, 10, 8); root.setSpacing(2)
        self._name = QLabel("—"); self._name.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        self._name.setStyleSheet(f"color:{C.TEXT_HI};")
        root.addWidget(self._name)

        W.separator(root); W.section("IMAGE", root)
        self._dims = self._info_label(); root.addWidget(self._dims)

        W.separator(root); W.section("COMPRESSION", root)
        self._tiles = self._info_label(); root.addWidget(self._tiles)
        self._pals = self._info_label(); root.addWidget(self._pals)

        self._cb = QComboBox(); self._cb.setFont(QFont(T.MONO, T.SM))
        for tok, label in COMPRESSION_METHODS:
            self._cb.addItem(label, tok)
        self._cb.currentIndexChanged.connect(self._on_method)
        W.row("Algo", self._cb, root)

        W.separator(root)
        self._btn = W.btn_accent("⟐  Importer / remplacer l'image…")
        self._btn.clicked.connect(self._on_replace)
        root.addWidget(self._btn)
        root.addStretch()

    def _info_label(self):
        l = QLabel("—"); l.setFont(QFont(T.MONO, T.SM)); l.setWordWrap(True)
        l.setStyleSheet(f"color:{C.TEXT_NORM};")
        return l

    def load(self, ba, project):
        self._project, self._ba = project, ba
        self._blocking = True
        self._name.setText(ba.name if ba else "—")
        if ba and ba.tileset:
            self._dims.setText(f"{ba.tiles_w*8}×{ba.tiles_h*8} px  ({ba.tiles_w}×{ba.tiles_h} tuiles)")
            n = len(ba.tileset); fits, budget = bg_fits_vram(ba.tileset)
            col = C.TEXT_NORM if fits else "#e06060"
            self._tiles.setStyleSheet(f"color:{col};")
            self._tiles.setText(f"Tuiles uniques : {n} / {budget}"
                                + ("" if fits else "  ⚠ dépasse la VRAM"))
            self._pals.setText(f"Palettes : {len(ba.palettes)} / 16")
            mi = self._cb.findData(getattr(ba, "compress_method", "median_cut"))
            self._cb.setCurrentIndex(mi if mi >= 0 else 0)
        else:
            for l in (self._dims, self._tiles, self._pals):
                l.setText("—")
        self._blocking = False

    def _png_path(self):
        img = self._ba.image_name() if self._ba else ""
        return (self._project.background_images_dir / img) if (self._project and img) else None

    def _on_method(self, _):
        if self._blocking or not self._ba or not self._project:
            return
        ap = self._png_path()
        if not ap or not ap.exists():
            return
        self._project._compress_background_asset(self._ba, ap, self._cb.currentData())
        with get_dispatcher().suspended():
            self._project.backgrounds.save(self._ba)
        self.load(self._ba, self._project)
        self.changed.emit()

    def _on_replace(self):
        if not self._project or not self._ba:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "", "Images (*.png *.bmp)")
        if not path:
            return
        import shutil
        dst = self._project.background_images_dir / f"{self._ba.name}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        self._ba.source = dst.name
        self._project._compress_background_asset(self._ba, dst, self._cb.currentData())
        with get_dispatcher().suspended():
            self._project.backgrounds.save(self._ba)
        self.load(self._ba, self._project)
        self.changed.emit()


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
        self._finder = BgFinderPanel()
        self._preview = BgPreviewPanel()
        self._props = BgPropertiesPanel()
        split.addWidget(self._finder); split.addWidget(self._preview); split.addWidget(self._props)
        split.setSizes([240, 800, 300])
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setStretchFactor(2, 0)
        root.addWidget(split)

        self._finder.bg_selected.connect(self._on_selected)
        self._finder.import_asked.connect(self._on_import)
        self._props.changed.connect(lambda: self._preview.load(self._props._ba))

    def load_project(self, project):
        self._project = project
        self._finder.load_project(project)

    def _on_selected(self, ba):
        self._preview.load(ba)
        self._props.load(ba, self._project)

    def _on_import(self):
        if not self._project:
            return
        ba = import_background(self._project, self)
        if ba:
            self._finder.refresh(select=ba.name)
