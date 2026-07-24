"""Textes du jeu — table de chaînes destinées au joueur.

Trois identifiants, un seul résolvable :

  `id`    — opaque, tiré une fois à la création, jamais affiché ni retapé.
            C'est lui que stockent les fichiers de données et que suit le
            graphe de dépendances. Il ne change JAMAIS, y compris si le
            contenu et la clé changent.
  `key`   — la poignée lisible, ce qu'un script Lua écrit. Unique, résolue au
            build vers un index de table C (comme SFX_* ou SCENE_IDX_*) : elle
            ne vit pas au runtime. Renommable — c'est alors à l'éditeur de
            réécrire les références.
  `label` — libre, purement organisationnel. Jamais résolu, peut se répéter,
            accents et espaces bienvenus.

**La clé situe, elle ne résume pas.** Elle est dérivée du CONTEXTE de création
(scène, élément), jamais du contenu : le contenu d'un texte est réécrit vingt
fois pendant l'écriture, sa place dans le jeu bouge rarement. Une clé tirée du
contenu (`garde_je_suis`) devient un mensonge dès que le garde devient un
mendiant — et personne ne va la corriger. Une clé positionnelle reste au pire
imprécise.

Corollaire verrouillé : **la clé n'est jamais recalculée**. Posée une fois, elle
appartient à l'utilisateur ; le sens n'y arrive que par renommage manuel, quand
un texte le mérite vraiment (`menu_confirmer`, `game_over`).

Le texte est destiné au JOUEUR, donc traduisible (cf. ROADMAP.md v0.8) : c'est
ce qui le distingue d'un `string` technique, qui reste un littéral dans le
script.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field


# Largeur de l'id opaque. 10^12 laisse la collision à ~1 sur un million
# d'entrées (paradoxe des anniversaires) — assez pour survivre à la fusion de
# deux projets ou de deux branches git, là où un compteur monotone casserait.
_ID_MIN = 100_000_000_000
_ID_MAX = 999_999_999_999

# Longueur max d'un segment de clé — au-delà on tronque (une clé sert à situer,
# pas à raconter).
_SEGMENT_MAX = 16


@dataclass
class Text:
    """Une entrée de la table de textes du projet."""
    id:      int = 0     # opaque, stable à vie — voir en-tête du module
    key:     str = ""    # poignée unique et lisible, référencée depuis Lua
    label:   str = ""    # organisation libre, jamais résolu
    content: str = ""    # le texte lui-même, tel qu'affiché au joueur
    note:    str = ""    # contexte pour le traducteur (v0.8)
    scene:   str = ""    # scène d'origine — filtre d'affichage uniquement
    auto_key: bool = True  # clé jamais renommée à la main → badge « auto »

    def to_dict(self) -> dict:
        return {
            "id": self.id, "key": self.key, "label": self.label,
            "content": self.content, "note": self.note, "scene": self.scene,
            "auto_key": self.auto_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Text":
        return cls(
            id       = int(d.get("id", 0)),
            key      = d.get("key", ""),
            label    = d.get("label", ""),
            content  = d.get("content", ""),
            note     = d.get("note", ""),
            scene    = d.get("scene", ""),
            auto_key = bool(d.get("auto_key", True)),
        )


# ── Génération d'identifiants ─────────────────────────────────────

def slug(s: str) -> str:
    """Segment de clé : ASCII minuscule, séparateurs en `_`, tronqué.

    Les accents sont dépliés (« Forêt » → « foret ») plutôt que supprimés :
    une clé reste lisible pour un francophone."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:_SEGMENT_MAX]


def new_id(taken: set[int]) -> int:
    """Id opaque non encore utilisé."""
    while True:
        candidate = random.randint(_ID_MIN, _ID_MAX)
        if candidate not in taken:
            return candidate


def make_key(scene: str = "", context: str = "", *, taken: set[str] | None = None) -> str:
    """Clé positionnelle unique : `<scene>_<context>_<NN>`.

    Sans contexte du tout (création depuis l'écran Textes), on retombe sur un
    compteur nu `texte_NNN` — qui ne prétend rien, donc ne ment pas."""
    taken = taken or set()
    parts = [p for p in (slug(scene), slug(context)) if p]
    base  = "_".join(parts) if parts else "texte"
    # Le compteur repart de 1 par base : c'est un rang dans un contexte, pas un
    # identifiant global (celui-là, c'est `id`).
    n = 1
    while True:
        candidate = f"{base}_{n:02d}" if parts else f"{base}_{n:03d}"
        if candidate not in taken:
            return candidate
        n += 1
