# permeable_pavement_live.py
# Live, time-stepped simulation for permeable pavements with Play / Pause / Step
# - 1-minute timestep water balance
# - Live KPIs, hyetograph, storage gauge, and animated cross-section fill
# - Pavement types: Porous asphalt, Pervious concrete, PICP

import time
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Permeable Pavements – LIVE", layout="wide")
st.title("🧱 Permeable Pavements – Live Simulation")

# -------------------- Presets --------------------
PRESETS = {
    "Porous asphalt":      {"k_mm_hr": 3000.0, "t_cm": 5.0,  "note": "Avoid over-compaction; preserve surface voids."},
    "Pervious concrete":   {"k_mm_hr": 2000.0, "t_cm": 12.0, "note": "Place/finish quickly; do not over-trowel."},
    "PICP (interlocking)": {"k_mm_hr": 1200.0, "t_cm": 8.0,  "note": "Keep joints/joint stone clean; vacuum as needed."},
}

# -------------------- Helpers --------------------
def mm_to_m(x): return x / 1000.0
def cm_to_m(x): return x / 100.0
def L_to_m3(x): return x / 1000.0

def make_hyetograph(total_mm, duration_hr, kind="Constant", peak_at=0.5):
    """Return per-minute intensity array in mm/min that sums to total_mm over duration_hr."""
    n = int(duration_hr * 60)
    if n < 1:
        return np.array([total_mm])  # degenerate
    if kind == "Constant" or n == 1:
        return np.full(n, total_mm / n)
    # Triangular with peak fraction at peak_at
    t = np.linspace(0, 1, n)
    up = t <= peak_at
    down = t > peak_at
    y = np.zeros_like(t)
    if peak_at > 0:
        y[up] = t[up] / peak_at
    if peak_at < 1:
        y[down] = (1 - t[down]) / (1 - peak_at)
    y = np.clip(y, 0, None)
    if y.sum() == 0:
        return np.full(n, total_mm / n)
    y = y / y.sum() * total_mm
    return y

# -------------------- Sidebar (controls) --------------------
st.sidebar.header("Storm & Site")
P_mm   = st.sidebar.slider("Storm depth (mm)", 5, 1400, 80, 5)
T_hr   = st.sidebar.slider("Storm duration (hr)", 0.5, 48.0, 6.0, 0.5)
A_m2   = st.sidebar.number_input("Contributing area (m²)", 10.0, 100000.0, 400.0, 10.0)

st.sidebar.header("Hyetograph")
pattern = st.sidebar.selectbox("Rain pattern", ["Constant", "Triangular"])
peak_pos = st.sidebar.slider("Triangular peak position (0–1)", 0.05, 0.95, 0.5, 0.05) if pattern == "Triangular" else 0.5

st.sidebar.header("Pavement Type & Surface")
ptype  = st.sidebar.selectbox("Pavement type", list(PRESETS.keys()))
preset = PRESETS[ptype]
k_clean = st.sidebar.number_input("Clean surface permeability (mm/hr)", 100.0, 10000.0, float(preset["k_mm_hr"]), 100.0)
clog_pct = st.sidebar.slider("Clogging level (0% clean → 80% clogged)", 0, 80, 10, 5)
surface_t_cm = st.sidebar.number_input("Surface thickness (cm)", 3.0, 50.0, float(preset["t_cm"]), 1.0)

st.sidebar.header("Reservoir Layers")
choker_t_cm = st.sidebar.slider("Choker/bedding thickness (cm)", 2, 5, 3)
base_t_cm   = st.sidebar.slider("Base reservoir thickness (cm)", 5, 25, 10)
sub_t_cm    = st.sidebar.slider("Subbase reservoir thickness (cm)", 10, 60, 25)
base_void   = st.sidebar.slider("Base void ratio (0–0.5)", 0.10, 0.50, 0.30, 0.01)
sub_void    = st.sidebar.slider("Subbase void ratio (0–0.5)", 0.10, 0.50, 0.35, 0.01)

st.sidebar.header("Soils & Underdrain")
soil_ksat = st.sidebar.number_input("Soil Ksat (mm/hr)", 0.5, 200.0, 10.0, 0.5)
use_drain = st.sidebar.checkbox("Include underdrain", value=False)
drain_Lps = st.sidebar.number_input("Underdrain capacity (L/s)", 0.0, 100.0, 2.0, 0.5) if use_drain else 0.0

st.sidebar.header("Losses & Safety")
edge_losses_pct = st.sidebar.slider("Edge/maintenance losses (%)", 0, 20, 5, 1)
storage_sf = st.sidebar.slider("Storage safety factor (0.8–1.2)", 0.8, 1.2, 1.0, 0.05)

st.sidebar.header("Live Controls")
sim_speed = st.sidebar.selectbox("Playback speed", ["Fast", "Normal", "Slow"])
delay = {"Fast": 0.02, "Normal": 0.08, "Slow": 0.15}[sim_speed]

# -------------------- Session State --------------------
if "t_idx" not in st.session_state: st.session_state.t_idx = 0
if "running" not in st.session_state: st.session_state.running = False

cols = st.columns([1,1,1,1])
play   = cols[0].button("▶️ Play", use_container_width=True)
pause  = cols[1].button("⏸️ Pause", use_container_width=True)
step   = cols[2].button("⏭️ Step", use_container_width=True)
reset  = cols[3].button("🔄 Reset", use_container_width=True)

if play:  st.session_state.running = True
if pause: st.session_state.running = False
if reset:
    st.session_state.running = False
    st.session_state.t_idx = 0
if step:
    st.session_state.t_idx += 1
    st.session_state.running = False

# -------------------- Precompute series --------------------
n_min = max(1, int(T_hr * 60))
rain_mm_min = make_hyetograph(P_mm, T_hr, pattern, peak_pos)  # length n_min
k_eff_mm_hr = k_clean * (1.0 - clog_pct / 100.0)
k_eff_mm_min = k_eff_mm_hr / 60.0
soil_ksat_mm_min = soil_ksat / 60.0
drain_m3_min = L_to_m3(drain_Lps * 60.0) if (use_drain and drain_Lps > 0) else 0.0

# Volumes (capacities)
storage_m3 = storage_sf * (
    A_m2 * cm_to_m(base_t_cm) * base_void +
    A_m2 * cm_to_m(sub_t_cm)  * sub_void
)

# Containers for time series
rain_in_m3   = np.zeros(n_min)
surf_pass_m3 = np.zeros(n_min)
surf_rej_m3  = np.zeros(n_min)
soil_exf_m3  = np.zeros(n_min)
drain_out_m3 = np.zeros(n_min)
overflow_m3  = np.zeros(n_min)
stored_m3    = np.zeros(n_min)  # instantaneous storage each minute

# Sim state variables
S = 0.0  # current stored volume (m3)
loss_factor = (1.0 - edge_losses_pct/100.0)

# -------------------- Live Areas --------------------
top_l, top_c, top_r = st.columns([1.2,1.4,1.2])

hyetograph_area = top_l.empty()
kpi_area = top_c.empty()
gauge_area = top_r.empty()

cross_col, bars_col = st.columns([1.1, 0.9])
cross_area = cross_col.empty()
bars_area = bars_col.empty()

tips = st.expander("Construction & O&M tips (quick)")
with tips:
    st.markdown(
        f"- Keep fines/mud out during construction; protect layers to prevent clogging.\n"
        f"- **{ptype}**: {preset['note']}\n"
        f"- Avoid over-compacting subgrade; enable infiltration to native soil.\n"
        f"- Routine sweeping/vacuuming (esp. PICP joints) maintains surface permeability.\n"
        f"- On steeper sites, terrace subgrades and consider underdrains."
    )

# -------------------- Render functions --------------------
def render_hyetograph(t_now):
    fig, ax = plt.subplots(figsize=(4.8, 2.2))
    ax.bar(np.arange(n_min), rain_mm_min, width=1.0)
    ax.axvline(t_now, linestyle="--")
    ax.set_title("Hyetograph (mm/min)")
    ax.set_xlabel("Minute")
    ax.set_ylabel("mm")
    hyetograph_area.pyplot(fig)

def render_kpis(t_now, totals):
    rain_eff = totals["rain_eff"]
    runoff   = totals["runoff"]
    stored   = totals["stored"]
    soilx    = totals["soilx"]
    drain    = totals["drain"]
    c1, c2, c3 = kpi_area.columns(3)
    c1.metric("Rain volume (eff.)", f"{rain_eff:.1f} m³")
    c2.metric("Runoff / Overflow", f"{runoff:.1f} m³")
    c3.metric("Stored (current)", f"{stored:.1f} m³")
    c4, c5, c6 = kpi_area.columns(3)
    c4.metric("Exfiltrated to soil", f"{soilx:.1f} m³")
    c5.metric("Underdrain outflow", f"{drain:.1f} m³")
    c6.metric("Surface k (eff.)", f"{k_eff_mm_hr:.0f} mm/hr")

def render_gauge(S_now):
    fig, ax = plt.subplots(figsize=(4.4, 2.2))
    cap = max(1e-6, storage_m3)
    frac = min(1.0, S_now / cap)
    ax.barh([0], [cap], height=0.5, edgecolor="black", fill=False)
    ax.barh([0], [S_now], height=0.5)
    ax.set_xlim(0, cap)
    ax.set_yticks([])
    ax.set_xlabel("Storage (m³)")
    ax.set_title(f"Reservoir fill: {S_now:.1f}/{cap:.1f} m³ ({frac*100:.0f}%)")
    gauge_area.pyplot(fig)

def render_cross_section(S_now):
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

    surf_h = surface_t_cm
    chok_h = choker_t_cm
    base_h = base_t_cm
    sub_h  = sub_t_cm
    total  = surf_h + chok_h + base_h + sub_h
    nh = lambda x: x / total

    y = 0.0
    layers = [
        ("Subbase reservoir", sub_h, (0.85, 0.92, 1.00), f"Void≈{sub_void:.2f}", "sub"),
        ("Base reservoir",    base_h, (0.80, 0.87, 0.98), f"Void≈{base_void:.2f}", "base"),
        ("Choker/Bedding",    chok_h, (0.92, 0.92, 0.92), "Uniform stone",        "none"),
        (ptype,               surf_h, (0.75, 0.75, 0.75), f"k≈{k_eff_mm_hr:.0f} mm/hr", "none"),
    ]

    # Draw layers
    for name, h_cm, color, note, key in layers:
        h = nh(h_cm)
        ax.add_patch(plt.Rectangle((0.1, y), 0.8, h, facecolor=color, edgecolor="black"))
        ax.text(0.5, y + h/2, f"{name}\n{h_cm:.0f} cm\n{note}", ha="center", va="center", fontsize=9)
        y += h

    # Draw water fill within reservoirs (stack base then subbase)
    cap_base = A_m2 * cm_to_m(base_t_cm) * base_void
    cap_sub  = A_m2 * cm_to_m(sub_t_cm)  * sub_void
    # Scale by safety factor (filled volume respects real cap, but gauge shows sf-adjusted)
    cap_base *= storage_sf
    cap_sub  *= storage_sf

    remaining = S_now
    # Fill base first
    if cap_base > 0:
        fill_base = min(remaining, cap_base); remaining -= fill_base
    else:
        fill_base = 0
    if cap_sub > 0:
        fill_sub  = min(remaining, cap_sub);  remaining -= fill_sub
    else:
        fill_sub = 0

    # Convert to normalized heights proportional to layer height
    # (visual only; not exact porosity mapping)
    y0_sub = 0.0
    h_sub = nh(sub_t_cm)
    y0_base = y0_sub + h_sub
    h_base  = nh(base_t_cm)

    def draw_fill(y0, h, frac):
        if frac <= 0: return
        ax.add_patch(plt.Rectangle((0.1, y0), 0.8, h*frac, facecolor=(0.5,0.7,1.0,0.6), edgecolor=None))

    frac_base = 0.0 if cap_base == 0 else (fill_base / cap_base)
    frac_sub  = 0.0 if cap_sub  == 0 else (fill_sub  / cap_sub)
    draw_fill(y0_sub,  h_sub,  frac_sub)
    draw_fill(y0_base, h_base, frac_base)

    if use_drain and drain_Lps > 0:
        ax.plot([0.15, 0.85], [0.05, 0.05], lw=6)
        ax.text(0.5, 0.02, f"Underdrain (~{drain_Lps:.1f} L/s)", ha="center", va="bottom", fontsize=9)

    ax.text(0.5, -0.02, f"Soil (Ksat≈{soil_ksat:.1f} mm/hr)", ha="center", va="top", fontsize=10)

    cross_area.pyplot(fig)

def render_bars(t_now):
    labels = ["Runoff", "Stored (curr.)", "Soil Exfiltration", "Underdrain"]
    v_runoff = overflow_m3[:t_now+1].sum() + surf_rej_m3[:t_now+1].sum()
    v_store  = stored_m3[t_now]
    v_soil   = soil_exf_m3[:t_now+1].sum()
    v_drain  = drain_out_m3[:t_now+1].sum()

    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    vals = [v_runoff, v_store, v_soil, v_drain]
    ax.bar(labels, vals)
    ax.set_ylabel("Volume (m³)")
    ax.set_title("Where has the stormwater gone so far?")
    vmax = max(vals) if max(vals) > 0 else 1.0
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02*vmax, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    bars_area.pyplot(fig)

# -------------------- Simulation Runner --------------------
def simulate_until(t_stop_idx):
    global S
    for t in range(st.session_state.t_idx, min(t_stop_idx+1, n_min)):
        # Minute rainfall (effective after minor edge losses)
        r_mm = rain_mm_min[t]
        rain_in_m3[t] = mm_to_m(r_mm) * A_m2 * loss_factor

        # Surface pass limited by k_eff
        surf_cap_m3_min = mm_to_m(k_eff_mm_min) * A_m2
        pass_m3 = min(rain_in_m3[t], surf_cap_m3_min)
        rej_m3  = max(0.0, rain_in_m3[t] - pass_m3)

        # At reservoir this minute:
        soil_m3 = mm_to_m(soil_ksat_mm_min) * A_m2
        drain_m3_now = drain_m3_min
        available_storage = max(0.0, storage_m3 - S)

        # Water that needs handling now:
        need = pass_m3

        # First: soil exfil + drain (limited by available water)
        to_soil  = min(need, soil_m3); need -= to_soil
        to_drain = min(need, drain_m3_now); need -= to_drain

        # Then: storage
        to_store = min(need, available_storage); need -= to_store

        # Anything left is overflow
        to_over = max(0.0, need)

        # Update state and series
        S = max(0.0, min(storage_m3, S + to_store))
        surf_pass_m3[t] = pass_m3
        surf_rej_m3[t]  = rej_m3
        soil_exf_m3[t]  = to_soil
        drain_out_m3[t] = to_drain
        overflow_m3[t]  = to_over
        stored_m3[t]    = S

        st.session_state.t_idx = t

# -------------------- Main Live Loop --------------------
def totals_up_to(t_now):
    return {
        "rain_eff": rain_in_m3[:t_now+1].sum(),
        "runoff":   overflow_m3[:t_now+1].sum() + surf_rej_m3[:t_now+1].sum(),
        "stored":   stored_m3[t_now],
        "soilx":    soil_exf_m3[:t_now+1].sum(),
        "drain":    drain_out_m3[:t_now+1].sum(),
    }

# Always render initial plots for current index
t_now = min(st.session_state.t_idx, n_min-1)
render_hyetograph(t_now)
render_kpis(t_now, totals_up_to(t_now))
render_gauge(stored_m3[t_now] if t_now < n_min else stored_m3[-1])
render_cross_section(stored_m3[t_now] if t_now < n_min else stored_m3[-1])
render_bars(t_now)

# If running, advance with delay and re-render progressively
if st.session_state.running:
    # Simulate a few minutes per rerun to feel smooth but responsive
    step_chunk = 2 if sim_speed == "Fast" else 1
    target = min(n_min-1, t_now + step_chunk)
    simulate_until(target)
    time.sleep(delay)
    st.rerun()

# Manual step (already applied earlier), re-render after step as well
