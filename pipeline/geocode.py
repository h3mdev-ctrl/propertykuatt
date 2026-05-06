"""Address / lat-lon -> SA2 (suburb-equivalent) resolver.

We standardise on ABS SA2 boundaries rather than postcodes because:
  * postcodes span multiple councils and bleed across natural market areas
  * SA2s are the geography the ABS uses for population and lending data,
    so anything we normalise per-capita lines up cleanly later.

The shapefile is downloaded once from ABS Statistical Geography Standard
(ASGS) Edition 3 and cached under data/raw/abs_sa2.

If a record arrives with lat/lon, we point-in-polygon to find its SA2.
If only a textual suburb name is available, we fall back to a
suburb-name -> SA2 lookup table (built once from the shapefile attributes).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from pipeline.config import RAW_DIR, SETTINGS

log = logging.getLogger(__name__)

SA2_SHAPEFILE = RAW_DIR / "abs_sa2" / "SA2_2021_AUST_GDA2020.shp"


@lru_cache(maxsize=1)
def _load_sa2() -> gpd.GeoDataFrame:
    if not SA2_SHAPEFILE.exists():
        raise FileNotFoundError(
            f"SA2 shapefile not found at {SA2_SHAPEFILE}. "
            "Download ASGS Ed. 3 SA2 from the ABS website and unzip into "
            f"{SA2_SHAPEFILE.parent}."
        )
    gdf = gpd.read_file(SA2_SHAPEFILE)
    gdf = gdf.to_crs(epsg=4326)
    # Clip to study area bounding box so every point-in-poly stays cheap.
    centre = Point(SETTINGS.area.centre_lon, SETTINGS.area.centre_lat)
    # Approx 1 deg lat ~ 111km; pad generously then filter properly downstream.
    pad_deg = (SETTINGS.area.radius_km / 111.0) * 1.5
    bbox = centre.buffer(pad_deg).bounds
    return gdf.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]].reset_index(drop=True)


def _suburb_lookup() -> dict[str, str]:
    gdf = _load_sa2()
    # SA2_NAME21 is the human-readable suburb-equivalent name.
    return {row["SA2_NAME21"].lower(): row["SA2_CODE21"] for _, row in gdf.iterrows()}


def attach_sa2(df: pd.DataFrame) -> pd.DataFrame:
    """Add `sa2_code` and `sa2_name` columns to a normalised DataFrame.

    Strategy: prefer lat/lon spatial join; fall back to suburb-name match.
    Records that resolve to neither are dropped with a warning count.
    """
    if df.empty:
        df["sa2_code"] = pd.Series(dtype="object")
        df["sa2_name"] = pd.Series(dtype="object")
        return df

    sa2 = _load_sa2()[["SA2_CODE21", "SA2_NAME21", "geometry"]].rename(
        columns={"SA2_CODE21": "sa2_code", "SA2_NAME21": "sa2_name"}
    )

    has_coords = df["lat"].notna() & df["lon"].notna()
    coord_part = df[has_coords].copy()
    text_part = df[~has_coords].copy()

    # Spatial join for records with coordinates.
    if not coord_part.empty:
        gdf = gpd.GeoDataFrame(
            coord_part,
            geometry=gpd.points_from_xy(coord_part["lon"], coord_part["lat"]),
            crs="EPSG:4326",
        )
        coord_part = gpd.sjoin(gdf, sa2, how="left", predicate="within").drop(
            columns=["geometry", "index_right"]
        )

    # Suburb-name match for the rest.
    if not text_part.empty:
        lookup = _suburb_lookup()
        text_part["sa2_code"] = text_part["suburb"].astype(str).str.lower().map(lookup)
        text_part = text_part.merge(
            sa2[["sa2_code", "sa2_name"]].drop_duplicates("sa2_code"),
            on="sa2_code",
            how="left",
        )

    out = pd.concat([coord_part, text_part], ignore_index=True)
    unresolved = out["sa2_code"].isna().sum()
    if unresolved:
        log.warning("%d records unresolved to SA2 (dropped)", unresolved)
    return out.dropna(subset=["sa2_code"]).reset_index(drop=True)
