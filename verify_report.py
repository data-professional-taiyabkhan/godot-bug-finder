"""Output check: test each Reporter claim against the run's own numbers.

The Reporter is a vision LLM, so anything it writes is a claim, not a fact.
This script checks what can be checked against signals.csv (the per-frame
numbers the Inspector measured) and the anomaly summary, without calling any
model:

  schema            required keys, severity 1-5, confidence 0-1
  kind              anomaly_type agrees with the Inspector, or says false positive
  harness           a harness-triaged anomaly is never called a real game bug
  frames_cited      every frame number it cites was one of the frames it was sent
                    (or the anomaly's own start/end)
  numbers           every decimal it quotes matches a measured value (+/- 0.01)
  no_change_claim   "identical" / "unchanged" / "not updating" wording is tested
                    against the measured change; citing a frame from before
                    the anomaly started as part of a frozen stretch is an error
  borderline_frame  a frame in the evidence window was close to the CLIP
                    cut-off (P(game) < 0.9), so another window may have been on
                    screen; flagged when the report blames the game or calls it
                    normal play. Added after run C (28 Sep), where exactly that
                    happened, so it is fitted to one known case.
  keys              keys named in the reproduction steps were actually pressed

Each finding is "fail" (the report contradicts the data) or "warn" (it goes
beyond the data). A report with no findings is not proven right: causes and
repro steps still cannot be checked from pixels.

Usage:
    python verify_report.py examples/run_a_softlock_28sep
    python verify_report.py --all examples
"""

import argparse
import csv
import json
import re
import statistics
from pathlib import Path

REQUIRED = ["title", "anomaly_type", "is_real_bug", "severity", "reproduction_steps",
            "suspected_cause", "evidence_note", "confidence"]
TEXT_FIELDS = ["title", "suspected_cause", "evidence_note", "reproduction_steps"]
KEYS = ["left", "right", "up", "down", "space"]
# About frames, not numbers: "22.155 vs 22.924, nearly identical" compares two
# medians and is fine. (The first version matched any "identical" and flagged
# exactly that sentence in run C; narrowed on 18 Nov.)
NO_CHANGE = re.compile(r"pixel[- ]identical|identical across|\bunchanged\b|no visual change|"
                       r"not (updating|advancing)|stop(ped|s)? updating|did not change", re.I)
GAME_BLAME = re.compile(r"normal (gameplay|play|platforming|traversal|movement)|camera", re.I)
BORDERLINE_P = 0.9
TOLERANCE = 0.01


def load_thresholds_used(folder):
    """Calibration numbers the Reporter may quote: thresholds.json, plus whatever
    the run's inspection.json recorded (older runs did not record clean_median)."""
    out = {}
    path = Path(__file__).resolve().parent / "thresholds.json"
    if path.exists():
        data = json.loads(path.read_text())
        out = {"diff_high": data["diff_high"], "diff_low": data["diff_low"],
               "clean_median": data["clean_pixel_diff"]["median"]}
    path = Path(folder) / "inspection.json"
    if path.exists():
        out.update({k: v for k, v in json.loads(path.read_text()).get("thresholds", {}).items() if v is not None})
    return out


def load_signals(folder):
    path = Path(folder) / "signals.csv"
    if not path.exists():
        return None
    rows = list(csv.DictReader(path.open()))
    return {"diff": [float(r["pixel_diff"]) for r in rows],
            "p_game": [float(r["p_game"]) for r in rows],
            "action": [r["action"] for r in rows]}


def report_text(report):
    parts = []
    for f in TEXT_FIELDS:
        v = report.get(f, "")
        parts.extend(v if isinstance(v, list) else [str(v)])
    return "\n".join(parts)


def cited_frames(text):
    """Frame numbers after 'frame'/'frames', including lists and arrows: 'frames 34, 75 and 157'."""
    found = set()
    for m in re.finditer(r"frames?\s+((?:\d+\s*(?:,|and|->|to|through|-|–)?\s*)+)", text, re.I):
        found.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    return found


def measured_values(summary, sig, thresholds=None):
    """Every number the Reporter could legitimately quote."""
    vals = [v for k, v in summary.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    for v in (thresholds or {}).values():  # clean-play median and the two cut-offs
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(v)
    if sig:
        s, e = summary["frame_start"], summary["frame_end"]
        window = sig["diff"][s:e + 1]
        if window:
            vals += [statistics.median(window), min(window), max(window)]
        vals += [min(sig["p_game"][s:e + 1]), statistics.mean(sig["p_game"][s:e + 1])]
    return vals


def verify(report, summary, sig, thresholds=None):
    """Findings for one report: a list of {check, level, detail}."""
    out = []

    def add(check, level, detail):
        out.append({"check": check, "level": level, "detail": detail})

    if "error" in report:
        add("schema", "fail", f"the reply was not valid JSON: {report['error']}")
        return out
    missing = [k for k in REQUIRED if k not in report]
    if missing:
        add("schema", "fail", f"missing keys: {missing}")
    sev = report.get("severity")
    if not isinstance(sev, (int, float)) or not 1 <= sev <= 5:
        add("schema", "fail", f"severity {sev!r} is not 1-5")
    conf = report.get("confidence")
    if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        add("schema", "fail", f"confidence {conf!r} is not 0-1")

    kind, triage = summary["kind"], summary["triage"]
    atype = report.get("anomaly_type")
    if atype not in (kind, "likely_false_positive"):
        add("kind", "fail", f"report says {atype!r}, the Inspector measured {kind!r}")
    if triage == "harness" and report.get("is_real_bug") is True:
        add("harness", "fail", "CLIP said these frames are not the game, but the report calls it a real game bug")

    text = report_text(report)
    s, e = summary["frame_start"], summary["frame_end"]
    sent = set(report.get("_frames_sent", []))
    allowed = sent | {s, e}
    extra = sorted(cited_frames(text) - allowed)
    if extra:
        add("frames_cited", "warn", f"cites frame(s) {extra}, but was only sent {sorted(sent)}")

    vals = measured_values(summary, sig, thresholds)
    for m in re.finditer(r"(?<![\w.])(\d+\.\d+)(?![\w.])", text):
        x = float(m.group(1))
        if not any(abs(x - v) <= TOLERANCE for v in vals):
            add("numbers", "fail", f"quotes {x}, which matches no measured value for this anomaly")

    if NO_CHANGE.search(text) and sig:
        window = sig["diff"][s:e + 1]
        med = statistics.median(window) if window else 0.0
        if med > 0:
            add("no_change_claim", "warn",
                f"says the frames did not change; measured median change in frames {s}-{e} is {med:.2f}, not zero")
        before = sorted(f for f in cited_frames(text) if f < s)
        if before:
            pre = sig["diff"][max(1, before[0]):s]
            pre_med = statistics.median(pre) if pre else 0.0
            add("no_change_claim", "fail",
                f"treats frame(s) {before} as part of the frozen stretch, but the anomaly starts at frame {s}; "
                f"frames {before[0]}-{s - 1} changed by a median of {pre_med:.1f}")

    if sig:
        first, last = summary.get("evidence_frames", [s, e])
        lo = min(range(first, last + 1), key=lambda i: sig["p_game"][i])
        if sig["p_game"][lo] < BORDERLINE_P and triage == "game":
            if report.get("is_real_bug") is True or GAME_BLAME.search(text):
                add("borderline_frame", "warn",
                    f"frame {lo} had P(game) {sig['p_game'][lo]:.2f}: another window may have been on screen, "
                    f"which the report does not consider" + ("" if lo in sent else f" (frame {lo} was not sent to it)"))

        pressed = set(sig["action"][max(0, s - 1):e + 1])
        steps = " ".join(report.get("reproduction_steps", []))
        named = {k for k in KEYS if re.search(rf"\b{k}\b", steps, re.I)}
        missing_keys = sorted(named - pressed)
        if missing_keys:
            add("keys", "warn", f"repro steps name {missing_keys}, which were not pressed in frames {s}-{e}")
    return out


def verdict(findings):
    if any(f["level"] == "fail" for f in findings):
        return "fail"
    return "warn" if findings else "pass"


def verify_folder(folder):
    folder = Path(folder)
    anomalies = {a["anomaly_index"]: a for a in json.loads((folder / "anomalies.json").read_text())}
    sig = load_signals(folder)
    results = []
    for path in sorted(folder.glob("report_*.json")):
        report = json.loads(path.read_text())
        summary = anomalies.get(report.get("_anomaly"))
        if summary is None:
            continue
        findings = verify(report, summary, sig, load_thresholds_used(folder))
        results.append({"report": f"{folder.name}/{path.name}", "verdict": verdict(findings),
                        "findings": findings, "signals_available": sig is not None})
    return results


def main():
    p = argparse.ArgumentParser(description="Check Reporter output against the measured data.")
    p.add_argument("folder", help="an evidence folder with anomalies.json, signals.csv and report_*.json")
    p.add_argument("--all", action="store_true", help="treat folder as a parent of several such folders")
    args = p.parse_args()
    folders = sorted(d for d in Path(args.folder).iterdir() if d.is_dir()) if args.all else [Path(args.folder)]
    for folder in folders:
        if not (folder / "anomalies.json").exists():
            continue
        for r in verify_folder(folder):
            print(f"{r['verdict'].upper():5s} {r['report']}" + ("" if r["signals_available"] else "  (no signals.csv)"))
            for f in r["findings"]:
                print(f"      {f['level']}: {f['check']}: {f['detail']}")


if __name__ == "__main__":
    main()
