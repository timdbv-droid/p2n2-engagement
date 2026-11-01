# P2N2 Creator Workspace: free automatic song engagement

This is a **zero-paid-service replacement** for the previous Apify-based collector. It keeps your existing local relationship workspace and adds a scheduled dashboard for public P2N2 song statistics.

## The important limitation

The code is complete and tested against offline fixtures, but **a live Suno collection has not yet been verified**. Suno's public pages and their undocumented endpoints are liable to change, restrict traffic, or require login. If the collector cannot retrieve counts for your public songs, it deliberately fails instead of showing made-up numbers. It can also discover only a subset of the public catalogue, which the dashboard labels as partial/unverified.

**Terms:** Suno's Terms of Service, revised August 2026, prohibit automated scraping and similar extraction. This project is a proof of concept and using it may violate those terms. It contains no credentials, login automation, proxy rotation, CAPTCHA bypass, or access-control circumvention. Do not use it if Suno disallows your access.

## How it works

* Reads public song IDs from the Suno P2N2 profile, trying the public profile response first, followed by public page HTML when necessary. Five verified public song IDs are included in `data/known_public_songs.json` to help bootstrap discovery.
* Requests each discovered song's publicly accessible metadata for title, owner, visibility, comments, upvotes and plays. Every song must identify `p2n2` as its creator; explicitly private or hidden songs are discarded.
* Never substitutes zero for an unavailable count. If comment counts are missing or too many song requests fail, it retains the previous snapshot.
* Writes `data/engagement.json` and 365 daily records in `data/history.json`; the dashboard displays them and can export CSV.
* GitHub Actions runs it at **07:17 UTC daily** and republishes a static dashboard, requiring no paid provider or API key.

## Free setup

1. Create a **public GitHub repository**, such as `p2n2-engagement`. Upload the *contents* of this folder to its `main` branch, including the hidden `.github/workflows/collect.yml` folder. Only public song counts and fictional relationship examples are committed. Your actual relationship notes are not uploaded by the page.
2. In the repository, go to **Settings → Pages** and select **GitHub Actions** as the build and deployment source.
3. Upload the project files to `main`. That push automatically attempts the first collection and publishes the dashboard. You can also go to **Actions → Collect and publish public P2N2 engagement → Run workflow** to retry.
4. Open **Actions** to inspect the first run. The dashboard is published even if Suno blocks collection, in which case it honestly says that counts are not yet available and the run is marked failed. The GitHub Pages URL appears under **Settings → Pages** or the deployment summary. Subsequent daily runs update the snapshot when collection succeeds.

GitHub Actions is free on public repos with standard runners. No Apify account, token, credentials, or subscription is needed. Daily scheduled jobs may run late or be paused when GitHub considers the repository inactive.

### Run locally (optional)

Python 3.10+ only, no packages to install:

```bash
python -m unittest discover -s tests -v
python collect.py
python -m http.server 8000
```

Open `http://localhost:8000` to inspect the dashboard. To run an offline parser test with example data, use `python collect.py --fixture path/to/sample.json`, but **be aware this rewrites the local snapshot with sample values**, so only do it on a test copy.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Combined dashboard and relationship workspace |
| `collect.py` | Direct public metadata collector with validation |
| `.github/workflows/collect.yml` | Free scheduled collection and Pages publication |
| `data/known_public_songs.json` | Five verified public song IDs for initial discovery |
| `data/engagement.json` | Latest verified snapshot, initially empty |
| `data/history.json` | Dated snapshots |
| `tests/test_collect.py` | Offline parser and data validation tests |

## Troubleshooting

* **403 / 429 / blocked:** Stop collection; do not bypass the restriction. A previous snapshot remains available.
* **Missing comment counts:** Endpoint response may have changed, or the counts may no longer be accessible publicly. The workflow fails without publishing invented statistics.
* **Only five songs:** Public profile discovery failed and the collector could read only the five known IDs. This is **not an all-time top-five ranking**. The dashboard warns about unverified catalogue coverage.
* **Different numbers than Suno UI:** Public counters may be cached or updated at different times. The collector records what the public response supplied, not verified unique listeners.

The originally connected Suno MCP plugin is unaffected.

## Deployment status

The setup is **not yet hosted**. The GitHub repository must be created in your account, its files uploaded, and Pages set to GitHub Actions. This archive is deployment-ready, not an already deployed live dashboard.
