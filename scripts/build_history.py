"""Summarize past seasons' play-by-play into data/history/team_games.csv.gz.

The backtest replays past seasons week by week, using only each season's own
games (the same rule the live grades follow). Play-by-play is ~18 MB a season,
so the summary (one row per team per game) is built once and committed.

    python scripts/build_history.py 1999 2025              # downloads from nflverse
    python scripts/build_history.py 1999 2025 --pbp-dir DIR  # local play_by_play_<season>.csv.gz or pbp_<season>.csv.gz
"""
import argparse
import csv
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nfl_edge import nflverse, stats  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "history" / "team_games.csv.gz"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("first", type=int)
    p.add_argument("last", type=int)
    p.add_argument("--pbp-dir", type=Path)
    p.add_argument("--schedule")
    a = p.parse_args(argv)
    games = nflverse.schedule(a.schedule)
    rows = []
    for season in range(a.first, a.last + 1):
        path = None
        if a.pbp_dir:
            for name in (f"play_by_play_{season}.csv.gz", f"pbp_{season}.csv.gz"):
                if (a.pbp_dir / name).exists():
                    path = a.pbp_dir / name
        part = stats.attach_points(stats.summarize(nflverse.pbp(season, path)), games)
        print(f"{season}: {len(part)} team-games", file=sys.stderr)
        rows += part
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=stats.FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
