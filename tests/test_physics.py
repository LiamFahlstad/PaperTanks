"""physics.py's two pure integration functions.

These take plain Vector2/float values in and return new values, with no
World/Tank/pygame-window dependency - exactly what makes them safe to
test with bare numbers.
"""

from __future__ import annotations

import pygame
import pytest

from papertanks import physics


def test_apply_gravity_adds_to_y_only():
    velocity = pygame.Vector2(120.0, -50.0)
    result = physics.apply_gravity(velocity, gravity=900.0, dt=1.0 / 120.0)

    assert result.x == velocity.x  # gravity never touches horizontal velocity
    assert result.y > velocity.y  # positive gravity increases y (down is positive y)
    assert result.y == pytest.approx(velocity.y + 900.0 * (1.0 / 120.0))


def test_apply_gravity_is_pure():
    velocity = pygame.Vector2(0.0, 0.0)
    physics.apply_gravity(velocity, gravity=900.0, dt=1.0 / 120.0)
    assert velocity == pygame.Vector2(0.0, 0.0)  # input untouched


def test_apply_gravity_accumulates_over_repeated_ticks():
    velocity = pygame.Vector2(0.0, 0.0)
    dt = 1.0 / 120.0
    for _ in range(120):
        velocity = physics.apply_gravity(velocity, gravity=900.0, dt=dt)
    # After ~1 simulated second, y-velocity should be close to gravity * 1s.
    assert velocity.y == pytest.approx(900.0, abs=1.0)


def test_integrate_position_moves_by_velocity_times_dt():
    position = pygame.Vector2(100.0, 200.0)
    velocity = pygame.Vector2(60.0, -30.0)
    dt = 0.5
    result = physics.integrate_position(position, velocity, dt)

    assert result == pygame.Vector2(130.0, 185.0)
    assert position == pygame.Vector2(100.0, 200.0)  # input untouched


def test_symplectic_euler_uses_new_velocity_for_position():
    """The project documents semi-implicit (symplectic) Euler: velocity
    is updated first, then position uses the *new* velocity for that same
    tick, not the pre-gravity one. Verify the two functions compose that
    way (as world.py calls them) rather than assuming explicit Euler."""
    dt = 1.0
    gravity = 10.0
    velocity = pygame.Vector2(0.0, 0.0)
    position = pygame.Vector2(0.0, 0.0)

    new_velocity = physics.apply_gravity(velocity, gravity, dt)
    new_position = physics.integrate_position(position, new_velocity, dt)

    # Symplectic Euler: position advances by the *post-gravity* velocity
    # (10.0 * 1.0 = 10.0), not the pre-gravity velocity (0.0).
    assert new_position.y == pytest.approx(10.0)
