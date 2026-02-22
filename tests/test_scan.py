def test_full_scan_response_shape_is_stable():
    # This is a contract test for the response model shape. The actual endpoint
    # integration is exercised in higher-level tests.
    from app.routers.scan_full import FullScanResponse

    r = FullScanResponse(
        markers=[{"name": "Glucose", "value": 90, "unit": "mg/dL"}],
        summary="OK",
        correlations=[{"markers": ["A", "B"], "finding": "example"}],
        report_url="/api/v1/scan/123/report",
        disclaimer="x",
    )

    d = r.model_dump()
    assert "markers" in d
    assert "summary" in d
    assert "correlations" in d
    assert "report_url" in d
    assert "disclaimer" in d
