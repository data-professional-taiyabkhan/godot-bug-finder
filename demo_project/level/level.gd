# =============================================================================
# BUG INJECTED: ShortcutLedge — collision / visual misalignment (level.tscn)
# =============================================================================
#
# DESCRIPTION
# -----------
# A "ShortcutLedge" StaticBody2D was added to level.tscn at Vector2(380, 450)
# as a helpful stepping-stone between the spawn ground (~y=636) and the first
# floating mid-tier platform (~y=370).  The node uses the same moving_platform
# texture as the real platforms so it blends in visually.
#
# The CollisionShape2D child was accidentally given a local offset of
#   Vector2(32, -7.5)   ← BUG (should be Vector2(0, -7.5))
# The 32-pixel rightward shift means the leftmost 32 px of the 192-px-wide
# sprite have NO backing collision.  In world space the "phantom" strip is:
#   x = 380 - 96       = 284   (left edge of visual)
#   x = 380 + 32 - 96  = 316   (left edge of collision)
#   gap width = 316 - 284 = 32 px
#
# ROOT CAUSE
# ----------
# Developer miscounted by one tile-width (32 px) when placing the shape in
# the Godot inspector.  The property was set to (32, -7.5) instead of (0, -7.5).
#
# REPRODUCTION STEPS
# ------------------
#   1. Launch the game (game_singleplayer.tscn).
#      Player spawns at approximately (90, 636).
#   2. Run RIGHT without jumping to build horizontal momentum.
#   3. At approximately world-x = 250 begin a SINGLE jump (W / Up arrow).
#   4. Aim to land on the LEFT EDGE of the floating dark ledge that appears
#      around (284, 450) — the leftmost part of the platform sprite.
#   5. EXPECTED: the player lands solidly on the ledge.
#      ACTUAL  : if the horizontal landing position is in the range x = 284..315,
#                the player clips straight through and falls back to ground level.
#   6. CONTROL: jump again and land further right (x > 316).
#              The player lands normally on the right two-thirds of the platform.
#
# FIX
# ---
#   In level.tscn, change ShortcutLedge/CollisionShape2D:
#     position = Vector2(32, -7.5)   →   position = Vector2(0, -7.5)
#
# AFFECTED NODE
# -------------
#   Level → ShortcutLedge → CollisionShape2D   (level.tscn, near end of file)
# =============================================================================

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
