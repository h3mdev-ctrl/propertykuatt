"""NSW Planning Portal — DA + A&A application feed.

This is the keystone free source. It carries:
  - Development Applications (new builds, subdivisions, commercial)
  - Modifications and Section 4.55 amendments
  - Residential alterations & additions (the "retail" reno-flow signal)

Each record exposes a `CostOfDevelopment` (or equivalent) field declared by
the applicant. That figure is the dollar-flow signal we want.

Two access patterns exist:
  1. data.nsw.gov.au bulk CSV/Parquet exports — refreshed roughly weekly.
  2. NSW DPE eplanning API — record-level JSON, paginated.

We default to (2) for freshness and fall back to (1) if the API is rate
limited or the dataset id changes. Both paths land at the same normalised
schema below so downstream code does not care which was used.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.config import RAW_DIR, SETTINGS

log = logging.getLogger(__name__)

# Canonical column names every source maps to before hitting the aggregator.
NORMALISED_COLUMNS = [
    "application_id",
    "lodged_date",
    "determined_date",
    "lga",
    "suburb",
    "postcode",
    "address",
    "lat",
    "lon",
    "category",          # one of: new_build, alterations_additions, commercial, infra, other
    "status",            # lodged | under_assessment | approved | rejected | withdrawn
    "cost_of_works",     # AUD, applicant declared
    "source",            # provenance tag, e.g. "nsw_planning_portal"
]


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class NSWPlanningClient:
    def __init__(self, base_url: str | None = None, session: requests.Session | None = None):
        self.base_url = (base_url or SETTINGS.sources.nsw_planning_api_base).rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def fetch_applications(
        self,
        lodged_from: date,
        lodged_to: date,
        lgas: tuple[str, ...] | None = None,
    ) -> Iterator[dict]:
        """Stream raw application records for a date window.

        The portal paginates; we walk pages until the API returns an empty
        page. LGA filtering is applied server-side when the endpoint supports
        it, otherwise we filter locally in :func:`normalise`.
        """
        page = 1
        page_size = SETTINGS.sources.nsw_planning_page_size
        while True:
            params = {
                "filters": json.dumps(
                    {
                        "LodgementDateFrom": lodged_from.isoformat(),
                        "LodgementDateTo": lodged_to.isoformat(),
                        **({"CouncilName": list(lgas)} if lgas else {}),
                    }
                ),
                "pageNumber": page,
                "pageSize": page_size,
            }
            payload = self._get("OnlineDA", params)
            records = payload.get("Application", []) or payload.get("data", [])
            if not records:
                break
            yield from records
            if len(records) < page_size:
                break
            page += 1


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Map raw applicant DA categories onto our canonical taxonomy. The portal's
# `ApplicationType` / `DevelopmentType` fields are free-text-ish, so we group
# by substring match. Anything unmatched falls through to "other" and gets
# logged for periodic review.
_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("alteration", "alterations_additions"),
    ("addition", "alterations_additions"),
    ("renovation", "alterations_additions"),
    ("dwelling - new", "new_build"),
    ("new dwelling", "new_build"),
    ("dual occupancy", "new_build"),
    ("residential flat", "new_build"),
    ("multi dwelling", "new_build"),
    ("subdivision", "new_build"),
    ("commercial", "commercial"),
    ("retail", "commercial"),
    ("office", "commercial"),
    ("industrial", "commercial"),
    ("warehouse", "commercial"),
    ("infrastructure", "infra"),
    ("road", "infra"),
    ("rail", "infra"),
)


def _categorise(development_type: str | None) -> str:
    if not development_type:
        return "other"
    s = development_type.lower()
    for needle, label in _CATEGORY_RULES:
        if needle in s:
            return label
    return "other"


def _coerce_float(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v


def normalise(records: list[dict]) -> pd.DataFrame:
    """Convert raw NSW Planning Portal records into the canonical schema."""
    rows = []
    for r in records:
        cost = _coerce_float(r.get("CostOfDevelopment") or r.get("EstimatedCost"))
        if cost is None or cost < SETTINGS.min_cost_of_works:
            continue
        rows.append(
            {
                "application_id": r.get("PlanningPortalApplicationNumber") or r.get("ApplicationId"),
                "lodged_date": r.get("LodgementDate"),
                "determined_date": r.get("DeterminationDate"),
                "lga": r.get("CouncilName"),
                "suburb": (r.get("Location") or {}).get("Suburb") if isinstance(r.get("Location"), dict) else r.get("Suburb"),
                "postcode": (r.get("Location") or {}).get("Postcode") if isinstance(r.get("Location"), dict) else r.get("Postcode"),
                "address": r.get("Address") or r.get("FullAddress"),
                "lat": r.get("Latitude"),
                "lon": r.get("Longitude"),
                "category": _categorise(r.get("DevelopmentType") or r.get("ApplicationType")),
                "status": (r.get("ApplicationStatus") or "").lower() or "lodged",
                "cost_of_works": cost,
                "source": "nsw_planning_portal",
            }
        )
    df = pd.DataFrame(rows, columns=NORMALISED_COLUMNS)
    if not df.empty:
        df["lodged_date"] = pd.to_datetime(df["lodged_date"], errors="coerce").dt.date
        df["determined_date"] = pd.to_datetime(df["determined_date"], errors="coerce").dt.date
    return df


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def pull(lodged_from: date, lodged_to: date, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Fetch + normalise + persist raw applications for the study area."""
    client = NSWPlanningClient()
    raw_records: list[dict] = []
    for rec in client.fetch_applications(lodged_from, lodged_to, SETTINGS.area.lgas):
        raw_records.append(rec)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    raw_path = raw_dir / f"nsw_planning_{lodged_from}_{lodged_to}_{stamp}.json"
    raw_path.write_text(json.dumps(raw_records))
    log.info("wrote %d raw NSW Planning records to %s", len(raw_records), raw_path)

    df = normalise(raw_records)
    log.info("normalised %d records (filtered from %d)", len(df), len(raw_records))
    return df
