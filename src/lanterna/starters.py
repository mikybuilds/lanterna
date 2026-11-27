"""Starters: the first files of a new project, written by Lanterna itself and checked by the tests.

A model makes its fewest mistakes when it builds on files that already work. Godot's scene files are the easiest to
get wrong (ids, parents, Godot 3 names), and a site looks calmer when it starts from one set of colors and sizes,
so the model can start a project from one of these and change it (projects.Projects.start). Only text files, all
inside the project's folder, through the same project_write rules.
"""
from __future__ import annotations

import datetime as dt
import html

# what the model is told after starting (the files are listed by projects.Projects.start)
GODOT_HOW = ("To play it, the user installs Godot 4 (free, godotengine.org), presses Import in its Project Manager, "
             "picks project.godot in {folder} and presses Run (F5). Build the user's game on these files: change "
             "and add to them (project_read shows them), keep Godot 4's words (@export, @onready, await, "
             "move_and_slide() with the velocity property, signal.connect(method)), scenes in format=3, and check "
             "with project_check.")
KITS = {
    "godot-2d": ("a Godot 4 2D game: a level with ground and a player that runs with the arrows and jumps with "
                 "Space or Enter (Godot's ui_left, ui_right, ui_accept). " + GODOT_HOW),
    "godot-3d": ("a Godot 4 3D game: a floor, light, sky color and a player (a capsule with a camera behind it) "
                 "that walks with the arrows and jumps with Space or Enter. " + GODOT_HOW),
    "website": ("a website: index.html with style.css, which holds the look of every page (colors in :root with a "
                "dark theme, type sizes, spacing, .wrap, .grid, .card, .btn and .btn.primary, forms). Write the "
                "user's real content in their language with these classes; a new page links the same style.css "
                "and gets a link in a <nav> in the header. Keep scripts inside the pages (<script>…</script>)."),
    "web-game": ("a browser game in one index.html: a canvas, the keyboard (arrows or WASD), a game loop with "
                 "requestAnimationFrame and a coin to collect with a score. Build the user's game on it; the words "
                 "the player sees are in WORDS at the top of the script."),
}
_SCORE = {"en": "Score", "uk": "Рахунок", "it": "Punti", "de": "Punkte", "es": "Puntos", "fr": "Score",
          "pl": "Wynik"}


def files(kind: str, name: str, lang: str = "") -> dict[str, str]:
    """The starter's files: {path in the project: text}. name: the project's name (shown in the game or site)."""
    lang = (lang or "en").strip().lower()[:8] or "en"
    lang = lang if all(c.isalnum() or c == "-" for c in lang) else "en"
    godot_name = name.replace("\\", "\\\\").replace('"', '\\"')
    page_name = html.escape(name, quote=False).replace('"', "&quot;")   # an apostrophe stays as it is (м'яч)
    fill = {"__NAME__": godot_name if kind.startswith("godot") else page_name, "__LANG__": lang,
            "__YEAR__": str(dt.date.today().year), "__SCORE__": _SCORE.get(lang.split("-")[0], "Score")}
    out = {}
    for path, text in _FILES[kind].items():
        for k, v in fill.items():
            text = text.replace(k, v)
        out[path] = text
    return out


_PROJECT = """; A Godot 4 project: open this folder in Godot 4 (Project Manager → Import → project.godot).

config_version=5

[application]

config/name="__NAME__"
run/main_scene="res://main.tscn"

[display]

window/size/viewport_width=1152
window/size/viewport_height=648
window/stretch/mode="canvas_items"

[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
"""

_MAIN_2D = """[gd_scene load_steps=3 format=3]

[ext_resource type="PackedScene" path="res://player.tscn" id="1_player"]

[sub_resource type="RectangleShape2D" id="RectangleShape2D_ground"]
size = Vector2(1152, 48)

[node name="Main" type="Node2D"]

[node name="Ground" type="StaticBody2D" parent="."]
position = Vector2(576, 624)

[node name="Shape" type="CollisionShape2D" parent="Ground"]
shape = SubResource("RectangleShape2D_ground")

[node name="Look" type="Polygon2D" parent="Ground"]
color = Color(0.25, 0.28, 0.33, 1)
polygon = PackedVector2Array(-576, -24, 576, -24, 576, 24, -576, 24)

[node name="Player" parent="." instance=ExtResource("1_player")]
position = Vector2(576, 400)
"""

_PLAYER_2D = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://player.gd" id="1_script"]

[sub_resource type="RectangleShape2D" id="RectangleShape2D_player"]
size = Vector2(32, 48)

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_script")

[node name="Shape" type="CollisionShape2D" parent="."]
shape = SubResource("RectangleShape2D_player")

[node name="Look" type="Polygon2D" parent="."]
color = Color(0.96, 0.71, 0.27, 1)
polygon = PackedVector2Array(-16, -24, 16, -24, 16, 24, -16, 24)
"""

_SCRIPT_2D = """extends CharacterBody2D

## How fast the player runs and jumps, in pixels per second.
@export var speed := 300.0
@export var jump_speed := 520.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")


func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity.y += gravity * delta
\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = -jump_speed
\tvar direction := Input.get_axis("ui_left", "ui_right")
\tvelocity.x = direction * speed
\tmove_and_slide()
"""

_MAIN_3D = """[gd_scene load_steps=6 format=3]

[ext_resource type="PackedScene" path="res://player.tscn" id="1_player"]

[sub_resource type="BoxShape3D" id="BoxShape3D_floor"]
size = Vector3(20, 1, 20)

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_floor"]
albedo_color = Color(0.3, 0.34, 0.4, 1)

[sub_resource type="BoxMesh" id="BoxMesh_floor"]
material = SubResource("StandardMaterial3D_floor")
size = Vector3(20, 1, 20)

[sub_resource type="Environment" id="Environment_sky"]
background_mode = 1
background_color = Color(0.55, 0.7, 0.85, 1)
ambient_light_source = 2
ambient_light_color = Color(0.6, 0.65, 0.7, 1)

[node name="Main" type="Node3D"]

[node name="Floor" type="StaticBody3D" parent="."]
position = Vector3(0, -0.5, 0)

[node name="Shape" type="CollisionShape3D" parent="Floor"]
shape = SubResource("BoxShape3D_floor")

[node name="Look" type="MeshInstance3D" parent="Floor"]
mesh = SubResource("BoxMesh_floor")

[node name="Sun" type="DirectionalLight3D" parent="."]
rotation_degrees = Vector3(-50, 30, 0)
shadow_enabled = true

[node name="Sky" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_sky")

[node name="Player" parent="." instance=ExtResource("1_player")]
position = Vector3(0, 0.5, 0)
"""

_PLAYER_3D = """[gd_scene load_steps=5 format=3]

[ext_resource type="Script" path="res://player.gd" id="1_script"]

[sub_resource type="CapsuleShape3D" id="CapsuleShape3D_player"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_player"]
albedo_color = Color(0.96, 0.71, 0.27, 1)

[sub_resource type="CapsuleMesh" id="CapsuleMesh_player"]
material = SubResource("StandardMaterial3D_player")

[node name="Player" type="CharacterBody3D"]
script = ExtResource("1_script")

[node name="Shape" type="CollisionShape3D" parent="."]
position = Vector3(0, 1, 0)
shape = SubResource("CapsuleShape3D_player")

[node name="Look" type="MeshInstance3D" parent="."]
position = Vector3(0, 1, 0)
mesh = SubResource("CapsuleMesh_player")

[node name="Camera" type="Camera3D" parent="."]
position = Vector3(0, 3.5, 6)
rotation_degrees = Vector3(-20, 0, 0)
"""

_SCRIPT_3D = """extends CharacterBody3D

## How fast the player walks and jumps, in meters per second.
@export var speed := 5.0
@export var jump_speed := 4.5

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity.y -= gravity * delta
\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = jump_speed
\tvar input_dir := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
\tvar direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
\tif direction:
\t\tvelocity.x = direction.x * speed
\t\tvelocity.z = direction.z * speed
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, speed)
\t\tvelocity.z = move_toward(velocity.z, 0, speed)
\tmove_and_slide()
"""

_SITE_PAGE = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top">
  <div class="wrap top-in">
    <a class="brand" href="index.html">__NAME__</a>
  </div>
</header>
<main>
  <div class="wrap">
    <section class="hero">
      <h1>__NAME__</h1>
    </section>
  </div>
</main>
<footer class="foot">
  <div class="wrap">© __YEAR__ __NAME__</div>
</footer>
</body>
</html>
"""

_SITE_STYLE = """/* The look of every page. Change the colors and sizes here, in :root, and the whole site follows. */
:root {
  --bg: #ffffff;
  --surface: #f5f5f4;
  --text: #1c1917;
  --muted: #57534e;
  --line: #e7e5e4;
  --accent: #b45309;
  --on-accent: #ffffff;
  --radius: 8px;
  --s1: 4px;
  --s2: 8px;
  --s3: 12px;
  --s4: 16px;
  --s5: 24px;
  --s6: 32px;
  --s7: 48px;
  --s8: 64px;
  --max: 1080px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141210;
    --surface: #1f1c19;
    --text: #f2efec;
    --muted: #a8a29e;
    --line: #33302c;
    --accent: #f59e0b;
    --on-accent: #141210;
  }
}
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 400 16px/1.6 var(--font); }
img, svg, video, canvas { display: block; max-width: 100%; height: auto; }
a { color: var(--accent); text-underline-offset: 2px; }
a:hover { text-decoration-thickness: 2px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
h1, h2, h3 { margin: 0 0 var(--s4); line-height: 1.2; font-weight: 700; letter-spacing: -0.01em; }
h1 { font-size: clamp(2rem, 1.4rem + 2.4vw, 3rem); }
h2 { font-size: clamp(1.5rem, 1.2rem + 1.2vw, 2rem); }
h3 { font-size: 1.25rem; }
p { margin: 0 0 var(--s4); max-width: 68ch; }
.muted { color: var(--muted); }
.wrap { width: 100%; max-width: var(--max); margin: 0 auto; padding: 0 var(--s4); }
.top { border-bottom: 1px solid var(--line); }
.top-in { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--s4); min-height: 64px; }
.brand { color: var(--text); font-weight: 700; text-decoration: none; }
.top nav { display: flex; flex-wrap: wrap; gap: var(--s4); }
.top nav a { color: var(--muted); text-decoration: none; }
.top nav a:hover, .top nav a[aria-current="page"] { color: var(--text); }
main { padding: var(--s7) 0; }
section { margin-bottom: var(--s8); }
.hero { padding: var(--s6) 0; }
.grid { display: grid; gap: var(--s4); grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.card { padding: var(--s5); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--s2); min-height: 44px; padding: 0 var(--s5);
  background: var(--surface); color: var(--text); border: 1px solid var(--line); border-radius: var(--radius);
  font: inherit; font-weight: 600; text-decoration: none; cursor: pointer; }
.btn.primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
label { display: block; margin-bottom: var(--s1); font-weight: 600; }
input, textarea, select { width: 100%; min-height: 44px; padding: var(--s2) var(--s3); background: var(--bg); color: var(--text);
  border: 1px solid var(--line); border-radius: var(--radius); font: inherit; }
.foot { padding: var(--s5) 0; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""

_GAME = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__</title>
<style>
  :root { --bg: #14161a; --field: #1d2026; --text: #ece9e4; --player: #f5b544; --coin: #7cc4ff; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { display: grid; place-items: center; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }
  canvas { display: block; width: min(100vw, 960px); height: auto; aspect-ratio: 16 / 9; background: var(--field); }
  .hud { position: fixed; top: 12px; left: 16px; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<canvas id="game" width="960" height="540" aria-label="__NAME__"></canvas>
<div class="hud" id="hud"></div>
<script>
"use strict";
// The words the player sees.
const WORDS = { score: "__SCORE__" };
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const hud = document.getElementById("hud");
const W = canvas.width, H = canvas.height;
const css = getComputedStyle(document.documentElement);
const COLORS = { player: css.getPropertyValue("--player").trim(), coin: css.getPropertyValue("--coin").trim() };

const keys = new Set();
addEventListener("keydown", (e) => {
  keys.add(e.key.toLowerCase());
  if (e.key.startsWith("Arrow") || e.key === " ") e.preventDefault();
});
addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));
addEventListener("blur", () => keys.clear());

const player = { x: W / 2, y: H / 2, r: 16, speed: 280 };
const coin = { x: 0, y: 0, r: 10 };
let score = 0;

function placeCoin() {
  coin.x = 40 + Math.random() * (W - 80);
  coin.y = 40 + Math.random() * (H - 80);
}

function update(dt) {
  let dx = 0, dy = 0;
  if (keys.has("arrowleft") || keys.has("a")) dx -= 1;
  if (keys.has("arrowright") || keys.has("d")) dx += 1;
  if (keys.has("arrowup") || keys.has("w")) dy -= 1;
  if (keys.has("arrowdown") || keys.has("s")) dy += 1;
  const len = Math.hypot(dx, dy) || 1;
  player.x = Math.max(player.r, Math.min(W - player.r, player.x + (dx / len) * player.speed * dt));
  player.y = Math.max(player.r, Math.min(H - player.r, player.y + (dy / len) * player.speed * dt));
  if (Math.hypot(player.x - coin.x, player.y - coin.y) < player.r + coin.r) {
    score += 1;
    placeCoin();
  }
}

function circle(x, y, r, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

function draw() {
  ctx.clearRect(0, 0, W, H);
  circle(coin.x, coin.y, coin.r, COLORS.coin);
  circle(player.x, player.y, player.r, COLORS.player);
  hud.textContent = `${WORDS.score}: ${score}`;
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  update(dt);
  draw();
  requestAnimationFrame(frame);
}
placeCoin();
requestAnimationFrame(frame);
</script>
</body>
</html>
"""

_FILES = {
    "godot-2d": {"project.godot": _PROJECT, "main.tscn": _MAIN_2D, "player.tscn": _PLAYER_2D, "player.gd": _SCRIPT_2D},
    "godot-3d": {"project.godot": _PROJECT, "main.tscn": _MAIN_3D, "player.tscn": _PLAYER_3D, "player.gd": _SCRIPT_3D},
    "website": {"index.html": _SITE_PAGE, "style.css": _SITE_STYLE},
    "web-game": {"index.html": _GAME},
}
