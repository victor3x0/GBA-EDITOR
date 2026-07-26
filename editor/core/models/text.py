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
  `path`  — le rangement : 1 à 3 niveaux de libellés libres, avec accents,
            espaces et doublons autorisés. Jamais résolu, jamais référencé.

**La clé situe, elle ne résume pas.** Elle est dérivée de la PLACE du texte
(son chemin de rangement), jamais du contenu : le contenu d'un texte est
réécrit vingt fois pendant l'écriture, sa place dans le jeu bouge rarement. Une
clé tirée du contenu (`garde_je_suis`) devient un mensonge dès que le garde
devient un mendiant — et personne ne va la corriger. Une clé positionnelle
reste au pire imprécise.

**Le chemin PROPOSE la clé, il ne la POSSÈDE pas.** Tant que `auto_key` est
vrai, ranger le texte ailleurs recale sa clé (et réécrit les scripts qui la
citent : c'est sans danger, une clé automatique est par définition jetable).
Dès que l'utilisateur la nomme à la main, `auto_key` tombe à faux et la clé se
détache définitivement — réorganiser l'arbre ne la touchera plus jamais.

Sans ce détachement, ranger reviendrait à refactorer : renommer un nœud
« Village » en « Village Nord » réécrirait N clés dans M fichiers `.lua`
versionnés en git, pour un geste purement cosmétique.

Le chemin ne suffit pas non plus à identifier : deux répliques rangées au même
endroit produisent la même clé, d'où un rang numéroté (`village_garde_02`). Si
la clé était strictement dérivée, il faudrait imposer un dernier niveau unique
— et le libellé ne serait plus libre, juste une clé déguisée.

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

# Profondeur max du chemin de rangement. Plafond de départ, choisi pour que la
# clé dérivée reste lisible (3 × 16 caractères, c'est déjà long) — pas une
# limite structurelle : le chemin est une liste, la relever ne coûtera rien.
MAX_DEPTH = 3

# Séparateur d'AFFICHAGE seulement. Le stockage est une liste : un libellé
# libre a le droit de contenir « / » ou « > » sans qu'on ait à inventer une
# règle d'échappement.
SEP = " › "


@dataclass
class Text:
    """Une entrée de la table de textes du projet."""
    id:      int = 0     # opaque, stable à vie — voir en-tête du module
    key:     str = ""    # poignée unique et lisible, référencée depuis Lua
    path:    list[str] = field(default_factory=list)  # rangement libre, 1..3 niveaux
    content: str = ""    # le texte lui-même, tel qu'affiché au joueur
    note:    str = ""    # contexte pour le traducteur (v0.8)
    scene:   str = ""    # scène d'origine — filtre d'affichage uniquement
    auto_key: bool = True  # clé jamais renommée à la main → badge « auto »

    def path_str(self) -> str:
        return SEP.join(self.path)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "key": self.key, "path": list(self.path),
            "content": self.content, "note": self.note, "scene": self.scene,
            "auto_key": self.auto_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Text":
        raw = d.get("path")
        if raw is None:
            # Migration depuis la table plate : le `label` unique devient le
            # premier — et pour l'instant seul — niveau du chemin.
            raw = [d["label"]] if d.get("label") else []
        return cls(
            id       = int(d.get("id", 0)),
            key      = d.get("key", ""),
            path     = norm_path(raw),
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


def norm_path(path) -> list[str]:
    """Chemin propre : segments rognés, trous supprimés, profondeur plafonnée.

    Les trous sont compactés (`["", "Garde"]` → `["Garde"]`) : un niveau vide
    au milieu d'un chemin ne veut rien dire, et le laisser passer produirait
    deux nœuds distincts d'apparence identique dans l'arbre."""
    if isinstance(path, str):
        path = [path]
    return [s for s in (str(p).strip() for p in (path or [])) if s][:MAX_DEPTH]


def new_id(taken: set[int]) -> int:
    """Id opaque non encore utilisé."""
    while True:
        candidate = random.randint(_ID_MIN, _ID_MAX)
        if candidate not in taken:
            return candidate


def key_from_path(path, *, taken: set[str] | None = None) -> str:
    """Clé positionnelle unique dérivée du chemin : `village_garde`.

    Le rang `_NN` n'apparaît qu'en cas de collision — plusieurs répliques
    rangées au même endroit. La clé reste ainsi lisible dans le cas courant
    (un texte par nœud), qui est aussi celui qu'on copie dans un script.

    Chemin vide : compteur nu `texte_NNN`, numéroté d'emblée puisqu'il ne situe
    rien et que le suivant tomberait de toute façon sur la même base."""
    taken = taken or set()
    segs = [s for s in (slug(p) for p in norm_path(path)) if s]
    base = "_".join(segs)
    if not base:
        n = 1
        while f"texte_{n:03d}" in taken:
            n += 1
        return f"texte_{n:03d}"
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n:02d}" in taken:
        n += 1
    return f"{base}_{n:02d}"
