"""
core/models/tile_codec.py — le format binaire d'une tuile et d'une entrée de
carte, et rien d'autre.

Deux encodages, tous deux dictés par le matériel ou par le stockage JSON :

- **La tuile** — 64 index de palette, rangés en chaîne hexadécimale dans le
  sidecar d'un fond (un caractère par pixel en 4bpp, deux en 8bpp). Plus les
  deux miroirs, qui réordonnent ces 64 index.
- **L'entrée de carte** (*screen entry*) — le mot de 16 bits que la GBA lit dans
  un screenblock : numéro de tuile, miroirs, banque de palette.

**Module FEUILLE : il n'importe rien du projet, et ne doit jamais le faire.**
C'est ce qui lui permet d'être appelé depuis n'importe quelle couche sans créer
de boucle. Il vivait auparavant dans `core/bg_import.py`, c'est-à-dire dans la
couche import de l'éditeur : les modèles, la génération et le canvas devaient
tous remonter jusque-là pour lire une tuile, et `bg_import` redescendait vers la
génération — d'où trois modules qui s'importaient mutuellement, en imports
différés au fond des fonctions pour que Python ne s'en aperçoive pas.

Rangé sous `models/` parce que c'est la couche la plus basse que tous ses
appelants partagent déjà ; il ne décrit pourtant aucune donnée de projet, juste
la façon dont le matériel lit ces octets.
"""
from __future__ import annotations


# ── La tuile : 64 index de palette ↔ chaîne hexadécimale ──────────

def tile_to_hex(tile: list) -> str:
    """Tuile (64 index 0-15) -> 64 caractères hex (1 nibble/index). Compact + JSON."""
    return "".join("%x" % (i & 0xF) for i in tile)


def hex_to_tile(s: str) -> list:
    return [int(ch, 16) for ch in s]


def tile_to_hex8(tile: list) -> str:
    """Tuile 8bpp (64 index 0-255) -> 128 caractères hex (2/octet)."""
    return "".join("%02x" % (i & 0xFF) for i in tile)


def hex_to_tile8(s: str) -> list:
    return [int(s[i:i + 2], 16) for i in range(0, len(s), 2)]


# ── Les miroirs : la même tuile lue à l'envers ────────────────────
# Le matériel les applique à l'affichage ; ici on les calcule pour reconnaître
# qu'une tuile est le miroir d'une autre (déduplication) et pour dessiner un
# aperçu fidèle.

def flip_h(grid: tuple) -> tuple:
    return tuple(grid[r * 8 + (7 - c)] for r in range(8) for c in range(8))


def flip_v(grid: tuple) -> tuple:
    return tuple(grid[(7 - r) * 8 + c] for r in range(8) for c in range(8))


# ── L'entrée de carte : un mot de 16 bits ─────────────────────────

def pack_se(tile_id: int, pal_bank: int, flip_h: bool, flip_v: bool) -> int:
    """Screen entry GBA : tile_id (0-9) | flip_h (10) | flip_v (11) | pal_bank (12-15).

    Les deux derniers paramètres masquent les fonctions du même nom ci-dessus —
    ce sont les DRAPEAUX que le mot porte, pas l'opération. Rien ici ne les
    appelle ; si un jour c'était nécessaire, il faudrait renommer les
    paramètres."""
    return (tile_id & 0x3FF) | (int(flip_h) << 10) | (int(flip_v) << 11) | ((pal_bank & 0xF) << 12)


def unpack_se(se: int) -> tuple[int, int, bool, bool]:
    return se & 0x3FF, (se >> 12) & 0xF, bool(se & 0x400), bool(se & 0x800)
