"""Detection rules, with no screen, keyboard or model dependencies.

Split out of inspector.py on 18 Nov 2026 (behaviour unchanged) so the rules
can be re-run offline on any signals.csv: see eval_pipeline.py.
"""

import json
from pathlib import Path

import numpy as np

import config

MOVEMENT_KEYS = {"left", "right", "up"}  # up is jump


def load_thresholds():
    thr = {"diff_high": config.INSPECTOR_DIFF_HIGH, "diff_low": config.INSPECTOR_DIFF_LOW,
           "freeze_frames": config.INSPECTOR_FREEZE_FRAMES, "source": "config.py defaults"}
    path = Path(config.THRESHOLDS_PATH)
    if path.exists():
        data = json.loads(path.read_text())
        thr.update(diff_high=float(data["diff_high"]), diff_low=float(data["diff_low"]),
                   clean_median=data.get("clean_pixel_diff", {}).get("median"),
                   source=f"thresholds.json (calibrated on {data.get('calibrated_on', '?')})")
    return thr


def runs(mask):
    """(start, end) index pairs for each stretch of consecutive True values."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def detect_anomalies(diffs, in_game, thr, actions=None):
    n = len(diffs)
    found = []

    for s, e in runs([not g for g in in_game]):
        found.append({"kind": "off_game", "triage": "harness", "frame_idx": (s + e) // 2,
                      "start": s, "end": e, "magnitude": float(e - s + 1)})

    # A pixel diff only means something when both frames show the game.
    usable = [i > 0 and in_game[i] and in_game[i - 1] for i in range(n)]

    w = config.EVIDENCE_WINDOW
    for i, d in enumerate(diffs):
        if usable[i] and d > thr["diff_high"]:
            found.append({"kind": "sudden_jump", "triage": "game", "frame_idx": i,
                          "start": max(0, i - w), "end": min(n - 1, i + w), "magnitude": d})

    # diffs[i] compares frame i with frame i-1, so it shows the result of the
    # key pressed at frame i-1: hence actions[s-1:...] against diffs[s:...].
    f = thr["freeze_frames"]
    actions = actions or [None] * n
    flagged = [False] * n
    for s in range(1, n - f + 1):
        if not all(usable[s:s + f]):
            continue
        moving = sum(a in MOVEMENT_KEYS for a in actions[s - 1:s - 1 + f]) / f
        if np.median(diffs[s:s + f]) < thr["diff_low"] and moving >= 0.5:
            flagged[s:s + f] = [True] * f
    for s, e in runs(flagged):
        # A window that straddles the onset is flagged whole; trim the stretch
        # to the frames that are themselves below the threshold.
        while s < e and diffs[s] >= thr["diff_low"]:
            s += 1
        while e > s and diffs[e] >= thr["diff_low"]:
            e -= 1
        found.append({"kind": "unresponsive", "triage": "game", "frame_idx": (s + e) // 2,
                      "start": s, "end": e, "magnitude": float(e - s + 1)})
    return found


def merge_overlapping(anomalies):
    """Merge anomalies of the same kind whose frame ranges overlap."""
    merged = []
    for a in sorted(anomalies, key=lambda a: (a["kind"], a["start"])):
        last = merged[-1] if merged else None
        if last and last["kind"] == a["kind"] and a["start"] <= last["end"]:
            last["end"] = max(last["end"], a["end"])
            last["magnitude"] = max(last["magnitude"], a["magnitude"])
        else:
            merged.append(dict(a))
    return sorted(merged, key=lambda a: a["start"])
