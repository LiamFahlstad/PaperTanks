"""Pure integration helpers.

No side effects, no references to World/entities - easy to reason about
and to unit-test in isolation later. Uses semi-implicit (symplectic)
Euler: velocity is updated from acceleration first, then position is
updated from the *new* velocity. This is more stable/energy-consistent
than explicit Euler for a fixed timestep and is standard for simple game
physics.
"""

from __future__ import annotations

import pygame


def apply_gravity(
    velocity: pygame.Vector2, gravity: float, dt: float
) -> pygame.Vector2:
    """Return a new velocity with gravity applied for one timestep.

    `gravity` is a positive px/s^2 value; it is added to the y component
    because down is positive y in this project's coordinate convention.
    """
    return pygame.Vector2(velocity.x, velocity.y + gravity * dt)


def integrate_position(
    position: pygame.Vector2, velocity: pygame.Vector2, dt: float
) -> pygame.Vector2:
    """Return a new position advanced by `velocity` over one timestep."""
    return position + velocity * dt
