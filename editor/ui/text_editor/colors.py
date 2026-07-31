"""
ui/text_editor/colors.py — les deux familles de couleur de l'écran Texte.

Point unique : c'est la couleur qui dit lequel des deux concepts on regarde,
du finder à l'inspecteur.
"""
from ui.common.theme import C


FONT_COLOR = C.ACCENT_ORG    # famille « police » (asset)
TEXT_COLOR = C.ACCENT        # famille « texte » (contenu) — accent primaire
