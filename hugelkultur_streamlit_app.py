# hugelkultur_viz_app.py
# Streamlit app: DYNAMIC hügelkultur schematic with a real-rain time simulation (no graphs).
# Fixes: uses placeholders (st.empty) + session_state so frames actually render during the loop.

import math, time, random
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# ---------- App setup ----------
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

# Keep a running flag in session_state
if "run_id" not in st.session_state:
    st.session_state.run_id = 0  # bump this to restart the loop

# ---------- Sidebar controls ----------
st.sidebar.header("Rainfall & Catchment")
total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 300, 80, 5)
duration_min  = st.sidebar.slider("Storm duration (minutes)", 5, 240, 40, 5)
rain_shape    = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded burst", "Back-loaded burst", "Pulsed"])
randiness     = st.sidebar.slider("Intensity randomness (0–smooth, 1–chaotic)", 0.0, 1.0, 0.15, 0.05)
A  = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=300.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1, help="Higher CN ⇒ more runoff (e.g., compacted/roadside).")

st.sidebar.header("Mound: Size & Sponge")
mound_length = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
mound_width0  = st.sidebar.number_input("Initial base width (m)", 0.5, 10.0, 2.0, 0.5)
mound_height0 = st.sidebar.number_input("Initial height (m)", 0.3, 3.0, 1.5, 0.1)
porosity0     = st.sidebar.slider("Wood/organic core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Aging (Shrink/Settling)")
half_life_years = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
extra_settle_5y = st.sidebar.slider("Extra settling over first 5y (%)", 0, 50, 15, 5)
year_t          = st.sidebar.slider("Year", 0, 20, 0, 1)

st.sidebar.header("Animation")
ms_per_frame = st.sidebar.slider("Animation speed (ms per frame)", 40, 400, 140, 10)
show_raindrop_rows = st.sidebar.checkbox("Show falling 💧 drops", True)

# IMPORTANT: Use on_click to bump a run_id so Streamlit treats it as a new loop
def _restart():
    st.session_state.run_id += 1
st.sidebar.button("▶️ Start / Replay Rain", on_click=_restart)

# ---------- Helpers ----------
def scs_runoff_mm(P_mm, CN):
    S = (25400 / CN) - 254   # mm
    Ia = 0.2 * S
    if P_mm <= Ia:
        return 0.0
    Q = ((P_mm - Ia)**2) / (P_mm - Ia + S)
    return max(Q, 0.0)

def initial_storage_m3(L, W, H, phi):
    return 0.5 * W * H * L * phi  # triangular cross-section area * length * porosity

def storage_at_year(S0, half_life, t_years, extra_settle_pct_5y):
    lam = math.log(2) / half_life
    decay = S0 * math.exp(-lam * t_years)
    frac = extra_settle_pct_5y / 100.0
    extra = (frac * S0) * (t_years/5.0) if t_years <= 5 else (frac * S0)
    return max(decay - extra, 0.0)

def make_hyetograph(total_mm, minutes, shape="Steady", jitter=0.0, pulses=6):
    t = np.linspace(0, 1, minutes)
    if shape == "Steady":
        base = np.ones_like(t)
    elif shape == "Front-loaded burst":
        base = (1 - t)**2.2 + 0.2
    elif shape == "Back-loaded burst":
        base = t**2.2 + 0.2
    elif shape == "Pulsed":
        base = np.ones_like(t) * 0.4
        for k in range(1, pulses+1):
            base += 0.35 * np.maximum(0, np.sin(np.pi * (k * t)))
    else:
        base = np.ones_like(t)

    base = np.clip(base, 0.05, None)
    base = base / base.sum()
    series = base * total_mm

    if jitter > 0:
        noise = np.random.normal(0, jitter, size=minutes)
        series = np.clip(series * (1 + noise), 0, None)
        series *= total_mm / max(series.sum(), 1e-9)
    return series  # mm per minute

def make_drop_frame(n_drops, width=(1,9), y_top=5.6, y_bot=1.8):
    xs = np.linspace(width[0], width[1], n_drops) + np.random.uniform(-0.15, 0.15, n_drops)
    ys = np.linspace(y_top, y_bot, n_drops) + np.random.uniform(-0.1, 0.1, n_drops)
    return list(zip(xs, ys))

# ---------- Static mound capacity now ----------
S0 = initial_storage_m3(mound_length, mound_width0, mound_height0, porosity0)
S_t = storage_at_year(S0, half_life_years, year_t, extra_settle_5y)

capacity_ratio = 0.0 if S0 == 0 else S_t / S0
mound_height_t = max(0.2, mound_height0 * capacity_ratio**0.8)
mound_width_t  = max(0.4, mound_width0  * (0.8 + 0.2 * capacity_ratio))

# ---------- UI placeholders (THIS is the key to make it show) ----------
metrics_ph   = st.empty()
subtitle_ph  = st.empty()
figure_ph    = st.empty()
caption_ph   = st.empty()

st.caption("Move the **Year** slider to see shrink/settling. Adjust rain total/duration/shape for realistic storms. "
           "Change mound size/porosity to see a larger or smaller sponge.")
st.markdown("---")

# ---------- Draw one frame into the placeholder ----------
def draw_frame(figure_placeholder, minute_idx, fill_ratio_frame, intercepted_m3, cum_runoff_m3, minutes):
    subtitle_ph.subheader("Schematic (Not to Scale)")

    fig, ax = plt.subplots(figsize=(11, 3.8))
    # Ground
    ax.plot([0, 10], [2, 2], linewidth=6)

    # Mound geometry
    cx = 5.0
    left = cx - mound_width_t/2
    right = cx + mound_width_t/2
    peak_y = 2 + mound_height_t

    # Outer mound
    ax.fill([left, cx, right], [2, peak_y, 2], alpha=0.6)

    # Inner core
    inset = 0.12 * mound_width_t
    left_in, right_in = left + inset, right - inset
    peak_in_y = 2 + mound_height_t * 0.7
    ax.fill([left_in, cx, right_in], [2, peak_in_y, 2], alpha=0.35)

    # Water fill
    if fill_ratio_frame > 0:
        water_top_y = 2 + (peak_in_y - 2) * min(fill_ratio_frame, 1.0)
        slope_left  = (peak_in_y - 2) / max(cx - left_in, 1e-9)
        slope_right = (peak_in_y - 2) / max(right_in - cx, 1e-9)
        xL = left_in + (water_top_y - 2) / slope_left
        xR = right_in - (water_top_y - 2) / slope_right
        ax.fill([xL, xR, right_in, left_in], [water_top_y, water_top_y, 2, 2], alpha=0.5)

    # Drops
    if show_raindrop_rows:
        n = 12
        for (x, y) in make_drop_frame(n):
            ax.text(x, y, "💧", ha="center", va="center", fontsize=12)

    # Infiltration arrows
    for x in np.linspace(left+0.1, right-0.1, 3):
        ax.annotate("", xy=(x, 2.15), xytext=(x, 2 + mound_height_t*0.75),
                    arrowprops=dict(arrowstyle="-|>", lw=2))

    # Labels
    ax.text(cx, peak_y + 0.15, "mulch + soil", ha="center", fontsize=10)
    ax.text(cx, 2 + mound_height_t*0.42, "wood/organic core\n('sponge')", ha="center", fontsize=10)
    ax.text(0.8, 5.3, f"Year: {year_t}", fontsize=10)
    ax.text(0.8, 4.9, f"Capacity now: {S_t:.1f} m³", fontsize=10)
    ax.text(0.8, 4.5, f"Intercepted so far: {intercepted_m3:.1f} m³", fontsize=10)
    ax.text(0.8, 4.1, f"Runoff so far: {cum_runoff_m3:.1f} m³", fontsize=10)
    ax.text(0.8, 3.7, f"Minute {minute_idx+1} / {minutes}", fontsize=10)

    ax.set_xlim(0, 10)
    ax.set_ylim(1.6, 5.8)
    ax.axis("off")

    figure_placeholder.pyplot(fig)
    plt.close(fig)

def show_metrics(cumP, cum_runoff_m3, S_t, intercepted_m3):
    with metrics_ph.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cumulative rain (mm)", f"{cumP:.1f}")
        c2.metric("Runoff volume (m³)", f"{cum_runoff_m3:.1f}")
        c3.metric("Mound capacity now (m³)", f"{S_t:.1f}")
        c4.metric("Intercepted so far (m³)", f"{intercepted_m3:.1f}")

# ---------- Simulation prep ----------
minutes = int(duration_min)
rain_series_mm = make_hyetograph(total_rain_mm, minutes, rain_shape, randiness)

# Initial (dry) frame so there’s always something on screen
show_metrics(0.0, 0.0, S_t, 0.0)
draw_frame(figure_ph, 0, 0.0 if S_t == 0 else 0.0, 0.0, 0.0, minutes)
caption_ph.caption(
    "Picture-only dashboard: time-stepped rain drives SCS runoff minute-by-minute; the mound soaks it until capacity is filled."
)

# ---------- Simulation loop (re-runs when run_id bumps) ----------
# This loop renders to placeholders each iteration—so it SHOWS.
current_run = st.session_state.run_id  # capture id at start of run
if current_run > 0:
    cumP = 0.0
    cum_runoff_m3 = 0.0
    intercepted_m3 = 0.0
    filled_out = False

    for i in range(minutes):
        # If user pressed the button again mid-run, stop this loop (new run will start)
        if st.session_state.run_id != current_run:
            break

        dP = float(rain_series_mm[i])
        prevP = cumP
        cumP += dP

        Q_prev = scs_runoff_mm(prevP, CN)
        Q_curr = scs_runoff_mm(cumP, CN)
        dQ = max(Q_curr - Q_prev, 0.0)

        dV = (dQ / 1000.0) * A
        cum_runoff_m3 += dV

        if not filled_out and S_t > 0:
            free_cap = max(S_t - intercepted_m3, 0.0)
            take = min(free_cap, dV)
            intercepted_m3 += take
            filled_out = intercepted_m3 >= S_t - 1e-9

        fill_ratio = 0.0 if S_t == 0 else min(intercepted_m3 / S_t, 1.0)
        show_metrics(cumP, cum_runoff_m3, S_t, intercepted_m3)
        draw_frame(figure_ph, i, fill_ratio, intercepted_m3, cum_runoff_m3, minutes)

        time.sleep(ms_per_frame / 1000.0)



