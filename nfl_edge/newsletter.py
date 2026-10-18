"""Sends the picks newsletter when one is due. Run by the `Picks email` workflow; see digest.py.

  python -m nfl_edge.newsletter          send if a window is open and this week's email hasn't gone out
  python -m nfl_edge.newsletter --test   send the email for the current slate to EMAIL_USER only, now

The newsletter goes to everyone in EMAIL_TO through Gmail (mailer.py). If those
secrets aren't set, it falls back to a GitHub issue assigned to the repo owner,
which GitHub emails to the owner only. A failed send is not recorded, so the
next run in the window tries again; a sent one is recorded before anything else
can go wrong, so it never goes out twice.
"""

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import digest, mailer

DATA = Path(__file__).resolve().parent.parent / "site" / "data"
SENT = DATA / "emails.json"


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def post_issue(title, body):
    """Open a GitHub issue assigned to the repo owner; GitHub emails them. Returns its URL."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps({"title": title, "body": body, "assignees": [repo.split("/")[0]]}).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("html_url")


def run(now, slate, log, sent, deliver):
    """Returns (key, title) of the email sent, or None. `deliver(title, body)` raises if it fails."""
    if not slate or slate.get("sample"):
        print("No live slate; nothing to send.")
        return None
    due = digest.due(now, sent)
    if not due:
        print("No email due right now.")
        return None
    which, key = due
    if not digest.fresh(slate, now, which):
        print(f"Waiting for fresher lines (last scan {slate['updated']}); a later run in this window will send.")
        return None
    title, body = digest.compose(slate, now, which, log)
    deliver(title, body)
    return key, title


def deliver(title, body):
    if mailer.configured():
        n = mailer.send(title, body)
        print(f"Emailed {n} people.")
    else:
        print("EMAIL_* secrets not set; sending to the repo owner as a GitHub issue instead.")
        if not post_issue(title, body):
            raise RuntimeError("No way to send: set the EMAIL_* secrets (see mailer.py).")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--test", action="store_true", help="send the current picks to EMAIL_USER only, right now")
    args = p.parse_args(argv)
    now = datetime.now(timezone.utc)
    slate = _load(DATA / "slate.json", None)
    log = _load(DATA / "picks.json", {}).get("picks", {})

    if args.test:
        which = "sat" if now.astimezone(digest.CENTRAL).weekday() in (4, 5, 6) else "wed"
        title, body = digest.compose(slate, now, which, log)
        me = os.environ.get("EMAIL_USER")
        if not me or not mailer.configured():
            raise SystemExit("Set the EMAIL_USER, EMAIL_APP_PASSWORD and EMAIL_TO secrets first.")
        mailer.send(f"[Test] {title}", body, to=[me])
        print(f"Test email sent to {me} only: {title}")
        return

    record = _load(SENT, {"sent": []})
    result = run(now, slate, log, record["sent"], deliver)
    if result:
        key, title = result
        record["sent"] = (record["sent"] + [key])[-30:]
        record.setdefault("log", []).insert(0, {"key": key, "t": now.isoformat(timespec="minutes"), "title": title})
        record["log"] = record["log"][:30]
        SENT.write_text(json.dumps(record, indent=1) + "\n")
        print(f"Sent: {title}")


if __name__ == "__main__":
    main()
