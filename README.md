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
