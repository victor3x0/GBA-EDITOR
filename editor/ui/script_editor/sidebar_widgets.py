"""ui/script_editor/sidebar_widgets.py — briques réutilisables de la sidebar (section, sous-section, bouton d'entrée)."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QSizePolicy
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt, QSize

from ui.common.theme import C, T
from .colors import _BG, _BG_HDR, _BG_HOVER, _BORDER, _TEXT_DIM, _TEXT_HI, _TEXT_NORM, _C_API, _C_REF, _C_SUB, _C_EVENT, _C_BEHAVIOR, _BG_SEL_REF

_BTN_BASE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE = (
    f"QPushButton{{color:{_TEXT_DIM};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_FILE_SEL = (
    f"QPushButton{{color:{_C_REF};background:{_BG_SEL_REF};border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.MD}px;}}"
    f"QPushButton:hover{{color:{_C_REF};background:{_BG_SEL_REF};}}"
)
_BTN_EVENT_DEFINED = (
    f"QPushButton{{color:{_C_EVENT};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;font-weight:bold;}}"
    f"QPushButton:hover{{background:{_BG_HOVER};}}"
)
_BTN_API = (
    f"QPushButton{{color:{_C_API};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_REF = (
    f"QPushButton{{color:{_C_REF};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)
_BTN_BEHAVIOR = (
    f"QPushButton{{color:{_C_BEHAVIOR};background:none;border:none;"
    f"text-align:left;padding:2px 8px 2px 16px;"
    f"font-family:{T.CODE},{T.MONO};font-size:{T.LG}px;}}"
    f"QPushButton:hover{{color:{_TEXT_HI};background:{_BG_HOVER};}}"
)


from scripting.api import EVENT_REGISTRY as _EVENT_META


def _event_tooltip(name: str) -> str:
    meta = _EVENT_META.get(name, {})
    desc = meta.get("desc", "")
    params = meta.get("params", [])
    stub_sig = f"function {name}(" + ", ".join(p["name"] for p in params) + ")"

    lines = [
        f"<b style='font-family:Consolas,monospace;color:{_C_EVENT}'>{stub_sig}</b>",
        f"<p style='color:{_TEXT_NORM};margin:4px 0'>{desc}</p>",
    ]
    if params:
        lines.append("<table cellspacing='2' style='margin-top:4px'>")
        for p in params:
            lines.append(
                f"<tr>"
                f"<td style='font-family:Consolas,monospace;color:{C.ACCENT_ORG}'>{p['name']}</td>"
                f"<td style='color:{_TEXT_DIM};padding:0 6px'>{p['type']}</td>"
                f"<td style='color:{_TEXT_DIM}'>{p['description']}</td>"
                f"</tr>"
            )
        lines.append("</table>")
    lines.append(f"<p style='color:{_C_SUB};margin-top:6px;font-size:9px'>? doc (bientôt disponible)</p>")
    return "".join(lines)


class _Section(QWidget):
    """Section collapsible avec header cliquable."""

    def __init__(self, title: str, color: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(26)
        hdr.setStyleSheet(
            f"background:{_BG_HDR};border-top:1px solid {_BORDER};"
            f"border-bottom:1px solid {_BORDER};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 0, 0)

        self._toggle = QPushButton()
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{color};border:none;background:transparent;"
            f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:0 4px 0 4px;}}"
            f"QPushButton:hover{{background:{_BG_HOVER};}}"
        )
        self._toggle.setText(f"▾  {title}")
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._do_toggle)
        self._color = color
        self._title = title
        hl.addWidget(self._toggle)
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 2, 0, 4)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._toggle.setText(f"{'▾' if self._expanded else '▸'}  {self._title}")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)

    def clear_body(self):
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def sub_label(self, text: str) -> QLabel:
        """Sous-label statique (utilisé pour RÉFÉRENCES)."""
        lbl = QLabel(f"  {text}")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(
            f"color:{_C_SUB};background:{_BG_HDR};"
            f"border-bottom:1px solid {_BORDER};padding:3px 0;"
        )
        lbl.setFixedHeight(18)
        self._body_layout.addWidget(lbl)
        return lbl

    def sub_section(self, text: str) -> "_SubSection":
        """Sous-section collapsible (utilisé pour les catégories API)."""
        ss = _SubSection(text)
        self._body_layout.addWidget(ss)
        return ss


class _SubSection(QWidget):
    """Sous-section collapsible (catégories API, ou dossiers du file tree si icon_key donné)."""

    def __init__(self, title: str, expanded: bool = False, icon_key: str | None = None, parent=None):
        super().__init__(parent)
        self._expanded = True
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toggle = QPushButton()
        self._toggle.setStyleSheet(
            f"QPushButton{{color:{_C_SUB};border:none;background:{_BG_HDR};"
            f"font-family:{T.MONO};font-size:{T.SM}pt;font-weight:bold;"
            f"text-align:left;padding:2px 4px 2px 8px;}}"
            f"QPushButton:hover{{color:{_TEXT_NORM};background:{_BG_HOVER};}}"
        )
        self._toggle.setFixedHeight(20)
        if icon_key:
            from ui.common.icons import get as _ico, COLOR_FOLDER
            self._toggle.setIcon(_ico(icon_key, COLOR_FOLDER))
            self._toggle.setIconSize(QSize(13, 13))
        self._toggle.setText(f"▾ {title}")
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._do_toggle)
        self._title = title
        root.addWidget(self._toggle)

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{_BG};")
        root.addWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)

        if not expanded:
            self._do_toggle()

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        arrow = "▾" if self._expanded else "▸"
        self._toggle.setText(f"{arrow} {self._title}")

    def add_widget(self, w: QWidget):
        self._body_layout.addWidget(w)


class _EntryButton(QPushButton):
    """Bouton d'entrée sidebar avec tooltip riche, icône optionnelle (ui/icons.py)."""

    def __init__(self, label: str, style: str, tooltip_html: str,
                 icon_key: str | None = None, icon_color: str | None = None, parent=None):
        super().__init__(label, parent)
        self.setFont(QFont(T.CODE, T.MD))
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(style)
        self.setToolTip(tooltip_html)
        self._icon_key = icon_key
        if icon_key:
            self.setIconSize(QSize(15, 15))
            self.set_icon_color(icon_color or _TEXT_DIM)

    def set_icon_color(self, color: str):
        """Recolore l'icône — QSS ne peut pas teinter un QIcon, contrairement au texte."""
        if self._icon_key:
            from ui.common.icons import get as _ico
            self.setIcon(_ico(self._icon_key, color))

