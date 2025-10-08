# hugelkultur_dynamic_app.py
# Streamlit dashboard to visualize how a hügelkultur mound's storage and runoff interception change over time.

import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# ----------------------------
# App config & title
# ----------------------------
st.set_page_config(page_title="Hügelkultur Dynamics", layout="wide")
st.title("Hügelkultur Dynamics")
st.caption("Adjust parameters and see how mound storage and storm interception evolve over time.")

# ----------------------------
# Sidebar Controls
# ----------------------------
st.sidebar.header("Rainfall & Catchment")
P = st.sidebar.slider("Storm rainfall P (mm)", 10, 200, 60, 5)
A = st.sidebar.number_input("Contributing area A (m²)", min_value=10.0, value=500.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1, help="Higher CN ⇒ more runoff (e.g., compacted surfaces).")

st.sidebar.header("Mound Geometry & Properties")
mound_length = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 15.0, 1.0)
mound_width  = st.sidebar.number_input("Mound base width (m)", 0.5, 10.0, 2.0, 0.5)
mound_height0 = st.sidebar.number_input("Initial mound height (m)", 0.3, 3.0, 1.5, 0.1)
wood_porosity = st.sidebar.slider("Effective porosity of wood core (0–1)", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Decomposition / Settling")
half_life_years = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
settling_frac_extra = st.sidebar.slider("Extra settling over 5y (%)", 0, 50, 15, 5,
                                        help="Additional storage loss not from decomposition (soil collapse/compaction).")
years = st.sidebar.slider("Years to simulate", 1, 30, 12, 1)

# ----------------------------
# Helper functions
# ----------------------------
def scs_runoff_mm(P_mm: float, CN: int) -> float:
    """NRCS/SCS runoff (mm) from storm depth P (mm)."""
    S = (25400 / CN) - 254   # potential max retention (mm)
    Ia = 0.2 * S             # initial abstraction (mm)
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia) ** 2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def mound_initial_storage_m3(length_m: float, width_m: float, height_m: float, porosity: float) -> float:
    """Approximate sponge-like storage from a triangular cross-section times length and porosity."""
    cross_area = 0.5 * width_m * height_m   # triangle area
    bulk_vol = cross_area * length_m
    return bulk_vol * porosity

def decay_series(initial_value: float, half_life: float, years: int, extra_settling_frac_5y: float = 0.0) -> np.ndarray:
    """Exponential decay for wood storage with a linear extra-settling loss over first 5 years."""
    t = np.arange(0, years + 1, 1)
    lam = math.log(2) / half_life
    decay_vals = initial_value * np.exp(-lam * t)

    extra = np.zeros_like(t, dtype=float)
    if years > 0 and extra_settling_frac_5y > 0:
        frac = extra_settling_frac_5y / 100.0
        ramp_years = min(5, years)
        ramp = np.linspace(0, frac * initial_value, ramp_years + 1)  # 0 → frac*initial over 5y
        extra[:ramp_years + 1] = ramp
        if years > ramp_years:
            extra[ramp_years + 1:] = frac * initial_value

    values = decay_vals - extra
    values[values < 0] = 0.0
    return values

# ----------------------------
# Core calculations
# ----------------------------
Q_mm = scs_runoff_mm(P, CN)          # runoff depth in mm
runoff_m3 = (Q_mm / 1000.0) * A      # event runoff volume (m³)

initial_storage_m3 = mound_initial_storage_m3(mound_length, mound_width, mound_height0, wood_porosity)
storage_time_series = decay_series(initial_storage_m3, half_life_years, years, settling_frac_extra)
intercepted_series = np.minimum(storage_time_series, runoff_m3)

# ----------------------------
# Metrics
# ----------------------------
colM1, colM2, colM3 = st.columns(3)
colM1.metric("Runoff depth Q (mm)", f"{Q_mm:.1f}")
colM2.metric("Event runoff (m³)", f"{runoff_m3:.1f}")
colM3.metric("Initial mound storage (m³)", f"{initial_storage_m3:.1f}")

st.markdown("---")

# ----------------------------
# Charts
# ----------------------------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Storage Decline Over Time")
    fig1, ax1 = plt.subplots(figsize=(6, 3.6))
    ax1.plot(np.arange(0, years + 1), storage_time_series, linewidth=2)
    ax1.set_xlabel("Year")
    ax1.set_ylabel("Mound Storage (m³)")
    ax1.grid(True, alpha=0.2)
    st.pyplot(fig1)

with col2:
    st.subheader("Intercepted Volume for This Storm Over Time")
    fig2, ax2 = plt.subplots(figsize=(6, 3.6))
    ax2.plot(np.arange(0, years + 1), intercepted_series, linewidth=2)
    ax2.set_xlabel("Year")
    ax2.set_ylabel("Intercepted Volume (m³)")
    ax2.grid(True, alpha=0.2)
    st.pyplot(fig2)

st.markdown("---")

# ----------------------------
# Simple Schematic (Not to Scale)
# ----------------------------
st.subheader("Schematic (Not to Scale)")
fig3, ax3 = plt.subplots(figsize=(9, 3.2))

# Ground
ax3.plot([0, 10], [2, 2], linewidth=3)

# Mound as triangle scaled to sidebar inputs
height = max(mound_height0, 0.1)
width = max(mound_width, 0.5)
left = 5 - width / 2
right = 5 + width / 2
ax3.fill([left, 5, right], [2, 2 + height, 2], alpha=0.6)

# Raindrops
for x in np.linspace(1, 9, 10):
    ax3.text(x, 5.0, "💧", ha="center", va="center", fontsize=10)

# Infiltration arrows
for x in np.linspace(left + 0.2, right - 0.2, 4):
    ax3.annotate("", xy=(x, 2.05), xytext=(x, 2 + height * 0.7),
                 arrowprops=dict(arrowstyle="-|>", lw=1.8))

# Labels
ax3.text(5, 2 + height * 0.83, "mulch + soil", ha="center", fontsize=9)
ax3.text(5, 2 + height * 0.45, "wood/organic core\n('sponge')", ha="center", fontsize=9)

ax3.set_xlim(0, 10)
ax3.set_ylim(1.5, 5.5)
ax3.axis("off")
st.pyplot(fig3)

# ----------------------------
# Footer
# ----------------------------
st.caption("Educational tool. For engineering design, consult local standards.")


