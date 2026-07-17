"""HydroTwin configuration.

Everything the demo depends on is set here. Edit this block to retarget
the basin, resize the grid, or change the storm length.
"""

# ---- Basin ------------------------------------------------------------
BASIN_LAT = 30.11          # Rishikesh, India — the Ganga exiting the Himalaya
BASIN_LON = 78.29
GRID_ROWS = 100
GRID_COLS = 100
SIM_DURATION_HR = 6.0      # simulated storm window
SAVE_EVERY_S = 900.0       # snapshot interval (s) -> 24 frames over 6 h

# ---- Physics (Landlab OverlandFlow) ------------------------------------
CELL_SIZE_M = 30.0         # used for synthetic terrain; a real DEM overrides it
MANNINGS_N = 0.03
DT_MAX_S = 30.0            # cap on the adaptive timestep
TEST_RAIN_MM_HR = 30.0     # Phase-1 constant test rainfall

# ---- Rainfall (Phase 2) -------------------------------------------------
MIN_DEMO_RAIN_MM = 30.0    # if the live forecast totals less than this over the
                           # sim window, use the synthetic design storm instead
RAIN_MULTIPLIER = 1.0      # scale factor applied to whichever series is used
OPEN_METEO_TIMEOUT_S = 10

# ---- Decisions (Phase 3) ------------------------------------------------
FLOOD_DEPTH_M = 0.30       # depth that counts as "flooded"
SEVERE_DEPTH_M = 1.00      # depth that counts as "severe"
ZONE_DIV = 4               # grid is split into ZONE_DIV x ZONE_DIV named zones
CLAUDE_MODEL = "claude-sonnet-5"

# Points of interest, in grid coordinates (row 0 = south edge).
POIS = [
    {"name": "District Hospital", "type": "hospital", "row": 38, "col": 44},
    {"name": "Govt. Senior School", "type": "school", "row": 62, "col": 58},
    {"name": "NH-7 River Bridge", "type": "road", "row": 30, "col": 50},
    {"name": "Station Road Junction", "type": "road", "row": 70, "col": 35},
]

# ---- Output --------------------------------------------------------------
OUTPUT_DIR = "outputs"
