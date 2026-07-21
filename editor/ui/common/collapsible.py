"""Widgets utilitaires : section depliable + item cliquable/draggable."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton,
)
from PyQt6.QtGui import QFont, QDrag
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData

from ui.common.theme import T


class CollapsibleSection(QWidget):
    """Section avec header cliquable et contenu depliable."""

    def __init__(self, title: str, color: str = "#aaa", parent=None):
        super().__init__(parent)
        self._collapsed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QFrame()
        self._header.setFixedHeight(28)
        self._header.setStyleSheet(
            "background:#1e1e1e; border-bottom:1px solid #2a2a2a;"
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(8, 0, 6, 0)
        h_layout.setSpacing(4)

        self._arrow = QLabel("▼")
        self._arrow.setFont(QFont(T.MONO, T.SM))
        self._arrow.setStyleSheet(f"color:{color};")
        self._arrow.setFixedWidth(12)
        h_layout.addWidget(self._arrow)

        lbl = QLabel(title)
        lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{color};")
        h_layout.addWidget(lbl, 1)

        self._btn_add = QToolButton()
        self._btn_add.setText("+")
        self._btn_add.setFixedSize(20, 20)
        self._btn_add.setStyleSheet(
            "QToolButton{color:#aaa;border:none;background:none;font-size:14px;}"
            "QToolButton:hover{color:#fff;}"
        )
        h_layout.addWidget(self._btn_add)
        layout.addWidget(self._header)

        self._content = QWidget()
        self._content.setStyleSheet("background:#161616;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 2, 0, 2)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content)

        self._header.mousePressEvent = lambda e: self._toggle()

    def _toggle(self):
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._arrow.setText("▶" if self._collapsed else "▼")

    @property
    def add_button(self) -> QToolButton:
        return self._btn_add

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)


class SectionItem(QFrame):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, label: str, icon: str = "•", active: bool = False,
                 parent=None, drag_mime: str = None, drag_data: str = None):
        super().__init__(parent)
        self._active = active
        self._drag_mime = drag_mime
        self._drag_data = drag_data
        self._press_pos = None
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 8, 0)
        layout.setSpacing(6)

        ico = QLabel(icon)
        ico.setFont(QFont(T.MONO, T.MD))
        ico.setStyleSheet("color:#666;")
        ico.setFixedWidth(12)
        layout.addWidget(ico)

        self._lbl = QLabel(label)
        self._lbl.setFont(QFont(T.MONO, T.MD))
        layout.addWidget(self._lbl, 1)

    def _update_style(self):
        if self._active:
            self.setStyleSheet("background:#241f3a; border-left:2px solid #9b8cff;")
        else:
            self.setStyleSheet("background:transparent; border-left:2px solid transparent;")

    def set_active(self, active: bool):
        self._active = active
        self._update_style()
        self._lbl.setStyleSheet("color:#fff;" if active else "color:#aaa;")

    def mousePressEvent(self, e):
        self._press_pos = e.position().toPoint()
        self.clicked.emit()

    def mouseMoveEvent(self, e):
        if not self._drag_mime or self._press_pos is None:
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < 8:
            return
        drag = QDrag(self)
        md = QMimeData()
        md.setData(self._drag_mime, self._drag_data.encode("utf-8"))
        drag.setMimeData(md)
        drag.exec(Qt.DropAction.CopyAction)

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()
