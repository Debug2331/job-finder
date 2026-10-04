"""Free daily internship finder.
Pulls postings from public Greenhouse, Lever and Ashby job-board APIs,
filters them, saves new ones to postings.csv, and optionally emails you.
"""
import csv, json, os, smtplib, ssl, datetime as dt
from email.message import EmailMessage
from pathlib import Path
import requests

# ---------- EDIT THESE ----------
# Company "slugs" = the part of their job board URL.
# e.g. boards.greenhouse.io/stripe -> "stripe"
GREENHOUSE = ["stripe", "airbnb", "databricks", "figma", "robinhood"]
LEVER = ["spotify", "palantir"]
ASHBY = ["ramp", "notion"]

TITLE_MUST_CONTAIN = ["intern"]                     # any of these
KEYWORDS = ["software", "data", "machine learning", "engineer", "research"]  # any of these (leave [] to skip)
EXCLUDE = ["senior", "staff", "principal", "manager"]
LOCATIONS = []                                       # e.g. ["remote", "new york", "kansas"]; [] = anywhere
# --------------------------------

SEEN_FILE = Path("seen.json")
CSV_FILE = Path("postings.csv")
HEADERS = {"User-Agent": "personal-internship-finder/1.0"}


def get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  skipped {url}: {e}")
        return None


def fetch_greenhouse(slug):
    data = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    for j in (data or {}).get("jobs", []):
        yield dict(company=slug, title=j["title"], url=j["absolute_url"],
                   location=(j.get("location") or {}).get("name", ""))


def fetch_lever(slug):
    data = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    for j in data or []:
        yield dict(company=slug, title=j["text"], url=j["hostedUrl"],
                   location=(j.get("categories") or {}).get("location", "") or "")


def fetch_ashby(slug):
    data = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    for j in (data or {}).get("jobs", []):
        yield dict(company=slug, title=j["title"], url=j.get("jobUrl", ""),
                   location=j.get("location", "") or "")


def matches(job):
    t = job["title"].lower()
    if not any(w in t for w in TITLE_MUST_CONTAIN):
        return False
    if any(w in t for w in EXCLUDE):
        return False
    if KEYWORDS and not any(w in t for w in KEYWORDS):
        return False
    if LOCATIONS and not any(w in job["location"].lower() for w in LOCATIONS):
        return False
    return True


def send_email(new_jobs):
    user, pw, to = (os.getenv("EMAIL_USER"), os.getenv("EMAIL_APP_PASSWORD"),
                    os.getenv("EMAIL_TO"))
    if not (user and pw and to):
        print("Email not configured; skipping.")
        return
    lines = [f"{len(new_jobs)} new internship postings:\n"]
    for j in new_jobs:
        lines.append(f"- {j['company']} | {j['title']} | {j['location']}\n  {j['url']}")
    msg = EmailMessage()
    msg["Subject"] = f"{len(new_jobs)} new internships - {dt.date.today()}"
    msg["From"], msg["To"] = user, to
    msg.set_content("\n".join(lines))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)
    print("Email sent.")


def main():
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    found = []
    for fetcher, slugs in [(fetch_greenhouse, GREENHOUSE), (fetch_lever, LEVER), (fetch_ashby, ASHBY)]:
        for slug in slugs:
            print(f"Checking {fetcher.__name__[6:]}: {slug}")
            found += [j for j in fetcher(slug) if matches(j)]

    new = [j for j in found if j["url"] and j["url"] not in seen]
    print(f"{len(found)} matching, {len(new)} new.")

    if new:
        write_header = not CSV_FILE.exists()
        with CSV_FILE.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date_found", "company", "title", "location", "url"])
            if write_header:
                w.writeheader()
            for j in new:
                w.writerow({"date_found": dt.date.today().isoformat(), **j})
        send_email(new)

    seen.update(j["url"] for j in found)
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=1))


if __name__ == "__main__":
    main()
