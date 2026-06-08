#!/usr/bin/env python3
"""Poll PACER RSS feeds for EDPA and NJ-Camden, classify filings, update JSON state."""
import html as html_mod, json, re, subprocess, sys
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
BRACKET_RE = re.compile(r"^\s*\[([^\]]+)\]")
DOCNUM_RE  = re.compile(r">\s*(\d+)\s*</a>")

# --- Criminal classification (exact match only per spec) ---
CRIMINAL_EXACT = {
    "indictments": {"indictment", "superseding indictment", "information",
                    "superseding information", "felony information"},
    "complaints":  {"criminal complaint"},
    "pleas":       {"plea agreement", "change of plea", "guilty plea", "notice of change of plea"},
    "sentencing":  {"sentencing memorandum", "judgment in a criminal case"},
}
# contains-match for criminal (checked after exact)
CRIMINAL_CONTAINS = [
    ("forfeiture", "forfeiture"),
    ("warrants",   "warrant"),
]

# --- Civil classification — ORDER MATTERS (1→6 per spec) ---
CIVIL_COMPLAINTS_EXACT = {
    "complaint", "complaint (attorney)", "complaint (ifp or government plaintiff)",
    "notice of removal", "notice of removal (attorney)",
}

# Written opinions only — exact match, no motions, no plain orders
OPINIONS_EXACT = {
    "memorandum",
    "memorandum and/or opinion",
    "memorandum and/or opinion order",
}


def parse_description(raw_desc: str):
    """Return (entry_type, doc_num) from a raw RSS description string."""
    text = html_mod.unescape(raw_desc)
    m_type = BRACKET_RE.search(text)
    entry_type = m_type.group(1).strip() if m_type else ""
    m_doc = DOCNUM_RE.search(text)
    doc_num = m_doc.group(1).strip() if m_doc else ""
    return entry_type, doc_num


def classify_criminal(entry_type: str):
    t = entry_type.lower()
    for cat, exact_set in CRIMINAL_EXACT.items():
        if t in exact_set:
            return cat
    for cat, kw in CRIMINAL_CONTAINS:
        if kw in t:
            return cat
    return None



def classify_civil(entry_type: str, doc_num: str):
    t = entry_type.lower()

    # 1. New complaints — exact type + doc_num == "1"
    if t in CIVIL_COMPLAINTS_EXACT:
        if doc_num == "1":
            return "complaints", False
        return None, False  # complaint type but not docket-opening; drop

    # Case Reopened also belongs in complaints tab with reopened flag
    if t == "case reopened":
        return "complaints", True  # (category, reopened)

    # 2. TROs & Injunctions
    if "restraining order" in t or "preliminary injunction" in t:
        return "tro", False

    # 3. Show cause
    if "show cause" in t:
        return "show_cause", False

    # 4. Sanctions
    if "sanctions" in t:
        return "sanctions", False

    # 5. Seal / Unseal
    if "seal" in t:
        return "seal", False

    # 6. Written opinions only
    if t in OPINIONS_EXACT:
        return "opinions", False

    return None, False


def classify(case_num: str, entry_type: str, doc_num: str):
    criminal = bool(re.search(r":\d{2}-cr-", case_num, re.I))
    if criminal:
        cat = classify_criminal(entry_type)
        if cat:
            return "criminal", cat, False
        return None, None, False
    else:
        cat, reopened = classify_civil(entry_type, doc_num)
        if cat:
            return "civil", cat, reopened
        return None, None, False


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
    unclassified_types: dict[str, int] = {}

    for item in root.iter("item"):
        guid  = (item.findtext("guid") or "").strip()
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        pub   = (item.findtext("pubDate") or "").strip()
        raw_desc = (item.findtext("description") or "").strip()

        if not guid or guid in entries:
            continue

        entry_type, doc_num = parse_description(raw_desc)

        m = CASE_RE.search(title) or CASE_RE.search(link)
        if not m:
            continue

        case_num = m.group(0)
        division = m.group(1)

        if camden_only and division != "1":
            continue

        group, category, reopened = classify(case_num, entry_type, doc_num)
        if not group:
            if entry_type:
                unclassified_types[entry_type] = unclassified_types.get(entry_type, 0) + 1
            continue

        record = {
            "guid":       guid,
            "title":      title,
            "link":       link,
            "date":       parse_date(pub),
            "group":      group,
            "category":   category,
            "case_num":   case_num,
            "entry_type": entry_type,
            "doc_num":    doc_num,
        }
        if reopened:
            record["reopened"] = True
        entries[guid] = record
        new_count += 1

    cutoff = (datetime.now(ET_TZ) - timedelta(days=KEEP_DAYS)).isoformat()
    entries = {k: v for k, v in entries.items() if v.get("date", "") >= cutoff}
    path.write_text(json.dumps(entries, indent=2))
    print(f"{court_key}: +{new_count} new ({len(entries)} total kept)")
    if unclassified_types:
        print(f"  unclassified entry_types ({court_key}):", json.dumps(unclassified_types, indent=2))


def main():
    DATA.mkdir(exist_ok=True)
    poll("edpa", EDPA_URL)
    poll("nj_camden", NJD_URL, camden_only=True)


if __name__ == "__main__":
    main()
