"""Geometry value-types used as collision shapes: Circle, Rectangle, Polygon.

This is a leaf module - it imports nothing from this project except
pygame itself, and nothing else in the project may import it in a way
that reaches back here. That's deliberate: these types describe *shape*
only ("a circle with this center and radius", "a polygon with these
points"), with zero knowledge of tanks, projectiles, terrain, sprites, or
the game world. Putting them in entities.py (which does know about all of
those) was the actual bug in an earlier pass - it forced sprite_shape.py
(a pure geometry-construction module with no business knowing about tanks
or terrain) to import entities.py just to build a Polygon, which in turn
made entities.py's own import of sprite_cache.py (which needs Polygon
too) close a three-module cycle. Moving Shape/Circle/Rectangle/Polygon
here removes the cycle at its root instead of routing around it with a
TYPE_CHECKING-guarded import or a deferred function-local import: every
module that needs these types (entities.py, collision.py, sprite_shape.py,
sprite_cache.py) can import shapes.py directly, at module top, and none of
them import each other in the reverse direction.

CollisionBody.collision_shape() (entities.py) returns these types;
collision.py's narrow-phase tests (circle_vs_rect, circle_vs_polygon)
consume them. Narrow-phase overlap math itself stays in collision.py, not
here - this module only describes geometry, it never tests it against
anything.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


class Shape:
    """Common base for the game's collision-shape geometry types.

    No stored fields or behavior of its own - it exists so
    CollisionBody.collision_shape() (entities.py) can declare one return
    type ("some Shape") instead of a widening union, not to host shared
    geometry logic. Narrow-phase overlap tests (circle_vs_rect,
    circle_vs_polygon, etc.) stay in collision.py, dispatched by concrete
    type. collision.sweep_projectile() calls collision_shape() for every
    tank and dispatches on whichever concrete Shape (Rectangle or Polygon)
    comes back - see entities.CollisionBody's docstring.
    """


@dataclass(frozen=True)
class Circle(Shape):
    """A circular collision shape - pygame has no built-in circle type."""

    center: pygame.Vector2
    radius: float


@dataclass(frozen=True)
class Rectangle(Shape):
    """An axis-aligned rectangular collision shape.

    Wraps the same geometry Tank.rect() (entities.py) already returns as
    a raw pygame.Rect, as an explicit Circle-style value type (a Vector2
    plus scalar dimensions) rather than wrapping pygame.Rect directly, so
    every Shape subclass has the same "plain, frozen, geometry-only"
    shape. Tank.rect() itself is unchanged and still returns pygame.Rect
    (used for rendering/positioning/muzzle math); this type is what
    Tank.collision_shape() returns instead, for collision.
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

    In active use for tanks with sprite art: sprite_shape.py's mask-derived
    outline is built into a Polygon by polygon_from_sprite_mask(), cached
    per (sprite_key, facing) by sprite_cache.py, and translated to world
    space by Tank.collision_shape() (entities.py) for any tank with a real
    sprite_key (currently only "tank1" has art; a Tank with sprite_key=None
    still returns Rectangle). collision.py's circle_vs_polygon() is the
    matching narrow-phase test, used by sweep_projectile() whenever a
    tank's collision_shape() returns a Polygon.
    """

    points: tuple[pygame.Vector2, ...]
