"""Live test for the Explorer's guard: cover the game with another window mid-run.

    python guard_test.py [seconds_into_run] [hold_s]

Start it at the same time as run_demo.py. It waits for the run to record its
first frame (Godot and CLIP take a while to load), then after
seconds_into_run it opens a plain window over the capture area and tries to
take focus, the way an IDE or a pop-up might, and closes it hold_s seconds
later. The guard should notice, stop pressing keys, bring the game back and
carry on. It prints when the window opened and closed, to match against the
session's events.jsonl.
"""

import sys
import time
import tkinter as tk

import config

into_run = float(sys.argv[1]) if len(sys.argv) > 1 else 10
hold = float(sys.argv[2]) if len(sys.argv) > 2 else 8

# Place the window in real pixels. Without this, on a display scaled to 150%
# Windows scales Tk's coordinates and the window lands off to the side.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def wait_for_first_frame(since):
    while True:
        for d in config.SESSIONS_DIR.glob("session_*"):
            if d.stat().st_ctime >= since and any((d / "frames").glob("frame_*.jpg")):
                return d
        time.sleep(0.5)


session = wait_for_first_frame(time.time() - 2)
print(f"run started: {session.name}", flush=True)
time.sleep(into_run)

root = tk.Tk()
root.title("guard test")
b = config.CAPTURE_BBOX
root.geometry(f"{b['width'] + 100}x{b['height'] + 100}+{b['left'] - 50}+{b['top'] - 50}")
root.configure(bg="#2b2b2b")
tk.Label(root, text="Not the game.\nThis window opened on top to test the guard.",
         fg="white", bg="#2b2b2b", font=("Segoe UI", 20)).pack(expand=True)

# Come to the front like a pop-up would, but don't stay topmost: the Explorer
# has to be able to put the game back above this window.
root.attributes("-topmost", True)
root.after(300, lambda: root.attributes("-topmost", False))
root.lift()
root.focus_force()
print(f"opened {time.time():.3f}", flush=True)
root.after(int(hold * 1000), root.destroy)
root.mainloop()
print(f"closed {time.time():.3f}", flush=True)
