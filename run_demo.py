"""
run_demo.py — one-shot demo runner.

1. Launches the Godot platformer (1280x720 window, 800x480 game at 1x).
2. Waits for the window, then brings it to the front so key presses land in
   the game, not the terminal.
3. Runs the Explorer (with the CLIP guard), then the Inspector (with CLIP
   triage), then the Reporter if an API key is set.
4. Watches the Godot process: if it exits early the Explorer stops cleanly
   rather than capturing desktop content.

Usage:
    .venv\\Scripts\\python run_demo.py [duration_seconds] [--clean] [--no-guard]

    --clean     launch with planted bug 2 (the soft-lock) switched off
    --no-guard  explore without the CLIP guard (the May behaviour)

Keep hands off the keyboard and mouse while it runs: it presses real keys.
"""

import argparse
import os
import subprocess
import time
from datetime import datetime

import config
from utils import focus_game_window

ap = argparse.ArgumentParser(description="Run the full demo loop.")
ap.add_argument("duration", nargs="?", type=int, default=60)
ap.add_argument("--clean", action="store_true", help="Disable the planted soft-lock.")
ap.add_argument("--no-guard", action="store_true", help="Explore without the CLIP guard.")
args = ap.parse_args()


# ─── 1. Launch Godot game window ────────────────────────────────────────────
name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
session_dir = config.SESSIONS_DIR / name
session_dir.mkdir(parents=True, exist_ok=True)
game_log = session_dir / "game_events.jsonl"    # the game writes ground truth here

env = dict(os.environ)
env["GBF_EVENT_LOG"] = str(game_log)
if args.clean:
    env["GBF_SOFTLOCK"] = "0"
print(f"[run_demo] Launching Godot platformer (1280x720), planted soft-lock "
      f"{'OFF' if args.clean else 'ON'}...")
godot_proc = subprocess.Popen(
    [
        config.GODOT_EXECUTABLE,
        "--path",       config.GODOT_PROJECT,
        "--resolution", "1280x720",
        "--position",   "100,80",
        "--windowed",
    ],
    env=env,
    creationflags=subprocess.DETACHED_PROCESS,
)
print("[run_demo] Waiting 6 s for game to initialise...")
time.sleep(6)


# ─── 2. Bring Godot window to front ─────────────────────────────────────────
if focus_game_window():
    print(f"[run_demo] Focused the '{config.GAME_WINDOW_TITLE}' window.")
else:
    print("[run_demo] WARNING: could not auto-focus the game window.")
    print("           Click the Godot game window NOW, then wait.")
    time.sleep(4)
time.sleep(1)  # let the focus change register


# ─── 3. Monkey-patch FrameGrabber to abort if Godot exits ───────────────────
# A process-health check so the Explorer doesn't silently capture desktop
# content after the game window closes. (The CLIP guard covers the other
# case: the game is running but something else is on top.)
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


# ─── 4. Run Explorer + Inspector (+ Reporter if a key is set) ───────────────
from explorer import run_exploration    # noqa: E402
from inspector import inspect_session   # noqa: E402

print(f"\n=== Run: {name} (duration={args.duration}s) ===\n")

try:
    run_exploration(args.duration, session_dir, guard=not args.no_guard)
except RuntimeError as e:
    print(f"\n[run_demo] Early exit: {e}")
    print("[run_demo] Continuing with Inspector on frames captured so far...")

# Stop the game before the Inspector loads CLIP, so nothing else is typing.
if godot_proc.poll() is None:
    print("\n[run_demo] Terminating Godot...")
    godot_proc.terminate()
else:
    print(f"\n[run_demo] Godot had already exited (code={godot_proc.returncode}).")

summaries = inspect_session(session_dir)
print(f"\n=== Summary: {len(summaries)} anomalies found ===")
for s in summaries:
    print(
        f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
        f"magnitude={s['magnitude']:.1f}  frames={s['frame_start']}-{s['frame_end']}"
    )

# ─── 5. Score against the planted bug (ground truth written by the game) ────
import json  # noqa: E402

if game_log.exists():
    truth = [json.loads(line) for line in game_log.read_text().splitlines() if line.strip()]
    frames = [e for e in utils.load_session(session_dir) if e["kind"] == "frame"]
    for ev in truth:
        # first frame captured after the event fired
        idx = next((i for i, f in enumerate(frames) if f["t"] >= ev["t"]), None)
        hit = [s for s in summaries
               if s["triage"] == "game" and idx is not None
               and s["frame_start"] <= idx + config.INSPECTOR_FREEZE_FRAMES
               and s["frame_end"] >= idx]
        print(f"\n[score] planted '{ev['event']}' fired at frame {idx} "
              f"(x={ev.get('x', 0):.0f}); Inspector {'CAUGHT it: ' + hit[0]['kind'] if hit else 'MISSED it'}")
else:
    print("\n[score] The planted soft-lock did not fire in this run (no game_events.jsonl).")

key_set = config.ANTHROPIC_API_KEY if config.LLM_BACKEND == "anthropic" else config.OPENAI_API_KEY
if summaries and key_set:
    from reporter import report_session  # noqa: E402
    report_session(name)
elif summaries:
    print("\n[run_demo] No API key set, so the Reporter was skipped. Run later with:")
    print(f"           .venv\\Scripts\\python reporter.py {name}")

print(f"\n[run_demo] Done. Session: {name}")
