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
- `out/gapcheck.log`: the cron log.

## Install on rimmer (Ubuntu 26.04)

The script lives in the repo at `tools/gapcheck/`, so clone the repo on rimmer:

```bash
git clone git@github.com:wybotz/site-adblock-gaps.git ~/dev/site-adblock-gaps
cd ~/dev/site-adblock-gaps/tools/gapcheck
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
chmod +x run.sh
```

Skip `--with-deps` on the last step. It only knows the apt package names for
supported LTS releases, and rimmer already has a full GNOME desktop, so
Chromium's libraries are in place. If Chromium fails to start, list what's
missing and install those packages with apt:

```bash
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome | grep 'not found'
```

## Exempt rimmer from AdGuard Home filtering

This step is required. If rimmer's DNS goes through AdGuard Home with
filtering on, the blocked ad scripts never load. Everything *they* would have
fetched is then invisible, which hides exactly the hosts you're looking for.
The script checks this first and stops with exit code 2.

In AdGuard Home, add rimmer's IP as a persistent client
(*Settings → Client settings*) and turn filtering off for that client only. The
trade-off is that rimmer's own browsing goes unfiltered.

## Run

```bash
./run.sh                                  # what cron runs
.venv/bin/python gapcheck.py --help
```

Cron (`crontab -e` as tobias), Mondays at 21:00:

```
0 21 * * 1  $HOME/dev/site-adblock-gaps/tools/gapcheck/run.sh
```

`run.sh` prints output only on changes or errors.

## Review a new candidate list

```bash
cd ~/dev/site-adblock-gaps
less tools/gapcheck/out/report.md
git diff --no-index blocklist.txt blocklist.new.txt
mv blocklist.new.txt blocklist.txt && git commit -am "gapcheck: update" && git push
```

Before committing, judge every `NEW` rule. If a new host is really a CDN or
another piece of infrastructure, add it to `[hosts]` in `gapcheck.toml` with
`kind = "infrastructure"` and delete the rule. It won't come back.

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
