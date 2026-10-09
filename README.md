# ⚠️ STATUS: RESTORED under FINAL WARNING (2026-10-06)

Account reinstated after appeal — but Bluesky issued a **final warning**: any repeat
(spam patterns OR bulk following) = permanent spam label or permanent takedown.

## Re-entry protocol (mandatory)
- **48–72h of silence first** — no posting until 2026-10-09.
- Then max **1 post per day**, dispatched manually — cron stays OFF until 2–3 clean weeks.
- Strict mix 2:1 — value posts (no links) : link posts. Value entries are in the queue
  (no "url" field). Alternate: link → value → link…
- Batch multi-shipment announcements into ONE post, never one post per product.
- Zero following/unfollowing. Network grows organically only.

## Cadence rules once restored (mandatory)
- Max **1 post per day** — never more than one dispatch per shipment day; batch announcements into a single post.
- Mix ratio ~2:1 — value posts (tips, facts, no links) : link posts.
- No follow/unfollow automation of any kind. Ever.
- Keep 2-3 topical hashtags max per post.

---


## Standing rule (from the owner, 2026-10-04)
Whenever a new article is published on any of our Blogger blogs or GitHub Pages sites,
the same working session also adds a Bluesky post for it to `queue.json` AND dispatches
it immediately — no extra request needed.

## Hashtags (standing rule, 2026-10-06)

Every post must carry **2-4 topical hashtags** for reach. Add a `"tags": ["Tag1","Tag2"]`
array to each queue entry — autopilot appends them as clickable #hashtags
(`app.bsky.richtext.facet#tag`), respects the post length limit, and skips anything
that looks like a URL fragment. Hashtags already present in the text are auto-faceted too.

## Medium channel (medium_publisher.py) — added 2026-10-07

Medium closed new OAuth integrations (repo archived 2023), but the API server
is ALIVE and self-issued integration tokens (Settings → Integration tokens)
still authenticate. Pipeline: `medium_queue.json` → fetch live article →
sanitize (tables flattened to text lines, TOC/share/nav/schema junk dropped,
relative URLs absolutized, h1-title dedup, stray tags self-closed) →
`POST /v1/public/users/{id}/posts` with canonicalUrl = the source page.

- Verify token: `MEDIUM_TOKEN=... python3 medium_publisher.py --check`
- Preview payload (no token needed): `python3 medium_publisher.py --dry-run --entry 1`
- Publish: `MEDIUM_TOKEN=... python3 medium_publisher.py --publish --entry 1` (`--status draft` to stage)
- Auto-detects the article boundary across network site types: static pages
  (`<article>`), Blogger (`post-body`), prophetic (`pb-body`).
- Protocol: max 2 posts/week · value articles only · canonical always the
  source page · zero bulk follows/engagement (same rule that saved bsky).
- NOT wired into any cron. Publishing is by explicit command only.

## dev.to channel (devto_publisher.py) — added 2026-10-07

dev.to's API is open (Forem): POST /api/articles with the `api-key` header —
body_markdown, tags (max 4), canonical_url, main_image. Queue:
`devto_queue.json`, markdown pre-built from prophetic.pw `src/data/reviews.ts`
(4 long-form reviews; the 6 short-form ones are reserved for a future roundup).

- Verify token: `DEVTO_TOKEN=... python3 devto_publisher.py --check`
- Preview (no token): `python3 devto_publisher.py --dry-run --entry 1`
- Publish as draft: `DEVTO_TOKEN=... python3 devto_publisher.py --publish --entry 1`
- Draft -> public:  `DEVTO_TOKEN=... python3 devto_publisher.py --flip --entry 1`
- Protocol: FIRST ARTICLE ALWAYS AS DRAFT, verify rendering, then flip.
  Max 2/week · canonical_url always the source page · affiliate disclosure
  line included in every review markdown.
- NOT wired into any cron. Publishing is by explicit command only.

## Pinterest channel (pinterest.py) — status 2026-10-09

- Runs daily (10:23 UTC) and on manual dispatch; one pin per run from `pins.json`.
- **Blocked upstream:** the Pinterest app (client id 1619387) has *Trial* access, and Pinterest
  rejects production pin creation with error code 29. Until the app is upgraded to **Standard
  access** at https://developers.pinterest.com/apps/1619387/ the run ends green with a warning
  and leaves the entry queued. Set `PINTEREST_STRICT=1` to make it fail instead.
- Pins made by hand in the browser must be added to `pinned_links.json`; the script never
  pins a link that is already there or already posted (links compared without query/www/slash).
- Tumblr and X are not automated here (no API apps/secrets); Bluesky cron stays off (final warning),
  Reddit/Facebook are shelved by the owner.
