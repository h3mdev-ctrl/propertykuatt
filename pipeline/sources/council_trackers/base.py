"""Abstract adapter contract for council DA-tracker scrapers.

Each council exposes a public DA register, but the underlying software is
one of a handful of vendor platforms (T1/eProperty, Civica Authority,
Open Cities, etc.). One adapter per vendor — councils on the same vendor
share the adapter, parameterised by their base URL.

Adapters return rows already normalised to ``schema.NORMALISED_COLUMNS``,
so the aggregator never sees vendor-specific shapes.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from pipeline.schema import NORMALISED_COLUMNS

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CouncilSite:
    """One council's entry in the registry."""
    council: str          # e.g. "Ryde"
    vendor: str           # e.g. "t1_etrack"
    base_url: str         # vendor-specific entry point
    extra: dict | None = None  # any vendor-specific config (form params, etc.)


class CouncilTrackerAdapter(ABC):
    """Base class — subclass per vendor platform."""

    vendor: str = "unknown"
    # Polite default delay between detail-page hits, seconds.
    request_delay_s: float = 0.5

    def __init__(self, site: CouncilSite, session: requests.Session | None = None):
        self.site = site
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "propertykuatt/0.1 (real-estate-flow research; contact via repo)",
                "Accept": "text/html,application/json",
            }
        )

    # -- HTTP helpers --------------------------------------------------------

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
    def _post(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.post(url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp

    # -- Adapter contract ----------------------------------------------------

    @abstractmethod
    def search(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        """Yield raw application summary dicts from the council's search UI."""

    @abstractmethod
    def fetch_detail(self, summary: dict) -> dict:
        """Given a summary row, fetch its detail page and return the merged dict."""

    # -- Driver --------------------------------------------------------------

    def pull(self, lodged_from: date, lodged_to: date) -> pd.DataFrame:
        rows: list[dict] = []
        for summary in self.search(lodged_from, lodged_to):
            try:
                row = self.fetch_detail(summary)
            except Exception as exc:  # noqa: BLE001 — keep going past one bad row
                log.warning("%s: detail fetch failed for %r: %s", self.site.council, summary.get("application_id"), exc)
                continue
            rows.append(self._finalise(row))
        df = pd.DataFrame(rows, columns=NORMALISED_COLUMNS)
        log.info("%s/%s: %d rows", self.site.council, self.vendor, len(df))
        return df

    def _finalise(self, row: dict) -> dict:
        row.setdefault("lga", self.site.council)
        row.setdefault("source", f"council_tracker:{self.site.council.lower().replace(' ', '_')}:{self.vendor}")
        row.setdefault("fetched_at", datetime.utcnow().isoformat(timespec="seconds"))
        for col in NORMALISED_COLUMNS:
            row.setdefault(col, None)
        return {k: row[k] for k in NORMALISED_COLUMNS}
