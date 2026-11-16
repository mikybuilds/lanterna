"""Round 142 (1.1.10b4): links in answers look and act like links.

A link in an answer had no href (so a click never opens a site inside Lanterna's window), and with no href the
window treated it as plain text: the text cursor under the pointer, no line, nothing on hover, out of reach of Tab.
Only a click worked. Now it is underlined, the pointer is a hand, the line gets brighter under it, the whole address
shows on hover, and Tab + Enter open it too. A full stop or comma after a bare address is no longer part of it.
"""
import re
from html import unescape
from pathlib import Path

from lanterna import gui
from test_round_139 import _md  # noqa: E402  (md() of app.js, run in node)

UI = Path(gui.__file__).parent / "ui"
JS = (UI / "app.js").read_text(encoding="utf-8")
CSS = (UI / "style.css").read_text(encoding="utf-8")


def _links(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<a ([^>]*)>(.*?)</a>", html):
        attrs = {k: unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(1))}
        out.append({**attrs, "text": unescape(m.group(2))})
    return out


def test_a_link_in_an_answer_is_a_link_for_the_pointer_the_keyboard_and_screen_readers():
    html = _md("Сторінка: [visualstudio.microsoft.com/vs/community/](https://visualstudio.microsoft.com/vs/community/).")
    (a,) = _links(html)
    assert a == {"data-href": "https://visualstudio.microsoft.com/vs/community/",
                 "title": "https://visualstudio.microsoft.com/vs/community/",       # the address shows on hover
                 "role": "link", "tabindex": "0", "text": "visualstudio.microsoft.com/vs/community/"}
    assert "href=" not in html.replace("data-href=", "")       # still no href: the window never goes to the site
    assert html.endswith("</a>.</p>")


def test_a_full_stop_or_a_comma_after_a_bare_address_is_not_part_of_it():
    html = _md("Тут: https://visualstudio.microsoft.com/downloads/. Або https://example.org/page, чи "
               "https://example.org/a?x=1&y=2; також «https://example.org/q»… і (https://example.org/b).")
    assert [a["data-href"] for a in _links(html)] == [
        "https://visualstudio.microsoft.com/downloads/", "https://example.org/page", "https://example.org/a?x=1&y=2",
        "https://example.org/q", "https://example.org/b"]
    assert all(a["text"] == a["data-href"] == a["title"] for a in _links(html))
    assert "</a>. Або" in html and "</a>, чи" in html and "</a>; також" in html and "«<a " in html and "</a>»…" in html


def test_an_address_in_quotes_is_a_link_without_the_quotes():
    html = _md('Сайти: "https://example.org/a", “https://example.org/b”, \'https://example.org/c\' і „https://example.org/d“.')
    assert [a["data-href"] for a in _links(html)] == [f"https://example.org/{x}" for x in "abcd"]
    assert html.startswith("<p>Сайти: &quot;<a ") and "</a>&quot;, “<a " in html and "</a>&#39; і „<a " in html


def test_an_address_that_ends_with_an_ampersand_keeps_it_and_a_bare_scheme_is_no_link():
    assert [a["data-href"] for a in _links(_md("Форма: https://example.org/f?a=1&"))] == ["https://example.org/f?a=1&"]
    assert _links(_md("Почни з https:// і далі.")) == []
    assert _links(_md("Твоє питання: https://example.org/x", plain=True)) == []        # your own messages: no links


def test_the_window_underlines_answer_links_shows_a_hand_and_opens_them_with_enter():
    rule = re.search(r"\.md a \{([^}]*)\}", CSS).group(1)
    assert "cursor: pointer" in rule and "text-decoration: underline" in rule
    assert re.search(r"\.md a:hover, \.md a:focus-visible \{[^}]*text-decoration-color: currentColor", CSS)
    key = JS[JS.index('document.addEventListener("keydown", e => {                  // Enter on a link'):][:300]
    assert 'e.key === "Enter"' in key and 'closest("a[data-href]")' in key and "api.open_url(a.dataset.href)" in key
