"""Figures for the research paper. Writes PNGs to paper/figures/.

    python make_figures.py
"""

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config
import imagery
import localities
import score_localities
import stagelib
import terrain

OUT = "paper/figures"
CUSEC = 0.0283168
# Hathnikund/Tajewala peak release (cusecs) and peak level at the Old
# Railway Bridge (m). Source: SANDRP, 16 July 2023.
FLOODS = [(1978, 709000, 207.49), (1988, 577522, 206.92),
          (1995, 536188, 206.93), (2008, 409576, 206.00),
          (2010, 744507, 207.11), (2013, 806464, 207.32),
          (2018, 503925, 206.05), (2019, 828000, 206.60),
          (2023, 359760, 208.66)]
INK, DIM, BLUE, RED, GREY = "#16202c", "#5b6b7d", "#1f6fd1", "#d8433b", "#9aa7b5"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": DIM, "axes.labelcolor": INK,
                     "xtick.color": DIM, "ytick.color": DIM,
                     "figure.dpi": 160, "savefig.bbox": "tight"})


def fig_release_vs_level():
    yr = np.array([f[0] for f in FLOODS])
    q = np.array([f[1] for f in FLOODS]) * CUSEC
    lv = np.array([f[2] for f in FLOODS])
    old = yr != 2023
    a, b = np.polyfit(q[old], lv[old], 1)
    r_old = np.corrcoef(q[old], lv[old])[0, 1]
    r_all = np.corrcoef(q, lv)[0, 1]
    pred = a * q[~old][0] + b
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    xs = np.linspace(8000, 25000, 10)
    ax.plot(xs, a * xs + b, color=GREY, lw=1.5, zorder=1)
    ax.scatter(q[old], lv[old], s=46, color=BLUE, zorder=3)
    ax.scatter(q[~old], lv[~old], s=90, color=RED, zorder=4)
    for y, x, l in zip(yr[old], q[old], lv[old]):
        ax.annotate(str(y), (x, l), xytext=(6, 5), textcoords="offset points",
                    color=DIM, fontsize=9)
    ax.annotate("2023\nrecord level,\nsmallest release", (q[~old][0], 208.66),
                xytext=(14, -34), textcoords="offset points", color=RED,
                fontsize=10, fontweight="bold")
    ax.plot([q[~old][0]] * 2, [pred, 208.66], color=RED, lw=1, ls=":")
    ax.annotate(f"{208.66 - pred:.2f} m above\nthe trend", (q[~old][0],
                (pred + 208.66) / 2), xytext=(8, -6),
                textcoords="offset points", color=RED, fontsize=9)
    ax.annotate(f"trend of the eight earlier floods (r = {r_old:.2f})",
                (17500, a * 17500 + b), xytext=(0, -22),
                textcoords="offset points", color=DIM, fontsize=9)
    ax.set_xlabel("Peak barrage release at Hathnikund (m³/s)")
    ax.set_ylabel("Peak level at Old Railway Bridge, Delhi (m)")
    ax.set_title("A bigger release did not mean a higher flood in 2023",
                 loc="left", color=INK, fontsize=13, fontweight="bold")
    fig.savefig(f"{OUT}/fig1_release_vs_level.png")
    plt.close(fig)
    return {"r_eight": round(float(r_old), 2), "r_all": round(float(r_all), 2),
            "predicted_2023_m": round(float(pred), 2),
            "miss_m": round(float(208.66 - pred), 2)}


def fig_rating():
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    out = {}
    for dem, col, name in (("srtm", BLUE, "SRTM (rooftops)"),
                           ("fabdem", "#e08a1e", "FABDEM (bare earth)")):
        lib = stagelib.Library(dem)
        ax.plot(lib.q, lib.stage, "-o", color=col, ms=4, lw=1.8, label=name)
        _, q = lib.depth_at_stage(208.66)
        out[dem] = round(q)
        ax.scatter([q], [208.66], s=70, color=col, zorder=5, edgecolor="white")
    ax.axhline(208.66, color=RED, lw=1, ls="--")
    ax.annotate("2023 record 208.66 m", (300, 208.66), xytext=(0, 5),
                textcoords="offset points", color=RED, fontsize=9)
    ax.axvline(359760 * CUSEC, color=GREY, lw=1, ls=":")
    ax.annotate("2023 peak release\nat the barrage", (359760 * CUSEC, 202.8),
                xytext=(6, 0), textcoords="offset points", color=DIM,
                fontsize=9)
    ax.set_xlabel("Steady river flow in the model (m³/s)")
    ax.set_ylabel("Model level at Old Railway Bridge (m)")
    ax.set_title("Flow the model needs to reach a given river level",
                 loc="left", color=INK, fontsize=13, fontweight="bold")
    ax.legend(frameon=False, loc="lower right")
    fig.savefig(f"{OUT}/fig2_rating_curves.png")
    plt.close(fig)
    return out


def fig_scores(scores):
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.9), sharey=True)
    for ax, s in zip(axes, scores):
        labels = ["Hydraulic\nmodel", "Bathtub\nrule"]
        hits = [s["model"]["hits"], s["bathtub"]["hits"]]
        fa = [s["model"]["false_alarms"], s["bathtub"]["false_alarms"]]
        x = np.arange(2)
        ax.bar(x - .19, hits, .36, color=BLUE, label="flooded places caught (of 7)")
        ax.bar(x + .19, fa, .36, color=RED, label="false alarms (of 10)")
        ax.tick_params(axis="x", pad=2)
        for i in range(2):
            ax.text(x[i] - .19, hits[i] + .12, str(hits[i]), ha="center",
                    color=INK, fontweight="bold")
            ax.text(x[i] + .19, fa[i] + .12, str(fa[i]), ha="center",
                    color=INK, fontweight="bold")
            csi = [s["model"]["csi"], s["bathtub"]["csi"]][i]
            ax.text(x[i], -1.75, f"CSI {csi:.2f}", ha="center", color=DIM,
                    fontsize=10)
        ax.set_xticks(x, labels)
        ax.set_ylim(0, 8.2)
        ax.set_title({"srtm": "SRTM (default)", "fabdem":
                      "FABDEM (bare earth)"}[s["dem"]], color=INK, fontsize=11)
    axes[0].set_ylabel("localities")
    fig.legend(*axes[0].get_legend_handles_labels(), frameon=False,
               fontsize=9, loc="lower center", ncol=2,
               bbox_to_anchor=(.5, -.2))
    fig.suptitle("Tested at the 2023 record level on 17 localities",
                 x=0.07, ha="left", color=INK, fontsize=13, fontweight="bold",
                 y=1.04)
    fig.savefig(f"{OUT}/fig4_scores.png")
    plt.close(fig)


def fig_map(dem="srtm"):
    lib = stagelib.Library(dem)
    depth, _ = lib.depth_at_stage(208.66)
    config.set_case("delhi")
    rows, cols = depth.shape
    sat = imagery.get_imagery(rows, cols)
    d = score_localities.site_depths(lib, depth)
    fig, ax = plt.subplots(figsize=(7.4, 7.4))
    ext = (0, cols, 0, rows)
    if sat is not None:
        ax.imshow(np.asarray(sat.convert("RGB")), extent=ext, alpha=.78)
    ax.imshow(np.ma.masked_less(depth, 0.05), origin="lower", extent=ext,
              cmap="Blues", vmin=-1.5, vmax=6, alpha=.82)
    style = {("river", True): ("o", BLUE, "flooded in 2023, flooded in model"),
             ("river", False): ("X", RED, "flooded in 2023, missed"),
             ("dry", True): ("^", "#ff9f1c", "no flood report, flooded in model"),
             ("dry", False): ("o", "white", "no flood report, dry in model"),
             ("drain", True): ("s", GREY, "drain flooding (not scored)"),
             ("drain", False): ("s", GREY, "drain flooding (not scored)")}
    seen = set()
    for name, lat, lon, label, src in localities.LOCALITIES:
        wet = d[name][0] >= 0.30
        r, c = d[name][1]
        m, col, lab = style[(label, wet)]
        ax.scatter([c + .5], [r + .5], marker=m, s=95, color=col,
                   edgecolor="black", linewidth=1.1, zorder=5,
                   label=None if lab in seen else lab)
        seen.add(lab)
        ax.annotate(name, (c + .5, r + .5), xytext=(7, 4),
                    textcoords="offset points", fontsize=7.5, color="white",
                    bbox=dict(boxstyle="round,pad=.15", fc="black", ec="none",
                              alpha=.6))
    ax.set_xlim(0, cols); ax.set_ylim(0, rows)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    km = 1000 / lib.cell
    ax.plot([6, 6 + 2 * km], [5, 5], color="white", lw=3)
    ax.text(6 + km, 7.5, "2 km", color="white", ha="center", fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.01), ncol=2,
              fontsize=8.5, frameon=False)
    ax.set_title("Model water at 208.66 m (river only) and the 2023 record",
                 loc="left", color=INK, fontsize=12.5, fontweight="bold")
    fig.savefig(f"{OUT}/fig3_map_{dem}.png")
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    stats = {"release_vs_level": fig_release_vs_level(),
             "flow_at_record_m3s": fig_rating()}
    scores = [score_localities.score(d, quiet=True) for d in ("srtm", "fabdem")]
    fig_scores(scores)
    fig_map("srtm")
    fig_map("fabdem")
    stats["scores"] = scores
    with open("paper/results.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps({k: stats[k] for k in ("release_vs_level",
                                            "flow_at_record_m3s")}))
