"""Drawing only. Reads World state; never mutates it, never advances
simulation. All positions drawn here are interpolated between a
projectile's previous and current fixed-step positions using `alpha`
(the accumulator's leftover fraction of a physics tick), so motion looks
smooth even when the display refresh rate doesn't evenly divide
config.PHYSICS_HZ.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import pygame

import config
from entities import Explosion, Projectile, Tank
from world import GameState, World


class Renderer:
    def __init__(self) -> None:
        pygame.font.init()
        self._font = pygame.font.SysFont(None, 24)
        self._big_font = pygame.font.SysFont(None, 48)
        # Keyed by (sprite_key, facing) since a tank's sprite is flipped once
        # for its facing and then reused every frame rather than re-scaled
        # and re-flipped each draw call.
        self._tank_sprites: Dict[Tuple[str, int], pygame.Surface] = {}

    def draw(self, screen: pygame.Surface, world: World, alpha: float) -> None:
        screen.fill(config.COLOR_BG)
        self._draw_terrain(screen, world)
        for tank in world.tanks:
            self._draw_tank(screen, world, tank)
        for proj in world.projectiles:
            self._draw_projectile(screen, proj, alpha)
        for explosion in world.explosions:
            self._draw_explosion(screen, explosion)
        self._draw_hud(screen, world)

        if world.state == GameState.PAUSED:
            self._draw_center_text(screen, "PAUSED", "P to resume")
        elif world.state == GameState.GAME_OVER:
            title = "DRAW" if world.winner is None else f"PLAYER {world.winner + 1} WINS"
            self._draw_center_text(screen, title, "R to restart")

    def _draw_terrain(self, screen: pygame.Surface, world: World) -> None:
        ground_y = round(world.terrain.height_at(0))
        rect = pygame.Rect(0, ground_y, config.SCREEN_WIDTH, config.SCREEN_HEIGHT - ground_y)
        pygame.draw.rect(screen, config.COLOR_GROUND, rect)

    def _draw_tank(self, screen: pygame.Surface, world: World, tank: Tank) -> None:
        rect = tank.rect(world.terrain)
        sprite = self._get_tank_sprite(tank) if tank.alive else None
        if sprite is not None:
            screen.blit(sprite, rect.topleft)
        else:
            color = config.COLOR_TANK_DEAD if not tank.alive else tank.color
            pygame.draw.rect(screen, color, rect)

        if tank.alive:
            muzzle = tank.muzzle_position(world.terrain)
            origin = (rect.centerx, rect.top)
            pygame.draw.line(screen, config.COLOR_BARREL, origin, muzzle, width=3)

        self._draw_hp_bar(screen, rect, tank)

    def _get_tank_sprite(self, tank: Tank) -> Optional[pygame.Surface]:
        """Load, scale to TANK_WIDTH/HEIGHT and cache a tank's sprite.

        Returns None when the tank has no sprite_key, so _draw_tank can
        fall back to the plain colored rect - sprites are opt-in per
        tank, not a requirement of the CollisionBody/rect-based
        collision and layout code, which is unaffected either way.
        """
        if tank.sprite_key is None:
            return None

        cache_key = (tank.sprite_key, tank.facing)
        sprite = self._tank_sprites.get(cache_key)
        if sprite is None:
            path = os.path.join(config.SPRITE_DIR, f"{tank.sprite_key}.png")
            raw = pygame.image.load(path).convert_alpha()
            sprite = pygame.transform.scale(raw, (config.TANK_WIDTH, config.TANK_HEIGHT))
            if tank.facing < 0:
                sprite = pygame.transform.flip(sprite, True, False)
            self._tank_sprites[cache_key] = sprite
        return sprite

    def _draw_hp_bar(self, screen: pygame.Surface, rect: pygame.Rect, tank: Tank) -> None:
        bar_width = rect.width
        bar_height = 6
        bar_x = rect.left
        bar_y = rect.top - bar_height - 6
        pygame.draw.rect(screen, config.COLOR_HP_BG, (bar_x, bar_y, bar_width, bar_height))
        fraction = max(0.0, tank.hp / config.TANK_MAX_HP)
        pygame.draw.rect(screen, config.COLOR_HP_FG, (bar_x, bar_y, bar_width * fraction, bar_height))

    def _draw_projectile(self, screen: pygame.Surface, proj: Projectile, alpha: float) -> None:
        draw_pos = proj.prev_position.lerp(proj.position, alpha)
        pygame.draw.circle(screen, config.COLOR_PROJECTILE, (round(draw_pos.x), round(draw_pos.y)), round(proj.radius))

    def _draw_explosion(self, screen: pygame.Surface, explosion: Explosion) -> None:
        radius = config.EXPLOSION_MAX_RADIUS * explosion.progress
        pos = (round(explosion.position.x), round(explosion.position.y))
        pygame.draw.circle(screen, config.COLOR_EXPLOSION, pos, max(1, round(radius)), width=2)

    def _draw_hud(self, screen: pygame.Surface, world: World) -> None:
        labels = [
            f"P1  aim {world.tanks[0].aim_deg:5.1f}deg  power {world.tanks[0].power:5.0f}",
            f"P2  aim {world.tanks[1].aim_deg:5.1f}deg  power {world.tanks[1].power:5.0f}",
        ]
        for i, text in enumerate(labels):
            surface = self._font.render(text, True, config.COLOR_TEXT)
            x = 12 if i == 0 else config.SCREEN_WIDTH - surface.get_width() - 12
            screen.blit(surface, (x, 12))

    def _draw_center_text(self, screen: pygame.Surface, title: str, subtitle: str) -> None:
        title_surface = self._big_font.render(title, True, config.COLOR_TEXT)
        subtitle_surface = self._font.render(subtitle, True, config.COLOR_TEXT)
        cx = config.SCREEN_WIDTH // 2
        cy = config.SCREEN_HEIGHT // 2
        screen.blit(title_surface, title_surface.get_rect(center=(cx, cy - 16)))
        screen.blit(subtitle_surface, subtitle_surface.get_rect(center=(cx, cy + 24)))
