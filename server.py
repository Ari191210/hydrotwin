"""HydroTwin live server.

    python server.py           # then open http://localhost:8000

Serves a single-page console. Type any city or lat/lon -> the server geocodes,
fetches global terrain + live rainfall + live river discharge, runs the
Landlab physics, and returns the 3D flood forecast for that exact place.
A live conditions feed polls current weather/river data to the second.

Physics takes ~20-30s per new location, so simulations run as background
jobs with real staged progress; results are cached by coordinate.
"""

import threading
import uuid

from flask import Flask, jsonify, request, Response
from flask_cors import CORS

import engine
from shell import SHELL_HTML

app = Flask(__name__)
CORS(app)

_JOBS = {}          # job_id -> {status, stage, pct, html?, summary?, error?}
_JOBS_LOCK = threading.Lock()


@app.route("/")
def index():
    return Response(SHELL_HTML, mimetype="text/html")


@app.route("/api/geocode")
def geocode():
    """City / place name -> lat,lon via Open-Meteo geocoding (no key)."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "empty query"}), 400
    # accept raw "lat,lon"
    try:
        parts = [float(x) for x in q.replace(" ", "").split(",")]
        if len(parts) == 2 and -90 <= parts[0] <= 90 and -180 <= parts[1] <= 180:
            return jsonify({"results": [{
                "name": f"{parts[0]:.3f}, {parts[1]:.3f}",
                "lat": parts[0], "lon": parts[1], "country": ""}]})
    except ValueError:
        pass
    try:
        import requests
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": q, "count": 5, "language": "en"},
            timeout=(4, 8))
        r.raise_for_status()
        results = []
        for g in r.json().get("results", []):
            label = ", ".join(x for x in (
                g.get("name"), g.get("admin1"), g.get("country")) if x)
            results.append({"name": label, "lat": g["latitude"],
                            "lon": g["longitude"],
                            "country": g.get("country", ""),
                            "population": g.get("population")})
        return jsonify({"results": results})
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502


@app.route("/api/conditions")
def conditions():
    """Per-second live feed: current rainfall + river discharge + time."""
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat & lon required"}), 400
    return jsonify(engine.current_conditions(lat, lon))


@app.route("/api/simulate", methods=["POST"])
def simulate():
    """Start (or reuse) a simulation job for a location. Returns a job id.
    Cached locations resolve instantly."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "lat & lon required"}), 400
    title = data.get("title")
    pop = data.get("pop_density")

    cached = engine.get_cached(lat, lon)
    if cached:
        jid = uuid.uuid4().hex[:12]
        with _JOBS_LOCK:
            _JOBS[jid] = {"status": "done", "stage": "cached", "pct": 100,
                          "html": cached["html"], "summary": cached["summary"]}
        return jsonify({"job_id": jid, "cached": True})

    jid = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[jid] = {"status": "running", "stage": "queued", "pct": 0}
    threading.Thread(target=_run_job, args=(jid, lat, lon, title, pop),
                     daemon=True).start()
    return jsonify({"job_id": jid, "cached": False})


def _run_job(jid, lat, lon, title, pop):
    def progress(stage, pct):
        with _JOBS_LOCK:
            if jid in _JOBS:
                _JOBS[jid].update(stage=stage, pct=pct)
    try:
        res = engine.simulate_location(lat, lon, title=title,
                                       pop_density=pop, progress=progress)
        with _JOBS_LOCK:
            _JOBS[jid].update(status="done", stage="done", pct=100,
                              html=res["html"], summary=res["summary"])
    except Exception as exc:
        import traceback
        traceback.print_exc()
        with _JOBS_LOCK:
            _JOBS[jid].update(status="error",
                              error=f"{type(exc).__name__}: {exc}")


@app.route("/api/job/<jid>")
def job_status(jid):
    """Poll job progress. Omits the (large) html unless status=done and
    ?html=1, so the progress poll stays lightweight."""
    with _JOBS_LOCK:
        job = _JOBS.get(jid)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        out = {k: job[k] for k in ("status", "stage", "pct") if k in job}
        if job.get("status") == "error":
            out["error"] = job.get("error")
        if job.get("status") == "done":
            out["summary"] = job.get("summary")
            if request.args.get("html"):
                out["html"] = job.get("html")
    return jsonify(out)


@app.route("/api/presets")
def presets():
    import config
    return jsonify([{"name": n, "title": c["title"], "lat": c["lat"],
                     "lon": c["lon"], "pop_density": c["pop_density_km2"]}
                    for n, c in config.CASES.items()])


if __name__ == "__main__":
    print("=" * 60)
    print("HydroTwin live server")
    print("  open http://localhost:8000 in your browser")
    print("  type any city or 'lat,lon' -> live flood forecast")
    print("=" * 60)
    app.run(host="0.0.0.0", port=8000, threaded=True, debug=False)
