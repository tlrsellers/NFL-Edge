"""Build site/data/grades.json from this season's games only.

    python -m nfl_edge.build                 # current season from nflverse (no key needed)
    python -m nfl_edge.build --season 2026
    python -m nfl_edge.build --sample        # offline sample data
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import nflverse, stats
from .grades import grade_season

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "grades.json"


def current_season(now=None):
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--season", type=int, default=current_season())
    p.add_argument("--sample", action="store_true", help="use generated sample data")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    if args.sample:
        from .sample import sample_season
        rows, games = sample_season(args.season)
    else:
        games = nflverse.schedule()
        rows = stats.attach_points(stats.summarize(nflverse.pbp(args.season)), games)
    result = grade_season(rows, args.season, games)
    result["sample"] = bool(args.sample)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    top = ", ".join(f"{t['team']} {t['grades']['ovr']}" for t in result["teams"][:5])
    print(f"Graded {len(result['teams'])} teams through week {result['through_week']}. Top 5: {top}")


if __name__ == "__main__":
    main()
