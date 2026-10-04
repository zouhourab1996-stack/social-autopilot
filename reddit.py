#!/usr/bin/env python3
"""
Reddit autopilot — posts the next unposted entry from reddit.json.

Strategy: our own subreddit (r/PropheticGuides by default). If the sub
doesn't exist, the script creates it (requires the account to be ~30 days
old). If creation fails, it falls back to posting on the account's profile
(u/<username>) — public and Google-indexable — so posting never blocks.

Secrets (GitHub Actions):
  REDDIT_CLIENT_ID      from reddit.com/prefs/apps (script app)
  REDDIT_CLIENT_SECRET  the app secret
  REDDIT_USERNAME       the account to post as (2FA must be off)
  REDDIT_PASSWORD       the account password
  SUBREDDIT_NAME        optional override (default: PropheticGuides)

Rate limits: script apps allow 60 requests/min — this run does ~4.
"""
import datetime
import json
import os
import urllib.request
import urllib.parse
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "reddit.json")

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
USERNAME = os.environ.get("REDDIT_USERNAME", "").strip()
PASSWORD = os.environ.get("REDDIT_PASSWORD", "").strip()
OUR_SUB = os.environ.get("SUBREDDIT_NAME", "PropheticGuides").strip()

DRY_RUN = not (CLIENT_ID and CLIENT_SECRET and USERNAME and PASSWORD)

UA = f"script:prophetic-publisher:v1.0 (by /u/{USERNAME or 'setup'})"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH = "https://oauth.reddit.com"


# ------------------------------------------------------------------ helpers
def http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode("utf-8", "replace")


def get_token():
    basic = __import__("base64").b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "password",
                                   "username": USERNAME, "password": PASSWORD}).encode()
    status, body = http(TOKEN_URL, data=data, headers={
        "Authorization": "Basic " + basic,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": UA})
    tok = json.loads(body)
    if "access_token" not in tok:
        raise SystemExit(f"Reddit auth failed ({status}): {str(tok)[:200]}")
    return tok["access_token"]


def api(token, path, params=None, post=False):
    headers = {"Authorization": "Bearer " + token, "User-Agent": UA}
    url = OAUTH + path
    data = None
    if post:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(params or {}).encode()
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        status, body = http(url, data=data, headers=headers)
        return status, json.loads(body or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")


def ensure_subreddit(token):
    """Return (sr_name, note): the subreddit if usable/created, else the profile."""
    status, about = api(token, f"/r/{OUR_SUB}/about.json")
    if status == 200 and isinstance(about.get("data"), dict):
        return OUR_SUB, "existing subreddit"
    # try to create it
    status, res = api(token, "/api/site_admin", post=True, params={
        "api_type": "json", "name": OUR_SUB, "title": "Prophetic Guides",
        "public_description": "Grounded astrology, numerology, health math and honest reviews from prophetic.pw and our network. No crystal-shop nonsense.",
        "type": "public", "over_18": "false"})
    status2, about2 = api(token, f"/r/{OUR_SUB}/about.json")
    if status2 == 200 and isinstance(about2.get("data"), dict):
        return OUR_SUB, "subreddit created this run"
    # fall back to profile posting
    return f"u_{USERNAME}", (f"subreddit creation unavailable "
                             f"({json.dumps(res)[:120]}); posting to profile")


def submit_link(token, sr, title, url):
    status, res = api(token, "/api/submit", post=True, params={
        "api_type": "json", "sr": sr, "kind": "link", "title": title, "url": url})
    j = res.get("json", {})
    if j.get("errors"):
        raise SystemExit(f"Reddit submit errors: {j['errors']}")
    return j.get("data", {}).get("url") or f"https://www.reddit.com/r/{sr}/new/"


# ------------------------------------------------------------------ main
def main():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue = json.load(f)

    entry = next((e for e in queue if not e.get("posted")), None)
    if entry is None:
        print("Reddit queue empty — nothing to post. Refill reddit.json.")
        return

    print(f"Next post: {entry['title'][:75]}...")
    if DRY_RUN:
        print(f"DRY-RUN (no credentials). Would post:\n"
              f"  sub (target) : r/{OUR_SUB} (auto-create) or u/<account> fallback\n"
              f"  title        : {entry['title']}\n"
              f"  url          : {entry['url']}")
        return

    token = get_token()
    sr, note = ensure_subreddit(token)
    print(f"target: {sr} ({note})")
    permalink = submit_link(token, sr, entry["title"], entry["url"])
    entry["posted"] = permalink
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry["sr"] = sr
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    print(f"Posted: {permalink}")


if __name__ == "__main__":
    main()
