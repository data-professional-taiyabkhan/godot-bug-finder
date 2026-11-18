"""Fixed eval set for the whole pipeline, offline: no Godot, no CLIP, no API key.

eval/cases.json holds labelled cases from the recorded runs in examples/,
failure cases included. This script scores three things against those labels:

  detection  re-runs the Inspector's rules (detect.py) on each run's
             signals.csv and checks the anomalies against the ground truth
  reports    checks each stored Reporter output: right verdict (real bug or
             not), and right reason (a crude keyword check, see cases.json)
  verifier   checks verify_report.py flags what it should, and nothing more

It writes eval_results.json and prints a table. Known failures stay in the set
and show up as FAIL: that is the point of keeping them.

Usage:
    python eval_pipeline.py
"""

import csv
import json
from pathlib import Path

from detect import detect_anomalies, load_thresholds, merge_overlapping
from verify_report import load_signals, load_thresholds_used, verdict, verify

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "eval" / "cases.json"
OUT = ROOT / "eval_results.json"


def run_detection(folder, thr):
    rows = list(csv.DictReader((folder / "signals.csv").open()))
    diffs = [float(r["pixel_diff"]) for r in rows]
    in_game = [r["in_game"] == "1" for r in rows]
    actions = [r["action"] for r in rows]
    return merge_overlapping(detect_anomalies(diffs, in_game, thr, actions))


def score_detection(case, thr):
    if case.get("out_of_scope"):
        return {"id": case["id"], "result": "OUT OF SCOPE", "detail": case["out_of_scope"]}
    found = run_detection(ROOT / case["folder"], thr)
    matched, missed = set(), []
    for exp in case["expect"]:
        hit = [i for i, a in enumerate(found)
               if a["kind"] == exp["kind"] and a["triage"] == exp["triage"]
               and a["start"] <= exp["covers_frame"] <= a["end"]]
        if hit:
            matched.add(hit[0])
        else:
            missed.append(exp)
    extra = [a for i, a in enumerate(found) if i not in matched]
    ok = not missed and not (case.get("expect_nothing_else") and extra)
    parts = []
    if missed:
        parts.append("missed " + ", ".join(f"{m['kind']} at frame {m['covers_frame']}" for m in missed))
    if extra:
        parts.append("unexpected " + ", ".join(f"{a['kind']} ({a['triage']}) frames {a['start']}-{a['end']}" for a in extra))
    if case["expect"] and not missed:
        parts.insert(0, "caught " + ", ".join(e["kind"] for e in case["expect"]))
    if not case["expect"] and not extra:
        parts.append("nothing flagged, correctly")
    return {"id": case["id"], "result": "PASS" if ok else "FAIL", "detail": "; ".join(parts),
            "known_failure": case.get("known_failure")}


def anomaly_for(report_path, report):
    anomalies = json.loads((report_path.parent / "anomalies.json").read_text())
    return next(a for a in anomalies if a["anomaly_index"] == report["_anomaly"])


def check_verifier(case_id, report, folder, summary, expect, expect_checks):
    findings = verify(report, summary, load_signals(folder), load_thresholds_used(folder))
    got = verdict(findings)
    fired = sorted({f["check"] for f in findings})
    missing = [c for c in expect_checks if c not in fired]
    ok = got == expect and not missing
    detail = f"expected {expect}, got {got}" + (f"; fired {fired}" if fired else "")
    if missing:
        detail += f"; did not fire {missing}"
    return {"id": case_id, "result": "PASS" if ok else "FAIL", "detail": detail, "findings": findings}


def main():
    cases = json.loads(CASES.read_text())
    thr = load_thresholds()
    results = {"thresholds": {k: thr[k] for k in ("diff_high", "diff_low", "freeze_frames")},
               "detection": [], "reports": [], "verifier": []}

    for case in cases["detection"]:
        results["detection"].append(score_detection(case, thr))

    for case in cases["reports"]:
        path = ROOT / case["report"]
        report = json.loads(path.read_text())
        text = json.dumps(report).lower()
        verdict_ok = report.get("is_real_bug") == case["is_real_bug"]
        reason_ok = any(k.lower() in text for k in case["right_reason_any"])
        results["reports"].append({
            "id": case["id"],
            "result": "PASS" if verdict_ok and reason_ok else "FAIL",
            "detail": f"verdict {'right' if verdict_ok else 'WRONG'}, reason {'right' if reason_ok else 'WRONG'}",
            "why": case.get("why")})
        results["verifier"].append(check_verifier(
            case["id"], report, path.parent, anomaly_for(path, report),
            case["verifier_expect"], case.get("verifier_expect_checks", [])))

    for case in cases["synthetic_reports"]:
        if "copy_of" in case:
            path = ROOT / case["copy_of"]
            report = dict(json.loads(path.read_text()), title="(copy) " + json.loads(path.read_text())["title"])
            folder = path.parent
        else:
            report = case["report"]
            folder = ROOT / case["anomalies_from"]
            path = folder / "report_000.json"
        results["verifier"].append(check_verifier(
            case["id"], report, folder, anomaly_for(path, report),
            case["verifier_expect"], case.get("verifier_expect_checks", [])))

    OUT.write_text(json.dumps(results, indent=2))
    for section in ("detection", "reports", "verifier"):
        rows = results[section]
        passed = sum(r["result"] == "PASS" for r in rows)
        scored = sum(r["result"] in ("PASS", "FAIL") for r in rows)
        print(f"\n{section}: {passed}/{scored} pass")
        for r in rows:
            print(f"  {r['result']:12s} {r['id']:30s} {r['detail']}")
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
