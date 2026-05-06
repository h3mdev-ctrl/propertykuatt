from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
OUTPUT_DIR = DATA_DIR / "output"

for d in (RAW_DIR, INTERIM_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class StudyArea:
    """Sydney CBD + 20km radius pilot footprint."""
    name: str = "sydney_20km"
    centre_lat: float = -33.8688
    centre_lon: float = 151.2093
    radius_km: float = 20.0
    # LGAs that fall mostly inside the 20km ring — used to filter source feeds
    # that index by LGA rather than coordinate.
    lgas: tuple = (
        "Sydney",
        "Inner West",
        "Bayside",
        "Canterbury-Bankstown",
        "North Sydney",
        "Willoughby",
        "Lane Cove",
        "Randwick",
        "Woollahra",
        "Waverley",
        "Mosman",
        "Hunters Hill",
        "Burwood",
        "Strathfield",
        "Canada Bay",
        "Ryde",
        "Parramatta",
        "Georges River",
    )


@dataclass
class Sources:
    # NSW Planning Portal — "Online DA Data" (bulk + API).
    # The portal exposes a public dataset on data.nsw.gov.au; the JSON API
    # endpoint and dataset id need to be set in .env / overridden at runtime.
    # Leaving as a placeholder rather than hard-coding a URL we haven't
    # verified against a live response.
    nsw_planning_api_base: str = "https://api.apps1.nsw.gov.au/eplanning/data/v0"
    nsw_planning_dataset: str = "OnlineDA"
    nsw_planning_page_size: int = 10_000

    # ABS Building Approvals 8731.0 — used as a state/LGA-level sanity check
    # against our own DA roll-up.
    abs_building_approvals_8731: str = (
        "https://api.data.abs.gov.au/data/ABS,BUILDING_APPROVALS_LGA,1.0.0"
    )


@dataclass
class Settings:
    area: StudyArea = field(default_factory=StudyArea)
    sources: Sources = field(default_factory=Sources)
    # Cost-of-works floor — anything below this is almost certainly a typo or
    # a $1 placeholder used by some councils to flag "no fee applicable".
    min_cost_of_works: float = 1_000.0
    # Cost-of-works ceiling for residential A&A — anything larger is almost
    # certainly a misclassified new-build or commercial fitout.
    max_aa_cost_of_works: float = 5_000_000.0


SETTINGS = Settings()
