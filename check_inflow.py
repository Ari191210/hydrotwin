"""Sanity check for the river-inflow source term.

Steady discharge Q down a walled rectangular channel of slope S should
settle at Manning's normal depth h = (Q n / (W sqrt(S)))^(3/5). Also checks
mass balance. Run: .venv/Scripts/python check_inflow.py
"""

import numpy as np

import config
import simulate

ROWS, COLS, CELL, SLOPE, Q = 80, 30, 30.0, 0.001, 500.0

y = np.arange(ROWS, dtype=float)[:, None] * CELL
elev = np.repeat(SLOPE * y, COLS, axis=1)       # rises to the north
elev[:, 0] += 100.0                             # walls
elev[:, -1] += 100.0

span = range(1, COLS - 1)
inflow = {
    "nodes": [(ROWS - 1 - d) * COLS + k
              for d in range(1, config.INFLOW_DEPTH_ROWS + 1) for k in span],
    "closed": [(ROWS - 1) * COLS + k for k in range(COLS)],
}
times, depths = simulate.run_simulation(
    elev, CELL, lambda t: 0.0, duration_s=8 * 3600.0, save_every_s=3600.0,
    inflow=inflow, inflow_m3s_at=lambda t: Q)

width = (COLS - 2) * CELL
expected = (Q * config.MANNINGS_N / (width * SLOPE ** 0.5)) ** 0.6
mid = depths[-1][ROWS // 3:2 * ROWS // 3, 1:-1]
got = float(mid.mean())
print(f"normal depth: expected {expected:.3f} m, model {got:.3f} m "
      f"({(got / expected - 1) * 100:+.1f}%), spread {mid.std():.3f} m")
print("last two snapshots mid-reach mean:",
      [round(float(d[ROWS // 3:2 * ROWS // 3, 1:-1].mean()), 3)
       for d in depths[-2:]])
