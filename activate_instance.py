#!/usr/bin/env python3
"""Bring one running BlueStacks instance process to the foreground on macOS."""

from __future__ import annotations

import argparse
import ctypes
import json


NS_APPLICATION_ACTIVATE_ALL_WINDOWS = 1 << 0
NS_APPLICATION_ACTIVATE_IGNORING_OTHER_APPS = 1 << 1


def activate_process(pid: int) -> bool:
    ctypes.CDLL(
        "/System/Library/Frameworks/AppKit.framework/AppKit",
        mode=ctypes.RTLD_GLOBAL,
    )
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")

    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p

    running_app_class = objc.objc_getClass(b"NSRunningApplication")
    find_selector = objc.sel_registerName(b"runningApplicationWithProcessIdentifier:")
    activate_selector = objc.sel_registerName(b"activateWithOptions:")

    send_find = ctypes.CFUNCTYPE(
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int32,
    )(("objc_msgSend", objc))
    send_activate = ctypes.CFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
    )(("objc_msgSend", objc))

    app = send_find(running_app_class, find_selector, pid)
    if not app:
        return False

    options = (
        NS_APPLICATION_ACTIVATE_ALL_WINDOWS
        | NS_APPLICATION_ACTIVATE_IGNORING_OTHER_APPS
    )
    return bool(send_activate(app, activate_selector, options))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()

    activated = activate_process(args.pid)
    print(json.dumps({"pid": args.pid, "activated": activated}))
    return 0 if activated else 1


if __name__ == "__main__":
    raise SystemExit(main())
