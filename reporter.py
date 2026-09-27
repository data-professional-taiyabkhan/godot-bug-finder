"""
Reporter agent — produces structured, triage-ready bug reports.

For each anomaly the Inspector flagged, the Reporter sends a small bundle
of evidence (a few sampled frames + the action sequence) to a vision LLM
and asks for a structured report. Output is JSON: title, reproduction
steps, severity (1–5), suspected cause, evidence pointers.

This is where the QoE severity model from the PhD listing would plug in
properly. For the demo, severity is asked of the LLM along with everything
else; the production system would replace that with a learned ranker
calibrated against human QA judgements.

Backend: defaults to Anthropic (Claude). Switch via config.LLM_BACKEND.
"""

import argparse
import base64
import json
from pathlib import Path
from typing import Optional

import cv2

import config
from utils import frame_to_base64


# ─────────────────────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a QA engineer reviewing automated bug detections from a game-testing agent.
For each candidate anomaly you receive:
  • The anomaly type (sudden_jump or frozen)
  • The action sequence that led up to it
  • A small set of in-order frames showing the moment of interest

Return a single JSON object with this exact schema:

{
  "title":         "short imperative title, max 80 chars",
  "anomaly_type":  "<sudden_jump | frozen | likely_false_positive>",
  "is_real_bug":   true | false,
  "severity":      1 to 5  (1 = cosmetic, 3 = noticeable, 5 = game-breaking),
  "qoe_dimensions_affected": ["immersion" | "fairness" | "comfort" | "usability" | "frustration" | ...],
  "reproduction_steps": ["ordered", "human-readable", "steps"],
  "suspected_cause":   "one or two sentences",
  "evidence_note":     "what the reviewer should look for in the attached frames",
  "confidence":        0.0 to 1.0
}

Be honest: if the frames look like normal gameplay or scene transitions, set is_real_bug=false.
Do not include any text outside the JSON object."""


# ─────────────────────────────────────────────────────────────────────────
# FRAME SAMPLING
# ─────────────────────────────────────────────────────────────────────────
def sample_frames(evidence_dir: Path, n: int) -> list[str]:
    """Pick `n` frames evenly spaced from the evidence folder and base64-encode them."""
    frame_paths = sorted(evidence_dir.glob("frame_*.jpg"))
    if not frame_paths:
        return []
    if len(frame_paths) <= n:
        chosen = frame_paths
    else:
        step = len(frame_paths) / n
        chosen = [frame_paths[int(i * step)] for i in range(n)]

    encoded = []
    for fp in chosen:
        img = cv2.imread(str(fp))
        if img is not None:
            encoded.append(frame_to_base64(img))
    return encoded


# ─────────────────────────────────────────────────────────────────────────
# LLM CALL — Anthropic
# ─────────────────────────────────────────────────────────────────────────
def call_anthropic(summary: dict, b64_frames: list[str]) -> dict:
    """Single Claude call with system prompt + interleaved frames + summary."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise SystemExit("Install the anthropic SDK: pip install anthropic")

    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("Set the ANTHROPIC_API_KEY environment variable.")

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_blocks = []
    for b64 in b64_frames:
        user_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    user_blocks.append({
        "type": "text",
        "text": "Anomaly summary:\n" + json.dumps(summary, indent=2)
                + "\n\nReturn the JSON report.",
    })

    resp = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_blocks}],
    )
    return _parse_json(resp.content[0].text)


# ─────────────────────────────────────────────────────────────────────────
# LLM CALL — OpenAI
# ─────────────────────────────────────────────────────────────────────────
def call_openai(summary: dict, b64_frames: list[str]) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("Install the openai SDK: pip install openai")

    if not config.OPENAI_API_KEY:
        raise SystemExit("Set the OPENAI_API_KEY environment variable.")

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    user_content = []
    for b64 in b64_frames:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    user_content.append({
        "type": "text",
        "text": "Anomaly summary:\n" + json.dumps(summary, indent=2)
                + "\n\nReturn the JSON report.",
    })

    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        max_tokens=800,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
    )
    return _parse_json(resp.choices[0].message.content)


# ─────────────────────────────────────────────────────────────────────────
# OUTPUT PARSING
# ─────────────────────────────────────────────────────────────────────────
def _parse_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response, tolerantly."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1:
        return {"error": "no JSON found", "raw": text}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        return {"error": str(e), "raw": text}


# ─────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────
def report_session(session_name: str) -> Path:
    evidence_root = config.EVIDENCE_DIR / session_name
    anomalies_path = evidence_root / "anomalies.json"
    if not anomalies_path.exists():
        raise SystemExit(f"No anomalies index at {anomalies_path}. Run the Inspector first.")

    summaries = json.loads(anomalies_path.read_text())
    out_dir = config.REPORTS_DIR / session_name
    out_dir.mkdir(parents=True, exist_ok=True)

    backend_fn = call_anthropic if config.LLM_BACKEND == "anthropic" else call_openai

    reports = []
    for s in summaries:
        ev_dir = Path(s["evidence_dir"])
        frames = sample_frames(ev_dir, config.LLM_FRAMES_PER_REPORT)
        if not frames:
            print(f"[reporter] No frames for anomaly {s['anomaly_index']}, skipping.")
            continue
        print(f"[reporter] Drafting report for anomaly {s['anomaly_index']} ({s['kind']})...")
        report = backend_fn(s, frames)
        report["_source_anomaly"] = s["anomaly_index"]
        report["_evidence_dir"]   = s["evidence_dir"]
        out_path = out_dir / f"report_{s['anomaly_index']:03d}.json"
        out_path.write_text(json.dumps(report, indent=2))
        reports.append(report)

    # Roll-up index sorted by severity (highest first).
    reports.sort(key=lambda r: -r.get("severity", 0))
    (out_dir / "index.json").write_text(json.dumps(reports, indent=2))
    print(f"[reporter] {len(reports)} reports written to {out_dir}")
    return out_dir


def main():
    p = argparse.ArgumentParser(description="Reporter agent.")
    p.add_argument("session", help="Session name to report on.")
    args = p.parse_args()
    report_session(args.session)


if __name__ == "__main__":
    main()
