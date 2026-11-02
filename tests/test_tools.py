"""Stage 4: tools, memory, reminders, files, the tool loop and rate-limit waiting. No network: all mocked."""
import base64
import datetime as dt
import io
import json
import zipfile

import httpx
import pytest

from lanterna import files, soul, tools
from lanterna.app import Api, _short_files
from lanterna.chat import Conversation, must_use_tool
from lanterna.discovery import Candidate
from lanterna.providers import PROVIDERS, Client, ProviderError, _error
from lanterna.router import AllFailed, Router
from lanterna.store import Store


def sse(*chunks: str) -> bytes:
    return ("".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
            + "data: [DONE]\n\n").encode()


def sse_tool(name: str, args: dict, call_id: str = "c1") -> bytes:
    a = json.dumps(args)
    parts = [{"index": 0, "id": call_id, "function": {"name": name, "arguments": a[:5]}},
             {"index": 0, "function": {"arguments": a[5:]}}]
    return ("".join(f"data: {json.dumps({'choices': [{'delta': {'tool_calls': [p]}}]})}\n\n" for p in parts)
            + "data: [DONE]\n\n").encode()


# --- math & dates ----------------------------------------------------------------------------
@pytest.mark.parametrize("expr,want", [("(12.5*3)+7^2", "86.5"), ("15% * 240", "36"), ("17 % 5", "2"),
                                       ("sqrt(16)+1", "5"), ("0.1+0.2", "0.3"), ("2*(3", "Error")])
def test_calculate(expr, want):
    assert want in tools.calculate(expr)


def test_calculate_refuses_code_and_huge_numbers():
    assert tools.calculate("__import__('os')").startswith("Error")
    assert tools.calculate("9**99999").startswith("Error")
    assert "division by zero" in tools.calculate("1/0")


def test_date_calc():
    today = dt.date(2026, 11, 2)
    assert "53 days" in tools.date_calc("between", "today", "2026-12-25", today=today)
    assert "2027-02-10" in tools.date_calc("add", "today", days=100, today=today)
    assert "Friday" in tools.date_calc("weekday", "2026-12-25", today=today)
    assert tools.date_calc("between", "2026-13-45", "today", today=today).startswith("Error")


def test_parse_when():
    now = dt.datetime(2026, 11, 2, 21, 30)
    assert tools.parse_when(in_minutes=20, now=now) == dt.datetime(2026, 11, 2, 21, 50)
    assert tools.parse_when("2026-11-03 08:15", now=now) == dt.datetime(2026, 11, 3, 8, 15)
    assert tools.parse_when("2026-11-03T08:15:00", now=now) == dt.datetime(2026, 11, 3, 8, 15)
    assert tools.parse_when("07:00", now=now) == dt.datetime(2026, 11, 3, 7, 0)       # already passed today → tomorrow
    assert tools.parse_when("2026-11-05", now=now) == dt.datetime(2026, 11, 5, 9, 0)
    assert tools.parse_when("someday", now=now) is None


# --- web, weather ------------------------------------------------------------------------------
DDG = """<div><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa&amp;rut=x">Example <b>A</b></a>
<a class="result__snippet" href="#">First &amp; best</a></div>
<div><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Ad</a></div>
<div><a class="result__a" href="https://example.net/b">B</a><a class="result__snippet">Second</a></div>"""


def test_web_search_parses_results_and_skips_ads():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=DDG)))
    out = tools.web_search("q", http=c)
    assert "1. Example A\n   https://example.org/a\n   First & best" in out
    assert "2. B" in out and "Ad" not in out


def test_weather_formats_forecast_and_air():
    def h(req):
        host = req.url.host
        if host.startswith("geocoding"):
            return httpx.Response(200, json={"results": [{"name": "Ferrara", "country": "Italy", "latitude": 44.8, "longitude": 11.6}]})
        if host.startswith("air-quality"):
            return httpx.Response(200, json={"current": {"european_aqi": 24, "pm2_5": 6.8}})
        return httpx.Response(200, json={"current": {"temperature_2m": 11.4, "apparent_temperature": 8.7, "weather_code": 3,
                                                     "wind_speed_10m": 7, "relative_humidity_2m": 56},
                                         "daily": {"time": ["2026-11-02"], "temperature_2m_min": [7], "temperature_2m_max": [16.6],
                                                   "weather_code": [61], "precipitation_probability_max": [80]}})
    out = tools.weather("Ferrara", 1, http=httpx.Client(transport=httpx.MockTransport(h)))
    assert "Ferrara, Italy" in out and "11.4°C" in out and "overcast" in out
    assert "light rain, rain chance 80%" in out and "AQI 24 (fair)" in out


def test_weather_unknown_place():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert "No place" in tools.weather("Nowhere-xyz", http=c)


def test_read_page_blocks_local_addresses_and_strips_html():
    blocked = tools.read_page("http://127.0.0.1:11434/api/tags", check_host=tools._public_host)
    assert "not on the public internet" in blocked
    assert "only http" in tools.read_page("file:///etc/passwd")
    page = "<html><head><title>x</title></head><body><script>evil()</script><h1>Hello</h1><p>World &amp; more</p></body></html>"
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page, headers={"content-type": "text/html"})))
    out = tools.read_page("https://example.org/", http=c, check_host=lambda h: True)
    assert "Hello" in out and "World & more" in out and "evil" not in out


def test_read_page_checks_every_redirect():
    seen = []

    def h(req):
        return httpx.Response(302, headers={"location": "http://192.168.1.1/admin"})
    c = httpx.Client(transport=httpx.MockTransport(h))
    out = tools.read_page("https://example.org/", http=c, check_host=lambda host: seen.append(host) or host == "example.org")
    assert "not on the public internet" in out and seen == ["example.org", "192.168.1.1"]


# --- memory & reminders -----------------------------------------------------------------------
def test_toolbox_memory_and_reminders(tmp_path):
    st = Store(tmp_path / "m.db")
    now = dt.datetime(2026, 11, 2, 20, 0)
    tb = tools.Toolbox(st, now=lambda: now)
    assert "Saved" in tb.run("remember", '{"fact": "Allergic to peanuts"}')
    tb.run("remember", '{"fact": "allergic to peanuts"}')                  # duplicate ignored
    assert [f["text"] for f in st.facts()] == ["Allergic to peanuts"]
    assert "Removed 1" in tb.run("forget", '{"fact": "peanut"}')
    out = tb.run("set_reminder", '{"text": "water", "in_minutes": 30}')
    assert "#1" in out and "20:30" in out
    assert "in the past" in tb.run("set_reminder", '{"text": "x", "at": "2026-11-01 10:00"}')
    assert "water" in tb.run("list_reminders", "{}")
    assert tb.run("nope", "{}").startswith("Error") and tb.run("calculate", "not json").startswith("Error")
    assert tb.run("calculate", '{"wrong": 1}').startswith("Error")
    due = now.timestamp() + 31 * 60
    assert [r["text"] for r in st.take_due(due)] == ["water"] and st.take_due(due) == []
    assert "cancelled" not in tb.run("cancel_reminder", '{"id": 1}')        # already fired


def test_api_fires_due_reminders_once(tmp_path, monkeypatch):
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    sent = []
    monkeypatch.setattr("lanterna.app.notify", lambda title, msg: sent.append(msg) or True)
    api = Api(store=Store(tmp_path / "a.db"), scheduler=False)
    api.store.add_reminder("call mom", 1000.0)
    api.store.add_reminder("later", 5000.0)
    assert [r["text"] for r in api.check_reminders(now=2000.0)] == ["call mom"]
    assert sent and "call mom" in sent[0]
    assert [a["text"] for a in api.alerts()] == ["call mom"] and api.alerts() == []
    assert [r["text"] for r in api.reminders()] == ["later"]
    assert api.cancel_reminder(api.reminders()[0]["id"]) == []


# --- files -------------------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_prepare_text_docx_and_photo():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (3000, 1500), "white").save(buf, "PNG")
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Hello</w:t></w:r></w:p><w:p><w:t>Docx</w:t></w:p></w:document>")
    p = files.prepare([{"name": "a.txt", "data": _b64("line one\r\nline two".encode())},
                       {"name": "b.docx", "data": _b64(docx.getvalue())},
                       {"name": "c.png", "data": _b64(buf.getvalue())}])
    assert "[File: a.txt]\n```\nline one\nline two\n```" in p.text
    assert "Hello\nDocx" in p.text and "[Photo: c.png]" in p.text
    assert len(p.images) == 1 and p.images[0].startswith("data:image/jpeg;base64,")
    im = Image.open(io.BytesIO(base64.b64decode(p.images[0].split(",", 1)[1])))
    assert max(im.size) == files.IMAGE_SIDE


def test_prepare_refuses_bad_files(tmp_path):
    with pytest.raises(files.FileError):
        files.prepare([{"path": str(tmp_path / "missing.txt")}])
    with pytest.raises(files.FileError):
        files.prepare([{"name": "x.exe", "data": _b64(b"\x00\x01\xff\xfe binary")}])
    long = tmp_path / "long.md"
    long.write_text("x" * (files.TEXT_LIMIT + 50), encoding="utf-8")
    assert "file cut" in files.prepare([{"path": str(long)}]).text


def test_short_files_for_display():
    full = "look\n\n[File: a.txt]\n```\nsecret body\n```\n\n[Photo: cat.jpg]"
    assert _short_files(full) == "look\n\n📎 a.txt\n\n🖼 cat.jpg"


# --- the tool loop -----------------------------------------------------------------------------
def _router(responses: list, bodies: list) -> Router:
    def h(req):
        bodies.append(json.loads(req.content))
        r = responses.pop(0)
        return r if isinstance(r, httpx.Response) else httpx.Response(200, content=r)
    return Router([Candidate("groq", "m", 50, vision=True)],
                  client_for=lambda pid: Client(PROVIDERS["groq"], "k", transport=httpx.MockTransport(h)))


def test_tool_loop_runs_tool_and_answers(tmp_path):
    bodies = []
    router = _router([sse_tool("calculate", {"expression": "2+2"}), sse("It's ", "4.")], bodies)
    conv = Conversation(router, "Anna", toolbox=tools.Toolbox(Store(tmp_path / "t.db")))
    out = list(conv.ask("what is 2+2"))
    assert any(getattr(p, "name", "") == "calculate" for p in out)
    assert conv.last_reply == "It's 4."
    second = bodies[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"] == {"name": "calculate", "arguments": '{"expression": "2+2"}'}
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "2+2 = 4"}
    assert bodies[0]["tool_choice"] == "auto" and "tools" in bodies[0]
    assert [m["role"] for m in conv.history] == ["user", "assistant"]          # tool messages stay out of history


def test_explicit_requests_force_a_tool(tmp_path):
    assert must_use_tool("Нагадай мені через 5 хвилин") and must_use_tool("remember that I like tea")
    assert must_use_tool("Ricordami di comprare il pane") and not must_use_tool("how are you?")
    bodies = []
    router = _router([sse_tool("set_reminder", {"text": "tea", "in_minutes": 5}), sse("Done.")], bodies)
    st = Store(tmp_path / "r.db")
    list(Conversation(router, toolbox=tools.Toolbox(st)).ask("Нагадай мені через 5 хвилин про чай"))
    assert bodies[0]["tool_choice"] == "required" and bodies[1]["tool_choice"] == "auto"
    assert [r["text"] for r in st.reminders()] == ["tea"]


def test_model_without_tools_still_answers(tmp_path):
    bodies = []
    bad = httpx.Response(400, json={"error": {"message": "tools not supported"}})
    router = _router([bad, sse("Hi!")], bodies)
    conv = Conversation(router, toolbox=tools.Toolbox(Store(tmp_path / "n.db")))
    list(conv.ask("hello"))
    assert conv.last_reply == "Hi!" and "tools" not in bodies[1]
    assert ("groq", "m") in router.no_tools


def test_photos_go_without_tools_and_with_language_hint(tmp_path):
    bodies = []
    router = _router([sse("Молоко і хліб.")], bodies)
    conv = Conversation(router, toolbox=tools.Toolbox(Store(tmp_path / "p.db")), lang="uk")
    list(conv.ask("Що на фото?", images=["data:image/jpeg;base64,AAAA"]))
    user = bodies[0]["messages"][-1]["content"]
    assert user[1]["image_url"]["url"].startswith("data:image") and "Ukrainian" in user[0]["text"]
    assert "tools" not in bodies[0]
    assert "[attached 1 image(s)]" in conv.history[0]["content"]


def test_no_photo_model_gives_clear_error():
    r = Router([Candidate("groq", "text-only", 50, vision=False)], client_for=lambda pid: None)
    with pytest.raises(ProviderError) as e:
        list(r.stream([{"role": "user", "content": "x"}], need_vision=True))
    assert e.value.kind == "vision"


# --- rate limits ----------------------------------------------------------------------------------
def test_retry_after_from_message():
    resp = httpx.Response(429, json={"error": {"message": "Rate limit reached. Please try again in 2.4s. Need more"}},
                          request=httpx.Request("POST", "https://x"))
    assert _error(resp).retry_after == 2.4
    resp = httpx.Response(429, json={"error": {"message": "try again in 1m3.5s"}}, request=httpx.Request("POST", "https://x"))
    assert _error(resp).retry_after == 63.5


def test_router_waits_once_on_short_rate_limit():
    slept, bodies = [], []
    limited = httpx.Response(429, json={"error": {"message": "Please try again in 2.4s"}})
    router = _router([limited, sse("ok")], bodies)
    router._sleep = slept.append
    assert "".join(p for p in router.stream([{"role": "user", "content": "x"}]) if isinstance(p, str)) == "ok"
    assert slept == [2.9]


def test_router_gives_up_on_long_rate_limit():
    router = _router([httpx.Response(429, json={"error": {"message": "Please try again in 7m0s"}})], [])
    router._sleep = lambda s: pytest.fail("should not wait 7 minutes")
    with pytest.raises(AllFailed):
        list(router.stream([{"role": "user", "content": "x"}]))


# --- soul -------------------------------------------------------------------------------------------
def test_language_hint_and_closers():
    assert "Ukrainian" in soul.lang_hint("Що це, підкажи?", "en")          # і → Ukrainian whatever the app language
    assert "Ukrainian" in soul.lang_hint("Що на фото?", "uk")               # no і/ї/є, but the app is in Ukrainian
    assert soul.lang_hint("Что это? Объясни", "uk") == ""                   # ы/ъ/э: really Russian, leave it
    assert soul.lang_hint("What is this?", "en") == ""
    assert soul.humanize("Бюджет 4 200 EUR. Якщо треба ще якісь розрахунки, дай знати!") == "Бюджет 4 200 EUR."
