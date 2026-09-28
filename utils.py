"""Screen capture, key presses, the game window, and the session log."""

import base64
import json
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import pyautogui

import config

pyautogui.FAILSAFE = False  # runs unattended; the mouse-in-the-corner abort only gets in the way


class FrameGrabber:
    def __init__(self, bbox=None):
        self.bbox = bbox or config.CAPTURE_BBOX
        self._sct = mss.mss()

    def grab(self):
        """The capture region as a BGR array."""
        # A region grab is fastest, but it can fail on GPU-rendered windows and
        # over Remote Desktop; then grab the whole screen and crop, then try PIL.
        b = self.bbox
        try:
            return cv2.cvtColor(np.array(self._sct.grab(b)), cv2.COLOR_BGRA2BGR)
        except Exception:
            pass
        try:
            screen = np.array(self._sct.grab(self._sct.monitors[1]))
            crop = screen[b["top"]:b["top"] + b["height"], b["left"]:b["left"] + b["width"]]
            return cv2.cvtColor(crop, cv2.COLOR_BGRA2BGR)
        except Exception:
            pass
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=(b["left"], b["top"], b["left"] + b["width"], b["top"] + b["height"]))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def close(self):
        self._sct.close()


def save_frame(frame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])


def frame_to_base64(frame, max_width=512):
    """A frame as a base64 JPEG, at most max_width wide (what the Reporter sends)."""
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf.tobytes()).decode("ascii")


def press_key(key, duration=0.1):
    # pyautogui also sleeps pyautogui.PAUSE (0.1 s) after keyDown and after
    # keyUp. That, more than config.EXPLORER_FPS, sets the Explorer's pace.
    pyautogui.keyDown(key)
    time.sleep(duration)
    pyautogui.keyUp(key)


# The game window (Windows only, via pygetwindow; elsewhere these do nothing).

def _find_game_window():
    try:
        import pygetwindow as gw
    except Exception:
        return None
    wins = gw.getWindowsWithTitle(config.GAME_WINDOW_TITLE)
    return wins[0] if wins else None


def game_has_focus():
    """True if the game window is the active one (or if we cannot tell)."""
    try:
        import pygetwindow as gw
    except Exception:
        return True
    active = gw.getActiveWindow()
    return active is not None and config.GAME_WINDOW_TITLE in active.title


def focus_game_window():
    """Bring the game window to the front. False if there is no game window."""
    w = _find_game_window()
    if w is None:
        return False
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
    except Exception:
        # activate() raises "The operation completed successfully" when Windows
        # refuses to hand over focus; minimise + restore gets round that.
        try:
            w.minimize()
            w.restore()
        except Exception:
            return False
    _lift(w._hWnd)
    return True


def _lift(hwnd):
    # Activating a window that already has focus does not lift it above one
    # that covers it, so raise it too: topmost, then straight back to normal.
    import ctypes
    from ctypes import wintypes
    set_pos = ctypes.windll.user32.SetWindowPos
    set_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
    keep_pos_and_size = 0x0002 | 0x0001  # SWP_NOMOVE | SWP_NOSIZE
    set_pos(hwnd, -1, 0, 0, 0, 0, keep_pos_and_size)  # HWND_TOPMOST
    set_pos(hwnd, -2, 0, 0, 0, 0, keep_pos_and_size)  # HWND_NOTOPMOST


class SessionLogger:
    """events.jsonl (one JSON object per line) plus the frames/ folder."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.frames_dir = session_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._fp = open(session_dir / "events.jsonl", "w")
        self.frame_count = 0

    def log_event(self, kind, payload):
        self._fp.write(json.dumps({"t": time.time(), "kind": kind, **payload}) + "\n")
        self._fp.flush()

    def log_frame(self, frame, action):
        path = self.frames_dir / f"frame_{self.frame_count:06d}.jpg"
        save_frame(frame, path)
        self.log_event("frame", {"index": self.frame_count, "action": action, "path": str(path)})
        self.frame_count += 1

    def close(self):
        self._fp.close()


def load_session(session_dir: Path):
    with open(session_dir / "events.jsonl") as fp:
        return [json.loads(line) for line in fp]
