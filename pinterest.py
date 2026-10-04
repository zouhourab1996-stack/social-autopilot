#!/usr/bin/env python3
"""
Pinterest autopilot — pins the next unposted entry from pins.json.

Secret (GitHub Actions):
  PINTEREST_ACCESS_TOKEN — an access token with scopes:
  boards:read, boards:write, pins:read, pins:write

Board handling: each pin names its target board; the script resolves the
board id by name and creates the board (PUBLIC) if it doesn't exist yet.

IMPORTANT — access tiers: pins created with a Trial-access app token are
reportedly visible only to the token's own account. After the first real
pin, check it in a logged-out browser; if private, the app needs Standard
access before the autopilot can drive public traffic.

Rate limits (trial): 300 write calls/day — the schedule posts ONE pin per run.
Access tokens expire every 30 days: regenerate and update the secret.
"""
import datetime
import json
import os
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PINS_PATH = os.path.join(HERE, "pins.json")
API = "https://api.pinterest.com/v5"

TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN", "").strip()
DRY_RUN = not TOKEN

TITLE_MAX = 100
DESC_MAX = 500


# ------------------------------------------------------------------ helpers
def call(path, payload=None):
    headers = {"Authorization": "Bearer " + TOKEN}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"Pinterest API {e.code} on {path}: {body}")


_board_cache = {}


def board_id_for(name):
    if name in _board_cache:
        return _board_cache[name]
    path = "/boards?page_size=100"
    while path:
        d = call(path)
        for b in d.get("items", []):
            _board_cache[b["name"]] = b["id"]
        cursor = d.get("bookmark")
        path = f"/boards?page_size=100&bookmark={cursor}" if cursor else None
    if name in _board_cache:
        return _board_cache[name]
    b = call("/boards", {"name": name,
                         "description": "Guides from prophetic.pw — grounded astrology, numerology and honest reviews.",
                         "privacy": "PUBLIC"})
    _board_cache[name] = b["id"]
    return b["id"]


def create_pin(entry):
    board_id = board_id_for(entry["board"])
    payload = {
        "board_id": board_id,
        "title": entry["title"][:TITLE_MAX],
        "description": entry["description"][:DESC_MAX],
        "link": entry["link"],
        "media_source": {"source_type": "image_url", "url": entry["image_url"]},
    }
    r = call("/pins", payload)
    return r.get("id"), board_id


# ------------------------------------------------------------------ main
def main():
    with open(PINS_PATH, encoding="utf-8") as f:
        pins = json.load(f)

    entry = next((p for p in pins if not p.get("posted")), None)
    if entry is None:
        print("Pin queue empty — nothing to pin. Refill pins.json.")
        return

    print(f"Next pin: {entry['title'][:70]}...")
    if DRY_RUN:
        ok_title = len(entry["title"]) <= TITLE_MAX
        ok_desc = len(entry["description"]) <= DESC_MAX
        print(f"DRY-RUN (no token). Would pin:\n"
              f"  board   : {entry['board']}\n"
              f"  title   : {entry['title']} ({len(entry['title'])} chars {'OK' if ok_title else 'TOO LONG'})\n"
              f"  desc    : {entry['description'][:70]}… ({len(entry['description'])} chars {'OK' if ok_desc else 'TOO LONG'})\n"
              f"  link    : {entry['link']}\n"
              f"  image   : {entry['image_url']}")
        return

    pin_id, board_id = create_pin(entry)
    entry["posted"] = pin_id
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry["pin_url"] = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else "?"
    with open(PINS_PATH, "w", encoding="utf-8") as f:
        json.dump(pins, f, ensure_ascii=False, indent=2)
    print(f"Pinned: {entry['pin_url']} (board {board_id})")
    print("NOTE: verify this pin in a LOGGED-OUT browser — trial-access pins may be private.")


if __name__ == "__main__":
    main()
