"""Collision geometry tests.

Circles, axis-aligned rectangles, and simple polygons (convex or
concave, but non-self-intersecting) are narrow-phase tested here - still
no physics-engine integration. shapes.py's Shape hierarchy has three
concrete types (Circle, Rectangle, Polygon); Tank.collision_shape()
(entities.py) returns whichever one applies - a sprite-derived Polygon
(see sprite_shape.py/sprite_cache.py) for a tank with real art (currently
only "tank1"), or a Rectangle fallback when a tank has no sprite_key, so
there's no art to derive a silhouette from. sweep_projectile() dispatches
on the concrete Shape type collision_shape() hands back rather than
assuming one shape per entity type - see circle_vs_rect()/
circle_vs_polygon() below. With at most two tanks and a handful of live
projectiles, a broad phase (spatial hashing/grid) would add complexity
without measurable benefit, so every projectile is narrow-phase tested
directly against the terrain and each tank each step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import pygame

from .entities import Tank, Terrain
from .shapes import Polygon, Rectangle, Shape


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def circle_vs_rect(center: pygame.Vector2, radius: float, rect: pygame.Rect) -> bool:
    """True if a circle overlaps an axis-aligned rectangle."""
    closest_x = clamp(center.x, rect.left, rect.right)
    closest_y = clamp(center.y, rect.top, rect.bottom)
    dx = center.x - closest_x
    dy = center.y - closest_y
    return (dx * dx + dy * dy) <= radius * radius


def _point_in_polygon(point: pygame.Vector2, points: Sequence[pygame.Vector2]) -> bool:
    """Even-odd ray-casting point-in-polygon test.

    Works for any simple polygon (convex or concave, non-self-
    intersecting) - required here since sprite-derived polygons
    (sprite_shape.py) aren't guaranteed convex (e.g. a stepped turret
    silhouette narrower than the hull below it produces concave
    "shoulder" corners).
    """
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i].x, points[i].y
        xj, yj = points[j].x, points[j].y
        if (yi > point.y) != (yj > point.y):
            x_at_y = (xj - xi) * (point.y - yi) / (yj - yi) + xi
            if point.x < x_at_y:
                inside = not inside
        j = i
    return inside


def _closest_point_on_segment(
    p: pygame.Vector2, a: pygame.Vector2, b: pygame.Vector2
) -> pygame.Vector2:
    """Closest point to `p` on the segment a-b (clamped to the segment)."""
    ab = b - a
    length_sq = ab.length_squared()
    if length_sq == 0.0:
        return pygame.Vector2(a)
    t = clamp((p - a).dot(ab) / length_sq, 0.0, 1.0)
    return a + ab * t


def circle_vs_polygon(
    center: pygame.Vector2, radius: float, points: Sequence[pygame.Vector2]
) -> bool:
    """True if a circle overlaps a simple (possibly concave) polygon.

    Two-part test, standard for this shape combination and correct
    without assuming convexity (sprite-derived polygons aren't
    guaranteed convex - see _point_in_polygon):
      1. If the circle's center is inside the polygon (even-odd ray
         cast), they already overlap regardless of edge distances - this
         covers a circle fully swallowed by the polygon, or a fast
         sample point that landed past every edge on one tick.
      2. Otherwise, check every edge: if the closest point on any edge
         segment to the center is within `radius`, they overlap.
    """
    if len(points) < 3:
        return False
    if _point_in_polygon(center, points):
        return True
    n = len(points)
    radius_sq = radius * radius
    for i in range(n):
        a = points[i]
        b = points[(i + 1) % n]
        closest = _closest_point_on_segment(center, a, b)
        if center.distance_squared_to(closest) <= radius_sq:
            return True
    return False


def _tank_shape_overlap(center: pygame.Vector2, radius: float, shape: Shape) -> bool:
    """Dispatch circle-vs-tank-shape to the right narrow-phase test.

    A Tank's collision_shape() returns either a Rectangle (no sprite art)
    or a Polygon (sprite-derived silhouette) - see Tank.collision_shape()'s
    docstring. Kept as a small private dispatcher (rather than an
    isinstance chain inline in sweep_projectile) so adding a third
    concrete Shape later touches one place.
    """
    if isinstance(shape, Rectangle):
        rect = pygame.Rect(
            round(shape.topleft.x),
            round(shape.topleft.y),
            round(shape.width),
            round(shape.height),
        )
        return circle_vs_rect(center, radius, rect)
    if isinstance(shape, Polygon):
        return circle_vs_polygon(center, radius, shape.points)
    return False  # unreachable for Tank today; explicit rather than silently swallowing a new Shape type


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

    Each tank is tested via tank.collision_shape(terrain) (dispatched by
    _tank_shape_overlap) rather than tank.rect(terrain) directly, so a
    sprite-backed tank is tested against its actual sprite-mask
    silhouette (a Polygon) instead of its full bounding rect; a tank with
    no sprite art still falls back to Rectangle, identical to the old
    rect-based test. collision_shape() itself is cheap to call here: the
    expensive mask/outline extraction is cached in sprite_cache.py per
    (sprite_key, facing), not recomputed per sample/tick.
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
            if _tank_shape_overlap(sample, radius, tank.collision_shape(terrain)):
                return CollisionResult("tank", sample, index)

    return None
