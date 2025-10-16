# hugelkultur_map_impact_free.py
# Hügelkultur impact simulation – HOPE Rwanda (Rwabutenge, Gahanga, Kicukiro)
# - Rain slider up to 1,400 mm
# - Wood decomposition reduces effective storage over time
# - NEW: Visible mound "sinking" over years due to shrinkage/settling (separate height settling rate)
# - Displays note: "Hugelbeds sink in size after several years..." [2]

import math, time
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
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

# Rwanda monthly rainfall guide (mm): dry Jun–Aug; rainy Mar–May & Sep–Nov
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
        st.sidebar.caption("Dry season: storms are typically smaller/rarer (Jun–Aug).")
    elif month in ["Mar", "Apr", "May", "Sep", "Oct", "Nov"]:
        st.sidebar.caption("Rainy season: heavier, more frequent downpours (Mar–May, Sep–Nov).")
    else:
        st.sidebar.caption("Transitional period with moderate rainfall.")

duration_min = st.sidebar.slider("Storm duration (minutes)", 5, 240, 60, 5)
rain_shape = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded", "Back-loaded", "Pulsed"])
randiness = st.sidebar.slider("Rain randomness", 0.0, 1.0, 0.15, 0.05)

# -------------------- Mound geometry (as-built) --------------------
st.sidebar.header("🧱 Hügelkultur Mound (As-built)")
L = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
W = st.sidebar.number_input("Base width (m)", 0.5, 10.0, 2.0, 0.5)
H = st.sidebar.number_input("Height (m)", 0.3, 3.0, 1.5, 0.1)
porosity = st.sidebar.slider("Core porosity", 0.2, 0.9, 0.6, 0.05)

# -------------------- Decomposition & Settling --------------------
st.sidebar.header("🌲 Aging: Decomposition & Settling")
years_since_build = st.sidebar.slider("Years since mound was built", 0, 20, 0, 1)

# Storage (void-space) decay = pore loss from decomposition/compaction
annual_storage_decay = st.sidebar.slider(
    "Annual storage decay (void loss)", 0.00, 0.20, 0.08, 0.01,
    help="Fractional loss of *effective storage* per year (e.g., 0.08 = 8%/yr)."
)

# NEW: Visible height settling rate (geometry sink)
annual_height_settling = st.sidebar.slider(
    "Annual height settling (visual)", 0.00, 0.10, 0.03, 0.01,
    help="Reduces visible mound height to mimic shrinkage/settling over years."
)

st.sidebar.header("🧮 Catchment & Soil")
A = st.sidebar.number_input("Contributing area (m²)", 10.0, 10000.0, 300.0, 10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1)

fps = st.sidebar.slider("Frames per second", 5, 30, 15)

# -------------------- Hydrology Functions --------------------
def scs_runoff_mm(P_mm, CN):
    """Cumulative runoff depth (mm) via SCS-CN."""
    S = (25400 / CN) - 254
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    return ((P_mm - Ia) ** 2) / (P_mm - Ia + S)

def hyetograph(total_mm, minutes, shape="Steady", jitter=0.0):
    """Rain intensity series (mm/minute)."""
    minutes = max(int(minutes), 1)
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
        rng = np.random.default_rng()
        noise = rng.normal(0, jitter, minutes)
        series = np.clip(series * (1 + noise), 0, None)
        series *= total_mm / max(series.sum(), 1e-9)
    return series

def mound_capacity(L, W, H, phi):
    """Triangular cross-section * length * porosity (m³)."""
    return 0.5 * W * H * L * phi

# -------------------- Simulation Setup --------------------
minutes = int(duration_min)
rain_series = hyetograph(total_rain_mm, minutes, rain_shape, randiness)

# As-built storage
S_initial = mound_capacity(L, W, H, porosity)

# Effective storage after years (void-space decay)
storage_decay_factor = (1.0 - annual_storage_decay) ** years_since_build
S_effective = S_initial * storage_decay_factor

# NEW: Visible height settling (geometry only; does NOT change storage, which is already handled)
height_settle_factor = (1.0 - annual_height_settling) ** years_since_build
H_visible = max(H * height_settle_factor, 0.05)  # keep a tiny floor to avoid zero-height drawing
core_height_visible = H_visible * 0.7

# Initialize accumulators
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
    dQ = max(Q_curr - Q_prev, 0.0)      # incremental runoff depth (mm)
    dV = (dQ / 1000.0) * A              # incremental runoff volume (m³)
    cum_runoff_no_mound += dV

    # Interception by mound (from runoff only), limited by effective storage
    if intercepted < S_effective:
        take = min(S_effective - intercepted, dV)
        intercepted += take
        dV -= take
    cum_runoff_with_mound += dV

    fill_ratio = intercepted / S_effective if S_effective > 0 else 0.0

    # ------------- Draw schematic (with visible sinking) -------------
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([0, 10], [0, 0], color="saddlebrown", linewidth=5)  # ground line

    cx = 5.0
    left = cx - W / 2.0
    right = cx + W / 2.0

    # Soil mound (visible/settled height)
    ax.fill([left, cx, right], [0, H_visible, 0], color="#cd853f", alpha=0.7, label="Soil")

    # Core (visible/settled height)
    ax.fill([left + 0.2, cx, right - 0.2], [0, core_height_visible, 0], color="#8b5a2b", alpha=0.5, label="Wood core")

    # Stored water (limited by effective storage, drawn within visible core)
    if fill_ratio > 0:
        water_h = core_height_visible * min(fill_ratio, 1.0)
        ax.fill_between([left + 0.2, right - 0.2], 0, water_h, color="dodgerblue", alpha=0.6, label="Stored water")

    # Show dashed line marking "effective capacity" level relative to visible core
    if years_since_build > 0 and (annual_storage_decay > 0 or annual_height_settling > 0):
        # Translate storage decay (void loss) into a notional horizontal line inside the core
        # purely for visual cue; does not change hydrology beyond S_effective
        eff_ratio = max(storage_decay_factor, 0.0)
        eff_core_h_line = core_height_visible * eff_ratio
        ax.plot([left + 0.2, right - 0.2], [eff_core_h_line, eff_core_h_line], linestyle="--", color="black", linewidth=1)
        ax.text(right - 0.2, eff_core_h_line + 0.03, "effective capacity", ha="right", va="bottom", fontsize=8)

    ax.set_xlim(0, 10)
    ax.set_ylim(0, max(2, H * 1.3))  # keep y-limits stable relative to as-built H for easy comparison
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

# Capacity & geometry panel
st.markdown("### 🪵 Storage Capacity, Settling & Decomposition")
cap1, cap2, cap3, cap4 = st.columns(4)
S_initial_val = mound_capacity(L, W, H, porosity)
cap1.metric("As-built capacity (m³)", f"{S_initial_val:.2f}")
cap2.metric("Effective capacity today (m³)", f"{S_effective:.2f}")
remain_pct = 100.0 * (S_effective / S_initial_val) if S_initial_val > 0 else 0.0
cap3.metric("Capacity remaining", f"{remain_pct:.0f}%")
cap4.metric("Visible height today (m)", f"{H_visible:.2f}")

st.caption(
    "Hugelbeds sink in size after several years due to wood shrinkage, decomposition and settling [2]. "
    "Here, **effective storage** declines with *Annual storage decay*, while **visible height** sinks with *Annual height settling*."
)

# Optional references section (shows your requested [2] marker)
with st.expander("References"):
    st.markdown("""
- **[2]** Hügelkultur aging effects: shrinkage, decomposition, and settling reduce mound size and storage over time.
    """)
