# PaperTanks

A minimal side-view artillery duel: two tanks on flat ground trade
gravity-arced shots. Built with Python and Pygame.

## Install

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

## Dev

```
pip install -r requirements-dev.txt
pytest
```

## Controls

| Action           | Player 1 (left)      | Player 2 (right)   |
|------------------|-----------------------|---------------------|
| Aim up / down    | `W` / `S`             | `Up` / `Down`       |
| Power up / down  | `D` / `A`             | `Right` / `Left`    |
| Fire             | `Space`               | `Enter`             |

Other keys: `P` pause/resume, `R` restart, `Esc` quit.

## Project layout

- `main.py` — entry point, sole file at the repo root; `python main.py`.
- `papertanks/` — the game code package.
  - `config.py` — all tunable constants and key bindings.
  - `entities.py` — `Tank`, `Projectile`, `Explosion`, `Terrain` data.
  - `physics.py` — pure gravity/position integration.
  - `collision.py` — circle/rect tests and tunneling-safe sweeps.
  - `world.py` — simulation rules and the fixed-timestep step.
  - `controls.py` — key state to per-tank intents.
  - `render.py` — drawing only, no gameplay mutation.
  - `sprite_cache.py` / `sprite_shape.py` — sprite loading and mask-derived collision polygons.
  - `game.py` — main loop (fixed-timestep accumulator).
- `assets/sprites/` — sprite art (e.g. `tank1.png`).
- `tests/` — headless pytest suite (`pytest`).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale.