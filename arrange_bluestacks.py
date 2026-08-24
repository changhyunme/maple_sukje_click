#!/usr/bin/env python3
"""Bring the three Maple BlueStacks windows onto the current desktop.

BlueStacks sometimes restores instances on a hidden/negative-y desktop and
its own position controls can fail.  This uses the macOS Accessibility window
position API through ``window_control.py`` and targets only the registered
BlueStacks PIDs.
"""

from __future__ import annotations

import argparse
import json
import time

from activate_instance import activate_process
from window_control import move_window
from instance_registry import current_pids, instance_name


DEFAULT_LAYOUT = {
    # The user's BlueStacks display is the upper monitor: bounds y=-1440..0.
    "Air": (20.0, -1420.0),
    # The upper display is 2048 points wide.  With Air1 restored to its
    # verified 1003-point width, x=1110 put the hamburger beyond the right
    # edge.  Air ends at x=1044, so x=1045 keeps both windows fully visible.
    "Air1": (1045.0, -1420.0),
    "Air2": (20.0, -740.0),
}

DEFAULT_SIZES = {
    "Air": (1024.0, 590.0),
    "Air1": (1003.0, 578.0),
    "Air2": (1093.0, 629.0),
}


def arrange(pids: list[int]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for pid in pids:
        name = instance_name(pid)
        if not activate_process(pid):
            raise RuntimeError(f"could not activate BlueStacks PID {pid}")
        time.sleep(0.2)
        x, y = DEFAULT_LAYOUT[name]
        width, height = DEFAULT_SIZES[name]
        results.append(move_window(pid, x, y, width, height))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids", nargs="+", type=int, default=None)
    args = parser.parse_args()
    if args.pids is None:
        args.pids = current_pids()
    print(json.dumps({"windows": arrange(args.pids)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
