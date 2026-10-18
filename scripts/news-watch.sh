#!/usr/bin/env bash
# Run News watch on the latest data and push. If a lines scan pushed in the
# meantime, start again from its data rather than merging two slates.
set -euo pipefail
git config user.name "nfl-edge-bot"
git config user.email "nfl-edge-bot@users.noreply.github.com"
for attempt in 1 2 3; do
  git fetch -q origin main
  git reset -q --hard origin/main
  python -m nfl_edge.newswatch
  git add site/data
  if git diff --cached --quiet; then
    exit 0
  fi
  git commit -q -m "News watch"
  if git push origin HEAD:main; then
    if [ -n "${GH_TOKEN:-}" ]; then gh workflow run pages.yml --ref main || true; fi
    exit 0
  fi
  sleep $((attempt * 10))
done
exit 1
