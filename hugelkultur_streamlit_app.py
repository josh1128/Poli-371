# app.py
# LIVE Permeable Pavement + Vetiver Grass Simulator (Streamlit, no Matplotlib)
# Deps: streamlit, numpy, pandas (built-in charts only)

import time
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Live Pavement + Vetiver Simulator", layout="wide")
st.title("🛣️ Permeable Pavement + 🌿 Vetiver — LIVE Runoff Simulator")

# -----------------------------
# Helpers
# -----------------------------
def scs_runoff_depth_mm(P, CN):
    """SCS-CN runoff depth (mm) for total event depth P."""
    S = 25400.0 / CN - 254.0  # mm
    Ia = 0.2 * S
    if P <= Ia:
        return 0.0
    return ((P - Ia) ** 2) / (P + 0.8 * S)

def mm_over_area_to_m3(mm, area_m2):
    return (mm / 1000.0) * area_m2

def hyetograph(total_depth_mm, duration_min, kind="Triangular", peak_at=0.4):
    """Return per-minute intensities that sum to total_depth_mm."""
    t = np.arange(duration_min, dtype=float)
    if kind == "Uniform":
        i = np.ones_like(t) * (total_depth_mm / duration_min)
    elif kind == "Front-loaded":
        # exponential decay
        x = np.linspace(0, 3, duration_min)
        w = np.exp(-x)
        i = w / w.sum() * total_depth_mm
    elif kind == "Back-loaded":
        x = np.linspace(0, 3, duration_min)
        w = np.exp(-x[::-1])
        i = w / w.sum() * total_depth_mm
    else:  # Triangular (default)
        peak_idx = max(1, int(peak_at * (duration_min - 1)))
        up = np.linspace(0, 1, peak_idx + 1)
        down = np.linspace(1, 0, duration_min - peak_idx - 1)
        shape = np.concatenate([up, down]) if down.size else up
        i = shape / shape.sum() * total_depth_mm
    return i

# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.header("Storm & Site")
P_total = st.sidebar.slider("Storm total (mm)", 20, 200, 80, 5)
duration_min = st.sidebar.slider("Storm duration (min)", 10, 240, 90, 5)
hyeto_kind = st.sidebar.selectbox("Hyetograph shape", ["Triangular", "Uniform", "Front-loaded", "Back-loaded"])
peak_at = st.sidebar.slider("Triangular peak at fraction of duration", 0.2, 0.8, 0.4, 0.05)
area_m2 = st.sidebar.number_input("Catchment area (m²)", 100.0, 50000.0, 3000.0, 50.0)
base_CN = st.sidebar.slider("Base Curve Number (dirt/unpaved)", 70, 95, 85, 1)
slope = st.sidebar.selectbox("Slope condition", ["Low", "Moderate", "Steep"], index=1)
slope_factor = {"Low": 0.95, "Moderate": 1.00, "Steep": 1.05}[slope]

st.sidebar.header("Permeable Pavement")
pp_on = st.sidebar.toggle("Enable Permeable Pavement", True)
pp_frac = st.sidebar.slider("Fraction of area converted", 0.0, 1.0, 0.30, 0.05) if pp_on else 0.0
pp_CN_delta = st.sidebar.slider("CN reduction on permeable area (points)", 0, 20, 8, 1) if pp_on else 0
pp_direct_infil_pct = (st.sidebar.slider("Direct infiltration on permeable area (%)", 0, 90, 40, 5)/100.0) if pp_on else 0.0

st.sidebar.header("Vetiver Grass")
vet_on = st.sidebar.toggle("Enable Vetiver Grass", True)
vet_CN_delta = st.sidebar.slider("CN reduction from vetiver (points)", 0, 12, 4, 1) if vet_on else 0
vet_extra_infil_pct = (st.sidebar.slider("Extra infiltration on remaining runoff (%)", 0, 40, 12, 1)/100.0) if vet_on else 0.0

st.sidebar.header("Playback")
speed = st.sidebar.slider("Playback speed (sim minutes / second)", 1, 20, 6, 1)
autoloop = st.sidebar.checkbox("Loop when finished", value=False)

# -----------------------------
# Session state for "live" sim
# -----------------------------
if "t_idx" not in st.session_state:
    st.session_state.t_idx = 0
if "playing" not in st.session_state:
    st.session_state.playing = False
if "last_tick" not in st.session_state:
    st.session_state.last_tick = time.time()

col_btn1, col_btn2, col_btn3 = st.columns([1,1,1])
if col_btn1.button("▶️ Play"):
    st.session_state.playing = True
    st.session_state.last_tick = time.time()
if col_btn2.button("⏸️ Pause"):
    st.session_state.playing = False
if col_btn3.button("⏮️ Reset"):
    st.session_state.playing = False
    st.session_state.t_idx = 0

# -----------------------------
# Build per-minute storm + CN
# -----------------------------
intensities = hyetograph(P_total, duration_min, kind=hyeto_kind, peak_at=peak_at)
cumP = np.cumsum(intensities)

# Effective CN (area-weighted) BEFORE slope factor
CN_eff = base_CN
if vet_on:
    CN_eff = max(30, CN_eff - vet_CN_delta)
if pp_on and pp_frac > 0:
    CN_perm = max(30, CN_eff - pp_CN_delta)
    CN_eff = (1 - pp_frac) * CN_eff + pp_frac * CN_perm
CN_eff *= slope_factor

# For live minute steps, we approximate SCS-CN **incrementally**:
# At each minute m, compute runoff depth from cumulative rain P[0:m],
# then take the **incremental** runoff for that minute as the difference.
def incremental_runoff_series(intensities_mm, CN):
    cum = np.cumsum(intensities_mm)
    Q_tot = np.array([scs_runoff_depth_mm(P, CN) for P in cum])
    inc = np.diff(np.concatenate([[0.0], Q_tot]))
    inc[inc < 0] = 0.0
    return inc, Q_tot

inc_Q_mm, cum_Q_mm = incremental_runoff_series(intensities, CN_eff)

# Partition each minute's water:
# 1) Rain falling on permeable fraction: direct infiltration share never becomes runoff.
rain_on_perm_mm = intensities * pp_frac
pp_direct_infil_mm = rain_on_perm_mm * pp_direct_infil_pct

# Convert **runoff** from SCS (which is post-generation) in mm to m³ then apply vetiver extra infiltration
inc_Q_m3 = mm_over_area_to_m3(inc_Q_mm, area_m2)
pp_direct_infil_m3 = mm_over_area_to_m3(pp_direct_infil_mm, area_m2)

# After subtracting permeable direct infiltration (some generation avoidance), any remaining runoff
# is further reduced by vetiver's extra infiltration percentage.
runoff_after_pp_m3 = np.maximum(0.0, inc_Q_m3 - pp_direct_infil_m3)
vetiver_extra_infil_m3 = runoff_after_pp_m3 * (vet_extra_infil_pct if vet_on else 0.0)
effective_runoff_m3_series = np.maximum(0.0, runoff_after_pp_m3 - vetiver_extra_infil_m3)

# -----------------------------
# Advance the simulation clock
# -----------------------------
if st.session_state.playing:
    now = time.time()
    dt = now - st.session_state.last_tick
    st.session_state.last_tick = now
    # advance by (speed * dt) simulated minutes
    advance = int(speed * dt)
    if advance > 0:
        st.session_state.t_idx += advance
        if st.session_state.t_idx >= duration_min:
            if autoloop:
                st.session_state.t_idx = 0
            else:
                st.session_state.t_idx = duration_min - 1
                st.session_state.playing = False
    st.experimental_rerun()

t = int(st.session_state.t_idx)  # current minute index (0 .. duration_min-1)
if t < 0: t = 0
if t > duration_min - 1: t = duration_min - 1

# -----------------------------
# KPIs (live)
# -----------------------------
baseline_CN_with_slope = base_CN * slope_factor
baseline_Q_mm_total = scs_runoff_depth_mm(P_total, baseline_CN_with_slope)
baseline_runoff_m3_total = mm_over_area_to_m3(baseline_Q_mm_total, area_m2)

live_cumP = cumP[t]
live_cumQ_mm = cum_Q_mm[t]
live_cum_runoff_m3 = np.sum(effective_runoff_m3_series[:t+1])
live_cum_pp_direct_m3 = np.sum(pp_direct_infil_m3[:t+1])
live_cum_vet_extra_m3 = np.sum(vetiver_extra_infil_m3[:t+1])

reduction_ratio = 1.0 - (live_cum_runoff_m3 / (baseline_runoff_m3_total + 1e-9))
score = (
    60 * max(0.0, reduction_ratio) +
    20 * (pp_frac if pp_on else 0.0) +
    20 * (1.0 if vet_on else 0.0)
)
score = float(np.clip(score, 0, 100))

k1, k2, k3, k4 = st.columns(4)
k1.metric("Minute", f"{t+1}/{duration_min}")
k2.metric("Cumulative rain (mm)", f"{live_cumP:,.1f}")
k3.metric("Cumulative runoff (m³)", f"{live_cum_runoff_m3:,.1f}")
k4.metric("Road Protection Score", f"{score:.0f}/100")

# Status banner
status = "✅ Roads holding well" if score >= 70 else ("🟨 Watch flow paths" if score >= 40 else "🟥 Likely washouts")
st.info(f"**Status:** {status}")

st.divider()

# -----------------------------
# Live charts
# -----------------------------
left, right = st.columns([1.2, 1.4])

with left:
    st.subheader("Rainfall Intensity (mm/min)")
    df_int = pd.DataFrame({"mm/min": intensities[:t+1]})
    st.line_chart(df_int, height=220)

    st.subheader("Cumulative Rain vs Runoff (mm)")
    df_cum = pd.DataFrame({
        "Rain (mm)": cumP[:t+1],
        "Runoff (mm, SCS w/ solutions)": cum_Q_mm[:t+1]
    })
    st.line_chart(df_cum, height=220)

with right:
    st.subheader("Where did the water go? (cumulative m³)")
    df_parts = pd.DataFrame({
        "Remaining runoff": [live_cum_runoff_m3],
        "Permeable direct infiltration": [live_cum_pp_direct_m3],
        "Vetiver extra infiltration": [live_cum_vet_extra_m3],
    }).T
    df_parts.columns = ["m³"]
    st.bar_chart(df_parts, height=320)

st.divider()
st.markdown("### Live Values (this minute)")
minute_table = pd.DataFrame(
    [
        ("Rain this minute (mm)", intensities[t]),
        ("Incremental runoff (mm, SCS)", inc_Q_mm[t]),
        ("Permeable direct infil (mm)", pp_direct_infil_mm[t] if pp_on else 0.0),
        ("Effective runoff this minute (m³)", effective_runoff_m3_series[t]),
    ],
    columns=["Metric", "Value"]
)
st.dataframe(minute_table, use_container_width=True, hide_index=True)

with st.expander("Model notes"):
    st.markdown(
        """
- SCS–CN is applied cumulatively; incremental runoff each minute is the difference of cumulative runoff.
- Permeable pavement effects:
  - **CN reduction** on the converted fraction (weighted area).
  - **Direct infiltration %** on the permeable patch removes some rainfall before it becomes runoff.
- Vetiver effects:
  - **CN reduction** (global improvement).
  - **Extra infiltration %** applied to the remaining runoff after permeable direct infiltration.
- This is an educational planner — not a calibrated engineering design.
        """
    )
