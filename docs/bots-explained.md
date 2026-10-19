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
| Backtest + rule check | Tue 9 AM, and on pull requests that change the model | Replays every season since 1999 week by week with the live rules, then checks each rule's health and searches for new ones; opens a GitHub issue (which GitHub emails you) when a rule changes status or a new candidate appears |
| Line history | By hand | Every NFL line since 1999 against the final score |
| Tests | Every code change | Checks the math still works |
| Deploy website | After every data update | Publishes `site/` to GitHub Pages |

The `schedule` lines use **cron** in UTC. `0 14 * * *` means "minute 0, hour 14 UTC, every day", which is 9 AM Central until early November and 8 AM after. GitHub often starts scheduled jobs a few minutes to an hour late.

## The improvement loop

1. **Track.** Every pick the dashboard shows is saved before kickoff, then graded.
2. **Measure.** The Results tab shows the record and CLV by tier and by kind of pick.
3. **Watch.** Every Tuesday the rule check (`scripts/rule_check.py`) rates each rule:
   - 🟢 clearly above break-even
   - 🟡 weak evidence or a cold last 3 seasons
   - 🔴 losing: under break-even long-run, or under 50% over the last 5 seasons

   It also tries about 3,600 combinations of game features. A combination only counts as a candidate if it won on 1999–2014 **and** again on 2015–today, seasons it wasn't chosen on. When a rule changes color or a new candidate appears, it opens a GitHub issue, and GitHub emails you.
4. **Test.** To act on a flag or a candidate, change `nfl_edge/picks.py` in a pull request. The Backtest job replays every season with the change.
5. **Decide.** Merge only if it holds up across many seasons, and if there's a real reason it should work. Nothing changes on the site by itself.

The danger in sports models is **overfitting**: tuning until the model explains the past perfectly, which makes it worse at the future. One change at a time, judged over many seasons, is how to avoid it.
