"""Narrow-phase collision tests (circle_vs_rect, circle_vs_polygon) and the
tunneling-safe sweep (sweep_projectile).

Tanks used here never set sprite_key, so Tank.collision_shape() always
returns a plain Rectangle (see entities.Tank.collision_shape) - this keeps
the suite headless and independent of the "tank1" sprite asset on disk.
"""

from __future__ import annotations

import pygame

from papertanks import collision
from papertanks.entities import Tank, Terrain


def make_tank(x: float) -> Tank:
    return Tank(x=x, facing=1, color=(0, 0, 0))


# --- circle_vs_rect ---------------------------------------------------------


def test_circle_vs_rect_overlap_center_inside():
    rect = pygame.Rect(0, 0, 20, 20)
    assert collision.circle_vs_rect(pygame.Vector2(10, 10), 1.0, rect) is True


def test_circle_vs_rect_overlap_at_edge():
    rect = pygame.Rect(0, 0, 20, 20)
    # Center just outside the right edge, radius reaches back in.
    assert collision.circle_vs_rect(pygame.Vector2(24.0, 10), 5.0, rect) is True


def test_circle_vs_rect_no_overlap():
    rect = pygame.Rect(0, 0, 20, 20)
    assert collision.circle_vs_rect(pygame.Vector2(100, 100), 5.0, rect) is False


def test_circle_vs_rect_touching_boundary_counts_as_overlap():
    rect = pygame.Rect(0, 0, 20, 20)
    # Distance from center to closest point == radius exactly (<=, not <).
    assert collision.circle_vs_rect(pygame.Vector2(25.0, 10), 5.0, rect) is True


def test_circle_vs_rect_corner_case_diagonal_miss():
    rect = pygame.Rect(0, 0, 20, 20)
    # Nearest point is the corner (20, 20); distance = sqrt(2)*5 ~= 7.07 > 5.
    assert collision.circle_vs_rect(pygame.Vector2(25, 25), 5.0, rect) is False


# --- circle_vs_polygon -------------------------------------------------------


def _square(cx: float, cy: float, half: float) -> tuple[pygame.Vector2, ...]:
    return (
        pygame.Vector2(cx - half, cy - half),
        pygame.Vector2(cx + half, cy - half),
        pygame.Vector2(cx + half, cy + half),
        pygame.Vector2(cx - half, cy + half),
    )


def test_circle_vs_polygon_center_inside():
    square = _square(0, 0, 10)
    assert collision.circle_vs_polygon(pygame.Vector2(0, 0), 1.0, square) is True


def test_circle_vs_polygon_no_overlap():
    square = _square(0, 0, 10)
    assert collision.circle_vs_polygon(pygame.Vector2(100, 100), 1.0, square) is False


def test_circle_vs_polygon_edge_overlap_from_outside():
    square = _square(0, 0, 10)
    # Center is outside the square but within radius of the right edge.
    assert collision.circle_vs_polygon(pygame.Vector2(13.0, 0.0), 5.0, square) is True


def test_circle_vs_polygon_concave_shape():
    # A concave "C" / notch shape: center placed inside the notch (outside
    # the polygon) must not register a hit, proving the point-in-polygon
    # test isn't assuming convexity.
    notch = (
        pygame.Vector2(-10, -10),
        pygame.Vector2(10, -10),
        pygame.Vector2(10, 10),
        pygame.Vector2(2, 10),
        pygame.Vector2(2, -2),
        pygame.Vector2(-10, -2),
    )
    # Point sitting in the notch's empty lower-left area.
    assert collision.circle_vs_polygon(pygame.Vector2(-5, 5), 0.5, notch) is False
    # Point sitting inside the solid upper region.
    assert collision.circle_vs_polygon(pygame.Vector2(0, -5), 0.5, notch) is True


def test_circle_vs_polygon_degenerate_fewer_than_three_points():
    assert (
        collision.circle_vs_polygon(
            pygame.Vector2(0, 0), 5.0, (pygame.Vector2(0, 0), pygame.Vector2(1, 1))
        )
        is False
    )


# --- sweep_projectile: tunneling ------------------------------------------


def test_sweep_projectile_ground_hit():
    terrain = Terrain(ground_y=500.0)
    old_pos = pygame.Vector2(100, 490)
    new_pos = pygame.Vector2(100, 505)
    result = collision.sweep_projectile(
        old_pos, new_pos, radius=5.0, terrain=terrain, tanks=[], owner_index=0
    )
    assert result is not None
    assert result.kind == "ground"


def test_sweep_projectile_skips_owner_tank():
    terrain = Terrain(ground_y=100000.0)  # push ground far away
    tank = make_tank(x=300.0)
    old_pos = pygame.Vector2(tank.rect(terrain).centerx, tank.rect(terrain).centery)
    new_pos = pygame.Vector2(old_pos)
    result = collision.sweep_projectile(
        old_pos, new_pos, radius=2.0, terrain=terrain, tanks=[tank], owner_index=0
    )
    assert result is None  # owner tank is never hit by its own shot


def test_sweep_projectile_catches_high_speed_tunneling_through_tank():
    """A fast enough projectile can cross an entire tank body within a
    single fixed timestep - the endpoint alone would miss the hit
    entirely. sweep_projectile must still detect it by sampling the
    straight-line motion segment.
    """
    terrain = Terrain(ground_y=100000.0)  # ground far away; only tank matters
    tank = make_tank(x=300.0)
    rect = tank.rect(terrain)
    radius = 5.0

    # Fires from well above the tank to well below it, in one physics tick.
    old_pos = pygame.Vector2(rect.centerx, rect.top - 200.0)
    new_pos = pygame.Vector2(rect.centerx, rect.bottom + 200.0)

    # Sanity check: the discrete endpoint by itself does NOT overlap the
    # tank - proving this test actually exercises the sweep, not just an
    # end-of-segment check.
    assert collision.circle_vs_rect(new_pos, radius, rect) is False

    result = collision.sweep_projectile(
        old_pos, new_pos, radius, terrain=terrain, tanks=[tank], owner_index=1
    )
    assert result is not None
    assert result.kind == "tank"
    assert result.tank_index == 0


def test_sweep_projectile_no_hit_when_path_clears_tank():
    terrain = Terrain(ground_y=100000.0)
    tank = make_tank(x=300.0)
    rect = tank.rect(terrain)

    # A horizontal path well above the tank never comes near it.
    old_pos = pygame.Vector2(rect.left - 500.0, rect.top - 500.0)
    new_pos = pygame.Vector2(rect.right + 500.0, rect.top - 500.0)

    result = collision.sweep_projectile(
        old_pos, new_pos, radius=5.0, terrain=terrain, tanks=[tank], owner_index=1
    )
    assert result is None
