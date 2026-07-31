"""ui.text_editor — écran Text Editor (polices + table de textes).

Un fichier par sous-zone de l'écran ; `text_editor_screen.py` n'assemble plus
que les trois colonnes et arbitre le contexte actif (la carte des modules est
en tête de ce fichier).

Import de compat :
    from ui.text_editor import TextEditorScreen
"""

from ui.text_editor.text_editor_screen import TextEditorScreen

__all__ = ["TextEditorScreen"]
