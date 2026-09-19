"""Inspecteur des notes libres du Graphe des scènes."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.common.labels import label
from ui.common.theme import C, T, ui_font
from ui.common.widgets import CollapsibleCard, NotesEdit, W

_COLORS = ("", "#6EA8FE", "#6EE7B7", "#FBBF24", "#FB7185", "#C4B5FD")


class GraphNoteInspector(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id = None
        self._state = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 12); root.setSpacing(8)
        self._title = QLineEdit(); self._title.editingFinished.connect(self._save_title)
        W.row(label("graphnote.title"), self._title, root)
        note_title = QLabel(label("common.note")); note_title.setFont(ui_font(T.SM))
        note_title.setStyleSheet(f"color:{C.TEXT_DIM};"); root.addWidget(note_title)
        self._text = NotesEdit(); self._text.committed.connect(self._save_text); root.addWidget(self._text)
        card = CollapsibleCard(label("groupinsp.presentation"))
        colors = QWidget(); lay = QHBoxLayout(colors); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
        self._color_buttons = {}
        for color in _COLORS:
            button = QPushButton(); button.setCheckable(True); button.setFixedSize(24, 24)
            fill = C.BG_INPUT if not color else color
            button.setStyleSheet(
                f"QPushButton{{background:{fill};border:1px solid {C.BORDER_MID};border-radius:12px;}}"
                f"QPushButton:checked{{border:2px solid {C.TEXT_HI};}}")
            button.clicked.connect(lambda _=False, value=color: self._save(color=value))
            lay.addWidget(button); self._color_buttons[color] = button
        lay.addStretch(1); W.row(label("groupinsp.color"), colors, card.body_layout)
        self._collapsed = QPushButton(label("groupinsp.collapsed")); self._collapsed.setCheckable(True)
        self._collapsed.clicked.connect(lambda value: self._save(collapsed=value))
        card.body_layout.addWidget(self._collapsed); root.addWidget(card); root.addStretch(1)

    def load(self, note_id, state) -> None:
        self._id, self._state = note_id, state
        note = (state.notes().get(note_id, {}) if state else {})
        self._title.setText(note.get("title", "")); self._text.set_text_silent(note.get("text", ""))
        color = note.get("color", "")
        for value, button in self._color_buttons.items(): button.setChecked(value == color)
        self._collapsed.setChecked(bool(note.get("collapsed", False)))

    def _save_title(self) -> None:
        self._save(title=self._title.text())

    def _save_text(self, text: str) -> None:
        self._save(text=text)

    def _save(self, **values) -> None:
        if self._state and self._id and self._state.update_note(self._id, **values):
            if "color" in values:
                for value, button in self._color_buttons.items(): button.setChecked(value == values["color"])
            self.changed.emit()
