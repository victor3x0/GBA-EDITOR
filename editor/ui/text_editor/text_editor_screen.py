"""
ui/text_editor/text_editor_screen.py — écran Text Editor.

Un seul écran pour DEUX concepts structurellement distincts mais qui se
croisent en permanence (cf. mémoire project_text_font_screen_design) :

  • Police (`Font`)  — un asset réutilisable, importé (PNG / BMFont `.fnt`).
  • Texte (`Text`)   — une entrée référencée par clé, rangée dans un arbre.

Ils vivent ensemble parce que deux features ne prennent leur sens que si les
deux sont sous les yeux : `Font.missing_chars()` (quels glyphes manquent pour
écrire ce texte ?) et l'aperçu d'un texte, qui a besoin d'une police pour se
rendre. Les modèles, eux, restent séparés.

Layout — trois colonnes :
  gauche  : liste des polices
  centre  : arbre des textes (haut) + atelier d'écriture (bas)
  droite  : inspecteur CONTEXTUEL

L'atelier met l'éditeur de contenu et l'aperçu écran CÔTE À CÔTE, et non l'un
sous l'autre : on écrit en regardant où le texte coupe. Empilés, l'aperçu
repoussait l'éditeur hors de vue dès que la fenêtre rétrécissait — or c'est
précisément pendant la frappe que le rendu compte (l'aperçu suit la frappe, pas
le commit). Les deux découpes sont des splitters : la place que mérite la liste
dépend du projet, pas de nous.

La bascule de contexte se fait par la SÉLECTION, pas par un onglet : choisir
une police entre en édition de police ; choisir un texte, ou cliquer dans le
vide, revient au contexte Texte (le défaut). C'est le pattern du Scene Manager
(sélection → inspecteur), mais câblé en signaux Qt LOCAUX : le bus global est
partagé avec le Scene Manager, dont l'inspecteur ne connaît pas `Font`/`Text`.
Les autres écrans autonomes (Background, Palette, Sprite) font déjà ainsi.

« Textes », jamais « Dialogue ». L'arbre range, il n'enchaîne pas : ses nœuds
sont des CLASSEURS libres, pas des étapes de conversation — pas de portraits,
pas de choix branchés, aucun ordre de lecture. Un éditeur de dialogue est une
décision de genre, que l'outil refuse de prendre à la place de l'utilisateur
(cf. ROADMAP v0.3.2, neutralité de style) ; le séquencement reste du script.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QTextEdit,
    QLineEdit, QAbstractItemView, QHeaderView, QMessageBox, QStackedWidget,
    QScrollArea, QPushButton, QSpinBox, QSizePolicy, QComboBox,
    QTreeWidget, QTreeWidgetItem, QToolButton, QApplication,
)
from PyQt6.QtGui import QFont, QPixmap, QPainter, QPen, QColor, QImage, QBrush
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QPoint, QTimer

from core.models.font import Glyph
from core.models.text import MAX_DEPTH, SEP, norm_path
from core.history import (
    get_history, Command, SetFieldCmd, AddListItemCmd, RemoveListItemCmd,
)
from ui.common.theme import C, T, QSS
from ui.common.widgets import W, FinderSection, BTN_ICON
from ui.common import icons

_FONT_COLOR = C.ACCENT_ORG    # famille « police » (asset)
_TEXT_COLOR = C.ACCENT        # famille « texte » (contenu) — accent primaire


# ── Trouage des couleurs-clés ─────────────────────────────────────
# Point unique côté AFFICHAGE, pendant de `Font.key_colors()` côté modèle. Les
# trois vues qui montrent des glyphes (planche, case isolée, aperçu écran)
# doivent trouer exactement pareil : dès qu'une seule oublie, elle promet un
# rendu que la ROM ne tiendra pas.

def key_out(px: Optional[QPixmap], keys) -> Optional[QPixmap]:
    """Copie de `px` où les couleurs de `keys` deviennent transparentes.
    Retourne l'original tel quel si rien n'est à trouer."""
    if px is None or px.isNull() or not keys:
        return px
    import numpy as np
    # RGBA8888 : ordre des octets garanti R,G,B,A quelle que soit
    # l'endianness, contrairement à ARGB32 qui sort en BGRA sur x86.
    img = px.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    arr = (np.frombuffer(ptr, dtype=np.uint8)
             .reshape(h, img.bytesPerLine())[:, :w * 4]
             .reshape(h, w, 4).copy())
    mask = np.zeros((h, w), dtype=bool)
    for k in keys:
        mask |= np.all(arr[:, :, :3] == np.array(tuple(k), dtype=np.uint8), axis=2)
    arr[mask] = 0
    # .copy() du QImage : `arr` est un tampon Python, l'image ne doit pas
    # rester à pointer dessus une fois la fonction sortie.
    return QPixmap.fromImage(
        QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy())


def checker_brush() -> QBrush:
    """Damier de transparence — même convention que l'écran Palette."""
    px = QPixmap(16, 16)
    px.fill(QColor(C.BG_DEEP))
    q = QPainter(px)
    q.fillRect(0, 0, 8, 8, QColor(C.BG_RAISED))
    q.fillRect(8, 8, 8, 8, QColor(C.BG_RAISED))
    q.end()
    return QBrush(px)


class RenameTextKeyCmd(Command):
    """Renommage de clé, annulable.

    `Project.rename_text_key` ne change pas qu'un champ : il réécrit aussi les
    `text.draw("clé")` des scripts Lua. L'annulation ne peut donc pas se
    contenter de remettre l'ancienne valeur — elle repasse par la même fonction
    en sens inverse, qui réécrit les scripts à l'identique."""

    def __init__(self, project, text, old_key: str, new_key: str,
                 old_auto: bool, persist_fn=None):
        self._project = project
        self._text = text
        self._old = old_key
        self._new = new_key
        # `old_auto` est passé par l'appelant, PAS lu sur `text` ici : le
        # renommage a déjà eu lieu quand la commande est construite, et il a
        # mis auto_key à False — le lire maintenant restaurerait cette
        # nouvelle valeur au lieu de l'ancienne.
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
        # `auto_key` passe à False dès le premier renommage manuel ; le
        # restaurer garde le badge « clé automatique » cohérent après annulation.
        self._text.auto_key = self._old_auto
        if self._persist:
            self._persist()


class SetTextPathCmd(Command):
    """Rangement d'un ou plusieurs textes, annulable.

    Un seul type de commande pour deux gestes qui sont la même opération à
    l'échelle près : déplacer une entrée, et renommer un nœud de l'arbre — qui
    déplace d'un coup tout ce qu'il contient.

    Ranger ne pose pas qu'un champ : les clés AUTOMATIQUES se recalent
    derrière, ce qui réécrit les `text.draw("clé")` des scripts. Les clés
    nommées à la main, elles, ne bougent pas — c'est le contrat de `auto_key`
    (cf. models/text.py) : le rangement reste un geste cosmétique tant qu'on
    n'a pas pris la main sur la clé."""

    def __init__(self, project, entries, label: str, persist_fn=None):
        self._project = project
        # (texte, ancien chemin, nouveau chemin, ancienne clé). L'ancienne clé
        # est capturée MAINTENANT, avant le premier execute().
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
            # `restore_text_key` et non `resync` : le rang `_NN` d'une clé
            # dérivée dépend des clés prises à l'instant du calcul, rejouer la
            # dérivation en sens inverse ne rendrait pas forcément la même.
            if t.auto_key:
                self._project.restore_text_key(t, key)
        if self._persist:
            self._persist()


class RelinkTextKeyCmd(Command):
    """Ré-accroche une clé nommée à la main à son chemin de rangement.

    Exact inverse du renommage manuel : la clé redevient dérivée et suivra les
    déplacements. Sert à revenir d'un nommage qu'on regrette sans avoir à
    retaper à la main ce que le chemin sait déjà produire."""

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


class _SetKeyColorCmd(Command):
    """Désignation d'une couleur-clé, annulable.

    Ne pose pas qu'un champ : la couleur d'espacement GOUVERNE LA CHASSE, donc
    les `Glyph.advance` de toute la planche sont relus derrière. L'annulation
    doit rendre les deux — un `SetFieldCmd` sur la seule couleur laisserait des
    chasses calculées pour une couleur qui n'est plus désignée."""

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
        """Un `.fnt` porte les `xadvance` voulus par son auteur : ils priment
        sur toute lecture de la planche (cf. models/font.py). Seule une police
        venue d'un PNG nu se laisse remesurer."""
        f = self._font
        if f.source_format != "png" or not f.asset or not self._project:
            return
        png = self._project.asset_abs(f.asset)
        if not png or not png.exists():
            return
        from core import font_import
        for g, a in zip(f.glyphs, font_import.measure_advances(
                png, f.glyphs, f.space_color)):
            g.advance = a

    def execute(self):
        self._apply(self._new)

    def undo(self):
        self._apply(self._old, self._advances_before)


class _ResliceFontCmd(Command):
    """Re-découpe d'une planche à une autre taille de cellule.

    Destructive par nature : la liste de glyphes entière est remplacée, donc
    toutes les corrections de caractères sont perdues. D'où l'instantané
    complet — c'est exactement le genre d'action qu'on veut pouvoir annuler."""

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


class _MergeGlyphsCmd(Command):
    """Fusionne plusieurs cases en un seul glyphe couvrant leur rectangle.

    Sert à deux besoins : une police plus grande (quatre cases 8×8 → un glyphe
    16×16) et un pictogramme large assigné à un mot (« (shift) »). Le modèle
    porte déjà un rect libre par glyphe — la fusion ne fait que le poser."""

    def __init__(self, font, indices: list, char: str, persist_fn=None):
        self._font = font
        self._before = list(font.glyphs)
        gs = [font.glyphs[i] for i in indices]
        x0 = min(g.x for g in gs); y0 = min(g.y for g in gs)
        x1 = max(g.x + g.w for g in gs); y1 = max(g.y + g.h for g in gs)
        merged = Glyph(char=char, x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                       advance=x1 - x0)
        keep = [g for i, g in enumerate(font.glyphs) if i not in set(indices)]
        # Réinsérer à la position de la 1ère case fusionnée : l'ordre de la
        # liste est celui de la planche, le perdre désordonnerait l'affichage.
        pos = min(indices)
        self._after = keep[:pos] + [merged] + keep[pos:]
        self.merged = merged
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


class _ContentEdit(QTextEdit):
    """Éditeur de contenu qui ne commite qu'à la perte du focus.

    Une commande par frappe rendrait l'historique inutilisable ; on suit le
    modèle de `NotesEdit`, avec une ligne de base comparée au moment du
    commit. `edited` reste émis à chaque frappe pour l'aperçu en table."""

    committed = pyqtSignal(str, str)   # (avant, après)
    edited    = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._baseline = ""
        self.textChanged.connect(lambda: self.edited.emit(self.toPlainText()))

    def set_text_silent(self, text: str):
        self._baseline = text or ""
        self.blockSignals(True)
        self.setPlainText(self._baseline)
        self.blockSignals(False)

    def commit(self):
        """Force le commit — appelé aussi avant un changement de sélection,
        car passer d'une ligne à l'autre ne provoque pas toujours un focus-out."""
        text = self.toPlainText()
        if text != self._baseline:
            before, self._baseline = self._baseline, text
            self.committed.emit(before, text)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.commit()


# ──────────────────────────────────────────────────────────────────
#  Aperçu écran — rendu fidèle avec la police réelle
# ──────────────────────────────────────────────────────────────────
class FontScreenPreview(QWidget):
    """Écran GBA simulé, dessiné avec les VRAIS glyphes de la police.

    Rejoue l'algorithme de `text_layout` (runtime/gba_engine.h) : correspondance
    au plus long — donc les ligatures —, avance par la CHASSE de chaque glyphe,
    coupe au mot, repli au glyphe pour un mot trop long. Ce qui s'affiche ici est
    ce que la console affichera.

    Tout se calcule en PIXELS, comme au runtime : une police proportionnelle pose
    ses glyphes à x=13 ou x=21, ce qu'une grille de tuiles ne saurait montrer.
    En mono, les chasses valant gw*8, les positions retombent d'elles-mêmes sur
    des multiples de 8 — aucun cas particulier.

    À ne pas confondre avec `ScreenTextPreview` (ui/common), qui n'est pas un
    rendu mais une jauge de longueur à chasse fixe de 8 px : elle sert là où
    aucune police n'est liée au texte, et se trompe dès qu'une police 16×16 ou
    une ligature entre en jeu."""

    GBA_W, GBA_H = 240, 160
    TILE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._sheet: Optional[QPixmap] = None
        self._text = ""
        self._overflow = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(80)

    def set_font_asset(self, font, project):
        self._font, self._project = font, project
        self._sheet = None
        if font and project and font.asset:
            path = project.asset_abs(font.asset)
            if path and path.exists():
                px = QPixmap(str(path))
                # Troué comme partout ailleurs : sans ça une planche opaque
                # rendrait chaque glyphe en pavé de couleur de fond, et
                # l'« aperçu réel » montrerait l'inverse de la ROM.
                self._sheet = None if px.isNull() else key_out(px, font.key_colors())
        self.update()

    def set_text(self, text: str):
        self._text = text or ""
        self.update()

    # ── Géométrie ─────────────────────────────────────────────────

    def _scale(self) -> int:
        """Échelle ENTIÈRE : le pixel art ne supporte pas l'interpolation."""
        return max(1, min(self.width() // self.GBA_W, 3)) if self.width() else 1

    def resizeEvent(self, e):
        self.setFixedHeight(self.GBA_H * self._scale() + 2)
        super().resizeEvent(e)

    # ── Disposition (miroir de text_render) ───────────────────────

    def _layout(self) -> tuple[list, bool]:
        """[(glyphe, px, py)] en PIXELS + débordement vertical.

        Miroir de `text_layout` (runtime/gba_engine.h) : mêmes chasses, même
        coupe au mot, même filet. Le mode vient de `font_emit.is_proportional`,
        la règle que suit l'émetteur — pas d'un second critère qui pourrait en
        diverger. En mono les chasses valent gw*8, donc tout retombe sur des
        multiples de 8 : un seul code pour les deux rendus, comme au runtime."""
        f = self._font
        if not f or not f.glyphs:
            return [], False
        from codegen.font_emit import (glyph_advance_px, font_line_px,
                                       font_fallback_adv_px)
        # Exactement ce que lit le runtime : chasses, interligne et avance de
        # secours sont émis DÉJÀ RÉSOLUS, donc aucun branchement sur le chemin
        # de rendu ici non plus. Le mode (tilemap ou composition) ne change que
        # la façon dont les pixels arrivent en VRAM, jamais où ils atterrissent.
        line = font_line_px(f)
        fallback = font_fallback_adv_px(f)

        def adv(g):
            return fallback if g is None else glyph_advance_px(g, f)

        def word_width(i):
            w, n = 0, len(self._text)
            while i < n and self._text[i] not in " \n":
                g = f.match_at(self._text, i)
                w += adv(g)
                i += len(g.char) if g else 1
            return w

        out, over = [], False
        x = y = 0
        i, n = 0, len(self._text)
        while i < n:
            ch = self._text[i]
            if ch == "\n":
                x, y, i = 0, y + line, i + 1
                continue
            if ch == " ":
                gsp = f.match_at(self._text, i)
                used_sp = len(gsp.char) if gsp else 1
                if x + adv(gsp) + word_width(i + used_sp) > self.GBA_W:
                    x, y, i = 0, y + line, i + used_sp
                    continue
            g = f.match_at(self._text, i)
            a = adv(g)
            if x + a > self.GBA_W:
                x, y = 0, y + line
            if y + line > self.GBA_H:
                over = True
                break
            if g:
                out.append((g, x, y))
            x += a
            i += len(g.char) if g else 1
        return out, over

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        s = self._scale()
        w, h = self.GBA_W * s, self.GBA_H * s
        # L'écran simulé est CENTRÉ dans le volet : à droite d'un splitter, sa
        # largeur ne tombe jamais juste sur un multiple de 240, et un écran collé
        # au bord gauche se lirait comme un défaut d'alignement.
        p.translate(max(0, (self.width() - w) // 2), 0)
        p.fillRect(QRect(0, 0, w, h), QColor(C.BG_DEEP))
        p.setPen(QPen(QColor(C.BORDER_MID)))
        p.drawRect(QRect(0, 0, w - 1, h - 1))

        if not self._sheet or not self._font:
            p.setPen(QColor(C.TEXT_MUTED))
            p.setFont(QFont(T.MONO, T.XS))
            p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "Choisir une police d'aperçu")
            return

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        placed, over = self._layout()
        for g, px, py in placed:
            src = QRect(g.x, g.y, g.w, g.h)
            dst = QRect(px * s, py * s, g.w * s, g.h * s)
            p.drawPixmap(dst, self._sheet, src)

        if over:
            p.setPen(QColor(C.ACCENT_YLW))
            p.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
            p.drawText(QRect(0, h - 16, w - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "déborde de l'écran")


# ──────────────────────────────────────────────────────────────────
#  Colonne gauche — liste des polices
# ──────────────────────────────────────────────────────────────────
class FontFinderPanel(QWidget):
    """Liste des `Font` du projet. La sélection pilote le contexte de l'écran."""

    font_selected = pyqtSignal(object)   # Font | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(420)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(20)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 0, 0)
        lbl = QLabel("FONT FINDER")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        hl.addWidget(lbl)
        root.addWidget(hdr)

        sec = FinderSection("POLICES", _FONT_COLOR)
        # Pas de bouton « + » : une police s'obtient en déposant un PNG ou un
        # .fnt dans assets/fonts/ (asset_sync.sync_font_file les détecte), comme
        # les sprites et les fonds. Pas d'assistant d'import — décision v0.3.2.
        sec.set_add_visible(False)
        root.addWidget(sec, 1)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
            f"QListWidget::item{{padding:4px 6px;}}"
            f"QListWidget::item:selected{{background:{C.BG_SEL}; color:{_FONT_COLOR};"
            f"border-left:2px solid {_FONT_COLOR};}}"
        )
        self._list.currentItemChanged.connect(self._on_sel)
        sec.set_widget(self._list)

        self._empty = QLabel(
            "Aucune police.\n\nDéposer un PNG ou un .fnt\ndans assets/fonts/"
        )
        self._empty.setFont(QFont(T.MONO, T.XS))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:12px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        root.addWidget(self._empty)

    def load_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        self._blocking = True
        self._list.blockSignals(True)
        self._list.clear()
        fonts = list(self._project.fonts) if self._project else []
        for f in fonts:
            it = QListWidgetItem(f.name)
            it.setFont(QFont(T.MONO, T.SM))
            it.setData(Qt.ItemDataRole.UserRole, f)
            it.setToolTip(
                f"{f.name}\n"
                f"{len(f.glyphs)} glyphes · {f.cell_w}×{f.cell_h} px\n"
                f"{f.tile_count()} tuiles dans le charblock du layer d'UI\n"
                f"source : {f.source_format}"
            )
            self._list.addItem(it)
        self._list.blockSignals(False)
        self._blocking = False
        self._empty.setVisible(not fonts)
        self._list.setVisible(bool(fonts))

    def clear_selection(self):
        """Désélectionne sans réémettre — utilisé quand l'écran repasse au
        contexte Texte suite à une sélection dans la table."""
        self._blocking = True
        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.setCurrentItem(None)
        self._list.blockSignals(False)
        self._blocking = False

    def _on_sel(self, cur, _prev):
        if self._blocking:
            return
        self.font_selected.emit(cur.data(Qt.ItemDataRole.UserRole) if cur else None)


# ──────────────────────────────────────────────────────────────────
#  Colonne centre — table des textes + éditeur de contenu
# ──────────────────────────────────────────────────────────────────
class TextTreePanel(QWidget):
    """Arbre des `Text` rangés par chemin + éditeur du contenu sélectionné.

    L'arbre est une VUE, pas un stockage : `texts.json` reste une liste plate
    dont chaque entrée porte son chemin. Les nœuds sont donc dérivés à chaque
    reconstruction — rien à garbage-collecter, diffs git lisibles, dep-graph
    inchangé. Contrepartie assumée : pas de groupe vide, créer un groupe veut
    dire créer un texte dedans (le « + » range la nouvelle entrée là où on
    regarde, sans passer par une boîte de dialogue)."""

    text_selected    = pyqtSignal(object)   # Text | None
    changed          = pyqtSignal()         # contenu modifié → persistance
    identity_changed = pyqtSignal(object)   # clé/chemin modifiés

    _COLS = ("Rangement / Contenu", "Clé")
    _ROLE_TEXT = Qt.ItemDataRole.UserRole        # Text, sur une feuille
    _ROLE_PATH = Qt.ItemDataRole.UserRole + 1    # tuple(str), sur un nœud

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._project = None
        self._blocking = False
        self._current: Optional[object] = None
        # Nœuds explicitement REPLIÉS, et non l'inverse : un chemin qui vient
        # d'apparaître doit s'ouvrir tout seul, sinon un texte rangé ailleurs
        # semblerait avoir disparu.
        self._collapsed: set[tuple] = set()
        # La clé est en lecture seule par défaut ; ce drapeau retient qu'on a
        # cliqué le cadenas, avant même d'avoir tapé quoi que ce soit (ce n'est
        # qu'au commit que `auto_key` tombe pour de bon).
        self._key_unlocked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QFrame()
        hdr.setFixedHeight(26)
        hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(6)
        lbl = QLabel("TEXTES")
        lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        hl.addWidget(lbl)
        self._count = QLabel("")
        self._count.setFont(QFont(T.MONO, T.XS))
        self._count.setStyleSheet(f"color:{C.TEXT_MUTED};")
        hl.addWidget(self._count)
        hl.addStretch()
        # Le filtre est TOUJOURS visible, pas caché derrière un bouton loupe :
        # dès qu'on peut replier des nœuds, on peut se cacher son propre
        # contenu — la recherche est la contrepartie obligatoire du pliage.
        self._search = W.search_box("Filtrer : clé, rangement ou contenu…")
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(lambda _q: self._apply_filter())
        hl.addWidget(self._search)
        self._btn_add = W.btn_add("Nouveau texte (rangé là où est la sélection)")
        self._btn_add.clicked.connect(self._add_text)
        hl.addWidget(self._btn_add)
        self._btn_del = W.btn_danger("Supprimer le texte sélectionné")
        self._btn_del.clicked.connect(self._delete_text)
        hl.addWidget(self._btn_del)
        root.addWidget(hdr)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(self._COLS))
        self._tree.setHeaderLabels(self._COLS)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Aucun déclencheur automatique : le double-clic est routé à la main
        # vers la COLONNE 0 d'un nœud (renommer un rangement), pour qu'un
        # double-clic sur une feuille ou sur la clé n'ouvre jamais d'éditeur.
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setUniformRowHeights(True)
        self._tree.setStyleSheet(
            f"QTreeWidget{{background:{C.BG_BASE}; color:{C.TEXT_NORM}; border:none;"
            f"font-family:{T.MONO}; font-size:{T.SM}px;}}"
            f"QTreeWidget::item{{padding:2px 4px;}}"
            f"QTreeWidget::item:selected{{background:{C.BG_SEL}; color:{_TEXT_COLOR};}}"
            f"QTreeWidget::item:hover{{background:{C.BG_HOVER};}}"
            f"QHeaderView::section{{background:{C.BG_PANEL}; color:{C.TEXT_DIM};"
            f"border:none; border-bottom:1px solid {C.BORDER}; padding:4px 6px;"
            f"font-family:{T.MONO}; font-size:{T.XS}px;}}"
        )
        th = self._tree.header()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.itemSelectionChanged.connect(self._on_sel)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.itemExpanded.connect(self._on_expanded)
        self._tree.itemCollapsed.connect(self._on_collapsed)

        # ── Découpage : la liste en haut, l'atelier en bas ─────────
        # L'atelier met l'écriture et son rendu CÔTE À CÔTE : on écrit en
        # regardant où le texte coupe, sans que l'aperçu repousse l'éditeur
        # hors de vue comme le faisait l'empilement vertical. Deux splitters
        # plutôt que des tailles figées — la place à donner à la liste dépend
        # du projet, pas de nous.
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setStyleSheet(QSS.splitter)
        vsplit.setChildrenCollapsible(False)
        vsplit.addWidget(self._tree)

        workbench = QSplitter(Qt.Orientation.Horizontal)
        workbench.setStyleSheet(QSS.splitter)
        workbench.setChildrenCollapsible(False)

        edit_pane = QWidget()
        edit_pane.setStyleSheet(f"background:{C.BG_BASE};")
        root_edit = QVBoxLayout(edit_pane)
        root_edit.setContentsMargins(0, 0, 0, 0)
        root_edit.setSpacing(0)

        # ── Widget d'édition : identité sur une ligne, contenu dessous ──
        # Éditer là où on lit. La clé est en mono (c'est du code : elle part
        # telle quelle dans les scripts Lua), le rangement en texte courant.
        ed_hdr = QFrame()
        ed_hdr.setFixedHeight(30)
        ed_hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        el = QHBoxLayout(ed_hdr)
        el.setContentsMargins(8, 2, 8, 2)
        el.setSpacing(4)

        self._key_edit = QLineEdit()
        self._key_edit.setFont(QFont(T.CODE, T.SM))
        self._key_edit.setFixedWidth(180)
        self._key_edit.setPlaceholderText("clé")
        self._key_edit.editingFinished.connect(self._commit_key)
        el.addWidget(self._key_edit)

        # Cadenas : la clé est en lecture seule tant qu'elle DÉRIVE du
        # rangement. Le geste de la nommer à la main est ainsi délibéré — c'est
        # lui qui la détache définitivement du chemin.
        self._btn_lock = QToolButton()
        self._btn_lock.setFixedSize(22, 22)
        self._btn_lock.setStyleSheet(BTN_ICON)
        self._btn_lock.clicked.connect(self._toggle_key_lock)
        el.addWidget(self._btn_lock)

        self._btn_copy = QToolButton()
        self._btn_copy.setFixedSize(22, 22)
        self._btn_copy.setStyleSheet(BTN_ICON)
        self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM))
        self._btn_copy.setToolTip("Copier la clé — à coller dans un script Lua")
        self._btn_copy.clicked.connect(self._copy_key)
        el.addWidget(self._btn_copy)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{C.BORDER};")
        el.addSpacing(4)
        el.addWidget(sep)
        el.addSpacing(4)

        # Rangement : un champ par niveau plutôt qu'une chaîne à séparateur.
        # Le stockage est une liste — un libellé a le droit de contenir « / »
        # sans qu'on ait à inventer une règle d'échappement — et le fil
        # d'Ariane rend la profondeur maximale visible sans avoir à l'expliquer.
        self._path_edits: list[QLineEdit] = []
        for lvl in range(MAX_DEPTH):
            if lvl:
                arrow = QLabel(SEP.strip())
                arrow.setFont(QFont(T.MONO, T.SM))
                arrow.setStyleSheet(f"color:{C.TEXT_MUTED};")
                el.addWidget(arrow)
            e = QLineEdit()
            e.setFont(QFont(T.MONO, T.SM))
            e.setStyleSheet(QSS.lineedit)
            e.setPlaceholderText(f"niveau {lvl + 1}")
            e.setToolTip(
                "<b>Rangement</b> — accents, espaces et doublons autorisés.<br>"
                "Jamais résolu, jamais référencé : il organise l'arbre et<br>"
                "propose la clé, sans jamais la posséder."
            )
            e.editingFinished.connect(self._commit_path)
            el.addWidget(e, 1)
            self._path_edits.append(e)
        root_edit.addWidget(ed_hdr)

        self._editor = _ContentEdit()
        self._editor.setFont(QFont(T.CODE, T.MD))
        self._editor.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI}; border:none;"
            f"padding:6px;}}"
        )
        self._editor.setPlaceholderText("Sélectionner un texte pour éditer son contenu…")
        self._editor.edited.connect(self._on_content_edited)
        self._editor.committed.connect(self._on_content_committed)
        root_edit.addWidget(self._editor, 1)
        workbench.addWidget(edit_pane)

        prev_pane = QWidget()
        prev_pane.setStyleSheet(f"background:{C.BG_DEEP};")
        root_prev = QVBoxLayout(prev_pane)
        root_prev.setContentsMargins(0, 0, 0, 0)
        root_prev.setSpacing(0)

        # Aperçu écran — mis à jour à la FRAPPE, pas au commit : c'est
        # justement pendant qu'on écrit qu'on veut voir où le texte coupe.
        prev_hdr = QFrame()
        prev_hdr.setFixedHeight(20)
        prev_hdr.setStyleSheet(f"background:{C.BG_PANEL}; border-top:1px solid {C.BORDER_DARK};")
        pl = QHBoxLayout(prev_hdr)
        pl.setContentsMargins(8, 0, 8, 0)
        pv = QLabel("APERÇU ÉCRAN")
        pv.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        pv.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        pl.addWidget(pv)
        pl.addStretch()
        self._preview_font = QComboBox()
        self._preview_font.setFont(QFont(T.MONO, T.XS))
        self._preview_font.setStyleSheet(QSS.combobox)
        self._preview_font.setToolTip("Police utilisée pour l'aperçu (n'affecte pas le texte)")
        self._preview_font.currentIndexChanged.connect(self._on_preview_font)
        pl.addWidget(self._preview_font)
        root_prev.addWidget(prev_hdr)

        # Zone scrollable : l'écran simulé garde une hauteur ENTIÈRE (240×160 ×1,
        # ×2 ou ×3 — jamais d'interpolation sur du pixel art), qui ne suit donc
        # pas continûment celle du volet. Sans scroll, un volet plus court que
        # l'échelle retenue rognerait le bas de l'écran en silence.
        prev_scroll = QScrollArea()
        prev_scroll.setWidgetResizable(True)
        prev_scroll.setStyleSheet(f"background:{C.BG_DEEP}; border:none;")
        wrap = QWidget()
        wrap.setStyleSheet(f"background:{C.BG_DEEP};")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 6, 6)
        self._preview = FontScreenPreview()
        wl.addWidget(self._preview)
        wl.addStretch()
        prev_scroll.setWidget(wrap)
        root_prev.addWidget(prev_scroll, 1)
        workbench.addWidget(prev_pane)

        # L'écriture prime sur le rendu : au premier affichage l'éditeur est
        # plus large que l'aperçu, qui n'a besoin que de ses 240 px logiques.
        workbench.setSizes([520, 360])
        workbench.setStretchFactor(0, 1)
        workbench.setStretchFactor(1, 0)
        vsplit.addWidget(workbench)
        vsplit.setSizes([260, 340])
        vsplit.setStretchFactor(0, 0)
        vsplit.setStretchFactor(1, 1)
        root.addWidget(vsplit, 1)

        self._set_enabled(False)

    # ── Chargement ────────────────────────────────────────────────

    def load_project(self, project):
        self._project = project
        self._reload_preview_fonts()
        self.refresh()

    def _reload_preview_fonts(self):
        """Peuple le sélecteur de police d'aperçu. Ce choix est un confort
        d'édition : il ne touche pas au texte, qui reste indépendant de toute
        police (c'est ce qui permettra les traductions en v0.8)."""
        self._blocking = True
        cur = self._preview_font.currentText()
        self._preview_font.clear()
        fonts = list(self._project.fonts) if self._project else []
        for f in fonts:
            self._preview_font.addItem(f.name, f)
        idx = self._preview_font.findText(cur)
        self._preview_font.setCurrentIndex(idx if idx >= 0 else 0)
        self._blocking = False
        self._apply_preview_font()

    def _apply_preview_font(self):
        f = self._preview_font.currentData()
        self._preview.set_font_asset(f, self._project)

    def _on_preview_font(self, _i):
        if not self._blocking:
            self._apply_preview_font()

    def refresh_preview_font(self):
        """Les couleurs-clés de la police ont bougé : la planche d'aperçu est
        à retrouer (elle est mise en cache au chargement, pas à chaque frame)."""
        self._apply_preview_font()

    def refresh(self, select_id: Optional[int] = None):
        # Un rafraîchissement peut venir du watcher (fichier déposé, texts.json
        # rechargé) alors que l'utilisateur travaille : on garde son entrée
        # sélectionnée plutôt que de le renvoyer en haut de l'arbre.
        if select_id is None and self._current is not None:
            select_id = self._current.id
        self._blocking = True
        self._tree.clear()
        texts = list(self._project.texts) if self._project else []

        # Deux passes, et pas une descente naïve : tous les nœuds d'abord, dans
        # l'ordre lexicographique des chemins (qui place un parent avant ses
        # enfants), puis les feuilles dans l'ordre du projet. Les rangements
        # apparaissent donc triés et AVANT les textes d'un même niveau —
        # disposition d'explorateur de fichiers, stable d'un refresh à l'autre.
        prefixes = {tuple(t.path[:n + 1]) for t in texts for n in range(len(t.path))}
        nodes: dict[tuple, QTreeWidgetItem] = {}
        for path in sorted(prefixes, key=lambda p: tuple(s.casefold() for s in p)):
            parent = nodes.get(path[:-1]) if len(path) > 1 else None
            it = QTreeWidgetItem(parent) if parent is not None else QTreeWidgetItem(self._tree)
            it.setText(0, path[-1])
            it.setData(0, self._ROLE_PATH, path)
            it.setForeground(0, QColor(C.TEXT_DIM))
            it.setIcon(0, icons.get("folder", icons.COLOR_FOLDER))
            it.setToolTip(0, "Double-clic pour renommer ce rangement "
                             "(et tout ce qu'il contient)")
            it.setExpanded(path not in self._collapsed)
            nodes[path] = it

        for t in texts:
            parent = nodes.get(tuple(t.path))
            leaf = QTreeWidgetItem(parent) if parent is not None else QTreeWidgetItem(self._tree)
            self._fill_leaf(leaf, t)

        for path, it in nodes.items():
            n = self._leaf_count(it)
            it.setText(1, str(n))
            it.setForeground(1, QColor(C.TEXT_MUTED))

        self._count.setText(f"  {len(texts)}")
        self._apply_filter()
        self._blocking = False

        if select_id is not None:
            self.select_by_id(select_id)
        # L'entrée visée a pu disparaître (supprimée hors éditeur) : la
        # sélection n'a alors pas été rétablie, il faut vider l'éditeur.
        if self._selected_text() is None:
            self._current = None
            self._sync_editor()

    def _fill_leaf(self, item: QTreeWidgetItem, t):
        """Une feuille montre ce qu'on LIT (le contenu) et ce qu'on COPIE (la
        clé) — le rangement, lui, est déjà porté par la place dans l'arbre."""
        preview = t.content.replace("\n", " ⏎ ")
        item.setText(0, preview or "(vide)")
        item.setForeground(0, QColor(C.TEXT_NORM if preview else C.TEXT_MUTED))
        item.setData(0, self._ROLE_TEXT, t)
        item.setText(1, t.key)
        # Clé dérivée = jetable, montrée en retrait ; clé nommée à la main =
        # un contrat que quelqu'un a posé, elle mérite l'accent.
        item.setForeground(1, QColor(C.TEXT_MUTED if t.auto_key else _TEXT_COLOR))
        item.setToolTip(1, "Clé automatique — suit le rangement"
                        if t.auto_key else "Clé nommée à la main — indépendante du rangement")

    @staticmethod
    def _leaf_count(item: QTreeWidgetItem) -> int:
        n = 0
        for i in range(item.childCount()):
            c = item.child(i)
            n += 1 if c.data(0, TextTreePanel._ROLE_TEXT) is not None \
                   else TextTreePanel._leaf_count(c)
        return n

    def select_by_id(self, tid: int):
        for item in self._iter_items():
            t = item.data(0, self._ROLE_TEXT)
            if t is not None and t.id == tid:
                self._tree.setCurrentItem(item)
                self._tree.scrollToItem(item)
                return

    def clear_selection(self):
        self._blocking = True
        self._tree.clearSelection()
        self._tree.setCurrentItem(None)
        self._blocking = False
        self._current = None
        self._sync_editor()

    def _iter_items(self, parent: Optional[QTreeWidgetItem] = None):
        node = parent if parent is not None else self._tree.invisibleRootItem()
        for i in range(node.childCount()):
            child = node.child(i)
            yield child
            yield from self._iter_items(child)

    # ── Filtre ────────────────────────────────────────────────────

    def _apply_filter(self):
        """Un nœud reste visible s'il correspond lui-même ou si un descendant
        correspond — et il est alors déplié d'office : replier permet de se
        cacher son propre contenu, la recherche doit le ramener sans que
        l'utilisateur ait à deviner où il l'avait rangé.

        Le pliage forcé par la recherche ne touche PAS `_collapsed` : l'état
        choisi à la main est retrouvé tel quel quand le filtre se vide."""
        q = self._search.text().strip().casefold()
        was_blocking, self._blocking = self._blocking, True

        def visit(item: QTreeWidgetItem) -> bool:
            t = item.data(0, self._ROLE_TEXT)
            hay = (f"{item.text(0)} {item.text(1)} {t.path_str()}" if t is not None
                   else item.text(0)).casefold()
            # Liste et non générateur : `any` court-circuiterait et laisserait
            # les frères suivants avec un état de visibilité périmé.
            hits = [visit(item.child(i)) for i in range(item.childCount())]
            visible = (not q) or (q in hay) or any(hits)
            item.setHidden(not visible)
            path = item.data(0, self._ROLE_PATH)
            if path is not None:
                item.setExpanded(any(hits) if q else path not in self._collapsed)
            return visible

        for i in range(self._tree.invisibleRootItem().childCount()):
            visit(self._tree.invisibleRootItem().child(i))
        self._blocking = was_blocking

    def _on_expanded(self, item: QTreeWidgetItem):
        path = item.data(0, self._ROLE_PATH)
        if not self._blocking and path is not None:
            self._collapsed.discard(path)

    def _on_collapsed(self, item: QTreeWidgetItem):
        path = item.data(0, self._ROLE_PATH)
        if not self._blocking and path is not None:
            self._collapsed.add(path)

    # ── Sélection / édition ───────────────────────────────────────

    def _selected_text(self):
        item = self._tree.currentItem()
        if item is None or item.isHidden():
            return None
        return item.data(0, self._ROLE_TEXT)

    def _selected_path(self) -> list[str]:
        """Chemin « courant » — celui du texte sélectionné, ou du nœud si c'est
        un rangement qui est sélectionné. Sert au « + » : la nouvelle entrée
        naît là où l'utilisateur regarde."""
        item = self._tree.currentItem()
        if item is None:
            return []
        t = item.data(0, self._ROLE_TEXT)
        if t is not None:
            return list(t.path)
        path = item.data(0, self._ROLE_PATH)
        return list(path) if path else []

    def _on_sel(self):
        if self._blocking:
            return
        # Commiter l'édition en cours AVANT de changer d'entrée, sinon la
        # frappe non validée serait attribuée au texte suivant.
        self._editor.commit()
        self._current = self._selected_text()
        self._key_unlocked = False      # le cadenas se referme d'une entrée à l'autre
        self._sync_editor()
        self.text_selected.emit(self._current)

    def _sync_editor(self):
        t = self._current
        self._set_enabled(t is not None)
        self._blocking = True
        self._key_edit.setText(t.key if t else "")
        path = list(t.path) if t else []
        for lvl, e in enumerate(self._path_edits):
            e.setText(path[lvl] if lvl < len(path) else "")
        self._sync_key_lock()
        self._blocking = False
        self._editor.set_text_silent(t.content if t else "")
        self._preview.set_text(t.content if t else "")

    def _sync_key_lock(self):
        """Reflète l'état de la clé : dérivée (verrouillée), dérivée mais
        déverrouillée pour l'édition en cours, ou nommée à la main."""
        t = self._current
        auto = bool(t and t.auto_key)
        editable = bool(t) and (not auto or self._key_unlocked)
        self._key_edit.setReadOnly(not editable)
        self._key_edit.setStyleSheet(
            QSS.lineedit if editable else
            QSS.lineedit + f"QLineEdit{{color:{C.TEXT_MUTED}; background:{C.BG_PANEL};}}"
        )
        self._key_edit.setToolTip(
            "<b>Clé</b> — la poignée qu'écrivent les scripts Lua, résolue au build.<br><br>"
            + ("Elle DÉRIVE du rangement et le suivra. Déverrouiller pour la<br>"
               "nommer à la main : elle s'en détachera définitivement."
               if auto else
               "Nommée à la main : le rangement ne la touche plus.<br>"
               "La renommer met à jour les scripts qui la citent.")
        )
        self._btn_lock.setIcon(icons.get(
            "key_auto" if auto else "key_manual",
            C.TEXT_DIM if auto else _TEXT_COLOR))
        self._btn_lock.setToolTip(
            ("Clé accrochée au rangement — cliquer pour la nommer à la main"
             if not self._key_unlocked else
             "Cliquer pour la ré-accrocher au rangement")
            if auto else
            "Clé nommée à la main — cliquer pour la ré-accrocher au rangement")

    def _set_enabled(self, on: bool):
        self._editor.setEnabled(on)
        self._key_edit.setEnabled(on)
        self._btn_lock.setEnabled(on)
        self._btn_copy.setEnabled(on)
        for e in self._path_edits:
            e.setEnabled(on)
        self._btn_del.setEnabled(on)

    # ── Identité (clé / rangement) ────────────────────────────────

    def _toggle_key_lock(self):
        t = self._current
        if not t or not self._project:
            return
        if t.auto_key:
            # Clé encore dérivée : le cadenas n'ouvre que le champ. `auto_key`
            # ne tombera qu'au commit d'un nom réellement différent — cliquer
            # par curiosité ne doit rien casser.
            self._key_unlocked = not self._key_unlocked
            self._blocking = True
            self._key_edit.setText(t.key)
            self._sync_key_lock()
            self._blocking = False
            if self._key_unlocked:
                self._key_edit.setFocus()
                self._key_edit.selectAll()
            return
        # Clé nommée à la main : la ré-accrocher au rangement.
        self._key_unlocked = False
        get_history().push(RelinkTextKeyCmd(
            self._project, t, persist_fn=self._after_identity_change))

    def _copy_key(self):
        t = self._current
        if not t:
            return
        QApplication.clipboard().setText(t.key)
        self._btn_copy.setIcon(icons.get("copied", C.POWER))
        QTimer.singleShot(
            900, lambda: self._btn_copy.setIcon(icons.get("copy", C.TEXT_DIM)))

    def _commit_key(self):
        t = self._current
        if self._blocking or not t or not self._project:
            return
        new = self._key_edit.text().strip()
        if not new or new == t.key:
            self._key_edit.setText(t.key)
            return
        old, old_auto = t.key, t.auto_key
        if not self._project.rename_text_key(t, new):
            QMessageBox.warning(
                self, "Clé invalide",
                f"« {new} » est vide ou déjà utilisée par un autre texte.")
            self._key_edit.setText(t.key)
            return
        self._key_unlocked = False      # la clé est désormais nommée à la main
        get_history().push(RenameTextKeyCmd(
            self._project, t, old, new, old_auto,
            persist_fn=self._after_identity_change,
        ))

    def _commit_path(self):
        t = self._current
        if self._blocking or not t or not self._project:
            return
        new = norm_path([e.text() for e in self._path_edits])
        if new == list(t.path):
            return
        get_history().push(SetTextPathCmd(
            self._project, [(t, list(t.path), new)],
            label=f"Ranger {t.key} dans {SEP.join(new) or '(racine)'}",
            persist_fn=self._after_identity_change,
        ))

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        """Renommer un rangement = renommer le segment pour tout ce qu'il
        contient. Édition sur place, jamais de boîte de dialogue."""
        if item.data(0, self._ROLE_PATH) is None:
            return
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._tree.editItem(item, 0)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        if self._blocking or col != 0 or not self._project:
            return
        path = item.data(0, self._ROLE_PATH)
        if path is None:
            return
        new_seg = item.text(0).strip()
        # Refermer l'édition ré-émet `itemChanged` — sur le drapeau comme sur
        # le texte. Sans ce garde, le handler se rappelle indéfiniment : Qt ne
        # déduplique rien, et la pile finit par déborder.
        self._blocking = True
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if not new_seg or new_seg == path[-1]:
            item.setText(0, path[-1])
        self._blocking = False
        if not new_seg or new_seg == path[-1]:
            return
        depth = len(path) - 1
        entries = [
            (t, list(t.path), list(t.path[:depth]) + [new_seg] + list(t.path[depth + 1:]))
            for t in self._project.texts
            if tuple(t.path[:len(path)]) == path
        ]
        if not entries:
            return
        # Le nœud replié l'était sous son ancien nom : reporter l'état, sinon
        # renommer un rangement le rouvrirait sans raison.
        renamed = path[:depth] + (new_seg,)
        if path in self._collapsed:
            self._collapsed.discard(path)
            self._collapsed.add(renamed)
        cmd = SetTextPathCmd(
            self._project, entries,
            label=f"Renommer le rangement {path[-1]} → {new_seg}",
            persist_fn=self._after_identity_change,
        )
        # Différé d'un tour de boucle : la commande reconstruit l'arbre, donc
        # DÉTRUIT l'item dont on est en train de traiter le signal. Le faire
        # ici plante Qt — le C++ sous-jacent revient dans un objet libéré.
        QTimer.singleShot(0, lambda: get_history().push(cmd))

    def _after_identity_change(self):
        self.changed.emit()
        self.refresh()
        self.identity_changed.emit(self._current)

    def _on_content_edited(self, text: str):
        """Frappe en cours : aperçu seulement, aucune écriture au modèle ni
        commande d'historique (celles-ci arrivent au commit)."""
        if self._blocking or not self._current:
            return
        self._preview.set_text(text)
        item = self._tree.currentItem()
        if item is not None and item.data(0, self._ROLE_TEXT) is not None:
            self._blocking = True
            preview = text.replace("\n", " ⏎ ")
            item.setText(0, preview or "(vide)")
            item.setForeground(0, QColor(C.TEXT_NORM if preview else C.TEXT_MUTED))
            self._blocking = False

    def _on_content_committed(self, before: str, after: str):
        t = self._current
        if not t:
            return
        get_history().push(SetFieldCmd(
            t, "content", before, after,
            label=f"Contenu de {t.key}", persist_fn=self._emit_changed,
        ))

    def _emit_changed(self):
        self.changed.emit()

    # ── CRUD ──────────────────────────────────────────────────────

    def _add_text(self):
        if not self._project:
            return
        # La nouvelle entrée naît DANS le rangement courant — c'est le seul
        # moyen de créer un groupe (l'arbre n'a pas de nœud vide), et ça évite
        # d'avoir à re-ranger à la main chaque texte juste après l'avoir créé.
        t = self._project.new_text(content="", path=self._selected_path())

        def _after():
            self.changed.emit()
            self.refresh(select_id=t.id if t in self._project.texts else None)

        # new_text a déjà ajouté l'entrée : execute() est un no-op au premier
        # passage (AddListItemCmd n'ajoute que si absent), undo la retire,
        # redo la remet.
        get_history().push(AddListItemCmd(
            self._project.texts, t, persist_fn=_after,
            label=f"Nouveau texte {t.key}",
        ))

    def _delete_text(self):
        t = self._current
        if not t or not self._project:
            return
        if QMessageBox.question(
            self, "Supprimer le texte",
            f"Supprimer « {t.key} » ?\n\nLes scripts qui l'utilisent ne compileront plus.",
        ) != QMessageBox.StandardButton.Yes:
            return
        def _after():
            self.changed.emit()
            if t not in self._project.texts:
                self._current = None
                self.refresh()
                self.text_selected.emit(None)
            else:                       # undo : l'entrée est revenue
                self.refresh(select_id=t.id)

        get_history().push(RemoveListItemCmd(
            self._project.texts, t, persist_fn=_after,
            label=f"Supprimer texte {t.key}",
        ))


# ──────────────────────────────────────────────────────────────────
#  Colonne centre (contexte police) — planche de glyphes annotée
# ──────────────────────────────────────────────────────────────────
class GlyphSheet(QWidget):
    """Planche de la police, découpée en cellules annotées de leur caractère.

    Ce n'est PAS un éditeur de pixels : on dessine ses glyphes dans son outil
    habituel, comme pour un sprite (décision v0.3.2). Ce qui s'édite ici est la
    CORRESPONDANCE case → caractère, que l'import ne peut que proposer.

    Saisie directe : une case sélectionnée reçoit le caractère tapé et la
    sélection avance — remapper une planche entière se fait au clavier, sans
    ouvrir un champ par case (cf. feedback « inline plutôt que dialogues »)."""

    glyph_selected    = pyqtSignal(object)          # Glyph | None
    glyph_edited      = pyqtSignal(object, str, str)  # (glyph, avant, après)
    zoom_changed      = pyqtSignal(int)
    selection_changed = pyqtSignal(int, object)     # (nb de cases, QRect|None)
    background_clicked = pyqtSignal()               # clic hors de la planche
    color_picked      = pyqtSignal(str, object)     # (rôle, (r,g,b))
    pick_ended        = pyqtSignal()                # pipette relâchée (prise ou annulée)

    _MIN_ZOOM, _MAX_ZOOM = 2, 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._pixmap: Optional[QPixmap] = None
        self._source: Optional[QPixmap] = None   # planche BRUTE, avant trouage
        self._image = None                       # QImage source — lecture des pixels
        self._zoom = 6
        self._index = -1          # index du glyphe sélectionné
        self._hover = -1          # index survolé — révèle son caractère
        self._pan_last = None     # origine du pan clic-central
        self._range: list = []    # sélection multiple (Maj+clic) — fusion
        self._picking = ""        # rôle de couleur en cours de prélèvement, "" = aucun
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)   # survol sans bouton enfoncé
        self.setStyleSheet(f"background:{C.BG_BASE};")

    # ── Chargement ────────────────────────────────────────────────

    def load(self, font, project):
        self._font = font
        self._index = -1
        self._source = None
        self._image = None
        if font and font.asset and project:
            path = project.asset_abs(font.asset)
            if path and path.exists():
                px = QPixmap(str(path))
                if not px.isNull():
                    self._source = px
                    self._image = px.toImage()
        self.refresh_keying()
        self._resize_to_content()
        self.update()
        self.glyph_selected.emit(None)

    # ── Couleurs-clés ─────────────────────────────────────────────
    # La planche est affichée TROUÉE : les couleurs désignées disparaissent au
    # profit d'un damier. Sans ça la pipette serait aveugle — l'utilisateur ne
    # verrait pas ce qu'il vient de rendre transparent, et découvrirait le
    # résultat sur la console. Le PNG d'origine n'est jamais modifié.

    def refresh_keying(self):
        """Reconstruit l'image affichée depuis la planche brute et les
        couleurs-clés courantes."""
        self._pixmap = self._keyed_pixmap()
        self.update()

    def _keyed_pixmap(self) -> Optional[QPixmap]:
        return key_out(self._source, self._font.key_colors() if self._font else [])

    def begin_pick(self, role: str):
        """Arme la pipette pour un rôle ('bg' | 'space'). Le prochain clic sur
        la planche prend la couleur du pixel visé ; Échap annule."""
        self._picking = role
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()

    def cancel_pick(self):
        if not self._picking:
            return
        self._picking = ""
        self.unsetCursor()
        self.pick_ended.emit()

    def _pick_at(self, pos) -> bool:
        """Prélève la couleur du pixel sous `pos` dans la planche BRUTE — pas
        dans l'image trouée, dont les pixels déjà transparents ne diraient plus
        de quelle couleur ils venaient."""
        if self._image is None:
            return False
        z = self._zoom
        o = self._origin()
        x = (int(pos.x()) - o.x()) // z
        y = (int(pos.y()) - o.y()) // z
        if not (0 <= x < self._image.width() and 0 <= y < self._image.height()):
            return False
        c = self._image.pixelColor(x, y)
        role = self._picking
        self._picking = ""
        self.unsetCursor()
        self.color_picked.emit(role, (c.red(), c.green(), c.blue()))
        self.pick_ended.emit()
        return True

    def set_zoom(self, z: int):
        self._zoom = max(self._MIN_ZOOM, min(int(z), self._MAX_ZOOM))
        self._resize_to_content()
        self.update()

    @property
    def zoom(self) -> int:
        return self._zoom

    def _resize_to_content(self):
        if self._pixmap:
            self.setMinimumSize(QSize(self._pixmap.width() * self._zoom,
                                      self._pixmap.height() * self._zoom))
        else:
            self.setMinimumSize(QSize(0, 0))
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    # ── Centrage ──────────────────────────────────────────────────
    # La planche est CENTRÉE dans la zone visible tant qu'elle y tient. Tout
    # passe donc par un décalage : le rendu le pose, le hit-test le retire.
    # Sans ce point unique, les deux divergent au premier changement de zoom.

    def _origin(self) -> QPoint:
        if not self._pixmap:
            return QPoint(0, 0)
        w = self._pixmap.width() * self._zoom
        h = self._pixmap.height() * self._zoom
        return QPoint(max(0, (self.width() - w) // 2),
                      max(0, (self.height() - h) // 2))

    # ── Rendu ─────────────────────────────────────────────────────

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG_BASE))
        if not self._pixmap or not self._font:
            return
        z = self._zoom
        o = self._origin()
        p.translate(o)
        # Pixel art : jamais de lissage, sinon la planche devient floue et les
        # bords de glyphe illisibles à fort zoom.
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        sheet_rect = QRect(0, 0, self._pixmap.width() * z, self._pixmap.height() * z)
        # Damier sous la planche : sans lui, une zone rendue transparente
        # s'afficherait sur le fond uni du panneau et serait indiscernable
        # d'une zone simplement sombre.
        if self._font and self._font.key_colors():
            p.fillRect(sheet_rect, self._checker_brush())
        p.drawPixmap(sheet_rect, self._pixmap)

        # Quadrillage NU : plus d'étiquette permanente par case. Annoter les
        # 224 cases en continu noyait la planche sous le texte et masquait le
        # dessin même des glyphes — l'information n'apparaît qu'à la demande,
        # au survol.
        grid = QPen(QColor(C.BORDER_MID)); grid.setWidth(1)
        p.setPen(grid)
        for g in self._font.glyphs:
            p.drawRect(QRect(g.x * z, g.y * z, g.w * z, g.h * z))

        # Survol : la case s'assombrit et son caractère apparaît par-dessus,
        # assez grand pour être lu d'un coup d'œil. Suspendu pendant un
        # prélèvement : le voile fausserait la couleur qu'on croit viser.
        if not self._picking and 0 <= self._hover < len(self._font.glyphs):
            g = self._font.glyphs[self._hover]
            r = QRect(g.x * z, g.y * z, g.w * z, g.h * z)
            p.fillRect(r, QColor(0, 0, 0, 165))
            label = g.char if g.char.strip() else "␣"
            p.setPen(QColor(C.TEXT_HI))
            p.setFont(self._label_font(r, label))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

        # Sélection étendue (Maj+clic) : teinte de fond sur toutes les cases
        # visées, pour voir la forme du futur glyphe fusionné.
        if len(self._range) > 1:
            tint = QColor(C.ACCENT); tint.setAlpha(60)
            for i in self._range:
                g = self._font.glyphs[i]
                p.fillRect(QRect(g.x * z, g.y * z, g.w * z, g.h * z), tint)

        if 0 <= self._index < len(self._font.glyphs):
            g = self._font.glyphs[self._index]
            r = QRect(g.x * z, g.y * z, g.w * z, g.h * z)
            sel = QPen(QColor(C.ACCENT)); sel.setWidth(2)
            p.setPen(sel)
            p.drawRect(r.adjusted(1, 1, -1, -1))

    _CHECKER = None

    @classmethod
    def _checker_brush(cls) -> QBrush:
        if cls._CHECKER is None:
            cls._CHECKER = checker_brush()
        return cls._CHECKER

    def _label_font(self, r: QRect, label: str) -> QFont:
        """Police du caractère révélé — dimensionnée pour tenir dans la case,
        y compris quand plusieurs caractères y sont assignés (« ... »)."""
        size = max(6, int(r.height() * 0.55))
        if len(label) > 1:
            size = max(6, int(size * 1.4 / len(label)))
        return QFont(T.MONO, size, QFont.Weight.Bold)

    # ── Sélection ─────────────────────────────────────────────────

    def _hit(self, pos) -> int:
        if not self._font:
            return -1
        z = self._zoom
        o = self._origin()
        pt = QPoint(int(pos.x()) - o.x(), int(pos.y()) - o.y())
        for i, g in enumerate(self._font.glyphs):
            if QRect(g.x * z, g.y * z, g.w * z, g.h * z).contains(pt):
                return i
        return -1

    def selection_rect(self) -> Optional[QRect]:
        """Rectangle englobant la sélection, en coordonnées IMAGE — c'est ce
        que l'inspecteur découpe pour son aperçu."""
        if not self._font or not self._range:
            return None
        gs = [self._font.glyphs[i] for i in self._range]
        x0 = min(g.x for g in gs); y0 = min(g.y for g in gs)
        x1 = max(g.x + g.w for g in gs); y1 = max(g.y + g.h for g in gs)
        return QRect(x0, y0, x1 - x0, y1 - y0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            # Pan au clic-central — même geste que le canvas du Scene Manager.
            self._pan_last = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        # Pipette armée : le clic prend une COULEUR, il ne touche pas à la
        # sélection de case. Un clic hors image annule au lieu de prélever du
        # vide — sinon on désignerait la couleur du panneau.
        if self._picking:
            if not self._pick_at(e.pos()):
                self.cancel_pick()
            e.accept()
            return
        idx = self._hit(e.pos())
        if idx < 0:
            # Clic hors de la planche : on remet la sélection à zéro et on
            # laisse l'écran retomber sur son contexte par défaut — même règle
            # que le canvas du Scene Manager (« sélection vide → défaut »).
            self._range = []
            self._index = -1
            self.update()
            self.glyph_selected.emit(None)
            self.selection_changed.emit(0, None)
            self.background_clicked.emit()
            return
        # Maj+clic étend la sélection en RECTANGLE — c'est la forme qu'aura le
        # glyphe fusionné, autant la désigner directement.
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self._index >= 0:
            self._range = self._rect_indices(self._index, idx)
        else:
            self._range = [idx]
            if idx != self._index:
                self._index = idx
                self.glyph_selected.emit(self._font.glyphs[idx])
        self.update()
        self.selection_changed.emit(len(self._range), self.selection_rect())
        self.setFocus()

    def _rect_indices(self, a: int, b: int) -> list:
        """Indices des glyphes dont la case tombe dans le rectangle englobant
        des cases `a` et `b`."""
        gs = self._font.glyphs
        ga, gb = gs[a], gs[b]
        x0, x1 = min(ga.x, gb.x), max(ga.x + ga.w, gb.x + gb.w)
        y0, y1 = min(ga.y, gb.y), max(ga.y + ga.h, gb.y + gb.h)
        return [i for i, g in enumerate(gs)
                if g.x >= x0 and g.x + g.w <= x1 and g.y >= y0 and g.y + g.h <= y1]

    def selected_indices(self) -> list:
        return list(self._range)

    def mouseMoveEvent(self, e):
        if self._pan_last is not None and (e.buttons() & Qt.MouseButton.MiddleButton):
            delta = e.position() - self._pan_last
            self._pan_last = e.position()
            area = self._scroll_area()
            if area:
                h, v = area.horizontalScrollBar(), area.verticalScrollBar()
                h.setValue(h.value() - round(delta.x()))
                v.setValue(v.value() - round(delta.y()))
            e.accept()
            return
        idx = self._hit(e.pos())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        if self._hover != -1:
            self._hover = -1
            self.update()
        super().leaveEvent(e)

    def wheelEvent(self, e):
        """Molette = zoom, en gardant sous le curseur le point visé — sans ça,
        zoomer sur une case précise la fait fuir hors de l'écran."""
        area = self._scroll_area()
        old = self._zoom
        new = old + (1 if e.angleDelta().y() > 0 else -1)
        new = max(self._MIN_ZOOM, min(new, self._MAX_ZOOM))
        if new == old:
            return
        # Point visé, converti en coordonnées IMAGE avant le zoom : l'offset de
        # centrage change avec le zoom, il doit sortir du calcul.
        o = self._origin()
        anchor = e.position()
        img_x = (anchor.x() - o.x()) / old
        img_y = (anchor.y() - o.y()) / old
        self.set_zoom(new)
        if area:
            no = self._origin()
            h, v = area.horizontalScrollBar(), area.verticalScrollBar()
            h.setValue(round(img_x * new + no.x() - (anchor.x() - h.value())))
            v.setValue(round(img_y * new + no.y() - (anchor.y() - v.value())))
        self.zoom_changed.emit(new)
        e.accept()

    def _scroll_area(self):
        from PyQt6.QtWidgets import QScrollArea as _QSA
        w = self.parentWidget()
        while w is not None and not isinstance(w, _QSA):
            w = w.parentWidget()
        return w

    def select_index(self, idx: int):
        if not self._font or not (0 <= idx < len(self._font.glyphs)):
            return
        self._index = idx
        self.update()
        self.glyph_selected.emit(self._font.glyphs[idx])

    # ── Saisie clavier ────────────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self._picking:
            self.cancel_pick()
            return
        if not self._font or not self._font.glyphs:
            return super().keyPressEvent(e)
        n = len(self._font.glyphs)
        key = e.key()

        if key in (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down):
            cols = self._cols_per_row()
            step = {Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1,
                    Qt.Key.Key_Down: cols, Qt.Key.Key_Up: -cols}[key]
            self.select_index(max(0, min((self._index if self._index >= 0 else 0) + step, n - 1)))
            return

        text = e.text()
        # Un caractère imprimable remplace celui de la case et avance — c'est
        # ce qui rend le remappage d'une planche entière tenable au clavier.
        if text and text.isprintable() and self._index >= 0:
            g = self._font.glyphs[self._index]
            if text != g.char:
                self.glyph_edited.emit(g, g.char, text)
            if self._index + 1 < n:
                self.select_index(self._index + 1)
            else:
                self.update()
            return
        super().keyPressEvent(e)

    def _cols_per_row(self) -> int:
        """Nombre de cases sur la première ligne — les planches sont des
        grilles régulières, une ligne suffit à déduire le pas de navigation."""
        gs = self._font.glyphs if self._font else []
        if not gs:
            return 1
        y0 = gs[0].y
        cols = sum(1 for g in gs if g.y == y0)
        return max(1, cols)


class GlyphSheetPanel(QWidget):
    """Enveloppe scrollable de la planche + barre d'outils (zoom, re-découpe)."""

    glyph_selected = pyqtSignal(object)
    glyph_edited   = pyqtSignal(object, str, str)
    reslice_asked  = pyqtSignal(int, int)
    merge_asked    = pyqtSignal(list)
    selection_changed  = pyqtSignal(int, object)
    background_clicked = pyqtSignal()
    color_picked       = pyqtSignal(str, object)
    pick_ended         = pyqtSignal()

    _HINT_DEFAULT = ("Cliquer une case puis taper le caractère qu'elle représente — "
                     "la sélection avance toute seule. Flèches pour naviguer.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C.BG_BASE};")
        self._font = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(f"background:{C.BG_PANEL}; border-bottom:1px solid {C.BORDER_DARK};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.setSpacing(6)

        self._title = QLabel("PLANCHE DE GLYPHES")
        self._title.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        self._title.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        bl.addWidget(self._title)
        bl.addStretch()

        self._btn_merge = W.btn_ghost("Fusionner")
        self._btn_merge.setFont(QFont(T.MONO, T.XS))
        self._btn_merge.setToolTip(
            "Réunit les cases sélectionnées en UN glyphe couvrant leur\n"
            "rectangle — une police 16×16 dans une planche 8×8, ou un\n"
            "pictogramme large pour un mot entier.\n\n"
            "Maj+clic sur une seconde case pour étendre la sélection."
        )
        self._btn_merge.setEnabled(False)
        self._btn_merge.clicked.connect(self._ask_merge)
        bl.addWidget(self._btn_merge)

        # Re-découpe : l'import propose une taille de cellule, il peut se
        # tromper (planche irrégulière, marge). C'est le correctif que citent
        # les avertissements d'import « vérifie la taille de cellule ».
        lbl_cell = QLabel("Cellule")
        lbl_cell.setFont(QFont(T.MONO, T.XS))
        lbl_cell.setStyleSheet(f"color:{C.TEXT_DIM};")
        bl.addWidget(lbl_cell)
        self._cw = QSpinBox(); self._ch = QSpinBox()
        for s in (self._cw, self._ch):
            s.setRange(1, 64); s.setFixedWidth(48)
            s.setFont(QFont(T.MONO, T.SM)); s.setStyleSheet(QSS.spinbox)
            bl.addWidget(s)
        self._btn_reslice = W.btn_ghost("Re-découper")
        self._btn_reslice.setFont(QFont(T.MONO, T.XS))
        self._btn_reslice.setToolTip(
            "Redécoupe la planche à cette taille de cellule.\n"
            "Les caractères assignés sont reproposés depuis zéro — à utiliser\n"
            "quand la grille détectée est fausse, pas pour un ajustement fin."
        )
        self._btn_reslice.clicked.connect(
            lambda: self.reslice_asked.emit(self._cw.value(), self._ch.value()))
        bl.addWidget(self._btn_reslice)

        lbl_zoom = QLabel("Zoom")
        lbl_zoom.setFont(QFont(T.MONO, T.XS))
        lbl_zoom.setStyleSheet(f"color:{C.TEXT_DIM};")
        bl.addWidget(lbl_zoom)
        self._zoom = QSpinBox()
        self._zoom.setRange(GlyphSheet._MIN_ZOOM, GlyphSheet._MAX_ZOOM)
        self._zoom.setValue(6); self._zoom.setFixedWidth(48)
        self._zoom.setFont(QFont(T.MONO, T.SM)); self._zoom.setStyleSheet(QSS.spinbox)
        bl.addWidget(self._zoom)
        root.addWidget(bar)

        self._scroll = QScrollArea()
        # La planche occupe toute la zone visible : c'est elle qui centre son
        # image (cf. GlyphSheet._origin), ce qui laisse aussi une marge
        # cliquable autour — le clic « hors image » qui remet à zéro.
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"background:{C.BG_BASE}; border:none;")
        self._sheet = GlyphSheet()
        self._scroll.setWidget(self._sheet)
        root.addWidget(self._scroll, 1)

        self._hint = QLabel(self._HINT_DEFAULT)
        self._hint.setFont(QFont(T.MONO, T.XS))
        self._hint.setStyleSheet(
            f"color:{C.TEXT_MUTED}; background:{C.BG_PANEL}; padding:4px 8px;"
            f"border-top:1px solid {C.BORDER_DARK};")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._zoom.valueChanged.connect(self._sheet.set_zoom)
        # La molette change aussi le zoom : le spinbox doit suivre, sinon les
        # deux commandes divergent et l'affichage ment.
        self._sheet.zoom_changed.connect(self._sync_zoom_spin)
        self._sheet.selection_changed.connect(self._on_selection_changed)
        self._sheet.selection_changed.connect(self.selection_changed)
        self._sheet.background_clicked.connect(self.background_clicked)
        self._sheet.glyph_selected.connect(self.glyph_selected)
        self._sheet.glyph_edited.connect(self.glyph_edited)
        self._sheet.color_picked.connect(self.color_picked)
        self._sheet.pick_ended.connect(self.pick_ended)
        self._sheet.pick_ended.connect(lambda: self._set_hint(""))

    # ── Pipette ───────────────────────────────────────────────────

    def begin_pick(self, role: str, label: str):
        self._sheet.begin_pick(role)
        self._set_hint(f"Clique la couleur {label} sur la planche — Échap pour annuler.")

    def refresh_keying(self):
        self._sheet.refresh_keying()

    def _set_hint(self, text: str):
        self._hint.setText(text or self._HINT_DEFAULT)

    def load(self, font, project):
        self._font = font
        self._blocking = True
        if font:
            self._cw.setValue(max(1, font.cell_w))
            self._ch.setValue(max(1, font.cell_h))
            self._title.setText(f"PLANCHE — {font.name}")
        else:
            self._title.setText("PLANCHE DE GLYPHES")
        self._blocking = False
        self._sheet.load(font, project)

    def _on_selection_changed(self, n: int, rect):
        self._btn_merge.setEnabled(n > 1)

    def _ask_merge(self):
        idx = self._sheet.selected_indices()
        if len(idx) > 1:
            self.merge_asked.emit(idx)

    def _sync_zoom_spin(self, z: int):
        self._zoom.blockSignals(True)
        self._zoom.setValue(z)
        self._zoom.blockSignals(False)

    def select_glyph(self, glyph):
        """Resélectionne une case depuis l'extérieur (ex. après édition dans
        l'inspecteur) pour que le cadre de sélection reste cohérent."""
        f = self._font
        if f and glyph in f.glyphs:
            self._sheet.select_index(f.glyphs.index(glyph))

    def refresh(self):
        self._sheet.update()


# ──────────────────────────────────────────────────────────────────
#  Colonne droite — inspecteurs contextuels
# ──────────────────────────────────────────────────────────────────
def _insp_scroll(color: str, title: str) -> tuple[QWidget, QVBoxLayout, QLabel]:
    """Coquille commune : titre coloré + zone scrollable."""
    host = QWidget()
    host.setStyleSheet(f"background:{C.BG_PANEL};")
    outer = QVBoxLayout(host)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(24)
    hdr.setStyleSheet(f"background:{C.BG_RAISED}; border-bottom:1px solid {C.BORDER_DARK};")
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(8, 0, 8, 0)
    lbl = QLabel(title)
    lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color:{color}; letter-spacing:1px;")
    hl.addWidget(lbl)
    hl.addStretch()
    name_lbl = QLabel("")
    name_lbl.setFont(QFont(T.MONO, T.XS))
    name_lbl.setStyleSheet(f"color:{C.TEXT_MUTED};")
    hl.addWidget(name_lbl)
    outer.addWidget(hdr)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet(f"background:{C.BG_PANEL}; border:none;")
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(8)
    scroll.setWidget(inner)
    outer.addWidget(scroll, 1)
    return host, lay, name_lbl


class TextInspector(QWidget):
    """Contexte par défaut : identité de l'entrée sélectionnée.

    Le contenu s'édite au centre (c'est lui qu'on relit en écrivant) ; ici vit
    ce qui l'identifie et le situe."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._text = None
        self._blocking = False
        # Index {clé: {script: n}} construit en un seul parcours des scripts,
        # pas un par sélection — luaparser est trop lent pour être relancé à
        # chaque clic dans la table. None = à reconstruire.
        self._usage_index = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        host, lay, self._name_lbl = _insp_scroll(_TEXT_COLOR, "TEXTE")
        root.addWidget(host)

        self._empty = QLabel("Sélectionner un texte\ndans la table")
        self._empty.setFont(QFont(T.MONO, T.MD))
        self._empty.setStyleSheet(f"color:{C.TEXT_MUTED}; padding:20px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty)

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        # Clé et label s'éditent au CENTRE, dans le widget d'édition, juste
        # au-dessus du contenu : on édite là où on lit. L'inspecteur ne garde
        # que ce qui n'accompagne pas l'écriture — la note du traducteur et
        # l'identité machine.
        note_lbl = QLabel("NOTE POUR LE TRADUCTEUR")
        note_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        note_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        bl.addWidget(note_lbl)
        self._note_edit = QTextEdit()
        self._note_edit.setFont(QFont(T.MONO, T.SM))
        self._note_edit.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_NORM};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}"
        )
        self._note_edit.setFixedHeight(64)
        self._note_edit.setPlaceholderText("Contexte, ton, contrainte de place…")
        self._note_edit.setToolTip(
            "Contexte destiné à la traduction (v0.8) — jamais affiché en jeu."
        )
        # Commit au focus-out (comme le contenu) : une commande par frappe
        # noierait l'historique.
        self._note_edit.focusOutEvent = self._note_focus_out
        self._note_baseline = ""
        bl.addWidget(self._note_edit)

        W.separator(bl)

        # « Utilisé par » — la contrepartie visible du renommage automatique :
        # renommer une clé réécrit les `text.draw("clé")` des scripts, encore
        # faut-il savoir lesquels avant d'y toucher (et vérifier après).
        use_lbl = QLabel("UTILISÉ PAR")
        use_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        use_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        bl.addWidget(use_lbl)
        self._usage = QLabel("")
        self._usage.setFont(QFont(T.MONO, T.XS))
        self._usage.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._usage.setWordWrap(True)
        bl.addWidget(self._usage)

        W.separator(bl)

        self._meta = QLabel("")
        self._meta.setFont(QFont(T.MONO, T.XS))
        self._meta.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._meta.setWordWrap(True)
        bl.addWidget(self._meta)

        lay.addWidget(self._body)
        lay.addStretch()
        self._body.setVisible(False)

    def load(self, text, project):
        self._project = project
        self._text = text
        self._blocking = True
        has = text is not None
        self._body.setVisible(has)
        self._empty.setVisible(not has)
        if has:
            self._note_edit.setPlainText(text.note)
            self._note_baseline = text.note
            self._name_lbl.setText(text.key)
            self._usage.setText(self._usage_text(text.key))
            self._meta.setText(
                f"id {text.id}\n"
                f"rangement : {text.path_str() or '(racine)'}\n"
                + ("clé dérivée du rangement — la nommer à la main l'en détache"
                   if text.auto_key else "clé nommée à la main — le rangement ne la touche plus")
                + (f"\nscène d'origine : {text.scene}" if text.scene else "")
            )
        else:
            self._name_lbl.setText("")
            self._usage.setText("")
        self._blocking = False

    # ── Utilisations dans les scripts ─────────────────────────────

    def invalidate_usages(self):
        """L'index devient faux dès qu'un script bouge — renommage (les
        `text.draw` viennent d'être réécrits), création, suppression, ou
        édition dans le Script Editor."""
        self._usage_index = None

    def _usage_text(self, key: str) -> str:
        if self._usage_index is None:
            self._usage_index = self._build_usage_index()
        used_in = self._usage_index.get(key, {})
        if not used_in:
            return "aucun script"
        n = sum(used_in.values())
        files = "\n".join(f"  {p.name} ×{c}" if c > 1 else f"  {p.name}"
                          for p, c in sorted(used_in.items()))
        return f"{n} référence(s) dans {len(used_in)} script(s)\n{files}"

    def _build_usage_index(self) -> dict:
        if not self._project:
            return {}
        try:
            from scripting.refactor import index_refs_in_project
            from scripting.api import DOMAIN_TEXT
            return index_refs_in_project(self._project, DOMAIN_TEXT)
        except Exception:
            # luaparser absent ou scripts illisibles : l'inspecteur reste
            # utilisable, il annonce juste qu'il ne sait pas.
            return {}

    def _note_focus_out(self, e):
        QTextEdit.focusOutEvent(self._note_edit, e)
        if self._blocking or not self._text:
            return
        new = self._note_edit.toPlainText()
        if new == self._note_baseline:
            return
        old, self._note_baseline = self._note_baseline, new
        get_history().push(SetFieldCmd(
            self._text, "note", old, new,
            label=f"Note de {self._text.key}", persist_fn=self.changed.emit,
        ))


class FontInspector(QWidget):
    """Contexte « police » — lecture seule dans cet incrément.

    La grille de glyphes annotée (édition de `Glyph.char`) et l'aperçu de rendu
    viendront ensuite ; ce qui compte ici est déjà le coût en tuiles, puisque
    ces tuiles sont en concurrence directe avec le décor."""

    glyph_char_changed = pyqtSignal(object, str, str)   # (glyph, avant, après)
    pick_asked         = pyqtSignal(str, str)           # (rôle, libellé)
    key_color_cleared  = pyqtSignal(str)                # rôle

    # Les deux rôles de couleur-clé : champ du modèle, libellé, explication.
    _KEY_ROLES = (
        ("bg", "bg_color", "Fond",
         "Couleur de FOND de la planche.<br><br>"
         "Une planche exportée sans canal alpha arrive sur un aplat — vert,<br>"
         "magenta, blanc. Sans la désigner, l'encodeur la prend pour de l'encre<br>"
         "et chaque glyphe sort en pavé plein.<br><br>"
         "Proposée automatiquement à l'import (couleur dominante) ; repique-la<br>"
         "si la planche est atypique."),
        ("space", "space_color", "Espacement",
         "Couleur qui MARQUE L'ESPACEMENT entre les glyphes.<br><br>"
         "Convention de plusieurs outils, dont GB Studio : une seconde couleur<br>"
         "remplit la fin de chaque case pour indiquer où s'arrête le caractère.<br>"
         "Elle doit disparaître au même titre que le fond, sinon elle s'affiche<br>"
         "en jeu."),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = None
        self._project = None
        self._glyph = None
        self._blocking = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        host, lay, self._name_lbl = _insp_scroll(_FONT_COLOR, "POLICE")
        root.addWidget(host)

        self._info = QLabel("")
        self._info.setFont(QFont(T.MONO, T.SM))
        self._info.setStyleSheet(f"color:{C.TEXT_NORM};")
        self._info.setWordWrap(True)
        lay.addWidget(self._info)

        W.separator(lay)

        # ── Transparence ──────────────────────────────────────────
        # Deux pipettes plutôt qu'un sélecteur de couleur : la couleur voulue
        # est SOUS LES YEUX, dans la planche. La nommer en hexadécimal serait
        # demander à l'utilisateur de faire le travail de la machine.
        tr_lbl = QLabel("TRANSPARENCE")
        tr_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        tr_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        lay.addWidget(tr_lbl)

        self._swatches: dict[str, QLabel] = {}
        for role, _field, label, tip in self._KEY_ROLES:
            lay.addLayout(self._key_row(role, label, tip))

        self._key_hint = QLabel("")
        self._key_hint.setFont(QFont(T.MONO, T.XS))
        self._key_hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._key_hint.setWordWrap(True)
        lay.addWidget(self._key_hint)

        W.separator(lay)

        cs_lbl = QLabel("CHARSET")
        cs_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        cs_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        lay.addWidget(cs_lbl)

        self._charset = QTextEdit()
        self._charset.setReadOnly(True)
        self._charset.setFont(QFont(T.CODE, T.MD))
        self._charset.setStyleSheet(
            f"QTextEdit{{background:{C.BG_INPUT}; color:{C.TEXT_HI};"
            f"border:1px solid {C.BORDER_MID}; border-radius:3px; padding:4px;}}"
        )
        self._charset.setFixedHeight(80)
        self._charset.setToolTip(
            "Caractères couverts par cette police — dérivé des glyphes,<br>"
            "jamais stocké tel quel. L'édition glyphe par glyphe viendra<br>"
            "avec la grille annotée."
        )
        lay.addWidget(self._charset)

        W.separator(lay)

        gl_lbl = QLabel("GLYPHE SÉLECTIONNÉ")
        gl_lbl.setFont(QFont(T.MONO, T.XS, QFont.Weight.Bold))
        gl_lbl.setStyleSheet(f"color:{C.TEXT_DIM}; letter-spacing:1px;")
        lay.addWidget(gl_lbl)

        # Le glyphe isolé : la case seule, agrandie, détachée de la planche —
        # c'est ce qu'on regarde pour décider quel caractère lui assigner.
        self._glyph_preview = QLabel()
        self._glyph_preview.setFixedHeight(72)
        self._glyph_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._glyph_preview.setStyleSheet(
            f"background:{C.BG_INPUT}; border:1px solid {C.BORDER_MID};"
            f"border-radius:3px;")
        lay.addWidget(self._glyph_preview)

        # Édition case par case plutôt que le charset entier : on corrige la
        # case qu'on a sous les yeux, sans risquer de décaler tout le reste.
        self._char_edit = QLineEdit()
        self._char_edit.setStyleSheet(QSS.lineedit)
        self._char_edit.setFont(QFont(T.CODE, T.LG))
        self._char_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._char_edit.setPlaceholderText("caractère")
        self._char_edit.setToolTip(
            "<b>Caractère de cette case</b><br><br>"
            "Plusieurs caractères sont acceptés (ex. « ... ») : la case devient<br>"
            "alors une <i>ligature</i>, un dessin unique pour une suite de<br>"
            "caractères."
        )
        self._char_edit.editingFinished.connect(self._commit_char)
        lay.addWidget(self._char_edit)

        self._glyph_info = QLabel("Aucune case sélectionnée")
        self._glyph_info.setFont(QFont(T.MONO, T.XS))
        self._glyph_info.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._glyph_info.setWordWrap(True)
        lay.addWidget(self._glyph_info)

        self._hint = QLabel(
            "Le dessin des glyphes se fait dans ton éditeur d'images, comme "
            "pour un sprite — ici on corrige seulement à quel caractère "
            "correspond chaque case."
        )
        self._hint.setFont(QFont(T.MONO, T.XS))
        self._hint.setStyleSheet(f"color:{C.TEXT_MUTED};")
        self._hint.setWordWrap(True)
        lay.addWidget(self._hint)

        lay.addStretch()

    # ── Couleurs-clés ─────────────────────────────────────────────

    def _key_row(self, role: str, label: str, tip: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        name = QLabel(label)
        name.setFont(QFont(T.MONO, T.SM))
        name.setStyleSheet(f"color:{C.TEXT_NORM};")
        name.setToolTip(tip)
        name.setFixedWidth(84)
        row.addWidget(name)

        swatch = QLabel()
        swatch.setFixedSize(28, 20)
        swatch.setToolTip(tip)
        self._swatches[role] = swatch
        row.addWidget(swatch)
        row.addStretch()

        pick = QPushButton()
        pick.setIcon(icons.get("eyedropper", C.TEXT_NORM))
        pick.setFixedSize(24, 22)
        pick.setToolTip(f"Prélever la couleur « {label} » sur la planche")
        pick.setStyleSheet(QSS.button_icon)
        pick.clicked.connect(lambda _=False, r=role, l=label: self.pick_asked.emit(r, l))
        row.addWidget(pick)

        clear = QPushButton()
        clear.setIcon(icons.get("clear", C.TEXT_MUTED))
        clear.setFixedSize(24, 22)
        clear.setToolTip(f"Ne plus rendre transparente la couleur « {label} »")
        clear.setStyleSheet(QSS.button_icon)
        clear.clicked.connect(lambda _=False, r=role: self.key_color_cleared.emit(r))
        row.addWidget(clear)
        return row

    def refresh_keys(self):
        """Relit les deux pastilles depuis le modèle — après un prélèvement,
        un effacement ou une annulation."""
        f = self._font
        for role, field_name, _label, _tip in self._KEY_ROLES:
            rgb = getattr(f, field_name, None) if f else None
            sw = self._swatches[role]
            if rgb is None:
                sw.setStyleSheet(
                    f"background:{C.BG_INPUT}; border:1px dashed {C.BORDER_MID};"
                    f"border-radius:3px;")
                sw.setText("")
            else:
                r, g, b = rgb
                sw.setStyleSheet(
                    f"background:rgb({r},{g},{b}); border:1px solid {C.BORDER_MID};"
                    f"border-radius:3px;")
                sw.setText("")
        n = len(f.key_colors()) if f else 0
        # La couleur d'espacement fait DEUX choses : elle disparaît, et elle
        # déclare la chasse. La seconde est invisible sur la planche — c'est ici
        # qu'il faut la dire, sinon l'utilisateur ne sait pas ce qu'il a gagné.
        mode = ""
        if f and f.source_format == "png":
            mode = ("\nChasse déclarée par l'espacement (proportionnelle)."
                    if f.space_color else
                    "\nChasse en mono — désigner l'espacement la rend proportionnelle.")
        self._key_hint.setText(
            ("Aucune couleur transparente — la planche part telle quelle."
             if n == 0 else
             f"{n} couleur(s) rendue(s) transparente(s). Le PNG n'est pas modifié.")
            + mode
        )

    def load(self, font, project=None):
        self._font = font
        if project is not None:
            self._project = project
        if not font:
            self._name_lbl.setText("")
            self._info.setText("")
            self._charset.setPlainText("")
            self.refresh_keys()
            self.set_glyph(None)
            return
        self._name_lbl.setText(font.name)
        self.refresh_stats()
        self.refresh_keys()
        self.set_glyph(None)

    def refresh_stats(self):
        """Recalcule les compteurs — le charset et le coût en tuiles sont
        dérivés des glyphes, donc à relire après chaque édition."""
        f = self._font
        if not f:
            return
        tiles = f.tile_count()
        # 512 tuiles par charblock GBA (16 Ko en 4bpp) : au-delà, la police
        # déborde sur le décor. Le chiffre seul ne parle pas, la limite si.
        warn = "  ⚠ dépasse un charblock" if tiles > 512 else ""
        self._info.setText(
            f"{len(f.glyphs)} glyphes\n"
            f"cellule {f.cell_w}×{f.cell_h} px · interligne {f.line_height}\n"
            f"{tiles} tuiles / 512 par charblock{warn}\n"
            f"source : {f.source_format}"
        )
        self._charset.setPlainText(f.charset)

    def set_glyph(self, glyph, project=None):
        if project is not None:
            self._project = project
        self._glyph = glyph
        self._blocking = True
        if not glyph:
            self._glyph_info.setText("Aucune case sélectionnée")
            self._glyph_preview.clear()
            self._char_edit.clear()
            self._char_edit.setEnabled(False)
            self._blocking = False
            return
        self._char_edit.setEnabled(True)
        self._char_edit.setText(glyph.char)
        self._glyph_preview.setPixmap(self._crop(glyph))
        extra = "  (ligature)" if len(glyph.char) > 1 else ""
        # D'où vient la chasse, et pas seulement sa valeur : « 5 px » ne dit pas
        # si c'est une déclaration de l'auteur ou le mono par défaut, alors que
        # c'est ce qui indique s'il faut désigner la couleur d'espacement.
        f = self._font
        origin = ("déclarée par l'espacement" if f and f.space_color
                  else "mono" if not f or f.source_format == "png"
                  else "descripteur .fnt")
        # La chasse EFFECTIVE, pas celle stockée : une police sans couleur
        # d'espacement est mono quoi que porte le champ (les sidecars importés
        # avant la règle gardent d'anciennes mesures d'encre). Afficher la
        # valeur brute ferait mentir l'inspecteur sur ce que fera la ROM.
        from codegen.font_emit import glyph_advance_px
        adv = glyph_advance_px(glyph, f) if f else glyph.advance
        self._glyph_info.setText(
            f"rect {glyph.w}×{glyph.h} à ({glyph.x}, {glyph.y})\n"
            f"chasse : {adv} px — {origin}{extra}"
        )
        self._blocking = False

    def set_selection(self, count: int, rect):
        """Sélection multiple (Maj+clic) : l'aperçu montre le RECTANGLE visé,
        c'est-à-dire le futur glyphe fusionné — pas seulement sa première case."""
        if count <= 1 or rect is None:
            return          # cas simple : set_glyph a déjà fait le travail
        self._glyph_preview.setPixmap(self._crop_rect(rect))
        self._char_edit.setEnabled(False)
        self._glyph_info.setText(
            f"{count} cases sélectionnées\n"
            f"fusion → un glyphe {rect.width()}×{rect.height()} "
            f"({max(1,(rect.width()+7)//8)}×{max(1,(rect.height()+7)//8)} tuiles)"
        )

    def _crop(self, glyph) -> QPixmap:
        return self._crop_rect(QRect(glyph.x, glyph.y, glyph.w, glyph.h))

    def _crop_rect(self, r: QRect) -> QPixmap:
        """Découpe une région de la planche et l'agrandit au plus grand zoom
        entier qui tient — un glyphe 8×8 est illisible à taille réelle."""
        f, p = self._font, self._project
        if not (f and p and f.asset):
            return QPixmap()
        path = p.asset_abs(f.asset)
        if not path or not path.exists():
            return QPixmap()
        sheet = QPixmap(str(path))
        if sheet.isNull():
            return QPixmap()
        cell = sheet.copy(r)
        z = max(1, min(64 // max(1, r.height()), 64 // max(1, r.width())))
        cell = cell.scaled(cell.width() * z, cell.height() * z,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        # Aperçu troué comme la planche : c'est ici qu'on juge si l'espacement
        # a bien été désigné — sur une case isolée, pas sur la grille entière.
        keys = f.key_colors()
        if not keys:
            return cell
        holed = key_out(cell, keys)
        out = QPixmap(holed.size())
        out.fill(Qt.GlobalColor.transparent)
        q = QPainter(out)
        q.fillRect(out.rect(), GlyphSheet._checker_brush())
        q.drawPixmap(0, 0, holed)
        q.end()
        return out

    def _commit_char(self):
        """Valide le caractère saisi pour la case courante."""
        if self._blocking or not self._glyph:
            return
        new = self._char_edit.text()
        if new == self._glyph.char:
            return
        if not new:
            self._char_edit.setText(self._glyph.char)
            return
        self.glyph_char_changed.emit(self._glyph, self._glyph.char, new)


# ──────────────────────────────────────────────────────────────────
#  Écran
# ──────────────────────────────────────────────────────────────────
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
            f"QSplitter::handle:hover{{background:{_TEXT_COLOR};}}"
        )

        self._fonts = FontFinderPanel()

        # Le CENTRE est contextuel lui aussi : table de textes par défaut,
        # planche de glyphes quand une police est sélectionnée. C'est la
        # colonne large — une police complète fait plusieurs centaines de
        # cases, elle n'aurait pas tenu dans l'inspecteur de droite.
        self._center = QStackedWidget()
        self._texts = TextTreePanel()
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
        self._fonts.font_selected.connect(self._on_font_selected)
        self._texts.text_selected.connect(self._on_text_selected)
        self._texts.changed.connect(self._persist)
        # Clé/label édités au centre : l'inspecteur (méta, badge « auto »)
        # doit se relire, il affiche la clé dans son en-tête.
        self._texts.identity_changed.connect(self._on_identity_changed)
        self._text_insp.changed.connect(self._on_text_insp_changed)
        self._sheet.glyph_selected.connect(self._font_insp.set_glyph)
        self._sheet.glyph_edited.connect(self._on_glyph_edited)
        self._sheet.reslice_asked.connect(self._on_reslice)
        self._sheet.merge_asked.connect(self._on_merge)
        self._sheet.selection_changed.connect(self._font_insp.set_selection)
        self._sheet.background_clicked.connect(self._on_sheet_background)
        # Pipettes : l'inspecteur DEMANDE, la planche PRÉLÈVE, l'écran décide
        # (commande d'historique + sauvegarde). Aucune des deux vues ne connaît
        # l'autre — même découpage que la sélection de glyphe.
        self._font_insp.pick_asked.connect(self._sheet.begin_pick)
        self._font_insp.key_color_cleared.connect(
            lambda role: self._set_key_color(role, None))
        self._sheet.color_picked.connect(self._set_key_color)
        # Deux chemins d'édition, une seule commande : la frappe sur la planche
        # et le champ de l'inspecteur passent par le même _on_glyph_edited.
        self._font_insp.glyph_char_changed.connect(self._on_glyph_edited)

    def load_project(self, project):
        self._project = project
        self._fonts.load_project(project)
        self._texts.load_project(project)
        self._text_insp.invalidate_usages()
        self._text_insp.load(None, project)
        self._inspectors.setCurrentIndex(self._CTX_TEXT)

    def invalidate_script_usages(self):
        """Branché sur « scripts_changed » : un script créé, supprimé ou
        réécrit périme l'index des utilisations. Recalculé paresseusement, à
        la prochaine sélection — l'écran n'est peut-être même pas affiché."""
        self._text_insp.invalidate_usages()

    def _on_identity_changed(self, text):
        """Clé renommée : `rename_text_key` vient de réécrire les scripts, donc
        l'index des utilisations ET l'inspecteur sont périmés tous les deux."""
        self._text_insp.invalidate_usages()
        self._text_insp.load(text, self._project)

    def refresh(self):
        """Recharge depuis le projet — polices modifiées ailleurs (dépôt de
        fichier détecté par le watcher), textes rétablis par un undo/redo."""
        if not self._project:
            return
        self._fonts.refresh()
        self._texts._reload_preview_fonts()   # polices apparues/disparues
        self._texts.refresh()
        # L'inspecteur affiche peut-être une valeur que l'undo vient de
        # changer (clé, label), ou une entrée qui n'existe plus.
        cur = self._text_insp._text
        if cur is not None and cur not in self._project.texts:
            cur = None
        # Un undo de renommage repasse par rename_text_key : les scripts ont
        # rebougé, l'index des utilisations aussi.
        self._text_insp.invalidate_usages()
        self._text_insp.load(cur, self._project)

        # Contexte police : un undo a pu changer un caractère ou re-découper la
        # planche — les deux se voient sur la grille et dans les compteurs.
        font = self._font_insp._font
        if font is not None:
            if font not in self._project.fonts:
                self._font_insp.load(None, self._project)
                self._sheet.load(None, self._project)
                self._set_context(self._CTX_TEXT)
            else:
                # refresh_keying et pas update() : un undo a pu porter sur une
                # couleur-clé, la planche trouée est à reconstruire.
                self._sheet.refresh_keying()
                self._font_insp.refresh_stats()
                self._font_insp.refresh_keys()

    # ── Contexte ──────────────────────────────────────────────────

    def _set_context(self, ctx: int):
        self._center.setCurrentIndex(ctx)
        self._inspectors.setCurrentIndex(ctx)

    def _on_font_selected(self, font):
        if font is None:
            # Retour au défaut : c'est la règle générale « sélection vide →
            # contexte par défaut », pas un cas particulier de retour.
            self._set_context(self._CTX_TEXT)
            return
        self._texts.clear_selection()
        self._font_insp.load(font, self._project)
        self._sheet.load(font, self._project)
        self._set_context(self._CTX_FONT)

    def _on_text_selected(self, text):
        # Sélectionner un texte quitte le contexte police, même si une police
        # reste surlignée à gauche.
        self._fonts.clear_selection()
        self._text_insp.load(text, self._project)
        self._set_context(self._CTX_TEXT)

    # ── Glyphes ───────────────────────────────────────────────────

    def _on_glyph_edited(self, glyph, before: str, after: str):
        font = self._font_insp._font
        get_history().push(SetFieldCmd(
            glyph, "char", before, after,
            label=f"Glyphe « {after} »",
            persist_fn=lambda: self._after_glyph_change(font),
        ))

    def _after_glyph_change(self, font):
        """Le charset et le coût en tuiles sont DÉRIVÉS des glyphes : les
        relire après chaque édition, sinon l'inspecteur ment."""
        self._sheet.refresh()
        self._font_insp.refresh_stats()
        # Réafficher la case courante : son champ et son aperçu doivent
        # montrer la valeur retenue, y compris après un undo.
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        if self._project and font:
            self._project.fonts.save(font)

    # ── Couleurs-clés de la planche ───────────────────────────────

    _KEY_FIELD = {"bg": ("bg_color", "fond"), "space": ("space_color", "espacement")}

    def _set_key_color(self, role: str, rgb):
        """Pose (ou retire, si `rgb` est None) une couleur transparente.

        Passe par l'historique comme toute autre édition : se tromper de pixel
        arrive, et sans undo il faudrait retrouver la bonne couleur à l'œil."""
        font = self._font_insp._font
        entry = self._KEY_FIELD.get(role)
        if not font or entry is None:
            return
        field_name, label = entry
        old = getattr(font, field_name)
        new = tuple(rgb) if rgb is not None else None
        if old == new:
            return
        get_history().push(_SetKeyColorCmd(
            self._project, font, field_name, old, new,
            label=(f"Couleur {label} de {font.name}" if new
                   else f"Retirer la couleur {label} de {font.name}"),
            persist_fn=lambda: self._after_key_color(font),
        ))

    def _after_key_color(self, font):
        """La transparence change ce que VOIT l'utilisateur (planche trouée,
        aperçu du glyphe) et ce que MESURE le modèle (chasse d'encre) — les
        deux se relisent, sinon l'aperçu et la ROM divergeraient."""
        self._sheet.refresh_keying()
        self._font_insp.refresh_keys()
        self._font_insp.set_glyph(self._font_insp._glyph, self._project)
        # L'aperçu écran vit dans l'autre contexte, mais il rend AVEC cette
        # police : il doit retrouer sa planche même si on ne le regarde pas.
        self._texts.refresh_preview_font()
        if self._project and font:
            self._project.fonts.save(font)

    def _on_sheet_background(self):
        """Clic hors de la planche : sélection à zéro et retour au contexte
        Texte. Même règle que partout ailleurs — une sélection vide ramène au
        contexte par défaut, sans bouton de retour dédié."""
        self._fonts.clear_selection()
        self._font_insp.set_glyph(None)
        self._set_context(self._CTX_TEXT)

    def _on_merge(self, indices: list):
        font = self._font_insp._font
        if not font or len(indices) < 2:
            return
        # Le caractère du glyphe fusionné : celui de la 1ère case par défaut,
        # que l'utilisateur remplace ensuite (souvent par un mot — « (shift) »).
        first = font.glyphs[min(indices)].char
        get_history().push(_MergeGlyphsCmd(
            font, indices, first,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _on_reslice(self, cw: int, ch: int):
        font = self._font_insp._font
        if not font or not self._project or not font.asset:
            return
        png = self._project.asset_abs(font.asset)
        if not png or not png.exists():
            QMessageBox.warning(self, "Re-découpe",
                                f"Planche introuvable : {font.asset}")
            return
        if QMessageBox.question(
            self, "Re-découper la planche",
            f"Redécouper « {font.name} » en cellules de {cw}×{ch} ?\n\n"
            "Les caractères assignés sont reproposés depuis zéro — les "
            "corrections manuelles seront perdues.",
        ) != QMessageBox.StandardButton.Yes:
            return
        from core import font_import
        try:
            # Les couleurs déjà repiquées restent : une re-découpe change le
            # DÉCOUPAGE, pas la lecture des couleurs de la planche.
            fields = font_import.import_font_png(png, cell=(cw, ch),
                                                 keys=font.key_colors(),
                                                 space_color=font.space_color)
        except Exception as exc:
            QMessageBox.warning(self, "Re-découpe", f"Import impossible : {exc}")
            return
        get_history().push(_ResliceFontCmd(
            self._project, font, fields,
            persist_fn=lambda: self._reload_font(font),
        ))

    def _reload_font(self, font):
        self._sheet.load(font, self._project)   # load reconstruit déjà le trouage
        self._font_insp.load(font, self._project)
        if self._project:
            self._project.fonts.save(font)

    # ── Persistance ───────────────────────────────────────────────

    def _persist(self):
        if self._project:
            self._project.save_texts()

    def _on_text_insp_changed(self):
        self._persist()
        # Seule la note s'édite désormais ici : la table ne l'affiche pas,
        # inutile de la reconstruire.
