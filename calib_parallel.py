import sys
from concurrent.futures import ProcessPoolExecutor

import backtest_delhi as bt

if __name__ == "__main__":
    qs = [float(x) for x in sys.argv[1:]]
    with ProcessPoolExecutor(max_workers=len(qs)) as ex:
        for q, stage in ex.map(bt.calib_trial, qs):
            print(f"peak_q={q:.0f}  ORB stage={stage:.3f} m  "
                  f"(target {bt.OBSERVED_ORB_M})", flush=True)
