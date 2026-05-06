# Project status — propertykuatt

A capital-flow heatmap of NSW suburbs: track actual dollars committed
into each suburb (DA cost-of-works, CDCs, infrastructure spend) rather
than backwards-looking sales prices. Pilot footprint: Sydney CBD + 20km
radius, 18 LGAs.

## What's built

- `pipeline/schema.py` — canonical record schema every source normalises to.
  `categorise_with_id()` picks a category from free-text dev type, falling
  back to application-id prefix (CDP/CDC -> cdc, MOD -> A&A, LDA/DA -> other).
- `pipeline/sources/council_trackers/` — vendor-adapter framework over
  public council DA registers.
  - `base.py` — abstract `CouncilTrackerAdapter` with retry/backoff, polite
    delays, and a normalised `pull()` driver.
  - `registry.py` — all 18 Sydney 20km LGAs tagged by vendor platform
    (`t1_etrack`, `civica_authority`, `open_cities`, `custom`).
  - `t1_etrack.py` — **working** adapter for TechnologyOne eTrack. Walks
    canned period buckets (TW/LW/TM/LM/TY/LY), parses the results grid,
    follows __doPostBack to detail pages, extracts cost_of_works.
    Confirmed working against Ryde (32 rows / 30 days, $ values clean).
- `pipeline/sources/opendata_extract.py` — reader for the email-delivered
  NSW Planning Portal "Online DA / CDC Data API" CSVs. Drops them into
  `data/raw/nsw_opendata/` and the loader picks them up.
- `pipeline/geocode.py` — ABS SA2 point-in-polygon resolver. Needs the
  ASGS Ed.3 SA2 shapefile dropped into `data/raw/abs_sa2/` before use.
- `pipeline/aggregator.py` — rolls applications up to (sa2, quarter,
  category) totals and computes a per-period z-scored `flow_score`.
- `pipeline/cli.py` — three commands:
  - `scrape --council X --from YYYY-MM-DD --to YYYY-MM-DD`
  - `opendata --kind DA|CDC`
  - `aggregate`
  - `debug --council X` (one-shot reachability + selector dump)

## What's NOT built yet

- **Open Cities adapter** — would unlock City of Sydney, North Sydney,
  Willoughby, Woollahra, Waverley, Mosman in one shot. Most of these
  have a JSON endpoint behind their XC.Track search page; usually a
  shorter adapter than T1.
- **Civica Authority / ePathway adapter** — Inner West, Bayside,
  Canterbury-Bankstown, Georges River, Burwood, Strathfield, Canada Bay.
  Harder: session-based ASPX with extensive ViewState.
- **Custom adapter for Parramatta** (and any other one-offs).
- **NSW infrastructure spend layer** — manual project->SA2 mapping table
  built once from NSW Treasury budget papers + Transport for NSW project
  pages, then dollar amounts updated quarterly. Stub not yet started.
- **Heatmap visualisation** — choropleth render. Aggregator already
  produces the right output shape; just needs a renderer.

## Open data feed

The NSW Planning Portal "Online DA Data API" dataset on data.nsw.gov.au
is delivered via email subscription, not a direct download. Email the
data broker on the dataset page to request DA + CDC bulk extracts for
your LGAs. When CSVs arrive, drop them in `data/raw/nsw_opendata/` and
run `python -m pipeline.cli opendata --kind DA`.

## Why we abandoned the v2 service API

The keyed APIs at `dpie-apim-prod.redocly.app/openapi/...` are
push-only webhooks — DPE pushes case data INTO councils' IT systems via
POST/PUT. There are no GET endpoints, so they can't be used as a data
source even with a key. The open-data extract + council scrapers are
the only viable free paths.

## Suggested next step

Build the Open Cities adapter. It's the highest-leverage move — covers
6 LGAs through the densest capital-flow zone (CBD + east) with one
implementation.

Reference Open Cities search URL (City of Sydney):
  https://eplanning.cityofsydney.nsw.gov.au/Pages/XC.Track/SearchApplication.aspx

Most Open Cities sites expose `/XC.Track/Services/SearchService.svc`
or `/Services/Application.svc` returning JSON, which is much friendlier
to scrape than the T1 ASPX postbacks.

## Working dataset

`data/output/applications.csv` — running upserted store of scraped
applications, keyed by (application_id, source). Currently holds 32
Ryde rows from a 30-day window.
