import pandas as pd

from medical_ratings.spatial import MarketRadii, add_entry_exposures


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
