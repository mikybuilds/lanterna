"""Godot 4 files looked over without Godot: GDScript (.gd), the project file (project.godot), scenes (.tscn) and
resources (.tres).

Models learned Godot mostly from Godot 3 examples, and Godot 4 stops at those names (KinematicBody2D, export var,
yield…), at mixed tabs and spaces, at a scene that points to a missing file or a resource id it never declared.
Each mistake comes back as a short sentence with its line, like the other checks in projects.py. Nothing is run.
"""
from __future__ import annotations

import re
from pathlib import Path

# Godot 3 classes and what they are called in Godot 4
CLASSES = {
    "KinematicBody2D": "CharacterBody2D", "KinematicBody": "CharacterBody3D", "Spatial": "Node3D",
    "Position2D": "Marker2D", "Position3D": "Marker3D", "Sprite": "Sprite2D", "AnimatedSprite": "AnimatedSprite2D",
    "Camera": "Camera3D", "MeshInstance": "MeshInstance3D", "CollisionShape": "CollisionShape3D",
    "CollisionPolygon": "CollisionPolygon3D", "RigidBody": "RigidBody3D", "StaticBody": "StaticBody3D",
    "Area": "Area3D", "RayCast": "RayCast3D", "DirectionalLight": "DirectionalLight3D", "OmniLight": "OmniLight3D",
    "SpotLight": "SpotLight3D", "Particles": "GPUParticles3D", "Particles2D": "GPUParticles2D",
    "CPUParticles": "CPUParticles3D", "Path": "Path3D", "PathFollow": "PathFollow3D", "Listener": "AudioListener3D",
    "Skeleton": "Skeleton3D", "ViewportContainer": "SubViewportContainer", "ToolButton": "Button",
    "TextureProgress": "TextureProgressBar", "GIProbe": "VoxelGI", "BakedLightmap": "LightmapGI",
    "VisibilityNotifier2D": "VisibleOnScreenNotifier2D", "VisibilityNotifier": "VisibleOnScreenNotifier3D",
    "VisibilityEnabler2D": "VisibleOnScreenEnabler2D", "YSort": "Node2D with y_sort_enabled = true",
    "SphereShape": "SphereShape3D", "BoxShape": "BoxShape3D", "CapsuleShape": "CapsuleShape3D",
    "CylinderShape": "CylinderShape3D", "ConvexPolygonShape": "ConvexPolygonShape3D",
    "ConcavePolygonShape": "ConcavePolygonShape3D", "RayShape": "SeparationRayShape3D",
    "RayShape2D": "SeparationRayShape2D", "PlaneShape": "WorldBoundaryShape3D", "LineShape2D": "WorldBoundaryShape2D",
    "CubeMesh": "BoxMesh", "Navigation2D": "NavigationRegion2D", "Navigation": "NavigationRegion3D",
    "NavigationMeshInstance": "NavigationRegion3D", "NavigationPolygonInstance": "NavigationRegion2D",
    "SpatialMaterial": "StandardMaterial3D", "World": "World3D", "Joint": "Joint3D", "Reference": "RefCounted",
    "PhysicsServer": "PhysicsServer3D", "Physics2DServer": "PhysicsServer2D", "VisualServer": "RenderingServer",
    "ARVRServer": "XRServer", "ARVROrigin": "XROrigin3D", "ARVRCamera": "XRCamera3D",
    "ARVRController": "XRController3D", "DynamicFont": "FontFile (or SystemFont)", "DynamicFontData": "FontFile",
    "BitmapFont": "FontFile", "StreamTexture": "CompressedTexture2D", "AnimationTreePlayer": "AnimationTree",
    "Tabs": "TabBar", "WindowDialog": "Window", "PopupDialog": "Popup", "HingeJoint": "HingeJoint3D",
    "PinJoint": "PinJoint3D", "SliderJoint": "SliderJoint3D", "ConeTwistJoint": "ConeTwistJoint3D",
    "Generic6DOFJoint": "Generic6DOFJoint3D", "SoftBody": "SoftBody3D", "VehicleBody": "VehicleBody3D",
    "VehicleWheel": "VehicleWheel3D", "RemoteTransform": "RemoteTransform3D", "BoneAttachment": "BoneAttachment3D",
    "SpringArm": "SpringArm3D", "ClippedCamera": "Camera3D", "Light2D": "PointLight2D",
}
# names so distinct that they are Godot 3 wherever they are written; the rest only where a class goes
_ANYWHERE = {"KinematicBody2D", "KinematicBody", "Spatial", "Position2D", "Position3D", "YSort",
             "VisibilityNotifier2D", "VisualServer", "Physics2DServer", "SpatialMaterial", "ToolButton", "GIProbe",
             "AnimationTreePlayer", "ARVRServer"}
_NOT_IN_CODE = {"Light2D", "Tabs", "World", "Path", "Joint"}   # still a word in Godot 4 code (a base class, a word)
# Godot 3 ways of writing code: (pattern in the code outside texts and comments, what to write in Godot 4)
CODE = (
    (r"(?m)^[ \t]*export\b", "'export var' is '@export var' in Godot 4 (export(int) var x → @export var x: int)"),
    (r"(?m)^[ \t]*onready\b", "'onready var' is '@onready var' in Godot 4"),
    (r"(?m)^[ \t]*tool[ \t]*$", "'tool' is '@tool' in Godot 4"),
    (r"(?m)^[ \t]*(remote|master|puppet|remotesync|mastersync|puppetsync)[ \t]+func\b",
     "remote/master/puppet func is '@rpc func' in Godot 4"),
    (r"\byield\s*\(", "yield(…) is await in Godot 4, e.g. await get_tree().create_timer(1.0).timeout"),
    (r"\.instance\s*\(\s*\)", ".instance() is .instantiate() in Godot 4"),
    (r"\bmove_and_slide\s*\(\s*[^)\s]", "move_and_slide() takes nothing in Godot 4: set velocity, then call "
                                        "move_and_slide()"),
    (r"\bmove_and_slide_with_snap\s*\(", "move_and_slide_with_snap() is gone in Godot 4: floor_snap_length, then "
                                         "move_and_slide()"),
    (r"\bconnect\s*\(\s*\"[^\"\n]*\"\s*,\s*self\s*,", "connect(\"signal\", self, \"method\") is "
                                                      "signal_name.connect(method) in Godot 4"),
    (r"\bsetget\b", "setget is gone in Godot 4: var x: set = _set_x, get = _get_x"),
    (r"\brand_range\s*\(", "rand_range() is randf_range() in Godot 4"),
    (r"\bstepify\s*\(", "stepify() is snapped() in Godot 4"),
    (r"\bdeg2rad\s*\(", "deg2rad() is deg_to_rad() in Godot 4"),
    (r"\brad2deg\s*\(", "rad2deg() is rad_to_deg() in Godot 4"),
    (r"\b(str2var|var2str|bytes2var|var2bytes)\s*\(", "str2var(), var2str() are str_to_var(), var_to_str() in "
                                                       "Godot 4"),
    (r"\blinear_interpolate\s*\(", "linear_interpolate() is lerp() in Godot 4"),
    (r"\bchange_scene\s*\(", "change_scene() is change_scene_to_file() in Godot 4"),
    (r"\bOS\s*\.\s*get_(ticks_msec|ticks_usec|unix_time|time|date|datetime)\s*\(",
     "OS.get_ticks_msec() and the like are in Time in Godot 4: Time.get_ticks_msec(), "
     "Time.get_datetime_dict_from_system()"),
    (r"\bFile\s*\.\s*new\s*\(", "File.new() is gone in Godot 4: FileAccess.open(path, FileAccess.READ)"),
    (r"\bDirectory\s*\.\s*new\s*\(", "Directory.new() is gone in Godot 4: DirAccess.open(path)"),
    (r"\bTween\s*\.\s*new\s*\(", "Tween.new() doesn't work in Godot 4: create_tween()"),
    (r"\bBUTTON_(LEFT|RIGHT|MIDDLE|WHEEL_UP|WHEEL_DOWN)\b", "BUTTON_LEFT is MOUSE_BUTTON_LEFT in Godot 4"),
    (r"\bKEY_CONTROL\b", "KEY_CONTROL is KEY_CTRL in Godot 4"),
    (r"\.scancode\b", ".scancode is .keycode in Godot 4"),
    (r"\.empty\s*\(\s*\)", ".empty() is .is_empty() in Godot 4"),
    (r"\b(set|get)_cellv\s*\(", "set_cellv() is gone in Godot 4: set_cell(coords, source_id, atlas_coords) on a "
                                "TileMapLayer"),
    (r"\brect_(position|size|min_size|rotation|scale|pivot_offset|global_position)\b",
     "rect_size and the like are size, position, custom_minimum_size… in Godot 4"),
    (r"\bEngine\s*\.\s*editor_hint\b", "Engine.editor_hint is Engine.is_editor_hint() in Godot 4"),
    (r"\bOS\s*\.\s*(window_size|window_fullscreen|set_window_fullscreen|set_window_size)\b",
     "the window is in DisplayServer in Godot 4 (get_window().size, DisplayServer.window_set_mode())"),
)
_CODE = [(re.compile(p), why) for p, why in CODE]
# Godot 4 nodes that are placed in 2D or 3D, and what each of them already has (a var of the same name is an error)
_SPATIAL = re.compile(r"^(Node2D|Node3D|CharacterBody[23]D|RigidBody[23]D|StaticBody[23]D|AnimatableBody[23]D|"
                      r"Area[23]D|Sprite[23]D|AnimatedSprite[23]D|Camera[23]D|MeshInstance3D|Marker[23]D|Path[23]D|"
                      r"PathFollow[23]D|Polygon2D|Line2D|TileMap|TileMapLayer|Label3D|GPUParticles[23]D|"
                      r"CPUParticles[23]D|VehicleBody3D|RayCast[23]D|ShapeCast[23]D|Skeleton[23]D)$")
_MEMBERS = {"position", "rotation", "scale", "visible", "name", "transform", "global_position"}
_PATHS = re.compile(r"\b(preload|load|change_scene_to_file|ResourceLoader\s*\.\s*load)\s*\(\s*\"|\bextends\s+\"")


def blank(text: str) -> str:
    """The code with every text's letters and every # comment turned into spaces (the quotes and the line breaks
    stay, so places and line numbers stay too)."""
    return _blank(text)[0]


def _blank(text: str) -> tuple[str, set[int]]:
    """blank() and the lines that start inside a text (a \"\"\" block)."""
    out, i, n, line = list(text), 0, len(text), 1
    inside: set[int] = set()
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
            continue
        if c in "\"'":
            q = text[i:i + 3] if text.startswith(('"""', "'''"), i) else c
            j = i + len(q)
            while j < n and not text.startswith(q, j):
                ch = text[j]
                if ch == "\\" and j + 1 < n:                # an escaped letter; \ at a line's end goes on
                    out[j] = " "
                    j += 1
                    ch = text[j]
                    if ch != "\n":
                        out[j] = " "
                        j += 1
                        continue
                elif ch == "\n" and len(q) == 1:
                    break                                  # a text not closed on its line: brackets() says so
                if ch == "\n":
                    line += 1
                    inside.add(line)
                else:
                    out[j] = " "
                j += 1
            i = j + len(q) if j < n and text.startswith(q, j) else j
            continue
        i += 1
    return "".join(out), inside


def _line(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


def res_root(folder: Path | None, here: Path | None) -> Path | None:
    """The Godot project's folder (where project.godot is), from a file's folder up to the Lanterna project's."""
    if folder is None or here is None:
        return None
    p = here
    for _ in range(12):
        if (p / "project.godot").is_file():
            return p
        if p == folder or p.parent == p:
            break
        p = p.parent
    return folder


def _missing(path: str, root: Path | None) -> bool:
    if root is None or not path.startswith("res://"):
        return False
    rel = path[6:].split("::")[0].strip("/")
    return bool(rel) and not (root / rel).exists()


def _class_names(root: Path | None) -> set[str]:
    """The classes this project names itself (class_name X): a project's own World or Area isn't Godot 3."""
    names: set[str] = set()
    if root is None or not root.is_dir():
        return names
    for n, f in enumerate(root.rglob("*.gd")):
        if n > 300:
            break
        try:
            names |= set(re.findall(r"(?m)^class_name\s+(\w+)", f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return names


def gdscript(body: str, folder: Path | None = None, here: Path | None = None) -> list[str]:
    """GDScript 2 (Godot 4): tabs and spaces, Godot 3 names, preload()/load() of files the project doesn't have."""
    out: list[str] = []
    code, inside = _blank(body)
    out += _indents(body, code, inside)
    root = res_root(folder, here)
    own = set(re.findall(r"(?m)^class_name\s+(\w+)", body)) | _class_names(root)
    seen: set[str] = set()
    for rx, why in _CODE:
        m = rx.search(code)
        if m and why not in seen:
            seen.add(why)
            out.append(f"line {_line(code, m.start())}: {why}")
    for old, new in CLASSES.items():
        if old in own or old in _NOT_IN_CODE:
            continue
        where = (rf"\b{old}\b" if old in _ANYWHERE else
                 rf"(?:\bextends\s+|\bas\s+|\bis\s+|:\s*|->\s*){old}\b|\b{old}\s*\.\s*new\s*\(")
        m = re.search(where, code)
        if m:
            out.append(f"line {_line(code, m.start())}: {old} is {new} in Godot 4")
    base = re.search(r"(?m)^extends\s+(\w+)", code)
    if base and _SPATIAL.match(base.group(1)):
        again = _MEMBERS | ({"velocity"} if base.group(1).startswith("CharacterBody") else set())
        for m in re.finditer(r"(?m)^var\s+(\w+)\b", code):
            if m.group(1) in again:
                out.append(f"line {_line(code, m.start())}: {base.group(1)} already has '{m.group(1)}' (Godot stops: "
                           f"the member already exists): remove this var and use the node's own {m.group(1)}")
                break
    for m in _PATHS.finditer(code):
        q = m.end() - 1                                    # the opening quote: the text is in the real body
        end = body.find('"', q + 1)
        path = body[q + 1:end] if end > 0 else ""
        if _missing(path, root):
            out.append(f"line {_line(body, q)}: '{path}' isn't in the project (write it, or fix the path)")
    return sorted(out, key=_line_of)


def _line_of(problem: str) -> int:
    m = re.match(r"line (\d+):", problem)
    return int(m.group(1)) if m else 0


def _indents(body: str, code: str, inside: set[int]) -> list[str]:
    """Godot stops at a line that indents with tabs and spaces mixed, or with the other kind than the file's first
    indented line. Lines inside brackets, after a \\ and inside a text don't count (nor blank and comment lines)."""
    out: list[str] = []
    first = ""
    depth, cont = 0, False
    for no, (raw, cl) in enumerate(zip(body.split("\n"), code.split("\n")), 1):
        if depth == 0 and not cont and cl.strip() and no not in inside:
            ws = raw[:len(raw) - len(raw.lstrip(" \t"))]
            if ws:
                if " " in ws and "\t" in ws:
                    out.append(f"line {no}: tabs and spaces mixed at the start of the line (Godot stops at this: "
                               "indent with tabs only)")
                elif not first:
                    first = ws[0]
                elif ws[0] != first:
                    kind, was = ("spaces", "tabs") if ws[0] == " " else ("tabs", "spaces")
                    out.append(f"line {no}: indented with {kind}, but the lines above use {was} (Godot stops at "
                               "this: use one kind, tabs are usual)")
                if len(out) >= 2:
                    break
        for c in cl:
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(0, depth - 1)
        cont = cl.rstrip().endswith("\\")
    return out


def scan(text: str) -> tuple[str, set[int]]:
    """Godot's text files (project.godot, .tscn, .tres): brackets and "texts" (a text may go over several lines, \\
    escapes); ';' at a line's start is a comment. (the first problem or "", the lines that start inside a text)"""
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    inside: set[int] = set()
    i, n, line, start = 0, len(text), 1, True
    while i < n:
        c = text[i]
        if c == "\n":
            line, start = line + 1, True
            i += 1
            continue
        if start and c in " \t\r":
            i += 1
            continue
        if start and c == ";":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        start = False
        if c == '"':
            at, j = line, i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                if j < n and text[j] == "\n":
                    line += 1
                    inside.add(line)
                j += 1
            if j >= n:
                return f"line {at}: a text in \" quotes is never closed (the file may be cut off)", inside
            i = j + 1
            continue
        if c in "([{":
            stack.append((c, line))
        elif c in ")]}":
            if not stack:
                return f"line {line}: '{c}' closes nothing", inside
            if stack[-1][0] != pairs[c]:
                want = {"(": ")", "[": "]", "{": "}"}[stack[-1][0]]
                return (f"line {line}: '{c}' where '{want}' was expected (for the '{stack[-1][0]}' on line "
                        f"{stack[-1][1]})"), inside
            stack.pop()
        i += 1
    if stack:
        top, at = stack[-1]
        return f"line {at}: '{top}' is never closed (the file may be cut off)", inside
    return "", inside


def project_file(body: str, folder: Path | None = None, here: Path | None = None) -> list[str]:
    """project.godot: Godot 4's format (config_version=5) and a main scene that is there."""
    problem, inside = scan(body)
    out = [problem] if problem else []
    section, conf, main, files = "", None, None, []
    for no, raw in enumerate(body.split("\n"), 1):
        s = raw.strip()
        if no in inside or not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]") and "=" not in s:
            section = s[1:-1].strip()
            continue
        key, eq, val = s.partition("=")
        if not eq:
            continue
        key, val = key.strip(), val.strip()
        if not section and key == "config_version":
            conf = val
        elif section == "application" and key == "run/main_scene":
            main = (no, val.strip('"'))
        elif (section == "application" and key == "config/icon") or section == "autoload":
            files.append((no, val.strip('"').lstrip("*")))
    if conf is None:
        out.append("there is no config_version=5 before the first [section]: Godot 4 doesn't open it as a project")
    elif conf != "5":
        out.append(f"config_version={conf} isn't Godot 4's: write config_version=5" +
                   (" (4 is Godot 3)" if conf == "4" else ""))
    if main is None:
        out.append("no run/main_scene=\"res://….tscn\" under [application]: Play doesn't know which scene to start")
    elif not main[1].startswith(("res://", "uid://")):
        out.append(f"line {main[0]}: run/main_scene must be a res:// path, e.g. \"res://main.tscn\"")
    elif here is not None and _missing(main[1], here):
        out.append(f"line {main[0]}: the main scene '{main[1]}' isn't in the project")
    for no, path in files:
        if here is not None and _missing(path, here):
            out.append(f"line {no}: '{path}' isn't in the project")
    m = re.search(r'"scancode"\s*:', body)
    if m:
        out.append(f"line {_line(body, m.start())}: the input map is written in Godot 3's words (\"scancode\"): "
                   "Godot 4 writes \"physical_keycode\" (or leave [input] out and use ui_left, ui_right, ui_up, "
                   "ui_down, ui_accept)")
    return out


_HEAD = re.compile(r"^\[(\w+)((?:\s+[\w/]+=(?:\"(?:[^\"\\]|\\.)*\"|[^\s\]]+))*)\s*\]\s*$")
_ATTR = re.compile(r"([\w/]+)=(\"(?:[^\"\\]|\\.)*\"|[^\s\]]+)")
_REF = re.compile(r"\b(Ext|Sub)Resource\(\s*(\"(?:[^\"\\]|\\.)*\"|[^)\s]+)\s*\)")


def scene(body: str, kind: str, folder: Path | None = None, here: Path | None = None) -> list[str]:
    """A scene (.tscn, kind "gd_scene") or resource (.tres, "gd_resource") in Godot 4's text format (format=3)."""
    first = next((x.strip() for x in body.split("\n") if x.strip() and not x.strip().startswith(";")), "")
    m = _HEAD.match(first) or re.match(r"^\[(\w+)(.*)\]$", first)
    if not m or m.group(1) != kind:
        return [f"the first line must be [{kind} format=3]: Godot can't read the file otherwise"]
    fmt = (re.search(r"\bformat=(\d+)", m.group(2)) or [None, ""])[1]
    if fmt in ("1", "2"):
        return [f"format={fmt} is Godot 3's file format: Godot 4 writes format=3, with ids in quotes "
                "(id=\"1_abc\", ExtResource(\"1_abc\")) and Godot 4 node types"]
    problem, inside = scan(body)
    out = [problem] if problem else []
    root = res_root(folder, here)
    lines = body.split("\n")
    heads = []
    for no, raw in enumerate(lines, 1):
        if no in inside or not raw.startswith("["):
            continue
        m = _HEAD.match(raw.strip())
        if not m:
            out.append(f"line {no}: this [ … ] line isn't one Godot reads (tag name=value …]): {raw.strip()[:60]}")
            continue
        heads.append((no, m.group(1), {k: v.strip('"') for k, v in _ATTR.findall(m.group(2))}))
    if not heads:
        return out
    ids = {"Ext": set(), "Sub": set()}
    paths = {".": False}                                   # node path -> is it another scene (its insides aren't here)
    first_node = True
    for no, tag, a in heads[1:]:
        if tag == "ext_resource":
            ids["Ext"].add(a.get("id", ""))
            if _missing(a.get("path", ""), root):
                out.append(f"line {no}: '{a['path']}' isn't in the project (write it, or fix the path)")
        elif tag == "sub_resource":
            ids["Sub"].add(a.get("id", ""))
            if a.get("type") in CLASSES:
                out.append(f"line {no}: {a['type']} is {CLASSES[a['type']]} in Godot 4")
        elif tag == "node":
            name, parent, typ = a.get("name", ""), a.get("parent"), a.get("type", "")
            if not name:
                out.append(f"line {no}: a [node] without name=")
            if typ in CLASSES:
                out.append(f"line {no}: {typ} is {CLASSES[typ]} in Godot 4")
            if first_node:
                first_node = False
                if parent is not None:
                    out.append(f"line {no}: the first [node] is the scene's root, it has no parent=")
                continue
            if parent is None:
                out.append(f"line {no}: node '{name}' has no parent= (only the first node, the root, has none)")
                continue
            here_path = name if parent == "." else f"{parent}/{name}"
            if parent not in paths and not any(parent.startswith(p + "/") for p, other in paths.items() if other):
                out.append(f"line {no}: parent=\"{parent}\" of '{name}' isn't a node above it")
            paths[here_path] = "instance" in a
        elif tag == "connection":
            for end in ("from", "to"):
                p = a.get(end, "")
                if p and p not in paths and not any(p.startswith(q + "/") for q, other in paths.items() if other):
                    out.append(f"line {no}: the signal's {end}=\"{p}\" isn't a node of this scene")
        if len(out) >= 6:
            return out
    for no, raw in enumerate(lines, 1):
        if no in inside:
            continue
        for kind_, ref in _REF.findall(raw):
            if not ref.startswith('"'):
                out.append(f"line {no}: {kind_}Resource({ref}) needs the id in quotes, e.g. {kind_}Resource(\"1_abc\")")
                return out
            if ref.strip('"') not in ids[kind_]:
                what = "ext_resource" if kind_ == "Ext" else "sub_resource"
                out.append(f"line {no}: {kind_}Resource({ref}) points to no [{what}] with that id")
                if len(out) >= 6:
                    return out
    return out
