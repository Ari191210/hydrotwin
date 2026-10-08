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
        # POIs by lat/lon (OSM Overpass, 2026-10-08); snapped to grid cells.
        # OSM maps no school inside this window, so none is listed. The two
        # bridges are unnamed in OSM: labels = road ref + river crossed.
        "pois": [
            {"name": "S.P.S Government Hospital", "type": "hospital",
             "lat": 30.10873, "lon": 78.29593},     # way/742423053
            {"name": "Nirmal Ashram Hospital", "type": "hospital",
             "lat": 30.10444, "lon": 78.30327},     # way/743357867
            {"name": "NH7 Chandrabhaga Bridge", "type": "road",
             "lat": 30.10867, "lon": 78.30156},     # way/102676805
            {"name": "NH34 Chandrabhaga Bridge", "type": "road",
             "lat": 30.11699, "lon": 78.28626},     # way/1094021117
            {"name": "Gaura Devi Chowk", "type": "road",
             "lat": 30.11412, "lon": 78.28381},     # node/10963006065
        ],
    },
    "delhi": {
        "title": "Delhi — Yamuna floodplain",
        # ~10 km box from Majnu ka Tilla (N) to ITO (S): zoom 11 = ~67 m cells
        "lat": 28.665, "lon": 77.240,
        "zoom": 11, "grid": (150, 150),
        # Yamuna enters across the north edge just below Wazirabad / the
        # Signature Bridge (OSM centreline 28.7100, 77.2314); snapped to the DEM bed
        "inflow": {"lat": 28.710, "lon": 77.2314, "name": "Yamuna"},
        "pop_density_km2": 12000,
        # POIs by lat/lon (OSM Nominatim, 2026-10-07); snapped to grid cells
        "pois": [
            {"name": "Yamuna Bazar", "type": "road",
             "lat": 28.6620, "lon": 77.2394},
            {"name": "Kashmere Gate ISBT", "type": "road",
             "lat": 28.6687, "lon": 77.2304},
            {"name": "Majnu ka Tilla", "type": "school",
             "lat": 28.7043, "lon": 77.2245},
            {"name": "Red Fort (Ring Road)", "type": "road",
             "lat": 28.6561, "lon": 77.2408},
            {"name": "ITO", "type": "road", "lat": 28.6282, "lon": 77.2410},
        ],
    },
    "hue": {
        "title": "Hue, Vietnam — Perfume River",
        "lat": 16.46, "lon": 107.59,
        "pop_density_km2": 2500,
        # POIs by lat/lon (OSM Overpass, 2026-10-08); snapped to grid cells.
        # Names are OSM name:en, shortened / ASCII-folded where noted.
        "pois": [
            {"name": "Hue Central Hospital", "type": "hospital",
             "lat": 16.46220, "lon": 107.58710},    # way/438257497
            {"name": "Quoc Hoc High School", "type": "school",
             "lat": 16.45954, "lon": 107.58380},    # way/695775622 (shortened)
            {"name": "Phu Xuan Bridge (QL1)", "type": "road",
             "lat": 16.46563, "lon": 107.58508},    # way/39419121
            {"name": "Truong Tien Bridge", "type": "road",
             "lat": 16.46895, "lon": 107.58879},    # way/1431129413 (ASCII)
        ],
    },
}
DEFAULT_CASES = ["rishikesh", "delhi", "hue"]

# ---- Active basin (set_case overwrites these) ---------------------------
# Per-case grid defaults (a case may override zoom/grid; live mode resets)
DEFAULT_GRID = (100, 100)
DEFAULT_ZOOM = 12          # AWS terrarium zoom: 12 = ~30 m cells, 11 = ~60 m

ACTIVE_CASE = "rishikesh"
CASE_TITLE = CASES["rishikesh"]["title"]
BASIN_LAT = CASES["rishikesh"]["lat"]
BASIN_LON = CASES["rishikesh"]["lon"]
POIS = CASES["rishikesh"]["pois"]
POP_DENSITY_KM2 = CASES["rishikesh"]["pop_density_km2"]
OUTPUT_DIR = "outputs/rishikesh"
GRID_ROWS, GRID_COLS = DEFAULT_GRID
TERRAIN_ZOOM = DEFAULT_ZOOM
INFLOW = None              # {"lat","lon","name"} where a river enters, or None


def set_case(name):
    """Point the whole pipeline at one of the demo cases."""
    global ACTIVE_CASE, CASE_TITLE, BASIN_LAT, BASIN_LON, POIS, \
        POP_DENSITY_KM2, OUTPUT_DIR, GRID_ROWS, GRID_COLS, TERRAIN_ZOOM, INFLOW
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
    GRID_ROWS, GRID_COLS = case.get("grid", DEFAULT_GRID)
    TERRAIN_ZOOM = case.get("zoom", DEFAULT_ZOOM)
    INFLOW = case.get("inflow")
    return case


def set_live_location(lat, lon, title, pois, pop_density_km2=3000,
                      name="live"):
    """Point the pipeline at an arbitrary lat/lon (live server mode).
    Does not touch the CASES preset dict — presets stay as fallback."""
    global ACTIVE_CASE, CASE_TITLE, BASIN_LAT, BASIN_LON, POIS, \
        POP_DENSITY_KM2, OUTPUT_DIR, GRID_ROWS, GRID_COLS, TERRAIN_ZOOM, INFLOW
    ACTIVE_CASE = name
    CASE_TITLE = title
    BASIN_LAT = lat
    BASIN_LON = lon
    POIS = pois
    POP_DENSITY_KM2 = pop_density_km2
    OUTPUT_DIR = f"outputs/{name}"
    # a preset's grid/inflow must never leak into a live run
    GRID_ROWS, GRID_COLS = DEFAULT_GRID
    TERRAIN_ZOOM = DEFAULT_ZOOM
    INFLOW = None
    return {"lat": lat, "lon": lon, "title": title, "pois": pois,
            "pop_density_km2": pop_density_km2}


# ---- Storm ----------------------------------------------------------------
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
RAIN_MULTIPLIER = 1.0      # the default scenario shown: the forecast as issued
OPEN_METEO_TIMEOUT_S = 10

# ---- River inflow ---------------------------------------------------------
INFLOW_SEARCH_M = 600.0    # snap the inflow point to the lowest edge cell within this
INFLOW_CHANNEL_DZ_M = 2.0  # edge cells within this of the channel bed take inflow
INFLOW_MAX_CELLS = 25      # cap on the inflow span along the edge
INFLOW_DEPTH_ROWS = 5      # inflow is spread this many rows into the domain
INFLOW_MAX_DH_M = 0.25     # cap on depth added to an inflow cell in one step

# ---- River channel conditioning (cases with an inflow point only) --------
CHANNEL_CONDITIONING = True      # cut the DEM thalweg to a non-increasing bed (river.condition_channel); False = raw DEM as before
CHANNEL_PATH_DIST_WEIGHT = 5e-4  # thalweg search: m of climb charged per m travelled (0.5 m/km)
CHANNEL_MIN_SLOPE = 0.0          # extra bed drop per m along the thalweg (0 = plain running minimum)
CHANNEL_SILL_MIN_M = 0.3         # bed highs smaller than this are not reported as sills

# ---- River baseline, bankfull footprint, warm start (inflow cases only) ---
# Routed discharge = GloFAS forecast above q_dem_baseline (February median:
# the flow the February-2000 SRTM surface already holds). The river's own
# footprint = every cell wet at steady state under the bankfull discharge
# (median annual maximum) above that baseline; it never counts as flooding.
BANKFULL_WET_M = 0.05      # steady-state depth that counts as "the river is here"
STEADY_TOL = 0.02          # steady state: outflow within this fraction of inflow
STEADY_MAX_HOURS = 96.0    # cap on simulated hours for a steady-state run
SPINUP_Q_STEP_M3S = 5.0    # warm starts are computed and cached at the routed discharge rounded to this

# ---- Decisions ------------------------------------------------------------
FLOOD_DEPTH_M = 0.30       # depth that counts as "flooded"
SEVERE_DEPTH_M = 1.00      # depth that counts as "severe"
ZONE_DIV = 4               # grid is split into ZONE_DIV x ZONE_DIV named zones
CLAUDE_MODEL = "claude-sonnet-5"
