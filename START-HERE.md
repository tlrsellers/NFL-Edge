# NFL Edge: setup, step by step

About 15 minutes. You need your GitHub account and a free The Odds API key. Everything else is free and needs no account.

## 1. Add your Odds API key

1. Get a free key at [the-odds-api.com](https://the-odds-api.com) (free plan: 500 credits a month). NFL Edge uses about 165 a month.
   - If your Fourth Down site uses the same key, the two together use about 345 of the 500. That fits, but a second free key under a different email keeps them separate.
2. In this repo: **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `ODDS_API_KEY`
   - Secret: your key
   - Click **Add secret**.

## 2. Let the bots save their work

**Settings → Actions → General → Workflow permissions** → choose **Read and write permissions** → **Save**.

## 3. Turn on the website

**Settings → Pages → Build and deployment → Source** → choose **GitHub Actions**. Nothing else on that page.

## 4. Run the first updates

In the **Actions** tab, run these in order. For each one, click its name on the left, then **Run workflow → Run workflow**, and wait for the green check (a minute or two):

1. **Update grades**
2. **Update lines**

Update lines starts **Deploy website** on its own. When that finishes, your site is at
`https://tlrsellers.github.io/NFL-Edge/` (the link also shows under **Settings → Pages**).

From then on everything runs by itself.

## 5. Optional: the picks email

Twice a week (Wednesday night and Saturday night) to you and anyone you add.

1. Turn on 2-Step Verification for your Gmail, then make an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
2. Add three repository secrets, the same way as step 1:
   - `EMAIL_USER`: your Gmail address
   - `EMAIL_APP_PASSWORD`: the 16-letter app password
   - `EMAIL_TO`: everyone's emails, separated by commas
3. To see it without bothering anyone: **Actions → Picks email → Run workflow**, leave **test** ticked. It goes to `EMAIL_USER` only.

Without these secrets the email goes to you as a GitHub issue instead.

## How to read the picks

- **LOCK**: an Under at an outdoor stadium with 15+ mph wind forecast within 36 hours of kickoff. 57% against the closing line since 1999. Most weeks have one or none; they usually show up Saturday night.
- **Strong**: a playoff underdog the model also likes (55.5%), or a 15+ mph wind Under that's still more than 36 hours away.
- **Lean**: an Under with a 10–14 mph wind forecast (53.8%).
- **Model lean**: where this season's numbers disagree with the market by 3+ points. Unproven: about 50% historically. Shown so you can see what the model thinks, not as a bet.

You need 52.4% to break even at -110. Before betting, check the injury report and the latest wind forecast, and confirm the line is still close.

## Changing things

- Schedules (times in UTC) are in `.github/workflows/`. `docs/bots-explained.md` explains each bot.
- Pick rules and the research behind them: `nfl_edge/picks.py` and `docs/research/`.
- Every Tuesday the **Backtest** job also runs a rule check: it rates each rule green, yellow or red and looks for new rules that held up on seasons they weren't chosen on. If anything changes, you get a GitHub issue (GitHub emails it to you). The latest report is always in `data/rule_check.md`.
- Want to act on it? Change the rule in `nfl_edge/picks.py`, open a pull request, and the **Backtest** workflow replays every season with your change. Check its run summary before merging.

Nothing here is a sure thing. Bet only what you can afford to lose. 21+. Gambling problem? Call 1-800-GAMBLER.
