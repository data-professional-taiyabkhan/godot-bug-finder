"""
Set the Inspector's thresholds from a run you know is clean.

    python calibrate.py session_20260520_094721

Rules:

    sudden jump  : pixel diff > 1.5 x the LARGEST diff seen in clean play
    unresponsive : over INSPECTOR_FREEZE_FRAMES frames (3 s at 10 fps) the
                   MEDIAN diff < the SMALLEST single diff seen in clean play,
                   while the Explorer keeps pressing movement keys

History, stated plainly: the first freeze rule was "every frame < 0.5 x the
clean minimum". In a live run on 27 Sep it MISSED the planted soft-lock,
because a paused game keeps animating shader grass (diffs 0.07-1.98 after
the pause). The rule above was changed after seeing that miss, so it was
then re-tested on a fresh run it had not seen.

The clean run is from 20 May 2026, before either bug was planted. One
minute of random play is a small sample: a starting point, not a
validated model.
"""

import argparse
import json
from datetime import date

import cv2
import numpy as np

import config
from inspector import mean_diff
from utils import load_session

JUMP_MARGIN = 1.5
FREEZE_MARGIN = 1.0


def main():
    p = argparse.ArgumentParser(description="Calibrate Inspector thresholds on a clean run.")
    p.add_argument("session", help="A session under sessions/ known to contain no bugs.")
    args = p.parse_args()

    session_dir = config.SESSIONS_DIR / args.session
    records = [e for e in load_session(session_dir) if e["kind"] == "frame"]

    diffs, prev = [], None
    for rec in records:
        frame = cv2.imread(rec["path"])
        if prev is not None and frame is not None:
            diffs.append(mean_diff(prev, frame))
        prev = frame
    if not diffs:
        raise SystemExit("No frame pairs to calibrate on.")

    d = np.array(diffs)
    out = {
        "calibrated_on": args.session,
        "frame_pairs": int(d.size),
        "clean_pixel_diff": {
            "min": round(float(d.min()), 3),
            "p5": round(float(np.percentile(d, 5)), 3),
            "median": round(float(np.median(d)), 3),
            "p95": round(float(np.percentile(d, 95)), 3),
            "max": round(float(d.max()), 3),
        },
        "diff_high": round(JUMP_MARGIN * float(d.max()), 2),
        "diff_low": round(FREEZE_MARGIN * float(d.min()), 2),
        "rule": (f"jump: diff > {JUMP_MARGIN} x clean max; unresponsive: 3 s median diff "
                 f"< {FREEZE_MARGIN} x clean min while pressing movement keys"),
        "created": date.today().isoformat(),
    }
    config.THRESHOLDS_PATH.write_text(json.dumps(out, indent=2))

    c = out["clean_pixel_diff"]
    print(f"[calibrate] {out['frame_pairs']} frame pairs from {args.session}")
    print(f"[calibrate] clean diff: min {c['min']}, median {c['median']}, max {c['max']}")
    print(f"[calibrate] sudden jump if diff > {out['diff_high']} (was {config.INSPECTOR_DIFF_HIGH})")
    print(f"[calibrate] unresponsive if the 3 s median diff < {out['diff_low']} while moving")
    print(f"[calibrate] wrote {config.THRESHOLDS_PATH}")


if __name__ == "__main__":
    main()
