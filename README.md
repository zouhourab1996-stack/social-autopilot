
## Standing rule (from the owner, 2026-10-04)
Whenever a new article is published on any of our Blogger blogs or GitHub Pages sites,
the same working session also adds a Bluesky post for it to `queue.json` AND dispatches
it immediately — no extra request needed.

## Hashtags (standing rule, 2026-10-06)

Every post must carry **2-4 topical hashtags** for reach. Add a `"tags": ["Tag1","Tag2"]`
array to each queue entry — autopilot appends them as clickable #hashtags
(`app.bsky.richtext.facet#tag`), respects the post length limit, and skips anything
that looks like a URL fragment. Hashtags already present in the text are auto-faceted too.
