import os, tempfile
import numpy as np
import pandas as pd
import streamlit as st
import hydrobricks as hb
import hydrobricks.models as models

st.set_page_config(page_title="Hydrobricks minimal (Socont)", layout="centered")
st.title("💧 Hydrobricks minimal (Socont) — robust ranges")

st.write("This creates tiny CSVs (bands + meteo), widens parameter ranges to avoid "
         "range errors, runs Socont for 30 days, and plots outlet discharge (mm/day).")

def make_inputs(tmpdir: str):
    # Elevation bands: 3 bands totaling 10 km² (areas in m²)
    elev_csv = os.path.join(tmpdir, "elevation_bands.csv")
    pd.DataFrame({
        "elevation": [1100, 1300, 1500],
        "area": [3.0e6, 4.0e6, 3.0e6],  # m²
    }).to_csv(elev_csv, index=False)

    # Meteo (daily): 30 days with a simple rain pulse and mild temps
    meteo_csv = os.path.join(tmpdir, "meteo.csv")
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    precip = np.zeros(30); precip[5:10] = [5, 10, 15, 10, 5]   # mm/day
    temp = 12 + 3*np.sin(np.linspace(0, 2*np.pi, 30))
    pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "precip(mm/day)": precip,
        "temp(C)": temp,
    }).to_csv(meteo_csv, index=False)

    # Dummy observed discharge (optional)
    obs_csv = os.path.join(tmpdir, "discharge.csv")
    pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "Discharge (mm/d)": np.zeros(30),
    }).to_csv(obs_csv, index=False)

    return elev_csv, meteo_csv, obs_csv

def widen_range(params, name, target_value):
    """
    Ensure the parameter 'name' can take 'target_value' by widening its allowed range.
    This avoids ValueError: below/above minimum/maximum threshold.
    """
    # Choose a symmetric window around the target value.
    # Keep it modest for stability.
    v = float(target_value)
    span = max(abs(v) * 0.5, 1e-3)  # half-width; at least small epsilon
    new_min, new_max = v - span, v + span
    try:
        params.change_range(name, new_min, new_max)
    except Exception:
        # Some aliases are grouped; attempt a few common aliases
        # (If unknown, you can skip or log)
        pass

if st.button("▶ Run Hydrobricks"):
    with tempfile.TemporaryDirectory() as tmpdir:
        elev_csv, meteo_csv, obs_csv = make_inputs(tmpdir)

        # --- Model ---
        socont = models.Socont(
            soil_storage_nb=2,
            surface_runoff="linear_storage",
            record_all=False
        )

        # --- Parameters ---
        params = socont.generate_parameters()

        # Choose simple demo values (you can change these later)
        desired = {
            "A": 200.0,        # degree-day factor (example)
            "a_snow": 3.0,     # snowmelt param (must be < a_ice typically)
            "k_quick": 1.0,    # quick reservoir coeff
            "k_slow_1": 0.8,   # slow reservoir 1 coeff
            "k_slow_2": 0.6,   # slow reservoir 2 coeff
            "percol": 10.0,    # percolation rate
        }

        # Make sure each desired value is within the allowed range
        for name, val in desired.items():
            widen_range(params, name, val)

        # Now set values (after widening ranges)
        params.set_values(desired)

        # --- Hydro units (elevation bands) ---
        hydro_units = hb.HydroUnits()
        hydro_units.load_from_csv(
            elev_csv,
            area_unit="m2",
            column_elevation="elevation",
            column_area="area",
        )

        # --- Forcing ---
        forcing = hb.Forcing(hydro_units)
        forcing.load_station_data_from_csv(
            meteo_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"precipitation": "precip(mm/day)", "temperature": "temp(C)"},
        )
        # Spatialize T and P with simple gradients/corrections
        ref_z = 1250
        forcing.spatialize_from_station_data("temperature", ref_elevation=ref_z, gradient=-0.6)
        forcing.correct_station_data("precipitation", correction_factor=0.9)
        forcing.spatialize_from_station_data("precipitation", ref_elevation=ref_z, gradient=0.05)
        forcing.compute_pet(method="Hamon", use=["t", "lat"], lat=47.3)

        # --- Observations (optional) ---
        obs = hb.Observations()
        obs.load_from_csv(
            obs_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"discharge": "Discharge (mm/d)"},
        )

        # --- Run ---
        outdir = os.path.join(tmpdir, "outputs"); os.makedirs(outdir, exist_ok=True)
        socont.setup(
            spatial_structure=hydro_units,
            output_path=outdir,
            start_date="2000-01-01",
            end_date="2000-01-30",
        )
        socont.initialize_state_variables(parameters=params, forcing=forcing)
        socont.run(parameters=params, forcing=forcing)

        # --- Plot outlet discharge ---
        sim_ts = socont.get_outlet_discharge()   # xarray.DataArray (mm/day)
        df = sim_ts.to_dataframe(name="Q_mm_day").reset_index()
        st.line_chart(df.set_index("time")["Q_mm_day"])
        st.success("✅ Hydrobricks run complete.")
