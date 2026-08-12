"""Aperçu du mélange de couleurs — la formule MATÉRIELLE, appliquée aux images.

Le canvas empile un item par layer ; ce module ne connaît que des images et rend
l'image du DESSUS déjà mélangée. C'est ce qui permet de garder l'architecture
d'édition (items déplaçables, visibilité par layer, inpainting) tout en montrant
le vrai rendu : on ne recompose pas la scène, on transforme le dessus.

**Les formules sont celles du matériel**, pas des modes de compositing Qt :

  alpha     out = min(31, dessus×EVA/16 + dessous×EVB/16)     — saturation
  éclaircir out = dessus + (31 − dessus)×EVY/16               — vers le blanc
  assombrir out = dessus − dessus×EVY/16                      — vers le noir

Le calcul se fait ici en 8 bits par canal parce que c'est la monnaie du canvas ;
les rapports sont les mêmes qu'en BGR555, la quantification 5 bits ayant déjà
eu lieu en amont (les pixmaps de layer sortent des palettes quantifiées).

**Deux règles que le matériel impose et qu'un compositing naïf trahit :**

1. Le mélange n'a lieu QUE là où un pixel du dessus a effectivement un pixel du
   dessous derrière lui. Ailleurs, le dessus s'affiche INTACT — il ne s'assombrit
   pas, il ne devient pas translucide. C'est exactement la panne que les gens
   décrivent comme « mon alpha ne marche pas » : sans seconde cible derrière,
   il ne se passe rien, et l'aperçu doit montrer ce rien-là.

2. Un pixel TRANSPARENT du dessus n'est pas mélangé : il n'est pas dessiné du
   tout, et c'est ce qui est derrière qui s'affiche normalement.

Les modes 2 et 3 n'emploient que le dessus — d'où l'absence de `bottom` dans
leur chemin, et non un oubli.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QImage

from core.models.scene import (BLEND_ALPHA, BLEND_BRIGHTEN, BLEND_DARKEN,
                               BLEND_EV_MAX)


def _to_rgba(img: QImage) -> np.ndarray:
    """(h, w, 4) uint8 en RGBA, copie indépendante du QImage source."""
    conv = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = conv.width(), conv.height()
    ptr = conv.constBits()
    ptr.setsize(conv.sizeInBytes())
    # bytesPerLine peut dépasser w*4 (padding) : on découpe la ligne utile.
    arr = np.frombuffer(bytes(ptr), dtype=np.uint8).reshape(h, conv.bytesPerLine() // 4, 4)
    return np.ascontiguousarray(arr[:, :w, :])


def _to_qimage(arr: np.ndarray) -> QImage:
    """L'inverse. `arr` doit rester vivante le temps du QImage — d'où la copie."""
    h, w = arr.shape[:2]
    buf = np.ascontiguousarray(arr, dtype=np.uint8).tobytes()
    return QImage(buf, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


def blend_images(top: QImage, bottom: "BottomLayer | None", mode: int,
                 eva: int = BLEND_EV_MAX, evb: int = 0,
                 evy: int = 0) -> QImage:
    """Image du DESSUS, mélangée selon `mode`. `bottom` = ce qui est
    IMMÉDIATEMENT derrière, résolu par `resolve_bottom` (couleurs + masque des
    pixels dont la couche est bien une seconde cible), ou None.

    Rend une image de la taille du dessus."""
    t = _to_rgba(top).astype(np.uint16)
    th, tw = t.shape[:2]

    if mode == BLEND_ALPHA:
        if bottom is None:
            return top          # aucune seconde cible : le dessus est intact
        b = np.zeros((th, tw, 4), dtype=np.uint16)
        ok = np.zeros((th, tw), dtype=bool)
        bh, bw = min(th, bottom.rgba.shape[0]), min(tw, bottom.rgba.shape[1])
        b[:bh, :bw] = bottom.rgba[:bh, :bw]
        ok[:bh, :bw] = bottom.is_target[:bh, :bw]
        # Mélange SEULEMENT là où la couche immédiatement derrière est une
        # seconde cible ET porte un pixel. Ailleurs le dessus reste intact :
        # c'est la règle n°1 de la docstring, et celle qui distingue « rien
        # derrière » de « quelque chose derrière qui n'a pas le droit ».
        pair = (ok & (b[..., 3] > 0))[..., None]
        mixed = np.minimum(
            255, (t[..., :3] * eva + b[..., :3] * evb) // BLEND_EV_MAX)
        out = t.copy()
        out[..., :3] = np.where(pair, mixed, t[..., :3])
    elif mode == BLEND_BRIGHTEN:
        out = t.copy()
        out[..., :3] = t[..., :3] + ((255 - t[..., :3]) * evy) // BLEND_EV_MAX
    elif mode == BLEND_DARKEN:
        out = t.copy()
        out[..., :3] = t[..., :3] - (t[..., :3] * evy) // BLEND_EV_MAX
    else:
        return top

    # Un pixel transparent du dessus n'est pas dessiné : le mélange ne doit pas
    # lui inventer une couleur (règle n°2).
    out[..., :3] = np.where(t[..., 3:4] > 0, out[..., :3], t[..., :3])
    return _to_qimage(out.astype(np.uint8))


class BottomLayer:
    """Ce qui se trouve IMMÉDIATEMENT derrière une couche, pixel par pixel.

    Deux tableaux et pas une image : la couleur ne suffit pas. Le matériel
    mélange avec la première couche visible derrière, **quelle qu'elle soit**,
    et n'accepte le mélange que si CELLE-LÀ est une seconde cible. Un pixel peut
    donc avoir quelque chose derrière lui sans avoir le droit de s'y mélanger —
    c'est la différence entre « rien derrière » et « quelque chose derrière qui
    n'est pas dans le set », et l'aperçu doit les distinguer."""

    __slots__ = ("rgba", "is_target")

    def __init__(self, rgba: np.ndarray, is_target: np.ndarray):
        self.rgba = rgba            # (h, w, 4) uint16
        self.is_target = is_target  # (h, w) bool


def resolve_bottom(entries: list, w: int, h: int,
                   backdrop_rgb: tuple | None = None,
                   backdrop_is_target: bool = False) -> "BottomLayer | None":
    """Résout la couche immédiatement derrière, sur toute la surface.

    `entries` = [(QImage, est_seconde_cible)] **de l'AVANT vers l'ARRIÈRE**,
    TOUTES les couches situées derrière le dessus — pas seulement les secondes
    cibles. C'est le point qui compte : une couche opaque qui n'est pas dans le
    set OCCULTE quand même ce qu'il y a derrière elle, et empêche donc le
    mélange. La sauter reviendrait à faire traverser le backdrop à travers un
    décor plein, ce qui teinte tout l'écran en permanence.

    Le backdrop ferme la marche : il est derrière tout et couvre toujours.
    Rend None s'il n'y a rien du tout derrière."""
    if not entries and backdrop_rgb is None:
        return None
    rgba = np.zeros((h, w, 4), dtype=np.uint16)
    is_target = np.zeros((h, w), dtype=bool)
    filled = np.zeros((h, w), dtype=bool)
    for img, target in entries:
        src = _to_rgba(img)
        sh, sw = min(h, src.shape[0]), min(w, src.shape[1])
        here = np.zeros((h, w), dtype=bool)
        here[:sh, :sw] = src[:sh, :sw, 3] > 0
        new = here & ~filled          # première couche à couvrir ce pixel
        if not new.any():
            continue
        buf = np.zeros((h, w, 4), dtype=np.uint16)
        buf[:sh, :sw] = src[:sh, :sw]
        rgba[new] = buf[new]
        is_target[new] = target
        filled |= new
    if backdrop_rgb is not None:
        rest = ~filled
        if rest.any():
            r, g, b = backdrop_rgb
            rgba[rest] = np.array([r, g, b, 255], dtype=np.uint16)
            is_target[rest] = backdrop_is_target
    return BottomLayer(rgba, is_target)


def scene_blend_plan(scene) -> dict | None:
    """Ce que le canvas doit composer pour cette scène, ou None si rien.

    Rend {mode, eva, evb, evy, top_slots, bottom_slots, obj_role,
    backdrop_role} — des SLOTS et pas des images : le canvas seul sait où sont
    ses pixmaps, et ce module reste sans dépendance à lui.

    None dès que le réglage ne peut rien produire (mode « aucun », ou aucune
    première cible) : l'appelant saute alors tout le chemin de composition
    plutôt que de recalculer une image identique à la source."""
    from core.models.scene import (BLEND_NONE, BLEND_TOP, BLEND_BOTTOM,
                                   blend_role_of)
    mode = int(getattr(scene, "blend_mode", BLEND_NONE) or BLEND_NONE)
    if mode == BLEND_NONE:
        return None
    tops = [L.bg_slot for L in getattr(scene, "background_layers", [])
            if blend_role_of(L) == BLEND_TOP]
    bottoms = [L.bg_slot for L in getattr(scene, "background_layers", [])
               if blend_role_of(L) == BLEND_BOTTOM]
    obj_role = getattr(scene, "blend_obj_role", "") or ""
    if not tops and obj_role != BLEND_TOP:
        return None             # aucune première cible : rien n'est mélangé
    return {
        "mode": mode,
        "eva": int(getattr(scene, "blend_eva", BLEND_EV_MAX)),
        "evb": int(getattr(scene, "blend_evb", 0)),
        "evy": int(getattr(scene, "blend_evy", 0)),
        "top_slots": tops,
        "bottom_slots": bottoms,
        "obj_role": obj_role,
        "backdrop_role": getattr(scene, "blend_backdrop_role", "") or "",
    }
