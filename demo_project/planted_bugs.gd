# =============================================================================
# PLANTED BUG 2 (27 Sep 2026): timed soft-lock — the game pauses itself
# =============================================================================
#
# DESCRIPTION
# -----------
# 30 s after the game starts, it calls get_tree().paused = true WITHOUT opening
# the pause menu. The screen keeps rendering, but nothing moves and no input
# does anything: a soft-lock. If GBF_EVENT_LOG is set, the moment it fires is
# written there, so a run can be scored against it.
#
# WHY IT EXISTS
# -------------
# Ground truth for the Inspector. Bug 1 (the ShortcutLedge in level.tscn) is
# invisible to pixel differences, so it cannot test whether the detectors work.
# This one should show up as a "frozen" anomaly that CLIP still labels as the
# game, i.e. a game bug rather than a harness failure.
#
# It is a fault injection on a timer, so it tests inspection and triage, not
# exploration. An earlier version fired only when the player stood in a zone
# near the spawn point; it lived in level.gd, which (as in the upstream Godot
# demo) is not attached to any scene, so it never ran. This file is attached
# to the "PlantedBugs" node in game_singleplayer.tscn.
#
# SETTINGS (environment variables)
# --------------------------------
#   GBF_SOFTLOCK=0             turn it off (run_demo.py --clean does this)
#   GBF_SOFTLOCK_AFTER_MS=500  change the delay (used for quick checks)
#   GBF_EVENT_LOG=<path>       where to write the ground-truth event
# =============================================================================

extends Node

const SOFTLOCK_AFTER_MS = 30000


func _ready() -> void:
	if OS.get_environment("GBF_SOFTLOCK") == "0":
		return
	var after_ms := SOFTLOCK_AFTER_MS
	var override := OS.get_environment("GBF_SOFTLOCK_AFTER_MS")
	if override.is_valid_int():
		after_ms = override.to_int()
	get_tree().create_timer(after_ms / 1000.0).timeout.connect(_trigger_softlock)


func _trigger_softlock() -> void:
	var pos := Vector2.ZERO
	var player := get_node_or_null(^"../Level/Player") as Node2D
	if player != null:
		pos = player.global_position
	print("[planted bug 2] soft-lock at ", pos)
	_log_game_event("softlock", {"x": pos.x, "y": pos.y})
	get_tree().paused = true


func _log_game_event(event_name: String, data: Dictionary) -> void:
	var path := OS.get_environment("GBF_EVENT_LOG")
	if path == "":
		return
	var f := FileAccess.open(path.replace("\\", "/"), FileAccess.WRITE)
	if f == null:
		push_error("planted_bugs.gd: cannot write %s" % path)
		return
	data["event"] = event_name
	data["t"] = Time.get_unix_time_from_system()
	f.store_line(JSON.stringify(data))
	f.close()
