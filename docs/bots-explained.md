# How the bots behind NFL Edge work

## Bot, crawler, API: what's the difference?

- A **bot** is any program that does a job on its own, on a schedule. NFL Edge has several, all run by **GitHub Actions**, GitHub's free robot. Each job is a recipe in `.github/workflows/`: "at this time, start a fresh computer, download the code, run these commands."
- An **API** is a website built for programs instead of people. NFL Edge gets lines from The Odds API, weather from the National Weather Service API, and stats and schedules from nflverse's free data files. APIs are faster, more reliable and more polite than scraping, and sportsbooks forbid scraping in their terms.
- A **crawler** reads pages meant for people. NFL Edge has one small one: `nfl_edge/news.py` reads Google News' public RSS feed (a list of headlines made for programs) for each team with a pick. It never changes a pick; it just shows the headlines.
- There is no AI anywhere in NFL Edge. Every bot follows fixed steps.

## The bots

| Bot | When (Central) | What it does |
|---|---|---|
| Update grades | Mon, Tue, Fri 6 AM | Downloads this season's play-by-play from nflverse and rebuilds the 0-10 grades |
| Update lines | 9 AM and 6 PM daily, plus before Thursday, Sunday and Monday games | Pulls DraftKings, FanDuel and Bovada lines, reads the wind forecast for outdoor games, checks the news, and scores and explains every pick |
| News watch | Every 2 hours | Re-reads headlines for upcoming games with a pick |
| Picks email | Wed and Sat night | Optional email with the LOCK, Strong and Lean plays and last week's record |
| Weekly grading | Tue 8 AM | Grades and archives every pick by week, and works out which kinds of picks are paying this season |
| Backtest | Tue 9 AM, and on pull requests that change the model | Replays every season since 2002 week by week with the live rules; results in the run summary |
| Line history | By hand | Every NFL line since 1999 against the final score |
| Tests | Every code change | Checks the math still works |
| Deploy website | After every data update | Publishes `site/` to GitHub Pages |

The `schedule` lines use **cron** in UTC. `0 14 * * *` means "minute 0, hour 14 UTC, every day", which is 9 AM Central until early November and 8 AM after. GitHub often starts scheduled jobs a few minutes to an hour late.

## The improvement loop

1. **Track.** Every pick the dashboard shows is saved before kickoff, then graded.
2. **Measure.** The Results tab shows the record and CLV by tier and by kind of pick.
3. **Test.** To try an idea, change `nfl_edge/picks.py` (or the grades) in a pull request. The Backtest job replays every season with the change.
4. **Decide.** Merge only if it holds up across many seasons, not just this one.

The danger in sports models is **overfitting**: tuning until the model explains the past perfectly, which makes it worse at the future. One change at a time, judged over many seasons, is how to avoid it.
