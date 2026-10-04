#!/usr/bin/env python3
"""
Facebook Pages autopilot — posts the next unposted entry from fb.json to our Page.

Secrets (GitHub Actions):
  FB_PAGE_ID      the numeric Page id (resolved at setup)
  FB_PAGE_TOKEN   never-expiring Page access token

Feed posts carry the link; Facebook auto-generates the share card
(og:title/description/image) from the target page, like Bluesky link cards.
"""
import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "fb.json")
GRAPH = "https://graph.facebook.com/v23.0"

PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()
DRY_RUN = not (PAGE_ID and PAGE_TOKEN)


def call(path, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(GRAPH + path, data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Graph API {e.code} on {path}: {e.read().decode()[:300]}")


def main():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue = json.load(f)

    entry = next((e for e in queue if not e.get("posted")), None)
    if entry is None:
        print("Facebook queue empty — refill fb.json.")
        return

    print(f"Next post: {entry['message'][:75]}...")
    if DRY_RUN:
        print(f"DRY-RUN (no token). Would post to page {PAGE_ID or '(unset)'}:\n"
              f"  message: {entry['message']}\n"
              f"  link   : {entry['link']}")
        return

    res = call(f"/{PAGE_ID}/feed/", {"message": entry["message"],
                                     "link": entry["link"],
                                     "access_token": PAGE_TOKEN})
    pid = res.get("id", "")
    entry["posted"] = pid
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    parts = pid.split("_")
    print(f"Posted: https://www.facebook.com/{parts[0]}/posts/{parts[-1]}")


if __name__ == "__main__":
    main()
