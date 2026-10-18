"""Projected score for any matchup, from the model block in grades.json.

Two estimates, averaged:
  * Scoring: opponent- and venue-adjusted points scored and allowed.
  * Efficiency: adjusted EPA per play (offense plus the defense it faces) times
    the expected number of plays, converted to points with a factor fitted on
    this season's games.
The efficiency half is steadier because it ignores fumble luck and red-zone
variance; the scoring half keeps the projection anchored to real points.
"""

SCORING_WEIGHT = 0.5


def team_points(model, offense, defense, venue):
    """Expected points for `offense` against `defense`. venue: +1 home, -1 away, 0 neutral."""
    pts, epa = model["points"], model["epa"]
    scoring = pts["mean"] + pts["off"].get(offense, 0.0) + pts["def"].get(defense, 0.0) + pts["hfa"] * venue
    pace = model["pace"]
    league = model["league_plays"]
    plays = (pace.get(offense, league) + pace.get(defense, league)) / 2
    epa_edge = epa["off"].get(offense, 0.0) + epa["def"].get(defense, 0.0) + epa["hfa"] * venue
    efficiency = pts["mean"] + epa["scale"] * epa_edge * plays
    return max(0.0, SCORING_WEIGHT * scoring + (1 - SCORING_WEIGHT) * efficiency)


def project(model, home, away, neutral=False):
    v = 0 if neutral else 1
    h = team_points(model, home, away, v)
    a = team_points(model, away, home, -v)
    return {
        "home": round(h, 1),
        "away": round(a, 1),
        # Spread in betting form for the home team: negative means home is favored.
        "spread": round(a - h, 1),
        "total": round(h + a, 1),
    }
