"""Turns nflverse play-by-play into one row per offense per game.

Garbage time is excluded the usual way: plays where the offense's win
probability was below 5% or above 95% before the snap. Kneels and spikes are
dropped. Every rate is stored as a sum plus a count so games can be weighted.

Columns (per team, per game, as the offense):
  plays, epa, success, explosive        all designed passes and runs
  pass_n, pass_epa, pass_success, pass_explosive   dropbacks (incl. sacks, scrambles)
  rush_n, rush_epa, rush_success, rush_stuffed     designed runs
  havoc               sacks + interceptions + forced fumbles + tackles for loss + passes defensed
  trips, trip_points  drives that reached the opponent's 40, and the points they scored
  start_pos           sum of own-drive starting yardline (yards from own goal), drives
  st_epa              net special-teams EPA (kicks, punts, returns, field goals)
  points              points scored
  qb_id, qb_name, qb_dropbacks, qb_epa   the passer with the most dropbacks that game
"""

from collections import defaultdict

from .nflverse import code

FIELDS = ["season", "week", "game_id", "team", "opp", "home", "plays", "epa", "success", "explosive",
          "pass_n", "pass_epa", "pass_success", "pass_explosive", "rush_n", "rush_epa", "rush_success",
          "rush_stuffed", "havoc", "trips", "trip_points", "drives", "start_pos", "st_epa", "points",
          "qb_id", "qb_name", "qb_dropbacks", "qb_epa"]
DRIVE_POINTS = {"Touchdown": 7, "Field goal": 3}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _on(row, key):
    return _f(row.get(key)) == 1


def summarize(plays, season_type="REG"):
    """plays: iterable of nflverse play dicts. Returns a list of team-game rows."""
    g = defaultdict(lambda: defaultdict(float))
    meta, qbs = {}, defaultdict(lambda: defaultdict(lambda: [0, 0.0, ""]))
    drives = {}
    for p in plays:
        if season_type and p.get("season_type") != season_type:
            continue
        off, de, gid = p.get("posteam"), p.get("defteam"), p.get("game_id")
        if not off or not de or not gid:
            continue
        off, de = code(off), code(de)
        key = (gid, off)
        if key not in meta:
            home = code(p.get("home_team", ""))
            meta[key] = (int(float(p["season"])), int(float(p["week"])), de, 1 if off == home else 0)
        epa = _f(p.get("epa"))

        # Drives: starting spot, whether they reached the opponent 40, and how they ended.
        dkey = (gid, p.get("fixed_drive"))
        ydl = _f(p.get("yardline_100"))
        if p.get("fixed_drive") and ydl is not None and p.get("play_type") in ("pass", "run", "field_goal", "punt", "qb_kneel", "qb_spike", "no_play"):
            d = drives.setdefault(dkey, {"team": off, "start": ydl, "best": ydl, "result": p.get("fixed_drive_result")})
            if d["team"] == off:
                d["best"] = min(d["best"], ydl)

        # Special teams: EPA is from the possessing team's point of view.
        if _on(p, "special_teams_play") and epa is not None:
            g[key]["st_epa"] += epa
            g[(gid, de)]["st_epa"] -= epa
            if (gid, de) not in meta:
                home = code(p.get("home_team", ""))
                meta[(gid, de)] = (int(float(p["season"])), int(float(p["week"])), off, 1 if de == home else 0)

        if epa is None or _on(p, "qb_kneel") or _on(p, "qb_spike"):
            continue
        dropback, rush = _on(p, "qb_dropback"), _on(p, "rush_attempt") and not _on(p, "qb_scramble")
        if not dropback and not rush:
            continue
        wp = _f(p.get("wp"))
        if wp is not None and not 0.05 <= wp <= 0.95:
            continue
        yards = _f(p.get("yards_gained")) or 0.0
        succ = 1.0 if epa > 0 else 0.0
        row = g[key]
        row["plays"] += 1
        row["epa"] += epa
        row["success"] += succ
        havoc = _on(p, "sack") or _on(p, "interception") or _on(p, "fumble_forced") or _on(p, "tackled_for_loss") \
            or bool(p.get("pass_defense_1_player_id"))
        row["havoc"] += 1.0 if havoc else 0.0
        if dropback:
            big = 1.0 if yards >= 20 else 0.0
            row["pass_n"] += 1
            row["pass_epa"] += epa
            row["pass_success"] += succ
            row["pass_explosive"] += big
            pid = p.get("passer_player_id") or p.get("passer_id")
            if pid:
                q = qbs[key][pid]
                q[0] += 1
                q[1] += _f(p.get("qb_epa")) if _f(p.get("qb_epa")) is not None else epa
                q[2] = p.get("passer_player_name") or q[2]
        else:
            big = 1.0 if yards >= 10 else 0.0
            row["rush_n"] += 1
            row["rush_epa"] += epa
            row["rush_success"] += succ
            row["rush_stuffed"] += 1.0 if yards <= 0 else 0.0
        row["explosive"] += big

    for (gid, _), d in drives.items():
        row = g[(gid, d["team"])]
        row["drives"] += 1
        row["start_pos"] += 100 - d["start"]
        if d["best"] <= 40:
            row["trips"] += 1
            row["trip_points"] += DRIVE_POINTS.get(d["result"], 0)
    out = []
    for key, row in g.items():
        if key not in meta:
            continue
        season, week, opp, home = meta[key]
        qb = max(qbs[key].items(), key=lambda kv: kv[1][0]) if qbs[key] else None
        out.append({
            "season": season, "week": week, "game_id": key[0], "team": key[1], "opp": opp, "home": home,
            **{k: round(row.get(k, 0.0), 4) for k in FIELDS[6:25]},
            "points": 0.0,
            "qb_id": qb[0] if qb else "", "qb_name": qb[1][2] if qb else "",
            "qb_dropbacks": qb[1][0] if qb else 0, "qb_epa": round(qb[1][1], 4) if qb else 0.0,
        })
    return sorted(out, key=lambda r: (r["season"], r["week"], r["game_id"], r["team"]))


def attach_points(rows, games):
    """Fill `points` (and fix home/opp) from the schedule's final scores."""
    by_id = {g["id"]: g for g in games}
    keep = []
    for r in rows:
        g = by_id.get(r["game_id"])
        if not g or not g["completed"]:
            continue
        home = r["team"] == g["home"]
        r["points"] = g["home_score"] if home else g["away_score"]
        r["home"] = 0 if g["neutral"] else (1 if home else -1)
        r["opp"] = g["away"] if home else g["home"]
        keep.append(r)
    return keep
