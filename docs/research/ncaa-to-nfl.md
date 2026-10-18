# From college to the NFL: what changed and why (October 2026)

NFL Edge started from Gridiron Edge, a college football dashboard whose picks come from the gap between its model and the betting line (Lean 4+ points, Strong 8+, LOCK 12+). Before copying those rules we tested them on every NFL game with a public line in nflverse: 7,355 games from 1999 to week 6 of 2026. Everything here can be re-run with `scripts/line_history.py` and `scripts/backtest.py`.

## 1. NFL lines are much harder to beat

- The final margin lands **10.3 points** from the closing spread on average (SD 13.2). The total misses by 10.6 (SD 13.4).
- Simple angles don't work. Home teams covered 49.0%, favorites 48.7%, underdogs 51.3%, all below the 52.4% break-even at -110 (`line-history.md`).
- **Key numbers matter more than in college.** 15.1% of NFL games are decided by exactly 3 points and 9.0% by 7 (college: about 9.6% and 7.3%). A half point around 3 or 7 is worth far more in the NFL.
- **Home field has shrunk** from about 2.5 points before 2015 to about 1.6 in the lines now.

## 2. The college model's edge didn't carry over

We rebuilt the grades for the NFL (same idea: opponent-adjusted EPA, success and explosive rates per game, only this season's games, garbage time removed) and replayed every season from 1999 week by week. Each week's grades used only that season's earlier games, exactly what the live site would have known.

| | Model | Closing line |
|---|---|---|
| Average miss on final margin | 10.7 | 10.3 |
| Average miss on total | 11.0 | 10.6 |

| Model edge vs closing spread | Record | Win % |
|---|---|---|
| 0–2 points | 1348-1382 | 49.4% |
| 2–4 points | 1076-982 | 52.3% |
| 4–6 points | 566-571 | 49.8% |
| 6–8 points | 262-242 | 52.0% |
| 8–11 points | 104-101 | 50.7% |
| 11+ points | 37-43 | 46.3% |

Bigger disagreements did **not** cover more often, and the biggest did worst: in the NFL a big gap usually means the market knows something (an injury, a QB change) that this season's stats can't. Fitting the cover rate to the edge gives a weight of **0.05**: only about 5% of the model's disagreement is real, against 0.2–0.35 in college. A 10-point NFL edge works out to about a 51.5% chance to cover, below break-even.

We tried other settings (more or less shrinkage toward average, more weight on recent weeks, scoring vs efficiency blends). The best got within 0.45 points of the line's accuracy but never beat it, and none produced edges that won. We kept the most accurate settings (ridge 6, no recency weighting, a 50/50 scoring and efficiency blend).

Two caveats. nflverse only has closing lines; Gridiron Edge's college edge was measured against opening lines, which are softer. NFL Edge records the first line it sees each week, so in a season or two its own CLV numbers will show whether the model does better against NFL openers. And the model only uses this season's games, by design.

## 3. What did beat the NFL closing line

A pattern counts only if it beat 52.4% overall **and** in most seasons, not just in total.

| Pattern | Record | Win % | Seasons above break-even | Used as |
|---|---|---|---|---|
| Under, outdoor, wind 15+ mph | 384-290 | 57.0% | 17 of 27 | LOCK |
| Playoff underdog the model also likes | 136-109 | 55.5% | (small sample) | Strong |
| Under, outdoor, wind 10–14 mph | 650-558 | 53.8% | 16 of 28 | Lean |
| Underdogs, weeks 1–4 | 890-786 | 53.1% | 16 of 28 | not used: too inconsistent |
| Underdogs getting 8–10.5 | 457-403 | 53.1% | 15 of 27 | not used: likely noise |

Wind is the one that holds up statistically (about 2.4 standard errors above break-even over 674 games) and has a physical reason: it hurts passing and kicking more than the market allows for. The model doesn't help it. Wind Unders won 57.4% when the model disagreed and 56.1% when it agreed, so the wind alone decides those picks.

The historical records use the wind measured at kickoff. The live site uses the National Weather Service forecast, which is less exact. So a LOCK needs a forecast read within 36 hours of kickoff, and the Saturday night scan is the one that usually finds them.

## 4. Other changes from the college version

- **Quarterbacks.** The NFL grade uses the most recent starter and warns when he isn't the season's main passer (it caught Baltimore starting Tyler Huntley for Lamar Jackson in week 5).
- **No conference or FCS logic.** Divisions replace conferences; every team plays every week.
- **Schedules** follow the NFL week: Thursday, Sunday and Monday games; grades rebuild Monday, Tuesday and Friday; the email goes out Wednesday and Saturday night.
- **Sportsbooks**: DraftKings, FanDuel and Bovada (the same Odds API credits as two books).
- **No AI review.** Changes are tested by opening a pull request; the Backtest workflow replays every season with the change.
- **Past seasons stay off the dashboard.** They are only used to set the rules above.
