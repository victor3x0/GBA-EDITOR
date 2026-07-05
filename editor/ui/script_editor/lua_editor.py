"""ui/script_editor/lua_editor.py — coloration syntaxique Lua + widget d'édition."""
from PyQt6.QtWidgets import QPlainTextEdit
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PyQt6.QtCore import QRegularExpression

from ui.common.theme import C, T

class LuaHighlighter(QSyntaxHighlighter):

    _KEYWORDS = (
        r"\bfunction\b", r"\bend\b", r"\bif\b", r"\bthen\b",
        r"\belseif\b", r"\belse\b", r"\bwhile\b", r"\bdo\b",
        r"\bfor\b", r"\breturn\b", r"\blocal\b", r"\band\b",
        r"\bor\b", r"\bnot\b", r"\btrue\b", r"\bfalse\b",
        r"\bnil\b", r"\bbreak\b", r"\bin\b", r"\brepeat\b",
        r"\buntil\b",
    )
    _API_MODULES = (
        r"\bself\b", r"\bsfx\b", r"\bmusic\b",
        r"\binput\b", r"\bglobal\b", r"\bsend\b", r"\bbroadcast\b",
        r"\bcamera\b", r"\bdisplay\b", r"\bmath\b",
    )

    def __init__(self, doc):
        super().__init__(doc)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        def fmt(color: str, bold=False, italic=False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:   f.setFontWeight(700)
            if italic: f.setFontItalic(True)
            return f

        kw_fmt = fmt("#c586c0", bold=True)
        for p in self._KEYWORDS:
            self._rules.append((QRegularExpression(p), kw_fmt))

        api_fmt = fmt("#4ec9b0")
        for p in self._API_MODULES:
            self._rules.append((QRegularExpression(p), api_fmt))

        self._rules.append((QRegularExpression(r"\b0x[0-9a-fA-F]+\b|\b\d+\.?\d*\b"),
                            fmt("#b5cea8")))
        self._str_fmt = fmt("#ce9178")
        self._rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'), self._str_fmt))
        self._rules.append((QRegularExpression(r"'[^'\\]*(\\.[^'\\]*)*'"), self._str_fmt))
        self._cmt_fmt = fmt("#6a9955", italic=True)
        self._rules.append((QRegularExpression(r"--[^\n]*"), self._cmt_fmt))

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ─── Éditeur de code ──────────────────────────────────────────────────

class LuaEditor(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont(T.CODE, T.LG)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet(
            f"QPlainTextEdit{{"
            f"  background:{C.BG_RAISED}; color:{C.TEXT_HI};"
            f"  border:none; padding:4px;"
            f"}}"
        )
        self.setTabStopDistance(32)
        self._hl = LuaHighlighter(self.document())

    def jump_to_function(self, func_name: str):
        doc = self.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            if f"function {func_name}" in block.text():
                cur = QTextCursor(block)
                cur.movePosition(QTextCursor.MoveOperation.NextBlock)
                cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cur)
                self.ensureCursorVisible()
                return

    def insert_at_cursor(self, text: str):
        """Insère text à la position courante du curseur."""
        cur = self.textCursor()
        cur.insertText(text)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        self.setFocus()

    def insert_stub(self, stub: str):
        """Insère un stub en fin de document, saute au corps."""
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if not self.toPlainText().endswith("\n"):
            cur.insertText("\n")
        cur.insertText("\n" + stub)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
