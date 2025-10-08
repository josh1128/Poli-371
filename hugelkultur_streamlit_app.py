# hugelkultur_viz_app.py
# A single-screen Streamlit app that dynamically updates a simple Hügelkultur schematic.
# No charts/graphs — just a schematic that changes with user inputs.

import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# =========================================================
# 1. PAGE CONFIGURATION
# =========================================================
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

# =========================================================
# 2. SIDEBAR CONTROLS
# =========================================================

# --- Rainfall & Catchment ---
st.sidebar.header("Rainfall & Catchment")
rainfall_mm = st.sidebar.slider("Storm rainfall (mm)", 10, 200, 60, 5)
catchment_area_m2 = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=300.0, step=10.0)
curve_number = st.sidebar.slider(
    "Curve Number (CN)", 55, 95, 85, 1,
    help="Higher CN ⇒ more runoff (e.g., compacted soils or roads)."
)

# --- Mound Dimensions ---
st.sidebar.header("Mound: Size & Sponge")
mound_length_m = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
mound_base_width_m = st.sidebar.number_input("Initial base width (m)", 0.5, 10.0, 2.0, 0.5)
mound_height_m = st.sidebar.number_input("Initial height (m)", 0.3, 3.0, 1.5, 0.1)
core_porosity = st.sidebar.slider("Wood/organic core porosity", 0.2, 0.9, 0.6, 0.05)

# --- Aging Factors ---
st.sidebar.header("Aging (Shrink/Settling)")
wood_half_life = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
extra_settling_pct = st.sidebar.slider("Extra settling over first 5y (%)", 0, 50, 15, 5)
years_elapsed = st.sidebar.slider("Year", 0, 20, 0, 1)

# =========================================================
# 3. HELPER FUNCTIONS
# =========================================================

def scs_runoff(P_mm, CN):
    """Compute runoff (mm) using SCS-CN method."""
    S = (25400 / CN) - 254
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia)**2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def initial_storage(length, width, height, porosity):
    """Initial storage capacity (m³) as triangular prism volume * porosity."""
    cross_section_area = 0.5 * width * height
    return cross_section_area * length * porosity

def aged_storage(S0, half_life, years, extra_pct):
    """Storage capacity at given year considering decay and settling."""
    decay = S0 * math.exp(-math.log(2) * years / half_life)
    extra = (extra_pct / 100) * S0 * min(years / 5, 1)
    return max(decay - extra, 0.0)

# =========================================================
# 4. CORE CALCULATIONS
# =========================================================

# Runoff depth and volume
runoff_mm = scs_runoff(rainfall_mm, curve_number)
runoff_m3 = (runoff_mm / 1000) * catchment_area_m2

# Mound capacity
initial_capacity_m3 = initial_storage(mound_length_m, mound_base_width_m, mound_height_m, core_porosity)
current_capacity_m3 = aged_storage(initial_capacity_m3, wood_half_life, years_elapsed, extra_settling_pct)

# Water intercepted by mound
intercepted_m3 = min(current_capacity_m3, runoff_m3)

# Shrinking effect (visual)
capacity_ratio = current_capacity_m3 / initial_capacity_m3 if initial_capacity_m3 > 0 else 0
visual_height = max(0.2, mound_height_m * capacity_ratio**0.8)
visual_width = max(0.4, mound_base_width_m * (0.8 + 0.2 * capacity_ratio))

# Fill level fraction
fill_ratio = min(intercepted_m3 / current_capacity_m3, 1.0) if current_capacity_m3 > 0 else 0.0

# =========================================================
# 5. METRICS DISPLAY
# =========================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("Runoff depth (mm)", f"{runoff_mm:.1f}")
col2.metric("Runoff volume (m³)", f"{runoff_m3:.1f}")
col3.metric("Mound capacity (m³)", f"{current_capacity_m3:.1f}")
col4.metric("Intercepted this storm (m³)", f"{intercepted_m3:.1f}")

st.caption(
    "Move the **Year** slider to see capacity loss over time. "
    "Adjust rainfall, catchment area, or curve number to change runoff. "
    "Change mound size or porosity to see different sponge capacities."
)

st.markdown("---")

# =========================================================
# 6. SCHEMATIC VISUALIZATION
# =========================================================
st.subheader("Schematic (Not to Scale)")
fig, ax = plt.subplots(figsize=(11, 3.8))

# Ground line
ax.plot([0, 10], [2, 2], linewidth=6, color="saddlebrown")

# Position parameters
center_x = 5
left_x = center_x - visual_width / 2
right_x = center_x + visual_width / 2
peak_y = 2 + visual_height

# Outer mound
ax.fill([left_x, center_x, right_x], [2, peak_y, 2], color="peru", alpha=0.6)

# Inner core (wood/organic matter)
inset = 0.12 * visual_width
inner_left = left_x + inset
inner_right = right_x - inset
inner_peak_y = 2 + visual_height * 0.7
ax.fill([inner_left, center_x, inner_right], [2, inner_peak_y, 2], color="sienna", alpha=0.35)

# Water fill (blue)
if fill_ratio > 0:
    water_level_y = 2 + (inner_peak_y - 2) * fill_ratio
    slope_left = (inner_peak_y - 2) / (center_x - inner_left)
    slope_right = (inner_peak_y - 2) / (inner_right - center_x)
    x_left = inner_left + (water_level_y - 2) / slope_left
    x_right = inner_right - (water_level_y - 2) / slope_right
    ax.fill([x_left, x_right, inner_right, inner_left],
            [water_level_y, water_level_y, 2, 2],
            color="deepskyblue", alpha=0.5)

# Raindrops above
n_drops = int(np.interp(rainfall_mm, [10, 200], [6, 18]))
for x in np.linspace(1, 9, n_drops):
    ax.text(x, 5.4, "💧", ha="center", va="center", fontsize=12)

# Infiltration arrows
for x in np.linspace(left_x + 0.1, right_x - 0.1, 3):
    ax.annotate("", xy=(x, 2.15), xytext=(x, 2 + visual_height * 0.75),
                arrowprops=dict(arrowstyle="-|>", lw=2))

# Labels
ax.text(center_x, peak_y + 0.15, "mulch + soil", ha="center", fontsize=10)
ax.text(center_x, 2 + visual_height * 0.42, "wood/organic core\n('sponge')", ha="center", fontsize=10)

# Capacity info
ax.text(0.8, 5.1, f"Year: {years_elapsed}", fontsize=10)
ax.text(0.8, 4.7, f"Capacity now: {current_capacity_m3:.1f} m³", fontsize=10)
ax.text(0.8, 4.3, f"Intercepted: {intercepted_m3:.1f} m³", fontsize=10)

# Final layout
ax.set_xlim(0, 10)
ax.set_ylim(1.6, 5.8)
ax.axis("off")

st.pyplot(fig)

# =========================================================
# 7. FOOTER
# =========================================================
st.caption(
    "This schematic dynamically updates with your inputs. "
    "The mound shrinks as capacity declines; the blue area shows intercepted water from this storm."
)



