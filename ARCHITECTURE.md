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

All game code lives in one importable package, `papertanks/`, so the
repo root stays down to a single entry point plus project metadata.
`main.py` (`python main.py`) is the only source file at the root; it
does nothing but `from papertanks.game import main`. Every module below
imports its project-internal neighbors with relative imports (`from .
import config`, `from .shapes import Polygon`, etc.) — this is still a
single game, not a library meant to be imported by other projects, so
the package boundary exists purely to declutter the root, not to define
a reusable public API or add layers beyond what's here.

```
papertanks/__init__.py    empty; marks the package
papertanks/config.py      constants, tuning values, key bindings, conventions
papertanks/shapes.py      collision-shape geometry value-types: Circle, Rectangle, Polygon
papertanks/entities.py    plain data: Terrain, Tank, Projectile, Explosion
papertanks/physics.py     pure gravity/position integration functions
papertanks/collision.py   circle-vs-rect / circle-vs-polygon tests, tunneling-safe sweep
papertanks/world.py       simulation rules — the only place gameplay happens
papertanks/controls.py    keyboard state -> per-tank Intent
papertanks/render.py      draws World state to a Surface; never mutates it
papertanks/sprite_cache.py loads/scales/flips/caches sprite Surfaces + their masks
papertanks/sprite_shape.py builds a collision Polygon from a sprite's alpha mask
papertanks/game.py        the fixed-timestep main loop; wires everything together
main.py                   `python main.py` entry point (repo root)
```

Two sibling directories sit alongside `papertanks/` and `main.py` at the
repo root: `assets/sprites/` (art, e.g. `tank1.png` - `config.SPRITE_DIR`,
still resolved relative to the process's current working directory, not
`papertanks/`'s location — see §9) and `tests/` (see §13). Neither is
game code, so neither lives inside the `papertanks/` package; `tests/`
imports it the same way an external caller would, with absolute imports
(`from papertanks import config`, `from papertanks.world import World`),
which is also what keeps the test suite honest about what the package
actually exposes.

Each module answers exactly one question:

| Module                       | Question it answers                                   |
|-------------------------------|--------------------------------------------------------|
| `papertanks/shapes.py`        | What geometry value-types exist for collision shapes?  |
| `papertanks/entities.py`      | What *is* a tank / projectile / terrain?               |
| `papertanks/physics.py`       | How does a thing move under gravity?                   |
| `papertanks/collision.py`     | Are two shapes touching?                               |
| `papertanks/world.py`         | What happens each tick, given intents and physics?     |
| `papertanks/controls.py`      | Which keys mean "aim up" / "fire" / etc.?               |
| `papertanks/render.py`        | How does current state look on screen?                 |
| `papertanks/sprite_cache.py`  | Which sprite Surface (and its mask) belongs to this key/facing? |
| `papertanks/sprite_shape.py`  | What collision geometry does this sprite's art actually have? |
| `papertanks/game.py`          | In what order do input, simulation and drawing happen? |
| `main.py`                     | Root-level entry point; imports and calls `papertanks.game.main()`. |

The dependency direction is one-way and shallow (module names below are
relative to `papertanks/`, and every arrow is a relative import — e.g.
`world.py`'s edge to `physics.py` is `from . import physics`):

```
game.py ──> controls.py ──> world.py ──> physics.py
   │                            │      └─> collision.py ──> shapes.py
   │                            └─────────> entities.py ──> shapes.py
   │                                            │        └─> sprite_cache.py
   │                                            │              └─> sprite_shape.py
   │                                            │                    └─> shapes.py
   └──> render.py ──────────────────────> entities.py / world.py (read-only)
                          └─────────────> sprite_cache.py

main.py (repo root) ──> papertanks/game.py
```

`render.py` and `controls.py` never talk to each other, and neither one
reaches into `physics.py` or `collision.py` directly — they only see
`World`'s public state. That's what keeps "simulate" and "present"
independently testable and independently replaceable (e.g. controls
could be swapped for a gamepad, or render swapped for a different
graphics backend, without touching the other).

`shapes.py` is the lowest leaf in the graph: it defines
`Shape`/`Circle`/`Rectangle`/`Polygon` (see §2's "Object hierarchy"
subsection and §5) with no project-level import of its own beyond
`pygame`. `sprite_shape.py` depends on it (to construct a `Polygon` from
a sprite's alpha mask) and nothing else in the project; `sprite_cache.py`
depends on `shapes.py` (for the `Polygon` type) and `sprite_shape.py`
(to build one); `entities.py` depends on `shapes.py` (for
`Tank.collision_shape()`'s return types) and on `sprite_cache.py` (to
fetch the cached, sprite-mask-derived `Polygon` for a tank with a
`sprite_key` — see §5); `collision.py` depends on `shapes.py` for the
same geometry types its narrow-phase tests dispatch on, alongside `Tank`/
`Terrain` from `entities.py`. Every one of those imports is an ordinary,
top-level `import` — no `TYPE_CHECKING` guard, no function-local deferred
import anywhere in this graph, because there is no cycle to route around:
none of `shapes.py`, `sprite_shape.py`, or `sprite_cache.py` imports
`entities.py`, `world.py`, or `render.py`. `render.py` separately calls
`sprite_cache.py` directly (to load/scale/flip/cache sprite `Surface`s
for drawing) — a second, independent edge into the same leaf, not a path
back up from `sprite_cache.py` toward `render.py`.

This is a correction of an earlier structure, worth calling out
explicitly: `Shape`/`Circle`/`Rectangle`/`Polygon` used to live inside
`entities.py` itself. That forced `sprite_shape.py` — a module with no
business knowing about tanks, terrain, or the game world — to import
`entities.py` just to construct a `Polygon`, which in turn meant
`entities.py`'s own (real, needed) dependency on `sprite_cache.py` closed
a three-module import cycle (`entities.py -> sprite_cache.py ->
sprite_shape.py -> entities.py`). The fix was not to route around the
cycle (a `TYPE_CHECKING`-only import plus a deferred, function-local
import were tried and rejected) but to remove its cause: the geometry
types were never actually about tanks/terrain/entities, so they moved to
their own leaf module. See `shapes.py`'s module docstring for the full
reasoning.

### Object hierarchy

`entities.py` also defines a small ABC hierarchy that the four
concrete classes sit under:

```
WorldObject        anything that exists and is drawn
  └─ CollisionBody  + has a solid shape (collision_shape())
       └─ RigidBody + is physics-integrated (gravity/velocity each tick)
```

`Tank` is a `CollisionBody` (has a rect or sprite-derived polygon shape,
see §5). It's still not a `RigidBody`: horizontal movement (§6, §12 item
1) is its own velocity/friction integration living in `world.py`, not a
use of `physics.py`'s gravity/integration functions, and aim/power/
reload remain direct state changes, not physics.
`Projectile` is a `RigidBody` (a circle shape, integrated by
`physics.py` each tick). `Explosion` is a bare `WorldObject` — it has
no collision shape, and the type now states that instead of leaving it
as an implicit consequence of `world.py` never checking it. `Terrain`
sits outside the hierarchy entirely: it's a singleton environment
object with a height-function shape, not a "body."

The base classes carry **one stored field**, not zero: `WorldObject`
declares `sprite_key: Optional[str] = None`, the same field `Tank`
alone used to own. It moved up because its type and meaning are
identical for every entity ("an optional lookup key; `None` means fall
back to primitive-shape drawing") — unlike position, where `Tank`'s
`x` is terrain-relative and derived on demand while `Projectile`'s and
`Explosion`'s `position` is a stored free `Vector2`, so a shared
stored-*position* field is still rejected for exactly the original
reason (it would force a redundant, sync-prone field onto `Tank`).
`sprite_key` has no such mismatch, so hanging it on `WorldObject` lets
any entity opt into sprite rendering without redeclaring the field or
affecting collision/layout code, which never reads it.

This did revive the classic dataclass field-ordering problem: a
base-class field with a default (`sprite_key`) would otherwise have to
land *before* a subclass's required fields (`Tank.x`, `.facing`,
`.color`) in the generated `__init__`, which Python rejects. The fix is
`@dataclass(kw_only=True)` on `WorldObject` and on every concrete
subclass (`Tank`, `Projectile`, `Explosion`) — keyword-only fields have
no positional ordering constraint regardless of MRO position. This was
free: every constructor call site in the codebase already used keyword
arguments, so no call site changed. The alternative considered was a
separate opt-in mixin dataclass (composed into only the entities that
want it) instead of a field on `WorldObject` itself; `WorldObject` was
chosen because its own docstring already scopes it to "anything that
exists *and is drawn*," which is precisely sprite rendering's concern,
so a second parallel type added no clarity.

`Shape`/`Circle`/`Rectangle`/`Polygon` are a second, unrelated small
hierarchy — the geometry types `collision_shape()` can return — and
because they're genuinely unrelated to "what is a tank/projectile/
terrain," they live in their own module, `shapes.py`, not in
`entities.py` (see this section's dependency-graph discussion above for
why that separation is what keeps the import graph acyclic). `Circle`
existed already; `Rectangle` wraps the same geometry `Tank.rect()`
already returns as a raw `pygame.Rect`, as an explicit
`topleft`/`width`/`height` value type so every `Shape` has the same
plain-frozen-dataclass shape as `Circle`. `Polygon` (`points:
tuple[Vector2, ...]`) is now in active use for tanks with sprite art —
see §5. `Shape` itself, like `WorldObject`, carries zero fields; it
exists only so `CollisionBody.collision_shape()` (`entities.py`) has one
return type to declare.

This hierarchy now has a polymorphic caller: `collision.py`'s
`sweep_projectile()` calls `tank.collision_shape(terrain)` for every
tank (instead of reading `tank.rect(terrain)` directly, which it used to
do specifically to avoid two ways of fetching the same geometry — see
`CollisionBody`'s docstring for how that tension was resolved) and
dispatches on whichever concrete `Shape` comes back — a sprite-derived
`Polygon` for a tank with real art (only `"tank1"` today), or `Rectangle`
for a tank with no `sprite_key`. `World` still holds three separate
concrete lists; that part of the "no polymorphic caller" story is
unchanged. What was a deliberately-early seam for entity types and
sprite rendering (see §10, "earn abstractions") is, for `Polygon`
specifically, no longer ahead of need.

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

Three shape types are narrow-phase tested: circles (the projectile),
axis-aligned rectangles, and simple polygons, convex or concave but
non-self-intersecting (a sprite-backed tank's silhouette). Still no
physics-engine integration — `collision.py`'s docstring states this
explicitly as a scope decision, not an oversight, because the shapes in
this game don't need anything richer.

`shapes.py` defines a `Polygon` shape (`points: tuple[Vector2, ...]`)
alongside `Circle` and `Rectangle`, under a common `Shape` base. It
started as a data-shape seam with no constructor and no narrow-phase
test (see git history / earlier drafts of this doc); both now exist:
`sprite_shape.polygon_from_sprite_mask()` builds a `Polygon` from a
sprite's alpha-mask silhouette (a low-res, centroid-relative outline,
optionally shrunk/expanded — see the module docstring for the angle-
bucketing and empty-sector-interpolation rules), `sprite_cache.py`
caches one per `(sprite_key, facing)` and hands it to
`Tank.collision_shape()` (translated to world space), and
`circle_vs_polygon()` in `collision.py` is the matching narrow-phase
test, called from `sweep_projectile()` for any tank whose
`collision_shape()` returns a `Polygon`. A `Tank` with no `sprite_key`
(no art to derive a silhouette from) still returns `Rectangle`, tested
by the pre-existing `circle_vs_rect()`.

```python
def circle_vs_rect(center, radius, rect) -> bool
def circle_vs_polygon(center, radius, points) -> bool
```

`circle_vs_rect` is a standard closest-point test: clamp the circle's
center into the rect's bounds, measure the distance from that clamped
point to the center, and compare against the radius.

`circle_vs_polygon` handles polygons that aren't guaranteed convex
(sprite-derived shapes can have concave "shoulder" corners, e.g. a
turret narrower than the hull beneath it), so it can't shortcut to a
convex-only test: it checks whether the circle's center is inside the
polygon (even-odd ray cast) *or* whether any edge segment's closest
point to the center is within the radius — either condition alone is
correct for a possibly-concave, non-self-intersecting polygon.

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

1. Apply each tank's `Intent` — clamp aim/power changes, integrate
   horizontal movement (velocity/friction, clamped to the screen), tick
   down the reload timer, fire if requested and off cooldown.
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
    move_delta: float = 0.0  # -1, 0, or 1 (- left, + right)
    fire: bool = False
```

`World` — not `controls.py` — multiplies these deltas by the configured
rate and `dt`. That separation matters: `controls.py` only has to
answer "is the aim-up key currently held," and has no idea what a
degree-per-second rate is. This means input could later come from a
replay file, an AI opponent, or a network message, and `World` would
behave identically, because it only ever consumes the same small
`Intent` shape.

`move_delta` is handled differently from `aim_delta`/`power_delta`
inside `World._apply_movement`: instead of a direct per-tick rate
applied to a value, it accelerates/decelerates a stored
`Tank.velocity_x` (`TANK_MOVE_ACCEL` while a move key is held,
`TANK_MOVE_FRICTION` once released, both in `config.py`), which is then
integrated into `Tank.x` and clamped to the screen bounds. `Tank.x` is
the only stored position field a tank has; there's no stored y; because
`Tank.rect()`/`muzzle_position()` already call
`terrain.height_at(self.x)` on every call rather than caching it, a
tank's vertical placement re-derives itself from the terrain seam
automatically as `x` changes — no separate "sync to terrain" step is
needed in `World.step`.

`GameState` (`PLAYING` / `PAUSED` / `GAME_OVER`) is also decided here:
`step()` is a no-op whenever the state isn't `PLAYING`, so pause is
"the simulation doesn't advance," not a scattered set of `if not
paused` checks throughout the codebase.

### Turn-based mode (§12 item 4)

Two more fields on `World`, reset in `_reset()` (so `restart()` naturally
starts the next game on player 0's turn): `active_player: int` (index
into `self.tanks`, same convention as `Projectile.owner`/`World.winner`)
and `shot_fired_this_turn: bool`.

The rules:

- `_apply_intent` now takes the tank's index. Every tank's `reload_timer`
  still ticks down every tick regardless of whose turn it is (harmless,
  and it means `reload_timer` doesn't need its own turn-aware special
  case), but aim/power/move/fire are applied only when
  `tank_index == self.active_player`. The inactive tank's `Intent` is
  still computed by `controls.py` and passed into `step()` every frame —
  it's simply read and discarded, which is what makes this a pure
  `World`-side gate rather than something `controls.py` needs to know
  about.
- Firing additionally requires `not self.shot_fired_this_turn`
  (alongside the pre-existing `reload_timer <= 0.0` check) — one shot per
  turn, not just one shot per cooldown window. `_fire()` sets
  `shot_fired_this_turn = True`.
- A new `_advance_turn()`, called at the end of `step()` after
  `_check_win_condition()`, hands the turn to the other tank
  (`active_player = 1 - active_player`, `shot_fired_this_turn = False`)
  once a shot has been fired *and* both `self.projectiles` and
  `self.explosions` are empty again — i.e. the fired projectile has
  fully resolved (hit something and its explosion finished, expired
  off-screen, or hit its max lifetime) with no visual feedback still
  playing. It's skipped once `state == GameState.GAME_OVER`, checked
  after the win condition specifically so a game-ending shot doesn't
  hand off a turn nobody can play.
- The active tank keeps full aim/power/move control between firing and
  the turn passing — only a second *fire* is blocked. Movement/aim are
  not frozen post-fire; this was a deliberate scope choice (repositioning
  while a shot is still in the air is allowed), not an oversight, and is
  the one open question worth revisiting if playtesting says otherwise.

None of this reaches into `physics.py`/`collision.py`: a projectile still
integrates and collides exactly as before, and `_advance_turn()` only
reads the size of `self.projectiles`/`self.explosions`, never their
contents. `controls.py` is also unchanged — both players' keys are
sampled every frame regardless of whose turn it is, which is what §12
item 4 meant by "would live entirely in `World`/`GameState`."

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
whenever `World` allows it" (per-tank `reload_timer`, and, since §12
item 4, whether it's this tank's turn and it hasn't already fired this
turn). Shot pacing has exactly one source of truth (`World`), not two.

## 8. Rendering: `render.py`

`Renderer.draw(screen, world, alpha)` is read-only with respect to
`World` — it never sets simulation state, never advances anything, and
contains no gameplay rules (no damage math, no collision checks). It
draws, in order: background, terrain, tanks (body + barrel + HP bar),
projectiles (interpolated by `alpha`), explosions, HUD text, and any
pause/game-over overlay. Since §12 item 4, the HUD's per-tank label also
reads `world.active_player` to mark whose turn it is (a `>` prefix and
`config.COLOR_TEXT_ACTIVE` instead of `config.COLOR_TEXT`) — still a
read, not a mutation.

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
  with only geometric queries (`rect()`, `muzzle_position()`,
  `collision_shape()`) — no `update()` methods, no behavior. Behavior
  lives in exactly one place (`world.py`), so there's never a question
  of "does this tank update itself, or does something else update it?"
  The `WorldObject`/`CollisionBody`/`RigidBody` ABC hierarchy (§2) is
  compatible with this: it adds typed *structure* (what kind of thing
  is this, does it have a shape, is it physics-driven), not stored
  state or behavior — `CollisionBody`/`RigidBody` add zero fields, and
  the one method `CollisionBody` requires is a query, same category as
  `rect()`. `WorldObject` carries one field (`sprite_key`) rather than
  zero; §2 explains why that specific field, and only that field, was
  judged safe to share (its type/meaning are uniform across every
  entity, unlike position).
- **Earn abstractions, don't pre-build them — mostly.** There's no
  ECS, no event bus, no service locator, no broad-phase collision
  structure — each was considered and explicitly deferred until the
  entity count or feature set actually demands it (documented inline
  where the decision was made, e.g. `collision.py`'s broad-phase note).
  Two tanks and a handful of projectiles don't need an
  entity-component framework; they need a list. The one deliberate
  exception is the object hierarchy in §2: it's built ahead of a
  concrete need, as a cheap, low-risk seam for the entity types and
  sprite rendering already planned, rather than left to be retrofitted
  later — a judgment call made explicitly, not a silent exception to
  this principle.
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

- Tanks move horizontally (§12 item 1 is implemented: `Intent.move_delta`
  drives a friction/acceleration-integrated `Tank.velocity_x`), but
  there's no tank-vs-tank collision — two tanks can currently overlap or
  pass through each other, since only the projectile/terrain/tank
  narrow-phase tests in `collision.py` exist. Whether tanks should block
  each other is an open design decision, not yet made.
- Terrain is flat. `Terrain.height_at(x)` already exists as the single
  seam a heightmap or destructible terrain would plug into, but nothing
  currently varies it.
- No window resizing — the screen is a fixed size, keeping the
  renderer's coordinate math trivial.
- No sound/particles beyond a simple expanding-ring explosion.
- ~~No turn structure~~ — done (§12 item 4): `World.active_player` gates
  aim/power/move/fire to one tank at a time; the other tank's input is
  still sampled every frame by `controls.py` but discarded by `World`.

## 12. Natural next slices, in order

1. ~~**Tank movement**~~ — done: `TANK_MOVE_SPEED`/`TANK_MOVE_ACCEL`/
   `TANK_MOVE_FRICTION` in `config.py`, `Intent.move_delta`, and
   `World._apply_movement` (see §6). Tank-vs-tank blocking was left out
   deliberately — see §11.
2. **Destructible / uneven terrain** — only `Terrain.height_at()` and
   the ground-drawing code in `render.py` need to change; tanks,
   projectiles, and collision code already go through that seam.
3. **Audio/particle feedback** on fire and impact.
4. ~~**Turn-based mode**~~ — done: `World.active_player` (index into
   `self.tanks`, same convention as `owner_index`/`winner`) and
   `World.shot_fired_this_turn` gate input entirely inside `World`
   (`_apply_intent`, `_fire`, and the new `_advance_turn`), exactly as
   predicted — `physics.py`/`collision.py` and `controls.py` were not
   touched. See §6 for the rules.

Each of these extends an existing seam rather than requiring a
restructure — which was the point of keeping the modules this narrow
from the start.

## 13. Tests

`tests/` holds fast, headless pytest tests (`pytest`, discovered via the
repo-root `pytest.ini`) - no real pygame window or display is opened;
`tests/conftest.py` forces `SDL_VIDEODRIVER=dummy` defensively before
anything imports pygame. Coverage is deliberately narrow and focused on
the properties this document claims elsewhere, not exhaustive:

- `test_physics.py` — `apply_gravity`/`integrate_position` as pure
  functions, including that they compose as semi-implicit Euler (§4).
- `test_collision.py` — `circle_vs_rect`/`circle_vs_polygon` (including a
  concave polygon), and `sweep_projectile`'s tunneling-safe sampling: a
  projectile fired fast enough to cross an entire tank body within one
  fixed tick still registers a hit, even though the discrete endpoint
  alone would miss it (§5, "Tunneling and the sweep" — this is the
  synthetic test that section refers to).
- `test_timestep.py` — the accumulator pattern itself (`clamp_frame_time`/
  `advance_simulation`, factored out of `Game.run()` in `game.py`
  specifically so this is testable without a real Clock/window): step
  count per frame_time, the stall-clamp bound, and the `alpha` invariant
  (leftover accumulator always in `[0, fixed_dt)`).
- `test_world_smoke.py` — the headless logic smoke test (§10): drives a
  real `World` through many fixed ticks with no display, checking pause
  is a true no-op, aim/power clamping, fire cooldown, gravity-driven
  flight ending in a collision/explosion, the win/draw condition, restart,
  and that two `World`s given the same seed and input sequence end up in
  identical states (determinism, §10).
- `test_turns.py` — turn-based mode (§6, "Turn-based mode", §12 item 4):
  `active_player` starts at 0, the inactive tank's intent is a no-op,
  one shot per turn holds even once `reload_timer` alone would allow a
  second shot, the turn passes only once both the fired projectile and
  its explosion have cleared (not just the projectile), an off-screen
  shot with no explosion still passes the turn, `restart()` resets turn
  state, a game-ending shot does not also advance the turn, and turn
  state stays part of the determinism guarantee.

Tank collision testing uses tanks with no `sprite_key` (a plain
`Rectangle` shape) except where determinism tests exercise the real
two-tank `World`, which does include the sprite-backed tank — this
caught a real bug during hardening: `Tank.collision_shape()` (called from
inside `World.step()`, the core simulation path) reached
`sprite_cache.get_sprite()`, which called `pygame.image.load(...).
convert_alpha()` — and `convert_alpha()` raises without an initialized
`pygame.display` surface. That made `World.step()` non-headless whenever
a projectile's flight was tested against a sprite-backed tank, silently
contradicting this document's "simulate first, render second, never mix
the two" principle (§10) and the "headless logic smoke test" claim.
Fixed in `sprite_cache.get_sprite()`: `convert_alpha()` now only runs
when `pygame.display.get_surface()` is not `None` (real game runs via
`game.py` always have one by the time any sprite loads); a loaded PNG
already carries its own per-pixel alpha, which is all
`sprite_shape.polygon_from_sprite_mask()`'s mask extraction needs, so
skipping the conversion costs nothing but a render-only blit-performance
optimization when no display exists to blit to anyway.
