import pytest

from nsw_site_controls import dcp


def test_load_real_yaml():
    data = dcp.load("ryde")
    assert data["council"] == "City of Ryde"
    assert "dwelling-house" in data["dev_types"]


@pytest.mark.parametrize("alias", ["dwelling-house", "dwelling house", "house", "DWELLING_HOUSE"])
def test_alias_normalisation(alias):
    assert dcp.normalise_dev_type(alias) == "dwelling-house"


@pytest.mark.parametrize("alias", ["dual", "duplex", "dual occupancy", "Dual-Occupancy"])
def test_alias_dual(alias):
    assert dcp.normalise_dev_type(alias) == "dual-occupancy"


def test_controls_for_dwelling_has_real_clauses():
    res = dcp.controls_for("dwelling-house")
    by_control = {c.control: c for c in res.controls}
    assert "6 m" in by_control["Front setback"].value
    assert by_control["Front setback"].clause.startswith("2.9.1")
    assert "9.5 m" in by_control["Max building height"].value
    assert by_control["Max building height"].clause == "2.8.1"
    assert "35%" in by_control["Deep soil"].value


def test_controls_for_dual_occupancy():
    res = dcp.controls_for("duplex")
    assert res.dev_type == "dual-occupancy"
    vals = " ".join(c.value for c in res.controls)
    assert "580" in vals and "1 space per dwelling" in vals


def test_unknown_dev_type_lists_available():
    with pytest.raises(dcp.DcpNotFound) as ei:
        dcp.controls_for("skyscraper")
    assert "dwelling-house" in str(ei.value)


def test_unknown_council():
    with pytest.raises(dcp.DcpNotFound):
        dcp.load("atlantis")
