"""Shared fixtures: build esri-style features and a fake layered query_fn.

No test touches the network — they inject query_fn or monkeypatch
``arcgis._http_get``. One on-disk fixture (fixtures/ryde_r2_fsr.json) proves we
parse a real-shaped ArcGIS response.
"""
from __future__ import annotations

import json
import pathlib

import pytest

FIX = pathlib.Path(__file__).parent / "fixtures"

# A small square parcel near Ryde, ~600 m² (rough), in WGS84.
RYDE_PARCEL = {
    "rings": [[
        [151.10400, -33.81360],
        [151.10400, -33.81340],
        [151.10380, -33.81340],
        [151.10380, -33.81360],
        [151.10400, -33.81360],
    ]],
    "spatialReference": {"wkid": 4326},
}


def feature(attrs: dict, geometry: dict | None = None) -> dict:
    f = {"attributes": attrs}
    if geometry is not None:
        f["geometry"] = geometry
    return f


@pytest.fixture
def ryde_layers():
    """Map layer_id -> features, mimicking an R2 Ryde site."""
    return {
        2: [feature({"SYM_CODE": "R2", "LAY_CLASS": "Low Density Residential",
                     "EPI_NAME": "Ryde Local Environmental Plan 2014"})],
        1: [feature({"FSR": 0.5, "SYM_CODE": "N",
                     "EPI_NAME": "Ryde Local Environmental Plan 2014"})],
        5: [feature({"MAX_B_H": 9.5, "UNITS": "m", "SYM_CODE": "I",
                     "EPI_NAME": "Ryde Local Environmental Plan 2014"})],
        4: [feature({"LOT_SIZE": 580, "UNITS": "m²", "SYM_CODE": "S",
                     "EPI_NAME": "Ryde Local Environmental Plan 2014"})],
        0: [],  # not heritage
    }


@pytest.fixture
def fake_query(ryde_layers):
    def _q(service, layer_id, *, geometry=None, geometry_type=None, **kw):
        return ryde_layers.get(layer_id, [])
    return _q


@pytest.fixture
def cadastre_lot_feature():
    return feature(
        {"lotnumber": "5", "planlabel": "DP12345", "lotidstring": "5//DP12345",
         "planlotarea": 600.0, "planlotareaunits": "m2"},
        geometry={"rings": RYDE_PARCEL["rings"]},
    )


def load_fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))
