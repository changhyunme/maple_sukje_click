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


DEFAULT_LAYOUT = {
    # The user's BlueStacks display is the upper monitor: bounds y=-1440..0.
    22112: (20.0, -1420.0),    # BlueStacks Air
    59938: (1110.0, -1420.0),  # BlueStacks Air 1
    31126: (20.0, -740.0),     # BlueStacks Air 2
}


def arrange(pids: list[int]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for pid in pids:
        if pid not in DEFAULT_LAYOUT:
            raise ValueError(f"unregistered BlueStacks PID: {pid}")
        if not activate_process(pid):
            raise RuntimeError(f"could not activate BlueStacks PID {pid}")
        time.sleep(0.2)
        x, y = DEFAULT_LAYOUT[pid]
        results.append(move_window(pid, x, y))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids", nargs="+", type=int, default=list(DEFAULT_LAYOUT))
    args = parser.parse_args()
    print(json.dumps({"windows": arrange(args.pids)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
