import os
import tempfile
import numpy as np
import pandas as pd
import streamlit as st
import hydrobricks as hb
import hydrobricks.models as models

st.set_page_config(page_title="Hydrobricks minimal (Socont)", layout="centered")
st.title("💧 Hydrobricks minimal (Socont)")

st.write(
    "This demo creates tiny CSV inputs (elevation bands with units, daily meteo) "
    "and runs the Socont model for 30 days. It then plots outlet discharge (mm/day)."
)

# ----------------------------
# Helpers
# ----------------------------
def write_elevation_csv(path: str):
    """
    Hydrobricks expects a second header row with units.
    We provide elevation [m] and area [m2].
    """
    with open(path, "w") as f:
        f.write("elevation,area\n")
        f.write("m,m2\n")                    # REQUIRED units row
        f.write("1100,3000000\n")
        f.write("1300,4000000\n")
        f.write("1500,3000000\n")

def write_meteo_csv(path: str):
    """
    Simple 30-day daily series with a small rainfall pulse and mild temperatures.
    Column names are referenced below when loading station data.
    """
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    precip = np.zeros(30)
    precip[5:10] = [5, 10, 15, 10, 5]   # mm/day pulse
    temp = 12 + 3 * np.sin(np.linspace(0, 2 * np.pi, 30))
    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "precip(mm/day)": precip,
        "temp(C)": temp,
    })
    df.to_csv(path, index=False)

def write_obs_csv(path: str):
    """
    Optional: observed discharge (mm/day). Here just zeros for the demo.
    """
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "Discharge (mm/d)": np.zeros(30),
    })
    df.to_csv(path, index=False)

def safe_set_params(params, values: dict):
    """
    Hydrobricks parameters have allowed ranges. If a target value is outside,
    widen the range just enough, then set. Keeps things robust for demos.
    """
    for name, v in values.items():
        v = float(v)
        # Try to widen range modestly around target value
        try:
            span = max(abs(v) * 0.5, 1e-3)
            params.change_range(name, v - span, v + span)
        except Exception:
            # Not all parameters support change_range; ignore if not available
            pass
    params.set_values(values)

# ----------------------------
# UI (optional sliders to tweak a few params)
# ----------------------------
with st.expander("Adjust parameters (optional)"):
    A = st.slider("Degree-day factor snow (A)", 50.0, 600.0, 200.0, 10.0)
    a_snow = st.slider("Snowmelt parameter (a_snow)", 0.5, 6.0, 3.0, 0.1)
    k_quick = st.slider("Quick reservoir coefficient (k_quick)", 0.2, 2.0, 1.0, 0.1)
    k_slow_1 = st.slider("Slow reservoir 1 coeff (k_slow_1)", 0.2, 2.0, 0.8, 0.1)
    k_slow_2 = st.slider("Slow reservoir 2 coeff (k_slow_2)", 0.2, 2.0, 0.6, 0.1)
    percol = st.slider("Percolation rate (percol)", 1.0, 20.0, 10.0, 0.5)
    rain_scale = st.slider("Rain pulse scale (×)", 0.2, 3.0, 1.0, 0.1)

run = st.button("▶ Run Hydrobricks")

if run:
    with tempfile.TemporaryDirectory() as tmpdir:
        elev_csv = os.path.join(tmpdir, "elevation_bands.csv")
        meteo_csv = os.path.join(tmpdir, "meteo.csv")
        obs_csv = os.path.join(tmpdir, "discharge.csv")
        outdir = os.path.join(tmpdir, "outputs")
        os.makedirs(outdir, exist_ok=True)

        # 1) Inputs
        write_elevation_csv(elev_csv)
        write_meteo_csv(meteo_csv)

        # Optionally scale rainfall by slider (edit the CSV we just wrote)
        if rain_scale != 1.0:
            dfm = pd.read_csv(meteo_csv)
            dfm["precip(mm/day)"] = dfm["precip(mm/day)"] * float(rain_scale)
            dfm.to_csv(meteo_csv, index=False)

        write_obs_csv(obs_csv)

        # 2) Hydro units (no kwargs — units row is already in the CSV)
        hydro_units = hb.HydroUnits()
        hydro_units.load_from_csv(elev_csv)

        # 3) Forcing
        forcing = hb.Forcing(hydro_units)
        forcing.load_station_data_from_csv(
            meteo_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={
                "precipitation": "precip(mm/day)",
                "temperature": "temp(C)",
            },
        )

        # Simple spatialization: lapse rate & precipitation gradient
        # NOTE: Gradients are per 100 m in this demo-style call.
        ref_z = 1250
        forcing.spatialize_from_station_data(
            "temperature", ref_elevation=ref_z, gradient=-0.6  # -0.6 °C / 100 m
        )
        forcing.correct_station_data("precipitation", correction_factor=0.9)
        forcing.spatialize_from_station_data(
            "precipitation", ref_elevation=ref_z, gradient=0.05  # +5% / 100 m
        )
        forcing.compute_pet(method="Hamon", use=["t", "lat"], lat=47.3)

        # 4) Model and parameters
        socont = models.Socont(
            soil_storage_nb=2,
            surface_runoff="linear_storage",
            record_all=False,
        )
        params = socont.generate_parameters()

        # Set a small, safe parameter set (ranges widened if needed)
        desired_params = {
            "A": A,
            "a_snow": a_snow,
            "k_quick": k_quick,
            "k_slow_1": k_slow_1,
            "k_slow_2": k_slow_2,
            "percol": percol,
        }
        safe_set_params(params, desired_params)

        # 5) (Optional) Observations
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

        # 7) Results → DataFrame → Plot
        sim_ts = socont.get_outlet_discharge()  # xarray.DataArray (mm/day)
        df = sim_ts.to_dataframe(name="Q_mm_day").reset_index()
        st.subheader("Outlet discharge (mm/day)")
        st.line_chart(df.set_index("time")["Q_mm_day"])

        # Quick peek at first rows
        st.dataframe(df.head())
        st.success("✅ Hydrobricks run complete.")

        st.success("✅ Hydrobricks run complete.")
