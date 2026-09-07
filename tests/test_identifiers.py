from medical_ratings.identifiers import build_clinic_key, normalize_name, normalize_zip
import pytest
import pandas as pd

@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("24060-1234", "24060"),
        (10001.0, "10001"),
        (7087.0, "07087"),
        ("07087.0", "07087"),
        ("07087", "07087"),
        (None, None),
        ("", None),
        ("L2A 2S7", None),
    ],
)
def test_normalize_zip(
    raw_value: object,
    expected: str | None,
) -> None:
    assert normalize_zip(raw_value) == expected


def test_normalize_name() -> None:
    assert normalize_name("Dr. Smith's Dental, LLC") == "dr smith s dental llc"

def test_normalize_name_missing_values() -> None:
    assert normalize_name(None) is None
    assert normalize_name(float("nan")) is None
    assert normalize_name(pd.NA) is None
    assert normalize_name("") is None


def test_stable_google_key_preferred() -> None:
    record = {"place_id": "abc", "title": "Clinic", "zip": "24060"}
    assert build_clinic_key(record) == "google:place_id:abc"


def test_fallback_key_is_deterministic() -> None:
    record = {
        "title": "Clinic",
        "zip": "24060",
        "latitude": 37.123456,
        "longitude": -80.123456,
    }
    assert build_clinic_key(record) == build_clinic_key(record)
