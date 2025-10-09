# hugelkultur_map_impact_free.py
# Streamlit app: Hügelkultur impact simulation at HOPE Rwanda site (Rwabutenge, Gahanga Sector, Kicukiro)
# - Expanded rainfall range to 1,400 mm
# - Rwanda seasonal presets
# - Wood decomposition & storage loss over years

import math, time
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium

# -------------------- Page setup --------------------
st.set_page_config(page_title="Hügelkultur Impact – HOPE Rwanda", layout="wide")
st.title("💧 Hügelkultur Impact Simulation – HOPE Rwanda Site (Rwabutenge, Gahanga, Kicukiro)")

# -------------------- Map --------------------
SITE_LAT, SITE_LON = -2.0344, 30.1318
with st.expander("🗺️ View Project Site Map", expanded=True):
    m = folium.Map(location=[SITE_LAT, SITE_LON], zoom_start=14, tiles="OpenStreetMap")
    folium.Marker(
        [SITE_LAT, SITE_LON],
        popup="HOPE Rwanda Project Site – Rwabutenge, Gahanga Sector",
        tooltip="Click for details",
        icon=folium.Icon(color="red", icon="tint")
    ).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, width=700, height=450)

st.markdown(
    """
    This tool simulates a **rainfall event** and compares **runoff** with and without a Hügelkultur mound.
    The mound stores rainwater like a sponge, reducing surface runoff and erosion.
    """
)

# -------------------- Sidebar Controls ----------------------
st.sidebar.header("🌧️ Storm Parameters")

# Rwanda monthly rainfall guide (mm)
monthly_mm = {
    "Jan": 100, "Feb": 110, "Mar": 120, "Apr": 150, "May": 150,
    "Jun": 20,  "Jul": 15,  "Aug": 30,
    "Sep": 110, "Oct": 120, "Nov": 130, "Dec": 100
}

rain_input_mode = st.sidebar.radio(
    "Rain input",
    ["Manual", "Rwanda seasonal preset"],
    index=1,
    help="Use Rwanda presets to reflect dry (Jun–Aug) vs rainy seasons (Mar–May, Sep–Nov)."
)

if rain_input_mode == "Manual":
    total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 1400, 120, 5)
else:
    month = st.sidebar.selectbox("Month (Rwanda climate)", list(monthly_mm.keys()), index=3)
    monthly_total = monthly_mm[month]
    storm_pct = st.sidebar.select_slider(
        "Storm size (% of monthly total)",
        options=[5, 10, 15, 20, 25, 30, 40, 50],
        value=10,
        help="Downpours are common; larger values approximate intense events."
    )
    suggested = int(round(monthly_total * storm_pct / 100.0))
    total_rain_mm = st.sidebar.slider(
        "Total storm rain (mm)",
        5, 1400, suggested, 5,
        help="Default is month × % of monthly rainfall; adjust as needed."
    )
    if month in ["Jun", "Jul", "Aug"]:
        st.sidebar.caption("Dry season: smaller, less frequent storms.")
    elif month in ["Mar", "Apr", "May", "Sep", "Oct", "Nov"]:
        st.sidebar.caption("Rainy season: heavier, frequent downpours.")
    else:
        st.sidebar.caption("Transition period with moderate rainfall.")

duration_min = st.sidebar.slider("Storm duration (minutes)", 5, 240, 60, 5)
rain_shape = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded", "Back-loaded", "Pulsed"])
randiness = st.sidebar.slider("Rain randomness", 0.0, 1.0, 0.15, 0.05)

# -------------------- Mound & decomposition --------------------
st.sidebar.header("🧱 Hügelkultur Mound (Initial Build)")
L = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
W = st.sidebar.number_input("Base width (m)", 0.5, 10.0, 2.0, 0.5)
H = st.sidebar.number_input("Height (m)", 0.3, 3.0, 1.5, 0.1)
porosity = st.sidebar.slider("Core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("🌲 Wood Decomposition / Settling")
years_since_build = st.sidebar.slider("Years since mound was built", 0, 20, 0, 1)
annual_decay_rate = st.sidebar.slider(
    "Annual shrinkage/decomposition rate", 0.00, 0.20, 0.08, 0.01,
    help="Fractional loss of *effective storage* per year (e.g., 0.08 = 8%/yr)."
)

st.sidebar.header("🧮 Catchment & Soil")
A = st.sidebar.number_input("Contributing area (m²)", 10.0, 10000.0, 300.0, 10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1)

fps = st.sidebar.slider("Frames per second", 5, 30, 15)

# -------------------- Hydrology Functions --------------------
def scs_runoff_mm(P_mm, CN):
    S = (25400 / CN) - 254
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    return ((P_mm - Ia) ** 2) / (P_mm - Ia + S)

def hyetograph(total_mm, minutes, shape="Steady", jitter=0.0):
    minutes = max(int(minutes), 1)
    t = np.linspace(0, 1, minutes)
    if shape == "Steady":
        base = np.ones_like(t)
    elif shape == "Front-loaded":
        base = (1 - t) ** 2.2 + 0.2
    elif shape == "Back-loaded":
        base = t ** 2.2 + 0.2
    else:
        base = 0.35 + 0.45 * np.maximum(0, np.sin(np.pi * 5 * t))
    base = np.clip(base, 0.05, None)
    base /= base.sum()
    series = base * total_mm
    if jitter > 0:
        rng = np.random.default_rng()
        noise = rng.normal(0, jitter, minutes)
        series = np.clip(series * (1 + noise), 0, None)
        series *= total_mm / max(series.sum(), 1e-9)
    return series

def mound_capacity(L, W, H, phi):
    return 0.5 * W * H * L * phi

# -------------------- Simulation Setup --------------------
minutes = int(duration_min)
rain_series = hyetograph(total_rain_mm, minutes, rain_shape, randiness)

S_initial = mound_capacity(L, W, H, porosity)
decay_factor = (1.0 - annual_decay_rate) ** years_since_build
S_effective = S_initial * decay_factor

cumP, cum_runoff_no_mound, cum_runoff_with_mound, intercepted = 0, 0, 0, 0

placeholder = st.empty()
progress = st.progress(0)

# -------------------- Simulation Loop --------------------
for minute in range(minutes):
    dP = rain_series[minute]
    Q_prev = scs_runoff_mm(cumP, CN)
    cumP += dP
    Q_curr = scs_runoff_mm(cumP, CN)
    dQ = max(Q_curr - Q_prev, 0.0)
    dV = (dQ / 1000.0) * A
    cum_runoff_no_mound += dV

    if intercepted < S_effective:
        take = min(S_effective - intercepted, dV)
        intercepted += take
        dV -= take
    cum_runoff_with_mound += dV

    fill_ratio = intercepted / S_effective if S_effective > 0 else 0.0

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([0, 10], [0, 0], color="saddlebrown", linewidth=5)
    cx = 5
    left = cx - W / 2
    right = cx + W / 2
    peak = H
    core_height = peak * 0.7
    ax.fill([left, cx, right], [0, peak, 0], color="#cd853f", alpha=0.7)
    ax.fill([left + 0.2, cx, right - 0.2], [0, core_height, 0], color="#8b5a2b", alpha=0.5)

    if fill_ratio > 0:
        water_h = core_height * min(fill_ratio, 1.0)
        ax.fill_between([left + 0.2, right - 0.2], 0, water_h, color="dodgerblue", alpha=0.6)

    if years_since_build > 0:
        eff_core_h = core_height * decay_factor
        ax.plot([left + 0.2, right - 0.2], [eff_core_h, eff_core_h], linestyle="--", color="black")
        ax.text(right - 0.2, eff_core_h + 0.03, "effective capacity", ha="right", va="bottom", fontsize=8)

    ax.set_xlim(0, 10)
    ax.set_ylim(0, max(2, H * 1.3))
    ax.axis("off")
    ax.set_title(
        f"Minute {minute+1}/{minutes} | Rain {cumP:.1f} mm | "
        f"Intercepted {intercepted:.2f} m³ | Runoff (no mound) {cum_runoff_no_mound:.2f} m³"
    )
    placeholder.pyplot(fig)
    progress.progress((minute + 1) / minutes)
    time.sleep(1.0 / fps)

# -------------------- Results --------------------
st.success("✅ Simulation complete!")

col1, col2, col3 = st.columns(3)
col1.metric("🌧️ Total Rainfall", f"{cumP:.1f} mm")
col2.metric("💦 Runoff (No Hügelkultur)", f"{cum_runoff_no_mound:.2f} m³")
col3.metric("💧 Runoff (With Hügelkultur)", f"{cum_runoff_with_mound:.2f} m³")

st.write(f"**Intercepted water volume (this storm):** {intercepted:.2f} m³")

st.markdown("### 🪵 Storage Capacity & Decomposition")
cap1, cap2, cap3 = st.columns(3)
cap1.metric("As-built capacity (m³)", f"{S_initial:.2f}")
cap2.metric("Effective capacity today (m³)", f"{S_effective:.2f}")
remain_pct = 100 * (S_effective / S_initial) if S_initial > 0 else 0
cap3.metric("Capacity remaining", f"{remain_pct:.0f}%")

st.caption(
    "Effective capacity declines with **years** as wood decomposes and mound settles. "
    "Rainfall range expanded to **1,400 mm** to reflect intense tropical downpours in Rwanda."
)
