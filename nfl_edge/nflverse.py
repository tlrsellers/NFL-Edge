"""Free NFL data from nflverse (https://github.com/nflverse/nflverse-data). No key needed.

* Schedule (games.csv): every game since 1999 with final score, rest days, roof,
  weather and the closing spread, total and moneylines.
* Play-by-play (play_by_play_<season>.csv.gz): every play with EPA, success and
  drive info. Only the current season is used for team grades.

Both are cached in data/raw/ for 50 minutes so a run doesn't download twice.
"""

import csv
import gzip
import io
import os
import time
import urllib.request
from pathlib import Path

RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"
SCHEDULE_URL = f"{RELEASES}/schedules/games.csv"
PBP_URL = RELEASES + "/pbp/play_by_play_{season}.csv.gz"
CACHE = Path(os.environ.get("NFL_EDGE_CACHE", Path(__file__).resolve().parent.parent / "data" / "raw"))
MAX_AGE = 50 * 60

# Abbreviation -> (name, nickname, division, color). nflverse codes; old codes map in FRANCHISE.
TEAMS = {
    "ARI": ("Arizona Cardinals", "Cardinals", "NFC West", "#97233F"),
    "ATL": ("Atlanta Falcons", "Falcons", "NFC South", "#A71930"),
    "BAL": ("Baltimore Ravens", "Ravens", "AFC North", "#241773"),
    "BUF": ("Buffalo Bills", "Bills", "AFC East", "#00338D"),
    "CAR": ("Carolina Panthers", "Panthers", "NFC South", "#0085CA"),
    "CHI": ("Chicago Bears", "Bears", "NFC North", "#0B162A"),
    "CIN": ("Cincinnati Bengals", "Bengals", "AFC North", "#FB4F14"),
    "CLE": ("Cleveland Browns", "Browns", "AFC North", "#311D00"),
    "DAL": ("Dallas Cowboys", "Cowboys", "NFC East", "#003594"),
    "DEN": ("Denver Broncos", "Broncos", "AFC West", "#FB4F14"),
    "DET": ("Detroit Lions", "Lions", "NFC North", "#0076B6"),
    "GB": ("Green Bay Packers", "Packers", "NFC North", "#203731"),
    "HOU": ("Houston Texans", "Texans", "AFC South", "#03202F"),
    "IND": ("Indianapolis Colts", "Colts", "AFC South", "#002C5F"),
    "JAX": ("Jacksonville Jaguars", "Jaguars", "AFC South", "#006778"),
    "KC": ("Kansas City Chiefs", "Chiefs", "AFC West", "#E31837"),
    "LA": ("Los Angeles Rams", "Rams", "NFC West", "#003594"),
    "LAC": ("Los Angeles Chargers", "Chargers", "AFC West", "#0080C6"),
    "LV": ("Las Vegas Raiders", "Raiders", "AFC West", "#000000"),
    "MIA": ("Miami Dolphins", "Dolphins", "AFC East", "#008E97"),
    "MIN": ("Minnesota Vikings", "Vikings", "NFC North", "#4F2683"),
    "NE": ("New England Patriots", "Patriots", "AFC East", "#002244"),
    "NO": ("New Orleans Saints", "Saints", "NFC South", "#D3BC8D"),
    "NYG": ("New York Giants", "Giants", "NFC East", "#0B2265"),
    "NYJ": ("New York Jets", "Jets", "AFC East", "#125740"),
    "PHI": ("Philadelphia Eagles", "Eagles", "NFC East", "#004C54"),
    "PIT": ("Pittsburgh Steelers", "Steelers", "AFC North", "#FFB612"),
    "SEA": ("Seattle Seahawks", "Seahawks", "NFC West", "#002244"),
    "SF": ("San Francisco 49ers", "49ers", "NFC West", "#AA0000"),
    "TB": ("Tampa Bay Buccaneers", "Buccaneers", "NFC South", "#D50A0A"),
    "TEN": ("Tennessee Titans", "Titans", "AFC South", "#4B92DB"),
    "WAS": ("Washington Commanders", "Commanders", "NFC East", "#5A1414"),
}
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}
NICK = {c: t[1] for c, t in TEAMS.items()}           # "KC" -> "Chiefs": the name the site shows
BY_NICK = {t[1]: c for c, t in TEAMS.items()}
ALIASES = {"Washington Football Team": "WAS", "Washington Redskins": "WAS", "Oakland Raiders": "LV",
           "St. Louis Rams": "LA", "San Diego Chargers": "LAC", "LA Rams": "LA", "LA Chargers": "LAC"}
FULL_TO_CODE = {t[0].casefold(): c for c, t in TEAMS.items()}
FULL_TO_CODE.update({n.casefold(): c for n, c in ALIASES.items()})

# Home stadium: (latitude, longitude, roof). "retractable" roofs are treated as closed
# for weather, since teams usually close them in bad weather.
STADIUMS = {
    "ARI": (33.528, -112.263, "retractable"), "ATL": (33.755, -84.401, "retractable"),
    "BAL": (39.278, -76.623, "outdoors"), "BUF": (42.773, -78.787, "outdoors"),
    "CAR": (35.226, -80.853, "outdoors"), "CHI": (41.862, -87.617, "outdoors"),
    "CIN": (39.095, -84.516, "outdoors"), "CLE": (41.506, -81.699, "outdoors"),
    "DAL": (32.748, -97.093, "retractable"), "DEN": (39.743, -105.020, "outdoors"),
    "DET": (42.340, -83.046, "dome"), "GB": (44.501, -88.062, "outdoors"),
    "HOU": (29.685, -95.411, "retractable"), "IND": (39.760, -86.164, "retractable"),
    "JAX": (30.324, -81.638, "outdoors"), "KC": (39.049, -94.484, "outdoors"),
    "LA": (33.953, -118.339, "dome"), "LAC": (33.953, -118.339, "dome"),
    "LV": (36.090, -115.183, "dome"), "MIA": (25.958, -80.239, "outdoors"),
    "MIN": (44.974, -93.258, "dome"), "NE": (42.091, -71.264, "outdoors"),
    "NO": (29.951, -90.081, "dome"), "NYG": (40.813, -74.074, "outdoors"),
    "NYJ": (40.813, -74.074, "outdoors"), "PHI": (39.901, -75.167, "outdoors"),
    "PIT": (40.447, -80.016, "outdoors"), "SEA": (47.595, -122.332, "outdoors"),
    "SF": (37.403, -121.970, "outdoors"), "TB": (27.976, -82.503, "outdoors"),
    "TEN": (36.166, -86.771, "outdoors"), "WAS": (38.908, -76.864, "outdoors"),
}


def code(abbr):
    return FRANCHISE.get(abbr, abbr)


def nick(abbr):
    """Team code (any era) -> nickname, e.g. "STL" -> "Rams"."""
    return NICK.get(code(abbr), abbr)


def _fetch(url, path, max_age=MAX_AGE):
    if path.exists() and time.time() - path.stat().st_mtime < max_age:
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "nfl-edge (github.com)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            break
        except OSError:
            if attempt == 2:
                if path.exists():
                    return path.read_bytes()  # a stale copy beats nothing
                raise
            time.sleep(3 * (attempt + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def schedule(path=None):
    """Every game (regular season and playoffs) as dicts with numeric fields parsed."""
    raw = Path(path).read_bytes() if path else _fetch(SCHEDULE_URL, CACHE / "games.csv")
    rows = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        g = {
            "id": r["game_id"], "season": int(r["season"]), "week": int(r["week"]),
            "type": r["game_type"], "date": r["gameday"], "time": r.get("gametime") or "13:00",
            "weekday": r.get("weekday"), "home": code(r["home_team"]), "away": code(r["away_team"]),
            "neutral": r.get("location") == "Neutral", "div_game": r.get("div_game") == "1",
            "roof": r.get("roof") or None, "surface": r.get("surface") or None,
            "stadium": r.get("stadium") or None,
            "home_qb": r.get("home_qb_name") or None, "away_qb": r.get("away_qb_name") or None,
        }
        for k in ("home_score", "away_score", "home_rest", "away_rest", "spread_line", "total_line",
                  "home_moneyline", "away_moneyline", "home_spread_odds", "away_spread_odds",
                  "over_odds", "under_odds", "temp", "wind"):
            g[k] = _num(r.get(k))
        g["completed"] = g["home_score"] is not None and g["away_score"] is not None
        rows.append(g)
    return rows


def kickoff_utc(g):
    """nflverse lists Eastern kickoff times."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    t = datetime.strptime(f"{g['date']} {g['time'] or '13:00'}", "%Y-%m-%d %H:%M")
    return t.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(ZoneInfo("UTC"))


def pbp(season, path=None):
    """Yields play rows (dicts of strings) for one season, streaming the gzip."""
    if path:
        data = Path(path).read_bytes()
    else:
        data = _fetch(PBP_URL.format(season=season), CACHE / f"pbp_{season}.csv.gz")
    with gzip.open(io.BytesIO(data), "rt", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)
