# Examples: real outputs, trimmed

Small copies of real run outputs, with local folder paths removed. In every
folder, `signals.csv` has one row per recorded frame: the key pressed after
it, the change from the previous frame, CLIP's P(game), and whether that counts
as the game. `anomalies.json` is what the Inspector reported, `inspection.json`
the thresholds and counts, and `report_NNN.json` what the Reporter wrote
(Claude Sonnet 5 via OpenRouter).

## run_a_softlock_28sep/

Run A, 28 Sep 2026, soft-lock on. `game_events.jsonl` is the ground truth the
game wrote when the soft-lock fired (just before frame 48). The Inspector
found an `unresponsive` stretch, frames 49-198 (`report_001.json`: real bug,
severity 4) and one false alarm, a `sudden_jump` at frames 46-47
(`report_000.json`: not a real bug). `frame_000045.jpg` to `frame_000047.jpg`
show the jump that moved the camera; `frame_000060.jpg` is the frozen game.

## run_b_clean_28sep/

Run B, 28 Sep 2026, soft-lock off: 198 frames and no anomalies.

## run_c_popup_28sep/

Run C, 28 Sep 2026: `guard_test.py` opened a window over the game 10 s in.
`events.jsonl` holds the whole session log, including the guard's `off_game`
and `recovery_attempt` events. `frame_000034.jpg` is the frame recorded with
the pop-up half over the game (P(game) 0.53), `off_game_tick_000035.jpg` the
frame the guard checked before pressing anything (0.37), and
`frame_000035.jpg` the game back in front. The `sudden_jump` in
`anomalies.json` is that pop-up, wrongly triaged as a game bug.

## live_run4_softlock_caught/

Live run 4, 27 Sep 2026, the first catch: `unresponsive`, frames 56-195.
`frame_000050.jpg` and `frame_000054.jpg` show normal play just before the
soft-lock, `frame_000056.jpg` and `frame_000100.jpg` after it. The anomaly
files are from the 27 Sep inspection; `report_000.json` was written on 28 Sep
from a re-inspection with the current code (same anomaly). It calls it a real
bug but guesses the wrong cause.

## may_0924_reinspected/

The May 09:24 run, inspected again with the September Inspector. In May it
reported a "sudden jump" and a "freeze"; both were my IDE in the capture after
the game window dropped out. Now it reports one `off_game` stretch (frames
110-194), triaged as a harness problem, and the Reporter agrees it is not a
game bug (`report_000.json`). The IDE frames themselves are not included.
