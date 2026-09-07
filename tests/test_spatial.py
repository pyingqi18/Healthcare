import pandas as pd

from medical_ratings.spatial import (
    MarketRadii,
    add_entry_exposures,
    add_spatial_eligibility,
)


def test_entry_exposure_is_restricted_to_market() -> None:
    clinics = pd.DataFrame(
        {
            "clinic_key": ["a", "b", "c"],
            "mapped_location": ["m1", "m1", "m2"],
            "entry_year": [2020, 2021, 2021],
            "latitude": [0.0, 0.0, 0.0],
            "longitude": [0.0, 0.01, 0.005],
        }
    )
    panel = pd.DataFrame(
        {
            "clinic_key": ["a", "a"],
            "year": [2021, 2022],
        }
    )
    radii = {"m1": MarketRadii(2.0, 5.0), "m2": MarketRadii(2.0, 5.0)}
    result = add_entry_exposures(panel, clinics, radii)
    assert result.loc[result["year"] == 2022, "entry_shock_inner_count"].iloc[0] == 1
    assert result.loc[result["year"] == 2021, "entry_shock_inner_count"].iloc[0] == 0

def test_add_spatial_eligibility() -> None:
    clinics = pd.DataFrame(
        {
            "search_location": [
                "Syracuse_NY_M",
                "Syracuse_NY_M",
                "LA_CA_L",
                "Syracuse_NY_M",
            ],
            "latitude": [
                43.0481,
                None,
                46.423669,
                41.08,
            ],
            "longitude": [
                -76.1474,
                None,
                -129.9427086,
                -112.06,
            ],
            "analysis_exclusion_reason": [
                "eligible",
                "eligible",
                "eligible",
                "location_code_mismatch",
            ],
            "preliminary_analysis_eligible": [
                True,
                True,
                True,
                False,
            ],
        }
    )

    regions = {
        "Syracuse_NY_M": {
            "hub": [43.0481, -76.1474],
        },
        "LA_CA_L": {
            "hub": [34.0522, -118.2437],
        },
    }

    result = add_spatial_eligibility(
        clinics,
        regions,
        max_hub_distance_miles=100,
    )

    assert result[
        "spatial_exclusion_reason"
    ].tolist() == [
        "eligible",
        "invalid_or_missing_coordinates",
        "outside_market_distance",
        "location_code_mismatch",
    ]

    assert result[
        "spatial_analysis_eligible"
    ].tolist() == [
        True,
        False,
        False,
        False,
    ]