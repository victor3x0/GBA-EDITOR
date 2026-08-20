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
    # Nombre d'emplacements de sauvegarde en SRAM. Un réglage et non une valeur
    # libre laissée au script : c'est lui qui BORNE la place occupée, donc ce
    # qui rend la capacité vérifiable au build plutôt qu'à l'exécution.
    save_slots: int = 1
    # Transition jouée à chaque changement de scène — le DÉFAUT du projet, qu'une
    # scène peut surcharger (cf. Scene.transition_kind). Répondre ici une fois
    # évite de reposer la question sur chaque scène ; la surcharge évite
    # d'imposer un fondu à un menu qui doit apparaître net.
    # Valeurs : les mêmes chaînes que les effets de mélange (models/scene.py),
    # un fondu au noir devant s'appeler pareil partout.
    transition_kind: str = "none"    # none | fade_black | fade_white
    transition_frames: int = 16      # durée d'UNE moitié (fermeture ou ouverture)
    # Capacité de la cartouche visée, en Mio — 4, 8, 16 ou 32, les tailles
    # réellement produites en cartouche masquée sur GBA (l'espace d'adressage
    # de la console s'arrête à 32 Mio). Sert de plafond au rapport de poids
    # affiché en fin de build (cf. codegen/rom_report.py).
    cartridge_mib: int = 4
    # Taux d'échantillonnage cible des effets, en Hz — le DÉFAUT du projet,
    # qu'un Sfx peut surcharger (cf. Sfx.sample_rate). 0 = on garde le taux du
    # fichier source. C'est bien le défaut : ré-échantillonner d'office
    # dégraderait un projet existant sans que personne ne l'ait demandé.
    sfx_sample_rate: int = 0
    # Canaux logiciels de maxmod, partagés par la musique et les effets.
    # `mmInitDefault(bank, n)` alloue exactement 92 × n + 1056 octets sur le
    # tas (40 o de voie de module + 28 o de voie active + 24 o de voie de
    # mixage par canal, plus le tampon de mixage 16 kHz) — mesuré au
    # désassemblage, cf. ROADMAP v0.8.8. Défaut 8 : la valeur qui était en dur,
    # pour qu'un projet existant ne change pas de son parce qu'un réglage est
    # apparu. Le pool de RÉFÉRENCES d'effets, lui, vaut 16 quoi qu'on mette ici.
    sound_channels: int = 8
    # Build DEBUG (`debug.log`, mesure de budget par frame — cf. ROADMAP v0.14)
    # vs RELEASE (les deux disparaissent de la ROM, à la compilation, pas au
    # runtime). Vrai par défaut : c'est le comportement qu'avait le logiciel
    # avant que ce réglage existe, un projet existant ne doit rien voir changer.
    debug_build: bool = True


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
    # Cette variable survit-elle à l'extinction de la console ? Un drapeau par
    # variable, et non « tout persister » : un compteur de travail n'a rien à
    # faire en SRAM, et surtout ce qui entre dans la sauvegarde décide de sa
    # compatibilité (cf. ROADMAP.md v0.5). C'est l'`id` ci-dessus qui l'identifie
    # dans le fichier de sauvegarde — jamais son rang, jamais son nom.
    persist: bool = False


@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle
    id:    int = 0       # opaque, stable à vie
