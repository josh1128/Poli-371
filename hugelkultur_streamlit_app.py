# hugelkultur_viz_app.py
# Dynamic Hügelkultur schematic with REALISTIC rain and bottom HUD.
# - Parallax rain layers (far/mid/near) with gravity & wind gusts
# - Impact splashes that fade
# - SCS-CN runoff minute-by-minute; mound fills until capacity
# - HUD (Year/Capacity/Intercepted/Runoff/Minute) at bottom-left
# - Single schematic only (no charts)

import math, time, random
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib import patches

# -------------------- Page setup --------------------
st.set_page_config(page_title="Dynamic Hügelkultur", layout="wide")
st.title("Dynamic Hügelkultur (No Graphs)")

if "run_id" not in st.session_state: st.session_state.run_id = 0
if "paused" not in st.session_state: st.session_state.paused = False

# -------------------- Controls ----------------------
st.sidebar.header("Rainfall & Catchment")
total_rain_mm = st.sidebar.slider("Total storm rain (mm)", 5, 300, 120, 5)
duration_min  = st.sidebar.slider("Storm duration (minutes)", 5, 240, 60, 5)
rain_shape    = st.sidebar.selectbox("Rain shape", ["Steady","Front-loaded burst","Back-loaded burst","Pulsed"])
randiness     = st.sidebar.slider("Intensity randomness", 0.0, 1.0, 0.15, 0.05)
A  = st.sidebar.number_input("Contributing area (m²)", 10.0, 100000.0, 300.0, 10.0)
CN = st.sidebar.slider("Curve Number (CN)", 55, 95, 85, 1)

st.sidebar.header("Mound: Size & Sponge")
L = st.sidebar.number_input("Mound length (m)", 1.0, 50.0, 12.0, 1.0)
W0 = st.sidebar.number_input("Initial base width (m)", 0.5, 10.0, 2.0, 0.5)
H0 = st.sidebar.number_input("Initial height (m)", 0.3, 3.0, 1.5, 0.1)
phi0 = st.sidebar.slider("Wood/organic core porosity", 0.2, 0.9, 0.6, 0.05)

st.sidebar.header("Aging (Shrink/Settling)")
half_life = st.sidebar.slider("Wood volume half-life (years)", 1, 15, 6, 1)
extra_settle_5y = st.sidebar.slider("Extra settling first 5y (%)", 0, 50, 15, 5)
year_t = st.sidebar.slider("Year", 0, 20, 0, 1)

st.sidebar.header("Animation style")
fps = st.sidebar.slider("Frames per second", 10, 60, 30, 1)
rain_intensity = st.sidebar.slider("Visual rain density", 10, 200, 80, 5)
base_wind = st.sidebar.slider("Base wind drift", -0.8, 0.8, 0.15, 0.05)
gustiness = st.sidebar.slider("Wind gustiness", 0.0, 1.0, 0.35, 0.05,
                              help="Higher = stronger, quick-changing gusts")

def _start(): st.session_state.run_id += 1; st.session_state.paused = False
def _pause(): st.session_state.paused = True
def _resume(): st.session_state.paused = False
st.sidebar.button("▶️ Start / Replay", on_click=_start)
st.sidebar.button("⏸️ Pause", on_click=_pause)
st.sidebar.button("⏯️ Resume", on_click=_resume)

# -------------------- Hydro helpers -----------------
def scs_runoff_mm(P_mm, CN):
    S = (25400 / CN) - 254
    Ia = 0.2 * S
    if P_mm <= Ia: return 0.0
    return ((P_mm - Ia)**2) / (P_mm - Ia + S)

def initial_storage_m3(L, W, H, phi):
    return 0.5 * W * H * L * phi  # triangular section * length * porosity

def storage_at_year(S0, half_life, t_years, extra_pct_5y):
    lam = math.log(2)/half_life
    decay = S0 * math.exp(-lam*t_years)
    extra = (extra_pct_5y/100.0)*S0*(t_years/5.0) if t_years<=5 else (extra_pct_5y/100.0)*S0
    return max(decay - extra, 0.0)

def hyetograph(total_mm, minutes, shape="Steady", jitter=0.0, pulses=5):
    t = np.linspace(0,1,minutes)
    if shape=="Steady":
        base = np.ones_like(t)
    elif shape=="Front-loaded burst":
        base = (1-t)**2.2 + 0.2
    elif shape=="Back-loaded burst":
        base = t**2.2 + 0.2
    else:  # Pulsed
        base = 0.35 + np.zeros_like(t)
        for k in range(1, pulses+1):
            base += 0.45*np.maximum(0,np.sin(np.pi*(k*t)))
    base = np.clip(base,0.05,None); base/=base.sum()
    series = base*total_mm
    if jitter>0:
        noise = np.random.normal(0,jitter,minutes)
        series = np.clip(series*(1+noise),0,None)
        series *= total_mm/max(series.sum(),1e-9)
    return series

# -------------------- Capacity now ------------------
S0 = initial_storage_m3(L,W0,H0,phi0)
S_t = storage_at_year(S0,half_life,year_t,extra_settle_5y)
cap_ratio = S_t/S0 if S0>0 else 0.0
H_t = max(0.2, H0*cap_ratio**0.8)
W_t = max(0.4, W0*(0.8+0.2*cap_ratio))

# -------------------- Placeholders -------------------
metrics_ph, title_ph, fig_ph, footer_ph = st.empty(), st.empty(), st.empty(), st.empty()

# -------------------- Realistic rain system ----------
class RainLayer:
    """Parallax layer of slanted rain streaks with gravity & wind."""
    def __init__(self, n, speed_range, length_range, alpha, linew, z_wind=1.0):
        self.n = n
        self.alpha = alpha
        self.linew = linew
        self.z_wind = z_wind
        self.x = np.random.uniform(0.6, 9.4, n)
        self.y = np.random.uniform(5.8, 6.6, n)
        self.v = np.random.uniform(*speed_range, n)  # vertical speed
        self.len = np.random.uniform(*length_range, n)

    def step(self, wind, accel=0.0015):
        self.v += accel  # gravity
        dx = (wind*self.z_wind)*0.06
        self.x += dx + np.random.normal(0, 0.004, self.n)
        self.y -= self.v
        # recycle
        mask = self.y < 2.05
        self.y[mask] = np.random.uniform(5.8, 6.3, mask.sum())
        self.x[mask] = np.random.uniform(0.6, 9.4, mask.sum())
        # streak endpoints (slanted)
        x0 = self.x
        y0 = self.y
        x1 = self.x - (self.len*wind*0.4)
        y1 = self.y + self.len
        return x0,y0,x1,y1,mask

class SplashField:
    """Short-lived splash fans spawned on ground impact."""
    def __init__(self, capacity=400):
        self.capacity = capacity
        self.alive = np.zeros(capacity, dtype=bool)
        self.x = np.zeros(capacity); self.y = np.zeros(capacity)
        self.age = np.zeros(capacity); self.max_age = np.zeros(capacity)
        self.spokes = [None]*capacity  # per splash: (dx0,dy0,dx1,dy1)

    def spawn(self, x, n_spokes=5):
        idx = np.where(~self.alive)[0]
        if len(idx)==0: return
        i = idx[0]
        self.alive[i]=True
        self.x[i]=x; self.y[i]=2.05
        self.age[i]=0.0; self.max_age[i]=random.uniform(8,14)
        angles = np.linspace(np.pi*0.9, np.pi*0.1, n_spokes) + np.random.normal(0,0.05,n_spokes)
        r0 = np.random.uniform(0.02, 0.06, n_spokes)
        r1 = r0 + np.random.uniform(0.03, 0.08, n_spokes)
        self.spokes[i] = np.stack([r0*np.cos(angles), r0*np.sin(angles),
                                   r1*np.cos(angles), r1*np.sin(angles)], axis=1)

    def step(self):
        segs = []; alphas = []
        for i in np.where(self.alive)[0]:
            self.age[i] += 1
            fade = max(0.0, 1.0 - self.age[i]/self.max_age[i])
            if fade <= 0:
                self.alive[i]=False
                continue
            dx0,dy0,dx1,dy1 = self.spokes[i].T
            segs.append((self.x[i]+dx0, self.y[i]+dy0, self.x[i]+dx1, self.y[i]+dy1))
            alphas.append(0.5*fade)
        return segs, alphas

class RainSystem:
    """Three parallax layers + splash field; returns streaks & splashes for drawing."""
    def __init__(self, density, base_wind, gustiness):
        n_far  = max(6, int(density*0.35))
        n_mid  = max(8, int(density*0.45))
        n_near = max(6, int(density*0.30))
        self.layers = [
            RainLayer(n_far,  (0.07, 0.10), (0.10, 0.18), alpha=0.30, linew=1.1, z_wind=0.6),
            RainLayer(n_mid,  (0.09, 0.13), (0.14, 0.22), alpha=0.45, linew=1.3, z_wind=1.0),
            RainLayer(n_near, (0.12, 0.17), (0.18, 0.28), alpha=0.70, linew=1.6, z_wind=1.3),
        ]
        self.splashes = SplashField(capacity=400)
        self.base_wind = base_wind
        self.gustiness = gustiness
        self._gust = 0.0
        self._t = 0

    def _wind_now(self):
        self._t += 1
        # smooth gusts (sine + small random walk)
        self._gust = 0.92*self._gust + 0.08*np.sin(self._t*0.07) + np.random.normal(0,0.01)
        return self.base_wind + self.gustiness*self._gust

    def step(self):
        wind = self._wind_now()
        streaks = []
        for layer in self.layers:
            x0,y0,x1,y1,hits_mask = layer.step(wind)
            if np.any(hits_mask):
                for x in x0[hits_mask]:
                    if 0.9 <= x <= 9.1:
                        self.splashes.spawn(float(x), n_spokes=random.randint(4,6))
            streaks.append((x0,y0,x1,y1, layer.alpha, layer.linew))
        splash_segs, splash_alpha = self.splashes.step()
        return streaks, splash_segs, splash_alpha

# -------------------- Drawing ------------------------
def draw_frame(min_i, fill_ratio, cumP, cum_runoff_m3, intercepted_m3, minutes,
               rain_streaks, splash_segs, splash_alpha):
    title_ph.subheader("Schematic (Not to Scale)")
    fig, ax = plt.subplots(figsize=(11, 4.0))

    # Ground
    ax.plot([0,10],[2,2], linewidth=6, color="#8b4513")

    # Mound geometry
    cx = 5.0
    left = cx - W_t/2
    right = cx + W_t/2
    peak_y = 2 + H_t

    # Outer mound
    ax.fill([left,cx,right],[2,peak_y,2], color="#cd853f", alpha=0.65)

    # Inner core
    inset = 0.12*W_t
    left_in, right_in = left+inset, right-inset
    peak_in_y = 2 + H_t*0.7
    ax.fill([left_in,cx,right_in],[2,peak_in_y,2], color="#8b5a2b", alpha=0.35)

    # Water fill
    if fill_ratio>0:
        water_top = 2 + (peak_in_y-2)*min(fill_ratio,1.0)
        slopeL = (peak_in_y-2)/max(cx-left_in,1e-9)
        slopeR = (peak_in_y-2)/max(right_in-cx,1e-9)
        xL = left_in + (water_top-2)/slopeL
        xR = right_in - (water_top-2)/slopeR
        ax.fill([xL,xR,right_in,left_in],[water_top,water_top,2,2], color="#1e90ff", alpha=0.55)

    # Realistic rain: streak lines (parallax) + splashes
    for (x0,y0,x1,y1, a, lw) in rain_streaks:
        for i in range(len(x0)):
            ax.plot([x0[i],x1[i]],[y0[i],y1[i]], color="#1f77b4", alpha=a, linewidth=lw)
    for k,(sx0,sy0,sx1,sy1) in enumerate(splash_segs):
        a = splash_alpha[k]
        ax.plot([sx0,sx1],[sy0,sy1], color="#1f77b4", alpha=a, linewidth=1.2)

    # Labels (static)
    ax.text(cx, peak_y+0.18, "mulch + soil", ha="center", fontsize=10)
    ax.text(cx, 2 + H_t*0.42, "wood/organic core\n('sponge')", ha="center", fontsize=10)

    # --------- Bottom HUD (with translucent background) ----------
    # Background panel
    panel_x, panel_y = 0.6, 2.08     # near bottom-left
    panel_w, panel_h = 3.1, 1.65     # width/height in data coords
    rect = patches.FancyBboxPatch(
        (panel_x, panel_y), panel_w, panel_h,
        boxstyle="round,pad=0.08,rounding_size=0.06",
        linewidth=0, facecolor=(1,1,1,0.45))
    ax.add_patch(rect)

    # Text lines stacked upward from panel_y
    base_y = panel_y + 0.18
    gap = 0.30
    ax.text(panel_x+0.18, base_y + 4*gap, f"Year: {year_t}", fontsize=10, va="bottom")
    ax.text(panel_x+0.18, base_y + 3*gap, f"Capacity now: {S_t:.1f} m³", fontsize=10, va="bottom")
    ax.text(panel_x+0.18, base_y + 2*gap, f"Intercepted: {intercepted_m3:.1f} m³", fontsize=10, va="bottom")
    ax.text(panel_x+0.18, base_y + 1*gap, f"Runoff: {cum_runoff_m3:.1f} m³", fontsize=10, va="bottom")
    ax.text(panel_x+0.18, base_y + 0*gap, f"Minute {min_i+1} / {minutes}", fontsize=10, va="bottom")

    # Axes
    ax.set_xlim(0,10); ax.set_ylim(1.6,6.0); ax.axis("off")
    fig_ph.pyplot(fig); plt.close(fig)

def show_metrics(cumP, cum_runoff_m3, intercepted_m3):
    with metrics_ph.container():
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Cumulative rain (mm)", f"{cumP:.1f}")
        c2.metric("Runoff volume (m³)", f"{cum_runoff_m3:.1f}")
        c3.metric("Mound capacity (m³)", f"{S_t:.1f}")
        c4.metric("Intercepted (m³)", f"{intercepted_m3:.1f}")

# -------------------- Prime UI -----------------------
minutes = int(duration_min)
series = hyetograph(total_rain_mm, minutes, rain_shape, randiness)
show_metrics(0.0,0.0,0.0)
draw_frame(0,0.0,0.0,0.0,0.0,minutes, [], [], [])
footer_ph.caption("Press ▶️ Start / Replay. Raindrops are slanted streaks with wind & gravity; splashes appear on impact. HUD is at the bottom.")

# -------------------- Animation loop ----------------
current_run = st.session_state.run_id
if current_run>0:
    cumP = 0.0
    cum_runoff_m3 = 0.0
    intercepted_m3 = 0.0
    filled = False

    rain = RainSystem(rain_intensity, base_wind, gustiness)
    frame_dt = 1.0/fps
    subframes = max(1, int(fps*0.6))  # ~0.6 s per "minute" visually

    for minute in range(minutes):
        if st.session_state.run_id != current_run: break
        while st.session_state.paused and st.session_state.run_id==current_run:
            time.sleep(0.05)

        # Hydrology increment
        dP = float(series[minute])
        Q_prev = scs_runoff_mm(cumP, CN)
        cumP += dP
        Q_curr = scs_runoff_mm(cumP, CN)
        dQ = max(Q_curr - Q_prev, 0.0)
        dV = (dQ/1000.0)*A
        cum_runoff_m3 += dV
        if not filled and S_t>0:
            take = min(max(S_t - intercepted_m3, 0.0), dV)
            intercepted_m3 += take
            filled = intercepted_m3 >= S_t - 1e-9

        # Animate: multiple frames within each minute
        for _ in range(subframes):
            if st.session_state.run_id != current_run or st.session_state.paused:
                break
            streaks, splash_segs, splash_alpha = rain.step()
            fill_ratio = 0.0 if S_t==0 else min(intercepted_m3/S_t, 1.0)
            show_metrics(cumP, cum_runoff_m3, intercepted_m3)
            draw_frame(minute, fill_ratio, cumP, cum_runoff_m3, intercepted_m3,
                       minutes, streaks, splash_segs, splash_alpha)
            time.sleep(frame_dt)

