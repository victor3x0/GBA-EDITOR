"""
ui/common/theme.py — Source unique du thème GBA Editor.

Usage :
    from ui.common.theme import C, T, QSS, GLOBAL_QSS

Couleurs via C :
    C.ACCENT_GRN   C.BG_INPUT   C.TEXT_DIM ...

Typographie via T :
    QFont(T.MONO, T.MD)   →  QFont("monospace", 9)
    QFont(T.CODE, T.LG)   →  QFont("Consolas",  11)
    f"font-size: {T.SM}px"  →  "font-size: 8px"

Fragments QSS via QSS :
    widget.setStyleSheet(QSS.spinbox)
    widget.setStyleSheet(QSS.checkbox)

Stylesheet globale à appliquer une seule fois dans main.py :
    app.setStyleSheet(GLOBAL_QSS)
"""

from pathlib import Path as _Path

# ──────────────────────────────────────────────────────────────────
#  Typographie — échelle de tailles et familles de polices
# ──────────────────────────────────────────────────────────────────

class _Typography:
    # Familles
    MONO = "monospace"   # labels, menus, inspector
    CODE = "Consolas"    # éditeur de code, callbacks Lua

    # Tailles (points pour QFont / pixels pour QSS — traitées identiquement)
    XS  = 9    # hints, sous-labels très discrets
    SM  = 10   # labels dim, boutons secondaires
    MD  = 11   # texte courant, menus, inputs
    MD2 = 12   # inputs légèrement plus grands (spinbox)
    LG  = 13   # titres section, sidebar éditeur
    XL  = 14   # titre projet, icônes larges
    XXL = 16   # très grands titres / icônes header


T = _Typography()


# ──────────────────────────────────────────────────────────────────
#  Palette de couleurs
# ──────────────────────────────────────────────────────────────────

class _Colors:
    # Fonds (du plus sombre au plus clair)
    BG_DEEP   = "#0e0e0e"   # barre statut, séparateurs forts
    BG_BASE   = "#141414"   # fond panels principaux
    BG_PANEL  = "#1a1a1a"   # fond widgets, inspector
    BG_RAISED = "#1e1e1e"   # menus, toolbars
    BG_INPUT  = "#252525"   # inputs (spinbox, lineedit, combobox)
    BG_HOVER  = "#2e2e2e"   # survol boutons
    BG_SEL    = "#1e3a2a"   # fond sélection verte

    # Bordures
    BORDER      = "#2e2e2e"  # bordure par défaut
    BORDER_MID  = "#383838"  # bordure inputs
    BORDER_DARK = "#232323"  # séparateurs discrets

    # Accents — couleurs sémantiques du projet
    ACCENT_GRN = "#4caf78"  # vert GBA  — sélection, transform, focus
    ACCENT_BLU = "#7ecfff"  # bleu      — components, refs Lua
    ACCENT_ORG = "#c48b3c"  # orange    — scripts, éditeur
    ACCENT_PRP = "#9b7bd5"  # violet    — prefabs
    ACCENT_RED = "#e05050"  # rouge     — erreurs, suppression
    ACCENT_YLW = "#e8c547"  # jaune     — avertissements

    # Textes
    TEXT_HI    = "#eeeeee"  # titre, valeurs importantes
    TEXT_NORM  = "#aaaaaa"  # texte courant
    TEXT_DIM   = "#666666"  # labels, hints
    TEXT_MUTED = "#444444"  # très discret

    # Axes vecteurs
    AXIS_X = "#c07070"   # rouge doux — axe X
    AXIS_Y = "#7090c0"   # bleu doux  — axe Y

    # Sélection panel
    SEL_BG     = "#192519"
    SEL_BORDER = "#4caf78"
    SEL_TEXT   = "#d0f0d8"


C = _Colors()


# ──────────────────────────────────────────────────────────────────
#  Petites flèches ▲▼ des QSpinBox — assets PNG livrés à côté de ce
#  module (référencés par CHEMIN, pas data-URI : le loader url() des QSS
#  ne supporte pas les data-URI, seuls les chemins/ressources marchent).
#  `.as_posix()` → slashs avant même sur Windows (QSS n'aime pas `\`).
# ──────────────────────────────────────────────────────────────────

_ICON_DIR = _Path(__file__).resolve().parent


def _spin_arrow(name: str) -> str:
    return _ICON_DIR.joinpath(name).as_posix()


# ──────────────────────────────────────────────────────────────────
#  Fragments QSS réutilisables widget par widget
# ──────────────────────────────────────────────────────────────────

class _QSS:

    @property
    def spinbox(self) -> str:
        return f"""
QSpinBox, QDoubleSpinBox {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 6px;
    font-family: monospace;
    font-size: {T.MD2}px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 15px; border: none; background: transparent;
    border-top-right-radius: 4px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 15px; border: none; background: transparent;
    border-bottom-right-radius: 4px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {C.BG_HOVER};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({_spin_arrow('spinbox_up.png')}); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({_spin_arrow('spinbox_down.png')}); width: 9px; height: 9px;
}}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{
    image: url({_spin_arrow('spinbox_up_hi.png')});
}}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{
    image: url({_spin_arrow('spinbox_down_hi.png')});
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {C.ACCENT_GRN};
}}
"""

    @property
    def lineedit(self) -> str:
        return f"""
QLineEdit {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 6px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
QLineEdit:focus {{
    border: 1px solid {C.ACCENT_GRN};
}}
QLineEdit:read-only {{
    color: {C.TEXT_DIM};
    background: {C.BG_PANEL};
}}
"""

    @property
    def checkbox(self) -> str:
        return f"""
QCheckBox {{
    color: {C.TEXT_NORM};
    font-family: monospace;
    font-size: {T.MD}px;
    spacing: 5px;
}}
QCheckBox::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid #444;
    border-radius: 2px;
    background: {C.BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT_GRN};
    border-color: {C.ACCENT_GRN};
}}
QCheckBox::indicator:hover {{
    border-color: {C.ACCENT_GRN};
}}
"""

    @property
    def combobox(self) -> str:
        return f"""
QComboBox {{
    background: {C.BG_INPUT};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 4px;
    padding: 3px 8px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
QComboBox:focus {{
    border: 1px solid {C.ACCENT_GRN};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {C.BG_RAISED};
    color: {C.TEXT_HI};
    border: 1px solid {C.BORDER_MID};
    border-radius: 0;
    selection-background-color: {C.BG_SEL};
    selection-color: {C.ACCENT_GRN};
    outline: none;
}}
"""

    @property
    def button_primary(self) -> str:
        return f"""
QPushButton {{
    background: #2a5c34;
    color: #c8ffc8;
    border: none;
    border-radius: 3px;
    padding: 4px 12px;
    font-family: monospace;
    font-size: {T.MD}px;
    font-weight: bold;
}}
QPushButton:hover  {{ background: #3a7a44; }}
QPushButton:pressed {{ background: #1e4828; }}
QPushButton:disabled {{ background: #1a3a24; color: #555; }}
"""

    @property
    def button_ghost(self) -> str:
        return f"""
QPushButton {{
    color: {C.TEXT_DIM};
    background: transparent;
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    padding: 2px 8px;
    font-family: monospace;
    font-size: {T.SM}px;
}}
QPushButton:hover {{ color: {C.TEXT_HI}; background: {C.BG_HOVER}; border-color: #444; }}
"""

    @property
    def button_icon(self) -> str:
        return f"""
QPushButton {{
    color: {C.TEXT_DIM};
    background: {C.BG_INPUT};
    border: 1px solid {C.BORDER_MID};
    border-radius: 3px;
    font-family: monospace;
    font-size: {T.XL}px;
}}
QPushButton:hover {{ color: {C.TEXT_HI}; background: {C.BG_HOVER}; border-color: #555; }}
"""

    @property
    def list_widget(self) -> str:
        return f"""
QListWidget {{
    background: #181818;
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    outline: none;
}}
QListWidget::item {{
    padding: 3px 6px;
    border-bottom: 1px solid {C.BORDER_DARK};
}}
QListWidget::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT_GRN};
    border-left: 2px solid {C.ACCENT_GRN};
}}
QListWidget::item:hover:!selected {{
    background: {C.BG_HOVER};
}}
"""

    @property
    def scrollbar(self) -> str:
        return f"""
QScrollBar:vertical {{
    background: {C.BG_BASE};
    width: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #383838;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #484848; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

QScrollBar:horizontal {{
    background: {C.BG_BASE};
    height: 8px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #383838;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: #484848; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""

    @property
    def splitter(self) -> str:
        return f"""
QSplitter::handle {{
    background: {C.BORDER};
}}
QSplitter::handle:horizontal {{
    width: 3px;
}}
QSplitter::handle:vertical {{
    height: 3px;
}}
QSplitter::handle:hover {{
    background: {C.ACCENT_GRN};
}}
"""

    @property
    def tooltip(self) -> str:
        return f"""
QToolTip {{
    background: #1c1c1c;
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER_MID};
    padding: 5px 8px;
    border-radius: 4px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
"""

    @property
    def menu(self) -> str:
        return f"""
QMenu {{
    background: {C.BG_RAISED};
    color: {C.TEXT_NORM};
    border: 1px solid {C.BORDER_MID};
    font-family: monospace;
    font-size: {T.MD}px;
    padding: 2px;
}}
QMenu::item {{
    padding: 4px 20px 4px 12px;
    border-radius: 2px;
}}
QMenu::item:selected {{
    background: {C.BG_SEL};
    color: {C.ACCENT_GRN};
}}
QMenu::separator {{
    height: 1px;
    background: {C.BORDER};
    margin: 3px 6px;
}}
"""

    @property
    def toolbar(self) -> str:
        return f"""
QToolBar {{
    background: {C.BG_RAISED};
    border-bottom: 1px solid {C.BORDER};
    spacing: 4px;
    padding: 2px 8px;
}}
QToolButton {{
    color: {C.TEXT_NORM};
    border: none;
    padding: 4px 8px;
    font-family: monospace;
    font-size: {T.MD}px;
    border-radius: 3px;
}}
QToolButton:hover {{
    background: {C.BG_HOVER};
    color: {C.TEXT_HI};
}}
QToolButton:checked {{
    background: #2a3a2a;
    color: {C.ACCENT_GRN};
}}
"""

    @property
    def menubar(self) -> str:
        return f"""
QMenuBar {{
    background: {C.BG_RAISED};
    color: {C.TEXT_NORM};
    font-family: monospace;
    font-size: {T.MD}px;
    border-bottom: 1px solid {C.BORDER};
}}
QMenuBar::item:selected {{ background: {C.BG_HOVER}; }}
QMenuBar::item:pressed  {{ background: {C.BG_SEL}; color: {C.ACCENT_GRN}; }}
"""

    @property
    def statusbar(self) -> str:
        return f"""
QStatusBar {{
    background: {C.BG_DEEP};
    color: {C.TEXT_DIM};
    font-family: monospace;
    font-size: {T.SM}px;
    border-top: 1px solid {C.BORDER};
}}
"""

    @property
    def tab(self) -> str:
        return f"""
QTabWidget::pane {{
    border: 1px solid {C.BORDER};
    background: {C.BG_PANEL};
}}
QTabBar::tab {{
    background: {C.BG_RAISED};
    color: {C.TEXT_DIM};
    border: 1px solid {C.BORDER};
    border-bottom: none;
    padding: 4px 12px;
    font-family: monospace;
    font-size: {T.MD}px;
}}
QTabBar::tab:selected {{
    background: {C.BG_PANEL};
    color: {C.ACCENT_GRN};
    border-top: 2px solid {C.ACCENT_GRN};
}}
QTabBar::tab:hover:!selected {{
    background: {C.BG_HOVER};
    color: {C.TEXT_NORM};
}}
"""


QSS = _QSS()


# ──────────────────────────────────────────────────────────────────
#  Stylesheet globale — à passer UNE SEULE FOIS à app.setStyleSheet()
#  Couvre tous les widgets standard sans setStyleSheet() individuel.
# ──────────────────────────────────────────────────────────────────

GLOBAL_QSS = (
    QSS.tooltip
    + QSS.menu
    + QSS.menubar
    + QSS.toolbar
    + QSS.statusbar
    + QSS.scrollbar
    + QSS.splitter
    + QSS.spinbox
    + QSS.lineedit
    + QSS.checkbox
    + QSS.combobox
    + QSS.list_widget
)
