from nsw_site_controls import arcgis, lep
from nsw_site_controls.locate import Site
from tests.conftest import RYDE_PARCEL


def _site():
    return Site(lon=151.1039, lat=-33.8135, lotidstring="5//DP12345",
                area_m2=600.0, parcel=RYDE_PARCEL, source="lot/DP")


def test_envelope_parses_and_derives(fake_query):
    env = lep.envelope(_site(), query_fn=fake_query)
    assert env.results["zoning"].values[0].value == "R2"
    assert env.results["fsr"].values[0].value == 0.5
    assert env.results["height"].values[0].value == 9.5
    # GFA = 0.5 * 600
    assert env.max_gfa_m2 == [300]
    assert "1 lot" in env.subdivision  # 600 / 580 -> 1


def test_envelope_uses_point_when_no_parcel(fake_query):
    site = Site(lon=151.1, lat=-33.8, source="coords")  # no parcel/area
    env = lep.envelope(site, query_fn=fake_query)
    assert env.results["zoning"].present
    assert env.max_gfa_m2 == []  # no area -> no GFA
    assert any("area unknown" in n for n in env.notes)


def test_split_site_returns_all_zones():
    layers = {
        2: [
            {"attributes": {"SYM_CODE": "R2", "LAY_CLASS": "Low Density",
                            "EPI_NAME": "Ryde LEP 2014"}},
            {"attributes": {"SYM_CODE": "R3", "LAY_CLASS": "Medium Density",
                            "EPI_NAME": "Ryde LEP 2014"}},
        ],
    }
    env = lep.envelope(_site(), query_fn=lambda s, lid, **k: layers.get(lid, []))
    z = env.results["zoning"]
    assert z.is_split and {v.value for v in z.values} == {"R2", "R3"}


def test_layer_error_is_isolated():
    def flaky(service, layer_id, **kw):
        if layer_id == 1:  # FSR layer down
            raise arcgis.ArcGISError("503 service unavailable")
        if layer_id == 2:
            return [{"attributes": {"SYM_CODE": "R2", "LAY_CLASS": "Low Density",
                                    "EPI_NAME": "Ryde LEP 2014"}}]
        return []

    env = lep.envelope(_site(), query_fn=flaky)
    assert env.results["fsr"].error and not env.results["fsr"].present
    assert env.results["zoning"].present   # partial render survives


def test_null_values_skipped():
    layers = {4: [{"attributes": {"LOT_SIZE": None, "UNITS": "m²", "SYM_CODE": "S"}}]}
    env = lep.envelope(_site(), query_fn=lambda s, lid, **k: layers.get(lid, []))
    assert not env.results["min_lot"].present
