# Weekly rule check

Every NFL game since 1999, settled against the closing line at -110 (52.4% breaks even). Nothing on the site changes automatically.

## Current rules

| Rule | Status | Since 1999 | Last 5 seasons | Last 3 seasons | Seasons above 52.4% | Live this season |
|---|---|---|---|---|---|---|
| LOCK: Under, outdoor wind 15+ mph | 🟡 YELLOW | 371-279 (57.1%) | 36-25 (59.0%) | 18-17 (51.4%) | 15 of 27 | 1-1 (50.0%) |
| Strong: playoff underdog the model likes | 🟡 YELLOW | 136-109 (55.5%) | 21-15 (58.3%) | 9-9 (50.0%) | 16 of 27 | no bets |
| Lean: Under, outdoor wind 10-14 mph | 🟡 YELLOW | 605-528 (53.4%) | 85-65 (56.7%) | 40-41 (49.4%) | 16 of 28 | 3-1 (75.0%) |

- **LOCK: Under, outdoor wind 15+ mph**: The last 3 seasons are under break-even. Worth watching, not yet a reason to change.
- **Strong: playoff underdog the model likes**: Profitable long-run, but the sample is small enough that it could be luck. Keep it at a lower tier and watch it.
- **Lean: Under, outdoor wind 10-14 mph**: Profitable long-run, but the sample is small enough that it could be luck. Keep it at a lower tier and watch it.

## New rule candidates

Tested 3,584 combinations. A candidate had to win 54%+ on 1999-2014, then 53.5%+ with z >= 2 on 2015-today (seasons it wasn't picked on), and beat break-even in 60%+ of seasons.

| Candidate | 1999-2014 | 2015-today | Seasons above 52.4% |
|---|---|---|---|
| Home team, non-division game, 32F or colder | 77-64 (54.6%) | 54-30 (64.3%) | 17 of 23 |
| Underdog, total 43-46.5, model total 3+ below line | 86-72 (54.4%) | 51-29 (63.7%) | 12 of 17 |
| Underdog, total 51+, model disagrees with spread 3+ | 47-36 (56.6%) | 88-57 (60.7%) | 13 of 18 |

These are leads, not new rules. With this many combinations tested, expect about one lucky survivor a year. Before adding one, ask whether there's a real reason it would work (like wind hurting passing), then add it to `nfl_edge/picks.py` in a pull request so the Backtest job can replay every season with it.
