#!/usr/bin/env bash
# Commit whatever changed under site/data (and data/), push, then redeploy the website.
# Retries if another update landed first.
set -euo pipefail
git config user.name "nfl-edge-bot"
git config user.email "nfl-edge-bot@users.noreply.github.com"
git add site/data data 2>/dev/null || git add site/data
if git diff --cached --quiet; then
  echo "No data changes."
  exit 0
fi
git commit -m "$1"
for attempt in 1 2 3; do
  if git pull --rebase origin "${GITHUB_REF_NAME:-main}" && git push; then
    # Pushes made by a workflow don't start other workflows, so ask for the deploy directly.
    if [ -n "${GH_TOKEN:-}" ]; then gh workflow run pages.yml --ref "${GITHUB_REF_NAME:-main}" || true; fi
    exit 0
  fi
  sleep $((attempt * 5))
done
exit 1
