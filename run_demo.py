"""
run_demo.py — one-shot demo runner.

1. Launches the Godot platformer at 800×480 (exact 1× integer scale — no black bars).
2. Waits for the window to appear, then brings it to front so pyautogui key
   events land in the game (not the terminal).
3. Runs Explorer (capture frames + actions) then Inspector (flag anomalies).
4. Monitors the Godot process: if it exits early the explorer stops cleanly
   rather than silently capturing desktop content.

Usage:
    .venv\\Scripts\\python run_demo.py [duration_seconds]

Example:
    .venv\\Scripts\\python run_demo.py 60
"""

import subprocess
import sys
import time
from datetime import datetime

import config


# ─── 1. Launch Godot game window ────────────────────────────────────────────
print("[run_demo] Launching Godot platformer (1280x720)...")
godot_proc = subprocess.Popen(
    [
        config.GODOT_EXECUTABLE,
        "--path",       config.GODOT_PROJECT,
        "--resolution", "1280x720",
        "--position",   "100,80",
        "--windowed",
    ],
    creationflags=subprocess.DETACHED_PROCESS,
)
print("[run_demo] Waiting 6 s for game to initialise...")
time.sleep(6)


# ─── 2. Bring Godot window to front ─────────────────────────────────────────
try:
    import pygetwindow as gw  # type: ignore

    wins = gw.getWindowsWithTitle("Platformer 2D")
    if not wins:
        wins = [w for w in gw.getAllWindows()
                if "godot" in w.title.lower() or "platformer" in w.title.lower()]
    if wins:
        w = wins[0]
        w.activate()
        print(f"[run_demo] Focused: {w.title!r}")
    else:
        print("[run_demo] WARNING: could not auto-focus game window.")
        print("           Please click the Godot game window NOW, then wait.")
        time.sleep(4)
except Exception as exc:
    print(f"[run_demo] Window-focus skipped ({exc}). Click the game window now.")
    time.sleep(4)

time.sleep(1)  # let the focus change register


# ─── 3. Monkey-patch FrameGrabber to abort if Godot exits ───────────────────
# We inject a process-health check so the explorer doesn't silently capture
# desktop content after the game window closes.
import utils  # noqa: E402

_original_grab = utils.FrameGrabber.grab

def _grab_with_health_check(self):
    if godot_proc.poll() is not None:
        raise RuntimeError(
            f"[run_demo] Godot process exited (code={godot_proc.returncode}) "
            "mid-session — stopping Explorer."
        )
    return _original_grab(self)

utils.FrameGrabber.grab = _grab_with_health_check


# ─── 4. Run Explorer + Inspector ─────────────────────────────────────────────
from explorer import run_exploration    # noqa: E402
from inspector import inspect_session   # noqa: E402

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
print(f"\n=== Run: {name} (duration={duration}s) ===\n")

session_dir = config.SESSIONS_DIR / name
try:
    run_exploration(duration, session_dir)
except RuntimeError as e:
    print(f"\n[run_demo] Early exit: {e}")
    print("[run_demo] Continuing with Inspector on frames captured so far...")

summaries = inspect_session(session_dir)
print(f"\n=== Summary: {len(summaries)} anomalies found ===")
for s in summaries:
    print(
        f"  [{s['anomaly_index']:03d}] {s['kind']:13s}  "
        f"magnitude={s['magnitude']:.1f}  "
        f"frames={s['frame_start']}-{s['frame_end']}"
    )


# ─── 5. Tidy up ──────────────────────────────────────────────────────────────
if godot_proc.poll() is None:
    print("\n[run_demo] Terminating Godot...")
    godot_proc.terminate()
else:
    print(f"\n[run_demo] Godot had already exited (code={godot_proc.returncode}).")
print("[run_demo] Done.")
