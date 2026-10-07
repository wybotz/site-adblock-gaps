# gapcheck

Surveys news sites in a headless browser and finds the ad/tracking hosts that
AdGuard Home's filter lists don't block. It writes a candidate
`blocklist.new.txt` for you to review. It never commits or pushes anything.

## How it works

1. **Browse.** Each site in `gapcheck.toml` opens in a fresh, logged-out
   Chromium profile. The script clicks the cookie wall's "accept all" button
   (every frame is searched, so Sourcepoint-style consent iframes work),
   scrolls to trigger lazy ad slots, and optionally follows one article link.
   Every network request is recorded.
2. **Check coverage.** The filter lists are downloaded in full every run and
   parsed. A run aborts if `doubleclick.net` or `amazon-adsystem.com` isn't
   found, since that means the download or the parser is broken. The check
   honours `@@` exceptions, `$important` and `$badfilter`. Lists marked
   `enforced = true` (the ones AdGuard Home actually uses) decide what counts
   as a gap. The others are shown for reference only.
3. **Diff.** The results are compared with the reviewed `blocklist.txt`.
   The candidate `blocklist.new.txt` is that same file with minimal edits, so
   its per-site sections, verification dates and reasons survive:
   - a new gap goes into the section of the first site (in `gapcheck.toml`
     order) it was seen on. It sits after that section's rules and before
     its "Already covered" notes, under a `! NEW <date>` line and a reason
     line. The reason is the host's `note` from `[hosts]` if it has one,
     otherwise `TODO`;
   - a site with no section gets a new one before the `[next site]`
     template, with `Verified: TODO`. Sections are matched on the domain in
     their header line (`! Name — domain`) against the site's `url` and
     `first_party`;
   - a rule now covered upstream is commented out where it stands, with the
     covering rule noted;
   - everything else is left untouched, including rules not seen this run,
     since ad slots rotate.

   If the rule set changed, `blocklist.new.txt` is written and the exit code
   is 3.

Outputs:

- `out/report.md`: every third-party host with its verdict.
- `out/observations.json`: raw data.
- The run summary goes to the journal (`journalctl --user -u gapcheck`).

## Install on rimmer (Ubuntu 26.04)

gapcheck runs as a one-shot rootless Podman container, started weekly by a
systemd user timer. The image is the official Playwright image, which bundles
Chromium and its libraries, plus the pinned `playwright` package from
`requirements.txt` (see `Containerfile`). Keep the image tag and the
`requirements.txt` pin in step.

```bash
sudo apt install podman
loginctl enable-linger            # run user units without being logged in
git clone git@github.com:wybotz/site-adblock-gaps.git ~/dev/site-adblock-gaps
cd ~/dev/site-adblock-gaps/tools/gapcheck/quadlet
mkdir -p ~/.config/containers/systemd ~/.config/systemd/user
cp gapcheck.build gapcheck.container ~/.config/containers/systemd/  # Quadlet
cp gapcheck.timer ~/.config/systemd/user/                         # plain systemd
systemctl --user daemon-reload
systemctl --user enable --now gapcheck.timer
```

The units in `quadlet/`:

- `gapcheck.build` builds `localhost/gapcheck` from `Containerfile`. It runs
  before every survey, and the layer cache makes it near-instant.
- `gapcheck.container` mounts the repo at `/work` and runs
  `python3 gapcheck.py` in `tools/gapcheck`. Exit code 3 (new candidate list)
  counts as success.
- `gapcheck.timer` runs the survey on Mondays at 21:00 Swedish time. `Persistent=true`
  catches up on a run missed while rimmer was off.

After editing a unit in the repo, copy it again and run
`systemctl --user daemon-reload`.

## DNS: the container uses its own resolver

The container resolves through `9.9.9.10` (Quad9, unfiltered), so rimmer
itself can stay behind AdGuard Home. Filtered DNS would hide the very hosts
this tool looks for: blocked ad scripts never load, so nothing *they* fetch is
seen. The script checks this first and stops with exit code 2 if
`doubleclick.net` or `amazon-adsystem.com` is sinkholed or doesn't resolve.
If that happens, the router is probably redirecting port 53 to AdGuard Home,
and rimmer needs a DNS exception on the UCG.

## Run

```bash
systemctl --user start gapcheck          # one survey now (takes ~4 minutes)
journalctl --user -u gapcheck -e         # its output
systemctl --user list-timers gapcheck    # next scheduled run
```

## Review a new candidate list

```bash
cd ~/dev/site-adblock-gaps
less tools/gapcheck/out/report.md
git diff --no-index blocklist.txt blocklist.new.txt
mv blocklist.new.txt blocklist.txt && git commit -am "gapcheck: update" && git push
```

Before committing, judge every `NEW` rule; `../../SURVEY_METHOD.md`,
"Judging a host", has the decision rules. If a new host is really a CDN or
another piece of infrastructure, add it to `[hosts]` in `gapcheck.toml` with
`kind = "infrastructure"` and delete the rule. It won't come back. The same
goes for ad-tech you decide not to block: `kind = "infrastructure"`, with a
note starting "Not blocked by decision (date)" that says why.

Replace every `TODO` line with a real one-line reason or verified date, as
`AGENTS.md` requires. The run summary and `report.md` count the `TODO`
lines still left.

## Configure

`gapcheck.toml` holds the sites, filter lists, consent button labels and
known hosts. Every option is commented in the file.

To add a site, append a `[[site]]` block with:

- `name` and `url`;
- optionally `article_pattern`, a regex for article links;
- `first_party`, the site's own domains.

Collapsing a growing subtree works through the reviewed list itself. Put a
parent rule such as `||inventory.schibsted.io^` in `blocklist.txt`, and new
hosts under it are folded into that rule instead of being listed one by one.
