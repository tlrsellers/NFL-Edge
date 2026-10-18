"""Generated sample season in the same shape as the real data.

Used by the tests and by `--sample` runs so the dashboard renders without any
downloads. Every team has a hidden true strength; the tests check that the
grader recovers it. None of these numbers are real.
"""

from datetime import timedelta

import numpy as np

from .nflverse import NICK, TEAMS

CODES = sorted(TEAMS)


def sample_season(season=2026, weeks=6, seed=7):
    """(team-game rows, schedule rows) for `weeks` completed weeks plus one upcoming week."""
    rng = np.random.default_rng(seed)
    true_off = dict(zip(CODES, rng.normal(0, .08, len(CODES))))
    true_def = dict(zip(CODES, rng.normal(0, .08, len(CODES))))  # EPA allowed above average; lower is better
    rows, games = [], []
    for week in range(1, weeks + 2):
        order = list(rng.permutation(CODES))
        for i, (home, away) in enumerate(zip(order[::2], order[1::2])):
            gid = f"{season}_{week:02d}_{away}_{home}"
            date = f"{season}-09-{min(28, 6 + 7 * (week - 1)) if week < 4 else 28}"
            g = {"id": gid, "season": season, "week": week, "type": "REG", "date": date, "time": "13:00",
                 "weekday": "Sunday", "home": home, "away": away, "neutral": False, "div_game": False,
                 "roof": "outdoors", "surface": None, "stadium": f"{TEAMS[home][0]} Stadium",
                 "home_qb": None, "away_qb": None, "home_score": None, "away_score": None,
                 "home_rest": 7.0, "away_rest": 7.0, "spread_line": None, "total_line": None,
                 "home_moneyline": None, "away_moneyline": None, "home_spread_odds": None,
                 "away_spread_odds": None, "over_odds": None, "under_odds": None, "temp": None, "wind": None,
                 "completed": False, "game_index": i}
            if week <= weeks:
                pts = {}
                for team, opp, venue in ((home, away, 1), (away, home, -1)):
                    epa = true_off[team] + true_def[opp] + .015 * venue + rng.normal(0, .07)
                    plays = int(rng.normal(60, 5))
                    pass_n = int(plays * .6)
                    rush_n = plays - pass_n
                    p_epa, r_epa = epa + .05 + rng.normal(0, .05), epa - .07 + rng.normal(0, .05)
                    pts[team] = max(0, int(round(22 + 60 * epa + rng.normal(0, 6))))
                    sr = min(.7, max(.25, .45 + epa))
                    rows.append({
                        "season": season, "week": week, "game_id": gid, "team": team, "opp": opp, "home": venue,
                        "plays": plays, "epa": p_epa * pass_n + r_epa * rush_n, "success": round(sr * plays),
                        "explosive": round(.08 * plays), "pass_n": pass_n, "pass_epa": p_epa * pass_n,
                        "pass_success": round(sr * pass_n), "pass_explosive": round(.07 * pass_n),
                        "rush_n": rush_n, "rush_epa": r_epa * rush_n, "rush_success": round((sr - .05) * rush_n),
                        "rush_stuffed": round(.18 * rush_n), "havoc": round(.15 * plays), "trips": 5,
                        "trip_points": max(0, 4 * 5 + 60 * epa), "drives": 11, "start_pos": 11 * 30.0,
                        "st_epa": rng.normal(0, 2), "points": pts[team], "qb_id": f"QB-{team}",
                        "qb_name": f"{team} Starter", "qb_dropbacks": pass_n, "qb_epa": p_epa * pass_n})
                g.update(home_score=pts[home], away_score=pts[away], completed=True)
            games.append(g)
    return rows, games


def sample_slate_inputs(grades, now):
    """(schedule, odds events, credits, forecasts): next week's games kicking off soon, with fake lines."""
    _, games = sample_season(grades["season"])
    from .nflverse import STADIUMS
    upcoming = [g for g in games if not g["completed"]]
    outdoor = [g["id"] for g in upcoming if STADIUMS[g["home"]][2] == "outdoors"]
    windy = {outdoor[0]: (17.0, "15 to 20 mph"), outdoor[1]: (12.0, "12 mph")}
    events, forecasts = [], {}
    for i, g in enumerate(upcoming):
        k = now + timedelta(hours=20 + 3 * i)
        from zoneinfo import ZoneInfo
        local = k.astimezone(ZoneInfo("America/New_York"))
        g["date"], g["time"] = local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
        spread = round((i % 7 - 3) * 1.5 * 2) / 2
        total = 40.5 + i % 6
        events.append({"id": g["id"], "home_team": TEAMS[g["home"]][0], "away_team": TEAMS[g["away"]][0],
                       "commence_time": k.isoformat().replace("+00:00", "Z"),
                       "bookmakers": [{"key": b, "markets": [
                           {"key": "spreads", "outcomes": [{"name": TEAMS[g["home"]][0], "point": spread + d, "price": -110},
                                                           {"name": TEAMS[g["away"]][0], "point": -spread - d, "price": -110}]},
                           {"key": "totals", "outcomes": [{"name": "Over", "point": total + d, "price": -110},
                                                          {"name": "Under", "point": total + d, "price": -110}]}]}
                           for b, d in (("draftkings", 0), ("fanduel", .5), ("bovada", 0))]})
        if g["id"] in windy:
            forecasts[g["id"]] = {"wind": windy[g["id"]][0], "wind_text": windy[g["id"]][1],
                                  "temp": 48, "short": "Windy", "rain": 10,
                                  "checked": now.isoformat(timespec="minutes").replace("+00:00", "Z")}
    return [g for g in games if g["completed"]] + upcoming, events, 480, forecasts


__all__ = ["sample_season", "sample_slate_inputs", "NICK"]
