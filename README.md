# godot-bug-finder

A small three-agent game tester (Explorer, Inspector, Reporter) that plays a
Godot platformer, flags suspicious moments and writes bug reports.

I started it in May 2026 as a prototype for my application to a University of
Surrey PhD studentship co-supervised with Sony Interactive Entertainment:
[QoE-Driven Agentic AI for Automated Bug Discovery in Video Games](https://www.jobs.ac.uk/job/DRA154/phd-studentship-qoe-driven-agentic-ai-for-automated-bug-discovery-in-video-games-collaborative-doctorate-with-sony-interactive-entertainment)
(PGR-2526-075). It is my own work for that application, not affiliated with
Surrey or Sony.

The git history has two chapters:

- **May 2026**: the original skeleton, committed unchanged.
- **September 2026**: a local CLIP model so the agents can tell the game from
  everything else, thresholds measured on a clean run, a planted bug the
  system can actually catch, and every number in this README.

This is *not* a research system. It is a deliberately small, honest skeleton.

## How it works

| Agent | File | What it does |
|-------|------|--------------|
| **Explorer**  | `explorer.py`  | Plays the game at 10 fps with a seeded random + heuristic policy (key presses via `pyautogui`, screenshots via `mss`). Twice a second it asks CLIP "is this the game?". If not, it stops pressing keys, brings the game window back and checks again: observe, decide, act, recover. |
| **Inspector** | `inspector.py` | Per-frame pixel differences flag **sudden jumps** and **unresponsive** stretches (the screen barely changes for 3 s while the agent keeps pressing movement keys). CLIP marks frames that are not the game as a **harness** problem and keeps them out of the pixel signals. Saves an evidence clip per anomaly and `signals.csv` with every frame's numbers. |
| **Reporter**  | `reporter.py`  | Sends each anomaly's frames and summary to a vision LLM (Claude by default, GPT-4o optional) for a structured triage report: title, severity 1-5, repro steps, suspected cause, `is_real_bug`. Needs an API key. |
| Perception    | `perception.py`| CLIP ViT-B/32 (Hugging Face `transformers`), zero-shot, on the CPU: about 80 ms per frame on an i5-11300H laptop. |

`run_demo.py` launches Godot, runs all three, and scores the run against the
planted bug's ground truth. `calibrate.py` sets thresholds from a clean run.
`eval_perception.py` measures the CLIP check against labelled frames.

## What happened when I ran it

### May 2026 (the original)

- Four runs. The Inspector flagged two anomalies, and **both were harness
  errors, not game bugs**: the game window dropped out and the screen capture
  recorded my IDE instead. One "sudden jump" into the IDE, one "freeze" on it.
  Meanwhile the Explorer kept sending key presses to whatever window had focus.
- The Reporter never ran, and the planted ledge bug was added after the last
  run, so it was never tested.
- The capture box was 32 px too low: every frame of the "fixed" run ended in a
  32 px black band.

### September 2026

All numbers below come from files in this repo (`eval_perception.json`,
`thresholds.json`, `examples/`) or from the run logs on my laptop.

| Check | Result |
|-------|--------|
| CLIP "is this the game?" on 416 labelled frames from the May runs (328 game, 88 IDE or black) | **416/416 correct, zero-shot.** Lowest P(game) on a real game frame: 0.97. Highest on a non-game frame: 0.02. About 82 ms per frame on the CPU. Prompts fixed before the run. |
| The May 09:24 run, inspected again | The two "game bugs" become **one harness issue**: frames 110-194 are not the game. |
| Thresholds from the clean May run | Sudden jump: diff > 43.03 (was 60). Unresponsive: 3 s median diff < 1.52 while moving (the first version was "every frame < 0.76"). |
| Live runs 1 and 2, 27 Sep | Guard on, every captured frame was the game, and the capture box fix removed the black band. Bug 2 never fired: its code lived in `level.gd`, which is not attached to any scene. (I first blamed the Explorer for not reaching the trigger zone. That was wrong.) |
| Live run 3 (bug 2 moved to `planted_bugs.gd`, 30 s timer) | Fired at frame 55. **The Inspector missed it.** A paused game keeps animating shader grass (diffs 0.07-1.98 after the pause), so "every frame below 0.76" never held for 3 s. I rewrote the rule as a 3 s median. |
| Live run 4 (a fresh run, new rule fixed beforehand) | Fired at frame 55. **Caught:** one `unresponsive` anomaly, frames 56-195. CLIP saw the game in 196/196 frames, so it was triaged as a game bug, not a harness failure. No other anomalies. |
| False alarms under the final rules | None on the clean May run, none on live runs 1 and 2, and only the harness issue on the May 09:24 run. |
| Reporter | Not run yet: there was no API key on this laptop when these results were produced. |

In normal play the lowest 3-second median difference across these runs was
4.6; after the soft-lock it sat between 0.59 and 0.78. That gap is what the
unresponsive rule relies on, and it comes from a handful of minutes of play.

## Planted bugs (ground truth)

| Bug | Where | What happens | Can this system see it? |
|-----|-------|--------------|--------------------------|
| 1. Phantom ledge (May) | `demo_project/level/level.tscn`, node `ShortcutLedge` | The collision box sits 32 px right of the sprite, so the left 32 px are a strip you fall through. | **No.** Falling through a ledge looks like ordinary falling, both to pixel differences and to a whole-frame CLIP check. It needs perception that knows what a platform is, or access to game state. |
| 2. Timed soft-lock (September) | `demo_project/planted_bugs.gd`, node `PlantedBugs` in `game_singleplayer.tscn` | 30 s after start the game pauses itself without the pause menu: still rendering, nothing responds. | **Yes**, as an `unresponsive` anomaly that CLIP confirms is still the game. |

Bug 2 is a fault injection on a timer: it tests inspection and triage, not
exploration. Two earlier versions fired only when the player stood in a zone
near the spawn point. Both lived in `level.gd`, which (as in the upstream
Godot demo) is not attached to any scene, so neither ever ran.

## Quickstart (Windows)

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

rem Godot 4.6.2 (editor build) goes in tools\godot\ ; it is not in the repo.
rem First CLIP use downloads about 600 MB of weights into .hf_cache\

.venv\Scripts\python calibrate.py <a clean session>
.venv\Scripts\python run_demo.py 60            &rem hands off: it presses real keys
.venv\Scripts\python run_demo.py 60 --clean    &rem same, with bug 2 switched off

set ANTHROPIC_API_KEY=...
.venv\Scripts\python reporter.py <session>
```

Raw sessions (frames and logs) are not in the repo because of their size;
`examples/` holds a small sample, and `eval_perception.json` and
`thresholds.json` hold the measured numbers.

## Honest limitations

1. **Exploration is random + heuristic, not learned.** It is seeded, so each
   run replays the same key sequence, and in 60 s it mostly wanders near the
   spawn point. No curiosity-driven RL, no coverage reward, no VLM-guided moves.
2. **Anomaly signals are pixel maths plus a whole-frame CLIP check.** Neither
   understands gameplay, which is why bug 1 is invisible. A real detector
   would be a learned, QoE-aware model of what matters to a player.
3. **Thresholds come from one clean minute of play.** The unresponsive rule
   was rewritten after it missed bug 2 once (a paused game keeps animating
   shader grass), then caught it on one fresh run. One catch is a
   demonstration, not a detection rate; more runs would make the
   calibration less fragile.
4. **The CLIP check was evaluated on 416 frames from one game and one IDE.**
   It is a sanity check, not a benchmark.
5. **Severity is an LLM's zero-shot guess**, with no QoE training data.
6. **No reproduction step.** The Inspector reports single observations; it
   does not replay the inputs to confirm a failure.
7. **External probing only, Windows only.** No engine instrumentation;
   `pyautogui`, `pygetwindow` and fixed window positions tie it to one setup.

## Files

```
godot-bug-finder/
├── config.py           # every knob: paths, capture box, thresholds, prompts
├── perception.py       # CLIP: "is this the game?"
├── utils.py            # screen capture, key presses, window focus, session log
├── explorer.py         # Explorer: plays, checks what it sees, recovers
├── inspector.py        # Inspector: pixel signals + CLIP triage, evidence
├── reporter.py         # Reporter: vision-LLM bug reports (needs an API key)
├── calibrate.py        # thresholds from a clean run -> thresholds.json
├── eval_perception.py  # CLIP accuracy on labelled frames -> eval_perception.json
├── run_demo.py         # launch Godot, run everything, score against bug 2
├── main.py             # the three agents without launching Godot
├── examples/           # a small sample of real outputs
└── demo_project/       # Godot's 2D platformer demo + the two planted bugs
```

## Credits

The game is Godot's official 2D Platformer demo from
[godot-demo-projects](https://github.com/godotengine/godot-demo-projects)
(MIT licence, see `demo_project/LICENSE.md`), with two planted bugs added.
Music: "Pompy" by Hubert Lamontagne (madbr), as credited in the demo's README.
