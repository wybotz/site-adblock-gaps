# How to survey a new site and add it to the blocklist

This is the method used for SvD and The Guardian (2 September 2026), written
up so the next site gets checked the same way.

## 1. Understand the consent flow first

Before touching network traffic, work out what the site's cookie/consent
banner actually does. Most commercial sites now use a Consent Management
Platform (CMP) — Sourcepoint, OneTrust, Didomi, etc. Find:

- Where the CMP is hosted (its own subdomain, e.g. `cmp.example.com`)
- What clicking "Accept" sets (cookies, `localStorage`, and — for
  IAB TCF-based CMPs — a consent string readable via `window.__tcfapi`)

**Do not block the CMP's own domain.** That's the mechanism that lets you
see and click "Accept" (or "Reject") at all — blocking it breaks the
banner, not the tracking.

## 2. Click the real "Accept all" and watch what fires

Click the honest, true "Accept all" (or equivalent) — not a spoofed
consent state — then watch outgoing requests directly:

- Browser devtools Network tab, or
- A network trace / packet capture, or
- uBlock Origin's logger in "no blocking" mode temporarily, just to see
  what would have fired

Note every third-party domain that starts receiving requests once
consent is granted. Distinguish clearly between:

- **Third-party ad-tech / tracking vendors** (ad exchanges, identity
  resolution, analytics beacons) — these are what you're trying to
  block.
- **The publisher's own first-party domains** — a network blocker
  generally can't touch these without breaking the page, and they're
  out of scope for this kind of list.
- **The CMP domain itself** — never block.

## 3. Check each domain against existing filter lists — properly

This is the step that went wrong the first time: fetching EasyList /
EasyPrivacy / the AdGuard DNS filter through a summarizing web-fetch tool
produced false "not found" results for domains that have been on those
lists for over a decade (`scorecardresearch.com`, `amazon-adsystem.com`),
because the fetch was silently truncating before reaching the relevant
lines.

**The reliable way:**

1. Pull the actual raw source files directly, not through a summarizer:
   - EasyList: `https://raw.githubusercontent.com/easylist/easylist/master/easylist/easylist_general_block.txt`
   - EasyPrivacy: `https://raw.githubusercontent.com/easylist/easylist/master/easyprivacy/easyprivacy_general.txt`
     (and the `_general_block`, `_specific_block`, `_thirdparty` variants —
     check all of them)
   - AdGuard DNS filter: `https://raw.githubusercontent.com/AdguardTeam/HostlistsRegistry/main/assets/filter_1.txt`
     (or whichever specific list is enabled in AdGuard Home — check
     Filters → DNS blocklists for the exact one and its source URL)
2. Save them locally and `grep` completely, not via a tool that might
   truncate.
3. **Sanity-check before trusting any "not found" result**: confirm a
   known decade-old domain (e.g. `doubleclick.net`,
   `amazon-adsystem.com`) actually appears in the file you just grepped.
   If it doesn't, the file didn't download completely — fix that before
   concluding anything is a genuine gap.
4. Watch for near-misses / typos in the existing lists (e.g. the
   AdGuard DNS filter has `sb.scorecard.research.com` — an extra dot —
   which looks like it should cover `scorecardresearch.com` but is
   actually a different, non-matching domain). A near-miss is not
   coverage.

## 4. Record the result

For each domain identified in step 2, it ends up in one of two buckets:

- **Genuine gap** → add as an active `||domain^` rule under that site's
  section in `blocklist.txt`, with a one-line comment on why it's
  notable (if anything is).
- **Already covered** → add as a `!`-commented line for the record,
  noting which existing rule/list covers it. This isn't functional, but
  it's a record that the domain was checked and isn't forgotten or
  silently missing.

Add a `! Verified: <date>` line under the site's header so it's clear
when the check was last done — filter lists change, so a site may be
worth re-checking periodically rather than assuming a past result still
holds.

## 5. Push and let AdGuard Home pick it up

If AdGuard Home is subscribed to this file's raw GitHub URL as a
blocklist (Filters → DNS blocklists), it refreshes on its own schedule.
To confirm immediately, use Filters → DNS blocklists → refresh, then
check Query Log while visiting the site to confirm the new domains show
up as blocked.
