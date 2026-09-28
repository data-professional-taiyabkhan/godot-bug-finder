# Planted bug 1 is in level.tscn, not in this script: the ShortcutLedge
# platform's collision shape sits 32 px right of its sprite (position
# (32, -7.5) instead of (0, -7.5)), so the left 32 px of the ledge, world
# x 284-315, cannot be stood on. Jump onto its left edge and you fall through.
#
# This script is not attached to any scene (nor is it in the upstream Godot
# demo), so nothing below actually runs.

extends Node2D

const LIMIT_LEFT = -315
const LIMIT_TOP = -250
const LIMIT_RIGHT = 955
const LIMIT_BOTTOM = 690


func _ready():
	for child in get_children():
		if child is Player:
			var camera = child.get_node(^"Camera")
			camera.limit_left = LIMIT_LEFT
			camera.limit_top = LIMIT_TOP
			camera.limit_right = LIMIT_RIGHT
			camera.limit_bottom = LIMIT_BOTTOM
