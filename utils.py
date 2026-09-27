"""
Shared low-level helpers used by all three agents.

Kept deliberately thin: every function does exactly one thing so the
agent code can be read top-to-bottom without context-switching.
"""

import base64
import io
import json
import time
from pathlib import Path
from typing import Optional

import cv2
import mss
import numpy as np
from PIL import Image
import pyautogui

import config


# Disable pyautogui's emergency failsafe (top-left corner abort) — useful when
# the demo runs unattended. Comment out during development if it makes you
# nervous.
pyautogui.FAILSAFE = False


# ─────────────────────────────────────────────────────────────────────────
# SCREEN CAPTURE
# ─────────────────────────────────────────────────────────────────────────
class FrameGrabber:
    """Lightweight wrapper around mss for fast screen capture."""

    def __init__(self, bbox: Optional[dict] = None):
        self.bbox = bbox or config.CAPTURE_BBOX
        self._sct = mss.mss()

    def grab(self) -> np.ndarray:
        """Return the current game frame as a BGR numpy array.

        mss BitBlt can fail on hardware-accelerated windows (Godot, games) or
        inside Remote Desktop sessions.  We try three increasingly-compatible
        strategies so the pipeline keeps running regardless of driver quirks.
        """
        # Strategy 1: mss direct-region grab (fastest, may fail on GPU windows)
        try:
            shot = self._sct.grab(self.bbox)
            img = np.array(shot)  # BGRA
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            pass

        # Strategy 2: mss full-monitor grab then crop.
        # Capturing the entire monitor often succeeds when a sub-region fails.
        try:
            monitor = self._sct.monitors[1]  # primary monitor
            shot = self._sct.grab(monitor)
            img = np.array(shot)  # BGRA, full screen
            t = self.bbox["top"]
            l = self.bbox["left"]
            h = self.bbox["height"]
            w = self.bbox["width"]
            cropped = img[t:t + h, l:l + w]
            return cv2.cvtColor(cropped, cv2.COLOR_BGRA2BGR)
        except Exception:
            pass

        # Strategy 3: PIL ImageGrab (uses a different GDI code path).
        from PIL import ImageGrab  # already installed via requirements.txt
        b = self.bbox
        pil_img = ImageGrab.grab(bbox=(
            b["left"], b["top"],
            b["left"] + b["width"],
            b["top"] + b["height"],
        ))
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def close(self):
        self._sct.close()


def save_frame(frame: np.ndarray, path: Path) -> None:
    """Persist a frame to disk as JPEG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])


def frame_to_base64(frame: np.ndarray, max_width: int = 512) -> str:
    """Encode a frame as base64 JPEG for transmission to a vision LLM."""
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame = cv2.resize(frame, (max_width, int(h * scale)))
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ─────────────────────────────────────────────────────────────────────────
# INPUT DRIVER
# ─────────────────────────────────────────────────────────────────────────
def press_key(key: str, duration: float = 0.10) -> None:
    """Press and release a single key. Cross-platform via pyautogui."""
    pyautogui.keyDown(key)
    time.sleep(duration)
    pyautogui.keyUp(key)


# ─────────────────────────────────────────────────────────────────────────
# SESSION LOGGING
# ─────────────────────────────────────────────────────────────────────────
class SessionLogger:
    """
    Append-only event log for a single exploration run.

    One JSONL line per event keeps the format inspector- and report-friendly
    without needing a database. Frames are saved beside the log.
    """

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = session_dir / "frames"
        self.frames_dir.mkdir(exist_ok=True)
        self.log_path = session_dir / "events.jsonl"
        self._fp = open(self.log_path, "w")
        self._frame_counter = 0

    def log_event(self, kind: str, payload: dict) -> None:
        record = {"t": time.time(), "kind": kind, **payload}
        self._fp.write(json.dumps(record) + "\n")
        self._fp.flush()

    def log_frame(self, frame: np.ndarray, action: Optional[str]) -> int:
        idx = self._frame_counter
        path = self.frames_dir / f"frame_{idx:06d}.jpg"
        save_frame(frame, path)
        self.log_event("frame", {"index": idx, "action": action, "path": str(path)})
        self._frame_counter += 1
        return idx

    def close(self):
        self._fp.close()


def load_session(session_dir: Path) -> list[dict]:
    """Read back a session log as a list of dicts."""
    events = []
    with open(session_dir / "events.jsonl") as fp:
        for line in fp:
            events.append(json.loads(line))
    return events
