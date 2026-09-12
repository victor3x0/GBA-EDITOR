"""
core/text_markup.py — le langage de balisage des entrées de la table de textes.

Syntaxe à la BBCode (décision ROADMAP v0.3.2, sur le modèle du `RichTextLabel`
de Godot) : `[speed=4]`, `[pause=3]`, `[wave]…[/wave]`. Elle est **fermée** —
sans borne de fin, `/S12` serait indécidable —, les crochets n'apparaissent pas
en prose là où `/` le fait (« et/ou », « 12/05 »), et elle a des **balises de
portée**, ce dont un effet par caractère a besoin puisqu'il s'applique à un
intervalle et pas à un point.

**Tout se résout au build, le moteur n'embarque aucun parseur.** Ce module est
donc le point unique : l'aperçu de l'éditeur et l'encodeur lisent la même
analyse, sinon l'éditeur promettrait un rendu que la ROM ne tiendrait pas.

Ce qui sort d'une analyse :
  • `display` — le texte AFFICHÉ, balises retirées. C'est exactement ce que
    l'encodeur sort en codepoints, donc ce dont `text.length` donne la longueur.
    Un marqueur de valeur y tient UNE place (`SENTINEL`) : `resolve()` la
    remplace par des chiffres pour l'aperçu, le runtime pour de vrai.
  • `markers` — les effets, repérés en coordonnées d'AFFICHAGE (pas de source) :
    c'est ce que la piste d'événements émettra, et le runtime ne connaît que ces
    positions-là.
  • `issues` — ce qui n'a pas été compris, repéré en coordonnées de SOURCE pour
    être souligné dans l'atelier.

Rien n'est deviné : une balise inconnue ou mal formée reste du TEXTE (elle
s'affichera telle quelle) et produit un avertissement. Mais l'avertissement est
réservé à ce qui RESSEMBLE à une tentative de balise — nom voisin d'une balise
connue, casse fautive, valeur portée, paire ouverte/fermée. « Touche [A] »
s'écrit donc sans rien échapper ET sans être signalée : même compromis que le
checker de scripts, qui n'avertit sur une chaîne que si elle a la forme d'une
clé sans en matcher aucune.

Seul `[` s'échappe, en le doublant (`[[`), parce que seul `[` ouvre quelque
chose ; un `]` isolé n'est jamais ambigu et passe toujours tel quel. Idem pour
le dollar : `$$` écrit un dollar littéral.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Catalogue des balises ─────────────────────────────────────────
# Point unique, comme `scripting.api.RUNTIME_API` : l'analyse, la validation et
# (à venir) la coloration de l'atelier le lisent, aucune n'en tient une copie.

VALUE_NONE = ""     # la balise ne prend pas de valeur
VALUE_INT  = "int"
VALUE_NAME = "name"


@dataclass(frozen=True)
class TagSpec:
    name:   str
    scoped: bool         # True = [x]…[/x], False = ponctuelle
    value:  str          # VALUE_NONE | VALUE_INT | VALUE_NAME
    doc:    str
    # Bornes d'un entier, quand le matériel en impose. None = pas de plafond.
    vmin:   int = 0
    vmax:   Optional[int] = None


TAGS: dict[str, TagSpec] = {t.name: t for t in (
    # ── Tempo — ponctuelles, elles marquent un INSTANT de la lecture ──
    TagSpec("speed", False, VALUE_INT,
            "Vitesse de lecture à partir d'ici, en frames par caractère. "
            "0 = instantané."),
    TagSpec("pause", False, VALUE_INT,
            "Attend n frames avant de continuer — la virgule du tempo."),
    # ── Insertion ─────────────────────────────────────────────────
    TagSpec("icon", False, VALUE_NAME,
            "Insère le glyphe nommé de la police (une case fusionnée). "
            "Équivaut à taper sa suite de caractères, mais l'éditeur peut "
            "vérifier que la police le porte."),
    # ── Effets — de PORTÉE, ils s'appliquent à un intervalle ───────
    TagSpec("wave",  True, VALUE_NONE, "Ondulation par caractère."),
    TagSpec("shake", True, VALUE_NONE, "Tremblement par caractère."),
    # 1..15 n'est pas un choix : une police est en 4bpp, l'index 0 y est la
    # transparence et il ne reste que quinze encres. Hors de cette plage, le
    # remappage du runtime déborderait son mot de 32 bits.
    TagSpec("color", True, VALUE_INT,
            "Couleur d'encre n dans la sous-palette de la police (1..15). "
            "Suppose une planche qui porte déjà plusieurs teintes.",
            vmin=1, vmax=15),
    TagSpec("font", True, VALUE_NAME,
            "Emploie la police nommée pour ce fragment de texte."),
)}

# Marqueur de valeur — pas une balise : il désigne un global ou une const, dont
# la valeur est substituée à la lecture. `$$` écrit un dollar littéral.
KIND_VALUE = "value"

# Un marqueur de valeur occupe UNE place dans le texte affiché, tenue par un
# non-caractère Unicode : U+FFFF est réservé à perpétuité par le standard, donc
# aucun texte ni aucun glyphe ne peut légitimement le porter. C'est ce que
# l'encodeur émet, et ce que `resolve` remplace par des chiffres.
SENTINEL = "￿"
VALUE_CP = 0xFFFF

# Balises de portée qui coûtent des glyphes ANIMÉS, donc de l'OAM : c'est ce que
# `Project.region_animated_glyphs` compte pour réserver la place.
ANIMATED_TAGS = frozenset({"wave", "shake"})


@dataclass(frozen=True)
class Marker:
    """Un effet posé sur le texte affiché.

    `at`/`end` sont des index dans `display` (`end` exclu, `end == at` pour une
    balise ponctuelle) ; `src` est le fragment de source correspondant, pour
    pouvoir le désigner dans l'atelier."""
    kind:  str
    at:    int
    end:   int
    value: Optional[object] = None
    src:   tuple[int, int] = (0, 0)

    @property
    def scoped(self) -> bool:
        return self.end > self.at


# Ce que la coloration de l'atelier a besoin de savoir : où sont les tokens
# RECONNUS dans la source. Le parseur les connaît déjà — les redire en regex
# côté vue aurait donné deux grammaires à tenir d'accord, et la seconde aurait
# menti au premier ajout de balise.
TOK_TAG    = "tag"      # [wave], [speed=4]
TOK_CLOSE  = "close"    # [/wave]
TOK_VALUE  = "value"    # $nom
TOK_ESCAPE = "escape"   # [[ et $$


@dataclass(frozen=True)
class Token:
    kind: str
    at:   int
    end:  int


@dataclass(frozen=True)
class Issue:
    """Ce que l'analyse n'a pas compris, situé dans la SOURCE."""
    at:      int
    end:     int
    message: str


@dataclass
class ParsedText:
    display: str = ""
    markers: list[Marker] = field(default_factory=list)
    issues:  list[Issue] = field(default_factory=list)
    tokens:  list[Token] = field(default_factory=list)   # spans SOURCE, pour la vue

    @property
    def length(self) -> int:
        """Longueur AFFICHÉE — ce que rend `text.length`."""
        return len(self.display)

    def of_kind(self, *kinds: str) -> list[Marker]:
        return [m for m in self.markers if m.kind in kinds]

    @property
    def animated_glyphs(self) -> int:
        """Caractères couverts par un effet animé — à confronter au budget
        déclaré par la zone qui affichera ce texte."""
        covered: set[int] = set()
        for m in self.markers:
            if m.kind in ANIMATED_TAGS:
                covered.update(range(m.at, m.end))
        return len(covered)


# ── Analyse ───────────────────────────────────────────────────────

# Un seul balayage : échappements, balises et marqueurs de valeur. Le reste du
# texte passe tel quel — y compris un crochet isolé, qui n'est une erreur que
# s'il ouvre quelque chose qui ressemble à une balise.
_TOKEN = re.compile(
    r"""\[\[                                  # [[ → [ littéral
      | \$\$                                  # $$ → $ littéral
      | \[ (?P<close>/)? (?P<name>[A-Za-z_][A-Za-z0-9_]*)
           (?: = (?P<value>[^\]]*) )? \]      # balise ouvrante ou fermante
      | \$ (?P<var>[A-Za-z_][A-Za-z0-9_]*)    # marqueur de valeur
    """,
    re.VERBOSE,
)


def parse(source: str) -> ParsedText:
    """Analyse une entrée de la table. Ne lève jamais : ce qui n'est pas compris
    devient du texte et un `Issue`."""
    out = ParsedText()
    if not source:
        return out
    disp: list[str] = []
    open_scopes: list[tuple] = []   # (nom, valeur, at_display, src_debut, src_fin)
    pos = 0

    def literal(a: int, b: int):
        disp.append(source[a:b])

    for m in _TOKEN.finditer(source):
        literal(pos, m.start())
        pos = m.end()
        tok = m.group(0)

        if tok == "[[":
            disp.append("[")
            out.tokens.append(Token(TOK_ESCAPE, m.start(), m.end()))
            continue
        if tok == "$$":
            disp.append("$")
            out.tokens.append(Token(TOK_ESCAPE, m.start(), m.end()))
            continue

        if m.group("var"):
            at = len("".join(disp))
            # UNE place réservée, pas le nom : c'est ce que l'encodeur émet, et
            # ce qui garde `at`/`end` des marqueurs suivants justes quelle que
            # soit la valeur substituée derrière.
            disp.append(SENTINEL)
            out.markers.append(Marker(KIND_VALUE, at, at + 1,
                                      m.group("var"), (m.start(), m.end())))
            out.tokens.append(Token(TOK_VALUE, m.start(), m.end()))
            continue

        name = m.group("name")
        raw = m.group("value")
        spec = TAGS.get(name)
        span = (m.start(), m.end())

        if spec is None:
            msg = _unknown_issue(name, raw, bool(m.group("close")), source)
            if msg:
                out.issues.append(Issue(*span, msg))
            disp.append(tok)
            continue

        if m.group("close"):
            before = len(out.issues)
            _close_scope(out, disp, open_scopes, spec, raw, tok, span)
            if len(out.issues) == before:
                out.tokens.append(Token(TOK_CLOSE, *span))
            continue

        value, err = _read_value(spec, raw)
        if err:
            out.issues.append(Issue(*span, err))
            disp.append(tok)
            continue
        # Reconnue et bien formée : elle mérite d'être colorée. Une balise
        # inconnue ou fautive n'en est pas une — elle s'affichera, donc elle
        # se lit comme du texte.
        out.tokens.append(Token(TOK_TAG, *span))

        at = len("".join(disp))
        if spec.scoped:
            open_scopes.append((name, value, at, span[0], span[1]))
        elif name == "icon":
            # Un icône EST sa suite de caractères : l'insérer dans le texte
            # affiché laisse la correspondance au plus long (les ligatures)
            # faire son travail, sans second chemin de rendu.
            disp.append(str(value))
            out.markers.append(Marker(name, at, len("".join(disp)), value, span))
        else:
            out.markers.append(Marker(name, at, at, value, span))

    literal(pos, len(source))
    out.display = "".join(disp)

    # Portées jamais refermées : l'intention est claire (la balise est valide,
    # seule sa fin manque), on l'étend jusqu'au bout plutôt que de la dessiner —
    # mais on le dit, sinon un `[/wave]` oublié passerait en ROM sans un mot.
    for name, value, at, s0, s1 in open_scopes:
        out.issues.append(Issue(s0, s1, f"« [{name}] » n'est jamais refermée — "
                                        f"l'effet court jusqu'à la fin du texte."))
        out.markers.append(Marker(name, at, len(out.display), value, (s0, s1)))

    out.markers.sort(key=lambda mk: (mk.at, mk.end))
    out.issues.sort(key=lambda i: i.at)
    out.tokens.sort(key=lambda t: t.at)
    return out


def _unknown_issue(name: str, raw: Optional[str], closing: bool,
                   source: str) -> str:
    """Message pour une balise inconnue, ou "" s'il faut se taire.

    Un crochet en prose (« touche [A] », « [Start] ») n'est pas une faute : le
    signaler à chaque fois rendrait l'avertissement inutile. On ne parle donc
    que si la forme trahit une TENTATIVE de balise."""
    lower = name.lower()
    if lower in TAGS and lower != name:
        return f"« [{name}] » : les balises s'écrivent en minuscules — « [{lower}] »."
    near = difflib.get_close_matches(lower, list(TAGS), n=1, cutoff=0.7)
    if near:
        return f"Balise inconnue « {name} » — vouliez-vous « {near[0]} » ?"
    if closing or raw is not None or f"[/{name}]" in source:
        return f"Balise inconnue « {name} » — elle s'affichera telle quelle."
    return ""


def _read_value(spec: TagSpec, raw: Optional[str]) -> tuple[object, str]:
    """(valeur, message d'erreur) — la valeur n'a de sens que si le message est
    vide."""
    if spec.value == VALUE_NONE:
        if raw is not None:
            return None, f"« [{spec.name}] » ne prend pas de valeur."
        return None, ""
    if raw is None or not raw.strip():
        kind = "un entier" if spec.value == VALUE_INT else "un nom"
        return None, f"« [{spec.name}] » attend {kind} : [{spec.name}=…]."
    raw = raw.strip()
    if spec.value == VALUE_INT:
        if not raw.isdigit():
            return None, (f"« [{spec.name}={raw}] » attend un entier positif.")
        n = int(raw)
        if n < spec.vmin or (spec.vmax is not None and n > spec.vmax):
            return None, (f"« [{spec.name}={n}] » est hors plage — "
                          f"attendu entre {spec.vmin} et {spec.vmax}.")
        return n, ""
    return raw, ""


def _close_scope(out: ParsedText, disp: list[str], open_scopes: list,
                 spec: TagSpec, raw: Optional[str], tok: str,
                 span: tuple[int, int]):
    """Referme une portée ouverte, ou signale ce qui l'en empêche."""
    if raw is not None:
        out.issues.append(Issue(*span, f"Une balise fermante ne porte pas de "
                                       f"valeur : écrire « [/{spec.name}] »."))
        disp.append(tok)
        return
    if not spec.scoped:
        out.issues.append(Issue(*span, f"« [{spec.name}] » est ponctuelle, elle "
                                       f"ne se referme pas."))
        disp.append(tok)
        return
    for i in range(len(open_scopes) - 1, -1, -1):
        if open_scopes[i][0] == spec.name:
            name, value, at, s0, s1 = open_scopes.pop(i)
            if i != len(open_scopes):
                # Mal imbriquée : on ferme quand même celle qui est nommée. La
                # refuser obligerait à choisir laquelle sacrifier.
                out.issues.append(Issue(*span, f"« [/{name}] » ferme une portée "
                                               f"ouverte avant d'autres encore "
                                               f"ouvertes — imbrication croisée."))
            out.markers.append(Marker(name, at, len("".join(disp)), value, (s0, s1)))
            return
    out.issues.append(Issue(*span, f"« [/{spec.name}] » ne ferme aucune portée "
                                   f"ouverte."))
    disp.append(tok)


def resolve(parsed: ParsedText, values: Optional[dict] = None) -> str:
    """Le texte tel qu'un joueur le lit : places réservées remplacées par les
    valeurs de `values`.

    Un nom absent de `values` rend `$nom` — l'anomalie reste donc VISIBLE dans
    l'aperçu au lieu de se traduire par un trou muet. Côté ROM c'est l'encodeur
    qui substitue les constantes et pose un pointeur pour les globals ; ici on
    montre les valeurs INITIALES, seules connues à l'édition."""
    if SENTINEL not in parsed.display:
        return parsed.display
    values = values or {}
    out, prev = [], 0
    for m in parsed.markers:
        if m.kind != KIND_VALUE:
            continue
        out.append(parsed.display[prev:m.at])
        out.append(str(values[m.value]) if m.value in values else f"${m.value}")
        prev = m.end
    out.append(parsed.display[prev:])
    return "".join(out)


def rename_value(source: str, old: str, new: str) -> str:
    """Réécrit les `$old` en `$new` dans une source balisée.

    Passe par l'ANALYSE et non par un remplacement de texte : seuls les
    marqueurs de valeur bougent. Un `$$old` échappé, un `[icon=old]` ou le mot
    « old » en prose restent intacts — c'est la même exigence que le repérage
    structurel de `scripting/refactor.py` pour les scripts."""
    parsed = parse(source)
    out, prev = [], 0
    for m in parsed.markers:
        if m.kind != KIND_VALUE or m.value != old:
            continue
        out.append(source[prev:m.src[0]])
        out.append("$" + new)
        prev = m.src[1]
    if not out:
        return source
    out.append(source[prev:])
    return "".join(out)


def display_text(source: str, values: Optional[dict] = None) -> str:
    """Analyse et résout d'un coup — raccourci pour tout ce qui n'a besoin que
    du texte lisible (ligne de table, extrait, mesure, charset)."""
    return resolve(parse(source), values)
