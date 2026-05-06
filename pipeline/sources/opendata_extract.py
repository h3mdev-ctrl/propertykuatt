"""Reader for the NSW Planning Portal "Online DA / CDC Data API" extracts.

The dataset on data.nsw.gov.au is delivered by email subscription, not a
direct download URL. Drop the CSVs the data broker sends you into
``data/raw/nsw_opendata/`` and this module will pick them up.

We expect filenames like ``Online_DA_*.csv`` and ``Online_CDC_*.csv``;
within each file the column names broadly match the OpenAPI schema
(``CostOfDevelopment``, ``LodgementDate``, ``CouncilName``, ``Suburb``,
``Latitude``, ``Longitude``, ``DevelopmentType``, etc.). Field names have
shifted between extract versions, so we map a tolerant set of aliases
onto the canonical schema.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.config import RAW_DIR
from pipeline.schema import NORMALISED_COLUMNS, categorise

log = logging.getLogger(__name__)

OPENDATA_DIR = RAW_DIR / "nsw_opendata"
OPENDATA_DIR.mkdir(parents=True, exist_ok=True)

# Source column -> canonical column. Lower-cased on read so casing drift
# between extracts doesn't break us.
_ALIASES: dict[str, str] = {
    "planningportalapplicationnumber": "application_id",
    "applicationid": "application_id",
    "pan": "application_id",
    "lodgementdate": "lodged_date",
    "lodgeddate": "lodged_date",
    "determinationdate": "determined_date",
    "councilname": "lga",
    "lga": "lga",
    "suburb": "suburb",
    "postcode": "postcode",
    "fulladdress": "address",
    "address": "address",
    "latitude": "lat",
    "longitude": "lon",
    "developmenttype": "_devtype",       # used for category derivation
    "applicationtype": "_apptype",
    "applicationstatus": "status",
    "costofdevelopment": "cost_of_works",
    "estimatedcost": "cost_of_works",
    "capitalinvestmentvalue": "cost_of_works",
    "developmentdescription": "description",
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: _ALIASES.get(c.lower().strip(), c) for c in df.columns})
    return df


def load_extracts(directory: Path = OPENDATA_DIR, kind: str = "DA") -> pd.DataFrame:
    """Load every CSV in ``directory`` whose name starts with ``Online_<kind>``."""
    pattern = f"Online_{kind}_*.csv"
    files = sorted(directory.glob(pattern))
    if not files:
        log.info("no %s extracts found in %s", kind, directory)
        return pd.DataFrame(columns=NORMALISED_COLUMNS)

    frames = []
    for f in files:
        log.info("reading %s", f.name)
        raw = pd.read_csv(f, low_memory=False)
        frames.append(_normalise_columns(raw))

    df = pd.concat(frames, ignore_index=True)
    df["category"] = (
        df.get("_devtype").fillna(df.get("_apptype", "")) if "_devtype" in df else df.get("_apptype", "")
    ).map(categorise)

    df["source"] = f"nsw_opendata:{kind.lower()}"
    df["source_url"] = None
    df["fetched_at"] = datetime.utcnow().isoformat(timespec="seconds")

    for col in NORMALISED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[NORMALISED_COLUMNS]
