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
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QScrollArea, QLineEdit, QComboBox, QPushButton, QSpinBox, QCheckBox,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import QSize, Qt

from core.project import Project
from core.history import get_history, SetFieldCmd
from core.command_dispatcher import get_dispatcher
from core.gba_color import bgr555_to_rgb888, rgb888_to_bgr555
from ui.common.theme import C, T, QSS
from ui.common.widgets import CollapsibleCard
from ui.common import icons


# Compteurs affichés dans la carte CONTENU : (attribut projet, icône, singulier, pluriel)
_COUNTERS: tuple[tuple[str, str, str, str], ...] = (
    ("scenes",      "scene",      "scene",      "scenes"),
    ("prefabs",     "prefab",     "prefab",     "prefabs"),
    ("sprites",     "sprite",     "sprite",     "sprites"),
    ("backgrounds", "background", "background", "backgrounds"),
    ("palettes",    "palette",    "palette",    "palettes"),
    ("fonts",       "font",       "font",       "fonts"),
)


# Transitions de scène — mêmes valeurs que les effets de mélange (models/scene.py).
# Le projet définit la transition, une scène peut la surcharger : le
# SceneInspector reprend donc CES libellés et y ajoute son « From project »,
# pour que le même fondu ne soit pas nommé de deux façons selon le panneau.
TRANSITION_LABELS: tuple[tuple[str, str], ...] = (
    ("none",       "Cut (no transition)"),
    ("fade_black", "Fade to black"),
    ("fade_white", "Fade to white"),
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
        id_card = CollapsibleCard("Identity")
        id_inner = id_card.body_layout

        self._ed_author = QLineEdit()
        self._ed_author.setPlaceholderText("Anonymous")
        self._ed_author.editingFinished.connect(
            lambda: self._set_setting("author", self._ed_author.text().strip()))
        self._row("Author", self._ed_author, id_inner)

        self._ed_version = QLineEdit()
        self._ed_version.setPlaceholderText("0.1")
        self._ed_version.setMaximumWidth(110)
        self._ed_version.editingFinished.connect(
            lambda: self._set_setting("version", self._ed_version.text().strip()))
        self._row("Version", self._ed_version, id_inner, stretch=False)

        self._combo_start = QComboBox()
        self._combo_start.setFont(QFont(T.UI, T.MD))
        self._combo_start.setStyleSheet(QSS.combobox)
        self._combo_start.setToolTip(
            "<b>Start scene</b><br><br>"
            "First scene loaded when the ROM boots.<br>"
            "Independent of the scene open in the editor."
        )
        self._combo_start.currentIndexChanged.connect(self._on_start_scene_changed)
        self._row("Start", self._combo_start, id_inner)

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
            "<b>Project backdrop color</b><br><br>"
            "Index 0 of the BG palette — shown wherever no layer or<br>"
            "sprite draws, including through a window that masks everything.<br><br>"
            "Default inherited by every scene that doesn't set its own.<br>"
            "Quantized to BGR555 (5 bits per channel) like on hardware."
        )
        self._btn_backdrop.clicked.connect(self._pick_backdrop)
        self._lbl_backdrop = QLabel()
        self._lbl_backdrop.setFont(QFont(T.MONO, T.XS))
        self._lbl_backdrop.setStyleSheet(f"color:{C.TEXT_MUTED};")
        bd_row.addWidget(self._btn_backdrop)
        bd_row.addWidget(self._lbl_backdrop)
        bd_row.addStretch(1)
        self._row("Backdrop", bd_box, id_inner)

        # ── Emplacements de sauvegarde ────────────────────────────
        # Un réglage de projet, et non une valeur libre laissée au script :
        # c'est lui qui borne la place occupée en SRAM, donc ce qui rend la
        # capacité vérifiable au build. Rien n'est émis tant qu'aucune variable
        # globale n'est marquée persistante.
        self._spin_slots = QSpinBox()
        self._spin_slots.setRange(1, 99)
        self._spin_slots.setFixedWidth(64)
        self._spin_slots.setFont(QFont(T.MONO, T.MD))
        self._spin_slots.setStyleSheet(QSS.spinbox)
        self._spin_slots.setToolTip(
            "<b>Save slots</b><br><br>"
            "How many separate saves the game can hold in SRAM.<br>"
            "Scripts address them by number: <tt>save.write(0)</tt>.<br><br>"
            "Only the global variables marked <i>persist</i> are stored.<br>"
            "A project with none of them writes no save data at all."
        )
        self._spin_slots.valueChanged.connect(
            lambda v: self._set_setting("save_slots", int(v)))
        self._row("Save slots", self._spin_slots, id_inner, stretch=False)

        # ── Cartouche visée ───────────────────────────────────────
        # Sert de plafond au rapport de poids affiché en fin de build. Les
        # quatre tailles réellement produites en cartouche masquée sur GBA ;
        # l'espace d'adressage de la console s'arrête à 32 Mio.
        from codegen.rom_report import CARTRIDGE_SIZES_MIB
        self._combo_cart = QComboBox()
        self._combo_cart.setFont(QFont(T.UI, T.MD))
        self._combo_cart.setStyleSheet(QSS.combobox)
        for mib in CARTRIDGE_SIZES_MIB:
            self._combo_cart.addItem(f"{mib} MiB", mib)
        self._combo_cart.setToolTip(
            "<b>Cartridge size</b><br><br>"
            "The capacity the build report compares the ROM against.<br>"
            "Going over it is reported as an error — the ROM still exists,<br>"
            "it simply does not fit on that cartridge.<br><br>"
            "These are the mask-ROM sizes actually manufactured for the GBA."
        )
        self._combo_cart.currentIndexChanged.connect(
            lambda i: self._set_setting("cartridge_mib", int(self._combo_cart.itemData(i) or 4)))
        self._row("Cartridge", self._combo_cart, id_inner, stretch=False)

        # ── Taux d'échantillonnage des effets (défaut projet) ──────
        # Surchargeable par effet (cf. Sfx.sample_rate). « Source » ne
        # ré-échantillonne rien : c'est le défaut, parce que dégrader d'office
        # un projet existant serait le faire dans le dos de son auteur.
        self._combo_rate = QComboBox()
        self._combo_rate.setFont(QFont(T.UI, T.MD))
        self._combo_rate.setStyleSheet(QSS.combobox)
        for value, label in ((0, "Source (no resampling)"), (8000, "8 000 Hz"),
                             (11025, "11 025 Hz"), (16000, "16 000 Hz"),
                             (22050, "22 050 Hz"), (32000, "32 000 Hz")):
            self._combo_rate.addItem(label, value)
        self._combo_rate.setToolTip(
            "<b>Default sample rate for sound effects</b><br><br>"
            "mmutil converts effects to 8-bit mono but <b>keeps their sample "
            "rate</b>,<br>so a 44.1 kHz effect costs about three times what it "
            "would at 16 kHz<br>— for detail the Maxmod mixer does not "
            "reproduce.<br><br>"
            "Resampling happens at build time. The file in <tt>assets/</tt> is "
            "never<br>rewritten, so raising the rate again loses nothing."
        )
        self._combo_rate.currentIndexChanged.connect(
            lambda i: self._set_setting("sfx_sample_rate", int(self._combo_rate.itemData(i) or 0)))
        self._row("SFX rate", self._combo_rate, id_inner, stretch=False)

        # ── Canaux logiciels ──────────────────────────────────────
        # Musique et effets se les partagent. Le coût est exact et vient du
        # modèle, pas d'un chiffre recopié ici (cf. audio.sound_channels_bytes).
        from core.models.audio import (SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX,
                                       SOUND_HANDLE_SLOTS, sound_channels_bytes)
        self._spin_channels = QSpinBox()
        self._spin_channels.setRange(SOUND_CHANNELS_MIN, SOUND_CHANNELS_MAX)
        self._spin_channels.setFixedWidth(64)
        self._spin_channels.setFont(QFont(T.MONO, T.MD))
        self._spin_channels.setStyleSheet(QSS.spinbox)
        self._spin_channels.setToolTip(
            "<b>Sound channels</b><br><br>"
            "Software mixing channels, shared by music and sound effects.<br>"
            "A module needs one per voice; every effect playing takes one more."
            "<br><br>"
            f"Each channel costs {sound_channels_bytes(1) - sound_channels_bytes(0)}"
            f" bytes of heap, plus a fixed {sound_channels_bytes(0)}-byte mixing "
            f"buffer.<br>"
            f"Eight channels — the default — cost {sound_channels_bytes(8)} bytes."
            "<br><br>"
            f"Unrelated to sound effect <i>references</i>: Maxmod tracks "
            f"{SOUND_HANDLE_SLOTS} of those<br>whatever this is set to. An effect "
            "past that limit still plays,<br>it simply has no reference."
        )
        self._spin_channels.valueChanged.connect(
            lambda v: self._set_setting("sound_channels", int(v)))
        self._row("Sound channels", self._spin_channels, id_inner, stretch=False)

        # ── Build debug ─────────────────────────────────────────────
        # `debug.log` et la mesure de budget par frame (cf. ROADMAP v0.14) ne
        # coûtent rien en ROM release : ce réglage décide de quel build sort
        # de F5. Coché par défaut, comme le comportement du logiciel avant
        # que ce réglage existe (aucun projet ne change de taille sans le
        # décider).
        self._chk_debug = QCheckBox("Debug build")
        self._chk_debug.setFont(QFont(T.UI, T.MD))
        self._chk_debug.setToolTip(
            "<b>Debug build</b><br><br>"
            "Enables <tt>debug.*</tt> in scripts: <tt>debug.log(...)</tt> writes "
            "to the mGBA log console,<br>and the engine measures frame time, OAM "
            "usage, sound channels and DMA<br>load once per frame, also logged "
            "there.<br><br>"
            "Unchecked (Release), every <tt>debug.*</tt> call and the "
            "measurement it costs<br>are removed at compile time — not just "
            "silenced at runtime."
        )
        self._chk_debug.toggled.connect(
            lambda v: self._set_setting("debug_build", bool(v)))
        self._row("Build", self._chk_debug, id_inner, stretch=False)

        # ── Transition de scène (défaut projet) ───────────────────
        # Le fondu joué à chaque changement de scène. Réglé une fois ici pour
        # tout le jeu ; une scène peut le surcharger depuis son inspecteur.
        trans_box = QWidget()
        trans_row = QHBoxLayout(trans_box)
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_row.setSpacing(6)
        self._combo_trans = QComboBox()
        self._combo_trans.setFont(QFont(T.UI, T.MD))
        self._combo_trans.setStyleSheet(QSS.combobox)
        for kind, label in TRANSITION_LABELS:
            self._combo_trans.addItem(label, kind)
        self._combo_trans.setToolTip(
            "<b>Scene transition</b><br><br>"
            "Fade played when the game leaves a scene and when it opens one.<br>"
            "Each scene fades out with its own setting and fades in with the<br>"
            "one of the scene being opened — including the very first scene.<br><br>"
            "While a transition plays, the outgoing scene is frozen and the<br>"
            "scene's own color blending is suspended: the hardware has a single<br>"
            "blend mode, so there is no fade on top of a translucency."
        )
        self._combo_trans.currentIndexChanged.connect(
            lambda i: self._set_setting("transition_kind",
                                        self._combo_trans.itemData(i) or "none"))
        self._spin_trans = QSpinBox()
        self._spin_trans.setRange(1, 255)
        self._spin_trans.setFixedWidth(64)
        self._spin_trans.setSuffix(" f")
        self._spin_trans.setFont(QFont(T.MONO, T.MD))
        self._spin_trans.setStyleSheet(QSS.spinbox)
        self._spin_trans.setToolTip(
            "Frames per half — 16 frames is a bit over a quarter of a second.")
        self._spin_trans.valueChanged.connect(
            lambda v: self._set_setting("transition_frames", int(v)))
        trans_row.addWidget(self._combo_trans, 1)
        trans_row.addWidget(self._spin_trans)
        self._row("Transition", trans_box, id_inner)

        layout.addWidget(id_card)

        # ── Carte Collisions (ROADMAP v0.23) ──────────────────────
        # Une grille TRIANGULAIRE entre tags de boxes : « est-ce que A touche
        # B ? » se lit à l'intersection, et une seule case par couple — la
        # question n'a pas d'ordre. Un masque par tag s'écrirait plus vite mais
        # demanderait de tenir deux champs asymétriques dans sa tête pour
        # répondre à la même question (le modèle layer/mask de Godot).
        #
        # Cochée = les deux se rencontrent, ce qui est le DÉFAUT : la matrice
        # ne stocke que les exceptions, et un projet où rien n'est décoché se
        # comporte exactement comme avant la v0.23.
        col_card = CollapsibleCard("Collisions")
        col_inner = col_card.body_layout
        self._col_hint = QLabel()
        self._col_hint.setFont(QFont(T.UI, T.XS))
        self._col_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._col_hint.setWordWrap(True)
        col_inner.addWidget(self._col_hint)
        self._col_grid_host = QWidget()
        self._col_grid = QGridLayout(self._col_grid_host)
        self._col_grid.setContentsMargins(0, 4, 0, 0)
        self._col_grid.setHorizontalSpacing(6)
        self._col_grid.setVerticalSpacing(2)
        col_inner.addWidget(self._col_grid_host)
        layout.addWidget(col_card)

        # ── Carte Contenu ─────────────────────────────────────────
        content_card = CollapsibleCard("Content")
        content_inner = content_card.body_layout

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
            "Select a scene or an actor in the left panel "
            "to show its properties."
        )
        self._hint.setFont(QFont(T.UI, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:2px 4px;")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        layout.addStretch()

    # ── Construction ──────────────────────────────────────────────

    def _row(self, label: str, widget: QWidget, layout: QVBoxLayout,
             stretch: bool = True):
        if isinstance(widget, QLineEdit):
            widget.setFont(QFont(T.MONO, T.MD))
            widget.setStyleSheet(QSS.lineedit)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFont(QFont(T.UI, T.SM))
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
        value.setFont(QFont(T.UI, T.SM))
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
                      self._btn_backdrop, self._spin_slots,
                      self._combo_trans, self._spin_trans):
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
                self._combo_start.addItem(f"{start}  (not found)", start)
                names = [start] + names
            for name in names:
                if self._combo_start.findData(name) < 0:
                    self._combo_start.addItem(name, name)
            idx = self._combo_start.findData(start)
            self._combo_start.setCurrentIndex(idx if idx >= 0 else 0)
            self._combo_start.setEnabled(self._combo_start.count() > 0)
        self._combo_start.blockSignals(False)

        self._spin_slots.blockSignals(True)
        self._spin_slots.setValue(getattr(p.settings, "save_slots", 1) if p else 1)
        self._spin_slots.blockSignals(False)

        self._chk_debug.blockSignals(True)
        self._chk_debug.setChecked(getattr(p.settings, "debug_build", True) if p else True)
        self._chk_debug.blockSignals(False)

        self._refresh_collision_matrix()

        self._spin_channels.blockSignals(True)
        self._spin_channels.setValue(getattr(p.settings, "sound_channels", 8) if p else 8)
        self._spin_channels.blockSignals(False)

        for combo, field, default in ((self._combo_cart, "cartridge_mib", 4),
                                      (self._combo_rate, "sfx_sample_rate", 0)):
            combo.blockSignals(True)
            idx = combo.findData(getattr(p.settings, field, default) if p else default)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        kind = getattr(p.settings, "transition_kind", "none") if p else "none"
        self._combo_trans.blockSignals(True)
        idx = self._combo_trans.findData(kind)
        self._combo_trans.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_trans.blockSignals(False)
        self._spin_trans.blockSignals(True)
        self._spin_trans.setValue(getattr(p.settings, "transition_frames", 16) if p else 16)
        self._spin_trans.blockSignals(False)
        # La durée ne veut rien dire sans fondu.
        self._spin_trans.setEnabled(bool(p) and kind != "none")

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

    # ── Matrice de collision (ROADMAP v0.23) ──────────────────────

    def _project_box_tags(self) -> list[str]:
        """Tous les tags de boxes du projet, scènes ET prefabs, dans l'ordre
        alphabétique. C'est la liste qui donne ses lignes et ses colonnes à la
        grille : un tag qu'aucune box ne porte n'aurait rien à croiser."""
        from core.models.components import CollisionBoxComponent
        tags: set = set()
        p = self._project
        if not p:
            return []
        owners = [a for sc in p.scenes for a in sc.actors] + list(p.prefabs)
        owners += [ch for pf in p.prefabs for ch in (getattr(pf, "children", []) or [])]
        for o in owners:
            for c in getattr(o, "components", []):
                if isinstance(c, CollisionBoxComponent) and c.active:
                    tags.add(c.tag or "body")
        return sorted(tags)

    def _refresh_collision_matrix(self):
        from core.models.settings import pair_key
        while self._col_grid.count():
            it = self._col_grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        tags = self._project_box_tags()
        if len(tags) < 2:
            self._col_hint.setText(
                "Il faut au moins deux tags de boxes dans le projet pour qu'une "
                "matrice ait un sens. Le tag se règle sur le composant Collision "
                "d'un acteur.")
            return
        self._col_hint.setText(
            "Décochez un couple pour que ces deux tags s'ignorent. La paire "
            "n'est alors PAS émise : ni code, ni test par frame.")
        disabled = set(getattr(self._project.settings,
                               "collision_disabled_pairs", []) or [])
        for c, tag in enumerate(tags):
            lbl = QLabel(tag)
            lbl.setFont(QFont(T.MONO, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            self._col_grid.addWidget(lbl, 0, c + 1)
        for r, ta in enumerate(tags):
            lbl = QLabel(ta)
            lbl.setFont(QFont(T.MONO, T.XS))
            lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
            self._col_grid.addWidget(lbl, r + 1, 0)
            # Triangulaire : le couple (A, B) est le même que (B, A), et
            # l'afficher deux fois inviterait à en décocher un seul.
            for c in range(r, len(tags)):
                tb = tags[c]
                box = QCheckBox()
                box.setChecked(pair_key(ta, tb) not in disabled)
                box.setStyleSheet(QSS.checkbox)
                box.setToolTip(f"{ta} × {tb}")
                box.toggled.connect(
                    lambda on, x=ta, y=tb: self._set_collision_pair(x, y, on))
                self._col_grid.addWidget(box, r + 1, c + 1)

    def _set_collision_pair(self, tag_a: str, tag_b: str, enabled: bool):
        if self._blocking or not self._project:
            return
        from core.models.settings import pair_key
        key = pair_key(tag_a, tag_b)
        cur = list(getattr(self._project.settings,
                           "collision_disabled_pairs", []) or [])
        new = [k for k in cur if k != key] if enabled else sorted(set(cur) | {key})
        self._set_setting("collision_disabled_pairs", new)

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
