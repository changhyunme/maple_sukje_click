"""Discover the currently running BlueStacks Air instance PIDs.

BlueStacks assigns new PIDs after every restart.  Coordinate profiles are tied
to the instance name/order, never to yesterday's process number.
"""

from __future__ import annotations

import subprocess


INSTANCE_ORDER = ("Air", "Air1", "Air2")


def discover_instances() -> dict[str, int]:
    result = subprocess.run(
        ["ps", "ax", "-o", "pid=,args="],
        check=True,
        capture_output=True,
        text=True,
    )
    found: dict[str, int] = {}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if "/Applications/BlueStacks.app/Contents/MacOS/BlueStacks" not in command:
            continue
        if "--instance Tiramisu64_2" in command:
            found["Air2"] = int(pid_text)
        elif "--instance Tiramisu64_1" in command:
            found["Air1"] = int(pid_text)
        elif "--instance" not in command:
            found["Air"] = int(pid_text)
    return found


def current_pids() -> list[int]:
    found = discover_instances()
    missing = [name for name in INSTANCE_ORDER if name not in found]
    if missing:
        raise RuntimeError(f"BlueStacks instances not running: {', '.join(missing)}")
    return [found[name] for name in INSTANCE_ORDER]


def instance_name(pid: int) -> str:
    for name, current_pid in discover_instances().items():
        if current_pid == pid:
            return name
    raise RuntimeError(f"PID {pid} is not a current BlueStacks Air instance")
