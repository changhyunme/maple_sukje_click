#!/usr/bin/env python3
"""Run the recorded Homework 1 growth-dungeon sweep on one BlueStacks PID."""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from mac_gesture import click_ratio
from full_flow_runner import ensure_awake


COORDINATES = {
    "hamburger_menu": (0.936, 0.095),
    # The growth-dungeon tile is the bottom-left tile in the open hamburger
    # panel.  The previous y=.652 landed in the gap above that tile, so the
    # menu stayed open and every subsequent tap hit the wrong screen.
    "growth_dungeon": (0.720, 0.690),
    "left_menu_x": 0.264,
    # Use the first card's centre rather than its top edge.  The other four
    # values are the centres verified against Air/Air1/Air2.
    "left_menu_y": [0.300, 0.393, 0.531, 0.671, 0.812],
    "sweep": (0.582, 0.868),
    "plus": (0.613, 0.748),
    "sweep_confirm": (0.481, 0.830),
    "result_confirm": (0.481, 0.711),
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


def _completed_today(pid: int) -> bool:
    """Return whether this PID was successfully driven through all five cards today."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return state.get(str(pid)) == date.today().isoformat()


def _record_completed(pid: int) -> None:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}
    state[str(pid)] = date.today().isoformat()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def click_named(pid: int, name: str, x_ratio: float, y_ratio: float) -> dict[str, object]:
    result = click_ratio(pid, x_ratio, y_ratio)
    return {"action": name, **result}


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
    events.append(click_named(pid, "hamburger_menu", x, y))
    time.sleep(MENU_PAUSE)

    x, y = COORDINATES["growth_dungeon"]
    events.append(click_named(pid, "growth_dungeon", x, y))
    time.sleep(SCREEN_PAUSE)

    for index, menu_y in enumerate(COORDINATES["left_menu_y"], start=1):
        events.append(
            click_named(
                pid,
                f"left_menu_{index}",
                COORDINATES["left_menu_x"],
                menu_y,
            )
        )
        time.sleep(MENU_PAUSE)

        x, y = COORDINATES["sweep"]
        events.append(click_named(pid, f"menu_{index}_sweep", x, y))
        time.sleep(MENU_PAUSE)

        x, y = COORDINATES["plus"]
        for plus_index in range(1, 4):
            events.append(
                click_named(pid, f"menu_{index}_plus_{plus_index}", x, y)
            )
            time.sleep(PLUS_PAUSE)

        x, y = COORDINATES["sweep_confirm"]
        events.append(click_named(pid, f"menu_{index}_sweep_confirm", x, y))
        time.sleep(CONFIRM_PAUSE)

        x, y = COORDINATES["result_confirm"]
        events.append(click_named(pid, f"menu_{index}_result_confirm", x, y))
        time.sleep(SCREEN_PAUSE)

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
