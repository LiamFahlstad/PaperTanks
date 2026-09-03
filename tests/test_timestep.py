"""The fixed-timestep accumulator pattern (game.clamp_frame_time /
game.advance_simulation), extracted from Game.run() specifically so it can
be exercised here without a real pygame window/Clock/event loop.
"""

from __future__ import annotations

from papertanks import config
from papertanks.game import advance_simulation, clamp_frame_time


class _FakeWorld:
    """Records World.step() calls without any real simulation/pygame work."""

    def __init__(self) -> None:
        self.step_calls: list[float] = []

    def step(self, dt: float, intents) -> None:
        self.step_calls.append(dt)


def test_clamp_frame_time_passes_small_deltas_through():
    assert clamp_frame_time(0.01, max_frame_time=0.25) == 0.01


def test_clamp_frame_time_clamps_large_stalls():
    # A debugger breakpoint or window-drag stall should never leak a huge
    # frame_time into the accumulator (the "spiral of death" case).
    assert clamp_frame_time(5.0, max_frame_time=0.25) == 0.25


def test_advance_simulation_steps_exactly_once_per_fixed_dt():
    world = _FakeWorld()
    fixed_dt = config.FIXED_DT
    leftover = advance_simulation(world, accumulator=0.0, frame_time=fixed_dt, intents=[], fixed_dt=fixed_dt)

    assert len(world.step_calls) == 1
    assert world.step_calls[0] == fixed_dt
    assert leftover == 0.0


def test_advance_simulation_accumulates_partial_frames():
    world = _FakeWorld()
    fixed_dt = 1.0 / 120.0

    # Two frames of half a fixed step each should not trigger a physics
    # step until their sum reaches one full fixed_dt.
    acc = advance_simulation(world, accumulator=0.0, frame_time=fixed_dt / 2, intents=[], fixed_dt=fixed_dt)
    assert len(world.step_calls) == 0
    assert acc > 0.0

    acc = advance_simulation(world, accumulator=acc, frame_time=fixed_dt / 2, intents=[], fixed_dt=fixed_dt)
    assert len(world.step_calls) == 1


def test_advance_simulation_runs_multiple_catchup_steps():
    world = _FakeWorld()
    fixed_dt = 1.0 / 120.0
    # A little more than 3 fixed steps' worth of real time in one call.
    frame_time = fixed_dt * 3.4
    leftover = advance_simulation(world, accumulator=0.0, frame_time=frame_time, intents=[], fixed_dt=fixed_dt)

    assert len(world.step_calls) == 3
    assert 0.0 <= leftover < fixed_dt


def test_advance_simulation_leftover_always_below_one_fixed_dt():
    """The interpolation alpha (leftover / fixed_dt) must stay in [0, 1)
    for render.py's lerp to make sense - this is the invariant that
    guarantees that."""
    world = _FakeWorld()
    fixed_dt = 1.0 / 120.0
    accumulator = 0.0
    for frame_time in (0.013, 0.027, 0.009, 0.031, 0.002):
        accumulator = advance_simulation(world, accumulator, frame_time, intents=[], fixed_dt=fixed_dt)
        assert 0.0 <= accumulator < fixed_dt


def test_clamp_then_advance_bounds_catchup_steps_after_a_stall():
    """The full pipeline used by Game.run(): clamp a huge stall, then feed
    the clamped value into the accumulator. Without the clamp this would
    request MAX_FRAME_TIME/fixed_dt-many steps; with it, the step count is
    bounded by config.MAX_FRAME_TIME regardless of how long the real stall
    was."""
    world = _FakeWorld()
    fixed_dt = config.FIXED_DT
    huge_stall = 30.0  # seconds - e.g. a breakpoint left hanging

    clamped = clamp_frame_time(huge_stall, max_frame_time=config.MAX_FRAME_TIME)
    advance_simulation(world, accumulator=0.0, frame_time=clamped, intents=[], fixed_dt=fixed_dt)

    max_expected_steps = int(config.MAX_FRAME_TIME / fixed_dt) + 1
    assert len(world.step_calls) <= max_expected_steps
