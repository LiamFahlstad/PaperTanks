"""Turn-based mode (§12 item 4 of ARCHITECTURE.md): World gates aim/power/
move/fire to whichever tank is world.active_player, and enforces one shot
per turn via world.shot_fired_this_turn. Everything here drives a real
World headlessly, same conventions as test_world_smoke.py; physics and
collision are untouched by this feature and are not re-tested here.
"""

from __future__ import annotations

import pygame
import pytest

from papertanks import config
from papertanks.entities import Projectile
from papertanks.world import GameState, Intent, World


def _run_until_turn_settles(world: World, max_ticks: int = 3000) -> None:
    """Step with neutral intents until the in-flight shot (projectile and
    any resulting explosion) has fully cleared, or give up after
    max_ticks - used by tests that only care about the turn-passing rule,
    not the exact trajectory."""
    neutral = [Intent(), Intent()]
    for _ in range(max_ticks):
        if not world.projectiles and not world.explosions:
            return
        world.step(config.FIXED_DT, neutral)


def test_turn_starts_with_player_0_active():
    world = World()
    assert world.active_player == 0
    assert world.shot_fired_this_turn is False


def test_inactive_players_intent_has_no_effect():
    world = World()
    tank1_before = world.tanks[1]
    aim_before = tank1_before.aim_deg
    power_before = tank1_before.power
    x_before = tank1_before.x

    # Player 0 is active; player 1 tries to aim/power/move/fire.
    intents = [
        Intent(),
        Intent(aim_delta=1.0, power_delta=1.0, move_delta=1.0, fire=True),
    ]
    for _ in range(30):
        world.step(config.FIXED_DT, intents)

    assert world.tanks[1].aim_deg == aim_before
    assert world.tanks[1].power == power_before
    assert world.tanks[1].x == x_before
    assert len(world.projectiles) == 0


def test_active_player_can_still_act_normally():
    """Regression guard: gating the inactive tank must not also gate the
    active one (default active_player is 0)."""
    world = World()
    intents = [
        Intent(aim_delta=1.0, power_delta=1.0, move_delta=1.0, fire=True),
        Intent(),
    ]
    world.step(config.FIXED_DT, intents)

    assert len(world.projectiles) == 1
    assert world.tanks[0].aim_deg > config.TANK_AIM_START_DEG
    assert world.tanks[0].power > config.TANK_POWER_START


def test_second_fire_is_blocked_for_the_rest_of_the_turn():
    """One shot per turn: holding fire (or pressing it again) must not
    spawn a second projectile even once reload_timer would normally allow
    it, as long as the turn hasn't passed."""
    world = World()
    intents = [Intent(fire=True), Intent()]

    world.step(config.FIXED_DT, intents)
    assert len(world.projectiles) == 1
    assert world.shot_fired_this_turn is True

    # Step well past TANK_FIRE_COOLDOWN while still holding fire and while
    # the shot is presumably still resolving (default aim/power arcs for
    # well over half a second).
    cooldown_ticks = int(config.TANK_FIRE_COOLDOWN / config.FIXED_DT) + 20
    for _ in range(cooldown_ticks):
        world.step(config.FIXED_DT, intents)

    assert world.tanks[0].reload_timer <= 0.0  # cooldown itself has elapsed
    assert len(world.projectiles) == 1  # but no second shot was fired
    assert world.active_player == 0  # turn hasn't passed yet (still in flight)


def test_turn_passes_only_after_projectile_and_explosion_both_clear():
    world = World()
    world.tanks[0].aim_deg = config.TANK_AIM_START_DEG
    intents = [Intent(fire=True), Intent()]
    world.step(config.FIXED_DT, intents)
    assert len(world.projectiles) == 1

    neutral = [Intent(), Intent()]
    max_ticks = int(config.PROJECTILE_MAX_LIFETIME / config.FIXED_DT) + 1
    saw_explosion_while_still_player_0 = False
    for _ in range(max_ticks):
        if not world.projectiles and not world.explosions:
            break
        world.step(config.FIXED_DT, neutral)
        if world.projectiles == [] and world.explosions:
            # Projectile just resolved into an explosion: turn must not
            # have passed yet, since the explosion hasn't cleared.
            saw_explosion_while_still_player_0 = True
            assert world.active_player == 0

    assert world.projectiles == []
    assert world.explosions == []
    assert saw_explosion_while_still_player_0  # sanity: the shot did hit something
    assert world.active_player == 1  # turn passed only once explosion cleared too
    assert world.shot_fired_this_turn is False  # reset for the new active player


def test_offscreen_shot_with_no_explosion_still_passes_turn():
    """A shot that expires out-of-bounds (no ground/tank hit, so no
    explosion is spawned - see World._integrate_projectiles) must still
    hand off the turn once it's removed. Constructed directly rather than
    via aim/power to avoid depending on exact trajectory math to reach the
    screen edge before falling to the ground."""
    world = World()
    world.shot_fired_this_turn = True
    world.projectiles = [
        Projectile(
            position=pygame.Vector2(config.SCREEN_WIDTH - 5.0, 50.0),
            velocity=pygame.Vector2(3000.0, 0.0),
            owner=0,
        )
    ]

    _run_until_turn_settles(world)

    assert world.projectiles == []
    assert world.explosions == []  # off-screen expiry never spawns one
    assert world.active_player == 1
    assert world.shot_fired_this_turn is False


def test_restart_resets_turn_state():
    world = World()
    world.active_player = 1
    world.shot_fired_this_turn = True

    world.restart()

    assert world.active_player == 0
    assert world.shot_fired_this_turn is False


def test_turn_does_not_advance_past_game_over():
    world = World()
    world.tanks[1].hp = 0.0
    world.tanks[1].alive = False
    world.shot_fired_this_turn = True

    world.step(config.FIXED_DT, [Intent(), Intent()])

    assert world.state == GameState.GAME_OVER
    # Win condition is checked before _advance_turn; the turn must not
    # flip on the same tick the game ends.
    assert world.active_player == 0


def test_deterministic_seed_produces_identical_turn_state():
    """Same seed, same input sequence -> identical turn state too, not
    just tank hp/position (extends the existing determinism guard in
    test_world_smoke.py to the new active_player/shot_fired_this_turn
    fields)."""
    intents = [
        Intent(aim_delta=1.0, power_delta=-1.0, move_delta=1.0, fire=True),
        Intent(move_delta=-1.0, fire=True),
    ]

    world_a = World(rng_seed=config.RNG_SEED)
    world_b = World(rng_seed=config.RNG_SEED)
    for _ in range(400):
        world_a.step(config.FIXED_DT, intents)
        world_b.step(config.FIXED_DT, intents)

    assert world_a.active_player == world_b.active_player
    assert world_a.shot_fired_this_turn == world_b.shot_fired_this_turn
    assert [t.hp for t in world_a.tanks] == [t.hp for t in world_b.tanks]
