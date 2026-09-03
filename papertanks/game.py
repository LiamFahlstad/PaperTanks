"""Main loop orchestration: input -> simulation -> render -> present.

Uses the standard fixed-timestep accumulator pattern so physics behaves
identically regardless of display refresh rate:
    1. Measure real elapsed time, clamp it (MAX_FRAME_TIME) to avoid a
       runaway catch-up loop after a long stall (breakpoint, window drag).
    2. Add it to an accumulator.
    3. While the accumulator holds at least one fixed step, advance the
       simulation by exactly config.FIXED_DT and consume that step.
    4. Render once per real frame, interpolating using the leftover
       fraction of a step (`alpha`) for smooth motion.

No gameplay rule lives in this module - it only wires the pieces
together and reacts to window-level events (quit, pause, restart, focus
loss). Window resizing is intentionally not supported yet: the window is
a fixed size for this slice, which keeps the renderer's coordinate
system trivial; a future slice can add scaling/letterboxing.
"""

from __future__ import annotations

from typing import Sequence

import pygame

from . import config
from . import controls
from .render import Renderer
from .world import Intent, World


def clamp_frame_time(frame_time: float, max_frame_time: float = config.MAX_FRAME_TIME) -> float:
    """Clamp a real-time frame delta so a long stall (breakpoint, window
    drag) can't force an unbounded run of catch-up physics steps once
    execution resumes ("spiral of death")."""
    return min(frame_time, max_frame_time)


def advance_simulation(
    world: World,
    accumulator: float,
    frame_time: float,
    intents: Sequence[Intent],
    fixed_dt: float = config.FIXED_DT,
) -> float:
    """Advance `world` by as many fixed-size steps as the accumulated time
    covers, and return the leftover accumulator (always in [0, fixed_dt)).

    Pulled out of Game.run() so the fixed-timestep accumulator pattern -
    the part that actually determines simulation correctness - can be
    unit-tested with a plain object and numbers, without a real pygame
    window, Clock, or event loop.
    """
    accumulator += frame_time
    while accumulator >= fixed_dt:
        world.step(fixed_dt, intents)
        accumulator -= fixed_dt
    return accumulator


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.world = World()
        self.renderer = Renderer()
        self.running = True

    def run(self) -> None:
        accumulator = 0.0
        try:
            while self.running:
                frame_time = self.clock.tick(config.MAX_RENDER_FPS) / 1000.0
                frame_time = clamp_frame_time(frame_time)

                self._handle_events()
                if not self.running:
                    break

                keys_pressed = pygame.key.get_pressed()
                intents = controls.build_intents(keys_pressed)

                accumulator = advance_simulation(self.world, accumulator, frame_time, intents)

                alpha = accumulator / config.FIXED_DT
                self.renderer.draw(self.screen, self.world, alpha)
                pygame.display.flip()
        finally:
            pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == config.KEY_QUIT:
                    self.running = False
                elif event.key == config.KEY_PAUSE:
                    self.world.toggle_pause()
                elif event.key == config.KEY_RESTART:
                    self.world.restart()
            elif event.type == pygame.WINDOWFOCUSLOST:
                # Auto-pause on focus loss so the duel doesn't keep firing
                # while the player is tabbed away; resuming is an explicit
                # choice (press P) rather than automatic on refocus.
                self.world.pause()


def main() -> None:
    Game().run()
