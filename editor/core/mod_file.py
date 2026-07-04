"""
core/mod_file.py — Parseur de fichiers MOD (ProTracker, tags M.K./xCHN).

Format binaire Amiga classique (31 instruments, table d'ordre, patterns 64
lignes). Utilisé par mod_render.py pour la preview audio du Sound Mixer —
seul le format ProTracker standard est supporté (pas XM/S3M/IT).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Tag 4 octets (offset 1080) -> nombre de canaux. Tag inconnu -> on suppose 4
# canaux (immense majorité des .mod en circulation).
_TAG_CHANNELS = {
    b"M.K.": 4, b"M!K!": 4, b"FLT4": 4, b"4CHN": 4,
    b"6CHN": 6,
    b"8CHN": 8, b"FLT8": 8, b"CD81": 8, b"OKTA": 8,
}


@dataclass
class ModSample:
    name: str
    length: int        # octets
    finetune: int       # -8..7 (non utilisé par le rendu v1, gardé pour référence)
    volume: int         # 0..64
    loop_start: int      # octets
    loop_length: int     # octets — <=2 : pas de boucle
    data: np.ndarray      # int8 mono, `length` échantillons

    @property
    def has_loop(self) -> bool:
        return self.loop_length > 2


@dataclass
class ModCell:
    sample: int   # 0 = pas de nouvel instrument déclenché sur ce cell
    period: int   # 0 = pas de nouvelle note
    effect: int   # 0x0-0xF
    param: int    # 0x00-0xFF


@dataclass
class ModFile:
    name: str
    num_channels: int
    samples: list[ModSample]              # index 0 = instrument #1 (les MOD indexent depuis 1)
    order: list[int]                      # position de lecture -> n° de pattern
    patterns: list[list[list[ModCell]]]   # [pattern][ligne][canal]


def _finetune_signed(nibble: int) -> int:
    return nibble - 16 if nibble >= 8 else nibble


def load_mod(path: Path) -> ModFile:
    data = path.read_bytes()

    name = data[0:20].rstrip(b"\x00").decode("latin-1", "ignore")

    headers = []
    off = 20
    for _ in range(31):
        s_name      = data[off:off + 22].rstrip(b"\x00").decode("latin-1", "ignore")
        length      = struct.unpack(">H", data[off + 22:off + 24])[0] * 2
        finetune    = _finetune_signed(data[off + 24] & 0x0F)
        volume      = min(data[off + 25], 64)
        loop_start  = struct.unpack(">H", data[off + 26:off + 28])[0] * 2
        loop_length = struct.unpack(">H", data[off + 28:off + 30])[0] * 2
        headers.append((s_name, length, finetune, volume, loop_start, loop_length))
        off += 30

    song_length = data[off]; off += 1
    off += 1  # position de restart — ignorée (v1)
    order = list(data[off:off + 128])[:song_length]
    off += 128

    tag = bytes(data[off:off + 4])
    num_channels = _TAG_CHANNELS.get(tag, 4)
    off += 4

    num_patterns = (max(order) + 1) if order else 0
    patterns: list[list[list[ModCell]]] = []
    for _p in range(num_patterns):
        pattern = []
        for _row in range(64):
            row = []
            for _ch in range(num_channels):
                b0, b1, b2, b3 = data[off], data[off + 1], data[off + 2], data[off + 3]
                off += 4
                row.append(ModCell(
                    sample=(b0 & 0xF0) | (b2 >> 4),
                    period=((b0 & 0x0F) << 8) | b1,
                    effect=b2 & 0x0F,
                    param=b3,
                ))
            pattern.append(row)
        patterns.append(pattern)

    samples = []
    for s_name, length, finetune, volume, loop_start, loop_length in headers:
        raw = data[off:off + length]
        off += length
        arr = np.frombuffer(raw, dtype=np.int8).copy() if raw else np.zeros(0, dtype=np.int8)
        if arr.size < length:
            # Fichier tronqué / sample coupé : compléter par du silence plutôt que planter.
            arr = np.pad(arr, (0, length - arr.size))
        samples.append(ModSample(s_name, length, finetune, volume, loop_start, loop_length, arr))

    return ModFile(name=name, num_channels=num_channels, samples=samples,
                    order=order, patterns=patterns)
