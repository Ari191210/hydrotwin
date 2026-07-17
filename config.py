"""HydroTwin configuration.

Three demo cases are defined in CASES. `python run.py` runs all of them;
`python run.py <case>` runs one. set_case() switches the active basin —
all other modules read the module-level values below at call time.
"""

# ---- Demo cases --------------------------------------------------------
CASES = {
    "rishikesh": {
        "title": "Rishikesh — Ganga exiting the Himalaya",
        "lat": 30.11, "lon": 78.29,
        "pop_density_km2": 1200,   # stated estimate for people-affected calc
        "pois": [
            {"name": "District Hospital", "type": "hospital", "row": 38, "col": 44},
            {"name": "Govt. Senior School", "type": "school", "row": 62, "col": 58},
            {"name": "NH-7 River Bridge", "type": "road", "row": 30, "col": 50},
            {"name": "Station Road Junction", "type": "road", "row": 70, "col": 35},
        ],
    },
    "delhi": {
        "title": "Delhi — Yamuna floodplain",
        "lat": 28.66, "lon": 77.23,
        "pop_density_km2": 12000,
        "pois": [
            {"name": "LNJP Hospital", "type": "hospital", "row": 45, "col": 30},
            {"name": "Govt. School Kashmere Gate", "type": "school", "row": 58, "col": 42},
            {"name": "Ring Road (ISBT)", "type": "road", "row": 50, "col": 55},
            {"name": "Old Iron Bridge Approach", "type": "road", "row": 35, "col": 62},
        ],
    },
    "hue": {
        "title": "Hue, Vietnam — Perfume River",
        "lat": 16.46, "lon": 107.59,
        "pop_density_km2": 2500,
        "pois": [
            {"name": "Hue Central Hospital", "type": "hospital", "row": 52, "col": 40},
            {"name": "Quoc Hoc High School", "type": "school", "row": 44, "col": 34},
            {"name": "Trang Tien Bridge", "type": "road", "row": 48, "col": 52},
            {"name": "QL1A Highway", "type": "road", "row": 65, "col": 60},
        ],
    },
}
DEFAULT_CASES = ["rishikesh", "delhi", "hue"]

# ---- Active basin (set_case overwrites these) ---------------------------
ACTIVE_CASE = "rishikesh"
CASE_TITLE = CASES["rishikesh"]["title"]
BASIN_LAT = CASES["rishikesh"]["lat"]
BASIN_LON = CASES["rishikesh"]["lon"]
POIS = CASES["rishikesh"]["pois"]
POP_DENSITY_KM2 = CASES["rishikesh"]["pop_density_km2"]
OUTPUT_DIR = "outputs/rishikesh"


def set_case(name):
    """Point the whole pipeline at one of the demo cases."""
    global ACTIVE_CASE, CASE_TITLE, BASIN_LAT, BASIN_LON, POIS, \
        POP_DENSITY_KM2, OUTPUT_DIR
    if name not in CASES:
        raise KeyError(f"unknown case '{name}' — choose from {list(CASES)}")
    case = CASES[name]
    ACTIVE_CASE = name
    CASE_TITLE = case["title"]
    BASIN_LAT = case["lat"]
    BASIN_LON = case["lon"]
    POIS = case["pois"]
    POP_DENSITY_KM2 = case["pop_density_km2"]
    OUTPUT_DIR = f"outputs/{name}"
    return case


def set_live_location(lat, lon, title, pois, pop_density_km2=3000,
                      name="live"):
    """Point the pipeline at an arbitrary lat/lon (live server mode).
    Does not touch the CASES preset dict — presets stay as fallback."""
    global ACTIVE_CASE, CASE_TITLE, BASIN_LAT, BASIN_LON, POIS, \
        POP_DENSITY_KM2, OUTPUT_DIR
    ACTIVE_CASE = name
    CASE_TITLE = title
    BASIN_LAT = lat
    BASIN_LON = lon
    POIS = pois
    POP_DENSITY_KM2 = pop_density_km2
    OUTPUT_DIR = f"outputs/{name}"
    return {"lat": lat, "lon": lon, "title": title, "pois": pois,
            "pop_density_km2": pop_density_km2}


# ---- Grid / storm --------------------------------------------------------
GRID_ROWS = 100
GRID_COLS = 100
SIM_DURATION_HR = 6.0      # simulated storm window
SAVE_EVERY_S = 900.0       # snapshot interval (s) -> 24 frames over 6 h

# ---- Physics (Landlab OverlandFlow) ------------------------------------
CELL_SIZE_M = 30.0         # used for synthetic terrain; a real DEM overrides it
MANNINGS_N = 0.03
DT_MAX_S = 30.0            # cap on the adaptive timestep
TEST_RAIN_MM_HR = 30.0     # Phase-1 constant test rainfall

# ---- Rainfall ------------------------------------------------------------
MIN_DEMO_RAIN_MM = 30.0    # if the live forecast totals less than this over the
                           # sim window, use the synthetic design storm instead
WHATIF_MULTIPLIERS = [1.0, 2.0, 3.0]   # storm scenarios simulated per case
RAIN_MULTIPLIER = 2.0      # the default scenario shown (must be in the list)
OPEN_METEO_TIMEOUT_S = 10

# ---- Decisions ------------------------------------------------------------
FLOOD_DEPTH_M = 0.30       # depth that counts as "flooded"
SEVERE_DEPTH_M = 1.00      # depth that counts as "severe"
ZONE_DIV = 4               # grid is split into ZONE_DIV x ZONE_DIV named zones
CLAUDE_MODEL = "claude-sonnet-5"
