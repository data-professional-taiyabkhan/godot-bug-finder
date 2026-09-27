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
# Game launched at --resolution 1280x720 --position 100,80. The 800x480 viewport
# is shown at 1x, centred with 240 px left/right and 120 px top/bottom margins.
# 27 Sep 2026: every frame captured with top=232 ended in a 32 px black band,
# i.e. --position places the client area, not the title bar. Game content
# therefore starts at y = 80 + 120 = 200.
CAPTURE_BBOX = {"top": 200, "left": 340, "width": 800, "height": 480}

# Title of the game window, used to bring it back to the front.
GAME_WINDOW_TITLE = "Platformer 2D"


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
# Thresholds for frame-difference anomaly detection. The defaults below were
# guesses. calibrate.py replaces them with values measured on a run you know
# is clean, written to thresholds.json, which the Inspector prefers.
INSPECTOR_DIFF_HIGH    = 60.0  # mean pixel diff that signals a sudden jump
INSPECTOR_DIFF_LOW     = 1.5   # a 3 s median diff below this, while moving, is "unresponsive"
INSPECTOR_FREEZE_FRAMES = 30   # window length in frames (3 s at 10 fps)
THRESHOLDS_PATH        = ROOT_DIR / "thresholds.json"

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


# ─────────────────────────────────────────────────────────────────────────
# PERCEPTION (CLIP, runs locally on the CPU, no API key)
# ─────────────────────────────────────────────────────────────────────────
# CLIP scores a frame against short text descriptions. The frame "is the
# game" when the game descriptions win. No training and no labels.
CLIP_MODEL    = "openai/clip-vit-base-patch32"
HF_CACHE_DIR  = ROOT_DIR / ".hf_cache"          # model weights stay in the project

# Fixed before any evaluation, and deliberately generic: a QA agent knows the
# genre of the game it is testing, nothing more.
GAME_PROMPTS = [
    "a screenshot of a video game",
    "a screenshot of a 2D platformer game",
]
NOT_GAME_PROMPTS = [
    "a screenshot of a code editor",
    "a screenshot of a computer desktop",
    "a screenshot of a web browser",
    "a black screen",
    "an error message dialog",
]
GAME_PROB_MIN = 0.5   # P(game) below this means "not looking at the game"

# Explorer guard: how often it checks what it is looking at, and how many
# times it tries to get the game back before giving up.
GUARD_ENABLED        = True
GUARD_EVERY_N_TICKS  = 5      # 10 fps / 5 = two checks a second
GUARD_MAX_RECOVERIES = 3
