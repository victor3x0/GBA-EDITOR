"""
ui/common/rom_budget_bar.py — bandeau fixe du panneau Build/debug : ce que la
ROM pèse RÉELLEMENT, mesuré sur le dernier build (codegen/rom_report.py).

Même langage visuel que `GbaStatusBar`/`SoundBudgetBar` (window.py,
sound_budget_bar.py) : label gris, valeur en gras, tooltip qui porte le
détail. Deux différences volontaires :

  - la jauge est CUMULATIVE, un segment par catégorie d'asset (Audio, Fonds,
    Sprites…), chacun dans SA couleur — l'exception à « une teinte par
    famille, la forme distingue le détail » (icons.py) que ce widget ne peut
    pas suivre : une icône a une forme, un pixel de barre n'en a pas, la
    teinte est ici la SEULE chose qui distingue un segment de son voisin ;
  - le mot « ROM » est cliquable : il choisit la cartouche visée
    (`Project.settings.cartridge_mib`), le dénominateur de cette jauge.

Rien n'est estimé : `RomReport` vient de `codegen/rom_report.py`, lu sur
l'ELF et le `.gba` d'un build réel. Tant qu'aucun build n'a eu lieu, le
bandeau le dit plutôt que d'annoncer un chiffre deviné.
"""
from __future__ import annotations

from ui.common.labels import label
from typing import Optional

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy, QToolTip, QMenu
from PyQt6.QtGui import QFont, QPainter, QColor, QCursor
from PyQt6.QtCore import Qt, pyqtSignal

from ui.common.theme import C, T
from ui.common.icons import (
    COLOR_SFX, COLOR_BACKGROUND, COLOR_SPRITE, COLOR_UI, COLOR_SCRIPT,
    COLOR_FONT, COLOR_DEFAULT,
)
from codegen.rom_report import RomReport, CARTRIDGE_SIZES_MIB

_WARN_RATIO = 0.75  # même seuil que GbaStatusBar / SoundBudgetBar

# Une couleur par catégorie de `rom_report.CATEGORY_ORDER`. Réutilise les
# teintes de FAMILLE déjà établies (icons.py) là où le rapprochement est
# direct (Audio, Fonds↔Background, Sprites, Interface↔UI, Collision↔Logique,
# Polices↔Font) ; Palettes et Tables de données ne sont pas des types d'asset
# (aucune famille ne les couvre) et prennent les accents génériques du thème ;
# Code/Reste ne sont pas des assets non plus : les deux teintes les plus
# discrètes du thème, pour qu'ils ne rivalisent pas visuellement avec ce sur
# quoi l'auteur peut agir.
_CATEGORY_COLORS: dict[str, str] = {
    "Audio":              COLOR_SFX,
    "Polices":            COLOR_FONT,
    "Fonds":               COLOR_BACKGROUND,
    "Sprites":            COLOR_SPRITE,
    "Palettes":           C.ACCENT_WARM,
    "Textes":             C.ACCENT,
    "Interface":          COLOR_UI,
    "Tables de données":  C.ACCENT_COOL,
    "Collision":          COLOR_SCRIPT,
    "Code":               C.TEXT_DIM,
    "Reste":              C.TEXT_MUTED,
}


_CATEGORY_KEYS = {'Audio': 'rombar.audio', 'Polices': 'common.fonts', 'Fonds': 'common.backgrounds', 'Sprites': 'common.sprites', 'Palettes': 'common.palettes', 'Textes': 'common.texts', 'Interface': 'common.interface', 'Tables de données': 'rombar.data_tables', 'Collision': 'rombar.collision', 'Code': 'rombar.code', 'Reste': 'rombar.other'}


def _color_of(category: str) -> str:
    return _CATEGORY_COLORS.get(category, COLOR_DEFAULT)


class _Gauge(QWidget):
    """Jauge cumulative : un segment par catégorie, largeur proportionnelle à
    son poids sur la capacité de la cartouche visée. Survoler un segment fait
    apparaître l'info de CETTE catégorie — c'est la seule façon de lire le
    détail, il n'y a plus de texte à côté."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        # [(catégorie, octets, couleur)], et le total (octets de la cartouche
        # visée) sur lequel la largeur de chaque segment se calcule.
        self._segments: list[tuple[str, int, str]] = []
        self._total = 0
        self._rom_bytes = 0

    def set_data(self, categories: dict[str, int], rom_bytes: int, cartridge_bytes: int):
        """`cartridge_bytes` est le dénominateur ACTUEL, pas forcément celui
        du dernier build : choisir une autre cartouche redessine tout de
        suite, sur les mêmes octets mesurés — rien n'est remesuré."""
        self._segments = [(cat, size, _color_of(cat))
                          for cat, size in categories.items() if size > 0]
        self._total = max(1, cartridge_bytes)
        self._rom_bytes = rom_bytes
        self.update()

    def _segment_at(self, x: int) -> Optional[tuple[str, int]]:
        """Catégorie sous le pixel `x`, ou None (zone vide au-delà du poids
        réel — la cartouche a de la place libre, ce n'est pas un asset)."""
        w = self.width()
        pos = 0.0
        for cat, size, _color in self._segments:
            seg_w = w * size / self._total
            if pos <= x < pos + seg_w:
                return cat, size
            pos += seg_w
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.BG_DEEP))
        p.drawRoundedRect(0, 0, w, h, 3, 3)

        x = 0.0
        for _cat, size, color in self._segments:
            seg_w = w * size / self._total
            p.setBrush(QColor(color))
            p.drawRect(round(x), 0, max(1, round(x + seg_w) - round(x)), h)
            x += seg_w

        # Coins arrondis par-dessus les rectangles carrés des segments — un
        # masque, pas un `setClipPath` par segment (coûterait un
        # antialiasing par segment pour un résultat identique).
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.end()

    def mouseMoveEvent(self, event):
        hit = self._segment_at(int(event.position().x()))
        if hit is None:
            QToolTip.hideText()
            return
        cat, size = hit
        pct = 100 * size / max(1, self._rom_bytes)
        category = label(_CATEGORY_KEYS[cat]) if cat in _CATEGORY_KEYS else cat
        QToolTip.showText(event.globalPosition().toPoint(),
                          label('rombar.category_usage', category=category, size=size / 1024, percent=pct), self)

    def leaveEvent(self, event):
        QToolTip.hideText()


class RomBudgetBar(QWidget):
    """Bandeau fixe : occupation de la cartouche, en segments colorés par
    catégorie d'asset. Reste sur le DERNIER build tant qu'aucun nouveau
    rapport n'arrive — changer d'écran ou vider la console ne l'efface pas."""

    cartridge_mib_changed = pyqtSignal(int)

    _STYLE_OK   = f"color:{C.TEXT_NORM};"
    _STYLE_WARN = f"color:{C.ACCENT_YLW};"
    _STYLE_CRIT = f"color:{C.ACCENT_RED};"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"background:{C.BG_DEEP}; border-top:1px solid {C.BORDER};")
        self._cartridge_mib = 4
        # Dernier rapport mesuré — conservé à part de la cartouche choisie :
        # changer de cartouche sans rebuilder redessine sur les MÊMES octets,
        # rien n'est remesuré (cf. `_refresh`).
        self._report: Optional[RomReport] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 8)
        lay.setSpacing(8)

        self._lbl_rom = QLabel()
        self._lbl_rom.setFont(QFont(T.MONO, T.XS, QFont.Weight.DemiBold))
        self._lbl_rom.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._lbl_rom.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_rom.mousePressEvent = lambda e: self._open_cartridge_menu()
        lay.addWidget(self._lbl_rom)

        self._value = QLabel("—")
        self._value.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._value.setStyleSheet(self._STYLE_OK)
        lay.addWidget(self._value)

        self._gauge = _Gauge()
        lay.addWidget(self._gauge, 1)

        self._refresh()

    def _open_cartridge_menu(self):
        menu = QMenu(self)
        for mib in CARTRIDGE_SIZES_MIB:
            act = menu.addAction(f"{mib} MiB")
            act.setCheckable(True)
            act.setChecked(mib == self._cartridge_mib)
            act.triggered.connect(lambda _checked, m=mib: self._pick_cartridge(m))
        menu.exec(QCursor.pos())

    def _pick_cartridge(self, mib: int):
        if mib == self._cartridge_mib:
            return
        self.cartridge_mib_changed.emit(mib)

    def set_cartridge_mib(self, mib: int):
        """Reflète la cartouche RÉELLEMENT réglée dans le projet — appelé au
        chargement du projet et après tout changement, pas seulement celui
        fait ici (l'inspecteur de projet a le même réglage). Le mot ROM et la
        jauge se mettent à jour tout de suite, même sans nouveau build."""
        self._cartridge_mib = mib
        self._refresh()

    @staticmethod
    def _kio(n: int) -> str:
        return f"{n / 1024:,.1f} KiB".replace(",", " ")

    def update_report(self, report: Optional[RomReport]):
        """Reçoit le `RomReport` mesuré à la fin d'un build (rom_build.py,
        événement `rom_report`) — jamais recalculé ici."""
        if report is None:
            return
        self._report = report
        self._cartridge_mib = report.cartridge_bytes // (1024 * 1024)
        self._refresh()

    def _refresh(self):
        """Seul endroit qui écrit le libellé ROM, la valeur et la jauge —
        appelé aussi bien par un nouveau build que par un simple changement
        de cartouche, pour que les deux chemins ne divergent jamais."""
        self._lbl_rom.setText(f"{self._cartridge_mib} MiB ▾")
        self._lbl_rom.setToolTip(
            label('rombar.target_tip', _cartridge_mib=self._cartridge_mib))

        cartridge_bytes = self._cartridge_mib * 1024 * 1024
        report = self._report
        if report is None:
            self._value.setText("—")
            self._value.setStyleSheet(self._STYLE_OK)
            self._gauge.set_data({}, 0, cartridge_bytes)
            return

        fill_ratio = report.rom_bytes / cartridge_bytes if cartridge_bytes else 0.0
        pct = 100 * fill_ratio
        self._value.setText(label('rombar.usage', value=self._kio(report.rom_bytes), _cartridge_mib=self._cartridge_mib, pct=pct))
        if report.rom_bytes > cartridge_bytes:
            self._value.setStyleSheet(self._STYLE_CRIT)
        elif fill_ratio >= _WARN_RATIO:
            self._value.setStyleSheet(self._STYLE_WARN)
        else:
            self._value.setStyleSheet(self._STYLE_OK)
        self._gauge.set_data(report.categories, report.rom_bytes, cartridge_bytes)
