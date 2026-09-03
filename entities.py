"""Plain data holders for world objects.

These classes intentionally contain only state plus small geometric
queries (rect(), muzzle_position(), collision_shape()). Simulation
rules live in world.py, collision tests live in collision.py, and
drawing lives in render.py - keeping "what an object is" separate from
"what happens to it" and "how it looks".

WorldObject/CollisionBody/RigidBody form a small ABC hierarchy that
groups entities by capability: does it exist and draw (WorldObject),
does it have a solid shape (CollisionBody), is it physics-integrated
(RigidBody). It's a seam for future entity types, not something the
current four classes need to function. WorldObject carries exactly one
stored field, sprite_key (see its docstring for why that one field is
an exception to "no shared state").

Shape/Circle/Rectangle/Polygon form a second, unrelated small
hierarchy: the geometry types collision_shape() can return. Like the
WorldObject family, Shape itself carries no fields or behavior - it's
a nominal-typing seam, not a place for shared geometry math (that stays
in collision.py, dispatched by concrete type).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pygame

import config


class Shape:
    """Common base for the game's collision-shape geometry types.

    No stored fields or behavior of its own, same reasoning as
    WorldObject below: it exists so CollisionBody.collision_shape() can
    have one return type ("some Shape") instead of a widening union,
    not to host shared geometry logic. Narrow-phase overlap tests
    (circle_vs_rect, etc.) stay in collision.py, dispatched by concrete
    type - this hierarchy has no method of its own for that, the same
    way collision_shape() itself has no current polymorphic caller
    (see CollisionBody's docstring).
    """


@dataclass(frozen=True)
class Circle(Shape):
    """A circular collision shape - pygame has no built-in circle type."""

    center: pygame.Vector2
    radius: float


@dataclass(frozen=True)
class Rectangle(Shape):
    """An axis-aligned rectangular collision shape.

    Wraps the same geometry Tank.rect() already returns as a raw
    pygame.Rect, as an explicit Circle-style value type (a Vector2 plus
    scalar dimensions) rather than wrapping pygame.Rect directly, so
    every Shape subclass has the same "plain, frozen, geometry-only"
    shape. Tank.rect() itself is unchanged and still returns
    pygame.Rect - collision.py keeps calling that directly (see
    CollisionBody's docstring for why); this type is what
    Tank.collision_shape() returns instead.
    """

    topleft: pygame.Vector2
    width: float
    height: float

    @classmethod
    def from_rect(cls, rect: pygame.Rect) -> "Rectangle":
        return cls(topleft=pygame.Vector2(rect.topleft), width=rect.width, height=rect.height)


@dataclass(frozen=True)
class Polygon(Shape):
    """A closed polygon collision shape defined by its vertices.

    Added as a data-shape seam ahead of concrete need - the same
    judgment call ARCHITECTURE.md documents for the WorldObject
    hierarchy itself - not because any current entity needs polygonal
    collision. No entity constructs one, and collision.py has no
    polygon narrow-phase test (no polygon-vs-circle/rect function);
    collision.py's module docstring still accurately states only
    rectangles and circles are tested today. Add the narrow-phase math
    only once a concrete entity needs it.
    """

    points: tuple[pygame.Vector2, ...]


@dataclass(kw_only=True)
class WorldObject(ABC):
    """Base for anything that exists in the game world and is drawn.

    Carries exactly one stored field, sprite_key: an optional lookup
    key (Sprites/{key}.png) render.py uses to sprite-render this object
    instead of its primitive-shape fallback (colored rect/circle).
    Every other kind of state stays off this base - position
    representation still differs per entity (Tank is terrain-relative;
    Projectile/Explosion store a free Vector2), so a shared *position*
    field is still rejected for the same reason as before. sprite_key
    is different: its type and meaning (Optional[str], "None means use
    the primitive fallback") are identical for every entity, so hanging
    it here lets any WorldObject opt in without redeclaring the field
    or widening collision/layout code, which never looks at it.

    Subclasses use @dataclass(kw_only=True) too (matching this class),
    which sidesteps the dataclass field-ordering trap of a base-class
    field landing before a subclass's own required fields - every call
    site in this codebase already constructs entities with keyword
    arguments, so this costs nothing at the call sites.
    """

    sprite_key: Optional[str] = None


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
    def collision_shape(self, terrain: "Terrain") -> Shape:
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


@dataclass(kw_only=True)
class Tank(CollisionBody):
    x: float
    facing: int  # +1 faces right, -1 faces left
    color: tuple
    hp: float = config.TANK_MAX_HP
    aim_deg: float = config.TANK_AIM_START_DEG
    power: float = config.TANK_POWER_START
    reload_timer: float = 0.0
    alive: bool = True
    # sprite_key is inherited from WorldObject; kept opt-in per Tank via the
    # same constructor kwarg as before (e.g. Tank(..., sprite_key="tank1")).

    def rect(self, terrain: Terrain) -> pygame.Rect:
        """Axis-aligned solid body used for collision and drawing."""
        rect = pygame.Rect(0, 0, config.TANK_WIDTH, config.TANK_HEIGHT)
        rect.midbottom = (round(self.x), round(terrain.height_at(self.x)))
        return rect

    def collision_shape(self, terrain: Terrain) -> Rectangle:
        return Rectangle.from_rect(self.rect(terrain))

    def aim_direction(self) -> pygame.Vector2:
        angle_rad = math.radians(self.aim_deg)
        return pygame.Vector2(math.cos(angle_rad) * self.facing, -math.sin(angle_rad))

    def muzzle_position(self, terrain: Terrain) -> pygame.Vector2:
        """Barrel-tip world position, used both for firing and drawing."""
        rect = self.rect(terrain)
        origin = pygame.Vector2(rect.centerx, rect.top)
        return origin + self.aim_direction() * config.TANK_BARREL_LENGTH


@dataclass(kw_only=True)
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


@dataclass(kw_only=True)
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
