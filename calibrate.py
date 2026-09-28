"""Measure the Inspector's thresholds on a run you know is clean.

    python calibrate.py session_20260520_094721

    sudden jump:   frame diff > 1.5 x the largest diff in clean play
    unresponsive:  30-frame median diff < the smallest diff in clean play,
                   while the Explorer is pressing movement keys

The clean run is from 20 May, before either bug was planted. One minute of
random play is a small sample, so treat the numbers as a starting point.
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
    p = argparse.ArgumentParser(description="Calibrate the Inspector on a clean run.")
    p.add_argument("session", help="a session under sessions/ with no bugs in it")
    args = p.parse_args()

    records = [e for e in load_session(config.SESSIONS_DIR / args.session) if e["kind"] == "frame"]
    diffs, prev = [], None
    for rec in records:
        frame = cv2.imread(rec["path"])
        if prev is not None and frame is not None:
            diffs.append(mean_diff(prev, frame))
        prev = frame
    if not diffs:
        raise SystemExit("no frame pairs to calibrate on")

    d = np.array(diffs)
    stats = {"min": d.min(), "p5": np.percentile(d, 5), "median": np.median(d),
             "p95": np.percentile(d, 95), "max": d.max()}
    out = {
        "calibrated_on": args.session,
        "frame_pairs": int(d.size),
        "clean_pixel_diff": {k: round(float(v), 3) for k, v in stats.items()},
        "diff_high": round(JUMP_MARGIN * float(d.max()), 2),
        "diff_low": round(FREEZE_MARGIN * float(d.min()), 2),
        "rule": (f"jump: diff > {JUMP_MARGIN} x clean max; unresponsive: "
                 f"{config.INSPECTOR_FREEZE_FRAMES}-frame median diff < {FREEZE_MARGIN} x clean min "
                 "while pressing movement keys"),
        "created": date.today().isoformat(),
    }
    config.THRESHOLDS_PATH.write_text(json.dumps(out, indent=2))

    c = out["clean_pixel_diff"]
    print(f"[calibrate] {out['frame_pairs']} frame pairs from {args.session}")
    print(f"[calibrate] clean diffs: min {c['min']}, median {c['median']}, max {c['max']}")
    print(f"[calibrate] sudden jump if diff > {out['diff_high']}")
    print(f"[calibrate] unresponsive if the {config.INSPECTOR_FREEZE_FRAMES}-frame median "
          f"< {out['diff_low']} while moving")
    print(f"[calibrate] wrote {config.THRESHOLDS_PATH}")


if __name__ == "__main__":
    main()
