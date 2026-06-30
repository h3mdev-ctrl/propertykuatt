"""Opt-in integration tests against the real NSW/SIX services.

These catch upstream schema drift (endpoint moves, field renames). They are
skipped unless ``NSC_LIVE=1`` so the normal suite stays offline & deterministic.

    NSC_LIVE=1 pytest tests/test_live.py
"""
import os

import pytest

from nsw_site_controls import lep, locate

pytestmark = pytest.mark.skipif(os.environ.get("NSC_LIVE") != "1",
                                reason="set NSC_LIVE=1 to run live integration tests")


# A real, public Ryde lot near Ryde Town Centre. The lot/DP path is the reliable
# one (the cadastre is flaky on point queries). This lot sits at a zone junction
# (MU1/R2/R4) so it also exercises multi-zone handling. If it drifts, update it.
GOLDEN_LOT = "3/DP24994"


@pytest.mark.live
def test_live_lot_returns_parcel_with_area():
    site = locate.from_lot(GOLDEN_LOT)
    assert site.parcel is not None, "cadastre returned no parcel — endpoint/fields may have drifted"
    assert site.area_m2 and site.area_m2 > 0, "area not computed (planlotarea NULL + geometry fallback failed?)"


@pytest.mark.live
def test_live_envelope_resolves_controls():
    site = locate.from_lot(GOLDEN_LOT)
    env = lep.envelope(site)
    assert env.results["zoning"].present, "zoning layer empty — check layer id 2 / SYM_CODE"
    assert env.results["fsr"].present, "FSR empty — check layer id 1 / FSR field"
    assert env.results["height"].present, "height empty — check layer id 5 / MAX_B_H field"
    assert env.max_gfa_m2, "GFA not derived despite FSR + area present"
