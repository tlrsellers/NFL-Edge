from nfl_edge import picks

PROJ = {"home": 24.0, "away": 20.0, "total": 44.0}
BOOKS = {"draftkings": {"spread_home": -3.0, "total": 44.5}, "fanduel": {"spread_home": -2.5, "total": 45.0},
         "bovada": {"spread_home": -3.5, "total": 44.0}}


def test_wind_15_is_a_lock_at_the_highest_total():
    p = picks.total_pick(PROJ, BOOKS, context={"outdoor": True, "wind": 17, "forecast_hours": 20})
    assert p["tier"] == "lock" and p["side"] == "Under" and p["line"] == 45.0 and p["book"] == "fanduel"
    assert p["pattern"] == "wind15" and p["cover"] == 0.570


def test_wind_lock_waits_for_a_close_forecast():
    p = picks.total_pick(PROJ, BOOKS, context={"outdoor": True, "wind": 18, "forecast_hours": 80})
    assert p["tier"] == "strong" and "hours away" in p["note"]


def test_wind_10_to_14_is_a_lean_and_domes_never_count():
    assert picks.total_pick(PROJ, BOOKS, context={"outdoor": True, "wind": 12, "forecast_hours": 5})["tier"] == "lean"
    p = picks.total_pick(PROJ, BOOKS, context={"outdoor": False, "wind": 25, "forecast_hours": 5})
    assert p["pattern"] is None and p["tier"] != "lock"


def test_model_edges_alone_never_reach_lean():
    big = {"home": 34.0, "away": 10.0, "total": 60.0}
    sp = picks.spread_pick(big, BOOKS, "Colts", "Titans")
    tp = picks.total_pick(big, BOOKS)
    assert sp["tier"] == "model" and tp["tier"] == "model"
    assert sp["cover"] < 0.54  # a 21-point edge still shrinks to about 53%
    small = picks.spread_pick({"home": 23.5, "away": 21.0, "total": 44}, BOOKS, "Colts", "Titans")
    assert small["tier"] == "pass"


def test_playoff_underdog_needs_model_agreement():
    likes_dog = {"home": 21.0, "away": 22.0, "total": 43.0}  # model has the away dog winning
    p = picks.spread_pick(likes_dog, BOOKS, "Colts", "Titans", context={"playoff": True})
    assert p["side"] == "Titans" and p["line"] == 3.5 and p["tier"] == "strong" and p["pattern"] == "playoff_dog"
    likes_fav = {"home": 31.0, "away": 20.0, "total": 51.0}
    p = picks.spread_pick(likes_fav, BOOKS, "Colts", "Titans", context={"playoff": True})
    assert p["side"] == "Colts" and p["pattern"] is None


def test_best_pick_prefers_tier_then_cover():
    lock = {"tier": "lock", "edge": 0.0, "cover": .57}
    model = {"tier": "model", "edge": 9.0, "cover": .51}
    assert picks.best_pick(model, lock) is lock


def test_backtest_rules_settle_against_the_final():
    r = {"home": "Bills", "away": "Jets", "type": "REG", "line": 3.0, "total_line": 40.0, "proj_margin": 9.0,
         "proj_total": 41.0, "margin": 7, "points": 33, "wind": 20, "roof": "outdoors"}
    sp, tp = picks.backtest_picks(r)
    assert sp["side"] == "Bills" and sp["result"] == "win"   # Bills -3, won by 7
    assert tp["tier"] == "lock" and tp["result"] == "win"    # Under 40, 33 points
