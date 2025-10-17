import os
import tempfile
import numpy as np
import pandas as pd
import streamlit as st
import hydrobricks as hb
import hydrobricks.models as models

st.set_page_config(page_title="Hydrobricks minimal (Socont)", layout="centered")
st.title("💧 Hydrobricks minimal (Socont) — no spatialization")

st.write(
    "Single hydro unit + station meteorology. No spatialization calls, so the API "
    "mismatch that caused the TypeError is avoided. We still compute PET (Hamon) "
    "and plot outlet discharge (mm/day)."
)

# ----------------------------
# Helpers
# ----------------------------
def write_hydrounits_csv(path: str):
    """
    Hydrobricks requires:
      - a first column named 'id'
      - a second header row with units
    We'll use ONE hydro unit: id=1, elevation=1200 m, area=10 km².
    """
    with open(path, "w") as f:
        f.write("id,elevation,area\n")
        f.write("-,m,m2\n")                  # units row (id has no units)
        f.write("1,1200,10000000\n")         # 10,000,000 m² = 10 km²

def write_meteo_csv(path: str, scale: float = 1.0):
    """
    Daily time series for 30 days:
      - a simple rainfall pulse
      - mild temperatures
    """
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    precip = np.zeros(30)
    precip[5:10] = np.array([5, 10, 15, 10, 5]) * float(scale)  # mm/day pulse
    temp = 12 + 3 * np.sin(np.linspace(0, 2 * np.pi, 30))       # °C

    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "precip(mm/day)": precip,
        "temp(C)": temp,
    })
    df.to_csv(path, index=False)

def write_obs_csv(path: str):
    """Optional observed discharge (mm/day)."""
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "Discharge (mm/d)": np.zeros(30),
    })
    df.to_csv(path, index=False)

def safe_set_params(params, values: dict):
    """
    Widen ranges slightly (if needed) before setting values to avoid
    'below minimum threshold' errors.
    """
    for name, v in values.items():
        v = float(v)
        try:
            span = max(abs(v) * 0.5, 1e-3)
            params.change_range(name, v - span, v + span)
        except Exception:
            pass
    params.set_values(values)

# ----------------------------
# UI
# ----------------------------
with st.expander("Adjust parameters (optional)"):
    A = st.slider("Degree-day factor snow (A)", 50.0, 600.0, 200.0, 10.0)
    a_snow = st.slider("Snowmelt parameter (a_snow)", 0.5, 6.0, 3.0, 0.1)
    k_quick = st.slider("Quick reservoir coefficient (k_quick)", 0.2, 2.0, 1.0, 0.1)
    k_slow_1 = st.slider("Slow reservoir 1 coeff (k_slow_1)", 0.2, 2.0, 0.8, 0.1)
    k_slow_2 = st.slider("Slow reservoir 2 coeff (k_slow_2)", 0.2, 2.0, 0.6, 0.1)
    percol = st.slider("Percolation rate (percol)", 1.0, 20.0, 10.0, 0.5)
    rain_scale = st.slider("Rain pulse scale (×)", 0.2, 3.0, 1.0, 0.1)
    lat = st.slider("Latitude for PET (deg)", -60.0, 60.0, 47.3, 0.1)

run = st.button("▶ Run Hydrobricks")

if run:
    with tempfile.TemporaryDirectory() as tmpdir:
        elev_csv = os.path.join(tmpdir, "hydro_units.csv")
        meteo_csv = os.path.join(tmpdir, "meteo.csv")
        obs_csv = os.path.join(tmpdir, "discharge.csv")
        outdir = os.path.join(tmpdir, "outputs")
        os.makedirs(outdir, exist_ok=True)

        # 1) Inputs
        write_hydrounits_csv(elev_csv)
        write_meteo_csv(meteo_csv, scale=rain_scale)
        write_obs_csv(obs_csv)

        # 2) Hydro units (CSV has id/elevation/area with units row)
        hydro_units = hb.HydroUnits()
        hydro_units.load_from_csv(elev_csv)

        # 3) Forcing — load station data only (NO spatialization)
        forcing = hb.Forcing(hydro_units)
        forcing.load_station_data_from_csv(
            meteo_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"precipitation": "precip(mm/day)", "temperature": "temp(C)"},
        )

        # Compute PET (Hamon) using temperature + latitude
        forcing.compute_pet(method="Hamon", use=["t", "lat"], lat=float(lat))

        # 4) Model + parameters
        socont = models.Socont(
            soil_storage_nb=2,
            surface_runoff="linear_storage",
            record_all=False,
        )
        params = socont.generate_parameters()
        desired_params = {
            "A": A,
            "a_snow": a_snow,
            "k_quick": k_quick,
            "k_slow_1": k_slow_1,
            "k_slow_2": k_slow_2,
            "percol": percol,
        }
        safe_set_params(params, desired_params)

        # 5) Observations (optional)
        obs = hb.Observations()
        obs.load_from_csv(
            obs_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"discharge": "Discharge (mm/d)"},
        )

        # 6) Setup & run
        socont.setup(
            spatial_structure=hydro_units,
            output_path=outdir,
            start_date="2000-01-01",
            end_date="2000-01-30",
        )
        socont.initialize_state_variables(parameters=params, forcing=forcing)
        socont.run(parameters=params, forcing=forcing)

        # 7) Results → plot
        sim_ts = socont.get_outlet_discharge()  # xarray.DataArray (mm/day)
        df = sim_ts.to_dataframe(name="Q_mm_day").reset_index()
        st.subheader("Outlet discharge (mm/day)")
        st.line_chart(df.set_index("time")["Q_mm_day"])
        st.dataframe(df.head())
        st.success("✅ Hydrobricks run complete (single hydro unit, no spatialization).")

