"""Entry point: pull -> geocode -> aggregate -> write parquet + GeoJSON.

Usage:
    python -m pipeline.cli --from 2023-01-01 --to 2024-12-31
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from pipeline.aggregator import aggregate_flows
from pipeline.config import OUTPUT_DIR
from pipeline.geocode import attach_sa2
from pipeline.sources import nsw_planning_portal


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="lodged_from", required=True, type=_parse_date)
    p.add_argument("--to", dest="lodged_to", required=True, type=_parse_date)
    args = p.parse_args()

    apps = nsw_planning_portal.pull(args.lodged_from, args.lodged_to)
    apps = attach_sa2(apps)

    flows = aggregate_flows(apps)

    apps_path = OUTPUT_DIR / "applications.parquet"
    flows_path = OUTPUT_DIR / "suburb_flows.parquet"
    apps.to_parquet(apps_path, index=False)
    flows.to_parquet(flows_path, index=False)
    logging.info("wrote %s (%d rows) and %s (%d rows)",
                 apps_path, len(apps), flows_path, len(flows))


if __name__ == "__main__":
    main()
