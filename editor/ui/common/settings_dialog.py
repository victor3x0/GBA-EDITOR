"""
ui/common/settings_dialog.py — Réglages du logiciel : un dialogue, quatre
catégories dans une colonne de gauche (Toolchains / Theme / Shortcuts /
External Tools), un panneau à droite. Remplace l'ancien `ToolchainDialog`
(OK/Cancel) — ici chaque champ se sauvegarde à l'instant où il change, comme
`Toolchain`/`Keybindings`/`ExternalTools` le font déjà chacun de leur côté :
un bouton Close referme l'écran, il n'y a rien à annuler.

Portée des quatre catégories, volontairement inégale (2026-08-23) :

  - **Toolchains** — devkitPro + mgba, ce qui existait déjà dans l'ancien
    dialogue, réemployé tel quel.
  - **Theme** — un seul thème existe aujourd'hui (indigo/périwinkle,
    cf. ARCHITECTURE.md « Thème GBA redesign ») : l'écran le DIT plutôt que
    de proposer un choix qui n'existe pas.
  - **Shortcuts** — les raccourcis remappables de `core/keybindings.py`.
    Persisté immédiatement ; les sites déjà construits avec `bind()` se
    remettent à jour EN COURS DE SESSION (`Keybindings.changed`), les autres
    (menus/canvas déjà ouverts ailleurs dans le code sans passer par `bind`,
    s'il y en avait) au prochain lancement.
  - **External Tools** — trois chemins persistés (image / son / police),
    PAS câblés à un bouton « Edit externally » nulle part encore — portée
    resserrée à la demande (2026-08-23), le câblage est un chantier séparé.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QLabel, QLineEdit, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QKeySequenceEdit, QScrollArea,
)
from PyQt6.QtGui import QFont, QKeySequence
from PyQt6.QtCore import Qt

from ui.common.theme import C, T, QSS
from core.toolchain import Toolchain
from core.external_tools import ExternalTools, TOOL_KINDS
from core.keybindings import get_keybindings, BINDINGS


def _field_font() -> QFont:
    return QFont(T.MONO, T.MD)


def _path_row(parent_layout, label_text: str, initial: str,
             browse_fn) -> QLineEdit:
    """Une ligne label + chemin + Browse — même geste pour devkitPro/mgba/les
    3 outils externes, un seul endroit qui la dessine."""
    row = QHBoxLayout()
    n = QLabel(label_text)
    n.setFont(QFont(T.UI, T.MD))
    n.setFixedWidth(140)
    edit = QLineEdit(initial)
    edit.setFont(_field_font())
    edit.setStyleSheet(QSS.lineedit)
    btn = QPushButton("Browse…")
    btn.setFixedWidth(90)
    btn.clicked.connect(lambda: browse_fn(edit))
    row.addWidget(n)
    row.addWidget(edit, 1)
    row.addWidget(btn)
    parent_layout.addLayout(row)
    return edit


def _category_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont(T.UI, T.LG, QFont.Weight.DemiBold))
    lbl.setStyleSheet(f"color:{C.TEXT_HI};")
    return lbl


# ── Toolchains ──────────────────────────────────────────────────────────

class ToolchainsPanel(QWidget):
    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self._toolchain = toolchain
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title("Toolchains"))
        note = QLabel("Chemins vers devkitPro et mgba — nécessaires pour Build & Run.")
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._dkp_edit = _path_row(lay, "devkitPro", str(toolchain.devkitpro_path or ""),
                                   self._browse_dkp)
        self._dkp_edit.editingFinished.connect(self._commit_dkp)
        self._mgba_edit = _path_row(lay, "mgba", str(toolchain.mgba_path or ""),
                                    self._browse_mgba)
        self._mgba_edit.editingFinished.connect(self._commit_mgba)
        lay.addStretch()

    def _browse_dkp(self, edit: QLineEdit):
        p = QFileDialog.getExistingDirectory(self, "devkitPro")
        if p:
            edit.setText(p)
            self._commit_dkp()

    def _browse_mgba(self, edit: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(self, "mgba executable")
        if p:
            edit.setText(p)
            self._commit_mgba()

    def _commit_dkp(self):
        t = self._dkp_edit.text().strip()
        if t:
            self._toolchain.devkitpro_path = Path(t)

    def _commit_mgba(self):
        t = self._mgba_edit.text().strip()
        if t:
            self._toolchain.mgba_path = Path(t)


# ── Theme ───────────────────────────────────────────────────────────────

class ThemePanel(QWidget):
    """Rien à régler pour l'instant — un seul thème existe. L'écran le dit
    plutôt que de proposer un choix qui n'existe pas encore."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title("Theme"))

        current = QLabel("GBA — indigo / périwinkle")
        current.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        current.setStyleSheet(f"color:{C.ACCENT};")
        lay.addWidget(current)

        note = QLabel(
            "Un seul thème existe aujourd'hui — pas de bascule clair/sombre ni "
            "de variante pour l'instant."
        )
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch()


# ── Shortcuts ───────────────────────────────────────────────────────────

class ShortcutsPanel(QWidget):
    """Liste + édition des raccourcis de `core/keybindings.BINDINGS`, groupés
    par contexte dans l'ordre du registre. Une substitution est visible tout
    de suite (fond legèrement teinté) et se remet au défaut d'un clic."""

    _COL_CONTEXT, _COL_ACTION, _COL_KEY, _COL_RESET = range(4)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kb = get_keybindings()
        self._edits: dict[str, QKeySequenceEdit] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_category_title("Shortcuts"))

        note = QLabel(
            "Cliquer une touche et taper la nouvelle combinaison. Deux actions sur "
            "la même touche sont signalées en rouge — les deux restent actives, "
            "seule la première déclarée du contexte répond."
        )
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._table = QTableWidget(len(BINDINGS), 4)
        self._table.setHorizontalHeaderLabels(["Context", "Action", "Shortcut", ""])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(QSS.list_widget)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self._COL_CONTEXT, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self._COL_ACTION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self._COL_KEY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self._COL_RESET, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(self._COL_CONTEXT, 110)
        self._table.setColumnWidth(self._COL_KEY, 150)
        self._table.setColumnWidth(self._COL_RESET, 30)

        for row, b in enumerate(BINDINGS):
            self._table.setItem(row, self._COL_CONTEXT, self._plain_item(b.context, dim=True))
            self._table.setItem(row, self._COL_ACTION, self._plain_item(b.label))

            kse = QKeySequenceEdit(QKeySequence(self._kb.resolve(b.id)))
            kse.setFont(_field_font())
            kse.keySequenceChanged.connect(lambda seq, bid=b.id: self._on_edited(bid, seq))
            self._table.setCellWidget(row, self._COL_KEY, kse)
            self._edits[b.id] = kse

            reset_btn = QPushButton("↺")
            reset_btn.setFixedWidth(26)
            reset_btn.setToolTip(f"Reset to {b.default}")
            reset_btn.clicked.connect(lambda _=False, bid=b.id: self._reset(bid))
            self._table.setCellWidget(row, self._COL_RESET, reset_btn)

        lay.addWidget(self._table, 1)

        reset_all = QPushButton("Reset all to defaults")
        reset_all.setStyleSheet(QSS.button_ghost)
        reset_all.clicked.connect(self._reset_all)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(reset_all)
        lay.addLayout(footer)

        self._refresh_conflicts()

    @staticmethod
    def _plain_item(text: str, dim: bool = False) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if dim:
            it.setForeground(Qt.GlobalColor.gray)
        return it

    def _on_edited(self, binding_id: str, seq: QKeySequence):
        self._kb.set(binding_id, seq.toString())
        self._refresh_conflicts()

    def _reset(self, binding_id: str):
        self._kb.reset(binding_id)
        self._edits[binding_id].setKeySequence(QKeySequence(self._kb.resolve(binding_id)))
        self._refresh_conflicts()

    def _reset_all(self):
        self._kb.reset_all()
        for b in BINDINGS:
            self._edits[b.id].setKeySequence(QKeySequence(b.default))
        self._refresh_conflicts()

    def _refresh_conflicts(self):
        """Une touche prise par PLUSIEURS actions du MÊME contexte est un vrai
        conflit (une seule répondra) — d'un contexte à l'autre, la même
        touche est normale (S = Select tool en canvas, autre chose ailleurs).
        """
        by_context: dict[str, dict[str, list[str]]] = {}
        for b in BINDINGS:
            seq = self._kb.resolve(b.id)
            if not seq:
                continue
            by_context.setdefault(b.context, {}).setdefault(seq, []).append(b.id)

        conflicted: set[str] = set()
        for seqs in by_context.values():
            for ids in seqs.values():
                if len(ids) > 1:
                    conflicted.update(ids)

        for b in BINDINGS:
            edit = self._edits[b.id]
            customized = self._kb.is_customized(b.id)
            if b.id in conflicted:
                edit.setStyleSheet(f"background:{C.BG_INPUT};color:{C.ACCENT_RED};"
                                   f"border:1px solid {C.ACCENT_RED};border-radius:3px;padding:2px;")
            elif customized:
                edit.setStyleSheet(f"background:{C.BG_INPUT};color:{C.ACCENT};"
                                   f"border:1px solid {C.ACCENT};border-radius:3px;padding:2px;")
            else:
                edit.setStyleSheet(QSS.lineedit)


# ── External Tools ──────────────────────────────────────────────────────

TOOL_KINDS_LABEL = dict(TOOL_KINDS)


class ExternalToolsPanel(QWidget):
    def __init__(self, tools: ExternalTools, parent=None):
        super().__init__(parent)
        self._tools = tools
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.addWidget(_category_title("External Tools"))

        note = QLabel(
            "Logiciels tiers pour éditer les assets — pas encore reliés à un "
            "bouton « Edit externally » dans les écrans, juste enregistrés ici."
        )
        note.setFont(QFont(T.UI, T.SM))
        note.setStyleSheet(f"color:{C.TEXT_DIM};")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._edits: dict[str, QLineEdit] = {}
        for kind, label in TOOL_KINDS:
            initial = str(tools.path(kind) or "")
            edit = _path_row(lay, label, initial,
                             lambda e, k=kind: self._browse(k, e))
            edit.editingFinished.connect(lambda k=kind: self._commit(k))
            self._edits[kind] = edit
        lay.addStretch()

    def _browse(self, kind: str, edit: QLineEdit):
        p, _ = QFileDialog.getOpenFileName(self, TOOL_KINDS_LABEL.get(kind, "Executable"))
        if p:
            edit.setText(p)
            self._commit(kind)

    def _commit(self, kind: str):
        t = self._edits[kind].text().strip()
        self._tools.set_path(kind, Path(t) if t else None)


# ── Le dialogue ─────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    """Colonne de catégories à gauche, panneau à droite — mêmes noms
    partout où on y entre (File → Settings, ToolchainBar → Configure,
    Game → build bloqué par un toolchain manquant)."""

    _CATEGORIES = ("Toolchains", "Theme", "Shortcuts", "External Tools")

    def __init__(self, toolchain: Toolchain, external_tools: ExternalTools,
                initial_category: str = "Toolchains", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setStyleSheet(QSS.dialog)
        self.resize(760, 480)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(QSS.list_widget)
        self._list.setFixedWidth(160)
        self._list.setFont(QFont(T.UI, T.MD))
        for cat in self._CATEGORIES:
            self._list.addItem(QListWidgetItem(cat))
        body.addWidget(self._list)

        self._stack = QStackedWidget()
        panels = [
            ToolchainsPanel(toolchain),
            ThemePanel(),
            ShortcutsPanel(),
            ExternalToolsPanel(external_tools),
        ]
        for panel in panels:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
            scroll.setWidget(panel)
            self._stack.addWidget(scroll)
        body.addWidget(self._stack, 1)

        self._list.currentRowChanged.connect(self._stack.setCurrentIndex)
        idx = self._CATEGORIES.index(initial_category) if initial_category in self._CATEGORIES else 0
        self._list.setCurrentRow(idx)

        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(QSS.button_primary)
        btn_close.setFixedWidth(90)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        root.addLayout(footer)
