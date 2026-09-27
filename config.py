"""
Configuration for the QoE-aware game probing agent system.

Maps directly to the QoE-Driven Agentic AI for Automated Bug Discovery
PhD project (Surrey + Sony Interactive Entertainment, PGR-2526-075):

    Explorer  → plays the game and surfaces candidate failures
    Inspector → verifies / reproduces anomalies and captures evidence
    Reporter  → produces structured, triage-ready bug reports

All tunable knobs live here so the rest of the codebase stays readable.
"""

import os
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────
ROOT_DIR        = Path(__file__).resolve().parent
SESSIONS_DIR    = ROOT_DIR / "sessions"        # raw per-run logs
REPORTS_DIR     = ROOT_DIR / "reports"         # structured bug reports
EVIDENCE_DIR    = ROOT_DIR / "evidence"        # frame clips per anomaly

for d in (SESSIONS_DIR, REPORTS_DIR, EVIDENCE_DIR):
    d.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────
# GAME UNDER TEST
# ─────────────────────────────────────────────────────────────────────────
# Path to the Godot executable. Leave as None to require launching the
# game manually before starting the Explorer (simpler for first run).
GODOT_EXECUTABLE = str(ROOT_DIR / "tools" / "godot" / "Godot_v4.6.2-stable_win64.exe")
GODOT_PROJECT    = str(ROOT_DIR / "demo_project")

# Bounding box of the game window for screen capture (top, left, width, height).
# Game launched at --resolution 1280x720 --position 100,80.
# Windows title bar (~32 px): content area starts at top=112, left=100.
# The project uses integer scale: 800x480 viewport is displayed at 1x (no 2x fit),
# centred in the 1280x720 window with 240 px left/right + 120 px top/bottom margins.
# CAPTURE_BBOX crops to the inner game content only — zero black bars.
CAPTURE_BBOX = {"top": 232, "left": 340, "width": 800, "height": 480}


# ─────────────────────────────────────────────────────────────────────────
# EXPLORER
# ─────────────────────────────────────────────────────────────────────────
# Action keys for a basic 2D platformer. Override per-game as needed.
ACTION_KEYS = ["left", "right", "up", "space", "down"]

EXPLORER_DURATION_SEC  = 180   # how long a single exploration run lasts
EXPLORER_FPS           = 10    # frames captured per second (10–15 is plenty)
EXPLORER_RANDOM_SEED   = 42    # reproducible runs
EXPLORER_HEURISTIC_MIX = 0.30  # fraction of actions chosen heuristically


# ─────────────────────────────────────────────────────────────────────────
# INSPECTOR
# ─────────────────────────────────────────────────────────────────────────
# Thresholds for frame-difference anomaly detection. These are heuristic
# starting points — the PhD would replace them with a learned QoE-aware
# severity model.
INSPECTOR_DIFF_HIGH    = 60.0  # mean pixel diff that signals a sudden jump
INSPECTOR_DIFF_LOW     = 1.5   # below this, frames look "frozen"
INSPECTOR_FREEZE_FRAMES = 30   # how many consecutive low-diff frames count as a freeze

# Evidence window around each anomaly (frames before + after).
EVIDENCE_WINDOW = 15


# ─────────────────────────────────────────────────────────────────────────
# REPORTER (LLM-backed)
# ─────────────────────────────────────────────────────────────────────────
# Backend: "anthropic" (default) or "openai".
LLM_BACKEND     = "anthropic"
ANTHROPIC_MODEL = "claude-sonnet-4-5"
OPENAI_MODEL    = "gpt-4o"

# Read API keys from environment so they never end up in the repo.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY")

# Number of frames to include with each anomaly when calling the LLM.
# 3–5 keeps cost low and gives the model enough temporal context.
LLM_FRAMES_PER_REPORT = 4
