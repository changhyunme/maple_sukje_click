#!/usr/bin/env python3
"""Run the fourth recorded action: free rewards, boosters and repeat hunting."""

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
    payload = json.loads(result.stdout)
    return {"action": label, **payload}


COORDINATES = {
    "free_icon": (0.039, 0.924),
    "free_claim": (0.500, 0.855),
    "free_bonus_tab": (0.640, 0.630),
    "leaf_icon": (0.126, 0.925),
    "ad_booster": (0.665, 0.400),
    "burning_booster": (0.665, 0.300),
    "close_overlay": (0.928, 0.100),
    "repeat": (0.220, 0.870),
    # Dialog confirm button is lower than the claim-dialog confirm used by action 3.
    "confirm": (0.556, 0.700),
    "dismiss": (0.135, 0.860),
}

# Air 2 is vertically offset and its modal tabs shift after a reward is
# consumed.  Keep the verified profile local to that instance instead of
# forcing a rerun to reuse Air's coordinates.
INSTANCE_OVERRIDES = {
    31126: {
        "free_bonus_tab": (0.640, 0.550),
        "free_close": (0.705, 0.124),
        "booster_close": (0.741, 0.160),
        "ad_booster": (0.665, 0.400),
        "burning_booster": (0.665, 0.400),
    },
}


def coordinates_for(pid: int) -> dict[str, tuple[float, float]]:
    coords = dict(COORDINATES)
    override = INSTANCE_OVERRIDES.get(pid, {})
    coords.update(override)
    coords.setdefault("free_close", coords["close_overlay"])
    coords.setdefault("booster_close", coords["close_overlay"])
    return coords


def run(pid: int, wait_seconds: float = 300.0) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    c = coordinates_for(pid)

    events.append(click(pid, *c["free_icon"], label="free_icon"))
    events.append(click(pid, *c["free_claim"], label="free_claim"))
    events.append(click(pid, *c["dismiss"], pause=0.8, label="dismiss_free_reward"))
    events.append(click(pid, *c["free_bonus_tab"], label="free_bonus_tab"))
    events.append(click(pid, *c["free_claim"], label="free_bonus_claim"))
    events.append(click(pid, *c["dismiss"], pause=0.8, label="dismiss_bonus_reward"))
    events.append(click(pid, *c["free_close"], label="close_free_overlay"))

    events.append(click(pid, *c["leaf_icon"], label="leaf_icon"))
    # The ad reward button needs a longer pause while the rewarded-ad state settles.
    events.append(click(pid, *c["ad_booster"], pause=5.0, label="daily_ad_booster"))
    events.append(click(pid, *c["burning_booster"], label="burning_field_booster_max"))
    events.append(click(pid, *c["booster_close"], label="close_booster_overlay"))

    events.append(click(pid, *c["repeat"], label="repeat_button"))
    events.append(click(pid, *c["confirm"], label="repeat_confirm"))
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    events.append({"action": "repeat_wait", "duration_seconds": wait_seconds})
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--wait-seconds", type=float, default=300.0)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(args.pid, args.wait_seconds)}, ensure_ascii=False))
