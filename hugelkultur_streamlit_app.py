# rain_env_live.py
# A live, interactive "environment" that simulates rainfall, flow, infiltration & storage
# across a small hilly site with multiple pavement types you can paint onto the map.
#
# - 2D heightmap terrain (hills like Kigali's topography, synthetic but realistic)
# - Per-cell pavement type: Impervious, Porous Asphalt, Pervious Concrete, PICP, Soil
# - Each permeable pavement has surface k (mm/hr) + reservoir storage (m) + soil Ksat (mm/hr)
# - Minute-by-minute rain (constant/triangular), Play/Pause/Step
# - Overland flow: slope-driven diffusion with downhill bias
# - Live maps: water depth, flow velocity magnitude, pavement layout, storage fill
# - Paint tools to "draw" real pavements into the environment

import time
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

# ---------------------------- UI Setup ----------------------------
st.set_page_config(page_title="Live Rain & Pavements Environment", layout="wide")
st.title("🌧️ Live Rain & Permeable Pavements – Mini Environment")

# ---------------------------- Helpers -----------------------------
def mm_to_m(x): return x / 1000.0
def L_to_m3(x): return x / 1000.0
def clamp(x, lo, hi): return max(lo, min(hi, x))

def make_hyetograph(total_mm, duration_hr, kind="Constant", peak_at=0.5):
    n = max(1, int(duration_hr * 60))
    if kind == "Constant" or n == 1:
        return np.full(n, total_mm / n)
    t = np.linspace(0, 1, n)
    y = np.zeros_like(t)
    up = t <= peak_at
    dn = t > peak_at
    if peak_at > 0: y[up] = t[up] / peak_at
    if peak_at < 1: y[dn] = (1 - t[dn]) / (1 - peak_at)
    y = np.clip(y, 0, None)
    y = y / y.sum() * total_mm if y.sum() > 0 else np.full(n, total_mm/n)
    return y

# ---------------------------- Sidebar -----------------------------
st.sidebar.header("Environment")
nx = st.sidebar.slider("Grid size (nx=ny)", 40, 120, 80, 10)
cell_m = st.sidebar.slider("Cell size (m)", 1, 5, 2, 1)  # each cell width/height in meters
area_m2 = (nx * cell_m) * (nx * cell_m)

st.sidebar.header("Storm")
P_mm = st.sidebar.slider("Storm depth (mm)", 5, 1400, 80, 5)
T_hr = st.sidebar.slider("Duration (hr)", 0.5, 24.0, 3.0, 0.5)
pattern = st.sidebar.selectbox("Pattern", ["Constant", "Triangular"])
peak_pos = st.sidebar.slider("Triangular peak position", 0.05, 0.95, 0.4, 0.05) if pattern == "Triangular" else 0.5

st.sidebar.header("Soils")
soil_ksat_mm_hr = st.sidebar.slider("Soil Ksat (mm/hr)", 0.5, 150.0, 10.0, 0.5)

st.sidebar.header("Flow Physics")
mann_n = st.sidebar.slider("Overland roughness (Manning n)", 0.01, 0.20, 0.05, 0.01)
dt_scale = st.sidebar.slider("Flow time-step scale (stability)", 0.1, 2.0, 1.0, 0.1)

st.sidebar.header("Playback")
speed = st.sidebar.selectbox("Playback speed", ["Fast", "Normal", "Slow"])
delay = {"Fast": 0.01, "Normal": 0.05, "Slow": 0.12}[speed]

# ------------------------- Pavement Catalog -----------------------
# Parameters per pavement type:
# - surf_k_mm_hr: surface permeability (limits per-minute pass-through)
# - res_storage_m: thickness of reservoir * void (effective storage depth, meters of water per cell area)
# - label/color
PAVES = {
    0: {"name":"Soil",            "surf_k_mm_hr": soil_ksat_mm_hr, "res_storage_m": 0.00, "color": (0.85, 1.00, 0.85)},
    1: {"name":"Impervious",      "surf_k_mm_hr": 0.0,             "res_storage_m": 0.00, "color": (0.80, 0.80, 0.80)},
    2: {"name":"Porous Asphalt",  "surf_k_mm_hr": 3000.0,          "res_storage_m": 0.10, "color": (0.50, 0.50, 0.60)},
    3: {"name":"Pervious Conc.",  "surf_k_mm_hr": 2000.0,          "res_storage_m": 0.12, "color": (0.70, 0.70, 0.80)},
    4: {"name":"PICP",            "surf_k_mm_hr": 1200.0,          "res_storage_m": 0.15, "color": (0.60, 0.65, 0.75)},
}
# Note: res_storage_m is an "effective water depth" that can be held in the base/subbase (area-normalized).

st.sidebar.header("Paint Pavements")
paint_type = st.sidebar.selectbox("Brush type", [f"{k}: {v['name']}" for k,v in PAVES.items()], index=3)
brush = st.sidebar.slider("Brush radius (cells)", 1, 8, 4, 1)

st.sidebar.header("Clogging")
clog_pct = st.sidebar.slider("Surface clogging (0–80%)", 0, 80, 10, 5)

# ---------------------- Session State ----------------------------
if "terrain" not in st.session_state or st.session_state.get("nx") != nx:
    # Synthetic hills: sum of sinusoids + Gaussian bump → "Rwanda-like" rolling site
    x = np.linspace(0, 2*np.pi, nx)
    y = np.linspace(0, 2*np.pi, nx)
    X, Y = np.meshgrid(x, y, indexing="ij")
    Z = 0.8*np.sin(1.0*X) + 0.6*np.sin(1.3*Y + 0.7) + 0.4*np.sin(0.7*X + 1.1*Y)
    # add a hill
    cx, cy = int(nx*0.65), int(nx*0.35)
    r2 = (np.arange(nx)[:,None]-cx)**2 + (np.arange(nx)[None,:]-cy)**2
    Z += 1.5*np.exp(-r2/(2*(0.15*nx)**2))
    Z = (Z - Z.min())/(Z.max()-Z.min())  # normalize 0..1
    st.session_state.terrain = Z
    st.session_state.nx = nx

    # Pavement layout (ints 0..4). Start with "impervious road" across center + soil elsewhere.
    pave = np.zeros((nx, nx), dtype=np.int32)  # soil
    pave[nx//2-2:nx//2+2, :] = 1  # a 4-cell-wide road
    # seed a pervious shoulder
    pave[nx//2+2:nx//2+4, int(nx*0.15):int(nx*0.85)] = 2
    st.session_state.pave = pave

    # State arrays
    st.session_state.h = np.zeros((nx, nx), dtype=np.float64)  # water depth on surface (m)
    st.session_state.s = np.zeros((nx, nx), dtype=np.float64)  # stored in reservoir (m water equiv.)
    st.session_state.t_idx = 0
    st.session_state.running = False

# hyetograph
rain_mm_min = make_hyetograph(P_mm, T_hr, pattern, peak_pos)
n_min = len(rain_mm_min)
nx = st.session_state.nx
Z  = st.session_state.terrain
pave = st.session_state.pave
h = st.session_state.h       # surface water depth (m)
s_store = st.session_state.s # reservoir storage (m water)

# Effective surface permeability after clogging
def k_eff_for(cell_code):
    k = PAVES[int(cell_code)]["surf_k_mm_hr"]
    return k * (1.0 - clog_pct/100.0)

k_eff_map_mm_hr = np.vectorize(k_eff_for)(pave)
k_eff_map_m_min = mm_to_m(k_eff_map_mm_hr)/60.0
soil_ksat_m_min = mm_to_m(soil_ksat_mm_hr)/60.0

# Reservoir capacity (m water) per cell
res_cap_m = np.zeros_like(s_store)
for code, props in PAVES.items():
    res_cap_m[pave==code] = props["res_storage_m"]

# ---------------------- Paint Tool ------------------------------
st.caption("Tip: Use the brush to paint pavements, then press ▶️ Play.")

with st.form("paint"):
    st.write("Click anywhere on the map preview to record a center coordinate, then apply brush.")
    click_x = st.number_input("Center X (0..nx-1)", min_value=0, max_value=nx-1, value=nx//2, step=1)
    click_y = st.number_input("Center Y (0..nx-1)", min_value=0, max_value=nx-1, value=nx//2, step=1)
    apply = st.form_submit_button("Apply Brush")
if apply:
    code = int(paint_type.split(":")[0])
    rr = brush
    x0, y0 = int(click_x), int(click_y)
    xs = slice(clamp(x0-rr, 0, nx-1), clamp(x0+rr+1, 0, nx))
    ys = slice(clamp(y0-rr, 0, nx-1), clamp(y0+rr+1, 0, nx))
    patch = np.indices((xs.stop-xs.start, ys.stop-ys.start))
    mask = (patch[0]-(x0-xs.start))**2 + (patch[1]-(y0-ys.start))**2 <= rr**2
    pave_view = st.session_state.pave[xs, ys]
    pave_view[mask] = code
    st.session_state.pave[xs, ys] = pave_view
    # refresh derived fields
    pave = st.session_state.pave
    k_eff_map_mm_hr = np.vectorize(k_eff_for)(pave)
    k_eff_map_m_min = mm_to_m(k_eff_map_mm_hr)/60.0
    for c, props in PAVES.items():
        res_cap_m[pave==c] = props["res_storage_m"]

# ---------------------- Controls -------------------------------
c1, c2, c3, c4 = st.columns(4)
if c1.button("▶️ Play", use_container_width=True): st.session_state.running = True
if c2.button("⏸️ Pause", use_container_width=True): st.session_state.running = False
if c3.button("⏭️ Step", use_container_width=True):
    st.session_state.t_idx = min(st.session_state.t_idx + 1, n_min-1)
    st.session_state.running = False
if c4.button("🔄 Reset", use_container_width=True):
    st.session_state.running = False
    st.session_state.t_idx = 0
    st.session_state.h.fill(0.0)
    st.session_state.s.fill(0.0)

# ---------------------- Physics -------------------------------
# Precompute terrain slopes (central differences)
dx = cell_m
dy = cell_m
dZdx = np.zeros_like(Z)
dZdy = np.zeros_like(Z)
dZdx[1:-1,:] = (Z[2:,:] - Z[:-2,:])/(2*dx)
dZdy[:,1:-1] = (Z[:,2:] - Z[:,:-2])/(2*dy)

def step_once(t):
    """Advance one minute: rain → surface pass → storage/soil → overland flow."""
    global h, s_store

    # 1) Rainfall arrives (mm/min -> m)
    rain_m = mm_to_m(rain_mm_min[t])

    # 2) Surface pass capacity (m/min) by pavement
    surf_cap_m = k_eff_map_m_min

    # water that can pass into system this minute (per cell area)
    pass_m = np.minimum(rain_m, surf_cap_m)  # into reservoir/soil
    reject_m = np.maximum(0.0, rain_m - pass_m)  # immediate surface addition

    # add rejected rain to surface water
    h = h + reject_m

    # 3) Handle pass_m: first soil exfiltration (soil Ksat), then reservoir storage
    soil_take = np.minimum(pass_m, soil_ksat_m_min)
    remain = pass_m - soil_take

    # storage space left
    space = np.maximum(0.0, res_cap_m - s_store)
    to_store = np.minimum(remain, space)
    overflow_from_store = np.maximum(0.0, remain - space)  # becomes surface water
    s_store = s_store + to_store
    h = h + overflow_from_store

    # 4) Overland flow (very simple shallow-water like diffusion with slope bias)
    # Compute water surface elevation = terrain + water depth
    eta = Z + h
    # Gradients of eta drive flow
    deta_dx = np.zeros_like(eta)
    deta_dy = np.zeros_like(eta)
    deta_dx[1:-1,:] = (eta[2:,:] - eta[:-2,:])/(2*dx)
    deta_dy[:,1:-1] = (eta[:,2:] - eta[:,:-2])/(2*dy)

    # Velocity magnitude proxy using Manning (very simplified)
    # v ~ (h^(2/3)/n) * sqrt(slope) ; use |grad(eta)| as slope proxy
    slope_mag = np.sqrt(deta_dx**2 + deta_dy**2) + 1e-9
    v = (np.power(np.maximum(h,0.0), 2.0/3.0) / mann_n) * np.sqrt(slope_mag)

    # Fluxes (discretized, stability via dt_scale)
    # Move fraction of water down gradient
    dt = dt_scale * 60.0  # seconds per step (scaled; display is still per-minute rain)
    # Simple upwind: compute fractional outflow per neighbor directions
    # Normalize gradient components to unit vector
    ux = -deta_dx / (slope_mag)
    uy = -deta_dy / (slope_mag)

    # Outflow per cell (m depth) ~ coef * v; keep small for stability
    coef = 0.15 * dt / max(dx, dy)
    out = coef * v
    out = np.minimum(out, h)  # cannot send more than available

    # Distribute outflow to 4-neighborhood based on direction cosines
    # weights to (i+1,j) (east), (i-1,j) (west), (i,j+1) (north), (i,j-1) (south)
    wx_e = np.maximum(0.0, ux); wx_w = np.maximum(0.0, -ux)
    wy_n = np.maximum(0.0, uy); wy_s = np.maximum(0.0, -uy)
    wsum = wx_e + wx_w + wy_n + wy_s + 1e-12
    fx_e = out * (wx_e/wsum); fx_w = out * (wx_w/wsum)
    fy_n = out * (wy_n/wsum); fy_s = out * (wy_s/wsum)

    # Apply fluxes
    h_next = h.copy()
    # east/west
    h_next[:, :-1] -= fx_e[:, :-1]; h_next[:, 1:] += fx_e[:, :-1]
    h_next[:, 1:]  -= fx_w[:, 1:];  h_next[:, :-1]+= fx_w[:, 1:]
    # north/south
    h_next[:-1, :] -= fy_n[:-1, :]; h_next[1:, :]  += fy_n[:-1, :]
    h_next[1:,  :] -= fy_s[1:,  :]; h_next[:-1, :]+= fy_s[1:,  :]

    # Small evaporation/drainage from surface where permeable (optional realism)
    evap = 0.0
    h = np.maximum(0.0, h_next - evap)

# ---------------------- Live Displays ---------------------------
top_l, top_c, top_r = st.columns([1.1,1.1,0.8])
map_area = top_l.empty()
flow_area = top_c.empty()
legend_area = top_r.empty()

bot_l, bot_c, bot_r = st.columns([1.0,1.0,1.0])
pave_area = bot_l.empty()
storage_area = bot_c.empty()
kpi_area = bot_r.empty()

def render_maps(t_now):
    # Surface water depth
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    im = ax.imshow(h, origin="lower", cmap="Blues")
    ax.set_title(f"Surface Water Depth (m) — minute {t_now+1}/{n_min}")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    map_area.pyplot(fig)

    # Flow velocity proxy
    eta = Z + h
    deta_dx = np.zeros_like(eta); deta_dy = np.zeros_like(eta)
    deta_dx[1:-1,:] = (eta[2:,:] - eta[:-2,:])/(2*dx)
    deta_dy[:,1:-1] = (eta[:,2:] - eta[:,:-2])/(2*dy)
    slope_mag = np.sqrt(deta_dx**2 + deta_dy**2) + 1e-9
    v = (np.power(np.maximum(h,0.0), 2.0/3.0) / mann_n) * np.sqrt(slope_mag)

    fig2, ax2 = plt.subplots(figsize=(5.2, 5.2))
    im2 = ax2.imshow(v, origin="lower", cmap="magma")
    ax2.set_title("Flow Speed (relative units)")
    plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    flow_area.pyplot(fig2)

    # Legend – pavement colors
    figl, axl = plt.subplots(figsize=(4.4, 3.2))
    axl.axis("off")
    y0 = 0.9
    for k, props in PAVES.items():
        axl.add_patch(plt.Rectangle((0.05, y0-0.06), 0.1, 0.05, color=props["color"]))
        axl.text(0.17, y0-0.04, f"{k}: {props['name']} (k={props['surf_k_mm_hr']:.0f} mm/hr, store={props['res_storage_m']:.2f} m)", fontsize=9)
        y0 -= 0.14
    axl.set_title("Pavement Legend")
    legend_area.pyplot(figl)

def render_layouts():
    # Pavement layout
    rgb = np.zeros((nx, nx, 3), dtype=float)
    for k, props in PAVES.items():
        rgb[pave==k] = props["color"]
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.imshow(rgb, origin="lower")
    ax.set_title("Pavement Layout (paintable)")
    pave_area.pyplot(fig)

    # Storage fill fraction
    frac = np.where(res_cap_m>0, np.clip(s_store/res_cap_m, 0, 1), 0.0)
    fig2, ax2 = plt.subplots(figsize=(5.2, 5.2))
    im = ax2.imshow(frac, origin="lower", vmin=0, vmax=1, cmap="viridis")
    ax2.set_title("Reservoir Fill (fraction of capacity)")
    plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
    storage_area.pyplot(fig2)

def render_kpis(t_now):
    rain_total_m3 = mm_to_m(rain_mm_min[:t_now+1].sum()) * area_m2
    surface_vol_m3 = h.sum() * (cell_m**2)
    stored_m3 = s_store.sum() * (cell_m**2)

    # Very rough “leaving the system” via soil exfil estimate (we handled implicitly cell-by-cell)
    # We’ll report stored & on-surface as of now.
    kpi_area.metric("Cumulative rain (m³)", f"{rain_total_m3:,.1f}")
    kpi_area.write(
        f"- Surface water now: **{surface_vol_m3:,.1f} m³**  \n"
        f"- Stored in reservoirs now: **{stored_m3:,.1f} m³**  \n"
        f"- Effective surface k reduced by clogging: **{(1-clog_pct/100):.0%}** of clean"
    )

# Initial render
t_now = min(st.session_state.t_idx, n_min-1)
render_maps(t_now)
render_layouts()
render_kpis(t_now)

# Main loop for live mode
if st.session_state.running:
    if t_now < n_min-1:
        st.session_state.t_idx += 1
        step_once(t_now)  # advance from t_now to t_now+1
        time.sleep(delay)
        st.rerun()
    else:
        st.session_state.running = False
