"""Adapter for Open Cities / Datacom XC.Track planning portals.

Used by City of Sydney, North Sydney, Willoughby, Woollahra, Waverley,
and Mosman. XC.Track is an ASP.NET WebForms app that exposes a real
date-range search form (unlike T1's canned period buckets) and renders
detail pages at honest URLs we can GET directly.

Anatomy of an XC.Track site:

  Search:  <base>/...XC.Track/SearchApplication.aspx
    POST with a Lodged From / Lodged To date range. The form is a single
    ASP.NET <form> with __VIEWSTATE / __EVENTVALIDATION; submit button is
    a __doPostBack on the search control.

  Results: same URL — server re-renders SearchApplication.aspx with a
    grid of matching applications. Each row links to a detail view via
    a real <a href="EnquirySummaryView.aspx?id=...">.

  Detail:  <base>/...XC.Track/EnquirySummaryView.aspx?id=<token>
    Renders application metadata in a 2-column label/value layout that
    matches the T1 detail shape closely enough to reuse the same
    label-map vocabulary.

  Pagination: the grid below the results includes ``Page$N`` postback
    links, identical mechanism to T1's pager.

Field names inside the search form vary slightly between councils
because XC.Track lets each council theme its template. The selectors
below match the shipped XC.Track defaults and have been observed across
City of Sydney + Mosman; first run against any new council should be
verified via the ``debug`` CLI before relying on the output.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin, urlparse, parse_qs

from pipeline.schema import categorise
from pipeline.sources.council_trackers.base import CouncilTrackerAdapter

log = logging.getLogger(__name__)


_DETAIL_LABEL_MAP: tuple[tuple[str, str], ...] = (
    ("application number", "application_id"),
    ("application no", "application_id"),
    ("reference", "application_id"),
    ("lodgement date", "lodged_date"),
    ("lodged", "lodged_date"),
    ("determination date", "determined_date"),
    ("determined", "determined_date"),
    ("decision date", "determined_date"),
    ("status", "status"),
    ("estimated cost", "cost_of_works"),
    ("cost of works", "cost_of_works"),
    ("estimated value", "cost_of_works"),
    ("estimated development", "cost_of_works"),
    ("development cost", "cost_of_works"),
    ("description", "description"),
    ("proposal", "description"),
    ("proposed development", "description"),
    ("type of application", "_apptype"),
    ("application type", "_apptype"),
    ("development type", "_devtype"),
    ("address", "address"),
    ("property address", "address"),
    ("primary property address", "address"),
    ("location", "address"),
    ("suburb", "suburb"),
    ("postcode", "postcode"),
)

_MONEY_RE = re.compile(r"[-+]?\$?\s*([\d,]+(?:\.\d+)?)")
_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d")

# XC.Track date-range fields. Names below are the shipped defaults — the
# ``ctl00$...`` prefix is appended at runtime by matching against the form.
_DATE_FROM_SUFFIXES = ("mDateLodgedFrom", "mFromDate", "DateLodgedFrom", "FromDate")
_DATE_TO_SUFFIXES   = ("mDateLodgedTo",   "mToDate",   "DateLodgedTo",   "ToDate")
_SEARCH_BTN_SUFFIXES = ("mSearchButton", "btnSearch", "SearchButton")


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


class OpenCitiesAdapter(CouncilTrackerAdapter):
    vendor = "open_cities"

    # Path tail under the council base_url. The registry stores the full
    # SearchApplication.aspx URL as ``base_url`` for these councils, so we
    # treat that as the search entry point directly.
    _DETAIL_FILE = "EnquirySummaryView.aspx"

    def _search_url(self) -> str:
        return self.site.base_url

    @staticmethod
    def _soup(resp) -> "BeautifulSoup":  # type: ignore[name-defined]
        from bs4 import BeautifulSoup
        return BeautifulSoup(resp.content, "html.parser")

    @staticmethod
    def _extract_aspx_state(soup) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                     "__PREVIOUSPAGE", "__EVENTTARGET", "__EVENTARGUMENT"):
            tag = soup.find("input", {"name": name})
            if tag is not None:
                out[name] = tag.get("value", "") or ""
        return out

    @staticmethod
    def _find_input_name(soup, suffixes: tuple[str, ...]) -> str | None:
        for inp in soup.find_all(["input", "select"]):
            name = inp.get("name") or ""
            for suf in suffixes:
                if name.endswith(suf) or name.endswith(suf + "$dateInput"):
                    return name
        return None

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    def search(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        url = self._search_url()
        log.info("%s: GET %s", self.site.council, url)
        resp = self._get(url)
        soup = self._soup(resp)

        from_field = self._find_input_name(soup, _DATE_FROM_SUFFIXES)
        to_field   = self._find_input_name(soup, _DATE_TO_SUFFIXES)
        btn_field  = self._find_input_name(soup, _SEARCH_BTN_SUFFIXES)
        if not (from_field and to_field):
            log.warning(
                "%s: could not locate date-range inputs on %s "
                "(from=%r to=%r). Selectors may need tuning for this council.",
                self.site.council, url, from_field, to_field,
            )
            return

        date_from_str = lodged_from.strftime("%d/%m/%Y")
        date_to_str   = lodged_to.strftime("%d/%m/%Y")

        form_data = {
            **self._extract_aspx_state(soup),
            from_field: date_from_str,
            to_field:   date_to_str,
        }
        # Telerik RadDateInput controls use companion hidden fields with
        # ``$dateInput$ClientState`` carrying a JSON snapshot of the date.
        # Best-effort: if a sibling ClientState input exists, populate it
        # with the same date in the format Telerik expects.
        for field, dt in ((from_field, lodged_from), (to_field, lodged_to)):
            stem = field.rsplit("$", 1)[0] if "$" in field else field
            client_state = self._find_input_name(soup, (stem.split("$")[-1] + "_ClientState",))
            if client_state:
                form_data[client_state] = (
                    '{"enabled":true,"emptyMessage":"",'
                    f'"validationText":"{dt.strftime("%Y-%m-%d-00-00-00")}",'
                    f'"valueAsString":"{dt.strftime("%Y-%m-%d-00-00-00")}",'
                    f'"minDateStr":"1980-01-01-00-00-00",'
                    f'"maxDateStr":"2099-12-31-00-00-00"}}'
                )

        if btn_field:
            form_data[btn_field] = "Search"
        else:
            # Fallback: trigger the search via __doPostBack on the form's
            # default submit control if no obvious button is present.
            form_data["__EVENTTARGET"] = ""
            form_data["__EVENTARGUMENT"] = ""

        time.sleep(self.request_delay_s)
        post = self._post(url, data=form_data)
        page_soup = self._soup(post)

        seen: set[str] = set()
        for row in self._walk_paginated(url, page_soup):
            aid = row.get("application_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)

            # Local trim by lodged_date if the summary surfaced one.
            lodged = row.get("lodged_date")
            if lodged:
                try:
                    d = date.fromisoformat(lodged)
                except (TypeError, ValueError):
                    d = None
                if d and not (lodged_from <= d <= lodged_to):
                    continue
            yield row

    def _walk_paginated(self, url: str, page_soup) -> Iterator[dict]:
        page = 1
        while True:
            for row in self._parse_results_table(page_soup):
                yield row
            page += 1
            next_target = self._next_page_target(page_soup, page)
            if not next_target:
                break
            form_data = {
                **self._extract_aspx_state(page_soup),
                "__EVENTTARGET": next_target,
                "__EVENTARGUMENT": f"Page${page}",
            }
            time.sleep(self.request_delay_s)
            post = self._post(url, data=form_data)
            page_soup = self._soup(post)

    def _parse_results_table(self, soup) -> Iterator[dict]:
        # XC.Track grids render with an id matching ``mDataGrid``,
        # ``mGridView`` or ``ResultsGrid`` depending on theme version.
        table = soup.find("table", id=re.compile(r"DataGrid|GridView|Results", re.I))
        if table is None:
            return
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not headers:
            return
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if not tds or len(tds) != len(headers):
                continue
            cells = [td.get_text(" ", strip=True) for td in tds]
            row: dict = {}
            for header, value in zip(headers, cells):
                if "application" in header or "reference" in header:
                    row["application_id"] = value
                elif "lodged" in header or "lodgement" in header:
                    row["lodged_date"] = _parse_date(value)
                elif "determin" in header or "decision" in header:
                    row["determined_date"] = _parse_date(value)
                elif "status" in header:
                    row["status"] = value
                elif "address" in header or "property" in header or "location" in header:
                    row["address"] = value
                elif "type" in header:
                    row["_devtype"] = value
                elif "description" in header or "proposal" in header:
                    row["description"] = value
                elif "value" in header or "cost" in header or "estimated" in header:
                    row["cost_of_works"] = _parse_money(value)

            # Detail link is a real anchor on XC.Track (no postback).
            link = tr.find("a", href=re.compile(self._DETAIL_FILE, re.I))
            if link:
                row["source_url"] = urljoin(self._search_url(), link["href"])

            if row.get("application_id"):
                yield row

    @staticmethod
    def _next_page_target(soup, target_page: int) -> str | None:
        for a in soup.find_all("a", href=True):
            m = re.search(r"__doPostBack\('([^']+)','Page\$(\d+)'\)", a["href"])
            if m and int(m.group(2)) == target_page:
                return m.group(1)
        return None

    # ------------------------------------------------------------------ #
    # Detail                                                             #
    # ------------------------------------------------------------------ #

    def fetch_detail(self, summary: dict) -> dict:
        merged = dict(summary)
        detail_url = summary.get("source_url")
        if not detail_url:
            return self._finalise_detail(merged)

        time.sleep(self.request_delay_s)
        resp = self._get(detail_url)
        detail_soup = self._soup(resp)

        for label_cell, value_cell in self._iter_label_value_pairs(detail_soup):
            label = (label_cell.get_text(" ", strip=True) or "").lower()
            value = value_cell.get_text(" ", strip=True) or None
            for needle, field in _DETAIL_LABEL_MAP:
                if needle in label:
                    merged[field] = value
                    break

        merged["source_url"] = resp.url
        return self._finalise_detail(merged)

    @staticmethod
    def _finalise_detail(merged: dict) -> dict:
        merged["cost_of_works"] = _parse_money(merged.get("cost_of_works"))
        if isinstance(merged.get("lodged_date"), str):
            merged["lodged_date"] = _parse_date(merged["lodged_date"])
        if isinstance(merged.get("determined_date"), str):
            merged["determined_date"] = _parse_date(merged["determined_date"])
        merged["category"] = categorise(
            merged.get("_devtype") or merged.get("_apptype") or merged.get("description")
        )
        for k in ("_apptype", "_devtype"):
            merged.pop(k, None)
        return merged

    @staticmethod
    def _iter_label_value_pairs(soup):
        for tr in soup.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) == 2:
                yield tds[0], tds[1]
