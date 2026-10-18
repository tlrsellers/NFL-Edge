"""News check: a small crawler that reads recent headlines for every team with a play.

The NFL publishes injury reports, but not in a free feed a bot can read, so
each lines scan asks Google News (its public RSS feed, no key needed) for the
last few days of headlines about each team with a pick, and flags headlines
that look like a quarterback problem or another injury.

Headlines show on the game's "Why" panel, with links, so you can read them.
They never change a tier: keyword matching can't tell "QB ruled out" from "QB
returns from injury", and the wind and playoff patterns don't depend on who
plays quarterback. A flagged headline is a prompt for a human look.

If the feed can't be reached the scan carries on without news.
"""

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FEED = "https://news.google.com/rss/search?"
DAYS = 4
MAX_HEADLINES = 5
PAUSE = 0.5  # seconds between requests, to be polite to the feed

QB = re.compile(r"\b(qb|quarterback|signal[- ]caller)s?\b", re.I)
TROUBLE = re.compile(
    r"\b(injur(y|ed|ies)(?! report)|ruled out|out for (the )?(season|year|game|week|sunday|monday|thursday)|won'?t play|will not play|doubtful|questionable|day[- ]to[- ]day|"
    r"suspend\w*|bench(ed|ing)|carted|surgery|concussion|torn|sidelined|game[- ]time decision|"
    r"(will|to) miss|misses|missing|unavailable|arrest\w*|dismiss\w*|leaves? (the )?team)\b", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("'", "").replace("ʻ", ""))


def classify(title):
    """'qb' for a quarterback problem, 'injury' for any other trouble, None for ordinary news."""
    if not TROUBLE.search(title):
        return None
    return "qb" if QB.search(title) else "injury"


def parse_feed(xml_text, team, full_name=None, now=None, days=DAYS):
    """Headlines from a Google News RSS document that mention the team, newest first."""
    now = now or datetime.now(timezone.utc)
    names = [_norm(team)] + ([_norm(full_name)] if full_name else [])
    out = []
    for item in ET.fromstring(xml_text).iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        if not any(n and n in _norm(title) for n in names):
            continue
        try:
            when = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if when < now - timedelta(days=days):
            continue
        out.append({"title": title, "link": item.findtext("link"), "source": source,
                    "published": when.astimezone(timezone.utc).isoformat(timespec="minutes"),
                    "flag": classify(title)})
    out.sort(key=lambda h: h["published"], reverse=True)
    return out


def fetch_team(team, full_name=None):
    query = f'"{full_name or team}" NFL when:{DAYS}d'
    url = FEED + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    req = urllib.request.Request(url, headers={"User-Agent": "nfl-edge/1.0 (personal betting dashboard)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return parse_feed(resp.read().decode("utf-8", "replace"), team, full_name)


def summarize(headlines):
    flagged = [h for h in headlines if h["flag"]]
    return {
        "qb_alert": any(h["flag"] == "qb" for h in headlines),
        "injury": any(h["flag"] == "injury" for h in headlines),
        # Flagged headlines first, then the latest news.
        "headlines": (flagged + [h for h in headlines if not h["flag"]])[:MAX_HEADLINES],
    }


def check_slate(games, full_names, fetch=fetch_team):
    """Attach game["news"] = {team: summary} to every game with a pick (model lean or better).
    Returns the number of teams checked (0 if the feed is down)."""
    cache, checked = {}, 0
    for g in games:
        picks = [p for p in g["picks"].values() if p and p["tier"] != "pass"]
        if not picks:
            continue
        news = {}
        for team in (g["away"], g["home"]):
            if team not in cache:
                try:
                    cache[team] = summarize(fetch(team, full_names.get(team)))
                    checked += 1
                except Exception as e:  # noqa: BLE001 - the scan must not fail because of the news
                    print(f"News check failed for {team}: {e}")
                    cache[team] = None
                if fetch is fetch_team:
                    time.sleep(PAUSE)
            if cache[team]:
                news[team] = cache[team]
        g["news"] = news
    return checked
