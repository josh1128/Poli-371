# Minimal Streamlit + PySWMM runoff toy
# One subcatchment, rectangular storm, Horton infiltration (fixed)
import tempfile
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from pyswmm import Simulation, Subcatchments

st.set_page_config(page_title="Tiny Runoff (PySWMM)", layout="centered")
st.title("💧 Tiny Runoff Simulator (PySWMM)")

# ---- Sliders (just 4) ----
P_mm = st.slider("Total storm depth (mm)", 5, 400, 50, 5)
dur_hr = st.slider("Storm duration (hours)", 0.25, 12.0, 2.0, 0.25)
area_ha = st.slider("Subcatchment area (hectares)", 0.1, 20.0, 1.0, 0.1)
pct_imp = st.slider("Impervious (%)", 0, 100, 40, 1)

if st.button("Run"):
    # --- Make a simple rectangular hyetograph at 5-min step ---
    start = datetime(2020, 1, 1, 0, 0, 0)
    times = pd.date_range(start, start + timedelta(hours=dur_hr), freq="5min")
    total_in = P_mm / 25.4
    I_in_hr = total_in / dur_hr if dur_hr > 0 else 0.0
    intens = np.zeros(len(times))
    intens[:-1] = I_in_hr  # last point 0
    ts_df = pd.DataFrame({"t": times, "i": intens})

    # --- Build a minimal SWMM input as text ---
    area_acres = area_ha * 2.47105
    width_m = 200.0      # simple fixed width
    slope = 0.02         # 2% slope
    n_perv = 0.24
    n_imp = 0.013
    stor_perv_in = 0.20  # ~5 mm
    stor_imp_in = 0.06   # ~1.5 mm
    zero_storage_pct = 25.0

    ts_lines = ["[TIMESERIES]"]
    for _, r in ts_df.iterrows():
        ts_lines.append(f"R1 {r['t'].strftime('%Y-%m-%d')} {r['t'].strftime('%H:%M')} {r['i']:.6f}")
    ts_block = "\n".join(ts_lines)

    # Horton infiltration (fixed simple values, inches/hour)
    f0 = 60/25.4     # initial infil capacity
    fmin = 6/25.4    # min infil capacity
    decay = 3.0      # 1/hr

    inp = f"""
[TITLE]
Tiny one-subcatchment runoff

[OPTIONS]
FLOW_UNITS              CFS
INFILTRATION            HORTON
FLOW_ROUTING            KINWAVE
START_DATE              01/01/2020
START_TIME              00:00:00
REPORT_START_DATE       01/01/2020
REPORT_START_TIME       00:00:00
END_DATE                01/02/2020
END_TIME                00:00:00
REPORT_STEP             00:05:00
WET_STEP                00:01:00
ROUTING_STEP            00:00:30

[RAINGAGES]
;;Name  Format    Interval SCF  Source
G1      INTENSITY 0:05     1.0  TIMESERIES R1

{ts_block}

[JUNCTIONS]
;;Name  Elev  MaxDepth  Init  SurDepth  Aponded
J1      0     0         0     0         0

[OUTFALLS]
;;Name  Elev  Type  Stage Data  Gated
O1      0     FREE               NO

[SUBCATCHMENTS]
;;Name  Raingage  Outlet  Area(ac)  %Imp   Width(m)  %Slope  Curb
S1      G1        O1      {area_acres:.4f} {pct_imp:.2f} {width_m:.2f}  {slope:.4f}  0

[SUBAREAS]
;;Sub   N-Imp     N-Perv   S-Imp     S-Perv    %ZeroImp  RouteTo  %Routed
S1      {n_imp:.3f}    {n_perv:.3f}  {stor_imp_in:.3f}  {stor_perv_in:.3f}  {zero_storage_pct:.1f} OUTLET   100

[INFILTRATION]
;;Sub  f0(in/hr)  fmin(in/hr)  decay(1/hr)
S1     {f0:.4f}    {fmin:.4f}     {decay:.3f}

[REPORT]
SUBCATCHMENTS ALL

[END]
""".strip()

    # --- Run the model and collect runoff time series ---
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(inp)
        f.flush()
        path = f.name

    times_out, q = [], []
    with Simulation(path) as sim:
        sub = Subcatchments(sim)["S1"]
        for _ in sim:
            times_out.append(sim.current_time)
            q.append(sub.runoff)  # m3/s

    df = pd.DataFrame({"time": pd.to_datetime(times_out), "q_m3s": q})

    # --- Plot ---
    fig, ax = plt.subplots()
    ax.plot(df["time"], df["q_m3s"])
    ax.set_xlabel("Time")
    ax.set_ylabel("Runoff (m³/s)")
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)

    # --- Simple totals ---
    dt = df["time"].diff().dt.total_seconds().fillna(0).to_numpy()
    vol_m3 = float(np.sum(df["q_m3s"].to_numpy() * dt))
    st.write(f"**Peak runoff:** {df['q_m3s'].max():.4f} m³/s")
    st.write(f"**Total runoff volume:** {vol_m3:.1f} m³")

else:
    st.info("Set the sliders and click **Run**.")

