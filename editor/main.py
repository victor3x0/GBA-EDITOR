"""
GBA Editor — point d'entrée
Usage : python main.py
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from window import MainWindow


def dark_palette() -> QPalette:
    """Thème sombre sobre — fond neutre, accents verts GBA."""
    p = QPalette()
    bg      = QColor("#1a1a1a")
    surface = QColor("#242424")
    border  = QColor("#333333")
    text    = QColor("#d4d4d4")
    muted   = QColor("#888888")
    accent  = QColor("#4caf78")

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            surface)
    p.setColor(QPalette.ColorRole.AlternateBase,   border)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
    p.setColor(QPalette.ColorRole.Button,          surface)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.Highlight,       accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
    return p


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("GBA Editor")
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
