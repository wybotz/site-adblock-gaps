# AGENTS.md

Context for any AI coding agent working in this repo.

## What this repo is

A small, hand-verified supplementary blocklist (`blocklist.txt`) of
ad/tracking domains that the AdGuard DNS filter (the list AdGuard Home
enforces) doesn't block, found by surveying specific sites' consent
flows. `tools/gapcheck/` surveys the sites weekly and proposes a
candidate `blocklist.new.txt`; a human reviews every change. See
`README.md` for the overview, `SURVEY_METHOD.md` for the survey and
judging process, and `tools/gapcheck/README.md` for the tool. Read
`SURVEY_METHOD.md` before adding or changing any rule.

## Hard rules

- **Never add a rule that blocks a site's own CMP (consent management
  platform) domain**, e.g. `cmp.svd.se`, `sourcepoint.theguardian.com`.
  Blocking the CMP breaks the ability to see or click "Accept"/"Reject"
  at all, which defeats the entire purpose of this list.
- **Never block a whole domain whose vendor also runs a CMP or another
  functional service elsewhere.** Use a host-only rule instead: e.g.
  `||choices.trustarc.com^`, never `||trustarc.com^`, because
  `consent.trustarc.com` is the consent dialog on other sites.
- **"Covered" means blocked by the AdGuard DNS filter, with DNS
  semantics.** EasyList/EasyPrivacy coverage doesn't count (AdGuard
  Home doesn't use them). Path rules and rules with narrowing modifiers
  (`$third-party`, `$script`, `$~media`, ...) don't block a host at DNS
  level, and an `@@` exception cancels a block. Before overriding an
  upstream `@@` exception, find out why it exists.
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
  near-miss is not coverage. Don't mark a domain "already covered" on
  the strength of a fuzzy match.
- **Every added rule needs a verification date and a one-line reason**
  in `blocklist.txt`, under the relevant site's section. Don't add a
  bare rule with no context. A gapcheck candidate list marks missing
  reasons with `TODO`; none may be committed.
- **Test rules that might break a function** (video players, payments,
  embeds) before adding them, as in `SURVEY_METHOD.md` step 5, and put
  them in their own documented section rather than a site section.
- **Don't delete or renumber existing site sections** when adding a new
  one. Append a new section following the same format instead.
- **Never log in to a surveyed site or use credentials.** The only
  click allowed in a survey is the cookie wall's "Accept all".
- **Never commit or push automatically from gapcheck**, and don't push
  agent commits without the user's review.

## Working with gapcheck output

- Judge every `NEW` rule in `blocklist.new.txt` (`SURVEY_METHOD.md`,
  "Judging a host"). Identify unknown hosts from full URLs, frame chain,
  referer and response bodies, not from the hostname alone.
- Infrastructure and CMP hosts go into `[hosts]` in
  `tools/gapcheck/gapcheck.toml` (`kind = "infrastructure"` or
  `"cmp"`), always with a note, and their rule is removed from the
  candidate list. A host the user decided not to block also goes there
  as `kind = "infrastructure"`, with a note starting "Not blocked by
  decision (date)".
- Ad-tech hosts get a `[hosts]` note too, so the reason appears in
  future candidate lists.
- `tools/gapcheck/HANDOFF.md` holds the progress log between sessions;
  add a dated entry when finishing a piece of work.

## Format reminder

Rules are standard Adblock Plus / uBlock Origin / AdGuard domain syntax:
`||domain^`, one per line, with notes on separate `!` lines (adblock
syntax has no inline comments). One file, organized by site with
`!`-comment headers. Don't split into per-site files (AdGuard Home
subscribes to one URL).

Site section headers are `! Name — domain` between two `! ====` bars,
followed by `! Verified: <date>`. gapcheck finds sections by that
domain and stops with an error on an unpaired bar. A cross-site section
has no domain in its header, so gapcheck never adds rules to it.
