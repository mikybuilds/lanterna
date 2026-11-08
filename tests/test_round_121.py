"""Round 121: numbered lists keep their numbers when text sits between the items, your own messages show lists
as lists, and Shift+Enter in the message box continues a list."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from lanterna import gui

JS = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")


def _grab(name: str) -> str:
    """One top-level function (or const) from app.js, by brace matching."""
    i = JS.index(name)
    j = JS.index("{", i)
    depth = 0
    for k in range(j, len(JS)):
        depth += {"{": 1, "}": -1}.get(JS[k], 0)
        if depth == 0:
            return JS[i:k + 1]
    raise AssertionError(name)


def _run(code: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    esc = re.search(r"^const esc = .*$", JS, re.M).group(0)
    src = "\n".join([esc, _grab("function md("), re.search(r"^const LIST_LINE = .*$", JS, re.M).group(0), code])
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _md(text, plain=False):
    return _run(f"process.stdout.write(JSON.stringify(md({json.dumps(text)}, {str(plain).lower()})))")


def test_numbers_continue_when_text_sits_between_items():
    text = ("Ось кілька фільмів:\n\n1. **Параноя (2007)**\n\n*Вайб:* трилер.\nХлопець під арештом.\n\n"
            "2. **Альфа Дог (2006)**\n\n*Вайб:* кримінал.\n\n3. **Донні Дарко (2001)**\n\nПохмурий.")
    html = _md(text)
    assert '<ol start="2">' in html and '<ol start="3">' in html
    assert html.count("<li>") == 3


def test_every_item_written_as_one_counts_on():
    html = _md("1. A\n\nAbout A\n\n1. B\n\nAbout B\n\n1. C")
    assert '<ol start="2">' in html and '<ol start="3">' in html


def test_indented_and_lazy_lines_stay_in_their_item():
    html = _md("1. Fear (1996)\n   Vibe: thriller\n\n2. Fight Club\nVibe: cult\n3. Project X")
    assert html.count("<ol") == 1 and html.count("<li>") == 3
    assert "Fear (1996)<br>Vibe: thriller" in html and "Fight Club<br>Vibe: cult" in html


def test_two_separate_lists_still_start_at_one():
    html = _md("Steps for A:\n1. a\n2. b\n\nSteps for B:\n1. c\n2. d")
    assert html.count("<ol>") == 2 and "start=" not in html


def test_your_message_shows_lists_but_no_markdown():
    html = _md("Порадь фільми, схожі на:\n1. Fear 1996\n2. **Супер перці**\n3. <b>Проєкт X</b>", plain=True)
    assert "<ol><li>Fear 1996</li><li>**Супер перці**</li><li>&lt;b&gt;Проєкт X&lt;/b&gt;</li></ol>" in html
    assert "<strong>" not in html
    assert _run('process.stdout.write(JSON.stringify([LIST_LINE.test("a\\n1. b"), LIST_LINE.test("в 2025. році"), LIST_LINE.test("- x")]))') == [True, False, True]


def test_composer_continues_lists():
    assert "listEnter(inp)" in JS
    body = _grab("function listEnter(")
    assert 'insertText' in body and "+m[2] + 1" in body
    assert 'classList.add("rich")' in JS


def test_your_line_after_a_list_stands_alone():
    html = _md("Схожі на:\n1. Fear\n2. Супер перці\nЩо ще подивитись?", plain=True)
    assert html.endswith("</ol><p>Що ще подивитись?</p>")
    assert "Fear 1996<br>Vibe" in _md("1. Fear 1996\nVibe: thriller")            # in answers it stays in the item


def test_terminal_app_counts_on_too():
    from lanterna.tui import count_on
    assert count_on("1. A\n\nAbout A\n\n1. B\n\nAbout B\n\n1. C") == "1. A\n\nAbout A\n\n2. B\n\nAbout B\n\n3. C"
    assert count_on("Steps:\n1. a\n2. b\n\nNext:\n1. c\n2. d") == "Steps:\n1. a\n2. b\n\nNext:\n1. c\n2. d"
    assert count_on("```\n1. x\n```\n1. y") == "```\n1. x\n```\n1. y"
