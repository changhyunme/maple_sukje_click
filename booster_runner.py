#!/usr/bin/env python3
"""Run the fourth recorded action: AD rewards, boosters and repeat hunting."""

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
    # The fast-hunt overlay opens on the gem-purchase tab.  This is an
    # explicitly requested daily reward claim and may consume 500 gems.
    "gem_purchase_claim": (0.500, 0.855),
    "free_claim": (0.500, 0.855),
    "free_bonus_tab": (0.640, 0.555),
    "leaf_icon": (0.126, 0.925),
    # Booster list: the first row is the daily Burning Field event.
    "burning_booster": (0.640, 0.430),
    # Burning Field use dialog: select all five, then confirm.
    "burning_max": (0.665, 0.575),
    "burning_confirm": (0.500, 0.700),
    "close_overlay": (0.910, 0.100),
    "repeat": (0.220, 0.870),
    # Dialog confirm button is lower than the claim-dialog confirm used by action 3.
    "confirm": (0.556, 0.700),
    "dismiss": (0.135, 0.860),
}

# Air 2 has a different fast-hunt default tab and a 1–4 booster dialog, in
# addition to its shifted modal coordinates. Keep that verified profile local
# to the instance instead of forcing a rerun to reuse Air's coordinates.
INSTANCE_OVERRIDES = {
    31126: {
        # Air2 opens on the normal 무료 tab, not the gem-purchase tab.
        "free_bonus_tab": (0.622, 0.575),
        "free_claim": (0.485, 0.877),
        "gem_purchase_claim": (0.485, 0.877),
        "dismiss": (0.485, 0.763),
        "free_close": (0.685, 0.167),
        "booster_close": (0.720, 0.200),
        "burning_booster": (0.646, 0.422),
        "burning_max": (0.660, 0.719),
        "burning_confirm": (0.485, 0.856),
        "repeat": (0.213, 0.877),
        "confirm": (0.567, 0.710),
    },
}

INITIAL_CLAIM_KEYS = {
    # Air2's first tab is 무료; Air/Air1 open on the requested gem-purchase
    # tab when that offer is available.
    31126: "free_claim",
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
    initial_claim = INITIAL_CLAIM_KEYS.get(pid, "gem_purchase_claim")
    events.append(click(pid, *c[initial_claim], label=initial_claim))
    events.append(click(pid, *c["dismiss"], pause=0.8, label="dismiss_free_reward"))
    events.append(click(pid, *c["free_bonus_tab"], label="free_bonus_tab"))
    events.append(click(pid, *c["free_claim"], label="free_bonus_claim"))
    events.append(click(pid, *c["dismiss"], pause=0.8, label="dismiss_bonus_reward"))
    events.append(click(pid, *c["free_close"], label="close_free_overlay"))

    events.append(click(pid, *c["leaf_icon"], label="leaf_icon"))
    events.append(click(pid, *c["burning_booster"], label="burning_field_booster"))
    events.append(click(pid, *c["burning_max"], label="burning_field_booster_max"))
    events.append(click(pid, *c["burning_confirm"], label="burning_field_booster_confirm"))
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
