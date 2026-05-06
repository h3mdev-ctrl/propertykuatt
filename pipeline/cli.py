"""Entry points: scrape councils, load opendata extracts, aggregate, write outputs.

Usage:
    # Scrape one or more councils for a date range
    python -m pipeline.cli scrape --council Ryde --from 2024-01-01 --to 2024-12-31
    python -m pipeline.cli scrape --all-t1 --from 2024-10-01 --to 2024-12-31

    # Load NSW Planning Portal opendata CSVs (DA + CDC) from data/raw/nsw_opendata
    python -m pipeline.cli opendata --kind DA
    python -m pipeline.cli opendata --kind CDC

    # Run the full aggregate over whatever is currently in data/output/applications.parquet
    python -m pipeline.cli aggregate
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from pipeline.config import OUTPUT_DIR
from pipeline.sources import opendata_extract
from pipeline.sources.council_trackers import REGISTRY, get_adapter

APPS_PATH = OUTPUT_DIR / "applications.parquet"
FLOWS_PATH = OUTPUT_DIR / "suburb_flows.parquet"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _persist(new_apps: pd.DataFrame) -> pd.DataFrame:
    """Upsert by (application_id, source) into the running applications parquet."""
    if APPS_PATH.exists():
        existing = pd.read_parquet(APPS_PATH)
        combined = pd.concat([existing, new_apps], ignore_index=True)
        combined = combined.drop_duplicates(subset=["application_id", "source"], keep="last")
    else:
        combined = new_apps
    combined.to_parquet(APPS_PATH, index=False)
    logging.info("applications.parquet now has %d rows", len(combined))
    return combined


def cmd_scrape(args: argparse.Namespace) -> None:
    councils: list[str]
    if args.all_t1:
        councils = [c for c, s in REGISTRY.items() if s.vendor == "t1_etrack"]
    elif args.council:
        councils = list(args.council)
    else:
        raise SystemExit("specify --council COUNCIL or --all-t1")

    frames = []
    for council in councils:
        try:
            adapter = get_adapter(council)
        except NotImplementedError as e:
            logging.warning("%s — skipped: %s", council, e)
            continue
        logging.info("scraping %s (%s)", council, adapter.vendor)
        frames.append(adapter.pull(args.lodged_from, args.lodged_to))

    if not frames:
        logging.warning("no councils produced any rows")
        return
    new_apps = pd.concat(frames, ignore_index=True)
    _persist(new_apps)


def cmd_opendata(args: argparse.Namespace) -> None:
    df = opendata_extract.load_extracts(kind=args.kind)
    if df.empty:
        logging.warning("no %s extracts to load", args.kind)
        return
    _persist(df)


def cmd_debug(args: argparse.Namespace) -> None:
    """One-shot reachability + selector check for a single council.

    Saves the raw search-results HTML to data/raw/debug/ and prints what
    was detected (form fields, results-table row count). Use this on the
    first run against a new council to tune selectors before a full pull.
    """
    from pipeline.config import RAW_DIR
    from pipeline.sources.council_trackers.registry import REGISTRY
    from bs4 import BeautifulSoup

    site = REGISTRY[args.council]
    adapter = get_adapter(args.council)

    debug_dir = RAW_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    url = adapter._search_url() if hasattr(adapter, "_search_url") else site.base_url
    params = (site.extra or {}).get("results_query", {}) or {}
    logging.info("GET %s params=%s", url, params)
    resp = adapter._get(url, params=params)
    out = debug_dir / f"{args.council.lower().replace(' ', '_')}_search.html"
    out.write_text(resp.text)
    logging.info("wrote %s (%d bytes, status %s)", out, len(resp.text), resp.status_code)

    soup = BeautifulSoup(resp.text, "html.parser")
    state = adapter._extract_aspx_state(soup) if hasattr(adapter, "_extract_aspx_state") else {}
    logging.info("ASPX state keys present: %s", list(state.keys()))

    inputs = [(i.get("name"), i.get("type"), i.get("value", "")[:30])
              for i in soup.find_all(["input", "select"]) if i.get("name")]
    logging.info("form inputs (%d):", len(inputs))
    for name, type_, value in inputs[:40]:
        logging.info("  %-50s type=%-10s value=%r", name, type_, value)

    tables = soup.find_all("table")
    logging.info("tables on page: %d", len(tables))
    for i, t in enumerate(tables[:10]):
        logging.info("  table[%d] id=%r class=%r rows=%d",
                     i, t.get("id"), t.get("class"), len(t.find_all("tr")))


def cmd_aggregate(_args: argparse.Namespace) -> None:
    if not APPS_PATH.exists():
        raise SystemExit(f"{APPS_PATH} not found — run scrape or opendata first")
    from pipeline.aggregator import aggregate_flows
    from pipeline.geocode import attach_sa2

    apps = pd.read_parquet(APPS_PATH)
    apps = attach_sa2(apps)
    flows = aggregate_flows(apps)
    flows.to_parquet(FLOWS_PATH, index=False)
    logging.info("wrote %s (%d rows)", FLOWS_PATH, len(flows))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scrape")
    sp.add_argument("--council", action="append", help="council name (repeatable)")
    sp.add_argument("--all-t1", action="store_true", help="scrape every council on the T1/eTrack adapter")
    sp.add_argument("--from", dest="lodged_from", required=True, type=_parse_date)
    sp.add_argument("--to",   dest="lodged_to",   required=True, type=_parse_date)
    sp.set_defaults(func=cmd_scrape)

    op = sub.add_parser("opendata")
    op.add_argument("--kind", choices=("DA", "CDC"), default="DA")
    op.set_defaults(func=cmd_opendata)

    ag = sub.add_parser("aggregate")
    ag.set_defaults(func=cmd_aggregate)

    db = sub.add_parser("debug", help="dump raw HTML + detected form fields for one council")
    db.add_argument("--council", required=True)
    db.set_defaults(func=cmd_debug)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
