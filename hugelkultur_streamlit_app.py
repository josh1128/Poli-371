# hugelkultur_viz_app.py
# A single-screen Streamlit app that DYNAMICALLY updates a simple hügelkultur schematic.
# No charts/graphs — just a picture that changes with your inputs.

import math
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# ---------- App setup ----------
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

# ---------- Sidebar controls ----------
st.sidebar.header("Rainfall & Catchment")
P = st.sidebar.slider("Storm rainfall (mm)", 10, 200, 60, 5)
A = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=300.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1, help="Higher CN ⇒ more runoff (e.g., compacted/roadside).")

st.sidebar.header("Mound: Size & Sponge")
mound_length = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
mound_width0  = st.sidebar.number_input("Initial base width (m)", 0.5, 10.0, 2.0, 0.5)
mound_height0 = st.sidebar.number_input("Initial height (m)", 0.3, 3.0, 1.5, 0.1)
porosity0     = st.sidebar.slider("Wood/organic core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Aging (Shrink/Settling)")
half_life_years = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
extra_settle_5y = st.sidebar.slider("Extra settling over first 5y (%)", 0, 50, 15, 5)
year_t = st.sidebar.slider("Year", 0, 20, 0, 1)

# ---------- Helpers ----------
def scs_runoff_mm(P_mm, CN):
    S = (25400 / CN) - 254   # mm
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia)**2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def initial_storage_m3(L, W, H, phi):
    # triangular cross-section area * length * porosity
    cross_area = 0.5 * W * H
    return cross_area * L * phi

def storage_at_year(S0, half_life, t_years, extra_settle_pct_5y):
    lam = math.log(2) / half_life
    decay = S0 * math.exp(-lam * t_years)
    # linear extra settling up to 5y, then flat
    extra = 0.0
    frac = extra_settle_pct_5y / 100.0
    if t_years <= 5:
        extra = (frac * S0) * (t_years / 5.0)
    else:
        extra = frac * S0
    S = max(decay - extra, 0.0)
    return S

# ---------- Core calculations ----------
Q_mm = scs_runoff_mm(P, CN)
runoff_m3 = (Q_mm / 1000.0) * A

S0 = initial_storage_m3(mound_length, mound_width0, mound_height0, porosity0)
S_t = storage_at_year(S0, half_life_years, year_t, extra_settle_5y)

# For a single storm, how much could the mound intercept right now?
intercept_m3 = min(S_t, runoff_m3)

# Scale the mound’s apparent dimensions with capacity loss (purely visual)
capacity_ratio = 0.0 if S0 == 0 else S_t / S0
mound_height_t = max(0.2, mound_height0 * capacity_ratio**0.8)  # soften shrink visually
mound_width_t  = max(0.4, mound_width0  * (0.8 + 0.2 * capacity_ratio))  # width shrinks less

# “Fill level” inside the mound to reflect this storm’s intercepted fraction
fill_ratio = 0.0 if S_t == 0 else min(intercept_m3 / S_t, 1.0)

# ---------- Metrics (text only, no graphs) ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Runoff depth (mm)", f"{Q_mm:.1f}")
c2.metric("Runoff volume (m³)", f"{runoff_m3:.1f}")
c3.metric("Mound capacity now (m³)", f"{S_t:.1f}")
c4.metric("Intercepted this storm (m³)", f"{intercept_m3:.1f}")

st.caption("Move the **Year** slider to see shrink/settling. Adjust rainfall/area/CN to change incoming runoff. "
           "Change mound size/porosity to see a larger or smaller sponge.")

st.markdown("---")

# ---------- Single schematic that updates ----------
st.subheader("Schematic (Not to Scale)")

fig, ax = plt.subplots(figsize=(11, 3.8))

# Ground line
ax.plot([0, 10], [2, 2], linewidth=6)

# Center position for mound
center_x = 5.0
left = center_x - mound_width_t/2
right = center_x + mound_width_t/2
peak_y = 2 + mound_height_t

# Outer mound polygon (soil + mulch)
ax.fill([left, center_x, right], [2, peak_y, 2], alpha=0.6)

# Inner “sponge” core (draw as a slightly inset triangle)
inset = 0.12 * mound_width_t
left_in  = left + inset
right_in = right - inset
peak_in_y = 2 + mound_height_t * 0.7
ax.fill([left_in, center_x, right_in], [2, peak_in_y, 2], alpha=0.35)

# Water fill inside the core to show THIS STORM interception
if fill_ratio > 0:
    # Draw a horizontal water line within the inner core
    water_top_y = 2 + (peak_in_y - 2) * fill_ratio
    # Compute intersection points with inner triangle sides to draw a filled trapezoid
    # Left side line: (x from left_in to center_x)
    # y = 2 + ( (peak_in_y-2)/(center_x-left_in) ) * (x-left_in)
    # Solve for x where y = water_top_y
    slope_left = (peak_in_y - 2) / (center_x - left_in) if center_x != left_in else 1e9
    xL = left_in + (water_top_y - 2) / slope_left

    # Right side
    slope_right = (peak_in_y - 2) / (right_in - center_x) if right_in != center_x else 1e9
    xR = right_in - (water_top_y - 2) / slope_right

    # Fill polygon for water (simple trapezoid)
    ax.fill([xL, xR, right_in, left_in], [water_top_y, water_top_y, 2, 2], alpha=0.5)

# Raindrops row: number reflects rainfall intensity
n_drops = int(np.interp(P, [10, 200], [6, 18]))
for x in np.linspace(1, 9, n_drops):
    ax.text(x, 5.4, "💧", ha="center", va="center", fontsize=12)

# Downward infiltration arrows over mound
for x in np.linspace(left+0.1, right-0.1, 3):
    ax.annotate("", xy=(x, 2.15), xytext=(x, 2 + mound_height_t*0.75),
                arrowprops=dict(arrowstyle="-|>", lw=2))

# Labels that change with year/capacity
ax.text(center_x, peak_y + 0.15, "mulch + soil", ha="center", fontsize=10)
ax.text(center_x, 2 + mound_height_t*0.42, "wood/organic core\n('sponge')", ha="center", fontsize=10)

# Capacity label
ax.text(0.8, 5.1, f"Year: {year_t}", fontsize=10)
ax.text(0.8, 4.7, f"Capacity now: {S_t:.1f} m³", fontsize=10)
ax.text(0.8, 4.3, f"Intercepted this storm: {intercept_m3:.1f} m³", fontsize=10)

ax.set_xlim(0, 10)
ax.set_ylim(1.6, 5.8)
ax.axis("off")
st.pyplot(fig)

st.caption(
    "Picture-only dashboard: the mound shrinks as capacity declines with age; blue fill shows how much of THIS storm "
    "the mound can soak up today. No charts are shown."
)



