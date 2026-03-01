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


def test_select_preview_empty_input():
    chosen = select_preview_markers([], max_items=4)
    assert chosen == []


def test_select_preview_respects_max_items():
    markers = [{"name": f"Marker{i}", "status": "high"} for i in range(10)]
    chosen = select_preview_markers(markers, max_items=4)
    assert len(chosen) <= 4


def test_select_preview_critical_first():
    markers = [
        {"name": "A", "status": "high"},
        {"name": "B", "status": "critical"},
        {"name": "C", "status": "normal"},
        {"name": "D", "status": "low"},
    ]
    chosen = select_preview_markers(markers, max_items=2)
    names = [m["name"] for m in chosen]
    assert "B" in names


def test_select_preview_mixed_borderline():
    markers = [
        {"name": "A", "status": "borderline_high"},
        {"name": "B", "status": "normal"},
        {"name": "C", "status": "borderline_low"},
    ]
    chosen = select_preview_markers(markers, max_items=4)
    names = {m["name"] for m in chosen}
    assert "A" in names
    assert "C" in names


def test_select_preview_single_marker():
    markers = [{"name": "Glucose", "status": "normal"}]
    chosen = select_preview_markers(markers, max_items=4)
    assert len(chosen) == 1
