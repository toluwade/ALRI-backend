from __future__ import annotations

# Minimal but comprehensive-enough set of common biomarkers.
# Values are typical adult reference ranges; they can vary by lab.
# This is used to provide context to the LLM and for basic fallback classification.

REFERENCE_RANGES: dict[str, dict] = {
    # CBC
    "hemoglobin": {
        "unit": "g/dL",
        "ranges": {
            "adult_male": {"low": 13.5, "high": 17.5},
            "adult_female": {"low": 12.0, "high": 16.0},
            "default": {"low": 12.0, "high": 17.5},
        },
    },
    "hematocrit": {"unit": "%", "ranges": {"adult_male": {"low": 41.0, "high": 53.0}, "adult_female": {"low": 36.0, "high": 46.0}, "default": {"low": 36.0, "high": 53.0}}},
    "wbc": {"unit": "K/uL", "ranges": {"default": {"low": 4.5, "high": 11.0}}},
    "rbc": {"unit": "M/uL", "ranges": {"adult_male": {"low": 4.7, "high": 6.1}, "adult_female": {"low": 4.2, "high": 5.4}, "default": {"low": 4.2, "high": 6.1}}},
    "platelets": {"unit": "K/uL", "ranges": {"default": {"low": 150.0, "high": 450.0}}},
    "mcv": {"unit": "fL", "ranges": {"default": {"low": 80.0, "high": 100.0}}},
    "mch": {"unit": "pg", "ranges": {"default": {"low": 27.0, "high": 33.0}}},
    "mchc": {"unit": "g/dL", "ranges": {"default": {"low": 32.0, "high": 36.0}}},
    "rdw": {"unit": "%", "ranges": {"default": {"low": 11.5, "high": 14.5}}},

    # Metabolic
    "glucose": {"unit": "mg/dL", "ranges": {"default": {"low": 70.0, "high": 100.0}}},
    "glucose_fasting": {"unit": "mg/dL", "ranges": {"default": {"low": 70.0, "high": 100.0}, "borderline": {"low": 100.0, "high": 125.0}}},
    "bun": {"unit": "mg/dL", "ranges": {"default": {"low": 7.0, "high": 20.0}}},
    "creatinine": {"unit": "mg/dL", "ranges": {"default": {"low": 0.6, "high": 1.3}}},
    "sodium": {"unit": "mmol/L", "ranges": {"default": {"low": 135.0, "high": 145.0}}},
    "potassium": {"unit": "mmol/L", "ranges": {"default": {"low": 3.5, "high": 5.1}}},
    "chloride": {"unit": "mmol/L", "ranges": {"default": {"low": 98.0, "high": 107.0}}},
    "co2": {"unit": "mmol/L", "ranges": {"default": {"low": 22.0, "high": 29.0}}},
    "calcium": {"unit": "mg/dL", "ranges": {"default": {"low": 8.6, "high": 10.2}}},

    # Lipid
    "total_cholesterol": {"unit": "mg/dL", "ranges": {"default": {"low": 0.0, "high": 200.0}}},
    "ldl": {"unit": "mg/dL", "ranges": {"default": {"low": 0.0, "high": 100.0}}},
    "hdl": {"unit": "mg/dL", "ranges": {"adult_male": {"low": 40.0, "high": 1000.0}, "adult_female": {"low": 50.0, "high": 1000.0}, "default": {"low": 40.0, "high": 1000.0}}},
    "triglycerides": {"unit": "mg/dL", "ranges": {"default": {"low": 0.0, "high": 150.0}}},
    "vldl": {"unit": "mg/dL", "ranges": {"default": {"low": 0.0, "high": 30.0}}},

    # Liver
    "alt": {"unit": "U/L", "ranges": {"default": {"low": 0.0, "high": 40.0}}},
    "ast": {"unit": "U/L", "ranges": {"default": {"low": 0.0, "high": 40.0}}},
    "alp": {"unit": "U/L", "ranges": {"default": {"low": 44.0, "high": 147.0}}},
    "bilirubin_total": {"unit": "mg/dL", "ranges": {"default": {"low": 0.1, "high": 1.2}}},
    "bilirubin_direct": {"unit": "mg/dL", "ranges": {"default": {"low": 0.0, "high": 0.3}}},
    "albumin": {"unit": "g/dL", "ranges": {"default": {"low": 3.5, "high": 5.0}}},
    "total_protein": {"unit": "g/dL", "ranges": {"default": {"low": 6.0, "high": 8.3}}},

    # Thyroid
    "tsh": {"unit": "uIU/mL", "ranges": {"default": {"low": 0.4, "high": 4.0}}},
    "free_t4": {"unit": "ng/dL", "ranges": {"default": {"low": 0.8, "high": 1.8}}},
    "free_t3": {"unit": "pg/mL", "ranges": {"default": {"low": 2.3, "high": 4.2}}},

    # Iron
    "serum_iron": {"unit": "ug/dL", "ranges": {"default": {"low": 60.0, "high": 170.0}}},
    "ferritin": {"unit": "ng/mL", "ranges": {"adult_male": {"low": 24.0, "high": 336.0}, "adult_female": {"low": 11.0, "high": 307.0}, "default": {"low": 11.0, "high": 336.0}}},
    "tibc": {"unit": "ug/dL", "ranges": {"default": {"low": 250.0, "high": 450.0}}},
    "transferrin_saturation": {"unit": "%", "ranges": {"default": {"low": 20.0, "high": 50.0}}},

    # Vitamins
    "vitamin_d": {"unit": "ng/mL", "ranges": {"default": {"low": 30.0, "high": 100.0}}},
    "vitamin_b12": {"unit": "pg/mL", "ranges": {"default": {"low": 200.0, "high": 900.0}}},
    "folate": {"unit": "ng/mL", "ranges": {"default": {"low": 3.0, "high": 20.0}}},

    # Other
    "hba1c": {"unit": "%", "ranges": {"default": {"low": 4.0, "high": 5.6}, "borderline": {"low": 5.7, "high": 6.4}}},
    "uric_acid": {"unit": "mg/dL", "ranges": {"adult_male": {"low": 3.4, "high": 7.0}, "adult_female": {"low": 2.4, "high": 6.0}, "default": {"low": 2.4, "high": 7.0}}},
    "crp": {"unit": "mg/L", "ranges": {"default": {"low": 0.0, "high": 3.0}}},
    "esr": {"unit": "mm/hr", "ranges": {"default": {"low": 0.0, "high": 20.0}}},
    "psa": {"unit": "ng/mL", "ranges": {"default": {"low": 0.0, "high": 4.0}}},
}


# Common alternative names found on real lab reports → our canonical keys
_ALIASES: dict[str, str] = {
    # Liver
    "ast/got": "ast", "sgot": "ast", "got": "ast", "aspartate_aminotransferase": "ast",
    "alt/gpt": "alt", "sgpt": "alt", "gpt": "alt", "alanine_aminotransferase": "alt",
    "alkaline_phosphatase": "alp",
    "total_bilirubin": "bilirubin_total", "t._bilirubin": "bilirubin_total", "t_bil": "bilirubin_total", "tbil": "bilirubin_total",
    "direct_bilirubin": "bilirubin_direct", "d._bilirubin": "bilirubin_direct", "d_bil": "bilirubin_direct", "dbil": "bilirubin_direct", "conjugated_bilirubin": "bilirubin_direct",
    "indirect_bilirubin": "bilirubin_total",  # close-enough fallback
    # CBC
    "white_blood_cell": "wbc", "white_blood_cells": "wbc", "wbc_count": "wbc",
    "red_blood_cell": "rbc", "red_blood_cells": "rbc", "rbc_count": "rbc",
    "platelet_count": "platelets", "plt": "platelets",
    "haemoglobin": "hemoglobin", "hgb": "hemoglobin", "hb": "hemoglobin",
    "haematocrit": "hematocrit", "hct": "hematocrit", "packed_cell_volume": "hematocrit", "pcv": "hematocrit",
    "mean_corpuscular_volume": "mcv",
    "mean_corpuscular_hemoglobin": "mch",
    "red_cell_distribution_width": "rdw",
    # Metabolic
    "blood_urea_nitrogen": "bun", "urea": "bun",
    "fasting_glucose": "glucose_fasting", "fasting_blood_sugar": "glucose_fasting", "fbs": "glucose_fasting",
    "random_blood_sugar": "glucose", "rbs": "glucose", "blood_sugar": "glucose", "blood_glucose": "glucose",
    # Lipid
    "cholesterol": "total_cholesterol", "t._cholesterol": "total_cholesterol",
    "ldl_cholesterol": "ldl", "ldl_c": "ldl",
    "hdl_cholesterol": "hdl", "hdl_c": "hdl",
    # Thyroid
    "thyroid_stimulating_hormone": "tsh",
    "ft4": "free_t4", "free_thyroxine": "free_t4",
    "ft3": "free_t3", "free_triiodothyronine": "free_t3",
    # Other
    "hemoglobin_a1c": "hba1c", "glycated_hemoglobin": "hba1c", "a1c": "hba1c",
    "c_reactive_protein": "crp", "hs_crp": "crp",
    "erythrocyte_sedimentation_rate": "esr",
    "prostate_specific_antigen": "psa",
    "25_hydroxy_vitamin_d": "vitamin_d", "vit_d": "vitamin_d",
    "vit_b12": "vitamin_b12",
}


def canonicalize(name: str) -> str:
    key = name.strip().lower().replace(" ", "_").replace("-", "_").replace("/", "/")
    # Try alias lookup first (handles "ast/got" → "ast", "total_bilirubin" → "bilirubin_total", etc.)
    return _ALIASES.get(key, key)


# Age-specific adjustments for key markers (pediatric <18, elderly >=65)
_PEDIATRIC_OVERRIDES: dict[str, dict] = {
    "hemoglobin": {"low": 11.5, "high": 15.5},
    "wbc": {"low": 5.0, "high": 13.0},
    "platelets": {"low": 150.0, "high": 450.0},
    "glucose": {"low": 60.0, "high": 100.0},
    "creatinine": {"low": 0.3, "high": 0.7},
    "alp": {"low": 100.0, "high": 390.0},
}

_ELDERLY_OVERRIDES: dict[str, dict] = {
    "glucose": {"low": 70.0, "high": 110.0},
    "creatinine": {"low": 0.6, "high": 1.5},
    "tsh": {"low": 0.4, "high": 5.0},
    "esr": {"low": 0.0, "high": 30.0},
    "psa": {"low": 0.0, "high": 6.5},
}


def get_reference_range(name: str, profile: dict | None = None) -> tuple[float | None, float | None, str | None]:
    key = canonicalize(name)
    item = REFERENCE_RANGES.get(key)
    if not item:
        return None, None, None

    age = (profile or {}).get("age")
    sex = (profile or {}).get("sex")

    # Check age-specific overrides first
    if isinstance(age, (int, float)):
        if age < 18 and key in _PEDIATRIC_OVERRIDES:
            r = _PEDIATRIC_OVERRIDES[key]
            return r["low"], r["high"], item.get("unit")
        if age >= 65 and key in _ELDERLY_OVERRIDES:
            r = _ELDERLY_OVERRIDES[key]
            return r["low"], r["high"], item.get("unit")

    # Standard adult sex-aware lookup
    group = "default"
    if sex == "male":
        group = "adult_male" if "adult_male" in item["ranges"] else "default"
    elif sex == "female":
        group = "adult_female" if "adult_female" in item["ranges"] else "default"

    r = item["ranges"].get(group) or item["ranges"].get("default")
    return r.get("low"), r.get("high"), item.get("unit")
