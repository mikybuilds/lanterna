"""Round 107: the morning summary."""
import datetime as dt

import httpx

from lanterna import keys, morning
from lanterna.store import Store


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


def test_it_is_due_once_a_morning():
    now = dt.datetime(2026, 11, 9, 8, 5)
    assert morning.due(True, "08:00", "", now)
    assert not morning.due(False, "08:00", "", now)
    assert not morning.due(True, "08:30", "", now)                       # not yet
    assert not morning.due(True, "08:00", "2026-11-09", now)             # already shown today
    assert not morning.due(True, "08:00", "", now.replace(hour=13))      # the PC was off all morning
    assert morning.due(True, "11:30", "", now.replace(hour=12, minute=10))   # a late "morning" still gets its 2 hours


def test_the_note_has_weather_reminders_and_tasks(tmp_path):
    s = Store(tmp_path / "t.db")
    now = dt.datetime(2026, 11, 9, 8, 0)
    s.add_reminder("Таблетки", dt.datetime(2026, 11, 9, 9, 0).timestamp(), "day")
    s.add_reminder("Завтра", dt.datetime(2026, 11, 10, 9, 0).timestamp())
    s.add_task("Погода в Києві", "day", "19:00", 0, "", dt.datetime(2026, 11, 9, 19, 0).timestamp())
    w = lambda city, lang: {"place": "Київ", "tmin": -2, "tmax": 5, "rain": 40, "code": 61}   # noqa: E731
    text = morning.build(s, "Міша", "Kyiv", "uk", now, weather=w)
    assert text.splitlines()[0] == "Доброго ранку, Міша! Сьогодні понеділок, 09.11."
    assert "🌧 Київ: -2…+5°C, імовірність дощу 40%" in text
    assert "• 09:00 Таблетки" in text and "Завтра" not in text
    assert "• 19:00 Погода в Києві" in text


def test_without_city_or_plans(tmp_path):
    s = Store(tmp_path / "t.db")
    text = morning.build(s, "", "", "en", dt.datetime(2026, 11, 9, 8, 0), weather=lambda *a: 1 / 0)
    assert text.startswith("Good morning! Today is Monday, 09.11.")
    assert "No reminders or regular tasks for today." in text
    bad = morning.build(s, "", "Nowhere", "en", dt.datetime(2026, 11, 9, 8, 0), weather=lambda *a: None)
    assert "Couldn't get the weather for Nowhere" in bad


def test_weather_today_reads_open_meteo():
    def answer(req):
        if "geocoding" in str(req.url):
            return httpx.Response(200, json={"results": [{"name": "Ferrara", "latitude": 44.8, "longitude": 11.6}]})
        return httpx.Response(200, json={"daily": {"weather_code": [3], "temperature_2m_min": [4.4],
                                                   "temperature_2m_max": [11.6], "precipitation_probability_max": [10]}})
    w = morning.weather_today("Ferrara", "it", http=httpx.Client(transport=httpx.MockTransport(answer)))
    assert w == {"place": "Ferrara", "tmin": 4, "tmax": 12, "rain": 10, "code": 3}
    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="no")))
    assert morning.weather_today("Ferrara", "it", http=down) is None
    assert morning.sky(0) == "☀️" and morning.sky(73) == "🌨" and morning.sky(95) == "⛈"


def test_the_app_shows_it_once_and_keeps_one_chat(tmp_path, monkeypatch):
    from lanterna import app as appmod
    api = _api(tmp_path, monkeypatch)
    told = []
    monkeypatch.setattr(appmod, "notify", lambda *a: told.append(a))
    api.save_settings({"morning": True, "morning_at": "7:30", "morning_city": ""})
    assert api.settings.morning_at == "07:30"
    day1 = dt.datetime(2026, 11, 9, 7, 45)
    assert api.check_morning(day1) and api.check_morning(day1 + dt.timedelta(minutes=5)) == ""
    assert api.check_morning(day1 + dt.timedelta(days=1))
    th = api.settings.morning_thread
    assert len(api.store.messages(th)) == 2 and len(told) == 2
    assert [a["kind"] for a in api.alerts()] == ["morning", "morning"]
    api.save_settings({"morning_at": "nonsense"})
    assert api.settings.morning_at == "07:30"


def test_off_by_default_and_the_window_may_preview(tmp_path, monkeypatch):
    from lanterna import gui
    api = _api(tmp_path, monkeypatch)
    assert api.settings.morning is False and api.check_morning(dt.datetime(2026, 11, 9, 9, 0)) == ""
    assert "morning_preview" in gui.METHODS
    assert api.morning_preview().startswith("Good morning")
