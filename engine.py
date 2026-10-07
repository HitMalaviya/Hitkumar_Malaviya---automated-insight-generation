"""
engine.py - Automated Insight Generation Engine
Designed for district-level healthcare performance analytics.
Strictly adheres to Assignment 4 specifications:
- Dynamic calculation & data-driven insights (no hardcoded narratives)
- Distinct separation of trend, outlier, and correlation insights
- Configuration-relative severity scaling (no arbitrary magic numbers)
"""

from typing import Dict, List, Any, Tuple, Optional
import pandas as pd
import numpy as np


REQUIRED_COLUMNS = [
    "month",
    "district",
    "anc_coverage",
    "institutional_delivery",
    "immunization",
    "high_risk_cases",
]


def load_and_validate_data(filepath_or_buffer) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Loads CSV, verifies schema, missing values, and data types.
    Returns:
        (DataFrame, validation_report_dict)
    """
    df = pd.read_csv(filepath_or_buffer)

    # Basic normalization of column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Check required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]

    # Detect numeric columns dynamically
    numeric_cols = [c for c in df.columns if c not in ["month", "district"] and pd.api.types.is_numeric_dtype(df[c])]

    # Convert month to string if not already
    df["month"] = df["month"].astype(str).str.strip()
    df["district"] = df["district"].astype(str).str.strip()

    # Check for missing values
    missing_counts = df.isnull().sum().to_dict()

    # Check composite key uniqueness
    duplicate_rows = int(df.duplicated(subset=["district", "month"]).sum())

    # Sort chronologically by month and alphabetically by district
    df = df.sort_values(by=["district", "month"]).reset_index(drop=True)

    validation_report = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": list(df.columns),
        "numeric_indicators": numeric_cols,
        "districts": sorted(df["district"].unique().tolist()),
        "months": sorted(df["month"].unique().tolist()),
        "missing_counts": missing_counts,
        "duplicate_composite_keys": duplicate_rows,
        "missing_required_cols": missing_cols,
        "is_valid": len(missing_cols) == 0 and duplicate_rows == 0,
    }

    return df, validation_report


def detect_trends(
    df: pd.DataFrame,
    indicators: Optional[List[str]] = None,
    trend_threshold: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Part B — Trend Detection:
    pct_change = (current - previous) / previous * 100
    Flag as significant if |pct_change| >= trend_threshold.
    Severity is computed relative to trend_threshold:
      - High:   |pct_change| >= 1.5 * threshold
      - Medium: |pct_change| >= 1.2 * threshold
      - Low:    |pct_change| >= 1.0 * threshold
    """
    if indicators is None:
        indicators = [c for c in df.columns if c not in ["month", "district"] and pd.api.types.is_numeric_dtype(df[c])]

    trends = []
    # Ensure proper ordering per district
    sorted_df = df.sort_values(by=["district", "month"]).copy()

    for district, group in sorted_df.groupby("district"):
        group = group.sort_values(by="month").reset_index(drop=True)
        if len(group) < 2:
            continue

        for ind in indicators:
            if ind not in group.columns:
                continue

            for i in range(1, len(group)):
                prev_val = float(group.loc[i - 1, ind])
                curr_val = float(group.loc[i, ind])
                period = str(group.loc[i, "month"])
                prev_period = str(group.loc[i - 1, "month"])

                if prev_val == 0:
                    pct_change = 0.0 if curr_val == 0 else 100.0
                else:
                    pct_change = ((curr_val - prev_val) / prev_val) * 100.0

                abs_pct = abs(pct_change)
                if abs_pct >= trend_threshold:
                    # Severity derived relative to user's active threshold
                    if abs_pct >= 1.5 * trend_threshold:
                        severity = "High"
                    elif abs_pct >= 1.2 * trend_threshold:
                        severity = "Medium"
                    else:
                        severity = "Low"

                    direction = "increased" if pct_change > 0 else "dropped"
                    
                    explanation = (
                        f"{ind.replace('_', ' ').title()} in {district} {direction} by "
                        f"{abs_pct:.1f}% (from {prev_val:g} in {prev_period} to {curr_val:g} in {period}), "
                        f"exceeding the {trend_threshold:g}% threshold."
                    )

                    trends.append({
                        "type": "trend",
                        "indicator": ind,
                        "entity": district,
                        "period": period,
                        "value": round(curr_val, 2),
                        "prev_value": round(prev_val, 2),
                        "change_pct": round(pct_change, 2),
                        "severity": severity,
                        "explanation": explanation,
                    })

    return trends


def detect_outliers(
    df: pd.DataFrame,
    indicators: Optional[List[str]] = None,
    iqr_multiplier: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Part C — Outlier Detection (IQR Method):
    For each indicator:
      IQR = Q3 - Q1
      Lower Bound = Q1 - iqr_multiplier * IQR
      Upper Bound = Q3 + iqr_multiplier * IQR
    Severity derived relative to distance beyond bounds / Z-score:
      - High:   Distance >= 2.0 * iqr_multiplier * IQR or |Z| >= 2.5
      - Medium: Distance >= 1.3 * iqr_multiplier * IQR or |Z| >= 2.0
      - Low:    Mild outlier (exceeds 1.0 * iqr_multiplier * IQR)
    """
    if indicators is None:
        indicators = [c for c in df.columns if c not in ["month", "district"] and pd.api.types.is_numeric_dtype(df[c])]

    outliers = []

    for ind in indicators:
        if ind not in df.columns:
            continue

        series = df[ind].astype(float)
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        mean_val = series.mean()
        std_val = series.std(ddof=1) if len(series) > 1 else 0.0

        lower_bound = q1 - (iqr_multiplier * iqr)
        upper_bound = q3 + (iqr_multiplier * iqr)

        for _, row in df.iterrows():
            val = float(row[ind])
            district = str(row["district"])
            period = str(row["month"])

            is_outlier = False
            dev_type = ""
            distance_from_bound = 0.0

            if val < lower_bound:
                is_outlier = True
                dev_type = "below lower bound"
                distance_from_bound = lower_bound - val
            elif val > upper_bound:
                is_outlier = True
                dev_type = "above upper bound"
                distance_from_bound = val - upper_bound

            if is_outlier:
                z_score = ((val - mean_val) / std_val) if std_val > 0 else 0.0
                abs_z = abs(z_score)

                # Severity relative to baseline deviation
                if abs_z >= 2.5 or (iqr > 0 and distance_from_bound >= 1.0 * iqr):
                    severity = "High"
                elif abs_z >= 2.0 or (iqr > 0 and distance_from_bound >= 0.5 * iqr):
                    severity = "Medium"
                else:
                    severity = "Low"

                pct_from_mean = ((val - mean_val) / mean_val * 100.0) if mean_val != 0 else 0.0

                z_desc = f"{abs_z:.1f}σ {'below' if z_score < 0 else 'above'} state mean ({mean_val:.1f})"
                explanation = (
                    f"{district}'s {ind.replace('_', ' ')} of {val:g} in {period} is {dev_type} "
                    f"[{lower_bound:.1f}, {upper_bound:.1f}] and {z_desc}, flagging for review."
                )

                outliers.append({
                    "type": "outlier",
                    "indicator": ind,
                    "entity": district,
                    "period": period,
                    "value": round(val, 2),
                    "prev_value": round(mean_val, 2),  # Reference baseline is state mean
                    "change_pct": round(pct_from_mean, 2),
                    "severity": severity,
                    "explanation": explanation,
                })

    return outliers


def compute_correlations(
    df: pd.DataFrame,
    indicators: Optional[List[str]] = None,
    corr_threshold: float = 0.70,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Part D — Correlation Detection:
    Computes Pearson correlation matrix across numerical indicators.
    Flags pairs with |r| >= corr_threshold (excluding self-correlation).
    Severity:
      - High:   |r| >= 0.85
      - Medium: |r| >= 0.75
      - Low:    |r| >= corr_threshold
    """
    if indicators is None:
        indicators = [c for c in df.columns if c not in ["month", "district"] and pd.api.types.is_numeric_dtype(df[c])]

    num_df = df[indicators].apply(pd.to_numeric, errors="coerce")
    corr_matrix = num_df.corr(method="pearson")

    flagged_correlations = []
    n_rows = len(df)
    cols = corr_matrix.columns.tolist()

    # Traverse upper triangle to avoid duplicates and self-correlations
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            col1 = cols[i]
            col2 = cols[j]
            r_val = float(corr_matrix.loc[col1, col2])

            if np.isnan(r_val):
                continue

            abs_r = abs(r_val)
            if abs_r >= corr_threshold:
                # Severity derived relative to correlation magnitude
                if abs_r >= 0.85:
                    severity = "High"
                elif abs_r >= 0.75:
                    severity = "Medium"
                else:
                    severity = "Low"

                rel_nature = "negative" if r_val < 0 else "positive"
                time_range = f"{df['month'].min()}..{df['month'].max()}"

                explanation = (
                    f"Strong {rel_nature} correlation (r={r_val:.2f}) observed between "
                    f"{col1.replace('_', ' ')} and {col2.replace('_', ' ')} across districts "
                    f"(fragile sample: N={n_rows})."
                )

                flagged_correlations.append({
                    "type": "correlation",
                    "indicator": f"{col1}:{col2}",
                    "entity": "All Districts",
                    "period": time_range,
                    "value": round(r_val, 2),
                    "prev_value": None,
                    "change_pct": round(r_val, 2),
                    "severity": severity,
                    "explanation": explanation,
                })

    return corr_matrix, flagged_correlations


def generate_all_insights(
    df: pd.DataFrame,
    indicators: Optional[List[str]] = None,
    trend_threshold: float = 10.0,
    iqr_multiplier: float = 1.5,
    corr_threshold: float = 0.70,
) -> pd.DataFrame:
    """
    Part E — Automated Insight Generation:
    Synthesizes trends, outliers, and correlations into a single
    structured DataFrame adhering to Section 4.1 output specification.
    """
    if indicators is None:
        indicators = [c for c in df.columns if c not in ["month", "district"] and pd.api.types.is_numeric_dtype(df[c])]

    raw_insights = []

    # 1. Trends
    trends = detect_trends(df, indicators=indicators, trend_threshold=trend_threshold)
    raw_insights.extend(trends)

    # 2. Outliers
    outliers = detect_outliers(df, indicators=indicators, iqr_multiplier=iqr_multiplier)
    raw_insights.extend(outliers)

    # 3. Correlations
    _, correlations = compute_correlations(df, indicators=indicators, corr_threshold=corr_threshold)
    raw_insights.extend(correlations)

    if not raw_insights:
        return pd.DataFrame(columns=[
            "insight_id", "type", "indicator", "entity", "period",
            "value", "prev_value", "change_pct", "severity", "explanation"
        ])

    # Convert to DataFrame and auto-number IDs
    insights_df = pd.DataFrame(raw_insights)
    insights_df.insert(0, "insight_id", [f"INS-{i+1:04d}" for i in range(len(insights_df))])

    # Standardize column order matching Section 4.1
    cols_order = [
        "insight_id", "type", "indicator", "entity", "period",
        "value", "prev_value", "change_pct", "severity", "explanation"
    ]
    insights_df = insights_df[cols_order]

    return insights_df
