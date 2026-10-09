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
Access tokens expire every 30 days: refresh.yml rotates them monthly.

No duplicates: an entry is skipped (and marked "duplicate") when its link,
normalized (no query/fragment, no www, no trailing slash), is already pinned
by an earlier queue entry or listed in pinned_links.json (manual pins).

Trial access (API error code 29): Pinterest refuses to create production pins
until the app (client id 1619387) is upgraded to Standard access at
developers.pinterest.com. The run then ends with a warning, not a failure,
and the entry stays queued so it posts on the first run after the upgrade.
Set PINTEREST_STRICT=1 to make that case fail the job instead.
"""
import datetime
import json
import os
import urllib.request
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PINS_PATH = os.path.join(HERE, "pins.json")
PINNED_PATH = os.path.join(HERE, "pinned_links.json")
API = os.environ.get("PINTEREST_API_BASE", "https://api.pinterest.com/v5").rstrip("/")
STRICT = os.environ.get("PINTEREST_STRICT", "") == "1"

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
        raise PinterestError(e.code, path, body)


class PinterestError(Exception):
    def __init__(self, status, path, body):
        super().__init__(f"Pinterest API {status} on {path}: {body}")
        self.status, self.path, self.body = status, path, body
        try:
            self.code = json.loads(body).get("code")
        except Exception:
            self.code = None


def annotate(level, msg):
    """GitHub Actions annotation + job summary line."""
    print(f"::{level}::{msg}")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(f"- **{level.upper()}**: {msg}\n")


def norm(url):
    u = urllib.parse.urlsplit(url.strip())
    host = u.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host + u.path.rstrip("/")


def already_pinned(pins):
    seen = {norm(p["link"]) for p in pins if p.get("posted") and p.get("posted") != "duplicate"}
    if os.path.exists(PINNED_PATH):
        with open(PINNED_PATH, encoding="utf-8") as f:
            seen |= {norm(p["link"]) for p in json.load(f).get("pins", [])}
    return seen


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


def save(pins):
    with open(PINS_PATH, "w", encoding="utf-8") as f:
        json.dump(pins, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ------------------------------------------------------------------ main
def main():
    with open(PINS_PATH, encoding="utf-8") as f:
        pins = json.load(f)

    seen = already_pinned(pins)
    entry = None
    for p in pins:
        if p.get("posted"):
            continue
        if norm(p["link"]) in seen:
            p["posted"] = "duplicate"
            print(f"Skip (already pinned): {p['link']}")
            continue
        entry = p
        break
    if entry is None:
        save(pins)
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

    try:
        pin_id, board_id = create_pin(entry)
    except PinterestError as e:
        save(pins)  # keep any duplicate marks
        if e.code == 29:
            msg = ("Pinterest app (client id 1619387) only has TRIAL access, which cannot create "
                   "production pins. Upgrade it to Standard access at "
                   "https://developers.pinterest.com/apps/1619387/ - entry left queued: "
                   + entry["title"][:70])
            annotate("error" if STRICT else "warning", msg)
            raise SystemExit(1 if STRICT else 0)
        if e.status == 401:
            annotate("error", "PINTEREST_ACCESS_TOKEN is expired/invalid - run the "
                     "'Pinterest token refresh' workflow (needs PINTEREST_REFRESH_TOKEN, "
                     "PINTEREST_CLIENT_SECRET, GH_PAT secrets). " + str(e))
            raise SystemExit(1)
        annotate("error", str(e))
        raise SystemExit(1)
    entry["posted"] = pin_id
    entry["posted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry["pin_url"] = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else "?"
    save(pins)
    annotate("notice", f"Pinned '{entry['title'][:70]}': {entry['pin_url']}")
    print(f"Pinned: {entry['pin_url']} (board {board_id})")
    print("NOTE: verify this pin in a LOGGED-OUT browser — trial-access pins may be private.")


if __name__ == "__main__":
    main()
