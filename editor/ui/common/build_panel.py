"""BuildPanel, ToolchainBar."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QPlainTextEdit, QToolButton,
)
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QPainter, QPainterPath
from PyQt6.QtCore import pyqtSignal, pyqtProperty, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtStateMachine import QStateMachine, QState

from ui.common.theme import C, T
from core.toolchain import Toolchain
from ui.common.rom_budget_bar import RomBudgetBar


class AnimatedBuildButton(QToolButton):
    """Bouton toolbar Build & Run : cartouche GBA (icône centrée, au repos) qui se
    transforme intégralement en barre de chargement pendant le build, pilotée par
    QStateMachine.

    États :
      idle     — icône cartouche centrée, largeur fixe.
      building — icône masquée, tout le bouton devient la jauge ; le remplissage
                 suit la progression réelle du build via `set_progress()`.
      done     — jauge figée sur le dernier progrès reçu (verte si succès, rouge
                 si échec) puis retour auto à idle après un court délai.
    """

    build_started = pyqtSignal()
    build_finished = pyqtSignal(bool)
    _settle = pyqtSignal()

    _WIDTH, _HEIGHT = 104, 32

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._fill = 0.0
        self._success = True
        self._bar_mode = False

        self._progress_anim = QPropertyAnimation(self, b"fill", self)
        self._progress_anim.setDuration(220)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(700)
        self._settle_timer.timeout.connect(self._settle)

        self.build_finished.connect(lambda ok: setattr(self, "_success", ok))

        self._machine = QStateMachine(self)
        st_idle = QState()
        st_building = QState()
        st_done = QState()

        st_idle.addTransition(self.build_started, st_building)
        st_building.addTransition(self.build_finished, st_done)
        st_done.addTransition(self._settle, st_idle)

        st_idle.entered.connect(self._enter_idle)
        st_building.entered.connect(self._enter_building)
        st_done.entered.connect(self._enter_done)

        for st in (st_idle, st_building, st_done):
            self._machine.addState(st)
        self._machine.setInitialState(st_idle)
        self._machine.start()

    # ── transitions d'état ───────────────────────────────────────
    def _enter_idle(self):
        self._bar_mode = False
        self._fill = 0.0
        self.update()

    def _enter_building(self):
        self._success = True
        self._bar_mode = True
        self._fill = 0.0
        self.update()

    def _enter_done(self):
        self._settle_timer.start()
        self.update()

    def set_progress(self, fraction: float):
        """Avance la jauge vers `fraction` (0..1) — reflète l'état réel du build."""
        fraction = max(0.0, min(1.0, fraction))
        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._fill)
        self._progress_anim.setEndValue(fraction)
        self._progress_anim.start()

    # ── propriété animable ──────────────────────────────────────
    def _get_fill(self): return self._fill
    def _set_fill(self, v):
        self._fill = v
        self.update()
    fill = pyqtProperty(float, _get_fill, _set_fill)

    # ── peinture ─────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if not self.isEnabled():
            bg = QColor("#1a3a24")
        elif self.underMouse():
            bg = QColor("#3a7a44")
        else:
            bg = QColor("#2a5c34")

        if not self._bar_mode:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(0, 0, w, h, 5, 5)

            # cartouche GBA centrée
            cw, ch = 20, 20
            cx, cy = (w - cw) // 2, (h - ch) // 2
            p.setPen(QColor("#c8ffc8"))
            p.setBrush(QColor("#123018"))
            p.drawRoundedRect(cx, cy, cw, ch, 3, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#1e4a28"))
            p.drawRect(cx + 3, cy + 3, cw - 6, ch - 11)
            p.setBrush(bg)
            p.drawRect(cx + cw // 2 - 3, cy + ch - 3, 6, 4)
        else:
            # tout le bouton devient la barre de chargement
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#123018"))
            p.drawRoundedRect(0, 0, w, h, 5, 5)
            fw = round(w * self._fill)
            if fw > 0:
                fill_color = QColor("#8be89b") if self._success else QColor("#e88b8b")
                p.setBrush(fill_color)
                p.setClipPath(self._rounded_path(w, h, 5))
                p.drawRect(0, 0, fw, h)
        p.end()

    @staticmethod
    def _rounded_path(w, h, r):
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        return path

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


class BuildPanel(QWidget):
    # Relais du même signal du bandeau ROM — window.py est seul à connaître
    # le projet, ce panneau n'en garde jamais de référence.
    cartridge_mib_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel("Build / debug")
        lbl.setFont(QFont(T.UI, T.MD, QFont.Weight.DemiBold))
        lbl.setStyleSheet(f"color:{C.TEXT_NORM};")
        hl.addWidget(lbl)
        hl.addStretch()
        btn_clear = QPushButton("Clear")
        btn_clear.setFont(QFont(T.UI, T.SM))
        btn_clear.setFixedHeight(20)
        btn_clear.clicked.connect(lambda: self.console.clear())
        hl.addWidget(btn_clear)
        layout.addWidget(header)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont(T.MONO, T.SM))
        self.console.setStyleSheet(
            f"background:{C.BG_DEEP}; color:#c8ffc8; border:none; padding:4px;"
        )
        self.console.setMaximumBlockCount(500)
        layout.addWidget(self.console, 1)

        # Séparé verticalement du journal, et FERRÉ en bas : contrairement au
        # texte de la console (qui défile et se vide au Clear), ce bandeau
        # garde le dernier poids mesuré en permanence visible.
        self.rom_bar = RomBudgetBar()
        self.rom_bar.cartridge_mib_changed.connect(self.cartridge_mib_changed)
        layout.addWidget(self.rom_bar, 0)

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

    def log_error(self, t): self.log(t, C.ACCENT_RED)
    def log_info(self, t):  self.log(t, C.ACCENT_COOL)

    def set_building(self, b):
        self.btn_build.setEnabled(not b)
        self.btn_build.setText("⏳  Building…" if b else "▶  Build & Run")

    def update_rom_report(self, report):
        """Reçoit le `RomReport` du dernier build (window.py, événement
        `rom_report`) et le passe au bandeau — ce panneau ne mesure rien."""
        self.rom_bar.update_report(report)

    def set_cartridge_mib(self, mib: int):
        """Resynchronise le bandeau ROM sur le réglage RÉEL du projet — au
        chargement, et après un changement fait ici ou dans l'inspecteur."""
        self.rom_bar.set_cartridge_mib(mib)


class ToolchainBar(QFrame):
    configure_requested = pyqtSignal()

    def __init__(self, toolchain: Toolchain, parent=None):
        super().__init__(parent)
        self.toolchain = toolchain
        self.setFixedHeight(28)
        self.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(12)
        font = QFont(T.UI, T.SM)

        lbl = QLabel("Toolchain:")
        lbl.setFont(font); lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        layout.addWidget(lbl)

        self._dkp  = QLabel(); self._dkp.setFont(font)
        self._mgba = QLabel(); self._mgba.setFont(font)
        layout.addWidget(self._dkp)
        layout.addWidget(self._mgba)
        layout.addStretch()

        btn = QPushButton("⚙ Configure")
        btn.setFixedHeight(20); btn.setFont(font)
        btn.setStyleSheet(
            f"background:{C.BORDER}; color:{C.TEXT_NORM}; border:1px solid {C.TEXT_MUTED};"
            "border-radius:3px; padding:0 6px;"
        )
        btn.clicked.connect(self.configure_requested)
        layout.addWidget(btn)
        self.refresh()

    def refresh(self):
        ok = self.toolchain.devkitpro_ok
        self._dkp.setText("devkitPro ✓" if ok else "devkitPro ✗")
        self._dkp.setStyleSheet(f"color:{C.POWER};" if ok else f"color:{C.ACCENT_RED};")
        ok2 = self.toolchain.mgba_ok
        self._mgba.setText("mgba ✓" if ok2 else "mgba ✗")
        self._mgba.setStyleSheet(f"color:{C.POWER};" if ok2 else f"color:{C.ACCENT_RED};")


## L'ancien ToolchainDialog (OK/Cancel, devkitPro + mgba) vit maintenant comme
## la catégorie « Toolchains » de ui/common/settings_dialog.py — un seul
## endroit qui configure le logiciel, plutôt qu'un dialogue par réglage.
