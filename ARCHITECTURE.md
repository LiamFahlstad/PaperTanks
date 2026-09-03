# PaperTanks — Architecture & Design

This document explains how PaperTanks is built and *why* it's built that
way. It's meant to be the reference for extending the game without
fighting the structure that's already here.

## 1. What the game is

A side-view artillery duel. Two tanks sit on flat ground, facing each
other. Each player adjusts their tank's aim angle and shot power, then
fires a projectile that arcs under gravity. A hit does fixed damage;
the first tank to 0 HP loses.

This mechanic was chosen deliberately for a *first* slice: it exercises
both physics (a real ballistic trajectory) and collision (projectile vs.
ground, projectile vs. tank) with the smallest possible amount of
supporting code — no movement, no inventory, no turns, no animation
system. It's a complete vertical slice, not a stub.

## 2. Module map

All source lives flat at the repo root — this project is a single game,
not a library meant to be imported elsewhere, so a `papertanks/` package
wrapper would only add a directory level with no benefit.

```
config.py      constants, tuning values, key bindings, conventions
entities.py    plain data: Terrain, Tank, Projectile, Explosion
physics.py     pure gravity/position integration functions
collision.py   circle-vs-rect test, tunneling-safe sweep
world.py       simulation rules — the only place gameplay happens
controls.py    keyboard state -> per-tank Intent
render.py      draws World state to a Surface; never mutates it
game.py        the fixed-timestep main loop; wires everything together
main.py        `python main.py` entry point
```

Each module answers exactly one question:

| Module        | Question it answers                                   |
|----------------|--------------------------------------------------------|
| `entities.py`  | What *is* a tank / projectile / terrain?               |
| `physics.py`   | How does a thing move under gravity?                   |
| `collision.py` | Are two shapes touching?                               |
| `world.py`     | What happens each tick, given intents and physics?     |
| `controls.py`  | Which keys mean "aim up" / "fire" / etc.?               |
| `render.py`    | How does current state look on screen?                 |
| `game.py`      | In what order do input, simulation and drawing happen? |

The dependency direction is one-way and shallow:

```
game.py ──> controls.py ──> world.py ──> physics.py
   │                            │      └─> collision.py
   │                            └─────────> entities.py
   └──> render.py ──────────────────────> entities.py / world.py (read-only)
```

`render.py` and `controls.py` never talk to each other, and neither one
reaches into `physics.py` or `collision.py` directly — they only see
`World`'s public state. That's what keeps "simulate" and "present"
independently testable and independently replaceable (e.g. controls
could be swapped for a gamepad, or render swapped for a different
graphics backend, without touching the other).

## 3. The game loop: fixed timestep with interpolation

`game.py` is intentionally the least interesting file in the project —
it contains zero gameplay rules. Its only job is orchestration:

```python
frame_time = clock.tick(MAX_RENDER_FPS) / 1000.0
frame_time = min(frame_time, MAX_FRAME_TIME)   # clamp stalls

accumulator += frame_time
while accumulator >= FIXED_DT:
    world.step(FIXED_DT, intents)
    accumulator -= FIXED_DT

alpha = accumulator / FIXED_DT
renderer.draw(screen, world, alpha)
```

**Why fixed timestep at all?** If physics used the real, variable frame
delta, the exact same input sequence could produce different
trajectories depending on machine speed or a momentary frame hitch —
gravity arcs would be inconsistent, and collisions could tunnel
unpredictably. Advancing simulation in fixed `1/120s` chunks
(`PHYSICS_HZ = 120` in `config.py`) makes the simulation deterministic:
same inputs, same result, every time, on every machine.

**Why an accumulator instead of just running at 120 FPS?** Display
refresh rates vary (60Hz, 75Hz, 144Hz, uncapped) and are rarely a clean
multiple of 120Hz. The accumulator lets rendering run at its own pace
(`MAX_RENDER_FPS = 240` is just a cap, not a target) while physics
always advances in true, identical increments — the two are decoupled.

**Why the `MAX_FRAME_TIME` clamp?** Without it, a debugger breakpoint or
the user dragging the window (which stalls the loop) would leave a huge
`frame_time` in the accumulator, forcing hundreds of catch-up physics
steps in a row (the "spiral of death") once execution resumes. Clamping
the real delta to 0.25s means the simulation simply "loses" wall-clock
time it can't keep up with, rather than freezing the game trying to
catch up.

**Why interpolate with `alpha`?** After the `while` loop, the
accumulator holds a leftover fraction of a physics step that hasn't
happened yet. If rendering just drew the last *completed* physics
state, fast-moving objects (the projectile) would visibly stutter at
low display refresh rates relative to the physics rate. `render.py`
uses `alpha` to draw the projectile blended between its previous and
current tick position (`prev_position.lerp(position, alpha)`), which is
purely cosmetic — it never feeds back into simulation.

## 4. Physics model

Conventions, documented once in `config.py` and relied on everywhere
else:

- **Coordinate system**: Pygame default — origin top-left, x right, y
  *down*.
- **Units**: pixels, pixels/second, pixels/second².
- **Gravity**: a positive constant (`GRAVITY = 900.0`) added to
  y-velocity each tick, because "down" is positive y here. This is a
  common source of sign-bugs in 2D games, so it's called out explicitly
  rather than left implicit.
- **Angles**: `aim_deg` is measured from horizontal (0° flat, 90°
  straight up) independent of which way the tank faces. `Tank.facing`
  (+1/-1) flips the horizontal velocity component, so aim input doesn't
  need to know which side of the arena the tank is on.

`physics.py` contains exactly two pure functions:

```python
def apply_gravity(velocity, gravity, dt) -> Vector2
def integrate_position(position, velocity, dt) -> Vector2
```

They take values in, return new values, and touch nothing else — no
`World`, no `Tank`, no globals. This is **semi-implicit (symplectic)
Euler** integration: velocity is updated from acceleration *first*,
then position is updated using the *new* velocity (rather than the old
one, as in explicit Euler). For a fixed timestep this is more
numerically stable and energy-consistent, and it's the standard choice
for simple game physics — a full physics engine (Runge-Kutta, sequential
impulse solvers, etc.) would be substantial overkill for "a ball falls
under gravity."

Being pure functions also means they can be unit-tested with plain
numbers, with no Pygame window, event loop, or `World` instance
required.

## 5. Collision model

Two shape types only: axis-aligned rectangles (tank bodies) and a
circle (the projectile). No polygons, no physics-engine integration —
`collision.py`'s docstring states this explicitly as a scope decision,
not an oversight, because the shapes in this game don't need anything
richer.

```python
def circle_vs_rect(center, radius, rect) -> bool
```

Standard closest-point test: clamp the circle's center into the rect's
bounds, measure the distance from that clamped point to the center, and
compare against the radius.

### Tunneling and the sweep

A fast projectile can, in principle, cross an entire 28px-tall tank
body within a single `1/120s` tick — jumping from "clearly above it" to
"clearly below it" without the discrete end-of-tick position ever
overlapping the tank. This is the classic tunneling problem in
fixed-timestep physics.

Rather than a full continuous-collision (swept-shape) solver,
`sweep_projectile()` takes the cheaper, sufficient route for this game's
speeds: it samples the straight-line motion segment for the tick at
increments no larger than the projectile's radius, and narrow-phase
tests each sample point. This was validated directly with a synthetic
test that fires a projectile fast enough to cross an entire tank body
in one tick and confirms the hit still registers.

### Why no broad phase?

With at most two tanks and a handful of live projectiles, a spatial
broad phase (grid/quadtree) would add real complexity (data structure
maintenance, invalidation on movement) for zero measurable benefit at
this scale. `collision.py`'s docstring calls this out explicitly: every
projectile is narrow-phase tested against the terrain and every tank,
every tick. If the entity count grows by an order of magnitude later,
this is the first place to revisit — not before.

### Collision detection vs. response

`sweep_projectile()` only *detects* — it returns a `CollisionResult`
(what was hit, where, which tank if applicable) and does nothing else.
`World._integrate_projectiles()` is what *responds*: spawning an
explosion, applying damage, removing the projectile. Keeping detection
free of side effects makes it independently testable and reusable if a
different response is ever needed (e.g. a shield that blocks damage but
still shows an impact).

## 6. `World`: where the game actually lives

`world.py` is the only module that knows game *rules*. Everything else
is plumbing around it. Its single entry point:

```python
world.step(dt: float, intents: Sequence[Intent]) -> None
```

is called once per fixed tick with `dt` always equal to `FIXED_DT`.
Inside, in order:

1. Apply each tank's `Intent` — clamp aim/power changes, tick down the
   reload timer, fire if requested and off cooldown.
2. Integrate all projectiles (gravity, position, collision test,
   damage/explosion on impact).
3. Age out explosions.
4. Check the win condition.

`Intent` is a small, input-agnostic struct:

```python
@dataclass
class Intent:
    aim_delta: float = 0.0   # -1, 0, or 1
    power_delta: float = 0.0 # -1, 0, or 1
    fire: bool = False
```

`World` — not `controls.py` — multiplies these deltas by the configured
rate and `dt`. That separation matters: `controls.py` only has to
answer "is the aim-up key currently held," and has no idea what a
degree-per-second rate is. This means input could later come from a
replay file, an AI opponent, or a network message, and `World` would
behave identically, because it only ever consumes the same small
`Intent` shape.

`GameState` (`PLAYING` / `PAUSED` / `GAME_OVER`) is also decided here:
`step()` is a no-op whenever the state isn't `PLAYING`, so pause is
"the simulation doesn't advance," not a scattered set of `if not
paused` checks throughout the codebase.

## 7. Input: `controls.py`

`build_intents()` samples `pygame.key.get_pressed()` once per real
frame and turns held keys into the two players' `Intent`s. It's a pure
translation layer with no gameplay knowledge:

```python
def build_intents(keys_pressed) -> List[Intent]
```

Held keys are sampled at display frame rate, not physics rate — the
same `Intent` list is fed into every fixed tick that happens to run
within one real frame. This is a standard, acceptable tradeoff: the
*sampling* of "is this key down" is tied to real frame rate, but the
*effect* of that input (how many degrees of aim change it produces) is
computed inside `World.step` using the fixed `dt`, so aim/power values
end up frame-rate independent even though input sampling itself isn't.

Firing has no debounce logic here — holding fire just means "fire
whenever `World`'s per-tank `reload_timer` allows it." Shot pacing has
exactly one source of truth (`World`), not two.

## 8. Rendering: `render.py`

`Renderer.draw(screen, world, alpha)` is read-only with respect to
`World` — it never sets simulation state, never advances anything, and
contains no gameplay rules (no damage math, no collision checks). It
draws, in order: background, terrain, tanks (body + barrel + HP bar),
projectiles (interpolated by `alpha`), explosions, HUD text, and any
pause/game-over overlay.

This one-way read is what makes it safe to swap rendering later
(different art style, a debug overlay, a headless test run) without
risking gameplay side effects sneaking into a `draw()` call — a mistake
explicitly called out as something to avoid (physics updates belong in
`step()`, never in `draw()`).

## 9. Configuration: `config.py`

Every tunable number in the game — screen size, gravity, tank
dimensions, aim/power rates and limits, projectile damage/radius,
colors, key bindings, the RNG seed — lives in one file. None of it is
hardcoded inside behavior code. This means balancing the game (heavier
gravity, faster reload, wider aim range) is a one-line change in a
predictable location, not a hunt through `world.py` or `entities.py`.

The module's docstring is also where the project's conventions
(coordinate system, units, angle convention, timestep) are written down
once, rather than left to be inferred from scattered code — anyone
extending the game has one place to check before writing new physics or
collision code.

## 10. Design principles this project follows

These are the judgment calls that shaped the structure above, stated
explicitly so future changes can stay consistent with them:

- **Simulate first, render second, never mix the two.** `World.step()`
  and `Renderer.draw()` are on opposite sides of a one-way read. This
  is what makes the simulation independently testable (see the headless
  logic smoke test) without a window or event loop.
- **Plain data over clever objects.** `entities.py` holds dataclasses
  with only geometric queries (`rect()`, `muzzle_position()`) — no
  `update()` methods, no behavior. Behavior lives in exactly one place
  (`world.py`), so there's never a question of "does this tank update
  itself, or does something else update it?"
- **Earn abstractions, don't pre-build them.** There's no ECS, no
  event bus, no service locator, no broad-phase collision structure —
  each was considered and explicitly deferred until the entity count or
  feature set actually demands it (documented inline where the decision
  was made, e.g. `collision.py`'s broad-phase note). Two tanks and a
  handful of projectiles don't need an entity-component framework; they
  need a list.
- **Determinism over convenience.** Fixed timestep, a seeded RNG
  (`config.RNG_SEED`), and pure integration functions mean the same
  input sequence always produces the same outcome — essential for
  debugging physics/collision issues and for eventually writing
  regression tests around specific trajectories.
- **State transitions are explicit.** Pause, restart, and focus-loss
  are each a deliberate, named code path in `game.py`/`world.py` (e.g.
  focus loss calls `world.pause()`, not a `visible` flag checked
  ad-hoc in the render loop) rather than inferred from other state.
- **Conventions are written down once.** Coordinate system, units,
  angle meaning, and gravity sign all live in `config.py`'s docstring
  specifically so they don't have to be re-derived (or guessed
  inconsistently) every time new physics code is added.

## 11. Known scope boundaries (not bugs)

These are deliberate omissions for this first slice, not oversights:

- Tanks don't move — only aim/power/fire. Movement is the natural next
  addition (see below).
- Terrain is flat. `Terrain.height_at(x)` already exists as the single
  seam a heightmap or destructible terrain would plug into, but nothing
  currently varies it.
- No window resizing — the screen is a fixed size, keeping the
  renderer's coordinate math trivial.
- No sound/particles beyond a simple expanding-ring explosion.
- No turn structure — both players can aim/fire simultaneously,
  paced only by each tank's own reload cooldown.

## 12. Natural next slices, in order

1. **Tank movement** — add per-tank speed/friction constants to
   `config.py`, extend `Intent` with a move axis, and re-derive tank
   position against `terrain.height_at(x)` each tick in `World`.
2. **Destructible / uneven terrain** — only `Terrain.height_at()` and
   the ground-drawing code in `render.py` need to change; tanks,
   projectiles, and collision code already go through that seam.
3. **Audio/particle feedback** on fire and impact.
4. **Turn-based mode**, if simultaneous play turns out to feel wrong —
   would live entirely in `World`/`GameState`, without touching physics
   or collision.

Each of these extends an existing seam rather than requiring a
restructure — which was the point of keeping the modules this narrow
from the start.
