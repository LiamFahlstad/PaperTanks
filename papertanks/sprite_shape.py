"""Derive a low-resolution collision Polygon from a sprite's alpha mask.

A narrow, standalone concern: "what collision geometry does this piece of
art actually have, ignoring its transparent padding?" This doesn't belong
in render.py (drawing only - it never derives gameplay shapes, and this
module never draws anything), entities.py (plain data about tanks/
projectiles/terrain, not sprite/mask geometry construction), or
collision.py (narrow-phase overlap tests only, by its own module
docstring - this module performs no overlap test, only shape
construction). A single-function module matches the project's "one
module, one question" convention (ARCHITECTURE.md §2).

This module never touches World, Tank, render.py's sprite cache, or
config.SPRITE_DIR - it takes a plain pygame.Surface (whatever the caller
already loaded/scaled, e.g. via sprite_cache.get_tank_sprite()'s output)
and returns a shapes.Polygon. That keeps it testable with a bare Surface
and reusable for any future sprite-backed entity, not just Tank; it also
means this module's only project-level dependency is shapes.py, a leaf
with no knowledge of tanks/terrain/entities.py, so there is nothing here
for entities.py (or anything that depends on entities.py) to accidentally
form a cycle with.

Coordinate note: the returned Polygon's points are in the *surface's own
local pixel space* - origin at the surface's top-left, the same frame the
surface was drawn/scaled in - not world space. Translating to world space
(e.g. adding a Rectangle-style topleft offset) is the caller's job, the
same way Rectangle itself only wraps local rect geometry without knowing
about world placement.

This module only *builds* a Polygon; it does not wire one into any
entity's collision_shape() or into collision.py's narrow-phase tests.
sprite_cache.get_tank_collision_polygon() is what calls this function and
caches the result; Tank.collision_shape() (entities.py) is what turns
that cached local-space Polygon into a world-space one.
"""

from __future__ import annotations

import math
from typing import List, Optional

import pygame
import pygame.mask

from . import config
from .shapes import Polygon


def polygon_from_sprite_mask(
    surface: pygame.Surface,
    num_points: int = config.SPRITE_SHAPE_POINTS,
    offset: float = config.SPRITE_SHAPE_OFFSET_PX,
) -> Polygon:
    """Build a low-res Polygon that hugs `surface`'s opaque-pixel silhouette.

    Algorithm:
      1. Build a pygame.mask.Mask from `surface`'s alpha channel and take
         its center of mass (Mask.centroid()) as the polygon's centroid.
      2. Walk the mask's outline pixels (Mask.outline()). Bucket each
         outline point into one of `num_points` equal-width angle sectors
         around the centroid (sector i spans
         [i * 2*pi/num_points, (i+1) * 2*pi/num_points)), keyed by the
         angle from the centroid to that point. Within each sector, keep
         only the point *farthest* from the centroid - this is what makes
         the result hug protrusions/extremities of the silhouette rather
         than just approximating an average boundary.
      3. Sectors are walked in increasing-angle order (angle = atan2(dy,
         dx), normalized to [0, 2*pi)), and the reconstructed point for
         sector i is placed at its leading-edge angle (i * 2*pi/num_points).
         Increasing angle order guarantees a simple (non-self-intersecting)
         star-shaped polygon around the centroid, independent of whether
         that reads as clockwise or counterclockwise on screen in this
         project's y-down frame - nothing here depends on winding order.
      4. Each resulting point is nudged along its own centroid-to-point
         ray by `offset` pixels: negative shrinks the shape inward,
         positive expands it outward. The shrink is clamped so a point can
         never cross past the centroid (radius floored at 0), i.e. it
         can collapse onto the centroid but never invert to the far side.

    Empty-sector handling: a coarse `num_points`, a very concave outline,
    or an outline with fewer boundary pixels than sectors can leave some
    sectors with no outline point at all. Those sectors' radius (distance
    from centroid) is linearly interpolated - weighted by angular distance
    - between the nearest sectors on either side (wrapping around the
    circle) that *did* get a point, instead of collapsing to a degenerate
    zero-radius spike. If only one sector has data, every empty sector
    borrows that same radius (a circle around the centroid) - a single
    data point offers no directional information to interpolate between,
    so a uniform radius is the honest fallback, and still yields valid,
    non-degenerate geometry.

    Tie-breaking: if two outline points land in the same sector at equal
    distance, the point encountered first in Mask.outline()'s (fixed,
    deterministic) contour order wins - so results are reproducible for
    the same input surface.

    Multi-blob sprites: Mask.outline() traces only the mask's first
    connected component (a pygame limitation, not one introduced here).
    A sprite with disconnected opaque regions (e.g. a body plus a
    separate floating decal) only contributes its first blob's outline.

    Raises:
        ValueError: `num_points` < 3 (not a polygon), or `surface` has no
            opaque pixels (nothing to derive a shape from).
    """
    if num_points < 3:
        raise ValueError(f"num_points must be >= 3, got {num_points}")

    mask = pygame.mask.from_surface(surface)
    if mask.count() == 0:
        raise ValueError("surface has no opaque pixels; cannot derive a collision polygon")

    cx, cy = mask.centroid()
    centroid = pygame.Vector2(cx, cy)

    outline = mask.outline()  # list[tuple[int, int]] in local pixel space, contour order

    two_pi = 2.0 * math.pi
    sector_width = two_pi / num_points

    # best_distance[i]: farthest outline-point distance found in sector i,
    # or None until a point lands there.
    best_distance: List[Optional[float]] = [None] * num_points

    for px, py in outline:
        dx, dy = px - centroid.x, py - centroid.y
        distance = math.hypot(dx, dy)
        if distance == 0.0:
            continue  # outline point exactly at the centroid: no angle to bucket by
        angle = math.atan2(dy, dx)
        if angle < 0.0:
            angle += two_pi
        sector = min(int(angle / sector_width), num_points - 1)
        if best_distance[sector] is None or distance > best_distance[sector]:
            best_distance[sector] = distance

    filled = {i for i, d in enumerate(best_distance) if d is not None}

    radii = [0.0] * num_points
    for i in range(num_points):
        if best_distance[i] is not None:
            radii[i] = best_distance[i]
        elif filled:
            left = _nearest_filled_sector(filled, i, num_points, step=-1)
            right = _nearest_filled_sector(filled, i, num_points, step=1)
            if left == right:
                radii[i] = best_distance[left]
            else:
                left_gap = (i - left) % num_points
                right_gap = (right - i) % num_points
                weight_right = left_gap / (left_gap + right_gap)
                radii[i] = best_distance[left] * (1.0 - weight_right) + best_distance[right] * weight_right
        # else: no sector has any data (every outline point sat exactly on
        # the centroid, e.g. a 1x1 opaque surface) - radius stays 0.0.

    points = []
    for i in range(num_points):
        angle = i * sector_width
        radius = max(0.0, radii[i] + offset)
        points.append(centroid + pygame.Vector2(math.cos(angle), math.sin(angle)) * radius)

    return Polygon(points=tuple(points))


def _nearest_filled_sector(filled: set, start: int, num_points: int, step: int) -> int:
    """Walk the sector ring from `start` in `step` (+1 or -1) direction
    until landing on a sector index present in `filled`. Always terminates
    because `filled` is non-empty (checked by the caller)."""
    i = start
    for _ in range(num_points):
        i = (i + step) % num_points
        if i in filled:
            return i
    raise AssertionError("unreachable: filled is non-empty")
