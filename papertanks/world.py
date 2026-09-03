"""World state and the fixed-timestep simulation step.

World.step() is the single place gameplay rules live: aiming/power/fire
handling, gravity integration, collision resolution, damage, and win
condition. It is called once per fixed physics tick with dt always equal
to config.FIXED_DT, so behavior is identical regardless of display frame
rate. Nothing here touches pygame drawing/events.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Sequence

import pygame

from . import collision
from . import config
from . import physics
from .entities import Explosion, Projectile, Tank, Terrain


class GameState(Enum):
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()


@dataclass
class Intent:
    """One tank's requested input for a single physics tick.

    aim_delta/power_delta are direction only (-1, 0, or 1); World scales
    them by the configured rate and dt, so input handling stays agnostic
    of tuning values.
    """

    aim_delta: float = 0.0
    power_delta: float = 0.0
    fire: bool = False


def _neutral_intents() -> List[Intent]:
    """Fresh, unheld-key Intents for both tanks.

    Used as World.step()'s default when no intents are supplied (e.g. a
    paused/headless step). Built fresh per call rather than shared as a
    module-level mutable list default - Intent is never mutated in place
    today, but a shared mutable default is a standing footgun for future
    code that might read-and-modify one, so it's avoided outright.
    """
    return [Intent(), Intent()]


class World:
    def __init__(self, rng_seed: int = config.RNG_SEED) -> None:
        self._rng_seed = rng_seed
        self._reset()

    def _reset(self) -> None:
        self.rng = random.Random(self._rng_seed)
        self.terrain = Terrain(config.GROUND_Y)
        self.tanks: List[Tank] = [
            Tank(x=config.TANK1_START_X, facing=1, color=config.COLOR_TANK_1, sprite_key="tank1"),
            Tank(x=config.TANK2_START_X, facing=-1, color=config.COLOR_TANK_2),
        ]
        self.projectiles: List[Projectile] = []
        self.explosions: List[Explosion] = []
        self.state = GameState.PLAYING
        self.winner: Optional[int] = None

    def restart(self) -> None:
        self._reset()

    def toggle_pause(self) -> None:
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
        elif self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def pause(self) -> None:
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED

    def step(self, dt: float, intents: Optional[Sequence[Intent]] = None) -> None:
        if self.state != GameState.PLAYING:
            return
        if intents is None:
            intents = _neutral_intents()

        for tank, intent in zip(self.tanks, intents):
            self._apply_intent(tank, intent, dt)

        self._integrate_projectiles(dt)
        self._update_explosions(dt)
        self._check_win_condition()

    def _apply_intent(self, tank: Tank, intent: Intent, dt: float) -> None:
        tank.reload_timer = max(0.0, tank.reload_timer - dt)

        if not tank.alive:
            return

        tank.aim_deg = collision.clamp(
            tank.aim_deg + intent.aim_delta * config.TANK_AIM_RATE_DEG_S * dt,
            config.TANK_AIM_MIN_DEG,
            config.TANK_AIM_MAX_DEG,
        )
        tank.power = collision.clamp(
            tank.power + intent.power_delta * config.TANK_POWER_RATE * dt,
            config.TANK_POWER_MIN,
            config.TANK_POWER_MAX,
        )

        if intent.fire and tank.reload_timer <= 0.0:
            self._fire(tank)

    def _fire(self, tank: Tank) -> None:
        owner_index = self.tanks.index(tank)
        muzzle = tank.muzzle_position(self.terrain)
        velocity = tank.aim_direction() * tank.power
        self.projectiles.append(
            Projectile(position=pygame.Vector2(muzzle), velocity=velocity, owner=owner_index)
        )
        tank.reload_timer = config.TANK_FIRE_COOLDOWN

    def _integrate_projectiles(self, dt: float) -> None:
        survivors: List[Projectile] = []
        for proj in self.projectiles:
            proj.prev_position = pygame.Vector2(proj.position)
            proj.velocity = physics.apply_gravity(proj.velocity, config.GRAVITY, dt)
            new_pos = physics.integrate_position(proj.position, proj.velocity, dt)
            proj.age += dt

            result = collision.sweep_projectile(
                proj.prev_position, new_pos, proj.radius, self.terrain, self.tanks, proj.owner
            )
            if result is not None:
                self.explosions.append(Explosion(position=pygame.Vector2(result.point)))
                if result.kind == "tank" and result.tank_index is not None:
                    self._apply_damage(self.tanks[result.tank_index], config.PROJECTILE_DAMAGE)
                continue  # projectile consumed on impact

            margin = config.PROJECTILE_OFFSCREEN_MARGIN_PX
            out_of_bounds = new_pos.x < -margin or new_pos.x > config.SCREEN_WIDTH + margin
            if proj.age >= config.PROJECTILE_MAX_LIFETIME or out_of_bounds:
                continue  # expire silently; safety net, should rarely trigger

            proj.position = new_pos
            survivors.append(proj)

        self.projectiles = survivors

    def _apply_damage(self, tank: Tank, amount: float) -> None:
        tank.hp = max(0.0, tank.hp - amount)
        if tank.hp <= 0.0:
            tank.alive = False

    def _update_explosions(self, dt: float) -> None:
        for explosion in self.explosions:
            explosion.timer += dt
        self.explosions = [e for e in self.explosions if not e.finished]

    def _check_win_condition(self) -> None:
        if self.state != GameState.PLAYING:
            return
        alive = [i for i, t in enumerate(self.tanks) if t.alive]
        if len(alive) <= 1:
            self.state = GameState.GAME_OVER
            self.winner = alive[0] if alive else None
