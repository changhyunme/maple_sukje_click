#!/usr/bin/env python3
"""Execute the recorded Maple homework flow for every BlueStacks instance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"
DEFAULT_PIDS = [22112, 59938, 31126]
# Current on-screen window numbers.  These are stable for the three running
# instances and let us inspect the window without clicking it.
WINDOW_IDS = {22112: 56638, 59938: 37229, 31126: 31903}


def run_command(args: list[str]) -> dict[str, object]:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"stdout": result.stdout}


def is_sleep_screen(pid: int) -> bool:
    """Detect the dark in-game sleep screen without sending a risky click."""
    window_id = WINDOW_IDS.get(pid)
    if window_id is None:
        return False
    with tempfile.NamedTemporaryFile(prefix=f"maple_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        probe = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", image_path,
                "-vf", "signalstats,metadata=print:file=-",
                "-frames:v", "1", "-f", "null", "-",
            ], capture_output=True, text=True, check=False,
        )
        for line in (probe.stdout + probe.stderr).splitlines():
            if "lavfi.signalstats.YAVG=" in line:
                return float(line.rsplit("=", 1)[1]) < 60.0
        return False
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def ensure_awake(pid: int) -> dict[str, object]:
    sleeping = is_sleep_screen(pid)
    if sleeping:
        wake = run_command(["python3", f"{ROOT}/mac_gesture.py", "unlock", str(pid)])
        time.sleep(1.0)
        return {"sleep_screen": True, "wake": wake}
    return {"sleep_screen": False}


def run_instance(pid: int, wait_seconds: float, world_boss_seconds: float) -> dict[str, object]:
    script = lambda name: f"{ROOT}/{name}"
    output: dict[str, object] = {"pid": pid}
    output["wake"] = ensure_awake(pid)
    output["homework_1"] = run_command(["python3", script("homework_runner.py"), str(pid)])
    output["action_4"] = run_command(["python3", script("booster_runner.py"), str(pid), "--wait-seconds", str(wait_seconds)])
    output["wake_before_action_3"] = ensure_awake(pid)
    output["action_3"] = run_command(["python3", script("claim_runner.py"), str(pid), "--no-unlock"])
    output["wake_before_action_5"] = ensure_awake(pid)
    output["action_5"] = run_command(["python3", script("guild_arena_worldboss_runner.py"), str(pid), "--world-boss-seconds", str(world_boss_seconds)])
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids", nargs="+", type=int, default=DEFAULT_PIDS)
    parser.add_argument("--wait-seconds", type=float, default=300.0)
    parser.add_argument("--world-boss-seconds", type=float, default=90.0)
    args = parser.parse_args()
    results = []
    for pid in args.pids:
        results.append(run_instance(pid, args.wait_seconds, args.world_boss_seconds))
    print(json.dumps({"instances": results}, ensure_ascii=False))
