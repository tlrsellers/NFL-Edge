"""Every public NFL line in nflverse (1999-today) against the final score.

No model here, just the market. For every completed game with a closing spread
it asks how far results land from the line, how often margins hit key numbers,
and whether any kind of bet beat the 52.4% break-even consistently. A split only
counts as a pattern if it beat break-even in most seasons, not just in total.

    python scripts/line_history.py                     # all seasons, report to stdout
    python scripts/line_history.py --md docs/research/line-history.md --json data/line_history.json

The JSON holds the calibration numbers the pick model uses (spread and total
spread-of-outcomes, key-number frequencies). Research only; nothing here goes on
the dashboard.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nfl_edge import nflverse  # noqa: E402

BREAK_EVEN = 110 / 210
KEY = (3, 7, 10, 6, 4, 14, 1, 17)


def rows(games):
    out = []
    for g in games:
        if not g["completed"] or g["spread_line"] is None:
            continue
        out.append({**g, "margin": g["home_score"] - g["away_score"],
                    "points": g["home_score"] + g["away_score"]})
    return out


def ats(r, side):
    v = r["margin"] - r["spread_line"]  # nflverse spread_line: points the home team is favored by
    if v == 0:
        return "push"
    return "win" if (v > 0) == (side == "home") else "loss"


def ou(r, side):
    if r["total_line"] is None or r["points"] == r["total_line"]:
        return "push" if r["total_line"] is not None else None
    return "win" if (r["points"] > r["total_line"]) == (side == "over") else "loss"


def rec(results):
    results = [x for x in results if x]
    w, l = results.count("win"), results.count("loss")
    return {"w": w, "l": l, "p": results.count("push"), "pct": round(w / (w + l), 3) if w + l else None,
            "units": round(w * 100 / 110 - l, 1)}


def split(name, data, pick):
    """pick(row) -> 'win'/'loss'/'push'/None. Returns totals plus season-by-season consistency."""
    by_season = defaultdict(list)
    for r in data:
        res = pick(r)
        if res:
            by_season[r["season"]].append(res)
    total = rec([x for v in by_season.values() for x in v])
    seasons = {s: rec(v) for s, v in sorted(by_season.items())}
    counted = [v for v in seasons.values() if v["w"] + v["l"] >= 10]
    beat = sum(v["pct"] > BREAK_EVEN for v in counted)
    return {"name": name, **total, "seasons_beat": beat, "seasons": len(counted),
            "consistent": bool(counted) and beat / len(counted) >= 0.6 and total["pct"] > BREAK_EVEN}


def fav_side(r):
    if r["spread_line"] == 0:
        return None
    return "home" if r["spread_line"] > 0 else "away"


def dog_side(r):
    f = fav_side(r)
    return None if f is None else ("away" if f == "home" else "home")


def size(r):
    a = abs(r["spread_line"])
    for hi, label in ((2.5, "0-2.5"), (3.5, "3-3.5"), (6.5, "4-6.5"), (7.5, "7-7.5"), (10.5, "8-10.5"), (13.5, "11-13.5")):
        if a <= hi:
            return label
    return "14+"


def study(games):
    data = [r for r in rows(games)]
    reg = [r for r in data if r["type"] == "REG"]
    resid = [r["margin"] - r["spread_line"] for r in data]
    tres = [r["points"] - r["total_line"] for r in data if r["total_line"] is not None]
    seasons = sorted({r["season"] for r in data})

    margins = Counter(abs(int(r["margin"])) for r in data)
    n = len(data)
    key = {k: round(margins[k] / n, 4) for k in KEY}
    eras = {}
    for label, lo, hi in (("1999-2014", 1999, 2014), ("2015-today", 2015, 9999)):  # 2015: extra point moved back
        sub = [r for r in data if lo <= r["season"] <= hi]
        m = Counter(abs(int(r["margin"])) for r in sub)
        eras[label] = {"games": len(sub), **{f"margin_{k}": round(m[k] / len(sub), 4) for k in (3, 7, 10, 6, 4, 14)}}

    hfa = {}
    for s in seasons:
        sub = [r for r in reg if r["season"] == s and not r["neutral"]]
        if sub:
            hfa[s] = {"home_margin": round(mean(r["margin"] for r in sub), 2),
                      "line_home_edge": round(mean(r["spread_line"] for r in sub), 2)}

    splits = []
    add = lambda name, sub, f: splits.append(split(name, sub, f))
    add("Home teams", data, lambda r: ats(r, "home"))
    add("Favorites", data, lambda r: fav_side(r) and ats(r, fav_side(r)))
    add("Underdogs", data, lambda r: dog_side(r) and ats(r, dog_side(r)))
    add("Home underdogs", data, lambda r: ats(r, "home") if r["spread_line"] < 0 else None)
    add("Road underdogs", data, lambda r: ats(r, "away") if r["spread_line"] > 0 else None)
    for lab in ("0-2.5", "3-3.5", "4-6.5", "7-7.5", "8-10.5", "11-13.5", "14+"):
        add(f"Underdogs getting {lab}", data, lambda r, lab=lab: dog_side(r) and size(r) == lab and ats(r, dog_side(r)))
    add("Division underdogs", data, lambda r: r["div_game"] and dog_side(r) and ats(r, dog_side(r)))
    add("Non-division underdogs", data, lambda r: (not r["div_game"]) and dog_side(r) and ats(r, dog_side(r)))
    add("Underdogs weeks 1-4", reg, lambda r: r["week"] <= 4 and dog_side(r) and ats(r, dog_side(r)))
    add("Underdogs weeks 13+", reg, lambda r: r["week"] >= 13 and dog_side(r) and ats(r, dog_side(r)))
    add("Underdogs, playoffs", [r for r in data if r["type"] != "REG"], lambda r: dog_side(r) and ats(r, dog_side(r)))
    add("Team off a bye vs team that wasn't (bye team ATS)", reg,
        lambda r: (ats(r, "home") if (r["home_rest"] or 0) >= 13 and (r["away_rest"] or 0) < 13 else
                   ats(r, "away") if (r["away_rest"] or 0) >= 13 and (r["home_rest"] or 0) < 13 else None))
    add("Thursday home teams", reg, lambda r: r["weekday"] == "Thursday" and ats(r, "home"))
    add("Monday underdogs", reg, lambda r: r["weekday"] == "Monday" and dog_side(r) and ats(r, dog_side(r)))
    # Totals
    add("Overs", data, lambda r: ou(r, "over"))
    add("Unders", data, lambda r: ou(r, "under"))
    for lo, hi in ((0, 37.5), (38, 41.5), (42, 44.5), (45, 47.5), (48, 50.5), (51, 99)):
        add(f"Unders, total {lo:g}-{hi:g}", data,
            lambda r, lo=lo, hi=hi: r["total_line"] is not None and lo <= r["total_line"] <= hi and ou(r, "under"))
    outdoor = lambda r: r["roof"] in ("outdoors", "open")
    add("Unders, outdoor wind 15+ mph", data, lambda r: outdoor(r) and (r["wind"] or 0) >= 15 and ou(r, "under"))
    add("Unders, outdoor wind 10-14 mph", data, lambda r: outdoor(r) and 10 <= (r["wind"] or 0) < 15 and ou(r, "under"))
    add("Unders, temp 32F or colder", data, lambda r: outdoor(r) and r["temp"] is not None and r["temp"] <= 32 and ou(r, "under"))
    add("Overs, dome", data, lambda r: r["roof"] in ("dome", "closed") and ou(r, "over"))
    add("Unders, division games", data, lambda r: r["div_game"] and ou(r, "under"))
    add("Unders, playoffs", [r for r in data if r["type"] != "REG"], lambda r: ou(r, "under"))

    # Moneylines (prices exist from 2006): do favorites win as often as the price says?
    ml = []
    for r in data:
        h, a = r["home_moneyline"], r["away_moneyline"]
        if h is None or a is None or r["margin"] == 0:
            continue
        ph, pa = _implied(h), _implied(a)
        fair_h = ph / (ph + pa)
        ml.append((fair_h, r["margin"] > 0, h, a))
    buckets = []
    for lo, hi in ((.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.01)):
        fav = [(p if p >= .5 else 1 - p, won if p >= .5 else not won, h if p >= .5 else a, a if p >= .5 else h)
               for p, won, h, a in ml]
        sub = [x for x in fav if lo <= x[0] < hi]
        if not sub:
            continue
        fav_roi = mean(_profit(price, won) for _, won, price, _ in sub)
        dog_roi = mean(_profit(dprice, not won) for _, won, _, dprice in sub)
        buckets.append({"favorite_fair_prob": f"{lo:.0%}-{min(hi, 1):.0%}", "games": len(sub),
                        "expected_win": round(mean(x[0] for x in sub), 3),
                        "actual_win": round(mean(x[1] for x in sub), 3),
                        "favorite_roi": round(fav_roi, 3), "underdog_roi": round(dog_roi, 3)})

    return {
        "games": n, "seasons": [seasons[0], seasons[-1]],
        "spread": {"mean_miss": round(mean(abs(x) for x in resid), 2), "sd": round(pstdev(resid), 2),
                   "bias_home": round(mean(resid), 2)},
        "total": {"games": len(tres), "mean_miss": round(mean(abs(x) for x in tres), 2),
                  "sd": round(pstdev(tres), 2), "bias": round(mean(tres), 2)},
        "key_numbers": key, "key_numbers_by_era": eras,
        "home_field_by_season": hfa,
        "splits": splits, "moneyline_by_price": buckets,
    }


def _implied(american):
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def _profit(american, won):
    return (american / 100 if american > 0 else 100 / -american) if won else -1.0


def markdown(s):
    out = [f"# Every NFL line vs the final score ({s['seasons'][0]}–{s['seasons'][1]})", "",
           f"{s['games']:,} games with a closing spread (regular season and playoffs), from nflverse.", "",
           "## How good is the line?", "",
           f"- The final margin lands **{s['spread']['mean_miss']} points** from the closing spread on average "
           f"(standard deviation {s['spread']['sd']}). Average bias toward the home team: {s['spread']['bias_home']:+} points.",
           f"- Totals miss by **{s['total']['mean_miss']} points** on average (SD {s['total']['sd']}, bias {s['total']['bias']:+}).",
           "", "## Key numbers (share of all games decided by exactly this margin)", "",
           "| Margin | All games | " + " | ".join(s["key_numbers_by_era"]) + " |", "|---|---|" + "---|" * len(s["key_numbers_by_era"])]
    for k in (3, 7, 10, 6, 4, 14):
        out.append(f"| {k} | {s['key_numbers'][k]:.1%} | " +
                   " | ".join(f"{e[f'margin_{k}']:.1%}" for e in s["key_numbers_by_era"].values()) + " |")
    out += ["", "## Home field by season (regular season, non-neutral)", "",
            "| Season | Home margin | Line's home edge |", "|---|---|---|"]
    for season, v in s["home_field_by_season"].items():
        out.append(f"| {season} | {v['home_margin']:+.1f} | {v['line_home_edge']:+.1f} |")
    out += ["", "## Bets at -110: did anything beat 52.4% consistently?", "",
            "A split is marked **consistent** only if it beat break-even overall and in at least 60% of seasons with 10+ bets.", "",
            "| Bet | Record | Win % | Units | Seasons above 52.4% | Consistent |", "|---|---|---|---|---|---|"]
    for x in s["splits"]:
        out.append(f"| {x['name']} | {x['w']}-{x['l']}-{x['p']} | {x['pct']:.1%} | {x['units']:+.1f} | "
                   f"{x['seasons_beat']}/{x['seasons']} | {'yes' if x['consistent'] else ''} |")
    out += ["", "## Moneylines: do favorites win as often as the price says? (2006 on)", "",
            "| Favorite's fair chance | Games | Price said | Actually won | Favorite ROI | Underdog ROI |",
            "|---|---|---|---|---|---|"]
    for b in s["moneyline_by_price"]:
        out.append(f"| {b['favorite_fair_prob']} | {b['games']} | {b['expected_win']:.1%} | {b['actual_win']:.1%} | "
                   f"{b['favorite_roi']:+.1%} | {b['underdog_roi']:+.1%} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schedule", help="local games.csv instead of downloading")
    p.add_argument("--md")
    p.add_argument("--json")
    a = p.parse_args(argv)
    s = study(nflverse.schedule(a.schedule))
    md = markdown(s)
    if a.md:
        Path(a.md).write_text(md)
    if a.json:
        Path(a.json).write_text(json.dumps(s, indent=1) + "\n")
    print(md if not a.md else f"Wrote {a.md}")


if __name__ == "__main__":
    main()
