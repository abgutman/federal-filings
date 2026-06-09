# federal-filings

EDPA federal court RSS filings tracker. Polls the PACER CM/ECF public RSS feed hourly, classifies docket entries, and builds a password-gated GitHub Pages dashboard.

**NJ-Camden is disabled** — the feed produced only 1 entry over 30 days and was removed (2026-06-08). The poll function remains in `poll_federal_rss.py` but is not called from `main()`. Re-enabling is a one-line change.

## Live dashboard

`https://abgutman.github.io/federal-filings/edpa.html` — password: `avstools2026`

## How it works

- `poll_federal_rss.py` — fetches EDPA RSS, classifies entries by bracketed entry_type, appends to `data/edpa.json`
- `build_federal_dashboard.py` — reads JSON, renders password-gated HTML dashboard
- GitHub Actions runs both hourly (`.github/workflows/poll.yml`), commits changed files, pushes to Pages

## Feed structure

Each RSS item has: `<title>` (case caption only), `<description>` (`[Entry Type] (<a>DOC#</a>)`), `<pubDate>` (ECF docket time — not the document's filing date). Nature of suit is not in the feed.

See `REBUILD_SPEC.md` for full classification rules and dashboard column spec.
