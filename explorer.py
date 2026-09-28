"""Explorer: plays the game with a seeded random policy and records what it sees.

Each tick it grabs a frame, picks a key and presses it. With the guard on it
first checks that it is still playing the game: the game window must have
focus, and every few ticks CLIP must agree the frame is the game. If a check
fails it stops pressing keys, brings the game back and checks again, and after
GUARD_MAX_RECOVERIES failed tries it ends the run rather than play blind. (In
May, with no guard, it kept pressing keys into whatever window had focus.)

Pace: EXPLORER_FPS is 10, but pyautogui sleeps 0.1 s after every key event,
so a tick takes about 0.3 s and a run records about 3.3 frames a second. The
Inspector's thresholds were calibrated at that pace, so changing it means
recalibrating.
"""

import argparse
import random
import time
from datetime import datetime

import config
from utils import (FrameGrabber, SessionLogger, focus_game_window, game_has_focus,
                   press_key, save_frame)


class MixedPolicy:
    """Mostly random keys. Sometimes it commits to left or right for 3-8 ticks,
    so the player crosses the level instead of jittering on the spot."""

    def __init__(self, seed, heuristic_mix):
        self._rng = random.Random(seed)
        self._mix = heuristic_mix
        self._direction = None
        self._ticks_left = 0

    def next_action(self):
        if self._ticks_left > 0:
            self._ticks_left -= 1
            return self._direction
        if self._rng.random() < self._mix:
            self._direction = self._rng.choice(["left", "right"])
            self._ticks_left = self._rng.randint(3, 8)
            return self._direction
        return self._rng.choice(config.ACTION_KEYS)


def recover(grabber, logger, is_game):
    """Try to get the game back. True once it has focus and CLIP sees it."""
    for attempt in range(1, config.GUARD_MAX_RECOVERIES + 1):
        found = focus_game_window()
        time.sleep(0.5)
        ok, p = is_game(grabber.grab())
        focused = game_has_focus()
        logger.log_event("recovery_attempt", {"attempt": attempt, "window_found": found,
                                              "focused": focused, "p_game": round(p, 4),
                                              "recovered": ok and focused})
        print(f"[explorer] recovery {attempt}: window found={found}, focused={focused}, "
              f"p_game={p:.2f}")
        if ok and focused:
            return True
    return False


def run_exploration(duration_sec, session_dir, guard=True, stop_if=None):
    """Play for duration_sec seconds, logging every frame and key press.

    stop_if, if given, is called every tick; a non-empty return value ends the
    run and becomes the end reason (run_demo.py uses it to stop if Godot exits).
    Returns the end reason.
    """
    grabber = FrameGrabber()
    logger = SessionLogger(session_dir)
    policy = MixedPolicy(config.EXPLORER_RANDOM_SEED, config.EXPLORER_HEURISTIC_MIX)

    guard = guard and config.GUARD_ENABLED
    if guard:
        from perception import is_game, warm_up
        print("[explorer] loading CLIP for the guard...")
        warm_up()

    interval = 1.0 / config.EXPLORER_FPS
    logger.log_event("session_start", {"duration_sec": duration_sec, "fps": config.EXPLORER_FPS,
                                       "seed": config.EXPLORER_RANDOM_SEED,
                                       "bbox": config.CAPTURE_BBOX, "guard": guard})
    print(f"[explorer] playing for {duration_sec}s, saving to {session_dir}")

    start = time.time()
    tick = 0
    reason = "time_up"
    try:
        while time.time() - start < duration_sec:
            tick_start = time.time()
            if stop_if is not None:
                stop_reason = stop_if()
                if stop_reason:
                    reason = stop_reason
                    break
            frame = grabber.grab()

            if guard:
                problem, extra = None, {}
                if not game_has_focus():
                    problem = "focus_lost"
                elif tick % config.GUARD_EVERY_N_TICKS == 0:
                    ok, p = is_game(frame)
                    if not ok:
                        problem, extra = "off_game", {"p_game": round(p, 4)}
                if problem:
                    shot = session_dir / "off_game" / f"tick_{tick:06d}.jpg"
                    save_frame(frame, shot)
                    logger.log_event(problem, {"tick": tick, "path": str(shot), **extra})
                    print(f"[explorer] tick {tick}: {problem}, pressing nothing, recovering")
                    if not recover(grabber, logger, is_game):
                        reason = "lost_game"
                        break
                    tick += 1
                    continue  # never act on a frame we don't trust

            action = policy.next_action()
            logger.log_frame(frame, action)
            # Let go before the next grab, so that frame shows the result of the press.
            press_key(action, duration=interval * 0.6)
            tick += 1
            time.sleep(max(0.0, interval - (time.time() - tick_start)))
    except KeyboardInterrupt:
        reason = "interrupted"
    finally:
        logger.log_event("session_end", {"frames": logger.frame_count, "reason": reason})
        logger.close()
        grabber.close()

    print(f"[explorer] done ({reason}), {logger.frame_count} frames")
    return reason


def main():
    p = argparse.ArgumentParser(description="Run the Explorer on its own (start the game first).")
    p.add_argument("--duration", type=int, default=config.EXPLORER_DURATION_SEC)
    p.add_argument("--name", help="session name (default: session_<timestamp>)")
    p.add_argument("--no-guard", action="store_true", help="no focus or CLIP checks, as in May")
    args = p.parse_args()

    name = args.name or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    print("[explorer] starting in 3 s: click the game window")
    time.sleep(3)
    run_exploration(args.duration, config.SESSIONS_DIR / name, guard=not args.no_guard)


if __name__ == "__main__":
    main()
