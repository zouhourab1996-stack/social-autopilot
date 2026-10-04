#!/usr/bin/env python3
"""
Bluesky autopilot — posts the next unposted entry from queue.json.

Driven by GitHub Actions on a schedule; each run posts exactly one entry,
marks it posted (with its at:// URI) and commits the state back.

Secrets (GitHub Actions):
  BSKY_HANDLE        e.g. prophetic.bsky.social
  BSKY_APP_PASSWORD  an app password created at bsky.app/settings/app-passwords

Without the secrets the script runs in DRY-RUN mode: it prints what it
would post and exits 0 without touching the queue.
"""
import json
import os
import sys
import datetime
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "queue.json")
BSKY = "https://bsky.social"

HANDLE = os.environ.get("BSKY_HANDLE", "").strip()
PASSWORD = os.environ.get("BSKY_APP_PASSWORD", "").strip()
DRY_RUN = not (HANDLE and PASSWORD)


# ------------------------------------------------------------------ helpers
def api(path, payload=None, raw=None, content_type="application/json", token=None):
    """POST to the AT Protocol (Bluesky) API; GET when payload and raw are None."""
    url = BSKY + path
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if raw is not None:
        data = raw
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="GET" if data is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"API error {e.code} on {path}: {body}")


def link_facet(text, url):
    """Byte-offset facet so the URL is clickable in the post."""
    i = text.find(url)
    if i < 0:
        return None
    start = len(text[:i].encode("utf-8"))
    end = start + len(url.encode("utf-8"))
    return {"index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}


def upload_image(path, token):
    """Upload a local image and return a blob reference."""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) > 950_000:
        raise SystemExit(f"image too large for a blob ({len(raw)} bytes): {path}")
    r = api("/xrpc/com.atproto.repo.uploadBlob", raw=raw,
            content_type="image/jpeg", token=token)
    return r["blob"]


def post_entry(entry):
    session = api("/xrpc/com.atproto.server.createSession",
                  {"identifier": HANDLE, "password": PASSWORD})
    token = session["access_token"]
    did = session["did"]

    text = entry["text"]
    url = entry["url"]
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.datetime.now(datetime.timezone.utc)
                        .isoformat().replace("+00:00", "Z"),
        "langs": ["en"],
    }
    facet = link_facet(text, url)
    if facet:
        record["facets"] = [facet]
    if entry.get("image") and entry.get("image") != "":
        blob = upload_image(os.path.join(HERE, entry["image"]), token)
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [{"alt": entry.get("image_alt", ""), "image": blob}],
        }

    r = api("/xrpc/com.atproto.repo.createRecord",
            {"repo": did, "collection": "app.bsky.feed.post", "record": record},
            token=token)
    return r["uri"]


# ------------------------------------------------------------------ main
def main():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue = json.load(f)

    entry = next((e for e in queue if not e.get("posted")), None)
    if entry is None:
        print("Queue empty — nothing to post. Refill queue.json.")
        return

    print(f"Next post: {entry['text'][:80]}...")
    if DRY_RUN:
        print(f"DRY-RUN (no credentials). Would post:\n  text : {entry['text']}\n  url  : {entry['url']}\n  image: {entry.get('image', '-')}")
        return

    uri = post_entry(entry)
    entry["posted"] = uri
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    print(f"Posted: {uri}")


if __name__ == "__main__":
    main()
