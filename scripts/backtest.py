"""Replays past seasons week by week and grades every pick against the closing line.

For each season and week, team grades are rebuilt from that season's earlier
games only (exactly what the live site knows on that day), every game is
projected, and the projection is compared with the nflverse closing spread and
total. Then each pick is settled against the final score.

    python scripts/backtest.py                          # 2002-today, summary to stdout
    python scripts/backtest.py --first 2015 --json out.json
    python scripts/backtest.py --games games.json       # also save every replayed game (for tuning)

The pick tiers in nfl_edge/picks.py come from this. Past games are research only;
they never appear on the dashboard.
"""
import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nfl_edge import nflverse, picks, stats  # noqa: E402
from nfl_edge.nflverse import NICK  # noqa: E402
from nfl_edge.grades import grade_season  # noqa: E402
from nfl_edge.projections import project  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history" / "team_games.csv.gz"
NUMERIC = set(stats.FIELDS) - {"game_id", "team", "opp", "qb_id", "qb_name"}


def load_history(path=HISTORY):
    with gzip.open(path, "rt") as f:
        out = []
        for r in csv.DictReader(f):
            for k in NUMERIC:
                r[k] = float(r[k]) if k not in ("season", "week", "home") else int(float(r[k]))
            r["qb_dropbacks"] = int(r["qb_dropbacks"])
            out.append(r)
    return out


def replay(history, games, first, last, min_week=2):
    """Every game from `first` to `last` with a closing line, projected from earlier weeks only."""
    by_season = defaultdict(list)
    for r in history:
        by_season[r["season"]].append(r)
    out = []
    for season in range(first, last + 1):
        rows = by_season.get(season)
        if not rows:
            continue
        sched = [g for g in games if g["season"] == season and g["completed"] and g["spread_line"] is not None]
        reg_weeks = sorted({g["week"] for g in sched if g["type"] == "REG"})
        last_reg = max(reg_weeks, default=0)
        cache = {}
        for g in sched:
            week = g["week"] if g["type"] == "REG" else last_reg + 1
            if week < min_week:
                continue
            if week not in cache:
                cache[week] = grade_season(rows, season, games, through_week=week)
            gr = cache[week]
            model = gr["model"]
            home, away = NICK[g["home"]], NICK[g["away"]]
            played = (model["games"].get(home, 0), model["games"].get(away, 0))
            if min(played) == 0:
                continue
            p = project(model, home, away, g["neutral"])
            out.append({
                "season": season, "week": g["week"], "type": g["type"], "id": g["id"],
                "home": home, "away": away, "neutral": g["neutral"], "div": g["div_game"],
                "games": list(played),
                "proj_margin": round(p["home"] - p["away"], 2), "proj_total": p["total"],
                "line": g["spread_line"], "total_line": g["total_line"],
                "margin": g["home_score"] - g["away_score"], "points": g["home_score"] + g["away_score"],
                "home_price": g["home_spread_odds"], "away_price": g["away_spread_odds"],
                "over_price": g["over_odds"], "under_price": g["under_odds"],
                "roof": g["roof"], "wind": g["wind"], "temp": g["temp"],
            })
    return out


def settle_spread(r):
    """Model's side against the closing spread: (edge, side, getting_points, result)."""
    home_edge = r["proj_margin"] - r["line"]
    side = "home" if home_edge >= 0 else "away"
    v = r["margin"] - r["line"]
    result = "push" if v == 0 else ("win" if (v > 0) == (side == "home") else "loss")
    dog = (r["line"] < 0) if side == "home" else (r["line"] > 0)
    return abs(home_edge), side, dog, result


def settle_total(r):
    if r["total_line"] is None:
        return None
    edge = r["proj_total"] - r["total_line"]
    side = "Over" if edge >= 0 else "Under"
    if r["points"] == r["total_line"]:
        res = "push"
    else:
        res = "win" if (r["points"] > r["total_line"]) == (side == "Over") else "loss"
    return abs(edge), side, res


def record(results):
    w, l = results.count("win"), results.count("loss")
    return {"w": w, "l": l, "p": results.count("push"), "pct": round(w / (w + l), 3) if w + l else None,
            "units": round(w * 100 / 110 - l, 1)}


def tier_report(replayed):
    """How each tier did, using the live pick rules, plus season-by-season consistency."""
    tiers = defaultdict(lambda: defaultdict(list))
    for r in replayed:
        s, t = picks.backtest_picks(r)
        for p in (s, t):
            if p and p["tier"] != "pass":
                tiers[f"{p['bet']}:{p['tier']}"][r["season"]].append(p["result"])
    out = {}
    for key, seasons in sorted(tiers.items()):
        allr = [x for v in seasons.values() for x in v]
        per = {s: record(v) for s, v in sorted(seasons.items())}
        beat = sum(1 for v in per.values() if v["pct"] is not None and v["w"] + v["l"] >= 5 and v["pct"] > 110 / 210)
        counted = sum(1 for v in per.values() if v["w"] + v["l"] >= 5)
        out[key] = {**record(allr), "seasons_beat": beat, "seasons": counted, "by_season": per}
    return out


def summary(replayed):
    import statistics as st
    model = [abs(r["margin"] - r["proj_margin"]) for r in replayed]
    line = [abs(r["margin"] - r["line"]) for r in replayed]
    tm = [abs(r["points"] - r["proj_total"]) for r in replayed if r["total_line"] is not None]
    tl = [abs(r["points"] - r["total_line"]) for r in replayed if r["total_line"] is not None]
    return {"games": len(replayed),
            "seasons": [min(r["season"] for r in replayed), max(r["season"] for r in replayed)],
            "margin_miss": {"model": round(st.mean(model), 2), "closing_line": round(st.mean(line), 2)},
            "total_miss": {"model": round(st.mean(tm), 2), "closing_line": round(st.mean(tl), 2)},
            "tiers": tier_report(replayed)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--first", type=int, default=2002)
    p.add_argument("--last", type=int, default=2100)
    p.add_argument("--schedule")
    p.add_argument("--current", action="store_true", help="also replay this season from live play-by-play")
    p.add_argument("--games", help="save every replayed game here")
    p.add_argument("--json", help="save the summary here")
    a = p.parse_args(argv)
    games = nflverse.schedule(a.schedule)
    history = load_history()
    if a.current:
        season = max(g["season"] for g in games if g["completed"])
        if season not in {r["season"] for r in history}:
            history += stats.attach_points(stats.summarize(nflverse.pbp(season)), games)
    replayed = replay(history, games, a.first, a.last)
    if a.games:
        Path(a.games).write_text(json.dumps(replayed))
    s = summary(replayed)
    if a.json:
        Path(a.json).write_text(json.dumps(s, indent=1) + "\n")
    print(f"{s['games']} games {s['seasons'][0]}-{s['seasons'][1]}. Margin miss: model {s['margin_miss']['model']}, "
          f"closing line {s['margin_miss']['closing_line']}. Total miss: model {s['total_miss']['model']}, "
          f"line {s['total_miss']['closing_line']}.")
    for k, v in s["tiers"].items():
        print(f"  {k:16s} {v['w']}-{v['l']}-{v['p']}  {v['pct']}  units {v['units']:+}  seasons above 52.4%: {v['seasons_beat']}/{v['seasons']}")


if __name__ == "__main__":
    main()
