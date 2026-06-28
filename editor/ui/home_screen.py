"""
ui/home_screen.py — Écran d'accueil du GBA Editor.

Affiché au démarrage si aucun projet n'est ouvert.
Liste les projets récents (persistés via QSettings) et permet
de créer ou d'ouvrir un projet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QInputDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QColor

from ui.theme import C, T

# ── Persistance ───────────────────────────────────────────────────────

_SETTINGS_ORG = "GBAEditor"
_SETTINGS_APP = "GBAEditor"
_KEY_RECENTS   = "recent_projects"
_MAX_RECENTS   = 12


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def get_recents() -> list[dict]:
    """Retourne la liste des projets récents [{name, path, last_opened}]."""
    raw = _settings().value(_KEY_RECENTS, "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


def add_recent(path: Path, name: str) -> None:
    """Ajoute ou remonte un projet en tête de liste."""
    recents = [r for r in get_recents() if r["path"] != str(path)]
    recents.insert(0, {
        "name":        name,
        "path":        str(path),
        "last_opened": datetime.now(timezone.utc).isoformat(),
    })
    s = _settings()
    s.setValue(_KEY_RECENTS, json.dumps(recents[:_MAX_RECENTS]))
    s.sync()


def remove_recent(path: Path) -> None:
    recents = [r for r in get_recents() if r["path"] != str(path)]
    s = _settings()
    s.setValue(_KEY_RECENTS, json.dumps(recents))
    s.sync()


def _relative_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        s = int(delta.total_seconds())
        if s < 60:        return "à l'instant"
        if s < 3600:      return f"il y a {s // 60} min"
        if s < 86400:     return f"il y a {s // 3600} h"
        if s < 86400 * 7: return f"il y a {s // 86400} j"
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return ""


# ── Carte projet récent ───────────────────────────────────────────────

class _ProjectCard(QFrame):
    clicked = pyqtSignal(str)   # émet le chemin

    def __init__(self, name: str, path: str, last_opened: str,
                 exists: bool, parent=None):
        super().__init__(parent)
        self._path = path
        self._exists = exists

        self.setFixedHeight(68)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if exists
            else Qt.CursorShape.ForbiddenCursor
        )
        alpha = "ff" if exists else "55"
        self.setStyleSheet(
            f"QFrame{{background:#1e1e1e{alpha};border:1px solid #2a2a2a;"
            f"border-radius:6px;}}"
            f"QFrame:hover{{border-color:{'#4caf78' if exists else '#333'};"
            f"background:{'#222222' if exists else '#1a1a1a'}ff;}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        # Icône GBA (texte)
        icon = QLabel("▣")
        icon.setFont(QFont(T.MONO, T.XL))
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color:{'#4caf78' if exists else '#333'};background:transparent;"
        )
        layout.addWidget(icon)

        # Textes
        txt = QVBoxLayout()
        txt.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        name_lbl.setStyleSheet(
            f"color:{'#eeeeee' if exists else '#555'};background:transparent;"
        )
        txt.addWidget(name_lbl)

        path_text = path if exists else f"⚠  introuvable — {path}"
        path_lbl = QLabel(path_text)
        path_lbl.setFont(QFont(T.MONO, T.XS))
        path_lbl.setStyleSheet(
            f"color:{'#555' if exists else '#7a3a3a'};background:transparent;"
        )
        path_lbl.setWordWrap(False)
        txt.addWidget(path_lbl)

        layout.addLayout(txt, 1)

        # Date
        if last_opened:
            date_lbl = QLabel(_relative_time(last_opened))
            date_lbl.setFont(QFont(T.MONO, T.XS))
            date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            date_lbl.setStyleSheet("color:#444;background:transparent;")
            layout.addWidget(date_lbl)

    def mousePressEvent(self, event):
        if self._exists and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._path)


# ── Écran d'accueil ───────────────────────────────────────────────────

class HomeScreen(QWidget):
    """Écran d'accueil — projets récents + créer / ouvrir."""

    new_project_requested    = pyqtSignal(str, str)  # (name, path)
    open_project_requested   = pyqtSignal(str)        # path
    recent_project_requested = pyqtSignal(str)        # path

    def __init__(self, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._build_ui()

    # ── Construction ─────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Zone centrale scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background:{C.BG_BASE};border:none;")

        inner = QWidget()
        inner.setStyleSheet(f"background:{C.BG_BASE};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(0, 60, 0, 60)
        vl.setSpacing(0)
        vl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # ── Hero ─────────────────────────────────────────────────────
        hero = QWidget()
        hero.setFixedWidth(640)
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(0, 0, 0, 48)
        hero_l.setSpacing(8)
        hero_l.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title = QLabel("GBA Editor")
        title.setFont(QFont(T.MONO, 32, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        hero_l.addWidget(title)

        tagline = QLabel("Créez des jeux pour Game Boy Advance")
        tagline.setFont(QFont(T.MONO, T.MD))
        tagline.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")
        hero_l.addWidget(tagline)

        # Boutons d'action
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setContentsMargins(0, 24, 0, 0)

        btn_new = QPushButton("  + Nouveau projet")
        btn_new.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        btn_new.setFixedHeight(42)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT_GRN};color:#0a1a0a;"
            f"border:none;border-radius:5px;padding:0 24px;}}"
            f"QPushButton:hover{{background:#5abf88;}}"
        )
        btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(btn_new)

        btn_open = QPushButton("  ⊕ Ouvrir…")
        btn_open.setFont(QFont(T.MONO, T.MD))
        btn_open.setFixedHeight(42)
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C.TEXT_NORM};"
            f"border:1px solid #333;border-radius:5px;padding:0 24px;}}"
            f"QPushButton:hover{{border-color:#555;color:{C.TEXT_HI};"
            f"background:{C.BG_PANEL};}}"
        )
        btn_open.clicked.connect(self._on_open)
        btn_row.addWidget(btn_open)

        btn_row.addStretch()
        hero_l.addLayout(btn_row)
        vl.addWidget(hero, 0, Qt.AlignmentFlag.AlignHCenter)

        # ── Séparateur ───────────────────────────────────────────────
        sep_lbl = QLabel("PROJETS RÉCENTS")
        sep_lbl.setFixedWidth(640)
        sep_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        sep_lbl.setStyleSheet(
            f"color:{C.TEXT_MUTED};background:transparent;"
            "letter-spacing:2px;padding-bottom:12px;"
        )
        vl.addWidget(sep_lbl, 0, Qt.AlignmentFlag.AlignHCenter)

        # ── Liste des projets récents ─────────────────────────────────
        self._recents_container = QWidget()
        self._recents_container.setFixedWidth(640)
        self._recents_layout = QVBoxLayout(self._recents_container)
        self._recents_layout.setContentsMargins(0, 0, 0, 0)
        self._recents_layout.setSpacing(6)
        self._populate_recents()
        vl.addWidget(self._recents_container, 0, Qt.AlignmentFlag.AlignHCenter)

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _populate_recents(self):
        # Vider
        while self._recents_layout.count():
            item = self._recents_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        recents = get_recents()
        if not recents:
            empty = QLabel("Aucun projet récent")
            empty.setFont(QFont(T.MONO, T.SM))
            empty.setStyleSheet(f"color:{C.TEXT_MUTED};background:transparent;padding:16px 0;")
            self._recents_layout.addWidget(empty)
            return

        for r in recents:
            path = r.get("path", "")
            exists = Path(path).exists()
            card = _ProjectCard(
                name=r.get("name", Path(path).name),
                path=path,
                last_opened=r.get("last_opened", ""),
                exists=exists,
            )
            card.clicked.connect(self.recent_project_requested)
            self._recents_layout.addWidget(card)

    def refresh(self):
        """Recharge la liste après ouverture d'un projet."""
        self._populate_recents()

    # ── Actions ──────────────────────────────────────────────────────

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "Nouveau projet", "Nom du projet :",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        path = self._projects_dir / name
        if path.exists():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Projet existant",
                f"Un dossier « {name} » existe déjà dans {self._projects_dir}."
            )
            return
        self.new_project_requested.emit(name, str(path))

    def _on_open(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Ouvrir un projet GBA",
            str(self._projects_dir),
        )
        if folder:
            self.open_project_requested.emit(folder)
