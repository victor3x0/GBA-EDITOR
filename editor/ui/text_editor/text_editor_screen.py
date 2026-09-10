"""
ui/text_editor/text_editor_screen.py — écran Text Editor.

Un seul écran pour deux concepts distincts mais qui se croisent en permanence
(cf. mémoire project_text_font_screen_design) :

  • Police (`Font`)  — un asset réutilisable, importé (PNG / BMFont `.fnt`).
  • Texte (`Text`)   — une entrée référencée par clé, rangée dans un arbre.

Ils cohabitent parce que `Font.missing_chars()` et l'aperçu d'un texte ont
besoin des deux sous les yeux ; les modèles, eux, restent séparés.

Trois colonnes : polices à gauche, table des textes + atelier d'écriture au
centre, inspecteur CONTEXTUEL à droite. Le centre et l'inspecteur basculent par
la SÉLECTION, jamais par un onglet (police → contexte police, texte ou clic
dans le vide → contexte texte). Pattern du Scene Manager, mais câblé en signaux
Qt LOCAUX : le bus global est partagé avec un inspecteur qui ne connaît pas
`Font`/`Text`.

« Textes », jamais « Dialogue » : la table range, elle n'enchaîne pas. Le
séquencement reste du script — la neutralité de style est une décision de
ROADMAP v0.3.2.

Un fichier par sous-zone ; ce module n'assemble que les colonnes et arbitre le
contexte actif :

  colors.py               les deux familles de couleur (police / texte)
  glyph_paint.py          trouage des couleurs-clés + damier
  text_commands.py        commandes annulables (clé, rangement, planche)
  (colonne gauche : AssetFinder — composant partagé, cf. ui/common/asset_finder.py)
  text_panel.py           colonne centre, contexte Texte — arbitre les deux
  text_table.py           la table des textes (haut du centre)
  text_workbench.py       l'atelier d'écriture (bas du centre)
  font_screen_preview.py  aperçu écran GBA (monté par l'atelier)
  markup_toolbar.py       boutons de balisage de l'atelier (dérivés de TAGS)
  glyph_sheet.py          planche de glyphes (canvas)
  glyph_sheet_panel.py    colonne centre, contexte Police — planche + outils
  inspector_shell.py      coquille commune aux deux inspecteurs
  text_inspector.py       colonne droite, contexte Texte
  font_inspector.py       colonne droite, contexte Police
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter, QStackedWidget, QMessageBox,
)
from PyQt6.QtCore import Qt

from core.history import get_history, SetFieldCmd
from ui.common.theme import C
from ui.common.labels import label
from ui.text_editor.colors import TEXT_COLOR
from ui.common.asset_finder import AssetFinder
from ui.common.asset_kinds import FONTS
from ui.text_editor.text_panel import TextPanel
from ui.text_editor.glyph_sheet_panel import GlyphSheetPanel
from ui.text_editor.text_inspector import TextInspector
from ui.text_editor.font_inspector import FontInspector
from ui.text_editor.text_commands import (
    SetKeyColorCmd, ResliceFontCmd, MergeGlyphsCmd, SetCharsetCmd,
)

class TextEditorScreen(QWidget):
    """Assemble les trois colonnes et arbitre le contexte actif."""

    _CTX_TEXT = 0
    _CTX_FONT = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_DEEP};")
        self._project = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setStyleSheet(
            f"QSplitter::handle{{background:{C.BORDER};}}"
            f"QSplitter::handle:horizontal{{width:2px;}}"
            f"QSplitter::handle:hover{{background:{TEXT_COLOR};}}"
        )

        self._fonts = AssetFinder(label('txtscr.font_finder'), [FONTS],
                                  min_width=180, max_width=420)

        # Le CENTRE est contextuel lui aussi : une planche fait plusieurs
        # centaines de cases, elle n'aurait pas tenu dans l'inspecteur.
        self._center = QStackedWidget()
        self._texts = TextPanel()
        self._sheet = GlyphSheetPanel()
        self._center.addWidget(self._texts)   # _CTX_TEXT
        self._center.addWidget(self._sheet)   # _CTX_FONT

        self._inspectors = QStackedWidget()
        self._inspectors.setMinimumWidth(200)
        self._inspectors.setMaximumWidth(420)
        self._text_insp = TextInspector()
        self._font_insp = FontInspector()
        self._inspectors.addWidget(self._text_insp)   # _CTX_TEXT
        self._inspectors.addWidget(self._font_insp)   # _CTX_FONT

        split.addWidget(self._fonts)
        split.addWidget(self._center)
        split.addWidget(self._inspectors)
        split.setSizes([240, 800, 300])
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        root.addWidget(split)

        # Bascule de contexte par sélection — jamais par un onglet.
        self._fonts.selected.connect(lambda _kind, f: self._on_font_selected(f))
        self._texts.text_selected.connect(self._on_text_selected)
        self._texts.changed.connect(self._persist)
        # Clé/rangement édités au centre : l'inspecteur affiche la clé dans
        # son en-tête, il doit se relire.
        self._texts.identity_changed.connect(self._on_identity_changed)
        # Le balisage se relit à la FRAPPE, comme l'aperçu : voir ce qui cloche
        # pendant qu'on écrit, pas au build.
        self._texts.parsed.connect(self._text_insp.set_parsed)
        self._texts.preview_font_changed.connect(self._text_insp.set_font)
        self._text_insp.changed.connect(self._on_text_insp_changed)
        self._sheet.glyph_selected.connect(self._font_insp.set_glyph)
        self._sheet.glyph_edited.connect(self._on_glyph_edited)
        self._sheet.reslice_asked.connect(self._on_reslice)
        self._sheet.merge_asked.connect(self._on_merge)
        self._sheet.selection_changed.connect(self._font_insp.set_selection)
        self._sheet.background_clicked.connect(self._on_sheet_background)
        # Pipettes : l'inspecteur DEMANDE, la planche PRÉLÈVE, l'écran DÉCIDE
        # (commande + sauvegarde) — aucune vue ne connaît l'autre.
        self._font_insp.pick_asked.connect(self._sheet.begin_pick)
        self._font_insp.key_color_cleared.connect(
            lambda role: self._set_key_color(role, None))
        self._sheet.color_picked.connect(self._set_key_color)
        # Deux chemins d'édition, une seule commande : frappe sur la planche
        # et champ de l'inspecteur passent par le même _on_glyph_edited.
        self._font_insp.glyph_char_changed.connect(self._on_glyph_edited)
        # Charset réécrit d'un bloc : assignation positionnelle sur les cases.
        self._font_insp.charset_edited.connect(self._on_charset_edited)

    def load_project(self, project):
        """Ouvre un projet — l'écran repart en contexte Texte."""
        self._project = project
        self._fonts.load_project(project)
        self._texts.load_project(project)
        self._text_insp.set_font(self._texts.preview_font())
        self._text_insp.invalidate_usages()
        self._text_insp.load(None, project)
        self._inspectors.setCurrentIndex(self._CTX_TEXT)

    def invalidate_script_usages(self):
        """Branché sur « scripts_changed » ET « ui_text_links_changed » —
        recalcul paresseux, à la prochaine sélection (l'écran n'est peut-être
        même pas affiché).

        Deux vues montrent les usages : la colonne de la table et la section de
        l'inspecteur. Elles lisent le même index, elles se périment ensemble."""
        self._text_insp.invalidate_usages()
        self._texts.invalidate_usages()

    def _on_identity_changed(self, text):
        """Clé renommée : les scripts viennent d'être réécrits, l'index des
        utilisations et l'inspecteur sont périmés tous les deux."""
        self._text_insp.invalidate_usages()
        self._text_insp.load(text, self._project)

    def refresh(self):
        """Recharge depuis le projet — fichier déposé (watcher) ou undo/redo."""
        if not self._project:
            return
        self._fonts.refresh()
        self._texts.reload_fonts()            # polices apparues/disparues
        self._texts.refresh()
        # L'inspecteur affiche peut-être une entrée que l'undo a changée, ou
        # qui n'existe plus.
        cur = self._text_insp._text
        if cur is not None and cur not in self._project.texts:
            cur = None
        # Un undo de renommage repasse par rename_text_key : les scripts ont
        # rebougé.
        self._text_insp.invalidate_usages()
        self._texts.invalidate_usages()
        self._text_insp.load(cur, self._project)

        # Contexte police : un undo a pu changer un caractère, une couleur-clé
        # ou la découpe — tout ça se voit.
        font = self._font_insp._font
        if font is not None:
            if font not in self._project.fonts:
                self._font_insp.load(None, self._project)
                self._sheet.load(None, self._project)
                self._set_context(self._CTX_TEXT)
            else:
                # refresh_keying et pas update() : la planche trouée peut être
                # à reconstruire.
                self._sheet.refresh_keying()
                self._font_insp.refresh_stats()
                self._font_insp.refresh_keys()

    # ── Contexte ──────────────────────────────────────────────────

    def _set_context(self, ctx: int):
        """Bascule centre et inspecteur d'un bloc."""
        self._center.setCurrentIndex(ctx)
        self._inspectors.setCurrentIndex(ctx)

    def _on_font_selected(self, font):
        """Sélection à gauche : entre en contexte Police (None = retour)."""
        if font is None:
            # Règle générale « sélection vide → contexte par défaut », pas un
            # cas particulier de retour.
            self._set_context(self._CTX_TEXT)
            return
        self._texts.clear_selection()
        self._font_insp.load(font, self._project)
        self._sheet.load(font, self._project)
        self._set_context(self._CTX_FONT)

    def _on_text_selected(self, text):
        """Sélection dans la table : revient au contexte Texte, même si une
        police reste surlignée à gauche."""
        self._fonts.clear_selection()
        self._text_insp.load(text, self._project)
        self._set_context(self._CTX_TEXT)

    # ── Glyphes ───────────────────────────────────────────────────

    def _on_glyph_edited(self, glyph, before: str, after: str):
        """Caractère d'une case changé, quelle que soit la vue d'origine."""
        font = self._font_insp._font
        get_history().push(SetFieldCmd(
            glyph, "char", before, after,
            label=f"Glyphe « {after} »",
            persist_fn=lambda: self._after_glyph_change(font),
        ))

    def _on_charset_edited(self, charset: str):
        """Charset réécrit d'un bloc : une seule commande réassigne les cases
        dans l'ordre de la planche (cf. SetCharsetCmd)."""
        font = self._font_insp._font
        if not font:
            return
        get_history().push(SetCharsetCmd(
            font, charset,
            persist_fn=lambda: self._after_glyph_change(font),
        ))

    def _after_glyph_change(self, font):
        """Relit tout ce qui DÉRIVE des glyphes (charset, coût en tuiles, case
        courante) et sauvegarde — sinon l'inspecteur ment après un undo."""
        self._sheet.refresh()
        self._font_insp.refresh_stats()
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        if self._project and font:
            self._project.fonts.save(font)

    # ── Couleurs-clés de la planche ───────────────────────────────

    _KEY_FIELD = {"bg": ("bg_color", "fond"), "space": ("space_color", "espacement")}

    def _set_key_color(self, role: str, rgb):
        """Pose (ou retire, si `rgb` est None) une couleur transparente.

        Passe par l'historique : se tromper de pixel arrive, et sans undo il
        faudrait retrouver la bonne couleur à l'œil."""
        font = self._font_insp._font
        entry = self._KEY_FIELD.get(role)
        if not font or entry is None:
            return
        field_name, label = entry
        old = getattr(font, field_name)
        new = tuple(rgb) if rgb is not None else None
        if old == new:
            return
        get_history().push(SetKeyColorCmd(
            self._project, font, field_name, old, new,
            label=(f"{label} color of {font.name}" if new
                   else f"Remove {label} color of {font.name}"),
            persist_fn=lambda: self._after_key_color(font),
        ))

    def _after_key_color(self, font):
        """La transparence change ce qu'on VOIT (planche, aperçu) et ce que
        MESURE le modèle (chasse) — relire les deux, sinon l'aperçu et la ROM
        divergent."""
        self._sheet.refresh_keying()
        self._font_insp.refresh_keys()
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        # L'aperçu écran vit dans l'autre contexte mais rend avec cette
        # police : sa planche est à retrouer même si on ne le regarde pas.
        self._texts.refresh_preview_font()
        if self._project and font:
            self._project.fonts.save(font)

    def _on_sheet_background(self):
        """Clic hors planche : sélection à zéro, retour au contexte Texte.
        Pas de bouton de retour dédié, la règle suffit."""
        self._fonts.clear_selection()
        self._font_insp.set_glyph(None)
        self._set_context(self._CTX_TEXT)

    def _on_merge(self, indices: list):
        """Fusionne les cases sélectionnées en un glyphe."""
        font = self._font_insp._font
        if not font or len(indices) < 2:
            return
        # Caractère du glyphe fusionné : celui de la 1ère case, que
        # l'utilisateur remplace ensuite (souvent par un mot).
        first = font.glyphs[min(indices)].char
        get_history().push(MergeGlyphsCmd(
            font, indices, first,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _on_reslice(self, cw: int, ch: int):
        """Re-découpe la planche après confirmation (geste destructif)."""
        font = self._font_insp._font
        if not font or not self._project or not font.asset:
            return
        png = self._project.asset_abs(font.asset)
        if not png or not png.exists():
            QMessageBox.warning(self, label("txtscr.reslice_title"),
                                label("txtscr.sheet_not_found", asset=font.asset))
            return
        if QMessageBox.question(
            self, label("txtscr.reslice_confirm_title"),
            label("txtscr.reslice_confirm_msg", name=font.name, cw=cw, ch=ch),
        ) != QMessageBox.StandardButton.Yes:
            return
        from core import font_import
        try:
            # Les couleurs repiquées restent : la re-découpe change le
            # DÉCOUPAGE, pas la lecture des couleurs.
            fields = font_import.import_font_png(png, cell=(cw, ch),
                                                 keys=font.key_colors(),
                                                 space_color=font.space_color)
        except Exception as exc:
            QMessageBox.warning(self, label("txtscr.reslice_title"),
                                label("txtscr.import_failed", error=exc))
            return
        get_history().push(ResliceFontCmd(
            self._project, font, fields,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _reload_font(self, font):
        """Recharge la planche et l'inspecteur après une édition lourde."""
        self._sheet.load(font, self._project)   # load reconstruit déjà le trouage
        self._font_insp.load(font, self._project)
        if self._project:
            self._project.fonts.save(font)

    # ── Persistance ───────────────────────────────────────────────

    def _persist(self):
        """Écrit texts.json."""
        if self._project:
            self._project.save_texts()

    def _on_text_insp_changed(self):
        self._persist()
        # Seule la note s'édite ici, et la table ne l'affiche pas : inutile de
        # la reconstruire.
