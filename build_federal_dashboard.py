#!/usr/bin/env python3
"""Build edpa.html and nj_camden.html from JSON state files."""
import html as html_mod, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth_gate import inject_auth

HERE = Path(__file__).parent
DATA = HERE / "data"
ET_TZ = timezone(timedelta(hours=-4))

COURTS = {
    "edpa": {
        "title": "EDPA Federal Filings",
        "subtitle": "Eastern District of Pennsylvania",
        "state_file": "edpa_entries.json",
        "out_file": "edpa.html",
    },
}

TABS = [
    ("criminal", "indictments", "Indictments"),
    ("criminal", "complaints",  "Complaints"),
    ("criminal", "pleas",       "Pleas"),
    ("criminal", "sentencing",  "Sentencing"),
    ("criminal", "forfeiture",  "Forfeiture"),
    ("criminal", "warrants",    "Warrants"),
    ("civil",    "complaints",  "New Complaints"),
    ("civil",    "tro",         "TROs & Injunctions"),
    ("civil",    "opinions",    "Opinions & Orders"),
    ("civil",    "show_cause",  "Show Cause"),
    ("civil",    "sanctions",   "Sanctions"),
    ("civil",    "seal",        "Seal / Unseal"),
]


def esc(s):
    return html_mod.escape(str(s or ""))


def fmt_dt(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d, %H:%M")
    except Exception:
        return iso[:16]


def cl_url(case_num: str, court: str = "paed") -> str:
    return "https://www.courtlistener.com/?" + urlencode({"type": "r", "court": court, "docket_number": case_num})


def strip_case_prefix(title: str, case_num: str) -> str:
    """Remove redundant leading case number from caption."""
    if title.startswith(case_num):
        return title[len(case_num):].lstrip(" -—")
    return title


def build_tab_id(group, cat):
    return f"{group[:2]}-{cat}"


def build_table(entries):
    if not entries:
        return '<p class="empty">No entries in the last 30 days.</p>'
    rows = []
    for e in sorted(entries, key=lambda x: x.get("date", ""), reverse=True):
        caption = strip_case_prefix(e.get("title", ""), e.get("case_num", ""))
        entry_type = e.get("entry_type", "")
        filing_cell = esc(entry_type)
        if e.get("reopened"):
            filing_cell += ' <span class="badge-reopened">REOPENED</span>'
        rows.append(f"""<tr>
          <td class="date">{fmt_dt(e.get("date",""))}</td>
          <td class="case">{esc(e.get("case_num",""))}</td>
          <td class="filing">{filing_cell}</td>
          <td class="docnum">{esc(e.get("doc_num",""))}</td>
          <td class="caption">{esc(caption)}</td>
          <td class="link"><a href="{esc(e.get("link",""))}" target="_blank" rel="noopener">PACER</a></td>
          <td class="link"><a href="{esc(cl_url(e.get("case_num","")))}" target="_blank" rel="noopener">CL</a></td>
        </tr>""")
    return f"""<table>
      <thead>
        <tr>
          <th title="Date docketed in ECF; document's own date may differ">Entered</th>
          <th>Case No.</th>
          <th>Filing</th>
          <th>Doc #</th>
          <th>Caption</th>
          <th></th>
          <th></th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""


def build_page(court_key: str, info: dict) -> str:
    state_file = DATA / info["state_file"]
    all_entries = list(json.loads(state_file.read_text()).values()) if state_file.exists() else []
    updated = datetime.now(ET_TZ).strftime("%Y-%m-%d %H:%M ET")

    rows = {"criminal": [], "civil": []}
    tab_panels = []
    first = True

    for group, cat, label in TABS:
        tab_id = build_tab_id(group, cat)
        entries = [e for e in all_entries if e.get("group") == group and e.get("category") == cat]
        count = len(entries)

        active = " active" if first else ""
        badge = f" <span class='badge'>{count}</span>" if count else ""
        rows[group].append(
            f'<button class="tab{active}" data-tab="{tab_id}" onclick="showTab(this)">'
            f'{esc(label)}{badge}</button>'
        )
        display = "" if first else " style='display:none'"
        tab_panels.append(
            f'<div class="tab-panel" id="panel-{tab_id}"{display}>{build_table(entries)}</div>'
        )
        first = False

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(info["title"])} — Av's Tools</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Helvetica,Arial,sans-serif; background:#eef0f3; color:#1a1a2e; }}
  .header {{ background:#1a1a2e; color:white; padding:24px 32px; }}
  .header h1 {{ font-size:22px; font-weight:700; margin-bottom:4px; }}
  .header p {{ font-size:13px; opacity:0.75; }}
  .tab-bar {{ background:white; border-bottom:2px solid #ddd; }}
  .tab-row {{ display:flex; align-items:center; padding:0 16px; border-bottom:1px solid #f0f0f0; }}
  .tab-row:last-child {{ border-bottom:none; }}
  .group-label {{ font-size:11px; font-weight:700; text-transform:uppercase; color:#999; padding:0 12px 0 0; letter-spacing:.5px; min-width:68px; }}
  .tab {{ background:none; border:none; padding:14px 13px; font-size:13px; font-weight:500; color:#555; cursor:pointer; border-bottom:3px solid transparent; margin-bottom:-2px; white-space:nowrap; }}
  .tab:hover {{ color:#1a1a2e; }}
  .tab.active {{ color:#1a1a2e; border-bottom-color:#1a1a2e; font-weight:600; }}
  .badge {{ background:#c0392b; color:white; border-radius:10px; padding:1px 6px; font-size:11px; font-weight:700; margin-left:3px; }}
  .badge-reopened {{ background:#e67e22; color:white; border-radius:4px; padding:1px 5px; font-size:10px; font-weight:700; margin-left:5px; vertical-align:middle; }}
  .container {{ max-width:1200px; margin:24px auto; padding:0 16px; }}
  .updated {{ font-size:12px; color:#999; margin-bottom:12px; }}
  table {{ width:100%; border-collapse:collapse; background:white; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.08); font-size:13px; }}
  thead th {{ background:#f5f6f8; padding:10px 12px; text-align:left; font-size:11px; font-weight:600; color:#888; text-transform:uppercase; letter-spacing:.4px; cursor:default; }}
  tbody tr {{ border-top:1px solid #f0f0f0; }}
  tbody tr:hover {{ background:#fafbfc; }}
  td {{ padding:10px 12px; vertical-align:top; }}
  td.date {{ white-space:nowrap; color:#666; width:90px; }}
  td.case {{ white-space:nowrap; font-family:monospace; font-size:12px; width:130px; }}
  td.filing {{ font-weight:500; width:220px; }}
  td.docnum {{ color:#888; font-family:monospace; font-size:12px; width:50px; text-align:center; }}
  td.caption {{ color:#444; }}
  td.link {{ width:55px; text-align:center; }}
  td.link a {{ color:#1a1a2e; font-weight:600; font-size:12px; text-decoration:none; }}
  td.link a:hover {{ text-decoration:underline; }}
  .empty {{ color:#aaa; padding:40px; text-align:center; background:white; border-radius:8px; font-size:14px; }}
</style>
</head>
<body>
<div class="header">
  <h1>{esc(info["title"])}</h1>
  <p>{esc(info["subtitle"])}</p>
</div>
<div class="tab-bar">
  <div class="tab-row"><span class="group-label">Criminal</span>{"".join(rows["criminal"])}</div>
  <div class="tab-row"><span class="group-label">Civil</span>{"".join(rows["civil"])}</div>
</div>
<div class="container">
  <p class="updated">Updated {updated} &mdash; Source: PACER CM/ECF RSS · Check source material before publishing</p>
{"".join(tab_panels)}
</div>
<script>
function showTab(btn) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
  btn.classList.add('active');
  document.getElementById('panel-' + btn.dataset.tab).style.display = '';
}}
</script>
</body>
</html>"""


def main():
    for court_key, info in COURTS.items():
        page = inject_auth(build_page(court_key, info))
        out = HERE / info["out_file"]
        out.write_text(page)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
