import pandas as pd
import pytest

from medical_ratings.coordinate_cluster_audit import audit_coordinate_clusters


def test_coordinate_clusters_stay_within_market_and_do_not_merge() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c", "d"],
            "search_location": ["m1", "m1", "m1", "m2"],
            "latitude": [1.0, 1.0, 1.0002, 1.0],
            "longitude": [1.0, 1.0, 1.0, 1.0],
            "spatial_analysis_eligible": [True, True, True, True],
            "title": ["Clinic A", "Dr A", "Clinic C", "Clinic D"],
            "address": ["1 Main St", "1 Main St", "2 Main St", "1 Main St"],
            "zip": ["12345", "12345", "12345", "12345"],
        }
    )

    exact, pairs, markets, metadata = audit_coordinate_clusters(
        clinics,
        distance_threshold_meters=50.0,
    )

    assert set(exact["clinic_key"]) == {"a", "b"}
    assert exact["coordinate_cluster_id"].nunique() == 1
    assert len(pairs) == 3
    assert set(pairs["market"]) == {"m1"}
    assert metadata["automatic_merges_performed"] == 0
    assert metadata["exact_coordinate_cluster_count"] == 1
    assert markets["clinic_count"].sum() == 4


def test_ineligible_and_invalid_coordinate_rows_are_excluded() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c"],
            "search_location": ["m1", "m1", "m1"],
            "latitude": [1.0, None, 1.0],
            "longitude": [1.0, 1.0, 1.001],
            "spatial_analysis_eligible": [True, True, False],
        }
    )

    exact, pairs, _, metadata = audit_coordinate_clusters(clinics)

    assert exact.empty
    assert pairs.empty
    assert metadata["included_clinic_rows"] == 1


def test_duplicate_clinic_keys_are_rejected() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "a"],
            "search_location": ["m1", "m1"],
            "latitude": [1.0, 1.01],
            "longitude": [1.0, 1.01],
            "spatial_analysis_eligible": [True, True],
        }
    )

    with pytest.raises(ValueError, match="Clinic keys must be unique"):
        audit_coordinate_clusters(clinics)
