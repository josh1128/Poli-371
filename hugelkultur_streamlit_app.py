import streamlit as st
from pyswmm import Simulation, Nodes
import tempfile
import os
import datetime as dt

st.set_page_config(page_title="PySWMM Minimal", layout="centered")
st.title("💧 Simple PySWMM Simulation (Minimal)")

st.write(
    "This runs a tiny SWMM model (1 subcatchment → 1 junction → outfall) "
    "and plots junction depth over time."
)

# Very small SWMM input file
SWMM_INP = """
[TITLE]
;; Minimal test model

[OPTIONS]
FLOW_UNITS            CFS
INFILTRATION          HORTON
FLOW_ROUTING          DYNWAVE
START_DATE            01/01/2000
START_TIME            00:00:00
REPORT_START_DATE     01/01/2000
REPORT_START_TIME     00:00:00
END_DATE              01/01/2000
END_TIME              02:00:00
SWEEP_START           01/01
SWEEP_END             12/31
DRY_DAYS              0
REPORT_STEP           00:05:00
WET_STEP              00:05:00
DRY_STEP              01:00:00
ROUTING_STEP          00:01:00

[RAINGAGES]
;;Name           Format    Interval SCF  Source
Gage1            VOLUME    0:05     1.0  TIMESERIES Rain1

[TIMESERIES]
;;Name           Date       Time     Value
Rain1                         00:00     0.0
Rain1                         00:30     0.2
Rain1                         01:00     0.4
Rain1                         01:30     0.0
Rain1                         02:00     0.0

[SUBCATCHMENTS]
;;Name   Raingage   Outlet   Area   %Imperv  Width  Slope  CurbLen  SnowPack
S1       Gage1      J1       10     50       1000   0.01   0

[SUBAREAS]
;;Subcatchment   N-Imperv   N-Perv   S-Imperv   S-Perv   %Zero   RouteTo
S1               0.01       0.1      0.05       0.05     25      OUTLET

[INFILTRATION]
;;Subcatchment   MaxRate   MinRate   Decay   DryTime   MaxInfil
S1               3.5       0.5       4.0     7.0       0

[JUNCTIONS]
;;Name  Elevation  MaxDepth  InitDepth  SurDepth  Aponded
J1      0          5         0          0         0

[OUTFALLS]
;;Name  Elevation  Type       Stage Data
Out1    0          FREE

[CONDUITS]
;;Name  FromNode  ToNode  Length  Roughness  InOffset  OutOffset  InitFlow  MaxFlow
C1      J1        Out1    400     0.013      0         0          0         0

[XSECTIONS]
;;Link  Shape   Geom1   Geom2  Geom3  Geom4  Barrels
C1      CIRCULAR  1.0     0      0      0      1

[REPORT]
INPUT      NO
CONTROLS   NO
SUBCATCHMENTS ALL
NODES ALL
LINKS ALL

[END]
"""

st.code("Python interpreter must be 3.10 or 3.11 for swmm-toolkit wheels.", language="text")

run = st.button("▶ Run Simulation")

if run:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = os.path.join(tmpdir, "model.inp")
            rpt_path = os.path.join(tmpdir, "model.rpt")
            out_path = os.path.join(tmpdir, "model.out")

            with open(inp_path, "w") as f:
                f.write(SWMM_INP)

            st.info("Running SWMM…")
            times = []
            depths = []

            # Explicitly pass report/output so the toolkit can write files
            with Simulation(inp_path, rpt_path, out_path) as sim:
                node = Nodes(sim)["J1"]
                for _ in sim:
                    # current_time is a datetime; use string to chart easily
                    times.append(sim.current_time.strftime("%H:%M"))
                    depths.append(node.depth)

            # Show results
            st.subheader("J1 Depth over time")
            st.line_chart({"Depth (ft)": depths}, x=times)
            st.success("✅ Simulation complete")

            with open(rpt_path, "r", errors="ignore") as f:
                rpt_preview = "".join(list(f)[:80])
            st.expander("Report preview").write(rpt_preview)

    except Exception as e:
        st.error(
            "SWMM failed to open/run. The most common cause is an **unsupported Python "
            "version** for `swmm-toolkit`. Make sure you are on Python 3.10 or 3.11."
        )
        st.exception(e)
