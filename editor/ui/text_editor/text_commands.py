"""
ui/text_editor/text_commands.py — commandes annulables de l'écran Texte.

Regroupées ici : ce sont les seules à connaître les effets de bord d'une
édition (réécriture des `text.draw` des scripts, remesure des chasses), que les
vues n'ont pas à porter.
"""
from __future__ import annotations

from core.history import Command


class RenameTextKeyCmd(Command):
    """Renomme une clé de texte.

    L'undo repasse par `Project.rename_text_key` en sens inverse : elle réécrit
    aussi les `text.draw("clé")` des scripts, remettre le champ ne suffirait pas.
    """

    def __init__(self, project, text, old_key: str, new_key: str,
                 old_auto: bool, persist_fn=None):
        self._project = project
        self._text = text
        self._old = old_key
        self._new = new_key
        # Passé par l'appelant : le renommage a déjà eu lieu et a mis auto_key
        # à False, le lire ici restaurerait la nouvelle valeur.
        self._old_auto = old_auto
        self.label = f"Renommer texte → {new_key}"
        self._persist = persist_fn
        self._first = True   # le renommage a déjà été appliqué par l'appelant

    def execute(self):
        if self._first:
            self._first = False        # premier passage : déjà fait
        else:
            self._project.rename_text_key(self._text, self._new)
        if self._persist:
            self._persist()

    def undo(self):
        self._project.rename_text_key(self._text, self._old)
        self._text.auto_key = self._old_auto   # garde le badge « auto » cohérent
        if self._persist:
            self._persist()


class SetTextPathCmd(Command):
    """Range un ou plusieurs textes (déplacer une entrée = renommer un nœud, à
    l'échelle près).

    Les clés AUTO se recalent derrière — donc les scripts sont réécrits ; les
    clés nommées à la main ne bougent pas (contrat de `auto_key`).
    """

    def __init__(self, project, entries, label: str, persist_fn=None):
        self._project = project
        # (texte, ancien chemin, nouveau chemin, ancienne clé) — la clé est
        # capturée MAINTENANT, avant le premier execute().
        self._entries = [(t, list(old), list(new), t.key) for t, old, new in entries]
        self.label = label
        self._persist = persist_fn

    def execute(self):
        for t, _old, new, _key in self._entries:
            t.path = list(new)
            self._project.resync_text_key(t)
        if self._persist:
            self._persist()

    def undo(self):
        for t, old, _new, key in self._entries:
            t.path = list(old)
            # `restore` et non `resync` : le rang `_NN` d'une clé dérivée dépend
            # des clés prises à l'instant du calcul, la rejouer ne rendrait pas
            # forcément la même.
            if t.auto_key:
                self._project.restore_text_key(t, key)
        if self._persist:
            self._persist()


class RelinkTextKeyCmd(Command):
    """Ré-accroche une clé nommée à la main à son chemin de rangement — exact
    inverse du renommage manuel : elle redevient dérivée."""

    def __init__(self, project, text, persist_fn=None):
        self._project = project
        self._text = text
        self._old_key = text.key
        self.label = f"Ré-accrocher {text.key} au rangement"
        self._persist = persist_fn

    def execute(self):
        self._text.auto_key = True
        self._project.resync_text_key(self._text)
        if self._persist:
            self._persist()

    def undo(self):
        self._project.restore_text_key(self._text, self._old_key)
        self._text.auto_key = False
        if self._persist:
            self._persist()


class SetKeyColorCmd(Command):
    """Désigne (ou retire) une couleur-clé.

    La couleur d'espacement gouverne la chasse : les `Glyph.advance` de toute la
    planche sont relus derrière, et l'undo doit rendre les deux.
    """

    def __init__(self, project, font, field: str, old, new,
                 label: str, persist_fn=None):
        self._project = project
        self._font = font
        self._field = field
        self._old, self._new = old, new
        self._advances_before = [g.advance for g in font.glyphs]
        self.label = label
        self._persist = persist_fn

    def _apply(self, value, advances=None):
        setattr(self._font, self._field, value)
        if advances is not None:
            for g, a in zip(self._font.glyphs, advances):
                g.advance = a
        else:
            self._remeasure()
        if self._persist:
            self._persist()

    def _remeasure(self):
        """Relit les chasses sur la planche (la règle d'autorité est dans
        `font_import.remeasure_advances`)."""
        f = self._font
        if not f.asset or not self._project:
            return
        from core.font_import import remeasure_advances
        remeasure_advances(f, self._project.asset_abs(f.asset))

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old, self._advances_before)


class ResliceFontCmd(Command):
    """Re-découpe la planche à une autre taille de cellule.

    Destructive : la liste de glyphes est remplacée, les corrections de
    caractères sont perdues — d'où l'instantané complet.
    """

    def __init__(self, project, font, fields: dict, persist_fn=None):
        self._project = project
        self._font = font
        self._fields = fields
        self._before = {
            "cell_w": font.cell_w, "cell_h": font.cell_h,
            "line_height": font.line_height, "glyphs": list(font.glyphs),
        }
        self.label = f"Re-découper {font.name} en {fields.get('cell_w')}×{fields.get('cell_h')}"
        self._persist = persist_fn

    def execute(self):
        from core.font_import import apply_font_import
        apply_font_import(self._font, self._fields)
        if self._persist:
            self._persist()

    def undo(self):
        for k, v in self._before.items():
            setattr(self._font, k, list(v) if k == "glyphs" else v)
        if self._persist:
            self._persist()


class MergeGlyphsCmd(Command):
    """Rend annulable la fusion calculée par `Font.merged_glyphs`.

    Instantané complet de la liste : la fusion remplace des glyphes, elle n'en
    modifie aucun.
    """

    def __init__(self, font, indices: list, char: str, persist_fn=None):
        self._font = font
        self._before = list(font.glyphs)
        self._after, self.merged = font.merged_glyphs(indices, char)
        self.label = f"Fusionner {len(indices)} cases"
        self._persist = persist_fn

    def execute(self):
        self._font.glyphs = list(self._after)
        if self._persist:
            self._persist()

    def undo(self):
        self._font.glyphs = list(self._before)
        if self._persist:
            self._persist()
