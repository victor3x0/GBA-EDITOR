"""Settings globaux du projet + variables déclarées explicitement (globals/constants)."""

from dataclasses import dataclass


@dataclass
class ProjectSettings:
    name: str = "mon_jeu"
    start_scene: str = ""
    author: str = ""
    version: str = "0.1"
    # Réservoir auto-import (cf. ROADMAP.md v0.2) — réglage projet, pas éditeur.
    palette_auto_import_enabled: bool = True
    # Couleur de backdrop par défaut (BGR555) — PAL_BG_RAM[0], affichée quand
    # rien d'opaque n'est dessiné nulle part. Scene.backdrop_color peut la
    # surcharger par scène. Pas d'écran dédié pour l'instant (même traitement
    # que palette_auto_import_enabled) — édition JSON manuelle en attendant.
    backdrop_color: int = 0


@dataclass
class GlobalVar:
    """Variable globale déclarée explicitement dans le projet."""
    name:    str  = "var"
    type:    str  = "int"   # "int" | "bool"
    default: int  = 0
    desc:    str  = ""      # description optionnelle


@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle
