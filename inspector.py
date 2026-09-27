"""
Inspector agent — verifies and reproduces candidate failures.

Reads a session log produced by the Explorer and flags anomalies with two
cheap signals plus one learned one:

  • Sudden visual jumps  (mean inter-frame pixel diff above a high
    threshold — possible teleport, clipping, scene break, crash-to-menu)
  • Unresponsive stretch (for 3 s the screen barely changes while the
    Explorer keeps pressing movement keys — possible hang or soft-lock).
    Measured as the median diff over a 3 s window, because a paused game
    is not a still image: shader-animated grass keeps moving. (The first
    rule, "every frame below a threshold", missed a planted soft-lock for
    exactly that reason.)
  • Off-game frames      (a local CLIP model says the frame is not the
    game at all — the window was lost, the desktop or another app is
    showing). These are triaged as HARNESS problems, not game bugs, and
    are kept out of the two pixel signals above.

Thresholds come from thresholds.json when it exists (see calibrate.py:
measured on a run known to be clean), otherwise from config.py.

For every detected anomaly the Inspector captures an evidence window:
frames + actions in a configurable neighbourhood around the event. This
is the "minimal but sufficient evidence (inputs, states, clips, logs)"
referenced in the PhD listing. It also writes signals.csv, one row per
frame, so every decision can be checked by hand.

The frame-diff signal is still a stand-in for what the PhD would build
properly: a learned, QoE-aware anomaly detector that understands which
visual changes are *gameplay-significant* vs cosmetic.
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


def load_thresholds() -> dict:
    """Calibrated thresholds if calibrate.py has been run, else config defaults."""
    thr = {
        "diff_high": config.INSPECTOR_DIFF_HIGH,
        "diff_low": config.INSPECTOR_DIFF_LOW,
        "freeze_frames": config.INSPECTOR_FREEZE_FRAMES,
        "source": "config.py defaults",
    }
    path = Path(config.THRESHOLDS_PATH)
    if path.exists():
        data = json.loads(path.read_text())
        thr["diff_high"] = float(data["diff_high"])
        thr["diff_low"] = float(data["diff_low"])
        thr["source"] = f"thresholds.json (calibrated on {data.get('calibrated_on', '?')})"
    return thr


# ─────────────────────────────────────────────────────────────────────────
# ANOMALY DETECTION
# ─────────────────────────────────────────────────────────────────────────
def _runs(mask: list[bool]) -> list[tuple[int, int]]:
    """(start, end) index pairs of consecutive True values."""
    runs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


MOVEMENT_KEYS = {"left", "right", "up"}   # "up" is jump in this game


def detect_anomalies(diffs: list[float], in_game: list[bool], thr: dict,
                     actions: list | None = None) -> list[dict]:
    """
    Return a list of anomaly events with kind + frame range.

    Each anomaly has:
      kind        — 'off_game', 'sudden_jump' or 'unresponsive'
      triage      — 'harness' (our capture / setup failed) or 'game'
      frame_idx   — central frame index
      start, end  — frame range
      magnitude   — signal strength (interpretable to a human)
    """
    n = len(diffs)
    w = config.EVIDENCE_WINDOW
    anomalies = []

    # 0) Off-game stretches: the capture is not showing the game at all.
    for s, e in _runs([not g for g in in_game]):
        anomalies.append({
            "kind": "off_game", "triage": "harness",
            "frame_idx": (s + e) // 2, "start": s, "end": e,
            "magnitude": float(e - s + 1),          # frames lost
        })

    # A pixel diff only means something when both frames show the game.
    usable = [i > 0 and in_game[i] and in_game[i - 1] for i in range(n)]

    # 1) Sudden jumps: one-frame spikes above the high threshold.
    for i, d in enumerate(diffs):
        if usable[i] and d > thr["diff_high"]:
            anomalies.append({
                "kind": "sudden_jump", "triage": "game",
                "frame_idx": i,
                "start": max(0, i - w), "end": min(n - 1, i + w),
                "magnitude": d,
            })

    # 2) Unresponsive: over a 3 s window of game frames the MEDIAN diff is
    #    below the threshold while at least half the key presses were moves.
    f = thr["freeze_frames"]
    actions = actions or [None] * n
    flagged = [False] * n
    medians = {}
    for s in range(1, n - f + 1):
        if not all(usable[s:s + f]):
            continue
        med = float(np.median(diffs[s:s + f]))
        moving = sum(a in MOVEMENT_KEYS for a in actions[s - 1:s - 1 + f]) / f
        if med < thr["diff_low"] and moving >= 0.5:
            for i in range(s, s + f):
                flagged[i] = True
                medians[i] = min(medians.get(i, med), med)
    for s, e in _runs(flagged):
        # A window straddling the onset is flagged as a whole; trim the run to
        # the frames that are themselves below the threshold.
        while s < e and diffs[s] >= thr["diff_low"]:
            s += 1
        while e > s and diffs[e] >= thr["diff_low"]:
            e -= 1
        anomalies.append({
            "kind": "unresponsive", "triage": "game",
            "frame_idx": (s + e) // 2, "start": s, "end": e,
            "magnitude": float(e - s + 1),            # frames affected
        })

    return anomalies


def merge_overlapping(anomalies: list[dict]) -> list[dict]:
    """Collapse anomalies of the same kind whose frame ranges overlap."""
    merged = []
    for a in sorted(anomalies, key=lambda a: (a["kind"], a["start"])):
        last = merged[-1] if merged else None
        if last and last["kind"] == a["kind"] and a["start"] <= last["end"]:
            last["end"] = max(last["end"], a["end"])
            last["magnitude"] = max(last["magnitude"], a["magnitude"])
        else:
            merged.append(dict(a))
    return sorted(merged, key=lambda a: a["start"])


# ─────────────────────────────────────────────────────────────────────────
# EVIDENCE CAPTURE
# ─────────────────────────────────────────────────────────────────────────
def collect_evidence(anomaly: dict, frame_records: list[dict], p_game: list[float],
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

    window = p_game[anomaly["start"]:anomaly["end"] + 1]
    summary = {
        "anomaly_index": idx,
        "kind": anomaly["kind"],
        "triage": anomaly["triage"],
        "magnitude": anomaly["magnitude"],
        "frame_start": anomaly["start"],
        "frame_end": anomaly["end"],
        "centre_frame": anomaly["frame_idx"],
        "n_frames": anomaly["end"] - anomaly["start"] + 1,
        "p_game_min": round(float(min(window)), 4) if window else None,
        "p_game_mean": round(float(np.mean(window)), 4) if window else None,
        "action_sequence": actions,
        "evidence_dir": str(ev_dir),
    }
    with open(ev_dir / "summary.json", "w") as fp:
        json.dump(summary, fp, indent=2)
    return summary


# ─────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────
def inspect_session(session_dir: Path, use_clip: bool = True, tag: str = "") -> list[dict]:
    """Inspect one session. `tag` writes to evidence/<session>_<tag> so an
    earlier inspection of the same session is kept, not overwritten."""
    print(f"[inspector] Inspecting {session_dir}")
    events = load_session(session_dir)
    frame_records = [e for e in events if e["kind"] == "frame"]
    print(f"[inspector] Loaded {len(frame_records)} frames.")

    frames, diffs, prev = [], [], None
    for rec in frame_records:
        frame = cv2.imread(rec["path"])
        frames.append(frame)
        if frame is None:
            diffs.append(0.0)
            prev = None
            continue
        diffs.append(0.0 if prev is None else mean_diff(prev, frame))
        prev = frame

    # Learned signal: is each frame the game at all? (CLIP, local)
    p_game = [1.0] * len(frames)
    if use_clip and frames:
        from perception import embed_images, game_probability
        ok = [f is not None for f in frames]
        embs = embed_images([f for f in frames if f is not None])
        probs = iter(game_probability(embs).tolist())
        p_game = [next(probs) if o else 0.0 for o in ok]
    in_game = [p >= config.GAME_PROB_MIN for p in p_game]
    print(f"[inspector] CLIP: {sum(in_game)}/{len(in_game)} frames look like the game.")

    thr = load_thresholds()
    print(f"[inspector] Thresholds from {thr['source']}: "
          f"jump > {thr['diff_high']:.2f}; unresponsive if the median over "
          f"{thr['freeze_frames']} frames < {thr['diff_low']:.2f} while moving.")

    actions = [rec.get("action") for rec in frame_records]
    anomalies = merge_overlapping(detect_anomalies(diffs, in_game, thr, actions))
    print(f"[inspector] {len(anomalies)} anomalies after merging.")

    # Build evidence packages.
    out_root = config.EVIDENCE_DIR / (session_dir.name + (f"_{tag}" if tag else ""))
    out_root.mkdir(parents=True, exist_ok=True)

    with open(out_root / "signals.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["frame", "action", "pixel_diff", "p_game", "in_game"])
        for i, rec in enumerate(frame_records):
            wr.writerow([i, rec.get("action"), round(diffs[i], 3),
                         round(p_game[i], 4), int(in_game[i])])

    summaries = [collect_evidence(a, frame_records, p_game, out_root, idx)
                 for idx, a in enumerate(anomalies)]

    # Session-level index (list, as the Reporter expects) + run metadata.
    with open(out_root / "anomalies.json", "w") as fp:
        json.dump(summaries, fp, indent=2)
    with open(out_root / "inspection.json", "w") as fp:
        json.dump({
            "session": session_dir.name,
            "frames": len(frame_records),
            "frames_in_game": sum(in_game),
            "thresholds": thr,
            "clip_used": use_clip,
            "counts": {k: sum(1 for s in summaries if s["kind"] == k)
                       for k in ("off_game", "sudden_jump", "unresponsive")},
        }, fp, indent=2)

    print(f"[inspector] Evidence saved to {out_root}")
    return summaries


def main():
    p = argparse.ArgumentParser(description="Inspector agent.")
    p.add_argument("session", help="Session name under sessions/ to inspect.")
    p.add_argument("--no-clip", action="store_true",
                   help="Pixel signals only (reproduces the May behaviour).")
    p.add_argument("--tag", default="",
                   help="Write to evidence/<session>_<tag> instead of overwriting.")
    args = p.parse_args()

    session_dir = config.SESSIONS_DIR / args.session
    if not session_dir.exists():
        raise SystemExit(f"Session not found: {session_dir}")

    for s in inspect_session(session_dir, use_clip=not args.no_clip, tag=args.tag):
        print(f"  [{s['anomaly_index']:03d}] {s['kind']:12s} triage={s['triage']:8s} "
              f"frames={s['frame_start']}-{s['frame_end']} p_game_min={s['p_game_min']}")


if __name__ == "__main__":
    main()
