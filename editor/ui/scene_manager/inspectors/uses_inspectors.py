"""
PrefabUsesInspector / ScriptUsesInspector / VariableUsesInspector.

Trois vues "Voir les utilisations" affichées dans l'inspector, groupées dans
un seul fichier car structurellement proches (header coloré + section bar +
liste + vidage de liste) — d'où la base commune _UsesInspectorBase ci-dessous.
Chaque sous-classe ne diffère que par ses couleurs, son bouton d'action
optionnel, et la façon dont elle peuple la liste (load()), qui reste propre
à son domaine (instances de prefab / actors utilisant un script / scripts
référençant une variable).
"""
from __future__ import annotations
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QScrollArea,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal

from core.selection_bus import get_bus
from ui.common.theme import C, T


# ──────────────────────────────────────────────────────────────────
#  Base commune : header coloré + section bar (+ bouton d'action
#  optionnel) + liste scrollable + helpers de construction de lignes.
# ──────────────────────────────────────────────────────────────────
class _UsesInspectorBase(QWidget):
    _HEADER_COLOR = C.ACCENT_GRN
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = ""
    _ACTION_BTN_TEXT: str | None = None
    _ACTION_BTN_COLOR: str | None = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_PANEL};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header coloré avec nom de l'élément inspecté ──────────
        self._top = QFrame()
        self._top.setFixedHeight(40)
        self._top.setStyleSheet(
            f"background:{self._HEADER_COLOR}{self._HEADER_BG_ALPHA}; "
            f"border-bottom:1px solid {self._HEADER_COLOR}{self._HEADER_BORDER_ALPHA};"
        )
        tl = QHBoxLayout(self._top)
        tl.setContentsMargins(12, 0, 8, 0)
        self._name_lbl = QLabel("")
        self._name_lbl.setFont(QFont(T.MONO, T.LG, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color:{C.TEXT_HI};")
        btn_close = QPushButton("v")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet(
            f"QPushButton{{color:{self._HEADER_COLOR};background:transparent;border:none;"
            "font-family:monospace;font-size:10px;}"
            f"QPushButton:hover{{color:{C.TEXT_HI};}}"
        )
        btn_close.setToolTip("Fermer cette vue")
        btn_close.clicked.connect(self._on_close)
        tl.addWidget(self._name_lbl, 1)
        tl.addWidget(btn_close)
        root.addWidget(self._top)

        # ── Barre de section (titre + bouton d'action optionnel) ──
        sec_bar = QFrame()
        sec_bar.setFixedHeight(28)
        sec_bar.setStyleSheet(f"background:{C.BG_DEEP}; border-bottom:1px solid {C.BORDER_DARK};")
        sl = QHBoxLayout(sec_bar)
        sl.setContentsMargins(10, 0, 8, 0)
        self._sec_lbl = QLabel(self._SECTION_TITLE)
        self._sec_lbl.setFont(QFont(T.MONO, T.SM, QFont.Weight.Bold))
        self._sec_lbl.setStyleSheet(f"color:{C.TEXT_MUTED}; letter-spacing:1px;")
        sl.addWidget(self._sec_lbl, 1)
        if self._ACTION_BTN_TEXT:
            self._action_btn = QPushButton(self._ACTION_BTN_TEXT)
            self._action_btn.setFont(QFont(T.MONO, T.SM))
            self._action_btn.setFixedHeight(20)
            self._action_btn.setStyleSheet(
                f"QPushButton{{color:{self._ACTION_BTN_COLOR};background:transparent;border:none;"
                "font-family:monospace;font-size:8px;}"
                f"QPushButton:hover{{color:{C.TEXT_HI};}}"
            )
            self._action_btn.clicked.connect(self._on_action)
            sl.addWidget(self._action_btn)
        root.addWidget(sec_bar)

        # ── Liste des utilisations ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_container = QWidget()
        self._list_container.setStyleSheet(f"background:{C.BG_PANEL};")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 4, 0, 8)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

    # ── Helpers de construction de liste, communs aux sous-classes ──

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            old_w = item.widget()
            if old_w:
                # hide() avant setParent(None) : un widget visible détaché de
                # son parent redevient une fenêtre top-level à part entière.
                old_w.hide()
                old_w.setParent(None)
                old_w.deleteLater()

    def _add_empty_row(self, text: str):
        empty = QLabel(f"  {text}")
        empty.setFont(QFont(T.MONO, T.MD))
        empty.setStyleSheet("color:#444; padding:12px;")
        self._list_layout.addWidget(empty)

    def _add_group_row(self, icon: str, label: str, color: str, count: int | None = None):
        row = QFrame()
        row.setFixedHeight(24)
        row.setStyleSheet(f"background:{C.BG_RAISED};")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 8, 0)
        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont(T.MONO, T.MD))
        icon_lbl.setStyleSheet(f"color:{color};")
        icon_lbl.setFixedWidth(16)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.MONO, T.MD))
        name_lbl.setStyleSheet(f"color:{color};")
        rl.addWidget(icon_lbl)
        rl.addWidget(name_lbl, 1)
        if count is not None:
            count_lbl = QLabel(f"×{count}")
            count_lbl.setFont(QFont(T.MONO, T.SM))
            count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
            rl.addWidget(count_lbl)
        self._list_layout.addWidget(row)

    def _add_leaf_row(self, label: str, on_click):
        leaf = QFrame()
        leaf.setFixedHeight(22)
        leaf.setStyleSheet(f"background:{C.BG_PANEL};")
        leaf.setCursor(Qt.CursorShape.PointingHandCursor)
        ll = QHBoxLayout(leaf)
        ll.setContentsMargins(28, 0, 8, 0)
        icon_lbl = QLabel("·")
        icon_lbl.setFont(QFont(T.MONO, T.MD2))
        icon_lbl.setStyleSheet(f"color:{C.BORDER_MID};")
        icon_lbl.setFixedWidth(12)
        name_lbl = QLabel(label)
        name_lbl.setFont(QFont(T.MONO, T.MD))
        name_lbl.setStyleSheet(f"color:{C.TEXT_DIM};")
        ll.addWidget(icon_lbl)
        ll.addWidget(name_lbl, 1)
        self._list_layout.addWidget(leaf)
        leaf.mousePressEvent = lambda e, cb=on_click: cb()

    # ── Actions par défaut, surchargeables ───────────────────────────

    def _on_action(self):
        pass

    def _on_close(self):
        get_bus().clear()


# ──────────────────────────────────────────────────────────────────
#  PrefabUsesInspector — liste des instances d'un prefab par scène
# ──────────────────────────────────────────────────────────────────
class PrefabUsesInspector(_UsesInspectorBase):
    """
    Vue 'PREFAB USES' affichée dans l'inspector quand on clique
    'Voir les instances' dans le panneau projet.

    Structure :
        ┌─ Header bleu : nom du prefab  ────────── [v] ─┐
        │  PREFAB USES              [Éditer le prefab]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        │      · Actor 2                                │
        │  ▸ Scene B                                    │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(object)   # Prefab — demande d'édition

    _HEADER_COLOR = C.ACCENT_BLU
    _HEADER_BG_ALPHA = "30"
    _HEADER_BORDER_ALPHA = "50"
    _SECTION_TITLE = "PREFAB USES"
    _ACTION_BTN_TEXT = "Éditer le prefab"
    _ACTION_BTN_COLOR = "#7ecfff"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prefab  = None
        self._project = None

    # ── Chargement ────────────────────────────────────────────────

    def load(self, prefab, project):
        self._prefab  = prefab
        self._project = project
        self._name_lbl.setText(prefab.name)
        self._clear_list()

        # Parcourir toutes les scènes pour trouver les instances liées
        found_any = False
        for scene in project.scenes:
            linked = [a for a in scene.actors if a.prefab_name == prefab.name]
            if not linked:
                continue
            found_any = True
            self._add_group_row("◈", scene.name, "#7ecfff", count=len(linked))
            for actor in linked:
                # Clic → sélectionner l'actor dans la scène active
                self._add_leaf_row(actor.name, lambda a=actor: get_bus().select(a))

        if not found_any:
            self._add_empty_row("Aucune instance dans le projet.")

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_action(self):
        if self._prefab:
            self.edit_requested.emit(self._prefab)

    def _on_close(self):
        """Renvoie à la vue précédente via le bus (re-sélectionne le prefab)."""
        if self._prefab:
            get_bus().select(self._prefab)


# ──────────────────────────────────────────────────────────────────
#  ScriptUsesInspector — liste des actors qui utilisent un script
# ──────────────────────────────────────────────────────────────────
class ScriptUsesInspector(_UsesInspectorBase):
    """
    Vue 'SCRIPT USES' — affiche toutes les scènes et actors
    qui ont un ScriptComponent pointant vers ce fichier script.

    Structure :
        ┌─ Header orange : nom du script  ──────── [v] ─┐
        │  SCRIPT USES              [Éditer le script]  │
        │  ▸ Scene A                                    │
        │      · Actor 1                                │
        └────────────────────────────────────────────────┘
    """
    edit_requested = pyqtSignal(str)   # path du script

    _HEADER_COLOR = C.ACCENT_ORG
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = "SCRIPT USES"
    _ACTION_BTN_TEXT = "Éditer le script"
    _ACTION_BTN_COLOR = C.ACCENT_ORG

    def __init__(self, parent=None):
        super().__init__(parent)
        self._script_path = None
        self._project     = None

    # ── Chargement ────────────────────────────────────────────────

    def load(self, script_path: str, project):
        self._script_path = script_path
        self._project     = project

        name = Path(script_path).name
        self._name_lbl.setText(name)
        self._clear_list()

        found_any = False

        # ── Acteurs placés dans une scène (inline ou instance de prefab) ──
        for scene in project.scenes:
            linked = [
                a for a in scene.actors
                if a.get_component("script") is not None
                and Path(a.get_component("script").script or "").name == name
            ]
            if not linked:
                continue
            found_any = True
            self._add_group_row("✦", scene.name, C.ACCENT_ORG, count=len(linked))
            for actor in linked:
                self._add_leaf_row(actor.name, lambda a=actor: get_bus().select(a))

        # ── Prefabs (template — inclut les prefabs spawnés par script, jamais
        #    placés dans scene.actors, donc invisibles à la boucle ci-dessus) ──
        linked_prefabs = [
            pf for pf in project.prefabs
            if pf.get_component("script") is not None
            and Path(pf.get_component("script").script or "").name == name
        ]
        if linked_prefabs:
            found_any = True
            self._add_group_row("◆", "PREFABS", C.ACCENT_BLU)
            for pf in linked_prefabs:
                self._add_leaf_row(pf.name, lambda p=pf: get_bus().select(p))

        # ── Scripts de scène (Scene.script — distinct des scripts d'actor) ──
        linked_scenes = [s for s in project.scenes if Path(s.script or "").name == name]
        if linked_scenes:
            found_any = True
            self._add_group_row("▤", "SCRIPTS DE SCÈNE", C.ACCENT_ORG)
            for scene in linked_scenes:
                self._add_leaf_row(scene.name, lambda s=scene: get_bus().select(s))

        if not found_any:
            self._add_empty_row("Aucun actor n'utilise ce script.")

        self._list_layout.addStretch()

    # ── Actions ───────────────────────────────────────────────────

    def _on_action(self):
        if self._script_path:
            self.edit_requested.emit(self._script_path)


class VariableUsesInspector(_UsesInspectorBase):
    """
    Vue 'GLOBAL USES' / 'CONSTANT USES' — recherche textuelle réelle des
    appels global.get/global.set (kind="global") ou const.get (kind="const")
    référençant ce nom, dans tous les scripts .lua du projet.

    Contrairement à PrefabUsesInspector/ScriptUsesInspector (comparaison
    structurelle sur les objets Actor/Scene/Prefab du projet), une variable
    ou constante n'a pas de "placement" — seul le contenu des scripts peut
    dire qui la référence. D'où une ligne de résultat différente (pas de
    distinction groupe/feuille, un compteur d'occurrences par script).
    """
    edit_requested = pyqtSignal(str)   # chemin absolu du script à ouvrir

    _LABELS = {"global": "GLOBAL USES", "const": "CONSTANT USES"}

    _HEADER_COLOR = C.ACCENT_GRN
    _HEADER_BG_ALPHA = "25"
    _HEADER_BORDER_ALPHA = "40"
    _SECTION_TITLE = "GLOBAL USES"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "global"
        self._name = ""

    # ── Chargement ────────────────────────────────────────────────

    def load(self, kind: str, name: str, project):
        self._kind = kind
        self._name = name
        self._name_lbl.setText(name)
        self._sec_lbl.setText(self._LABELS.get(kind, "USES"))
        self._clear_list()

        if kind == "const":
            patterns = [rf'const\.get\(\s*"{re.escape(name)}"']
        else:
            patterns = [
                rf'global\.get\(\s*"{re.escape(name)}"',
                rf'global\.set\(\s*"{re.escape(name)}"',
            ]
        combined = re.compile("|".join(patterns))

        script_dirs = [
            getattr(project, "scripts_actors_dir", None),
            getattr(project, "scripts_scenes_dir", None),
            getattr(project, "scripts_behaviors_dir", None),
        ]

        found_any = False
        for d in script_dirs:
            if not d or not Path(d).exists():
                continue
            for script_path in sorted(Path(d).rglob("*.lua")):
                try:
                    text = script_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                count = len(combined.findall(text))
                if count == 0:
                    continue
                found_any = True
                self._add_row(script_path, count)

        if not found_any:
            self._add_empty_row(f"Aucun script n'utilise « {name} ».")

        self._list_layout.addStretch()

    def _add_row(self, script_path: Path, count: int):
        row = QFrame()
        row.setFixedHeight(24)
        row.setStyleSheet(f"background:{C.BG_RAISED};")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 0, 8, 0)
        icon_lbl = QLabel("λ")
        icon_lbl.setFont(QFont(T.MONO, T.MD))
        icon_lbl.setStyleSheet(f"color:{C.ACCENT_GRN};")
        icon_lbl.setFixedWidth(16)
        name_lbl = QLabel(script_path.name)
        name_lbl.setFont(QFont(T.MONO, T.MD))
        name_lbl.setStyleSheet(f"color:{C.ACCENT_GRN};")
        count_lbl = QLabel(f"×{count}")
        count_lbl.setFont(QFont(T.MONO, T.SM))
        count_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
        rl.addWidget(icon_lbl)
        rl.addWidget(name_lbl, 1)
        rl.addWidget(count_lbl)
        self._list_layout.addWidget(row)
        row.mousePressEvent = lambda e, p=str(script_path): self.edit_requested.emit(p)
