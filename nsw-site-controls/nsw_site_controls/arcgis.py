"""Thin client for ArcGIS REST ``MapServer/<id>/query`` endpoints.

ALL network access in this package funnels through ``_http_get`` so unit tests
can monkeypatch it with recorded fixtures and never touch the network. The NSW
planning layers and the SIX cadastre are both public ArcGIS REST services, so a
plain stdlib ``urllib`` GET against the documented ``query`` operation is the
whole client — no GIS engine, no SDK. [Layer 1: use the published API.]
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 40
DEFAULT_RETRIES = 2            # SIX cadastre in particular is flaky/slow
_BACKOFF = (0.6, 1.5)         # seconds between attempts
_UA = "nsw-site-controls/0.1 (planning-controls CLI)"


class ArcGISError(RuntimeError):
    """Network, HTTP, non-JSON, or ArcGIS-reported error from a service."""


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT, *, accept: str = "application/json",
              retries: int = DEFAULT_RETRIES, _sleep=time.sleep):
    """GET ``url`` and return parsed JSON (dict or list). Raises ArcGISError.

    Centralised so tests monkeypatch exactly one function. Retries only on
    network/HTTP failures (the NSW/SIX services time out intermittently); a
    non-JSON or ArcGIS-reported error is not retried (it would just repeat).
    """
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            break
        except Exception as exc:  # URLError, HTTPError, socket timeout, ...
            last_exc = exc
            if attempt < retries:
                _sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
    else:
        raise ArcGISError(f"GET failed after {retries + 1} tries: {url}: {last_exc}") from last_exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArcGISError(f"non-JSON response from {url}: {raw[:200]!r}") from exc
    if isinstance(data, dict) and "error" in data:
        raise ArcGISError(f"ArcGIS error from {url}: {data['error']}")
    return data


def point_geometry(lon: float, lat: float) -> dict:
    """An esri point geometry in WGS84 (wkid 4326)."""
    return {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}


def query(
    service_url: str,
    layer_id: int,
    *,
    geometry: dict,
    geometry_type: str = "esriGeometryPoint",
    in_sr: int = 4326,
    out_fields: str = "*",
    spatial_rel: str = "esriSpatialRelIntersects",
    return_geometry: bool = False,
    out_sr: int | None = None,
    where: str = "1=1",
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Run a spatial ``query`` and return the raw ``features`` list.

    Each feature is ``{"attributes": {...}, "geometry": {...}?}``. Querying by a
    parcel *polygon* (intersects) instead of a single point is what lets callers
    detect a site that straddles two zoning / FSR polygons.
    """
    base = service_url.rstrip("/") + f"/{layer_id}/query"
    params = {
        "f": "json",
        "where": where,
        "geometry": json.dumps(geometry),
        "geometryType": geometry_type,
        "inSR": in_sr,
        "spatialRel": spatial_rel,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
    }
    if out_sr is not None:
        params["outSR"] = out_sr
    url = base + "?" + urllib.parse.urlencode(params)
    data = _http_get(url, timeout=timeout)
    if not isinstance(data, dict):
        raise ArcGISError(f"unexpected query payload (not an object) from {url}")
    return data.get("features", [])


def query_where(
    service_url: str,
    layer_id: int,
    *,
    where: str,
    out_fields: str = "*",
    return_geometry: bool = True,
    out_sr: int | None = 4326,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Attribute-only query (no geometry filter) — used for lot/DP lookups."""
    base = service_url.rstrip("/") + f"/{layer_id}/query"
    params = {
        "f": "json",
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
    }
    if out_sr is not None:
        params["outSR"] = out_sr
    url = base + "?" + urllib.parse.urlencode(params)
    data = _http_get(url, timeout=timeout)
    if not isinstance(data, dict):
        raise ArcGISError(f"unexpected query payload (not an object) from {url}")
    return data.get("features", [])
