"""ui/common/reveal.py — ouvrir l'explorateur de fichiers du système sur le
dossier RÉEL d'une famille d'assets.

Un finder liste ce qu'un projet contient, mais l'utilisateur retrouve parfois
plus vite un fichier en le manipulant directement sur le disque (le glisser
ailleurs, l'ouvrir avec un autre outil, vérifier ce qui traîne à côté). Ce
module ne fait qu'ouvrir le dossier — jamais un fichier précis : révéler UN
asset supposerait que l'explorateur du système sache le sélectionner, ce que
Qt ne garantit pas hors Windows/macOS.
"""
from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def reveal_in_file_manager(path) -> None:
    """Ouvre `path` (ou son dossier parent si c'est un fichier) dans
    l'explorateur de fichiers par défaut du système. Silencieux si `path` est
    vide ou n'existe pas encore — pas de message d'erreur pour un dossier
    qu'un projet fraîchement créé n'a simplement pas encore créé sur disque."""
    if not path:
        return
    p = Path(path)
    target = p if p.is_dir() else p.parent
    if not target.exists():
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
