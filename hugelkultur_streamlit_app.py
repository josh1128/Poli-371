# app.py
# Streamlit + PySWMM "one-subcatchment" runoff simulator
# - Builds a minimal SWMM .inp file from your slider settings
# - Runs the engine via pyswmm
# - Plots hydrograph and cumulative runoff volume

import tempfile
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from pyswmm import Simulation, Subcatchments

st.set_page_config(page_title="Simple Runoff (PySWMM)", layout="wide")
st.title("💧 Simple Runoff Simulation (PySWMM + Streamlit)")

# ---------------- Sidebar controls ----------------
st.sidebar.header("Storm")
P_mm = st.sidebar.slider("Total storm depth (mm)", 5, 1400, 60, 5)
dur_hr = st.sidebar.slider("Storm duration (hours)", 0.25, 24.0, 2.0, 0.25)
dt_min = st.sidebar.slider("Hyetograph step (minutes)", 1, 30, 5, 1)

st.sidebar.header("Subcatchment")
area_ha = st.sidebar.slider("Area (hectares)", 0.1, 20.0, 2.0, 0.1)
pct_imp = st.sidebar.slider("Impervious (%)", 0, 100, 30, 1)
slope_pct = st.sidebar.slider("Average slope (%)", 0.1, 20.0, 2.0, 0.1)
width_m = st.sidebar.slider("Characteristic width (m)", 10, 2000, 200, 10)
rough_perv = st.sidebar.number_input("Manning n (pervious)", min_value=0.01, value=0.24, step=0.01, format="%.2f")
rough_imp = st.sidebar.number_input("Manning n (impervious)", min_value=0.01, value=0.013, step=0.001, format="%.3f")
pct_zero_storage = st.sidebar.slider("Impervious with zero storage (%)", 0, 100, 25, 5)
depress_perv_mm = st.sidebar.number_input("Depression storage pervious (mm)", min_value=0.0, value=5.0, step=0.5)
depress_imp_mm = st.sidebar.number_input("Depression storage impervious (mm)", min_value=0.0, value=1.5, step=0.5)

st.sidebar.header("Infiltration")
model_choice = st.sidebar.selectbox("Model", ["Green-Ampt", "Horton"])
if model_choice == "Green-Ampt":
    # Typical sandy loam-ish defaults (adjust as needed)
    ga_suction_mm = st.sidebar.number_input("Suction head (mm)", 20.0, 300.0, 110.0, 1.0)
    ga_Ksat_mmhr = st.sidebar.number_input("Hydraulic conductivity (mm/hr)", 1.0, 100.0, 12.0, 0.5)
    ga_IMD = st.sidebar.number_input("Initial moisture deficit (0–1)", 0.0, 1.0, 0.4, 0.05)
else:
    # Horton defaults
    hort_f0 = st.sidebar.number_input("f0 initial infil (mm/hr)", 1.0, 200.0, 60.0, 1.0)
    hort_fmin = st.sidebar.number_input("fmin minimum infil (mm/hr)", 0.1, 50.0, 6.0, 0.1)
    hort_decay = st.sidebar.number_input("decay (1/hr)", 0.1, 10.0, 3.0, 0.1)

st.sidebar.header("Run")
run_btn = st.sidebar.button("Run Simulation")

# ---------------- Helpers ----------------
def make_rectangular_hyetograph(total_mm, dur_hr, dt_minutes):
    """Return a pandas DataFrame with datetime and intensity (in/hr) for SWMM TIMESERIES."""
    start = datetime(2020, 1, 1, 0, 0, 0)
    times = pd.date_range(start, start + timedelta(hours=dur_hr), freq=f"{int(dt_minutes)}min")
    if len(times) < 2:
        times = pd.date_range(start, start + timedelta(hours=dur_hr), freq="1min")
    # Average intensity in in/hr
    total_in = total_mm / 25.4
    I_in_hr = total_in / dur_hr if dur_hr > 0 else 0.0
    intens = np.zeros(len(times))
    intens[:-1] = I_in_hr  # hold last point at 0
    return pd.DataFrame({"time": times, "intensity_in_hr": intens})

def build_swmm_inp(ts_df,
                   area_ha, pct_imp, slope_pct, width_m,
                   rough_perv, rough_imp,
                   pct_zero_storage,
                   depress_perv_mm, depress_imp_mm,
                   infil_model, infil_params):
    """Create a minimal SWMM input file as a string."""
    # Units & conversions
    area_acres = area_ha * 2.47105
    slope = slope_pct / 100.0
    z_pcnt = pct_zero_storage
    stor_perv_in = depress_perv_mm / 25.4
    stor_imp_in = depress_imp_mm / 25.4

    # TIMESERIES block
    ts_lines = ["[TIMESERIES]"]
    for _, row in ts_df.iterrows():
        # SWMM expects hh:mm and value. We use absolute datetime; engine uses clock times.
        ts_lines.append(f"Rain1 {row['time'].strftime('%Y-%m-%d')} {row['time'].strftime('%H:%M')} {row['intensity_in_hr']:.6f}")
    ts_block = "\n".join(ts_lines)

    # Infiltration
    if infil_model == "Green-Ampt":
        suction_in, Ksat_in_hr, IMD = infil_params
        infil_block = "[INFILTRATION]\n" \
                      f"S1 {suction_in:.4f} {Ksat_in_hr:.4f} {IMD:.4f}\n"
        infil_opt = "INFILTRATION GREEN_AMPT"
    else:
        f0_in, fmin_in, decay = infil_params
        infil_block = "[INFILTRATION]\n" \
                      f"S1 {f0_in:.4f} {fmin_in:.4f} {decay:.4f}\n"
        infil_opt = "INFILTRATION HORTON"

    # Full .inp text
    inp = f"""
[TITLE]
;; Project Title/Notes
HOPE Rwanda – Simple One-Subcatchment Runoff

[OPTIONS]
FLOW_UNITS              CFS
INFILTRATION            {infil_opt.split()[-1]}
FLOW_ROUTING            KINWAVE
START_DATE              01/01/2020
START_TIME              00:00:00
REPORT_START_DATE       01/01/2020
REPORT_START_TIME       00:00:00
END_DATE                01/02/2020
END_TIME                00:00:00
SWEEP_START             01/01
SWEEP_END               12/31
DRY_DAYS                0
REPORT_STEP             00:05:00
WET_STEP                00:01:00
ROUTING_STEP            00:00:30
ALLOW_PONDING           NO
LINK_OFFSETS            DEPTH
MIN_SLOPE               0

[RAINGAGES]
;;Name           Format    Interval SCF  Source
RG1              INTENSITY 0:05     1.0  TIMESERIES Rain1

{ts_block}

[JUNCTIONS]
;;Name           Elevation  MaxDepth  InitDepth  SurDepth  Aponded
J1               0          0         0          0         0

[OUTFALLS]
;;Name           Elevation  Type       Stage Data       Gated
O1               0          FREE                       NO

[SUBCATCHMENTS]
;;Name  Raingage  Outlet  Area     %Imperv  Width  %Slope   CurbLen  SnowPack
S1      RG1       O1      {area_acres:.4f} {pct_imp:.2f} {width_m:.2f} {slope:.4f} 0

[SUBAREAS]
;;Subcatch  N-Imperv   N-Perv   S-Imperv   S-Perv   %Zero-Imperv   RouteTo    %Routed
S1         {rough_imp:.3f}     {rough_perv:.3f}   {stor_imp_in:.3f}     {stor_perv_in:.3f}    {z_pcnt:.1f}            OUTLET     100

{infil_block}

[REPORT]
SUBCATCHMENTS ALL
NODES ALL
LINKS NONE

[TAGS]

[END]
""".strip()
    return inp

def run_swmm_from_string(inp_text):
    """Run SWMM given full .inp text, return times and runoff series for S1."""
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".inp", delete=False) as f:
        f.write(inp_text)
        f.flush()
        path = f.name

    times, q = [], []
    with Simulation(path) as sim:
        sub = Subcatchments(sim)["S1"]
        for _ in sim:
            times.append(sim.current_time)
            q.append(sub.runoff)  # m3/s
    return pd.DataFrame({"time": pd.to_datetime(times), "runoff_cumecs": q})

# ---------------- Build & Run ----------------
if run_btn:
    # Hyetograph + conversions for infiltration
    ts = make_rectangular_hyetograph(P_mm, dur_hr, dt_min)

    if model_choice == "Green-Ampt":
        # Convert Green-Ampt params to inches/hr and inches for SWMM input
        ga_suction_in = (ga_suction_mm / 25.4)
        ga_Ksat_in_hr = (ga_Ksat_mmhr / 25.4)
        infil_params = (ga_suction_in, ga_Ksat_in_hr, ga_IMD)
    else:
        # Horton params are in length/time units SWMM expects inches/hr
        infil_params = (hort_f0 / 25.4, hort_fmin / 25.4, hort_decay)

    inp = build_swmm_inp(
        ts_df=ts,
        area_ha=area_ha,
        pct_imp=pct_imp,
        slope_pct=slope_pct,
        width_m=width_m,
        rough_perv=rough_perv,
        rough_imp=rough_imp,
        pct_zero_storage=pct_zero_storage,
        depress_perv_mm=depress_perv_mm,
        depress_imp_mm=depress_imp_mm,
        infil_model=model_choice,
        infil_params=infil_params
    )

    df = run_swmm_from_string(inp)

    # Integrate flow to volume (m^3)
    if len(df) >= 2:
        dt_sec = (df["time"].diff().dt.total_seconds()).fillna(0).to_numpy()
        vol = np.cumsum(df["runoff_cumecs"].to_numpy() * dt_sec)  # m^3
    else:
        vol = np.zeros(len(df))
    df["cumulative_m3"] = vol

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Runoff hydrograph (m³/s)")
        fig1, ax1 = plt.subplots()
        ax1.plot(df["time"], df["runoff_cumecs"])
        ax1.set_xlabel("Time")
        ax1.set_ylabel("Runoff (m³/s)")
        ax1.grid(True, alpha=0.3)
        st.pyplot(fig1)

    with col2:
        st.subheader("Cumulative runoff volume (m³)")
        fig2, ax2 = plt.subplots()
        ax2.plot(df["time"], df["cumulative_m3"])
        ax2.set_xlabel("Time")
        ax2.set_ylabel("Volume (m³)")
        ax2.grid(True, alpha=0.3)
        st.pyplot(fig2)

    st.divider()
    st.subheader("Key numbers")
    st.write(f"- **Total storm**: {P_mm:.0f} mm over {dur_hr:.2f} h")
    st.write(f"- **Peak runoff**: {df['runoff_cumecs'].max():.4f} m³/s")
    st.write(f"- **Total runoff volume**: {df['cumulative_m3'].iloc[-1]:.1f} m³")
    st.download_button("⬇️ Download generated SWMM input (.inp)", data=inp, file_name="hope_rwanda_simple.inp", mime="text/plain")

else:
    st.info("Set your sliders, then click **Run Simulation** in the sidebar.")
