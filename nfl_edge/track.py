"""Pick tracking: remembers every play the dashboard made and grades it after the game.

site/data/picks.json holds one entry per game and bet type ("<game id>:spread").
The entry is the call the dashboard showed you: it's saved the first time the
game has a model lean or better on that bet, and replaced only if the call later gets
stronger (a Lean that becomes a LOCK is graded as a LOCK at the LOCK number).
Until kickoff each scan also records the market consensus, so the last one
before kickoff is the closing line.

After the game, each pick gets a result (win, loss or push) and its closing
line value (CLV): how many points better our number was than the close. CLV is
the most reliable early sign of a real edge, because it shows up long before
the win-loss record means anything.
"""

from collections import defaultdict

from .picks import RANK

TIERS = ("lock", "strong", "lean", "model")


def _close_for_side(entry):
    """The closing number from our side's point of view, comparable with entry['line']."""
    close = entry.get("close")
    if close is None:
        return None
    if entry["bet"] == "spread":
        return close if entry["side"] == entry["home"] else -close
    return close


def record_calls(log, slate_games, now_iso):
    """Save or upgrade calls for games that haven't kicked off, and refresh their closing line."""
    for g in slate_games:
        if g["start"] <= now_iso:
            continue  # kicked off: the call and the close are frozen
        for bet in ("spread", "total"):
            p = g["picks"].get(bet)
            key = f"{g['id']}:{bet}"
            entry = log.get(key)
            if p and p["tier"] != "pass" and (entry is None or RANK[p["tier"]] > RANK[entry["tier"]]):
                entry = log[key] = {
                    "game": g["id"], "week": g.get("week"), "start": g["start"], "home": g["home"], "away": g["away"],
                    "bet": bet, "side": p["side"], "line": p["line"], "book": p["book"], "edge": p["edge"],
                    "tier": p["tier"], "pattern": p.get("pattern"), "cover": p.get("cover"), "called": now_iso,
                    "projection": {k: g["projection"][k] for k in ("home", "away", "total")},
                    "features": _features(g, bet, p),
                }
            if entry is not None:
                lines = [b.get("spread_home" if bet == "spread" else "total") for b in g["lines"].values()]
                lines = [x for x in lines if x is not None]
                if lines:
                    entry["close"] = round(sum(lines) / len(lines), 2)
    return log


def _features(g, bet, p):
    """What the dashboard knew when it made the call, so the weekly review can learn which signals pay."""
    why = (g.get("why") or {}).get(bet) or {}
    news = g.get("news") or {}
    return {
        "neutral": g.get("neutral"),
        "playoff": g.get("type") not in (None, "REG"),
        "wind": (g.get("weather") or {}).get("wind"),
        "side_is_home": p["side"] == g["home"] if bet == "spread" else None,
        "moved_against": p.get("moved_against"),
        "note": p.get("note"),
        "factors": why.get("factors", []),
        "risks": why.get("risks", []),
        "news_qb": any(n["qb_alert"] for n in news.values()),
        "news_injury": any(n["injury"] for n in news.values()),
    }


def grade(log, games):
    """Fill in result, margin and CLV for finished games. `games` is the nflverse schedule."""
    finals = {str(g["id"]): g for g in games if g.get("completed")}
    for entry in log.values():
        g = finals.get(str(entry["game"]))
        if g is None or "result" in entry:
            continue
        hp, ap = int(g["home_score"]), int(g["away_score"])
        entry["final"] = {"home": hp, "away": ap}
        if entry["bet"] == "spread":
            mine, theirs = (hp, ap) if entry["side"] == entry["home"] else (ap, hp)
            margin = mine - theirs + entry["line"]
        else:
            margin = (hp + ap - entry["line"]) * (1 if entry["side"] == "Over" else -1)
        entry["margin"] = round(margin, 1)
        entry["result"] = "win" if margin > 0 else "loss" if margin < 0 else "push"
        close = _close_for_side(entry)
        if close is not None:
            if entry["bet"] == "spread":
                clv = entry["line"] - close           # we got more points than the close
            elif entry["side"] == "Over":
                clv = close - entry["line"]           # we bought the over at a lower total
            else:
                clv = entry["line"] - close
            entry["clv"] = round(clv, 1)
    return log


def _record(entries):
    w = sum(e["result"] == "win" for e in entries)
    l = sum(e["result"] == "loss" for e in entries)
    p = sum(e["result"] == "push" for e in entries)
    clv = [e["clv"] for e in entries if e.get("clv") is not None]
    return {
        "wins": w, "losses": l, "pushes": p,
        "win_pct": round(w / (w + l), 3) if w + l else None,
        # At standard -110 prices you need 52.4% to break even.
        "units": round(w * 100 / 110 - l, 2),
        "avg_clv": round(sum(clv) / len(clv), 2) if clv else None,
        "beat_close": round(sum(c > 0 for c in clv) / len(clv), 3) if clv else None,
    }


def summarize(log):
    graded = [e for e in log.values() if "result" in e]
    by = defaultdict(list)
    for e in graded:
        by[f"{e['bet']}:{e['tier']}"].append(e)
        by[f"{e['bet']}:all"].append(e)
        by[f"week:{e.get('week')}"].append(e)
    return {
        "graded": len(graded),
        "pending": len(log) - len(graded),
        "overall": _record(graded),
        "by_tier": {k: _record(v) for k, v in by.items() if not k.startswith("week:")},
        "by_week": {k.split(":", 1)[1]: _record(v) for k, v in sorted(by.items()) if k.startswith("week:")},
    }


def evidence(summary):
    """Lines of 'how picks like this have done live this season', keyed like 'spread:lock'."""
    out = defaultdict(list)
    for key, rec in (summary or {}).get("by_tier", {}).items():
        if rec["wins"] + rec["losses"] + rec["pushes"]:
            line = f"Live this season: {rec['wins']}-{rec['losses']}" + (f"-{rec['pushes']}" if rec["pushes"] else "")
            if rec["win_pct"] is not None:
                line += f" ({rec['win_pct']:.0%})"
            if rec["avg_clv"] is not None:
                line += f", beating the closing line by {rec['avg_clv']:+.1f} points on average"
            out[key].append(line + ".")
    return dict(out)
