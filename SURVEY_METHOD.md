# How sites are surveyed and how a found host is judged

The method was first used by hand for SvD and The Guardian (2 September
2026). Since 7 October 2026 the collecting and coverage checking is
automated by gapcheck (`tools/gapcheck/`), which runs weekly. The
judging is still done by hand, and some pages still need a manual
survey. This file covers both.

Ground rules for every survey, by hand or automated:

- Never log in to a surveyed site and never use credentials of any
  kind. The only click allowed is the cookie wall's "Accept all".
- Click the honest "Accept all", not a spoofed consent state. The
  point of the list is to neutralise what that consent nominally
  allows.

## 1. Understand the consent flow first

Before touching network traffic, work out what the site's cookie/consent
banner actually does. Most commercial sites now use a Consent Management
Platform (CMP): Sourcepoint, OneTrust, Didomi, TrustArc, or the
publisher's own. Find:

- Where the CMP is hosted (its own subdomain, e.g. `cmp.example.com`,
  and any platform host behind it, e.g. `cdn.privacy-mgmt.com` for
  Sourcepoint)
- What clicking "Accept" sets (cookies, `localStorage`, and, for
  IAB TCF-based CMPs, a consent string readable via `window.__tcfapi`)

**Do not block the CMP's own domains.** That's the mechanism that lets
you see and click "Accept" (or "Reject") at all; blocking it breaks the
banner, not the tracking. gapcheck excludes the frame the Accept button
was found in automatically; other CMP hosts go into `gapcheck.toml`
(the site's `cmp` list, or `[hosts]` with `kind = "cmp"`).

## 2. Collect the hosts

### Automatically: gapcheck (the normal path)

gapcheck opens each `[[site]]` in `tools/gapcheck/gapcheck.toml` in a
fresh browser profile, clicks "Accept all", scrolls, follows one article
link, and records every request. Its container resolves through
unfiltered DNS (and refuses to run if DNS is filtered), so it sees
everything the ad scripts load, not only what gets past AdGuard Home.
See `tools/gapcheck/README.md` for running it and reading its output.

To add a site: append a `[[site]]` block, run gapcheck once, and fix
what the run reports (no consent button found, no article matched).

### By hand (what gapcheck can't reach)

gapcheck only sees a site's front page and one article. Anything behind
a further click needs a manual survey: subscribe/paywall flows (e.g.
DN's Klarna hosts), video players that only load ad tech on play, live
blogs. Use:

- Browser devtools Network tab, or
- uBlock Origin's logger in "no blocking" mode temporarily, just to see
  what would have fired, or
- a small Playwright script in the gapcheck image (as in step 5)

Make sure the browser's DNS isn't filtered by AdGuard Home while you
watch, or blocked scripts hide what they would have loaded.

## 3. Check each host against the filter lists, properly

**What counts as covered** is the AdGuard DNS filter, because that is
the list AdGuard Home actually enforces (gapcheck: `enforced = true`).
EasyList and EasyPrivacy are reference only. Before October 2026 the
manual surveys counted EasyPrivacy coverage as "covered"; that was
wrong for this setup, and some hosts marked covered then are gaps now.

DNS-level blocking also changes what a rule means:

- A rule with a path (`||trustarc.com/cap?`) or a narrowing modifier
  (`$third-party`, `$script`, `$~media`) does not block the host in
  AdGuard Home. It's at most partial coverage.
- An `@@` exception cancels a block. `www.googleadservices.com` and
  `tags.crwdcntrl.net` are both blocked by a parent rule and let through
  by an exception, so both are gaps.
- Wildcard rules (`||prebid-*.rubiconproject.com^`) do count.

gapcheck applies all of this. When checking by hand, this is the step
that went wrong the first time: fetching the lists through a
summarizing web-fetch tool produced false "not found" results for
domains that have been on those lists for over a decade
(`scorecardresearch.com`, `amazon-adsystem.com`), because the fetch was
silently truncating before reaching the relevant lines.

**The reliable way:**

1. Pull the actual raw source files directly, not through a summarizer:
   - AdGuard DNS filter: `https://raw.githubusercontent.com/AdguardTeam/HostlistsRegistry/main/assets/filter_1.txt`
     (or whichever list is enabled in AdGuard Home; check
     Filters → DNS blocklists for the exact one and its source URL)
   - For reference, EasyList: `https://raw.githubusercontent.com/easylist/easylist/master/easylist/easylist_general_block.txt`
     (and `easylist_adservers.txt`, `easylist_allowlist.txt`)
   - For reference, EasyPrivacy: `https://raw.githubusercontent.com/easylist/easylist/master/easyprivacy/easyprivacy_general.txt`
     (and the `_thirdparty` and `_specific` variants; check all of them)
2. Save them locally and `grep` completely, not via a tool that might
   truncate.
3. **Sanity-check before trusting any "not found" result**: confirm a
   known decade-old domain (e.g. `doubleclick.net`,
   `amazon-adsystem.com`) actually appears in the file you just grepped.
   If it doesn't, the file didn't download completely; fix that before
   concluding anything is a genuine gap.
4. Watch for near-misses / typos in the existing lists (e.g. the
   AdGuard DNS filter has `sb.scorecard.research.com`, an extra dot,
   which looks like it should cover `scorecardresearch.com` but is
   actually a different, non-matching domain). A near-miss is not
   coverage.

## 4. Judging a host

Every host that isn't covered gets one of these outcomes:

| Outcome | Where it goes |
|---|---|
| Ad-tech or tracking | Active `\|\|host^` rule in `blocklist.txt` |
| Infrastructure (CDN, fonts, video player, login, feature flags, payments, embeds, an advertiser's own site) | `[hosts]` in `gapcheck.toml`, `kind = "infrastructure"` |
| Consent platform | `[hosts]`, `kind = "cmp"` (or the site's `cmp` list) |
| Ad-tech, but deliberately not blocked | `[hosts]`, `kind = "infrastructure"`, note starting "Not blocked by decision (date): reason" |

Anything put in `[hosts]` stays out of future gapcheck runs, so every
entry needs a note saying what the host is.

**Identify a host before judging it.** The hostname is often not enough
(`prmutv.co`, `tq-tungsten.com`, random `cloudfront.net` hosts). Look at:

- the full request URLs (a path like `/v2.0/pxid` or `/collect/3pEvent`
  usually gives it away);
- which frame made the request, and that frame's parents. Requests
  from inside an ad frame (`*.safeframe.googlesyndication.com`, an
  `amazon-adsystem.com` frame) belong to the ad, not the site;
- the referer, and whether the request happens before or after the
  consent click. Anything that loads before consent and is needed to
  show the dialog is CMP, not tracking;
- the response body, for scripts and JSON.

**Choose the scope of the rule.**

- A parent rule (`||nodals.io^`, `||inventory.schibsted.io^`) only when
  the whole domain is ad-tech. It also collapses a growing subtree:
  gapcheck folds new hosts under an existing parent rule into it.
- A host-only rule whenever the same domain also serves something
  functional. Examples: `choices.trustarc.com` (TrustArc also runs a
  CMP, `consent.trustarc.com`, on other sites, so `||trustarc.com^`
  would break their Accept buttons); `impressions.onelink.me`
  (`onelink.me` also does app links); `tapet.bnek.bn.nr` (not
  `tapet-paywall.`).
- If the AdGuard DNS filter has an `@@` exception for the host, find
  out why before overriding it. `www.googleadservices.com` is let
  through because Google's sponsored search results redirect clicks
  through it; it stays unblocked by decision.

**Test before adding anything that might break a function** (video
players, payment buttons, embeds); see step 5. Such rules go in their
own documented section, not a site section, so they are easy to find
and comment out.

**Low-value gaps.** gapcheck surveys with unfiltered DNS, so it also
reports hosts that only load inside frames the AdGuard DNS filter
already blocks (the trustarc hosts on the Guardian load only inside
blocked ad frames). They are real gaps and cheap to add when the rule
is narrow, but they change little in practice.

## 5. Breakage testing

Test in the same container image gapcheck uses, so the browser and
codecs match (Playwright's Chromium in that image plays H.264):

1. **Baseline:** simulate today's blocking in the browser. Parse the
   raw AdGuard DNS filter and the current `blocklist.txt` (gapcheck's
   `FilterList` class does it) and abort every request to a blocked
   host from a `context.route` handler with `connectionrefused`, the
   same failure AdGuard Home's `0.0.0.0` answer causes.
2. **Variant:** the same plus the candidate rules.
3. Measure the function itself, not just the page load. For video:
   start playback and sample `currentTime` of every `<video>` element
   (in every frame) every few seconds; it must keep advancing in both
   runs. For consent: the Accept button must still be found and
   clicked.
4. Also record whether the candidate hosts were requested at all. A
   site that never requests them can't be affected.
5. Write the result into the section's comment: what was tested, how,
   on which date, and what wasn't tested.

Gotchas from the first tests (7 October 2026):

- Launch Chromium with `--autoplay-policy=no-user-gesture-required`,
  or players wait for a gesture.
- YouTube shows its own consent dialog, which pauses the video. Its
  "Godkänn alla" button has a long aria-label, so match the visible
  text, not the accessible name.
- Opening a YouTube embed URL directly fails with a player
  configuration error unless a referer is sent, as it would be from a
  real page.

## 6. Record the result

Each rule in `blocklist.txt` gets its own paragraph under the site
section where it was first seen:

```
! Added 2026-10-07 (gapcheck, reviewed), seen on Guardian, DN
! One-line reason: what the host is and why it's a gap
||host^
```

Hosts that were checked and found covered can be listed as comments
under the section's "Already covered elsewhere" block, with the rule
that covers them.

A site section header must keep the form `! Name — domain`, between two
`! ====` bars, with a `! Verified: <date>` line. gapcheck matches
sections on that domain and refuses to run on an unpaired bar. A
cross-site section (like the video-ad section) has no domain in its
header, so gapcheck never puts new rules there.

Filter lists change, so a site may be worth re-checking periodically
rather than assuming a past result still holds; gapcheck does this
weekly and comments out rules that upstream now covers.

## 7. Push and let AdGuard Home pick it up

If AdGuard Home is subscribed to this file's raw GitHub URL as a
blocklist (Filters → DNS blocklists), it refreshes on its own schedule.
To confirm immediately, use Filters → DNS blocklists → refresh, then
check Query Log while visiting the site to confirm the new domains show
up as blocked.
