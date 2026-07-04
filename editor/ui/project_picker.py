"""
ui/project_picker.py — HomeScreen : écran d'accueil affiché au lancement.

• Liste les projets récemment ouverts (stockée dans ~/.gba_editor_recent.json)
• Double-clic ou Ouvrir → ouvre le projet
• Nouveau → crée un nouveau projet dans PROJECTS_DIR
• Clear list → supprime les entrées qui pointent vers des dossiers morts
• Statut devkitPro / mGBA avec lien de téléchargement discret si manquant
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QFileDialog, QSizePolicy,
    QLineEdit, QWidget,
)
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from ui.theme import C, T, QSS

# toolchain est dans editor/, un niveau au-dessus
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.toolchain import Toolchain, DEVKITPRO_URL, MGBA_URL

PROJECTS_DIR  = Path.home() / "GBAProjects"
_RECENT_FILE  = Path.home() / ".gba_editor_recent.json"
_MAX_RECENT   = 12


# ── Persistance des récents ───────────────────────────────────────────

def load_recent() -> list[Path]:
    try:
        data = json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
        return [Path(p) for p in data if isinstance(p, str)]
    except Exception:
        return []


def save_recent(paths: list[Path]):
    try:
        _RECENT_FILE.write_text(
            json.dumps([str(p) for p in paths[:_MAX_RECENT]]),
            encoding="utf-8",
        )
    except Exception:
        pass


def push_recent(path: Path):
    recent = load_recent()
    recent = [p for p in recent if p != path]
    recent.insert(0, path)
    save_recent(recent[:_MAX_RECENT])


# ── Statut toolchain (devkitPro / mGBA) ─────────────────────────────────

class ToolchainStatus(QWidget):
    """
    Statut discret devkitPro / mGBA sur l'écran d'accueil.
    Une explication + un lien de téléchargement n'apparaissent que pour ce
    qui manque, sans bloquer l'utilisateur — pas de popup forcé au lancement.
    """

    configure_requested = pyqtSignal()

    _EXPLAIN = {
        "devkitPro": "la chaîne de compilation (ARM + grit) qui transforme ton projet en ROM .gba jouable",
        "mGBA":      "l'émulateur utilisé pour lancer et tester ta ROM directement depuis l'éditeur",
    }

    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self._toolchain = toolchain
        self.setStyleSheet("background:transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.refresh()

    def refresh(self):
        """Relance la détection et reconstruit l'affichage."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        checks = [
            ("devkitPro", self._toolchain.devkitpro_ok, DEVKITPRO_URL),
            ("mGBA",      self._toolchain.mgba_ok,      MGBA_URL),
        ]
        missing = [c for c in checks if not c[1]]

        row = QWidget()
        row.setStyleSheet("background:transparent;")
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(16)
        for name, ok, _ in checks:
            lbl = QLabel(f"{'✓' if ok else '✗'} {name}")
            lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            lbl.setStyleSheet(
                f"color:{'#4caf78' if ok else '#a05050'};background:transparent;"
            )
            row_l.addWidget(lbl)
        row_l.addStretch()

        cfg = QLabel('<a href="#" style="color:#555;text-decoration:none;">⚙ Configurer manuellement</a>')
        cfg.setFont(QFont(T.MONO, T.XS))
        cfg.setStyleSheet("background:transparent;")
        cfg.linkActivated.connect(lambda _: self.configure_requested.emit())
        row_l.addWidget(cfg)

        self._layout.addWidget(row)

        for name, ok, url in missing:
            expl = QLabel(
                f'<span style="color:#666;">{name} — {self._EXPLAIN[name]}. '
                f'<a href="{url}" style="color:#4c8caf;">Télécharger →</a></span>'
            )
            expl.setFont(QFont(T.MONO, T.XS))
            expl.setStyleSheet("background:transparent;")
            expl.setOpenExternalLinks(True)
            expl.setWordWrap(True)
            self._layout.addWidget(expl)


# ── Widget d'une entrée ───────────────────────────────────────────────

class _ProjectItem(QWidget):
    def __init__(self, path: Path, dead: bool = False, parent=None):
        super().__init__(parent)
        self.path = path
        self.dead = dead

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(10)

        # Icône dossier
        icon = QLabel("📁" if not dead else "⚠")
        icon.setFont(QFont(T.MONO, 16))
        icon.setFixedWidth(28)
        icon.setStyleSheet("background:transparent;")
        hl.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)

        name_lbl = QLabel(path.name)
        name_lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        name_lbl.setStyleSheet(
            f"color:{'#888' if dead else C.TEXT_HI};background:transparent;"
        )
        col.addWidget(name_lbl)

        path_lbl = QLabel(str(path))
        path_lbl.setFont(QFont(T.MONO, T.XS))
        path_lbl.setStyleSheet(
            f"color:{'#e05555' if dead else C.TEXT_DIM};background:transparent;"
        )
        path_lbl.setWordWrap(False)
        col.addWidget(path_lbl)

        hl.addLayout(col, 1)

        if dead:
            dead_badge = QLabel("introuvable")
            dead_badge.setFont(QFont(T.MONO, T.XS))
            dead_badge.setStyleSheet(
                "color:#e05555;background:#2a1a1a;border:1px solid #e05555;"
                "border-radius:3px;padding:1px 5px;"
            )
            hl.addWidget(dead_badge)


# ── Écran d'accueil ───────────────────────────────────────────────────

class HomeScreen(QDialog):
    """
    Écran d'accueil — affiché au lancement (et rouvrable via _go_home()
    dans window.py pour changer de projet en cours de session).

    Attributs après exec() == Accepted :
      result_path   : Path vers le dossier projet choisi / créé
      result_is_new : bool — True si nouveau projet
      result_name   : str  — nom saisi (si nouveau)
    """

    result_path:   Optional[Path] = None
    result_is_new: bool           = False
    result_name:   str            = ""

    def __init__(self, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        self._recent       = load_recent()
        self._toolchain    = Toolchain()

        self.setWindowTitle("GBA Editor — Ouvrir un projet")
        self.setMinimumSize(580, 460)
        self.setMaximumSize(720, 640)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog{{background:{C.BG_BASE};}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(56)
        hdr.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-bottom:1px solid {C.BORDER_DARK};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel("GBA Editor")
        title_lbl.setFont(QFont(T.MONO, 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color:{C.TEXT_HI};background:transparent;")
        sub_lbl = QLabel("Sélectionner un projet")
        sub_lbl.setFont(QFont(T.MONO, T.SM))
        sub_lbl.setStyleSheet(f"color:{C.TEXT_DIM};background:transparent;")

        hc = QVBoxLayout()
        hc.setSpacing(2)
        hc.addWidget(title_lbl)
        hc.addWidget(sub_lbl)
        hl.addLayout(hc, 1)
        root.addWidget(hdr)

        # ── Liste des récents ─────────────────────────────────────
        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE};border:none;outline:none;}}"
            f"QListWidget::item{{padding:0;border-bottom:1px solid {C.BORDER_DARK};}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL};}}"
            f"QListWidget::item:hover:!selected{{background:{C.BG_HOVER};}}"
        )
        self._list.setIconSize(QSize(0, 0))
        self._list.setSpacing(0)
        self._list.itemDoubleClicked.connect(self._open_selected)
        root.addWidget(self._list, 1)

        self._populate()

        # ── Message si liste vide ─────────────────────────────────
        self._empty_lbl = QLabel(
            "Aucun projet récent.\nCréez un nouveau projet ou ouvrez un dossier existant."
        )
        self._empty_lbl.setFont(QFont(T.MONO, T.MD))
        self._empty_lbl.setStyleSheet(
            f"color:{C.TEXT_MUTED};background:{C.BG_BASE};"
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setVisible(not self._recent)
        root.addWidget(self._empty_lbl)

        # ── Statut toolchain (devkitPro / mGBA) ────────────────────
        status_wrap = QWidget()
        status_wrap.setStyleSheet(
            f"background:{C.BG_PANEL};border-top:1px solid {C.BORDER_DARK};"
        )
        sw_l = QVBoxLayout(status_wrap)
        sw_l.setContentsMargins(16, 8, 16, 8)
        self._toolchain_status = ToolchainStatus(self._toolchain)
        self._toolchain_status.configure_requested.connect(self._open_toolchain_dialog)
        sw_l.addWidget(self._toolchain_status)
        root.addWidget(status_wrap)

        # ── Barre du bas ──────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background:{C.BG_PANEL};"
            f"border-top:1px solid {C.BORDER_DARK};"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)

        btn_clear = QPushButton("🗑  Clear list")
        btn_clear.setFont(QFont(T.MONO, T.SM))
        btn_clear.setFixedHeight(30)
        btn_clear.setStyleSheet(
            f"QPushButton{{color:#e05555;background:{C.BG_INPUT};"
            f"border:1px solid #3a2020;border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{background:#2a1a1a;border-color:#e05555;}}"
            f"QPushButton:pressed{{background:#1e1010;}}"
        )
        btn_clear.setToolTip("Supprime les entrées qui pointent vers des projets introuvables")
        btn_clear.clicked.connect(self._clear_dead)
        fl.addWidget(btn_clear)

        fl.addStretch()

        btn_open = QPushButton("Ouvrir un dossier…")
        btn_open.setFont(QFont(T.MONO, T.SM))
        btn_open.setFixedHeight(30)
        btn_open.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};border-color:#555;}}"
        )
        btn_open.clicked.connect(self._browse)
        fl.addWidget(btn_open)

        btn_new = QPushButton("+ Nouveau projet")
        btn_new.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        btn_new.setFixedHeight(30)
        btn_new.setStyleSheet(
            f"QPushButton{{color:#000;background:{C.ACCENT_GRN};"
            f"border:none;border-radius:4px;padding:0 14px;}}"
            f"QPushButton:hover{{background:#5dc487;}}"
            f"QPushButton:pressed{{background:#3d9060;}}"
        )
        btn_new.clicked.connect(self._new_project)
        fl.addWidget(btn_new)

        root.addWidget(footer)

        # Sélectionner le premier item valide
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if w and not w.dead:
                self._list.setCurrentRow(i)
                break

        # Enter pour ouvrir
        self._list.itemSelectionChanged.connect(self._on_sel)

    # ── Population ─────────────────────────────────────────────────

    def _populate(self):
        self._list.clear()
        for path in self._recent:
            dead = not path.exists()
            item = QListWidgetItem(self._list)
            w = _ProjectItem(path, dead)
            item.setSizeHint(QSize(0, 64))
            self._list.addItem(item)
            self._list.setItemWidget(item, w)

    # ── Actions ────────────────────────────────────────────────────

    def _on_sel(self):
        pass

    def _open_selected(self, *_):
        row = self._list.currentRow()
        if row < 0:
            return
        w = self._list.itemWidget(self._list.item(row))
        if not w or w.dead:
            return
        self._accept(w.path, is_new=False)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_selected()
        else:
            super().keyPressEvent(ev)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Ouvrir un projet existant", str(self._projects_dir)
        )
        if path:
            self._accept(Path(path), is_new=False)

    def _new_project(self):
        dlg = _NewProjectDialog(self._projects_dir, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._accept(dlg.result_path, is_new=True, name=dlg.result_name)

    def _clear_dead(self):
        alive = [p for p in self._recent if p.exists()]
        save_recent(alive)
        self._recent = alive
        self._populate()
        self._empty_lbl.setVisible(not self._recent)

    def _open_toolchain_dialog(self):
        from ui.build_panel import ToolchainDialog
        dlg = ToolchainDialog(self._toolchain, self)
        dlg.exec()
        self._toolchain_status.refresh()

    def _accept(self, path: Path, is_new: bool = False, name: str = ""):
        push_recent(path)
        self.result_path   = path
        self.result_is_new = is_new
        self.result_name   = name
        self.accept()


# ── Dialogue nouveau projet ───────────────────────────────────────────

class _NewProjectDialog(QDialog):
    result_path: Optional[Path] = None
    result_name: str            = ""

    def __init__(self, projects_dir: Path, parent=None):
        super().__init__(parent)
        self._projects_dir = projects_dir
        self.setWindowTitle("Nouveau projet")
        self.setFixedSize(420, 160)
        self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{C.BG_BASE};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Nom du projet
        row1 = QHBoxLayout()
        lbl = QLabel("Nom :")
        lbl.setFont(QFont(T.MONO, T.MD))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl.setFixedWidth(60)
        self._name_edit = QLineEdit()
        self._name_edit.setFont(QFont(T.MONO, T.MD))
        self._name_edit.setStyleSheet(QSS.lineedit)
        self._name_edit.setPlaceholderText("MonJeu")
        row1.addWidget(lbl)
        row1.addWidget(self._name_edit, 1)
        root.addLayout(row1)

        # Dossier parent
        row2 = QHBoxLayout()
        lbl2 = QLabel("Dans :")
        lbl2.setFont(QFont(T.MONO, T.MD))
        lbl2.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl2.setFixedWidth(60)
        self._dir_lbl = QLabel(str(projects_dir))
        self._dir_lbl.setFont(QFont(T.MONO, T.XS))
        self._dir_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        btn_dir = QPushButton("…")
        btn_dir.setFixedSize(28, 26)
        btn_dir.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:3px;}}"
            f"QPushButton:hover{{background:{C.BG_HOVER};}}"
        )
        btn_dir.clicked.connect(self._pick_dir)
        row2.addWidget(lbl2)
        row2.addWidget(self._dir_lbl, 1)
        row2.addWidget(btn_dir)
        root.addLayout(row2)

        root.addStretch()

        # Boutons
        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFont(QFont(T.MONO, T.SM))
        btn_cancel.setFixedHeight(28)
        btn_cancel.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_DIM};background:{C.BG_INPUT};"
            f"border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;}}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Créer")
        btn_ok.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        btn_ok.setFixedHeight(28)
        btn_ok.setStyleSheet(
            f"QPushButton{{color:#000;background:{C.ACCENT_GRN};"
            f"border:none;border-radius:4px;padding:0 16px;}}"
            f"QPushButton:hover{{background:#5dc487;}}"
        )
        btn_ok.clicked.connect(self._create)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

        self._name_edit.setFocus()
        self._name_edit.returnPressed.connect(self._create)

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier parent", str(self._projects_dir)
        )
        if path:
            self._projects_dir = Path(path)
            self._dir_lbl.setText(path)

    def _create(self):
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return
        path = self._projects_dir / name
        path.mkdir(parents=True, exist_ok=True)
        self.result_path = path
        self.result_name = name
        self.accept()
