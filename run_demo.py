"""Launch the game, play it, inspect the run and score it against the planted bug.

    python run_demo.py [seconds] [--clean] [--no-guard]

--clean turns the planted soft-lock off. --no-guard plays without the focus
and CLIP checks, as in May. Keep your hands off the keyboard while it runs:
it presses real keys.
"""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime

import config
from explorer import run_exploration
from inspector import inspect_session
from utils import focus_game_window, load_session


def launch_game(event_log, softlock=True):
    env = dict(os.environ, GBF_EVENT_LOG=str(event_log))
    if not softlock:
        env["GBF_SOFTLOCK"] = "0"
    return subprocess.Popen(
        [config.GODOT_EXECUTABLE, "--path", config.GODOT_PROJECT,
         "--resolution", "1280x720", "--position", "100,80", "--windowed"],
        env=env, creationflags=subprocess.DETACHED_PROCESS)


# What each planted bug should show up as.
EXPECTED_KIND = {"softlock": "unresponsive"}


def score(session_dir, summaries):
    """Match the anomalies against the planted bug, which the game logs when it fires.

    Anything left unmatched had no planted bug behind it: a false alarm, a
    harness problem, or a real bug in the demo."""
    frames = [e for e in load_session(session_dir) if e["kind"] == "frame"]
    log = session_dir / "game_events.jsonl"
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()] if log.exists() else []
    if not events:
        print("[score] no planted bug fired in this run")

    matched = set()
    for event in events:
        # the first frame captured after it fired
        idx = next((i for i, f in enumerate(frames) if f["t"] >= event["t"]), None)
        want = EXPECTED_KIND.get(event["event"])
        hits = [s for s in summaries
                if s["kind"] == want and idx is not None
                and s["frame_start"] <= idx + config.INSPECTOR_FREEZE_FRAMES and s["frame_end"] >= idx]
        matched.update(s["anomaly_index"] for s in hits)
        if hits:
            verdict = f"CAUGHT it: {want}, frames {hits[0]['frame_start']}-{hits[0]['frame_end']}"
        else:
            verdict = "MISSED it"
        print(f"[score] planted '{event['event']}' fired at frame {idx}; the Inspector {verdict}")

    for s in summaries:
        if s["anomaly_index"] not in matched:
            print(f"[score] no planted bug behind: {s['kind']} ({s['triage']}), "
                  f"frames {s['frame_start']}-{s['frame_end']}")


def main():
    ap = argparse.ArgumentParser(description="Run the whole loop against the Godot demo.")
    ap.add_argument("duration", nargs="?", type=int, default=60, help="seconds of play (default 60)")
    ap.add_argument("--clean", action="store_true", help="turn the planted soft-lock off")
    ap.add_argument("--no-guard", action="store_true", help="no focus or CLIP checks, as in May")
    args = ap.parse_args()

    name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
    session_dir = config.SESSIONS_DIR / name
    session_dir.mkdir(parents=True)

    print(f"[run_demo] {name}: starting Godot, soft-lock {'off' if args.clean else 'on'}")
    game = launch_game(session_dir / "game_events.jsonl", softlock=not args.clean)
    time.sleep(6)  # give the window time to appear
    if not focus_game_window():
        print("[run_demo] could not find the game window: click it now")
        time.sleep(4)
    time.sleep(1)

    def game_exited():
        code = game.poll()
        return None if code is None else f"game exited (code {code})"

    try:
        reason = run_exploration(args.duration, session_dir, guard=not args.no_guard,
                                 stop_if=game_exited)
    finally:
        if game.poll() is None:
            game.terminate()

    summaries = inspect_session(session_dir)
    print(f"\n{len(summaries)} anomalies")
    for s in summaries:
        print(f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
              f"frames {s['frame_start']}-{s['frame_end']}")
    score(session_dir, summaries)

    if summaries and config.LLM_API_KEY.get(config.LLM_BACKEND):
        from reporter import report_session
        report_session(name)
    elif summaries:
        print(f"[run_demo] no API key, so no reports; later: python reporter.py {name}")
    print(f"[run_demo] done ({reason}): {name}")


if __name__ == "__main__":
    main()
