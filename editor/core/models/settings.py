"""Settings globaux du projet + variables déclarées explicitement (globals/constants)."""

from dataclasses import dataclass, field


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
    # Les couples de TAGS de boxes qui ne se rencontrent PAS (ROADMAP v0.23).
    # Chaque entrée est une clé `pair_key(a, b)`, donc un couple non ordonné :
    # « les projectiles du joueur ignorent ceux du boss » se dit une fois.
    #
    # On stocke ce qui est INTERDIT, pas ce qui est permis : un projet existant
    # a une liste vide et tout continue de se heurter, comme avant. C'est aussi
    # ce qui garde le fichier court — on déclare les exceptions, pas la règle.
    #
    # Le build s'en sert pour NE PAS ÉMETTRE la paire : le gain est en ROM
    # autant qu'en cycles, ce qu'un filtre au runtime n'aurait pas donné.
    collision_disabled_pairs: list = field(default_factory=list)
    # Cadence de répétition des listes de menu, en frames (ROADMAP v0.22) —
    # le DÉFAUT du projet, qu'une liste peut surcharger (UIPanel.list_repeat_*).
    # Répondre ici une fois évite trois listes à trois cadences dans le même
    # jeu, ce qu'un joueur sent ; la surcharge laisse un cas particulier
    # possible. Même politique d'héritage que la transition de scène (v0.6.2).
    list_repeat_delay: int = 10   # avant le premier renvoi
    list_repeat_rate: int = 4     # entre les renvois suivants


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
    # Combien de CASES cette variable tient (ROADMAP v0.20). 1 = un scalaire,
    # exactement ce qu'était toute variable avant cette version — un projet
    # existant ne voit donc rien changer. Au-delà, c'est un tableau, écrit
    # `global.coffres[i]` dans un script et indexé À PARTIR DE 1 comme tout
    # tableau du langage (v0.7.1).
    #
    # Un tableau plutôt qu'un système de drapeaux : `flag.set(id)` serait un
    # domaine de plus pour un seul usage, là où un tableau sert aussi bien les
    # 200 à 400 booléens de monde d'un metroidvania (coffres, portes, boss
    # vaincus) que l'inventaire, les niveaux de compétence et le journal.
    #
    # `default` reste UNE valeur, pour toutes les cases : c'est ce que demande
    # le cas qui a ouvert le chantier (tout à faux au départ). Un inventaire
    # de départ se remplit dans `on_start`.
    count:   int  = 1


@dataclass
class Constant:
    """Constante déclarée explicitement dans le projet (lecture seule)."""
    name:  str = "const"
    type:  str = "int"   # même jeu de types que GlobalVar : int|bool|u8|u16|s8|s16
    value: int = 0
    desc:  str = ""      # description optionnelle
    id:    int = 0       # opaque, stable à vie


# ── La matrice de collision (ROADMAP v0.23) ──────────────────────────
# Une matrice par PAIRES et non un masque par tag. Le masque s'écrit plus vite
# mais se relit mal : c'est le modèle « layer / mask » de Godot, où il faut
# tenir deux champs asymétriques dans sa tête pour répondre à « est-ce que A
# touche B ? ». La paire répond à cette question-là directement, et c'est la
# question qu'on se pose. Une grille triangulaire de n tags fait n(n+1)/2
# cases : dix tags, cinquante-cinq cases — ça se lit d'un coup d'œil.

def pair_key(tag_a: str, tag_b: str) -> str:
    """La clé d'un couple de tags, indépendante de l'ordre — « A contre B » et
    « B contre A » sont la même question."""
    a, b = sorted((tag_a or "body", tag_b or "body"))
    return f"{a}|{b}"


def tags_collide(settings, tag_a: str, tag_b: str) -> bool:
    """Ces deux tags se rencontrent-ils ? Vrai par défaut : la matrice ne
    contient que les exceptions."""
    disabled = getattr(settings, "collision_disabled_pairs", None) or []
    return pair_key(tag_a, tag_b) not in disabled
