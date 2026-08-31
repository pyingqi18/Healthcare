"""Fixed-effects model wrappers with an explicit specification registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PanelSpecification:
    name: str
    outcome: str
    exposures: tuple[str, ...]
    controls: tuple[str, ...] = ()
    entity: str = "clinic_key"
    time: str = "year"
    market: str = "mapped_location"
    cluster_entity: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable specification record."""

        return asdict(self)


def fit_market_year_fe(
    data: pd.DataFrame,
    specification: PanelSpecification,
) -> Any:
    """Fit clinic effects plus market-by-year effects using PanelOLS."""

    try:
        import statsmodels.api as sm
        from linearmodels.panel import PanelOLS
    except ImportError as exc:
        raise ImportError("Install the analysis dependency group") from exc

    spec = specification
    required = [
        spec.outcome,
        *spec.exposures,
        *spec.controls,
        spec.entity,
        spec.time,
        spec.market,
    ]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise KeyError(f"Missing model columns: {missing}")

    model_data = data.dropna(subset=required).copy()
    model_data["market_year"] = (
        model_data[spec.market].astype(str) + "_" + model_data[spec.time].astype(str)
    )
    model_data = model_data.set_index([spec.entity, spec.time]).sort_index()

    regressors = [*spec.exposures, *spec.controls]
    exogenous = sm.add_constant(model_data[regressors], has_constant="add")
    market_year = pd.DataFrame(
        model_data["market_year"].astype("category").cat.codes,
        index=model_data.index,
        columns=["market_year"],
    )
    model = PanelOLS(
        model_data[spec.outcome],
        exogenous,
        entity_effects=True,
        other_effects=market_year,
        drop_absorbed=True,
    )
    return model.fit(cov_type="clustered", cluster_entity=spec.cluster_entity)
