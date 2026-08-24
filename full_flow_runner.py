#!/usr/bin/env python3
"""Execute the recorded Maple homework flow for every BlueStacks instance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time

from instance_registry import current_pids


ROOT = os.path.dirname(os.path.abspath(__file__))


def run_command(args: list[str]) -> dict[str, object]:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"stdout": result.stdout}


def command_failure(error: subprocess.CalledProcessError) -> dict[str, object]:
    """Return a serializable failure without hiding the runner's diagnosis."""
    return {
        "status": "failed",
        "returncode": error.returncode,
        "command": error.cmd,
        "stdout": error.stdout,
        "stderr": error.stderr,
    }


def is_sleep_screen(pid: int) -> bool:
    """Detect the dark in-game sleep screen without sending a risky click."""
    window = run_command(["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)])
    window_id = int(window["window_id"])
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
        time.sleep(1.2)
        return {"sleep_screen": True, "wake": wake}
    return {"sleep_screen": False}


def run_instance_before_mission(
    pid: int,
    wait_seconds: float,
    world_boss_seconds: float,
    summon_max_batches: int,
    *,
    skip_action_5: bool = False,
) -> dict[str, object]:
    script = lambda name: f"{ROOT}/{name}"
    output: dict[str, object] = {"pid": pid}
    output["wake"] = ensure_awake(pid)
    output["homework_1"] = run_command(["python3", script("homework_runner.py"), str(pid)])
    output["action_4"] = run_command(["python3", script("booster_runner.py"), str(pid), "--wait-seconds", str(wait_seconds)])
    output["wake_before_shop"] = ensure_awake(pid)
    output["shop_free_rewards"] = run_command(["python3", script("shop_runner.py"), str(pid)])
    output["wake_before_summon"] = ensure_awake(pid)
    output["summon_free_rewards"] = run_command(
        ["python3", script("summon_runner.py"), str(pid), "--max-batches", str(summon_max_batches)]
    )
    output["friend_exchange"] = run_command(
        ["python3", script("friend_runner.py"), str(pid)]
    )
    output["wake_before_action_5"] = ensure_awake(pid)
    if skip_action_5:
        output["action_5"] = {
            "status": "skipped",
            "reason": "verification mode: daily combat actions already completed",
        }
    else:
        output["action_5"] = run_command(["python3", script("guild_arena_worldboss_runner.py"), str(pid), "--world-boss-seconds", str(world_boss_seconds)])
    output["wake_before_action_3"] = ensure_awake(pid)
    output["mailbox_pass"] = run_command([
        "python3", script("claim_runner.py"), str(pid), "--no-unlock",
        "--only", "mailbox-pass",
    ])
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids", nargs="+", type=int, default=None)
    parser.add_argument("--wait-seconds", type=float, default=300.0)
    parser.add_argument("--world-boss-seconds", type=float, default=90.0)
    parser.add_argument(
        "--verify-completed", action="store_true",
        help="recheck idempotent screens without repeating guild/arena/world-boss",
    )
    parser.add_argument(
        "--summon-max-batches", type=int, default=2000,
        help="deprecated compatibility option; summon tickets are never spent",
    )
    args = parser.parse_args()
    if args.pids is None:
        args.pids = current_pids()
    results = []
    for pid in args.pids:
        try:
            result = run_instance_before_mission(
                pid,
                args.wait_seconds,
                args.world_boss_seconds,
                args.summon_max_batches,
                skip_action_5=args.verify_completed,
            )
            result["pre_mission_status"] = "completed"
        except subprocess.CalledProcessError as error:
            # A visual guard should stop the uncertain VM, but it must not
            # prevent the other two independent instances from completing.
            result = {
                "pid": pid,
                "pre_mission_status": "failed",
                "failure": command_failure(error),
            }
        results.append(result)
    # Daily missions run only after all ordinary chores finish on all VMs.
    # The dynamic event scan is the sole phase allowed after missions.
    for result, pid in zip(results, args.pids):
        if result.get("pre_mission_status") != "completed":
            result["mission_last"] = {
                "status": "skipped",
                "reason": "pre_mission_flow_failed",
            }
            continue
        result["wake_before_mission"] = ensure_awake(pid)
        try:
            mission_attempts = []
            mission_complete = False
            for _ in range(3):
                attempt = run_command([
                    "python3", f"{ROOT}/claim_runner.py", str(pid), "--no-unlock",
                    "--only", "mission",
                ])
                mission_attempts.append(attempt)
                probes = {
                    event.get("action"): event.get("available")
                    for event in attempt.get("events", [])
                    if event.get("action") in {
                        "mission_claim_probe", "mission_final_claim_probe",
                    }
                }
                if (
                    probes.get("mission_claim_probe") is False
                    and probes.get("mission_final_claim_probe") is False
                ):
                    mission_complete = True
                    break
            result["mission_last"] = {
                "attempts": mission_attempts,
                "completed": mission_complete,
                "status": "completed" if mission_complete else "failed",
            }
        except subprocess.CalledProcessError as error:
            # Mission failures are isolated as well, so PID2/PID3 are still
            # attempted after PID1 while retaining a machine-readable report.
            result["mission_last"] = command_failure(error)
    # Event badges are dynamic and depend on rewards produced by every other
    # chore, including missions, so the adaptive event scan is the true final
    # phase.  It is isolated per VM just like the earlier phases.
    for result, pid in zip(results, args.pids):
        if result.get("pre_mission_status") != "completed":
            result["event_final"] = {
                "status": "skipped",
                "reason": "pre_mission_flow_failed",
            }
            continue
        if isinstance(result.get("mission_last"), dict) and result["mission_last"].get("status") == "failed":
            result["event_final"] = {
                "status": "skipped",
                "reason": "mission_flow_failed",
            }
            continue
        result["wake_before_event"] = ensure_awake(pid)
        try:
            result["event_final"] = run_command([
                "python3", f"{ROOT}/event_runner.py", str(pid),
            ])
        except subprocess.CalledProcessError as error:
            result["event_final"] = command_failure(error)
    print(json.dumps({"instances": results}, ensure_ascii=False))
