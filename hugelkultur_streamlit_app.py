
import math
import numpy as np
import pandas as pd
import streamlit as st

# ----------------------------
# Title & Intro
# ----------------------------
st.set_page_config(page_title="Hügelkultur: Effects & Risks – HOPE Rwanda", layout="wide")
st.title("Hügelkultur: Effects & Risks – HOPE Rwanda")

st.markdown("""
This interactive tool helps you explore how **hügelkultur** (raised mounds built with buried wood and organic matter) can
affect **water retention** and **runoff** in HOPE Rwanda's context, and how certain **technical/social/economic risks** might evolve over time.
            
**Key reference:** Hügel beds retain water but **shrink over several years** as buried wood decomposes; this reduces storage and changes planting/maintenance needs. [Source in your uploaded notes]
""")

with st.expander("What is modeled here?"):
    st.markdown("""
- **Runoff from a small catchment** using a simplified SCS Curve Number (CN) method for a single storm.
- **Sponge-like storage of a hugel mound** that decays exponentially over time due to decomposition/settling.
- **Simple road-adjacent scenario**: A mound placed to intercept sheet flow before it reaches a dirt road.
- **Risk explorer**: Likelihood vs. Impact scoring for key risks (no mitigation shown, by request).
            
*These are **illustrative** calculations to support planning and communication, not engineered designs.*
""")

# ----------------------------
# Sidebar Inputs
# ----------------------------
st.sidebar.header("Rainfall & Catchment")
P = st.sidebar.slider("Storm rainfall P (mm)", min_value=10, max_value=200, value=60, step=5)
A = st.sidebar.number_input("Contributing catchment area (m²)", min_value=50.0, value=500.0, step=50.0)
CN = st.sidebar.slider("Curve Number (CN)", min_value=55, max_value=95, value=85, step=1,
                       help="Higher CN = more runoff (e.g., compacted road shoulders ~85–90).")

st.sidebar.header("Hügelkultur Geometry & Material")
mound_length = st.sidebar.number_input("Mound length (m)", min_value=1.0, value=15.0, step=1.0)
mound_width = st.sidebar.number_input("Mound base width (m)", min_value=0.5, value=2.0, step=0.5)
mound_height0 = st.sidebar.number_input("Initial mound height (m)", min_value=0.3, value=1.5, step=0.1)
wood_porosity = st.sidebar.slider("Effective porosity of wood core (0–1)", min_value=0.2, max_value=0.9, value=0.6, step=0.05)

st.sidebar.header("Decomposition / Settling")
half_life_years = st.sidebar.slider("Wood volume half-life (years)", min_value=1, max_value=15, value=6, step=1,
                                    help="Time for wood storage capacity to halve.")
settling_frac_extra = st.sidebar.slider("Extra settling (non-decomposition) over 5y (%)", min_value=0, max_value=50, value=15, step=5)

st.sidebar.header("Road & Slope Context")
slope_pct = st.sidebar.slider("Hillslope (%)", min_value=0, max_value=40, value=12, step=1)
road_distance_m = st.sidebar.slider("Hugel to road distance (m)", min_value=2, max_value=50, value=10, step=1)

years = st.sidebar.slider("Years to simulate", min_value=1, max_value=20, value=10, step=1)

# ----------------------------
# Helper functions
# ----------------------------
def scs_runoff_mm(P_mm, CN):
    """SCS runoff (mm) from storm depth P (mm)."""
    S = (25400 / CN) - 254  # potential max retention (mm)
    Ia = 0.2 * S            # initial abstraction (mm)
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia) ** 2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def mound_initial_storage_m3(length_m, width_m, height_m, porosity):
    """
    Approximate sponge-like storage within the wood core volume.
    Use a triangular cross-section approximation for mound profile.
    """
    # triangular cross-sectional area ~ 0.5 * base * height
    cross_area = 0.5 * width_m * height_m
    bulk_vol = cross_area * length_m  # m³
    return bulk_vol * porosity

def decay_series(initial_value, half_life, years, extra_settling_frac_5y=0.0):
    """
    Exponential decay for wood storage; apply extra settling as a linear loss over first 5 years.
    Returns an array of length (years+1) at integer years.
    """
    t = np.arange(0, years+1, 1)
    lam = math.log(2) / half_life
    decay_vals = initial_value * np.exp(-lam * t)
    # extra settling applied as fraction of initial over first 5y
    extra = np.zeros_like(t, dtype=float)
    if years > 0 and extra_settling_frac_5y > 0:
        frac = extra_settling_frac_5y / 100.0
        # linear ramp 0 -> frac*initial over first 5 years, then flat
        ramp_years = min(5, years)
        ramp = np.linspace(0, frac * initial_value, ramp_years + 1)
        extra[:ramp_years+1] = ramp
        extra[ramp_years+1:] = frac * initial_value
    return np.maximum(decay_vals - extra, 0.0)

# ----------------------------
# Calculations
# ----------------------------
Q_mm = scs_runoff_mm(P, CN)  # runoff depth in mm
runoff_m3 = Q_mm / 1000.0 * A  # volume (m³)

initial_storage_m3 = mound_initial_storage_m3(mound_length, mound_width, mound_height0, wood_porosity)
storage_time_series = decay_series(initial_storage_m3, half_life_years, years, settling_frac_extra)

# Simple interception effect: fraction of event runoff that mound could absorb in year 0 vs later
intercepted0 = min(initial_storage_m3, runoff_m3)
interceptedT = np.minimum(storage_time_series, runoff_m3)

# ----------------------------
# Layout
# ----------------------------
col1, col2 = st.columns([1,1])

with col1:
    st.subheader("Storm Runoff Estimate (Single Event)")
    st.metric("Curve Number (CN)", CN)
    st.metric("Runoff depth Q (mm)", f"{Q_mm:.1f}")
    st.metric("Runoff volume (m³) from A", f"{runoff_m3:.1f}")
    st.caption("SCS CN method (illustrative).")

    st.subheader("Hügel Mound Initial Storage")
    st.metric("Initial sponge-like storage (m³)", f"{initial_storage_m3:.1f}")
    st.caption("Approximate from mound shape and wood porosity.")

with col2:
    st.subheader("Interception vs. Years")
    df = pd.DataFrame({
        "Year": np.arange(0, years+1),
        "Mound Storage (m³)": storage_time_series,
        "Runoff Volume (m³)": runoff_m3,
        "Intercepted This Event (m³)": interceptedT
    })
    st.line_chart(df.set_index("Year")[["Mound Storage (m³)", "Intercepted This Event (m³)"]])

    st.caption("As wood decomposes and the mound settles, storage declines – reducing how much stormwater a mound can intercept.")

st.markdown("---")
st.subheader("Spatial Schematic (Not to Scale)")
st.markdown(f"""
- Hillslope: **{slope_pct}%**; mound is **{road_distance_m} m** upslope of the road.
- The mound acts as a **sponge**: in Year 0, it could intercept up to **{intercepted0:.1f} m³** from this storm.
- By Year {years}, its capacity declines to **{storage_time_series[-1]:.1f} m³**, intercepting **{min(storage_time_series[-1], runoff_m3):.1f} m³** for the same storm.
""")

# ----------------------------
# Risk Explorer (No Mitigations)
# ----------------------------
st.markdown("---")
st.header("Risk Explorer (No Mitigations)")

st.markdown("""
Score each risk's **Likelihood** and **Impact** (1–5). This creates a heat-style table to compare which risks are most critical **without** proposing mitigations.
""")

risk_items = [
    "Structural settling/shrinkage of mound (capacity loss)",
    "Sediment buildup reducing performance",
    "Overflow/erosion during extreme storms",
    "Water quality/contamination in stored water",
    "Unequal benefit distribution across households",
    "Gendered labor/time burden",
    "Funding instability (build or O&M)",
    "Opportunity cost of land allocation"
]

likelihood = {}
impact = {}
for r in risk_items:
    with st.expander(r):
        likelihood[r] = st.slider(f"Likelihood – {r}", 1, 5, 3, key=f"lik_{r}")
        impact[r] = st.slider(f"Impact – {r}", 1, 5, 3, key=f"imp_{r}")

risk_df = pd.DataFrame({
    "Risk": risk_items,
    "Likelihood (1–5)": [likelihood[r] for r in risk_items],
    "Impact (1–5)": [impact[r] for r in risk_items]
})
risk_df["Risk Score = L × I"] = risk_df["Likelihood (1–5)"] * risk_df["Impact (1–5)"]

st.dataframe(risk_df, use_container_width=True)

st.markdown("""
**Interpretation:** Higher scores indicate risks that are both more likely and more damaging under current assumptions (with no mitigations applied).
""")

# ----------------------------
# Notes & Sources
# ----------------------------
st.markdown("---")
st.markdown("""
### Notes & Sources
- Hügelkultur mounds are built from logs/plant debris and **shrink over several years** as wood decomposes; they **retain water like a sponge**, slowing runoff and storing moisture for dry spells (see your uploaded notes).  
- Model simplifies complex hydrology; use for scoping and education, not engineering design.
""")
