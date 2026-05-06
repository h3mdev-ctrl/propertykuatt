"""Canonical record schema every source normalises to.

Keeping this in one place so adapters (council trackers, opendata
extracts, future state-budget feeds) all converge on the same columns
before hitting the geocoder + aggregator.
"""
from __future__ import annotations

NORMALISED_COLUMNS: list[str] = [
    "application_id",      # e.g. "LDA2024/0123" or portal PAN-xxxxx
    "lodged_date",         # ISO date
    "determined_date",     # ISO date or None
    "lga",                 # council name
    "suburb",              # text suburb (free-form, geocoder will resolve)
    "postcode",            # 4-digit
    "address",             # full address string
    "lat",
    "lon",
    "category",            # new_build | alterations_additions | commercial | infra | cdc | cc | oc | other
    "status",              # lodged | under_assessment | approved | rejected | withdrawn | issued
    "cost_of_works",       # AUD, applicant declared
    "description",         # free-text development description (optional)
    "source",              # provenance, e.g. "council_tracker:ryde:t1_etrack"
    "source_url",          # back-link to the detail page on the council tracker
    "fetched_at",          # ISO datetime when we scraped this row
]


# Free-text development-type -> canonical category mapping. Adapters call
# `categorise(text)` once they have the most specific description string the
# tracker exposes.
_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("alteration", "alterations_additions"),
    ("addition", "alterations_additions"),
    ("renovation", "alterations_additions"),
    ("internal fitout", "alterations_additions"),
    ("dwelling - new", "new_build"),
    ("new dwelling", "new_build"),
    ("new single dwelling", "new_build"),
    ("dual occupancy", "new_build"),
    ("residential flat", "new_build"),
    ("multi dwelling", "new_build"),
    ("multi-dwelling", "new_build"),
    ("subdivision", "new_build"),
    ("secondary dwelling", "new_build"),
    ("granny flat", "new_build"),
    ("commercial", "commercial"),
    ("retail", "commercial"),
    ("office", "commercial"),
    ("industrial", "commercial"),
    ("warehouse", "commercial"),
    ("mixed use", "commercial"),
    ("infrastructure", "infra"),
    ("road work", "infra"),
    ("rail", "infra"),
    ("complying development", "cdc"),
    ("cdc", "cdc"),
    ("construction certificate", "cc"),
    ("occupation certificate", "oc"),
)


def categorise(text: str | None) -> str:
    if not text:
        return "other"
    s = text.lower()
    for needle, label in _CATEGORY_RULES:
        if needle in s:
            return label
    return "other"


# Application-id prefix -> canonical category. Used as a fallback when
# the free-text development description is uninformative (e.g. councils
# that put a Lot/DP reference in the description column). Recognised
# prefixes across NSW councils:
#   DA / LDA       Development Application (treat as 'other' until the
#                  detail page resolves a more specific dev type)
#   MOD            Modification request — bucketed as alterations_additions
#                  since modifications are overwhelmingly resi A&A
#   CDP / CDC      Complying Development Certificate
#   CC             Construction Certificate
#   OC             Occupation Certificate
#   S68            Section 68 Local Government Act approval
#   REV            Section 8.2 review
_ID_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("CDP", "cdc"),
    ("CDC", "cdc"),
    ("CC",  "cc"),
    ("OC",  "oc"),
    ("MOD", "alterations_additions"),
    ("LDA", "other"),  # generic DA — leave as 'other', details refine
    ("DA",  "other"),
    ("S68", "infra"),
    ("REV", "other"),
)


def categorise_with_id(text: str | None, application_id: str | None) -> str:
    """Like ``categorise`` but use the application-id prefix as a tiebreaker.

    Free-text rules win when they hit; otherwise we fall back to the id
    prefix. Always returns a non-empty category string.
    """
    text_cat = categorise(text)
    if text_cat != "other":
        return text_cat
    if application_id:
        upper = application_id.upper()
        for prefix, label in _ID_PREFIX_RULES:
            if upper.startswith(prefix):
                return label
    return "other"
