"""Tuesday grading: archive every graded pick by week and work out which signals are paying.

    python -m nfl_edge.review          # final scores come from nflverse (no key)

Runs every Tuesday morning (Actions -> Weekly grading), after Monday night's game:
  1. Grades any finished pick still waiting on a score.
  2. Writes site/data/archive/<season>-week-<NN>.json for every week whose picks
     are all graded: each pick with the line, edge, result, CLV and what the
     dashboard knew when it made the call (factors, risks, news, line movement).
  3. Writes site/data/insights.json: the record for each kind of pick across
     every archived week (underdogs vs favorites, home vs road, edge size,
     line moving against us, news flags...). The Results tab shows it, so you
     can see which kinds of picks are actually paying this season.

The archive only grows: a week once archived is rewritten only if a score changes.
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import nflverse, track

DATA = Path(__file__).resolve().parent.parent / "site" / "data"
ARCHIVE = DATA / "archive"
SMALL = 30  # fewer graded picks than this and a record is mostly noise


def season_of(entry):
    start = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
    return start.year if start.month >= 3 else start.year - 1


def weeks(log):
    """{(season, week): [entries]} for weeks where every pick has a result."""
    by = defaultdict(list)
    for e in log.values():
        by[(season_of(e), e.get("week"))].append(e)
    return {k: v for k, v in by.items() if k[1] is not None and all("result" in e for e in v)}


def archive(log, out=ARCHIVE):
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for (season, week), entries in sorted(weeks(log).items()):
        entries = sorted(entries, key=lambda e: (e["start"], e["game"], e["bet"]))
        doc = {"season": season, "week": week, "summary": track.summarize({str(i): e for i, e in enumerate(entries)}),
               "picks": entries}
        path = out / f"{season}-week-{week:02d}.json"
        text = json.dumps(doc, indent=1) + "\n"
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
        o = doc["summary"]["overall"]
        index.append({"season": season, "week": week, "file": path.name, "picks": len(entries),
                      "wins": o["wins"], "losses": o["losses"], "pushes": o["pushes"], "units": o["units"],
                      "avg_clv": o["avg_clv"]})
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return index


def load_archive(out=ARCHIVE):
    entries = []
    for path in sorted(out.glob("*-week-*.json")):
        entries += json.loads(path.read_text())["picks"]
    return entries


# Each group splits graded picks one way; a pick can land in several groups.
def _groups(e):
    f = e.get("features") or {}
    name = {"lock": "LOCK", "model": "Model lean"}.get(e["tier"], e["tier"].title())
    yield "Tier", f"{e['bet'].title()} {name}"
    if e.get("pattern"):
        yield "Pattern", {"wind15": "Wind 15+ Under", "wind10": "Wind 10-14 Under", "playoff_dog": "Playoff underdog"}.get(e["pattern"], e["pattern"])
    if e["bet"] == "spread":
        line = e["line"]
        yield "Side", "Underdog" if line > 0 else "Favorite" if line < 0 else "Pick'em"
        if f.get("side_is_home") is not None:
            yield "Venue", "Neutral site" if f.get("neutral") else "Home team" if f["side_is_home"] else "Road team"
        if e["tier"] == "model":
            edge = e["edge"]
            yield "Model edge", "7+ points" if edge >= 7 else "5 to 7 points" if edge >= 5 else "3 to 5 points"
    else:
        yield "Totals", e["side"]
    moved = f.get("moved_against")
    if moved is not None:
        yield "Line since open", "Moved against us" if moved > 0 else "Moved our way" if moved < 0 else "Didn't move"
    if f.get("news_qb"):
        yield "News", "QB headline"
    elif f.get("news_injury"):
        yield "News", "Injury headline"
    elif "news_qb" in f:
        yield "News", "No flagged news"


def insights(entries):
    groups = defaultdict(list)
    for e in entries:
        if "result" not in e:
            continue
        for group, label in _groups(e):
            groups[(group, label)].append(e)
    rows = []
    order = ["Tier", "Pattern", "Model edge", "Side", "Venue", "Line since open", "News", "Totals"]
    for (group, label), es in sorted(groups.items(), key=lambda kv: (order.index(kv[0][0]), kv[0][1])):
        rec = track._record(es)
        n = rec["wins"] + rec["losses"]
        rows.append({"group": group, "label": label, **rec, "graded": n, "small_sample": n < SMALL})
    return {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "graded": sum(1 for e in entries if "result" in e), "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true", help="don't fetch final scores from nflverse")
    args = ap.parse_args(argv)
    path = DATA / "picks.json"
    stored = json.loads(path.read_text()) if path.exists() else {"picks": {}}
    log = stored.get("picks", {})
    if not args.no_fetch and log:
        track.grade(log, nflverse.schedule())
        path.write_text(json.dumps({"summary": track.summarize(log), "picks": log}, indent=1) + "\n")
    index = archive(log)
    result = insights(load_archive())
    (DATA / "insights.json").write_text(json.dumps(result, indent=1) + "\n")
    print(f"Archived {len(index)} weeks; {result['graded']} graded picks in the archive.")


if __name__ == "__main__":
    main()
