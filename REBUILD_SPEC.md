# Federal RSS tracker — rebuild spec

Authored on Opus (2026-06-08) against live EDPA (497 items) + NJ (891 items) feeds.
Build target: Sonnet. **Transcribe these tables exactly. Do not invent or "improve" categories at build time** — if a type is missing here, leave it unclassified and log it, don't guess.

## Feed structure (ground truth)

Each `<item>` gives only:
- `<title>` — case caption ONLY (e.g. `2:26-cv-03911 LEE v. AAA INTERINSURANCE EXCHANGE`)
- `<description>` — `[Entry Type] (<a href="...">DOC#</a>)` — the bracket is the docket entry type; the link text is the document number
- `<pubDate>` — when the entry hit the feed = **ECF-entered time, NOT filing date**. There is no filing date in the feed.

**Nature of Suit / case type is NOT in the feed. Do not add a case-type column.** (Confirmed: 0 hits across 497 items.)

## Parsing (poll_federal_rss.py)

For each item, extract and STORE these new fields on every entry:
- `entry_type` — text inside the first `[...]` in description (unescape HTML entities first)
- `doc_num` — text of the first `<a>` tag in description (may be empty for some admin entries)

Keep existing fields: `guid`, `title`, `link`, `date` (from pubDate), `case_num`, plus add `group` and `category` from classification below.

Criminal vs civil switch: `:\d{2}-cr-` in case_num → criminal, else civil. (Reliable, keep as-is.)
NJ-Camden filter: keep `1:` division filter.

## Classification — match on `entry_type`, in the order listed

Matching is **case-insensitive**. "exact" = full string equals. "prefix" = entry_type starts with. "contains" = substring. First rule that matches wins; check rules top-to-bottom within the group.

### CRIMINAL (case_num contains `:YY-cr-`)

| category | rule | match strings |
|----------|------|---------------|
| indictments | exact | `Indictment`, `Superseding Indictment`, `Information`, `Superseding Information`, `Felony Information` |
| complaints | exact | `Criminal Complaint` |
| pleas | exact | `Plea Agreement`, `Change of Plea`, `Guilty Plea`, `Notice of Change of Plea` |
| sentencing | exact | `Sentencing Memorandum`, `Judgment in a Criminal Case` |
| forfeiture | contains | `forfeiture` |
| warrants | contains | `warrant` |

(Anything else criminal → unclassified, dropped from tabs but fine.)

### CIVIL (everything else) — ORDER MATTERS; check 1→6

**1. complaints (New Complaints tab)** — the docket-opening / reopening signal
- exact-match types: `Complaint`, `Complaint (Attorney)`, `Complaint (IFP or Government Plaintiff)`, `Notice of Removal`, `Notice of Removal (Attorney)`
- **AND** require `doc_num == "1"` (confirms it opens the docket). If a complaint type appears with doc_num != 1, leave unclassified.
- **PLUS** type exact `Case Reopened` → also goes in this tab (matches user's "reopening a docket" definition). Tag these with a `reopened: true` flag so the dashboard can badge them "REOPENED".
- These exact matches automatically exclude the false positives that broke the old build: `Amended Complaint`, `Answer to Complaint`, `Answer to Amended Complaint`, `Notice of Filing Short Form Complaint`, `Counterclaim`, `Crossclaim`, `Third Party Complaint`.

**2. tro (TROs & Injunctions)**
- contains any of: `restraining order`, `preliminary injunction`

**3. show_cause**
- contains: `show cause`

**4. sanctions**
- contains: `sanctions`

**5. seal (Seal / Unseal)**
- contains: `seal` (catches Seal, Unseal, Order on Motion to Seal, etc.)

**6. opinions (Opinions & Orders)** — substantive rulings; catch-all for orders NOT claimed above
- INCLUDE if entry_type contains `opinion` OR contains `memorandum` OR contains `summary judgment` OR starts with `Order`
- **THEN EXCLUDE (deny-list)** if entry_type is any of / starts with:
  - prefix `Order Referring`
  - prefix `Order Reassigning`
  - prefix `Procedural Order`
  - prefix `Pro Se` (admin orders)
  - exact `Order Returning Passport`
  - exact `Scheduling Order`
  - exact `Order for Probation`
  - exact `Stipulation and Order`
  - exact `Order on Motion to Continue`
  - exact `Order on Motion for Leave to File`
  - exact `Order on Motion for Leave to Proceed In Forma Pauperis`
  - exact `Order on Motion to Substitute Attorney`
  - contains `Pro Hac Vice`
  - contains `USCA` (Third Circuit orders/mandates, not this court's ruling)
- Net effect: keeps `Order`, `Memorandum`, `Memorandum and/or Opinion`, `Memorandum and/or Opinion Order`, `Order on Motion to Dismiss`, `Order on Motion for Summary Judgment`, `Order Dismissing Case`, etc. Drops referrals, reassignments, scheduling, pro-hac-vice, passport returns, appellate mandates.

> Why opinions is last: rules 2–5 (seal/show-cause/sanctions/tro) are also "Order on Motion for X" types. Checking them first prevents the broad opinions rule from swallowing them.

## Dashboard (build_federal_dashboard.py)

Table columns, left→right:
1. **Entered** — from `date`. Header tooltip/footnote: *"Entered = date docketed in ECF; the document's own date may differ."* (Do NOT label this "Filed".)
2. **Case No.** — `case_num`
3. **Filing** — `entry_type` (THIS is the fix for "useless" tables — every row now states what was filed)
4. **Doc #** — `doc_num`
5. **Caption** — `title` with the leading case number stripped (it's redundant with col 2)
6. **PACER** — link

New Complaints tab: render the `reopened: true` flag as a small `REOPENED` badge next to the filing.

Keep: two-row tab layout (Criminal / Civil), password gate via `inject_auth`, noindex, source line, 30-day retention.

## Verification (mandatory before declaring done — per CLAUDE.md)

Run poller against the live feed, then check:
1. New Complaints tab contains ONLY doc#=1 complaint/removal types + Case Reopened entries. No `Answer to`/`Amended`/`Short Form` leakage.
2. Opinions tab now includes plain `[Order]` and `[Memorandum]` entries (the ~9 the user said were missing) and EXCLUDES referrals/reassignments/scheduling/pro-hac-vice.
3. Every row in every tab shows a non-empty Filing (entry_type) value.
4. Spot-check 5 rows against the raw XML: entry_type and doc_num parsed correctly.
5. Print a count of unclassified entry_types seen (sanity — catch types we should add later).
