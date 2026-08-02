"""ProjectInspector — carte d'identité du projet, mode par défaut de
l'inspecteur quand rien n'est sélectionné (clic hors de la zone active du
canvas, Échap, etc.).

Édite ProjectSettings avec les mêmes conventions que les autres inspecteurs :
commit à la perte de focus pour le texte, mutation undoable via SetFieldCmd,
persistance immédiate dans project.json.

`start_scene` est le point de départ du JEU — distinct de `last_scene`, la
dernière scène ouverte dans l'éditeur (cf. Project.set_active_scene).

`backdrop_color` est le DÉFAUT projet : chaque scène l'hérite tant qu'elle ne
pose pas son propre `Scene.backdrop_color` (cf. SceneInspector, même dialogue
quantifié BGR555)."""
from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QScrollArea, QLineEdit, QComboBox, QPushButton,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import QSize, Qt

from core.project import Project
from core.history import get_history, SetFieldCmd
from core.command_dispatcher import get_dispatcher
from core.color_utils import bgr555_to_rgb888, rgb888_to_bgr555
from ui.common.theme import C, T, QSS
from ui.common import icons


# Compteurs affichés dans la carte CONTENU : (attribut projet, icône, singulier, pluriel)
_COUNTERS: tuple[tuple[str, str, str, str], ...] = (
    ("scenes",      "scene",      "scène",   "scènes"),
    ("prefabs",     "prefab",     "prefab",  "prefabs"),
    ("sprites",     "sprite",     "sprite",  "sprites"),
    ("backgrounds", "background", "fond",    "fonds"),
    ("palettes",    "palette",    "palette", "palettes"),
    ("fonts",       "font",       "police", "polices"),
)


class ProjectInspector(QWidget):
    """Identité éditable du projet (auteur, version, scène de démarrage) +
    inventaire des assets."""

    _LABEL_W = 104

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._blocking = False
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        # ── Carte Identité ────────────────────────────────────────
        id_card, id_inner = self._card()
        id_inner.addWidget(self._card_title("IDENTITÉ", C.ACCENT))

        self._ed_author = QLineEdit()
        self._ed_author.setPlaceholderText("Anonyme")
        self._ed_author.editingFinished.connect(
            lambda: self._set_setting("author", self._ed_author.text().strip()))
        self._row("Auteur", self._ed_author, id_inner)

        self._ed_version = QLineEdit()
        self._ed_version.setPlaceholderText("0.1")
        self._ed_version.setMaximumWidth(110)
        self._ed_version.editingFinished.connect(
            lambda: self._set_setting("version", self._ed_version.text().strip()))
        self._row("Version", self._ed_version, id_inner, stretch=False)

        self._combo_start = QComboBox()
        self._combo_start.setFont(QFont(T.MONO, T.MD))
        self._combo_start.setStyleSheet(QSS.combobox)
        self._combo_start.setToolTip(
            "<b>Scène de démarrage</b><br><br>"
            "Première scène chargée au lancement de la ROM.<br>"
            "Indépendante de la scène ouverte dans l'éditeur."
        )
        self._combo_start.currentIndexChanged.connect(self._on_start_scene_changed)
        self._row("Démarrage", self._combo_start, id_inner)

        # ── Backdrop (défaut projet) ──────────────────────────────
        # Couleur de PAL_BG_RAM[0] : ce que le hardware affiche là où aucun
        # calque ni sprite ne dessine. Réglée ici pour TOUT le projet ; une
        # scène peut la surcharger depuis son propre inspecteur.
        bd_box = QWidget()
        bd_row = QHBoxLayout(bd_box)
        bd_row.setContentsMargins(0, 0, 0, 0)
        bd_row.setSpacing(6)
        self._btn_backdrop = QPushButton()
        self._btn_backdrop.setFixedSize(40, 22)
        self._btn_backdrop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backdrop.setToolTip(
            "<b>Couleur de fond (backdrop) du projet</b><br><br>"
            "Index 0 de la palette BG — affiché partout où aucun calque ni<br>"
            "sprite ne dessine, y compris à travers une window qui masque tout.<br><br>"
            "Défaut hérité par toutes les scènes qui ne définissent pas le leur.<br>"
            "Quantifiée en BGR555 (5 bits par canal) comme sur console."
        )
        self._btn_backdrop.clicked.connect(self._pick_backdrop)
        self._lbl_backdrop = QLabel()
        self._lbl_backdrop.setFont(QFont(T.MONO, T.XS))
        self._lbl_backdrop.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bd_row.addWidget(self._btn_backdrop)
        bd_row.addWidget(self._lbl_backdrop)
        bd_row.addStretch(1)
        self._row("Backdrop", bd_box, id_inner)

        layout.addWidget(id_card)

        # ── Carte Contenu ─────────────────────────────────────────
        content_card, content_inner = self._card()
        content_inner.addWidget(self._card_title("CONTENU", C.TEXT_NORM))

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self._count_labels: dict[str, QLabel] = {}
        for i, (attr, icon_key, _sing, _plur) in enumerate(_COUNTERS):
            chip, value_lbl = self._stat_chip(icon_key)
            self._count_labels[attr] = value_lbl
            grid.addWidget(chip, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        content_inner.addLayout(grid)

        layout.addWidget(content_card)

        self._hint = QLabel(
            "Sélectionnez une scène ou un actor dans le panneau de gauche "
            "pour afficher ses propriétés."
        )
        self._hint.setFont(QFont(T.MONO, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:2px 4px;")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        layout.addStretch()

    # ── Construction ──────────────────────────────────────────────

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        """Section à plat : léger fond élevé sur le BG_PANEL de l'inspecteur,
        sans bordure — même grammaire que SceneInspector (regroupement par
        élévation, identité par la couleur du titre)."""
        f = QFrame()
        f.setObjectName("pj_card")
        f.setStyleSheet(QSS.card("pj_card"))
        inner = QVBoxLayout(f)
        inner.setContentsMargins(10, 8, 10, 10)
        inner.setSpacing(6)
        return f, inner

    def _card_title(self, text: str, accent: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        lbl.setStyleSheet(
            f"color:{accent};letter-spacing:1px;"
            f"border-bottom:1px solid {C.BORDER};padding-bottom:4px;"
        )
        return lbl

    def _row(self, label: str, widget: QWidget, layout: QVBoxLayout,
             stretch: bool = True):
        if isinstance(widget, QLineEdit):
            widget.setFont(QFont(T.MONO, T.MD))
            widget.setStyleSheet(QSS.lineedit)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFont(QFont(T.MONO, T.SM))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        lbl.setFixedWidth(self._LABEL_W)
        row.addWidget(lbl)
        row.addWidget(widget, 1 if stretch else 0)
        if not stretch:
            row.addStretch(1)
        layout.addLayout(row)

    def _stat_chip(self, icon_key: str) -> tuple[QWidget, QLabel]:
        """Puce « icône · 3 scènes » — le QLabel retourné porte le texte à
        rafraîchir."""
        chip = QWidget()
        h = QHBoxLayout(chip)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(icons.get(icon_key, icons.COLOR_DEFAULT).pixmap(QSize(14, 14)))
        ico.setFixedWidth(16)
        value = QLabel("—")
        value.setFont(QFont(T.MONO, T.SM))
        value.setStyleSheet(f"color:{C.TEXT_NORM};")
        h.addWidget(ico)
        h.addWidget(value, 1)
        return chip, value

    # ── Chargement ────────────────────────────────────────────────

    def load(self, project: Optional[Project]):
        self._project = project
        self._blocking = True
        try:
            enabled = project is not None
            for w in (self._ed_author, self._ed_version, self._combo_start,
                      self._btn_backdrop):
                w.setEnabled(enabled)
            self._refresh_fields()
            self._refresh_counts()
        finally:
            self._blocking = False

    def _refresh_fields(self):
        """(Re)synchronise les widgets depuis ProjectSettings — appelé au
        chargement ET après chaque mutation (donc aussi après un undo)."""
        p = self._project
        self._ed_author.setText(p.settings.author if p else "")
        self._ed_version.setText(p.settings.version if p else "")

        self._combo_start.blockSignals(True)
        self._combo_start.clear()
        if p:
            names = [s.name for s in p.scenes]
            start = p.settings.start_scene
            if start and start not in names:
                # Scène de démarrage disparue (supprimée hors éditeur) : on la
                # garde visible plutôt que de la réécrire silencieusement.
                self._combo_start.addItem(f"{start}  (introuvable)", start)
                names = [start] + names
            for name in names:
                if self._combo_start.findData(name) < 0:
                    self._combo_start.addItem(name, name)
            idx = self._combo_start.findData(start)
            self._combo_start.setCurrentIndex(idx if idx >= 0 else 0)
            self._combo_start.setEnabled(self._combo_start.count() > 0)
        self._combo_start.blockSignals(False)

        self._refresh_backdrop()

    def _refresh_backdrop(self):
        v = self._project.settings.backdrop_color if self._project else 0
        r, g, b = bgr555_to_rgb888(v)
        self._btn_backdrop.setStyleSheet(
            f"QPushButton{{background:rgb({r},{g},{b});"
            f"border:1px solid {C.BORDER_MID};border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        self._lbl_backdrop.setText(f"0x{v:04X}")

    def _refresh_counts(self):
        p = self._project
        for attr, _icon, sing, plur in _COUNTERS:
            n = len(getattr(p, attr)) if p else 0
            self._count_labels[attr].setText(f"{n} {sing if n <= 1 else plur}")

    # ── Mutations ─────────────────────────────────────────────────

    def _persist(self):
        if self._project:
            self._project.save_settings()
        self._blocking = True
        try:
            self._refresh_fields()   # resynchronise l'UI après execute ET undo
        finally:
            self._blocking = False

    def _set_setting(self, field: str, value, extra_persist=None):
        if self._blocking or not self._project:
            return
        old = getattr(self._project.settings, field, None)
        if old == value:
            return

        def _do_persist():
            self._persist()          # sauvegarde + resynchronise (execute ET undo)
            if extra_persist:
                extra_persist()

        get_history().push(SetFieldCmd(
            self._project.settings, field, old, value,
            label=f"Projet.{field}", persist_fn=_do_persist,
        ))

    def _pick_backdrop(self):
        """Couleur de backdrop par défaut du projet — quantifiée en BGR555 :
        la valeur stockée est celle que la console affichera réellement, pas la
        couleur 8 bits/canal choisie dans le dialogue."""
        from PyQt6.QtWidgets import QColorDialog
        if not self._project:
            return
        r, g, b = bgr555_to_rgb888(self._project.settings.backdrop_color)
        col = QColorDialog.getColor(
            QColor(r, g, b), self, "Couleur de backdrop du projet",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if not col.isValid():
            return
        self._set_setting(
            "backdrop_color", rgb888_to_bgr555(col.red(), col.green(), col.blue()),
            # Les scènes sans override affichent cette couleur : prévenir le
            # canvas pour qu'il se repeigne (même signal que SceneInspector).
            extra_persist=lambda: get_dispatcher()._emit("backdrop_changed"),
        )

    def _on_start_scene_changed(self, _idx: int):
        name = self._combo_start.currentData()
        if name is not None:
            self._set_setting("start_scene", name)
