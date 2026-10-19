# site-adblock-gaps

A personal supplementary blocklist of ad/tracking domains that the
**AdGuard DNS filter** (the list AdGuard Home runs) doesn't block, found
by surveying specific sites' consent flows and watching real network
traffic after clicking "Accept."

This is not a general-purpose blocklist and isn't trying to replace
the standard lists. It only contains the small number of domains that
fell through the cracks for specific sites, so it's meant to be used
*alongside* the AdGuard DNS filter, not instead of it.

## Why this exists

Standard filter lists are huge but not perfect. Some publisher-specific
ad-serving infrastructure (hosted under the publisher's own domain
rather than a well-known third-party one) or older tracker domains can
be absent even from lists that are otherwise comprehensive. This repo is
where those specific, verified gaps get tracked as they're found, site
by site.

What counts as a gap is what AdGuard Home would actually let through.
EasyList and EasyPrivacy are checked too, but only for reference: they
are browser lists, AdGuard Home doesn't subscribe to them, and many of
their rules (path rules, `$third-party`, `$~media`) can't work at DNS
level anyway. So a domain EasyList blocks can still belong here.

## Files

- **`blocklist.txt`**: the actual rules, in standard Adblock
  Plus / uBlock Origin / AdGuard domain-blocking syntax (`||domain^`),
  organized by site with verification dates and comments, plus a
  cross-site section for video-ad hosts.
- **`SURVEY_METHOD.md`**: how a site gets checked and how each found
  host is judged, so future additions follow the same process (and
  don't repeat a false-negative mistake made early on with a
  summarizing fetch tool; see that file for details).
- **`tools/gapcheck/`**: the survey tool. It runs the survey weekly in
  a headless browser and proposes a candidate `blocklist.new.txt`; see
  its `README.md`.
- **`AGENTS.md`**: hard rules for AI coding agents working in this
  repo (and a good checklist for humans too).

## How the list is maintained

1. Every Monday evening, gapcheck surveys the configured sites in a
   rootless Podman container on rimmer.
2. If it finds hosts the AdGuard DNS filter doesn't block, or rules
   that upstream now covers, it writes `blocklist.new.txt` next to
   `blocklist.txt`. It never commits or pushes.
3. Every proposed host is judged by hand (`SURVEY_METHOD.md`, "Judging
   a host"): ad-tech gets a rule with a date and reason, infrastructure
   and consent platforms go into `gapcheck.toml` so they aren't
   proposed again.
4. The reviewed list is committed and pushed; AdGuard Home picks it up
   on its next filter update.

## Using this with AdGuard Home

Filters → DNS blocklists → Add blocklist → point at the raw URL:

```
https://raw.githubusercontent.com/wybotz/site-adblock-gaps/main/blocklist.txt
```

AdGuard Home will then refresh it on its normal filter-update schedule,
same as any other subscribed list. Force an immediate refresh from the
same page if needed.

The list blocks network-wide, so if something on the network stops
working (a video player, a payment button), check AdGuard Home's Query
Log for this list's rules first. Rules with a known breakage risk sit in
their own documented section (currently the video-ad hosts) so they are
easy to find and comment out.

## Adding a new site

Add a `[[site]]` block to `tools/gapcheck/gapcheck.toml` and run
gapcheck once (`systemctl --user start gapcheck`); see
`tools/gapcheck/README.md`. Then judge the proposed hosts as described
in `SURVEY_METHOD.md`.

Some things gapcheck can't see, such as pages behind a click (a
subscribe flow, a video that needs playing). Those are surveyed by hand,
using the manual method in `SURVEY_METHOD.md`.
