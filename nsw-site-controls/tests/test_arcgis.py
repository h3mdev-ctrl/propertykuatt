import pytest

from nsw_site_controls import arcgis
from tests.conftest import load_fixture


def test_query_parses_features_and_builds_url(monkeypatch):
    captured = {}

    def fake_get(url, timeout=30, accept="application/json"):
        captured["url"] = url
        return {"features": [{"attributes": {"FSR": 0.5}}]}

    monkeypatch.setattr(arcgis, "_http_get", fake_get)
    feats = arcgis.query("https://svc/MapServer", 1,
                         geometry=arcgis.point_geometry(151.1, -33.8))
    assert feats == [{"attributes": {"FSR": 0.5}}]
    assert "/1/query" in captured["url"]
    assert "f=json" in captured["url"]
    assert "geometryType=esriGeometryPoint" in captured["url"]


def test_query_on_disk_fixture_shape(monkeypatch):
    payload = load_fixture("ryde_r2_fsr.json")
    monkeypatch.setattr(arcgis, "_http_get", lambda *a, **k: payload)
    feats = arcgis.query("https://svc/MapServer", 1,
                         geometry=arcgis.point_geometry(151.1, -33.8))
    assert feats[0]["attributes"]["FSR"] == 0.5


def test_arcgis_reported_error_raises(monkeypatch):
    def fake_get(url, timeout=30, accept="application/json"):
        return {"error": {"code": 400, "message": "bad"}}

    monkeypatch.setattr(arcgis, "_http_get", fake_get)
    # _http_get itself raises on dict-with-error; simulate by raising here:
    monkeypatch.setattr(arcgis, "_http_get",
                        lambda *a, **k: (_ for _ in ()).throw(arcgis.ArcGISError("boom")))
    with pytest.raises(arcgis.ArcGISError):
        arcgis.query("https://svc/MapServer", 1,
                     geometry=arcgis.point_geometry(151.1, -33.8))


def test_http_get_retries_then_succeeds(monkeypatch):
    import json as _json

    class FakeResp:
        def __init__(self, body):
            self._b = body.encode()
        def read(self):
            return self._b
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    calls = {"n": 0}

    def flaky_urlopen(req, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read timed out")
        return FakeResp(_json.dumps({"features": [1]}))

    monkeypatch.setattr(arcgis.urllib.request, "urlopen", flaky_urlopen)
    data = arcgis._http_get("https://svc", retries=2, _sleep=lambda s: None)
    assert data == {"features": [1]} and calls["n"] == 2


def test_http_get_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(arcgis.urllib.request, "urlopen",
                        lambda req, timeout=30: (_ for _ in ()).throw(TimeoutError("nope")))
    with pytest.raises(arcgis.ArcGISError):
        arcgis._http_get("https://svc", retries=1, _sleep=lambda s: None)


def test_http_get_flags_error_payload(monkeypatch):
    import json as _json

    class FakeResp:
        def __init__(self, body):
            self._b = body.encode()
        def read(self):
            return self._b
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(arcgis.urllib.request, "urlopen",
                        lambda req, timeout=30: FakeResp(_json.dumps({"error": {"message": "x"}})))
    with pytest.raises(arcgis.ArcGISError):
        arcgis._http_get("https://svc")
