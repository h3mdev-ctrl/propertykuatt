import pytest

from nsw_site_controls import locate


@pytest.mark.parametrize("ref,expected", [
    ("5/DP12345", ("5", "DP12345")),
    ("5//DP12345", ("5", "DP12345")),
    ("5\\\\DP12345", ("5", "DP12345")),
    ("5 DP12345", ("5", "DP12345")),
    ("LOT 5 DP 12345", ("5", "DP12345")),
    ("12/SP56789", ("12", "SP56789")),
    ("7/DP1000", ("7", "DP1000")),
    ("3//12345", ("3", "DP12345")),
])
def test_parse_lot(ref, expected):
    assert locate.parse_lot(ref) == expected


def test_parse_lot_bad():
    with pytest.raises(ValueError):
        locate.parse_lot("not a lot")


@pytest.mark.parametrize("value,units,expected", [
    (600, "m2", 600.0),
    (600, "m²", 600.0),
    (0.06, "ha", 600.0),
    (0.06, "HA", 600.0),
    (None, "m2", None),
    ("", "m2", None),
])
def test_convert_area(value, units, expected):
    assert locate.convert_area(value, units) == expected


def test_polygon_area_m2_unit_square():
    # 0.001 deg lon x 0.001 deg lat near Sydney -> ~ (92.5 m x 110.5 m) ~ 10220 m²
    lat0 = -33.81
    rings = [[
        [151.000, lat0], [151.001, lat0], [151.001, lat0 + 0.001],
        [151.000, lat0 + 0.001], [151.000, lat0],
    ]]
    area = locate.polygon_area_m2(rings)
    assert 9_500 < area < 11_000


def test_area_falls_back_to_geometry_when_planlotarea_null():
    feat = {
        "attributes": {"lotidstring": "3//DP24994",
                       "planlotarea": None, "planlotareaunits": None},
        "geometry": {"rings": [[
            [151.09300, -33.80760], [151.09340, -33.80760],
            [151.09340, -33.80740], [151.09300, -33.80740],
            [151.09300, -33.80760],
        ]]},
    }
    parcel, lotid, area, area_source = locate._parcel_from_feature(feat)
    assert lotid == "3//DP24994"
    assert area and area > 0   # computed from geometry, not planlotarea
    assert area_source == "geometry"


def test_from_lot(cadastre_lot_feature):
    def fake_where(service, layer_id, *, where, **kw):
        assert "lotnumber='5'" in where and "planlabel='DP12345'" in where
        return [cadastre_lot_feature]

    site = locate.from_lot("5/DP12345", query_fn=fake_where)
    assert site.area_m2 == 600.0
    assert site.lotidstring == "5//DP12345"
    assert site.parcel and "rings" in site.parcel
    assert 151.103 < site.lon < 151.105   # centroid inside parcel
    assert -33.815 < site.lat < -33.813


def test_from_lot_not_found():
    with pytest.raises(LookupError):
        locate.from_lot("9/DP99999", query_fn=lambda *a, **k: [])


def test_from_coords_no_parcel_warns():
    site = locate.from_coords(151.0, -33.0, query_fn=lambda *a, **k: [])
    assert site.area_m2 is None
    assert any("no cadastral parcel" in w for w in site.warnings)


def test_from_coords_enriches(cadastre_lot_feature):
    site = locate.from_coords(151.104, -33.8135,
                              query_fn=lambda *a, **k: [cadastre_lot_feature])
    assert site.area_m2 == 600.0
    assert site.lotidstring == "5//DP12345"
