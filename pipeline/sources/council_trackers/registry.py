"""Registry of Sydney 20km councils and which vendor adapter handles each.

Vendor codes (verified live 2026-05-06 via /browse audit):
  * ``t1_etrack``               — TechnologyOne T1 eProperty / eTrack (legacy ASPX)
  * ``t1_cianywhere``           — TechnologyOne CiAnywhere (newer SPA portal)
  * ``open_cities``             — Open Cities / Datacom XC.Track (Pages/XC.Track/SearchApplication.aspx)
  * ``civica_authority``        — Civica Authority / ePathway (ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx)
  * ``infor_masterview``        — Infor MasterView (datracker./masterview.<council>; ASP.NET MVC; /Home/Search)
  * ``infor_pathway_public``    — Infor Pathway Public portal (eplanning.<council>/Public/PlanningRegister.aspx)
  * ``infor_eservice_struts``   — Java/Struts eservice (/eservice/dialog/daEnquiryInit.do)
  * ``custom``                  — bespoke per-council site (one-off scraper)
  * ``unknown``                 — vendor not yet identified or tracker URL not yet found

Adapters currently implemented:
  * ``t1_etrack``        (Ryde — 32 rows confirmed)
  * ``open_cities``      (City of Sydney, Bayside, Georges River — smoke test pending)
  * ``civica_authority`` (Randwick, Waverley, Parramatta, Canterbury-Bankstown,
                          Inner West — adapter shipped, smoke test pending)

Adapters yet to build (in rough ROI order, councils per vendor):
  * ``infor_masterview``      → 3 councils (North Sydney, Burwood, Strathfield)
  * ``infor_eservice_struts`` → 3 councils (Mosman, Lane Cove, Woollahra)
  * ``t1_cianywhere``         → 1 council (Willoughby), Inner West may follow
  * ``infor_pathway_public``  → 1 council (Hunters Hill)

(* = registry URL believed correct from prior knowledge but couldn't verify
from the audit machine due to DNS/geoblock; first scrape will confirm.)

Each ``CouncilSite.notes`` field records what was found during the audit so
adapter authors and future re-verification have a paper trail. ``base_url``
is the entry point the adapter should hit (search/disclaimer/landing).
"""
from __future__ import annotations

from pipeline.sources.council_trackers.base import CouncilSite, CouncilTrackerAdapter
from pipeline.sources.council_trackers.civica_authority import CivicaAuthorityAdapter
from pipeline.sources.council_trackers.open_cities import OpenCitiesAdapter
from pipeline.sources.council_trackers.t1_etrack import T1eTrackAdapter

# Council registry. URLs and vendor codes verified live 2026-05-06.
REGISTRY: dict[str, CouncilSite] = {
    # -- TechnologyOne eTrack (legacy) -------------------------------------
    "Ryde": CouncilSite(
        council="Ryde",
        vendor="t1_etrack",
        base_url="https://ryde-web.t1cloud.com/T1PRDefault/WebApps/eProperty/P1/eTrack/",
        extra={
            "results_path": "eTrackApplicationSearchResults.aspx",
            "results_query": {"Field": "S", "r": "COR.P1.WEBGUEST", "f": "$P1.ETR.SEARCH.STW"},
            "notes": "audit 2026-05-06: working, 32 rows scraped Apr 2026",
        },
    ),
    "Hunters Hill": CouncilSite(
        # WAS: t1_etrack at hunters-hill.t1cloud.com — INCORRECT
        # Council's main site links DA tracking to eplanning.huntershill, an
        # Infor Pathway 'Public' portal (Resources/Scripts/oo_common.js etc).
        council="Hunters Hill",
        vendor="infor_pathway_public",
        base_url="https://eplanning.huntershill.nsw.gov.au/Public/PlanningRegister.aspx",
        extra={"notes": "audit 2026-05-06: title 'EPlanning - Development | PlanningRegister', Infor Pathway Public portal"},
    ),
    "Lane Cove": CouncilSite(
        # WAS: t1_etrack at lanecove.t1cloud.com — INCORRECT
        # Real tracker is a Java/Struts eservice on ecouncil.lanecove.
        council="Lane Cove",
        vendor="infor_eservice_struts",
        base_url="https://ecouncil.lanecove.nsw.gov.au/eservice/dialog/daEnquiryInit.do?doc_type=8&nodeNum=6636",
        extra={"notes": "audit 2026-05-06: same /eservice/dialog/*.do shape as Mosman + Woollahra"},
    ),

    # -- Open Cities / XC.Track --------------------------------------------
    "City of Sydney": CouncilSite(
        council="City of Sydney",
        vendor="open_cities",
        base_url="https://eplanning.cityofsydney.nsw.gov.au/Pages/XC.Track/SearchApplication.aspx",
        extra={"notes": "audit 2026-05-06: 200 OK, genuine XC.Track"},
    ),
    "Bayside": CouncilSite(
        # WAS: civica_authority at eservices.bayside — INCORRECT
        # Council's DA Tracker button points to eplanning.bayside, XC.Track.
        council="Bayside",
        vendor="open_cities",
        base_url="https://eplanning.bayside.nsw.gov.au/ePlanning/Pages/XC.Track/SearchApplication.aspx?as=n",
        extra={"notes": "audit 2026-05-06: XC.Track at eplanning.bayside, not ePathway"},
    ),
    "Georges River": CouncilSite(
        # WAS: civica_authority at eservices.georgesriver — INCORRECT
        # Council's tracker page links etrack.georgesriver, XC.Track.
        council="Georges River",
        vendor="open_cities",
        base_url="https://etrack.georgesriver.nsw.gov.au/Pages/XC.Track/SearchApplication.aspx",
        extra={"notes": "audit 2026-05-06: XC.Track at etrack.georgesriver, not ePathway"},
    ),

    # -- Civica Authority / ePathway ---------------------------------------
    "Randwick": CouncilSite(
        # WAS: open_cities at /T1PRProd/.../eTrackApplicationSearch.aspx — DOUBLY INCORRECT
        # Real tracker is ePathway on onlineservices.randwick.
        council="Randwick",
        vendor="civica_authority",
        base_url="https://onlineservices.randwick.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx",
        extra={"notes": "audit 2026-05-06: ePathway. Was previously misclassified as open_cities with a T1 URL."},
    ),
    "Waverley": CouncilSite(
        # WAS: open_cities at eservices.waverley — INCORRECT
        # Council's DA tracker button points to epwgate.waverley, ePathway.
        council="Waverley",
        vendor="civica_authority",
        base_url="https://epwgate.waverley.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx",
        extra={"notes": "audit 2026-05-06: ePathway at epwgate.waverley, not XC.Track"},
    ),
    "Parramatta": CouncilSite(
        # WAS: custom at /Production/ — partially correct, but URL path is wrong
        # Real path is /Prod/Web/Custom/da-track-choice.htm leading into ePathway.
        council="Parramatta",
        vendor="civica_authority",
        base_url="https://onlineservices.cityofparramatta.nsw.gov.au/ePathway/Prod/Web/GeneralEnquiry/EnquiryLists.aspx",
        extra={"notes": "audit 2026-05-06: ePathway at /Prod/ (not /Production/). Choice page at /Custom/da-track-choice.htm precedes the tracker."},
    ),
    "Canterbury-Bankstown": CouncilSite(
        # Registry URL unreachable from audit machine; vendor inference from
        # eservices.cbcity.nsw.gov.au/ePathway/... links seen on main site.
        council="Canterbury-Bankstown",
        vendor="civica_authority",
        base_url="https://onlineservices.cbcity.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx",
        extra={"notes": "audit 2026-05-06: tracker host did not resolve from audit machine; ePathway shape inferred from cbcity main-site eservices links. Verify on first scrape."},
    ),
    "Inner West": CouncilSite(
        # WAS: civica_authority at eservices.innerwest — UNVERIFIED
        # Inner West's online-services hub is entirely on innerwest.t1cloud.com
        # (CiAnywhere). DA tracker URL not surfaced during audit; previous
        # ePathway URL kept pending a real check on first scrape.
        council="Inner West",
        vendor="civica_authority",
        base_url="https://eservices.innerwest.nsw.gov.au/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx",
        extra={"notes": "audit 2026-05-06: tracker URL not confirmed. Council's other online services have migrated to innerwest.t1cloud.com (CiAnywhere); DA tracker may have followed. Try ePathway URL first; if 404, re-audit with /browse against innerwest.t1cloud.com."},
    ),

    # -- Infor MasterView ---------------------------------------------------
    "North Sydney": CouncilSite(
        # WAS: open_cities at services.northsydney/Common/.../XC.Track — INCORRECT
        # Council's "Development tracking" link is masterview.northsydney.
        council="North Sydney",
        vendor="infor_masterview",
        base_url="https://masterview.northsydney.nsw.gov.au/",
        extra={"notes": "audit 2026-05-06: Infor MasterView (markers: masterview.js, Infor). ASP.NET MVC, /Home/Disclaimer + /Home/Search routes."},
    ),
    "Burwood": CouncilSite(
        # WAS: civica_authority — INCORRECT.
        council="Burwood",
        vendor="infor_masterview",
        base_url="https://datracker.burwood.nsw.gov.au/Home/Search",
        extra={"notes": "audit 2026-05-06: same Infor MasterView shape as North Sydney (masterview.js)"},
    ),
    "Strathfield": CouncilSite(
        # WAS: civica_authority — INCORRECT.
        council="Strathfield",
        vendor="infor_masterview",
        base_url="https://datracker.strathfield.nsw.gov.au/Home/Disclaimer",
        extra={"notes": "audit 2026-05-06: Infor MasterView (datracker.<council>/Home/Disclaimer landing page)"},
    ),

    # -- Infor eservice / Java Struts --------------------------------------
    "Mosman": CouncilSite(
        # WAS: open_cities at applications.mosman/Pages/XC.Track — INCORRECT (host doesn't exist)
        council="Mosman",
        vendor="infor_eservice_struts",
        base_url="https://applicationtracker.mosman.nsw.gov.au/eservice/daEnquiryInit.do?doc_typ=8&nodeNum=119608",
        extra={"notes": "audit 2026-05-06: Java/Struts eservice. Note doc_typ (no E) parameter spelling differs from Lane Cove's doc_type."},
    ),
    "Woollahra": CouncilSite(
        # WAS: open_cities at eservices.woollahra/Common/.../XC.Track — INCORRECT (404)
        # Council page links to auth.woollahra/eservice/navigationStart.do — Java/Struts.
        council="Woollahra",
        vendor="infor_eservice_struts",
        base_url="https://auth.woollahra.nsw.gov.au/eservice/navigationStart.do",
        extra={"notes": "audit 2026-05-06: Java/Struts eservice on auth.woollahra. Entry point is navigationStart; specific daEnquiry URL TBD on adapter build."},
    ),

    # -- Unknown / pending --------------------------------------------------
    "Canada Bay": CouncilSite(
        # WAS: civica_authority at eservices.canadabay — UNVERIFIED.
        # Council's /eservices/da-tracker page surfaces no external tracker
        # link; their eservices hub uses canadabay-web.t1cloud.com which
        # returned blank. Could be ePathway, T1 eTrack, or behind a
        # JavaScript-loaded panel. Re-audit after deeper drill.
        council="Canada Bay",
        vendor="unknown",
        base_url="https://www.canadabay.nsw.gov.au/eservices/da-tracker",
        extra={"notes": "audit 2026-05-06: tracker host not identified. Council eservices hub is canadabay-web.t1cloud.com (T1) but DA-tracker URL pattern not surfaced. Manual verification needed."},
    ),

    # -- TechnologyOne CiAnywhere (newer SPA portal) -----------------------
    "Willoughby": CouncilSite(
        # WAS: open_cities at eservice.willoughby/Common/.../XC.Track — INCORRECT (host doesn't exist)
        # DA tracking lives in CiAnywhere, the newer T1 portal product.
        council="Willoughby",
        vendor="t1_cianywhere",
        base_url="https://willoughby.t1cloud.com/T1Default/CiAnywhere/Web/WILLOUGHBY/Compliance/ApplicationPortalMyEnquiry",
        extra={
            "notes": "audit 2026-05-06: T1 CiAnywhere (different from Ryde's eTrack despite shared 't1cloud.com' domain). SPA portal — adapter likely needs a real browser, not requests+bs4.",
            "search_query": {"f": "$P1.COM.APPLNDAT.ENQ", "suite": "PR", "func": "$P1.COM.APPLNDAT.ENQ", "portal": "PRPORTAL", "isOldGuest": "false"},
        },
    ),
}


_ADAPTERS: dict[str, type[CouncilTrackerAdapter]] = {
    "t1_etrack":        T1eTrackAdapter,
    "open_cities":      OpenCitiesAdapter,
    "civica_authority": CivicaAuthorityAdapter,
    # Vendors stubbed — drop in concrete adapters as they're built:
    # "infor_masterview":      InforMasterViewAdapter,        # 3 councils
    # "infor_eservice_struts": InforEServiceStrutsAdapter,    # 3 councils
    # "t1_cianywhere":         T1CiAnywhereAdapter,           # 2 councils, needs Playwright
    # "infor_pathway_public":  InforPathwayPublicAdapter,     # 1 council
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
