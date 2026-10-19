import importlib.util
import random
from pathlib import Path

spec = importlib.util.spec_from_file_location("rule_check", Path(__file__).resolve().parents[1] / "scripts" / "rule_check.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def _game(season, rng, wind, under_wins):
    total_line = 44.0
    points = 40 if under_wins else 48
    return {"season": season, "week": 6, "type": "REG", "home": "Bills", "away": "Jets", "neutral": False,
            "div": False, "line": rng.choice([-3.0, 3.0, -6.5, 6.5]), "total_line": total_line,
            "margin": rng.choice([-10, -2, 4, 9]), "points": points, "proj_margin": 0.0, "proj_total": 44.0,
            "roof": "outdoors", "wind": wind, "temp": 50, "weekday": "Sunday", "home_rest": 7, "away_rest": 7}


def test_health_flags_a_losing_rule_red():
    rng = random.Random(1)
    games = [_game(s, rng, 18, under_wins=(i % 10) < 4) for s in range(1999, 2026) for i in range(20)]  # 40% Unders
    h = {x["rule"]: x for x in rc.health(games)}
    assert h["wind15"]["status"] == "RED"


def test_health_green_for_a_strong_rule():
    rng = random.Random(2)
    games = [_game(s, rng, 18, under_wins=(i % 10) < 6) for s in range(1999, 2026) for i in range(30)]  # 60% Unders
    assert {x["rule"]: x for x in rc.health(games)}["wind15"]["status"] == "GREEN"


def test_search_finds_a_planted_pattern_and_ignores_noise():
    rng = random.Random(3)
    games = []
    for s in range(1999, 2026):
        for i in range(60):
            cold = i < 15
            g = _game(s, rng, 5, under_wins=(rng.random() < (0.66 if cold else 0.5)))
            g["temp"] = 20 if cold else 60
            games.append(g)
    found = rc.search(games)
    assert any(c["side"] == "under" and "32F or colder" in c["features"] for c in found)
    assert not any(c["side"] == "over" and "32F or colder" in c["features"] for c in found)
