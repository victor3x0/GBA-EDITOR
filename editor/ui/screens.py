"""Les écrans de l'éditeur : le contrat qu'ils remplissent, et le registre où
un plugin en ajoute un.

Un écran n'était pas une donnée. Il fallait l'épeler à CINQ endroits de
`window.py` — le tableau `SCREENS`, l'ordre des `addWidget` dans `_setup_ui`,
un attribut `self._x`, une ligne dans `_refresh_ui`, les abonnements du
dispatcher — dont deux listes parallèles dont l'accord n'était tenu que par un
commentaire (« l'ordre doit rester synchronisé »). Un écran inséré au milieu
décalait silencieusement l'autre liste.

Ici il n'y a qu'une liste, construite par `MainWindow._screen_catalogue()`, et
tout en dérive : les libellés de la barre de navigation, l'ordre du
`QStackedWidget`, et la propagation du projet ouvert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from PyQt6.QtWidgets import QWidget


@runtime_checkable
class ProjectScreen(Protocol):
    """Ce qu'un écran doit savoir faire : recevoir le projet ouvert.

    Le contrat existait déjà, sans nom : six écrans l'écrivaient
    `load_project`, un septième `set_project`, et rien ne disait lequel était
    le bon. C'est `load_project` — la majorité, et le verbe juste (un écran
    charge un projet, il ne le configure pas).

    `Protocol` et non classe de base : un écran est un `QWidget` d'abord, et
    l'héritage multiple avec Qt coûte plus qu'il ne rapporte ici. Le contrôle
    se fait à la construction (`MainWindow._build_screens`), ce qui couvre
    aussi les écrans venus d'un plugin — qu'aucun contrôle statique ne peut
    voir.
    """

    def load_project(self, project) -> None: ...


@dataclass(frozen=True)
class EditorScreen:
    """Une entrée du catalogue d'écrans.

    `build` rend le widget ; il n'est appelé qu'une fois, au démarrage. C'est
    un appelable et non une classe parce qu'un écran ne se construit pas
    forcément par simple appel de constructeur — le Scene Manager est assemblé
    par la fenêtre à partir de trois colonnes qu'elle possède déjà.
    """

    name: str
    build: Callable[[], QWidget]
    # Un écran de plugin est du code tiers : la fenêtre entoure ses appels
    # plutôt que de laisser une exception traverser un slot Qt (cf.
    # `MainWindow._refresh_ui`). Les écrans natifs, eux, doivent échouer fort.
    plugin: bool = False


# ── Registre des plugins ──────────────────────────────────────────────
# La seconde surface d'extension, à côté de `COMPONENT_REGISTRY` (un éditeur de
# composant) et de `@register_validator` (une règle de build) : un écran entier.
# Les plugins sont chargés par `main.py` AVANT la fenêtre, donc ce module ne
# doit rien importer d'elle — d'où le registre ici et pas dans `window.py`.

_PLUGIN_SCREENS: list[EditorScreen] = []


def register_screen(name: str, build: Callable[[], QWidget]) -> None:
    """Ajoute un écran à la barre de navigation. À appeler depuis le
    `editor.py` d'un plugin, au chargement du module.

        from ui.screens import register_screen
        register_screen("Mon écran", MonEcran)

    Le widget rendu par `build` doit satisfaire `ProjectScreen` ; sinon il est
    monté quand même, mais ne recevra jamais le projet et la fenêtre le
    signale au démarrage (même canal que les erreurs de chargement de plugin).

    Un nom déjà pris est refusé : il sert de clé de navigation
    (`MainWindow._switch_screen`).
    """
    if any(s.name == name for s in _PLUGIN_SCREENS):
        raise ValueError(f"écran « {name} » déjà enregistré")
    _PLUGIN_SCREENS.append(EditorScreen(name, build, plugin=True))


def plugin_screens() -> list[EditorScreen]:
    """Les écrans enregistrés par les plugins, dans l'ordre de chargement.

    Ils sont ajoutés APRÈS les écrans natifs : les index de ces derniers ne
    bougent pas quand un plugin est installé ou retiré, et l'ordre de la barre
    de navigation enregistré par l'utilisateur survit (cf.
    `ReorderableButtonBar._load_order`, qui repart de zéro si le compte change).
    """
    return list(_PLUGIN_SCREENS)
