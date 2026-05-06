"""Adapter for TechnologyOne T1 / eProperty / eTrack public DA registers.

Used by Ryde, Hunters Hill, Lane Cove and a number of regional councils.

Anatomy of an eTrack site:

  Search results: <base>/eTrackApplicationSearchResults.aspx
    ?Field=S
    &Period=<period_code>
    &r=COR.P1.WEBGUEST
    &f=$P1.ETR.SEARCH.STW

  Period codes (observed across councils):
    TW = This Week, LW = Last Week,
    TM = This Month, LM = Last Month,
    TY = This Year, LY = Last Year

  Detail page: <base>/eTrackApplicationDetails.aspx
    ?r=COR.P1.WEBGUEST
    &f=$P1.ETR.APPDET.VIW
    &ApplicationId=<id>      (parameter name varies; sometimes ``r1``)

The pages are server-rendered ASP.NET WebForms — searches paginate via
__doPostBack on a __VIEWSTATE form, and detail pages render as labelled
field/value rows in a table. There is no documented JSON endpoint.

Because period codes only span up to a year, the adapter walks
month-buckets when a wider date range is requested, switching to
``Period=LM`` and stepping the system clock... no, we can't step the
clock. Instead we use the ``DateLodged`` advanced-search form which
accepts arbitrary from/to dates via POST. That form lives at
``eTrackApplicationSearch.aspx``.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup  # noqa: F401  -- imported lazily where needed

from pipeline.schema import categorise
from pipeline.sources.council_trackers.base import CouncilTrackerAdapter

log = logging.getLogger(__name__)


# Mapping of common label strings on the detail page to canonical fields.
# Labels vary slightly between councils; lower-cased substring match.
_DETAIL_LABEL_MAP: tuple[tuple[str, str], ...] = (
    ("application number", "application_id"),
    ("application no", "application_id"),
    ("lodgement date", "lodged_date"),
    ("lodged", "lodged_date"),
    ("determination date", "determined_date"),
    ("determined", "determined_date"),
    ("status", "status"),
    ("estimated cost", "cost_of_works"),
    ("cost of works", "cost_of_works"),
    ("estimated value", "cost_of_works"),
    ("development cost", "cost_of_works"),
    ("description", "description"),
    ("proposal", "description"),
    ("type of application", "_apptype"),
    ("application type", "_apptype"),
    ("development type", "_devtype"),
    ("address", "address"),
    ("property address", "address"),
    ("suburb", "suburb"),
    ("postcode", "postcode"),
)


_MONEY_RE = re.compile(r"[-+]?\$?\s*([\d,]+(?:\.\d+)?)")
_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d")


def _parse_money(s: str | None) -> float | None:
    if not s:
        return None
    m = _MONEY_RE.search(s)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return v if v > 0 else None


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class T1eTrackAdapter(CouncilTrackerAdapter):
    vendor = "t1_etrack"

    # eTrack splits very long ranges across pages. We chunk wide windows
    # into 31-day slices and concat to keep result tables small + reduce
    # the chance of pagination edge cases.
    _max_window_days = 31

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    def search(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        cur = lodged_from
        while cur <= lodged_to:
            window_end = min(cur + timedelta(days=self._max_window_days - 1), lodged_to)
            yield from self._search_window(cur, window_end)
            cur = window_end + timedelta(days=1)

    def _search_url(self) -> str:
        path = (self.site.extra or {}).get("results_path", "eTrackApplicationSearchResults.aspx")
        return urljoin(self.site.base_url, path)

    def _search_window(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        """Submit the date-range advanced search and walk paginated results.

        T1 eTrack's advanced search form posts back to itself with
        __VIEWSTATE preserved. We do a GET to acquire the form, then a POST
        with the date range filled in. Pagination is via __EVENTTARGET on
        the same form.
        """
        from bs4 import BeautifulSoup

        url = self._search_url()
        # Initial GET — establishes session + ViewState.
        resp = self._get(url, params=(self.site.extra or {}).get("results_query", {}))
        soup = BeautifulSoup(resp.text, "html.parser")

        viewstate = self._extract_aspx_state(soup)
        if not viewstate:
            log.warning("%s: no ASPX viewstate found at %s — page layout may have changed",
                        self.site.council, url)
            return

        # Find the date inputs. T1 commonly uses control IDs like
        # ``ctl00$Content$txtDateFrom`` / ``ctl00$Content$txtDateTo`` but
        # the exact prefix varies by skin. We pattern-match by suffix.
        date_from_name = self._find_input_name(soup, suffixes=("txtDateFrom", "txtFromDate", "DateLodgedFrom"))
        date_to_name   = self._find_input_name(soup, suffixes=("txtDateTo",   "txtToDate",   "DateLodgedTo"))
        submit_name    = self._find_input_name(soup, suffixes=("btnSearch", "btnGo"))

        if not (date_from_name and date_to_name and submit_name):
            log.warning("%s: could not locate date-range form fields — falling back to Period=LM scrape",
                        self.site.council)
            yield from self._scrape_period(soup)
            return

        form_data = {
            **viewstate,
            date_from_name: lodged_from.strftime("%d/%m/%Y"),
            date_to_name:   lodged_to.strftime("%d/%m/%Y"),
            submit_name:    "Search",
        }
        post = self._post(url, data=form_data)
        page_soup = BeautifulSoup(post.text, "html.parser")

        page = 1
        while True:
            for row in self._parse_results_table(page_soup):
                yield row
            page += 1
            next_target = self._next_page_target(page_soup, page)
            if not next_target:
                break
            form_data["__EVENTTARGET"] = next_target
            form_data["__EVENTARGUMENT"] = ""
            form_data.update(self._extract_aspx_state(page_soup))
            time.sleep(self.request_delay_s)
            post = self._post(url, data=form_data)
            page_soup = BeautifulSoup(post.text, "html.parser")

    def _scrape_period(self, soup) -> Iterator[dict]:
        yield from self._parse_results_table(soup)

    # ------------------------------------------------------------------ #
    # Detail                                                             #
    # ------------------------------------------------------------------ #

    def fetch_detail(self, summary: dict) -> dict:
        from bs4 import BeautifulSoup

        time.sleep(self.request_delay_s)
        detail_url = summary.get("source_url")
        if not detail_url:
            return summary

        resp = self._get(detail_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        merged = dict(summary)
        for label_cell, value_cell in self._iter_label_value_pairs(soup):
            label = (label_cell.get_text(" ", strip=True) or "").lower()
            value = value_cell.get_text(" ", strip=True) or None
            for needle, field in _DETAIL_LABEL_MAP:
                if needle in label:
                    merged[field] = value
                    break

        merged["cost_of_works"] = _parse_money(merged.get("cost_of_works"))
        merged["lodged_date"] = _parse_date(merged.get("lodged_date"))
        merged["determined_date"] = _parse_date(merged.get("determined_date"))
        merged["category"] = categorise(merged.get("_devtype") or merged.get("_apptype") or merged.get("description"))
        merged["source_url"] = detail_url
        # _apptype / _devtype are scratch fields — drop before returning.
        merged.pop("_apptype", None)
        merged.pop("_devtype", None)
        return merged

    # ------------------------------------------------------------------ #
    # ASPX helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_aspx_state(soup) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
            tag = soup.find("input", {"name": name})
            if tag and tag.get("value") is not None:
                out[name] = tag["value"]
        return out

    @staticmethod
    def _find_input_name(soup, suffixes: tuple[str, ...]) -> str | None:
        for inp in soup.find_all(["input", "select"]):
            name = inp.get("name") or ""
            for suf in suffixes:
                if name.endswith(suf):
                    return name
        return None

    def _parse_results_table(self, soup) -> Iterator[dict]:
        """Yield summary dicts from the search results table.

        T1 renders results as a single ``<table>`` with a header row and
        clickable application-number cells linking to the detail page.
        """
        from bs4 import BeautifulSoup  # noqa: F401

        table = soup.find("table", id=re.compile(r"grd|Results|Search", re.I))
        if table is None:
            return
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            cells = [td.get_text(" ", strip=True) for td in tds]
            link = tr.find("a", href=True)
            row: dict = {}
            for header, value in zip(headers, cells):
                if "application" in header and "number" in header:
                    row["application_id"] = value
                elif "lodged" in header or "lodgement" in header:
                    row["lodged_date"] = _parse_date(value)
                elif "determin" in header:
                    row["determined_date"] = _parse_date(value)
                elif "status" in header:
                    row["status"] = value
                elif "address" in header or "property" in header:
                    row["address"] = value
                elif "type" in header:
                    row["_devtype"] = value
                elif "description" in header or "proposal" in header:
                    row["description"] = value
                elif "value" in header or "cost" in header or "estimated" in header:
                    row["cost_of_works"] = _parse_money(value)
            if link:
                row["source_url"] = urljoin(self.site.base_url, link["href"])
            if row.get("application_id"):
                yield row

    @staticmethod
    def _next_page_target(soup, target_page: int) -> str | None:
        """Find the __EVENTTARGET that advances to ``target_page``.

        T1 pagers render as a row of <a href="javascript:__doPostBack('ctl..','Page$N')">
        links — we extract the matching anchor's postback target.
        """
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"__doPostBack\('([^']+)','Page\$(\d+)'\)", href)
            if m and int(m.group(2)) == target_page:
                return m.group(1)
        return None

    @staticmethod
    def _iter_label_value_pairs(soup):
        """Yield (label_cell, value_cell) tuples from any 2-column table layout."""
        for tr in soup.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) == 2:
                yield tds[0], tds[1]
