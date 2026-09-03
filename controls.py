"""Translate raw Pygame key state into per-tank Intents.

(Named `controls` rather than `input` to avoid shadowing the builtin.)

Held keys are sampled once per real frame (via pygame.key.get_pressed())
and the same Intent list is fed into every fixed physics tick that runs
within that frame. Aim/power rates are applied inside World.step using
the fixed dt, so the resulting aim/power values are frame-rate
independent even though the *sampling* of "is this key down right now"
is inherently tied to real frame rate - a standard and acceptable
tradeoff for real-time input.

Firing has no debounce here: holding the fire key simply means "fire
whenever the cooldown allows it", and World's reload_timer is the single
source of truth for shot pacing.
"""

from __future__ import annotations

from typing import List, Sequence

import config
from world import Intent


def build_intents(keys_pressed: Sequence[bool]) -> List[Intent]:
    p1 = Intent(
        aim_delta=_axis(keys_pressed, config.P1_AIM_UP, config.P1_AIM_DOWN),
        power_delta=_axis(keys_pressed, config.P1_POWER_UP, config.P1_POWER_DOWN),
        fire=keys_pressed[config.P1_FIRE],
    )
    p2 = Intent(
        aim_delta=_axis(keys_pressed, config.P2_AIM_UP, config.P2_AIM_DOWN),
        power_delta=_axis(keys_pressed, config.P2_POWER_UP, config.P2_POWER_DOWN),
        fire=keys_pressed[config.P2_FIRE],
    )
    return [p1, p2]


def _axis(keys_pressed: Sequence[bool], positive_key: int, negative_key: int) -> float:
    value = 0.0
    if keys_pressed[positive_key]:
        value += 1.0
    if keys_pressed[negative_key]:
        value -= 1.0
    return value
