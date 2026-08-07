#!/usr/bin/env python3
"""Claim the daily free weapon and companion summon rewards."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"

# Ratios are relative to the BlueStacks game window.  The free-reward buttons
# are intentionally clicked even when they show 0/1 and are disabled; this
# makes the daily action idempotent after today's reward was already claimed.
COORDINATES = {
    "summon_menu": (0.830, 0.095),
    "weapon_free_reward": (0.575, 0.885),
    "companion_tab": (0.105, 0.420),
    "companion_free_reward": (0.575, 0.885),
    # The summon screen's top-right X is close to the emulator toolbar and
    # can trigger sleep mode with the window's offset coordinates.  Use the
    # in-game back arrow on the top-left instead.
    "back": (0.035, 0.095),
}


def click(pid: int, x: float, y: float, label: str, pause: float = 0.7) -> dict[str, object]:
    result = subprocess.run(
        [
            "python3",
            f"{ROOT}/mac_gesture.py",
            "click",
            str(pid),
            "--x-ratio",
            f"{x:.3f}",
            "--y-ratio",
            f"{y:.3f}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if pause:
        time.sleep(pause)
    payload = json.loads(result.stdout)
    return {"action": label, **payload}


def run(pid: int) -> list[dict[str, object]]:
    c = COORDINATES
    events: list[dict[str, object]] = []
    events.append(click(pid, *c["summon_menu"], label="summon_menu"))
    events.append(click(pid, *c["weapon_free_reward"], label="weapon_free_reward"))
    events.append(click(pid, *c["companion_tab"], label="companion_summon"))
    events.append(click(pid, *c["companion_free_reward"], label="companion_free_reward"))
    events.append(click(pid, *c["back"], label="back_from_summon"))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid)}, ensure_ascii=False))
