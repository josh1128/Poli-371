# hugelkultur_viz_app.py
# Dynamic Hügelkultur schematic with REAL-TIME rain animation (everything moves).
# - Falling drops with wind drift
# - Minute-by-minute storm hyetograph (steady / burst / pulsed)
# - Rising water fill as mound intercepts runoff (SCS-CN)
# - Pulsing infiltration arrows
# - Live metrics
#
# Tips:
#  - If you change controls, press "Start / Replay" to re-run the animation.
#  - Animation uses st.empty() placeholders + session_state to render every frame.

import math, time, random
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# ----------------------- Page Setup -----------------------
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

# session state for animation lifecycle
if "run_id" not in st.session_state: st.session_state.run_id = 0
if "paused" not in st.session_state: st.session_state.paused = False

# ----------------------- Sidebar --------------------------
st.sidebar.header("Rainfall & Catchment")
total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 300, 100, 5)
duration_min  = st.sidebar.slider("Storm duration (minutes)", 5, 240, 60, 5)
rain_shape    = st.sidebar.selectbox("Rain shape", ["Steady", "Front-loaded burst", "Back-loaded burst", "Pulsed"])
randomness    = st.sidebar.slider("Intensity randomness", 0.0, 1.0, 0.15, 0.05,
                                  help="Natural variability in minute-by-minute intensity.")
A  = st.sidebar.number_input("Contributing area (m²)", min_value=10.0, value=300.0, step=10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1, help="Higher CN ⇒ more runoff (e.g., compacted/roadside).")

st.sidebar.header("Mound: Size & Sponge")
L = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
W0 = st.sidebar.number_input("Initial base width (m)", 0.5, 10.0, 2.0, 0.5)
H0 = st.sidebar.number_input("Initial height (m)", 0.3, 3.0, 1.5, 0.1)
phi0 = st.sidebar.slider("Wood/organic core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Aging (Shrink/Settling)")
half_life = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
extra_settle_5y = st.sidebar.slider("Extra settling (first 5y, %)", 0, 50, 15, 5)
year_t = st.sidebar.slider("Year", 0, 20, 0, 1)

st.sidebar.header("Animation")
fps = st.sidebar.slider("Frames per second", 5, 60, 24, 1)
drop_density = st.sidebar.slider("Raindrop density", 5, 80, 28, 1)
wind = st.sidebar.slider("Wind drift (left↔right)", -0.6, 0.6, 0.15, 0.05)
show_drops = st.sidebar.checkbox("Show 💧 raindrops", True)
show_arrows = st.sidebar.checkbox("Show infiltration arrows", True, help="Arrows gently pulse to indicate infiltration.")
def _start(): st.session_state.run_id += 1; st.session_state.paused = False
def _pause(): st.session_state.paused = True
def _resume(): st.session_state.paused = False
st.sidebar.button("▶️ Start / Replay", on_click=_start)
st.sidebar.button("⏸️ Pause", on_click=_pause)
st.sidebar.button("⏯️ Resume", on_click=_resume)

# ----------------------- Hydrology helpers ----------------
def scs_runoff_mm(P_mm, CN):
    S = (25400 / CN) - 254  # mm
    Ia = 0.2 * S
    if P_mm <= Ia: return 0.0
    return max(((P_mm - Ia)**2) / (P_mm - Ia + S), 0.0)

def initial_storage_m3(L, W, H, phi):
    return 0.5 * W * H * L * phi  # triangular cross-section * length * porosity

def storage_at_year(S0, half_life, t_years, extra_settle_pct_5y):
    lam = math.log(2) / half_life
    decay = S0 * math.exp(-lam * t_years)
    frac = extra_settle_pct_5y / 100.0
    extra = (frac * S0) * (t_years/5.0) if t_years <= 5 else (frac * S0)
    return max(decay - extra, 0.0)

def hyetograph(total_mm, minutes, shape="Steady", jitter=0.0, pulses=5):
    t = np.linspace(0, 1, minutes)
    if shape == "Steady":
        base = np.ones_like(t)
    elif shape == "Front-loaded burst":
        base = (1 - t)**2.2 + 0.2
    elif shape == "Back-loaded burst":
        base = t**2.2 + 0.2
    elif shape == "Pulsed":
        base = 0.35 + np.zeros_like(t)
        for k in range(1, pulses+1):
            base += 0.45 * np.maximum(0, np.sin(np.pi * (k*t)))
    else:
        base = np.ones_like(t)
    base = np.clip(base, 0.05, None)
    base = base / base.sum()
    series = base * total_mm
    if jitter := float(jitter):
        noise = np.random.normal(0, jitter, size=minutes)
        series = np.clip(series * (1 + noise), 0, None)
        series *= total_mm / max(series.sum(), 1e-9)
    return series  # mm per minute

# ----------------------- Capacity (now) -------------------
S0 = initial_storage_m3(L, W0, H0, phi0)
S_t = storage_at_year(S0, half_life, year_t, extra_settle_5y)
cap_ratio = S_t / S0 if S0 > 0 else 0.0
H_t = max(0.2, H0 * cap_ratio**0.8)                 # height shrinks more
W_t = max(0.4, W0 * (0.8 + 0.2 * cap_ratio))        # width shrinks less

# ----------------------- Placeholders ---------------------
metrics_ph  = st.empty()
title_ph    = st.empty()
fig_ph      = st.empty()
footer_ph   = st.empty()

# ----------------------- Drawing --------------------------
def draw_frame(min_i, fill_ratio, cumP, cum_runoff_m3, intercepted_m3, minutes,
               drops_xy, arrow_phase):
    title_ph.subheader("Schematic (Not to Scale)")
    fig, ax = plt.subplots(figsize=(11, 3.9))

    # Ground line
    ax.plot([0, 10], [2, 2], linewidth=6, color="#8b4513")

    # Mound geometry
    cx = 5.0
    left = cx - W_t/2
    right = cx + W_t/2
    peak_y = 2 + H_t

    # Outer mound
    ax.fill([left, cx, right], [2, peak_y, 2], color="#cd853f", alpha=0.65)

    # Inner core
    inset = 0.12 * W_t
    left_in, right_in = left + inset, right - inset
    peak_in_y = 2 + H_t * 0.7
    ax.fill([left_in, cx, right_in], [2, peak_in_y, 2], color="#8b5a2b", alpha=0.35)

    # Water fill (rises over time)
    if fill_ratio > 0:
        water_top = 2 + (peak_in_y - 2) * min(fill_ratio, 1.0)
        slope_L = (peak_in_y - 2) / max(cx - left_in, 1e-9)
        slope_R = (peak_in_y - 2) / max(right_in - cx, 1e-9)
        xL = left_in + (water_top - 2) / slope_L
        xR = right_in - (water_top - 2) / slope_R
        ax.fill([xL, xR, right_in, left_in], [water_top, water_top, 2, 2], color="#1e90ff", alpha=0.55)

    # Falling raindrops
    if show_drops:
        for (x, y) in drops_xy:
            ax.text(x, y, "💧", ha="center", va="center", fontsize=12)

    # Pulsing infiltration arrows
    if show_arrows:
        n_ar = 3
        ys = 2 + H_t*(0.55 + 0.18*np.sin(arrow_phase))  # tip oscillation
        for x in np.linspace(left+0.15, right-0.15, n_ar):
            ax.annotate("", xy=(x, 2.12), xytext=(x, ys),
                        arrowprops=dict(arrowstyle="-|>", lw=2))

    # Labels
    ax.text(cx, peak_y + 0.18, "mulch + soil", ha="center", fontsize=10)
    ax.text(cx, 2 + H_t*0.42, "wood/organic core\n('sponge')", ha="center", fontsize=10)

    # HUD
    ax.text(0.8, 5.4, f"Year: {year_t}", fontsize=10)
    ax.text(0.8, 5.0, f"Capacity now: {S_t:.1f} m³", fontsize=10)
    ax.text(0.8, 4.6, f"Intercepted: {intercepted_m3:.1f} m³", fontsize=10)
    ax.text(0.8, 4.2, f"Runoff: {cum_runoff_m3:.1f} m³", fontsize=10)
    ax.text(0.8, 3.8, f"Minute {min_i+1} / {minutes}", fontsize=10)

    ax.set_xlim(0, 10)
    ax.set_ylim(1.6, 5.9)
    ax.axis("off")
    fig_ph.pyplot(fig)
    plt.close(fig)

def show_metrics(cumP, cum_runoff_m3, intercepted_m3):
    with metrics_ph.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cumulative rain (mm)", f"{cumP:.1f}")
        c2.metric("Runoff volume (m³)", f"{cum_runoff_m3:.1f}")
        c3.metric("Mound capacity (m³)", f"{S_t:.1f}")
        c4.metric("Intercepted (m³)", f"{intercepted_m3:.1f}")

# ----------------------- Drop System ----------------------
class RainField:
    """Simple particle system for falling drops across the scene."""
    def __init__(self, count, wind=0.0):
        self.count = count
        self.wind = wind
        self.reset()

    def reset(self):
        self.x = np.random.uniform(1.0, 9.0, self.count)
        self.y = np.random.uniform(5.6, 6.3, self.count)
        self.v = np.random.uniform(0.04, 0.09, self.count)  # fall per frame

    def step(self):
        # update positions
        self.y -= self.v
        self.x += self.wind * 0.02 + np.random.normal(0, 0.005, self.count)
        # recycle drops that hit the ground
        mask = self.y < 2.05
        self.y[mask] = np.random.uniform(5.6, 6.2, mask.sum())
        self.x[mask] = np.random.uniform(1.0, 9.0, mask.sum())
        # clamp horizon
        self.x = np.clip(self.x, 0.7, 9.3)
        return list(zip(self.x, self.y))

# ----------------------- Initial static frame -------------
minutes = int(duration_min)
series = hyetograph(total_rain_mm, minutes, rain_shape, randomness)
show_metrics(0.0, 0.0, 0.0)
draw_frame(0, 0.0, 0.0, 0.0, 0.0, minutes, [], 0.0)
footer_ph.caption("Press ▶️ Start / Replay to animate. The mound fills as rain produces runoff; arrows pulse to show infiltration.")

# ----------------------- Animation Loop -------------------
current_run = st.session_state.run_id
if current_run > 0:
    # Hydrology state
    cumP = 0.0
    cum_runoff_m3 = 0.0
    intercepted_m3 = 0.0
    filled_out = False

    # visuals
    rf = RainField(drop_density, wind=wind)
    arrow_phase = 0.0
    frame_dt = 1.0 / fps

    for i in range(minutes):
        if st.session_state.run_id != current_run:  # interrupted by new Start
            break

        # Allow pause/resume
        while st.session_state.paused and st.session_state.run_id == current_run:
            time.sleep(0.05)

        # Minute hydrology increment
        dP = float(series[i])
        Q_prev = scs_runoff_mm(cumP, CN)
        cumP += dP
        Q_curr = scs_runoff_mm(cumP, CN)
        dQ = max(Q_curr - Q_prev, 0.0)             # mm this minute to runoff
        dV = (dQ / 1000.0) * A                      # m³ this minute
        cum_runoff_m3 += dV

        if not filled_out and S_t > 0:
            take = min(max(S_t - intercepted_m3, 0.0), dV)
            intercepted_m3 += take
            filled_out = intercepted_m3 >= S_t - 1e-9

        # animate sub-frames inside each "minute" so things move smoothly
        subframes = max(1, int(fps * 0.6))  # ~0.6s per minute for visual pacing
        for _ in range(subframes):
            if st.session_state.run_id != current_run or st.session_state.paused:
                break
            drops = rf.step()
            arrow_phase += 0.25
            fill_ratio = 0.0 if S_t == 0 else min(intercepted_m3 / S_t, 1.0)
            show_metrics(cumP, cum_runoff_m3, intercepted_m3)
            draw_frame(i, fill_ratio, cumP, cum_runoff_m3, intercepted_m3, minutes, drops, arrow_phase)
            time.sleep(frame_dt)

# ----------------------- End ------------------------------
