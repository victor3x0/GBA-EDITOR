"""Snap d'alignement des zones de texte — géométrie PURE, sans Qt.

Le canvas fait vivre le geste en flottant (cf. `UIRegionItem`), puis pose le
snap à la tuile au relâchement. Ce module ajoute, PENDANT le geste, l'aimantation
aux lignes qui comptent pour une mise en page : les bords et centres des AUTRES
zones, et le cadre écran 240×160. C'est le même service que les guides dynamiques
d'un éditeur vectoriel — une ligne apparaît quand un bord s'aligne, et le bord y
colle.

**Pourquoi séparé du dessin.** Le calcul « quelle cible est la plus proche, de
combien décaler » est de l'arithmétique testable sans fenêtre ; le tracé des
lignes magenta est un détail de scène Qt. Les mélanger rendrait le premier
invérifiable en tête.

**Trois lignes par zone et par axe** : début, centre, fin. Un bord gauche qui
tombe sur le bord droit d'une autre zone, deux centres qui s'alignent, deux zones
qui partagent leur droite — tous les cas d'alignement usuels sortent de ces trois
positions, sans cas particulier.

**Le seuil est en pixels ÉCRAN**, converti par l'appelant (`SNAP_PX / zoom`) :
aimanter dans un rayon constant à l'affichage, sinon la zone d'accroche
enflerait en dézoomant et deviendrait imprenable en zoomant.
"""
from __future__ import annotations

# Rayon d'accroche par défaut, en pixels écran. L'appelant divise par le zoom.
SNAP_PX = 6.0


def candidate_lines(start: float, size: float) -> tuple[float, float, float]:
    """(début, centre, fin) d'un segment sur un axe."""
    return (start, start + size / 2.0, start + size)


def collect_targets(segments, screen_span: float) -> set[float]:
    """Positions-cibles d'un axe : début/centre/fin de chaque segment voisin,
    plus le cadre écran (0, milieu, bord). `segments` = itérable de
    (start, size) — déjà en coordonnées scène, offset d'actor compris, puisque
    l'appelant lit les items tels qu'ils sont dessinés."""
    vals: set[float] = set()
    for s, sz in segments:
        vals.update(candidate_lines(s, sz))
    vals.update((0.0, screen_span / 2.0, float(screen_span)))
    return vals


def snap(candidates, targets, threshold: float):
    """Meilleur appariement (candidat, cible) à distance ≤ seuil.

    `candidates` = lignes qui se déplacent ENSEMBLE (les trois d'une zone qu'on
    translate) ou une seule (le bord tiré d'un redimensionnement). Retourne
    (delta, cible) — `delta` à ajouter à la quantité mobile pour coller le
    candidat gagnant sur sa cible — ou (0.0, None) si rien n'accroche.

    À égalité de distance, le premier trouvé gagne ; l'ordre des cibles étant un
    ensemble, on ne promet pas lequel, mais deux cibles à distance égale sont au
    même endroit à moins d'un pixel, donc le choix est cosmétique."""
    best = None   # (abs_dist, delta, target)
    for c in candidates:
        for t in targets:
            d = t - c
            ad = abs(d)
            if ad <= threshold and (best is None or ad < best[0]):
                best = (ad, d, t)
    return (best[1], best[2]) if best else (0.0, None)
