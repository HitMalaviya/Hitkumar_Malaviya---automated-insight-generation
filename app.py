"""
app.py - Streamlit UI for Automated Insight Generation Engine
Meets all Assignment 4 requirements:
- Data loading, inspection (head, info, missing values)
- Live filtering (District, Month, Indicator)
- Configurable threshold sliders (Trend %, Outlier IQR, Correlation |r|)
- Visualizations: Severity bar chart, Correlation heatmap, Per-district line chart
- Downloads: insights.csv, correlation_matrix.csv, insights.json
"""

import io
import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import engine

st.set_page_config(
    page_title="Auto-Analytics Insight Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏥 Auto-Analytics Engine — Healthcare Performance")
st.caption("Automated generation of trends, outliers, correlations, and natural-language insights.")

# --- SIDEBAR: Configuration & Filters ---
st.sidebar.header("📁 Data Source")
uploaded_file = st.sidebar.file_uploader("Upload District CSV", type=["csv"])
default_csv_path = "data/healthcare_performance.csv"

# Load dataset
if uploaded_file is not None:
    df_raw, validation_report = engine.load_and_validate_data(uploaded_file)
    data_source_label = "Uploaded CSV"
else:
    df_raw, validation_report = engine.load_and_validate_data(default_csv_path)
    data_source_label = "Default Sample CSV"

st.sidebar.markdown(f"**Loaded:** `{data_source_label}` ({validation_report['total_rows']} rows)")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Threshold Controls (Sliders)")

trend_thresh = st.sidebar.slider(
    "Trend Threshold (± %)",
    min_value=1.0,
    max_value=50.0,
    value=10.0,
    step=1.0,
    help="Flags period-over-period change if |pct_change| >= threshold (Part B)",
)

iqr_mult = st.sidebar.slider(
    "Outlier IQR Multiplier",
    min_value=1.0,
    max_value=3.0,
    value=1.5,
    step=0.1,
    help="Flags values beyond Q1/Q3 ± (multiplier * IQR) (Part C)",
)

corr_thresh = st.sidebar.slider(
    "Correlation Threshold (|r|)",
    min_value=0.50,
    max_value=0.95,
    value=0.70,
    step=0.05,
    help="Flags indicator pairs if Pearson |r| >= threshold (Part D)",
)

st.sidebar.markdown("---")
st.sidebar.header("🔍 Live Data Filters")

all_districts = validation_report["districts"]
selected_districts = st.sidebar.multiselect(
    "Filter by District",
    options=all_districts,
    default=all_districts,
    help="Filter active data views by district",
)

all_months = validation_report["months"]
selected_months = st.sidebar.multiselect(
    "Filter by Month",
    options=all_months,
    default=all_months,
    help="Filter active data views by month",
)

all_indicators = validation_report["numeric_indicators"]
selected_indicators = st.sidebar.multiselect(
    "Filter Indicators",
    options=all_indicators,
    default=all_indicators,
    help="Select indicators for analysis & visualization",
)

# Apply filters to dataset
if not selected_districts or not selected_months or not selected_indicators:
    st.warning("⚠️ Please select at least one District, Month, and Indicator in the sidebar.")
    st.stop()

filtered_df = df_raw[
    (df_raw["district"].isin(selected_districts)) &
    (df_raw["month"].isin(selected_months))
].copy()

# Sample size warning required by assignment guidelines
if len(filtered_df) < 20:
    st.info(
        f"ℹ️ **Statistical Fragility Notice (Section 10 Warning):** "
        f"Active sample contains {len(filtered_df)} observations across {len(selected_districts)} districts and "
        f"{len(selected_months)} months. Pearson correlation estimates and baseline variance are sensitive to small sample sizes."
    )

# --- RUN ENGINE ---
insights_df = engine.generate_all_insights(
    df=filtered_df,
    indicators=selected_indicators,
    trend_threshold=trend_thresh,
    iqr_multiplier=iqr_mult,
    corr_threshold=corr_thresh,
)

corr_matrix, flagged_corrs = engine.compute_correlations(
    df=filtered_df,
    indicators=selected_indicators,
    corr_threshold=corr_thresh,
)

# --- TOP METRICS BAR ---
high_count = int((insights_df["severity"] == "High").sum()) if not insights_df.empty else 0
med_count = int((insights_df["severity"] == "Medium").sum()) if not insights_df.empty else 0
low_count = int((insights_df["severity"] == "Low").sum()) if not insights_df.empty else 0

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Records", len(filtered_df))
m2.metric("Total Insights", len(insights_df))
m3.metric("🔴 High Severity", high_count)
m4.metric("🟠 Medium Severity", med_count)
m5.metric("🔵 Low Severity", low_count)

# --- TABS FOR WORKFLOW ---
tab_insights, tab_visuals, tab_data = st.tabs([
    "💡 Automated Insights",
    "📈 Visualizations (Line, Bar, Heatmap)",
    "📋 Data Inspection & Validation",
])

# ==========================================
# TAB 1: AUTOMATED INSIGHTS
# ==========================================
with tab_insights:
    st.subheader("Dynamic Machine-Generated Insights")
    st.caption("Insights are dynamically evaluated without hardcoded narratives. All numbers derive strictly from calculations.")

    if insights_df.empty:
        st.info("No insights flagged with current filter and threshold parameters. Try lowering threshold sliders in the sidebar.")
    else:
        # Filter insights by severity or type
        c_filter1, c_filter2 = st.columns(2)
        with c_filter1:
            sev_filter = st.multiselect(
                "Filter by Severity",
                options=["High", "Medium", "Low"],
                default=["High", "Medium", "Low"],
            )
        with c_filter2:
            type_filter = st.multiselect(
                "Filter by Insight Type",
                options=insights_df["type"].unique().tolist(),
                default=insights_df["type"].unique().tolist(),
            )

        displayed_insights = insights_df[
            (insights_df["severity"].isin(sev_filter)) &
            (insights_df["type"].isin(type_filter))
        ].copy()

        # Download Buttons
        c_down1, c_down2, c_down3 = st.columns([1, 1, 2])
        csv_insights = displayed_insights.to_csv(index=False).encode("utf-8")
        c_down1.download_button(
            label="📥 Download insights.csv",
            data=csv_insights,
            file_name="insights.csv",
            mime="text/csv",
        )

        json_insights = json.dumps(displayed_insights.to_dict(orient="records"), indent=2).encode("utf-8")
        c_down2.download_button(
            label="📥 Download insights.json",
            data=json_insights,
            file_name="insights.json",
            mime="application/json",
        )

        # Insights Table
        st.dataframe(
            displayed_insights,
            use_container_width=True,
            column_config={
                "insight_id": st.column_config.TextColumn("ID", width="small"),
                "type": st.column_config.TextColumn("Type", width="small"),
                "indicator": st.column_config.TextColumn("Indicator", width="medium"),
                "entity": st.column_config.TextColumn("Entity", width="medium"),
                "period": st.column_config.TextColumn("Period", width="small"),
                "value": st.column_config.NumberColumn("Value", format="%.2f"),
                "prev_value": st.column_config.NumberColumn("Prev / Base", format="%.2f"),
                "change_pct": st.column_config.NumberColumn("Change % / r", format="%.2f"),
                "severity": st.column_config.TextColumn("Severity", width="small"),
                "explanation": st.column_config.TextColumn("Explanation", width="large"),
            },
            hide_index=True,
        )

        st.markdown("### 📝 Insight Narratives Feed")
        for _, row in displayed_insights.iterrows():
            sev_badge = {
                "High": "🔴 **HIGH**",
                "Medium": "🟠 **MEDIUM**",
                "Low": "🔵 **LOW**",
            }.get(row["severity"], row["severity"])

            with st.container(border=True):
                col_meta, col_text = st.columns([1, 3])
                with col_meta:
                    st.markdown(f"**{row['insight_id']}** | `{row['type'].upper()}`")
                    st.markdown(f"Entity: **{row['entity']}** ({row['period']})")
                    st.markdown(f"Severity: {sev_badge}")
                with col_text:
                    st.markdown(f"**Indicator:** `{row['indicator']}`")
                    st.write(f"💬 {row['explanation']}")


# ==========================================
# TAB 2: VISUALIZATIONS
# ==========================================
with tab_visuals:
    st.subheader("Data & Performance Visualizations")

    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.markdown("#### 1. Severity Distribution (Bar Chart)")
        if not insights_df.empty:
            sev_counts = insights_df.groupby(["severity", "type"]).size().reset_index(name="count")
            fig_bar = px.bar(
                sev_counts,
                x="severity",
                y="count",
                color="type",
                barmode="group",
                color_discrete_map={
                    "trend": "#3b82f6",
                    "outlier": "#ef4444",
                    "correlation": "#10b981",
                },
                title="Insight Counts by Severity & Category",
                category_orders={"severity": ["High", "Medium", "Low"]},
            )
            fig_bar.update_layout(xaxis_title="Severity Level", yaxis_title="Number of Insights", height=380)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No insights to visualize.")

    with col_v2:
        st.markdown("#### 2. Pearson Correlation Heatmap")
        if not corr_matrix.empty and len(corr_matrix.columns) > 1:
            fig_heat = px.imshow(
                corr_matrix,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdBu_r",
                zmin=-1.0,
                zmax=1.0,
                title=f"Pearson Correlation Matrix (|r| ≥ {corr_thresh:.2f} flagged)",
            )
            fig_heat.update_layout(height=380)
            st.plotly_chart(fig_heat, use_container_width=True)

            corr_csv = corr_matrix.to_csv().encode("utf-8")
            st.download_button(
                label="📥 Download correlation_matrix.csv",
                data=corr_csv,
                file_name="correlation_matrix.csv",
                mime="text/csv",
            )
        else:
            st.info("Need at least two numeric indicators to compute correlation.")

    st.markdown("#### 3. Per-District Indicator Trends (Line Chart)")
    chosen_chart_ind = st.selectbox(
        "Select Indicator for District Comparison",
        options=selected_indicators,
        index=0,
    )

    if not filtered_df.empty:
        fig_line = px.line(
            filtered_df,
            x="month",
            y=chosen_chart_ind,
            color="district",
            markers=True,
            title=f"Monthly Trajectory of {chosen_chart_ind.replace('_', ' ').title()} by District",
        )
        fig_line.update_layout(
            xaxis_title="Month",
            yaxis_title=chosen_chart_ind.replace("_", " ").title(),
            height=420,
        )
        st.plotly_chart(fig_line, use_container_width=True)


# ==========================================
# TAB 3: DATA INSPECTION & VALIDATION
# ==========================================
with tab_data:
    st.subheader("Data Profiling & Quality Audit (Part A)")

    col_audit1, col_audit2 = st.columns([2, 1])

    with col_audit1:
        st.markdown("#### `head()` — Raw Data Preview")
        st.dataframe(df_raw.head(), use_container_width=True)

        st.markdown("#### Summary Statistics (`describe()`)")
        st.dataframe(df_raw.describe(), use_container_width=True)

    with col_audit2:
        st.markdown("#### Missing-Value Report (`isnull().sum()`)")
        missing_df = pd.DataFrame(
            list(validation_report["missing_counts"].items()),
            columns=["Column", "Missing Values Count"],
        )
        st.dataframe(missing_df, hide_index=True, use_container_width=True)

        st.markdown("#### Data Health Check")
        st.write(f"- **Composite Key Duplicates:** {validation_report['duplicate_composite_keys']}")
        st.write(f"- **Missing Schema Columns:** {validation_report['missing_required_cols'] or 'None (All present)'}")
        st.write(f"- **Total Rows:** {validation_report['total_rows']}")
        st.write(f"- **Total Districts:** {len(validation_report['districts'])}")
        st.write(f"- **Total Months:** {len(validation_report['months'])}")
