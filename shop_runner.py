#!/usr/bin/env python3
"""Claim the daily free rewards from the General and Cygnus shops."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time

from ui_guard import ClickVerificationError, Roi, verified_click
from full_flow_runner import ensure_awake


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
TAB_CYAN_THRESHOLD = 0.08

TAB_CROPS = {
    "general_shop": (0.02, 0.54, 0.16, 0.14),
    "cygnus_shop": (0.02, 0.83, 0.16, 0.14),
}


def _cyan_pixel(r: int, g: int, b: int) -> bool:
    return r < 90 and g > 130 and b > 130


TAB_CYAN = _cyan_pixel


def click(
    pid: int,
    x: float,
    y: float,
    label: str,
    pause: float = CLICK_PAUSE,
    retries: int = 2,
    verify: bool = False,
    roi: Roi | None = None,
) -> dict[str, object]:
    """Click with retries; optionally require a visual state transition."""
    if verify:
        try:
            return verified_click(
                pid,
                x,
                y,
                label=label,
                pause=pause,
                roi=roi,
                retries=max(0, retries - 1),
            )
        except ClickVerificationError:
            raise

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


def _signal(pid: int, crop: tuple[float, float, float, float], predicate) -> float:
    return _pixel_ratio(_window_rgb(pid, crop), predicate)


def shop_tab_signal(pid: int, shop: str) -> float:
    """Return the cyan-highlight ratio for a selected left shop tab."""
    return _signal(pid, TAB_CROPS[shop], TAB_CYAN)


def shop_tab_selected(pid: int, shop: str, samples: int = 4) -> tuple[bool, float]:
    last_signal = -1.0
    for _ in range(samples):
        try:
            last_signal = shop_tab_signal(pid, shop)
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            last_signal = -1.0
        if last_signal >= TAB_CYAN_THRESHOLD:
            return True, last_signal
        time.sleep(0.35)
    return False, last_signal


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
    events.append(click(
        pid,
        *COORDINATES["first_card"],
        label=f"{shop}_first_card",
        pause=1.0,
        verify=True,
        roi=Roi(0.20, 0.20, 0.60, 0.70),
    ))
    events.append(click(
        pid,
        *COORDINATES["free_claim"],
        label=f"{shop}_free_{index}",
        pause=1.8,
        verify=True,
        roi=Roi(0.20, 0.20, 0.60, 0.70),
    ))
    events.append(click(
        pid,
        *COORDINATES["dismiss_reward"],
        label=f"dismiss_{shop}_{index}",
        pause=1.2,
        verify=True,
        roi=Roi(0.20, 0.20, 0.60, 0.70),
    ))
    # A successful click changes the first card: General loses its AD badge;
    # Cygnus keeps it only until the second daily claim.
    expected_remaining = shop == "cygnus_shop" and index < 2
    remaining, remaining_signal = free_card_available(pid)
    events.append({
        "action": f"verify_{shop}_free_{index}",
        "expected_badge": expected_remaining,
        "badge_present": remaining,
        "free_button_signal": remaining_signal,
    })
    if remaining != expected_remaining:
        raise ClickVerificationError(
            f"{shop}_free_{index}: reward state did not change as expected "
            f"(expected_badge={expected_remaining}, signal={remaining_signal})"
        )
    return True


def run(pid: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    # This runner is also used standalone.  Without the wake guard a sleeping
    # VM accepts the OS event but leaves every following tap on the lock
    # overlay, which previously looked like a successful run in the JSON log.
    events.append({"action": "ensure_awake", **ensure_awake(pid)})
    time.sleep(0.8)
    events.append(click(
        pid,
        *COORDINATES["shop_icon"],
        label="shop_icon",
        pause=1.8,
        verify=True,
        roi=Roi(0.00, 0.12, 0.20, 0.88),
    ))

    for attempt in range(1, 4):
        events.append(click(pid, *COORDINATES["general_shop"], label="general_shop"))
        selected, signal = shop_tab_selected(pid, "general_shop")
        if selected:
            events.append({"action": "verify_general_shop", "attempt": attempt, "tab_signal": signal})
            break
    else:
        raise ClickVerificationError("general_shop: selected tab was not detected")
    claim_one(pid, "general_shop", 1, events)

    for attempt in range(1, 4):
        events.append(click(pid, *COORDINATES["cygnus_shop"], label="cygnus_shop"))
        selected, signal = shop_tab_selected(pid, "cygnus_shop")
        if selected:
            events.append({"action": "verify_cygnus_shop", "attempt": attempt, "tab_signal": signal})
            break
    else:
        raise ClickVerificationError("cygnus_shop: selected tab was not detected")
    # Cygnus shows 일간 2/2, so its free card is claimed twice.
    claim_one(pid, "cygnus_shop", 1, events)
    claim_one(pid, "cygnus_shop", 2, events)

    events.append(click(
        pid,
        *COORDINATES["close_shop"],
        label="close_shop",
        verify=True,
        roi=Roi(0.00, 0.12, 0.20, 0.88),
    ))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid)}, ensure_ascii=False))
