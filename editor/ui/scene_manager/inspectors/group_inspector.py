"""Inspecteur d'organisation d'un groupe de scènes du graphe."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.common.labels import label
from ui.common.theme import C, T, ui_font
from ui.common.widgets import CollapsibleCard, NotesEdit, W


_COLORS = ("", "#6EA8FE", "#6EE7B7", "#FBBF24", "#FB7185", "#C4B5FD")


class GroupInspector(QWidget):
    """Métadonnées éditoriales d'un dossier de scènes affiché comme groupe."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id = None
        self._folders = None
        self._state = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 12); root.setSpacing(8)

        self._name = QLineEdit(); self._name.editingFinished.connect(self._rename)
        W.row(label("groupinsp.name"), self._name, root)

        note_title = QLabel(label("common.note")); note_title.setFont(ui_font(T.SM))
        note_title.setStyleSheet(f"color:{C.TEXT_DIM};")
        root.addWidget(note_title)
        self._note = NotesEdit(); self._note.committed.connect(self._save_note); root.addWidget(self._note)

        card = CollapsibleCard(label("groupinsp.presentation"))
        colors = QWidget(); lay = QHBoxLayout(colors)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(5)
        self._color_buttons = {}
        for color in _COLORS:
            button = QPushButton(); button.setCheckable(True); button.setFixedSize(24, 24)
            fill = C.BG_INPUT if not color else color
            button.setStyleSheet(
                f"QPushButton{{background:{fill};border:1px solid {C.BORDER_MID};border-radius:12px;}}"
                f"QPushButton:checked{{border:2px solid {C.TEXT_HI};}}")
            button.clicked.connect(lambda _=False, value=color: self._set_color(value))
            lay.addWidget(button); self._color_buttons[color] = button
        lay.addStretch(1)
        W.row(label("groupinsp.color"), colors, card.body_layout)
        self._collapsed = QPushButton(label("groupinsp.collapsed")); self._collapsed.setCheckable(True)
        self._collapsed.clicked.connect(self._set_collapsed)
        self._collapsed.setStyleSheet(
            f"QPushButton{{color:{C.TEXT_NORM};background:{C.BG_INPUT};border:1px solid {C.BORDER_MID};padding:4px 8px;}}"
            f"QPushButton:checked{{color:{C.BG_DEEP};background:{C.ACCENT};border-color:{C.ACCENT};}}")
        card.body_layout.addWidget(self._collapsed)
        root.addWidget(card)

        self._content = CollapsibleCard(label("groupinsp.content"))
        root.addWidget(self._content)
        root.addStretch(1)

    def load(self, group_id, folders, state) -> None:
        self._id, self._folders, self._state = group_id, folders, state
        folder = self._folder()
        self._name.setText(folder.name if folder else "")
        self._note.set_text_silent(state.group_note(group_id) if state else "")
        color = folder.color if folder else ""
        for value, button in self._color_buttons.items(): button.setChecked(value == color)
        self._collapsed.setChecked(state.group_collapsed(group_id) if state else True)
        self._refresh_content()

    def _folder(self):
        return next((f for f in self._folders.folders("scenes") if f.id == self._id), None) if self._folders else None

    def _rename(self) -> None:
        if self._folders and self._id and self._folders.rename_folder("scenes", self._id, self._name.text()):
            self.changed.emit()

    def _save_note(self, text: str) -> None:
        if self._state and self._id and self._state.set_group_note(self._id, text): self.changed.emit()

    def _set_color(self, color: str) -> None:
        if self._folders and self._id:
            changed = self._folders.set_folder_color("scenes", self._id, color)
            for value, button in self._color_buttons.items(): button.setChecked(value == color)
            if changed: self.changed.emit()

    def _set_collapsed(self, collapsed: bool) -> None:
        if self._state and self._id and self._state.set_group_collapsed(self._id, collapsed): self.changed.emit()

    def _refresh_content(self) -> None:
        lay = self._content.body_layout
        while lay.count():
            item = lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        folders = self._folders.folders("scenes") if self._folders else []
        folder = self._folder()
        scenes = list(folder.members) if folder else []
        children = [f.name for f in folders if f.parent_id == self._id]
        for title, names in ((label("groupinsp.scenes", count=len(scenes)), scenes),
                             (label("groupinsp.groups", count=len(children)), children)):
            row = QLabel(title); row.setStyleSheet(f"color:{C.TEXT_DIM}; padding:3px 0;")
            lay.addWidget(row)
            for name in names:
                value = QLabel(f"•  {name}"); value.setStyleSheet(f"color:{C.TEXT_NORM}; padding-left:8px;")
                lay.addWidget(value)
        if not scenes and not children:
            empty = QLabel(label("groupinsp.empty")); empty.setStyleSheet(f"color:{C.TEXT_DIM}; padding:5px 0;")
            lay.addWidget(empty)
