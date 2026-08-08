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


def find_clickable_window_bounds(pid: int) -> WindowBounds:
    """Return bounds after bringing offscreen windows into the visible desktop."""
    bounds = find_window_bounds(pid)
    if bounds.y < 0:
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
    time.sleep(0.05)
    _post_mouse(K_CG_EVENT_LEFT_MOUSE_UP, point)


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


def unlock(
    pid: int,
    lock_x_ratio: float,
    lock_y_ratio: float,
    drag_distance: float,
) -> dict[str, object]:
    if not activate_process(pid):
        raise RuntimeError(f"could not activate PID {pid}")
    time.sleep(0.2)

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
    time.sleep(0.15)
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

    unlock_parser = subparsers.add_parser("unlock")
    unlock_parser.add_argument("pid", type=int)
    unlock_parser.add_argument("--lock-x-ratio", type=float, default=530 / 1093)
    unlock_parser.add_argument("--lock-y-ratio", type=float, default=504 / 629)
    unlock_parser.add_argument("--drag-distance", type=float, default=200)

    click_parser = subparsers.add_parser("click")
    click_parser.add_argument("pid", type=int)
    click_parser.add_argument("--x-ratio", type=float, required=True)
    click_parser.add_argument("--y-ratio", type=float, required=True)

    args = parser.parse_args()
    if args.command == "inspect":
        result = {"pid": args.pid, "window": asdict(find_window_bounds(args.pid))}
    elif args.command == "unlock":
        result = unlock(
            args.pid,
            args.lock_x_ratio,
            args.lock_y_ratio,
            args.drag_distance,
        )
    else:
        result = click_ratio(args.pid, args.x_ratio, args.y_ratio)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
