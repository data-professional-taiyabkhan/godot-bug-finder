"""Settings for the bug finder. Everything tunable lives here."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = ROOT_DIR / "sessions"    # raw runs: frames/ + events.jsonl
EVIDENCE_DIR = ROOT_DIR / "evidence"    # Inspector output
REPORTS_DIR = ROOT_DIR / "reports"      # Reporter output
for d in (SESSIONS_DIR, EVIDENCE_DIR, REPORTS_DIR):
    d.mkdir(exist_ok=True)


def _load_dotenv(path):
    # Just enough to read KEY=value lines from a local .env (git ignores it).
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT_DIR / ".env")


# The game. Godot itself is not in the repo: put the editor build in tools/godot/.
GODOT_EXECUTABLE = str(ROOT_DIR / "tools" / "godot" / "Godot_v4.6.2-stable_win64.exe")
GODOT_PROJECT = str(ROOT_DIR / "demo_project")
GAME_WINDOW_TITLE = "Platformer 2D"

# Screen region to capture. run_demo.py opens a 1280x720 window whose client
# area starts at (100, 80); the 800x480 game view is centred inside it.
CAPTURE_BBOX = {"top": 200, "left": 340, "width": 800, "height": 480}


# Explorer
ACTION_KEYS = ["left", "right", "up", "space", "down"]
EXPLORER_DURATION_SEC = 180
EXPLORER_FPS = 10              # a target; real runs record ~3.3 fps (see explorer.py)
EXPLORER_RANDOM_SEED = 42
EXPLORER_HEURISTIC_MIX = 0.30  # share of moves that commit to one direction for a few ticks

# Guard: before acting, check the game has focus and (every few ticks) that
# CLIP still sees the game.
GUARD_ENABLED = True
GUARD_EVERY_N_TICKS = 5        # a CLIP check about every 1.5 s at the real pace
GUARD_MAX_RECOVERIES = 3


# Inspector. calibrate.py measures thresholds on a clean run and writes them
# to thresholds.json, which wins over the two guesses below.
INSPECTOR_DIFF_HIGH = 60.0     # frame diff above this: sudden jump
INSPECTOR_DIFF_LOW = 1.5       # 30-frame median below this, while moving: unresponsive
INSPECTOR_FREEZE_FRAMES = 30   # about 9 s at ~3.3 fps
THRESHOLDS_PATH = ROOT_DIR / "thresholds.json"
EVIDENCE_WINDOW = 15           # frames of context kept around an anomaly


# Perception: CLIP on the CPU, no API key.
CLIP_MODEL = "openai/clip-vit-base-patch32"
HF_CACHE_DIR = ROOT_DIR / ".hf_cache"
# Fixed before any evaluation, and generic on purpose: a tester knows the genre
# of the game, nothing more.
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
GAME_PROB_MIN = 0.5


# Reporter. Only the OpenRouter path has been run end to end so far.
LLM_BACKEND = os.environ.get("GBF_LLM_BACKEND", "openrouter")   # or "anthropic", "openai"
LLM_MODEL = {
    "openrouter": "anthropic/claude-sonnet-5",
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
}
LLM_API_KEY = {
    "openrouter": os.environ.get("OPENROUTER_API_KEY") or os.environ.get("openrouterAPI"),
    "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
    "openai": os.environ.get("OPENAI_API_KEY"),
}
LLM_FRAMES_PER_REPORT = 4
