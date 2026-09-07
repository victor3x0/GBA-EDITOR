"""ui/scene_manager/canvas/canvas_region_item.py — l'item de zone d'interface.

Extrait de `scene_canvas` (A3) : `UIRegionItem`, l'item graphique le plus riche du
canvas — il rend une zone/conteneur/texte (aplat, image, nine-slice, glyphes
composés), porte ses poignées de redimensionnement et son drag avec snap
d'alignement. Sa règle de composition (`region_is_composited`) et sa banque d'encre
(`region_ink_bank`) sont lues du build via `gen_text` (imports locaux), pour que
l'aperçu ne puisse pas diverger de la ROM.

Dépend vers le bas : modèle, thème, `align_snap`, `canvas_const`/`canvas_items`
(`hw_layer_z`), et `gen_text`/`font_emit`/… en imports locaux. Ne remonte jamais
vers la scène/vue (il dialogue avec sa scène via `self.scene()` + `hasattr`).
"""
from __future__ import annotations

import copy

from core.sprite_compose import compose_frame_image
from core.selection_bus import get_bus, UIRegionSelection
from ui.common.theme import C
from ui.scene_manager.align_snap import (
    candidate_lines, collect_targets, snap as _align_snap, SNAP_PX as _ALIGN_SNAP_PX,
)
from ui.scene_manager.canvas.canvas_const import GBA_W, GBA_H
from ui.scene_manager.canvas.canvas_items import hw_layer_z
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsPixmapItem,
)


# Poignées de redimensionnement — chaque nom porte les bords qu'il déplace
# (left, top, right, bottom). Les coins bougent deux bords, les milieux un seul.
_HANDLE_EDGES = {
    "nw": (True,  True,  False, False),
    "n":  (False, True,  False, False),
    "ne": (False, True,  True,  False),
    "e":  (False, False, True,  False),
    "se": (False, False, True,  True),
    "s":  (False, False, False, True),
    "sw": (True,  False, False, True),
    "w":  (True,  False, False, False),
}
_HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
    "n":  Qt.CursorShape.SizeVerCursor,   "s":  Qt.CursorShape.SizeVerCursor,
    "e":  Qt.CursorShape.SizeHorCursor,   "w":  Qt.CursorShape.SizeHorCursor,
}
# Demi-côté du carré de poignée dessiné, et tolérance de préhension, en pixels
# ÉCRAN : convertis en unités scène via le zoom courant pour rester constants à
# l'affichage quel que soit le niveau de zoom.
_HANDLE_HALF_PX = 3.5
_HANDLE_GRAB_PX = 6.0

# Planches de glyphes trouées : {(chemin, mtime, taille): QPixmap | None}.
# Au niveau du module, pas de l'item — les items sont reconstruits à chaque
# sauvegarde et retrouer une planche (numpy) à ce rythme se sentirait.
_TEXT_SHEETS: dict = {}

# Planches APLATIES sur une encre : {(cacheKey de la planche, (r,g,b)): QPixmap}.
# L'encre d'index 1-15 remplace toute la couleur de la police par une seule
# (cf. `UIText.text_color`) ; recolorer l'atlas à chaque repaint (survol, zoom,
# pan) se sentirait, d'où ce cache jumeau de `_TEXT_SHEETS`.
_FLAT_SHEETS: dict = {}

# Sentinelle « pas encore calculé » pour le cache de banque d'un item (une valeur
# None étant, elle, un résultat légitime — « pas de banque »).
_UNSET = object()


class UIRegionItem(QGraphicsRectItem):
    """Une zone de texte dessinée dans le canvas — sélectionnable, déplaçable,
    redimensionnable par ses poignées.

    Le rectangle est en coordonnées LOCALES (0,0,w,h) et la position porte x/y :
    sans ça, déplacer l'item ne changerait pas `pos()` et il n'y aurait rien à
    relire au relâchement.

    Déplacement ET redimensionnement sont validés au RELÂCHEMENT, pas à chaque
    pixel : pousser une commande d'historique par événement de souris remplirait
    la pile de cent entrées pour un seul geste. Même raison que pour le drag d'un
    actor. Le geste vit en flottant dans le canvas ; le snap à la tuile (cible
    BG) et l'arrondi de taille ne tombent qu'à la fin, exactement comme le move.

    Une zone ancrée sur un actor est dessinée à l'offset près de son acteur si
    on le trouve — sinon à l'origine de l'écran, avec un liseré discontinu qui
    dit que la position affichée n'est pas celle du jeu."""

    # Exception canvas-only à la règle « forme, pas teinte » (icons.py) :
    # pendant un drag, la couleur se lit plus vite qu'une icône de 6 px.
    # Ailleurs (arbre, finders) le type reste porté par la FORME.
    _KIND_COLORS = {
        "text":   "#4f8ff7",   # texte (bleu, famille Interface)
        "container": "#b388ff",   # conteneur (lavande — structure/groupe)
        # La liste est un conteneur : même famille que lui, teinte plus soutenue
        # — ce qu'elle ajoute est un comportement, pas une autre nature.
        "list":   "#8c6bff",
        "image":  "#ffb454",   # image (ambre — un dessin, pas une structure)
    }
    _KIND_ICONS = {"container": "ui_container", "list": "ui_list",
                   "text": "ui_text", "image": "ui_image"}

    def __init__(self, layout_asset, region, project, scene, save_fn=None, parent=None):
        super().__init__(0, 0, max(8, region.w), max(8, region.h), parent)
        self._layout, self._region = layout_asset, region
        self._project, self._scene = project, scene
        self._save = save_fn
        self._press_pos = None
        from ui.common import icons as _icons
        self._COLOR = QColor(self._KIND_COLORS.get(getattr(region, "kind", "region"),
                                                    _icons.COLOR_UI))
        # Poignée en cours de traction (None = déplacement/simple sélection) et
        # géométrie de départ du geste, figée au press pour que chaque mouvement
        # se calcule depuis l'origine et non depuis l'image précédente.
        self._resize_handle: "str | None" = None
        self._resize_start: "tuple | None" = None
        # Vrai le temps d'un déplacement à la souris — le seul cas où l'on veut
        # aimanter la position et tracer des guides. Sans ce drapeau, les setPos
        # internes (rebuild, snap au relâchement, commit d'un resize) passeraient
        # aussi dans le chemin d'aimantation d'`itemChange`.
        self._moving = False
        # Dernière position vue pendant le geste — sert à calculer le delta à
        # rejouer sur les DESCENDANTS (leur x/y modèle est relatif au parent :
        # rien à réécrire chez eux, mais l'écran doit les faire suivre).
        self._last_pos = None
        self.setAcceptHoverEvents(True)

        ox, oy, anchored = self._origin()
        self.setPos(ox, oy)

        # Tout le dessin passe par `paint` : l'item lui-même ne porte ni trait ni
        # remplissage. Sans ça `super().paint()` reposerait le style de repos
        # par-dessus l'état (survol, sélection) que `paint` vient de calculer.
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._anchored = anchored
        self._hovered = False
        # CONTENU (ce que la GBA affichera : couleur de palette, hachures d'un
        # asset pas encore rendu) — à distinguer du CHROME d'édition (voile,
        # contour, poignées), qui lui dépend de l'état.
        self._content_brush = self._fill_brush()
        # Nine-slice / background : si l'image source charge, elle est peinte
        # dans `paint` et REMPLACE le pinceau ; sinon on garde les hachures.
        self._ns_pixmap = None
        self._ns = None
        self._bg_pixmap = None
        # Image : la frame RÉELLE du sprite, peinte comme le sera la ROM. Un
        # rectangle nommé ne dirait pas si l'icône est la bonne ni si elle
        # déborde du conteneur — or c'est exactement pour ça qu'on la pose dans
        # un canvas plutôt que dans un formulaire.
        self._img_pixmap = None
        # Fond sprite d'un conteneur : la MÊME frame que `_img_pixmap`, mais
        # répétée sur le rectangle (cf. `_paint_sprite_fill`). Le drapeau tient
        # la différence, la source du dessin étant identique.
        self._tile_fill = False
        from core.models.ui_region import (
            FILL_NINE, FILL_BG, FILL_SPRITE, KIND_CONTAINER)
        _fk = getattr(region, "fill_kind", "")
        if getattr(region, "kind", "") == KIND_CONTAINER:
            if _fk == FILL_NINE:
                pix, ns = self._load_nine_slice()
                if pix is not None and not pix.isNull():
                    self._ns_pixmap, self._ns = pix, ns
                    self._content_brush = None
            elif _fk == FILL_BG:
                pix = self._load_bg_fill()
                if pix is not None and not pix.isNull():
                    self._bg_pixmap = pix
                    self._content_brush = None
            elif _fk == FILL_SPRITE:
                # `_load_image_frame` lit `sprite_name`/`state_index`, que
                # `UIContainer` expose comme `UIImage` — rien à dupliquer.
                pix = self._load_image_frame()
                if pix is not None and not pix.isNull():
                    self._img_pixmap = pix
                    self._tile_fill = True
                    self._content_brush = None
        elif getattr(region, "kind", "") == "image":
            pix = self._load_image_frame()
            if pix is not None and not pix.isNull():
                self._img_pixmap = pix
                self._content_brush = None
        rm = int(getattr(scene, "render_mode", 0) or 0)
        is_obj_target = self._layout.resolved_target(region, rm) == "obj"
        target = "sprite (OBJ)" if is_obj_target else "fond (BG)"
        # Même échelle que les fonds et les acteurs (`hw_layer_z`) : une zone
        # OBJ (image, panneau à fond sprite) porte SA priorité (`.priority`,
        # 0-3, absente = 0 = devant) ; une zone BG vit sur le layer d'UI de la
        # scène (`text_bg`), à SA priorité — jamais un zValue fixe qui la
        # placerait toujours devant les acteurs, contrairement à la ROM.
        # `set_ui_regions` affine ensuite l'ordre ENTRE zones du même layer.
        if is_obj_target:
            # Priorité HÉRITÉE (-1) : on résout comme le runtime (`ui_obj_prio`)
            # — la profondeur de l'acteur ancré, à défaut 0 (devant). Un aperçu
            # qui montrerait le fond de container au fond alors que la ROM le
            # pose à la profondeur de sa mouche, c'est justement le décalage à
            # éviter. Une valeur 0-3 explicite reste une surcharge.
            prio = int(getattr(region, "priority", -1))
            if prio < 0:
                anchor, actor_name = self._layout.effective_anchor(region)
                prio = 0
                if anchor == "actor" and actor_name and self._scene:
                    a = next((x for x in getattr(self._scene, "actors", [])
                              if getattr(x, "name", "") == actor_name), None)
                    if a is not None:
                        prio = int(getattr(a, "priority", 0) or 0)
            base_z = hw_layer_z(prio, is_obj=True)
        else:
            text_bg = getattr(scene, "text_bg", -1)
            base_z = hw_layer_z(text_bg if text_bg in (0, 1, 2, 3) else 0, is_obj=False)
        self.setZValue(base_z)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        # L'empreinte en tuiles n'a de sens que pour une zone de texte ; un
        # conteneur ou un texte authoré n'expose pas `tile_rect`.
        tiles = ""
        if hasattr(region, "tile_rect"):
            _, _, tw, th = region.tile_rect()
            tiles = f"{tw}×{th} tiles · "
        self.setToolTip(f"“{region.name}” — {self._layout.name}\n"
                        f"{tiles}target {target}\n"
                        f"Drag to move · handles to resize · Alt-drag to duplicate")

        # Étiquette : icône de type + le nom que cite le script, lisibles sans
        # passer par l'inspecteur.
        icon = _icons.get(self._KIND_ICONS.get(getattr(region, "kind", "text"),
                                               "ui_text"), self._COLOR.name())
        self._kind_icon = QGraphicsPixmapItem(icon.pixmap(32, 32), self)
        self._kind_icon.setScale(6.0 / 32.0)      # ≈ 6 px GBA, net à tout zoom
        self._label = QGraphicsSimpleTextItem(region.name, self)
        self._label.setBrush(QBrush(self._COLOR))
        fnt = self._label.font()
        fnt.setPointSizeF(5.0)
        self._label.setFont(fnt)
        self._label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)
        self._sync_chrome()

    def _actor_pos(self, name: str):
        """(x, y) de l'acteur nommé, ou None. Passé aux helpers d'ancrage du
        modèle qui, eux, ne connaissent pas la scène."""
        for a in getattr(self._scene, "actors", []):
            if a.name == name:
                return (a.x, a.y)
        return None

    def _origin(self) -> tuple[int, int, bool]:
        """Position ÉCRAN de l'origine + « l'ancre du root est-elle résolue ? ».
        Délègue au modèle : la position d'un élément se lit en remontant à son
        root (offsets cumulés + socle du frame), plus seulement de son ancrage
        propre — un enfant est pixel-relatif à son parent."""
        return self._layout.absolute_origin(self._region, self._actor_pos)

    def _fill_brush(self):
        """Pinceau d'aperçu du fond d'un conteneur, ou None (autre type / sans
        fond). Une couleur = une entrée de PALETTE, résolue en RGB PLEIN pour
        l'écran — exactement la teinte que le hardware affichera, jamais une
        teinte d'édition translucide qui mentirait sur le rendu compilé ; un
        fond d'asset (nine-slice / background) est hachuré en attendant son
        vrai rendu."""
        from core.models.ui_region import FILL_NONE, FILL_COLOR, KIND_CONTAINER
        el = self._region
        if getattr(el, "kind", "") != KIND_CONTAINER:
            return None
        fk = getattr(el, "fill_kind", FILL_NONE)
        if fk == FILL_NONE:
            return None
        if fk == FILL_COLOR and self._project is not None:
            bank = self._project.get_palette(getattr(el, "fill_palette", ""))
            idx = int(getattr(el, "fill_index", 0) or 0)
            if bank and 0 <= idx < len(bank.colors):
                from core.models.gba_color import bgr555_to_rgb888
                r, g, b = bgr555_to_rgb888(bank.colors[idx])
                return QBrush(QColor(r, g, b))
        # Fond d'asset (ou couleur non résolue) : hachures dans la couleur du type.
        return QBrush(QColor(self._COLOR), Qt.BrushStyle.BDiagPattern)

    def _load_nine_slice(self):
        """(QPixmap, BackgroundAsset) du cadre référencé, ou (None, bg/None).

        Le cadre EST un fond d'interface (`kind == "ui"`) : il porte son image
        et ses marges de découpe, il n'y a rien à déréférencer entre les deux."""
        get_bg = getattr(self._project, "get_background", None)
        if not get_bg:
            return None, None
        bg = get_bg(getattr(self._region, "fill_asset", ""))
        if bg is None or not getattr(bg, "asset", ""):
            return None, bg
        path = self._project.background_images_dir / bg.asset
        return QPixmap(str(path)), bg

    def _load_image_frame(self):
        """QPixmap de la 1re frame de l'état déclaré par un `UIImage`, ou None.

        La PREMIÈRE frame et pas une animation vivante : le canvas est un plan,
        pas un aperçu de jeu. Faire tourner les images ferait bouger le décor
        sous la souris pendant qu'on le compose — et masquerait le seul défaut
        qu'on cherche ici, un cadrage faux.

        Même chaîne que les acteurs (`compose_frame_image`), pour que ce que
        montre le canvas soit ce que le build assemblera : une seconde façon de
        composer une frame divergerait au premier flip."""
        el = self._region
        name = getattr(el, "sprite_name", "") or ""
        if not (self._project and name):
            return None
        sprite = self._project.get_sprite(name)
        if sprite is None or not getattr(sprite, "asset", ""):
            return None
        states = list(getattr(sprite, "states", []) or [])
        if not states:
            return None
        st = states[el.state_index(sprite)]
        # Direction 0 (omni) si elle existe, sinon la première déclarée — la
        # même règle de repli que la boucle d'animation du runtime.
        dirs = list(getattr(st, "directions", []) or [])
        if not dirs:
            return None
        d = next((x for x in dirs if getattr(x, "dir", 0) == 0), dirs[0])
        frames = list(getattr(d, "frames", []) or [])
        if not frames:
            return None
        ap = self._project.asset_abs(sprite.asset)
        if ap is None or not ap.exists():
            return None
        try:
            img = compose_frame_image(ap, frames[0], sprite.frame_w, sprite.frame_h)
            if img.width <= 0 or img.height <= 0:
                return None
            data = bytes(img.tobytes("raw", "RGBA"))
            qi = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
            return QPixmap.fromImage(qi)
        except Exception:
            return None      # un asset illisible se dessine en hachures, pas en trace

    def _load_bg_fill(self):
        """QPixmap du background référencé par un fond `background`, ou None."""
        get_bg = getattr(self._project, "get_background", None)
        if not get_bg:
            return None
        bg = get_bg(getattr(self._region, "fill_asset", ""))
        if bg is None or not getattr(bg, "asset", ""):
            return None
        return QPixmap(str(self._project.background_images_dir / bg.asset))

    def _paint_background(self, painter):
        """Peint le background à taille NATURELLE, calé en haut-gauche, ROGNÉ en
        bas/à droite si la zone est plus petite que l'image (pas d'étirement —
        c'est une fenêtre sur le fond)."""
        if self._bg_pixmap is None:
            return
        pix = self._bg_pixmap
        r = self.rect()
        w = min(int(r.width()), pix.width())
        h = min(int(r.height()), pix.height())
        if w <= 0 or h <= 0:
            return
        painter.save()
        painter.drawPixmap(QRectF(r.left(), r.top(), w, h), pix, QRectF(0, 0, w, h))
        painter.restore()

    def _paint_image(self, painter):
        """Peint la frame du sprite, à taille NATURELLE et jamais étirée.

        Le rectangle vaut déjà la frame (`UIImage.sync_size_from`), donc les
        deux coïncident dans le cas normal ; dessiner à taille naturelle plutôt
        qu'au rectangle est ce qui rend VISIBLE le cas anormal — un sprite
        échangé hors de l'éditeur, dont la frame a changé de taille."""
        if self._img_pixmap is None:
            return
        pix, r = self._img_pixmap, self.rect()
        painter.save()
        if self._tile_fill:
            # Fond de conteneur : la frame se RÉPÈTE, exactement comme le
            # runtime pose un OBJ par case (cf. `sprite_grid`). La dernière
            # colonne/rangée déborde plutôt que d'être rognée — le matériel ne
            # sait pas couper un sprite, et l'aperçu doit le montrer plutôt que
            # de laisser croire à un cadrage propre.
            fw, fh = max(1, pix.width()), max(1, pix.height())
            cols = max(1, -(-int(r.width()) // fw))
            rows = max(1, -(-int(r.height()) // fh))
            for cy in range(rows):
                for cx in range(cols):
                    painter.drawPixmap(
                        QRectF(r.left() + cx * fw, r.top() + cy * fh, fw, fh),
                        pix, QRectF(0, 0, fw, fh))
        else:
            painter.drawPixmap(QRectF(r.left(), r.top(), pix.width(), pix.height()),
                               pix, QRectF(0, 0, pix.width(), pix.height()))
        painter.restore()

    def _paint_nine_slice(self, painter):
        """Peint le cadre : chaque case via `nine_slice_rects` — coins 1:1,
        bords/centre TUILÉS pour remplir sans déformer."""
        if self._ns_pixmap is None or self._ns is None:
            return
        from core.nine_slice import nine_slice_rects
        pix, ns = self._ns_pixmap, self._ns
        r = self.rect()
        left, right, top, bottom = ns.slice_margins()
        cells = nine_slice_rects(pix.width(), pix.height(),
                                 left, right, top, bottom,
                                 int(r.width()), int(r.height()))
        painter.save()
        for c in cells:
            sx, sy, sw, sh = c["src"]
            dx, dy, dw, dh = c["dst"]
            dst = QRectF(r.left() + dx, r.top() + dy, dw, dh)
            if c["tile"]:
                painter.drawTiledPixmap(dst, pix.copy(sx, sy, sw, sh))
            else:
                painter.drawPixmap(dst, pix, QRectF(sx, sy, sw, sh))
        painter.restore()

    # ── Texte réel ───────────────────────────────────────────────
    # Aperçu des vrais glyphes dans la boîte : `text_layout` les place comme le
    # moteur, `display_text` résout balises et `$valeurs`.

    def _text_content(self) -> str:
        """Ce que cet élément AFFICHE, balisage résolu.

        Un texte authoré montre SON contenu (celui que la ROM écrira) ; une zone
        montre son `preview_text`, simple étalon d'éditeur — le script décidera.
        Les deux passent par `display_text`, sinon l'aperçu montrerait les
        crochets d'un `[speed=6]` que le joueur ne verra jamais."""
        el, p = self._region, self._project
        if p is None:
            return ""
        kind = getattr(el, "kind", "region")
        key = (getattr(el, "text_key", "") if kind == "text"
               else getattr(el, "preview_text", "")) or ""
        get_text = getattr(p, "get_text", None)
        t = get_text(key) if (key and get_text) else None
        if t is None:
            return ""
        from core.text_markup import display_text
        values = p.text_values() if hasattr(p, "text_values") else {}
        return display_text(t.content or "", values)

    def _text_font(self):
        """Police de l'élément, ou celle que la SCÈNE charge par défaut.

        Le défaut passe par `font_emit.scene_default_font` — le même calcul que
        l'émission, la réservation VRAM et le validateur. Mesurer l'aperçu avec
        une autre police que celle du build ferait mentir le débordement montré
        au canvas, qui est tout l'intérêt du `preview_text`."""
        p = self._project
        named = getattr(self._region, "font_name", "") or ""
        fonts = list(getattr(p, "fonts", []) or []) if p else []
        if named:
            return next((f for f in fonts if f.name == named), None)
        try:
            from codegen.font_emit import scene_default_font
            name = scene_default_font(p, self._scene)[1]
            return next((f for f in fonts if f.name == name), None)
        except Exception:
            # Stub de test, ou chaîne codegen indisponible.
            return fonts[0] if fonts else None

    def _composited(self) -> bool:
        """Le texte se COMPOSE-t-il (pixel) plutôt que de se poser à la tuile ?

        Délègue à `main_gen.region_is_composited` — même règle que le
        validateur (`_check_ui_text_surf_alias`) : les laisser diverger
        risquerait qu'un aperçu dise « pas de conflit » sur un cas que le
        build compose bel et bien. Seul l'offset de ferrage change ici, mais
        7 px de décalage sur un titre centré se voient."""
        from codegen.runtime_codegen.gen_text import region_is_composited
        try:
            from codegen.font_emit import scene_default_font
            default_name = scene_default_font(self._project, self._scene)[1]
        except Exception:
            default_name = ""
        return region_is_composited(self._project, self._layout, self._region, default_name)

    def _bank_colors(self):
        """Les couleurs (r,g,b) de la banque où l'encre ET le surlignement de
        cette zone s'indexent — mis en cache pour la VIE de l'item.

        La résolution (`_compute_bank_colors`) coûte ~15 ms (elle rejoue
        l'allocation de palettes de la scène) ; l'appeler à chaque repaint —
        survol, zoom, pan — étranglerait le canvas. Un item est reconstruit dès
        qu'un réglage de palette/couleur change (inspecteur `changed` →
        `_reload_ui_regions` → `set_ui_regions`), donc le cache ne survit jamais à
        ce qu'il devrait refléter."""
        cached = getattr(self, "_bank_colors_cache", _UNSET)
        if cached is not _UNSET:
            return cached
        cols = self._compute_bank_colors()
        self._bank_colors_cache = cols
        return cols

    def _compute_bank_colors(self):
        """Résout la banque, sans cache. Même vérité que l'inspecteur
        (`_ink_bank`) et le build (`region_ink_bank`, `slot_colors[bank]`) :
        conteneur si le build lie la zone, sinon banque d'UI de la scène, None si
        aucune. Enveloppé de `try` pour les stubs de test, comme `_composited`."""
        p, scene = self._project, self._scene
        if p is None or scene is None:
            return None
        off = None
        try:
            from codegen.runtime_codegen.gen_text import region_ink_bank
            resolved = region_ink_bank(p, scene, self._region)
            if resolved is not None:
                off = resolved[0]
        except Exception:
            off = None
        if off is None:      # texte libre : la banque d'UI de la scène
            slot = int(getattr(scene, "ui_pal_bank", -1))
            active = list(getattr(scene, "active_bg_palettes", []) or [])
            off = slot if 0 <= slot < len(active) else None
        if off is None:
            return None
        try:
            from codegen.palette_alloc import scene_bank_layout
            cols = scene_bank_layout(p, scene, "bg").slot_colors[off]
        except Exception:
            return None
        if not cols:
            return None
        from core.models.gba_color import bgr555_to_rgb888
        return [bgr555_to_rgb888(c) for c in cols]

    def _highlight_color(self):
        """QColor du surlignement de cette zone, ou None — l'index
        `highlight_color` dans la banque résolue (cf. `_bank_colors`)."""
        idx = int(getattr(self._region, "highlight_color", 0) or 0)
        if not idx:
            return None
        cols = self._bank_colors()
        if not cols or idx >= len(cols):
            return None
        r, g, b = cols[idx]
        return QColor(r, g, b)

    def _load_text_sheet(self, font):
        """Planche de glyphes TROUÉE, mise en cache par (chemin, empreinte).

        Cache au niveau du MODULE (cf. `_TEXT_SHEETS`). La clé porte l'empreinte
        disque, pour qu'une planche retouchée dans l'éditeur de police
        apparaisse quand même."""
        p = self._project
        if not font or not getattr(font, "asset", "") or p is None:
            return None
        path = p.asset_abs(font.asset)
        if not path or not path.exists():
            return None
        try:
            st = path.stat()
            key = (str(path), st.st_mtime_ns, st.st_size)
        except OSError:
            return None
        if key in _TEXT_SHEETS:
            return _TEXT_SHEETS[key]
        px = QPixmap(str(path))
        from ui.text_editor.glyph_paint import key_out
        sheet = None if px.isNull() else key_out(px, font.key_colors())
        if len(_TEXT_SHEETS) > 16:      # une poignée de polices suffit
            _TEXT_SHEETS.clear()
        _TEXT_SHEETS[key] = sheet
        return sheet

    @staticmethod
    def _flatten_sheet(sheet, color):
        """Planche recolorée : les pixels d'encre prennent `color`, l'alpha (la
        forme des glyphes, et les trous) est gardé. Le pendant canvas de la
        recoloration VRAM de l'encre au chargement (`text_recolor`). Mise en
        cache par (planche, couleur) — cf. `_FLAT_SHEETS`."""
        ck = (sheet.cacheKey(), (color.red(), color.green(), color.blue()))
        hit = _FLAT_SHEETS.get(ck)
        if hit is not None:
            return hit
        out = QPixmap(sheet.size())
        out.fill(Qt.GlobalColor.transparent)
        pnt = QPainter(out)
        pnt.drawPixmap(0, 0, sheet)
        # SourceIn : garde l'alpha de la planche, remplace sa couleur par l'aplat.
        pnt.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        pnt.fillRect(out.rect(), color)
        pnt.end()
        if len(_FLAT_SHEETS) > 32:
            _FLAT_SHEETS.clear()
        _FLAT_SHEETS[ck] = out
        return out

    def _paint_text(self, painter) -> bool:
        """Dessine les VRAIS glyphes dans le rectangle. Retourne True si le texte
        déborde (tronqué par le moteur au dernier glyphe qui tient).

        Pas de repli « faux texte » si la police manque : une approximation Qt
        donnerait une idée fausse de l'encombrement."""
        text = self._text_content()
        if not text:
            return False
        font = self._text_font()
        sheet = self._load_text_sheet(font)
        if sheet is None:
            return False
        # Encre APLATIE : un index 1-15 remplace toute la couleur de la police
        # par la couleur de la banque résolue (cf. `UIText.text_color`) ; l'index
        # 0 garde les teintes d'origine de la police, on ne touche donc rien.
        ink = int(getattr(self._region, "text_color", 0) or 0)
        if ink:
            cols = self._bank_colors()
            if cols and ink < len(cols):
                r, g, b = cols[ink]
                sheet = self._flatten_sheet(sheet, QColor(r, g, b))
        from core.engine_emulation.text_layout import layout_text
        r = self.rect()
        placed, over = layout_text(font, text, int(r.width()), int(r.height()),
                                   align=getattr(self._region, "align", "left"),
                                   composited=self._composited())
        if not placed:
            return over
        painter.save()
        # Pixel art : jamais d'interpolation, à aucun zoom.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Surlignement SOUS les glyphes, sur l'étendue rendue arrondie à la
        # TUILE — le moteur peint des tuiles de surface, pas des pixels libres
        # (cf. `text_surf_seed`). Bornes prises comme les siennes : la plume
        # (donc la CHASSE, pas la largeur d'encre) à droite, l'INTERLIGNE en
        # bas. Les mesurer autrement donnerait une tuile d'écart avec la ROM sur
        # une police dont les glyphes sont plus petits que leur cellule.
        hl = self._highlight_color()
        if hl is not None:
            from codegen.font_emit import glyph_advance_px, font_line_px
            line = font_line_px(font)
            x0 = min(gx for _g, gx, _gy in placed) // 8 * 8
            y0 = min(gy for _g, _gx, gy in placed) // 8 * 8
            x1 = -(-max(gx + glyph_advance_px(g, font) for g, gx, _gy in placed) // 8) * 8
            y1 = -(-(max(gy for _g, _gx, gy in placed) + line) // 8) * 8
            painter.fillRect(QRectF(r.left() + x0, r.top() + y0, x1 - x0, y1 - y0), hl)
        for g, gx, gy in placed:
            painter.drawPixmap(QRectF(r.left() + gx, r.top() + gy, g.w, g.h),
                               sheet, QRectF(g.x, g.y, g.w, g.h))
        painter.restore()
        return over

    # ── Peinture ─────────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        """Rectangle ÉLARGI d'une marge.

        Contour et poignées sont au pinceau COSMÉTIQUE (largeur 0), or Qt calcule
        sa zone à repeindre depuis `pen().widthF()` : le trait déborde de ce que
        Qt efface et le déplacement laisse des traînées. Marge en unités de
        SCÈNE, dimensionnée sur le pire cas (zoom 0.5). Fixe et non dérivée du
        zoom : Qt met `boundingRect` en cache."""
        m = 6.0
        return self.rect().adjusted(-m, -m, m, m)

    def _sync_chrome(self):
        """Visibilité et position du libellé selon l'état.

        Le NOM ne s'affiche qu'au survol ou à la sélection, sinon cinq zones
        imbriquées recouvrent le jeu (l'arbre donne déjà l'inventaire). L'icône
        de type, elle, reste toujours visible.

        Le libellé se pose AU-DESSUS du rectangle, et retombe à l'intérieur
        quand la zone touche le haut de l'écran."""
        show = self.isSelected() or self._hovered
        self._label.setVisible(show)
        y = -7.5 if self.pos().y() >= 9 else 1.0
        self._kind_icon.setPos(1, y)
        self._label.setPos(8.5, y)

    def paint(self, painter, option, widget=None):
        """Le CONTENU réel (couleur de palette PLEINE, nine-slice, background)
        — exactement ce que le build affichera, jamais une teinte d'édition ;
        sans contenu déclaré, rien n'est peint que le contour (pas de bulle de
        remplissage). Coins droits, comme le rendu compilé — le hardware n'a
        pas de rectangle arrondi."""
        r = self.rect()
        sel = self.isSelected()
        active = getattr(self.scene(), "active_item", None) is self
        path = QPainterPath()
        path.addRect(r)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.save()

        # 1. Contenu réel seulement — un conteneur SANS fond déclaré ne peint
        #    rien ici, juste son contour (étape 2 plus bas).
        painter.save()
        painter.setClipPath(path)
        self._paint_nine_slice(painter)
        self._paint_background(painter)
        self._paint_image(painter)
        if self._content_brush is not None:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(self._content_brush)
            painter.drawRect(r)
        # Le TEXTE en dernier, et sous le clip : le moteur borne le rendu au
        # rectangle (`text_clip_set`), l'aperçu doit couper au même endroit.
        overflows = self._paint_text(painter)
        painter.restore()   # lève le clip avant le contour (sinon la moitié du trait est rognée)

        # Débordement : liseré ambre en bas. Le moteur tronque au dernier glyphe
        # qui tient sans rien dire, et c'est ici qu'on peut encore agrandir.
        if overflows:
            warn = QPen(QColor(C.ACCENT_YLW))
            warn.setWidthF(2.0)
            warn.setCosmetic(True)
            painter.setPen(warn)
            painter.drawLine(QPointF(r.left(), r.bottom()),
                             QPointF(r.right(), r.bottom()))

        # 2. Contour — la COULEUR porte le type (cf. _KIND_COLORS). Un
        #    CONTENEUR est un cadre : tirets au repos. Une ancre non résolue
        #    reste en pointillés (position affichée ≠ position du jeu), et ce
        #    signal prime sur le reste.
        col = QColor("#ffffff") if (sel and active) else QColor(self._COLOR)
        col.setAlpha(255 if sel else (230 if self._hovered else 150))
        pen = QPen(col)
        pen.setWidthF(1.4)
        pen.setCosmetic(True)
        if not self._anchored:
            pen.setStyle(Qt.PenStyle.DotLine)
        elif getattr(self._region, "can_contain", False) and not sel:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawPath(path)

        # 3. Poignées — sélection seule.
        if sel:
            half = _HANDLE_HALF_PX / self._view_scale()
            painter.setPen(QPen(QColor("#ffffff"), 0))
            painter.setBrush(QBrush(self._COLOR))
            for hx, hy in self._handle_points().values():
                painter.drawRect(QRectF(hx - half, hy - half, 2 * half, 2 * half))
        painter.restore()

    # ── Poignées ─────────────────────────────────────────────────
    def _view_scale(self) -> float:
        """Facteur de zoom de la vue (m11), 1.0 s'il n'y a pas encore de vue."""
        sc = self.scene()
        views = sc.views() if sc else []
        return views[0].transform().m11() if views else 1.0

    def _handle_points(self) -> dict:
        """Centre de chaque poignée en coordonnées LOCALES.

        Rentrées d'un demi-côté vers l'INTÉRIEUR : centrées sur le bord, elles
        déborderaient du `boundingRect` et laisseraient des rémanences."""
        r = self.rect()
        d = _HANDLE_HALF_PX / self._view_scale()
        l, t, rt, b = r.left() + d, r.top() + d, r.right() - d, r.bottom() - d
        mx, my = (r.left() + r.right()) / 2, (r.top() + r.bottom()) / 2
        return {
            "nw": (l, t), "n": (mx, t), "ne": (rt, t), "e": (rt, my),
            "se": (rt, b), "s": (mx, b), "sw": (l, b), "w": (l, my),
        }

    def _handle_at(self, local_pos) -> "str | None":
        """Nom de la poignée sous `local_pos`, ou None. La tolérance est en
        pixels écran : une poignée reste attrapable même très dézoomée."""
        tol = _HANDLE_GRAB_PX / self._view_scale()
        for name, (hx, hy) in self._handle_points().items():
            if abs(local_pos.x() - hx) <= tol and abs(local_pos.y() - hy) <= tol:
                return name
        return None

    # ── Aimantation d'alignement ─────────────────────────────────
    def _snap_step(self) -> int:
        """Pas de grille de cette zone : 8 px (tuile) pour une cible BG — le
        moteur y écrit des entrées de tilemap, l'origine ne peut pas tomber
        entre deux tuiles — 1 px (libre) pour une cible OBJ composée pixel par
        pixel. Recalculé à chaque appel : `render_mode` peut changer sous
        l'édition."""
        rm = int(getattr(self._scene, "render_mode", 0) or 0)
        return 8 if self._layout.resolved_target(self._region, rm) == "bg" else 1

    def _axis_snap(self, moving_vals, is_x: bool):
        """(delta, ligne-guide) pour aimanter `moving_vals` (positions scène sur
        un axe) aux bords/centres des autres zones et au cadre écran. Le seuil
        est en pixels écran, converti via le zoom courant."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "ui_align_segments"):
            return 0.0, None
        xs, ys = sc.ui_align_segments(self)
        targets = collect_targets(xs if is_x else ys, GBA_W if is_x else GBA_H)
        thr = _ALIGN_SNAP_PX / self._view_scale()
        return _align_snap(moving_vals, targets, thr)

    def _descendant_items(self) -> list:
        """Items du canvas portant les DESCENDANTS de cet élément (tout le
        sous-arbre). Sert au suivi visuel pendant un drag de conteneur."""
        sc = self.scene()
        if sc is None or not hasattr(sc, "_ui_region_items"):
            return []
        names = {d.name for d in self._layout.descendants(self._region.name)}
        return [it for it in sc._ui_region_items
                if it is not self and it._region.name in names]

    def _move_descendants(self, dx: float, dy: float):
        if dx or dy:
            for it in self._descendant_items():
                it.moveBy(dx, dy)

    def itemChange(self, change, value):
        # Aimante la position PROPOSÉE pendant un déplacement souris (et trace
        # les guides). Uniquement en sélection simple : en groupe, Qt translate
        # tous les items du même delta, dévier celui-ci désynchroniserait le lot.
        sc = self.scene()
        single = (sc is not None and hasattr(sc, "selectable_items")
                  and len(sc.selectable_items()) == 1)
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and self._moving and single):
            nx, ny = value.x(), value.y()
            w, h = self.rect().width(), self.rect().height()
            dx, gx = self._axis_snap(candidate_lines(nx, w), True)
            dy, gy = self._axis_snap(candidate_lines(ny, h), False)
            sc.show_align_guides(gx, gy)
            nx, ny = nx + dx, ny + dy
            # Aimantation à la grille EN COURS de geste : la boîte reste figée
            # sur sa case tant que la souris n'a pas franchi la suivante, au
            # lieu de suivre le pixel puis sauter d'un coup au relâchement.
            step = self._snap_step()
            if step > 1:
                nx = (int(nx) // step) * step
                ny = (int(ny) // step) * step
            return QPointF(nx, ny)
        # Position APPLIQUÉE pendant le geste : les enfants suivent du même
        # delta. Leur modèle est relatif au parent, il n'y a donc rien à
        # committer chez eux — c'est un suivi d'écran, pas une écriture.
        # Sélection simple seulement : en groupe, Qt déplace déjà chaque item.
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and self._moving and single):
            if self._last_pos is not None:
                self._move_descendants(value.x() - self._last_pos.x(),
                                       value.y() - self._last_pos.y())
            self._last_pos = QPointF(value)
        # Le libellé passe au-dessus ou à l'intérieur selon la place disponible,
        # et le chrome change avec la sélection : les deux se resynchronisent ici.
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged):
            self._sync_chrome()
        return super().itemChange(change, value)

    # ── Interaction ──────────────────────────────────────────────
    def hoverMoveEvent(self, e):
        if not self._hovered:
            self._hovered = True
            self._sync_chrome()
            self.update()
        name = self._handle_at(e.pos()) if self.isSelected() else None
        if name:
            self.setCursor(_HANDLE_CURSORS[name])
        elif self.isSelected():
            self.setCursor(Qt.CursorShape.SizeAllCursor)   # rappel : déplaçable
        else:
            self.unsetCursor()
        super().hoverMoveEvent(e)

    def hoverLeaveEvent(self, e):
        self.unsetCursor()
        self._hovered = False
        self._sync_chrome()
        self.update()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e):
        self._press_pos = self.pos()
        # Figé AVANT le select : le bus resélectionne synchroniquement, donc
        # `isSelected()` serait déjà vrai juste après. Une poignée n'est dessinée
        # que sur une zone sélectionnée — le premier clic doit donc sélectionner,
        # et seul le geste SUIVANT sur une poignée redimensionne.
        was_selected = self.isSelected()
        from core.selection_bus import get_bus, UIRegionSelection
        get_bus().select(UIRegionSelection(self._layout, self._region))
        if (e.button() == Qt.MouseButton.LeftButton and was_selected):
            handle = self._handle_at(e.pos())
            if handle:
                self._resize_handle = handle
                self._resize_start = (QPointF(self.pos()), QRectF(self.rect()))
                e.accept()   # on ne passe PAS à Qt : sinon l'item se déplacerait
                return
        # Pas une poignée → déplacement : autoriser l'aimantation d'`itemChange`
        # et armer le suivi des descendants (delta depuis la position de départ).
        if e.button() == Qt.MouseButton.LeftButton:
            self._moving = True
            self._last_pos = QPointF(self.pos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resize_handle:
            self._drag_resize(e.scenePos())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._resize_handle:
            self._resize_handle = None
            self._resize_start = None
            self._press_pos = None
            self._commit_resize()
            sc = self.scene()
            if sc is not None and hasattr(sc, "clear_align_guides"):
                sc.clear_align_guides()
            e.accept()
            return
        super().mouseReleaseEvent(e)
        # Fin du déplacement : couper l'aimantation AVANT le snap tuile ci-dessous
        # (un setPos passerait sinon de nouveau par `itemChange`) et retirer les
        # guides.
        self._moving = False
        sc = self.scene()
        if sc is not None and hasattr(sc, "clear_align_guides"):
            sc.clear_align_guides()
        if self._press_pos is None:
            return
        start, self._press_pos = self._press_pos, None
        # Filet de sécurité : `itemChange` aimante déjà à la grille pendant le
        # geste (cf. `_snap_step`), donc ce re-snap est normalement un no-op —
        # sauf pour un setPos programmatique qui aurait contourné `_moving`.
        step = self._snap_step()
        pre = self.pos()
        nx = int(pre.x()) // step * step
        ny = int(pre.y()) // step * step
        self.setPos(nx, ny)
        # Le snap final doit aussi emporter les descendants — `_moving` est déjà
        # retombé, le suivi d'`itemChange` ne le fait plus. Sélection simple
        # seulement, comme le suivi lui-même (en groupe, chaque item gère le sien).
        if (sc is not None and hasattr(sc, "selectable_items")
                and len(sc.selectable_items()) == 1):
            self._move_descendants(nx - pre.x(), ny - pre.y())
        self._last_pos = None
        if (nx, ny) == (int(start.x()), int(start.y())):
            return
        # Un ancrage actor stocke un OFFSET : c'est lui qu'il faut réécrire,
        # pas la position absolue lue dans le canvas.
        ax, ay = self._parent_origin()
        from core.history import get_history, MoveUIRegionCmd
        get_history().push(MoveUIRegionCmd(
            self._region, self._region.x, self._region.y,
            nx - ax, ny - ay, persist_fn=self._save))

    # ── Redimensionnement ────────────────────────────────────────
    def _parent_origin(self) -> tuple[int, int]:
        """Origine ÉCRAN du PARENT (ou socle du frame si root). Sert à
        retrancher pour restocker x/y RELATIFS au parent : un enfant est
        pixel-relatif à son conteneur, un root à son socle d'ancrage."""
        return self._layout.parent_origin(self._region, self._actor_pos)

    def _drag_resize(self, scene_pos):
        """Déplace le(s) bord(s) de la poignée tirée vers la souris. Aimante à
        la grille de la cible (`_snap_step`) PENDANT le geste : le bord suivi
        reste sur sa case tant que la souris n'a pas franchi la suivante,
        `_commit_resize` ne fait plus alors qu'appliquer les bornes finales."""
        start_pos, start_rect = self._resize_start
        l = start_pos.x() + start_rect.left()
        t = start_pos.y() + start_rect.top()
        rt = start_pos.x() + start_rect.right()
        b = start_pos.y() + start_rect.bottom()
        ml, mt, mr, mb = _HANDLE_EDGES[self._resize_handle]
        if ml: l = scene_pos.x()
        if mt: t = scene_pos.y()
        if mr: rt = scene_pos.x()
        if mb: b = scene_pos.y()
        # Aimantation d'alignement sur le(s) SEUL(S) bord(s) que la poignée
        # déplace — un coin bouge un bord par axe, un milieu un seul.
        gx = gy = None
        if ml:
            dx, gx = self._axis_snap([l], True);  l += dx
        elif mr:
            dx, gx = self._axis_snap([rt], True); rt += dx
        if mt:
            dy, gy = self._axis_snap([t], False); t += dy
        elif mb:
            dy, gy = self._axis_snap([b], False); b += dy
        sc = self.scene()
        if sc is not None and hasattr(sc, "show_align_guides"):
            sc.show_align_guides(gx, gy)
        # Snap à la grille des SEULS bords tirés — les bords fixes viennent de
        # `_resize_start`, déjà sur la grille depuis le geste précédent. Les
        # quatre bords arrondissent vers l'EXTÉRIEUR de la boîte (floor à
        # gauche/haut, ceil à droite/bas) : rogner couperait du texte pour
        # faire joli, comme `_commit_resize`.
        step = self._snap_step()
        if step > 1:
            if ml: l = (int(l) // step) * step
            elif mr: rt = ((int(rt) + step - 1) // step) * step
            if mt: t = (int(t) // step) * step
            elif mb: b = ((int(b) + step - 1) // step) * step
        # Plancher de 8 px : le bord tiré s'arrête, le bord opposé ne bouge pas.
        if rt - l < 8:
            if ml: l = rt - 8
            else:  rt = l + 8
        if b - t < 8:
            if mt: t = b - 8
            else:  b = t + 8
        self.setPos(l, t)
        self.setRect(0, 0, rt - l, b - t)

    def _commit_resize(self):
        """Fige le geste : bornes, puis une seule commande d'historique. Le
        snap à la grille est déjà fait en LIVE par `_drag_resize` — ce re-snap
        est un filet de sécurité (no-op en pratique), comme dans
        `mouseReleaseEvent` pour le déplacement."""
        step = self._snap_step()
        l = int(self.pos().x())
        t = int(self.pos().y())
        rt = l + int(self.rect().width())
        b = t + int(self.rect().height())
        l = (l // step) * step
        t = (t // step) * step
        rt = ((rt + step - 1) // step) * step
        b = ((b + step - 1) // step) * step
        w = max(8, min(512, rt - l))
        h = max(8, min(512, b - t))
        self.setPos(l, t)
        self.setRect(0, 0, w, h)
        ax, ay = self._parent_origin()
        old = (self._region.x, self._region.y, self._region.w, self._region.h)
        new = (l - ax, t - ay, w, h)
        if old == new:
            return
        from core.history import get_history, ResizeUIRegionCmd
        get_history().push(ResizeUIRegionCmd(
            self._region, old, new, persist_fn=self._save))


