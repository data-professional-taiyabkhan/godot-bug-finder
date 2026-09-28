"""Inspector: finds suspicious moments in a recorded run.

Three signals:

  off_game      CLIP says the frame is not the game (lost window, desktop,
                another app). Triaged as a harness problem, not a game bug,
                and kept out of the two pixel signals.
  sudden_jump   the mean grey-level change from the previous frame is above
                diff_high: a teleport, a scene break, a crash to the menu.
  unresponsive  over 30 frames the median change is below diff_low while at
                least half the key presses were moves: a hang or soft-lock.
                The median, because a paused game is not a still image (the
                grass shader keeps animating), so "every frame below the
                threshold" never holds.

Thresholds come from thresholds.json (see calibrate.py) or else config.py.
Each anomaly gets an evidence folder of frames and a summary, and
signals.csv has every frame's numbers so any decision can be checked by hand.
"""

import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

import config
from utils import load_session

MOVEMENT_KEYS = {"left", "right", "up"}  # up is jump


def mean_diff(a, b):
    """Mean absolute grey-level difference between two frames (0-255)."""
    if a.shape != b.shape:
        return 0.0
    grey_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    grey_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(grey_a, grey_b)))


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


def collect_evidence(anomaly, records, diffs, p_game, thr, out_root, idx):
    """Copy an anomaly's frames into its own folder and write summary.json."""
    ev_dir = out_root / f"anomaly_{idx:03d}_{anomaly['kind']}"
    ev_dir.mkdir(parents=True, exist_ok=True)
    s, e = anomaly["start"], anomaly["end"]

    # A jump's range already has context on both sides. For the other two,
    # also keep the frames just before the onset, to show what changed.
    lead = 0 if anomaly["kind"] == "sudden_jump" else config.EVIDENCE_WINDOW
    first = max(0, s - lead)
    for rec in records[first:e + 1]:
        src = Path(rec["path"])
        if src.exists():
            shutil.copy(src, ev_dir / src.name)

    p = p_game[s:e + 1]
    summary = {
        "anomaly_index": idx,
        "kind": anomaly["kind"],
        "triage": anomaly["triage"],
        "magnitude": anomaly["magnitude"],
        "frame_start": s,
        "frame_end": e,
        "centre_frame": anomaly["frame_idx"],
        "n_frames": e - s + 1,
        "evidence_frames": [first, e],
        # between two non-game frames the diff says nothing about the game
        "pixel_diff_median": (None if anomaly["kind"] == "off_game"
                              else round(float(np.median(diffs[s:e + 1])), 3)),
        "clean_play_median_diff": thr.get("clean_median"),
        "p_game_min": round(float(min(p)), 4) if p else None,
        "p_game_mean": round(float(np.mean(p)), 4) if p else None,
        "action_sequence": [rec.get("action") for rec in records[s:e + 1]],
        "evidence_dir": str(ev_dir),
    }
    (ev_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def inspect_session(session_dir, use_clip=True, tag=""):
    """Inspect one run. A tag writes to evidence/<session>_<tag>, keeping earlier results."""
    records = [e for e in load_session(session_dir) if e["kind"] == "frame"]
    print(f"[inspector] {session_dir.name}: {len(records)} frames")

    frames, diffs, prev = [], [], None
    for rec in records:
        frame = cv2.imread(rec["path"])
        frames.append(frame)
        diffs.append(0.0 if prev is None or frame is None else mean_diff(prev, frame))
        prev = frame

    p_game = [1.0] * len(frames)
    if use_clip and frames:
        from perception import embed_images, game_probability
        probs = iter(game_probability(embed_images([f for f in frames if f is not None])).tolist())
        p_game = [next(probs) if f is not None else 0.0 for f in frames]
    in_game = [p >= config.GAME_PROB_MIN for p in p_game]
    print(f"[inspector] CLIP: {sum(in_game)}/{len(in_game)} frames look like the game")

    thr = load_thresholds()
    print(f"[inspector] thresholds from {thr['source']}: jump if diff > {thr['diff_high']:.2f}, "
          f"unresponsive if the {thr['freeze_frames']}-frame median < {thr['diff_low']:.2f} while moving")

    actions = [rec.get("action") for rec in records]
    anomalies = merge_overlapping(detect_anomalies(diffs, in_game, thr, actions))
    print(f"[inspector] {len(anomalies)} anomalies")

    out_root = config.EVIDENCE_DIR / (session_dir.name + (f"_{tag}" if tag else ""))
    out_root.mkdir(parents=True, exist_ok=True)
    with open(out_root / "signals.csv", "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["frame", "action", "pixel_diff", "p_game", "in_game"])
        for i, rec in enumerate(records):
            writer.writerow([i, rec.get("action"), round(diffs[i], 3), round(p_game[i], 4),
                             int(in_game[i])])

    summaries = [collect_evidence(a, records, diffs, p_game, thr, out_root, i)
                 for i, a in enumerate(anomalies)]
    (out_root / "anomalies.json").write_text(json.dumps(summaries, indent=2))
    (out_root / "inspection.json").write_text(json.dumps({
        "session": session_dir.name,
        "frames": len(records),
        "frames_in_game": sum(in_game),
        "thresholds": thr,
        "clip_used": use_clip,
        "counts": {k: sum(s["kind"] == k for s in summaries)
                   for k in ("off_game", "sudden_jump", "unresponsive")},
    }, indent=2))
    print(f"[inspector] evidence in {out_root}")
    return summaries


def main():
    p = argparse.ArgumentParser(description="Inspect a recorded run.")
    p.add_argument("session", help="a folder name under sessions/")
    p.add_argument("--no-clip", action="store_true", help="pixel signals only, as in May")
    p.add_argument("--tag", default="", help="write to evidence/<session>_<tag>")
    args = p.parse_args()

    session_dir = config.SESSIONS_DIR / args.session
    if not session_dir.exists():
        raise SystemExit(f"no such session: {session_dir}")
    for s in inspect_session(session_dir, use_clip=not args.no_clip, tag=args.tag):
        print(f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
              f"frames {s['frame_start']}-{s['frame_end']}  p_game_min={s['p_game_min']}")


if __name__ == "__main__":
    main()
