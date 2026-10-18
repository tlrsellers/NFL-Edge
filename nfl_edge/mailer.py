"""Sends the picks email to a list of people (you and your friends) through Gmail.

Free: Gmail lets an account send mail from a program with an "app password".
Three repository secrets turn it on (Settings -> Secrets and variables -> Actions):

  EMAIL_USER          the Gmail address that sends it, e.g. you@gmail.com
  EMAIL_APP_PASSWORD  a 16-letter app password for that account (not your normal password)
  EMAIL_TO            everyone who should get it, separated by commas

The addresses live only in the secret, never in the code or on the website, and
every recipient is BCC'd so nobody sees the others' addresses. Without the
secrets nothing is sent and the GitHub issue email still reaches you.
"""

import html
import os
import re
import smtplib
from email.message import EmailMessage

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def recipients(value=None):
    value = os.environ.get("EMAIL_TO", "") if value is None else value
    return [a.strip() for a in re.split(r"[,;\s]+", value) if "@" in a]


def configured():
    return bool(os.environ.get("EMAIL_USER") and os.environ.get("EMAIL_APP_PASSWORD") and recipients())


def _inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)


def to_html(markdown):
    """Just enough Markdown for the picks email: headings, bullets, tables, bold, links."""
    out, rows, items = [], [], []

    def flush():
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()
        if rows:
            head, body = rows[0], [r for r in rows[2:]]
            cell = 'style="border:1px solid #ddd;padding:6px 8px;text-align:left"'
            out.append('<table style="border-collapse:collapse;font-size:14px">'
                       + "<tr>" + "".join(f"<th {cell}>{c}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td {cell}>{c}</td>" for c in r) + "</tr>" for r in body)
                       + "</table>")
            rows.clear()

    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("|"):
            rows.append([_inline(c.strip()) for c in s.strip("|").split("|")])
            continue
        if s.startswith("- "):
            items.append(_inline(s[2:]))
            continue
        flush()
        if s.startswith("### "):
            out.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            out.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s:
            out.append(f"<p>{_inline(s)}</p>")
    flush()
    return ('<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:680px;'
            'line-height:1.5;color:#111">' + "\n".join(out) + "</div>")


def send(subject, markdown, to=None, smtp=None):
    """Email everyone on the list. Returns how many addresses it went to (0 if not set up)."""
    to = recipients() if to is None else to
    user, password = os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_APP_PASSWORD")
    if not (user and password and to):
        return 0
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"], msg["Bcc"] = subject, f"NFL Edge <{user}>", user, ", ".join(to)
    msg.set_content(markdown)
    msg.add_alternative(to_html(markdown), subtype="html")
    server = smtp or smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
    with server:
        server.login(user, password)
        server.send_message(msg)
    return len(to)
