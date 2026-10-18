"""Kickoff wind forecasts from the National Weather Service (api.weather.gov). Free, no key.

Wind is the one thing in 27 seasons of NFL lines that beat the market year
after year: at outdoor stadiums with 15+ mph wind, Unders went 384-290 (57.0%)
and were profitable in 17 of 27 seasons (docs/research/line-history.md).

For each upcoming game at an outdoor home stadium, this reads the NWS hourly
forecast for the stadium and takes the wind for the kickoff hour. Domes and
retractable roofs are skipped (teams close them in bad weather), and so are
neutral-site games abroad, which NWS doesn't cover.

Forecasts more than a few days out are rough. picks.py only makes a LOCK when
the forecast was read within LOCK_FORECAST_HOURS of kickoff.
"""

import json
import re
import time
import urllib.request
from datetime import datetime, timezone

from .nflverse import STADIUMS

API = "https://api.weather.gov"
HEADERS = {"User-Agent": "nfl-edge weather check (github.com/nfl-edge)", "Accept": "application/geo+json"}
PAUSE = 0.3
MAX_DAYS = 7  # NWS hourly forecasts run about 7 days ahead


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def parse_wind(text):
    """'10 mph' -> 10, '10 to 15 mph' -> 12.5, '' -> None."""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]
    return sum(nums) / len(nums) if nums else None


def kickoff_period(periods, kickoff):
    """The hourly period that contains kickoff (or the closest one)."""
    best, gap = None, None
    for p in periods:
        try:
            start = datetime.fromisoformat(p["startTime"])
            end = datetime.fromisoformat(p["endTime"])
        except (KeyError, ValueError):
            continue
        if start <= kickoff < end:
            return p
        d = abs((start - kickoff).total_seconds())
        if gap is None or d < gap:
            best, gap = p, d
    return best if gap is not None and gap <= 3 * 3600 else None


def outdoor(home_code, neutral):
    s = STADIUMS.get(home_code)
    return bool(s) and not neutral and s[2] == "outdoors"


def forecast(home_code, kickoff, get=_get):
    """{'wind': mph, 'temp': F, 'short': 'Partly Sunny', 'checked': iso} for an outdoor home game, else None."""
    lat, lon, _ = STADIUMS[home_code]
    point = get(f"{API}/points/{lat:.4f},{lon:.4f}")
    url = point["properties"]["forecastHourly"]
    if not url.startswith(API + "/"):
        raise ValueError("Unexpected forecast URL")
    hourly = get(url)
    p = kickoff_period(hourly["properties"]["periods"], kickoff)
    if not p:
        return None
    return {"wind": parse_wind(p.get("windSpeed")), "wind_text": p.get("windSpeed"),
            "temp": p.get("temperature"), "short": p.get("shortForecast"),
            "rain": (p.get("probabilityOfPrecipitation") or {}).get("value"),
            "checked": datetime.now(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")}


def check_games(games, now, get=_get):
    """games: [(game_id, home_code, kickoff_utc, neutral)]. Returns {game_id: forecast} for outdoor games
    within MAX_DAYS. Failures are skipped so the scan never stops for the weather."""
    out = {}
    for gid, home, kickoff, neutral in games:
        if not outdoor(home, neutral) or (kickoff - now).total_seconds() > MAX_DAYS * 86400 or kickoff < now:
            continue
        try:
            f = forecast(home, kickoff, get)
            if f:
                out[gid] = f
        except Exception as e:  # noqa: BLE001 - weather must not break the scan
            print(f"Weather check failed for {home}: {e}")
        if get is _get:
            time.sleep(PAUSE)
    return out
