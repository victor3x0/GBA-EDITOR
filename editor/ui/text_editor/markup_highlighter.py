"""
ui/text_editor/markup_highlighter.py — coloration des balises dans l'atelier.

Ne redit PAS la grammaire : la coloration lit les spans que `text_markup.parse`
produit déjà. Une seconde grammaire en expressions régulières aurait menti au
premier ajout de balise, et surtout elle aurait coloré ce que le parseur
refuse — un `[wav]` fautif se lirait comme une balise valide alors qu'il
s'affichera tel quel en jeu.

C'est aussi ce qui rend la coloration HONNÊTE : ce qui est peint est exactement
ce qui disparaîtra du rendu, et ce qui est souligné est exactement ce que
l'inspecteur signale.
"""
from __future__ import annotations

from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont

from core.text_markup import (
    parse, TOK_TAG, TOK_CLOSE, TOK_VALUE, TOK_ESCAPE,
)
from ui.common.icons import COLOR_GLOBAL
from ui.common.theme import C


class MarkupHighlighter(QSyntaxHighlighter):
    """Peint les balises reconnues et souligne ce qui cloche.

    L'analyse porte sur le document ENTIER, pas sur le bloc courant : une
    portée `[wave]…[/wave]` peut enjamber un retour à la ligne, et Qt ne
    colore que bloc par bloc. On analyse donc une fois par frappe et on
    reprojette les spans dans chaque bloc.
    """

    def __init__(self, doc):
        super().__init__(doc)
        self._src = None
        self._parsed = None

        def fmt(color: str, *, bold=False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        self._fmt = {
            # Une balise est une INSTRUCTION, pas du texte : elle se lit d'un
            # coup d'œil comme telle, et on voit du même geste ce qui ne sera
            # pas affiché.
            TOK_TAG:    fmt(C.ACCENT_BLU, bold=True),
            TOK_CLOSE:  fmt(C.ACCENT_BLU),
            # Même couleur que les globals ailleurs dans l'éditeur : c'est la
            # même chose qu'on désigne.
            TOK_VALUE:  fmt(COLOR_GLOBAL, bold=True),
            # Un échappement s'affiche, lui — d'où le gris : présent, discret.
            TOK_ESCAPE: fmt(C.TEXT_MUTED),
        }

    def _analysis(self):
        """L'analyse du document courant, refaite seulement si le texte a
        changé — Qt rappelle `highlightBlock` une fois par bloc touché."""
        src = self.document().toPlainText()
        if src != self._src:
            self._src = src
            self._parsed = parse(src)
        return self._parsed

    def highlightBlock(self, text: str):
        parsed = self._analysis()
        if parsed is None:
            return
        start = self.currentBlock().position()
        end = start + len(text)

        def paint(a: int, b: int, f):
            """Découpe un span du DOCUMENT dans le bloc courant."""
            a, b = max(a, start), min(b, end)
            if a < b:
                self.setFormat(a - start, b - a, f)

        for t in parsed.tokens:
            paint(t.at, t.end, self._fmt[t.kind])
        # Les anomalies s'AJOUTENT à la couleur déjà posée, caractère par
        # caractère : un `[wave]` jamais refermé est une balise valide dont la
        # fin manque — il doit rester peint en balise ET être souligné. Poser
        # un format entier ici l'aurait repeint en texte ordinaire, ce qui
        # aurait dit l'inverse.
        for i in parsed.issues:
            a = max(i.at, start)
            b = min(max(i.end, i.at + 1), end)
            for pos in range(a, b):
                f = QTextCharFormat(self.format(pos - start))
                f.setUnderlineStyle(
                    QTextCharFormat.UnderlineStyle.WaveUnderline)
                f.setUnderlineColor(QColor(C.ACCENT_YLW))
                self.setFormat(pos - start, 1, f)
