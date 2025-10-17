import streamlit as st
from pyswmm import Simulation, Nodes
import tempfile

# --- Streamlit setup ---
st.title("💧 Simple PySWMM Simulation")
st.write("Run a basic SWMM model directly in Streamlit.")

# Example SWMM input (very small)
swmm_inp = """
[TITLE]
;;Project Title/Notes

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
Rain1                         0:00     0.0
Rain1                         0:30     0.2
Rain1                         1:00     0.4
Rain1                         1:30     0.0
Rain1                         2:00     0.0

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

# Write temporary SWMM input file
with tempfile.NamedTemporaryFile(delete=False, suffix=".inp") as tmp:
    tmp.write(swmm_inp.encode())
    tmp_path = tmp.name

if st.button("▶ Run Simulation"):
    st.write("Running simulation... please wait.")
    times, depths = [], []
    with Simulation(tmp_path) as sim:
        node = Nodes(sim)["J1"]
        for step in sim:
            times.append(sim.current_time)
            depths.append(node.depth)

    st.line_chart(depths)
    st.success("✅ Simulation complete!")

