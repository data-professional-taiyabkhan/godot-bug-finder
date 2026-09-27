# godot-bug-finder

A small prototype of the three-agent architecture described in the
**QoE-Driven Agentic AI for Automated Bug Discovery in Video Games** PhD
project (University of Surrey × Sony Interactive Entertainment,
`PGR-2526-075`).

This is *not* a research system. It is a deliberately minimal,
demonstrably-working skeleton built to engage concretely with the
research problem ahead of applying.

## Architecture

| PhD agent | This prototype | Role |
|-----------|----------------|------|
| **Explorer**  | `explorer.py`  | Drives the game with a mixed random + heuristic policy; captures frames and actions at a fixed frame rate. |
| **Inspector** | `inspector.py` | Reads the session log, computes per-frame visual differences, flags `sudden_jump` and `frozen` anomalies, and saves an evidence window (frames + input sequence) around each. |
| **Reporter**  | `reporter.py`  | Sends each anomaly's evidence to a vision LLM (Claude by default, GPT-4o optional) and asks for a structured triage report: title, severity (1–5), reproduction steps, QoE dimensions affected, suspected cause. |

## Quickstart

```bash
# 1. Set up
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 2. Open a Godot game in windowed mode. Note its position/size.
#    Update CAPTURE_BBOX in config.py to match.

# 3. Run the full loop.
python main.py --duration 120 --name demo_run_1
```

Outputs:

- `sessions/demo_run_1/` — raw frames + `events.jsonl`
- `evidence/demo_run_1/anomaly_NNN_*/` — per-anomaly frame clips
- `reports/demo_run_1/report_NNN.json` — structured LLM bug reports
- `reports/demo_run_1/index.json` — all reports, sorted by severity

## Test scenario

The demo is intended to be run against a **2D platformer with one
deliberately injected bug** — e.g. a wall-clip on a specific jump or a
counter that freezes after a known trigger. The injected bug provides
ground truth: you can measure whether the Explorer reaches the failure,
whether the Inspector flags it, and whether the Reporter classifies it
correctly.

A reasonable starting point: the official Godot 2D platformer demo, with
a single `Sprite2D` collision exception added to one wall.

## Honest limitations

This is a **3-week scoped prototype**, not a research contribution. Known
gaps the actual PhD would address:

1. **Exploration policy is random + heuristic, not learned.** No
   curiosity-driven RL, no coverage-aware reward shaping, no VLM-guided
   action selection. Random+heuristic is the right *baseline* to beat.
2. **Anomaly signal is pixel-difference, not perceptual.** A real
   detector would use a learned, QoE-aware model — likely a fine-tuned
   VLM — that distinguishes gameplay-meaningful changes from cosmetic
   ones (camera shake, particle effects, UI fades).
3. **Severity ranking is LLM-zero-shot, not calibrated.** The PhD's
   contribution is precisely a learned severity model trained on human
   QA judgements. This demo asks Claude to guess; it has no QoE training
   data, no inter-rater calibration, no link to player-impact studies.
4. **No reproducibility verification.** The Inspector flags single
   observations. A real Inspector would re-run the observed action
   sequence to confirm the failure reproduces — currently out of scope.
5. **External probing only.** No engine instrumentation, no log scraping,
   no internal state access. For a closed-source AAA title this is the
   right constraint; for QA tooling it should be relaxed.

## Why this exists

I built this to ground my application to the PhD in something concrete.
The framework matches the project description's Explorer / Inspector /
Reporter decomposition; the limitations above are exactly the directions
in which the PhD would push the work forward. I am very much aware this
is a sketch — that is the point.

## Files

```
godot-bug-finder/
├── config.py        # all tunable knobs, paths, thresholds, API keys
├── utils.py         # screen capture, input, session logging, base64 helpers
├── explorer.py      # Explorer agent — drives the game
├── inspector.py     # Inspector agent — finds and reproduces anomalies
├── reporter.py      # Reporter agent — LLM-backed structured bug reports
├── main.py          # end-to-end orchestrator
├── requirements.txt
└── README.md        # this file
```
