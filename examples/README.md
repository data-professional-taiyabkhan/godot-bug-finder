# Examples: real outputs, trimmed

Small copies of real run outputs, with local folder paths removed.

## live_run4_softlock_caught/

Live run on 27 Sep 2026, planted bug 2 on, final Inspector rules fixed before
the run.

- `game_events.jsonl`: ground truth written by the game when the soft-lock fired.
- `signals.csv`: one row per captured frame: key pressed, pixel difference to the
  previous frame, CLIP's P(game), and whether it counts as the game.
- `anomalies.json`: what the Inspector reported (one `unresponsive` anomaly,
  frames 56-195, triaged as a game bug).
- `inspection.json`: thresholds used and counts.
- `frame_000050.jpg`, `frame_000054.jpg`: normal play just before the soft-lock.
- `frame_000056.jpg`, `frame_000100.jpg`: after it. The game is still rendering,
  but nothing responds.

## may_0924_reinspected/

The May 09:24 run, inspected again with the September Inspector. In May it
reported a "sudden jump" and a "freeze"; both were my IDE in the capture after
the game window dropped out. Now it reports one `off_game` stretch (frames
110-194), triaged as a harness problem. The IDE frames themselves are not
included.
