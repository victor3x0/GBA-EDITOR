"""BuildPanel, ToolchainBar, ToolchainDialog."""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QPlainTextEdit, QDialog, QDialogButtonBox, QGroupBox,
    QLineEdit, QFileDialog,
)
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtCore import pyqtSignal

from ui.theme import T

# toolchain est dans editor/, un niveau au-dessus
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.toolchain import Toolchain


class BuildPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet("background:#1e1e1e; border-bottom:1px solid #2a2a2a;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel("BUILD / DEBUG")
        lbl.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#aaa;")
        hl.addWidget(lbl)
        hl.addStretch()
        btn_clear = QPushButton("Effacer")
        btn_clear.setFont(QFont(T.MONO, T.SM))
        btn_clear.setFixedHeight(20)
        btn_clear.clicked.connect(lambda: self.console.clear())
        hl.addWidget(btn_clear)
        layout.addWidget(header)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont(T.MONO, T.SM))
        self.console.setStyleSheet(
            "background:#0d0d0d; color:#c8ffc8; border:none; padding:4px;"
        )
        self.console.setMaximumBlockCount(500)
        layout.addWidget(self.console)

        self.btn_build = QPushButton("▶  Build & Run")
        self.btn_build.setEnabled(False)
        self.btn_build.setVisible(False)

    def log(self, text, color="#c8ffc8"):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(("\n" if self.console.toPlainText() else "") + text, fmt)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def log_error(self, t): self.log(t, "#ff6b6b")
    def log_info(self, t):  self.log(t, "#6bcfff")

    def set_building(self, b):
        self.btn_build.setEnabled(not b)
        self.btn_build.setText("⏳  Build en cours…" if b else "▶  Build & Run")


class ToolchainBar(QFrame):
    configure_requested = pyqtSignal()

    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self.toolchain = toolchain
        self.setFixedHeight(28)
        self.setStyleSheet("background:#1a1f1a; border-bottom:1px solid #2a2a2a;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)
        font = QFont(T.MONO, T.SM)

        lbl = QLabel("Toolchain :")
        lbl.setFont(font); lbl.setStyleSheet("color:#555;")
        layout.addWidget(lbl)

        self._dkp  = QLabel(); self._dkp.setFont(font)
        self._mgba = QLabel(); self._mgba.setFont(font)
        layout.addWidget(self._dkp)
        layout.addWidget(self._mgba)
        layout.addStretch()

        btn = QPushButton("⚙ Configurer")
        btn.setFixedHeight(20); btn.setFont(font)
        btn.setStyleSheet(
            "background:#2a2a2a; color:#aaa; border:1px solid #444;"
            "border-radius:3px; padding:0 6px;"
        )
        btn.clicked.connect(self.configure_requested)
        layout.addWidget(btn)
        self.refresh()

    def refresh(self):
        ok = self.toolchain.devkitpro_ok
        self._dkp.setText("devkitPro ✓" if ok else "devkitPro ✗")
        self._dkp.setStyleSheet("color:#4caf78;" if ok else "color:#ff6b6b;")
        ok2 = self.toolchain.mgba_ok
        self._mgba.setText("mgba ✓" if ok2 else "mgba ✗")
        self._mgba.setStyleSheet("color:#4caf78;" if ok2 else "color:#ff6b6b;")


class ToolchainDialog(QDialog):
    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self.toolchain = toolchain
        self.setWindowTitle("Configuration toolchain")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grp = QGroupBox("devkitPro")
        grp.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        grp.setStyleSheet(
            "QGroupBox{color:#ccc;border:1px solid #333;border-radius:4px;"
            "margin-top:6px;padding:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px;}"
        )
        gl = QHBoxLayout(grp)
        n = QLabel("devkitPro"); n.setFont(QFont(T.MONO, T.MD)); n.setFixedWidth(160)
        self._dkp_edit = QLineEdit(str(toolchain.devkitpro_path or ""))
        self._dkp_edit.setFont(QFont(T.MONO, T.MD))
        self._dkp_edit.setStyleSheet(
            "background:#222;color:#ccc;border:1px solid #333;border-radius:3px;padding:3px;"
        )
        btn = QPushButton("Parcourir…"); btn.setFixedWidth(90)
        btn.clicked.connect(self._browse_dkp)
        gl.addWidget(n); gl.addWidget(self._dkp_edit, 1); gl.addWidget(btn)
        layout.addWidget(grp)

        grp2 = QGroupBox("mgba")
        grp2.setFont(QFont(T.MONO, T.MD, QFont.Weight.Bold))
        grp2.setStyleSheet(grp.styleSheet())
        gl2 = QHBoxLayout(grp2)
        mn = QLabel("mgba"); mn.setFixedWidth(160); mn.setFont(QFont(T.MONO, T.MD))
        self._mgba_edit = QLineEdit(str(toolchain.mgba_path or ""))
        self._mgba_edit.setFont(QFont(T.MONO, T.MD))
        self._mgba_edit.setStyleSheet(self._dkp_edit.styleSheet())
        btn2 = QPushButton("Parcourir…"); btn2.setFixedWidth(90)
        btn2.clicked.connect(self._browse_mgba)
        gl2.addWidget(mn); gl2.addWidget(self._mgba_edit, 1); gl2.addWidget(btn2)
        layout.addWidget(grp2)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _browse_dkp(self):
        p = QFileDialog.getExistingDirectory(self, "devkitPro")
        if p: self._dkp_edit.setText(p)

    def _browse_mgba(self):
        p, _ = QFileDialog.getOpenFileName(self, "mgba executable")
        if p: self._mgba_edit.setText(p)

    def _save(self):
        d = self._dkp_edit.text().strip()
        t = self._mgba_edit.text().strip()
        if d: self.toolchain.devkitpro_path = Path(d)
        if t: self.toolchain.mgba_path = Path(t)
        self.toolchain.save()
        self.accept()
