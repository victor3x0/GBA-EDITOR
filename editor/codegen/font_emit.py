"""codegen/font_emit.py — polices et textes émis en C.

**Police → tuiles.** Chaque glyphe est rendu dans une cellule de
`tiles_x × tiles_y` tuiles 8×8 (1 seule pour une police 8×8, le cas courant),
posées à la suite dans le charblock du layer d'UI. Un glyphe étant une tuile,
tout ce qui s'applique à une tuile s'applique au texte : `tilemap.set_palette`
le recolore, les windows le découpent, la priorité de layer le place.

**Texte → codepoints, pas glyphes.** Un texte est émis en `u16` Unicode et la
correspondance caractère → tuile est faite au runtime via la table de la police
courante. C'est ce qui rend un texte **indépendant de la police** : la même
entrée peut être rendue avec une autre police, ce dont la v0.8 aura besoin (une
traduction peut exiger un autre jeu de glyphes). Le coût est une recherche
dichotomique par caractère, à l'affichage — pas par frame.

Limite assumée : `u16` couvre le plan multilingue de base (BMP). Les émojis et
autres plans supplémentaires ne passent pas — sans objet pour une console qui
affiche des tuiles 8×8.
"""

from __future__ import annotations

from pathlib import Path

# Banque de palette BG réservée aux glyphes. Convention héritée du chemin TTE
# (`SE_PALBANK(15)`), conservée pour ne pas déplacer la contrainte existante.
FONT_PAL_BANK = 15

# Les `slot` émis sont RELATIFS (0 = première tuile du bloc alloué au texte).
# La base absolue dans le charblock est décidée par scène et posée au runtime
# par `text_set_tile_base` — cuire une base ici interdirait au texte de
# partager un charblock avec un fond (cf. ARCHITECTURE.md, « Allocation de la
# VRAM BG »).

_MAX_INK_COLORS = 15   # index 0 = transparent, restent 1..15


# ── Chasse et mode de rendu ───────────────────────────────────────
# Règle UNIQUE, partagée par l'émission C et l'aperçu de l'éditeur : si les deux
# divergeaient, l'aperçu promettrait un placement que la ROM ne tiendrait pas.

def glyph_tiles_w(g) -> int:
    return max(1, (g.w + 7) // 8)


def advances_declared(font) -> bool:
    """La police DÉCLARE-t-elle ses chasses ?

    Applique la règle d'autorité du modèle (cf. core/models/font.py) : un `.fnt`
    porte les `xadvance` de son auteur ; une planche PNG ne déclare quoi que ce
    soit que si sa couleur d'espacement a été désignée ; sans elle, la police est
    **mono**, quoi que dise le champ `advance`.

    Ce dernier point n'est pas un détail : les polices importées AVANT la règle
    portent des chasses issues de l'ancienne mesure d'encre. Les lire
    telles quelles ferait passer en proportionnel des polices que l'éditeur
    annonce comme mono — deux réponses à la même question. On dérive donc au
    point d'usage plutôt que de réparer les sidecars, ce qui soigne aussi
    l'existant sans migration."""
    if getattr(font, "source_format", "png") == "fnt":
        return True
    return getattr(font, "space_color", None) is not None


def advance_source(font) -> str:
    """QUI décide de la chasse : "fnt" | "spacing" | "mono".

    Même règle d'autorité que `advances_declared`, mais elle nomme la source au
    lieu de répondre oui/non — l'éditeur affiche d'où vient la chasse, et « 5 px »
    seul ne dit pas si c'est une décision de l'auteur ou le mono par défaut."""
    if getattr(font, "source_format", "png") == "fnt":
        return "fnt"
    return "spacing" if getattr(font, "space_color", None) is not None else "mono"


def glyph_advance_px(g, font=None) -> int:
    """Chasse effective d'un glyphe, en pixels.

    Sans `font`, la chasse stockée est prise telle quelle (appel bas niveau).
    Avec, la règle d'autorité s'applique : une police qui ne déclare rien est
    mono, sa chasse est sa largeur dessinée.

    Bornée à cette largeur : une chasse plus large trouerait la ligne, une
    chasse nulle empilerait les glyphes au même endroit."""
    tw = glyph_tiles_w(g)
    if font is not None and not advances_declared(font):
        return tw * 8
    return max(1, min(int(getattr(g, "advance", 0) or tw * 8), tw * 8))


def is_proportional(font) -> bool:
    """Le rendu proportionnel n'est retenu que s'il CHANGE quelque chose.

    Une police dont chaque chasse remplit sa cellule rend exactement pareil par
    le chemin tilemap, qui ne coûte rien par appel — on ne paie la composition
    pixel que quand elle sert. Le mode est donc déduit de la donnée, jamais
    réglé à la main."""
    if not advances_declared(font):
        return False
    return any(glyph_advance_px(g, font) != glyph_tiles_w(g) * 8
               for g in getattr(font, "glyphs", []) if g.char)


# ── Interligne et avance de secours ───────────────────────────────
# Émis DÉJÀ RÉSOLUS : le runtime les lit sans se demander quel chemin de rendu
# il suit. Sans ça, forcer la composition sur une police mono changerait son
# interligne (line_height brut au lieu de l'interligne arrondi à la tuile) —
# un déplacement de rendu invisible à la relecture du code.

def font_line_px(font) -> int:
    """Interligne effectif, en pixels."""
    if is_proportional(font):
        return int(getattr(font, "line_height", 0) or getattr(font, "cell_h", 0) or 8)
    return max(1, ((int(getattr(font, "cell_h", 0) or 8)) + 7) // 8) * 8


def font_fallback_adv_px(font) -> int:
    """Avance d'un caractère absent de la police, en pixels."""
    if is_proportional(font):
        return int(getattr(font, "cell_w", 0) or 8)
    return max(1, ((int(getattr(font, "cell_w", 0) or 8)) + 7) // 8) * 8


# ── Empreinte VRAM du texte ───────────────────────────────────────
# Doit rester d'accord avec TEXT_SURF_W/H de runtime/gba_engine.h : c'est la
# surface que le chemin de composition réserve dans le charblock.
TEXT_SURF_W, TEXT_SURF_H = 30, 8
TEXT_SURF_TILES = TEXT_SURF_W * TEXT_SURF_H


def glyph_seq(g) -> tuple:
    """Séquence de codepoints d'un glyphe — plusieurs pour une ligature.
    Hors BMP écarté, comme pour les textes : la table runtime est en u16."""
    return tuple(ord(c) for c in getattr(g, "char", "") if ord(c) < 0x10000)


def seq_displayable(seq, codepoints) -> bool:
    """Ce glyphe peut-il servir à une scène qui affiche `codepoints` ?

    `codepoints=None` = ensemble inconnu, donc tout est retenu. Une ligature
    n'est retenue que si TOUS ses codepoints sont affichables — elle n'est pas
    atteignable autrement. Règle écrite une fois : le compteur de tuiles et
    l'émetteur du sous-ensemble doivent retenir exactement les mêmes glyphes,
    sinon la place réservée et la copie ne coïncident plus."""
    return codepoints is None or all(c in codepoints for c in seq)


def effective_glyphs(font) -> list:
    """Glyphes RÉELLEMENT encodés : un par séquence de codepoints, le premier
    de la planche gagnant.

    Une planche découpée à la grille déclare toutes ses cases vides sur le même
    caractère — 130 des 224 du démo valent « espace ». Le runtime n'en atteint
    jamais qu'un (`text_find` prend la première correspondance du groupe), les
    autres sont de la VRAM payée pour rien.

    Règle UNIQUE, partagée par l'encodeur et par tout ce qui compte des tuiles :
    les laisser diverger, c'est réserver une place que l'encodeur n'occupe pas
    (ou l'inverse, ce qui écrase le décor)."""
    seen: set = set()
    out: list = []
    for g in getattr(font, "glyphs", []):
        if not g.char:
            continue
        key = glyph_seq(g)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(g)
    return out


def subset_glyphs(font, codepoints=None) -> list:
    """Glyphes chargés en VRAM pour une scène affichant `codepoints`."""
    return [g for g in effective_glyphs(font)
            if seq_displayable(glyph_seq(g), codepoints)]


def mono_vram_tiles(font, codepoints=None) -> int:
    """Tuiles de glyphes à charger en VRAM pour le chemin tilemap.

    `codepoints=None` = la police entière (ensemble d'affichage inconnu)."""
    return sum(glyph_tiles_w(g) * max(1, (g.h + 7) // 8)
               for g in subset_glyphs(font, codepoints))


def render_composited(font) -> bool:
    """Le texte est-il COMPOSÉ pixel à pixel dans une surface, plutôt que posé
    par le tilemap ?

    DEUX raisons de composer, et la seconde n'a rien à voir avec la typographie :

    1. Le rendu **proportionnel** l'exige — une tuile se pose à 8 px près, le
       tilemap ne sait pas placer un glyphe à x=13.

    2. La police **ne tient pas** en VRAM. Composer ne charge AUCUN glyphe (ils
       restent en ROM et servent de source) : le coût devient la surface, donc
       indépendant de la taille de la police — 2000 glyphes coûtent autant que
       60. C'est ce qui rend une police riche possible dans 512 tuiles.

    Le seuil est la surface elle-même : le moins cher des deux gagne. En
    dessous, le chemin tilemap, qui ne coûte rien par appel."""
    if is_proportional(font):
        return True
    return mono_vram_tiles(font) > TEXT_SURF_TILES


def font_vram_tiles(font, codepoints=None) -> int:
    """Tuiles que cette police occupe en VRAM une fois chargée.

    Une police COMPOSÉE ne charge aucun glyphe : son coût est la surface, que
    le sous-ensemble ne change donc pas. Le chemin tilemap, lui, ne charge que
    ce que la scène peut afficher."""
    return (TEXT_SURF_TILES if render_composited(font)
            else mono_vram_tiles(font, codepoints))


def text_vram_tiles(fonts, codepoints=None) -> int:
    """Réservation à faire pour le texte dans le charblock du layer d'UI.

    Le MAXIMUM sur toutes les polices du projet, pas la police initiale :
    `text.set_font()` peut en charger une autre à tout moment, et la place doit
    déjà être là — trop petite, elle écraserait le voisin en silence."""
    return max((font_vram_tiles(f, codepoints) for f in fonts), default=0)


# ── Contrat avec l'allocateur (codegen/vram_alloc) ────────────────
# `scene_layout()` réclame un nombre de tuiles à réserver au texte, calculé PAR
# SCÈNE (`scene_font_names`) à partir de deux sources : ce que la mise en page
# DÉCLARE (`UIRegion.font_name`) et ce que les scripts de la scène CHARGENT
# (`text.set_font("…")`, repéré par domaine).
#
# La règle de sûreté est asymétrique : réserver trop coûte des tuiles au décor,
# réserver trop peu fait écrire le texte DANS le décor, sans un signe avant
# l'exécution. Tout ce qui n'est pas établi retombe donc sur le projet entier
# (police choisie au runtime, script illisible, luaparser absent). D'où le
# `set | None` : `None` veut dire « je ne sais pas », jamais « rien ».

def scene_text_tiles(fonts, names: set[str] | None = None,
                     codepoints: set | None = None) -> int:
    """Réservation pour UNE scène, restreinte aux polices `names`.

    `names=None` = ensemble indécidable → repli sur tout le projet. Ne jamais
    faire rendre 0 à un ensemble vide *déduit* : « aucune police déclarée » et
    « aucune police possible » sont deux choses différentes."""
    if names is None:
        return text_vram_tiles(fonts, codepoints)
    return text_vram_tiles([f for f in fonts if getattr(f, "name", "") in names],
                           codepoints)


def scene_default_font(p, scene) -> tuple[int, str]:
    """(index dans `project_fonts`, nom) de la police que `scene_init` charge.

    POINT UNIQUE — l'émission (`text_set_font(i)`), la réservation VRAM, les
    sous-ensembles de glyphes, le validateur de débordement et l'aperçu de
    l'éditeur lisent tous ceci. Ils divergeaient déjà une fois dans ce module
    (cf. `scene_text_reservation`) : une scène qui réserve pour une police et en
    charge une autre écrit son texte DANS le décor, sans erreur avant
    l'exécution.

    Deux replis vers la première police encodable, et ils veulent dire deux
    choses différentes :
    - `Scene.font_name` vide — l'auteur n'a pas choisi, c'est le comportement
      historique et il est légitime ;
    - nom introuvable ou police non encodable — l'auteur a choisi et se trompe.
      Le rendu ne peut pas tomber pour autant (le moteur doit bien charger
      QUELQUE chose), donc c'est `validator._check_scene_font` qui le dit.

    (-1, "") quand le projet n'a aucune police encodable : `scene_init` n'émet
    alors aucun `text_set_font`, et un projet sans texte compile toujours."""
    from codegen.runtime_codegen.main_gen import project_fonts
    fonts = project_fonts(p)
    if not fonts:
        return -1, ""
    want = getattr(scene, "font_name", "") or ""
    for i, f in enumerate(fonts):
        if f.name == want:
            return i, f.name
    return 0, fonts[0].name


def layout_font_names(layout, default_font: str = "") -> set[str]:
    """Polices DÉCLARÉES par une mise en page.

    `UILayout.font_names()` ne rend que les polices explicitement nommées ; une
    région qui hérite de la scène est complétée ici, ce module étant le premier
    à connaître le défaut. Réponse partielle — cf. le commentaire ci-dessus."""
    names = set(layout.font_names()) if layout is not None else set()
    if default_font and (layout is None or
                         any(not r.font_name for r in layout.slots)):
        names.add(default_font)
    return names


def scene_codepoints(p, scene) -> "set | None":
    """Codepoints qu'une scène peut afficher, ou None si c'est indécidable.

    Décidable parce qu'une clé de texte est TOUJOURS littérale (le checker le
    garantit, `DOMAIN_TEXT`) : on lit les textes que les scripts de la scène
    citent, on résout leur balisage, on prend les caractères. Un littéral passé
    à `text.draw` est déjà une entrée anonyme et suit le même chemin.

    DEUX sources, exactement comme `scene_font_names` : les scripts ET les
    textes AUTHORÉS de la mise en page, que `_gen_ui_texts` écrit à l'init sans
    qu'aucune ligne de script les cite. Les oublier ne fait pas tomber le texte
    d'un bloc — les glyphes absents du sous-ensemble sont sautés un à un
    (`text_glyph_slot` rend -1), et la zone rend un texte troué.

    Les chiffres sont ajoutés d'office : une valeur interpolée (`$score`) ne
    montre son écriture qu'en jeu. Les constantes, elles, sont cuites au build,
    donc déjà dans le texte résolu.

    Rend None dès qu'un script échappe à l'analyse — même règle et même raison
    que `scene_font_names`."""
    if not hasattr(p, "scene_scripts") or not hasattr(p, "build_texts"):
        return None
    from core.text_markup import parse, resolve
    from scripting.api import DOMAIN_TEXT, anon_text_key

    paths, opaque = p.scene_scripts(scene)
    if opaque:
        return None
    by_key = {t.key: t for t in p.build_texts()}
    consts = {c.name: c.value for c in getattr(p, "constants", [])}

    cited: set = set()
    for path in paths:
        names, dynamic = _script_text_keys(path)
        if dynamic:
            return None
        cited |= names

    out: set = set(ord(c) for c in "0123456789")
    for name in cited:
        # Une chaîne résout vers une entrée de la table, sinon c'est un littéral
        # — lequel a sa propre entrée, sous une clé dérivée de son contenu.
        t = by_key.get(name) or by_key.get(anon_text_key(name))
        if t is None:
            return None      # entrée introuvable : on ne parie pas
        out |= set(ord(c) for c in resolve(parse(t.content or ""), consts))
    for t in layout_texts(p, scene):
        out |= set(ord(c) for c in resolve(parse(t.content or ""), consts))
    return out


def layout_texts(p, scene) -> list:
    """Entrées de la table écrites par la mise en page d'une scène, à l'init.

    Le même parcours que `_gen_ui_texts` côté émission : un slot de type texte
    portant une clé RÉSOLUE. Une clé introuvable n'est pas une inconnue mais un
    non-événement — l'émetteur la signale et n'écrit rien —, d'où l'omission
    plutôt qu'un `None` qui ferait charger la police entière."""
    from core.models.ui_region import KIND_TEXT
    if not hasattr(p, "build_texts"):
        return []
    lay = p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None
    if lay is None:
        return []
    by_key = {t.key: t for t in p.build_texts()}
    out = []
    for el in lay.slots:
        if getattr(el, "kind", "") != KIND_TEXT:
            continue
        t = by_key.get(getattr(el, "text_key", "") or "")
        if t is not None:
            out.append(t)
    return out


def _script_text_keys(path) -> tuple[set, bool]:
    """({textes cités}, indécidable ?) pour UN script — même mémo que les polices."""
    from scripting.api import DOMAIN_TEXT
    return _script_domain_args(path, DOMAIN_TEXT)


def build_font_subset(e: dict, codepoints: "set | None") -> "dict | None":
    """Sous-ensemble à charger pour une police ENCODÉE (cf. encode_font).

    Rend {slot, load} : `slot` est indexé par glyphe encodé (0xFFFF = pas
    chargé), `load` liste les tuiles ROM dans l'ordre où elles atterrissent en
    VRAM. None quand il n'y a rien à restreindre — police composée (elle ne
    charge aucun glyphe) ou ensemble d'affichage inconnu."""
    if codepoints is None or e.get("composited"):
        return None
    seq, off, ln = e["seq"], e["seq_off"], e["seq_len"]
    slots, gw, gh = e["slots"], e["gw"], e["gh"]
    out_slot = [0xFFFF] * len(slots)
    load: list[int] = []
    for gi in range(len(slots)):
        s = seq[off[gi]: off[gi] + ln[gi]]
        if not seq_displayable(s, codepoints):
            continue
        out_slot[gi] = len(load)
        load += [slots[gi] + t for t in range(gw[gi] * gh[gi])]
    return {"slot": out_slot, "load": load}


def scene_font_names(p, scene, default_font: str = "") -> "set | None":
    """Polices qu'une scène peut avoir en VRAM, ou None si c'est indécidable.

    Trois sources :
    - la police par défaut, TOUJOURS — `scene_init` émet `text_set_font(0)`,
      donc elle est chargée même dans une scène sans une ligne de texte ;
    - les polices nommées par les zones de la mise en page ;
    - celles que chargent les scripts de la scène (`text.set_font`), repérées
      par DOMAINE — une zone n'a pas besoin de les nommer pour qu'elles
      arrivent en VRAM.

    Rend None dès qu'un script choisit sa police au runtime ou n'est pas
    analysable : mieux vaut réserver pour tout le projet que trop peu."""
    names = layout_font_names(
        p.scene_ui_layout(scene) if hasattr(p, "scene_ui_layout") else None,
        default_font)
    if default_font:
        names.add(default_font)
    if not hasattr(p, "scene_scripts"):
        return None
    paths, opaque = p.scene_scripts(scene)
    if opaque:
        return None            # script introuvable ou C natif : on ne sait pas
    for path in paths:
        cited, dynamic = _script_font_names(path)
        if dynamic:
            return None
        names |= cited
    return names


# Les scripts des prefabs reviennent dans CHAQUE scène (spawnables de partout)
# et le calcul tourne deux fois, placement et garde-fou de budget : sans mémo,
# vingt scènes reparsent vingt fois les mêmes fichiers. Clé sur l'empreinte
# disque, pour qu'un script réécrit ne rende pas une réponse périmée.
_FONT_SCAN_CACHE: dict = {}


def clear_font_scan_cache() -> None:
    """Vidé en tête de build. L'empreinte disque de la clé laisse une fenêtre :
    un script réécrit à taille identique dans le même tick d'horloge rendrait
    une réponse périmée, donc une réservation trop PETITE. Un cache qui ne vit
    qu'un build ferme la question."""
    _FONT_SCAN_CACHE.clear()


def _script_domain_args(path, domain: str) -> tuple[set, bool]:
    """({noms cités dans ce domaine}, indécidable ?) pour UN script.

    Mémoïsé par (fichier, domaine) — cf. `_FONT_SCAN_CACHE`."""
    from scripting.refactor import domain_args_in_text
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size, domain)
    except OSError:
        return set(), True
    hit = _FONT_SCAN_CACHE.get(key)
    if hit is None:
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            return set(), True
        hit = domain_args_in_text(src, domain)
        _FONT_SCAN_CACHE[key] = hit
    return hit


def _script_font_names(path) -> tuple[set, bool]:
    from scripting.api import DOMAIN_FONT
    return _script_domain_args(path, DOMAIN_FONT)


def _bgr555(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return ((r >> 3) & 31) | (((g >> 3) & 31) << 5) | (((b >> 3) & 31) << 10)


def _tile_words(idx: list[int]) -> list[int]:
    """64 index 4bpp (row-major) → 8 mots u32, format tuile GBA."""
    return [sum((idx[r * 8 + i] & 0xF) << (4 * i) for i in range(8)) for r in range(8)]


def encode_font(font, png_path: Path) -> dict:
    """Encode une police en tuiles 4bpp + table de correspondance.

    Retourne {tiles, n_tiles, codepoints, slots, palette, tiles_x, tiles_y,
    warning}. `codepoints` est TRIÉ (le runtime fait une dichotomie dessus) et
    `slots` donne, pour chaque codepoint, l'index de sa première tuile."""
    import numpy as np
    from PIL import Image

    img = Image.open(png_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]

    cw, ch = max(1, font.cell_w), max(1, font.cell_h)
    tiles_x, tiles_y = (cw + 7) // 8, (ch + 7) // 8

    # ── Palette : les couleurs d'encre les plus fréquentes ────────
    # Le vide vient du canal alpha ET des couleurs-clés de la police (fond,
    # espacement). Sans elles, une planche opaque — le cas d'une police reprise
    # de GB Studio — donnerait des glyphes en pavés pleins : tout serait encre.
    ink = alpha > 0
    keys = font.key_colors() if hasattr(font, "key_colors") else []
    for k in keys:
        ink &= ~np.all(rgb == np.array(k, dtype=rgb.dtype), axis=2)
    warning = None
    if ink.any():
        flat = rgb[ink].reshape(-1, 3)
        colors, counts = np.unique(flat, axis=0, return_counts=True)
        order = np.argsort(-counts)
        kept = [tuple(int(v) for v in colors[i]) for i in order[:_MAX_INK_COLORS]]
        if len(colors) > _MAX_INK_COLORS:
            warning = (f"Police « {font.name} » : {len(colors)} couleurs, "
                       f"réduites aux {_MAX_INK_COLORS} plus fréquentes.")
    else:
        kept = []
        warning = (f"Police « {font.name} » : les couleurs transparentes couvrent "
                   f"toute la planche — repique-les dans l'écran Police."
                   if keys else
                   f"Police « {font.name} » : planche entièrement vide.")

    # index 0 = transparent, 1..15 = encre
    palette = [0] + [_bgr555(c) for c in kept]
    palette += [0] * (16 - len(palette))
    lut = {c: i + 1 for i, c in enumerate(kept)}

    def _index_of(px, is_ink) -> int:
        if not is_ink:
            return 0
        c = tuple(int(v) for v in px)
        hit = lut.get(c)
        if hit is not None:
            return hit
        # Couleur écartée : on prend la plus proche des retenues (distance
        # euclidienne, comme le reste du pipeline palette).
        if not kept:
            return 0
        best = min(range(len(kept)),
                   key=lambda i: sum((kept[i][k] - c[k]) ** 2 for k in range(3)))
        return best + 1

    # ── Glyphes → tuiles ─────────────────────────────────────────
    # Chaque glyphe porte SA taille (rect du modèle) : une planche 8×8 peut
    # contenir une case fusionnée 16×16 ou un pictogramme large. La cellule
    # globale cw/ch ne sert plus que de valeur par défaut (interligne, avance
    # d'un caractère absent).
    tiles: list[int] = []
    entries: list[dict] = []
    h_img, w_img = ink.shape
    # Un glyphe par SÉQUENCE de codepoints (cf. `effective_glyphs`) : encoder
    # les 130 cases vides d'une planche de 224, c'est payer 58 % de sa VRAM
    # pour des tuiles que rien n'atteint.
    #
    # Le premier rencontré gagne, comme `text_find` au runtime qui prend la
    # première correspondance du groupe (le tri ci-dessous est stable, donc
    # l'ordre de la planche départage). Dédupliquer ne change aucun rendu.
    for g in effective_glyphs(font):
        gtx = max(1, (g.w + 7) // 8)
        gty = max(1, (g.h + 7) // 8)
        # Cellule vierge, puis dépôt du bitmap du glyphe à son offset. Le
        # BMFont `xoffset`/`yoffset` positionne le dessin dans la cellule ;
        # une planche régulière a simplement des offsets nuls.
        cell = [[0] * (gtx * 8) for _ in range(gty * 8)]
        for yy in range(g.h):
            sy = g.y + yy
            dy = yy + g.oy
            if sy >= h_img or dy < 0 or dy >= gty * 8:
                continue
            for xx in range(g.w):
                sx = g.x + xx
                dx = xx + g.ox
                if sx >= w_img or dx < 0 or dx >= gtx * 8:
                    continue
                cell[dy][dx] = _index_of(rgb[sy, sx], ink[sy, sx])

        slot = len(tiles) // 8
        for ty in range(gty):
            for tx in range(gtx):
                block = [cell[ty * 8 + r][tx * 8 + c] for r in range(8) for c in range(8)]
                tiles += _tile_words(block)
        # Séquence complète de codepoints : un glyphe peut représenter
        # plusieurs caractères (ligature). Hors BMP écarté, comme pour les
        # textes — la table runtime est en u16.
        seq = [ord(c) for c in g.char if ord(c) < 0x10000]
        if not seq:
            continue
        entries.append({"seq": seq, "slot": slot, "gw": gtx, "gh": gty,
                        "adv": glyph_advance_px(g, font)})

    # Tri : 1er codepoint croissant (dichotomie runtime), puis séquence la
    # PLUS LONGUE d'abord. Le runtime prend la première correspondance
    # complète du groupe : elle est donc automatiquement la plus longue,
    # sans comparer les candidats entre eux.
    entries.sort(key=lambda e: (e["seq"][0], -len(e["seq"])))

    codepoints = [e["seq"][0] for e in entries]
    slots      = [e["slot"] for e in entries]
    gw         = [e["gw"] for e in entries]
    gh         = [e["gh"] for e in entries]
    adv        = [e["adv"] for e in entries]
    composited = int(render_composited(font))
    seq_flat: list[int] = []
    seq_off:  list[int] = []
    seq_len:  list[int] = []
    for e in entries:
        seq_off.append(len(seq_flat))
        seq_len.append(len(e["seq"]))
        seq_flat += e["seq"]

    return {"tiles": tiles, "n_tiles": len(tiles) // 8,
            "codepoints": codepoints, "slots": slots, "palette": palette,
            "seq": seq_flat, "seq_off": seq_off, "seq_len": seq_len,
            "gw": gw, "gh": gh, "adv": adv, "composited": composited,
            "cell_w": font_fallback_adv_px(font), "line_h": font_line_px(font),
            "tiles_x": tiles_x, "tiles_y": tiles_y, "warning": warning}


# ── Émission C ────────────────────────────────────────────────────

def _c_ident(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name).upper()


def emit_fonts_c(encoded: list[tuple[str, dict]]) -> list[str]:
    """`encoded` = [(nom de police, résultat d'encode_font)] → lignes C.

    Émet un `FontInfo` par police et la table `g_fonts` que `text_set_font()`
    indexe. Une police vide donne quand même une entrée : mieux vaut un texte
    invisible qu'un projet qui ne linke pas."""
    L: list[str] = ["/* ── Polices ─────────────────────────────────────── */"]
    for name, e in encoded:
        sym = _c_ident(name)
        L.append(f"static const unsigned int g_font_{sym}_tiles[{max(1, len(e['tiles']))}] "
                 "__attribute__((aligned(4))) = {"
                 + (",".join(f"0x{w:08X}" for w in e["tiles"]) or "0") + "};")
        L.append(f"static const unsigned short g_font_{sym}_pal[16] = {{"
                 + ",".join(f"0x{w:04X}" for w in e["palette"]) + "};")
        L.append(f"static const unsigned short g_font_{sym}_cp[{max(1, len(e['codepoints']))}] = {{"
                 + (",".join(str(c) for c in e["codepoints"]) or "0") + "};")
        L.append(f"static const unsigned short g_font_{sym}_slot[{max(1, len(e['slots']))}] = {{"
                 + (",".join(str(s) for s in e["slots"]) or "0") + "};")
        # Séquences de codepoints (ligatures) + taille de chaque glyphe en
        # tuiles : c'est ce qui permet « ... » d'un bloc et une case 16×16
        # dans une planche 8×8.
        L.append(f"static const unsigned short g_font_{sym}_seq[{max(1, len(e['seq']))}] = {{"
                 + (",".join(str(c) for c in e["seq"]) or "0") + "};")
        L.append(f"static const unsigned short g_font_{sym}_soff[{max(1, len(e['seq_off']))}] = {{"
                 + (",".join(str(c) for c in e["seq_off"]) or "0") + "};")
        L.append(f"static const unsigned char g_font_{sym}_slen[{max(1, len(e['seq_len']))}] = {{"
                 + (",".join(str(c) for c in e["seq_len"]) or "0") + "};")
        L.append(f"static const unsigned char g_font_{sym}_gw[{max(1, len(e['gw']))}] = {{"
                 + (",".join(str(c) for c in e["gw"]) or "1") + "};")
        L.append(f"static const unsigned char g_font_{sym}_gh[{max(1, len(e['gh']))}] = {{"
                 + (",".join(str(c) for c in e["gh"]) or "1") + "};")
        # Chasses en PIXELS : ce que le chemin proportionnel avance après chaque
        # glyphe. Le chemin mono ne les lit pas.
        L.append(f"static const unsigned char g_font_{sym}_adv[{max(1, len(e['adv']))}] = {{"
                 + (",".join(str(c) for c in e["adv"]) or "8") + "};")
    L.append("")
    L.append(f"const FontInfo g_fonts[{max(1, len(encoded))}] = {{")
    if encoded:
        for name, e in encoded:
            sym = _c_ident(name)
            L.append(f"    {{ g_font_{sym}_tiles, {e['n_tiles']}, g_font_{sym}_pal, "
                     f"g_font_{sym}_cp, g_font_{sym}_slot, "
                     f"g_font_{sym}_seq, g_font_{sym}_soff, g_font_{sym}_slen, "
                     f"g_font_{sym}_gw, g_font_{sym}_gh, {len(e['codepoints'])}, "
                     f"{e['tiles_x']}, {e['tiles_y']}, "
                     f"g_font_{sym}_adv, {e['cell_w']}, {e['line_h']}, "
                     f"{e['composited']} }},")
    else:
        L.append("    { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 8, 8, 0 },")
    L.append("};")
    # `g_fonts` étant générée, le moteur ne peut borner `text_set_font` sans ce
    # compte — et un index hors table lirait un pointeur de tuiles au hasard.
    L.append(f"const int g_font_count = {max(1, len(encoded))};")
    L.append("")
    return L


def emit_ui_regions_c(regions: list, font_names: list, emit=None,
                      obj_place: dict | None = None,
                      actor_index: dict | None = None,
                      bg_fill: dict | None = None) -> list[str]:
    """Table des emplacements de texte — `regions` est [(UILayout, UIText)]
    dans l'ordre de `Project.all_regions()`, qui fait l'index.

    Contenu AUTHORÉ et contenu écrit par un script partagent la même entrée :
    ce n'était déjà que l'écrivain qui différait (`scene_init` pour l'un, le Lua
    pour l'autre, cf. `_gen_ui_texts`), et c'est ce constat qui a fait fusionner
    les deux types côté modèle.

    Coordonnées émises **déjà alignées** pour une cible BG : le moteur y écrit
    des entrées de tilemap, une origine entre deux tuiles n'existe pas.

    La police est résolue en index (255 = « garder la police courante »), pour
    que le runtime n'ait aucun nom à chercher."""
    from core.models.ui_region import TARGET_OBJ, ALIGNS, ANCHORS

    L: list[str] = ["/* ── Slots de texte (UILayout) ─────────────────── */"]
    rows: list[str] = []
    for _lay, r in regions:
        # Cible et ancrage EFFECTIFS (hérités du root) : une zone imbriquée sous
        # un panel n'a plus d'ancrage propre.
        target_obj = (_lay.resolved_target(r) == TARGET_OBJ)
        eff_anchor, eff_actor = _lay.effective_anchor(r)
        x, y, w, h = r.x, r.y, r.w, r.h
        if not target_obj:
            # Position ÉCRAN absolue : x/y d'un enfant sont RELATIFS à son
            # parent, mais le runtime lit des cases écran. Pour un root, la
            # somme se réduit à x/y — comportement d'avant inchangé.
            x, y, _res = _lay.absolute_origin(r, None)
            # Copie alignée — le modèle de l'auteur n'est pas modifié.
            x -= x % 8
            y -= y % 8
            w = max(8, ((w + 7) // 8) * 8)
            h = max(8, ((h + 7) // 8) * 8)
        font_idx = font_names.index(r.font_name) if r.font_name in font_names else 255
        pl = (obj_place or {}).get(r.name) if target_obj else None
        ai = (actor_index or {}).get(r.name, -1)
        alloc = (f"{ai}, {pl['oam_rel']}, {pl['oam']}, {pl['tile_rel']}, "
                 f"{sum(c // 8 for c in pl['cols'])}, {pl['rows']}, {pl['anim']}, "
                 f"0, {FONT_PAL_BANK}"
                 if pl else "-1, 0, 0, 0, 0, 0, 0, 0, 0")
        bgf = (bg_fill or {}).get(r.name, -1)
        # En commentaire : d'où vient le contenu. La table seule ne le dit pas,
        # et c'est la première question en relisant le C.
        origin = "authoré" if getattr(r, "text_key", "") else "écrit par script"
        rows.append(
            f"    {{ {x}, {y}, {w}, {h}, {ALIGNS.index(r.align)}, "
            f"{font_idx}, {1 if target_obj else 0}, {ANCHORS.index(eff_anchor)}, "
            f"{alloc}, {bgf}, {int(getattr(r, 'text_color', 0) or 0) & 0xF} }},"
            f"  /* {r.name} — {origin} */"
        )
        if target_obj and emit and pl:
            extra = (f" (dont {pl['anim']} glyphe(s) animé(s) réservé(s))"
                     if pl["anim"] else "")
            emit("log_line",
                 f"[text] '{r.name}' en sprites : {pl['oam']} OAM, "
                 f"{pl['tiles']} tuiles OBJ{extra}")
        if target_obj and emit and ai < 0 and eff_anchor == "actor":
            # Sans acteur résolu, la bande se pose à l'origine de l'écran — ce
            # qui ressemble à un bug de placement plutôt qu'à une référence
            # cassée. Le dire ici évite la chasse.
            emit("log_line",
                 f"[warn] texte '{r.name}' : ancré sur l'actor "
                 f"'{eff_actor or '(aucun)'}', introuvable — il se posera "
                 f"à l'origine de l'écran.")
    L.append(f"const UIRegionInfo g_ui_regions[{max(1, len(rows))}] = {{")
    L += rows or ["    { 0, 0, 240, 32, 0, 255, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0 },   /* aucun texte */"]
    L.append("};")
    L.append("")
    return L


# Correspondance balise → constante C. Une seule table plutôt qu'un `if` par
# balise : ajouter un effet ne doit toucher que le catalogue et ce dict.
_EV_KIND = {
    "speed": "TEXT_EV_SPEED", "pause": "TEXT_EV_PAUSE",
    "wave":  "TEXT_EV_WAVE",  "shake": "TEXT_EV_SHAKE",
    "color": "TEXT_EV_COLOR", "value": "TEXT_EV_VALUE",
}


def emit_texts_c(texts: list, globals_=(), constants=(), emit=None,
                 fonts=()) -> list[str]:
    """Tables C des textes : codepoints affichables, piste d'événements et
    sources à interpoler.

    Le balisage est résolu ICI, une fois pour toutes — c'est ce qui dispense le
    moteur d'un parseur et garde `text_length` sur la longueur AFFICHÉE. Les
    `#define TEXT_<CLE>` sont émis par le codegen de script (là où vivent déjà
    SFX_*/MUSIC_*), pas ici.

    Une constante est cuite dans les codepoints : elle ne change jamais, la
    lire au runtime coûterait une indirection pour rien. Un global, lui, laisse
    une place réservée et un pointeur dans `g_text_values`."""
    from core.text_markup import parse, KIND_VALUE

    const_values = {c.name: c.value for c in constants}
    global_names = {g.name for g in globals_}

    L: list[str] = ["/* ── Textes ──────────────────────────────────────── */"]
    lengths: list[int] = []
    ev_names: list[str] = []
    ev_counts: list[int] = []
    sources: list[str] = []       # symboles C des globals à lire, dans l'ordre

    for i, t in enumerate(texts):
        parsed = parse(t.content)
        # Ce qui n'est pas un global se règle AVANT le découpage en codepoints :
        # une constante vaut « 7 » comme « 100 », donc décale tout ce qui suit.
        bake = {}
        for m in parsed.markers:
            if m.kind != KIND_VALUE or m.value in bake:
                continue
            if m.value in const_values:
                bake[m.value] = str(const_values[m.value])
            elif m.value not in global_names:
                # Rendu littéralement, comme dans l'aperçu de l'éditeur : le
                # nom apparaît sur la console au lieu d'un trou muet. `$$`
                # l'échappe, sinon la relecture le reprendrait pour un marqueur.
                bake[m.value] = f"$${m.value}"
                if emit:
                    emit("log_line", f"[text] {t.key} : « ${m.value} » n'est ni "
                                     f"un global ni une constante — écrit tel quel.")
        if bake:
            parsed = parse(_bake_values(t.content, bake))

        for iss in parsed.issues:
            if emit:
                emit("log_line", f"[text] {t.key} : {iss.message}")
        # `[color]` repose sur la composition pixel : le chemin tilemap pose une
        # tuile DÉJÀ encrée, partagée par toutes ses occurrences, donc la
        # recolorer recolorerait le texte entier. Si aucune police du projet ne
        # compose, la couleur ne sortira jamais — autant le dire au build plutôt
        # que de laisser chercher pourquoi rien ne change.
        if emit and fonts and parsed.of_kind("color") \
                and not any(render_composited(f) for f in fonts):
            emit("log_line",
                 f"[text] {t.key} : « [color] » demande une police composée "
                 f"(proportionnelle, ou trop grosse pour la VRAM) — aucune "
                 f"police du projet ne l'est, la couleur sera ignorée.")

        cps = [ord(c) for c in parsed.display if ord(c) < 0x10000]
        events = []
        for m in parsed.markers:
            kind = _EV_KIND.get(m.kind)
            if kind is None:            # icon : déjà résolu dans les codepoints
                continue
            value = m.value
            if m.kind == KIND_VALUE:
                # Dédoublonnées : un même global cité par dix textes ne mérite
                # qu'un pointeur.
                sym = f"GLOBAL_{m.value.upper()}"
                if sym not in sources:
                    sources.append(sym)
                value = sources.index(sym)
            events.append(f"    {{ {m.at}, {m.end}, {value or 0}, {kind}, 0 }},")

        L.append(f"static const unsigned short g_text_{i}[{max(1, len(cps))}] = {{"
                 + (",".join(str(c) for c in cps) or "0") + "};")
        lengths.append(len(cps))
        if events:
            L.append(f"static const TextEvent g_text_ev_{i}[{len(events)}] = {{")
            L += events
            L.append("};")
            ev_names.append(f"g_text_ev_{i}")
        else:
            ev_names.append("0")
        ev_counts.append(len(events))

    L.append(f"const unsigned short* const g_texts[{max(1, len(texts))}] = {{"
             + (",".join(f"g_text_{i}" for i in range(len(texts))) or "0") + "};")
    L.append(f"const unsigned short g_text_len[{max(1, len(texts))}] = {{"
             + (",".join(str(n) for n in lengths) or "0") + "};")
    L.append(f"const TextEvent* const g_text_events[{max(1, len(texts))}] = {{"
             + (",".join(ev_names) or "0") + "};")
    L.append(f"const unsigned short g_text_ev_count[{max(1, len(texts))}] = {{"
             + (",".join(str(n) for n in ev_counts) or "0") + "};")
    # INDEX, et non pointeurs : les globals gardent chacun leur type C (un `u8`
    # coûte un octet), donc aucun tableau de pointeurs ne peut les contenir sans
    # mentir sur l'un d'eux — `const int* const` sur un `&g_vies` en u8 ne
    # compile même pas. Le moteur lit par `global_read(index)`, dont le switch
    # généré convertit chaque cas correctement.
    L.append(f"const unsigned short g_text_values[{max(1, len(sources))}] = {{"
             + (",".join(sources) or "0") + "};")
    L.append("")
    if emit and sources:
        emit("log_line", f"[text] {len(sources)} valeur(s) interpolée(s)")
    return L


def _bake_values(source: str, bake: dict) -> str:
    """Réécrit la SOURCE en remplaçant les `$nom` de `bake`, puis laisse
    l'analyse repartir de zéro.

    Repasser par la source plutôt que rapiécer le résultat : la substitution
    décale tout ce qui suit, et recalculer les positions à la main les ferait
    diverger de l'analyse au premier oubli. Seuls les globals survivent à ce
    passage — eux gardent leur place réservée."""
    from core.text_markup import parse, KIND_VALUE
    parsed = parse(source)
    out, prev = [], 0
    for m in parsed.markers:
        if m.kind != KIND_VALUE or m.value not in bake:
            continue
        out.append(source[prev:m.src[0]])
        out.append(bake[m.value])
        prev = m.src[1]
    out.append(source[prev:])
    return "".join(out)
