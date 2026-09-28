"""Reporter: turns each anomaly into a short bug report with a vision LLM.

For every anomaly it sends four frames from the evidence folder (the first
from just before the anomaly, where there is one) and the Inspector's summary,
and asks for a JSON report: title, severity 1-5, reproduction steps, suspected
cause, and whether it is a real bug at all. Severity is the model's zero-shot
guess; there is no player-experience data behind it.

Backend and model are set in config.py (OpenRouter by default).
"""

import argparse
import json
from pathlib import Path

import cv2

import config
from utils import frame_to_base64

SYSTEM_PROMPT = """You are a QA engineer reviewing detections from an automated game-testing agent.
For each candidate anomaly you get a few frames in time order and the Inspector's summary.

What the summary fields mean:
- kind: off_game (the frames are not the game at all), sudden_jump (a one-frame visual jump),
  or unresponsive (the screen barely changed for a while as the agent kept pressing movement keys)
- triage: "harness" if a CLIP model said the frames do not show the game (lost window, desktop,
  another app), "game" if they do
- pixel_diff_median: median change between consecutive frames during the anomaly, in grey levels
  (0-255); clean_play_median_diff is the same measure for a normal run of this game
- action_sequence: the keys the agent pressed during the anomaly

Return one JSON object with exactly these keys:
{
  "title": "short title, max 80 characters",
  "anomaly_type": "off_game | sudden_jump | unresponsive | likely_false_positive",
  "is_real_bug": true or false,
  "severity": 1 to 5 (1 cosmetic, 3 noticeable, 5 game-breaking),
  "qoe_dimensions_affected": ["immersion", "fairness", "comfort", "usability", "frustration", ...],
  "reproduction_steps": ["ordered", "steps"],
  "suspected_cause": "one or two sentences",
  "evidence_note": "what a reviewer should look for in the frames",
  "confidence": 0.0 to 1.0
}

Be honest. If the frames look like normal play or a scene transition, set is_real_bug to false.
If the frames do not show the game, it is a test-harness problem, not a game bug: is_real_bug false.
No text outside the JSON object."""


def sample_frames(evidence_dir, n):
    """n evenly spaced frames from an evidence folder, as (frame number, base64 JPEG)."""
    paths = sorted(evidence_dir.glob("frame_*.jpg"))
    if len(paths) > n:
        step = len(paths) / n
        paths = [paths[int(i * step)] for i in range(n)]
    frames = []
    for path in paths:
        img = cv2.imread(str(path))
        if img is not None:
            frames.append((int(path.stem.split("_")[1]), frame_to_base64(img)))
    return frames


def ask_model(summary, frames):
    """Send one anomaly to the configured model and return its reply as text."""
    backend = config.LLM_BACKEND
    key = config.LLM_API_KEY.get(backend)
    if not key:
        raise SystemExit(f"No API key for the '{backend}' backend; see the Reporter section of config.py.")

    parts = []  # ("text", str) or ("image", base64), in order
    for number, b64 in frames:
        before = " (before the anomaly starts)" if number < summary["frame_start"] else ""
        parts += [("text", f"Frame {number}{before}:"), ("image", b64)]
    parts.append(("text", "Inspector summary:\n" + json.dumps(summary, indent=2)
                  + "\n\nReturn the JSON report."))

    if backend == "anthropic":
        from anthropic import Anthropic
        content = [{"type": "text", "text": v} if kind == "text" else
                   {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": v}}
                   for kind, v in parts]
        resp = Anthropic(api_key=key).messages.create(
            model=config.LLM_MODEL[backend], max_tokens=1500, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}])
        return resp.content[0].text

    # OpenRouter speaks the OpenAI chat API, so both go through the openai SDK.
    from openai import OpenAI
    base_url = "https://openrouter.ai/api/v1" if backend == "openrouter" else None
    content = [{"type": "text", "text": v} if kind == "text" else
               {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{v}"}}
               for kind, v in parts]
    resp = OpenAI(api_key=key, base_url=base_url).chat.completions.create(
        model=config.LLM_MODEL[backend], max_tokens=1500,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": content}])
    return resp.choices[0].message.content


def parse_json(text):
    """The outermost {...} in the reply; copes with code fences and chatter around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {"error": "no JSON in the reply", "raw": text}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        return {"error": str(e), "raw": text}


def _severity(report):
    try:
        return float(report.get("severity", 0))
    except (TypeError, ValueError):
        return 0.0


def report_session(name):
    """Write reports/<name>/report_NNN.json for every anomaly in evidence/<name>."""
    anomalies_path = config.EVIDENCE_DIR / name / "anomalies.json"
    if not anomalies_path.exists():
        raise SystemExit(f"{anomalies_path} not found: run the Inspector first.")
    out_dir = config.REPORTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    model = config.LLM_MODEL[config.LLM_BACKEND]

    reports = []
    for s in json.loads(anomalies_path.read_text()):
        frames = sample_frames(Path(s["evidence_dir"]), config.LLM_FRAMES_PER_REPORT)
        if not frames:
            print(f"[reporter] anomaly {s['anomaly_index']}: no frames, skipped")
            continue
        print(f"[reporter] anomaly {s['anomaly_index']} ({s['kind']}): asking {model}")
        report = parse_json(ask_model(s, frames))
        report.update(_anomaly=s["anomaly_index"], _frames_sent=[n for n, _ in frames], _model=model)
        (out_dir / f"report_{s['anomaly_index']:03d}.json").write_text(json.dumps(report, indent=2))
        reports.append(report)

    reports.sort(key=_severity, reverse=True)
    (out_dir / "index.json").write_text(json.dumps(reports, indent=2))
    print(f"[reporter] {len(reports)} report(s) in {out_dir}")
    return out_dir


def main():
    p = argparse.ArgumentParser(description="Write bug reports for an inspected run.")
    p.add_argument("session", help="a folder name under evidence/")
    report_session(p.parse_args().session)


if __name__ == "__main__":
    main()
