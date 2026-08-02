"""Géométrie de découpe nine-slice — PURE (sans Qt), donc testable en tête.

Un nine-slice étire un cadre sans déformer ses coins : l'image source est
découpée en 9 cases par 4 marges (left/right/top/bottom), puis reposée sur le
rectangle cible — les 4 COINS à taille naturelle, les 4 BORDS et le CENTRE
RÉPÉTÉS (tuilés) le long de l'axe qu'ils remplissent. C'est la sémantique
matérielle GBA (coins = tuiles fixes, bords/centre = tuiles répétées) ; le rendu
Qt de l'éditeur la reproduit en tuilant plutôt qu'en étirant.

`nine_slice_rects` ne fait que l'arithmétique : elle rend, pour chaque case, le
rectangle SOURCE, le rectangle DESTINATION, et un drapeau `tile` (faux pour un
coin, dessiné 1:1 ; vrai pour un bord/centre, à tuiler). L'appelant Qt boucle
dessus (`drawPixmap` si coin, `drawTiledPixmap` sinon)."""
from __future__ import annotations


def _clamp_margins(l: int, r: int, span: int) -> tuple[int, int]:
    """Empêche deux marges opposées de dépasser la taille disponible : si
    `l + r > span`, on les réduit proportionnellement pour que le milieu ne soit
    jamais négatif (un panel plus étroit que ses deux coins réunis)."""
    l = max(0, int(l))
    r = max(0, int(r))
    if l + r <= span:
        return l, r
    if l + r == 0:
        return 0, 0
    # réduction proportionnelle, en gardant la somme = span
    nl = span * l // (l + r)
    return nl, span - nl


def nine_slice_rects(src_w: int, src_h: int,
                     left: int, right: int, top: int, bottom: int,
                     dst_w: int, dst_h: int) -> list[dict]:
    """Les 9 cases, chacune {src:(x,y,w,h), dst:(x,y,w,h), tile:bool}.

    Les marges sont bornées à la SOURCE (une coupe ne peut pas dépasser l'image)
    puis à la DESTINATION (les coins ne peuvent pas se chevaucher dans une petite
    zone). Une case de taille nulle (bord/centre écrasé) est omise."""
    sl, sr = _clamp_margins(left, right, src_w)
    st, sb = _clamp_margins(top, bottom, src_h)
    dl, dr = _clamp_margins(sl, sr, dst_w)      # coins bornés à la destination
    dt, db = _clamp_margins(st, sb, dst_h)

    # (offset, taille) des 3 tranches d'un axe, côté source puis destination.
    def bands(m0: int, m1: int, total: int):
        return [(0, m0), (m0, total - m0 - m1), (total - m1, m1)]

    sx = bands(sl, sr, src_w)
    sy = bands(st, sb, src_h)
    dx = bands(dl, dr, dst_w)
    dy = bands(dt, db, dst_h)

    out: list[dict] = []
    for row in range(3):
        for col in range(3):
            s_ox, s_w = sx[col]
            s_oy, s_h = sy[row]
            d_ox, d_w = dx[col]
            d_oy, d_h = dy[row]
            if s_w <= 0 or s_h <= 0 or d_w <= 0 or d_h <= 0:
                continue          # case écrasée : rien à dessiner
            is_corner = col in (0, 2) and row in (0, 2)
            out.append({
                "src": (s_ox, s_oy, s_w, s_h),
                "dst": (d_ox, d_oy, d_w, d_h),
                "tile": not is_corner,
            })
    return out
