#!/usr/bin/env python3
"""Claim only the daily free weapon and companion summon rewards."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time

from ui_guard import Roi, verified_click

ROOT = os.path.dirname(os.path.abspath(__file__))

COORDINATES = {
    "summon_menu": (0.830, 0.095),
    "weapon_tab": (0.105, 0.300),
    "weapon_free_reward": (0.575, 0.885),
    "companion_tab": (0.105, 0.420),
    "companion_free_reward": (0.575, 0.885),
    "dismiss_results": (0.035, 0.095),
    "close": (0.910, 0.100),
}


def click(pid: int, x: float, y: float, label: str, pause: float = 1.0) -> dict[str, object]:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
         "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}"],
        check=True, capture_output=True, text=True,
    )
    if pause:
        time.sleep(pause)
    return {"action": label, **json.loads(result.stdout)}


def _window_rgb(pid: int, crop: tuple[float, float, float, float]) -> bytes:
    window = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = json.loads(window.stdout)["window_id"]
    with tempfile.NamedTemporaryFile(prefix=f"maple_summon_{pid}_", suffix=".png", delete=False) as image:
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


def free_reward_available(pid: int) -> bool:
    """The free button is cyan when 1/1 is available and grey at 0/1."""
    rgb = _window_rgb(pid, (0.47, 0.78, 0.16, 0.12))
    return _pixel_ratio(rgb, lambda r, g, b: g > 130 and b > 130 and g > r * 1.3) > 0.08


def claim_free(pid: int, key: str, events: list[dict[str, object]]) -> None:
    if not free_reward_available(pid):
        events.append({"action": key, "status": "unavailable_or_already_claimed"})
        return
    events.append(click(pid, *COORDINATES[key], label=key, pause=4.0))
    # Active free rewards show a result layer.  Dismiss only after an active
    # click; doing this on a disabled button would exit the summon screen.
    events.append(click(pid, *COORDINATES["dismiss_results"], label=f"dismiss_{key}_results"))


def run(pid: int, max_batches: int | None = None) -> list[dict[str, object]]:
    # max_batches is accepted for compatibility with full_flow_runner but is
    # intentionally ignored: this macro never spends summon tickets or gems.
    events: list[dict[str, object]] = []
    c = COORDINATES
    events.append(verified_click(
        pid, *c["summon_menu"], label="summon_menu", pause=1.5,
        roi=Roi(0.16, 0.12, 0.72, 0.80),
        min_delta=0.012, noise_multiplier=0.0, retries=1,
    ))
    events.append(click(pid, *c["weapon_tab"], label="weapon_summon"))
    claim_free(pid, "weapon_free_reward", events)
    events.append(click(pid, *c["companion_tab"], label="companion_summon", pause=2.0))
    claim_free(pid, "companion_free_reward", events)
    # One verified close only.  A blind second tap after the first succeeded
    # can hit a field icon on a shifted VM layout.
    events.append(verified_click(
        pid, *c["close"], label="close_summon", pause=1.5,
        roi=Roi(0.16, 0.12, 0.72, 0.80),
        # Air2's close transition measured only ~0.0012 in this ROI because
        # the animated field dominated both signatures.  It still visibly
        # returned to the field; keep a fixed low gate and never retry.
        min_delta=0.0008, noise_multiplier=0.0, retries=0,
    ))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--max-batches", type=int, default=0,
                        help="deprecated compatibility option; summon tickets are never spent")
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid, args.max_batches)}, ensure_ascii=False))
