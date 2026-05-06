"""Registry of Sydney 20km councils and which vendor adapter handles each.

Vendor codes:
  * ``t1_etrack``        — TechnologyOne T1 / eProperty / eTrack (ASPX)
  * ``civica_authority`` — Civica Authority / APR / Pathway portals
  * ``open_cities``      — Open Cities / Datacom planning portals
  * ``infocouncil``      — InfoCouncil-style register
  * ``custom``           — bespoke per-council site (one-off scraper)

Sites flagged ``adapter_ready=False`` need their adapter implemented or
their base_url verified before they will return rows.
"""
from __future__ import annotations

from pipeline.sources.council_trackers.base import CouncilSite, CouncilTrackerAdapter
from pipeline.sources.council_trackers.t1_etrack import T1eTrackAdapter

# Council registry. Base URLs are best-known public entry points. Vendor
# attributions are based on visible page chrome / URL patterns and should
# be verified on first scrape before relying on them.
REGISTRY: dict[str, CouncilSite] = {
    "Ryde": CouncilSite(
        council="Ryde",
        vendor="t1_etrack",
        base_url="https://ryde-web.t1cloud.com/T1PRDefault/WebApps/eProperty/P1/eTrack/",
        extra={
            "results_path": "eTrackApplicationSearchResults.aspx",
            "results_query": {"Field": "S", "r": "COR.P1.WEBGUEST", "f": "$P1.ETR.SEARCH.STW"},
        },
    ),
    "Hunters Hill": CouncilSite(
        council="Hunters Hill",
        vendor="t1_etrack",
        base_url="https://hunters-hill.t1cloud.com/T1Default/WebApps/eProperty/P1/eTrack/",
        extra={
            "results_path": "eTrackApplicationSearchResults.aspx",
            "results_query": {"Field": "S", "r": "COR.P1.WEBGUEST", "f": "$P1.ETR.SEARCH.STW"},
        },
    ),
    "Lane Cove": CouncilSite(
        council="Lane Cove",
        vendor="t1_etrack",
        base_url="https://lanecove.t1cloud.com/T1PRDefault/WebApps/eProperty/P1/eTrack/",
        extra={
            "results_path": "eTrackApplicationSearchResults.aspx",
            "results_query": {"Field": "S", "r": "COR.P1.WEBGUEST", "f": "$P1.ETR.SEARCH.STW"},
        },
    ),
    "City of Sydney":      CouncilSite("City of Sydney",      "open_cities",      "https://eplanning.cityofsydney.nsw.gov.au/Pages/XC.Track/SearchApplication.aspx"),
    "North Sydney":        CouncilSite("North Sydney",        "open_cities",      "https://services.northsydney.nsw.gov.au/Common/Common/Pages/XC.Track/SearchApplication.aspx"),
    "Willoughby":          CouncilSite("Willoughby",          "open_cities",      "https://eservice.willoughby.nsw.gov.au/Common/Common/Pages/XC.Track/SearchApplication.aspx"),
    "Inner West":          CouncilSite("Inner West",          "civica_authority", "https://eservices.innerwest.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Bayside":             CouncilSite("Bayside",             "civica_authority", "https://eservices.bayside.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Canterbury-Bankstown":CouncilSite("Canterbury-Bankstown","civica_authority", "https://onlineservices.cbcity.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Georges River":       CouncilSite("Georges River",       "civica_authority", "https://eservices.georgesriver.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Randwick":            CouncilSite("Randwick",            "open_cities",      "https://eservices.randwick.nsw.gov.au/T1PRProd/WebApps/eProperty/P1/eTrack/eTrackApplicationSearch.aspx"),
    "Woollahra":           CouncilSite("Woollahra",           "open_cities",      "https://eservices.woollahra.nsw.gov.au/Common/Common/Pages/XC.Track/SearchApplication.aspx"),
    "Waverley":            CouncilSite("Waverley",            "open_cities",      "https://eservices.waverley.nsw.gov.au/Common/Common/Pages/XC.Track/SearchApplication.aspx"),
    "Mosman":              CouncilSite("Mosman",              "open_cities",      "https://applications.mosman.nsw.gov.au/Pages/XC.Track/SearchApplication.aspx"),
    "Burwood":             CouncilSite("Burwood",             "civica_authority", "https://eservices.burwood.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Strathfield":         CouncilSite("Strathfield",         "civica_authority", "https://eservices.strathfield.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Canada Bay":          CouncilSite("Canada Bay",          "civica_authority", "https://eservices.canadabay.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
    "Parramatta":          CouncilSite("Parramatta",          "custom",           "https://onlineservices.cityofparramatta.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx"),
}


_ADAPTERS: dict[str, type[CouncilTrackerAdapter]] = {
    "t1_etrack": T1eTrackAdapter,
    # Other vendors stubbed — drop in concrete adapters as they're built.
    # "civica_authority": CivicaAuthorityAdapter,
    # "open_cities":      OpenCitiesAdapter,
}


def get_adapter(council: str) -> CouncilTrackerAdapter:
    site = REGISTRY[council]
    cls = _ADAPTERS.get(site.vendor)
    if cls is None:
        raise NotImplementedError(
            f"No adapter for vendor {site.vendor!r} yet (council: {council}). "
            "Implement a subclass of CouncilTrackerAdapter and register it."
        )
    return cls(site)
