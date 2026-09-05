#!/usr/bin/env python3
"""Complete the daily friend elite-summon-point exchange.

The friend list exposes two per-friend round buttons: receive (left arrow)
and send (right arrow).  On the first available row, both buttons are tapped
in that order.  The game disables the row after the send tap and increments
the daily counter; no bulk-transfer or paid action is used.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

from full_flow_runner import ensure_awake
from ui_guard import ClickVerificationError, Roi, verified_click
from instance_registry import instance_name


ROOT = os.path.dirname(os.path.abspath(__file__))

# Ratios are relative to the BlueStacks window (including its title bar).
# Air2 was inspected with Computer Use on 2026-08-11.  The friend tile is the
# first tile in row 3 of the hamburger panel; the first friend row is stable.
# Each arrow opens an item-acquired overlay, which is dismissed before the
# other arrow receives its own tap.
COORDINATES = {
    "hamburger": (0.936, 0.120),
    "friend_tile": (0.700, 0.430),
    "receive_first_row": (0.782, 0.343),
    "send_first_row": (0.816, 0.343),
    "dismiss_reward": (0.135, 0.860),
    "close": (0.852, 0.142),
}

CLICK_PAUSE = 1.2
BUTTON_CROPS = {
    "receive": (0.761, 0.315, 0.040, 0.060),
    "send": (0.795, 0.315, 0.040, 0.060),
}
FRIEND_SCREEN_MIN_YAVG = 150.0
COMPLETED_BUTTON_YAVG = 211.0
STATE_FILE = Path(__file__).with_name(".friend_state.json")


def _window_id(pid: int) -> int:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(json.loads(result.stdout)["window_id"])


def _button_yavg(pid: int, button: str) -> float:
    """Return brightness of one first-row arrow button.

    An available button is white (about 230 Y); after the exchange the same
    button is gray (about 207 Y).  The probe is deliberately tiny and does
    not inspect friend names or any account information.
    """
    window_id = _window_id(pid)
    with tempfile.NamedTemporaryFile(prefix=f"maple_friend_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), image_path], check=True)
        x, y, width, height = BUTTON_CROPS[button]
        probe = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                "-vf", f"crop=iw*{width}:ih*{height}:iw*{x}:ih*{y},signalstats,metadata=print:file=-",
                "-frames:v", "1", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in (probe.stdout + probe.stderr).splitlines():
            if "lavfi.signalstats.YAVG=" in line:
                return float(line.rsplit("=", 1)[1])
        return -1.0
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def _completed_today(pid: int) -> bool:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return state.get(instance_name(pid)) == date.today().isoformat()


def _record_completed(pid: int) -> None:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = {}
    state[instance_name(pid)] = date.today().isoformat()
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run(
    pid: int,
    *,
    force: bool = False,
    already_open: bool = False,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    if _completed_today(pid) and not force:
        return [{
            "action": "skip_friend_already_completed",
            "pid": pid,
            "date": date.today().isoformat(),
        }]
    events.append({"action": "ensure_awake", **ensure_awake(pid)})
    time.sleep(0.8)

    if not already_open:
        events.append(verified_click(
            pid, *COORDINATES["hamburger"], label="hamburger_friend",
            pause=CLICK_PAUSE, roi=Roi(0.66, 0.08, 0.32, 0.82),
        ))
        events.append(verified_click(
            pid, *COORDINATES["friend_tile"], label="friend_menu",
            pause=2.5, roi=Roi(0.18, 0.12, 0.72, 0.78),
        ))
    else:
        events.append({"action": "friend_screen_resume", "status": "already_open"})

    receive_before = _button_yavg(pid, "receive")
    send_before = _button_yavg(pid, "send")
    events.append({
        "action": "friend_buttons_probe_before",
        "receive_button_yavg": round(receive_before, 3),
        "send_button_yavg": round(send_before, 3),
        "receive_available": receive_before >= COMPLETED_BUTTON_YAVG,
        "send_available": send_before >= COMPLETED_BUTTON_YAVG,
    })
    # A disabled receive arrow can be much darker than the old gray-button
    # sample (Air1 measured 126) while the adjacent send arrow remains active.
    # The verified menu transition plus either visible row button is enough to
    # establish that the friend screen loaded.
    if max(receive_before, send_before) < FRIEND_SCREEN_MIN_YAVG:
        raise ClickVerificationError(
            "friend screen was not detected "
            f"(button probes receive={receive_before:.3f}, send={send_before:.3f})"
        )
    if (
        receive_before < COMPLETED_BUTTON_YAVG
        and send_before < COMPLETED_BUTTON_YAVG
    ):
        # The first row is already complete.  This is a safe daily rerun: do
        # not walk into another friend or press the paid bulk-transfer button.
        events.append({
            "action": "friend_exchange",
            "status": "already_completed_or_unavailable",
            "receive_button_yavg": round(receive_before, 3),
            "send_button_yavg": round(send_before, 3),
        })
    else:
        for button, label, coordinate in (
            ("receive", "friend_receive", "receive_first_row"),
            ("send", "friend_send", "send_first_row"),
        ):
            before_button = receive_before if button == "receive" else send_before
            if before_button < COMPLETED_BUTTON_YAVG:
                events.append({
                    "action": f"{label}_skip",
                    "status": "already_completed_or_unavailable",
                    "button_yavg": round(before_button, 3),
                })
                continue
            try:
                click_event = verified_click(
                    pid, *COORDINATES[coordinate], label=label,
                    pause=CLICK_PAUSE, roi=Roi(0.68, 0.20, 0.24, 0.62),
                    retries=1,
                )
            except ClickVerificationError:
                # The send action can complete without an item-acquired
                # overlay.  Its only visual change is then the tiny arrow
                # turning gray, which is below the broad ROI delta threshold.
                # Accept that case only when the button-specific brightness
                # probe proves the requested row is now disabled.
                after_button = _button_yavg(pid, button)
                if after_button >= COMPLETED_BUTTON_YAVG:
                    raise
                events.append({
                    "action": label,
                    "status": "completed_without_reward_overlay",
                    "button_yavg": round(after_button, 3),
                })
                continue
            events.append(click_event)
            # A verified large transition is the item-acquired overlay.
            events.append(verified_click(
                pid, *COORDINATES["dismiss_reward"],
                label=f"dismiss_{label}", pause=CLICK_PAUSE,
                roi=Roi(0.10, 0.18, 0.80, 0.70), retries=1,
            ))
        receive_after = _button_yavg(pid, "receive")
        send_after = _button_yavg(pid, "send")
        events.append({
            "action": "friend_exchange_verify",
            "before_receive_button_yavg": round(receive_before, 3),
            "before_send_button_yavg": round(send_before, 3),
            "after_receive_button_yavg": round(receive_after, 3),
            "after_send_button_yavg": round(send_after, 3),
            "completed": (
                receive_after < COMPLETED_BUTTON_YAVG
                and send_after < COMPLETED_BUTTON_YAVG
            ),
        })
        if (
            receive_after >= COMPLETED_BUTTON_YAVG
            or send_after >= COMPLETED_BUTTON_YAVG
        ):
            raise ClickVerificationError(
                "friend_exchange: first row did not change to completed "
                f"(receive={receive_after:.3f}, send={send_after:.3f})"
            )
        _record_completed(pid)

    events.append(verified_click(
        pid, *COORDINATES["close"], label="friend_close",
        pause=CLICK_PAUSE, roi=Roi(0.18, 0.12, 0.72, 0.78),
    ))
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument(
        "--force", action="store_true",
        help="inspect the live friend buttons even when today's state is cached",
    )
    parser.add_argument(
        "--already-open", action="store_true",
        help="resume from a visually verified open friend list",
    )
    args = parser.parse_args()
    print(json.dumps(
        {
            "pid": args.pid,
            "events": run(
                args.pid,
                force=args.force,
                already_open=args.already_open,
            ),
        },
        ensure_ascii=False,
    ))
