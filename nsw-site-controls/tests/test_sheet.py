from nsw_site_controls import dcp, lep, sheet
from nsw_site_controls.locate import Site
from tests.conftest import RYDE_PARCEL


def _env(fake_query):
    site = Site(lon=151.1039, lat=-33.8135, lotidstring="5//DP12345",
                area_m2=600.0, parcel=RYDE_PARCEL, source="lot/DP")
    return site, lep.envelope(site, query_fn=fake_query)


def test_render_text_core(fake_query):
    site, env = _env(fake_query)
    txt = sheet.render_text(site, env)
    assert "FSR" in txt
    assert "Max GFA" in txt and "300" in txt
    assert "Ryde Local Environmental Plan 2014" in txt
    assert sheet.DISCLAIMER in txt
    # R2 -> reform warning surfaces
    assert "Low & Mid-Rise Housing reforms" in txt


def test_render_text_with_dcp(fake_query):
    site, env = _env(fake_query)
    res = dcp.controls_for("dwelling-house")
    txt = sheet.render_text(site, env, res)
    assert "Dwelling house" in txt
    assert "clause 2.9.1" in txt
    assert "Front setback" in txt


def test_render_json(fake_query):
    site, env = _env(fake_query)
    res = dcp.controls_for("dwelling-house")
    out = sheet.render_json(site, env, res)
    assert out["envelope"]["fsr"]["values"][0]["value"] == 0.5
    assert out["derived"]["max_gfa_m2"] == [300]
    assert out["dcp"]["dev_type"] == "dwelling-house"
    assert any("reform" in w.lower() for w in out["site"]["warnings"])
    assert out["disclaimer"]


def test_non_residential_no_reform_warning():
    site = Site(lon=151.1, lat=-33.8, source="coords")
    layers = {2: [{"attributes": {"SYM_CODE": "E2", "LAY_CLASS": "Commercial Centre",
                                  "EPI_NAME": "Ryde LEP 2014"}}]}
    env = lep.envelope(site, query_fn=lambda s, lid, **k: layers.get(lid, []))
    txt = sheet.render_text(site, env)
    assert "Low & Mid-Rise" not in txt
