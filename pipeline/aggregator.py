"""Suburb-level capital-flow aggregation.

Input  : long-format DataFrame of normalised application records, one row
         per project, with sa2_code attached.
Output : wide-format DataFrame, one row per (sa2_code, period), with $
         volume per signal layer plus a composite z-scored flow_score.

The composite score is intentionally simple at the MVP stage — equally
weighted z-scores across the available signal layers. We can revisit
weighting once the layers below DA/A&A come online (PEXA, Cordell, etc.).
"""
from __future__ import annotations

import pandas as pd

PERIOD = "Q"  # quarterly buckets — long enough to absorb monthly DA noise


def _to_period(series: pd.Series) -> pd.PeriodIndex:
    return pd.to_datetime(series).dt.to_period(PERIOD)


def aggregate_flows(
    apps: pd.DataFrame,
    population: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Roll application-level rows up to (sa2, quarter, category) totals.

    Parameters
    ----------
    apps
        Normalised DataFrame from a source module, post-geocode.
    population
        Optional DataFrame with columns ``sa2_code`` and ``population``
        (ABS ERP). When supplied we add a ``$_per_capita`` column.
    """
    if apps.empty:
        return pd.DataFrame()

    df = apps.copy()
    df["period"] = _to_period(df["lodged_date"])

    grouped = (
        df.groupby(["sa2_code", "sa2_name", "period", "category"], as_index=False)
        .agg(
            project_count=("application_id", "nunique"),
            committed_aud=("cost_of_works", "sum"),
        )
    )

    wide = grouped.pivot_table(
        index=["sa2_code", "sa2_name", "period"],
        columns="category",
        values="committed_aud",
        fill_value=0.0,
    ).add_prefix("aud_")

    counts = grouped.pivot_table(
        index=["sa2_code", "sa2_name", "period"],
        columns="category",
        values="project_count",
        fill_value=0,
    ).add_prefix("count_")

    out = wide.join(counts).reset_index()
    out["aud_total"] = out.filter(like="aud_").sum(axis=1)

    if population is not None and not population.empty:
        out = out.merge(population, on="sa2_code", how="left")
        out["aud_total_per_capita"] = out["aud_total"] / out["population"]

    out["flow_score"] = _composite_score(out)
    return out.sort_values(["period", "flow_score"], ascending=[True, False])


def _composite_score(df: pd.DataFrame) -> pd.Series:
    """Equal-weighted z-score across the dollar-volume columns.

    Per-period z-scores so a hot quarter doesn't drag historical periods
    along with it.
    """
    cols = [c for c in df.columns if c.startswith("aud_") and c != "aud_total"]
    if not cols:
        return pd.Series(0.0, index=df.index)

    def _z(g: pd.DataFrame) -> pd.DataFrame:
        std = g[cols].std(ddof=0).replace(0, 1.0)
        return (g[cols] - g[cols].mean()) / std

    z = df.groupby("period", group_keys=False).apply(_z)
    return z.mean(axis=1)
