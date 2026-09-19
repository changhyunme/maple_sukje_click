#!/usr/bin/env python3
"""Run the recorded Homework 1 growth-dungeon sweep on one BlueStacks PID."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

from full_flow_runner import ensure_awake
from ui_guard import Roi, verified_click
from instance_registry import instance_name


COORDINATES = {
    "hamburger_menu": (0.936, 0.095),
    # The growth-dungeon tile is the bottom-left tile in the open hamburger
    # panel.  The previous y=.652 landed in the gap above that tile, so the
    # menu stayed open and every subsequent tap hit the wrong screen.
    "growth_dungeon": (0.720, 0.690),
    "left_menu_x": 0.264,
    # Current Air2 card bounds are roughly .16-.30, .30-.44, .44-.58,
    # .58-.72 and .72-.85.  The former first value (.300) sat exactly on the
    # boundary between cards, leaving the detail pane empty and making the
    # following sweep click a no-op.  Keep every selector near its card's
    # visual centre.
    "left_menu_y": [0.230, 0.370, 0.510, 0.650, 0.790],
    # 2026-08-14 UI: use the dedicated bulk sweep.  The old per-card sweep
    # coordinate now opens preset settings and can leave every entry undone.
    "bulk_sweep": (0.265, 0.915),
    "bulk_confirm": (0.482, 0.870),
    "bulk_result_confirm": (0.482, 0.675),
    # 2026-09-05 UI: the modal X moved upward and left.  The former point
    # (.845, .190) landed on the empty header and left the completed modal
    # open, even though every card already showed 0/10.
    "growth_close": (0.805, 0.118),
}

# The growth-dungeon UI is animation-heavy.  Keep a full transition pause
# between taps, and a shorter (but non-zero) pause between the three plus taps
# so one input is not swallowed while the counter is updating.
# BlueStacks can still be animating the modal after the input event returns.
# These pauses are intentionally conservative: a swallowed tap is worse than
# the extra few seconds on a once-per-day routine.
MENU_PAUSE = 1.2
SCREEN_PAUSE = 2.0
CONFIRM_PAUSE = 1.8
PLUS_PAUSE = 0.5
STATE_FILE = Path(__file__).with_name(".homework_state.json")
CARD_DOT_Y = [0.160, 0.300, 0.438, 0.575, 0.710]
CARD_DOT_THRESHOLD = 0.015


def _window_rgb(pid: int, crop: tuple[float, float, float, float]) -> bytes:
    window = subprocess.run(
        ["python3", str(Path(__file__).with_name("mac_gesture.py")), "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(window.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(prefix=f"maple_growth_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        x, y, width, height = crop
        return subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                "-vf", f"crop=iw*{width}:ih*{height}:iw*{x}:ih*{y},format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def _card_dot_signal(pid: int, index: int) -> float:
    """Return the red availability-dot ratio for one growth-dungeon card."""
    window = subprocess.run(
        ["python3", str(Path(__file__).with_name("mac_gesture.py")), "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(window.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(prefix=f"maple_growth_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        raw = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                # The current client draws the badge centre at x ~= .365.
                # Starting the crop at .370 clipped the badge completely and
                # made unfinished cards look completed.  Cover both the badge
                # and a small dark margin so the red-pixel signal is stable.
                "-vf", f"crop=iw*0.016:ih*0.032:iw*0.358:ih*{CARD_DOT_Y[index - 1]},format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
        pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
        if not pixels:
            return 0.0
        return sum(r > 180 and g < 100 and b < 135 for r, g, b in pixels) / len(pixels)
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def _completed_today(pid: int) -> bool:
    """Return whether this PID was successfully driven through all five cards today."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return state.get(instance_name(pid)) == date.today().isoformat()


def _record_completed(pid: int) -> None:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}
    state[instance_name(pid)] = date.today().isoformat()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_homework(pid: int, *, force: bool = False) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []

    # A second run on the same day is unsafe: once all five counters are 0/10,
    # the game's sweep button opens a ticket-selection dialog instead of the
    # normal result flow.  Never click through that dialog implicitly.
    if not force and _completed_today(pid):
        return [{
            "action": "skip_already_completed",
            "pid": pid,
            "date": date.today().isoformat(),
            "reason": "growth dungeon already completed today",
        }]

    # This runner is also invoked directly during recovery.  Previously it
    # assumed the caller had already woken the emulator; when a VM was on the
    # sleep screen every subsequent click was posted to the lock overlay and
    # the JSON log still misleadingly reported success.  Wake it here so the
    # standalone command has the same safety as the full-flow runner.
    wake = ensure_awake(pid)
    events.append({"action": "ensure_awake", **wake})
    time.sleep(0.8)

    x, y = COORDINATES["hamburger_menu"]
    events.append(verified_click(
        pid, x, y,
        label="hamburger_menu",
        pause=MENU_PAUSE,
        roi=Roi(0.68, 0.10, 0.30, 0.80),
        min_delta=0.012,
        noise_multiplier=0.0,
        retries=0,
    ))

    x, y = COORDINATES["growth_dungeon"]
    events.append(verified_click(
        pid, x, y,
        label="growth_dungeon",
        pause=SCREEN_PAUSE,
        roi=Roi(0.18, 0.16, 0.68, 0.72),
        min_delta=0.012,
        noise_multiplier=0.0,
        retries=0,
    ))

    before = [_card_dot_signal(pid, index) for index in range(1, 6)]
    events.append({"action": "growth_availability_before", "signals": before})
    any_badge = any(signal >= CARD_DOT_THRESHOLD for signal in before)
    bulk_modal_completed = False
    if instance_name(pid) == "Air2":
        # Air2 has not unlocked bulk sweep. Red badges are safe here because
        # the detector uses a tight crop around the badge centre.
        if any_badge:
            for index, menu_y in enumerate(COORDINATES["left_menu_y"], start=1):
                if before[index - 1] < CARD_DOT_THRESHOLD:
                    continue
                events.append(verified_click(
                    pid, COORDINATES["left_menu_x"], menu_y,
                    label=f"left_menu_{index}", pause=MENU_PAUSE,
                    roi=Roi(0.18, 0.16, 0.68, 0.72), allow_no_change=True,
                ))
                events.append(verified_click(
                    pid, 0.582, 0.915, label=f"menu_{index}_sweep",
                    pause=MENU_PAUSE, roi=Roi(0.30, 0.28, 0.46, 0.62),
                    min_delta=0.008, noise_multiplier=0.0, retries=1,
                ))
                events.append(verified_click(
                    pid, 0.675, 0.748, label=f"menu_{index}_max",
                    pause=PLUS_PAUSE, roi=Roi(0.42, 0.62, 0.30, 0.25),
                    min_delta=0.002, noise_multiplier=0.0, retries=1,
                ))
                events.append(verified_click(
                    pid, 0.485, 0.830, label=f"menu_{index}_sweep_confirm",
                    pause=CONFIRM_PAUSE, roi=Roi(0.25, 0.24, 0.52, 0.68),
                ))
                events.append(verified_click(
                    pid, 0.485, 0.725, label=f"menu_{index}_result_confirm",
                    pause=SCREEN_PAUSE, roi=Roi(0.25, 0.24, 0.52, 0.68),
                ))
    else:
        # Air/Air1 always open the bulk modal. This avoids guessing completion
        # from artwork. The modal's own bottom button is cyan only when at
        # least one sweep remains, and gray when all five counters are zero.
        x, y = COORDINATES["bulk_sweep"]
        events.append(verified_click(
            pid, x, y, label="bulk_sweep_open", pause=SCREEN_PAUSE,
            roi=Roi(0.05, 0.08, 0.88, 0.84), min_delta=0.008,
            noise_multiplier=0.0, retries=1,
        ))
        confirm_rgb = _window_rgb(pid, (0.38, 0.82, 0.22, 0.10))
        confirm_pixels = list(zip(confirm_rgb[0::3], confirm_rgb[1::3], confirm_rgb[2::3]))
        bulk_available = bool(confirm_pixels) and sum(
            g > 115 and b > 110 and g > r * 1.25 for r, g, b in confirm_pixels
        ) / len(confirm_pixels) > 0.08
        events.append({"action": "bulk_confirm_probe", "available": bulk_available})
        bulk_modal_completed = not bulk_available
        if bulk_available:
            x, y = COORDINATES["bulk_confirm"]
            events.append(verified_click(
                pid, x, y, label="bulk_sweep_confirm", pause=CONFIRM_PAUSE,
                roi=Roi(0.08, 0.10, 0.84, 0.78), min_delta=0.008,
                noise_multiplier=0.0, retries=1,
            ))
            x, y = COORDINATES["bulk_result_confirm"]
            events.append(verified_click(
                pid, x, y, label="bulk_result_confirm", pause=SCREEN_PAUSE,
                roi=Roi(0.08, 0.10, 0.84, 0.78), min_delta=0.008,
                noise_multiplier=0.0, retries=1,
            ))

            # Bulk result confirmation returns to the field. Re-open for proof.
            events.append(verified_click(
                pid, *COORDINATES["hamburger_menu"], label="hamburger_verify_growth",
                pause=MENU_PAUSE, roi=Roi(0.68, 0.10, 0.30, 0.80),
                min_delta=0.012, noise_multiplier=0.0, retries=0,
            ))
            events.append(verified_click(
                pid, *COORDINATES["growth_dungeon"], label="growth_verify_reopen",
                pause=SCREEN_PAUSE, roi=Roi(0.18, 0.16, 0.68, 0.72),
                min_delta=0.012, noise_multiplier=0.0, retries=0,
            ))
        else:
            events.append(verified_click(
                pid, 0.882, 0.135, label="close_completed_bulk_modal",
                pause=MENU_PAUSE, roi=Roi(0.05, 0.08, 0.88, 0.84),
                min_delta=0.008, noise_multiplier=0.0, retries=0,
            ))

    remaining = [_card_dot_signal(pid, index) for index in range(1, 6)]
    completed = bulk_modal_completed or all(
        signal < CARD_DOT_THRESHOLD for signal in remaining
    )
    events.append({
        "action": "verify_all_growth_complete", "signals": remaining,
        "completed": completed,
        "proof": "bulk_confirm_disabled" if bulk_modal_completed else "card_badges_absent",
    })
    if instance_name(pid) == "Air2" and any(signal >= CARD_DOT_THRESHOLD for signal in remaining):
        raise RuntimeError(f"growth availability remains after bulk sweep: {remaining}")

    # Leave the modal in a known field state before the next homework action.
    x, y = COORDINATES["growth_close"]
    events.append(verified_click(
        pid, x, y,
        label="growth_close",
        pause=SCREEN_PAUSE,
        roi=Roi(0.18, 0.16, 0.68, 0.72),
        # On combat-heavy fields the growth modal can close successfully while
        # the normalized frame delta stays small (Air1 measured 0.00694).
        # Keep a non-zero guard, but accept that verified close transition.
        min_delta=0.004,
        noise_multiplier=0.0,
        retries=0,
    ))

    _record_completed(pid)
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--force", action="store_true", help="rerun even if this PID was completed today")
    args = parser.parse_args()
    events = run_homework(args.pid, force=args.force)
    print(json.dumps({"pid": args.pid, "event_count": len(events), "events": events}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
