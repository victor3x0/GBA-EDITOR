"""Data Editor screen — les tables de données du projet.

Remplace l'écriteau « Tileset Manager », qui annonçait un écran devenu sans
objet : le tileset comme asset de premier rang est sorti du périmètre en v0.4
(« ce logiciel n'est pas un outil de dessin »), et l'entrée de navigation
promettait donc quelque chose qui ne viendra pas.

Layout : 3 colonnes (même modèle que le Palette Editor)
  Gauche  : les tables du projet          (AssetFinder — composant partagé)
  Centre  : la grille de la table active  (DataGridPanel)
  Droite  : la colonne et la cellule      (DataInspectorPanel)

Un script lit une table par indexation — `data.Objets[i].prix` — et le build
l'émet en `const` dans la ROM. C'est pour ça que le nom d'une table et celui de
ses colonnes sont des IDENTIFIANTS et non des libellés : ils s'écrivent comme
du code, sans guillemets.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from ui.common.theme import C, QSS
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import DATA_TABLES
from core.project import Project

from .data_grid_panel import DataGridPanel
from .data_inspector_panel import DataInspectorPanel


class DataEditorScreen(QWidget):
    """Écran complet : finder + grille + inspecteur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self.setStyleSheet(f"background:{C.BG_PANEL};")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(QSS.splitter)
        root.addWidget(split, 1)

        self._finder    = AssetFinder("Data finder", [DATA_TABLES],
                                      min_width=200, max_width=360)
        self._grid      = DataGridPanel()
        self._inspector = DataInspectorPanel()

        split.addWidget(self._finder)
        split.addWidget(self._grid)
        split.addWidget(self._inspector)
        split.setSizes([240, 700, 300])
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)     # la grille absorbe le redimensionnement
        split.setStretchFactor(2, 0)
        split.setCollapsible(1, False)

        # Le finder rend l'ASSET, la grille travaille par nom : c'est ici, et
        # nulle part dans le finder, que se fait la conversion — le composant
        # partagé ne connaît aucune famille en particulier.
        self._finder.selected.connect(lambda _kind, t: self._grid.show_table(t.name))
        self._finder.emptied.connect(lambda _kind: self._grid.on_table_deleted())
        # La grille écrit, l'inspecteur détaille : un seul chemin d'écriture,
        # donc un seul endroit qui pousse dans l'historique.
        self._grid.cell_selected.connect(self._inspector.set_selection)
        self._grid.table_changed.connect(self._finder.refresh)
        self._inspector.type_changed.connect(self._grid.set_column_type)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project: Project):
        self._project = project
        self._finder.load_project(project)
        self._grid.load_project(project)
        self._inspector.load_project(project)

    def refresh(self):
        """Le projet a changé sous l'écran (undo, renommage ailleurs)."""
        if not self._project:
            return
        name = self._grid.table_name
        self._finder.refresh()
        table = self._project.data_tables.get(name) if name else None
        if table is not None:
            self._finder.select(DATA_TABLES.label, table)
