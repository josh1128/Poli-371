# pyswmm_minimal.py
# Requires: pip install pyswmm

from pyswmm import Simulation, Nodes, Links, Subcatchments

# --- 1) Write a very small SWMM input file -------------------------------
inp_text = r"""
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
;;Name   Date       Time     Value(mm/hr)
TS1                00:00     0.0
TS1                00:05     5.0
TS1                00:10     15.0
TS1                00:15     30.0
TS1                00:20     30.0
TS1                00:25     15.0
TS1                00:30     5.0
TS1                00:35     0.0

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
"""

with open("toy_model.inp", "w") as f:
    f.write(inp_text)

# --- 2) Run with PySWMM and access results -------------------------------
with Simulation("toy_model.inp") as sim:
    nodes = Nodes(sim)
    links = Links(sim)
    subs = Subcatchments(sim)

    j1 = nodes["J1"]
    c1 = links["C1"]
    s1 = subs["S1"]

    print("time, subcatch_runoff(L/s), node_depth(m), link_flow(L/s)")
    for step in sim:
        print(f"{sim.current_time}, "
              f"{s1.runoff:6.2f}, "
              f"{j1.depth:5.3f}, "
              f"{c1.flow:6.2f}")

# --- 3) After run, you could also read simple totals if desired ----------
with Simulation("toy_model.inp") as sim:
    sim.execute()  # run once quickly just to access final stats
    # Simple, quick aggregates (example):
    # PySWMM exposes time-step values during iteration; for true reports,
    # parse the .rpt file or accumulate during the loop above.
    print("\nSimulation complete. See printed time series above.")
