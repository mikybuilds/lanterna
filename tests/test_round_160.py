"""Round 160: Godot 4 games, websites with a design and bigger projects. Godot's files are checked without Godot
(godot.py), a new game or site starts from files that already work (starters.py, project_start), and project_check
also notes what isn't a mistake but matters (a page tiny on a phone, text hard to read, a library Python lacks)."""
import json
import re
from pathlib import Path

import pytest

from lanterna import chat, godot, i18n, projects, starters, thinking
from lanterna.projects import Projects, check_text, contrast, notes_for
from lanterna.tools import GROUPS
from lanterna.workspace import WorkError

LOCALE = Path(projects.__file__).parent / "locale"


@pytest.fixture()
def pr(tmp_path):
    return Projects(root=lambda: tmp_path / "Lanterna projects", opener=lambda p: None)


def lines(problems):
    return [int(re.match(r"line (\d+)", p).group(1)) for p in problems]


# ---------------------------------------------------------------- GDScript
GOOD = '''extends CharacterBody2D

## How fast the player runs and jumps (pixels per second).
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
'''

OLD = '''extends KinematicBody2D
export var speed = 200
onready var sprite = $Sprite
var velocity = Vector2()
func _physics_process(delta):
\tvelocity = move_and_slide(velocity, Vector2.UP)
\tyield(get_tree().create_timer(1), "timeout")
\tvar b = Bullet.instance()
\tconnect("pressed", self, "_on_pressed")
'''


def test_godot_4_code_passes():
    assert godot.gdscript(GOOD) == []
    assert check_text("player.gd", GOOD) == []


def test_godot_3_words_come_back_with_their_godot_4_words_in_line_order():
    out = godot.gdscript(OLD)
    assert lines(out) == [1, 2, 3, 6, 7, 8, 9]
    text = "\n".join(out)
    for old, new in (("KinematicBody2D", "CharacterBody2D"), ("'export var'", "@export"), ("'onready var'", "@onready"),
                     ("move_and_slide()", "set velocity"), ("yield", "await"), (".instance()", ".instantiate()"),
                     ('connect("signal", self, "method")', "signal_name.connect(method)")):
        assert old in text and new in text, old
    assert check_text("old.gd", OLD)[:1] == out[:1]          # project_check says the same


def test_tabs_and_spaces_are_checked_where_godot_checks_them():
    mixed = ("func f():\n\tif a:\n\t\tpass\n    var x = 1\n\tvar arr = [\n        1,\n    2]\n\t\"\"\"doc\n    inside\n"
             "  \"\"\"\n")
    out = godot.gdscript(mixed)
    assert lines(out) == [4] and "spaces" in out[0] and "tabs" in out[0]   # not inside [ ] or a text
    assert lines(godot.gdscript("func f():\n\t \tpass\n")) == [2]


def test_words_in_texts_comments_and_own_classes_are_left_alone():
    assert godot.gdscript('func f():\n\tprint("KinematicBody2D yield(")  # export var Spatial\n\tvar s = \'onready\'\n') == []
    own = godot.gdscript("class_name World\nextends Node2D\nvar w: World\nfunc g(a: Area) -> void:\n\tpass\n")
    assert lines(own) == [4] and "Area3D" in own[0]


def test_a_body_that_has_velocity_already():
    out = godot.gdscript("extends CharacterBody3D\nvar velocity = Vector3.ZERO\nvar speed = 2\n")
    assert lines(out) == [2] and "velocity" in out[0]
    assert godot.gdscript("extends RigidBody2D\nvar velocity = Vector2.ZERO\n") == []


# ---------------------------------------------------------------- project.godot and scenes
def make_game(tmp_path):
    base = tmp_path / "Game"
    (base / "scenes").mkdir(parents=True)
    (base / "project.godot").write_text('config_version=5\n\n[application]\n\nconfig/name="Game"\n'
                                        'run/main_scene="res://scenes/main.tscn"\n', encoding="utf-8")
    return base


def test_the_project_file(tmp_path):
    base = make_game(tmp_path)
    body = (base / "project.godot").read_text(encoding="utf-8")
    out = godot.project_file(body, base, base)
    assert lines(out) == [6] and "res://scenes/main.tscn" in out[0]
    (base / "scenes" / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n',
                                               encoding="utf-8")
    assert godot.project_file(body, base, base) == []
    old = godot.project_file('config_version=4\n[application]\nrun/main_scene="res://scenes/main.tscn"\n[input]\n'
                             'ui_x={\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"scancode":65)]\n}\n', base, base)
    assert len(old) == 2 and "config_version=5" in old[0] and "physical_keycode" in old[1]
    none = godot.project_file('[application]\nconfig/name="x"\n', base, base)
    assert len(none) == 2 and "config_version=5" in none[0] and "run/main_scene" in none[1]


def test_paths_in_code_must_be_in_the_project(tmp_path):
    base = make_game(tmp_path)
    (base / "scenes" / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n',
                                               encoding="utf-8")
    code = 'extends Node2D\nvar b = preload("res://scenes/bullet.tscn")\nvar m = load("res://scenes/main.tscn")\n'
    out = godot.gdscript(code, base, base / "scenes")
    assert lines(out) == [2] and "bullet.tscn" in out[0]


SCENE = '''[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://player.gd" id="1_s"]
[ext_resource type="PackedScene" path="res://scenes/main.tscn" id="2_m"]

[sub_resource type="RectangleShape2D" id="Rect_1"]
size = Vector2(32, 48)

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_s")

[node name="Shape" type="CollisionShape2D" parent="."]
shape = SubResource("Rect_1")

[node name="Look" type="Polygon2D" parent="."]
polygon = PackedVector2Array(-16, -24, 16, -24, 16, 24, -16, 24)

[node name="Level" parent="." instance=ExtResource("2_m")]

[node name="Deep" type="Node2D" parent="Level/Inside"]

[node name="Bad" type="KinematicBody2D" parent="Nowhere"]
shape = SubResource("Rect_9")

[connection signal="body_entered" from="Shape" to="." method="_on_hit"]
'''


def test_a_scene_is_checked_like_godot_reads_it(tmp_path):
    base = make_game(tmp_path)
    (base / "scenes" / "main.tscn").write_text('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n',
                                               encoding="utf-8")
    out = godot.scene(SCENE, "gd_scene", base, base / "scenes")
    assert lines(out) == [3, 22, 22, 23]                 # a node under an instanced scene ("Level/Inside") is fine
    text = "\n".join(out)
    assert "res://player.gd" in text and "CharacterBody2D" in text and 'parent="Nowhere"' in text and "Rect_9" in text
    assert check_text("player.tscn", SCENE, base, base / "scenes") == out


def test_godot_3_scenes_cut_files_and_other_files():
    g3 = godot.scene('[gd_scene load_steps=2 format=2]\n\n[ext_resource path="res://a.gd" type="Script" id=1]\n\n'
                     '[node name="A" type="KinematicBody2D"]\nscript = ExtResource( 1 )\n', "gd_scene")
    assert len(g3) == 1 and "format=3" in g3[0]
    assert "[gd_scene format=3]" in godot.scene("hello", "gd_scene")[0]
    assert godot.scene('[gd_resource type="Theme" format=3]\n\n[resource]\ndefault_font_size = 18\n', "gd_resource") == []
    cut = godot.scene('[gd_scene format=3]\n\n[node name="A" type="Node2D"]\nposition = Vector2(1, 2\n', "gd_scene")
    assert lines(cut) == [4] and "never closed" in cut[0]
    builtin = ('[gd_scene format=3]\n\n[sub_resource type="GDScript" id="G_1"]\nscript/source = "extends Node\n'
               '[node name=\\"x\\"]\nfunc _ready():\n\tpass\n"\n\n[node name="A" type="Node" ]\nscript = SubResource("G_1")\n')
    assert godot.scene(builtin, "gd_scene") == []         # a script kept inside the scene is a text, not sections


def test_godot_files_are_project_files():
    for ext in (".godot", ".tscn", ".tres", ".gd", ".gdshader"):
        assert ext in projects.CHECKED, ext
    assert check_text("water.gdshader", "shader_type canvas_item;\nvoid fragment() {\n\tCOLOR = vec4(1.0);\n")
    assert check_text("water.gdshader", "shader_type canvas_item;\nvoid fragment() {\n\tCOLOR = vec4(1.0);\n}\n") == []


# ---------------------------------------------------------------- starters
@pytest.mark.parametrize("kind", list(starters.KITS))
def test_every_starter_passes_the_check_with_no_notes(pr, kind):
    out = pr.start(f"Test {kind}", kind, "uk")
    files = starters.files(kind, f"Test {kind}", "uk")
    for path in files:
        assert (pr.folder(f"Test {kind}") / path).is_file(), path
        assert path in out
    assert not any(p.endswith(".js") for p in files)
    report = pr.check(f"Test {kind}")
    assert "no mistakes found" in report and "Not mistakes" not in report, report
    assert starters.KITS[kind].split(":")[0] in out


def test_godot_starters_are_godot_4(pr):
    for kind in ("godot-2d", "godot-3d"):
        f = starters.files(kind, 'Гра "Зірка"', "uk")
        assert "config_version=5" in f["project.godot"] and 'config/name="Гра \\"Зірка\\""' in f["project.godot"]
        assert f["main.tscn"].startswith("[gd_scene") and "format=3" in f["main.tscn"].splitlines()[0]
        assert "\n\t" in f["player.gd"] and "\n    " not in f["player.gd"]       # tabs, as Godot writes
        assert "move_and_slide()" in f["player.gd"] and "@export" in f["player.gd"]
    assert "godotengine.org" in starters.KITS["godot-3d"] and "project.godot" in starters.KITS["godot-2d"]


def test_a_starter_speaks_the_users_language_and_escapes_the_name(pr):
    game = starters.files("web-game", "Tom & Jerry", "uk")["index.html"]
    assert 'lang="uk"' in game and "Рахунок" in game and "Tom &amp; Jerry" in game and "Tom & Jerry" not in game
    assert 'lang="en"' in starters.files("website", "x", "")["index.html"]
    assert 'lang="en"' in starters.files("website", "x", '"><script>')["index.html"]     # not a language: English
    site = pr.start("Кав'ярня & чай", "website", "uk")
    assert "Кав'ярня &amp; чай" in (pr.folder("Кав'ярня & чай") / "index.html").read_text(encoding="utf-8")
    assert "no mistakes found" in pr.check("Кав'ярня & чай") and "style.css" in site


def test_a_starter_goes_only_into_a_new_project(pr):
    pr.write("Mine", "notes.txt", "my own text")
    with pytest.raises(WorkError, match="already has files"):
        pr.start("Mine", "website")
    assert (pr.folder("Mine") / "notes.txt").read_text(encoding="utf-8") == "my own text"
    with pytest.raises(WorkError, match="godot-2d"):
        pr.start("New", "unity")
    assert not pr.folder("New").exists()


def test_the_tool_starts_a_project_in_the_apps_language(pr):
    tools = {t.name: t for t in projects.project_tools(pr, lang=lambda: "it")}
    start = tools["project_start"]
    assert start.parameters["properties"]["kind"]["enum"] == list(starters.KITS)
    assert start.parameters["required"] == ["project", "kind"]
    out = start.run(project="Gioco", kind="web-game")
    assert "Punti" in (pr.folder("Gioco") / "index.html").read_text(encoding="utf-8") and "index.html" in out
    assert list(tools)[0] == "project_start"
    assert "Godot 4" in tools["project_check"].description and "notes" in tools["project_check"].description


# ---------------------------------------------------------------- notes
PAGE = '''<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Кав'ярня</title>
</head>
<body><img src="cup.svg" alt="Чашка"></body>
</html>
'''


def test_a_page_gets_notes_on_what_a_person_notices():
    assert notes_for("index.html", PAGE) == []
    bare = notes_for("index.html", "<!DOCTYPE html>\n<html>\n<body><img src='a.png'><p>Lorem ipsum dolor</p></body>\n</html>")
    text = "\n".join(bare)
    for word in ("viewport", "lang", "<title>", "alt", "lorem ipsum"):
        assert word in text, word
    assert notes_for("part.html", "<p>a piece</p>") == []           # a piece of a page has no head to check


def test_styles_get_notes_on_contrast_tiny_text_and_fixed_widths():
    assert round(contrast((0, 0, 0), (255, 255, 255))) == 21
    css = ":root { --ink: #777; --bg: #888; }\nbody { color: var(--ink); background: var(--bg); }\n"
    out = notes_for("style.css", css)
    assert lines(out) == [2] and "contrast" in out[0] and "4.5" in out[0]
    assert notes_for("style.css", "body { color: #222; background: #fff; }") == []
    tiny = notes_for("style.css", "p { font-size: 10px; }")
    assert lines(tiny) == [1] and "12px" in tiny[0]
    wide = notes_for("style.css", ".page { width: 960px; }")
    assert len(wide) == 1 and "max-width: 960px" in wide[0]
    assert notes_for("style.css", ".page { width: 960px; }\n@media (max-width: 600px) { .page { width: auto; } }") == []
    inside = notes_for("index.html", PAGE.replace("</head>", "<style>\np { font-size: 9px; }\n</style>\n</head>"))
    assert lines(inside) == [8] and "9px" in inside[0]


def test_a_python_program_gets_a_note_on_what_python_lacks(tmp_path):
    base = tmp_path / "P"
    base.mkdir()
    (base / "helper.py").write_text("X = 1\n", encoding="utf-8")
    code = "import json\nimport tkinter\nimport helper\nimport requests\nfrom PIL import Image\n"
    out = notes_for("main.py", code, base, base)
    assert len(out) == 1 and "requests" in out[0] and "pillow" in out[0] and "pip install pillow requests" in out[0]
    (base / "requirements.txt").write_text("requests>=2.31  # the web\nPillow\n", encoding="utf-8")
    assert notes_for("main.py", code, base, base) == []
    assert notes_for("main.py", "import json\n", base, base) == []
    assert notes_for("main.py", "def (:\n", base, base) == []        # a mistake is project_check's, not a note


def test_check_lists_notes_apart_from_mistakes(pr):
    pr.write("Site", "index.html", "<!DOCTYPE html>\n<html>\n<body><p>Lorem ipsum</p></body>\n</html>\n")
    report = pr.check("Site")
    assert "no mistakes found" in report and "Not mistakes" in report and "viewport" in report
    assert report.index("index.html: OK") < report.index("Not mistakes")


# ---------------------------------------------------------------- how the model is told
def test_the_tool_text_and_its_translations():
    text = thinking.TOOL_TEXT["project_start"][0]
    assert thinking.TOOL_TEXT["project_start"][1] == "project" and "{x}" in text
    assert i18n._T[text]["uk"] and i18n._T[text]["it"]
    for lang in ("de", "es", "fr", "pl"):
        assert "{x}" in json.loads((LOCALE / f"{lang}.json").read_text(encoding="utf-8"))[text], lang
    assert "project_start" in chat.CHANGES_FILES


def test_the_guide_speaks_of_godot_4_sites_and_bigger_projects():
    g = chat.PROJECT_GUIDE
    for word in ("project_start", "Godot 4", "@export", "format=3", "style.css", "lorem ipsum", "README.md",
                 "phone", "Unity"):
        assert word in g, word


def test_engines_and_site_design_bring_the_project_tools():
    rx = GROUPS["make"]
    for q in ("зроби гру на двіжку Godot", "гра на рушії", "напиши скрипт на GDScript", "web design for my bakery",
              "портфоліо для фотографа", "дизайн сайту для кав'ярні", "a pygame snake", "щось на Unreal",
              "гру на юніті"):
        assert rx.search(q), q
    for q in ("яка погода завтра?", "погодою на вихідних", "привіт"):
        assert not rx.search(q), q
