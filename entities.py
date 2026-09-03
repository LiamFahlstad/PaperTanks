"""Plain data holders for world objects.

These classes intentionally contain only state plus small geometric
queries (rect(), muzzle_position(), collision_shape()). Simulation
rules live in world.py, collision tests live in collision.py, and
drawing lives in render.py - keeping "what an object is" separate from
"what happens to it" and "how it looks".

WorldObject/CollisionBody/RigidBody form a small ABC hierarchy (each
carries zero stored fields - see WorldObject's docstring for why) that
groups entities by capability: does it exist and draw (WorldObject),
does it have a solid shape (CollisionBody), is it physics-integrated
(RigidBody). It's a seam for future entity types, not something the
current four classes need to function.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pygame

import config


@dataclass(frozen=True)
class Circle:
    """A circular collision shape - pygame has no built-in circle type."""

    center: pygame.Vector2
    radius: float


class WorldObject(ABC):
    """Base for anything that exists in the game world and is drawn.

    No stored fields: position representation differs per entity (Tank
    is terrain-relative; Projectile/Explosion store a free Vector2), so
    the shared contract is "is a kind of thing," not shared state.
    render.py still dispatches on concrete type for now - this exists
    so future entities/renderer code can reason about "things in the
    world" as one family without every entity forcing the same layout.
    """


class CollisionBody(WorldObject, ABC):
    """A WorldObject with a solid shape, testable for collision.

    collision_shape() is a query, not behavior (same category as the
    existing rect()/muzzle_position()) - the overlap math itself stays
    in collision.py. Currently only Tank's rect() feeds
    sweep_projectile directly (kept as-is, to avoid two ways to fetch
    the same geometry); collision_shape() is the seam a second
    collision body type or a generic collision loop will use once one
    exists.
    """

    @abstractmethod
    def collision_shape(self, terrain: "Terrain") -> "pygame.Rect | Circle":
        ...


class RigidBody(CollisionBody, ABC):
    """A CollisionBody whose motion is driven each tick by physics.py's
    gravity/integration functions, as opposed to a CollisionBody like
    Tank that never moves under simulated forces (aim/power/reload are
    direct state changes, not physics).
    """


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
class Tank(CollisionBody):
    x: float
    facing: int  # +1 faces right, -1 faces left
    color: tuple
    hp: float = config.TANK_MAX_HP
    aim_deg: float = config.TANK_AIM_START_DEG
    power: float = config.TANK_POWER_START
    reload_timer: float = 0.0
    alive: bool = True
    sprite_key: Optional[str] = None  # looked up as Sprites/{key}.png by render.py; None falls back to a colored rect

    def rect(self, terrain: Terrain) -> pygame.Rect:
        """Axis-aligned solid body used for collision and drawing."""
        rect = pygame.Rect(0, 0, config.TANK_WIDTH, config.TANK_HEIGHT)
        rect.midbottom = (round(self.x), round(terrain.height_at(self.x)))
        return rect

    def collision_shape(self, terrain: Terrain) -> pygame.Rect:
        return self.rect(terrain)

    def aim_direction(self) -> pygame.Vector2:
        angle_rad = math.radians(self.aim_deg)
        return pygame.Vector2(math.cos(angle_rad) * self.facing, -math.sin(angle_rad))

    def muzzle_position(self, terrain: Terrain) -> pygame.Vector2:
        """Barrel-tip world position, used both for firing and drawing."""
        rect = self.rect(terrain)
        origin = pygame.Vector2(rect.centerx, rect.top)
        return origin + self.aim_direction() * config.TANK_BARREL_LENGTH


@dataclass
class Projectile(RigidBody):
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

    def collision_shape(self, terrain: Terrain) -> Circle:
        return Circle(self.position, self.radius)


@dataclass
class Explosion(WorldObject):
    """Purely cosmetic hit feedback; carries no gameplay weight and no
    collision shape - it's a WorldObject, not a CollisionBody, so the
    type system states it never participates in a collision test."""

    position: pygame.Vector2
    timer: float = 0.0

    @property
    def progress(self) -> float:
        """0 at spawn, 1 when finished."""
        return min(1.0, self.timer / config.EXPLOSION_DURATION)

    @property
    def finished(self) -> bool:
        return self.timer >= config.EXPLOSION_DURATION
