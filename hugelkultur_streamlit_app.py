# Minimal Streamlit + Phydrus (HYDRUS-1D) runner
# - One soil layer (van Genuchten)
# - 1D profile 0 to -100 cm
# - Constant-head top (ponding) & free-drainage bottom
# - Plots water content profile at end & head time series at an observation node

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

import phydrus as ps
from phydrus import profile as pf

st.set_page_config(page_title="Phydrus (HYDRUS-1D) – Minimal Runner", layout="centered")
st.title("💧 HYDRUS-1D (via Phydrus) – Minimal Streamlit Runner")

# --- 1) Path to HYDRUS-1D executable ---
st.subheader("1) Hydrus-1D executable")
default_ws = os.path.abspath("ws_simple")
exe_path = st.text_input(
    "Path to Hydrus-1D executable (H1D_CALC.EXE or compiled binary)",
    value="/path/to/H1D_CALC.exe" if os.name == "nt" else "/path/to/H1D_CALC_unix_binary",
    help="On Windows, this is the installed Hydrus-1D H1D_CALC.EXE. On macOS/Linux, point to your compiled binary."
)

# --- 2) Basic model setup ---
st.subheader("2) Soil & domain")
col1, col2 = st.columns(2)
with col1:
    top_cm = st.number_input("Top depth (cm)", value=0, step=1)
    bot_cm = st.number_input("Bottom depth (cm)", value=-100, step=1)
    dx_cm  = st.number_input("Node spacing (cm)", value=1.0, step=0.5, min_value=0.1)
    tmax_h = st.number_input("Simulation time (hours)", value=48.0, step=1.0, min_value=1.0)
with col2:
    # van Genuchten (theta_r, theta_s, alpha[1/cm], n[-], Ks[cm/hr], l[-])
    theta_r = st.number_input("θr", value=0.08, step=0.01, min_value=0.0, max_value=0.4)
    theta_s = st.number_input("θs", value=0.43, step=0.01, min_value=0.2, max_value=0.7)
    alpha   = st.number_input("α (1/cm)", value=0.036, step=0.001, min_value=0.001)
    n_vg    = st.number_input("n (–)", value=1.56, step=0.01, min_value=1.01)
    Ks      = st.number_input("Ks (cm/hr)", value=10.0, step=0.5, min_value=0.01)
    l_param = st.number_input("l (–)", value=-0.5, step=0.1)

st.subheader("3) Boundary & initial conditions")
col3, col4 = st.columns(2)
with col3:
    top_bc = st.selectbox("Top BC", ["Constant head (ponding at 0 cm)"], index=0)
    bot_bc = st.selectbox("Bottom BC", ["Free drainage"], index=0)
with col4:
    init_head = st.number_input("Initial pressure head (cm)", value=-100.0, step=5.0)

run = st.button("Run simulation")

def build_and_run(exe_path, ws_name):
    # Model shell
    ml = ps.Model(
        exe_name=exe_path,
        ws_name=ws_name,
        name="demo",
        length_unit="cm",
        time_unit="hours"
    )

    # Soil material (van Genuchten)
    m = ml.get_empty_material_df(n=1)
    m.loc[1] = [theta_r, theta_s, alpha, n_vg, Ks, l_param]
    ml.add_material(m)

    # 1D profile and initial condition
    prof = pf.create_profile(top=top_cm, bot=bot_cm, dx=dx_cm, h=init_head, lay=1, mat=1)
    ml.add_profile(prof)

    # Water flow module: model=0 (Richards), top_bc=0 (const head), bot_bc=4 (free drainage)
    ml.add_waterflow(model=0, top_bc=0, bot_bc=4)

    # Time info
    ml.add_time_info(tinit=0.0, tmax=float(tmax_h), dt=0.01)

    # Files + run
    ml.write_input()
    ml.simulate()

    # Results
    obs = ml.read_obs_node()        # observation node time series (if any defined by Phydrus default)
    h_prof, th_prof = ml.read_end_profile(var="h"), ml.read_end_profile(var="theta")

    return obs, h_prof, th_prof, ml

if run:
    # Quick checks
    if not os.path.isfile(exe_path) or not os.access(exe_path, os.X_OK):
        st.error("Hydrus executable not found or not executable. Please check the path.")
    else:
        ws = default_ws
        try:
            obs, h_prof, th_prof, ml = build_and_run(exe_path, ws)

            st.success("Simulation finished.")

            # --- Plot 1: Final water content profile θ(z) ---
            st.subheader("Final water content profile θ(z)")
            fig1, ax1 = plt.subplots()
            ax1.plot(th_prof["theta"], th_prof["depth"])
            ax1.set_xlabel("θ (–)")
            ax1.set_ylabel("Depth (cm)")
            ax1.invert_yaxis()
            ax1.grid(True, alpha=0.3)
            st.pyplot(fig1)

            # --- Plot 2: Final pressure head profile h(z) ---
            st.subheader("Final pressure head profile h(z)")
            fig2, ax2 = plt.subplots()
            ax2.plot(h_prof["h"], h_prof["depth"])
            ax2.set_xlabel("h (cm)")
            ax2.set_ylabel("Depth (cm)")
            ax2.invert_yaxis()
            ax2.grid(True, alpha=0.3)
            st.pyplot(fig2)

            # --- Plot 3: Time series at an observation node (if available) ---
            st.subheader("Pressure head at observation node (if present)")
            if isinstance(obs, pd.DataFrame) and not obs.empty:
                fig3, ax3 = plt.subplots()
                # Try to auto-pick a column that looks like pressure head
                col_candidates = [c for c in obs.columns if c.lower().startswith("h(")]
                y = obs[col_candidates[0]] if col_candidates else obs.iloc[:, 1]
                ax3.plot(obs["time"], y)
                ax3.set_xlabel("Time (h)")
                ax3.set_ylabel("h (cm)")
                ax3.grid(True, alpha=0.3)
                st.pyplot(fig3)
            else:
                st.info("No observation-node time series in this minimal setup (that’s okay for a quick run).")

            with st.expander("Show working directory"):
                st.code(ml.ws_path)

        except Exception as e:
            st.exception(e)
else:
    st.info("Set parameters, provide the Hydrus executable path, then click **Run simulation**.")

