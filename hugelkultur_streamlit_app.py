# hugelkultur_map_impact_free.py
# Streamlit app: Hügelkultur impact simulation at HOPE Rwanda site (Rwabutenge, Gahanga Sector, Kicukiro)

import math, time
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib import patches
import folium
from streamlit_folium import st_folium

# -------------------- Page setup --------------------
st.set_page_config(page_title="Hügelkultur Impact – HOPE Rwanda", layout="wide")
st.title("💧 Hügelkultur Impact Simulation – HOPE Rwanda Site (Rwabutenge, Gahanga, Kicukiro)")

# -------------------- Free Map (OpenStreetMap) --------------------
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
total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 300, 120, 5)
duration_min = st.sidebar.slider("Storm duration (minutes)", 5, 240, 60, 5)
rain_shape = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded", "Back-loaded", "Pulsed"])
randiness = st.sidebar.slider("Rain randomness", 0.0, 1.0, 0.15, 0.05)

st.sidebar.header("🧱 Hügelkultur Mound")
L = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
W = st.sidebar.number_input("Base width (m)", 0.5, 10.0, 2.0, 0.5)
H = st.sidebar.number_input("Height (m)", 0.3, 3.0, 1.5, 0.1)
porosity = st.sidebar.slider("Core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("🧮 Catchment & Soil")
A = st.sidebar.number_input("Contributing area (m²)", 10.0, 10000.0, 300.0, 10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1)

fps = st.sidebar.slider("Frames per second", 5, 30, 15)

# -------------------- Hydrology Functions --------------------
def scs_runoff_mm(P_mm, CN):
    """Compute cumulative runoff depth (mm) using SCS-CN method"""
    S = (25400 / CN) - 254
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    return ((P_mm - Ia) ** 2) / (P_mm - Ia + S)

def hyetograph(total_mm, minutes, shape="Steady", jitter=0.0):
    """Rain intensity series (mm/minute)"""
    t = np.linspace(0, 1, minutes)
    if shape == "Steady":
        base = np.ones_like(t)
    elif shape == "Front-loaded":
        base = (1 - t) ** 2.2 + 0.2
    elif shape == "Back-loaded":
        base = t ** 2.2 + 0.2
    else:  # Pulsed
        base = 0.35 + 0.45 * np.maximum(0, np.sin(np.pi * 5 * t))
    base = np.clip(base, 0.05, None)
    base /= base.sum()
    series = base * total_mm
    if jitter > 0:
        noise = np.random.normal(0, jitter, minutes)
        series = np.clip(series * (1 + noise), 0, None)
        series *= total_mm / max(series.sum(), 1e-9)
    return series

def mound_capacity(L, W, H, phi):
    """Triangular cross-section * length * porosity"""
    return 0.5 * W * H * L * phi

# -------------------- Simulation Setup --------------------
minutes = int(duration_min)
rain_series = hyetograph(total_rain_mm, minutes, rain_shape, randiness)

S_t = mound_capacity(L, W, H, porosity)
cumP = 0.0
cum_runoff_no_mound = 0.0
cum_runoff_with_mound = 0.0
intercepted = 0.0

placeholder = st.empty()
progress = st.progress(0)

# -------------------- Simulation Loop --------------------
for minute in range(minutes):
    dP = rain_series[minute]
    Q_prev = scs_runoff_mm(cumP, CN)
    cumP += dP
    Q_curr = scs_runoff_mm(cumP, CN)
    dQ = max(Q_curr - Q_prev, 0.0)
    dV = (dQ / 1000.0) * A  # m³
    cum_runoff_no_mound += dV

    # Interception by Hügelkultur mound
    if intercepted < S_t:
        take = min(S_t - intercepted, dV)
        intercepted += take
        dV -= take
    cum_runoff_with_mound += dV

    fill_ratio = intercepted / S_t if S_t > 0 else 0.0

    # Draw schematic
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([0, 10], [0, 0], color="saddlebrown", linewidth=5)
    cx = 5
    left = cx - W / 2
    right = cx + W / 2
    peak = H
    # Soil mound
    ax.fill([left, cx, right], [0, peak, 0], color="#cd853f", alpha=0.7)
    # Core sponge
    ax.fill([left + 0.2, cx, right - 0.2], [0, peak * 0.7, 0], color="#8b5a2b", alpha=0.5)
    # Water fill
    if fill_ratio > 0:
        water_h = peak * 0.7 * fill_ratio
        ax.fill_between([left + 0.2, right - 0.2], 0, water_h, color="dodgerblue", alpha=0.6)
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

st.write(f"**Intercepted water volume:** {intercepted:.2f} m³")
st.write(f"**Storage capacity of mound:** {S_t:.2f} m³")
st.write("✅ Hügelkultur **reduces runoff** and **increases water retention**, ideal for erosion control and soil moisture improvement.")

