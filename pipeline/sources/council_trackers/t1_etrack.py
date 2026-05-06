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

from pipeline.schema import categorise_with_id
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

    # T1 eTrack does not expose an arbitrary date-range search at the
    # public results URL — instead it has six canned "period" buckets,
    # each with a matching form code:
    #
    #   Period=TW  f=$P1.ETR.SEARCH.STW   This Week
    #   Period=LW  f=$P1.ETR.SEARCH.SLW   Last Week
    #   Period=TM  f=$P1.ETR.SEARCH.STM   This Month
    #   Period=LM  f=$P1.ETR.SEARCH.SLM   Last Month
    #   Period=TY  f=$P1.ETR.SEARCH.STY   This Year
    #   Period=LY  f=$P1.ETR.SEARCH.SLY   Last Year
    #
    # Strategy: pick the smallest set of periods that covers the
    # requested [lodged_from, lodged_to] window, hit each, dedupe by
    # application_id, and post-filter rows by their parsed lodged_date.
    _PERIOD_FORM = "$P1.ETR.SEARCH.S{code}"

    def _periods_covering(self, lodged_from: date, lodged_to: date) -> list[str]:
        today = date.today()
        # Approximate period bounds — generous on both sides so we
        # never under-cover the requested window. Local date filtering
        # handles the trim.
        first_of_month = today.replace(day=1)
        first_of_year  = today.replace(month=1, day=1)
        prev_month_end = first_of_month - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        bounds: dict[str, tuple[date, date]] = {
            "TW": (today - timedelta(days=today.weekday()), today),
            "LW": (today - timedelta(days=today.weekday() + 7),
                   today - timedelta(days=today.weekday() + 1)),
            "TM": (first_of_month, today),
            "LM": (prev_month_start, prev_month_end),
            "TY": (first_of_year, today),
            "LY": (first_of_year.replace(year=first_of_year.year - 1),
                   first_of_year - timedelta(days=1)),
        }
        # Prefer narrower buckets first to minimise duplicate fetching.
        priority = ["TW", "LW", "TM", "LM", "TY", "LY"]
        chosen: list[str] = []
        covered_from, covered_to = None, None
        for code in priority:
            b_from, b_to = bounds[code]
            # Skip buckets fully outside the requested window.
            if b_to < lodged_from or b_from > lodged_to:
                continue
            chosen.append(code)
            covered_from = min(b_from, covered_from) if covered_from else b_from
            covered_to   = max(b_to,   covered_to)   if covered_to   else b_to
            if covered_from <= lodged_from and covered_to >= lodged_to:
                break
        return chosen or ["LM"]

    @staticmethod
    def _soup(resp) -> "BeautifulSoup":
        from bs4 import BeautifulSoup
        # T1 serves CP1252 but doesn't always declare it; pass raw bytes
        # so bs4 sniffs the meta tag rather than relying on requests'
        # default ISO-8859-1.
        return BeautifulSoup(resp.content, "html.parser")

    def search(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        seen: set[str] = set()
        url = urljoin(self.site.base_url, "eTrackApplicationSearchResults.aspx")
        base_q = {"Field": "S", "r": (self.site.extra or {}).get("results_query", {}).get("r", "COR.P1.WEBGUEST")}

        for code in self._periods_covering(lodged_from, lodged_to):
            params = {**base_q, "Period": code, "f": self._PERIOD_FORM.format(code=code)}
            log.info("%s: GET Period=%s", self.site.council, code)
            try:
                resp = self._get(url, params=params)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: Period=%s fetch failed: %s", self.site.council, code, exc)
                continue
            soup = self._soup(resp)
            for row in self._walk_paginated(url, soup, params):
                aid = row.get("application_id")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                # Stash the search-page URL + params so fetch_detail can
                # re-acquire ViewState before posting back.
                row["_search_url"] = url
                row["_search_params"] = params
                # Local trim by lodged_date if present in summary.
                lodged = row.get("lodged_date")
                if lodged:
                    try:
                        d = date.fromisoformat(lodged)
                    except (TypeError, ValueError):
                        d = None
                    if d and not (lodged_from <= d <= lodged_to):
                        continue
                yield row

    def _walk_paginated(self, url: str, page_soup, params: dict) -> Iterator[dict]:
        """Walk paginated results inside a single Period bucket."""
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
                "__EVENTARGUMENT": "",
            }
            time.sleep(self.request_delay_s)
            post = self._post(url, params=params, data=form_data)
            page_soup = self._soup(post)

    # ------------------------------------------------------------------ #
    # Detail                                                             #
    # ------------------------------------------------------------------ #

    def fetch_detail(self, summary: dict) -> dict:
        """Fetch the application's detail view via __doPostBack.

        T1 detail links are JavaScript postbacks against the search-page
        form, not real URLs. We refresh the search page (cheap — the
        Period bucket is cached server-side), grab a fresh ViewState,
        then POST with __EVENTTARGET set to the row's postback control.
        The server responds with the rendered detail page.
        """
        merged = dict(summary)
        target = summary.get("_postback_target")
        if not target:
            # Fall back to whatever data we already have from the summary row.
            return self._finalise_detail(merged)

        time.sleep(self.request_delay_s)
        search_url = summary.get("_search_url")
        search_params = summary.get("_search_params") or {}
        resp = self._get(search_url, params=search_params)
        page_soup = self._soup(resp)

        form_data = {
            **self._extract_aspx_state(page_soup),
            "__EVENTTARGET": target,
            "__EVENTARGUMENT": summary.get("_postback_arg", ""),
        }
        post = self._post(search_url, params=search_params, data=form_data)
        detail_soup = self._soup(post)

        for label_cell, value_cell in self._iter_label_value_pairs(detail_soup):
            label = (label_cell.get_text(" ", strip=True) or "").lower()
            value = value_cell.get_text(" ", strip=True) or None
            for needle, field in _DETAIL_LABEL_MAP:
                if needle in label:
                    merged[field] = value
                    break

        merged["source_url"] = post.url
        return self._finalise_detail(merged)

    @staticmethod
    def _finalise_detail(merged: dict) -> dict:
        merged["cost_of_works"] = _parse_money(merged.get("cost_of_works"))
        if isinstance(merged.get("lodged_date"), str):
            merged["lodged_date"] = _parse_date(merged["lodged_date"])
        if isinstance(merged.get("determined_date"), str):
            merged["determined_date"] = _parse_date(merged["determined_date"])
        merged["category"] = categorise_with_id(
            merged.get("_devtype") or merged.get("_apptype") or merged.get("description"),
            merged.get("application_id"),
        )
        # Scratch fields used during scrape — drop before returning.
        for k in ("_apptype", "_devtype", "_postback_target", "_postback_arg",
                  "_search_url", "_search_params"):
            merged.pop(k, None)
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

    _POSTBACK_RE = re.compile(r"__doPostBack\('([^']+)','([^']*)'\)")

    def _parse_results_table(self, soup) -> Iterator[dict]:
        """Yield summary dicts from the search results table.

        T1 renders results as a ``<table class="grid">`` with one header
        row of ``<th>`` cells and one ``<tr>`` of ``<td>`` cells per
        application. Application-number cells contain a postback link
        rather than a real href; we capture the postback control name in
        ``_postback_target`` so ``fetch_detail`` can follow it.
        """
        table = soup.find("table", id=re.compile(r"grd|Results|Search", re.I))
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
                if "application" in header:        # "Application Link", "Application Number", ...
                    row["application_id"] = value
                elif "lodged" in header or "lodgement" in header:
                    row["lodged_date"] = _parse_date(value)
                elif "determin" in header:
                    row["determined_date"] = _parse_date(value)
                elif "status" in header:
                    row["status"] = value
                elif "address" in header or "property" in header:
                    row["address"] = value
                elif "group" in header:            # "Group Description" — application category
                    row["_devtype"] = value
                elif "description" in header or "proposal" in header:
                    row["description"] = value
                elif "value" in header or "cost" in header or "estimated" in header:
                    row["cost_of_works"] = _parse_money(value)

            # First cell usually holds the postback link to the detail view.
            link = tds[0].find("a", href=True)
            if link:
                m = self._POSTBACK_RE.search(link["href"])
                if m:
                    row["_postback_target"] = m.group(1)
                    row["_postback_arg"] = m.group(2)
                else:
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
