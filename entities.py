"""Plain data holders for world objects.

These classes intentionally contain only state plus small geometric
queries (rect(), muzzle_position()). Simulation rules live in world.py,
collision tests live in collision.py, and drawing lives in render.py -
keeping "what an object is" separate from "what happens to it" and "how
it looks".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pygame

import config


class Terrain:
    """Ground surface the tanks stand on and projectiles collide with.

    Flat for this first slice, but every caller goes through height_at(x)
    rather than touching ground_y directly, so swapping in a heightmap or
    destructible terrain later doesn't require changing tank/projectile/
    collision code.
    """

    def __init__(self, ground_y: float = config.GROUND_Y) -> None:
        self.ground_y = ground_y

    def height_at(self, x: float) -> float:
        return self.ground_y


@dataclass
class Tank:
    x: float
    facing: int  # +1 faces right, -1 faces left
    color: tuple
    hp: float = config.TANK_MAX_HP
    aim_deg: float = config.TANK_AIM_START_DEG
    power: float = config.TANK_POWER_START
    reload_timer: float = 0.0
    alive: bool = True

    def rect(self, terrain: Terrain) -> pygame.Rect:
        """Axis-aligned solid body used for collision and drawing."""
        rect = pygame.Rect(0, 0, config.TANK_WIDTH, config.TANK_HEIGHT)
        rect.midbottom = (round(self.x), round(terrain.height_at(self.x)))
        return rect

    def aim_direction(self) -> pygame.Vector2:
        angle_rad = math.radians(self.aim_deg)
        return pygame.Vector2(math.cos(angle_rad) * self.facing, -math.sin(angle_rad))

    def muzzle_position(self, terrain: Terrain) -> pygame.Vector2:
        """Barrel-tip world position, used both for firing and drawing."""
        rect = self.rect(terrain)
        origin = pygame.Vector2(rect.centerx, rect.top)
        return origin + self.aim_direction() * config.TANK_BARREL_LENGTH


@dataclass
class Projectile:
    position: pygame.Vector2
    velocity: pygame.Vector2
    owner: int  # index into World.tanks of the firing tank; never hits its owner
    radius: float = config.PROJECTILE_RADIUS
    age: float = 0.0
    prev_position: Optional[pygame.Vector2] = None

    def __post_init__(self) -> None:
        # Defaults prev_position to the spawn point so the very first
        # rendered frame (before any physics step) doesn't interpolate
        # from an unset value.
        if self.prev_position is None:
            self.prev_position = pygame.Vector2(self.position)


@dataclass
class Explosion:
    """Purely cosmetic hit feedback; carries no gameplay weight."""

    position: pygame.Vector2
    timer: float = 0.0

    @property
    def progress(self) -> float:
        """0 at spawn, 1 when finished."""
        return min(1.0, self.timer / config.EXPLOSION_DURATION)

    @property
    def finished(self) -> bool:
        return self.timer >= config.EXPLOSION_DURATION
