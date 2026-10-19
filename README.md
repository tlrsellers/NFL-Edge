# NFL Edge

NFL team grades, projections and picks, rebuilt from the college-football dashboard *Gridiron Edge* and re-tuned for the NFL on every game with a public betting line since 1999. Everything runs on free services inside GitHub: no computer at home, and no AI.

**Setting it up? Start with [START-HERE.md](START-HERE.md).**

## What's here

- **Team grades** (`nfl_edge/grades.py`): all 32 teams 0–10 on offense, pass O, rush O, QB, defense, pass D, rush D, special teams, pace and overall, **from this season's games only**. 5.0 is NFL average and each point is half a standard deviation. Built from nflverse play-by-play: EPA, success and explosive-play rates for passes and runs, havoc, points per trip inside the 40, special-teams EPA and field position. Every metric is adjusted for opponent and home field, and garbage time is excluded. The QB grade uses the team's most recent starter and flags a QB change.
- **Projections** (`projections.py`): a score for any matchup, averaging opponent-adjusted scoring with adjusted EPA per play times expected plays.
- **Lines and picks** (`odds.py`, `weather.py`, `picks.py`, `slate.py`): DraftKings, FanDuel and Bovada spreads and totals from The Odds API, plus the National Weather Service wind forecast for every outdoor game.

  | Tier | Rule | Since 1999 vs the closing line |
  |---|---|---|
  | LOCK | Under, outdoor stadium, forecast wind 15+ mph, forecast read within 36 hours of kickoff | 384-290 (57.0%), profitable in 17 of 27 seasons |
  | Strong | Playoff underdog the model also likes (or a 15+ mph wind Under more than 36 hours out) | 136-109 (55.5%) |
  | Lean | Under, outdoor stadium, forecast wind 10–14 mph | 650-558 (53.8%), profitable in 16 of 28 seasons |
  | Model lean | The model disagrees with the best line by 3+ points | about 50%: unproven, shown for information |

  Why it's built this way: in college football, your friend's model beat the opening line when it disagreed by 8+ points. In the NFL it doesn't. Replaying 1999–2026 week by week, the model (built only from each season's earlier games) missed final margins by 10.7 points against the closing line's 10.3, and its biggest disagreements didn't cover more often. Only about 5% of its edge is real, against ~30% in college. So the top tiers come only from patterns that beat the NFL closing line for decades. The full study is in [docs/research/](docs/research/).
- **Why each pick** (`explain.py`): opening a game shows the pattern and its record, where the model's number comes from (each team's offense, defense and home field, in points), the checks a pick passed, and risks such as a QB change or a forecast that's still days away.
- **Pick tracking** (`track.py`): every model lean or better is saved before kickoff in `site/data/picks.json`, graded after the game and scored for closing line value (CLV). The Results tab shows the record by tier.
- **News check** (`news.py`): reads recent Google News headlines for each team with a pick and flags quarterback and injury headlines on the game. Headlines never change a tier.
- **Weekly grading** (`review.py`): Tuesday mornings every pick is graded, archived by week in `site/data/archive/` and broken down by kind of pick in `site/data/insights.json`.
- **Newsletter** (`newsletter.py`, `digest.py`, `mailer.py`): optional, two emails a week (Wednesday and Saturday night) through Gmail.
- **Dashboard** (`site/`): This Week, Schedule, Matchup, Lines, Results, Team Grades and Compare. Light and dark themes, works on phones, every view has a shareable link. Hosted free on GitHub Pages.
- **Research** (`scripts/`, research only, never on the dashboard): `line_history.py` studies every NFL line since 1999 against the final score; `backtest.py` replays every season week by week with the live pick rules. `data/history/team_games.csv.gz` is a compact summary of 1999–2025 play-by-play so the backtest doesn't download 450 MB each time.

## The bots

| Job | When (Central) | What it does | Cost |
|---|---|---|---|
| Update lines | 9 AM and 6 PM daily, plus before Thursday, Sunday and Monday games | Lines, wind forecasts, news, picks | ~165 Odds API credits a month |
| Update grades | Monday, Tuesday and Friday 6 AM | Rebuilds grades from nflverse | free |
| News watch | Every 2 hours | Re-reads headlines for games with picks | free |
| Picks email | Wednesday and Saturday night | Optional newsletter | free |
| Weekly grading | Tuesday 8 AM | Grades and archives picks | free |
| Backtest + rule check | Tuesday 9 AM | Replays 1999–today; flags any rule that's slipping and searches for new rules that hold up on unseen seasons; opens a GitHub issue if anything changed | free |
| Deploy website | After every data update | Publishes `site/` to GitHub Pages | free |

Public repositories get unlimited free GitHub Actions minutes.

## Run locally

```sh
pip install -r requirements.txt pytest
python -m pytest -q
python -m nfl_edge.build                  # real grades from nflverse (no key)
python -m nfl_edge.build --sample         # or offline sample data
python -m nfl_edge.slate --sample         # sample lines and picks, no key
ODDS_API_KEY=... python -m nfl_edge.slate # real lines
python -m http.server -d site 8000        # open http://localhost:8000
```

Nothing here is a sure thing. Bet only what you can afford to lose. 21+. Gambling problem? Call 1-800-GAMBLER.
