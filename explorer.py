"""
Explorer agent — actively probes the game to discover candidate failures.

Strategy: mixed random + heuristic action policy. This is deliberately
simple. Random + heuristic baselines are the right comparator class for
agentic game-testing research (the PhD listing explicitly says evaluation
will be against scripted and random baselines), and a learned policy is
out of scope for a demo.

Since September it also checks what it is looking at before it acts
(observe -> decide -> act -> recover). Twice a second a local CLIP model
answers "is this the game?". If not, the Explorer stops pressing keys,
logs what it saw, brings the game window back to the front and checks
again; after three failed tries it ends the run instead of recording the
wrong window. In May, without this, it kept sending key presses to
whatever window had focus after the game dropped out.

Future work the PhD would explore:
  • Curiosity-driven RL exploration
  • VLM-guided action selection (look at the frame, propose useful moves)
  • Coverage-based reward shaping over game state
"""

import argparse
import random
import time
from datetime import datetime
from pathlib import Path

import config
from utils import FrameGrabber, SessionLogger, focus_game_window, press_key, save_frame


# ─────────────────────────────────────────────────────────────────────────
# POLICY
# ─────────────────────────────────────────────────────────────────────────
class MixedPolicy:
    """Picks the next action — mostly random, sometimes heuristic."""

    def __init__(self, seed: int, heuristic_mix: float):
        self._rng = random.Random(seed)
        self._heuristic_mix = heuristic_mix
        self._momentum = None  # bias toward continuing a direction
        self._momentum_left = 0

    def next_action(self, frame=None) -> str:
        # Heuristic branch: keep moving in one direction for a few frames so
        # the agent traverses the level instead of jittering in place.
        if self._momentum_left > 0:
            self._momentum_left -= 1
            return self._momentum

        if self._rng.random() < self._heuristic_mix:
            direction = self._rng.choice(["left", "right"])
            self._momentum = direction
            self._momentum_left = self._rng.randint(3, 8)
            return direction

        # Otherwise: pure random.
        return self._rng.choice(config.ACTION_KEYS)


# ─────────────────────────────────────────────────────────────────────────
# GUARD: am I looking at the game? If not, get it back.
# ─────────────────────────────────────────────────────────────────────────
def recover(grabber: FrameGrabber, logger: SessionLogger, is_game) -> bool:
    """Try to bring the game back to the front. True once CLIP sees it again."""
    for attempt in range(1, config.GUARD_MAX_RECOVERIES + 1):
        found = focus_game_window()
        time.sleep(0.5)                       # let the window come forward
        ok, p = is_game(grabber.grab())
        logger.log_event("recovery_attempt", {
            "attempt": attempt, "window_found": found,
            "p_game": round(p, 4), "recovered": ok,
        })
        print(f"[explorer] recovery {attempt}: window_found={found} p_game={p:.2f}")
        if ok:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────
def run_exploration(duration_sec: int, session_dir: Path, guard: bool = True) -> Path:
    """Drive the game for `duration_sec` seconds, logging every action+frame."""
    grabber = FrameGrabber()
    logger  = SessionLogger(session_dir)
    policy  = MixedPolicy(config.EXPLORER_RANDOM_SEED, config.EXPLORER_HEURISTIC_MIX)

    guard = guard and config.GUARD_ENABLED
    is_game = None
    if guard:
        from perception import is_game, warm_up   # CLIP, loaded once
        print("[explorer] Loading CLIP for the guard...")
        warm_up()

    frame_interval = 1.0 / config.EXPLORER_FPS
    print(f"[explorer] Run starts. Capturing for {duration_sec}s at {config.EXPLORER_FPS} fps.")
    print(f"[explorer] Session dir: {session_dir}")

    logger.log_event("session_start", {
        "duration_sec": duration_sec,
        "fps": config.EXPLORER_FPS,
        "seed": config.EXPLORER_RANDOM_SEED,
        "bbox": config.CAPTURE_BBOX,
        "guard": guard,
    })

    off_dir = session_dir / "off_game"        # what it saw when it was lost
    start = time.time()
    tick = 0
    end_reason = "time_up"
    try:
        while time.time() - start < duration_sec:
            tick_start = time.time()
            frame = grabber.grab()

            # Observe before acting: is this still the game?
            if guard and tick % config.GUARD_EVERY_N_TICKS == 0:
                ok, p = is_game(frame)
                if not ok:
                    shot = off_dir / f"tick_{tick:06d}.jpg"
                    save_frame(frame, shot)
                    logger.log_event("off_game", {"tick": tick, "p_game": round(p, 4),
                                                  "path": str(shot)})
                    print(f"[explorer] tick {tick}: not the game (p_game={p:.2f}); "
                          "no keys pressed, recovering")
                    if not recover(grabber, logger, is_game):
                        end_reason = "lost_game"
                        break
                    tick += 1
                    continue                   # never act on a frame we don't trust

            action = policy.next_action(frame=frame)
            logger.log_frame(frame, action=action)

            # Press input for slightly less than the tick interval so the
            # next capture sees the *result* of the press, not the press
            # itself in progress.
            press_key(action, duration=frame_interval * 0.6)
            tick += 1

            # Throttle to the configured frame rate.
            elapsed = time.time() - tick_start
            sleep_for = max(0.0, frame_interval - elapsed)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        end_reason = "interrupted"
        print("[explorer] Interrupted by user.")
    finally:
        logger.log_event("session_end", {"frames": logger._frame_counter, "reason": end_reason})
        logger.close()
        grabber.close()

    print(f"[explorer] Done ({end_reason}). {logger._frame_counter} frames captured.")
    return session_dir


# ─────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Explorer agent.")
    p.add_argument("--duration", type=int, default=config.EXPLORER_DURATION_SEC,
                   help="Exploration duration in seconds.")
    p.add_argument("--name", type=str, default=None,
                   help="Optional session name; auto-generated if omitted.")
    p.add_argument("--no-guard", action="store_true",
                   help="Turn off the CLIP guard (reproduces the May behaviour).")
    args = p.parse_args()

    name = args.name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    session_dir = config.SESSIONS_DIR / name

    print("[explorer] Make sure the game window is focused. Starting in 3s...")
    time.sleep(3)

    run_exploration(args.duration, session_dir, guard=not args.no_guard)


if __name__ == "__main__":
    main()
