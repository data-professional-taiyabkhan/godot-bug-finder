# Planted bug 2: a timed soft-lock.
#
# 30 s after start the game pauses itself (get_tree().paused = true) without
# opening the pause menu. It keeps rendering, but nothing responds. The point
# is ground truth for the Inspector: if GBF_EVENT_LOG is set, the moment it
# fires is written there so run_demo.py can score the run.
#
# GBF_SOFTLOCK=0 turns it off (run_demo.py --clean); GBF_SOFTLOCK_AFTER_MS
# changes the delay. Attached to the PlantedBugs node in
# game_singleplayer.tscn, not to level.gd: as in the upstream demo, level.gd
# is not attached to any scene, so code there never runs.

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
