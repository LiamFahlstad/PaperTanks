"""Shared sprite-Surface loading/caching, plus the collision Polygon
derived from each cached Surface's alpha mask.

This is the shared leaf both render.py (drawing) and entities.py
(Tank.collision_shape()) depend on, so sprite art is decoded from disk in
exactly one place. Before this module existed, render.py's Renderer
owned this loading/caching privately (_sprites/_tank_sprites); it has
been extracted here, behavior-for-behavior, so entities.py can reuse the
exact same cached Surfaces for collision geometry without importing
render.py (which would invert the one-way dependency direction
ARCHITECTURE.md documents: render.py depends on entities.py/world.py,
never the reverse) and without Renderer re-implementing the same
load/scale/flip logic a second time just for collision.

Three caches, all process-lifetime and unbounded - this game has exactly
one real sprite_key ("tank1") and two facings, so none of these can grow
large:
  - get_sprite(sprite_key, size): load+scale+cache a Surface, keyed by
    (sprite_key, size). Same cache Renderer._sprites used to be.
  - get_tank_sprite(sprite_key, facing): the tank-sized
    (config.TANK_WIDTH x config.TANK_HEIGHT) sprite, additionally
    flipped horizontally when facing < 0. Same cache
    Renderer._tank_sprites used to be.
  - get_tank_collision_polygon(sprite_key, facing): the *local-space*
    collision points (see sprite_shape.polygon_from_sprite_mask),
    derived once from get_tank_sprite()'s Surface and cached by the same
    (sprite_key, facing) key. Deriving from the already-flipped Surface
    (rather than mirroring an unflipped polygon's x-coordinates) means a
    flipped tank's collision silhouette matches what's actually drawn
    with no separate mirroring logic to keep in sync, and costs nothing
    extra since that flipped Surface is already cached by
    get_tank_sprite().

Imports shapes.Polygon at module top, as an ordinary dependency - there
is no cycle to guard against here. The Shape/Circle/Rectangle/Polygon
geometry types live in shapes.py, a leaf module with no dependency on
entities.py (or anything else in this project); sprite_shape.py depends
only on shapes.py too. So the real dependency shape is:
shapes.py <- sprite_shape.py <- sprite_cache.py (this module) <-
entities.py, strictly one-way, with entities.py at the top depending
down into this module rather than the reverse. (entities.py separately
depends on shapes.py directly, for Tank.collision_shape()'s Rectangle
fallback and return-type annotation - both edges point the same
direction, so nothing here closes a loop back up toward entities.py.)

sprite_key=None is not handled by get_tank_sprite()/
get_tank_collision_polygon() - callers (Tank.collision_shape(),
Renderer._get_tank_sprite()) are responsible for checking sprite_key
before calling in, the same contract Renderer's original private methods
already had.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

import pygame

import config
from shapes import Polygon
from sprite_shape import polygon_from_sprite_mask

_sprites: Dict[Tuple[str, Tuple[int, int]], pygame.Surface] = {}
_tank_sprites: Dict[Tuple[str, int], pygame.Surface] = {}
_tank_collision_polygons: Dict[Tuple[str, int], Polygon] = {}


def get_sprite(sprite_key: str, size: Tuple[int, int]) -> pygame.Surface:
    """Load, scale to `size`, and cache sprite_key's image.

    The single place any sprite Surface is decoded from disk - every
    caller (render.py, entities.py) goes through this instead of owning
    a private pygame.image.load, so art is loaded at most once per
    (sprite_key, size).
    """
    cache_key = (sprite_key, size)
    sprite = _sprites.get(cache_key)
    if sprite is None:
        path = os.path.join(config.SPRITE_DIR, f"{sprite_key}.png")
        raw = pygame.image.load(path)
        # convert_alpha() needs an initialized pygame.display surface to
        # match pixel formats against - it's a blit-performance optimization
        # only, not a correctness requirement (a loaded PNG already carries
        # its own per-pixel alpha, which is all mask.from_surface() in
        # sprite_shape.py needs). Tank.collision_shape() reaches this
        # function from inside World.step() - the core simulation path,
        # which must stay usable with no window (headless tests, a future
        # dedicated server, etc.) - so this only converts when a display
        # actually exists (the real game via game.py's Game.__init__),
        # and falls back to the unconverted surface otherwise. Production
        # rendering is unaffected: game.py always initializes the display
        # before the first draw.
        if pygame.display.get_surface() is not None:
            raw = raw.convert_alpha()
        sprite = pygame.transform.scale(raw, size)
        _sprites[cache_key] = sprite
    return sprite


def get_tank_sprite(sprite_key: str, facing: int) -> pygame.Surface:
    """Tank-sized sprite Surface, flipped horizontally when facing < 0."""
    cache_key = (sprite_key, facing)
    sprite = _tank_sprites.get(cache_key)
    if sprite is None:
        base = get_sprite(sprite_key, (config.TANK_WIDTH, config.TANK_HEIGHT))
        sprite = pygame.transform.flip(base, True, False) if facing < 0 else base
        _tank_sprites[cache_key] = sprite
    return sprite


def get_tank_collision_polygon(sprite_key: str, facing: int) -> Polygon:
    """Local-space collision Polygon for a tank's sprite.

    "Local-space" means (0, 0) is the sprite's top-left, matching
    Tank.rect().topleft - the caller (Tank.collision_shape()) is
    responsible for translating these points into world space.
    Derived once per (sprite_key, facing) via
    sprite_shape.polygon_from_sprite_mask() (mask/outline extraction is
    not free) and cached thereafter, so a repeated call is a plain dict
    lookup, not a recomputation.
    """
    cache_key = (sprite_key, facing)
    polygon = _tank_collision_polygons.get(cache_key)
    if polygon is None:
        surface = get_tank_sprite(sprite_key, facing)
        polygon = polygon_from_sprite_mask(surface)
        _tank_collision_polygons[cache_key] = polygon
    return polygon
