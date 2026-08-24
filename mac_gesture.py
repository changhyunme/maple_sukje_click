#!/usr/bin/env python3
"""Target a BlueStacks process window and send recorded macOS gestures."""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from dataclasses import asdict, dataclass

from activate_instance import activate_process
from window_control import move_window


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


@dataclass(frozen=True)
class WindowBounds:
    x: float
    y: float
    width: float
    height: float


APPLICATION_SERVICES = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
CORE_FOUNDATION = ctypes.CDLL(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
CORE_GRAPHICS = ctypes.CDLL(
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
)

APPLICATION_SERVICES.CGWindowListCopyWindowInfo.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint32,
]
APPLICATION_SERVICES.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
APPLICATION_SERVICES.CGRectMakeWithDictionaryRepresentation.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(CGRect),
]
APPLICATION_SERVICES.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool

CORE_FOUNDATION.CFArrayGetCount.argtypes = [ctypes.c_void_p]
CORE_FOUNDATION.CFArrayGetCount.restype = ctypes.c_long
CORE_FOUNDATION.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
CORE_FOUNDATION.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
CORE_FOUNDATION.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
CORE_FOUNDATION.CFDictionaryGetValue.restype = ctypes.c_void_p
CORE_FOUNDATION.CFNumberGetValue.argtypes = [
    ctypes.c_void_p,
    ctypes.c_long,
    ctypes.c_void_p,
]
CORE_FOUNDATION.CFNumberGetValue.restype = ctypes.c_bool
CORE_FOUNDATION.CFRelease.argtypes = [ctypes.c_void_p]

K_CG_WINDOW_OWNER_PID = ctypes.c_void_p.in_dll(
    APPLICATION_SERVICES, "kCGWindowOwnerPID"
).value
K_CG_WINDOW_NUMBER = ctypes.c_void_p.in_dll(
    APPLICATION_SERVICES, "kCGWindowNumber"
).value
K_CG_WINDOW_LAYER = ctypes.c_void_p.in_dll(
    APPLICATION_SERVICES, "kCGWindowLayer"
).value
K_CG_WINDOW_BOUNDS = ctypes.c_void_p.in_dll(
    APPLICATION_SERVICES, "kCGWindowBounds"
).value

K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY = 1
K_CF_NUMBER_INT_TYPE = 9
K_CG_HID_EVENT_TAP = 0
K_CG_EVENT_LEFT_MOUSE_DOWN = 1
K_CG_EVENT_LEFT_MOUSE_UP = 2
K_CG_EVENT_MOUSE_MOVED = 5
K_CG_EVENT_LEFT_MOUSE_DRAGGED = 6
K_CG_MOUSE_BUTTON_LEFT = 0

CORE_GRAPHICS.CGGetActiveDisplayList.argtypes = [
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(ctypes.c_uint32),
]
CORE_GRAPHICS.CGGetActiveDisplayList.restype = ctypes.c_int32
CORE_GRAPHICS.CGDisplayBounds.argtypes = [ctypes.c_uint32]
CORE_GRAPHICS.CGDisplayBounds.restype = CGRect


def _dictionary_int(dictionary: int, key: int) -> int | None:
    number = CORE_FOUNDATION.CFDictionaryGetValue(dictionary, key)
    if not number:
        return None
    value = ctypes.c_int()
    if not CORE_FOUNDATION.CFNumberGetValue(
        number, K_CF_NUMBER_INT_TYPE, ctypes.byref(value)
    ):
        return None
    return value.value


def find_window_bounds(pid: int) -> WindowBounds:
    window_info = APPLICATION_SERVICES.CGWindowListCopyWindowInfo(
        K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY, 0
    )
    if not window_info:
        raise RuntimeError("CGWindowListCopyWindowInfo returned no data")

    matches: list[WindowBounds] = []
    try:
        count = CORE_FOUNDATION.CFArrayGetCount(window_info)
        for index in range(count):
            item = CORE_FOUNDATION.CFArrayGetValueAtIndex(window_info, index)
            if _dictionary_int(item, K_CG_WINDOW_OWNER_PID) != pid:
                continue
            if _dictionary_int(item, K_CG_WINDOW_LAYER) != 0:
                continue

            bounds_dictionary = CORE_FOUNDATION.CFDictionaryGetValue(
                item, K_CG_WINDOW_BOUNDS
            )
            bounds = CGRect()
            if bounds_dictionary and APPLICATION_SERVICES.CGRectMakeWithDictionaryRepresentation(
                bounds_dictionary, ctypes.byref(bounds)
            ):
                matches.append(
                    WindowBounds(
                        x=bounds.origin.x,
                        y=bounds.origin.y,
                        width=bounds.size.width,
                        height=bounds.size.height,
                    )
                )
    finally:
        CORE_FOUNDATION.CFRelease(window_info)

    if not matches:
        raise RuntimeError(f"no on-screen layer-0 window for PID {pid}")
    return max(matches, key=lambda item: item.width * item.height)


def find_window_id(pid: int) -> int:
    """Return the on-screen layer-0 window number for a BlueStacks PID."""
    window_info = APPLICATION_SERVICES.CGWindowListCopyWindowInfo(
        K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY, 0
    )
    if not window_info:
        raise RuntimeError("CGWindowListCopyWindowInfo returned no data")

    matches: list[tuple[int, float]] = []
    try:
        count = CORE_FOUNDATION.CFArrayGetCount(window_info)
        for index in range(count):
            item = CORE_FOUNDATION.CFArrayGetValueAtIndex(window_info, index)
            if _dictionary_int(item, K_CG_WINDOW_OWNER_PID) != pid:
                continue
            if _dictionary_int(item, K_CG_WINDOW_LAYER) != 0:
                continue
            window_id = _dictionary_int(item, K_CG_WINDOW_NUMBER)
            if window_id is None:
                continue
            bounds_dictionary = CORE_FOUNDATION.CFDictionaryGetValue(
                item, K_CG_WINDOW_BOUNDS
            )
            bounds = CGRect()
            if bounds_dictionary and APPLICATION_SERVICES.CGRectMakeWithDictionaryRepresentation(
                bounds_dictionary, ctypes.byref(bounds)
            ):
                matches.append((window_id, bounds.size.width * bounds.size.height))
    finally:
        CORE_FOUNDATION.CFRelease(window_info)

    if not matches:
        raise RuntimeError(f"no on-screen layer-0 window for PID {pid}")
    return max(matches, key=lambda item: item[1])[0]


def _intersects_active_display(bounds: WindowBounds) -> bool:
    display_ids = (ctypes.c_uint32 * 16)()
    display_count = ctypes.c_uint32()
    error = CORE_GRAPHICS.CGGetActiveDisplayList(
        16, display_ids, ctypes.byref(display_count)
    )
    if error != 0:
        return False
    for index in range(display_count.value):
        display = CORE_GRAPHICS.CGDisplayBounds(display_ids[index])
        if (
            bounds.x < display.origin.x + display.size.width
            and bounds.x + bounds.width > display.origin.x
            and bounds.y < display.origin.y + display.size.height
            and bounds.y + bounds.height > display.origin.y
        ):
            return True
    return False


def find_clickable_window_bounds(pid: int) -> WindowBounds:
    """Return bounds, recovering only windows outside every active display."""
    bounds = find_window_bounds(pid)
    if not _intersects_active_display(bounds):
        move_window(pid, 50.0, 50.0)
        time.sleep(0.3)
        bounds = find_window_bounds(pid)
    return bounds


APPLICATION_SERVICES.CGEventCreateMouseEvent.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint32,
    CGPoint,
    ctypes.c_uint32,
]
APPLICATION_SERVICES.CGEventCreateMouseEvent.restype = ctypes.c_void_p
APPLICATION_SERVICES.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
APPLICATION_SERVICES.CGEventSetLocation.argtypes = [ctypes.c_void_p, CGPoint]

def _post_mouse(event_type: int, point: CGPoint) -> None:
    event = APPLICATION_SERVICES.CGEventCreateMouseEvent(
        None, event_type, point, K_CG_MOUSE_BUTTON_LEFT
    )
    if not event:
        raise RuntimeError("CGEventCreateMouseEvent failed")
    try:
        APPLICATION_SERVICES.CGEventPost(K_CG_HID_EVENT_TAP, event)
    finally:
        CORE_FOUNDATION.CFRelease(event)


def click_point(point: CGPoint) -> None:
    _post_mouse(K_CG_EVENT_MOUSE_MOVED, point)
    time.sleep(0.05)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_DOWN, point)
    # BlueStacks intermittently drops a stationary down/up pair when its
    # window lives on the display above the primary display (negative global
    # Y coordinates).  A sub-click-size dragged event makes Android receive
    # the tap reliably while staying far below the game's drag threshold.
    # A single dragged event is still occasionally coalesced away by the
    # emulator.  Emit a short four-step 2 px motion, matching the event shape
    # that proved reliable in live Air reward dialogs while remaining well
    # below any in-game swipe threshold.
    jitter_distance = 2.0
    for step in range(1, 5):
        jitter = CGPoint(point.x + jitter_distance * step / 4, point.y)
        _post_mouse(K_CG_EVENT_LEFT_MOUSE_DRAGGED, jitter)
        time.sleep(0.02)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, jitter)


def drag_left(
    start: CGPoint,
    distance: float = 200,
    duration: float = 0.4,
    steps: int = 20,
) -> CGPoint:
    end = CGPoint(start.x - distance, start.y)
    _post_mouse(K_CG_EVENT_MOUSE_MOVED, start)
    time.sleep(0.05)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_DOWN, start)

    for step in range(1, steps + 1):
        progress = step / steps
        point = CGPoint(start.x - distance * progress, start.y)
        _post_mouse(K_CG_EVENT_LEFT_MOUSE_DRAGGED, point)
        time.sleep(duration / steps)

    _post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, end)
    return end


def drag_ratio(
    pid: int,
    start_x_ratio: float,
    start_y_ratio: float,
    end_x_ratio: float,
    end_y_ratio: float,
    duration: float = 0.6,
    steps: int = 24,
) -> dict[str, object]:
    """Drag between two window-relative positions on one exact instance."""
    if not activate_process(pid):
        raise RuntimeError(f"could not activate PID {pid}")
    # Each BlueStacks VM is a separate macOS process.  When focus moves from
    # one VM to another, 150 ms was not long enough and the first gesture was
    # consumed only to activate the window.  Wait for AppKit focus to settle
    # before posting the actual game input.
    time.sleep(0.55)
    bounds = find_clickable_window_bounds(pid)
    start = CGPoint(
        bounds.x + bounds.width * start_x_ratio,
        bounds.y + bounds.height * start_y_ratio,
    )
    end = CGPoint(
        bounds.x + bounds.width * end_x_ratio,
        bounds.y + bounds.height * end_y_ratio,
    )
    _post_mouse(K_CG_EVENT_MOUSE_MOVED, start)
    time.sleep(0.05)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_DOWN, start)
    for step in range(1, steps + 1):
        progress = step / steps
        point = CGPoint(
            start.x + (end.x - start.x) * progress,
            start.y + (end.y - start.y) * progress,
        )
        _post_mouse(K_CG_EVENT_LEFT_MOUSE_DRAGGED, point)
        time.sleep(duration / steps)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, end)
    return {
        "pid": pid,
        "activated": True,
        "window": asdict(bounds),
        "start_ratio": {"x": start_x_ratio, "y": start_y_ratio},
        "end_ratio": {"x": end_x_ratio, "y": end_y_ratio},
        "duration_seconds": duration,
        "steps": steps,
    }


def unlock(
    pid: int,
    lock_x_ratio: float,
    lock_y_ratio: float,
    drag_distance: float,
) -> dict[str, object]:
    if not activate_process(pid):
        raise RuntimeError(f"could not activate PID {pid}")
    time.sleep(0.55)

    bounds = find_clickable_window_bounds(pid)
    activation_point = CGPoint(
        bounds.x + bounds.width / 2,
        bounds.y + bounds.height / 2,
    )
    click_point(activation_point)
    time.sleep(0.2)

    lock_x = bounds.width * lock_x_ratio
    lock_y = bounds.height * lock_y_ratio
    lock_point = CGPoint(bounds.x + lock_x, bounds.y + lock_y)
    end_point = drag_left(lock_point, distance=drag_distance)
    return {
        "pid": pid,
        "activated": True,
        "window": asdict(bounds),
        "activation_click": {
            "relative": {"x": bounds.width / 2, "y": bounds.height / 2},
            "global": {"x": activation_point.x, "y": activation_point.y},
        },
        "lock_position": {
            "ratio": {"x": lock_x_ratio, "y": lock_y_ratio},
            "relative": {"x": lock_x, "y": lock_y},
            "global": {"x": lock_point.x, "y": lock_point.y},
        },
        "drag": {
            "direction": "left",
            "distance": drag_distance,
            "start_global": {"x": lock_point.x, "y": lock_point.y},
            "end_global": {"x": end_point.x, "y": end_point.y},
            "duration_seconds": 0.4,
            "steps": 20,
        },
    }


def click_ratio(pid: int, x_ratio: float, y_ratio: float) -> dict[str, object]:
    if not activate_process(pid):
        raise RuntimeError(f"could not activate PID {pid}")
    time.sleep(0.55)
    bounds = find_clickable_window_bounds(pid)
    point = CGPoint(
        bounds.x + bounds.width * x_ratio,
        bounds.y + bounds.height * y_ratio,
    )
    click_point(point)
    return {
        "pid": pid,
        "activated": True,
        "window": asdict(bounds),
        "position_ratio": {"x": x_ratio, "y": y_ratio},
        "position_global": {"x": point.x, "y": point.y},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("pid", type=int)

    window_id_parser = subparsers.add_parser("window-id")
    window_id_parser.add_argument("pid", type=int)

    unlock_parser = subparsers.add_parser("unlock")
    unlock_parser.add_argument("pid", type=int)
    unlock_parser.add_argument("--lock-x-ratio", type=float, default=530 / 1093)
    unlock_parser.add_argument("--lock-y-ratio", type=float, default=504 / 629)
    unlock_parser.add_argument("--drag-distance", type=float, default=200)

    click_parser = subparsers.add_parser("click")
    click_parser.add_argument("pid", type=int)
    click_parser.add_argument("--x-ratio", type=float, required=True)
    click_parser.add_argument("--y-ratio", type=float, required=True)

    drag_parser = subparsers.add_parser("drag")
    drag_parser.add_argument("pid", type=int)
    drag_parser.add_argument("--start-x-ratio", type=float, required=True)
    drag_parser.add_argument("--start-y-ratio", type=float, required=True)
    drag_parser.add_argument("--end-x-ratio", type=float, required=True)
    drag_parser.add_argument("--end-y-ratio", type=float, required=True)
    drag_parser.add_argument("--duration", type=float, default=0.6)

    args = parser.parse_args()
    if args.command == "inspect":
        result = {"pid": args.pid, "window": asdict(find_window_bounds(args.pid))}
    elif args.command == "window-id":
        result = {"pid": args.pid, "window_id": find_window_id(args.pid)}
    elif args.command == "unlock":
        result = unlock(
            args.pid,
            args.lock_x_ratio,
            args.lock_y_ratio,
            args.drag_distance,
        )
    elif args.command == "click":
        result = click_ratio(args.pid, args.x_ratio, args.y_ratio)
    else:
        result = drag_ratio(
            args.pid,
            args.start_x_ratio,
            args.start_y_ratio,
            args.end_x_ratio,
            args.end_y_ratio,
            args.duration,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
