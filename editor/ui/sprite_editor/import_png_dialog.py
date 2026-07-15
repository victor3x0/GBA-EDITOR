"""ui/sprite_editor/import_png_dialog.py — import sprite NON-DESTRUCTIF.

Aligné sur le pipeline background : Watcher/UI → **Validator** (detect_sprite_import_mode)
→ **Encodage** (encode_sprite, métadonnées) → asset éditable. Le PNG source n'est
JAMAIS modifié ; la PAL_BANK (sous-palettes) + le pont de compat `own_palette`
vivent dans le .json du sprite. Plus de dialogue de compression modal — l'algo se
règle dans l'éditeur (comme le mode d'un background dans son inspecteur).
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from core.sprite_import import encode_sprite, detect_sprite_import_mode
from core.command_dispatcher import get_dispatcher


def _encode_and_store(project, sprite, source) -> Optional[str]:
    """Encode `source` sur `sprite` (métadonnées, PNG intact) + persiste via le
    dispatcher. Renvoie un warning d'import éventuel (palette réduite)."""
    from core.project import Project
    warning = detect_sprite_import_mode(source).get("warning")
    Project.apply_sprite_encoding(sprite, encode_sprite(source, sprite.quantize_method))
    get_dispatcher().save_sprite(sprite)
    return warning


def import_new_sprite(project, parent=None) -> Optional[Path]:
    """Choisit un fichier, le COPIE tel quel dans assets/sprites/, crée le sprite
    et l'encode (Validator → Encodage). Retourne le chemin ou None."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Importer une image", "", "Images (*.png *.bmp)")
    if not path:
        return None
    dst = project.import_asset(Path(path), "sprites")   # copie le source intact
    warning = project.sync_sprite_png(dst)              # détection + encodage + save
    if warning and parent is not None:
        QMessageBox.information(parent, "Import sprite", warning)
    return dst


def replace_sprite_image(project, sprite, parent=None) -> bool:
    """Choisit un nouveau fichier, le COPIE comme source du sprite courant, et le
    ré-encode (PNG jamais réécrit). True si appliqué."""
    if not sprite:
        return False
    path, _ = QFileDialog.getOpenFileName(
        parent, "Choisir une image", "", "Images (*.png *.bmp)")
    if not path:
        return False
    dst_dir = project.assets_dir / "sprites"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{sprite.name}.png"
    shutil.copy2(path, dst)            # copie du source, jamais réécrit
    sprite.asset = project.asset_rel(dst)
    warning = _encode_and_store(project, sprite, dst)
    if warning and parent is not None:
        QMessageBox.information(parent, "Remplacement sprite", warning)
    return True
