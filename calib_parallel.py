"""Parallel calibration trials: `calib_parallel.py [--save-every-h H] q1 q2 ...`

The ORB stage is the peak over SAVED frames, so it depends on the save
cadence (default 24 h here). Use --save-every-h 6 to match score_backtest.py.
"""
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import backtest_delhi as bt

if __name__ == "__main__":
    args = sys.argv[1:]
    save_h = 24.0
    if "--save-every-h" in args:
        i = args.index("--save-every-h")
        save_h = float(args[i + 1])
        del args[i:i + 2]
    conditioned = "--conditioned" in args   # post-hoc variant, see the prereg
    if conditioned:
        args.remove("--conditioned")
    qs = [float(x) for x in args]
    print(f"saving every {save_h:g} h"
          + (", CONDITIONED river bed (post-hoc variant)" if conditioned
             else ""), flush=True)
    trial = partial(bt.calib_trial, save_every_h=save_h,
                    conditioned=conditioned)
    with ProcessPoolExecutor(max_workers=len(qs)) as ex:
        for q, stage in ex.map(trial, qs):
            print(f"peak_q={q:.0f}  ORB stage={stage:.3f} m  "
                  f"(target {bt.OBSERVED_ORB_M})", flush=True)
