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
SPRITE_DIR = "assets/sprites"

# --- Sprite-derived collision shapes (sprite_shape.py) --------------------
# Tunables for polygon_from_sprite_mask(): how many points the generated
# collision polygon has, and how far each point is nudged inward/outward
# along its own centroid-to-point ray. Wired in via sprite_cache.py's
# per-(sprite_key, facing) cache into Tank.collision_shape() (entities.py),
# which returns a shapes.Polygon for any tank with a sprite_key.
SPRITE_SHAPE_POINTS = 12
# Negative = shrink inward (the default). Collision shapes are
# conventionally drawn slightly smaller than the sprite art, so a shot
# that visually grazes the edge of the art doesn't register a hit before
# it looks like it should. Positive would expand outward instead.
SPRITE_SHAPE_OFFSET_PX = -3.0

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

# Horizontal ground movement. Modeled as velocity + acceleration/friction
# (not an instant "set position" or a direct rate like aim/power) so a
# held move key ramps up to speed and a released one coasts to a stop
# rather than snapping - the small amount of momentum is deliberate game
# feel, not leftover complexity. All in px/s and px/s^2, same units as
# gravity/projectile motion (see this module's docstring).
TANK_MOVE_SPEED = 140.0  # px/s, top horizontal speed
TANK_MOVE_ACCEL = 500.0  # px/s^2 while a move key is held (~0.28s to top speed)
TANK_MOVE_FRICTION = (
    700.0  # px/s^2 deceleration once the move key is released (~0.2s to stop)
)

# --- Projectile -----------------------------------------------------------
PROJECTILE_RADIUS = 5.0
PROJECTILE_DAMAGE = 34
# Safety net only: a shot should always end via ground/tank collision.
# This guards against a projectile that somehow never crosses the ground
# (e.g. future terrain gaps) from living forever.
PROJECTILE_MAX_LIFETIME = 8.0
# Also a safety net: how far past either screen edge a projectile may
# travel before it's despawned as out-of-bounds, rather than living
# forever off-screen (e.g. a very high-power shot fired near-horizontal).
PROJECTILE_OFFSCREEN_MARGIN_PX = 50.0

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
# WASD is already fully claimed by aim/power, so movement gets the next
# keys over rather than reusing power's A/D (which would make A/D mean
# two different things at once). Q/E sit right next to the WASD cluster.
P1_MOVE_LEFT = pygame.K_q
P1_MOVE_RIGHT = pygame.K_e

# Player 2: right tank (red)
P2_AIM_UP = pygame.K_UP
P2_AIM_DOWN = pygame.K_DOWN
P2_POWER_UP = pygame.K_RIGHT
P2_POWER_DOWN = pygame.K_LEFT
P2_FIRE = pygame.K_RETURN
# Same reasoning as P1: the arrow cluster is already aim/power. Numpad
# 4/6 sit immediately beside the arrow cluster on a full-size keyboard as
# the nearest free left/right pair - flagged as a placeholder binding
# worth revisiting (e.g. on a laptop with no numpad) rather than a
# considered final choice.
P2_MOVE_LEFT = pygame.K_KP4
P2_MOVE_RIGHT = pygame.K_KP6

KEY_PAUSE = pygame.K_p
KEY_RESTART = pygame.K_r
KEY_QUIT = pygame.K_ESCAPE

# Seeded RNG so any future randomized effects (particle jitter, etc.) stay
# reproducible for debugging.
RNG_SEED = 20260903
