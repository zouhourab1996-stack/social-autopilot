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
