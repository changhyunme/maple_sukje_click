#!/usr/bin/env python3
"""Claim the daily free rewards from the General and Cygnus shops."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"

# Ratios are relative to the BlueStacks game window.  These were verified on
# BlueStacks Air 2; the three shop screens use the same layout.
COORDINATES = {
    "shop_icon": (0.889, 0.086),
    "general_shop": (0.076, 0.583),
    "cygnus_shop": (0.076, 0.872),
    "first_card": (0.256, 0.397),
    "free_claim": (0.485, 0.747),
    "dismiss_reward": (0.485, 0.758),
    "close_shop": (0.930, 0.095),
}

CLICK_PAUSE = 1.2
# The free card is marked with a cyan ``AD`` badge in the upper-right corner
# of the first card.  The old detector looked for a green button strip near
# the bottom of the card; that strip is mostly gray on Cygnus and caused every
# available card to be reported as already claimed.
FREE_BADGE_THRESHOLD = 0.01


def click(
    pid: int,
    x: float,
    y: float,
    label: str,
    pause: float = CLICK_PAUSE,
    retries: int = 2,
) -> dict[str, object]:
    """Click with a short retry for swallowed macOS/BlueStacks inputs."""
    command = [
        "python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
        "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}",
    ]
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            if pause:
                time.sleep(pause)
            event = {"action": label, "attempt": attempt, **json.loads(result.stdout)}
            return event
        except subprocess.CalledProcessError as error:
            last_error = error
            if attempt < retries:
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


def _window_rgb(pid: int, crop: tuple[float, float, float, float]) -> bytes:
    window = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = json.loads(window.stdout)["window_id"]
    with tempfile.NamedTemporaryFile(prefix=f"maple_shop_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        x, y, width, height = crop
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
             "-vf", f"crop=iw*{width}:ih*{height}:iw*{x}:ih*{y},format=rgb24",
             "-f", "rawvideo", "-"],
            check=True, capture_output=True,
        )
        return result.stdout
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def _pixel_ratio(rgb: bytes, predicate) -> float:
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    return sum(predicate(r, g, b) for r, g, b in pixels) / len(pixels) if pixels else 0.0


def free_card_signal(pid: int) -> float:
    """Detect the cyan ``AD`` badge on the first (free) card.

    Once a daily reward is claimed, the card disappears and a paid weekly
    card moves into its place; the badge disappears with it.  This works for
    both General and Cygnus shops, whose bottom price strips have different
    colors.
    """
    # First card's top-right badge; keep the crop away from the item artwork.
    rgb = _window_rgb(pid, (0.31, 0.16, 0.10, 0.10))
    return _pixel_ratio(
        rgb,
        lambda r, g, b: r < 100 and g > 130 and b > 130,
    )


def free_card_available(pid: int, samples: int = 3) -> tuple[bool, float]:
    """Poll the card probe so a slow shop transition cannot cause a bad click."""
    last_signal = -1.0
    for _ in range(samples):
        try:
            last_signal = free_card_signal(pid)
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            last_signal = -1.0
        if last_signal >= FREE_BADGE_THRESHOLD:
            return True, last_signal
        time.sleep(0.35)
    return False, last_signal


def claim_one(pid: int, shop: str, index: int, events: list[dict[str, object]]) -> bool:
    available, signal = free_card_available(pid)
    if not available:
        status = "probe_failed" if signal < 0 else "unavailable_or_already_claimed"
        events.append({"action": f"{shop}_free_{index}", "status": status, "free_button_signal": signal})
        return False
    events.append({"action": f"{shop}_free_{index}_probe", "free_button_signal": signal})
    events.append(click(pid, *COORDINATES["first_card"], label=f"{shop}_first_card"))
    events.append(click(pid, *COORDINATES["free_claim"], label=f"{shop}_free_{index}", pause=1.8))
    events.append(click(pid, *COORDINATES["dismiss_reward"], label=f"dismiss_{shop}_{index}", pause=1.2))
    return True


def run(pid: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    events.append(click(pid, *COORDINATES["shop_icon"], label="shop_icon", pause=1.8))

    events.append(click(pid, *COORDINATES["general_shop"], label="general_shop"))
    claim_one(pid, "general_shop", 1, events)

    events.append(click(pid, *COORDINATES["cygnus_shop"], label="cygnus_shop"))
    # Cygnus shows 일간 2/2, so its free card is claimed twice.
    claim_one(pid, "cygnus_shop", 1, events)
    claim_one(pid, "cygnus_shop", 2, events)

    events.append(click(pid, *COORDINATES["close_shop"], label="close_shop"))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid)}, ensure_ascii=False))
