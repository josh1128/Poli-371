import os, tempfile
import pandas as pd
import numpy as np
import streamlit as st
import hydrobricks as hb
import hydrobricks.models as models

st.set_page_config(page_title="Hydrobricks minimal demo", layout="centered")
st.title("💧 Hydrobricks minimal (Socont) — synthetic example")

st.write("This creates tiny CSVs (elevation bands, meteo, discharge), "
         "runs the Socont model for a few weeks, and plots outlet discharge.")

# --- make tiny synthetic inputs ---
def make_inputs(tmpdir: str):
    # Elevation bands: 3 bands totaling 10 km² (areas in m²)
    elev_csv = os.path.join(tmpdir, "elevation_bands.csv")
    elev_df = pd.DataFrame({
        "elevation": [1100, 1300, 1500],
        "area": [3.0e6, 4.0e6, 3.0e6],  # m²
    })
    elev_df.to_csv(elev_csv, index=False)

    # Meteo (daily): simple 30-day series with a rain pulse; temperature around 10–15°C
    meteo_csv = os.path.join(tmpdir, "meteo.csv")
    t = pd.date_range("2000-01-01", periods=30, freq="D")
    precip = np.zeros(30)
    precip[5:10] = [5, 10, 15, 10, 5]  # mm/day pulse
    temp = 12 + 3*np.sin(np.linspace(0, 2*np.pi, 30))
    meteo_df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "precip(mm/day)": precip,
        "temp(C)": temp,
    })
    meteo_df.to_csv(meteo_csv, index=False)

    # Observed discharge (mm/day) — just zeros for the demo
    obs_csv = os.path.join(tmpdir, "discharge.csv")
    obs_df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "Discharge (mm/d)": np.zeros(30),
    })
    obs_df.to_csv(obs_csv, index=False)

    return elev_csv, meteo_csv, obs_csv

if st.button("▶ Run Hydrobricks"):
    with tempfile.TemporaryDirectory() as tmpdir:
        elev_csv, meteo_csv, obs_csv = make_inputs(tmpdir)

        # --- build model ---
        socont = models.Socont(
            soil_storage_nb=2,
            surface_runoff="linear_storage",
            record_all=False
        )

        # Parameters (taken from docs’ style; you can tune)
        params = socont.generate_parameters()
        params.set_values({
            "A": 458,        # degree-day factor snow (example)
            "a_snow": 1.8,   # snowmelt param
            "k_slow_1": 0.9,
            "k_slow_2": 0.8,
            "k_quick": 1.0,
            "percol": 9.8,
        })

        # Hydro units (elevation bands)
        hydro_units = hb.HydroUnits()
        hydro_units.load_from_csv(
            elev_csv,
            area_unit="m2",
            column_elevation="elevation",
            column_area="area",
        )

        # Forcing from station CSV → spatialize temperature & precipitation; compute PET
        forcing = hb.Forcing(hydro_units)
        forcing.load_station_data_from_csv(
            meteo_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"precipitation": "precip(mm/day)", "temperature": "temp(C)"},
        )
        ref_z = 1250
        forcing.spatialize_from_station_data("temperature", ref_elevation=ref_z, gradient=-0.006*1000)  # -0.6°C/100 m
        forcing.correct_station_data("precipitation", correction_factor=0.75)
        forcing.spatialize_from_station_data("precipitation", ref_elevation=ref_z, gradient=0.0005*1000)  # +5%/100 m
        forcing.compute_pet(method="Hamon", use=["t", "lat"], lat=47.3)

        # Observations (optional, for metrics)
        obs = hb.Observations()
        obs.load_from_csv(
            obs_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"discharge": "Discharge (mm/d)"},
        )

        # Setup & run
        outdir = os.path.join(tmpdir, "outputs")
        os.makedirs(outdir, exist_ok=True)
        socont.setup(
            spatial_structure=hydro_units,
            output_path=outdir,
            start_date="2000-01-01",
            end_date="2000-01-30",
        )
        socont.initialize_state_variables(parameters=params, forcing=forcing)
        socont.run(parameters=params, forcing=forcing)

        # Results
        sim_ts = socont.get_outlet_discharge()   # xarray.DataArray (mm/day)
        df = sim_ts.to_dataframe(name="Q_mm_day").reset_index()
        st.line_chart(df.set_index("time")["Q_mm_day"])
        st.success("✅ Hydrobricks run complete.")
