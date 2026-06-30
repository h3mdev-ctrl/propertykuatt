# nsw-site-controls

Turn a NSW site location into the planning controls you can design to — straight
from the command line.

Give it a **lot/DP**, **coordinates** (read off SixMaps), or an **address**, and
it prints a *Site Control Sheet*:

- **LEP/SEPP envelope** (live, statewide): land zoning, floor space ratio (FSR),
  max building height, minimum lot size, heritage — pulled by spatial query from
  the NSW Planning ArcGIS REST layers, plus derived **max GFA** (FSR × site area)
  and a quick subdivision check.
- **Council DCP controls** (curated): setbacks, deep soil, landscaping, parking,
  etc. — currently **City of Ryde DCP 2014**, with the exact clause cited for
  every control. Add `--dev-type` to switch this section on.

> **Decision-support only.** This is generated from public spatial data and a
> transcription of the council DCP. It is **not** planning advice or a
> certificate. Verify against the source instruments / a planner / a s10.7
> certificate before lodging a DA.

## Install

```bash
pip install -e ".[dev]"
```

## Use

```bash
# Authoritative path — lot/DP (most reliable)
controls --lot 3/DP24994 --dev-type dwelling-house

# Exact point off SixMaps (lon,lat WGS84)
controls --coords 151.0931,-33.8076

# Address (geocoded approximately — always verify the point/lot)
controls "1 Devlin St, Ryde NSW" --dev-type dual-occupancy

# JSON for piping into other tools
controls --lot 3/DP24994 --dev-type dwelling-house --json
```

`--dev-type` accepts `dwelling-house` / `dual-occupancy` (aliases: `house`,
`duplex`, `dual`, …). Without it, only the LEP/SEPP envelope is shown (setbacks
are meaningless without a development type).

## How it works

```
  location (lot/DP | coords | address)
        │  locate.py
        ▼
  Site(point, parcel polygon, area)          area: cadastre planlotarea,
        │                                    else computed from the geometry
        ├─ lep.py  ── ArcGIS REST point/polygon query per LayerSpec
        │            (registry.py: one row per control)
        │            → zoning, FSR, height, min-lot, heritage
        │            → derive max GFA, subdivision
        │
        └─ dcp.py  ── curated YAML (data/ryde_dcp_2014.yaml)
                     → setbacks / deep soil / parking + clause cites
        ▼
  sheet.py → text sheet or --json   (cites every source; partial-renders
                                      if a layer service is down)
```

### Design notes / known edges
- **Multi-zone sites:** a parcel that straddles two zoning/FSR/height polygons
  shows **all** values with a "straddles N areas" flag — it never silently picks
  one.
- **R2 lots often have no LEP FSR/height** — low density is governed by minimum
  lot size + the DCP's 9.5 m / 2-storey limit, not the LEP FSR/HOB layers. "none
  mapped" there is correct, not a failure.
- **`planlotarea` is frequently NULL** in the SIX cadastre, so area falls back to
  an equirectangular shoelace on the parcel geometry (the sheet says which source
  it used). The stored `shape_Area` is Web Mercator and distorted ~1.45× at
  Sydney — we do not use it.
- **SIX cadastre is flaky** on point queries; calls retry with backoff. The
  lot/DP path is the most reliable.
- **Low/Mid-Rise Housing reforms (2024–2025)** can override council controls in
  residential zones — the sheet warns about this; it does not yet query the
  reform layer.

### Why the Ryde DCP is a curated YAML, not live RAG
A single council's DCP is a small, stable set of tables. A checked-in
[`ryde_dcp_2014.yaml`](nsw_site_controls/data/ryde_dcp_2014.yaml) is
deterministic, testable, citable clause-by-clause, and human-reviewable. RAG over
the PDFs earns its place only when generalising across many councils — a later
phase. The numbers were transcribed from the adopted Ryde DCP 2014 Part 3.3
(refresh the source PDFs with `scripts/fetch_ryde_dcp.py`).

## Tests

```bash
pytest                       # offline unit tests (recorded fixtures, no network)
NSC_LIVE=1 pytest tests/test_live.py    # opt-in live checks (catch upstream drift)
python scripts/record_fixtures.py 151.0931 -33.8076   # refresh fixtures from live
```

## Data sources
- NSW Planning — `Planning/EPI_Primary_Planning_Layers` (ArcGIS REST)
- SIX cadastre — `public/NSW_Cadastre` layer 9 (ArcGIS REST)
- City of Ryde DCP 2014 (transcribed; clause-cited)

## Roadmap
1. ✅ LEP/SEPP envelope + Ryde DCP (curated) — this release.
2. Wire the Low/Mid-Rise reform + hazard (flood/bushfire) layers into the registry.
3. More councils' DCPs (each a curated YAML; RAG only if it stops scaling).
4. Optional: address geocoder with a NSW key; map/PDF export.
