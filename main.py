"""
End-to-end orchestrator: Explorer → Inspector → Reporter.

This is the script a reviewer would run to see the loop in action. It
mirrors the multi-agent workflow described in the PhD listing.

    python main.py --duration 120 --name demo_run_1

Steps:
  1. Explorer plays the game for `duration` seconds, logging frames+actions.
  2. Inspector scans the session, flags anomalies, captures evidence.
  3. Reporter sends each anomaly to a vision LLM and writes JSON reports.
"""

import argparse
from datetime import datetime

import config
from explorer  import run_exploration
from inspector import inspect_session
from reporter  import report_session


def main():
    p = argparse.ArgumentParser(description="Run the full three-agent loop.")
    p.add_argument("--duration", type=int, default=config.EXPLORER_DURATION_SEC,
                   help="Exploration duration in seconds.")
    p.add_argument("--name", type=str, default=None,
                   help="Session name (auto-generated if omitted).")
    p.add_argument("--skip-report", action="store_true",
                   help="Stop after the Inspector (useful while iterating).")
    p.add_argument("--no-guard", action="store_true",
                   help="Explore without the CLIP guard (the May behaviour).")
    args = p.parse_args()

    name = args.name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    print(f"\n=== Run: {name} ===\n")

    # 1. Explorer
    session_dir = config.SESSIONS_DIR / name
    run_exploration(args.duration, session_dir, guard=not args.no_guard)

    # 2. Inspector
    summaries = inspect_session(session_dir)
    print(f"\n=== Summary: {len(summaries)} anomalies found ===")
    for s in summaries:
        print(f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
              f"magnitude={s['magnitude']:.1f}  "
              f"frames={s['frame_start']}–{s['frame_end']}")

    # 3. Reporter
    if args.skip_report:
        print("\n[main] --skip-report given; not calling the LLM.")
        return
    if not summaries:
        print("\n[main] No anomalies to report.")
        return

    report_session(name)
    print("\n=== Done. ===")


if __name__ == "__main__":
    main()
