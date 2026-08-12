"""
core/mod_render.py — Rejoue un ModFile en PCM, façon mixeur logiciel Maxmod GBA.

Objectif : preview qui *sonne* comme le rendu en jeu, pas un lecteur MOD
desktop haute fidélité. Deux choix pilotent ça :
  - taux de mixage réduit (GBA_MIX_RATE) au lieu de 44.1kHz
  - lecture des échantillons au plus proche voisin (pas d'interpolation
    linéaire) — le mixeur logiciel du GBA n'interpole pas non plus.

Effets ProTracker implémentés : arpeggio, portamento up/down/tone, vibrato,
volume slide (+ variantes fines E1/E2/EA/EB), sample offset, position jump,
pattern break, set speed/tempo, note cut (EC). Effets plus rares (pattern
loop E6, note delay ED, tremolo 7xx, panoramique 8xx…) ignorés — suffisant
pour une preview fidèle sans viser l'exactitude bit-à-bit de Maxmod.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .mod_file import ModFile

GBA_MIX_RATE = 13379          # Hz — taux "qualité standard" des presets Maxmod GBA
AMIGA_PAL_CLOCK = 7093789.2   # Hz — horloge de référence period -> fréquence
_MAX_VISITED = 4096           # anti-boucle infinie sur des patterns qui se rebouclent


@dataclass
class _Channel:
    sample_idx: int = -1
    period: int = 0
    volume: float = 0.0
    pos: float = 0.0
    porta_target: int = 0
    porta_speed: int = 0
    vibrato_pos: int = 0
    vibrato_speed: int = 0
    vibrato_depth: int = 0
    cut_tick: int = -1


def _period_to_step(period: float, mix_rate: int) -> float:
    if period <= 0:
        return 0.0
    return (AMIGA_PAL_CLOCK / (period * 2)) / mix_rate


def _clamp_period(period: int) -> int:
    return max(56, min(1712, period))


def _slide_toward(period: int, target: int, step: int) -> int:
    if period < target:
        return min(target, period + step)
    if period > target:
        return max(target, period - step)
    return period


def render_mod(mod: ModFile, mix_rate: int = GBA_MIX_RATE) -> np.ndarray:
    """Retourne un tableau int16 stéréo entrelacé (frames, 2)."""
    n_ch = mod.num_channels
    channels = [_Channel() for _ in range(n_ch)]
    # Panoramique dur façon Amiga : canaux 0/3 à gauche, 1/2 à droite (motif
    # répété par groupe de 4 pour les MOD 6/8 voies).
    pan_left = [(i % 4) in (0, 3) for i in range(n_ch)]

    speed = 6
    bpm = 125
    order_pos = 0
    row = 0
    visited: set[tuple[int, int]] = set()

    out_l: list[np.ndarray] = []
    out_r: list[np.ndarray] = []

    def render_tick(effective_periods: list[float]) -> None:
        n = round(mix_rate * 2.5 / bpm)
        if n <= 0:
            return
        left = np.zeros(n, dtype=np.float32)
        right = np.zeros(n, dtype=np.float32)
        for ci, ch in enumerate(channels):
            if ch.sample_idx < 0 or ch.volume <= 0:
                continue
            samp = mod.samples[ch.sample_idx]
            if samp.data.size == 0:
                continue
            step = effective_periods[ci]
            if step <= 0:
                continue
            positions = ch.pos + step * np.arange(n, dtype=np.float64)
            length = samp.length
            if samp.has_loop:
                loop_start, loop_len = samp.loop_start, samp.loop_length
                over = positions >= loop_start
                positions = np.where(
                    over,
                    loop_start + np.mod(positions - loop_start, loop_len),
                    positions,
                )
            valid = positions < length
            idx = np.clip(positions.astype(np.int64), 0, max(length - 1, 0))
            vals = samp.data[idx].astype(np.float32)
            vals[~valid] = 0.0
            gain = ch.volume / 64.0
            if pan_left[ci]:
                left += vals * gain
            else:
                right += vals * gain
            # Avancer la position réelle du canal (fin de ce tick)
            last_pos = ch.pos + step * n
            if samp.has_loop and last_pos >= samp.loop_start:
                last_pos = samp.loop_start + math.fmod(last_pos - samp.loop_start, samp.loop_length)
            ch.pos = last_pos
            if not samp.has_loop and last_pos >= length:
                ch.sample_idx = -1  # fin de sample non bouclé : canal s'éteint
        out_l.append(left)
        out_r.append(right)

    while order_pos < len(mod.order):
        pattern_idx = mod.order[order_pos]
        if pattern_idx >= len(mod.patterns):
            order_pos += 1
            row = 0
            continue
        pattern = mod.patterns[pattern_idx]
        looped_out = False

        while row < 64:
            key = (order_pos, row)
            if key in visited or len(visited) > _MAX_VISITED:
                looped_out = True
                break
            visited.add(key)

            cells = pattern[row]
            next_order_jump: int | None = None
            next_row_break: int | None = None

            # ── Tick 0 : déclenchement de note + effets "immédiats" ──
            for ci, cell in enumerate(cells):
                ch = channels[ci]

                if cell.sample != 0 and cell.sample <= len(mod.samples):
                    ch.sample_idx = cell.sample - 1
                    ch.volume = float(mod.samples[ch.sample_idx].volume)
                if cell.period != 0:
                    if cell.effect in (0x3, 0x5):
                        ch.porta_target = cell.period
                    else:
                        ch.period = cell.period
                        ch.pos = 0.0

                ch.cut_tick = -1
                e, p = cell.effect, cell.param
                if e == 0x3 and p:
                    ch.porta_speed = p * 4
                elif e in (0x4, 0x6) and p:
                    ch.vibrato_speed, ch.vibrato_depth = (p >> 4), (p & 0x0F)
                elif e == 0x9 and p:
                    ch.pos = float(p) * 256
                elif e == 0xB:
                    next_order_jump = p
                elif e == 0xD:
                    next_row_break = (p >> 4) * 10 + (p & 0x0F)
                elif e == 0xC:
                    ch.volume = min(64.0, float(p))
                elif e == 0xF and p:
                    if p < 32:
                        speed = p
                    else:
                        bpm = p
                elif e == 0xE:
                    sub, sp = (p >> 4), (p & 0x0F)
                    if sub == 0x1:
                        ch.period = _clamp_period(ch.period - sp * 4)
                    elif sub == 0x2:
                        ch.period = _clamp_period(ch.period + sp * 4)
                    elif sub == 0xA:
                        ch.volume = min(64.0, ch.volume + sp)
                    elif sub == 0xB:
                        ch.volume = max(0.0, ch.volume - sp)
                    elif sub == 0xC:
                        ch.cut_tick = 0 if sp == 0 else sp
                        if ch.cut_tick == 0:
                            ch.volume = 0.0

            # ── Ticks 0..speed-1 : effets continus + rendu ──
            for tick in range(speed):
                if tick > 0:
                    for ci, cell in enumerate(cells):
                        ch = channels[ci]
                        e, p = cell.effect, cell.param
                        if e == 0x1:
                            ch.period = _clamp_period(ch.period - p * 4)
                        elif e == 0x2:
                            ch.period = _clamp_period(ch.period + p * 4)
                        elif e == 0x3:
                            ch.period = _slide_toward(ch.period, ch.porta_target, ch.porta_speed)
                        elif e == 0x5:
                            ch.period = _slide_toward(ch.period, ch.porta_target, ch.porta_speed)

                        if e in (0xA, 0x5, 0x6):
                            up, down = (p >> 4), (p & 0x0F)
                            if up:
                                ch.volume = min(64.0, ch.volume + up)
                            elif down:
                                ch.volume = max(0.0, ch.volume - down)

                        if e in (0x4, 0x6):
                            ch.vibrato_pos = (ch.vibrato_pos + ch.vibrato_speed) & 63

                        if e == 0xE and (p >> 4) == 0xC and ch.cut_tick == tick:
                            ch.volume = 0.0

                effective: list[float] = []
                for ci, cell in enumerate(cells):
                    ch = channels[ci]
                    period: float = ch.period
                    if cell.effect == 0x0 and cell.param and period and tick % 3 != 0:
                        semis = (cell.param >> 4) if tick % 3 == 1 else (cell.param & 0x0F)
                        period = period / (2 ** (semis / 12.0))
                    elif cell.effect in (0x4, 0x6) and ch.vibrato_depth and period:
                        period = period + ch.vibrato_depth * math.sin(2 * math.pi * ch.vibrato_pos / 64.0)
                    effective.append(_period_to_step(period, mix_rate))

                render_tick(effective)

            if next_row_break is not None or next_order_jump is not None:
                order_pos = next_order_jump if next_order_jump is not None else order_pos + 1
                row = next_row_break if next_row_break is not None else 0
                break
            row += 1
        else:
            order_pos += 1
            row = 0
            continue

        if looped_out:
            break

    if not out_l:
        return np.zeros((0, 2), dtype=np.int16)

    left = np.concatenate(out_l)
    right = np.concatenate(out_r)
    # Gain global : les échantillons MOD sont des int8 (-128..127) pondérés par
    # volume/64 ; on remet à l'échelle int16 avec un peu de marge pour limiter
    # l'écrêtage quand plusieurs canaux forts se superposent (comportement
    # "authentique" GBA : ça peut quand même saturer, comme sur la vraie console).
    scale = 190.0
    left = np.clip(left * scale, -32768, 32767).astype(np.int16)
    right = np.clip(right * scale, -32768, 32767).astype(np.int16)
    stereo = np.empty((left.size, 2), dtype=np.int16)
    stereo[:, 0] = left
    stereo[:, 1] = right
    return stereo
