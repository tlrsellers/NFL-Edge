"""Weekly rule check: is each pick rule still working, and is there a better one?

Runs every Tuesday after the backtest (Actions -> Backtest), on the same
replayed games (every NFL game since 1999, team grades rebuilt week by week
from that season's earlier games only, settled against the closing line).

1. Health check for every live rule in nfl_edge/picks.py:
     RED     the rule is losing: its long-run record is under the 52.4% break-even,
             or the last 5 seasons are under 50% with 40+ bets
     YELLOW  the evidence is weak (win % minus 1.28 standard errors is below
             break-even) or the last 3 seasons are under break-even. Worth
             watching; NFL patterns have cold streaks, and 3 seasons is small.
     GREEN   clearly above break-even long-run, and recent seasons are fine
   This season's live record (site/data/picks.json) is shown next to it.

2. New-rule search. Thousands of combinations of game features (spread and
   total size, wind, temperature, week, division game, rest, day of the week,
   playoffs, whether the model agrees) are tried as spread or total bets.
   With that many tries, some look great by luck, so a candidate must:
     * win at least 54% over 1999-2014 (DISCOVERY), with 80+ bets, AND
     * then win at least 53.5% with z >= 2 over 2015-today (VALIDATION), seasons
       it was never chosen on, with 60+ bets, AND
     * beat break-even in at least 60% of seasons with 5+ bets.
   Candidates that are just a slice of an existing rule are left out.

Nothing changes automatically. The report goes to the run summary,
data/rule_check.md, and a GitHub issue (which GitHub emails you) when a rule
changes status or a new candidate appears. To adopt a candidate, add it to
picks.py in a pull request; the Backtest job replays every season with it.

    python scripts/rule_check.py --games replay.json [--issue]
"""
import argparse
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nfl_edge import picks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "rule_check.json"
REPORT = ROOT / "data" / "rule_check.md"
BREAK_EVEN = 110 / 210
DISCOVERY = (1999, 2014)
VALIDATION_START = 2015
MIN_DISC, MIN_VAL = 80, 60
DISC_PCT, VAL_PCT, VAL_Z = 0.54, 0.535, 2.0


# ---------- settling bets ----------

def ats(r, side):
    """'win'/'loss'/'push' for a spread bet on 'home' or 'away' (nflverse line: home favored by)."""
    v = r["margin"] - r["line"]
    if v == 0:
        return "push"
    return "win" if (v > 0) == (side == "home") else "loss"


def ou(r, side):
    if r["total_line"] is None:
        return None
    if r["points"] == r["total_line"]:
        return "push"
    return "win" if (r["points"] > r["total_line"]) == (side == "over") else "loss"


def fav(r):
    return None if r["line"] == 0 else ("home" if r["line"] > 0 else "away")


def dog(r):
    f = fav(r)
    return None if f is None else ("away" if f == "home" else "home")


def model_side(r):
    return "home" if r["proj_margin"] - r["line"] >= 0 else "away"


SIDES = {
    "home": ("Home team", lambda r: ats(r, "home")),
    "away": ("Road team", lambda r: ats(r, "away")),
    "fav": ("Favorite", lambda r: fav(r) and ats(r, fav(r))),
    "dog": ("Underdog", lambda r: dog(r) and ats(r, dog(r))),
    "model": ("Model's side (spread)", lambda r: ats(r, model_side(r))),
    "over": ("Over", lambda r: ou(r, "over")),
    "under": ("Under", lambda r: ou(r, "under")),
}

# ---------- game features: (family, label, test) ----------

def _outdoor(r):
    return r.get("roof") in ("outdoors", "open")


def _bye(r, side):
    me, them = (r.get("home_rest"), r.get("away_rest")) if side == "home" else (r.get("away_rest"), r.get("home_rest"))
    return (me or 0) >= 13 and (them or 0) < 13


FEATURES = [
    ("season", "weeks 1-4", lambda r: r["type"] == "REG" and r["week"] <= 4),
    ("season", "weeks 5-12", lambda r: r["type"] == "REG" and 5 <= r["week"] <= 12),
    ("season", "week 13+", lambda r: r["type"] == "REG" and r["week"] >= 13),
    ("season", "playoffs", lambda r: r["type"] != "REG"),
    ("div", "division game", lambda r: bool(r.get("div"))),
    ("div", "non-division game", lambda r: not r.get("div")),
    ("spread", "spread 0-2.5", lambda r: abs(r["line"]) <= 2.5),
    ("spread", "spread 3", lambda r: abs(r["line"]) == 3),
    ("spread", "spread 3.5-6.5", lambda r: 3.5 <= abs(r["line"]) <= 6.5),
    ("spread", "spread 7", lambda r: abs(r["line"]) == 7),
    ("spread", "spread 7.5-10.5", lambda r: 7.5 <= abs(r["line"]) <= 10.5),
    ("spread", "spread 11+", lambda r: abs(r["line"]) >= 11),
    ("total", "total under 39", lambda r: r["total_line"] is not None and r["total_line"] < 39),
    ("total", "total 39-42.5", lambda r: r["total_line"] is not None and 39 <= r["total_line"] <= 42.5),
    ("total", "total 43-46.5", lambda r: r["total_line"] is not None and 43 <= r["total_line"] <= 46.5),
    ("total", "total 47-50.5", lambda r: r["total_line"] is not None and 47 <= r["total_line"] <= 50.5),
    ("total", "total 51+", lambda r: r["total_line"] is not None and r["total_line"] >= 51),
    ("weather", "outdoor, wind under 10", lambda r: _outdoor(r) and r.get("wind") is not None and r["wind"] < 10),
    ("weather", "outdoor, wind 10-14", lambda r: _outdoor(r) and r.get("wind") is not None and 10 <= r["wind"] < 15),
    ("weather", "outdoor, wind 15+", lambda r: _outdoor(r) and (r.get("wind") or 0) >= 15),
    ("weather", "dome or closed roof", lambda r: r.get("roof") in ("dome", "closed")),
    ("temp", "32F or colder", lambda r: _outdoor(r) and r.get("temp") is not None and r["temp"] <= 32),
    ("temp", "80F or hotter", lambda r: _outdoor(r) and r.get("temp") is not None and r["temp"] >= 80),
    ("day", "Thursday", lambda r: r.get("weekday") == "Thursday"),
    ("day", "Monday", lambda r: r.get("weekday") == "Monday"),
    ("day", "Sunday", lambda r: r.get("weekday") == "Sunday"),
    ("rest", "home team off a bye", lambda r: _bye(r, "home")),
    ("rest", "road team off a bye", lambda r: _bye(r, "away")),
    ("site", "neutral site", lambda r: bool(r.get("neutral"))),
    ("model", "model disagrees with spread 3+", lambda r: abs(r["proj_margin"] - r["line"]) >= 3),
    ("model", "model agrees with spread (<1 apart)", lambda r: abs(r["proj_margin"] - r["line"]) < 1),
    ("model", "model total 3+ below line", lambda r: r["total_line"] is not None and r["total_line"] - r["proj_total"] >= 3),
    ("model", "model total 3+ above line", lambda r: r["total_line"] is not None and r["proj_total"] - r["total_line"] >= 3),
]
SPREAD_SIDES, TOTAL_SIDES = ("home", "away", "fav", "dog", "model"), ("over", "under")


def candidates():
    """Every one- and two-feature rule (features from different families), on every side."""
    singles = [(f,) for f in FEATURES]
    pairs = [(a, b) for a, b in combinations(FEATURES, 2) if a[0] != b[0]]
    for feats in singles + pairs:
        for side in SPREAD_SIDES + TOTAL_SIDES:
            yield side, feats


# ---------- records ----------

def record(results):
    results = [x for x in results if x]
    w, l = results.count("win"), results.count("loss")
    n = w + l
    pct = w / n if n else None
    z = (pct - BREAK_EVEN) / math.sqrt(BREAK_EVEN * (1 - BREAK_EVEN) / n) if n else None
    return {"w": w, "l": l, "p": results.count("push"), "n": n, "pct": pct, "z": z,
            "units": round(w * 100 / 110 - l, 1)}


def seasons_beat(by_season):
    counted = [record(v) for v in by_season.values()]
    counted = [c for c in counted if c["n"] >= 5]
    return sum(c["pct"] > BREAK_EVEN for c in counted), len(counted)


def fmt(rec):
    if not rec or not rec["n"]:
        return "no bets"
    return f"{rec['w']}-{rec['l']} ({rec['pct']:.1%})"


# ---------- 1. health of the live rules ----------

LIVE_RULES = {
    "wind15": ("LOCK: Under, outdoor wind 15+ mph", "total"),
    "playoff_dog": ("Strong: playoff underdog the model likes", "spread"),
    "wind10": ("Lean: Under, outdoor wind 10-14 mph", "total"),
}


def health(replayed, live_log=None):
    by_rule = defaultdict(lambda: defaultdict(list))
    for r in replayed:
        sp, tp = picks.backtest_picks(r)
        for p in (sp, tp):
            if p and p.get("pattern") in LIVE_RULES:
                by_rule[p["pattern"]][r["season"]].append(p["result"])
    last = max(r["season"] for r in replayed)
    out = []
    for key, (name, bet) in LIVE_RULES.items():
        seasons = by_rule[key]
        allr = record([x for v in seasons.values() for x in v])
        last5 = record([x for s, v in seasons.items() if s > last - 5 for x in v])
        last3 = record([x for s, v in seasons.items() if s > last - 3 for x in v])
        beat, counted = seasons_beat(seasons)
        se = math.sqrt(allr["pct"] * (1 - allr["pct"]) / allr["n"]) if allr["n"] else 1
        status, why = "GREEN", "Long-run record is clearly above break-even and recent seasons are fine."
        if not allr["n"] or allr["pct"] < BREAK_EVEN:
            status, why = "RED", "The long-run record has fallen under the 52.4% break-even. Consider removing this rule."
        elif last5["n"] >= 40 and last5["pct"] < 0.50:
            status, why = "RED", "The last 5 seasons are under 50%. Consider removing or tightening this rule."
        elif allr["pct"] - 1.28 * se < BREAK_EVEN:
            status, why = "YELLOW", ("Profitable long-run, but the sample is small enough that it could be luck. "
                                     "Keep it at a lower tier and watch it.")
        elif last3["n"] and last3["pct"] < BREAK_EVEN:
            status, why = "YELLOW", "The last 3 seasons are under break-even. Worth watching, not yet a reason to change."
        live = None
        if live_log:
            live = record([e.get("result") for e in live_log.values() if e.get("pattern") == key and e.get("result")])
        out.append({"rule": key, "name": name, "status": status, "why": why, "all": allr, "last5": last5,
                    "last3": last3, "seasons_beat": f"{beat} of {counted}", "live": live})
    return out


# ---------- 2. search for new rules ----------

def search(replayed):
    last = max(r["season"] for r in replayed)
    found = []
    for side, feats in candidates():
        label, settle = SIDES[side]
        disc, val, by_season = [], [], defaultdict(list)
        for r in replayed:
            if not all(f[2](r) for f in feats):
                continue
            res = settle(r)
            if not res:
                continue
            (disc if DISCOVERY[0] <= r["season"] <= DISCOVERY[1] else val).append(res)
            by_season[r["season"]].append(res)
        d = record(disc)
        if d["n"] < MIN_DISC or d["pct"] < DISC_PCT:
            continue
        v = record(val)
        if v["n"] < MIN_VAL or v["pct"] < VAL_PCT or v["z"] < VAL_Z:
            continue
        beat, counted = seasons_beat(by_season)
        if counted == 0 or beat / counted < 0.6:
            continue
        name = f"{label}, " + ", ".join(f[1] for f in feats)
        if _covered(side, feats):
            continue
        found.append({"name": name, "side": side, "features": [f[1] for f in feats],
                      "discovery": d, "validation": v, "all": record(disc + val),
                      "seasons_beat": f"{beat} of {counted}", "through": last})
    # Drop near-duplicates: keep the stronger of two candidates that share a side and a feature.
    found.sort(key=lambda c: -c["validation"]["z"])
    kept = []
    for c in found:
        if any(c["side"] == k["side"] and set(c["features"]) & set(k["features"]) for k in kept):
            continue
        kept.append(c)
    return kept


def _covered(side, feats):
    """True if the candidate is a slice of a rule already on the site."""
    labels = {f[1] for f in feats}
    if side == "under" and labels & {"outdoor, wind 15+", "outdoor, wind 10-14"}:
        return True
    if side == "dog" and "playoffs" in labels:
        return True
    return False


# ---------- report ----------

ICON = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}


def report(h, cands, tested):
    out = ["# Weekly rule check", "",
           "Every NFL game since 1999, settled against the closing line at -110 (52.4% breaks even). "
           "Nothing on the site changes automatically.", "", "## Current rules", "",
           "| Rule | Status | Since 1999 | Last 5 seasons | Last 3 seasons | Seasons above 52.4% | Live this season |",
           "|---|---|---|---|---|---|---|"]
    for x in h:
        out.append(f"| {x['name']} | {ICON[x['status']]} {x['status']} | {fmt(x['all'])} | {fmt(x['last5'])} | "
                   f"{fmt(x['last3'])} | {x['seasons_beat']} | {fmt(x['live']) if x['live'] else 'no bets yet'} |")
    out.append("")
    for x in h:
        if x["status"] != "GREEN":
            out.append(f"- **{x['name']}**: {x['why']}")
    out += ["", "## New rule candidates", "",
            f"Tested {tested:,} combinations. A candidate had to win 54%+ on 1999-2014, then 53.5%+ with z >= 2 on "
            "2015-today (seasons it wasn't picked on), and beat break-even in 60%+ of seasons.", ""]
    if cands:
        out += ["| Candidate | 1999-2014 | 2015-today | Seasons above 52.4% |", "|---|---|---|---|"]
        out += [f"| {c['name']} | {fmt(c['discovery'])} | {fmt(c['validation'])} | {c['seasons_beat']} |" for c in cands]
        out += ["", "These are leads, not new rules. With this many combinations tested, expect about one "
                "lucky survivor a year. Before adding one, ask whether there's a real reason it would work "
                "(like wind hurting passing), then add it to `nfl_edge/picks.py` in a pull request so the "
                "Backtest job can replay every season with it."]
    else:
        out.append("None passed this week. That's the normal result: the NFL closing line is hard to beat.")
    return "\n".join(out) + "\n"


def open_issue(title, body):
    token, repo = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("No GitHub token; skipping the issue.")
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps({"title": title, "body": body, "assignees": [repo.split("/")[0]]}).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("html_url")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--games", required=True, help="replayed games from scripts/backtest.py --games")
    p.add_argument("--issue", action="store_true", help="open a GitHub issue if anything changed")
    a = p.parse_args(argv)
    replayed = json.loads(Path(a.games).read_text())
    log_path = ROOT / "site" / "data" / "picks.json"
    live = json.loads(log_path.read_text()).get("picks", {}) if log_path.exists() else {}
    h = health(replayed, live)
    tested = sum(1 for _ in candidates())
    cands = search(replayed)
    md = report(h, cands, tested)
    REPORT.write_text(md)
    print(md)

    prev = json.loads(STATE.read_text()) if STATE.exists() else {"status": {}, "candidates": []}
    status = {x["rule"]: x["status"] for x in h}
    changed = {k: (prev["status"].get(k), v) for k, v in status.items() if prev["status"].get(k, "GREEN") != v}
    new = [c["name"] for c in cands if c["name"] not in prev["candidates"]]
    STATE.write_text(json.dumps({"status": status, "candidates": sorted(set(prev["candidates"]) | {c["name"] for c in cands}),
                                 "through": replayed[-1]["season"] if replayed else None}, indent=1) + "\n")
    if a.issue and (changed or new):
        parts = [f"{k}: {old or 'new'} → {now}" for k, (old, now) in changed.items()] + [f"new candidate: {n}" for n in new]
        title = "Rule check: " + "; ".join(parts)[:200]
        url = open_issue(title, md)
        print(f"Opened {url}")


if __name__ == "__main__":
    main()
