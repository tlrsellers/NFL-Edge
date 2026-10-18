"""Turns projections, lines and the weather into a tier for every spread and total.

Why the tiers work the way they do (docs/research/):

  * 27 seasons of NFL lines (7,355 games) show the closing line is very hard to
    beat. Replaying 1999-2026 week by week, a stats model built from each
    season's own games missed the final margin by 10.7 points against the
    line's 10.3, and its biggest disagreements with the line did NOT cover more
    often. Only about 5% of its edge is real (MODEL_WEIGHT), against ~30% in
    college football. So model edges alone never reach Lean or better.
  * Two kinds of games did beat the closing line over the long run, and they
    set the top tiers:

      LOCK    Under, outdoor stadium, forecast wind 15+ mph   384-290 (57.0%), profitable in 17 of 27 seasons
      Strong  Playoff underdog that the model also likes      136-109 (55.5%) in replays
      Lean    Under, outdoor stadium, forecast wind 10-14 mph 650-558 (53.8%), profitable in 16 of 28 seasons

    Those records use the measured game-time wind. Live picks use the NWS
    forecast, which is less exact, so a wind LOCK needs a forecast read within
    LOCK_FORECAST_HOURS of kickoff; earlier than that it shows as Strong.
  * Model lean: the model's side when it disagrees with the best line by
    MODEL_LEAN+ points. Shown so you can see what the numbers say, clearly
    labeled unproven: in the replays these went about 50%.

Every pick carries `cover`, the estimated chance it wins (pushes ignored). For
patterns it's the long-run record; for model leans it's
Phi(MODEL_WEIGHT * edge / SPREAD_SD), which stays close to 50%. At -110 you
need 52.4% to break even.
"""

from math import erf, sqrt

MODEL_WEIGHT = 0.05   # share of the model's edge that held up in 27 seasons of replays
SPREAD_SD = 13.2      # SD of final margin vs closing spread, 7,355 NFL games 1999-2026
TOTAL_SD = 13.4
MODEL_LEAN = 3.0      # points of disagreement before the model's side is shown as a lean
WIND_LOCK = 15.0      # mph
WIND_LEAN = 10.0
LOCK_FORECAST_HOURS = 36
RANK = {"pass": 0, "model": 1, "lean": 2, "strong": 3, "lock": 4}

PATTERNS = {
    "wind15": {"name": "Wind 15+ mph Under", "record": "384-290", "pct": 0.570, "seasons": "17 of 27 seasons",
               "text": "At outdoor stadiums with 15+ mph wind, Unders went 384-290 (57.0%) from 1999 to today, "
                       "profitable in 17 of 27 seasons. Wind cuts the passing and kicking game more than the line allows for."},
    "wind10": {"name": "Wind 10-14 mph Under", "record": "650-558", "pct": 0.538, "seasons": "16 of 28 seasons",
               "text": "At outdoor stadiums with 10-14 mph wind, Unders went 650-558 (53.8%) from 1999 to today, "
                       "profitable in 16 of 28 seasons. A smaller, less reliable version of the 15+ mph pattern."},
    "playoff_dog": {"name": "Playoff underdog", "record": "136-109", "pct": 0.555, "seasons": "15 of 25 seasons (all playoff dogs)",
                    "text": "Playoff underdogs went 165-137 (54.6%) against the closing spread from 1999 to today, and "
                            "136-109 (55.5%) when the model also liked them. A small sample: about 11 playoff games a year."},
}


def cover_prob(edge, sd=SPREAD_SD, weight=MODEL_WEIGHT):
    return round(0.5 * (1 + erf(weight * edge / sd / sqrt(2))), 3)


def _fmt(x):
    return "PK" if x == 0 else f"{x:+g}"


def _book_max(lines):
    return max(lines, key=lines.get)


def _book_min(lines):
    return min(lines, key=lines.get)


def spread_pick(proj, books, home, away, open_spread=None, context=None):
    """books: {book: {"spread_home": -3.5, ...}}. context: {"playoff": bool}."""
    context = context or {}
    lines = {b: l["spread_home"] for b, l in books.items() if l.get("spread_home") is not None}
    if not lines:
        return None
    margin = proj["home"] - proj["away"]
    home_book, away_book = _book_max(lines), _book_min(lines)
    home_edge = margin + lines[home_book]
    away_edge = -margin - lines[away_book]
    sides = {home: (home_book, lines[home_book], home_edge, None if open_spread is None else lines[home_book] - open_spread),
             away: (away_book, -lines[away_book], away_edge, None if open_spread is None else open_spread - lines[away_book])}
    model_side = home if home_edge >= away_edge else away
    book, line, edge, moved = sides[model_side]
    pick = {"bet": "spread", "side": model_side, "line": line, "book": book, "edge": round(edge, 1),
            "label": f"{model_side} {_fmt(line)}", "cover": cover_prob(edge), "tier": "pass",
            "moved_against": None if moved is None else round(moved, 1), "pattern": None}
    if context.get("playoff") and line > 0:
        pick.update(tier="strong", pattern="playoff_dog", cover=PATTERNS["playoff_dog"]["pct"])
    elif edge >= MODEL_LEAN:
        pick["tier"] = "model"
    return pick


def total_pick(proj, books, open_total=None, context=None):
    """context: {"wind": mph or None, "outdoor": bool, "forecast_hours": hours before kickoff the forecast was read}."""
    context = context or {}
    lines = {b: l["total"] for b, l in books.items() if l.get("total") is not None}
    if not lines:
        return None
    wind = context.get("wind")
    if context.get("outdoor") and wind is not None and wind >= WIND_LEAN:
        book = _book_max(lines)  # Under: the highest total is the best number
        line = lines[book]
        key = "wind15" if wind >= WIND_LOCK else "wind10"
        pick = {"bet": "total", "side": "Under", "line": line, "book": book,
                "edge": round(line - proj["total"], 1), "label": f"Under {line:g}",
                "cover": PATTERNS[key]["pct"], "pattern": key, "wind": round(wind, 1),
                "moved_against": None if open_total is None else round(open_total - line, 1)}
        if key == "wind15":
            hours = context.get("forecast_hours")
            if hours is not None and hours > LOCK_FORECAST_HOURS:
                pick["tier"] = "strong"
                pick["note"] = (f"Wind forecast of {wind:.0f} mph, but kickoff is {hours:.0f} hours away. "
                                f"Forecasts that far out often change; this becomes a LOCK if it holds inside "
                                f"{LOCK_FORECAST_HOURS} hours.")
            else:
                pick["tier"] = "lock"
        else:
            pick["tier"] = "lean"
        return pick
    over_book, under_book = _book_min(lines), _book_max(lines)
    over_edge, under_edge = proj["total"] - lines[over_book], lines[under_book] - proj["total"]
    if over_edge >= under_edge:
        side, book, edge = "Over", over_book, over_edge
        moved = None if open_total is None else open_total - lines[book]
    else:
        side, book, edge = "Under", under_book, under_edge
        moved = None if open_total is None else lines[book] - open_total
    return {"bet": "total", "side": side, "line": lines[book], "book": book, "edge": round(edge, 1),
            "label": f"{side} {lines[book]:g}", "cover": cover_prob(edge, TOTAL_SD), "pattern": None,
            "tier": "model" if edge >= MODEL_LEAN else "pass",
            "moved_against": None if moved is None else round(moved, 1)}


def best_pick(*picks):
    picks = [p for p in picks if p]
    if not picks:
        return None
    return max(picks, key=lambda p: (RANK[p["tier"]], p.get("cover") or 0, p["edge"]))


def backtest_picks(r):
    """The live rules applied to one replayed game (scripts/backtest.py). Adds 'result' to each pick."""
    books = {"close": {"spread_home": -r["line"], "total": r["total_line"]}}
    proj = {"home": (r["proj_total"] + r["proj_margin"]) / 2, "away": (r["proj_total"] - r["proj_margin"]) / 2,
            "total": r["proj_total"]}
    sp = spread_pick(proj, books, r["home"], r["away"], context={"playoff": r["type"] != "REG"})
    tp = total_pick(proj, books, context={"wind": r.get("wind"), "outdoor": r.get("roof") in ("outdoors", "open"),
                                          "forecast_hours": 0})
    if sp:
        mine = r["margin"] if sp["side"] == r["home"] else -r["margin"]
        v = mine + sp["line"]
        sp["result"] = "win" if v > 0 else "loss" if v < 0 else "push"
    if tp:
        v = (r["points"] - tp["line"]) * (1 if tp["side"] == "Over" else -1)
        tp["result"] = "win" if v > 0 else "loss" if v < 0 else "push"
    return sp, tp
