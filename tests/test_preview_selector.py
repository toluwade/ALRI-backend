from app.services.preview_selector import select_preview_markers


def test_select_preview_prioritizes_abnormal():
    markers = [
        {"name": "Glucose", "status": "normal"},
        {"name": "Hemoglobin", "status": "low"},
        {"name": "LDL", "status": "high"},
        {"name": "WBC", "status": "normal"},
    ]
    chosen = select_preview_markers(markers, max_items=4)
    assert any(m["name"] == "Hemoglobin" for m in chosen)
    assert any(m["name"] == "LDL" for m in chosen)


def test_select_preview_common_when_all_normal():
    markers = [
        {"name": "RandomThing", "status": "normal"},
        {"name": "Glucose", "status": "normal"},
        {"name": "Total Cholesterol", "status": "normal"},
    ]
    chosen = select_preview_markers(markers, max_items=4)
    names = {m["name"] for m in chosen}
    assert "Glucose" in names
