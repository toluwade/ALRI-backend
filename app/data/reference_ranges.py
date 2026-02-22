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


def canonicalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def get_reference_range(name: str, profile: dict | None = None) -> tuple[float | None, float | None, str | None]:
    key = canonicalize(name)
    item = REFERENCE_RANGES.get(key)
    if not item:
        return None, None, None

    sex = (profile or {}).get("sex")
    group = "default"
    if sex == "male":
        group = "adult_male" if "adult_male" in item["ranges"] else "default"
    elif sex == "female":
        group = "adult_female" if "adult_female" in item["ranges"] else "default"

    r = item["ranges"].get(group) or item["ranges"].get("default")
    return r.get("low"), r.get("high"), item.get("unit")
