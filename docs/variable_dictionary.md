# Variable Dictionary

## Identity and geography

| Variable | Definition |
| --- | --- |
| `clinic_key` | Stable clinic-location identifier, preferably based on Google place ID or CID |
| `NPI` | Provider identifier; not necessarily unique to one practice location |
| `mapped_location` | Prespecified study market |
| `zip` | Five-digit practice ZIP code |
| `latitude`, `longitude` | Practice-location coordinates |

## Rating outcomes

| Variable | Definition |
| --- | --- |
| `rating_value` | Cross-sectional displayed average rating |
| `new_count` | Number of observed reviews in a clinic-year |
| `new_stars` | Sum of observed review ratings in a clinic-year |
| `dynamic_rating` | Cumulative observed review rating through a clinic-year |
| `cumulative_low_review_share` | Cumulative share of reviews at or below the prespecified low-rating threshold |
| `log_votes_dynamic` | Log of one plus cumulative observed reviews; excluded from the main specification by default |

## Competition exposures

| Variable | Definition |
| --- | --- |
| `entry_shock_inner_count` | Number of neighboring clinics entering in the prior year within the inner radius |
| `entry_shock_outer_ring_count` | Number of neighboring clinics entering in the prior year between inner and outer radii |
| `density_inner_count` | Active neighboring clinics within the inner radius |
| `density_outer_ring_count` | Active neighboring clinics between inner and outer radii |
| `strong_entry_shock_inner_count` | Prior-year entrants classified using information available at entry time |

## Historical notebook names

The historical notebooks use names such as `lag_entry_shock_25pct_count`, `log_density_25pct_total`, and `strong_entry_shock_25pct_count`. These correspond to sample-dependent market distance quantiles. They should not be confused with fixed physical-distance measures.

## NLP outcomes

The latest notebooks include ratios such as `price_issue_ratio`, `compare_ratio`, `service_issue_ratio`, and `cosmetic_ratio`. These variables require a separate NLP metadata record containing model version, labels, prompt or classifier settings, sample selection, and cleaning rules.
