"""Explorer, Inspector and Reporter in one go, against a game you have already started.

    python main.py --duration 120 --name demo_run_1

run_demo.py does the same, but launches Godot itself and scores the run.
"""

import argparse
from datetime import datetime

import config
from explorer import run_exploration
from inspector import inspect_session


def main():
    p = argparse.ArgumentParser(description="Explorer, Inspector and Reporter in one go.")
    p.add_argument("--duration", type=int, default=config.EXPLORER_DURATION_SEC)
    p.add_argument("--name", help="session name (default: session_<timestamp>)")
    p.add_argument("--skip-report", action="store_true", help="stop after the Inspector")
    p.add_argument("--no-guard", action="store_true", help="no focus or CLIP checks, as in May")
    args = p.parse_args()

    name = args.name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    session_dir = config.SESSIONS_DIR / name
    run_exploration(args.duration, session_dir, guard=not args.no_guard)

    summaries = inspect_session(session_dir)
    for s in summaries:
        print(f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
              f"frames {s['frame_start']}-{s['frame_end']}")
    if summaries and not args.skip_report:
        from reporter import report_session
        report_session(name)


if __name__ == "__main__":
    main()
