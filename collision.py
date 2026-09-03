"""Collision geometry tests.

Only axis-aligned rectangles and circles are narrow-phase tested here -
no polygon collision or physics engine. entities.py's Shape hierarchy
also defines a Polygon type, but it's an unused data-shape seam (no
entity constructs one, no narrow-phase test exists for it); see
Polygon's docstring. With at most two tanks and a handful of live
projectiles, a broad phase (spatial hashing/grid) would add complexity
without measurable benefit, so every projectile is narrow-phase tested
directly against the terrain and each tank each step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import pygame

from entities import Tank, Terrain


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def circle_vs_rect(center: pygame.Vector2, radius: float, rect: pygame.Rect) -> bool:
    """True if a circle overlaps an axis-aligned rectangle."""
    closest_x = clamp(center.x, rect.left, rect.right)
    closest_y = clamp(center.y, rect.top, rect.bottom)
    dx = center.x - closest_x
    dy = center.y - closest_y
    return (dx * dx + dy * dy) <= radius * radius


@dataclass(frozen=True)
class CollisionResult:
    kind: str  # "ground" or "tank"
    point: pygame.Vector2
    tank_index: Optional[int] = None


def sweep_projectile(
    old_pos: pygame.Vector2,
    new_pos: pygame.Vector2,
    radius: float,
    terrain: Terrain,
    tanks: Sequence[Tank],
    owner_index: int,
) -> Optional[CollisionResult]:
    """Test a projectile's motion for one physics step against the world.

    Fast projectiles can cross an entire thin tank body within a single
    fixed timestep ("tunneling"). Rather than a full continuous-collision
    solve, this samples the straight-line segment from old_pos to new_pos
    at increments no larger than the projectile radius, which is cheap
    and sufficient for the speeds/timestep this game uses. The owning
    tank is skipped so a shot can never hit the tank that fired it.
    """
    delta = new_pos - old_pos
    distance = delta.length()
    steps = 1 if distance <= 0 else max(1, math.ceil(distance / max(radius, 1.0)))

    for step in range(1, steps + 1):
        t = step / steps
        sample = old_pos.lerp(new_pos, t)

        if sample.y + radius >= terrain.height_at(sample.x):
            return CollisionResult("ground", sample)

        for index, tank in enumerate(tanks):
            if index == owner_index or not tank.alive:
                continue
            if circle_vs_rect(sample, radius, tank.rect(terrain)):
                return CollisionResult("tank", sample, index)

    return None
