#!/usr/bin/env python3
"""Poll PACER RSS feeds for EDPA and NJ-Camden, classify filings, update JSON state."""
import json, re, subprocess, sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

DATA = Path(__file__).parent / "data"
ET_TZ = timezone(timedelta(hours=-4))
KEEP_DAYS = 30

EDPA_URL = "https://ecf.paed.uscourts.gov/cgi-bin/rss_outside.pl"
NJD_URL  = "https://ecf.njd.uscourts.gov/cgi-bin/rss_outside.pl"

CASE_RE = re.compile(r"(\d+):(\d{2})-([a-z]+)-(\d+)", re.I)

CRIMINAL_RULES = [
    ("indictments", ["indictment"]),
    ("complaints",  ["criminal complaint"]),
    ("pleas",       ["plea agreement", "guilty plea", "plea of guilty", "change of plea"]),
    ("sentencing",  ["sentencing memorandum", "position re: sentencing",
                     "position regarding sentencing"]),
    ("forfeiture",  ["forfeiture"]),
    ("warrants",    ["arrest warrant", "search warrant", " warrant"]),
]

CIVIL_RULES = [
    ("tro",        ["temporary restraining order", " tro ", "preliminary injunction"]),
    ("opinions",   ["opinion", "memorandum opinion", "memorandum and order"]),
    ("show_cause", ["show cause"]),
    ("sanctions",  ["sanctions"]),
    ("seal",       ["motion to seal", "motion to unseal", "order to seal",
                    "order to unseal", "unseal"]),
    ("complaints", ["complaint", "notice of removal"]),
]

def classify(case_num: str, text: str):
    t = text.lower()
    criminal = bool(re.search(r":\d{2}-cr-", case_num, re.I))
    rules = CRIMINAL_RULES if criminal else CIVIL_RULES
    group = "criminal" if criminal else "civil"
    for cat, kws in rules:
        if any(kw in t for kw in kws):
            return (group, cat)
    return None

def parse_date(s: str) -> str:
    try:
        return parsedate_to_datetime(s).astimezone(ET_TZ).isoformat()
    except Exception:
        return s

def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}

def poll(court_key: str, url: str, camden_only: bool = False) -> None:
    path = DATA / f"{court_key}_entries.json"
    entries = load(path)

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "30",
             "-H", "User-Agent: Inquirer Newsroom agutman@inquirer.com", url],
            capture_output=True, timeout=35
        )
        root = ET.fromstring(result.stdout)
    except (subprocess.TimeoutExpired, ET.ParseError) as e:
        print(f"ERROR {court_key}: {e}", file=sys.stderr)
        return

    new_count = 0
    for item in root.iter("item"):
        guid  = (item.findtext("guid") or "").strip()
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        pub   = (item.findtext("pubDate") or "").strip()
        desc  = (item.findtext("description") or "").strip()

        if not guid or guid in entries:
            continue

        full_text = f"{title} {desc}"
        m = CASE_RE.search(full_text) or CASE_RE.search(link)
        if not m:
            continue

        case_num = m.group(0)
        division = m.group(1)

        if camden_only and division != "1":
            continue

        result = classify(case_num, full_text)
        if not result:
            continue

        group, category = result
        entries[guid] = {
            "guid": guid,
            "title": title,
            "link": link,
            "date": parse_date(pub),
            "group": group,
            "category": category,
            "case_num": case_num,
        }
        new_count += 1

    cutoff = (datetime.now(ET_TZ) - timedelta(days=KEEP_DAYS)).isoformat()
    entries = {k: v for k, v in entries.items() if v.get("date", "") >= cutoff}
    path.write_text(json.dumps(entries, indent=2))
    print(f"{court_key}: +{new_count} new ({len(entries)} total kept)")

def main():
    DATA.mkdir(exist_ok=True)
    poll("edpa", EDPA_URL)
    poll("nj_camden", NJD_URL, camden_only=True)

if __name__ == "__main__":
    main()
