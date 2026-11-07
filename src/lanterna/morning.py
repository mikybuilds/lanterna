"""Morning summary: once a day, at the time the user picked, a short note for the day — the weather in their
city, today's reminders and regular tasks. Made on this computer without a model (only the weather comes from
Open-Meteo, and only if a city is set). Off by default (Settings → Reminders)."""
from __future__ import annotations

import datetime as dt

import httpx

from .i18n import t
from .tasks import DAYS, clean_time

LATEST_HOUR = 12          # the PC was off all morning: no "good morning" after noon


def sky(code: int | None) -> str:
    """An emoji for an Open-Meteo weather code (no words to translate)."""
    if code is None:
        return "🌡"
    if code == 0:
        return "☀️"
    if code in (1, 2):
        return "⛅"
    if code == 3:
        return "☁️"
    if code in (45, 48):
        return "🌫"
    if code in (71, 73, 75, 77, 85, 86):
        return "🌨"
    if code >= 95:
        return "⛈"
    return "🌧"


def weather_today(place: str, lang: str, http: httpx.Client | None = None) -> dict | None:
    """{place, tmin, tmax, rain, code} for today, or None (no such place, no internet)."""
    from .tools import FORECAST_URL, GEO_URL, _http
    if not (place or "").strip():
        return None
    c = http or _http()
    try:
        g = c.get(GEO_URL, params={"name": place.strip(), "count": 1, "language": lang, "format": "json"}).json()
        if not g.get("results"):
            return None
        p = g["results"][0]
        f = c.get(FORECAST_URL, params={"latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto",
                                        "forecast_days": 1, "daily": "weather_code,temperature_2m_max,"
                                        "temperature_2m_min,precipitation_probability_max"}).json()
        d = f["daily"]
        return {"place": p.get("name") or place, "tmin": round(d["temperature_2m_min"][0]),
                "tmax": round(d["temperature_2m_max"][0]), "rain": d["precipitation_probability_max"][0],
                "code": d["weather_code"][0]}
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None
    finally:
        if http is None:
            c.close()


def _deg(x) -> str:
    return f"{'+' if x > 0 else ''}{x}"


def build(store, name: str, city: str, lang: str, now: dt.datetime, weather=weather_today) -> str:
    """The note itself, in the interface language."""
    tr = lambda s, **kw: t(s, lang, **kw)                 # noqa: E731
    day = f"{tr(DAYS[now.weekday()])}, {now:%d.%m}"
    lines = [tr("Good morning, {name}! Today is {day}.", name=name, day=day) if name
             else tr("Good morning! Today is {day}.", day=day)]
    if city.strip():
        w = weather(city, lang)
        if w:
            lines.append(f"{sky(w['code'])} " + tr("{place}: {min}…{max}°C, chance of rain {rain}%", place=w["place"],
                                                   min=_deg(w["tmin"]), max=_deg(w["tmax"]),
                                                   rain=w["rain"] if w["rain"] is not None else "?"))
        else:
            lines.append("🌡 " + tr("Couldn't get the weather for {place} right now.", place=city.strip()))
    end = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time()).timestamp()
    rems = [r for r in store.reminders() if r["due"] < end]
    if rems:
        lines.append("⏰ " + tr("Reminders today:"))
        lines += [f"• {dt.datetime.fromtimestamp(r['due']):%H:%M} {r['text']}" for r in rems[:8]]
    jobs = [x for x in store.tasks() if not x["paused"] and x["next"] < end]
    if jobs:
        lines.append("🔁 " + tr("Regular tasks today:"))
        lines += [f"• {dt.datetime.fromtimestamp(x['next']):%H:%M} {x['text']}" for x in jobs[:8]]
    if not rems and not jobs:
        lines.append(tr("No reminders or regular tasks for today."))
    return "\n".join(lines)


def due(on: bool, at: str, last: str, now: dt.datetime) -> bool:
    """Time for today's note: it's on, the time has come, it's still morning, and today's was not shown yet."""
    if not on or last == now.strftime("%Y-%m-%d"):
        return False
    hh, mm = (int(x) for x in clean_time(at).split(":"))
    return (now.hour, now.minute) >= (hh, mm) and now.hour < max(LATEST_HOUR, hh + 2)
