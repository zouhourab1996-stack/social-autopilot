#!/usr/bin/env python3
"""
devto_publisher.py — dev.to channel publisher (fully automated, open API).

dev.to's API is open and current (Forem): POST /api/articles with the
`api-key` header; body_markdown + tags (max 4) + canonical_url + main_image.
First article goes out as a draft, gets verified, then --flip publishes it.

Queue: devto_queue.json (markdown pre-built from prophetic.pw reviews.ts).

Usage:
  python3 devto_publisher.py --list
  python3 devto_publisher.py --dry-run --entry 1
  DEVTO_TOKEN=... python3 devto_publisher.py --check
  DEVTO_TOKEN=... python3 devto_publisher.py --publish --entry 1 [--status draft|public]
  DEVTO_TOKEN=... python3 devto_publisher.py --flip --entry 1   # draft -> public

Protocol (README): first publish as DRAFT, verify rendering on dev.to,
then flip. Max 2/week. canonical_url is ALWAYS the source page.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://dev.to/api"
HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "devto_queue.json")


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(q):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api_call(path, token, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(API + path, data=data,
                  method=method or ("POST" if data else "GET"),
                  headers={"api-key": token,
                           "Content-Type": "application/json",
                           "Accept": "application/vnd.forem.api-v1+json",
                           "User-Agent": "Mozilla/5.0 (compatible; autopilot/1.0)"})
    try:
        with urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body.strip() else {})
    except HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}


def article_payload(entry, published):
    art = {
        "title": entry["title"],
        "published": published,
        "body_markdown": entry["markdown"],
        "tags": entry["tags"][:4],
        "canonical_url": entry["canonical_url"],
    }
    if entry.get("main_image"):
        art["main_image"] = entry["main_image"]
    if entry.get("series"):
        art["series"] = entry["series"]
    return {"article": art}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--flip", action="store_true", help="flip an existing draft to public")
    ap.add_argument("--entry", type=int, help="entry id (default: first pending)")
    ap.add_argument("--status", choices=["draft", "public"], default="draft")
    keyfile = os.path.join(HERE, ".devto_key")
    default_token = os.environ.get("DEVTO_TOKEN")
    if not default_token and os.path.exists(keyfile):
        with open(keyfile) as f:
            default_token = f.read().strip()
    ap.add_argument("--token", default=default_token)
    a = ap.parse_args()

    q = load_queue()
    entries = q["entries"]

    if a.list:
        for e in entries:
            mark = {"pending": "[ ]", "draft": "[~]", "published": "[x]", "skipped": "[-]"}.get(e["status"], "[?]")
            print("%s #%d %-9s %-14s %s" % (mark, e["id"], e["status"], e["slug"], e["title"][:70]))
        print("pending: %d / %d" % (sum(1 for e in entries if e["status"] == "pending"), len(entries)))
        return 0

    if a.check:
        if not a.token:
            print("ERROR: no token (DEVTO_TOKEN env or --token)"); return 2
        code, body = api_call("/users/me", a.token)
        print("HTTP", code)
        if code == 200:
            print("id       :", body.get("id"))
            print("username :", body.get("username"))
            print("name     :", body.get("name"))
            print("joined   :", body.get("joined_at"))
            return 0
        print(json.dumps(body, indent=2)[:500])
        return 1

    # pick entry
    if a.entry:
        ent = next((e for e in entries if e["id"] == a.entry), None)
    else:
        ent = next((e for e in entries if e["status"] == "pending"), None)
    if not ent:
        print("ERROR: entry not found or nothing pending"); return 2

    if a.dry_run:
        print("entry #%d (%s) -> %s" % (ent["id"], ent["slug"], ent["canonical_url"]))
        print("title    : %s" % ent["title"])
        print("tags     : %s | series: %s" % (", ".join(ent["tags"][:4]), ent.get("series")))
        print("main_img : %s" % ent.get("main_image"))
        print("markdown : %d chars, %d lines" % (len(ent["markdown"]), ent["markdown"].count("\n") + 1))
        print("--- first 40 lines ---")
        print("\n".join(ent["markdown"].splitlines()[:40]))
        with open("/tmp/devto_preview.md", "w", encoding="utf-8") as f:
            f.write(ent["markdown"])
        print("--- full markdown: /tmp/devto_preview.md ---")
        return 0

    if a.publish:
        if not a.token:
            print("ERROR: no token (DEVTO_TOKEN env or --token)"); return 2
        code, me = api_call("/users/me", a.token)
        if code != 200:
            print("ERROR: token check failed:", code, json.dumps(me)[:300]); return 1
        print("authenticated as @%s (%s)" % (me.get("username"), me.get("id")))
        published = (a.status == "public")
        code, body = api_call("/articles", a.token, article_payload(ent, published))
        print("publish (%s) -> HTTP %s" % (a.status, code))
        if code in (200, 201):
            print("DEVTO URL:", body.get("url"))
            print("ID       :", body.get("id"))
            ent["status"] = a.status
            ent["devto_id"] = body.get("id")
            ent["devto_url"] = body.get("url")
            ent["published_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            q["updated"] = ent["published_at"]
            save_queue(q)
            print("queue updated: entry #%d -> %s" % (ent["id"], a.status))
            return 0
        print(json.dumps(body, indent=2)[:600])
        return 1

    if a.flip:
        if not a.token:
            print("ERROR: no token (DEVTO_TOKEN env or --token)"); return 2
        if not ent.get("devto_id"):
            print("ERROR: entry has no devto_id — publish it first"); return 2
        code, body = api_call("/articles/%s" % ent["devto_id"], a.token,
                              article_payload(ent, True), method="PUT")
        print("flip -> HTTP %s" % code)
        if code in (200, 201):
            print("DEVTO URL:", body.get("url"))
            ent["status"] = "public"
            if body.get("url"):
                ent["devto_url"] = body["url"]  # final slug replaces draft temp-slug
            ent["flipped_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            q["updated"] = ent["flipped_at"]
            save_queue(q)
            print("queue updated: entry #%d -> public" % ent["id"])
            return 0
        print(json.dumps(body, indent=2)[:600])
        return 1

    print("nothing to do: use --list / --dry-run / --check / --publish / --flip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
