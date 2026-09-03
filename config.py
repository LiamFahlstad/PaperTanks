"""Centralized tunable constants and key bindings for PaperTanks.

Conventions (documented once, relied on everywhere else):
  * Coordinate system: Pygame default. Origin (0, 0) is top-left; x
    increases rightward; y increases downward.
  * Units: positions in pixels, velocities in pixels/second, gravity in
    pixels/second^2. Gravity is a *positive* value added to y-velocity
    each physics tick, since "down" is positive y.
  * Angles: aim_deg is measured from the horizontal, 0 = flat, 90 =
    straight up, independent of which way the tank faces. A tank's
    `facing` (+1 right, -1 left) flips the horizontal velocity component.
  * Simulation runs on a fixed timestep (see PHYSICS_HZ) so gameplay is
    reproducible regardless of display frame rate.
"""

from __future__ import annotations

import pygame

# --- Window / rendering -----------------------------------------------
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
WINDOW_TITLE = "PaperTanks"
# Rendering is decoupled from physics; this only caps CPU/GPU usage.
MAX_RENDER_FPS = 240

# --- Simulation timestep -------------------------------------------------
PHYSICS_HZ = 120
FIXED_DT = 1.0 / PHYSICS_HZ
# Clamp huge real-time deltas (breakpoints, window drag, alt-tab) so the
# accumulator never has to run an unbounded number of catch-up steps.
MAX_FRAME_TIME = 0.25

# --- World / physics -------------------------------------------------
GRAVITY = 900.0  # px/s^2, downward (positive y)
# Flat ground for this first slice. Terrain.height_at(x) hides this
# detail so a future heightmap/destructible terrain doesn't require
# touching collision or entity code.
GROUND_Y = float(SCREEN_HEIGHT - 80)

# --- Assets --------------------------------------------------------------
SPRITE_DIR = "Sprites"

# --- Tank ---------------------------------------------------------------
TANK_WIDTH = 56
TANK_HEIGHT = 28
TANK_BARREL_LENGTH = 34
TANK_MAX_HP = 100
TANK_FIRE_COOLDOWN = 0.6  # seconds between shots, per tank

TANK_AIM_MIN_DEG = 5.0
TANK_AIM_MAX_DEG = 85.0
TANK_AIM_START_DEG = 45.0
TANK_AIM_RATE_DEG_S = 60.0  # degrees/second while the aim key is held

TANK_POWER_MIN = 200.0  # px/s muzzle speed
TANK_POWER_MAX = 900.0
TANK_POWER_START = 500.0
TANK_POWER_RATE = 300.0  # px/s^2 change while the power key is held

TANK1_START_X = 150.0
TANK2_START_X = SCREEN_WIDTH - 150.0

# --- Projectile -----------------------------------------------------------
PROJECTILE_RADIUS = 5.0
PROJECTILE_DAMAGE = 34
# Safety net only: a shot should always end via ground/tank collision.
# This guards against a projectile that somehow never crosses the ground
# (e.g. future terrain gaps) from living forever.
PROJECTILE_MAX_LIFETIME = 8.0

# --- Explosion feedback -------------------------------------------------
EXPLOSION_DURATION = 0.35  # seconds
EXPLOSION_MAX_RADIUS = 30.0

# --- Colors ("paper" palette) --------------------------------------------
COLOR_BG = (235, 231, 219)
COLOR_GROUND = (120, 100, 70)
COLOR_TANK_1 = (60, 110, 60)
COLOR_TANK_2 = (150, 60, 60)
COLOR_TANK_DEAD = (120, 120, 120)
COLOR_BARREL = (30, 30, 30)
COLOR_PROJECTILE = (30, 30, 30)
COLOR_EXPLOSION = (230, 140, 30)
COLOR_TEXT = (20, 20, 20)
COLOR_HP_BG = (80, 80, 80)
COLOR_HP_FG = (200, 40, 40)

# --- Input bindings -------------------------------------------------------
# Player 1: left tank (green)
P1_AIM_UP = pygame.K_w
P1_AIM_DOWN = pygame.K_s
P1_POWER_UP = pygame.K_d
P1_POWER_DOWN = pygame.K_a
P1_FIRE = pygame.K_SPACE

# Player 2: right tank (red)
P2_AIM_UP = pygame.K_UP
P2_AIM_DOWN = pygame.K_DOWN
P2_POWER_UP = pygame.K_RIGHT
P2_POWER_DOWN = pygame.K_LEFT
P2_FIRE = pygame.K_RETURN

KEY_PAUSE = pygame.K_p
KEY_RESTART = pygame.K_r
KEY_QUIT = pygame.K_ESCAPE

# Seeded RNG so any future randomized effects (particle jitter, etc.) stay
# reproducible for debugging.
RNG_SEED = 20260903
