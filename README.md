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

## Controls

| Action           | Player 1 (left)      | Player 2 (right)   |
|------------------|-----------------------|---------------------|
| Aim up / down    | `W` / `S`             | `Up` / `Down`       |
| Power up / down  | `D` / `A`             | `Right` / `Left`    |
| Fire             | `Space`               | `Enter`             |

Other keys: `P` pause/resume, `R` restart, `Esc` quit.

## Project layout

- `config.py` — all tunable constants and key bindings.
- `entities.py` — `Tank`, `Projectile`, `Explosion`, `Terrain` data.
- `physics.py` — pure gravity/position integration.
- `collision.py` — circle/rect tests and tunneling-safe sweeps.
- `world.py` — simulation rules and the fixed-timestep step.
- `controls.py` — key state to per-tank intents.
- `render.py` — drawing only, no gameplay mutation.
- `game.py` — main loop (fixed-timestep accumulator).
- `main.py` — entry point.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design rationale.