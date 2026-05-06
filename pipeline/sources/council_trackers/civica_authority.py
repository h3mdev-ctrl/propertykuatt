"""Adapter for Civica Authority / ePathway public DA registers.

Used by Randwick, Waverley, Parramatta, Canterbury-Bankstown, Inner West
(verified or strongly inferred via the 2026-05-06 audit). ePathway is an
ASP.NET WebForms portal exposed as a multi-module enquiry hub.

Anatomy of an ePathway site:

  Hub:    <base>/ePathway/Production/Web/GeneralEnquiry/EnquiryLists.aspx
    A landing page listing enquiry modules — Applications, Customer
    Requests, Licensing, Payments — as a tile grid. Each tile is a
    LinkButton wrapped over an __doPostBack against the hub form. The
    "Applications" tile is the one we want.

    Some deployments swap "Production" for "Prod" in the URL path
    (Parramatta is the wrinkle here). The adapter never assumes the
    capitalisation: ``base_url`` from the registry is treated as the
    EnquiryLists landing whatever it is, and downstream URLs are derived
    by string substitution within the same path prefix.

  Search: <hub>/EnquirySummaryView.aspx (after entering a module)
    A standard ASP.NET WebForms <form> with __VIEWSTATE and
    __EVENTVALIDATION. The search panel exposes Lodged From / Lodged To
    date inputs (formatted dd/mm/yyyy) plus an Application Number text
    box and a few module-specific filters. Submit triggers the same
    page to re-render with a results grid.

  Results: same URL — grid of matching applications below the search
    form. Each row's first cell carries a LinkButton with the
    application number which posts back to load the detail view.
    Pager renders Page$N postback links identical to T1 / XC.Track.

  Detail: <hub>/EnquiryDetailView.aspx (followed via postback)
    Two-column label/value table layout — same shape as T1 / XC.Track
    so the same label-map vocabulary applies.

Compared to XC.Track this adapter has one extra round trip: the hub
postback that selects the Applications module before the date-range
form is even visible.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urljoin

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
_POSTBACK_RE = re.compile(r"__doPostBack\('([^']+)','([^']*)'\)")

# ePathway field-name suffixes. Selectors are best-known defaults; the
# adapter uses suffix matching against the live form so per-council
# template variations get absorbed without code changes.
_APP_TILE_SUFFIXES   = ("mApplicationsTab", "mApplicationsLink", "mApplicationsButton")
_APP_TILE_TEXT_PAT   = re.compile(r"^\s*application", re.I)
_DATE_FROM_SUFFIXES  = (
    "mDateLodgedFromDate$dateInputBox",
    "mFromDate$dateInputBox",
    "mDateLodgedFrom",
    "mFromDate",
    "DateLodgedFrom",
    "FromDate",
)
_DATE_TO_SUFFIXES    = (
    "mDateLodgedToDate$dateInputBox",
    "mToDate$dateInputBox",
    "mDateLodgedTo",
    "mToDate",
    "DateLodgedTo",
    "ToDate",
)
_SEARCH_BTN_SUFFIXES = ("mSearchButton", "mSearch", "btnSearch", "SearchButton")


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


class CivicaAuthorityAdapter(CouncilTrackerAdapter):
    vendor = "civica_authority"

    # ------------------------------------------------------------------ #
    # Setup helpers                                                      #
    # ------------------------------------------------------------------ #

    def _hub_url(self) -> str:
        # ``base_url`` in the registry points at EnquiryLists.aspx.
        return self.site.base_url

    def _search_url(self) -> str:
        # EnquirySummaryView lives in the same directory as EnquiryLists.
        return self._hub_url().rsplit("/", 1)[0] + "/EnquirySummaryView.aspx"

    @staticmethod
    def _soup(resp) -> "BeautifulSoup":  # type: ignore[name-defined]
        from bs4 import BeautifulSoup
        return BeautifulSoup(resp.content, "html.parser")

    @staticmethod
    def _extract_aspx_state(soup) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                     "__PREVIOUSPAGE"):
            tag = soup.find("input", {"name": name})
            if tag is not None:
                out[name] = tag.get("value", "") or ""
        return out

    @staticmethod
    def _find_input_name(soup, suffixes: tuple[str, ...]) -> str | None:
        for inp in soup.find_all(["input", "select", "textarea"]):
            name = inp.get("name") or ""
            for suf in suffixes:
                if name.endswith(suf):
                    return name
        return None

    @classmethod
    def _find_postback_link(cls, soup, *, name_suffixes: tuple[str, ...] = (),
                            text_pattern: re.Pattern | None = None) -> tuple[str, str] | None:
        """Find an <a>/<input> that triggers __doPostBack and matches our
        desired tile. Returns (event_target, event_argument) or None."""
        for a in soup.find_all(["a", "input"]):
            href_or_onclick = a.get("href", "") or a.get("onclick", "")
            text = a.get_text(" ", strip=True) or a.get("value", "") or ""
            m = _POSTBACK_RE.search(href_or_onclick)
            if not m:
                continue
            event_target, event_arg = m.group(1), m.group(2)
            # Match by attribute suffix on the postback target, or by text.
            if name_suffixes and any(event_target.endswith(suf) for suf in name_suffixes):
                return event_target, event_arg
            if text_pattern and text_pattern.match(text):
                return event_target, event_arg
        return None

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    def search(self, lodged_from: date, lodged_to: date) -> Iterator[dict]:
        hub_url = self._hub_url()
        log.info("%s: GET %s (hub)", self.site.council, hub_url)
        resp = self._get(hub_url)
        soup = self._soup(resp)

        # If the hub already exposes a date-range form (some councils
        # default-land on Applications), skip the module-selection step.
        from_field = self._find_input_name(soup, _DATE_FROM_SUFFIXES)
        if not from_field:
            soup = self._enter_applications_module(hub_url, soup)
            if soup is None:
                log.warning("%s: could not enter Applications module from %s",
                            self.site.council, hub_url)
                return

        page_soup = self._submit_date_range(soup, lodged_from, lodged_to)
        if page_soup is None:
            return

        seen: set[str] = set()
        for row in self._walk_paginated(page_soup):
            aid = row.get("application_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)

            lodged = row.get("lodged_date")
            if lodged:
                try:
                    d = date.fromisoformat(lodged)
                except (TypeError, ValueError):
                    d = None
                if d and not (lodged_from <= d <= lodged_to):
                    continue
            yield row

    def _enter_applications_module(self, hub_url: str, hub_soup):
        """Click the Applications tile on the hub. Returns the resulting
        page soup, or None if the tile couldn't be located."""
        target = self._find_postback_link(
            hub_soup,
            name_suffixes=_APP_TILE_SUFFIXES,
            text_pattern=_APP_TILE_TEXT_PAT,
        )
        if not target:
            return None
        event_target, event_arg = target
        form_data = {
            **self._extract_aspx_state(hub_soup),
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": event_arg,
        }
        time.sleep(self.request_delay_s)
        log.info("%s: POST hub __doPostBack target=%s (Applications tile)",
                 self.site.council, event_target)
        post = self._post(hub_url, data=form_data)
        return self._soup(post)

    def _submit_date_range(self, soup, lodged_from: date, lodged_to: date):
        """Fill the Lodged From / Lodged To inputs and submit. Returns the
        results-page soup, or None if the form couldn't be located."""
        from_field = self._find_input_name(soup, _DATE_FROM_SUFFIXES)
        to_field   = self._find_input_name(soup, _DATE_TO_SUFFIXES)
        btn_field  = self._find_input_name(soup, _SEARCH_BTN_SUFFIXES)
        if not (from_field and to_field):
            log.warning(
                "%s: could not locate ePathway date-range inputs (from=%r to=%r). "
                "Selectors may need tuning for this council.",
                self.site.council, from_field, to_field,
            )
            return None

        form_data = {
            **self._extract_aspx_state(soup),
            from_field: lodged_from.strftime("%d/%m/%Y"),
            to_field:   lodged_to.strftime("%d/%m/%Y"),
        }
        if btn_field:
            form_data[btn_field] = "Search"
        else:
            form_data["__EVENTTARGET"] = ""
            form_data["__EVENTARGUMENT"] = ""

        time.sleep(self.request_delay_s)
        url = self._search_url()
        log.info("%s: POST %s with date range %s..%s",
                 self.site.council, url,
                 lodged_from.isoformat(), lodged_to.isoformat())
        post = self._post(url, data=form_data)
        return self._soup(post)

    def _walk_paginated(self, page_soup) -> Iterator[dict]:
        url = self._search_url()
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
        # ePathway's results grid has an id ending in mGridResults /
        # mDataGrid / mEnquiryListGrid depending on theme version.
        table = soup.find("table", id=re.compile(
            r"mGridResults|mEnquiryListGrid|mDataGrid|mGridView|GridResults", re.I))
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
                if "application" in header or "reference" in header or "number" in header:
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

            # Detail link: ePathway uses a __doPostBack on a LinkButton
            # rather than a real href.
            link = tr.find("a", href=True)
            if link:
                m = _POSTBACK_RE.search(link["href"])
                if m:
                    row["_postback_target"] = m.group(1)
                    row["_postback_arg"]    = m.group(2)
                else:
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
        target = summary.get("_postback_target")
        # Direct URL fallback for any deployments that expose real hrefs.
        if not target and not summary.get("source_url"):
            return self._finalise_detail(merged)

        if target:
            url = self._search_url()
            time.sleep(self.request_delay_s)
            # Refresh the search page to get a clean ViewState before
            # posting back to the detail-view link.
            resp = self._get(url)
            soup = self._soup(resp)
            form_data = {
                **self._extract_aspx_state(soup),
                "__EVENTTARGET": target,
                "__EVENTARGUMENT": summary.get("_postback_arg", ""),
            }
            post = self._post(url, data=form_data)
            detail_soup = self._soup(post)
            detail_url = post.url
        else:
            time.sleep(self.request_delay_s)
            resp = self._get(summary["source_url"])
            detail_soup = self._soup(resp)
            detail_url = resp.url

        for label_cell, value_cell in self._iter_label_value_pairs(detail_soup):
            label = (label_cell.get_text(" ", strip=True) or "").lower()
            value = value_cell.get_text(" ", strip=True) or None
            for needle, field in _DETAIL_LABEL_MAP:
                if needle in label:
                    merged[field] = value
                    break

        merged["source_url"] = detail_url
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
        for k in ("_apptype", "_devtype", "_postback_target", "_postback_arg"):
            merged.pop(k, None)
        return merged

    @staticmethod
    def _iter_label_value_pairs(soup):
        for tr in soup.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) == 2:
                yield tds[0], tds[1]
