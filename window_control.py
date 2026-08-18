#!/usr/bin/env python3
"""Move a specific BlueStacks window into the visible desktop area.

BlueStacks can leave an instance window on a negative-y virtual desktop.  The
recorded gesture coordinates are relative to the window, but CGEvent still
needs a visible global position, so this helper moves only the requested PID.
"""

from __future__ import annotations

import argparse
import ctypes
import json


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


AX = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
CF = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

AX.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
AX.AXUIElementCreateApplication.restype = ctypes.c_void_p
AX.AXUIElementCopyAttributeValue.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
AX.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
AX.AXUIElementSetAttributeValue.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
AX.AXUIElementSetAttributeValue.restype = ctypes.c_int32
AX.AXValueCreate.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
AX.AXValueCreate.restype = ctypes.c_void_p
AX.AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
AX.AXValueGetValue.restype = ctypes.c_bool

CF.CFArrayGetCount.argtypes = [ctypes.c_void_p]
CF.CFArrayGetCount.restype = ctypes.c_long
CF.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
CF.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
CF.CFStringCreateWithCString.restype = ctypes.c_void_p
CF.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
CF.CFStringGetCString.restype = ctypes.c_bool
CF.CFRelease.argtypes = [ctypes.c_void_p]

K_CF_STRING_ENCODING_UTF8 = 0x08000100
K_AX_VALUE_TYPE_CGPOINT = 1
K_AX_VALUE_TYPE_CGSIZE = 2


def _cf_string(value: str) -> int:
    result = CF.CFStringCreateWithCString(
        None, value.encode("utf-8"), K_CF_STRING_ENCODING_UTF8
    )
    if not result:
        raise RuntimeError(f"could not create CoreFoundation string: {value}")
    return result


K_AX_WINDOWS = _cf_string("AXWindows")
K_AX_TITLE = _cf_string("AXTitle")
K_AX_POSITION = _cf_string("AXPosition")
K_AX_SIZE = _cf_string("AXSize")
K_AX_FOCUSED_WINDOW = _cf_string("AXFocusedWindow")


def _attribute(element: int, name: int) -> int:
    value = ctypes.c_void_p()
    error = AX.AXUIElementCopyAttributeValue(element, name, ctypes.byref(value))
    if error != 0 or not value.value:
        raise RuntimeError(f"AX attribute read failed: {error}")
    return value.value


def _title(element: int) -> str:
    value = _attribute(element, K_AX_TITLE)
    try:
        buffer = ctypes.create_string_buffer(1024)
        if CF.CFStringGetCString(value, buffer, len(buffer), K_CF_STRING_ENCODING_UTF8):
            return buffer.value.decode("utf-8", errors="replace")
        return ""
    finally:
        CF.CFRelease(value)


def _set_window_geometry(
    window: int,
    x: float,
    y: float,
    width: float | None,
    height: float | None,
) -> None:
    point = CGPoint(x, y)
    ax_point = AX.AXValueCreate(K_AX_VALUE_TYPE_CGPOINT, ctypes.byref(point))
    if not ax_point:
        raise RuntimeError("could not create AX point")
    try:
        error = AX.AXUIElementSetAttributeValue(window, K_AX_POSITION, ax_point)
    finally:
        CF.CFRelease(ax_point)
    if error != 0:
        raise RuntimeError(f"AX position write failed: {error}")

    if width is None or height is None:
        return
    size = CGSize(width, height)
    ax_size = AX.AXValueCreate(K_AX_VALUE_TYPE_CGSIZE, ctypes.byref(size))
    if not ax_size:
        raise RuntimeError("could not create AX size")
    try:
        error = AX.AXUIElementSetAttributeValue(window, K_AX_SIZE, ax_size)
    finally:
        CF.CFRelease(ax_size)
    if error != 0:
        raise RuntimeError(f"AX size write failed: {error}")


def move_window(
    pid: int,
    x: float,
    y: float,
    width: float | None = None,
    height: float | None = None,
) -> dict[str, object]:
    application = AX.AXUIElementCreateApplication(pid)
    if not application:
        raise RuntimeError(f"could not create AX application for PID {pid}")
    try:
        windows = _attribute(application, K_AX_WINDOWS)
        try:
            count = CF.CFArrayGetCount(windows)
            for index in range(count):
                window = CF.CFArrayGetValueAtIndex(windows, index)
                title = _title(window)
                if "BlueStacks Air" not in title or "Keymap Overlay" in title:
                    continue
                _set_window_geometry(window, x, y, width, height)
                return {
                    "pid": pid, "title": title, "x": x, "y": y,
                    "width": width, "height": height,
                }
            # BlueStacks can expose an empty AXWindows array while still
            # exposing its focused instance window.  This is common after
            # switching Spaces/displays, so use that focused window as a
            # targeted fallback instead of touching any other application.
            focused = _attribute(application, K_AX_FOCUSED_WINDOW)
            try:
                _set_window_geometry(focused, x, y, width, height)
                return {
                    "pid": pid, "title": _title(focused), "x": x, "y": y,
                    "width": width, "height": height,
                }
            finally:
                CF.CFRelease(focused)
        finally:
            CF.CFRelease(windows)
    finally:
        CF.CFRelease(application)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--x", type=float, default=50.0)
    parser.add_argument("--y", type=float, default=50.0)
    parser.add_argument("--width", type=float, default=None)
    parser.add_argument("--height", type=float, default=None)
    args = parser.parse_args()
    print(json.dumps(
        move_window(args.pid, args.x, args.y, args.width, args.height),
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
