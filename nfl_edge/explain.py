"""Plain-English reasons behind each pick, shown when you open a game.

Worked out from the same numbers the pick uses, so the explanation can't
disagree with the pick:

  * Pattern picks (wind Unders, playoff underdogs): what the pattern is, its
    long-run record, and the checks it passed.
  * Where the model's projected margin or total comes from: the projection is
    a sum of each team's offense, the other team's defense and home field, so
    it splits exactly into those pieces (see projections.py).
  * Warnings about what the model can't see (QB changes, small samples, huge
    disagreements with the market).
  * How picks like this have done live this season.
"""

from .odds import BOOK_NAMES
from .picks import LOCK_FORECAST_HOURS, MODEL_LEAN, PATTERNS, WIND_LEAN, WIND_LOCK
from .projections import SCORING_WEIGHT

HUGE_EDGE = 7.0       # NFL lines rarely miss by this much; usually the model is missing something
SMALL_SAMPLE = 4      # games played
QB_FEW_DROPBACKS = 60

UNIT_NAMES = {"pass": "pass offense", "rush": "run offense", "passD": "pass defense", "rushD": "run defense"}
MODEL_NOTE = ("Model leans are shown so you can see what the numbers say, but they're unproven: in 27 seasons "
              "of week-by-week replays, the model's side against the closing line won about 50%.")


def _plays(model, a, b):
    pace, league = model["pace"], model["league_plays"]
    return (pace.get(a, league) + pace.get(b, league)) / 2


def _side_points(model, offense, defense, plays):
    pts, epa = model["points"], model["epa"]
    w = SCORING_WEIGHT
    off = w * pts["off"].get(offense, 0.0) + (1 - w) * epa["scale"] * epa["off"].get(offense, 0.0) * plays
    dfn = w * pts["def"].get(defense, 0.0) + (1 - w) * epa["scale"] * epa["def"].get(defense, 0.0) * plays
    return off, dfn


def margin_parts(model, home, away, neutral):
    """Projected home margin split into team units. Positive numbers help the home team."""
    v = 0 if neutral else 1
    plays = _plays(model, home, away)
    h_off, a_def = _side_points(model, home, away, plays)
    a_off, h_def = _side_points(model, away, home, plays)
    w = SCORING_WEIGHT
    hfa = v * 2 * (w * model["points"]["hfa"] + (1 - w) * model["epa"]["scale"] * model["epa"]["hfa"] * plays)
    return [(f"{home} offense", h_off), (f"{away} defense", a_def), (f"{away} offense", -a_off),
            (f"{home} defense", -h_def), ("Home field", hfa)], plays


def _book(key):
    return BOOK_NAMES.get(key, str(key).title())


def _favorite(team_a, team_b, margin):
    if abs(margin) < 0.05:
        return "a pick'em"
    return f"the {team_a if margin > 0 else team_b} by {abs(margin):.1f}"


def explain_spread(game, pick, teams, model, evidence):
    home, away = game["home"], game["away"]
    proj = game["projection"]
    model_margin = proj["home"] - proj["away"]
    market_margin = -pick["line"] if pick["side"] == home else pick["line"]
    side_is_home = pick["side"] == home
    parts, plays = margin_parts(model, home, away, game["neutral"])
    sgn = 1 if side_is_home else -1
    factors = sorted(((label, sgn * pts) for label, pts in parts if abs(pts) >= 0.1), key=lambda f: -abs(f[1]))

    if pick.get("pattern"):
        pat = PATTERNS[pick["pattern"]]
        summary = (f"{pick['side']} are a playoff underdog getting {pick['line']:g} at {_book(pick['book'])}, and the model "
                   f"agrees: it has {_favorite(home, away, model_margin)} against the market's {_favorite(home, away, market_margin)}.")
        reasons = [pat["text"]]
    else:
        summary = (f"The model has {_favorite(home, away, model_margin)}; the market has {_favorite(home, away, market_margin)}. "
                   f"That's a {pick['edge']:.1f} point gap on {pick['label']} at {_book(pick['book'])}.")
        reasons = [MODEL_NOTE]
    for label, pts in factors[:3]:
        if label == "Home field":
            reasons.append(f"Home field is worth {abs(pts):.1f} points to the {home} this season.")
            continue
        team, unit = label.rsplit(" ", 1)
        good = (team == pick["side"]) == (pts > 0)
        reasons.append(f"The {team} {unit} is {'better' if good else 'worse'} than average, worth {abs(pts):.1f} points "
                       f"{'for' if pts > 0 else 'against'} the {pick['side']}.")
    reasons += _unit_clashes(teams.get(home), teams.get(away))
    checks = []
    if pick.get("pattern"):
        checks += [{"ok": True, "text": "Playoff game."},
                   {"ok": pick["line"] > 0, "text": "This side is the underdog."},
                   {"ok": pick["edge"] > 0, "text": "The model also likes this side."}]
    else:
        checks.append({"ok": pick["edge"] >= MODEL_LEAN, "text": f"Model edge of {pick['edge']:.1f} points "
                       f"({'over' if pick['edge'] >= MODEL_LEAN else 'under'} the {MODEL_LEAN:g}-point bar for a model lean)."})
        checks.append({"ok": False, "text": "Matches a pattern that has beaten the closing line over many seasons."})
    checks += _common_checks(pick)
    return {
        "summary": summary,
        "factors": [{"label": label, "points": round(pts, 1)} for label, pts in factors],
        "factor_note": f"How the model gets to its number, in points for the {pick['side']}. Built only from this "
                       f"season's games, opponent-adjusted; pace is {plays:.0f} plays a side.",
        "reasons": reasons,
        "checks": checks,
        "risks": _spread_risks(game, pick, teams),
        "evidence": evidence.get(f"spread:{pick['tier']}") or [],
    }


def explain_total(game, pick, teams, model, evidence):
    home, away, proj = game["home"], game["away"], game["projection"]
    plays = _plays(model, home, away)
    h_off, a_def = _side_points(model, home, away, plays)
    a_off, h_def = _side_points(model, away, home, plays)
    sgn = 1 if pick["side"] == "Over" else -1
    factors = sorted(((f"{home} offense", sgn * h_off), (f"{away} defense", sgn * a_def),
                      (f"{away} offense", sgn * a_off), (f"{home} defense", sgn * h_def)), key=lambda f: -abs(f[1]))
    wx = game.get("weather") or {}
    checks = []
    if pick.get("pattern"):
        pat = PATTERNS[pick["pattern"]]
        wind_txt = wx.get("wind_text") or f"{pick['wind']:.0f} mph"
        summary = (f"The forecast calls for {wind_txt} wind at kickoff in an outdoor stadium. "
                   f"Best Under number: {pick['line']:g} at {_book(pick['book'])}.")
        reasons = [pat["text"], f"The model, which doesn't know about the wind, projects {proj['total']:.1f} points."]
        hours = _forecast_hours(game, wx)
        checks += [{"ok": True, "text": "Outdoor stadium (no dome or retractable roof)."},
                   {"ok": pick["wind"] >= WIND_LOCK,
                    "text": f"Forecast wind {pick['wind']:.0f} mph (LOCK needs {WIND_LOCK:g}+, Lean {WIND_LEAN:g}+)."}]
        if pick["pattern"] == "wind15":
            checks.append({"ok": hours is not None and hours <= LOCK_FORECAST_HOURS,
                           "text": f"Forecast read {hours:.0f} hours before kickoff (LOCK needs {LOCK_FORECAST_HOURS} or fewer)."
                           if hours is not None else "Forecast timing unknown."})
    else:
        summary = (f"The model projects {proj['total']:.1f} total points; the best {pick['side']} number is "
                   f"{pick['line']:g}. That's a {pick['edge']:.1f} point gap.")
        reasons = [MODEL_NOTE]
        checks.append({"ok": pick["edge"] >= MODEL_LEAN, "text": f"Model edge of {pick['edge']:.1f} points "
                       f"({'over' if pick['edge'] >= MODEL_LEAN else 'under'} the {MODEL_LEAN:g}-point bar for a model lean)."})
        checks.append({"ok": False, "text": "Matches a pattern that has beaten the closing line over many seasons."})
    league = model["league_plays"]
    if abs(plays - league) >= 3:
        faster = plays > league
        reasons.append(f"These teams average {plays:.0f} plays against an NFL average of {league:.0f}, so the game "
                       f"should be {'faster' if faster else 'slower'} than usual.")
    for label, pts in factors[:2]:
        team, unit = label.rsplit(" ", 1)
        reasons.append(f"The {team} {unit} {'pushes toward' if pts > 0 else 'works against'} the {pick['side']} "
                       f"by {abs(pts):.1f} points.")
    checks += _common_checks(pick)
    risks = []
    if pick.get("pattern"):
        risks.append("Wind forecasts change. Check the forecast again close to kickoff; the pattern is based on "
                     "the wind measured at the game.")
        if wx.get("rain") is not None and wx["rain"] >= 50:
            risks.append(f"{wx['rain']}% chance of rain, which also tends to slow scoring.")
    elif pick["edge"] >= HUGE_EDGE:
        risks.append(f"A {pick['edge']:.1f} point gap on an NFL total is far outside what the model gets right. "
                     "Treat it as a sign the model is missing something.")
    for name in (home, away):
        qb = _qb_risk(teams.get(name))
        if qb:
            risks.append(qb)
    return {
        "summary": summary,
        "factors": [{"label": label, "points": round(pts, 1)} for label, pts in factors],
        "factor_note": f"Points each unit adds to (or takes from) the {pick['side']}, compared with two average teams.",
        "reasons": reasons, "checks": checks, "risks": risks,
        "evidence": evidence.get(f"total:{pick['tier']}") or [],
    }


def _forecast_hours(game, wx):
    from datetime import datetime
    try:
        k = datetime.fromisoformat(game["start"].replace("Z", "+00:00"))
        c = datetime.fromisoformat(wx["checked"].replace("Z", "+00:00"))
        return (k - c).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return None


def _common_checks(pick):
    out = []
    if pick.get("cover") is not None:
        basis = "its long-run record" if pick.get("pattern") else "the model edge, shrunk toward the market"
        out.append({"ok": None, "text": f"Estimated chance to win: {pick['cover'] * 100:.1f}%, from {basis}. "
                                        "You need 52.4% to break even at -110."})
    moved = pick.get("moved_against")
    if moved is None:
        out.append({"ok": None, "text": "No opening line recorded yet, so line movement can't be checked."})
    else:
        out.append({"ok": None, "text": (f"The line has moved {abs(moved):g} {'against' if moved > 0 else 'toward'} "
                                         "this side since it opened." if moved else "The line hasn't moved since it opened.")})
    out.append({"ok": None, "text": "Check the official injury report for both starting quarterbacks before betting."})
    return out


def _unit_clashes(home_t, away_t):
    if not home_t or not away_t:
        return []
    out = []
    for off_t, def_t in ((home_t, away_t), (away_t, home_t)):
        for o, d in (("pass", "passD"), ("rush", "rushD")):
            gap = off_t["grades"][o] - def_t["grades"][d]
            if abs(gap) >= 2.5:
                o_txt = f"the {off_t['team']} {UNIT_NAMES[o]} ({off_t['grades'][o]:.1f})"
                d_txt = f"the {def_t['team']} {UNIT_NAMES[d]} ({def_t['grades'][d]:.1f})"
                out.append((abs(gap), f"{o_txt[0].upper() + o_txt[1:]} should beat {d_txt}." if gap > 0
                            else f"{d_txt[0].upper() + d_txt[1:]} should shut down {o_txt}."))
    return [text for _, text in sorted(out, reverse=True)[:2]]


def _qb_risk(team):
    qb = team.get("qb") if team else None
    if not qb:
        return None
    if qb.get("changed"):
        return (f"The {team['team']}' most recent starter, {qb['name']}, isn't the QB who played most of the season "
                f"({qb['season_leader']}). The grades still mostly reflect {qb['season_leader']}.")
    if qb.get("dropbacks") is not None and qb["dropbacks"] < QB_FEW_DROPBACKS:
        return f"The {team['team']}' QB ({qb['name']}) has only {qb['dropbacks']} dropbacks this season."
    return None


def _spread_risks(game, pick, teams):
    risks = []
    if pick["edge"] >= HUGE_EDGE:
        risks.append(f"A {pick['edge']:.1f} point gap with an NFL line is unusually large. It usually means the market "
                     "knows something the stats don't (an injury, a QB change). Check the injury report.")
    for name in (game["home"], game["away"]):
        t = teams.get(name)
        if t and t.get("games", 99) < SMALL_SAMPLE:
            risks.append(f"The {name} have played only {t['games']} games, so their grades can still move a lot.")
        qb = _qb_risk(t)
        if qb:
            risks.append(qb)
    return risks


def explain_game(game, teams, model, evidence=None):
    """Adds game["why"] = {"spread": {...}, "total": {...}} for each pick that isn't a Pass."""
    evidence = evidence or {}
    why = {}
    sp, tp = game["picks"].get("spread"), game["picks"].get("total")
    if sp and sp["tier"] != "pass":
        why["spread"] = explain_spread(game, sp, teams, model, evidence)
    if tp and tp["tier"] != "pass":
        why["total"] = explain_total(game, tp, teams, model, evidence)
    _add_news(game, why)
    game["why"] = why
    return game


def _add_news(game, why):
    news = game.get("news") or {}
    headlines = [{**h, "team": team} for team, n in news.items() for h in n["headlines"]]
    for w in why.values():
        w["news"] = headlines
        for team, n in news.items():
            if n["qb_alert"]:
                w["risks"].insert(0, f"Recent headlines mention a quarterback issue for the {team}. Read them below before betting.")
            elif n["injury"]:
                w["risks"].append(f"Recent headlines mention an injury or absence for the {team}.")
