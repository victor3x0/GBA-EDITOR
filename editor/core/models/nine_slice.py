"""NineSlice — asset de cadre étirable, fond d'un `UIPanel`.

Un cadre découpé en 9 par 4 marges : coins fixes, bords/centre répétés (cf.
`core/nine_slice.py` pour la géométrie). C'est un ASSET nommé et réutilisable —
une même boîte de dialogue sert N panels et se corrige en un endroit, comme une
palette ou une police.

Interim : le PNG source vient d'un background DÉJÀ importé (`source` = nom d'un
`BackgroundAsset`) — pas encore de pipeline d'import dédié au nine-slice."""

from dataclasses import dataclass

from core.models.resource import Resource


@dataclass
class NineSlice(Resource):
    name:   str = "nine_slice"
    source: str = ""   # nom du BackgroundAsset dont le PNG fournit le cadre
    left:   int = 4    # marges de coupe, en pixels de l'image source
    right:  int = 4
    top:    int = 4
    bottom: int = 4
