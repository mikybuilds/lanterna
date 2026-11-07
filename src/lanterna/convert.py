"""Exact conversions the model shouldn't guess: currency (the official National Bank of Ukraine rates, about 60
currencies, any pair through the hryvnia) and units (length, weight, volume, area, speed, time, data, energy,
pressure, temperature). Units work offline; currency asks bank.gov.ua (cached for an hour)."""
from __future__ import annotations

import threading
import time

import httpx

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
CACHE_FOR = 3600
_cache: dict = {"at": 0.0, "rates": {}, "date": ""}
_lock = threading.Lock()

_CUR_ALIAS = {"грн": "UAH", "гривня": "UAH", "гривні": "UAH", "гривень": "UAH", "₴": "UAH", "$": "USD", "долар": "USD",
              "долари": "USD", "доларів": "USD", "dollar": "USD", "dollars": "USD", "€": "EUR", "євро": "EUR",
              "euro": "EUR", "euros": "EUR", "£": "GBP", "фунт": "GBP", "злотий": "PLN", "злотих": "PLN", "zł": "PLN",
              "zloty": "PLN", "¥": "JPY", "₺": "TRY"}


def nbu_rates(http: httpx.Client | None = None) -> tuple[dict[str, float], str]:
    """{code: hryvnias per 1 unit} and the date they are for. Cached for an hour."""
    with _lock:
        if _cache["rates"] and time.time() - _cache["at"] < CACHE_FOR and http is None:
            return _cache["rates"], _cache["date"]
    from .tools import _http
    c = http or _http()
    try:
        r = c.get(NBU_URL, params={"json": ""})
        r.raise_for_status()
        rows = r.json()
    finally:
        if http is None:
            c.close()
    rates = {"UAH": 1.0}
    date = ""
    for r in rows:
        if r.get("cc") and r.get("rate"):
            rates[str(r["cc"]).upper()] = float(r["rate"])
            date = r.get("exchangedate") or date
    if len(rates) < 5:
        raise ValueError("unexpected answer")
    if http is None:
        with _lock:
            _cache.update(at=time.time(), rates=rates, date=date)
    return rates, date


def _code(x: str) -> str:
    x = (x or "").strip()
    return _CUR_ALIAS.get(x.lower(), _CUR_ALIAS.get(x, x.upper()))


def _num(x: float) -> str:
    if float(x).is_integer() and abs(x) < 1e15:
        return f"{int(x):,}".replace(",", " ")
    if abs(x) >= 100:
        s = f"{x:,.2f}"
    elif abs(x) >= 1:
        s = f"{x:,.4f}".rstrip("0").rstrip(".")
    else:
        s = f"{x:.6g}"
    return s.replace(",", " ")


def currency(amount: float, src: str, dst: str, http: httpx.Client | None = None) -> str:
    try:
        amount = float(str(amount).replace(",", ".").replace(" ", ""))
    except ValueError:
        return "Error: amount must be a number."
    a, b = _code(src), _code(dst)
    try:
        rates, date = nbu_rates(http)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return "Error: the National Bank of Ukraine rates are not available right now (no internet?)."
    missing = [c for c in (a, b) if c not in rates]
    if missing:
        return f"Error: no official rate for {', '.join(missing)}. Use 3-letter codes like USD, EUR, PLN, UAH."
    value = amount * rates[a] / rates[b]
    money = f"{value:,.2f}".replace(",", " ") if abs(value) >= 0.01 else f"{value:.6g}"
    one = rates[a] / rates[b]
    return (f"{_num(amount)} {a} = {money} {b} (1 {a} = {_num(one)} {b}). Official National Bank of Ukraine "
            f"rate for {date}; banks and exchange offices buy and sell at their own rates.")


# ------------------------------------------------------------------------------------------- units
_DIMS: dict[str, dict[str, float]] = {
    "length": {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1, "km": 1000, "in": 0.0254, "ft": 0.3048, "yd": 0.9144,
               "mi": 1609.344, "nmi": 1852},
    "weight": {"mg": 1e-6, "g": 0.001, "kg": 1, "t": 1000, "oz": 0.028349523125, "lb": 0.45359237, "st": 6.35029318,
               "ct": 0.0002},
    "volume": {"ml": 0.001, "cl": 0.01, "dl": 0.1, "l": 1, "m3": 1000, "cm3": 0.001, "tsp": 0.00492892159375,
               "tbsp": 0.01478676478125, "cup": 0.2365882365, "floz": 0.0295735295625, "pt": 0.473176473,
               "qt": 0.946352946, "gal": 3.785411784, "ukgal": 4.54609},
    "area": {"mm2": 1e-6, "cm2": 1e-4, "m2": 1, "a": 100, "ha": 1e4, "km2": 1e6, "in2": 0.00064516, "ft2": 0.09290304,
             "yd2": 0.83612736, "acre": 4046.8564224, "mi2": 2589988.110336},
    "speed": {"m/s": 1, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 1852 / 3600, "ft/s": 0.3048},
    "time": {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800, "year": 31557600},
    "data": {"bit": 0.125, "kbit": 125, "mbit": 125e3, "gbit": 125e6, "b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "kib": 1024, "mib": 1024 ** 2,
             "gib": 1024 ** 3, "tib": 1024 ** 4},
    "energy": {"j": 1, "kj": 1e3, "cal": 4.184, "kcal": 4184, "wh": 3600, "kwh": 3.6e6},
    "pressure": {"pa": 1, "hpa": 100, "kpa": 1e3, "bar": 1e5, "atm": 101325, "mmhg": 133.322387415, "psi": 6894.757293168},
}
_ALIAS = {"meter": "m", "metre": "m", "meters": "m", "м": "m", "км": "km", "см": "cm", "мм": "mm", "inch": "in",
          "inches": "in", "дюйм": "in", "\"": "in", "foot": "ft", "feet": "ft", "фут": "ft", "'": "ft", "yard": "yd",
          "mile": "mi", "miles": "mi", "миля": "mi", "милі": "mi", "миль": "mi", "кг": "kg", "г": "g", "гр": "g",
          "мг": "mg", "т": "t", "ton": "t", "tonne": "t", "pound": "lb", "pounds": "lb", "lbs": "lb", "ounce": "oz",
          "унція": "oz", "фунт": "lb", "л": "l", "liter": "l", "litre": "l", "liters": "l", "мл": "ml", "м3": "m3",
          "m³": "m3", "cm³": "cm3", "gallon": "gal", "gallons": "gal", "галон": "gal", "pint": "pt", "quart": "qt",
          "cups": "cup", "склянка": "cup", "м2": "m2", "m²": "m2", "км2": "km2", "km²": "km2", "см2": "cm2",
          "cm²": "cm2", "ft²": "ft2", "га": "ha", "hectare": "ha", "сотка": "a", "соток": "a", "сотки": "a", "ар": "a",
          "acres": "acre", "кмгод": "km/h", "км/год": "km/h", "км/г": "km/h", "kmh": "km/h", "kph": "km/h",
          "м/с": "m/s", "mps": "m/s", "knot": "kn", "knots": "kn", "вузол": "kn", "сек": "s", "с": "s", "sec": "s",
          "хв": "min", "хвилина": "min", "minute": "min", "minutes": "min", "год": "h", "hour": "h", "hours": "h",
          "hr": "h", "днів": "day", "день": "day", "дні": "day", "days": "day", "d": "day", "тиждень": "week",
          "weeks": "week", "рік": "year", "років": "year", "years": "year", "byte": "b", "bytes": "b", "кб": "kb",
          "мб": "mb", "гб": "gb", "тб": "tb", "дж": "j", "кдж": "kj", "кал": "cal", "ккал": "kcal", "квт·год": "kwh",
          "квтгод": "kwh", "kw·h": "kwh", "мм рт. ст.": "mmhg", "мм рт ст": "mmhg", "гпа": "hpa", "атм": "atm"}
_TEMP = {"c": "c", "°c": "c", "celsius": "c", "ц": "c", "°ц": "c", "f": "f", "°f": "f", "fahrenheit": "f",
         "k": "k", "kelvin": "k", "к": "k"}


def _unit(u: str) -> str:
    u = (u or "").strip()
    low = u.lower()
    if u in ("Mb", "Mbit", "Mbps"):                        # megabit, not megabyte
        return "mbit"
    if u in ("Gb", "Gbit"):
        return "gbit"
    return _ALIAS.get(low, low)


def _to_c(v: float, u: str) -> float:
    return v if u == "c" else (v - 32) * 5 / 9 if u == "f" else v - 273.15


def convert_units(value: float, src: str, dst: str) -> str:
    try:
        v = float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        return "Error: value must be a number."
    ts, td = _TEMP.get((src or "").strip().lower()), _TEMP.get((dst or "").strip().lower())
    if ts and td:
        c = _to_c(v, ts)
        out = c if td == "c" else c * 9 / 5 + 32 if td == "f" else c + 273.15
        sign = lambda u: "K" if u == "k" else "°" + u.upper()        # noqa: E731
        return f"{_num(v)} {sign(ts)} = {_num(round(out, 4))} {sign(td)}"
    a, b = _unit(src), _unit(dst)
    for table in _DIMS.values():
        if a in table and b in table:
            out = v * table[a] / table[b]
            return f"{_num(v)} {a} = {_num(out)} {b}"
    known = [u for u in (a, b) if not any(u in t for t in _DIMS.values())]
    if known:
        return f"Error: unknown unit {', '.join(known)}. Use short names like km, mi, kg, lb, l, gal, m2, ha, km/h, gb, kwh, c, f."
    return f"Error: can't convert {a} to {b}: they measure different things."
