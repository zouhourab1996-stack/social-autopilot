#!/usr/bin/env python3
"""
medium_publisher.py — Medium channel publisher for the network.

Medium's API server is ALIVE (verified 2026-10-07: 401 "access token required").
Publishing needs a self-issued integration token from:
    https://medium.com/me/settings  ->  "Integration tokens" section
(OAuth app registrations are closed since 2023; self-issued tokens are the
remaining sanctioned path. If the section is gone from the account, the
fallback is medium.com/p/import — see MEDIUM-IMPORT-QUEUE.md.)

Queue: medium_queue.json (same folder). Entry: {id, url, tags, status}.

Usage:
  python3 medium_publisher.py --list
  python3 medium_publisher.py --dry-run --entry 1        # build payload, no send
  MEDIUM_TOKEN=... python3 medium_publisher.py --check   # verify token -> userId
  MEDIUM_TOKEN=... python3 medium_publisher.py --publish --entry 1 [--status draft|public]

Standing protocol (README): max 2 posts/week, value articles only,
canonicalUrl ALWAYS the source page, zero bulk follows/engagement.
"""
import argparse
import html as html_mod
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

API_BASE = "https://api.medium.com/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "medium_queue.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# --- HTML allow-list (Medium API accepted subset) -------------------------
ALLOWED = {"p", "br", "hr", "strong", "em", "u", "a", "img", "blockquote",
           "pre", "code", "ul", "ol", "li", "h3", "h4", "figure", "figcaption"}
RENAME = {"b": "strong", "i": "em", "h2": "h3", "h5": "h4", "h6": "h4", "h1": "h3"}
DROP = {"script", "style", "nav", "footer", "header", "form", "button", "svg",
        "noscript", "iframe", "aside", "template", "select", "textarea",
        "video", "audio", "canvas", "dialog", "label", "input", "object",
        "embed", "ins", "del"}
TRANSPARENT = {"div", "span", "section", "main", "article", "body", "html",
               "head", "center", "font", "small", "sub", "sup", "picture",
               "source", "time", "address", "abbr", "dl", "dt", "dd", "table",
               "thead", "tbody", "tfoot", "tr", "td", "th", "caption"}
TABLE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption"}
VOID = {"br", "hr", "img"}
NEVER_CLOSES = {"input", "embed", "source", "track", "wbr", "param", "keygen", "base", "link", "meta", "col", "area"}


def esc(t, quote=False):
    return html_mod.escape(t, quote=quote)


def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()


def strip_tags(fragment):
    return clean_text(re.sub(r"<[^>]+>", " ", fragment))


# --- Title extraction ------------------------------------------------------
CONTENT_DIV_CLASSES = {"post-body", "pb-body", "entry-content", "post-content",
                       "article-content", "article-body", "markdown-body",
                       "prose", "e-content", "postBody", "blog-content"}
DROP_CLASS_TOKENS = {"toc", "breadcrumbs", "crumbs", "pb-crumbs", "share",
                     "sharing", "sharedaddy", "post-share-buttons",
                     "post-footer", "post-labels", "related", "related-posts",
                     "sidebar", "widget", "comments", "comment-form",
                     "newsletter", "subscribe", "subscription", "pagination",
                     "post-navigation", "nav-links", "pb-tags", "kicker",
                     "adsbygoogle", "ad", "ad-slot", "social", "share-buttons"}


def strip_site_suffix(t):
    """Drop trailing ' | BlogName' from og:title / <title> values."""
    if " | " in t:
        parts = t.split(" | ")
        head = " | ".join(parts[:-1])
        if len(parts[-1]) <= 30 and len(head) >= 20:
            return head
    return t


def extract_title(raw):
    # 1) Blogger h1.post-title (cleanest, no blog-name prefix)
    m = re.search(r"<h1[^>]*class=['\"][^'\"]*post-title[^'\"]*['\"][^>]*>(.*?)</h1>", raw, re.I | re.S)
    if m and clean_text(strip_tags(m.group(1))):
        return clean_text(html_mod.unescape(strip_tags(m.group(1))))
    # 2) og:title
    m = (re.search(r"<meta[^>]+(?:property|name)=['\"]og:title['\"][^>]*?content=['\"]([^'\"]*)['\"]", raw, re.I)
         or re.search(r"<meta[^>]+content=['\"]([^'\"]*)['\"][^>]*?(?:property|name)=['\"]og:title['\"]", raw, re.I))
    if m and clean_text(m.group(1)):
        return strip_site_suffix(clean_text(html_mod.unescape(m.group(1))))
    # 3) first h1
    m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.I | re.S)
    if m and clean_text(strip_tags(m.group(1))):
        return clean_text(html_mod.unescape(strip_tags(m.group(1))))
    # 4) <title> tag
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
    if m and clean_text(strip_tags(m.group(1))):
        return strip_site_suffix(clean_text(html_mod.unescape(strip_tags(m.group(1)))))
    return None


# --- Boundary detection (pass 1) -------------------------------------------
class BoundaryFinder(HTMLParser):
    """Decides which page region holds the article. Priority: a content div
    (post-body/pb-body/entry-content...) anywhere in the page, then <article>,
    then whole <body>. Records candidates; the best one wins even if it
    appears later in the stream."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.content_div = False
        self.article = False

    @property
    def boundary(self):
        if self.content_div:
            return "content-div"
        if self.article:
            return "article"
        return "body"

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            cls = set((dict(attrs).get("class") or "").split())
            if cls & CONTENT_DIV_CLASSES:
                self.content_div = True
        elif tag == "article":
            self.article = True


# --- Sanitizer (pass 2) ----------------------------------------------------
class Sanitizer(HTMLParser):
    def __init__(self, base_url, boundary, title):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.boundary = boundary
        self.title_norm = clean_text(title or "").lower()
        self.out = []
        self.capture_on = False
        self.finished = False
        self.gate_tag = None
        self.gate_depth = 0
        self.skip_tag = None
        self.skip_depth = 0
        self.in_h1 = False
        self.h1_buf = []
        self.first_h1_seen = False
        self.table_depth = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.a_emitted = []  # stack: was this <a> open emitted?
        self.open_tags = []  # open container tags awaiting close

    # -- gate control -------------------------------------------------------
    def _open_gate(self, tag):
        self.capture_on = True
        self.gate_tag = tag
        self.gate_depth = 1

    def _maybe_open_gate(self, tag, attrs):
        if self.finished or self.capture_on:
            return
        if self.boundary == "content-div" and tag == "div":
            cls = set((dict(attrs).get("class") or "").split())
            if cls & CONTENT_DIV_CLASSES:
                self._open_gate("div")
        elif self.boundary == "article" and tag == "article":
            self._open_gate("article")
        elif self.boundary == "body" and tag == "body":
            self._open_gate("body")

    def _gate_close(self, tag):
        if tag == self.gate_tag:
            self.gate_depth -= 1
            if self.gate_depth <= 0:
                self.capture_on = False
                self.finished = True

    # -- emission helpers ---------------------------------------------------
    def _emit_text(self, data):
        if self.in_h1:
            self.h1_buf.append(data)
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        if self.table_depth > 0:
            return
        self.out.append(esc(data))

    def _flush_table(self):
        parts = []
        for i, r in enumerate(self.rows):
            cells = [clean_text("".join(c)) for c in r if c and "".join(c).strip()]
            if not cells:
                continue
            line = "  —  ".join(cells)
            if i == 0:
                parts.append("<p><strong>%s</strong></p>" % esc(line))
            else:
                parts.append("<p>%s</p>" % esc(line))
        self.out.extend(parts)
        self.rows = []

    # -- parser events ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._maybe_open_gate(tag, attrs)
        if not self.capture_on:
            return
        if self.gate_tag == tag:
            self.gate_depth += 1
        # skip containers entirely
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        if tag in DROP:
            if tag in VOID or tag in NEVER_CLOSES:
                return  # tag that never closes: skip it alone, no skip mode
            self.skip_tag = tag
            self.skip_depth = 1
            return
        # drop noisy containers by class token (toc, share, related...)
        if tag in ("div", "aside", "nav", "section", "header", "footer", "span", "ul"):
            cls = set((dict(attrs).get("class") or "").split())
            if cls & DROP_CLASS_TOKENS:
                self.skip_tag = tag
                self.skip_depth = 1
                return
        # tables: flatten
        if tag in TABLE_TAGS:
            if tag == "table":
                self.table_depth += 1
                if self.table_depth == 1:
                    self.rows = []
            elif tag == "tr" and self.table_depth:
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = []
            return
        if tag == "h1":
            self.in_h1 = True
            self.h1_buf = []
            return
        if self.table_depth:
            return  # inside a table: cells are text-only
        t = RENAME.get(tag, tag)
        if t not in ALLOWED:
            return  # transparent: children flow through
        a = dict(attrs)
        if t == "a":
            href = a.get("href") or ""
            if href and not href.startswith(("#", "javascript:", "data:")):
                href = urljoin(self.base, href)
                self.out.append('<a href="%s">' % esc(href, quote=True))
                self.a_emitted.append(True)
                self.open_tags.append("a")
            else:
                self.a_emitted.append(False)
            # dead/fragment anchor: emit nothing, children flow as text
        elif t == "img":
            src = a.get("src") or ""
            if src.startswith("data:"):
                return
            src = urljoin(self.base, src)
            alt = esc(a.get("alt") or "", quote=True)
            self.out.append('<img src="%s" alt="%s"/>' % (esc(src, quote=True), alt))
        elif t in VOID:
            self.out.append("<%s/>" % t)
        else:
            self.out.append("<%s>" % t)
            self.open_tags.append(t)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID and self.capture_on and not self.skip_tag and self.table_depth == 0 and not self.in_h1:
            t = RENAME.get(tag, tag)
            if t in ALLOWED:
                if t == "img":
                    a = dict(attrs)
                    src = urljoin(self.base, a.get("src") or "")
                    if not src or src.startswith("data:"):
                        return
                    self.out.append('<img src="%s" alt="%s"/>' % (esc(src, quote=True), esc(a.get("alt") or "", quote=True)))
                else:
                    self.out.append("<%s/>" % t)

    def handle_endtag(self, tag):
        if not self.capture_on:
            return
        if self.gate_tag == tag:
            self._gate_close(tag)
            if not self.capture_on:
                return
        if self.skip_tag:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth <= 0:
                    self.skip_tag = None
                    self.skip_depth = 0
            return
        if tag in TABLE_TAGS:
            if tag in ("td", "th") and self.cell is not None:
                if self.row is not None:
                    self.row.append("".join(self.cell))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None
            elif tag == "table":
                self.table_depth -= 1
                if self.table_depth <= 0:
                    self.table_depth = 0
                    self._flush_table()
            return
        if self.table_depth:
            return  # inside a table: suppress stray end tags from cells
        if tag == "h1" and self.in_h1:
            self.in_h1 = False
            text = clean_text("".join(self.h1_buf))
            self.h1_buf = []
            if not self.first_h1_seen and self.title_norm and text.lower() == self.title_norm:
                self.first_h1_seen = True
                return  # duplicate of title -> drop
            self.first_h1_seen = True
            if text:
                self.out.append("<h3>%s</h3>" % esc(text))
            return
        t = RENAME.get(tag, tag)
        if t == "a":
            if self.a_emitted and self.a_emitted.pop():
                self.out.append("</a>")
                if "a" in self.open_tags:
                    self.open_tags.reverse()
                    self.open_tags.remove("a")
                    self.open_tags.reverse()
            return
        if t in ALLOWED and t not in VOID:
            self.out.append("</%s>" % t)
            if t in self.open_tags:
                self.open_tags.reverse()
                self.open_tags.remove(t)
                self.open_tags.reverse()

    def handle_data(self, data):
        if not self.capture_on:
            return
        if self.skip_tag:
            return  # inside script/style/nav/toc/etc: discard
        self._emit_text(data)

    def handle_comment(self, data):
        pass

    def result(self):
        # self-close any tags the source left open (Blogger often leaves <p>)
        for t in reversed(self.open_tags):
            self.out.append("</%s>" % t)
        html_out = "".join(self.out)
        html_out = re.sub(r"(<(?:p|li|h3|h4|blockquote|pre|ul|ol|figure)>)+\s*(</(?:p|li|h3|h4|blockquote|pre|ul|ol|figure)>)+", "", html_out)
        html_out = re.sub(r"\s+", " ", html_out)
        html_out = re.sub(r"> <p", "><p", html_out)
        return html_out.strip()


def extract_article(url):
    raw = fetch(url)
    title = extract_title(raw)
    bf = BoundaryFinder()
    bf.feed(raw)
    boundary = bf.boundary or "body"
    s = Sanitizer(url, boundary, title)
    s.feed(raw)
    s.close()
    content = s.result()
    return title, content, boundary, len(raw)


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(q):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api_call(path, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(API_BASE + path, data=data, method="POST" if data else "GET",
                  headers={"Authorization": "Bearer " + token,
                           "Content-Type": "application/json",
                           "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"error": e.read().decode("utf-8", "replace")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--entry", type=int, help="entry id (default: first pending)")
    ap.add_argument("--status", choices=["draft", "public"], default="public")
    ap.add_argument("--token", default=os.environ.get("MEDIUM_TOKEN"))
    a = ap.parse_args()

    q = load_queue()
    entries = q["entries"]

    if a.list:
        for e in entries:
            mark = {"pending": "[ ]", "published": "[x]", "skipped": "[-]"}.get(e["status"], "[?]")
            print("%s #%d %-9s %s" % (mark, e["id"], e["status"], e["url"]))
        print("pending: %d / %d" % (sum(1 for e in entries if e["status"] == "pending"), len(entries)))
        return 0

    if a.check:
        if not a.token:
            print("ERROR: no token (MEDIUM_TOKEN env or --token)"); return 2
        code, body = api_call("/me", a.token)
        print("HTTP", code)
        if code == 200:
            d = body.get("data", {})
            print("userId :", d.get("id"))
            print("name   :", d.get("name"))
            print("username:", d.get("username"))
            print("url    :", d.get("url"))
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

    url = ent["url"]
    tags = ent.get("tags", [])[:5]
    print("entry #%d -> %s" % (ent["id"], url))
    title, content, boundary, raw_len = extract_article(url)
    if not title or len(title) < 3:
        print("ERROR: could not extract title"); return 1
    if len(content) < 500:
        print("ERROR: extracted content too short (%d chars) — extraction failed?" % len(content)); return 1
    payload = {
        "title": title,
        "contentFormat": "html",
        "content": content,
        "canonicalUrl": url,
        "tags": tags,
        "publishStatus": a.status,
    }

    if a.dry_run:
        print("boundary : %s (raw page %d chars)" % (boundary, raw_len))
        print("title    : %s (%d chars)" % (title, len(title)))
        print("tags     : %s" % ", ".join(tags))
        print("canonical: %s" % url)
        print("content  : %d chars of sanitized HTML" % len(content))
        print("images   : %d | links: %d | tables flattened: %s"
              % (content.count("<img"), content.count("<a "), "yes" if "—  " in content or boundary else "n/a"))
        print("--- first 500 chars ---")
        print(content[:500])
        with open("/tmp/medium_payload_preview.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("--- full sanitized HTML: /tmp/medium_payload_preview.html ---")
        return 0

    if a.publish:
        if not a.token:
            print("ERROR: no token (MEDIUM_TOKEN env or --token)"); return 2
        code, me = api_call("/me", a.token)
        if code != 200:
            print("ERROR: token check failed:", code, json.dumps(me)[:300]); return 1
        uid = me["data"]["id"]
        print("authenticated as %s (%s)" % (me["data"].get("name"), uid))
        code, body = api_call("/public/users/%s/posts" % uid, a.token, payload)
        print("publish -> HTTP", code)
        if code in (200, 201):
            d = body.get("data", {})
            print("MEDIUM URL:", d.get("url"))
            ent["status"] = "published"
            ent["medium_url"] = d.get("url")
            ent["published_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            q["updated"] = ent["published_at"]
            save_queue(q)
            print("queue updated: entry #%d -> published" % ent["id"])
            return 0
        print(json.dumps(body, indent=2)[:600])
        return 1

    print("nothing to do: use --list / --dry-run / --check / --publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
