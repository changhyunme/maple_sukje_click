#!/usr/bin/env python3
"""Run the registered mailbox/pass/mission claim action on one BlueStacks window."""
from __future__ import annotations

import argparse
import subprocess
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"


def click(pid: int, x: float, y: float, pause: float = 0.8) -> None:
    subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
         "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}"],
        check=True,
    )
    time.sleep(pause)


def unlock(pid: int) -> None:
    subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "unlock", str(pid)],
        check=True,
    )
    time.sleep(1.0)


def mailbox_flow(pid: int) -> None:
    click(pid, 0.936, 0.095)       # hamburger
    click(pid, 0.851, 0.204)       # mailbox
    click(pid, 0.805, 0.840)       # 모두수령
    click(pid, 0.556, 0.790)       # aggregate confirmation: 수령
    click(pid, 0.135, 0.860)        # dismiss item-acquired overlay
    click(pid, 0.850, 0.100)        # close screen


def simple_flow(pid: int, item_x: float, item_y: float, claim_x: float, claim_y: float) -> None:
    click(pid, 0.936, 0.095)       # hamburger
    click(pid, item_x, item_y)      # pass/mission
    click(pid, claim_x, claim_y)    # claim all
    click(pid, 0.135, 0.860)        # dismiss item-acquired overlay
    click(pid, 0.850, 0.100)        # close screen


def run(pid: int, do_unlock: bool = True) -> None:
    if do_unlock:
        unlock(pid)
    # Mailbox: 우편함 -> 모두수령 -> aggregate confirmation -> reward popup -> close
    mailbox_flow(pid)
    # Pass: 패스 -> 일괄 받기 -> reward popup -> close
    simple_flow(pid, 0.782, 0.204, 0.900, 0.920)
    # Mission: 미션 -> 일괄 수령 -> reward popup -> close
    simple_flow(pid, 0.716, 0.150, 0.780, 0.840)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--no-unlock", action="store_true")
    args = parser.parse_args()
    run(args.pid, do_unlock=not args.no_unlock)
