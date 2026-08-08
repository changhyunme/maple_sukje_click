#!/usr/bin/env python3
"""Run the registered mailbox/pass/mission claim action on one BlueStacks window."""
from __future__ import annotations

import argparse
import subprocess
import time


ROOT = "/Users/gorgeous/utils/maple_clicker"


INSTANCE_OVERRIDES = {
    # Verified on a rerun: pass/mission are full-page screens on Air 2 and
    # their menu cells sit slightly left of the Air/Air 1 positions.
    31126: {
        "pass": (0.770, 0.205),
        "mission": (0.707, 0.205),
        "close": (0.910, 0.120),
    },
}


def coordinates_for(pid: int) -> dict[str, tuple[float, float]]:
    coords = {
        "hamburger": (0.936, 0.095),
        "mailbox": (0.851, 0.204),
        "mail_claim": (0.805, 0.840),
        "confirm": (0.556, 0.790),
        "pass": (0.782, 0.204),
        "pass_claim": (0.900, 0.920),
        "mission": (0.716, 0.150),
        "mission_claim": (0.780, 0.840),
        "close": (0.928, 0.100),
    }
    override = INSTANCE_OVERRIDES.get(pid, {})
    coords.update(override)
    return coords


def click(pid: int, x: float, y: float, pause: float = 1.0) -> None:
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
    time.sleep(1.2)


def mailbox_flow(pid: int) -> None:
    c = coordinates_for(pid)
    click(pid, *c["hamburger"])   # hamburger
    click(pid, *c["mailbox"])     # mailbox
    click(pid, *c["mail_claim"])  # 모두수령
    click(pid, *c["confirm"])     # aggregate confirmation: 수령
    click(pid, 0.135, 0.860)        # dismiss item-acquired overlay
    click(pid, *c["close"])        # close screen


def simple_flow(pid: int, item_x: float, item_y: float, claim_x: float, claim_y: float) -> None:
    c = coordinates_for(pid)
    click(pid, *c["hamburger"])    # hamburger
    click(pid, item_x, item_y)      # pass/mission
    click(pid, claim_x, claim_y)    # claim all
    click(pid, 0.135, 0.860)        # dismiss item-acquired overlay
    click(pid, *c["close"])        # close screen


def run(pid: int, do_unlock: bool = True) -> None:
    if do_unlock:
        unlock(pid)
    # Mailbox: 우편함 -> 모두수령 -> aggregate confirmation -> reward popup -> close
    mailbox_flow(pid)
    # Pass: 패스 -> 일괄 받기 -> reward popup -> close
    c = coordinates_for(pid)
    simple_flow(pid, *c["pass"], *c["pass_claim"])
    # Mission: 미션 -> 일괄 수령 -> reward popup -> close
    simple_flow(pid, *c["mission"], *c["mission_claim"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--no-unlock", action="store_true")
    args = parser.parse_args()
    run(args.pid, do_unlock=not args.no_unlock)
