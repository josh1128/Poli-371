import os
import tempfile
import numpy as np
import pandas as pd
import streamlit as st
import hydrobricks as hb
import hydrobricks.models as models

st.set_page_config(page_title="Hydrobricks minimal (Socont)", layout="centered")
st.title("💧 Hydrobricks minimal (Socont) — visible hydrograph demo")

with st.expander("Environment check"):
    st.write({"hydrobricks_version": getattr(hb, "__version__", "unknown")})
    try:
        import pyet
        st.write({"pyet_version": getattr(pyet, "__version__", "unknown")})
    except Exception as e:
        st.warning(f"pyet import failed: {e}")

st.write(
    "Single hydro unit + station meteo. Stronger storm by default, lower PET, and "
    "robust plotting. If the hydrograph is flat, increase rain or tweak parameters."
)

# ----------------------------
# Helpers
# ----------------------------
def write_hydrounits_csv(path: str):
    with open(path, "w") as f:
        f.write("id,elevation,area\n")
        f.write("-,m,m2\n")
        f.write("1,1200,10000000\n")  # 10 km²

def write_meteo_csv(path: str, scale: float = 1.0, days: int = 60):
    """
    Daily meteo for `days`:
      - Big storm block (10 days) in the middle (20–60 mm/d)
      - Mild temperatures ~ 10–15°C (reduce PET vs hot)
    """
    t = pd.date_range("2000-01-01", periods=days, freq="D")
    precip = np.zeros(days)
    mid = days // 2
    pulse = np.array([20, 30, 40, 60, 40, 30, 25, 20, 15, 10], dtype=float)  # mm/day
    start = max(0, mid - len(pulse)//2)
    precip[start:start+len(pulse)] = pulse * float(scale)
    temp = 12 + 3 * np.sin(np.linspace(0, 2*np.pi, days))  # °C

    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "precip(mm/day)": precip,
        "temp(C)": temp,
    })
    df.to_csv(path, index=False)

def write_obs_csv(path: str, days: int = 60):
    t = pd.date_range("2000-01-01", periods=days, freq="D")
    df = pd.DataFrame({
        "Date": t.strftime("%d/%m/%Y"),
        "Discharge (mm/d)": np.zeros(days),
    })
    df.to_csv(path, index=False)

def safe_set_params(params, values: dict):
    for name, v in values.items():
        v = float(v)
        try:
            span = max(abs(v) * 0.5, 1e-3)
            params.change_range(name, v - span, v + span)
        except Exception:
            pass
    params.set_values(values)

def to_series(obj):
    import pandas as pd
    try:
        import xarray as xr
    except Exception:
        xr = None

    if xr is not None and isinstance(obj, xr.DataArray):
        s = obj.to_series().rename("Q_mm_day")
        if isinstance(s.index, pd.MultiIndex) and "time" in s.index.names:
            s = s.reset_index().set_index("time")["Q_mm_day"]
        return s

    if isinstance(obj, pd.Series):
        return obj.rename("Q_mm_day")

    if isinstance(obj, pd.DataFrame):
        first_col = obj.columns[0]
        return obj[first_col].rename("Q_mm_day")

    try:
        import numpy as np
        if isinstance(obj, (list, tuple)) or isinstance(obj, np.ndarray):
            n = len(obj)
            idx = pd.date_range("2000-01-01", periods=n, freq="D")
            return pd.Series(obj, index=idx, name="Q_mm_day")
    except Exception:
        pass

    return pd.Series([float(obj)], index=pd.date_range("2000-01-01", periods=1), name="Q_mm_day")

# ----------------------------
# UI
# ----------------------------
with st.expander("Adjust parameters (optional)"):
    A = st.slider("Degree-day factor snow (A)", 50.0, 600.0, 200.0, 10.0)
    a_snow = st.slider("Snowmelt parameter (a_snow)", 0.5, 6.0, 3.0, 0.1)
    k_quick = st.slider("Quick reservoir coefficient (k_quick)", 0.2, 2.0, 1.2, 0.1)
    k_slow_1 = st.slider("Slow reservoir 1 coeff (k_slow_1)", 0.2, 2.0, 0.9, 0.1)
    k_slow_2 = st.slider("Slow reservoir 2 coeff (k_slow_2)", 0.2, 2.0, 0.7, 0.1)
    percol = st.slider("Percolation rate (percol)", 0.5, 20.0, 5.0, 0.5)
    rain_scale = st.slider("Rain scale (×)", 0.2, 3.0, 1.0, 0.1)
    lat = st.slider("Latitude for PET (deg)", -60.0, 60.0, 20.0, 0.1)  # lower lat → lower PET
    sim_days = st.slider("Simulation length (days)", 30, 180, 60, 5)

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
        write_meteo_csv(meteo_csv, scale=rain_scale, days=sim_days)
        write_obs_csv(obs_csv, days=sim_days)

        # 2) Hydro units
        hydro_units = hb.HydroUnits()
        hydro_units.load_from_csv(elev_csv)

        # 3) Forcing (no spatialization). Show inputs so you can see what's fed in.
        forcing = hb.Forcing(hydro_units)
        forcing.load_station_data_from_csv(
            meteo_csv,
            column_time="Date",
            time_format="%d/%m/%Y",
            content={"precipitation": "precip(mm/day)", "temperature": "temp(C)"},
        )
        forcing.compute_pet(method="hamon", use=["t", "lat"], lat=float(lat))

        # Preview the forcing we just built (for confidence)
        st.subheader("Inputs (precip & temperature)")
        met = pd.read_csv(meteo_csv)
        met["Date"] = pd.to_datetime(met["Date"], format="%d/%m/%Y")
        st.line_chart(met.set_index("Date")[["precip(mm/day)", "temp(C)"]])

        # 4) Model + parameters (record_all=True to ensure outputs are stored)
        socont = models.Socont(
            soil_storage_nb=2,
            surface_runoff="linear_storage",
            record_all=True,
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
        start_date = "2000-01-01"
        end_date = (pd.to_datetime(start_date) + pd.Timedelta(days=sim_days-1)).strftime("%Y-%m-%d")
        socont.setup(
            spatial_structure=hydro_units,
            output_path=outdir,
            start_date=start_date,
            end_date=end_date,
        )
        socont.initialize_state_variables(parameters=params, forcing=forcing)
        socont.run(parameters=params, forcing=forcing)

        # 7) Results (robust)
        sim_ts = socont.get_outlet_discharge()
        st.write("Return type:", type(sim_ts).__name__)
        series = to_series(sim_ts)

        # Quick nan/flat guard
        series = series.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        max_q = float(series.max()) if len(series) else 0.0
        if max_q <= 1e-6:
            st.info("Hydrograph looks flat. Try ↑ Rain scale, ↑ k_quick, ↓ percol, or longer duration.")

        st.subheader("Outlet discharge (mm/day)")
        st.line_chart(series)
        st.dataframe(series.reset_index().rename(columns={"index": "time", 0: "Q_mm_day"}).head())
        st.success("✅ Run complete.")

