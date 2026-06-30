# NSW Site Controls — web calculator

A zero-backend static port of the `controls` CLI. Open `index.html`, enter a NSW
site (lot/DP, coordinates, or address), and it queries the public NSW planning
ArcGIS layers + SIX cadastre **directly from the browser** (those services send
permissive CORS headers), computes the envelope, and renders the Site Control
Sheet. No server, no API key, no AI — just public data + arithmetic.

## Run locally

Any static file server works (ES module `import`, so `file://` won't load `app.js`):

```bash
python -m http.server -d web 8000   # then open http://localhost:8000
```

## Deploy (Vercel)

This folder is a standalone static project. From `web/`:

```bash
npx vercel --prod
```

Deployed separately from path-of-trading (its own Vercel project).

## What's where

- `index.html` — form UI, three map panels (NSW aerial / Google satellite /
  Street View), styles. Loads Leaflet from CDN.
- `app.js` — faithful JS port of `arcgis.py`, `locate.py`, `lep.py`, `registry.py`,
  `dcp.py`, `sheet.py`, plus `renderMaps()`. The DCP lives in a **`COUNCILS`
  registry** — adding a council = adding one data entry (slug + transcribed,
  clause-cited controls); it then appears in the Council dropdown automatically,
  no UI/code change. Ryde 2014 is inlined from
  `../nsw_site_controls/data/ryde_dcp_2014.yaml` — keep them in sync if the YAML changes.
- `vercel.json` — clean-URLs static config.

## Maps

After a calculation the page shows three previews centred on the resolved site:
the **NSW aerial** (Leaflet + SIX imagery tiles) with the **actual cadastral
parcel boundary** overlaid (doubles as a "did it find the right lot?" check),
**Google satellite**, and **Street View** — both keyless Google embeds.

## Caveats (same as the CLI)

- **Lot/DP is the reliable input.** Address geocoding (OpenStreetMap) is approximate.
- DCP setback/parking detail is **City of Ryde only**; zoning/FSR/height/min-lot
  work statewide.
- Decision-support, **not** planning advice — verify against a s10.7 certificate.
