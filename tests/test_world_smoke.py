"""Headless logic smoke test: drive World.step() for real, with no
display/window/event loop, and check the rules it documents (aim/power
clamping, movement/friction, fire cooldown, gravity-driven flight, win
condition) actually hold. This is the test ARCHITECTURE.md refers to as
validating World in isolation from rendering/input.
"""

from __future__ import annotations

import pytest

from papertanks import config
from papertanks.world import GameState, Intent, World


def test_world_constructs_with_two_alive_tanks():
    world = World()
    assert len(world.tanks) == 2
    assert all(tank.alive for tank in world.tanks)
    assert world.state == GameState.PLAYING


def test_paused_world_does_not_advance():
    world = World()
    world.toggle_pause()
    assert world.state == GameState.PAUSED

    aim_before = world.tanks[0].aim_deg
    intents = [Intent(aim_delta=1.0), Intent()]
    for _ in range(60):
        world.step(config.FIXED_DT, intents)

    assert world.tanks[0].aim_deg == aim_before  # step() is a no-op while paused


def test_aim_delta_is_clamped_to_configured_range():
    world = World()
    intents = [Intent(aim_delta=1.0), Intent()]
    # Hold "aim up" far longer than needed to hit the ceiling.
    for _ in range(1000):
        world.step(config.FIXED_DT, intents)

    assert world.tanks[0].aim_deg == config.TANK_AIM_MAX_DEG


def test_fire_respects_reload_cooldown():
    world = World()
    intents = [Intent(fire=True), Intent()]

    world.step(config.FIXED_DT, intents)
    assert len(world.projectiles) == 1

    # Holding fire during the cooldown window must not spawn a second shot.
    for _ in range(5):
        world.step(config.FIXED_DT, intents)
    assert len(world.projectiles) == 1


def test_projectile_falls_under_gravity_and_eventually_hits_ground():
    world = World()
    # Aim flat and fire so the shot travels roughly horizontal, then arcs
    # down under gravity and hits the ground well before the safety-net
    # lifetime expires.
    world.tanks[0].aim_deg = config.TANK_AIM_MIN_DEG
    intents = [Intent(fire=True), Intent()]
    world.step(config.FIXED_DT, intents)
    assert len(world.projectiles) == 1

    max_ticks = int(config.PROJECTILE_MAX_LIFETIME / config.FIXED_DT) + 1
    neutral = [Intent(), Intent()]
    for _ in range(max_ticks):
        if not world.projectiles:
            break
        world.step(config.FIXED_DT, neutral)

    assert len(world.projectiles) == 0  # consumed by ground collision (or expired)
    assert len(world.explosions) >= 1  # ground/tank impact leaves explosion feedback


def test_move_intent_moves_tank_right():
    world = World()
    start_x = world.tanks[0].x
    intents = [Intent(move_delta=1.0), Intent()]
    for _ in range(60):  # 0.5s at 120Hz
        world.step(config.FIXED_DT, intents)

    assert world.tanks[0].x > start_x
    assert world.tanks[0].velocity_x > 0.0


def test_move_intent_respects_top_speed():
    world = World()
    intents = [Intent(move_delta=1.0), Intent()]
    # Hold move far longer than needed to reach terminal velocity.
    for _ in range(600):
        world.step(config.FIXED_DT, intents)

    assert world.tanks[0].velocity_x == pytest.approx(config.TANK_MOVE_SPEED)


def test_friction_stops_tank_after_move_key_released():
    world = World()
    intents = [Intent(move_delta=1.0), Intent()]
    for _ in range(60):
        world.step(config.FIXED_DT, intents)
    assert world.tanks[0].velocity_x > 0.0

    neutral = [Intent(), Intent()]
    # Long enough to fully decelerate at TANK_MOVE_FRICTION from top speed.
    stop_ticks = (
        int(config.TANK_MOVE_SPEED / config.TANK_MOVE_FRICTION / config.FIXED_DT) + 5
    )
    for _ in range(stop_ticks):
        world.step(config.FIXED_DT, neutral)

    assert world.tanks[0].velocity_x == pytest.approx(0.0)


def test_tank_position_stays_clamped_to_screen_bounds():
    world = World()
    intents = [Intent(move_delta=-1.0), Intent()]  # drive tank 0 toward the left edge
    for _ in range(600):
        world.step(config.FIXED_DT, intents)

    half_width = config.TANK_WIDTH / 2.0
    assert world.tanks[0].x == pytest.approx(half_width)


def test_tank_y_tracks_terrain_height_at_x_while_moving():
    world = World()
    intents = [Intent(move_delta=1.0), Intent()]
    for _ in range(30):
        world.step(config.FIXED_DT, intents)

    tank = world.tanks[0]
    # Terrain is flat today, but rect()/muzzle_position() must derive their
    # vertical placement from terrain.height_at(tank.x) fresh each call,
    # not a stale/cached y - this is the seam a future heightmap plugs into.
    assert tank.rect(world.terrain).bottom == round(world.terrain.height_at(tank.x))


def test_aim_power_fire_unaffected_by_movement():
    """Movement is a new, independent axis; it must not change how
    aim/power/fire behave (regression guard for §12 item 1)."""
    world = World()
    intents = [
        Intent(aim_delta=1.0, power_delta=1.0, move_delta=1.0, fire=True),
        Intent(),
    ]
    world.step(config.FIXED_DT, intents)

    assert len(world.projectiles) == 1
    assert world.tanks[0].aim_deg > config.TANK_AIM_START_DEG
    assert world.tanks[0].power > config.TANK_POWER_START


def test_deterministic_seed_produces_identical_runs():
    """Same seed, same fixed-dt input sequence -> identical resulting
    state, which is what config.RNG_SEED and the fixed timestep are for."""
    intents = [
        Intent(aim_delta=1.0, power_delta=-1.0, move_delta=1.0, fire=True),
        Intent(move_delta=-1.0, fire=True),
    ]

    world_a = World(rng_seed=config.RNG_SEED)
    world_b = World(rng_seed=config.RNG_SEED)
    for _ in range(200):
        world_a.step(config.FIXED_DT, intents)
        world_b.step(config.FIXED_DT, intents)

    assert [t.hp for t in world_a.tanks] == [t.hp for t in world_b.tanks]
    assert [t.aim_deg for t in world_a.tanks] == [t.aim_deg for t in world_b.tanks]
    assert [t.x for t in world_a.tanks] == [t.x for t in world_b.tanks]
    assert len(world_a.projectiles) == len(world_b.projectiles)


def test_win_condition_ends_game_when_one_tank_dies():
    world = World()
    # Drive the tank to 0 HP directly (bypassing shot trajectory/geometry,
    # which is exercised elsewhere) to isolate the win-condition rule
    # itself: exactly one tank left alive ends the game with that tank
    # recorded as the winner.
    world.tanks[1].hp = 0.0
    world.tanks[1].alive = False

    world.step(config.FIXED_DT, [Intent(), Intent()])

    assert world.state == GameState.GAME_OVER
    assert world.winner == 0


def test_win_condition_is_a_draw_when_both_tanks_die_same_tick():
    world = World()
    world.tanks[0].hp = 0.0
    world.tanks[0].alive = False
    world.tanks[1].hp = 0.0
    world.tanks[1].alive = False

    world.step(config.FIXED_DT, [Intent(), Intent()])

    assert world.state == GameState.GAME_OVER
    assert world.winner is None


def test_restart_resets_state_deterministically():
    world = World()
    world.tanks[0].hp = 0.0
    world.tanks[0].alive = False
    world.step(config.FIXED_DT, [Intent(), Intent()])
    assert world.state == GameState.GAME_OVER

    world.restart()

    assert world.state == GameState.PLAYING
    assert all(tank.alive for tank in world.tanks)
    assert all(tank.hp == config.TANK_MAX_HP for tank in world.tanks)
    assert world.projectiles == []
    assert world.explosions == []
