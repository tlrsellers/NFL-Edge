"""DraftKings, FanDuel and Bovada NFL spreads and totals from The Odds API (https://the-odds-api.com).

One call returns every upcoming NFL game. The Odds API bills by market and by
group of up to 10 books, so two markets at three books costs 2 credits a scan,
the same as one book. The key comes from ODDS_API_KEY.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .nflverse import FULL_TO_CODE, NICK

URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
BOOKS = ("draftkings", "fanduel", "bovada")
BOOK_NAMES = {"draftkings": "DraftKings", "fanduel": "FanDuel", "bovada": "Bovada"}


class OddsError(RuntimeError):
    pass


def fetch_odds():
    """Returns (events, credits_remaining)."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise OddsError("ODDS_API_KEY is not set. Get a free key at the-odds-api.com.")
    query = urllib.parse.urlencode({
        "apiKey": key, "markets": "spreads,totals", "bookmakers": ",".join(BOOKS),
        "oddsFormat": "american", "dateFormat": "iso",
    })
    try:
        with urllib.request.urlopen(f"{URL}?{query}", timeout=60) as resp:
            remaining = resp.headers.get("x-requests-remaining")
            return json.load(resp), (int(float(remaining)) if remaining else None)
    except urllib.error.HTTPError as e:
        # Never print the URL: it contains the key.
        raise OddsError(f"The Odds API returned HTTP {e.code}") from None


def team(name):
    """'Kansas City Chiefs' -> 'Chiefs' (the name the site uses), or None."""
    code = FULL_TO_CODE.get(str(name).casefold())
    return NICK.get(code) if code else None


def parse_event(event):
    """One Odds API event -> {book: {spread_home, spread_home_price, spread_away_price, total, over_price, under_price}}."""
    home, away = event["home_team"], event["away_team"]
    books = {}
    for b in event.get("bookmakers", []):
        if b.get("key") not in BOOKS:
            continue
        line = {}
        for m in b.get("markets", []):
            outcomes = {o.get("name"): o for o in m.get("outcomes", [])}
            if m.get("key") == "spreads" and home in outcomes and away in outcomes:
                line["spread_home"] = outcomes[home].get("point")
                line["spread_home_price"] = outcomes[home].get("price")
                line["spread_away_price"] = outcomes[away].get("price")
            elif m.get("key") == "totals" and "Over" in outcomes and "Under" in outcomes:
                line["total"] = outcomes["Over"].get("point")
                line["over_price"] = outcomes["Over"].get("price")
                line["under_price"] = outcomes["Under"].get("price")
        if line:
            books[b["key"]] = line
    return books
