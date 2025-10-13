# hugelkultur_map_impact_free_swale.py
# Hügelkultur impact simulation – HOPE Rwanda (Rwabutenge, Gahanga, Kicukiro)
# - Rain slider up to 1,400 mm
# - Wood decomposition reduces effective storage over time
# - Visible mound "sinking" over years due to shrinkage/settling (separate height settling rate)
# - NEW (#3): Overflow routing to a swale/pond with its own infiltration and live graphics
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
    The mound stores rainwater like a sponge, reducing surface runoff and erosion. Extra water can now overflow
    into a **downstream swale/pond** that also infiltrates into the subsoil.
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

# -------------------- Catchment & Soil --------------------
st.sidebar.header("🧮 Catchment & Soil")
A = st.sidebar.number_input("Contributing area (m²)", 10.0, 10000.0, 300.0, 10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1)

# -------------------- Downstream Swale/Pond (NEW #3) --------------------
st.sidebar.header("🟦 Downstream Swale/Pond (Overflow)")
swale_capacity = st.sidebar.number_input("Swale storage capacity (m³)", 0.0, 5000.0, 8.0, 0.5,
                                        help="Max volume the swale/pond can hold before spilling.")
swale_infiltration_m3_per_hr = st.sidebar.slider("Swale infiltration (m³/hr)", 0.0, 20.0, 1.5, 0.5,
                                                help="How fast water in the swale infiltrates into the soil.")

# Experience toggles
fps = st.sidebar.slider("Frames per second", 5, 30, 15)
animate = st.sidebar.toggle("Animate schematic", True)
run = st.sidebar.button("Run simulation", type="primary")
if not run:
    st.stop()

# -------------------- Hydrology Functions --------------------
def scs_runoff_mm(P_mm, CN):
    """Cumulative runoff depth (mm) via SCS-CN."""
    CN = float(np.clip(CN, 35, 98))
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

# Visible height settling (geometry only; does NOT change storage, which is already handled)
height_settle_factor = (1.0 - annual_height_settling) ** years_since_build
H_visible = max(H * height_settle_factor, 0.05)  # tiny floor to avoid zero-height drawing
core_height_visible = H_visible * 0.7

# Initialize accumulators
cumP = 0.0
cum_runoff_no_mound = 0.0
cum_runoff_with_mound = 0.0
intercepted = 0.0

# Swale states (NEW)
swale_stored = 0.0
swale_peak = 0.0

placeholder = st.empty()
progress = st.progress(0)

# -------------------- Simulation Loop --------------------
for minute in range(minutes):
    dP = rain_series[minute]

    # --- Catchment runoff generation (no mound) ---
    Q_prev = scs_runoff_mm(cumP, CN)
    cumP += dP
    Q_curr = scs_runoff_mm(cumP, CN)
    dQ = max(Q_curr - Q_prev, 0.0)      # incremental runoff depth (mm)
    dV = (dQ / 1000.0) * A              # incremental runoff volume (m³)
    cum_runoff_no_mound += dV

    # --- Hügel mound interception (limited by effective storage) ---
    if intercepted < S_effective:
        take = min(S_effective - intercepted, dV)
        intercepted += take
        dV -= take

    # --- Overflow routing to swale/pond (NEW #3) ---
    if dV > 0 and swale_stored < swale_capacity:
        take2 = min(swale_capacity - swale_stored, dV)
        swale_stored += take2
        dV -= take2
        swale_peak = max(swale_peak, swale_stored)

    # --- Swale infiltration (drain from swale volume each minute) ---
    if swale_stored > 0:
        swale_drain = min(swale_stored, (swale_infiltration_m3_per_hr / 60.0))
        swale_stored -= swale_drain

    # Remaining dV after mound + swale goes offsite as runoff
    cum_runoff_with_mound += dV

    fill_ratio = intercepted / S_effective if S_effective > 0 else 0.0
    swale_ratio = (swale_stored / swale_capacity) if swale_capacity > 0 else 0.0

    # ------------- Draw schematic (with visible sinking + swale) -------------
    fig, ax = plt.subplots(figsize=(11, 4.2))

    # Ground baseline
    ax.plot([0, 12], [0, 0], color="saddlebrown", linewidth=5)

    # Positions
    cx = 5.0
    left = cx - W / 2.0
    right = cx + W / 2.0

    # Soil mound (visible/settled height)
    ax.fill([left, cx, right], [0, H_visible, 0], color="#C89E71", alpha=0.8, label="Soil")

    # Core (visible/settled height)
    ax.fill([left + 0.2, cx, right - 0.2], [0, core_height_visible, 0], color="#8B5A2B", alpha=0.55, label="Wood core")

    # Stored water in mound (within visible core)
    if fill_ratio > 0:
        water_h = core_height_visible * min(fill_ratio, 1.0)
        ax.fill_between([left + 0.2, right - 0.2], 0, water_h, color="#1E90FF", alpha=0.65, label="Stored in mound")

    # Effective capacity line (visual cue)
    if years_since_build > 0 and (annual_storage_decay > 0 or annual_height_settling > 0):
        eff_ratio = max(storage_decay_factor, 0.0)
        eff_core_h_line = core_height_visible * eff_ratio
        ax.plot([left + 0.2, right - 0.2], [eff_core_h_line, eff_core_h_line], linestyle="--", color="black", linewidth=1)
        ax.text(right - 0.2, eff_core_h_line + 0.03, "effective capacity", ha="right", va="bottom", fontsize=8)

    # Swale/Pond graphic block on the right
    # Draw a rectangular basin; visual height scaled relative to mound height for consistency
    swale_x0, swale_x1 = 8.0, 10.5
    swale_h_max = max(0.6, H * 0.9)  # visual height for full capacity
    # Basin outline
    ax.fill([swale_x0, swale_x1, swale_x1, swale_x0], [0, 0, swale_h_max, swale_h_max], color="#A9A9A9", alpha=0.15, label="Swale basin")
    # Water fill based on swale_ratio
    if swale_capacity > 0 and swale_ratio > 0:
        swale_h = swale_h_max * min(swale_ratio, 1.0)
        ax.fill([swale_x0, swale_x1, swale_x1, swale_x0], [0, 0, swale_h, swale_h], color="#4AA3FF", alpha=0.75, label="Swale storage")

    # Overflow arrow from mound to swale (only when overflow occurred this minute)
    if dV > 0 or (swale_capacity > 0 and swale_ratio > 0):
        ax.annotate("overflow → swale",
                    xy=(right, 0.15), xytext=((swale_x0 + swale_x1) / 2.0, swale_h_max + 0.1),
                    arrowprops=dict(arrowstyle="->", lw=1.5), ha="center", va="bottom", fontsize=9)

    # HUD panel
    text_box = (
        f"Rain {cumP:.1f} mm  |  Intercepted {intercepted:.2f} m³  |  "
        f"Swale {swale_stored:.2f}/{swale_capacity:.2f} m³  |  "
        f"Runoff (no mound) {cum_runoff_no_mound:.2f} m³"
    )
    ax.text(0.4, max(1.6, H * 1.05), text_box, fontsize=10, bbox=dict(boxstyle="round,pad=0.35", fc="#F7F2E7", ec="#8B7E66", alpha=0.95))

    ax.set_xlim(0, 12)
    ax.set_ylim(0, max(2, H * 1.4))
    ax.axis("off")
    ax.set_title(
        f"Minute {minute+1}/{minutes}  •  With Hügelkultur + Swale Routing",
        fontsize=12, loc="left"
    )

    if animate:
        placeholder.pyplot(fig)
        time.sleep(1.0 / fps)
    progress.progress((minute + 1) / minutes)

# -------------------- Results --------------------
st.success("✅ Simulation complete!")

col1, col2, col3 = st.columns(3)
col1.metric("🌧️ Total Rainfall", f"{cumP:.1f} mm")
col2.metric("💦 Runoff (No Hügelkultur)", f"{cum_runoff_no_mound:.2f} m³")
col3.metric("💧 Runoff (With Hügelkultur + Swale)", f"{cum_runoff_with_mound:.2f} m³")

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

# Swale summary
st.markdown("### 🟦 Swale / Pond Summary")
s1, s2, s3 = st.columns(3)
s1.metric("Swale capacity (m³)", f"{swale_capacity:.2f}")
s2.metric("Swale peak storage (m³)", f"{swale_peak:.2f}")
s3.metric("Swale storage at end (m³)", f"{swale_stored:.2f}")

st.caption(
    "Hugelbeds sink in size after several years due to wood shrinkage, decomposition and settling [2]. "
    "Here, **effective storage** declines with *Annual storage decay*, while **visible height** sinks with *Annual height settling*."
)

# Optional references section (shows your requested [2] marker)
with st.expander("References"):
    st.markdown("""
- **[2]** Hügelkultur aging effects: shrinkage, decomposition, and settling reduce mound size and storage over time.
    """)
