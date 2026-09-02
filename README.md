# site-adblock-gaps

A personal supplementary blocklist of ad/tracking domains that are
**missing** from the standard filter lists (EasyList, EasyPrivacy, the
AdGuard DNS filter) — found by surveying specific sites' consent flows
and watching real network traffic after clicking "Accept."

This is not a general-purpose blocklist and isn't trying to replace
EasyList/EasyPrivacy/AdGuard's lists — it only contains the small number
of domains that fell through the cracks of those lists for specific
sites, so it's meant to be used *alongside* them, not instead of them.

## Why this exists

Standard filter lists are huge but not perfect. Some publisher-specific
ad-serving infrastructure (hosted under the publisher's own domain
rather than a well-known third-party one) or older tracker domains can
be absent even from lists that are otherwise comprehensive. This repo is
where those specific, verified gaps get tracked as they're found, site
by site.

## Files

- **`blocklist.txt`** — the actual rules, in standard Adblock
  Plus / uBlock Origin / AdGuard domain-blocking syntax (`||domain^`),
  organized by site with verification dates and comments.
- **`SURVEY_METHOD.md`** — how a site gets checked, so future additions
  follow the same process (and don't repeat a false-negative mistake
  made early on with a summarizing fetch tool — see that file for
  details).

## Using this with AdGuard Home

Filters → DNS blocklists → Add blocklist → point at the raw URL:

```
https://raw.githubusercontent.com/wybotz/site-adblock-gaps/main/blocklist.txt
```

AdGuard Home will then refresh it on its normal filter-update schedule,
same as any other subscribed list. Force an immediate refresh from the
same page if needed.

## Adding a new site

See `SURVEY_METHOD.md`. Short version: click the real "Accept," watch
what fires, grep the *actual* EasyList/EasyPrivacy/AdGuard source files
directly (not through a summarizing tool) to confirm what's already
covered, then add only the genuine gaps — with the rest kept as comments
for the record.
