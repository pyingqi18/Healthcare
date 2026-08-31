import pandas as pd

from medical_ratings.validation import add_rating_reconciliation


def test_rating_reconciliation_preserves_mismatch() -> None:
    data = pd.DataFrame(
        {
            "votes_count": [10, 5],
            "rating_1_star": [1, 0],
            "rating_2_star": [1, 0],
            "rating_3_star": [2, 0],
            "rating_4_star": [2, 0],
            "rating_5_star": [4, 0],
        }
    )
    result = add_rating_reconciliation(data)
    assert result.loc[0, "rating_count_status"] == "reconciled"
    assert result.loc[1, "rating_count_status"] == "distribution_unavailable"
    assert len(result) == 2
