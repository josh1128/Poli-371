# app.py (or Simulation.py)
# HOPE Rwanda – Stormwater Solutions Sandbox (no Matplotlib)

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="HOPE Rwanda Stormwater Sandbox", layout="wide")
st.title("HOPE Rwanda – Stormwater Solutions Sandbox")

with st.expander("About this tool", expanded=False):
    st.markdown(
        """
Explore combined effects of feasible measures at the HOPE Rwanda site:
- Rainwater Harvesting (barrels/tanks)
- Vetiver Grass hedgerows
- Hügelkultur beds
- Permeable Pavements

This uses a simplified SCS–Curve Number water balance to show estimated runoff reduction,
temporary storage, and a qualitative Road Protection Score (illustrative).
"""
    )

# -------------------------
# Sidebar: Site & Storm Inputs
# -------------------------
st.sidebar.header("1) Site & Storm Inputs")

colA, colB = st.sidebar.columns(2)
P_mm = colA.slider("Design storm depth P (mm)", 20, 200, 80, 5)
catchment_area_m2 = colB.number_input("Road catchment draining to problem spots (m²)", 100.0, 20000.0, 3000.0, 50.0)

colC, colD = st.sidebar.columns(2)
roof_area_m2 = colC.number_input("Rooftop area available for harvesting (m²)", 0.0, 5000.0, 400.0, 10.0)
base_CN = colD.slider("Base Curve Number (dirt roads/soils)", 70, 95, 85, 1)

slope_note = st.sidebar.selectbox("Slope condition", ["Low", "Moderate", "Steep"], index=1)
slope_factor = {"Low": 0.95, "Moderate": 1.00, "Steep": 1.05}[slope_note]

# -------------------------
# Sidebar: Solutions
# -------------------------
st.sidebar.header("2) Solutions")

# Rainwater Harvesting
harv_on = st.sidebar.toggle("Enable Rainwater Harvesting", value=True)
if harv_on:
    colH1, colH2 = st.sidebar.columns(2)
    storage_per_unit_L = colH1.number_input("Unit size (L)", 200.0, 10000.0, 1000.0, 50.0)
    n_units = colH2.number_input("# of units", 0, 500, 10, 1)
    first_flush_mm = st.sidebar.slider("First-flush diverter (mm skimmed)", 0, 5, 2, 1)
else:
    storage_per_unit_L, n_units, first_flush_mm = 0.0, 0, 0

# Vetiver Grass
vetiver_on = st.sidebar.toggle("Enable Vetiver Grass hedgerows", value=True)
if vetiver_on:
    vetiver_CN_delta = st.sidebar.slider("CN reduction from vetiver (points)", 0, 10, 4, 1)
    vetiver_infiltration_boost = st.sidebar.slider("Extra infiltration from vetiver (%)", 0, 30, 10, 1) / 100.0
else:
    vetiver_CN_delta, vetiver_infiltration_boost = 0, 0.0

# Hügelkultur
hug_on = st.sidebar.toggle("Enable Hügelkultur beds", value=True)
if hug_on:
    colHu1, colHu2, colHu3 = st.sidebar.columns(3)
    n_beds = colHu1.number_input("# of beds", 0, 200, 20, 1)
    bed_length_m = colHu2.number_input("Bed length (m)", 1.0, 50.0, 6.0, 0.5)
    bed_width_m = colHu3.number_input("Bed width (m)", 0.5, 5.0, 1.2, 0.1)
    bed_core_depth_m = st.sidebar.number_input("Core thickness (m)", 0.1, 2.0, 0.6, 0.05)
    core_porosity = st.sidebar.slider("Core porosity (void fraction)", 0.20, 0.80, 0.50, 0.05)
    border_loss_factor = st.sidebar.slider("Edge losses (fraction of capacity)", 0.0, 0.5, 0.15, 0.05)
    hug_intercept_share = st.sidebar.slider("Share of road runoff intercepted by beds (%)", 0, 80, 30, 5) / 100.0
else:
    n_beds, bed_length_m, bed_width_m, bed_core_depth_m = 0, 0.0, 0.0, 0.0
    core_porosity, border_loss_factor, hug_intercept_share = 0.0, 0.0, 0.0

# Permeable Pavements
pp_on = st.sidebar.toggle("Enable Permeable Pavements", value=False)
if pp_on:
    pp_CN_delta = st.sidebar.slider("CN reduction (permeable area)", 0, 20, 8, 1)
    pp_infiltration_share = st.sidebar.slider("Direct infiltration on permeable area (%)", 0, 90, 40, 5) / 100.0
    pp_fraction_of_catch = st.sidebar.slider("Fraction of catchment converted", 0.0, 1.0, 0.25, 0.05)
else:
    pp_CN_delta, pp_infiltration_share, pp_fraction_of_catch = 0, 0.0, 0.0

# -------------------------
# Helpers
# -------------------------
def scs_runoff_depth_mm(P, CN):
    """SCS-CN runoff depth (mm)."""
    S = 25400.0 / CN - 254.0  # mm
    Ia = 0.2 * S
    if P <= Ia:
        return 0.0
    return ((P - Ia) ** 2) / (P + 0.8 * S)

def m3_from_mm_over_area(mm, area_m2):
    return (mm / 1000.0) * area_m2

# -------------------------
# 1) Baseline runoff (with solution-adjusted CN)
# -------------------------
CN_effective = base_CN
if vetiver_on:
    CN_effective = max(30, CN_effective - vetiver_CN_delta)
if pp_on:
    # Weighted CN with permeable patch reduction
    CN_effective = (1 - pp_fraction_of_catch) * CN_effective + pp_fraction_of_catch * max(30, CN_effective - pp_CN_delta)

CN_effective = CN_effective * slope_factor
Q_mm = scs_runoff_depth_mm(P_mm, CN_effective)
baseline_runoff_m3 = m3_from_mm_over_area(Q_mm, catchment_area_m2)

# -------------------------
# 2) Rainwater Harvesting
# -------------------------
if harv_on:
    harvest_P_effective_mm = max(0.0, P_mm - first_flush_mm)
    roof_yield_m3 = m3_from_mm_over_area(harvest_P_effective_mm, roof_area_m2)
    total_rooftop_storage_m3 = (storage_per_unit_L * n_units) / 1000.0
    captured_roof_m3 = min(roof_yield_m3, total_rooftop_storage_m3)
    roof_overflow_m3 = max(0.0, roof_yield_m3 - captured_roof_m3)
else:
    roof_yield_m3 = 0.0
    captured_roof_m3 = 0.0
    roof_overflow_m3 = 0.0

# -------------------------
# 3) Hügelkultur storage & interception
# -------------------------
if hug_on:
    hugel_core_vol_m3 = n_beds * bed_length_m * bed_width_m * bed_core_depth_m
    hugel_storage_m3 = hugel_core_vol_m3 * core_porosity * (1.0 - border_loss_factor)
    hugel_intercepted_m3 = min(baseline_runoff_m3 * hug_intercept_share, hugel_storage_m3)
    hugel_overflow_m3 = max(0.0, baseline_runoff_m3 * hug_intercept_share - hugel_intercepted_m3)
else:
    hugel_storage_m3 = 0.0
    hugel_intercepted_m3 = 0.0
    hugel_overflow_m3 = 0.0

# -------------------------
# 4) Permeable pavements direct infiltration (on permeable fraction)
# -------------------------
if pp_on:
    pp_incident_rain_m3 = m3_from_mm_over_area(P_mm, catchment_area_m2 * pp_fraction_of_catch)
    pp_direct_infiltration_m3 = pp_incident_rain_m3 * pp_infiltration_share
else:
    pp_direct_infiltration_m3 = 0.0

# -------------------------
# 5) Vetiver additional infiltration
# -------------------------
remaining_after_hugel = max(0.0, baseline_runoff_m3 - hugel_intercepted_m3)
vetiver_extra_infiltration_m3 = remaining_after_hugel * vetiver_infiltration_boost if vetiver_on else 0.0

# -------------------------
# 6) Combine flows
# -------------------------
effective_runoff_m3 = (
    max(0.0, baseline_runoff_m3 - hugel_intercepted_m3 - vetiver_extra_infiltration_m3)
    + hugel_overflow_m3
)
effective_runoff_m3 = max(0.0, effective_runoff_m3 - pp_direct_infiltration_m3)
effective_runoff_m3 += roof_overflow_m3

# -------------------------
# 7) Road Protection Score (0–100)
# -------------------------
reduction_ratio = 1.0 - (effective_runoff_m3 / (baseline_runoff_m3 + 1e-9))
score = (
    40 * max(0.0, reduction_ratio)
    + 20 * (1.0 if vetiver_on else 0.0)
    + 20 * (pp_fraction_of_catch if pp_on else 0.0)
    + 20 * (min(1.0, hugel_intercepted_m3 / (hugel_storage_m3 + 1e-9)) if hug_on else 0.0)
)
score = float(np.clip(score, 0, 100))

# -------------------------
# Outputs
# -------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Baseline runoff (m³)", f"{baseline_runoff_m3:,.1f}")
col2.metric("Effective runoff after solutions (m³)", f"{effective_runoff_m3:,.1f}")
col3.metric("Water captured in tanks (m³)", f"{captured_roof_m3:,.1f}")
col4.metric("Road Protection Score (0–100)", f"{score:.0f}")

st.divider()
st.subheader("Water Balance & Effects Summary")

summary_rows = [
    ("Design storm depth (mm)", P_mm),
    ("Catchment area (m²)", catchment_area_m2),
    ("Effective CN (after solutions)", round(CN_effective, 1)),
    ("Baseline runoff (m³)", round(baseline_runoff_m3, 2)),
    ("Rooftop yield (m³)", round(roof_yield_m3, 2)),
    ("Captured in tanks (m³)", round(captured_roof_m3, 2)),
    ("Rooftop overflow (m³)", round(roof_overflow_m3, 2)),
    ("Hügel storage capacity (m³)", round(hugel_storage_m3, 2)),
    ("Hügel intercepted (m³)", round(hugel_intercepted_m3, 2)),
    ("Hügel overflow (m³)", round(hugel_overflow_m3, 2)),
    ("Permeable direct infiltration (m³)", round(pp_direct_infiltration_m3, 2)),
    ("Vetiver extra infiltration (m³)", round(vetiver_extra_infiltration_m3, 2)),
    ("Effective runoff after solutions (m³)", round(effective_runoff_m3, 2)),
    ("Road Protection Score", round(score, 0)),
]
df = pd.DataFrame(summary_rows, columns=["Metric", "Value"])
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("Distribution of Water (m³)")
bars = pd.DataFrame(
    {
        "Volume (m³)": {
            "Tanks (rooftop)": float(captured_roof_m3),
            "Hügel intercepted": float(hugel_intercepted_m3),
            "Permeable infiltration": float(pp_direct_infiltration_m3),
            "Vetiver added infiltration": float(vetiver_extra_infiltration_m3),
            "Remaining runoff": float(effective_runoff_m3),
        }
    }
)
# Streamlit’s built-in chart (no extra plotting packages required)
st.bar_chart(bars)

st.divider()
st.markdown("### What to try")
st.markdown(
    """
- Increase **# of tanks** or **unit size** to reduce ground overflow.
- Add **Hügelkultur** (more/longer/deeper/higher porosity) to intercept more road runoff.
- Turn on **Permeable Pavements** and grow the **converted fraction** to boost direct infiltration.
- Increase **Vetiver CN reduction** and **extra infiltration** to represent dense, maintained hedgerows.
- Test higher **storm depths** and compare the Road Protection Score.
"""
)

