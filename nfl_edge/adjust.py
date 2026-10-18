"""Opponent adjustment.

Each game gives one observation per offense: value = mean + offense_strength
+ defense_allowed + home_field. Solving that for every team at once (ridge
regression) means 400 yards against a bad defense counts for less than 400
against a good one. The ridge penalty pulls teams with few games toward
average, which keeps one blowout in week 2 from defining a team.
"""

import numpy as np


def opponent_adjust(rows, ridge=3.0):
    """rows: iterable of (offense, defense, value, weight, venue) where venue is
    +1 if the offense was at home, -1 if away, 0 if neutral.

    Returns (offense, defense, mean, home_field): offense[team] is how far above
    average the team's offense is; defense[team] is how far above average its
    defense lets opponents get (so lower is better).
    """
    rows = [r for r in rows if r[2] is not None and np.isfinite(r[2])]
    if not rows:
        return {}, {}, 0.0, 0.0
    teams = sorted({r[0] for r in rows} | {r[1] for r in rows})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    # columns: [mean, offense x n, defense x n, home_field]
    X = np.zeros((len(rows), 2 * n + 2))
    y = np.empty(len(rows))
    w = np.empty(len(rows))
    for k, (off, dfn, value, weight, venue) in enumerate(rows):
        X[k, 0] = 1.0
        X[k, 1 + idx[off]] = 1.0
        X[k, 1 + n + idx[dfn]] = 1.0
        X[k, -1] = venue
        y[k] = value
        w[k] = weight
    penalty = np.full(2 * n + 2, ridge)
    penalty[0] = penalty[-1] = 1e-6  # barely shrink the mean or home field (keeps the solve stable with no home games)
    XtW = X.T * w
    coef = np.linalg.solve(XtW @ X + np.diag(penalty), XtW @ y)
    offense = {t: float(coef[1 + i]) for t, i in idx.items()}
    defense = {t: float(coef[1 + n + i]) for t, i in idx.items()}
    return offense, defense, float(coef[0]), float(coef[-1])
