#!/usr/bin/env python3
"""Adaptively claim event rewards marked by circular red badges.

The event catalogue changes without a client update, so this runner does not
encode event names or row numbers.  It rescans the target VM after every
interaction, distinguishes circular red dots from rectangular NEW labels, and
clicks only orange reward-claim buttons.  Cyan shortcuts and purchases are
never clicked.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from full_flow_runner import ensure_awake
from instance_registry import instance_name
from ui_guard import Roi, verified_click


ROOT = os.path.dirname(os.path.abspath(__file__))
SCAN_WIDTH = 512
SCAN_HEIGHT = 295
EVENT_ICON = (0.790, 0.095)
EVENT_CLOSE = (0.930, 0.140)
LEFT_SCROLL_START = (0.080, 0.840)
LEFT_SCROLL_END = (0.080, 0.300)
AUDIT_ROOT = Path("/tmp/maple_event_audit")


@dataclass(frozen=True)
class Component:
    pixels: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


def _window_id(pid: int) -> int:
    result = subprocess.run(
        ["python3", f"{ROOT}/mac_gesture.py", "window-id", str(pid)],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(json.loads(result.stdout)["window_id"])


def _capture_rgb(pid: int) -> bytes:
    with tempfile.NamedTemporaryFile(prefix=f"maple_event_{pid}_", suffix=".png", delete=False) as image:
        image_path = image.name
    try:
        subprocess.run(["screencapture", "-x", "-l", str(_window_id(pid)), image_path], check=True)
        return subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", image_path,
                "-vf", f"scale={SCAN_WIDTH}:{SCAN_HEIGHT}:flags=area,format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "-",
            ],
            check=True,
            capture_output=True,
        ).stdout
    finally:
        try:
            os.unlink(image_path)
        except FileNotFoundError:
            pass


def save_audit_capture(pid: int, label: str) -> str:
    """Persist an unresolved dynamic screen for the next Codex inspection."""
    directory = AUDIT_ROOT / instance_name(pid)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"{stamp}-{label}.png"
    subprocess.run(["screencapture", "-x", "-l", str(_window_id(pid)), str(path)], check=True)
    return str(path)


def _components(rgb: bytes, predicate) -> list[Component]:
    mask = bytearray(SCAN_WIDTH * SCAN_HEIGHT)
    for index, (red, green, blue) in enumerate(zip(rgb[0::3], rgb[1::3], rgb[2::3])):
        mask[index] = predicate(red, green, blue)
    seen = bytearray(len(mask))
    output: list[Component] = []
    for start, active in enumerate(mask):
        if not active or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        xs: list[int] = []
        ys: list[int] = []
        while stack:
            point = stack.pop()
            x = point % SCAN_WIDTH
            y = point // SCAN_WIDTH
            xs.append(x)
            ys.append(y)
            for next_y in range(max(0, y - 1), min(SCAN_HEIGHT, y + 2)):
                for next_x in range(max(0, x - 1), min(SCAN_WIDTH, x + 2)):
                    adjacent = next_y * SCAN_WIDTH + next_x
                    if mask[adjacent] and not seen[adjacent]:
                        seen[adjacent] = 1
                        stack.append(adjacent)
        if len(xs) >= 3:
            output.append(Component(len(xs), min(xs), min(ys), max(xs), max(ys)))
    return output


def _red_components(rgb: bytes) -> list[Component]:
    return _components(
        rgb,
        lambda red, green, blue: red > 145 and green < 105 and blue < 125 and red > green * 1.45,
    )


def _orange_components(rgb: bytes) -> list[Component]:
    return _components(
        rgb,
        lambda red, green, blue: red > 180 and 60 < green < 195 and blue < 105 and red > green * 1.20,
    )


def _ratio_x(value: float) -> float:
    return value / SCAN_WIDTH


def _ratio_y(value: float) -> float:
    return value / SCAN_HEIGHT


def circular_badges(rgb: bytes, *, sidebar: bool) -> list[tuple[float, float]]:
    """Find compact red dots while rejecting wide rectangular NEW labels."""
    found: list[tuple[float, float]] = []
    for item in _red_components(rgb):
        center_x = (item.left + item.right) / 2
        center_y = (item.top + item.bottom) / 2
        # A notification dot is a filled compact circle.  Tiny red fragments
        # in character/event artwork previously passed the upper-bound-only
        # filter and produced taps across the banner image.
        fill = item.pixels / (item.width * item.height)
        aspect = item.width / item.height
        if (
            item.width < 5 or item.height < 5
            or item.width > 11 or item.height > 11
            or item.pixels < 18 or item.pixels > 90
            or fill < 0.42 or not 0.60 <= aspect <= 1.65
        ):
            continue
        if sidebar:
            if not (0.120 <= _ratio_x(center_x) <= 0.150 and 0.18 <= _ratio_y(center_y) <= 0.94):
                continue
        else:
            # Internal daily/achievement tabs live in the upper half.  Keep
            # away from artwork and the cumulative reward chooser on right.
            if not (0.17 <= _ratio_x(center_x) <= 0.64 and 0.27 <= _ratio_y(center_y) <= 0.40):
                continue
        found.append((_ratio_x(center_x), _ratio_y(center_y)))
    return sorted(found, key=lambda point: point[1])


def orange_claim_buttons(rgb: bytes) -> list[tuple[float, float]]:
    """Find orange mission claims with a purple progress bar on their left.

    The paired progress bar is the safety discriminator: an orange event-shop
    purchase button must not be treated as a reward merely because its color
    happens to match ``보상 받기``.
    """
    rows: list[tuple[float, float]] = []
    for item in _orange_components(rgb):
        center_x = (item.left + item.right) / 2
        center_y = (item.top + item.bottom) / 2
        # Real row claims live below the event tab/header area.  The stamp
        # event's orange ``스탬프 일괄 찍기`` control is around y=.305 and
        # was previously misclassified, causing an endless no-op loop.
        if not (0.42 <= _ratio_x(center_x) <= 0.72 and 0.40 <= _ratio_y(center_y) <= 0.94):
            continue
        if item.width < 25 or item.height < 4 or item.pixels < 70:
            continue
        row = int(round(center_y))
        purple_pixels = 0
        inspected = 0
        for y in range(max(0, row - 8), min(SCAN_HEIGHT, row + 9)):
            for x in range(int(SCAN_WIDTH * 0.20), int(SCAN_WIDTH * 0.49)):
                offset = (y * SCAN_WIDTH + x) * 3
                red, green, blue = rgb[offset:offset + 3]
                inspected += 1
                if blue > 120 and red > 70 and blue > green * 1.08 and red > green * 0.95:
                    purple_pixels += 1
        if not inspected or purple_pixels / inspected < 0.07:
            continue
        rows.append((_ratio_x(center_x), _ratio_y(center_y)))
    # Gradients sometimes split one button into two components; merge by row.
    merged: list[tuple[float, float]] = []
    for point in sorted(rows, key=lambda value: value[1]):
        if not merged or abs(point[1] - merged[-1][1]) > 0.045:
            merged.append(point)
    return merged


def body_fingerprint(rgb: bytes) -> bytes:
    """Coarse event-body fingerprint, robust to small animation changes."""
    values = bytearray()
    for y in range(int(SCAN_HEIGHT * 0.22), int(SCAN_HEIGHT * 0.88), 8):
        for x in range(int(SCAN_WIDTH * 0.16), int(SCAN_WIDTH * 0.94), 8):
            offset = (y * SCAN_WIDTH + x) * 3
            red, green, blue = rgb[offset:offset + 3]
            values.append(((red + green + blue) // 3) // 24)
    return bytes(values)


def fingerprint_delta(left: bytes, right: bytes) -> float:
    if len(left) != len(right) or not left:
        return 1.0
    return sum(abs(a - b) for a, b in zip(left, right)) / (10.0 * len(left))


def click(pid: int, point: tuple[float, float], label: str, pause: float = 1.2) -> dict[str, object]:
    result = subprocess.run(
        [
            "python3", f"{ROOT}/mac_gesture.py", "click", str(pid),
            "--x-ratio", f"{point[0]:.4f}", "--y-ratio", f"{point[1]:.4f}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(pause)
    return {"action": label, **json.loads(result.stdout)}


def drag_sidebar(pid: int) -> dict[str, object]:
    result = subprocess.run(
        [
            "python3", f"{ROOT}/mac_gesture.py", "drag", str(pid),
            "--start-x-ratio", str(LEFT_SCROLL_START[0]),
            "--start-y-ratio", str(LEFT_SCROLL_START[1]),
            "--end-x-ratio", str(LEFT_SCROLL_END[0]),
            "--end-y-ratio", str(LEFT_SCROLL_END[1]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(1.2)
    return {"action": "scroll_event_sidebar", **json.loads(result.stdout)}


def claim_current_event(pid: int, events: list[dict[str, object]], max_claims: int) -> int:
    claims = 0
    visited_internal: set[tuple[int, int]] = set()
    stalled_buttons: set[tuple[int, int]] = set()
    for _ in range(max_claims * 3 + 8):
        rgb = _capture_rgb(pid)
        buttons = orange_claim_buttons(rgb)
        if buttons:
            point = buttons[0]
            key = (round(point[0] * 100), round(point[1] * 100))
            if key in stalled_buttons:
                events.append({
                    "action": "event_claim_stalled_skip",
                    "button": key,
                    "audit_screenshot": save_audit_capture(pid, "stalled-claim"),
                })
                return claims
            events.append(click(pid, point, "event_reward_claim", pause=3.5))
            # Reward animation ignores early dismissal clicks.  One late click
            # on blank content closes the result without touching a button.
            events.append(click(pid, (0.780, 0.720), "dismiss_event_reward", pause=1.4))
            after_rgb = _capture_rgb(pid)
            remaining_keys = {
                (round(item[0] * 100), round(item[1] * 100))
                for item in orange_claim_buttons(after_rgb)
            }
            if key in remaining_keys:
                stalled_buttons.add(key)
                events.append({
                    "action": "event_claim_no_state_change",
                    "button": key,
                    "audit_screenshot": save_audit_capture(pid, "claim-no-change"),
                })
                continue
            claims += 1
            if claims >= max_claims:
                raise RuntimeError(f"event reward claim safety limit reached: {max_claims}")
            continue

        internal = circular_badges(rgb, sidebar=False)
        next_badge = next(
            (point for point in internal if (round(point[0] * 100), round(point[1] * 100)) not in visited_internal),
            None,
        )
        if next_badge is None:
            return claims
        visited_internal.add((round(next_badge[0] * 100), round(next_badge[1] * 100)))
        events.append(click(pid, next_badge, "event_internal_badge"))
    return claims


def run(pid: int, *, modal_open: bool = False, max_claims: int = 80, max_scrolls: int = 10) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    if not modal_open:
        events.append(ensure_awake(pid))
        events.append(verified_click(
            pid,
            *EVENT_ICON,
            label="open_event_modal",
            pause=1.8,
            roi=Roi(0.00, 0.08, 0.96, 0.86),
            min_delta=0.012,
            noise_multiplier=0.0,
            retries=1,
        ))

    # Do not claim the default event merely because it happens to contain an
    # orange button.  The user-defined entry condition is a circular red dot.
    total_claims = 0
    unchanged_scrolls = 0
    previous_sidebar = b""
    seen_bodies: list[bytes] = []
    no_new_viewports = 0
    for scroll_index in range(max_scrolls + 1):
        ignored_in_viewport: set[int] = set()
        viewport_new_event = False
        while True:
            rgb = _capture_rgb(pid)
            sidebar_badges = circular_badges(rgb, sidebar=True)
            new_badge = next(
                (point for point in sidebar_badges if round(point[1] * 100) not in ignored_in_viewport),
                None,
            )
            if new_badge is None:
                break
            badge_key = round(new_badge[1] * 100)
            ignored_in_viewport.add(badge_key)
            events.append(click(pid, (0.080, new_badge[1]), "event_sidebar_badge", pause=1.5))
            selected_rgb = _capture_rgb(pid)
            fingerprint = body_fingerprint(selected_rgb)
            if any(fingerprint_delta(fingerprint, seen) < 0.055 for seen in seen_bodies):
                events.append({
                    "action": "event_duplicate_skip",
                    "sidebar_y_ratio": round(new_badge[1], 4),
                })
                continue
            seen_bodies.append(fingerprint)
            viewport_new_event = True
            claims_before = total_claims
            total_claims += claim_current_event(pid, events, max_claims - total_claims)
            if total_claims == claims_before:
                # Some dots represent a permanent-choice cumulative reward.
                # Record it for Codex/user review, but never guess the choice
                # or repeatedly re-enter the same event.
                events.append({
                    "action": "event_badge_unresolved",
                    "status": "manual_choice_or_non_claim_action",
                    "sidebar_y_ratio": round(new_badge[1], 4),
                    "audit_screenshot": save_audit_capture(pid, "unresolved"),
                })

        if viewport_new_event:
            no_new_viewports = 0
        else:
            no_new_viewports += 1
        if no_new_viewports >= 2:
            events.append({"action": "event_scroll_stop", "reason": "no_new_event_bodies"})
            break

        if scroll_index >= max_scrolls:
            break
        rgb = _capture_rgb(pid)
        sidebar_signature = bytes(
            channel
            for row in range(int(SCAN_HEIGHT * 0.18), int(SCAN_HEIGHT * 0.94), 4)
            for col in range(0, int(SCAN_WIDTH * 0.16), 4)
            for channel in rgb[(row * SCAN_WIDTH + col) * 3:(row * SCAN_WIDTH + col) * 3 + 3]
        )
        if sidebar_signature == previous_sidebar:
            unchanged_scrolls += 1
        else:
            unchanged_scrolls = 0
        if unchanged_scrolls >= 1:
            break
        previous_sidebar = sidebar_signature
        events.append(drag_sidebar(pid))

    events.append(verified_click(
        pid, *EVENT_CLOSE, label="close_event_modal", pause=1.5,
        roi=Roi(0.00, 0.08, 0.96, 0.86),
        min_delta=0.012, noise_multiplier=0.0, retries=0,
    ))
    events.append({
        "action": "event_scan_complete",
        "claims": total_claims,
        "final_screenshot": save_audit_capture(pid, "final"),
    })
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--modal-open", action="store_true")
    parser.add_argument("--max-claims", type=int, default=80)
    parser.add_argument("--max-scrolls", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps({"pid": args.pid, "events": run(
        args.pid,
        modal_open=args.modal_open,
        max_claims=args.max_claims,
        max_scrolls=args.max_scrolls,
    )}, ensure_ascii=False))
