"""Shared pytest setup.

Forces a headless SDL video driver before anything imports pygame, so the
whole suite runs with no real display/window - required for CI and for
running tests on a machine with no GUI session. Every test module in this
package only touches pygame.Vector2/Rect/math (no Surface/font/display
calls), so the dummy driver is a formality here, not a requirement - but
setting it defensively means a future test that *does* touch a Surface
still runs headlessly instead of failing to open a window.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
