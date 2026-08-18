#!/usr/bin/env python3
"""Safely claim mailbox, pass, and mission rewards on one BlueStacks VM."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time

from full_flow_runner import ensure_awake
from instance_registry import instance_name
from ui_guard import ClickVerificationError, Roi, verified_click


ROOT = "/Users/gorgeous/utils/maple_clicker"


INSTANCE_OVERRIDES = {
    "Air2": {
        "pass": (0.770, 0.205),
        "mission": (0.707, 0.205),
        # Air2's mailbox modal is narrower than its full-screen pass and
        # mission views, so it needs its own close point.
        "mailbox_close": (0.832, 0.170),
    },
}


def coordinates_for(pid: int) -> dict[str, tuple[float, float]]:
    coords = {
        "hamburger": (0.936, 0.095),
        "mailbox": (0.851, 0.204),
        "mail_claim": (0.760, 0.840),
        "confirm": (0.556, 0.790),
        "pass": (0.782, 0.204),
        "pass_claim": (0.880, 0.920),
        "mission": (0.716, 0.150),
        "mission_claim": (0.760, 0.840),
        "mission_final_claim": (0.760, 0.285),
        "dismiss": (0.135, 0.860),
        "close": (0.928, 0.100),
    }
    coords.update(INSTANCE_OVERRIDES.get(instance_name(pid), {}))
    return coords


BUTTON_CROPS = {
    # Sample only the interior of each action button. Wider crops picked up
    # orange mission progress bars and colorful reward icons on Air1, causing
    # already-gray buttons to be treated as claimable forever.
    "mail_claim": (0.720, 0.825, 0.070, 0.050),
    "pass_claim": (0.845, 0.890, 0.070, 0.055),
    "mission_claim": (0.720, 0.825, 0.070, 0.050),
    # Keep this crop inside the top-right completion button.  The old, wider
    # crop included the brightly coloured ticket/gem reward icons and could
    # mistake a disabled gray button for an active one.
    "mission_final_claim": (0.720, 0.265, 0.070, 0.045),
}
ACTIVE_COLOR_THRESHOLD = 0.075


def _window_rgb(pid: int, crop: tuple[float, float, float, float]) -> bytes:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(result.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(prefix=f"maple_claim_{pid}_", suffix=".png", delete=False) as image:
        path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), path], check=True)
        x, y, width, height = crop
        return subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
                "-vf", f"crop=iw*{width}:ih*{height}:iw*{x}:ih*{y},format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def active_button_signal(pid: int, button: str) -> float:
    """Measure colored fill; completed buttons are neutral gray."""
    rgb = _window_rgb(pid, BUTTON_CROPS[button])
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    if not pixels:
        return -1.0
    return sum(
        max(red, green, blue) > 125
        and max(red, green, blue) - min(red, green, blue) > 45
        for red, green, blue in pixels
    ) / len(pixels)


def button_available(pid: int, button: str, samples: int = 3) -> tuple[bool, float]:
    signal = -1.0
    for _ in range(samples):
        signal = active_button_signal(pid, button)
        if signal >= ACTIVE_COLOR_THRESHOLD:
            return True, signal
        time.sleep(0.30)
    return False, signal


def guarded_click(
    pid: int,
    point: tuple[float, float],
    label: str,
    *,
    pause: float = 1.4,
    roi: Roi = Roi(0.08, 0.10, 0.84, 0.82),
    min_delta: float = 0.008,
) -> dict[str, object]:
    return verified_click(
        pid, *point, label=label, pause=pause, roi=roi,
        min_delta=min_delta, noise_multiplier=0.0, retries=0,
    )


def open_menu_screen(pid: int, screen: str, events: list[dict[str, object]]) -> None:
    c = coordinates_for(pid)
    events.append(guarded_click(
        pid, c["hamburger"], f"hamburger_{screen}",
        roi=Roi(0.66, 0.08, 0.32, 0.82), min_delta=0.012,
    ))
    events.append(guarded_click(
        pid, c[screen], screen, pause=1.8,
        roi=Roi(0.06, 0.08, 0.88, 0.84), min_delta=0.012,
    ))


def close_screen(pid: int, screen: str, events: list[dict[str, object]]) -> None:
    c = coordinates_for(pid)
    close_point = c.get(f"{screen}_close", c["close"])
    events.append(guarded_click(
        pid, close_point, f"close_{screen}", pause=1.2,
        roi=Roi(0.06, 0.08, 0.88, 0.84),
    ))


def mailbox_flow(pid: int, events: list[dict[str, object]]) -> None:
    c = coordinates_for(pid)
    open_menu_screen(pid, "mailbox", events)
    available, signal = button_available(pid, "mail_claim")
    events.append({
        "action": "mail_claim_probe", "active_color_signal": round(signal, 5),
        "available": available,
    })
    if available:
        # Air2's reward overlay fades in slowly and can produce only a small
        # frame delta even though the claim succeeded.  Keep zero retries but
        # accept that measured transition so a successful claim is not
        # reported as a failure.
        events.append(guarded_click(
            pid, c["mail_claim"], "mail_claim", pause=2.0, min_delta=0.004,
        ))
        # All three instances now show the intermediate "일괄 수령 목록"
        # confirmation dialog.  Air2 used to skip this step, leaving the
        # dialog open and making the following reward-dismiss click miss.
        events.append(guarded_click(
            pid, c["confirm"], "mail_confirm", pause=2.8, min_delta=0.004,
        ))
        events.append(guarded_click(pid, c["dismiss"], "dismiss_mail_reward", pause=1.2))
    close_screen(pid, "mailbox", events)


def pass_flow(pid: int, events: list[dict[str, object]]) -> None:
    c = coordinates_for(pid)
    open_menu_screen(pid, "pass", events)
    available, signal = button_available(pid, "pass_claim")
    events.append({
        "action": "pass_claim_probe", "active_color_signal": round(signal, 5),
        "available": available,
    })
    if available:
        events.append(guarded_click(pid, c["pass_claim"], "pass_claim", pause=2.8))
        events.append(guarded_click(pid, c["dismiss"], "dismiss_pass_reward", pause=1.2))
    close_screen(pid, "pass", events)


def run_mailbox_pass(pid: int, do_unlock: bool = True) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    if do_unlock:
        events.append({"action": "ensure_awake", **ensure_awake(pid)})
    mailbox_flow(pid, events)
    pass_flow(pid, events)
    return events


def run_mission(pid: int, do_unlock: bool = True) -> list[dict[str, object]]:
    """Claim daily missions as the final normal action of the multi-VM run."""
    events: list[dict[str, object]] = []
    if do_unlock:
        events.append({"action": "ensure_awake", **ensure_awake(pid)})
    c = coordinates_for(pid)
    open_menu_screen(pid, "mission", events)

    available, signal = button_available(pid, "mission_claim")
    events.append({
        "action": "mission_claim_probe", "active_color_signal": round(signal, 5),
        "available": available,
    })
    if available:
        events.append(guarded_click(pid, c["mission_claim"], "mission_claim_all", pause=2.8))
        events.append(guarded_click(pid, c["dismiss"], "dismiss_mission_rewards", pause=1.2))

    final_available, final_signal = button_available(pid, "mission_final_claim")
    events.append({
        "action": "mission_final_claim_probe",
        "active_color_signal": round(final_signal, 5),
        "available": final_available,
    })
    if final_available:
        events.append(guarded_click(
            pid, c["mission_final_claim"], "mission_final_claim",
            pause=3.2, min_delta=0.004,
        ))
        # Some final-reward overlays fade straight back to the field and
        # measure only about 0.003 delta.  This click is non-retrying and far
        # from every paid control, so accept that observed transition.
        events.append(guarded_click(
            pid, c["dismiss"], "dismiss_mission_final_reward",
            pause=1.2, min_delta=0.002,
        ))
    close_screen(pid, "mission", events)
    return events


def run(pid: int, do_unlock: bool = True) -> list[dict[str, object]]:
    events = run_mailbox_pass(pid, do_unlock=do_unlock)
    events.extend(run_mission(pid, do_unlock=False))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--no-unlock", action="store_true")
    parser.add_argument(
        "--only", choices=("all", "mailbox-pass", "mission"), default="all",
        help="split mission so it can run after every other VM action",
    )
    args = parser.parse_args()
    do_unlock = not args.no_unlock
    if args.only == "mailbox-pass":
        output = run_mailbox_pass(args.pid, do_unlock=do_unlock)
    elif args.only == "mission":
        output = run_mission(args.pid, do_unlock=do_unlock)
    else:
        output = run(args.pid, do_unlock=do_unlock)
    print(json.dumps({"pid": args.pid, "events": output}, ensure_ascii=False))
