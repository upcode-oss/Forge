import pytest


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", ""),
        ("POST", ""),
        ("DELETE", ""),
        ("GET", "/identity"),
        ("POST", "/pair"),
        ("POST", "/test"),
        ("GET", "/peer"),
        ("DELETE", "/peer"),
    ],
)
def test_deferred_pairing_endpoints_are_unavailable(admin, method, suffix):
    assert admin.request(method, f"/api/v1/integrations/instance{suffix}").status_code == 404
    paths = admin.get("/openapi.json").json()["paths"]
    assert not any("/integrations/" in path for path in paths)
