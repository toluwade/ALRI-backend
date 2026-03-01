from app.services.scan_pipeline import parse_markers_from_text, _safe_float, _enrich_with_reference


def test_parse_markers_from_standard_line():
    text = "Glucose 92 mg/dL\nHemoglobin 14.5 g/dL"
    markers = parse_markers_from_text(text)
    assert len(markers) == 2
    assert markers[0]["name"] == "Glucose"
    assert markers[0]["value"] == 92.0
    assert markers[0]["unit"] == "mg/dL"
    assert markers[1]["name"] == "Hemoglobin"
    assert markers[1]["value"] == 14.5


def test_parse_markers_skips_short_lines():
    text = "AB\nGlucose 92 mg/dL"
    markers = parse_markers_from_text(text)
    assert len(markers) == 1


def test_parse_markers_empty_input():
    assert parse_markers_from_text("") == []
    assert parse_markers_from_text(None) == []


def test_parse_markers_deduplicates():
    text = "Glucose 92 mg/dL\nGlucose 95 mg/dL"
    markers = parse_markers_from_text(text)
    assert len(markers) == 1
    assert markers[0]["value"] == 92.0  # keeps first


def test_parse_markers_no_unit():
    text = "WBC 5500"
    markers = parse_markers_from_text(text)
    assert len(markers) == 1
    assert markers[0]["unit"] is None


def test_parse_markers_decimal_value():
    text = "HbA1c 5.7 %"
    markers = parse_markers_from_text(text)
    assert len(markers) == 1
    assert markers[0]["value"] == 5.7


def test_safe_float_valid():
    assert _safe_float("92") == 92.0
    assert _safe_float("14.5") == 14.5
    assert _safe_float("1,200") == 1200.0


def test_safe_float_invalid():
    assert _safe_float("abc") is None
    assert _safe_float(None) is None
    assert _safe_float("") is None


def test_enrich_with_reference_known_marker():
    markers = [{"name": "Glucose", "value": 92, "unit": "mg/dL"}]
    enriched = _enrich_with_reference(markers, None)
    assert len(enriched) == 1
    assert enriched[0]["reference_low"] == 70.0
    assert enriched[0]["reference_high"] == 100.0


def test_enrich_with_reference_unknown_marker():
    markers = [{"name": "UnknownMarker", "value": 50, "unit": "units"}]
    enriched = _enrich_with_reference(markers, None)
    assert enriched[0]["reference_low"] is None
    assert enriched[0]["reference_high"] is None


def test_enrich_with_reference_sex_aware():
    markers = [{"name": "Hemoglobin", "value": 14, "unit": "g/dL"}]
    male = _enrich_with_reference(markers, {"sex": "male"})
    female = _enrich_with_reference(markers, {"sex": "female"})
    assert male[0]["reference_low"] == 13.5
    assert female[0]["reference_low"] == 12.0
