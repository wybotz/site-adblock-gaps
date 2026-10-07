#!/usr/bin/env python3
"""gapcheck — find ad/tracking hosts that your AdGuard Home filter lists miss.

For every site in the config it:
  1. opens the site in a fresh, logged-out headless Chromium,
  2. clicks the cookie wall's "accept all" button (searching every frame,
     so third-party consent iframes such as Sourcepoint work),
  3. scrolls to trigger lazy-loaded ad slots, optionally follows one article
     link, and records the hostname of every network request the page made,
  4. checks each third-party host against the real, fully downloaded filter
     lists, honouring @@ exceptions, $important and $badfilter,
  5. writes a report and, if the set of rules changed, a new candidate
     blocklist next to your current one for you to review and commit. The
     candidate is the current list with minimal edits: new rules land in
     their site's section, rules now covered upstream are commented out.

It never pushes or commits anything.

Exit codes: 0 = no change, 3 = new blocklist written (changes to review),
            2 = DNS is filtered (results would be incomplete), 1 = error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import re
import socket
import sys
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

EXIT_OK, EXIT_ERROR, EXIT_DNS_FILTERED, EXIT_CHANGED = 0, 1, 2, 3

SANITY_HOSTS = ("doubleclick.net", "amazon-adsystem.com")

# Modifiers that don't narrow a domain rule in practice (for a third-party host).
BROWSER_FULL_OPTS = {"third-party", "3p", "~first-party", "important", "all"}
# AdGuard Home only understands a handful of modifiers; anything else makes the
# rule client/type-specific or unsupported at the DNS level.
DNS_FULL_OPTS = {"important", "all"}
COSMETIC_MARKERS = ("##", "#@#", "#?#", "#$#", "#%#", "$$", "#@$#")
NULL_IPS = {"0.0.0.0", "127.0.0.1", "::", "::1"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[gapcheck] {msg}", file=sys.stderr, flush=True)


def host_of(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def parents(host: str) -> list[str]:
    """host itself plus every parent domain with at least two labels."""
    labels = host.split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def registrable(host: str) -> str:
    """Rough eTLD+1, good enough for grouping and first-party defaults."""
    labels = host.split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in {
        "co", "com", "org", "net", "ac", "gov", "edu"
    }:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def under(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def sort_key(host: str):
    return list(reversed(host.split(".")))


# --------------------------------------------------------------------------
# Filter-list parsing
# --------------------------------------------------------------------------

@dataclass
class Rule:
    text: str
    important: bool = False
    exact: bool = False  # hosts-file entries match only that exact host


@dataclass
class FilterList:
    name: str
    url: str
    enforced: bool
    syntax: str  # "dns" or "browser"
    lines: int = 0
    blocks: dict[str, Rule] = field(default_factory=dict)
    exceptions: dict[str, Rule] = field(default_factory=dict)
    partials: dict[str, str] = field(default_factory=dict)

    def parse(self, text: str) -> None:
        full_opts = DNS_FULL_OPTS if self.syntax == "dns" else BROWSER_FULL_OPTS
        badfiltered: set[str] = set()
        for raw in text.splitlines():
            self.lines += 1
            line = raw.strip()
            if not line or line[0] in "![" or any(m in line for m in COSMETIC_MARKERS):
                continue
            if line.startswith("#"):
                continue
            # hosts-file syntax: "0.0.0.0 host"
            parts = line.split()
            if len(parts) >= 2 and parts[0] in NULL_IPS:
                h = parts[1].lower()
                if h not in ("localhost", "0.0.0.0") and "." in h:
                    self.blocks.setdefault(h, Rule(line, exact=True))
                continue
            exception = line.startswith("@@")
            body = line[2:] if exception else line
            if not body.startswith("||"):
                continue  # regex, |http…, plain paths: not domain rules
            pattern, _, optstr = body[2:].partition("$")
            opts = {o.strip().lower() for o in optstr.split(",") if o.strip()} if optstr else set()
            m = re.match(r"([a-z0-9.\-_]+)(.*)$", pattern, re.I)
            if not m:
                continue
            domain, rest = m.group(1).lower().strip("."), m.group(2)
            if "." not in domain:
                continue
            if "badfilter" in opts:
                badfiltered.add(domain)
                continue
            whole_domain = rest in ("^", "^|", "", "|")
            narrowing = opts - full_opts
            if not whole_domain or narrowing:
                if not exception:
                    self.partials.setdefault(domain, line)
                continue
            rule = Rule(line, important="important" in opts)
            target = self.exceptions if exception else self.blocks
            target.setdefault(domain, rule)
        for d in badfiltered:
            self.blocks.pop(d, None)

    def check(self, host: str) -> tuple[str, str | None]:
        """Return (status, rule) with status in blocked/excepted/partial/none."""
        cands = parents(host)
        block = next(((d, self.blocks[d]) for d in cands
                      if d in self.blocks and (not self.blocks[d].exact or d == host)), None)
        exc = next(((d, self.exceptions[d]) for d in cands if d in self.exceptions), None)
        if block and exc and not (block[1].important and not exc[1].important):
            return "excepted", f"{block[1].text}  but  {exc[1].text}"
        if block:
            return "blocked", block[1].text
        partial = next((self.partials[d] for d in cands if d in self.partials), None)
        if partial:
            return "partial", partial
        return "none", None


def load_lists(cfg: dict) -> list[FilterList]:
    lists = []
    for entry in cfg["filter_list"]:
        fl = FilterList(
            name=entry["name"], url=entry["url"],
            enforced=bool(entry.get("enforced", False)),
            syntax=entry.get("syntax", "dns" if entry.get("enforced") else "browser"),
        )
        log(f"downloading {fl.name}")
        req = urllib.request.Request(fl.url, headers={"User-Agent": "gapcheck"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            fl.parse(resp.read().decode("utf-8", errors="replace"))
        log(f"  {fl.lines} lines, {len(fl.blocks)} domain blocks, "
            f"{len(fl.exceptions)} exceptions")
        lists.append(fl)
    enforced = [fl for fl in lists if fl.enforced]
    if not enforced:
        raise SystemExit("config error: no [[filter_list]] has enforced = true")
    # Sanity check: decade-old staples must be found, or the download/parse is broken.
    for h in SANITY_HOSTS:
        if not any(fl.check(h)[0] == "blocked" for fl in lists):
            raise RuntimeError(f"sanity check failed: {h} not blocked by any list — "
                               "download truncated or parser broken; refusing to report gaps")
    return lists


# --------------------------------------------------------------------------
# DNS check
# --------------------------------------------------------------------------

def dns_is_filtered(probe_hosts) -> str | None:
    for h in probe_hosts:
        try:
            addrs = {ai[4][0] for ai in socket.getaddrinfo(h, 443)}
        except socket.gaierror:
            return f"{h} does not resolve"
        if addrs & NULL_IPS:
            return f"{h} resolves to {sorted(addrs & NULL_IPS)}"
    return None


# --------------------------------------------------------------------------
# Browsing
# --------------------------------------------------------------------------

@dataclass
class SiteResult:
    name: str
    visited: list[str] = field(default_factory=list)
    consent: str | None = None          # label clicked
    consent_host: str | None = None     # frame host the button lived in
    requests: int = 0
    hosts: dict[str, set[str]] = field(default_factory=dict)  # host -> resource types
    errors: list[str] = field(default_factory=list)


def click_consent(page, labels, timeout_s: float):
    rx = re.compile(r"^\s*(?:" + "|".join(re.escape(l) for l in labels) + r")\s*$", re.I)
    deadline = dt.datetime.now() + dt.timedelta(seconds=timeout_s)
    while dt.datetime.now() < deadline:
        for frame in page.frames:
            try:
                btn = frame.get_by_role("button", name=rx)
                if btn.count() and btn.first.is_visible():
                    label = btn.first.inner_text().strip()
                    btn.first.click(timeout=5000)
                    return label, host_of(frame.url)
            except Exception:
                continue  # frame detached or not ready; try again next round
        page.wait_for_timeout(500)
    return None, None


def settle(page, bcfg) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=bcfg.get("settle_s", 8) * 1000)
    except Exception:
        pass
    for _ in range(bcfg.get("scroll_steps", 6)):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(1200)
    page.wait_for_timeout(bcfg.get("settle_s", 8) * 1000)


def survey_site(browser, site: dict, bcfg: dict) -> SiteResult:
    res = SiteResult(site["name"])
    ctx_args = dict(
        locale=bcfg.get("locale", "sv-SE"),
        timezone_id=bcfg.get("timezone", "Europe/Stockholm"),
        viewport=bcfg.get("viewport", {"width": 1366, "height": 900}),
    )
    if bcfg.get("user_agent"):
        ctx_args["user_agent"] = bcfg["user_agent"]
    ctx = browser.new_context(**ctx_args)  # fresh profile: no prior consent cookies

    def on_request(req):
        h = host_of(req.url)
        if h and not req.url.startswith(("data:", "blob:")):
            res.requests += 1
            res.hosts.setdefault(h, set()).add(req.resource_type)

    ctx.on("request", on_request)
    page = ctx.new_page()
    page.set_default_timeout(bcfg.get("page_timeout_s", 45) * 1000)
    try:
        page.goto(site["url"], wait_until="domcontentloaded")
        res.visited.append(page.url)
        res.consent, res.consent_host = click_consent(
            page, bcfg["consent_labels"], bcfg.get("consent_timeout_s", 15))
        if not res.consent:
            res.errors.append("no consent button found (already consented? new label?)")
        settle(page, bcfg)

        pattern = site.get("article_pattern")
        if pattern:
            rx = re.compile(pattern)
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            article = next((u for u in links if rx.search(u)), None)
            if article:
                page.goto(article, wait_until="domcontentloaded")
                res.visited.append(page.url)
                if not res.consent:  # some sites only show the wall on articles
                    res.consent, res.consent_host = click_consent(
                        page, bcfg["consent_labels"], bcfg.get("consent_timeout_s", 15))
                    if res.consent:
                        res.errors.pop()
                settle(page, bcfg)
            else:
                res.errors.append(f"no link matched article_pattern {pattern!r}")
    except Exception as e:
        res.errors.append(f"{type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        ctx.close()
    return res


def survey(cfg: dict) -> list[SiteResult]:
    from playwright.sync_api import sync_playwright

    bcfg = cfg["browser"]
    results = []
    with sync_playwright() as p:
        launch = dict(headless=bcfg.get("headless", True))
        if bcfg.get("channel"):
            launch["channel"] = bcfg["channel"]
        if bcfg.get("launch_args"):
            launch["args"] = bcfg["launch_args"]
        browser = p.chromium.launch(**launch)
        if bcfg.get("mask_headless_ua", True) and not bcfg.get("user_agent"):
            probe = browser.new_context()
            ua = probe.new_page().evaluate("navigator.userAgent")
            probe.close()
            bcfg["user_agent"] = ua.replace("HeadlessChrome", "Chrome")
        for site in cfg["site"]:
            log(f"surveying {site['name']} ({site['url']})")
            r = survey_site(browser, site, bcfg)
            log(f"  {r.requests} requests, {len(r.hosts)} hosts, consent={r.consent!r}"
                + (f", errors: {r.errors}" if r.errors else ""))
            results.append(r)
        browser.close()
    return results


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

@dataclass
class HostVerdict:
    host: str
    sites: set[str]
    kind: str            # gap / covered / excepted / infrastructure / cmp
    enforced_rule: str | None = None
    enforced_by: str | None = None
    reference: list[str] = field(default_factory=list)  # other lists that block it
    note: str = ""


def classify(results, cfg, lists) -> tuple[dict[str, HostVerdict], dict[str, str]]:
    known = {h.lower(): v for h, v in cfg.get("hosts", {}).items()}
    third_party: dict[str, set[str]] = {}
    auto_cmp: dict[str, str] = {}
    for site, r in zip(cfg["site"], results):
        first = set(site.get("first_party", [])) | {registrable(host_of(site["url"]))}
        cmp = set(site.get("cmp", []))
        if r.consent_host and not under(r.consent_host, first):
            cmp.add(r.consent_host)
            auto_cmp[r.consent_host] = r.name
        for h in r.hosts:
            if is_ip(h) or under(h, first) or under(h, cmp):
                continue
            third_party.setdefault(h, set()).add(r.name)

    verdicts = {}
    for h, sites in third_party.items():
        info = next((known[d] for d in parents(h) if d in known), {})
        v = HostVerdict(h, sites, "gap", note=info.get("note", ""))
        if info.get("kind") in ("infrastructure", "cmp"):
            v.kind = info["kind"]
        elif h in auto_cmp:
            v.kind = "cmp"
        if v.kind == "gap":
            excepted = None
            for fl in lists:
                status, rule = fl.check(h)
                if fl.enforced and status == "blocked" and not v.enforced_rule:
                    v.kind, v.enforced_rule, v.enforced_by = "covered", rule, fl.name
                elif fl.enforced and status == "excepted":
                    excepted = (rule, fl.name)
                elif not fl.enforced and status == "blocked":
                    v.reference.append(fl.name)
            if v.kind == "gap" and excepted:
                v.kind, v.enforced_rule, v.enforced_by = "excepted", *excepted
        verdicts[h] = v
    return verdicts, auto_cmp


# --------------------------------------------------------------------------
# Blocklist generation
#
# The reviewed blocklist.txt is organised by site: a "! ====" bar, a header
# ("! Name — domain", "! Verified: …"), a closing bar, then that site's rules,
# each with a hand-written reason. The candidate list is that same file with
# minimal edits, so a plain diff shows exactly what changed:
#   - a new gap goes into the section of the site it was seen on, with a dated
#     comment line and a reason to fill in;
#   - a site without a section gets a new one, before the "[next site]"
#     template if the file has one;
#   - a rule now covered upstream is commented out where it stands;
#   - everything else (rules not seen this run, notes, headers) is untouched.
# --------------------------------------------------------------------------

BAR_RX = re.compile(r"^!\s*={10,}\s*$")
RULE_RX = re.compile(r"^\|\|([a-z0-9.\-_]+)\^", re.I)
SECTION_DOMAIN_RX = re.compile(r"\s[—–-]\s*([a-z0-9.\-]+\.[a-z]{2,})\s*$", re.I)
COVERED_BLOCK_RX = re.compile(r"^!\s*Already covered", re.I)
REASON_TODO = "TODO: one-line reason before committing"
BAR = "! " + "=" * 69


def read_current_rules(path: Path) -> list[str]:
    """Domains of the active ||domain^ rules in the reviewed blocklist."""
    if not path.exists():
        log(f"current blocklist {path} not found — treating as empty")
        return []
    out = []
    for line in path.read_text().splitlines():
        m = RULE_RX.match(line.strip())
        if m:
            out.append(m.group(1).lower())
    return out


@dataclass
class Section:
    header: list[str]   # bar, header lines, bar
    body: list[str]     # everything up to the next section's opening bar
    domain: str | None  # from "! Name — domain" on the first header line

    @property
    def is_template(self) -> bool:
        return any("[next site]" in l for l in self.header)


def split_sections(lines: list[str]) -> tuple[list[str], list[Section]]:
    """Split the blocklist into a preamble and its site sections."""
    bars = [i for i, l in enumerate(lines) if BAR_RX.match(l.strip())]
    if len(bars) % 2:
        raise RuntimeError(f"blocklist has an unpaired '! ====' bar (line {bars[-1] + 1}); "
                           "every site header needs an opening and a closing bar")
    preamble, sections = lines[:bars[0]] if bars else lines[:], []
    for opening, closing in zip(bars[::2], bars[1::2]):
        end = next((b for b in bars if b > closing), len(lines))
        header = lines[opening:closing + 1]
        m = SECTION_DOMAIN_RX.search(header[1]) if len(header) > 2 else None
        sections.append(Section(header, lines[closing + 1:end], m.group(1).lower() if m else None))
    return preamble, sections


def insert_paragraph(body: list[str], block: list[str]) -> None:
    """Add a comment+rule paragraph after the section's rules, before its
    "Already covered" notes if it has them."""
    at = next((i for i, l in enumerate(body) if COVERED_BLOCK_RX.match(l)), None)
    if at is None:
        at = len(body)
        while at and not body[at - 1].strip():
            at -= 1
    para = block[:]
    if at == 0 or body[at - 1].strip():
        para.insert(0, "")
    if at >= len(body) or body[at].strip():
        para.append("")
    body[at:at] = para


def build_blocklist(verdicts, current, current_text, lists, cfg, run_date):
    enforced = [fl for fl in lists if fl.enforced]
    known = {h.lower(): v for h, v in cfg.get("hosts", {}).items()}

    def note_for(d):
        return next((known[p].get("note", "") for p in parents(d) if p in known), "")

    # Map every gap host to the rule that should block it: an existing (possibly
    # parent) rule from the current list if one covers it, else itself.
    observed_rules: dict[str, set[str]] = {}
    for v in verdicts.values():
        if v.kind not in ("gap", "excepted"):
            continue
        rule = next((c for c in current if under(v.host, [c])), v.host)
        observed_rules.setdefault(rule, set()).add(v.host)
    added = sorted(set(observed_rules) - set(current), key=sort_key)

    retained, now_covered = [], {}
    for d in current:
        if d in observed_rules:
            continue
        hit = next(((fl.name, fl.check(d)[1]) for fl in enforced if fl.check(d)[0] == "blocked"), None)
        if hit:
            now_covered[d] = hit
        else:
            retained.append(d)

    preamble, sections = split_sections(current_text.splitlines())

    # Rules now covered upstream: comment out in place, keeping their reason above.
    for part in [preamble] + [s.body for s in sections]:
        for i, line in enumerate(part):
            m = RULE_RX.match(line.strip())
            if m and m.group(1).lower() in now_covered:
                name, rule = now_covered[m.group(1).lower()]
                part[i] = (f"! {line.strip()}   -> now covered upstream ({name}: {rule}); "
                           f"disabled by gapcheck {run_date}")

    def section_for(site: dict) -> Section:
        own = set(site.get("first_party", [])) | {registrable(host_of(site["url"]))}
        sec = next((s for s in sections if s.domain and under(s.domain, own)), None)
        if sec:
            return sec
        domain = registrable(host_of(site["url"]))
        sec = Section([BAR, f"! {site['name']} — {domain}",
                       f"! Verified: TODO (section created by gapcheck {run_date})", BAR],
                      [""], domain)
        at = next((i for i, s in enumerate(sections) if s.is_template), len(sections))
        before = sections[at - 1].body if at else preamble
        if before[-1:] != [""]:
            before.append("")
        sections.insert(at, sec)
        return sec

    # New rules go into the section of the first configured site that saw them.
    sites_cfg = cfg["site"]
    order = {s["name"]: i for i, s in enumerate(sites_cfg)}
    for rule in added:
        hosts = sorted(observed_rules[rule], key=sort_key)
        sites = sorted(set().union(*(verdicts[h].sites for h in hosts)), key=order.__getitem__)
        block = [f"! NEW {run_date} (gapcheck), seen on {', '.join(sites)}"
                 + (f"; covers {', '.join(hosts)}" if hosts != [rule] else ""),
                 f"! {note_for(rule) or REASON_TODO}"]
        for h in hosts:
            v = verdicts[h]
            if v.kind == "excepted":
                block.append(f"!   {h}: looks blocked, but an @@ exception cancels it ({v.enforced_by})")
            if v.reference:
                block.append(f"!   {h}: blocked in browser lists only ({', '.join(v.reference)})")
        block.append(f"||{rule}^")
        insert_paragraph(section_for(sites_cfg[order[sites[0]]]).body, block)

    out = preamble + [l for s in sections for l in s.header + s.body]
    changes = {
        "added": added,
        "dropped": sorted(now_covered, key=sort_key),
        "not_seen": sorted(retained, key=sort_key),
        "todo": sum("TODO" in l for l in out if l.startswith("!")),
    }
    return "\n".join(out) + "\n", bool(added or now_covered), changes


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def build_report(run_date, results, verdicts, auto_cmp, changes, lists, dns_note):
    L = [f"# gapcheck report — {run_date}", ""]
    if dns_note:
        L += [f"> **DNS was filtered** ({dns_note}); requests that blocked scripts "
              "would have made are missing from this run.", ""]
    L += ["## Sites", "", "| Site | Consent clicked | Consent frame host | Requests | Hosts | Problems |",
          "|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r.name} | {r.consent or '—'} | {r.consent_host or '—'} | {r.requests} "
                 f"| {len(r.hosts)} | {'; '.join(r.errors) or ''} |")
    L += ["", "Visited:", *[f"- {r.name}: {', '.join(r.visited) or '—'}" for r in results], ""]
    if auto_cmp:
        L += ["Consent frames auto-detected and excluded as CMP hosts: "
              + ", ".join(f"{h} ({s})" for h, s in auto_cmp.items()), ""]
    L += ["## Changes vs current blocklist", ""]
    for k, title in (("added", "New gap rules"), ("dropped", "Now covered upstream (drop)"),
                     ("not_seen", "Retained, not seen this run")):
        L.append(f"- **{title}:** {', '.join(changes[k]) or 'none'}")
    if changes["todo"]:
        L.append(f"- **TODO lines in the candidate list:** {changes['todo']} "
                 "(new rules need a one-line reason, new sections a verified date)")
    L += ["", "## Every third-party host", "",
          "| Host | Sites | Verdict | Enforced rule | Browser lists | Note |", "|---|---|---|---|---|---|"]
    order = {"gap": 0, "excepted": 1, "covered": 2, "infrastructure": 3, "cmp": 4}
    for v in sorted(verdicts.values(), key=lambda v: (order[v.kind], sort_key(v.host))):
        L.append(f"| {v.host} | {', '.join(sorted(v.sites))} | {v.kind} | "
                 f"{('`' + v.enforced_rule + '`') if v.enforced_rule else ''} | "
                 f"{', '.join(v.reference)} | {v.note} |")
    L += ["", "Lists: " + "; ".join(
        f"{fl.name} ({'enforced' if fl.enforced else 'reference'}, {fl.lines} lines)" for fl in lists), ""]
    return "\n".join(L)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", default=Path(__file__).with_name("gapcheck.toml"), type=Path)
    ap.add_argument("--allow-filtered-dns", action="store_true",
                    help="run even if this machine's DNS blocks trackers (results will be incomplete)")
    args = ap.parse_args()

    cfg = tomllib.loads(args.config.read_text())
    base = args.config.resolve().parent
    out_cfg = cfg.get("output", {})
    out_dir = (base / out_cfg.get("dir", "out")).resolve()
    current_path = (base / out_cfg["current_blocklist"]).resolve()
    new_path = (base / out_cfg["new_blocklist"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_date = dt.date.today().isoformat()

    dns_note = dns_is_filtered(cfg.get("dns", {}).get("probe_hosts", SANITY_HOSTS))
    if dns_note and not args.allow_filtered_dns and cfg.get("dns", {}).get("require_unfiltered", True):
        log(f"DNS on this machine is filtered: {dns_note}. Exempt this machine in AdGuard Home "
            "(see README) or pass --allow-filtered-dns.")
        return EXIT_DNS_FILTERED

    try:
        lists = load_lists(cfg)
        results = survey(cfg)
    except Exception as e:
        log(f"error: {e}")
        return EXIT_ERROR
    if not any(r.hosts for r in results):
        log("error: no site produced any requests — network problem?")
        return EXIT_ERROR

    verdicts, auto_cmp = classify(results, cfg, lists)
    current = read_current_rules(current_path)
    current_text = current_path.read_text() if current_path.exists() else ""
    try:
        text, changed, changes = build_blocklist(verdicts, current, current_text, lists, cfg, run_date)
    except RuntimeError as e:
        log(f"error: {e}")
        return EXIT_ERROR
    report = build_report(run_date, results, verdicts, auto_cmp, changes, lists, dns_note)

    (out_dir / "report.md").write_text(report)
    (out_dir / "observations.json").write_text(json.dumps({
        "date": run_date,
        "sites": [{"name": r.name, "visited": r.visited, "consent": r.consent,
                   "consent_host": r.consent_host, "errors": r.errors,
                   "hosts": {h: sorted(t) for h, t in sorted(r.hosts.items())}} for r in results],
        "verdicts": {h: {"sites": sorted(v.sites), "kind": v.kind, "rule": v.enforced_rule,
                         "reference": v.reference} for h, v in sorted(verdicts.items())},
    }, indent=2))

    problems = [f"{r.name}: {e}" for r in results for e in r.errors]
    if changed:
        new_path.write_text(text)
        print(f"gapcheck {run_date}: CHANGES — new candidate list at {new_path}")
        print(f"  added:   {', '.join(changes['added']) or 'none'}")
        print(f"  dropped: {', '.join(changes['dropped']) or 'none'}")
        if changes["todo"]:
            print(f"  todo:    {changes['todo']} TODO line(s) to fill in before committing")
    else:
        print(f"gapcheck {run_date}: no change to the rule set")
    for p in problems:
        print(f"  problem: {p}")
    print(f"  report:  {out_dir / 'report.md'}")
    return EXIT_CHANGED if changed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
