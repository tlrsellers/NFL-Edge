"""The picks newsletter: exactly two emails a week, to you and your friends.

  Wednesday night  the week's LOCKs, Strong and Lean plays (Thursday through Monday)
  Saturday night   Sunday's and Monday's plays, with wind forecasts close to kickoff

Both include last week's record. Nothing else ever emails anyone: LOCKs, line
moves and headlines only show on the dashboard. The `Picks email` workflow
(newsletter.py) runs a few times inside each window, because GitHub starts
scheduled jobs late; the first run with fresh lines sends the email and records
it in site/data/emails.json so it never goes out twice.

  Wednesday window:  Wednesday 6 PM to Thursday 10 AM Central
  Saturday window:   Saturday 6 PM to Sunday 9 AM Central

Wind LOCKs need a forecast read within 36 hours of kickoff, so most Sunday
LOCKs first appear in the Saturday email.
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .odds import BOOK_NAMES
from .picks import PATTERNS

CENTRAL = ZoneInfo("America/Chicago")
def _site():
    """The dashboard's address: the SITE_URL repository variable, else the repo's GitHub Pages URL."""
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return "the dashboard"


SITE = _site()
NAMES = {"wed": "Wednesday", "sat": "Saturday night"}
DAYS = {"wed": 2, "sat": 5}  # Monday is 0


def window(now):
    local = now.astimezone(CENTRAL)
    day, hour = local.weekday(), local.hour
    if (day == 2 and hour >= 18) or (day == 3 and hour < 10):
        return "wed"
    if (day == 5 and hour >= 18) or (day == 6 and hour < 9):
        return "sat"
    return None


def _window_start(now, which):
    local = now.astimezone(CENTRAL)
    back = (local.weekday() - DAYS[which]) % 7
    return (local - timedelta(days=back)).replace(hour=18, minute=0, second=0, microsecond=0)


def key(now, which):
    return f"{_window_start(now, which).date().isoformat()}-{which}"


def due(now, sent):
    which = window(now)
    if which and key(now, which) not in sent:
        return which, key(now, which)
    return None


def fresh(slate, now, which):
    """True when lines were scanned inside this window, or the window is nearly over (send what we have)."""
    start = _window_start(now, which)
    if _parse(slate["updated"]) >= start - timedelta(hours=1):
        return True
    return now.astimezone(CENTRAL) >= start + timedelta(hours=10)


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _kick(ts):
    return _parse(ts).astimezone(CENTRAL).strftime("%a %-I:%M %p CT")


def horizon(now):
    """Last kickoff the email covers: the end of the coming Monday night game (Tuesday 4 AM Central)."""
    local = now.astimezone(CENTRAL)
    days = (1 - local.weekday()) % 7 or 7
    return (local + timedelta(days=days)).replace(hour=4, minute=0, second=0, microsecond=0)


def plays(slate, now):
    """{tier: [(game, pick)]} for LOCK, Strong and Lean picks kicking off between now and the horizon."""
    end = horizon(now)
    out = {"lock": [], "strong": [], "lean": []}
    for g in slate["games"]:
        if not (now < _parse(g["start"]) <= end):
            continue
        for p in (g["picks"].get("spread"), g["picks"].get("total")):
            if p and p["tier"] in out:
                out[p["tier"]].append((g, p))
    for v in out.values():
        v.sort(key=lambda gp: gp[0]["start"])
    return out


def _wl(entries):
    w = sum(e.get("result") == "win" for e in entries)
    l = sum(e.get("result") == "loss" for e in entries)
    p = sum(e.get("result") == "push" for e in entries)
    return f"{w}-{l}" + (f"-{p}" if p else "")


def last_week(log, week):
    if not week or not log:
        return []
    graded = [e for e in log.values() if e.get("week") == week - 1 and e.get("tier") in ("lock", "strong", "lean")
              and "result" in e]
    if not graded:
        return []
    year = max(e["start"][:4] for e in graded)
    season = [e for e in log.values() if "result" in e and e.get("tier") in ("lock", "strong", "lean")
              and e["start"][:4] == year]
    lines = [f"## Last week (week {week - 1})", ""]
    for t, name in (("lock", "LOCKs"), ("strong", "Strong"), ("lean", "Lean")):
        es = [e for e in graded if e["tier"] == t]
        lines.append(f"- **{name}: {_wl(es)}**" if es else f"- {name}: none")
    mark = {"win": "✅", "loss": "❌", "push": "➖"}
    for e in sorted(graded, key=lambda e: e["start"]):
        if e["tier"] == "lock":
            lines.append(f"  - {mark.get(e['result'], '')} 🔒 {e['side']} {e['line']:g} ({e['away']} @ {e['home']})")
    lines += ["- Season so far: " + ", ".join(f"{n} {_wl([e for e in season if e['tier'] == t])}"
                                              for t, n in (("lock", "LOCKs"), ("strong", "Strong"), ("lean", "Lean"))), ""]
    return lines


def _block(g, p, icon):
    why = (g.get("why") or {}).get(p["bet"]) or {}
    pat = PATTERNS.get(p.get("pattern") or "", {})
    lines = [f"### {icon} {p['label']} at {BOOK_NAMES.get(p['book'], p['book'])}",
             f"{g['away']} @ {g['home']}, {_kick(g['start'])}. {pat.get('name', '')}: "
             f"{pat.get('record', '')} historically ({p['cover'] * 100:.0f}%).", ""]
    if why.get("summary"):
        lines.append(why["summary"])
    if p.get("note"):
        lines.append(f"_{p['note']}_")
    risks = why.get("risks") or []
    if risks:
        lines += ["", "**What could go wrong**"] + [f"- {r}" for r in risks[:3]]
    return "\n".join(lines)


def compose(slate, now, which, log=None):
    """(title, markdown body) for the email."""
    tiers = plays(slate, now)
    n_lock, n_strong, n_lean = (len(tiers[t]) for t in ("lock", "strong", "lean"))
    when = NAMES[which]
    title = (f"🔒 NFL Edge {when} picks: {n_lock} LOCK{'s' if n_lock != 1 else ''}, {n_strong} Strong, {n_lean} Lean"
             if n_lock else f"NFL Edge {when} picks: {n_strong} Strong, {n_lean} Lean")
    out = [f"Lines as of {_parse(slate['updated']).astimezone(CENTRAL).strftime('%a %-I:%M %p CT')}. "
           f"Full breakdowns on the [dashboard]({SITE}).", ""]
    if which == "wed":
        out += ["Wind forecasts firm up over the weekend; the Saturday night email has the final call on Sunday's games.", ""]
    out += last_week(log, slate.get("week"))
    for t, name, icon in (("lock", "LOCKs", "🔒"), ("strong", "Strong plays", "💪"), ("lean", "Leans", "👀")):
        out += [f"## {name}", ""]
        if tiers[t]:
            out += ["\n\n".join(_block(g, p, icon) for g, p in tiers[t]), ""]
        else:
            out += ["None." if t != "lock" else
                    "No LOCKs. A LOCK needs a forecast of 15+ mph wind at an outdoor stadium, read within 36 hours "
                    "of kickoff. Most weeks have none, and that's fine.", ""]
    model = sum(1 for g in slate["games"] for p in g["picks"].values() if p and p["tier"] == "model")
    if model:
        out += [f"The dashboard also lists {model} model lean{'s' if model != 1 else ''}. Those are unproven: "
                "in 27 seasons of replays the model's side won about half the time, so they aren't in this email.", ""]
    out += ["Before betting: check the injury report and the latest wind forecast, and confirm the line is still "
            "close to the one above. No pick is a sure thing; bet only what you can afford to lose.",
            "", "_NFL Edge sends two emails a week, Wednesday and Saturday night. For entertainment and information "
            "only. 21+. Gambling problem? Call 1-800-GAMBLER._"]
    return title, "\n".join(out)
