"""Build site/data/slate.json: this week's games, live lines, weather, projections and picks.

    python -m nfl_edge.slate            # needs ODDS_API_KEY
    python -m nfl_edge.slate --sample   # offline sample slate, no key

Each run also appends a snapshot to site/data/lines.json (line history, used
for "since open" movement), checks the wind forecast for outdoor games, saves
every Lean-or-better call to picks.json, and lists new LOCKs on the dashboard's
feed. It never emails anyone; the newsletter (newsletter.py) does that.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import news, nflverse, odds, track, weather
from .explain import explain_game
from .nflverse import NICK, TEAMS
from .picks import RANK, best_pick, spread_pick, total_pick
from .projections import project

DATA = Path(__file__).resolve().parent.parent / "site" / "data"
LOOKAHEAD_DAYS = 8
MOVE_ALERT = 1.0  # points moved between two scans that earns a feed entry


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _consensus(books, key):
    vals = [b[key] for b in books.values() if b.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def upcoming_games(schedule, now):
    """Schedule rows kicking off from 4 hours ago to LOOKAHEAD_DAYS ahead, with kickoff times in UTC."""
    out = []
    for g in schedule:
        if g["completed"]:
            continue
        k = nflverse.kickoff_utc(g)
        if now - timedelta(hours=4) <= k <= now + timedelta(days=LOOKAHEAD_DAYS):
            out.append({**g, "start": _iso(k), "kickoff": k})
    return sorted(out, key=lambda g: g["start"])


def build_slate(grades, games, events, history, now, forecasts=None):
    """Pure function: returns (slate, history, new_alerts). `games` from upcoming_games()."""
    model = grades["model"]
    forecasts = forecasts or {}
    by_pair = {}
    unmatched = 0
    for e in events:
        h, a = odds.team(e["home_team"]), odds.team(e["away_team"])
        if not h or not a:
            unmatched += 1
            continue
        by_pair.setdefault(frozenset((h, a)), []).append(e)

    stamp = _iso(now)
    out, alerts = [], []
    for g in games:
        home, away, neutral = NICK[g["home"]], NICK[g["away"]], g["neutral"]
        proj = project(model, home, away, neutral)
        books = {}
        cands = by_pair.get(frozenset((home, away)), [])
        event = min(cands, key=lambda e: abs((_parse(e["commence_time"]) - g["kickoff"]).total_seconds()), default=None)
        if event and abs((_parse(event["commence_time"]) - g["kickoff"]).total_seconds()) < 2 * 86400:
            books = odds.parse_event(event)
            if odds.team(event["home_team"]) != home:  # books list the teams the other way round
                books = {k: _flip(v) for k, v in books.items()}
        key = g["id"]
        h = history.setdefault(key, {"start": g["start"], "open": None, "snaps": []})
        s_now, t_now = _consensus(books, "spread_home"), _consensus(books, "total")
        if s_now is not None or t_now is not None:
            if h["open"] is None:
                h["open"] = {"spread_home": s_now, "total": t_now, "t": stamp}
            last = h["snaps"][-1] if h["snaps"] else None
            if last and s_now is not None and last[1] is not None and abs(s_now - last[1]) >= MOVE_ALERT:
                alerts.append({"t": stamp, "kind": "move", "game": key,
                               "text": f"{home} moved {last[1]:+g} to {s_now:+g} against the {away}."})
            if last and t_now is not None and last[2] is not None and abs(t_now - last[2]) >= MOVE_ALERT:
                alerts.append({"t": stamp, "kind": "move", "game": key,
                               "text": f"{away} @ {home} total moved {last[2]:g} to {t_now:g}."})
            h["snaps"].append([stamp, s_now, t_now])
        op = h["open"] or {}
        wx = forecasts.get(key)
        outdoor = weather.outdoor(g["home"], neutral)
        ctx_total = {"outdoor": outdoor, "wind": wx and wx.get("wind"),
                     "forecast_hours": wx and (g["kickoff"] - _parse(wx["checked"])).total_seconds() / 3600}
        sp = spread_pick(proj, books, home, away, None, {"playoff": g["type"] != "REG"})
        tp = total_pick(proj, books, None, ctx_total)
        _movement(sp, tp, home, op, s_now, t_now)
        out.append({
            "id": key, "start": g["start"], "week": g["week"], "type": g["type"], "neutral": neutral,
            "div_game": g["div_game"], "home": home, "away": away, "venue": g.get("stadium"),
            "roof": "outdoors" if outdoor else (nflverse.STADIUMS.get(g["home"], (0, 0, "unknown"))[2] if not neutral else "neutral site"),
            "weather": wx, "lines": books, "open": h["open"], "history": h["snaps"][-40:],
            "projection": proj, "picks": {"spread": sp, "total": tp}, "best": best_pick(sp, tp),
        })
    slate = {
        "updated": stamp,
        "week": min((g["week"] for g in out), default=None),
        "season": grades.get("season"),
        "sample": bool(grades.get("sample")),
        "unmatched_events": unmatched,
        "games": out,
    }
    for key in [k for k, v in history.items() if _parse(v["start"]) < now - timedelta(days=3)]:
        del history[key]
    return slate, history, alerts


def _movement(sp, tp, home, opened, s_now, t_now):
    """Points the market average has moved against each pick's side since the first scan (consensus vs consensus)."""
    o_s, o_t = opened.get("spread_home"), opened.get("total")
    if sp and o_s is not None and s_now is not None:
        sp["moved_against"] = round((s_now - o_s) if sp["side"] == home else (o_s - s_now), 1)
    if tp and o_t is not None and t_now is not None:
        tp["moved_against"] = round((o_t - t_now) if tp["side"] == "Over" else (t_now - o_t), 1)


def _flip(line):
    out = dict(line)
    if line.get("spread_home") is not None:
        out["spread_home"] = -line["spread_home"]
        out["spread_home_price"], out["spread_away_price"] = line.get("spread_away_price"), line.get("spread_home_price")
    return out


def lock_alerts(slate, sent):
    """New LOCK picks not alerted before. `sent` is the set of keys already alerted."""
    new = []
    for g in slate["games"]:
        for p in (g["picks"]["spread"], g["picks"]["total"]):
            if p and p["tier"] == "lock":
                key = f'{g["id"]}:{p["bet"]}:{p["side"]}'
                if key not in sent:
                    new.append((key, g, p))
    return new


def full_names():
    return {NICK[c]: t[0] for c, t in TEAMS.items()}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sample", action="store_true", help="offline sample slate (no API key)")
    p.add_argument("--no-news", action="store_true", help="skip the headline check")
    p.add_argument("--no-weather", action="store_true", help="skip the wind forecasts")
    args = p.parse_args(argv)
    now = datetime.now(timezone.utc)
    grades = _load(DATA / "grades.json", None)
    if not args.sample and (not grades or "model" not in grades):
        from . import build  # first run: build grades so the projection model exists
        build.main([])
        grades = _load(DATA / "grades.json", None)
    if not grades or "model" not in grades:
        raise SystemExit("grades.json has no projection model. Run: python -m nfl_edge.build --sample")

    if args.sample:
        from .sample import sample_slate_inputs
        schedule, events, credits, forecasts = sample_slate_inputs(grades, now)
        games, history = upcoming_games(schedule, now), {}
    else:
        schedule = nflverse.schedule()
        games = upcoming_games(schedule, now)
        events, credits = odds.fetch_odds()
        history = _load(DATA / "lines.json", {})
        forecasts = {} if args.no_weather else weather.check_games(
            [(g["id"], g["home"], g["kickoff"], g["neutral"]) for g in games], now)
        print(f"Wind forecasts for {len(forecasts)} outdoor games.")

    slate, history, feed_new = build_slate(grades, games, events, history, now, forecasts)
    slate["credits_remaining"] = credits

    if not args.sample and not args.no_news:
        checked = news.check_slate(slate["games"], full_names())
        print(f"News checked for {checked} teams.")
        for g in slate["games"]:
            g["best"] = best_pick(g["picks"]["spread"], g["picks"]["total"])

    # Explain each pick, then save and grade every call.
    log = _load(DATA / "picks.json", {}).get("picks", {}) if not args.sample else {}
    track.grade(log, schedule)
    summary = track.summarize(log)
    evidence = track.evidence(summary)
    team_grades = {t["team"]: t for t in grades["teams"]}
    for g in slate["games"]:
        explain_game(g, team_grades, grades["model"], evidence)
    track.record_calls(log, slate["games"], slate["updated"])
    slate["record"] = track.summarize(log)

    alert_log = _load(DATA / "alerts.json", {"sent": [], "feed": []}) if not args.sample else {"sent": [], "feed": []}
    sent = set(alert_log["sent"])
    for key, game, pick in lock_alerts(slate, sent):
        sent.add(key)
        feed_new.append({"t": slate["updated"], "kind": "lock", "game": game["id"], "url": None,
                         "text": f"LOCK: {pick['label']} at {odds.BOOK_NAMES.get(pick['book'], pick['book'])} "
                                 f"({game['away']} @ {game['home']}), wind {pick.get('wind', 0):.0f} mph."})
    alert_log = {"sent": sorted(sent)[-300:], "feed": (feed_new + alert_log["feed"])[:60]}
    slate["feed"] = alert_log["feed"]

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "slate.json").write_text(json.dumps(slate, indent=1) + "\n")
    if not args.sample:
        (DATA / "lines.json").write_text(json.dumps(history) + "\n")
        (DATA / "alerts.json").write_text(json.dumps(alert_log, indent=1) + "\n")
        (DATA / "picks.json").write_text(json.dumps({"summary": slate["record"], "picks": log}, indent=1) + "\n")
    tiers = [g["best"]["tier"] for g in slate["games"] if g["best"]]
    print(f"{len(slate['games'])} games, {sum(1 for g in slate['games'] if g['lines'])} with lines, "
          f"{tiers.count('lock')} locks, {tiers.count('strong')} strong, {tiers.count('lean')} lean. "
          f"Odds credits left: {credits}. Unmatched odds events: {slate['unmatched_events']}.")


if __name__ == "__main__":
    main()
