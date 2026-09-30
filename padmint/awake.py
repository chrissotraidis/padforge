"""While PadMint builds, keep the computer awake. On Windows, also stop a click in
the window from pausing the build (QuickEdit), and turn it back on afterwards so
the player can still copy the last lines. Every call is best-effort and silent."""
import contextlib
import ctypes
import os
import shutil
import subprocess
import sys

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
STD_INPUT_HANDLE = -10


@contextlib.contextmanager
def while_building():
    undo = []
    with contextlib.suppress(Exception):
        if sys.platform == "win32":
            _windows(undo)
        elif sys.platform == "darwin":
            _mac(undo)
    try:
        yield
    finally:
        for step in reversed(undo):
            with contextlib.suppress(Exception):
                step()


def _windows(undo):
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    kernel32.SetThreadExecutionState.restype = ctypes.c_uint32
    if kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
        undo.append(lambda: kernel32.SetThreadExecutionState(ES_CONTINUOUS))
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    handle = ctypes.c_void_p(kernel32.GetStdHandle(STD_INPUT_HANDLE))
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and mode.value & ENABLE_QUICK_EDIT_MODE:
        before = mode.value | ENABLE_EXTENDED_FLAGS
        if kernel32.SetConsoleMode(handle, before & ~ENABLE_QUICK_EDIT_MODE):
            undo.append(lambda: kernel32.SetConsoleMode(handle, before))


def _mac(undo):
    program = shutil.which("caffeinate")
    if program:
        # -i: no idle sleep. -w: it also stops by itself if PadMint ends without cleaning up.
        process = subprocess.Popen([program, "-i", "-w", str(os.getpid())], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        undo.append(lambda: (process.terminate(), process.wait(timeout=5)))
