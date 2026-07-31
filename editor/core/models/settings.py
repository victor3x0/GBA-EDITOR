"""Settings globaux du projet + variables déclarées explicitement (globals/constants)."""

from dataclasses import dataclass


@dataclass
class ProjectSettings:
    name: str = "mon_jeu"
    start_scene: str = ""   # scène sur laquelle démarre le JEU (choisie par l'auteur)
    # Dernière scène ouverte dans l'ÉDITEUR — état d'interface, pas réglage de
    # jeu : restauré à l'ouverture du projet. Séparé de start_scene, sinon
    # éditer une autre scène écraserait silencieusement le point de départ.
    last_scene: str = ""
    author: str = ""
    version: str = "0.1"
    # Couleur de backdrop par défaut (BGR555) — PAL_BG_RAM[0], affichée quand
    # rien d'opaque n'est dessiné nulle part. Éditée dans le ProjectInspector ;
    # Scene.backdrop_color peut la surcharger par scène.
    backdrop_color: int = 0


# ── Variables du projet ───────────────────────────────────────────
# DEUX identifiants, comme pour les textes (cf. models/text.py) :
#
#   `id`   — opaque, tiré une fois, jamais affiché. C'est lui que citent les
#            fichiers de DONNÉES (une référence de champ, `{"var": <id>}`).
#            Renommer la variable ne le touche pas : le lien tient.
#   `name` — la poignée lisible, seule chose qu'écrit le Lua et seule chose que
#            cite un `$nom` dans un texte. Renommable — c'est alors à l'éditeur
#            de réécrire ces citations-là, qui sont du texte écrit à la main.
#
# Un id opaque dans un `.lua` versionné en git serait illisible et indébuggable
# hors éditeur ; un nom dans un fichier de données casse au premier renommage.
# D'où les deux, chacun là où il est bon.

@dataclass
class GlobalVar:
    """Variable globale déclarée explicitement dans le projet."""
    name:    str  = "var"
    type:    str  = "int"   # int|bool|u8|u16|s8|s16 — un type par variable en C
    default: int  = 0
    desc:    str  = ""      # description optionnelle
    id:      int  = 0       # opaque, stable à vie — voir en-tête de section


@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle
    id:    int = 0       # opaque, stable à vie
