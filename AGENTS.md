# AGENTS.md

Context for any AI coding agent working in this repo.

## What this repo is

A small, hand-verified supplementary blocklist (`blocklist.txt`) of
ad/tracking domains missing from EasyList, EasyPrivacy, and the AdGuard
DNS filter — found by surveying specific sites' consent flows. See
`README.md` for the overview and `SURVEY_METHOD.md` for the full survey
process. Read `SURVEY_METHOD.md` before adding or changing any rule.

## Hard rules

- **Never add a rule that blocks a site's own CMP (consent management
  platform) domain** — e.g. `cmp.svd.se`, `sourcepoint.theguardian.com`.
  Blocking the CMP breaks the ability to see or click "Accept"/"Reject"
  at all, which defeats the entire purpose of this list.
- **Never claim a domain is "already covered" or "not found" in
  EasyList/EasyPrivacy/the AdGuard DNS filter without grepping the
  actual raw source file directly.** A summarizing web-fetch tool has
  previously produced false "not found" results for decade-old, clearly
  present domains (`scorecardresearch.com`, `amazon-adsystem.com`) by
  silently truncating before reaching the relevant lines. Always:
  1. Download the raw file (raw.githubusercontent.com URLs, not a
     rendered/summarized view).
  2. Sanity-check first by confirming a known domain (e.g.
     `doubleclick.net`) actually appears in what was downloaded.
  3. Only then trust a "not found" result for the domain in question.
- **Watch for near-miss / typo domains in existing lists** (e.g. the
  AdGuard DNS filter contains `sb.scorecard.research.com`, an extra dot,
  which is a different domain from the real
  `sb.scorecardresearch.com` and provides no actual coverage). A
  near-miss is not coverage — don't mark a domain "already covered" on
  the strength of a fuzzy match.
- **Every added rule needs a verification date and a one-line reason**
  in `blocklist.txt`, under the relevant site's section. Don't add a
  bare rule with no context.
- **Don't delete or renumber existing site sections** when adding a new
  one — append a new section following the same format instead.

## Format reminder

Rules are standard Adblock Plus / uBlock Origin / AdGuard domain syntax:
`||domain^`. One file, organized by site with `!`-comment headers —
don't split into per-site files (AdGuard Home subscribes to one URL).
