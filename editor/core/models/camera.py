"""Camera — comment l'écran regarde le monde, en tant qu'asset réutilisable.

Une caméra est rangée avec les données PROPRES au projet (`project/cameras/`)
et non avec les ressources importées : elle ne dépend d'aucun fichier extérieur,
comme une mise en page d'UI ou une palette.

**Une seule caméra est active à la fois.** La GBA n'a qu'un écran et le
multijoueur est hors périmètre : « plusieurs caméras » veut donc dire plusieurs
configurations nommées dont une est active, jamais plusieurs vues simultanées.
La scène désigne sa caméra de démarrage ; un script en change par appel
explicite (`camera.switch`), il n'existe pas de bascule automatique par zone —
un script déclenché par une collision suffit à en faire une.

Ce que la caméra ne porte PAS, et pourquoi :

- **le défilement horizontal/vertical** reste une propriété de la scène. Deux
  concepts distincts : la caméra décide *comment* la position est calculée, le
  défilement dit *si le niveau lui-même* est censé défiler dans cet axe.
  Changer de caméra ne doit pas changer ça ;
- **la rotation, le zoom, une projection** : un calque régulier ne sait ni
  tourner ni se mettre à l'échelle. Ce sont des calques affines, donc la v2.0.
  Les proposer ici promettrait un rendu que le matériel ne sait pas produire ;
- **un viewport** : découper l'écran, c'est une window matérielle, et il n'y en
  a que deux — que la scène authore déjà (cf. `Scene.windows`). Question
  rouverte en v2.0 avec l'écran partagé ;
- **les paramètres de secousse** : une secousse est un événement, pas un état.
  Ses valeurs vivent à l'appel (`camera.shake(amplitude, frames)`).
"""

from dataclasses import dataclass
from typing import Optional

from core.models.resource import Resource

# Modes — QUI écrit la position de la caméra pendant la frame.
CAM_FIXED  = "fixed"    # personne : elle reste là où l'activation l'a posée
CAM_FOLLOW = "follow"   # le suivi déclaratif, sur `follow_target`
CAM_SCRIPT = "script"   # le script seul (le déclaratif ne calcule rien)
CAM_MODES = (CAM_FIXED, CAM_FOLLOW, CAM_SCRIPT)

# Le mode tel que le runtime le reçoit — un entier dans la table des caméras.
CAM_MODE_IDS = {CAM_FIXED: 0, CAM_FOLLOW: 1, CAM_SCRIPT: 2}


@dataclass
class Camera(Resource):
    name: str = "Camera"
    # Cadrage appliqué À L'ACTIVATION (démarrage de scène ou camera.switch).
    # Une caméra fixe ne bouge plus ensuite ; une caméra en suivi se recale
    # dans la frame même.
    x: int = 0
    y: int = 0
    mode: str = CAM_FIXED
    # Acteur suivi, par NOM — résolu dans CHAQUE scène qui emploie cette
    # caméra (cf. project.camera_users). Une caméra est réutilisable, les noms
    # d'acteurs sont locaux à une scène : une scène sans acteur de ce nom
    # laisse la caméra immobile, et le validateur le dit.
    follow_target: str = ""
    # Zone morte : la caméra ne bouge que lorsque la cible s'éloigne de plus de
    # ça du bord de l'écran. 0 = recentrage permanent.
    margin_x: int = 40
    margin_y: int = 20
    # Bornes du monde en pixels, appliquées à l'activation ; None = axe
    # illimité. Un script peut les redéfinir ensuite (camera.set_bounds), et
    # une réactivation les repose.
    bounds_w: Optional[int] = None
    bounds_h: Optional[int] = None
    # Script Lua de la caméra, mêmes points d'entrée qu'une scène. Les réglages
    # déclaratifs ci-dessus sont TOUJOURS calculés avant qu'il ne s'exécute :
    # l'usage peut donc être purement déclaratif, purement scripté, ou les
    # deux, sans réglage de bascule dédié.
    script: str = ""

    def mode_id(self) -> int:
        return CAM_MODE_IDS.get(self.mode, 0)
