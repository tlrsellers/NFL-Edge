import json
from datetime import datetime, timedelta, timezone

import numpy as np

from nfl_edge import digest, grades, news, odds, sample, slate, stats, track, weather
from nfl_edge.nflverse import NICK


def test_grades_recover_hidden_strength():
    rows, games = sample.sample_season(2026, weeks=8, seed=3)
    g = grades.grade_season(rows, 2026, games)
    assert len(g["teams"]) == 32
    rng = np.random.default_rng(3)
    true_off = dict(zip(sample.CODES, rng.normal(0, .08, 32)))
    off = {t["abbr"]: t["grades"]["off"] for t in g["teams"]}
    corr = np.corrcoef([true_off[c] for c in sample.CODES], [off[c] for c in sample.CODES])[0, 1]
    assert corr > 0.6
    assert all(0 <= v <= 10 for t in g["teams"] for v in t["grades"].values())


def test_grades_only_use_earlier_weeks():
    rows, games = sample.sample_season(2026, weeks=6)
    g3 = grades.grade_season(rows, 2026, games, through_week=3)
    assert g3["through_week"] == 2
    assert max(g3["model"]["games"].values()) == 2


def test_summarize_plays():
    base = {"season": "2026", "week": "1", "season_type": "REG", "game_id": "G", "home_team": "KC",
            "posteam": "KC", "defteam": "BUF", "wp": "0.5", "fixed_drive": "1", "yardline_100": "75",
            "play_type": "pass", "fixed_drive_result": "Touchdown"}
    plays = [dict(base, qb_dropback="1", epa="0.5", yards_gained="25", passer_player_id="Q1", passer_player_name="P.Mahomes", qb_epa="0.5"),
             dict(base, rush_attempt="1", epa="-0.4", yards_gained="0", play_type="run", yardline_100="30"),
             dict(base, rush_attempt="1", epa="1.0", yards_gained="3", play_type="run", wp="0.99")]  # garbage time
    rows = stats.summarize(plays)
    kc = next(r for r in rows if r["team"] == "KC")
    assert kc["plays"] == 2 and kc["pass_explosive"] == 1 and kc["rush_stuffed"] == 1
    assert kc["trips"] == 1 and kc["trip_points"] == 7 and kc["qb_name"] == "P.Mahomes"


def test_sample_slate_end_to_end(tmp_path):
    rows, games = sample.sample_season(2026)
    gr = grades.grade_season(rows, 2026, games)
    now = datetime(2026, 10, 17, 18, tzinfo=timezone.utc)
    schedule, events, credits, forecasts = sample.sample_slate_inputs(gr, now)
    s, history, alerts = slate.build_slate(gr, slate.upcoming_games(schedule, now), events, {}, now, forecasts)
    assert len(s["games"]) == 16 and all(g["lines"] for g in s["games"])
    assert set(s["games"][0]["lines"]) == {"draftkings", "fanduel", "bovada"}
    tiers = [p["tier"] for g in s["games"] for p in g["picks"].values() if p]
    assert "lock" in tiers and "lean" in tiers
    json.dumps(s)  # serializable


def test_odds_team_names():
    assert odds.team("Kansas City Chiefs") == "Chiefs"
    assert odds.team("Washington Commanders") == "Commanders"
    assert odds.team("Los Angeles Rams") == "Rams"
    assert odds.team("Nowhere FC") is None


def test_weather_parsing():
    assert weather.parse_wind("10 to 15 mph") == 12.5
    assert weather.parse_wind("7 mph") == 7
    k = datetime(2026, 10, 18, 17, tzinfo=timezone.utc)
    periods = [{"startTime": "2026-10-18T12:00:00-05:00", "endTime": "2026-10-18T13:00:00-05:00", "windSpeed": "18 mph"}]
    assert weather.kickoff_period(periods, k)["windSpeed"] == "18 mph"
    assert weather.outdoor("BUF", False) and not weather.outdoor("DET", False) and not weather.outdoor("BUF", True)


def test_track_grades_and_clv():
    log = {}
    g = {"id": "2026_07_NYJ_BUF", "start": "2026-10-25T17:00Z", "week": 7, "home": "Bills", "away": "Jets",
         "type": "REG", "neutral": False, "projection": {"home": 20, "away": 18, "total": 38},
         "lines": {"bovada": {"total": 41.0}},
         "picks": {"spread": None, "total": {"tier": "lock", "side": "Under", "line": 42.0, "book": "fanduel",
                                             "edge": 4.0, "pattern": "wind15", "cover": .57}}}
    track.record_calls(log, [g], "2026-10-24T12:00Z")
    sched = [{"id": g["id"], "completed": True, "home_score": 17, "away_score": 13}]
    track.grade(log, sched)
    e = log[f"{g['id']}:total"]
    assert e["result"] == "win" and e["clv"] == 1.0
    assert track.summarize(log)["by_tier"]["total:lock"]["wins"] == 1


def test_news_flags():
    assert news.classify("Bills QB ruled out for Sunday") == "qb"
    assert news.classify("Jets WR questionable with ankle injury") == "injury"
    assert news.classify("Chiefs beat Raiders") is None


def test_email_windows():
    ct = digest.CENTRAL
    wed = datetime(2026, 10, 21, 19, tzinfo=ct)
    sat = datetime(2026, 10, 24, 20, tzinfo=ct)
    assert digest.window(wed) == "wed" and digest.window(sat) == "sat"
    assert digest.window(datetime(2026, 10, 22, 12, tzinfo=ct)) is None
    assert digest.horizon(sat).weekday() == 1  # through Monday night


def test_every_team_has_a_nickname():
    assert len(set(NICK.values())) == 32
