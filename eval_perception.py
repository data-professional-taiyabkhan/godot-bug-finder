"""How well does zero-shot CLIP tell the game from everything else?

    python eval_perception.py

The labels are my May runs. They were made without CLIP, with a colour check
(the game art is saturated; my IDE and a black screen are grey), then
spot-checked by eye:

    session_20260520_091400  frames 0-2      black screen  not game
    session_20260520_092423  frames 0-109    the game      game
                             frames 110-194  my IDE        not game
    session_20260520_093317  frames 0-15     the game      game
    session_20260520_094721  frames 0-201    the game      game

The prompts and the 0.5 cut-off in config.py were fixed before this ran.
416 frames of one game and one IDE is a sanity check, not a benchmark.
"""

import json
import time

import cv2
import numpy as np

import config
from perception import best_description, embed_images, game_probability
from utils import load_session

LABELS = {
    "session_20260520_091400": [(0, 2, False)],
    "session_20260520_092423": [(0, 109, True), (110, 194, False)],
    "session_20260520_093317": [(0, 15, True)],
    "session_20260520_094721": [(0, 201, True)],
}


def label(ranges, i):
    for start, end, is_game in ranges:
        if start <= i <= end:
            return is_game
    return None


def main():
    rows = []
    seconds, n_embedded = 0.0, 0
    for session, ranges in LABELS.items():
        records = [e for e in load_session(config.SESSIONS_DIR / session) if e["kind"] == "frame"]
        frames = [cv2.imread(r["path"]) for r in records]
        t0 = time.time()
        embs = embed_images(frames)
        seconds += time.time() - t0
        n_embedded += len(frames)
        for i, (p, caption) in enumerate(zip(game_probability(embs), best_description(embs))):
            truth = label(ranges, i)
            if truth is not None:
                rows.append({"session": session, "frame": i, "truth_game": truth, "p_game": float(p),
                             "pred_game": bool(p >= config.GAME_PROB_MIN), "closest_prompt": caption})

    y = np.array([r["truth_game"] for r in rows])
    pred = np.array([r["pred_game"] for r in rows])
    p = np.array([r["p_game"] for r in rows])
    tp, tn = int(np.sum(y & pred)), int(np.sum(~y & ~pred))
    fp, fn = int(np.sum(~y & pred)), int(np.sum(y & ~pred))

    result = {
        "frames": len(rows),
        "game_frames": int(y.sum()),
        "not_game_frames": int((~y).sum()),
        "accuracy": round((tp + tn) / len(rows), 4),
        "confusion": {"game_called_game": tp, "game_called_not_game": fn,
                      "not_game_called_game": fp, "not_game_called_not_game": tn},
        "lowest_p_game_on_a_game_frame": round(float(p[y].min()), 4),
        "highest_p_game_on_a_not_game_frame": round(float(p[~y].max()), 4),
        "ms_per_frame_cpu": round(1000 * seconds / max(1, n_embedded), 1),
        "cut_off": config.GAME_PROB_MIN,
        "prompts": {"game": config.GAME_PROMPTS, "not_game": config.NOT_GAME_PROMPTS},
        "mistakes": [r for r in rows if r["truth_game"] != r["pred_game"]],
    }
    (config.ROOT_DIR / "eval_perception.json").write_text(json.dumps(result, indent=2))

    print(f"[eval] {result['frames']} labelled frames ({result['game_frames']} game, "
          f"{result['not_game_frames']} not game)")
    print(f"[eval] accuracy {result['accuracy']:.1%}, confusion {result['confusion']}")
    print(f"[eval] lowest P(game) on a game frame: {result['lowest_p_game_on_a_game_frame']}")
    print(f"[eval] highest P(game) on a non-game frame: {result['highest_p_game_on_a_not_game_frame']}")
    print(f"[eval] {result['ms_per_frame_cpu']} ms per frame on this CPU")
    for m in result["mistakes"][:10]:
        print(f"[eval] wrong: {m['session']} frame {m['frame']}, p_game={m['p_game']:.3f}, "
              f"closest caption '{m['closest_prompt']}'")


if __name__ == "__main__":
    main()
