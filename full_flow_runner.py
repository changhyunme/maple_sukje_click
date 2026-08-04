#!/usr/bin/env python3
"""Execute the recorded Maple homework flow for every BlueStacks instance."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"
DEFAULT_PIDS = [22112, 59938, 31126]


def run_command(args: list[str]) -> dict[str, object]:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"stdout": result.stdout}


def run_instance(pid: int, wait_seconds: float, world_boss_seconds: float) -> dict[str, object]:
    script = lambda name: f"{ROOT}/{name}"
    output: dict[str, object] = {"pid": pid}
    output["wake"] = run_command(["python3", script("mac_gesture.py"), "unlock", str(pid)])
    time.sleep(1.0)
    output["homework_1"] = run_command(["python3", script("homework_runner.py"), str(pid)])
    output["action_4"] = run_command(["python3", script("booster_runner.py"), str(pid), "--wait-seconds", str(wait_seconds)])
    output["action_3"] = run_command(["python3", script("claim_runner.py"), str(pid), "--no-unlock"])
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
