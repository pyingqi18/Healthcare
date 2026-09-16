import numpy as np
import pandas as pd
import pytest

from medical_ratings.distance_ring_variants import (
    fit_half_mile_entity_market_year_fe,
    fit_half_mile_entity_year_fe,
    fit_joint_distance_rings_entity_market_year_fe,
    fit_joint_distance_rings_entity_year_fe,
)


def _regression_panel() -> pd.DataFrame:
    rng = np.random.default_rng(20260915)
    rows = []
    for clinic_number in range(18):
        clinic_effect = rng.normal(scale=0.08)
        for year_offset in range(6):
            exposures = rng.uniform(0.0, 1.2, size=6)
            votes = rng.uniform(0.0, 2.0)
            rating = (
                4.0
                + clinic_effect
                + 0.02 * year_offset
                + 0.04 * exposures[0]
                + 0.02 * exposures[1]
                + 0.01 * exposures[2]
                - 0.03 * exposures[3]
                - 0.01 * exposures[4]
                - 0.02 * exposures[5]
                + 0.03 * votes
                + rng.normal(scale=0.01)
            )
            rows.append(
                {
                    "clinic_key": f"clinic_{clinic_number}",
                    "search_location": f"market_{clinic_number % 3}",
                    "year": 2019 + year_offset,
                    "dynamic_rating": rating,
                    "log_shock_0_05": exposures[0],
                    "log_shock_05_2": exposures[1],
                    "log_shock_2_5": exposures[2],
                    "log_density_0_05": exposures[3],
                    "log_density_05_2": exposures[4],
                    "log_density_2_5": exposures[5],
                    "log_votes_dynamic": votes,
                    "analysis_period": True,
                    "spatial_analysis_eligible": True,
                }
            )
    return pd.DataFrame(rows)


def test_joint_ring_variant_adds_year_effects() -> None:
    result, metadata = fit_joint_distance_rings_entity_year_fe(
        _regression_panel()
    )

    assert metadata["sample_rows"] == 108
    assert metadata["sample_clinics"] == 18
    assert metadata["entity_effects"] is True
    assert metadata["time_effects"] is True
    assert "TimeEffects" in metadata["formula"]
    assert "log_shock_2_5" in result.params.index
    assert "log_density_2_5" in result.params.index


def test_half_mile_variant_adds_year_effects() -> None:
    result, metadata = fit_half_mile_entity_year_fe(_regression_panel())

    assert metadata["sample_rows"] == 108
    assert metadata["sample_clinics"] == 18
    assert metadata["time_effects"] is True
    assert set(result.params.index) == {
        "log_shock_0_05",
        "log_density_0_05",
        "log_votes_dynamic",
    }


def test_ring_variant_rejects_duplicate_clinic_year_rows() -> None:
    panel = _regression_panel()
    panel = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate clinic-year"):
        fit_joint_distance_rings_entity_year_fe(panel)


def test_joint_ring_variant_uses_market_year_effects() -> None:
    result, metadata = fit_joint_distance_rings_entity_market_year_fe(
        _regression_panel()
    )

    assert metadata["sample_rows"] == 108
    assert metadata["sample_clinics"] == 18
    assert metadata["market_count"] == 3
    assert metadata["market_year_effect_count"] == 18
    assert metadata["market_year_effects"] is True
    assert "log_shock_2_5" in result.params.index


def test_half_mile_variant_uses_market_year_effects() -> None:
    result, metadata = fit_half_mile_entity_market_year_fe(
        _regression_panel()
    )

    assert metadata["sample_rows"] == 108
    assert metadata["market_count"] == 3
    assert metadata["market_year_effect_count"] == 18
    assert metadata["market_year_effects"] is True
    assert "log_shock_0_05" in result.params.index
