"""
Inspector agent — verifies and reproduces candidate failures.

Reads a session log produced by the Explorer and flags anomalies based on
two simple, well-known signals:

  • Sudden visual jumps  (mean inter-frame pixel diff above a high
    threshold — possible teleport, clipping, scene break, crash-to-menu)
  • Frozen frames        (low diff sustained for many frames in a row —
    possible hang, soft-lock, or input-not-registered)

For every detected anomaly the Inspector captures an evidence window:
frames + actions in a configurable neighbourhood around the event. This
is the "minimal but sufficient evidence (inputs, states, clips, logs)"
referenced in the PhD listing.

The frame-diff signal is a stand-in for what the PhD would build
properly: a learned, QoE-aware anomaly detector that understands which
visual changes are *gameplay-significant* vs cosmetic.
"""

import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

import config
from utils import load_session


# ─────────────────────────────────────────────────────────────────────────
# CORE SIGNAL: frame-to-frame mean absolute difference
# ─────────────────────────────────────────────────────────────────────────
def mean_diff(frame_a: np.ndarray, frame_b: np.ndarray) -> float:
    """Mean per-pixel absolute difference between two grayscale frames."""
    if frame_a.shape != frame_b.shape:
        return 0.0
    g_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    g_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(g_a, g_b)))


# ─────────────────────────────────────────────────────────────────────────
# ANOMALY DETECTION
# ─────────────────────────────────────────────────────────────────────────
def detect_anomalies(diffs: list[float]) -> list[dict]:
    """
    Return a list of anomaly events with kind + frame range.

    Each anomaly has:
      kind        — 'sudden_jump' or 'frozen'
      frame_idx   — central frame index
      start, end  — frame range
      magnitude   — signal strength (interpretable to a human)
    """
    anomalies = []

    # 1) Sudden jumps: one-frame spikes above the high threshold.
    for i, d in enumerate(diffs):
        if d > config.INSPECTOR_DIFF_HIGH:
            anomalies.append({
                "kind": "sudden_jump",
                "frame_idx": i,
                "start": max(0, i - config.EVIDENCE_WINDOW),
                "end":   min(len(diffs) - 1, i + config.EVIDENCE_WINDOW),
                "magnitude": d,
            })

    # 2) Frozen runs: sustained sub-threshold diffs.
    streak = 0
    streak_start = None
    for i, d in enumerate(diffs):
        if d < config.INSPECTOR_DIFF_LOW:
            if streak == 0:
                streak_start = i
            streak += 1
        else:
            if streak >= config.INSPECTOR_FREEZE_FRAMES:
                centre = streak_start + streak // 2
                anomalies.append({
                    "kind": "frozen",
                    "frame_idx": centre,
                    "start": streak_start,
                    "end":   i,
                    "magnitude": float(streak),
                })
            streak = 0
            streak_start = None

    # Tail freeze (session ended while still frozen).
    if streak >= config.INSPECTOR_FREEZE_FRAMES:
        centre = streak_start + streak // 2
        anomalies.append({
            "kind": "frozen",
            "frame_idx": centre,
            "start": streak_start,
            "end":   len(diffs) - 1,
            "magnitude": float(streak),
        })

    return anomalies


# ─────────────────────────────────────────────────────────────────────────
# EVIDENCE CAPTURE
# ─────────────────────────────────────────────────────────────────────────
def collect_evidence(anomaly: dict, frame_records: list[dict],
                     out_root: Path, idx: int) -> dict:
    """Copy the evidence frames into a per-anomaly folder."""
    ev_dir = out_root / f"anomaly_{idx:03d}_{anomaly['kind']}"
    ev_dir.mkdir(parents=True, exist_ok=True)

    actions = []
    for fi in range(anomaly["start"], anomaly["end"] + 1):
        if fi >= len(frame_records):
            break
        rec = frame_records[fi]
        src = Path(rec["path"])
        if src.exists():
            shutil.copy(src, ev_dir / src.name)
        actions.append(rec.get("action"))

    summary = {
        "anomaly_index": idx,
        "kind": anomaly["kind"],
        "magnitude": anomaly["magnitude"],
        "frame_start": anomaly["start"],
        "frame_end": anomaly["end"],
        "centre_frame": anomaly["frame_idx"],
        "n_frames": anomaly["end"] - anomaly["start"] + 1,
        "action_sequence": actions,
        "evidence_dir": str(ev_dir),
    }
    with open(ev_dir / "summary.json", "w") as fp:
        json.dump(summary, fp, indent=2)
    return summary


# ─────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────
def inspect_session(session_dir: Path) -> list[dict]:
    print(f"[inspector] Inspecting {session_dir}")
    events = load_session(session_dir)
    frame_records = [e for e in events if e["kind"] == "frame"]
    print(f"[inspector] Loaded {len(frame_records)} frames.")

    # Compute consecutive frame diffs.
    diffs = []
    prev = None
    for rec in frame_records:
        frame = cv2.imread(rec["path"])
        if frame is None:
            diffs.append(0.0)
            prev = None
            continue
        diffs.append(0.0 if prev is None else mean_diff(prev, frame))
        prev = frame

    anomalies = detect_anomalies(diffs)
    print(f"[inspector] Found {len(anomalies)} candidate anomalies.")

    # Dedupe / collapse anomalies that overlap heavily.
    anomalies = sorted(anomalies, key=lambda a: a["frame_idx"])
    merged = []
    for a in anomalies:
        if merged and a["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], a["end"])
            merged[-1]["magnitude"] = max(merged[-1]["magnitude"], a["magnitude"])
        else:
            merged.append(a)
    print(f"[inspector] Collapsed overlapping anomalies -> {len(merged)}.")

    # Build evidence packages.
    out_root = config.EVIDENCE_DIR / session_dir.name
    out_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    for idx, a in enumerate(merged):
        summaries.append(collect_evidence(a, frame_records, out_root, idx))

    # Save a session-level index.
    with open(out_root / "anomalies.json", "w") as fp:
        json.dump(summaries, fp, indent=2)

    print(f"[inspector] Evidence saved to {out_root}")
    return summaries


def main():
    p = argparse.ArgumentParser(description="Inspector agent.")
    p.add_argument("session", help="Session name under sessions/ to inspect.")
    args = p.parse_args()

    session_dir = config.SESSIONS_DIR / args.session
    if not session_dir.exists():
        raise SystemExit(f"Session not found: {session_dir}")

    inspect_session(session_dir)


if __name__ == "__main__":
    main()
