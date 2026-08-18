#!/usr/bin/env python3
"""Run the fourth recorded action: AD rewards, boosters and repeat hunting."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from ui_guard import Roi, verified_click
from instance_registry import instance_name
from full_flow_runner import ensure_awake


ROOT = "/Users/gorgeous/utils/maple_clicker"
STATE_FILE = Path(__file__).with_name(".booster_state.json")


def click(pid: int, x: float, y: float, pause: float = 1.0, label: str = "click") -> dict[str, object]:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
         "--x-ratio", f"{x:.3f}", "--y-ratio", f"{y:.3f}"],
        check=True, capture_output=True, text=True,
    )
    if pause:
        time.sleep(pause)
    payload = json.loads(result.stdout)
    return {"action": label, **payload}


COORDINATES = {
    "free_icon": (0.039, 0.924),
    # The fast-hunt overlay opens on the left tab.  Accumulated free claims
    # temporarily turn this tab into ``무료`` and add a green FREE badge.  As
    # soon as those claims are exhausted it becomes the paid 500-gem tab, so
    # the badge must be checked before every click.
    "gem_purchase_claim": (0.500, 0.880),
    "free_claim": (0.500, 0.880),
    # The 2026-08-14 modal is shorter: tab centres moved to y=.65.
    # The former y=.555 now lands in the reward artwork and does nothing.
    "gem_purchase_tab": (0.370, 0.650),
    "free_bonus_tab": (0.640, 0.650),
    "free_close": (0.685, 0.167),
    "leaf_icon": (0.126, 0.925),
    # The daily ad booster is below the ordinary 30%/50% boosters.  Scroll the
    # list once, then use only this third row; the top rows must never be
    # consumed by the homework flow.
    "burning_booster": (0.640, 0.720),
    # Burning Field use dialog: select all five, then confirm.
    # The refreshed booster-use dialog moved Max and Use upward.
    "burning_max": (0.665, 0.610),
    "burning_confirm": (0.500, 0.730),
    "close_overlay": (0.910, 0.100),
    "repeat": (0.220, 0.870),
    # Dialog confirm button is lower than the claim-dialog confirm used by action 3.
    "confirm": (0.556, 0.700),
    "dismiss": (0.135, 0.860),
}

# Air 2 has a different fast-hunt default tab and a 1–4 booster dialog, in
# addition to its shifted modal coordinates. Keep that verified profile local
# to the instance instead of forcing a rerun to reuse Air's coordinates.
INSTANCE_OVERRIDES = {
    "Air2": {
        # Air2's fast-hunt modal is shifted slightly down.
        "gem_purchase_tab": (0.370, 0.575),
        "free_bonus_tab": (0.622, 0.575),
        "free_claim": (0.485, 0.895),
        "gem_purchase_claim": (0.485, 0.895),
        "dismiss": (0.485, 0.763),
        "free_close": (0.685, 0.167),
        "booster_close": (0.720, 0.200),
        "burning_booster": (0.646, 0.720),
        "burning_max": (0.660, 0.610),
        "burning_confirm": (0.485, 0.730),
        "repeat": (0.213, 0.877),
        "confirm": (0.567, 0.710),
    },
}

def coordinates_for(pid: int) -> dict[str, tuple[float, float]]:
    coords = dict(COORDINATES)
    override = INSTANCE_OVERRIDES.get(instance_name(pid), {})
    coords.update(override)
    coords.setdefault("free_close", coords["close_overlay"])
    coords.setdefault("booster_close", coords["close_overlay"])
    return coords


def _load_state() -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _step_completed(pid: int, step: str) -> bool:
    entry = _load_state().get(instance_name(pid), {})
    return entry.get("date") == date.today().isoformat() and step in entry.get("steps", [])


def _record_step(pid: int, step: str) -> None:
    state = _load_state()
    key = instance_name(pid)
    today = date.today().isoformat()
    entry = state.get(key, {})
    steps = list(entry.get("steps", [])) if entry.get("date") == today else []
    if step not in steps:
        steps.append(step)
    state[key] = {"date": today, "steps": steps}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _active_color_signal(pid: int, crop: tuple[float, float, float, float]) -> float:
    """Return the colored-fill ratio for a normalized window crop."""
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(result.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(
        prefix=f"maple_booster_{pid}_", suffix=".png", delete=False,
    ) as image:
        path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), path], check=True)
        x, y, width, height = crop
        rgb = subprocess.run(
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
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    if not pixels:
        return -1.0
    return sum(
        max(red, green, blue) > 125
        and max(red, green, blue) - min(red, green, blue) > 45
        for red, green, blue in pixels
    ) / len(pixels)


def _green_free_badge_signal(pid: int) -> float:
    """Detect only the green FREE badge on the left fast-hunt tab.

    The paid 500-gem state has no badge.  This guard is intentionally more
    specific than the generic colored-button detector so a force audit can
    never continue into the paid state.
    """
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True, capture_output=True, text=True,
    )
    window_id = int(json.loads(result.stdout)["window_id"])
    with tempfile.NamedTemporaryFile(
        prefix=f"maple_free_badge_{pid}_", suffix=".png", delete=False,
    ) as image:
        path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(window_id), path], check=True)
        rgb = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
                "-vf", "crop=iw*0.050:ih*0.060:iw*0.370:ih*0.600,format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True, capture_output=True,
        ).stdout
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    pixels = list(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    if not pixels:
        return -1.0
    return sum(
        green > 110 and green > red * 1.20 and green > blue * 1.10
        for red, green, blue in pixels
    ) / len(pixels)


def guarded_click(
    pid: int,
    point: tuple[float, float],
    *,
    label: str,
    roi: Roi,
    pause: float = 1.0,
    min_delta: float = 0.010,
    retries: int = 0,
    allow_no_change: bool = False,
) -> dict[str, object]:
    """Fail closed when a coordinate does not change the expected UI.

    Reward/use confirmations deliberately use zero retries: a second click can
    consume another paid gem reward or land on an unrelated control after the
    first transition.
    """
    return verified_click(
        pid,
        *point,
        label=label,
        pause=pause,
        roi=roi,
        min_delta=min_delta,
        noise_multiplier=0.0,
        retries=retries,
        allow_no_change=allow_no_change,
    )


def scroll_to_daily_ad_booster(pid: int) -> dict[str, object]:
    result = subprocess.run(
        [
            "python3", f"{ROOT}/mac_gesture.py", "drag", str(pid),
            "--start-x-ratio", "0.580", "--start-y-ratio", "0.800",
            "--end-x-ratio", "0.580", "--end-y-ratio", "0.380",
            "--duration", "0.8",
        ],
        check=True, capture_output=True, text=True,
    )
    time.sleep(1.2)
    return {"action": "scroll_to_daily_ad_booster", **json.loads(result.stdout)}


def run(
    pid: int,
    wait_seconds: float = 300.0,
    *,
    force_verify: bool = False,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    c = coordinates_for(pid)
    # Recovery runs invoke this script directly, sometimes after another VM
    # has occupied the full five-minute wait.  Wake this instance before any
    # coordinate click so the first tap cannot land on the sleep overlay.
    events.append({"action": "ensure_awake", **ensure_awake(pid)})
    time.sleep(0.8)

    fast_hunt_steps = ("gem_purchase", "free_reward")
    if force_verify or not all(_step_completed(pid, step) for step in fast_hunt_steps):
        events.append(guarded_click(
            pid, c["free_icon"], label="free_icon",
            roi=Roi(0.20, 0.15, 0.58, 0.78), retries=1,
        ))

        if force_verify or not _step_completed(pid, "gem_purchase"):
            # Select the tab explicitly on every VM; never infer it from the
            # tab that happened to be active when the modal opened.
            events.append(guarded_click(
                pid, c["gem_purchase_tab"], label="gem_purchase_tab",
                roi=Roi(0.28, 0.52, 0.44, 0.32), allow_no_change=True,
            ))
            for claim_index in range(1, 4):
                free_signal = _green_free_badge_signal(pid)
                events.append({
                    "action": f"gem_purchase_free_probe_{claim_index}",
                    "green_free_badge_signal": round(free_signal, 5),
                    "available": free_signal >= 0.025,
                })
                if free_signal < 0.025:
                    break
                events.append(guarded_click(
                    pid, c["gem_purchase_claim"],
                    label=f"gem_purchase_free_claim_{claim_index}",
                    roi=Roi(0.20, 0.20, 0.60, 0.70),
                ))
                events.append(guarded_click(
                    pid, c["dismiss"],
                    label=f"dismiss_gem_reward_{claim_index}",
                    roi=Roi(0.20, 0.20, 0.60, 0.70), pause=0.8,
                ))
            _record_step(pid, "gem_purchase")

        if force_verify or not _step_completed(pid, "free_reward"):
            events.append(guarded_click(
                pid, c["free_bonus_tab"], label="free_bonus_tab",
                roi=Roi(0.28, 0.52, 0.44, 0.32), allow_no_change=True,
            ))
            for claim_index in range(1, 4):
                free_bonus_signal = _active_color_signal(
                    pid, (0.425, 0.840, 0.150, 0.075),
                )
                free_bonus_available = free_bonus_signal >= 0.075
                events.append({
                    "action": f"free_bonus_probe_{claim_index}",
                    "active_color_signal": round(free_bonus_signal, 5),
                    "available": free_bonus_available,
                })
                if not free_bonus_available:
                    break
                events.append(guarded_click(
                    pid, c["free_claim"],
                    label=f"free_bonus_claim_{claim_index}",
                    roi=Roi(0.20, 0.20, 0.60, 0.70),
                ))
                events.append(guarded_click(
                    pid, c["dismiss"],
                    label=f"dismiss_bonus_reward_{claim_index}",
                    roi=Roi(0.20, 0.20, 0.60, 0.70), pause=0.8,
                ))
            _record_step(pid, "free_reward")

        events.append(guarded_click(
            pid, c["free_close"], label="close_free_overlay",
            roi=Roi(0.20, 0.15, 0.58, 0.78),
        ))
    else:
        events.append({"action": "fast_hunt_rewards_skip", "status": "completed_today"})

    if force_verify or not _step_completed(pid, "burning_booster"):
        events.append(guarded_click(
            pid, c["leaf_icon"], label="leaf_icon",
            roi=Roi(0.20, 0.15, 0.65, 0.75), retries=1,
        ))
        events.append(scroll_to_daily_ad_booster(pid))
        use_signal = _active_color_signal(pid, (0.595, 0.680, 0.105, 0.075))
        use_available = use_signal >= 0.075
        events.append({
            "action": "burning_field_booster_probe",
            "active_color_signal": round(use_signal, 5),
            "available": use_available,
        })
        if use_available:
            events.append(guarded_click(
                pid, c["burning_booster"], label="burning_field_booster",
                roi=Roi(0.30, 0.25, 0.42, 0.56), pause=1.4,
            ))
            # When only one booster is owned, the quantity dialog opens with
            # 1/1 already selected.  Pressing Max is then a legitimate no-op.
            # Some Air2 layouts consume the lone item immediately instead, so
            # detect the green dialog confirmation before clicking through it.
            confirm_crop = (0.435, 0.695, 0.130, 0.070)
            dialog_signal = _active_color_signal(pid, confirm_crop)
            remaining_use_signal = _active_color_signal(
                pid, (0.595, 0.680, 0.105, 0.075),
            )
            events.append({
                "action": "burning_field_dialog_probe",
                "confirm_signal": round(dialog_signal, 5),
                "remaining_use_signal": round(remaining_use_signal, 5),
            })
            if dialog_signal >= 0.075:
                events.append(guarded_click(
                    pid, c["burning_max"], label="burning_field_booster_max",
                    roi=Roi(0.42, 0.48, 0.26, 0.30), min_delta=0.002,
                    retries=0, allow_no_change=True,
                ))
                events.append(guarded_click(
                    pid, c["burning_confirm"], label="burning_field_booster_confirm",
                    roi=Roi(0.30, 0.25, 0.42, 0.56),
                ))
            elif remaining_use_signal < 0.075:
                events.append({
                    "action": "burning_field_booster_consumed_without_dialog",
                    "status": "completed",
                })
            else:
                raise RuntimeError(
                    "booster use did not open the quantity dialog or consume the item"
                )
        else:
            events.append({
                "action": "burning_field_booster_skip",
                "status": "used_or_unavailable",
            })
        _record_step(pid, "burning_booster")
        events.append(guarded_click(
            pid, c["booster_close"], label="close_booster_overlay",
            roi=Roi(0.20, 0.15, 0.65, 0.75),
        ))
    else:
        events.append({"action": "burning_booster_skip", "status": "completed_today"})

    if not force_verify and not _step_completed(pid, "repeat_hunt"):
        events.append(guarded_click(
            pid, c["repeat"], label="repeat_button",
            roi=Roi(0.28, 0.25, 0.46, 0.52),
        ))
        events.append(guarded_click(
            pid, c["confirm"], label="repeat_confirm",
            roi=Roi(0.28, 0.25, 0.46, 0.52),
        ))
        _record_step(pid, "repeat_hunt")
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        events.append({"action": "repeat_wait", "duration_seconds": wait_seconds})
    elif not force_verify:
        events.append({"action": "repeat_hunt_skip", "status": "completed_today"})
    else:
        events.append({
            "action": "repeat_hunt_skip",
            "status": "force verification does not restart the timed hunt",
        })
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--wait-seconds", type=float, default=300.0)
    parser.add_argument(
        "--force-verify", action="store_true",
        help="inspect live free rewards and booster state despite today's cache",
    )
    args = parser.parse_args()
    print(json.dumps({
        "pid": args.pid,
        "events": run(args.pid, args.wait_seconds, force_verify=args.force_verify),
    }, ensure_ascii=False))
