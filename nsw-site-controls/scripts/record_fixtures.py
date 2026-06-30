"""Hit the live services for one golden site and save raw responses as fixtures.

Run when you want to refresh the on-disk fixtures from reality:

    python scripts/record_fixtures.py 151.1043 -33.8136

Writes tests/fixtures/live_<layer>.json. Review the diff before committing — a
changed shape means the upstream service drifted and the parser may need work.
"""
from __future__ import annotations

import json
import pathlib
import sys

from nsw_site_controls import arcgis
from nsw_site_controls.registry import (CADASTRE_LOT_LAYER, CADASTRE_SERVICE,
                                        LAYER_REGISTRY, PLANNING_SERVICE)

OUT = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main(argv):
    if len(argv) != 2:
        print("usage: record_fixtures.py <lon> <lat>", file=sys.stderr)
        return 2
    lon, lat = float(argv[0]), float(argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    pt = arcgis.point_geometry(lon, lat)

    cad = arcgis.query(CADASTRE_SERVICE, CADASTRE_LOT_LAYER, geometry=pt,
                       return_geometry=True, out_sr=4326)
    (OUT / "live_cadastre.json").write_text(json.dumps({"features": cad}, indent=2), encoding="utf-8")
    print(f"cadastre: {len(cad)} feature(s)")

    for spec in LAYER_REGISTRY:
        feats = arcgis.query(PLANNING_SERVICE, spec.layer_id, geometry=pt)
        (OUT / f"live_{spec.key}.json").write_text(
            json.dumps({"features": feats}, indent=2), encoding="utf-8")
        print(f"{spec.key}: {len(feats)} feature(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
