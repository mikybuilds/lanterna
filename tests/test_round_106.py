"""Round 106: repeating reminders (no model needed) and "Snooze 10 min"."""
import datetime as dt

from lanterna import keys, tools
from lanterna.store import Store, next_due


def _ts(*a):
    return dt.datetime(*a).timestamp()


def _api(tmp_path, monkeypatch):
    from lanterna.app import Api
    monkeypatch.setattr(keys, "get_key", lambda n: None)
    monkeypatch.setenv("LANTERNA_HOME", str(tmp_path))
    return Api(store=Store(tmp_path / "t.db"), scheduler=False)


# ---------------------------------------------------------------- the next time
def test_next_time_for_each_kind_of_repeat():
    fri_9 = _ts(2026, 11, 6, 9, 0)                       # a Friday
    assert next_due(fri_9, "day", fri_9) == _ts(2026, 11, 7, 9, 0)
    assert next_due(fri_9, "weekday", fri_9) == _ts(2026, 11, 9, 9, 0)      # skips the weekend
    assert next_due(fri_9, "week", fri_9) == _ts(2026, 11, 13, 9, 0)
    assert next_due(fri_9, "month", fri_9) == _ts(2026, 12, 6, 9, 0)


def test_missed_times_are_skipped_not_shown_one_by_one():
    due = _ts(2026, 11, 1, 8, 30)
    now = _ts(2026, 11, 5, 12, 0)                        # the PC was off for four days
    assert next_due(due, "day", now) == _ts(2026, 11, 6, 8, 30)


def test_month_keeps_the_day_even_after_a_short_month():
    jan31 = _ts(2027, 1, 31, 10, 0)
    assert next_due(jan31, "month", jan31) == _ts(2027, 2, 28, 10, 0)
    assert next_due(jan31, "month", _ts(2027, 3, 1)) == _ts(2027, 3, 31, 10, 0)   # not stuck on the 28th


# ---------------------------------------------------------------- the store
def test_a_repeating_reminder_comes_back_and_a_one_time_one_does_not(tmp_path):
    s = Store(tmp_path / "t.db")
    now = _ts(2026, 11, 7, 9, 0)
    pills = s.add_reminder("Таблетки", now - 1, "day")
    bus = s.add_reminder("Автобус", now - 1)
    assert {r["text"] for r in s.take_due(now)} == {"Таблетки", "Автобус"}
    left = s.reminders()
    assert [(r["id"], r["repeat"]) for r in left] == [(pills, "day")]
    assert left[0]["due"] == _ts(2026, 11, 8, 8, 59, 59)
    assert s.take_due(now + 60) == []                    # shown once per time
    assert bus not in [r["id"] for r in left]


def test_an_unknown_repeat_is_a_one_time_reminder(tmp_path):
    s = Store(tmp_path / "t.db")
    s.add_reminder("x", 1.0, "yearly")
    assert s.reminders()[0]["repeat"] == ""


def test_snooze_a_one_time_reminder(tmp_path):
    s = Store(tmp_path / "t.db")
    now = _ts(2026, 11, 7, 9, 0)
    rid = s.add_reminder("Подзвонити мамі", now - 1)
    s.take_due(now)
    assert s.reminders() == []
    assert s.snooze_reminder(rid, 10, now=now) == rid
    assert [(r["id"], r["due"]) for r in s.reminders()] == [(rid, now + 600)]
    assert [r["text"] for r in s.take_due(now + 601)] == ["Подзвонити мамі"]


def test_snooze_a_repeating_reminder_keeps_its_own_time(tmp_path):
    s = Store(tmp_path / "t.db")
    now = _ts(2026, 11, 7, 9, 0)
    rid = s.add_reminder("Таблетки", now, "day")
    s.take_due(now)
    copy = s.snooze_reminder(rid, 10, now=now)
    assert copy and copy != rid
    got = {r["id"]: (r["due"], r["repeat"]) for r in s.reminders()}
    assert got == {rid: (_ts(2026, 11, 8, 9, 0), "day"), copy: (now + 600, "")}


def test_a_cancelled_reminder_is_not_snoozed(tmp_path):
    s = Store(tmp_path / "t.db")
    rid = s.add_reminder("x", 10.0)
    s.cancel_reminder(rid)
    assert s.snooze_reminder(rid) == 0 and s.snooze_reminder(999) == 0


# ---------------------------------------------------------------- sync
def test_repeat_goes_to_the_other_device(tmp_path):
    a, b = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    a.add_reminder("Таблетки", _ts(2030, 1, 1, 9, 0), "weekday")
    b.import_sync(a.export_sync())
    assert [(r["text"], r["repeat"]) for r in b.reminders()] == [("Таблетки", "weekday")]


def test_an_older_lanterna_does_not_stop_a_repeating_reminder(tmp_path):
    a, b = Store(tmp_path / "a.db"), Store(tmp_path / "b.db")
    a.add_reminder("Таблетки", _ts(2026, 1, 1, 9, 0), "day")
    snap = a.export_sync()
    b.import_sync(snap)
    old = a.export_sync()                                # what an older version would send after showing it once
    for r in old["reminders"].values():
        r.pop("repeat")
        r["done"], r["changed"] = 1, r["changed"] + 5
    b.import_sync(old)
    left = b.reminders()
    assert len(left) == 1 and left[0]["repeat"] == "day" and left[0]["due"] > dt.datetime.now().timestamp()


# ---------------------------------------------------------------- the tool the model uses
def test_the_tool_sets_a_repeating_reminder(tmp_path):
    s = Store(tmp_path / "t.db")
    tb = tools.Toolbox(s)
    tb._now = lambda: dt.datetime(2026, 11, 7, 8, 0)     # a Saturday
    out = tb._set_reminder("Таблетки", at="2026-11-07 09:00", repeat="weekday")
    assert "repeats on weekdays" in out
    r = s.reminders()[0]
    assert r["repeat"] == "weekday" and r["due"] == _ts(2026, 11, 9, 9, 0)            # first on Monday
    assert "Error" in tb._set_reminder("x", at="2026-11-07 10:00", repeat="yearly")
    assert "repeats" in tb._list_reminders()
    assert "repeats" not in tb._set_reminder("Один раз", in_minutes=5, repeat="once")


def test_the_model_is_told_about_repeat():
    tb = tools.Toolbox(None)
    spec = {t.name: t for t in tb._make()}
    assert spec["set_reminder"].parameters["properties"]["repeat"]["enum"] == ["day", "weekday", "week", "month"]
    assert "set_reminder with repeat" in spec["add_task"].description


# ---------------------------------------------------------------- the app and the window
def test_reminder_alerts_carry_the_id_and_snooze_works(tmp_path, monkeypatch):
    from lanterna import app as appmod
    api = _api(tmp_path, monkeypatch)
    monkeypatch.setattr(appmod, "notify", lambda *a: True)
    rid = api.store.add_reminder("Вода", 1.0)
    api.check_reminders()
    got = api.alerts()
    assert got[0]["id"] == rid
    assert api.snooze_reminder(rid) is True
    assert api.reminders()[0]["id"] == rid


def test_the_window_may_snooze_and_shows_the_button():
    from pathlib import Path

    from lanterna import gui
    assert "snooze_reminder" in gui.METHODS
    js = (Path(gui.__file__).parent / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'label: t("Snooze 10 min")' in js and "api.snooze_reminder(a.id, 10)" in js


def test_new_strings_are_translated():
    from lanterna import i18n
    for key in ("Every month", "Snooze 10 min", "I'll remind you again in 10 minutes.", "F8: snooze 10 min"):
        for lang in ("uk", "it", "de", "es", "fr", "pl"):
            assert i18n.t(key, lang) != key, (key, lang)
