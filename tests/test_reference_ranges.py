from app.data.reference_ranges import canonicalize, get_reference_range


def test_canonicalize_basic():
    assert canonicalize("Hemoglobin") == "hemoglobin"
    assert canonicalize("Total Cholesterol") == "total_cholesterol"
    assert canonicalize("Free T4") == "free_t4"
    assert canonicalize("  HbA1c  ") == "hba1c"


def test_canonicalize_hyphen():
    assert canonicalize("Bilirubin-Total") == "bilirubin_total"


def test_get_reference_range_known():
    low, high, unit = get_reference_range("Glucose")
    assert low == 70.0
    assert high == 100.0
    assert unit == "mg/dL"


def test_get_reference_range_unknown():
    low, high, unit = get_reference_range("SomeFakeMarker")
    assert low is None
    assert high is None
    assert unit is None


def test_get_reference_range_male():
    low, high, unit = get_reference_range("Hemoglobin", {"sex": "male"})
    assert low == 13.5
    assert high == 17.5


def test_get_reference_range_female():
    low, high, unit = get_reference_range("Hemoglobin", {"sex": "female"})
    assert low == 12.0
    assert high == 16.0


def test_get_reference_range_default_sex():
    low, high, unit = get_reference_range("Hemoglobin")
    assert low == 12.0
    assert high == 17.5


def test_get_reference_range_no_sex_variant():
    low, high, unit = get_reference_range("WBC", {"sex": "male"})
    assert low == 4.5
    assert high == 11.0


def test_get_reference_range_pediatric():
    low, high, unit = get_reference_range("Hemoglobin", {"age": 10, "sex": "male"})
    assert low is not None
    assert high is not None


def test_get_reference_range_elderly():
    low, high, unit = get_reference_range("Glucose", {"age": 70})
    assert low is not None
    assert high is not None
