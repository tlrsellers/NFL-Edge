"""Round-the-clock news check between line scans.

    python -m nfl_edge.newswatch

Runs every two hours, day and night (Actions -> News watch). It re-reads the
headlines for every upcoming game with a pick, using the slate from the last
lines scan, so it costs no Odds API credits. It doesn't send email.

To keep the repo's history small, the slate is only rewritten when a new
flagged headline (QB, injury, suspension...) appears. Ordinary headlines are
picked up by the next lines scan.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import news, track
from .slate import full_names
from .explain import explain_game
from .picks import best_pick

DATA = Path(__file__).resolve().parent.parent / "site" / "data"


def _load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _signature(games):
    """What a refresh must change before it's worth publishing."""
    sig = []
    for g in games:
        tiers = tuple(sorted((b, p["tier"]) for b, p in g["picks"].items() if p))
        flagged = tuple(sorted((t, h["flag"], h["title"]) for t, n in (g.get("news") or {}).items()
                               for h in n["headlines"] if h["flag"]))
        sig.append((g["id"], tiers, flagged))
    return sig


def refresh(slate, names, team_grades, model, evidence, now_iso, fetch=news.fetch_team):
    """Re-check news for upcoming games. Returns True if a flagged headline changed."""
    upcoming = [g for g in slate["games"] if g["start"] > now_iso]
    before = _signature(upcoming)
    for g in upcoming:
        g.pop("news", None)
    if not news.check_slate(upcoming, names, fetch=fetch):
        return False  # feed unreachable: keep the last scan's news
    for g in upcoming:
        g["best"] = best_pick(g["picks"]["spread"], g["picks"]["total"])
        explain_game(g, team_grades, model, evidence)
    return _signature(upcoming) != before


def main(argv=None):
    now = datetime.now(timezone.utc)
    slate = _load(DATA / "slate.json", None)
    grades = _load(DATA / "grades.json", None)
    if not slate or not grades or "model" not in grades or slate.get("sample"):
        print("No live slate yet; nothing to check.")
        return
    summary = _load(DATA / "picks.json", {}).get("summary")
    evidence = track.evidence(summary)
    now_iso = now.isoformat(timespec="minutes").replace("+00:00", "Z")
    if not refresh(slate, full_names(), {t["team"]: t for t in grades["teams"]}, grades["model"], evidence, now_iso):
        print("No new flagged headlines; nothing to publish.")
        return
    slate["news_checked"] = now_iso
    (DATA / "slate.json").write_text(json.dumps(slate, indent=1) + "\n")
    print("Published news update.")


if __name__ == "__main__":
    main()
