#!/usr/bin/env python3
"""Run the fifth action: guild buildings, arena and world boss."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"


def click(pid: int, x: float, y: float, pause: float = 1.0, label: str = "click") -> dict[str, object]:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
         "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}"],
        check=True, capture_output=True, text=True,
    )
    if pause:
        time.sleep(pause)
    return {"action": label, **json.loads(result.stdout)}


# These are the same menu-relative coordinates used by the recorded menu actions.
COORDINATES = {
    "hamburger": (0.936, 0.095),
    "guild": (0.852, 0.424),
    "guild_building": (0.080, 0.680),
    "free_upgrade_x": (0.300, 0.545, 0.825),
    "free_upgrade_y": 0.880,
    "arena": (0.923, 0.680),
    "arena_top_person": (0.870, 0.230),
    "arena_start": (0.870, 0.230),
    "arena_pause": 8.0,
    "world_boss": (0.780, 0.680),
    "world_boss_enter": (0.815, 0.910),
    "close": (0.928, 0.100),
}


# Verified manually against the rerun layout of BlueStacks Air 2.  Air and
# Air 1 retain the original profile above.
INSTANCE_OVERRIDES = {
    31126: {
        "guild": (0.840, 0.445),
        "guild_building": (0.100, 0.680),
        "free_upgrade_x": (0.305, 0.555, 0.810),
        "free_upgrade_y": 0.835,
        "arena": (0.905, 0.680),
        "arena_top_person": (0.865, 0.250),
        "arena_start": (0.865, 0.250),
        # Air 2 battles can last 20–30 seconds; a short fixed pause would
        # send the next tap into the battle scene on a rerun.
        "arena_pause": 30.0,
        "close": (0.910, 0.120),
    },
}


def coordinates_for(pid: int) -> dict[str, object]:
    coords: dict[str, object] = dict(COORDINATES)
    coords.update(INSTANCE_OVERRIDES.get(pid, {}))
    return coords


def run(pid: int, world_boss_seconds: float = 90.0) -> list[dict[str, object]]:
    c = coordinates_for(pid)
    events: list[dict[str, object]] = []

    events.append(click(pid, *c["hamburger"], label="hamburger_guild"))
    events.append(click(pid, *c["guild"], label="guild"))
    events.append(click(pid, *c["guild_building"], label="guild_building"))
    for i, x in enumerate(c["free_upgrade_x"], start=1):
        events.append(click(pid, x, c["free_upgrade_y"], label=f"guild_free_upgrade_{i}"))
        events.append(click(pid, 0.135, 0.860, pause=0.8, label=f"dismiss_upgrade_{i}"))
    events.append(click(pid, *c["close"], label="close_guild"))

    events.append(click(pid, *c["hamburger"], label="hamburger_arena"))
    events.append(click(pid, *c["arena"], label="arena"))
    events.append(click(pid, *c["arena_top_person"], label="arena_top_person"))
    for i in range(1, 4):
        events.append(click(pid, *c["arena_start"], label=f"arena_battle_{i}", pause=float(c["arena_pause"])))
    events.append(click(pid, *c["close"], label="close_arena"))

    events.append(click(pid, *c["hamburger"], label="hamburger_world_boss"))
    events.append(click(pid, *c["world_boss"], label="world_boss"))
    events.append(click(pid, *c["world_boss_enter"], label="world_boss_enter"))
    if world_boss_seconds > 0:
        time.sleep(world_boss_seconds)
    events.append({"action": "world_boss_wait", "duration_seconds": world_boss_seconds})
    events.append(click(pid, *c["close"], label="close_world_boss"))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--world-boss-seconds", type=float, default=90.0)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid, args.world_boss_seconds)}, ensure_ascii=False))
