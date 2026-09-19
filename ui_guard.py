"""Small visual gates for destructive sequential UI macros.

CGEvent posting only proves that an event was emitted.  These helpers capture
the target window before and after a click and require a measurable visual
transition before the caller continues.  They intentionally fail closed: a
missed click stops the sequence instead of sending the next coordinate to an
unknown screen.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import time
from typing import NamedTuple
from typing import Callable

from mac_gesture import click_ratio


ROOT = Path(__file__).resolve().parent


class ClickVerificationError(RuntimeError):
    """Raised when a click did not produce the expected screen transition."""


def wait_for_state(
    probe: Callable[[], bool], *, label: str, timeout: float = 12.0,
    interval: float = 1.0, consecutive: int = 2,
) -> dict[str, object]:
    """Require repeated observations of a caller-defined semantic state.

    This only polls: a timeout must never automatically repeat a reward claim.
    The caller must inspect the current screen before deciding to retry input.
    """
    if timeout <= 0 or interval <= 0 or consecutive < 1:
        raise ValueError("timeout/interval must be positive; consecutive must be >= 1")
    started = time.monotonic()
    streak = samples = 0
    while time.monotonic() - started < timeout:
        matched = probe()
        samples += 1
        streak = streak + 1 if matched else 0
        if streak >= consecutive:
            return {"state": label, "state_verified": True, "samples": samples,
                    "elapsed_seconds": round(time.monotonic() - started, 3)}
        remaining = timeout - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise ClickVerificationError(f"{label}: expected state not stable within {timeout}s")


class Roi(NamedTuple):
    x: float
    y: float
    width: float
    height: float


def _window_id(pid: int) -> int:
    result = subprocess.run(
        ["python3", str(ROOT / "mac_gesture.py"), "window-id", str(pid)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(json.loads(result.stdout)["window_id"])


def capture_signature(pid: int, roi: Roi | None = None) -> bytes:
    """Return a small grayscale signature for a PID's on-screen window."""
    window_id = _window_id(pid)
    with tempfile.NamedTemporaryFile(prefix=f"maple_guard_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        filters: list[str] = []
        if roi is not None:
            filters.append(
                f"crop=iw*{roi.width}:ih*{roi.height}:iw*{roi.x}:ih*{roi.y}"
            )
        filters.extend(["scale=64:36:flags=area", "format=gray"])
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                "-vf", ",".join(filters), "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True,
            capture_output=True,
        )
        return result.stdout
    finally:
        try:
            import os

            os.unlink(image_path)
        except FileNotFoundError:
            pass


def signature_delta(before: bytes, after: bytes) -> float:
    if not before or not after or len(before) != len(after):
        return 0.0
    return sum(abs(left - right) for left, right in zip(before, after)) / (255.0 * len(before))


def verified_click(
    pid: int,
    x_ratio: float,
    y_ratio: float,
    *,
    label: str,
    pause: float = 1.0,
    roi: Roi | None = None,
    min_delta: float = 0.012,
    noise_multiplier: float = 1.25,
    retries: int = 1,
    allow_no_change: bool = False,
) -> dict[str, object]:
    """Click and require a visual transition before returning.

    ``allow_no_change`` is reserved for intentionally idempotent taps such as
    a third ``+`` press when the game has already reached its maximum.
    """
    # The game field is animated continuously.  Calibrate the natural change
    # in the exact ROI first, then require the click-induced change to exceed
    # that noise floor.  A single before/after threshold would incorrectly
    # accept a missed click during combat animation.
    before = capture_signature(pid, roi)
    time.sleep(0.25)
    before_stable = capture_signature(pid, roi)
    noise = signature_delta(before, before_stable)
    attempts: list[float] = []
    for attempt in range(1, retries + 2):
        event = click_ratio(pid, x_ratio, y_ratio)
        time.sleep(pause)
        after = capture_signature(pid, roi)
        delta = signature_delta(before_stable, after)
        attempts.append(delta)
        required_delta = max(min_delta, noise * noise_multiplier)
        if delta >= required_delta or allow_no_change:
            return {
                "action": label,
                **event,
                "visual_verified": delta >= required_delta,
                "visual_delta": round(delta, 5),
                "visual_noise": round(noise, 5),
                "visual_required": round(required_delta, 5),
                "visual_attempts": [round(value, 5) for value in attempts],
            }
        if attempt <= retries:
            time.sleep(0.4)
            before_stable = after
            noise = 0.0
    raise ClickVerificationError(
        f"{label}: no visual transition after {len(attempts)} click(s); deltas={attempts}"
    )
