def test_preview_selector_prefers_abnormal_when_present():
    # Contract-level test: preview selector should prioritize abnormal markers.
    ps = __import__("pytest").importorskip("app.services.preview_selector")
    select_preview_markers = ps.select_preview_markers

    markers = [
        {"name": "Glucose", "status": "normal"},
        {"name": "Hemoglobin", "status": "low"},
        {"name": "LDL", "status": "high"},
        {"name": "WBC", "status": "normal"},
        {"name": "TSH", "status": "borderline_high"},
        {"name": "Vitamin D", "status": "normal"},
    ]

    chosen = select_preview_markers(markers)
    assert 3 <= len(chosen) <= 4
    chosen_names = {m.get("name") for m in chosen}

    # At least two abnormal markers should be included
    assert {"Hemoglobin", "LDL"}.issubset(chosen_names)


def test_preview_selector_size_and_subset():
    ps = __import__("pytest").importorskip("app.services.preview_selector")
    select_preview_markers = ps.select_preview_markers

    markers = [{"name": f"M{i}", "status": "normal"} for i in range(20)]
    chosen = select_preview_markers(markers)
    assert 3 <= len(chosen) <= 4
    assert all(m in markers for m in chosen)
