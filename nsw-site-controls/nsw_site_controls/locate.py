"""Turn a user-supplied location into a :class:`Site` (point + parcel + area).

Three input paths, in order of how trustworthy the result is:

    --coords lon,lat   exact point; we enrich with the containing parcel
    --lot 5/DP12345    authoritative; we look the parcel up by lot/DP
    "12 Smith St ..."  best-effort geocode (Nominatim); ALWAYS warns to verify

Parcel area comes from the cadastre's ``planlotarea`` field (the surveyed area
from the plan), NOT from the polygon geometry — the cadastre is served in Web
Mercator where polygon area is distorted. Authoritative field beats clever math.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import arcgis
from .registry import CADASTRE_LOT_LAYER, CADASTRE_SERVICE


@dataclass
class Site:
    lon: float
    lat: float
    lotidstring: str | None = None
    area_m2: float | None = None
    area_source: str | None = None   # "planlotarea" | "geometry"
    parcel: dict | None = None       # esri polygon geometry in wkid 4326
    source: str = ""                 # how we resolved it
    warnings: list[str] = field(default_factory=list)


# --- helpers ----------------------------------------------------------------
def convert_area(value, units) -> float | None:
    """Cadastre area -> square metres. Units are 'm2'/'ha' (case/spelling vary)."""
    if value in (None, "", 0):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = (units or "").strip().lower()
    if u.startswith("ha") or u == "h":
        return v * 10_000.0
    return v  # assume square metres


def polygon_area_m2(rings) -> float | None:
    """Area of a lon/lat ring set in square metres.

    The SIX cadastre's ``planlotarea`` field is frequently NULL, and its stored
    ``shape_Area`` is in Web Mercator (distorted ~1/cos²(lat) ≈ 1.45× at Sydney).
    So we compute from the WGS84 geometry directly: project each ring to local
    metres with an equirectangular projection at the ring's mean latitude
    (sub-0.1% error at parcel scale), then signed-shoelace. Holes (reverse-wound
    rings) subtract via their sign, so multi-ring parcels net out correctly.
    """
    if not rings:
        return None
    total = 0.0
    for ring in rings:
        pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
        if len(pts) < 3:
            continue
        lat0 = sum(p[1] for p in pts) / len(pts)
        mx = 111_320.0 * math.cos(math.radians(lat0))
        my = 110_540.0
        xy = [(p[0] * mx, p[1] * my) for p in pts]
        s = 0.0
        for i in range(len(xy)):
            x1, y1 = xy[i]
            x2, y2 = xy[(i + 1) % len(xy)]
            s += x1 * y2 - x2 * y1
        total += s / 2.0
    area = abs(total)
    return area if area > 0 else None


def _ring_centroid(rings) -> tuple[float, float] | None:
    """Rough centroid: mean of the outer ring's vertices (good enough to query)."""
    if not rings:
        return None
    ring = rings[0]
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _parcel_from_feature(feat: dict) -> tuple[dict | None, str | None, float | None]:
    attrs = feat.get("attributes", {})
    geom = feat.get("geometry")
    parcel = None
    if geom and "rings" in geom:
        parcel = {"rings": geom["rings"], "spatialReference": {"wkid": 4326}}
    lotid = attrs.get("lotidstring")
    # planlotarea is authoritative but often NULL -> fall back to the geometry.
    area = convert_area(attrs.get("planlotarea"), attrs.get("planlotareaunits"))
    area_source = "planlotarea" if area is not None else None
    if area is None and parcel:
        area = polygon_area_m2(parcel["rings"])
        area_source = "geometry" if area is not None else None
    return parcel, lotid, area, area_source


# --- input paths ------------------------------------------------------------
def from_coords(lon: float, lat: float, *, query_fn=arcgis.query) -> Site:
    """Point -> enrich with the containing cadastral parcel (best effort)."""
    site = Site(lon=lon, lat=lat, source="coords")
    try:
        feats = query_fn(
            CADASTRE_SERVICE, CADASTRE_LOT_LAYER,
            geometry=arcgis.point_geometry(lon, lat),
            geometry_type="esriGeometryPoint", in_sr=4326,
            return_geometry=True, out_sr=4326,
        )
    except arcgis.ArcGISError as exc:
        site.warnings.append(f"cadastre lookup failed: {exc}")
        return site
    if not feats:
        site.warnings.append("no cadastral parcel found at this point; site area unknown")
        return site
    if len(feats) > 1:
        site.warnings.append(f"{len(feats)} parcels at this point (strata?); using the first")
    parcel, lotid, area, area_source = _parcel_from_feature(feats[0])
    site.parcel, site.lotidstring, site.area_m2, site.area_source = parcel, lotid, area, area_source
    return site


def parse_lot(ref: str) -> tuple[str, str]:
    """'5/DP12345' or '5//DP12345' or '5 DP12345' -> ('5', 'DP12345')."""
    s = ref.strip().upper().replace("\\", "/")
    m = re.match(r"^\s*([0-9A-Z]+)\s*/{1,2}\s*(?:[0-9A-Z]*\s*/\s*)?((?:DP|SP)?\s*\d+)\s*$", s)
    if not m:
        # also accept "LOT 5 DP 12345"
        m = re.match(r"^\s*(?:LOT\s*)?([0-9A-Z]+)\s+(?:SEC\s*\S+\s+)?((?:DP|SP)?\s*\d+)\s*$", s)
    if not m:
        raise ValueError(f"could not parse lot reference {ref!r} (try '5/DP12345')")
    lot = m.group(1)
    plan = m.group(2).replace(" ", "")
    if not plan.startswith(("DP", "SP")):
        plan = "DP" + plan
    return lot, plan


def from_lot(ref: str, *, query_fn=arcgis.query_where) -> Site:
    """Look up a parcel by lot number + plan label (DP/SP)."""
    lot, plan = parse_lot(ref)
    where = f"lotnumber='{lot}' AND planlabel='{plan}'"
    feats = query_fn(
        CADASTRE_SERVICE, CADASTRE_LOT_LAYER,
        where=where, return_geometry=True, out_sr=4326,
    )
    if not feats:
        raise LookupError(f"no parcel found for lot {lot}/{plan}")
    parcel, lotid, area, area_source = _parcel_from_feature(feats[0])
    centroid = _ring_centroid(parcel["rings"]) if parcel else None
    if centroid is None:
        raise LookupError(f"parcel {lot}/{plan} has no usable geometry")
    site = Site(lon=centroid[0], lat=centroid[1], lotidstring=lotid or f"{lot}/{plan}",
                area_m2=area, area_source=area_source, parcel=parcel, source="lot/DP")
    if len(feats) > 1:
        site.warnings.append(f"{len(feats)} parcels matched {lot}/{plan}; using the first")
    return site


def geocode_address(address: str, *, timeout: int = 30) -> tuple[float, float]:
    """Best-effort AU address -> (lon, lat) via OpenStreetMap Nominatim.

    Isolated here so it is trivially swappable for a NSW geocoder with a key.
    """
    params = urllib.parse.urlencode(
        {"q": address, "format": "json", "countrycodes": "au", "limit": 1}
    )
    url = "https://nominatim.openstreetmap.org/search?" + params
    req = urllib.request.Request(url, headers={"User-Agent": arcgis._UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise LookupError(f"geocoding failed for {address!r}: {exc}") from exc
    if not data:
        raise LookupError(f"no geocoding match for {address!r}")
    return float(data[0]["lon"]), float(data[0]["lat"])


def from_address(address: str, *, query_fn=arcgis.query) -> Site:
    lon, lat = geocode_address(address)
    site = from_coords(lon, lat, query_fn=query_fn)
    site.source = f"address (geocoded): {address}"
    site.warnings.insert(0, "address was geocoded approximately — verify the point/lot in SixMaps")
    return site


def resolve(*, coords=None, lot=None, address=None) -> Site:
    """Dispatch to the right input path. Exactly one argument should be set."""
    if coords:
        lon, lat = coords
        return from_coords(lon, lat)
    if lot:
        return from_lot(lot)
    if address:
        return from_address(address)
    raise ValueError("provide one of: coords, lot, address")
