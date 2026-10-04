#!/usr/bin/env python3
"""
Bluesky autopilot — posts the next unposted entry from queue.json.

Each run posts exactly one entry, marks it posted (with its at:// URI) and
commits the state back (done by the GitHub Actions workflow).

Secrets (GitHub Actions):
  BSKY_HANDLE        e.g. prophetic.bsky.social
  BSKY_APP_PASSWORD  an app password created at bsky.app/settings/app-passwords

Post format: every post carries a clickable link — as an external link card
(title + description + og:image thumbnail scraped from the target page) when
the page has Open Graph tags, or as a plain URL appended to the text when it
doesn't. Without the secrets the script runs in DRY-RUN mode.
"""
import datetime
import html as html_mod
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "queue.json")
BSKY = "https://bsky.social"
UA = "Mozilla/5.0 (compatible; social-autopilot/1.0; +https://prophetic.pw)"

HANDLE = os.environ.get("BSKY_HANDLE", "").strip()
PASSWORD = os.environ.get("BSKY_APP_PASSWORD", "").strip()
DRY_RUN = not (HANDLE and PASSWORD)
LIMIT = 290  # safety margin under Bluesky's 300-grapheme post cap


# ------------------------------------------------------------------ helpers
def api(path, payload=None, raw=None, content_type="application/json", token=None):
    """POST to the AT Protocol (Bluesky) API."""
    url = BSKY + path
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if raw is not None:
        data = raw
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"API error {e.code} on {path}: {body}")


def link_facet(text, url):
    """Byte-offset facet so the URL is clickable wherever it appears in text."""
    i = text.find(url)
    if i < 0:
        return None
    start = len(text[:i].encode("utf-8"))
    end = start + len(url.encode("utf-8"))
    return {"index": {"byteStart": start, "byteEnd": end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}


def fetch_meta(url):
    """og:title / og:description / og:image from the target page."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        page = urllib.request.urlopen(req, timeout=12).read(500_000).decode("utf-8", "replace")
    except Exception:
        return "", "", ""
    def og(prop):
        m = re.search(r'<meta[^>]+(?:property|name)=["\']' + prop + r'["\'][^>]+content=["\']([^"\']*)["\']', page, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']' + prop + r'["\']', page, re.I)
        return html_mod.unescape(m.group(1)).strip() if m else ""
    return og("og:title"), og("og:description"), og("og:image")


def download(url):
    """Download an og:image; returns (bytes, content_type) or (None, None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            if ct not in ("image/jpeg", "image/png", "image/webp"):
                ct = "image/jpeg"
            return r.read(950_000), ct
    except Exception:
        return None, None


def with_url(text, url):
    """Append the URL to the text, trimming the text if needed to fit LIMIT."""
    if len(text) + len(url) + 1 <= LIMIT:
        return text + "\n" + url
    room = LIMIT - len(url) - 2
    cut = text[:room].rsplit(" ", 1)[0].rstrip(" ,:;—-")
    return cut + "…\n" + url


def build_post(entry, token):
    """Assemble the post record: link card when possible, URL-in-text fallback."""
    text, url = entry["text"], entry["url"]
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.datetime.now(datetime.timezone.utc)
                        .isoformat().replace("+00:00", "Z"),
        "langs": ["en"],
    }

    embed = None
    title, desc, image = fetch_meta(url)
    if title:
        external = {"uri": url, "title": title[:256]}
        if desc:
            external["description"] = desc[:256]
        if image:
            raw, ct = download(image)
            if raw:
                try:
                    external["thumb"] = api("/xrpc/com.atproto.repo.uploadBlob",
                                            raw=raw, content_type=ct, token=token)["blob"]
                except SystemExit:
                    pass  # post without a thumbnail rather than not posting
        embed = {"$type": "app.bsky.embed.external", "external": external}

    if embed is None:
        text = with_url(text, url)
        record["text"] = text

    facet = link_facet(text, url)
    if facet:
        record["facets"] = [facet]
    if embed:
        record["embed"] = embed
    return record


def post_entry(entry):
    session = api("/xrpc/com.atproto.server.createSession",
                  {"identifier": HANDLE, "password": PASSWORD})
    token = session["accessJwt"]
    did = session["did"]

    record = build_post(entry, token)
    r = api("/xrpc/com.atproto.repo.createRecord",
            {"repo": did, "collection": "app.bsky.feed.post", "record": record},
            token=token)
    return r["uri"], record


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
        title, desc, image = fetch_meta(entry["url"])
        print(f"DRY-RUN (no credentials). Would post:\n"
              f"  text   : {entry['text']}\n"
              f"  url    : {entry['url']}\n"
              f"  card   : {'YES — ' + title[:60] if title else 'no (URL appended to text)'}\n"
              f"  og:img : {image or '-'}")
        return

    uri, record = post_entry(entry)
    entry["posted"] = uri
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    embed_type = (record.get("embed") or {}).get("$type", "text+url")
    print(f"Posted: {uri} (embed: {embed_type})")


if __name__ == "__main__":
    main()
