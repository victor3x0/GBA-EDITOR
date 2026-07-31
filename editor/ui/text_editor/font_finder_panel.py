"""
ui/text_editor/font_finder_panel.py — colonne gauche : liste des polices.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T
from ui.common.widgets import FinderSection
from ui.text_editor.colors import FONT_COLOR


class FontFinderPanel(QWidget):
    """Liste des `Font` du projet. La sélection pilote le contexte de l'écran."""

    font_selected = pyqtSignal(object)   # Font | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(20)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 0, 0)
        lbl = QLabel("FONT FINDER")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        hl.addWidget(lbl)
        root.addWidget(hdr)

        sec = FinderSection("POLICES", FONT_COLOR)
        # Pas de « + » : une police s'obtient en déposant un PNG ou un .fnt dans
        # assets/fonts/ (asset_sync.sync_font_file), comme sprites et fonds.
        sec.set_add_visible(False)
        root.addWidget(sec, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
            f"QListWidget::item{{padding:4px 6px;}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL}; color:{FONT_COLOR};"
            f"border-left:2px solid {FONT_COLOR};}}"
        )
        self._list.currentItemChanged.connect(self._on_sel)
        sec.set_widget(self._list)

        self._empty = QLabel(
            "Aucune police.\n\nDéposer un PNG ou un .fnt\ndans assets/fonts/"
        )
        self._empty.setFont(QFont(T.MONO, T.XS))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:12px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        root.addWidget(self._empty)

    def load_project(self, project):
        """Ouvre un projet."""
        self._project = project
        self.refresh()

    def refresh(self):
        """Reconstruit la liste depuis le projet."""
        self._blocking = True
        self._list.blockSignals(True)
        self._list.clear()
        fonts = list(self._project.fonts) if self._project else []
        for f in fonts:
            it = QListWidgetItem(f.name)
            it.setFont(QFont(T.MONO, T.SM))
            it.setData(Qt.ItemDataRole.UserRole, f)
            it.setToolTip(
                f"{f.name}\n"
                f"{len(f.glyphs)} glyphes · {f.cell_w}×{f.cell_h} px\n"
                f"{f.tile_count()} tuiles dans le charblock du layer d'UI\n"
                f"source : {f.source_format}"
            )
            self._list.addItem(it)
        self._list.blockSignals(False)
        self._blocking = False
        self._empty.setVisible(not fonts)
        self._list.setVisible(bool(fonts))

    def clear_selection(self):
        """Désélectionne sans réémettre — quand l'écran repasse au contexte
        Texte suite à une sélection dans la table."""
        self._blocking = True
        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.setCurrentItem(None)
        self._list.blockSignals(False)
        self._blocking = False

    def _on_sel(self, cur, _prev):
        if self._blocking:
            return
        self.font_selected.emit(cur.data(Qt.ItemDataRole.UserRole) if cur else None)
