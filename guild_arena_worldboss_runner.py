#!/usr/bin/env python3
"""Run the fifth action: guild buildings, arena and world boss."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time

from instance_registry import instance_name
from ui_guard import Roi, verified_click
from full_flow_runner import ensure_awake


ROOT = "/Users/gorgeous/utils/maple_clicker"


def click(pid: int, x: float, y: float, pause: float = 1.0, label: str = "click") -> dict[str, object]:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
         "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}"],
        check=True, capture_output=True, text=True,
    )
    if pause:
        time.sleep(pause)
    return {"action": label, **json.loads(result.stdout)}


# These are the same menu-relative coordinates used by the recorded menu actions.
COORDINATES = {
    "hamburger": (0.936, 0.095),
    "guild": (0.852, 0.424),
    "guild_building": (0.080, 0.680),
    "free_upgrade_x": (0.300, 0.545, 0.825),
    "free_upgrade_y": 0.855,
    "arena": (0.923, 0.650),
    "arena_top_person": (0.870, 0.230),
    "arena_start": (0.870, 0.230),
    # A battle plus the result auto-exit takes roughly 20 seconds.  At eight
    # seconds the next two taps were swallowed by the first battle scene.
    "arena_pause": 30.0,
    "world_boss": (0.780, 0.680),
    "world_boss_enter": (0.815, 0.910),
    "close": (0.928, 0.100),
}


# Verified manually against the rerun layout of BlueStacks Air 2.  Air and
# Air 1 retain the original profile above.
INSTANCE_OVERRIDES = {
    "Air2": {
        "guild": (0.840, 0.445),
        "guild_building": (0.100, 0.680),
        "free_upgrade_x": (0.305, 0.555, 0.810),
        "free_upgrade_y": 0.855,
        "arena": (0.905, 0.650),
        "arena_top_person": (0.865, 0.250),
        "arena_start": (0.865, 0.250),
        # Air 2 battles can last 20–30 seconds; a short fixed pause would
        # send the next tap into the battle scene on a rerun.
        "arena_pause": 30.0,
        "close": (0.910, 0.120),
    },
}

# A free building button has a compact red badge at its upper-right.  Paid
# buttons retain the same cyan fill, so the badge is the only safe selector.
FREE_BADGE_CENTERS = ((0.405, 0.826), (0.670, 0.826), (0.935, 0.826))
FREE_BADGE_THRESHOLD = 0.006


def _window_rgb(pid: int, crop: tuple[float, float, float, float]) -> bytes:
    window = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(window.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(prefix=f"maple_guild_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        x, y, width, height = crop
        return subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                "-vf", f"crop=iw*{width}:ih*{height}:iw*{x}:ih*{y},format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def free_upgrade_badge_signal(pid: int, index: int) -> float:
    center_x, center_y = FREE_BADGE_CENTERS[index]
    rgb = _window_rgb(pid, (center_x - 0.012, center_y - 0.020, 0.024, 0.040))
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    if not pixels:
        return 0.0
    return sum(red > 155 and green < 100 and blue < 135 for red, green, blue in pixels) / len(pixels)


def arena_start_signal(pid: int) -> float:
    """Return the cyan-button coverage of the first arena start button."""
    rgb = _window_rgb(pid, (0.815, 0.195, 0.125, 0.085))
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    if not pixels:
        return 0.0
    return sum(
        red < 95 and green > 115 and blue > 125
        for red, green, blue in pixels
    ) / len(pixels)


def wait_for_arena_list(pid: int, timeout: float = 45.0) -> dict[str, object]:
    """Wait until combat returns to the opponent list before the next tap."""
    deadline = time.monotonic() + timeout
    attempts = 0
    signal = 0.0
    # A match cannot finish immediately.  Delaying the first probe also avoids
    # mistaking the list that is still fading out for a completed battle.
    time.sleep(16.0)
    while time.monotonic() < deadline:
        attempts += 1
        signal = arena_start_signal(pid)
        if signal >= 0.035:
            return {
                "action": "wait_for_arena_list",
                "completed": True,
                "attempts": attempts,
                "start_button_signal": round(signal, 5),
            }
        time.sleep(3.0)
    raise RuntimeError(
        f"arena did not return to opponent list within {timeout:.0f}s "
        f"(cyan signal={signal:.5f})"
    )


def coordinates_for(pid: int) -> dict[str, object]:
    coords: dict[str, object] = dict(COORDINATES)
    coords.update(INSTANCE_OVERRIDES.get(instance_name(pid), {}))
    return coords


def run_guild(pid: int) -> list[dict[str, object]]:
    c = coordinates_for(pid)
    events: list[dict[str, object]] = [{"action": "ensure_awake", **ensure_awake(pid)}]

    events.append(verified_click(
        pid, *c["hamburger"], label="hamburger_guild", pause=1.2,
        roi=Roi(0.66, 0.08, 0.32, 0.82), min_delta=0.012,
        noise_multiplier=0.0, retries=0,
    ))
    events.append(verified_click(
        pid, *c["guild"], label="guild", pause=3.2,
        roi=Roi(0.10, 0.08, 0.82, 0.84), min_delta=0.012,
        noise_multiplier=0.0, retries=0,
    ))
    events.append(verified_click(
        pid, *c["guild_building"], label="guild_building", pause=1.8,
        roi=Roi(0.04, 0.14, 0.92, 0.78), min_delta=0.012,
        noise_multiplier=0.0, retries=1,
    ))
    for i, x in enumerate(c["free_upgrade_x"], start=1):
        before_signal = free_upgrade_badge_signal(pid, i - 1)
        if before_signal < FREE_BADGE_THRESHOLD:
            events.append({
                "action": f"guild_free_upgrade_{i}",
                "status": "unavailable_or_already_claimed",
                "badge_signal": round(before_signal, 5),
            })
            continue
        events.append(click(
            pid, x, c["free_upgrade_y"], pause=3.4,
            label=f"guild_free_upgrade_{i}",
        ))
        # The reward animation ignores early taps.  Dismiss from the empty
        # left margin only after it has settled, away from every building.
        events.append(click(pid, 0.150, 0.760, pause=1.0, label=f"dismiss_upgrade_{i}"))
        after_signal = free_upgrade_badge_signal(pid, i - 1)
        events.append({
            "action": f"verify_guild_free_upgrade_{i}",
            "badge_signal": round(after_signal, 5),
            "completed": after_signal < FREE_BADGE_THRESHOLD,
        })
        if after_signal >= FREE_BADGE_THRESHOLD:
            raise RuntimeError(
                f"guild free upgrade {i} badge remains: {after_signal:.5f}"
            )
    events.append(verified_click(
        pid, *c["close"], label="close_guild", pause=1.5,
        roi=Roi(0.04, 0.12, 0.92, 0.80), min_delta=0.008,
        noise_multiplier=0.0, retries=0,
    ))
    return events


def run_arena(
    pid: int,
    battles: int = 3,
    *,
    already_open: bool = False,
) -> list[dict[str, object]]:
    c = coordinates_for(pid)
    events: list[dict[str, object]] = [{"action": "ensure_awake", **ensure_awake(pid)}]

    if not already_open:
        events.append(verified_click(
            pid, *c["hamburger"], label="hamburger_arena", pause=1.2,
            roi=Roi(0.66, 0.08, 0.32, 0.82), min_delta=0.012,
            noise_multiplier=0.0, retries=0,
        ))
        events.append(verified_click(
            pid, *c["arena"], label="arena", pause=2.5,
            roi=Roi(0.08, 0.08, 0.86, 0.84), min_delta=0.012,
            noise_multiplier=0.0, retries=0,
        ))
    initial_signal = arena_start_signal(pid)
    # Hamburger-panel animations can satisfy the generic click delta even
    # when the arena tile tap itself is swallowed.  Give a genuine load a
    # second chance, then retry the tile once only while the arena-specific
    # start-button signal is still absent.
    if initial_signal < 0.035:
        time.sleep(2.0)
        initial_signal = arena_start_signal(pid)
    if initial_signal < 0.035:
        events.append(verified_click(
            pid, *c["arena"], label="arena_retry", pause=2.5,
            roi=Roi(0.08, 0.08, 0.86, 0.84), min_delta=0.012,
            noise_multiplier=0.0, retries=0,
        ))
        initial_signal = arena_start_signal(pid)
    events.append({
        "action": "verify_arena_list",
        "start_button_signal": round(initial_signal, 5),
        "completed": initial_signal >= 0.035,
    })
    if initial_signal < 0.035:
        raise RuntimeError(f"arena start button unavailable: {initial_signal:.5f}")
    # The earlier implementation tapped this coordinate once before the loop,
    # then tapped again while the loading screen was appearing.  All remaining
    # taps could land in combat.  Every battle is now one verified transition,
    # followed by a visual wait for the opponent list to return.
    for i in range(1, battles + 1):
        events.append(verified_click(
            pid, *c["arena_start"], label=f"arena_battle_{i}", pause=3.0,
            roi=Roi(0.06, 0.08, 0.88, 0.84), min_delta=0.020,
            # BlueStacks occasionally drops the first tap while the opponent
            # list finishes repainting.  A zero-delta tap is safe to retry:
            # once combat starts the large loading transition is detected
            # before verified_click can issue a second tap.
            noise_multiplier=0.0, retries=1,
        ))
        events.append({"battle": i, **wait_for_arena_list(pid)})
    events.append(verified_click(
        pid, *c["close"], label="close_arena", pause=1.5,
        roi=Roi(0.04, 0.10, 0.92, 0.82), min_delta=0.008,
        noise_multiplier=0.0, retries=0,
    ))
    # Arena background animation can satisfy a generic image-delta check even
    # when the X tap was swallowed.  The cyan opponent buttons must disappear
    # after a real close; retry the X once if that arena-specific signal stays.
    close_signal = arena_start_signal(pid)
    if close_signal >= 0.035:
        events.append(verified_click(
            pid, *c["close"], label="close_arena_retry", pause=1.5,
            roi=Roi(0.04, 0.10, 0.92, 0.82), min_delta=0.008,
            noise_multiplier=0.0, retries=0,
        ))
        close_signal = arena_start_signal(pid)
    events.append({
        "action": "verify_arena_closed",
        "start_button_signal": round(close_signal, 5),
        "completed": close_signal < 0.035,
    })
    if close_signal >= 0.035:
        raise RuntimeError(f"arena remained open after close: {close_signal:.5f}")
    return events


def run_world_boss(pid: int, world_boss_seconds: float = 90.0) -> list[dict[str, object]]:
    c = coordinates_for(pid)
    events: list[dict[str, object]] = [{"action": "ensure_awake", **ensure_awake(pid)}]

    events.append(verified_click(
        pid, *c["hamburger"], label="hamburger_world_boss", pause=1.2,
        roi=Roi(0.66, 0.08, 0.32, 0.82), min_delta=0.012,
        noise_multiplier=0.0, retries=0,
    ))
    events.append(verified_click(
        pid, *c["world_boss"], label="world_boss", pause=2.5,
        roi=Roi(0.06, 0.08, 0.88, 0.84), min_delta=0.012,
        noise_multiplier=0.0, retries=0,
    ))
    events.append(verified_click(
        pid, *c["world_boss_enter"], label="world_boss_enter", pause=3.0,
        roi=Roi(0.06, 0.08, 0.88, 0.84), min_delta=0.020,
        noise_multiplier=0.0, retries=0,
    ))
    if world_boss_seconds > 0:
        time.sleep(world_boss_seconds)
    events.append({"action": "world_boss_wait", "duration_seconds": world_boss_seconds})
    # The world boss returns to the field automatically.  A blind close tap
    # there opens the hamburger menu, corrupting the next runner's zero point.
    return events


def run(pid: int, world_boss_seconds: float = 90.0, arena_battles: int = 3) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    events.extend(run_guild(pid))
    events.extend(run_arena(pid, arena_battles))
    events.extend(run_world_boss(pid, world_boss_seconds))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--world-boss-seconds", type=float, default=90.0)
    parser.add_argument("--arena-battles", type=int, default=3)
    parser.add_argument(
        "--arena-already-open", action="store_true",
        help="resume at an arena opponent list that was visually verified",
    )
    parser.add_argument(
        "--only", choices=("all", "guild", "arena", "world-boss"), default="all",
    )
    args = parser.parse_args()
    if args.only == "guild":
        events = run_guild(args.pid)
    elif args.only == "arena":
        events = run_arena(
            args.pid, args.arena_battles,
            already_open=args.arena_already_open,
        )
    elif args.only == "world-boss":
        events = run_world_boss(args.pid, args.world_boss_seconds)
    else:
        events = run(args.pid, args.world_boss_seconds, args.arena_battles)
    print(json.dumps({"pid": args.pid, "events": events}, ensure_ascii=False))
