# streamlit_pyswmm_min.py
# Streamlit-friendly PySWMM demo: writes files into a temp dir and runs safely.
# requirements.txt (recommended pins below in this message)

import os, textwrap
import streamlit as st
from tempfile import TemporaryDirectory
from pyswmm import Simulation, Nodes, Links, Subcatchments

st.set_page_config(page_title="PySWMM Minimal", layout="centered")
st.title("PySWMM Minimal – Tempdir-safe run")

# --- Small controls just to vary something ---
storm_peak = st.slider("Peak intensity (mm/hr)", 10, 60, 30, 5)

# --- Build an INP string (tiny model) ---
inp_text = textwrap.dedent(f"""
[TITLE]
;; Simple 1-subcatchment → junction → outfall model

[OPTIONS]
FLOW_UNITS              LPS
INFILTRATION            HORTON
FLOW_ROUTING            KINWAVE
START_DATE              01/01/2020
START_TIME              00:00:00
REPORT_START_DATE       01/01/2020
REPORT_START_TIME       00:00:00
END_DATE                01/01/2020
END_TIME                06:00:00
SWEEP_START             01/01
SWEEP_END               12/31
DRY_DAYS                0
REPORT_STEP             00:15:00
WET_STEP                00:05:00
DRY_STEP                01:00:00
ROUTING_STEP            00:01:00

[RAINGAGES]
;;Name           Format     Interval SCF   Source
RG1              INTENSITY  0:05      1.0   TIMESERIES TS1

[TIMESERIES]
;;Name   Date   Time     Value(mm/hr)
TS1             00:00    0.0
TS1             00:05    {storm_peak/3:.1f}
TS1             00:10    {storm_peak:.1f}
TS1             00:15    {storm_peak:.1f}
TS1             00:20    {storm_peak/3:.1f}
TS1             00:25    0.0

[SUBCATCHMENTS]
;;Name     Raingage  Outlet  Area   %Imperv   Width  %Slope  CurbLen  Snowpack
S1         RG1       J1      0.50   40        50     2       0

[SUBAREAS]
;;Subcatch  N-Imperv   N-Perv   S-Imperv  S-Perv   %Zero %RouteTo   PctRouted
S1          0.015      0.24     1.5       6.0      25    OUTLET     0

[INFILTRATION]
;;Subcatch   MaxRate  MinRate  Decay  DryTime  MaxInfil
S1           25       5        4      7        0

[JUNCTIONS]
;;Name   Elevation  MaxDepth  InitDepth  SurDepth  Aponded
J1       100.0      2.0       0.0        0.5       0

[OUTFALLS]
;;Name   Elevation  Type       Stage Data     Gated
O1       99.5       FREE                        NO

[CONDUITS]
;;Name  FromNode  ToNode  Length  Roughness  InOffset  OutOffset  InitFlow  MaxFlow
C1      J1        O1      50      0.013      0         0          0         0

[XSECTIONS]
;;Link  Shape     Geom1  Geom2  Geom3  Geom4  Barrels  Culvert
C1      CIRCULAR  0.6    0      0      0      1

[REPORT]
INPUT      NO
CONTROLS   NO
SUBCATCHMENTS ALL
NODES        ALL
LINKS        ALL

[END]
""").strip()

# --- Run in a temp directory (writable in Streamlit Cloud) ---
with TemporaryDirectory() as tmp:
    inp_path = os.path.join(tmp, "toy_model.inp")
    rpt_path = os.path.join(tmp, "toy_model.rpt")
    out_path = os.path.join(tmp, "toy_model.out")
    with open(inp_path, "w") as f:
        f.write(inp_text)

    st.code(f"Working dir: {tmp}\nFiles will be:\n{inp_path}\n{rpt_path}\n{out_path}")

    try:
        with Simulation(inp_path, rpt_path, out_path) as sim:
            nodes = Nodes(sim)
            links = Links(sim)
            subs = Subcatchments(sim)
            j1 = nodes["J1"]; c1 = links["C1"]; s1 = subs["S1"]

            rows = []
            for _ in sim:
                rows.append((str(sim.current_time), round(s1.runoff,2),
                             round(j1.depth,3), round(c1.flow,2)))

        st.success("Simulation completed.")
        st.write("time, subcatch_runoff(L/s), node_depth(m), link_flow(L/s)")
        st.dataframe(rows, use_container_width=True)

        # If the engine wrote a report, show the tail for debugging
        if os.path.exists(rpt_path):
            with open(rpt_path, "r", errors="ignore") as fr:
                tail = "".join(fr.readlines()[-120:])
            with st.expander("SWMM report tail (debug)"):
                st.text(tail)

    except Exception as e:
        st.error("SWMM failed to open/run. See details below.")
        st.exception(e)
        # If an RPT was created, errors/warnings are often at the end:
        if os.path.exists(rpt_path):
            with open(rpt_path, "r", errors="ignore") as fr:
                tail = "".join(fr.readlines()[-200:])
            with st.expander("SWMM report tail (debug)"):
                st.text(tail)

