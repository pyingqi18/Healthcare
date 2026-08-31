from medical_ratings.identifiers import build_clinic_key, normalize_name, normalize_zip


def test_normalize_zip() -> None:
    assert normalize_zip("24060-1234") == "24060"
    assert normalize_zip(10001.0) == "10001"
    assert normalize_zip(None) is None


def test_normalize_name() -> None:
    assert normalize_name("Dr. Smith's Dental, LLC") == "dr smith s dental llc"


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
