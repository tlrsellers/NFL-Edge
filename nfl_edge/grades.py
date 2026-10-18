"""0-10 unit grades for all 32 NFL teams, from this season's games only.

Scale: 5.0 is NFL average and each point is half a standard deviation, so a
7.0 unit is one standard deviation above average. Grades are clipped to 0-10.

Pipeline:
  1. One row per offense per game (stats.py): EPA, success and explosive-play
     rates for passes and runs, havoc, red-zone-ish trips (drives reaching the
     opponent 40) and the points they produced, special-teams EPA, plays.
  2. Each per-game metric is opponent- and venue-adjusted (adjust.py). The last
     RECENT_WEEKS weeks count RECENT_WEIGHT times as much as earlier games.
  3. Adjusted metrics are standardized across the league and blended into units.
  4. Unit scores are standardized again and mapped onto the 0-10 scale.

Quarterback: the passer who started the team's most recent game, graded on his
EPA per dropback this season (shrunk toward average until he has
QB_SHRINK_DROPBACKS), blended 70/30 with the passing unit. If he isn't the
season's main passer the grade says so: a QB change is the biggest thing a
stats model can miss.
"""

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from .adjust import opponent_adjust
from .nflverse import BY_NICK, NICK, TEAMS

RECENT_WEEKS = 4
RECENT_WEIGHT = 1.0  # recency weighting made NFL projections slightly worse
QB_SHRINK_DROPBACKS = 150
RIDGE = {"default": 6.0, "points": 6.0}  # tuned on 2010-2025 replays: steadier than 2.0

# metric -> (numerator column, denominator column). Per-game rates.
RATES = {
    "epa": ("epa", "plays"), "success": ("success", "plays"), "explosive": ("explosive", "plays"),
    "pass_epa": ("pass_epa", "pass_n"), "pass_success": ("pass_success", "pass_n"),
    "pass_explosive": ("pass_explosive", "pass_n"),
    "rush_epa": ("rush_epa", "rush_n"), "rush_success": ("rush_success", "rush_n"),
    "rush_stuffed": ("rush_stuffed", "rush_n"),
    "havoc": ("havoc", "plays"), "ppt": ("trip_points", "trips"),
}

# Unit blends: (metric, side, weight). "off" = what the offense does, "def" = what the
# defense allows (negated where allowing less is better).
UNITS = {
    "off": [("epa", "off", .45), ("success", "off", .25), ("explosive", "off", .10),
            ("ppt", "off", .10), ("havoc", "off", -.10)],
    "pass": [("pass_epa", "off", .55), ("pass_success", "off", .30), ("pass_explosive", "off", .15)],
    "rush": [("rush_epa", "off", .45), ("rush_success", "off", .35), ("rush_stuffed", "off", -.20)],
    "def": [("epa", "def", -.45), ("success", "def", -.25), ("explosive", "def", -.10),
            ("ppt", "def", -.10), ("havoc", "def", .10)],
    "passD": [("pass_epa", "def", -.55), ("pass_success", "def", -.30), ("pass_explosive", "def", -.15)],
    "rushD": [("rush_epa", "def", -.45), ("rush_success", "def", -.35), ("rush_stuffed", "def", .20)],
}
GRADE_KEYS = ("off", "pass", "rush", "qb", "def", "passD", "rushD", "st", "pace", "ovr")


def _z(values, teams):
    arr = np.array([values[t] for t in teams if values.get(t) is not None], dtype=float)
    if arr.size < 2 or arr.std() == 0:
        return {t: 0.0 for t in teams}
    mean, std = arr.mean(), arr.std()
    return {t: (values[t] - mean) / std if values.get(t) is not None else 0.0 for t in teams}


def to_grade(z):
    return round(float(np.clip(5 + 2 * z, 0, 10)), 1)


def _rate(row, metric):
    num, den = RATES[metric]
    return row[num] / row[den] if row[den] else None


def grade_season(rows, season, games=(), now=None, through_week=None):
    """rows: team-game rows (stats.py) for `season`. games: schedule rows, for records.

    through_week: only use games before this week (the backtest replays weeks this way).
    """
    # Teams are keyed by nickname ("Chiefs") everywhere the site sees them.
    rows = [dict(r, team=NICK.get(r["team"], r["team"]), opp=NICK.get(r["opp"], r["opp"]))
            for r in rows if r["season"] == season and (through_week is None or r["week"] < through_week)]
    teams = sorted(NICK.values())
    last_week = max((r["week"] for r in rows), default=0)

    def weight(r):
        return RECENT_WEIGHT if r["week"] > last_week - RECENT_WEEKS else 1.0

    metric_rows = defaultdict(list)
    plays, games_played, st, field = defaultdict(list), defaultdict(int), defaultdict(list), defaultdict(list)
    by_game = defaultdict(dict)
    epa_fit = []
    for r in rows:
        t, o, wt, v = r["team"], r["opp"], weight(r), r["home"]
        games_played[t] += 1
        by_game[r["game_id"]][t] = r
        for m in RATES:
            metric_rows[m].append((t, o, _rate(r, m), wt, v))
        metric_rows["points"].append((t, o, r["points"], wt, v))
        if r["plays"]:
            plays[t].append(r["plays"])
            epa_fit.append((r["epa"] / r["plays"], r["plays"], r["points"]))
        st[t].append(r["st_epa"])
        if r["drives"]:
            field[t].append(r["start_pos"] / r["drives"])
    # Field position battle: my average start minus my opponents' average start.
    fp_net = defaultdict(list)
    for gid, pair in by_game.items():
        if len(pair) == 2:
            a, b = pair.values()
            if a["drives"] and b["drives"]:
                d = a["start_pos"] / a["drives"] - b["start_pos"] / b["drives"]
                fp_net[a["team"]].append(d)
                fp_net[b["team"]].append(-d)

    adjusted, fit = {}, {}
    for name, mrows in metric_rows.items():
        off, dfn, mean, hfa = opponent_adjust(mrows, ridge=RIDGE.get(name, RIDGE["default"]))
        adjusted[name] = {"off": off, "def": dfn}
        fit[name] = (mean, hfa)

    zs = {(m, side): _z(adjusted[m][side], teams) for m in adjusted for side in ("off", "def")}
    composite = {}
    for unit, parts in UNITS.items():
        raw = {t: sum(w * zs[(m, side)].get(t, 0.0) for m, side, w in parts) for t in teams}
        composite[unit] = _z(raw, teams)

    qbs = _quarterbacks(rows)
    qb_z = _z({t: qbs[t]["shrunk"] for t in qbs}, teams)
    composite["qb"] = _z({t: .7 * qb_z[t] + .3 * composite["pass"][t] if t in qbs else composite["pass"][t]
                          for t in teams}, teams)
    composite["pace"] = _z({t: float(np.mean(plays[t])) if plays[t] else None for t in teams}, teams)
    st_raw = {t: (float(np.mean(st[t])) + 0.05 * float(np.mean(fp_net[t])) if fp_net[t] else float(np.mean(st[t])))
              if st[t] else None for t in teams}
    composite["st"] = _z(st_raw, teams)
    composite["ovr"] = _z({t: .50 * composite["off"][t] + .40 * composite["def"][t] + .10 * composite["st"][t]
                           for t in teams}, teams)

    records = _records(games, season, through_week)
    out = []
    for t in teams:
        if not games_played[t]:
            continue
        abbr = BY_NICK[t]
        name, _, division, color = TEAMS[abbr]
        qb = qbs.get(t)
        out.append({
            "team": t, "abbr": abbr, "name": name, "conference": division, "color": color,
            "record": records.get(t, "0-0"), "games": games_played[t],
            "grades": {u: to_grade(composite[u][t]) for u in GRADE_KEYS},
            "qb": qb and {k: qb[k] for k in ("name", "epa_per_dropback", "dropbacks", "season_leader", "changed")},
            "adjusted": {
                "epa_per_play": _round(adjusted["epa"]["off"].get(t)),
                "epa_allowed": _round(adjusted["epa"]["def"].get(t)),
                "success_rate": _round(adjusted["success"]["off"].get(t)),
                "success_allowed": _round(adjusted["success"]["def"].get(t)),
                "points_per_game": _round(fit["points"][0] + adjusted["points"]["off"].get(t, 0), 1),
                "points_allowed": _round(fit["points"][0] + adjusted["points"]["def"].get(t, 0), 1),
                "plays_per_game": _round(np.mean(plays[t]) if plays[t] else None, 1),
            },
        })
    out.sort(key=lambda r: -r["grades"]["ovr"])
    return {
        "season": season,
        "through_week": last_week,
        "updated": (now or datetime.now(timezone.utc)).isoformat(timespec="minutes"),
        "teams": out,
        "model": _projection_model(adjusted, fit, plays, epa_fit, games_played),
    }


def _quarterbacks(rows):
    """Most recent starter per team, with his season EPA per dropback shrunk toward the league."""
    season = defaultdict(lambda: defaultdict(lambda: [0, 0.0, ""]))
    latest = {}
    for r in sorted(rows, key=lambda r: r["week"]):
        if not r["qb_id"]:
            continue
        s = season[r["team"]][r["qb_id"]]
        s[0] += r["qb_dropbacks"]
        s[1] += r["qb_epa"]
        s[2] = r["qb_name"]
        latest[r["team"]] = r["qb_id"]
    all_db = sum(v[0] for t in season.values() for v in t.values())
    league = sum(v[1] for t in season.values() for v in t.values()) / all_db if all_db else 0.0
    out = {}
    for team, qid in latest.items():
        db, epa, name = season[team][qid]
        leader = max(season[team].items(), key=lambda kv: kv[1][0])
        out[team] = {"name": name, "dropbacks": int(db),
                     "epa_per_dropback": round(epa / db, 3) if db else None,
                     "shrunk": (epa + league * QB_SHRINK_DROPBACKS) / (db + QB_SHRINK_DROPBACKS),
                     "season_leader": leader[1][2], "changed": leader[0] != qid}
    return out


def _records(games, season, through_week):
    rec = defaultdict(lambda: [0, 0, 0])
    for g in games:
        if g["season"] != season or g["type"] != "REG" or not g["completed"]:
            continue
        if through_week is not None and g["week"] >= through_week:
            continue
        h, a = g["home_score"], g["away_score"]
        if h == a:
            rec[NICK[g["home"]]][2] += 1
            rec[NICK[g["away"]]][2] += 1
        else:
            w, l = (NICK[g["home"]], NICK[g["away"]]) if h > a else (NICK[g["away"]], NICK[g["home"]])
            rec[w][0] += 1
            rec[l][1] += 1
    return {t: f"{w}-{l}" + (f"-{ti}" if ti else "") for t, (w, l, ti) in rec.items()}


def _projection_model(adjusted, fit, plays, epa_fit, games_played):
    pts_mean, pts_hfa = fit.get("points", (22.0, 1.5))
    epa_mean, epa_hfa = fit.get("epa", (0.0, 0.0))
    if len(epa_fit) > 20:
        x = np.array([(e - epa_mean) * p for e, p, _ in epa_fit])
        y = np.array([pts for _, _, pts in epa_fit]) - pts_mean
        epa_scale = float(x @ y / (x @ x)) if x @ x > 0 else 0.3
    else:
        epa_scale = 0.3
    league_plays = float(np.mean([p for v in plays.values() for p in v])) if plays else 60.0
    r = lambda d: {t: round(v, 4) for t, v in d.items()}
    return {
        "points": {"mean": round(pts_mean, 3), "hfa": round(pts_hfa, 3),
                   "off": r(adjusted["points"]["off"]), "def": r(adjusted["points"]["def"])},
        "epa": {"hfa": round(epa_hfa, 4), "scale": round(epa_scale, 4),
                "off": r(adjusted["epa"]["off"]), "def": r(adjusted["epa"]["def"])},
        "pace": {t: round(float(np.mean(v)), 2) for t, v in plays.items() if v},
        "league_plays": round(league_plays, 2),
        "games": dict(games_played),
    }


def _round(x, nd=3):
    return None if x is None else round(float(x), nd)
