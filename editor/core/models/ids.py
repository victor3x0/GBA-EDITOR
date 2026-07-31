"""
core/models/ids.py — identifiants opaques, partagés par les modèles.

**Un id opaque dans les fichiers de DONNÉES, un nom lisible dans le code écrit à
la main.** C'est la règle dégagée par la table de textes (cf. models/text.py),
étendue ici aux variables du projet : ce qu'un fichier JSON référence doit
survivre à un renommage, alors qu'un id dans du Lua versionné en git serait
illisible et indébuggable hors éditeur.

12 chiffres tirés au sort, et non un compteur monotone : ça survit à la fusion
de deux branches ou de deux projets, là où deux compteurs auraient produit les
mêmes valeurs pour des objets différents.
"""
from __future__ import annotations

import random

ID_MIN = 100_000_000_000
ID_MAX = 999_999_999_999


def new_id(taken) -> int:
    """Id opaque non encore utilisé. `taken` est un ensemble d'ids pris."""
    while True:
        candidate = random.randint(ID_MIN, ID_MAX)
        if candidate not in taken:
            return candidate
