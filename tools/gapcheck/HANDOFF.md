# Handoff: gapcheck: automated ad/tracker gap survey for site-adblock-gaps

*Written 2026-10-07 at the end of a claude.ai session, for Claude Code to pick up on rimmer.*

## Progress (2026-10-07, Claude Code session on Tobias's Mac)

All of this is on the `gapcheck` branch, pushed to `origin`. `main` is
untouched. Pick up at **task 2**; the Mac had no Podman, no systemd and only
Python 3.9, so tasks 2–5 have to happen on rimmer.

- **Task 1 done.** `tools/gapcheck/` is committed. `.gitignore` covers
  `blocklist.new.txt`, `tools/gapcheck/out/` and `tools/gapcheck/.venv/`.
- **`blocklist.txt` format checked.** Every rule is a bare `||host^` line
  with notes on separate `!` lines. There are no inline comments to convert.
- **Generator rewritten to keep site sections.** The old generator rebuilt
  the file as Observed / Retained / Now covered. That would have deleted the
  per-site sections, verification dates and reasons `AGENTS.md` requires.
  `build_blocklist` now edits `blocklist.txt` in place:
  - A new gap goes into the section of the first site (in `gapcheck.toml`
    order) that loaded it. It sits after that section's rules and before its
    "Already covered" notes, under `! NEW <date> (gapcheck), seen on …` and
    a reason line. The reason is the host's `[hosts]` note, otherwise `TODO`.
  - A site with no section (currently Aftonbladet and DN) gets a new one
    before the `[next site]` template, with `Verified: TODO`. Sections are
    matched on the domain in their header line against the site's `url` and
    `first_party`.
  - A rule now covered upstream is commented out where it stands.
  - Everything else is left untouched.
  - An unpaired `! ====` bar is an error (exit 1).
  - The run summary and `report.md` count the `TODO` lines left.
  - `README.md` describes this.
- **Generator tested, browser survey not.** Testing used the real
  `blocklist.txt` with synthetic verdicts and a stub enforced list:
  placement, new sections, comment-out and the excepted annotation all
  worked, and a second pass on the output produced no changes. The full
  tool (Playwright) has still **never run**.
- **`www.googleadservices.com` re-verified** against the raw AdGuard DNS
  filter (v1.0.82.9, 2026-10-07). The filter has `||googleadservices.com^`
  at line 10813 and `@@||www.googleadservices.com^|` at line 179092, so this
  host is a real gap. The file gives no reason for the exception. The likely
  reason is that www. also serves the click redirect for Google sponsored
  results (`/pagead/aclk`), which DNS blocking would break. Tobias still has
  to decide whether to add the rule; the first run will propose it with a
  `TODO` reason.
- **Still open:** tasks 2–6. Task 6 means `AGENTS.md` and
  `SURVEY_METHOD.md`; only the gapcheck README was updated.

## Background

Tobias runs **AdGuard Home** (DNS-level blocking) on the Proxmox VM `lister`
(snowmane, VM 101). Its enabled list is the **AdGuard DNS filter**
(`AdguardTeam/HostlistsRegistry` `assets/filter_1.txt`).

He reads svd.se, theguardian.com, aftonbladet.se and dn.se. SvD, the Guardian
and Aftonbladet use "consent or pay": rejecting tracking costs money (Schibsted
"annonsval" 39–49 kr/month, Guardian Ad-Lite €5/month), while "Accept all" is
free. His strategy is to click the free "Accept all", which is honest, and let
blocking neutralise the trackers that the consent nominally allows.

This repo, **`site-adblock-gaps`**, collects the hosts that the standard lists
miss:

- GitHub `wybotz/site-adblock-gaps`, MIT, SSH remote.
- Global git identity is `wybotz` with the GitHub noreply email.
- The repo holds `blocklist.txt`, `SURVEY_METHOD.md`, `AGENTS.md`, `README.md`
  and `.gitignore`.
- A few verified gap rules are also pasted into AdGuard Home's custom rules
  for now.
- The longer-term plan is to point AdGuard Home at the raw GitHub URL of
  `blocklist.txt`.

## Why this tool exists

Until now the survey ran as a weekly claude.ai **scheduled task** that drove a
browser. It needed site-permission approvals on every run, so it couldn't work
unattended. **That scheduled task is now paused.**

The replacement is `tools/gapcheck/`: a self-contained Python and Playwright
tool that runs on Tobias's own machine. It was written and tested in a cloud
sandbox that **could not reach the news sites**, so it has never run against
them.

## What gapcheck does (tools/gapcheck/)

| File | Purpose |
|---|---|
| `gapcheck.py` | The tool (stdlib + Playwright; Python ≥ 3.11 for `tomllib`) |
| `gapcheck.toml` | Config: sites, filter lists, consent labels, known hosts |
| `run.sh` | Cron wrapper (venv-based). **To be replaced by Podman Quadlet**, see below |
| `requirements.txt` | `playwright>=1.49`. **Pin this** to match the container image |
| `README.md` | Install/run/review docs (venv + cron version; needs updating) |

What a run does:

1. **DNS guard.** The run resolves `doubleclick.net` and `amazon-adsystem.com`.
   If either gives `0.0.0.0`/`::`, or doesn't resolve, it exits **2**. With
   filtered DNS, blocked scripts never load, and the hosts they would fetch
   are invisible.
2. **Lists.** It downloads every `[[filter_list]]` in full and parses
   `||domain^` rules and hosts-file entries. It honours `@@` exceptions,
   `$important` and `$badfilter`. Rules with paths or narrowing modifiers
   count only as "partial".
   - It aborts if the two sanity hosts aren't blocked by some list. An earlier
     survey once got false negatives from a summarising fetch tool, which is
     what this guards against.
   - `enforced = true` lists (only the AdGuard DNS filter) decide what is
     "covered".
   - `syntax = "dns"` applies AdGuard Home semantics: `$third-party`,
     `$script` and similar don't count.
   - The EasyPrivacy and EasyList files are **reference only**, reported as
     "browser lists".
3. **Survey.** Each `[[site]]` gets a fresh Playwright context, so no prior
   consent cookies.
   - It opens `url` and finds an exact-label "accept all" button **in any
     frame**, which handles cross-origin Sourcepoint iframes, then clicks it.
   - It waits for networkidle, scrolls in steps to trigger lazy ad slots and
     waits again.
   - Optionally it opens the first link matching `article_pattern` and repeats.
   - Every request hostname is recorded via `context.on("request")`, not
     `performance.getEntries`, whose buffer evicts entries.
   - It uses the full Chromium build (`channel="chromium"`, new headless mode)
     with "HeadlessChrome" removed from the user agent.
4. **Classify.** Each third-party host gets one verdict:
   - Hosts under `first_party`, plus the URL's own domain, are skipped, as are
     IP addresses.
   - **cmp:** hosts in the site's `cmp` list, the auto-detected frame host the
     Accept button lived in, or `[hosts]` entries with `kind="cmp"`.
   - **infrastructure:** `[hosts]` entries with `kind="infrastructure"`.
   - **covered:** blocked by an enforced list.
   - **excepted:** blocked, but an `@@` rule cancels it (as with
     `www.googleadservices.com`).
   - **gap:** none of the above.
5. **Output.**
   - `out/report.md` and `out/observations.json` are written on every run.
   - When the **set of active rules differs** from `blocklist.txt`, the run
     writes `../../blocklist.new.txt` and exits **3**. Otherwise it exits 0.
     It exits 1 on error.
   - The new list has three sections:
     - Observed this run (new rules marked `NEW`).
     - Retained but not seen this run, since ad slots rotate. Nothing is
       silently dropped.
     - Now covered upstream (commented out).
   - If `blocklist.txt` already holds a parent rule, such as
     `||inventory.schibsted.io^`, observed children fold into it.
   - Notes go on **their own `!` lines**, because adblock syntax has no inline
     comments.
6. **It never commits or pushes.** Tobias reviews the result with
   `git diff --no-index blocklist.txt blocklist.new.txt`.

### Tested in the sandbox

- **Real lists:** parsing the real lists reproduces the known findings. These
  are gaps:
  - `ads.inventory.schibsted.io`
  - `sb.scorecardresearch.com`
  - `launchpad.privacymanager.io`
  - `phx.bmtrcs.com`
  - `tapet.bnek.bn.nr`
  - `eu.klarnaevt.com`

  `www.googleadservices.com` comes out as excepted. These are covered:
  - `adsdk.microsoft.com`
  - `a.teads.tv`
  - `securepubads.g.doubleclick.net`
  - `cdn.id5-sync.com`
  - `collector.schibsted.io`
  - `cdn.brandmetrics.com`
- **Local mock site** (hostnames remapped with `launch_args`):
  - finding and clicking the accept button inside a cross-origin consent
    iframe, then CMP auto-detection;
  - scripts injected after consent;
  - a lazy image loaded by scrolling;
  - following an article link;
  - first-party exclusion;
  - generating `blocklist.new.txt`: add, drop as covered, and retain;
  - a second run with no change exits 0.

### Untested and likely to need fixing

- **Real sites.** The `article_pattern` regexes for all four sites are
  educated guesses.
- **Consent labels.** Known so far: "Godkänn alla" on SvD and Aftonbladet,
  "Accept all" on the Guardian. DN's is unknown.
- **First-party and CMP lists** per site (the config comments list what is
  known).
- **The format of the real `blocklist.txt`.** Only lines starting with
  `||host^` are read as rules. Check whether the existing file has inline
  `||host^ ! note` comments; if so, convert them to separate comment lines.
  This matters even outside gapcheck, because inline comments may also break
  rules pasted into AdGuard Home.

## Decided next step: run it as a rootless Podman container on rimmer

Decided in chat, not yet implemented. **rimmer** is Proxmox VM 102 on
snowmane: Ubuntu 26.04 "resolute", snap-free, GNOME, 2 cores, 4 GB RAM. Tobias
does not use auto-login.

The plan:

- Install rootless **Podman** from the Ubuntu archive (`sudo apt install
  podman`), plus `loginctl enable-linger tobias` so user units run without a
  login.
- Use the image `mcr.microsoft.com/playwright/python:vX.Y.Z-noble`. It bundles
  Chromium and its dependencies, which avoids Playwright's lack of 26.04
  dependency support. **Pin the tag and make `requirements.txt` match exactly**
  (`playwright==X.Y.Z`).
- Run it as a **one-shot container started by a systemd user timer**, not a
  long-running container. Use a Quadlet `.container` file in
  `~/.config/containers/systemd/` and a `.timer` for Mondays at 21:00 with
  `Persistent=true`.
- Give the container its **own DNS**, `9.9.9.10` (Quad9 unfiltered;
  `1.1.1.1` also works). That way rimmer itself stays behind AdGuard Home with
  no client exemption.
- Use `--shm-size=1g`, because Chromium crashes with the default 64 MB.
- Mount `~/dev/site-adblock-gaps` at `/work`, with `WorkingDir` set to
  `/work/tools/gapcheck`.
- Set `SuccessExitStatus=3` so that a run producing a new candidate list isn't
  treated as a failure.
- Logs go to `journalctl --user -u gapcheck`.
- Remove `run.sh` once this works, and rewrite the README's install/run
  sections for Podman.

Draft unit, to be verified against the installed Podman's Quadlet keys
(`DNS=` and the `ShmSize=` vs `PodmanArgs=` options differ by version):

```ini
[Unit]
Description=gapcheck ad-tracker survey

[Container]
Image=mcr.microsoft.com/playwright/python:vX.Y.Z-noble
Volume=%h/dev/site-adblock-gaps:/work
WorkingDir=/work/tools/gapcheck
Exec=python3 gapcheck.py
DNS=9.9.9.10
PodmanArgs=--shm-size=1g

[Service]
Type=oneshot
SuccessExitStatus=3
```

**Risk:** the router (Ubiquiti UCG Ultra) may redirect all port-53 traffic to
AdGuard. In that case the container's DNS is hijacked anyway. The DNS guard
catches this (exit 2), and the fix is a firewall/DNS exception for rimmer on
the UCG.

## Tasks for Claude Code

1. Place `tools/gapcheck/` in the repo if it isn't there already, and add
   `.gitignore` entries: `blocklist.new.txt`, `tools/gapcheck/out/`,
   `tools/gapcheck/.venv/`.
2. Set up Podman and the Quadlet units as above. Choose and pin the Playwright
   image tag and the matching `requirements.txt` version.
3. Run it once by hand (`systemctl --user start gapcheck`). Confirm the DNS
   guard passes inside the container.
4. Against the **real sites**, fix the article patterns, consent labels and
   first-party/CMP hosts. Record DN's real button text.
5. Inspect the first `blocklist.new.txt`. Every `NEW` host must be judged: if
   it is infrastructure (CDN, fonts, login, feature flags, payments), add it to
   `[hosts]` as `kind = "infrastructure"` instead.
6. Update `README.md`, `AGENTS.md` and `SURVEY_METHOD.md` to describe the tool
   and the review workflow.
7. Commit on a branch. **Do not push**; Tobias reviews first.

## Ground rules (from Tobias)

- Never log in to any surveyed site; no credentials of any kind. The only
  click allowed is the cookie-consent "accept" button.
- The tool never commits or pushes automatically. It only proposes
  `blocklist.new.txt`.
- Sites must stay configurable in `gapcheck.toml`, not hardcoded.
- Prefer clean, non-hacky solutions. Tobias pushes back on flawed analysis and
  expects the same rigour.
- Always grep complete, raw filter-list files. Never trust summarising fetch
  tools for coverage checks.

## Known state of the gap list (last manual survey, 5 Oct 2026)

Use this to sanity-check the first real run.

**Genuine gaps** (not blocked by the AdGuard DNS filter):

- **Schibsted ad-serving** (SvD, Aftonbladet), all under
  `inventory.schibsted.io`:
  - `ads.`
  - `cogwheel.`
  - `log.kcontent.`
  - `logreq.kcontent.`
  - `streams.kcontent.`
  - `alertory-cdn.`

  The subtree keeps growing, so consider one parent rule.
- `hasher.schibsted.com`, `ncis.schibsted.com` (Aftonbladet).
- `scorecardresearch.com` (Guardian). The filter only has the typo
  `sb.scorecard.research.com`.
- `www.googleadservices.com` (Guardian), cancelled by
  `@@||www.googleadservices.com^|`.
- `privacymanager.io` (Guardian header bidding).
- `bmtrcs.com` (SvD; a Brandmetrics host distinct from `brandmetrics.com`).
- `tapet.bnek.bn.nr`, `tapet-paywall.bnek.bn.nr` (DN).
- `sch-map.norstatsurveys.com` (Aftonbladet; Norstat survey/panel).
- Klarna hosts on DN: `eu.klarnaevt.com`, `osm.klarnaservices.com`,
  `js.klarna.com`, `x.klarnacdn.net`. The last two may be payment
  infrastructure; check that DN's subscribe flow survives blocking them.

**Infrastructure, never block:**

- `akamai.vgc.no`
- `esm.schibsted.tech`
- `unleash-edge.schibsted.tech`
- `session-service.login.schibsted.com`
- `cdn.stream.schibsted.media`
- `mediacdn.prenly.com`
- `time.akamai.com`
- Google Fonts

**CMP, never block:**

- `cmp.svd.se`, `cm.svd.se`
- `sourcepoint.theguardian.com`, `cdn.privacy-mgmt.com`
- `cmp.aftonbladet.se`, `cm.aftonbladet.se`
- `cmp.bonniernews.se`

**Correction to earlier surveys:** earlier surveys counted a host as covered if
*EasyPrivacy* blocked it. AdGuard Home doesn't subscribe to EasyPrivacy, so
gapcheck only counts the AdGuard DNS filter. A few hosts previously marked
"covered" may therefore come out as gaps. That is expected, not a regression.
