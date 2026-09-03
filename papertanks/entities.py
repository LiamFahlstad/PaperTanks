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

The Shape/Circle/Rectangle/Polygon geometry-value-type hierarchy - the
types collision_shape() below can return - lives in shapes.py, not here,
because it's genuinely unrelated to "what is a tank/projectile/terrain":
it has no notion of tanks, terrain, or the game world, only points and
radii. Keeping it in a separate leaf module (rather than bundled into
this one) is also what lets sprite_shape.py/sprite_cache.py depend on the
Shape types without depending on entities.py - see shapes.py's module
docstring for the full reasoning.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pygame

from . import config
from . import sprite_cache
from .shapes import Circle, Polygon, Rectangle, Shape


@dataclass(kw_only=True)
class WorldObject(ABC):
    """Base for anything that exists in the game world and is drawn.

    Carries exactly one stored field, sprite_key: an optional lookup
    key (assets/sprites/{key}.png) render.py uses to sprite-render this object
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
    in collision.py, dispatched by concrete Shape type. sweep_projectile()
    now calls this directly for every tank instead of tank.rect() - the
    "two ways to fetch the same geometry" tension this docstring used to
    flag is resolved by consolidating on collision_shape() as the single
    source, now that a second concrete Shape (Polygon, from Tank's
    sprite art) actually exists. tank.rect() is unchanged and still used
    for rendering/positioning/muzzle math; it's just no longer read
    directly for collision.
    """

    @abstractmethod
    def collision_shape(self, terrain: "Terrain") -> Shape: ...


class RigidBody(CollisionBody, ABC):
    """A CollisionBody whose motion is driven each tick by physics.py's
    gravity/integration functions, as opposed to a CollisionBody like
    Tank: it has its own velocity_x/friction integration (see
    World._apply_intent) for horizontal ground movement, but that's a
    separate, gravity-free model living in world.py, not a use of
    physics.py's apply_gravity/integrate_position - so Tank still isn't a
    RigidBody. aim/power/reload remain direct state changes, not physics.
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
    # Horizontal ground speed (px/s, +right/-left); the only stored motion
    # state a Tank carries. There's no stored y - rect()/muzzle_position()
    # below already re-derive vertical placement from terrain.height_at(x)
    # on every call, so a moving tank tracking the ground is "free" as long
    # as x itself changes; see World._apply_intent for the friction/
    # acceleration integration that updates x and velocity_x each tick.
    velocity_x: float = 0.0
    # sprite_key is inherited from WorldObject; kept opt-in per Tank via the
    # same constructor kwarg as before (e.g. Tank(..., sprite_key="tank1")).

    def rect(self, terrain: Terrain) -> pygame.Rect:
        """Axis-aligned solid body used for collision and drawing."""
        rect = pygame.Rect(0, 0, config.TANK_WIDTH, config.TANK_HEIGHT)
        rect.midbottom = (round(self.x), round(terrain.height_at(self.x)))
        return rect

    def collision_shape(self, terrain: Terrain) -> Shape:
        """Solid shape used for collision testing (see CollisionBody).

        Returns a world-space Polygon derived from this tank's sprite
        silhouette when sprite_key is set - a low-res polygon that hugs
        the actual painted tank shape (see sprite_shape.py) instead of
        its full bounding rect, so a shot that visually grazes empty
        (transparent) art near a corner doesn't register a hit. Falls
        back to the plain bounding Rectangle when sprite_key is None
        (only "tank1" has real art today; a tank with no sprite has no
        silhouette to derive one from). This is why the return type is
        the generic Shape rather than Rectangle: which concrete Shape a
        given Tank returns depends on whether it has art.

        sprite_cache.get_tank_collision_polygon() is imported at module
        top, same as any other dependency - there's no cycle to route
        around here: sprite_cache.py and sprite_shape.py both depend on
        shapes.py for Polygon, not on this module, so entities.py can
        depend on sprite_cache.py in the ordinary one-way direction (see
        shapes.py's module docstring). The underlying Polygon is cached
        inside sprite_cache (see its docstring), so this method is a cheap
        cache hit after the first call per (sprite_key, facing).
        """
        if self.sprite_key is None:
            return Rectangle.from_rect(self.rect(terrain))

        local_polygon = sprite_cache.get_tank_collision_polygon(
            self.sprite_key, self.facing
        )
        origin = pygame.Vector2(self.rect(terrain).topleft)
        return Polygon(points=tuple(origin + point for point in local_polygon.points))

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
