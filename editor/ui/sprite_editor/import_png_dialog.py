"""ui/sprite_editor/import_png_dialog.py — import & compression NON-DESTRUCTIVE.

Le PNG source de l'utilisateur n'est JAMAIS modifié. L'import calcule la
compression (palette propre + algo) et la stocke en MÉTADONNÉES sur le
SpriteAsset (JSON). La représentation indexée est dérivée à la volée
(preview + build) depuis `source + own_palette`.
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog,
)
from PyQt6.QtGui import QFont, QPixmap, QImage
from PyQt6.QtCore import Qt

from ui.common.theme import C, T
from core.color_utils import (
    COMPRESSION_METHODS, own_palette_from_source, render_indexed, _distinct_opaque,
)
from core.command_dispatcher import get_dispatcher

_MAX_COLORS = 15


def _pil_to_pixmap(img, box: int = 128) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qi = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    pm = QPixmap.fromImage(qi)
    return pm.scaled(box, box, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.FastTransformation)


class CompressionDialog(QDialog):
    """Choix de l'algorithme de compression quand un PNG dépasse 15 couleurs
    opaques. Aperçu du résultat (dérivé, source jamais modifié) + nombre de
    couleurs, mis à jour à chaque changement d'algo. Retourne
    (own_palette, method)."""

    def __init__(self, rgba_img, n_colors: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compresser le sprite")
        self.setStyleSheet(f"background:{C.BG_PANEL}; color:{C.TEXT_NORM};")
        self._rgba = rgba_img
        self._palette: list = []
        self._method: str = COMPRESSION_METHODS[0][0]

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        info = QLabel(
            f"L'image contient {n_colors} couleurs opaques — un sprite est "
            f"limité à {_MAX_COLORS} (index 0 réservé à la transparence). Le PNG "
            f"n'est PAS modifié : la compression est enregistrée dans le sprite.\n"
            f"Choisis l'algorithme de réduction :"
        )
        info.setWordWrap(True)
        info.setFont(QFont(T.MONO, T.SM))
        root.addWidget(info)

        self._combo = QComboBox()
        self._combo.setFont(QFont(T.MONO, T.SM))
        for token, label in COMPRESSION_METHODS:
            self._combo.addItem(label, token)
        self._combo.currentIndexChanged.connect(self._refresh_preview)
        root.addWidget(self._combo)

        prev_row = QHBoxLayout()
        self._before = QLabel(); self._before.setFixedSize(128, 128)
        self._before.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._before.setStyleSheet(f"border:1px solid {C.BORDER}; background:{C.BG_DEEP};")
        self._before.setPixmap(_pil_to_pixmap(rgba_img))
        self._after = QLabel(); self._after.setFixedSize(128, 128)
        self._after.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._after.setStyleSheet(f"border:1px solid {C.BORDER}; background:{C.BG_DEEP};")
        col_b = QVBoxLayout(); col_b.addWidget(QLabel("Original")); col_b.addWidget(self._before)
        col_a = QVBoxLayout(); self._after_lbl = QLabel("Compressé")
        col_a.addWidget(self._after_lbl); col_a.addWidget(self._after)
        prev_row.addLayout(col_b); prev_row.addLayout(col_a)
        root.addLayout(prev_row)

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("Annuler"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Appliquer"); ok.setDefault(True); ok.clicked.connect(self.accept)
        for b in (cancel, ok):
            b.setFont(QFont(T.MONO, T.SM)); b.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"QPushButton{{background:{C.BG_SEL}; color:{C.ACCENT_GRN}; "
                         f"padding:5px 16px; border:none; border-radius:3px;}}")
        cancel.setStyleSheet(f"QPushButton{{padding:5px 16px; border:1px solid {C.BORDER}; "
                             f"border-radius:3px;}}")
        btns.addWidget(cancel); btns.addWidget(ok)
        root.addLayout(btns)

        self._refresh_preview()

    def _refresh_preview(self):
        self._method = self._combo.currentData()
        self._palette = own_palette_from_source(self._rgba, self._method)
        self._after_lbl.setText(f"Compressé — {len(self._palette)} couleurs")
        self._after.setPixmap(_pil_to_pixmap(render_indexed(self._rgba, self._palette)))

    def result(self) -> tuple[list, str]:
        return self._palette, self._method


def choose_compression(source, parent=None) -> Optional[tuple[list, str]]:
    """Retourne (own_palette BGR555, method) pour `source` (chemin/image). Si
    <=15 couleurs opaques : median-cut direct (sans perte, sans dialogue). Sinon
    ouvre CompressionDialog. None si annulé. Ne modifie jamais le source."""
    from PIL import Image
    img = source if hasattr(source, "mode") else Image.open(source)
    rgba = img.convert("RGBA")
    order, _counts = _distinct_opaque(rgba)
    if len(order) <= _MAX_COLORS:
        return own_palette_from_source(rgba, "median_cut"), "median_cut"
    dlg = CompressionDialog(rgba, len(order), parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.result()


def _store(project, sprite, palette: list, method: str):
    sprite.own_palette = palette
    sprite.compress_method = method
    get_dispatcher().save_sprite(sprite)


def import_new_sprite(project, parent=None) -> Optional[Path]:
    """Choisit un fichier, le COPIE tel quel dans assets/sprites/, crée le sprite
    et calcule sa compression (métadonnées). Retourne le chemin ou None."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Importer une image", "", "Images (*.png *.bmp)")
    if not path:
        return None
    res = choose_compression(path, parent)
    if res is None:
        return None
    dst = project.import_asset(Path(path), "sprites")   # copie le source intact
    sprite = project.sync_sprite_png(dst)
    _store(project, sprite, *res)
    return dst


def reindex_sprite(project, sprite, parent=None) -> bool:
    """Recalcule la compression du sprite courant (algo au choix) et la stocke
    en métadonnées. Le PNG source n'est PAS touché. True si appliqué."""
    if not sprite or not sprite.asset:
        return False
    ap = project.root / sprite.asset
    if not ap.exists():
        return False
    res = choose_compression(ap, parent)
    if res is None:
        return False
    _store(project, sprite, *res)
    return True


def replace_sprite_image(project, sprite, parent=None) -> bool:
    """Choisit un nouveau fichier, le COPIE tel quel comme source du sprite
    courant, et recalcule sa compression. True si appliqué."""
    if not sprite:
        return False
    path, _ = QFileDialog.getOpenFileName(
        parent, "Choisir une image", "", "Images (*.png *.bmp)")
    if not path:
        return False
    res = choose_compression(path, parent)
    if res is None:
        return False
    dst_dir = project.assets_dir / "sprites"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{sprite.name}.png"
    shutil.copy2(path, dst)            # copie du source, jamais réécrit
    sprite.asset = project.asset_rel(dst)
    _store(project, sprite, *res)
    return True
