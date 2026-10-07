"""Field-report triage with Laya (NandhaKishorM/laya).

The physics decides where water goes; it cannot read what people on the
ground are saying. This layer reads free-text field reports in any language
(English, Hindi, Hinglish, Vietnamese, ...) and turns each into a typed
triage record in one forward pass: need, urgency, trapped / rising water /
vulnerable people, and which mapped point of interest it mentions.

Fusion rule: reports can only ESCALATE a zone's physics-derived priority,
never lower it, so a misread report cannot hide real flooding.

The Router loads in a background thread at server start; until it is ready
(or if torch / the checkpoints are missing) the layer reports its status and
everything else keeps working.
"""

import os
import threading
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")   # checkpoints are cached locally

_ROUTER = None
_STATUS = {"state": "idle", "detail": ""}      # idle|loading|ready|unavailable
_LOAD_LOCK = threading.Lock()
_PREDICT_LOCK = threading.Lock()

NEED_Q = {
    "type": "choice",
    "instructions": "What does the person sending this flood report need?",
    "criteria": {
        "rescue": "people trapped or stranded by water, need a boat or evacuation",
        "medical": "injury, illness, pregnancy or medicine needed",
        "supplies": "food, drinking water or shelter needed",
        "infrastructure": "road, bridge, power line or embankment damaged or blocked",
        "observation": "water level or rain report, nobody in danger",
        "irrelevant": "not about the flood",
    },
}
URGENCY_Q = {
    "type": "score",
    "instructions": "How urgent is this flood report?",
    "criteria": ["no danger", "needs help today", "life in danger right now"],
}
FLAG_QS = {
    "trapped": {"type": "noul", "instructions":
                "Are people trapped, stranded or unable to leave because of water?"},
    "rising": {"type": "noul", "instructions":
               "Does the report say the water is still rising or coming in?"},
    "vulnerable": {"type": "noul", "instructions":
                   "Are children, elderly, pregnant, disabled or sick people involved?"},
}
FLAG_THRESHOLD = 0.5
PLACE_CONFIDENCE = 0.6


def status():
    return dict(_STATUS)


def start_loading():
    """Kick off the Router load in the background. Safe to call repeatedly."""
    with _LOAD_LOCK:
        if _STATUS["state"] in ("loading", "ready"):
            return
        _STATUS.update(state="loading", detail="loading Laya checkpoints")
    threading.Thread(target=_load, daemon=True).start()


def _load():
    global _ROUTER
    t0 = time.time()
    try:
        from laya import Router
        router = Router()
        router.preload(["english", "multilingual"])
        _ROUTER = router
        _STATUS.update(state="ready",
                       detail=f"english + multilingual loaded in "
                              f"{time.time() - t0:.0f} s")
    except Exception as exc:
        _STATUS.update(state="unavailable",
                       detail=f"{type(exc).__name__}: {exc}")
    print(f"[laya] {_STATUS['state']}: {_STATUS['detail']}")


def triage(text, pois):
    """Classify one report. Returns a dict, or raises RuntimeError when the
    model isn't ready. `pois` is the current location's POI list."""
    if _ROUTER is None:
        raise RuntimeError(f"Laya {_STATUS['state']}: {_STATUS['detail']}")

    questions = {"need": NEED_Q, "urgency": URGENCY_Q, **FLAG_QS}
    names = [p["name"] for p in pois]
    if names:
        questions["place"] = {
            "type": "choice",
            "instructions": "Which of these places does the report mention?",
            "criteria": {**{n: p["type"] for n, p in zip(names, pois)},
                         "none": "no listed place is mentioned"},
        }

    t0 = time.perf_counter()
    with _PREDICT_LOCK:
        res = _ROUTER.predict({"field_report": text}, questions)
    ms = round((time.perf_counter() - t0) * 1000)
    a = res["answers"]

    flags = [k for k in FLAG_QS if a[k]["noul"] >= FLAG_THRESHOLD]
    urgency = float(a["urgency"]["score"])       # ~0 (none) .. ~2 (life)
    need = a["need"]["choice"]

    poi, suggested = _match_place(text, pois, a.get("place"))

    return {
        "text": text,
        "need": need,
        "need_confidence": round(float(a["need"]["confidence"]), 2),
        "urgency": round(urgency, 2),
        "flags": flags,
        "flag_probs": {k: round(float(a[k]["noul"]), 2) for k in FLAG_QS},
        "poi": poi["name"] if poi else None,
        "zone": poi["zone"] if poi else None,
        "suggested_poi": suggested,
        "severity": _severity(need, urgency, flags),
        "model": res["routing"]["model"],
        "routing_reason": res["routing"]["reason"],
        "ms": ms,
    }


def _match_place(text, pois, place_answer):
    """Only an exact name mention places a report automatically. Laya's
    place pick is returned as a suggestion for the operator to confirm:
    in eval_laya.py it tagged "the bridge" in a Vietnamese report with a
    Delhi bridge. Returns (poi or None, suggested poi name or None)."""
    low = text.lower()
    for p in pois:
        if p["name"].lower() in low:
            return p, None
    if place_answer and place_answer["choice"] != "none" \
            and place_answer["confidence"] >= PLACE_CONFIDENCE:
        return None, place_answer["choice"]
    return None, None


def _severity(need, urgency, flags):
    """Map a triage record onto the physics priority vocabulary.

    Tuned on eval_laya.py: the urgency score spans roughly 0 (no danger) to
    2 (life in danger), and the `trapped` flag also fires on blocked roads,
    so flags only count toward `immediate` when the need is rescue/medical.
    """
    if need == "irrelevant" or (need == "observation" and not flags):
        return None
    if need in ("rescue", "medical") and (flags or urgency >= 1.6):
        return "immediate"
    if need in ("rescue", "medical", "supplies", "infrastructure"):
        return "high"
    return "monitor"


_RANK = {None: 0, "monitor": 1, "high": 2, "immediate": 3}


def fuse(evac_zones, report):
    """Escalate-only merge of one triaged report into evacuation_zones.
    Returns the escalation applied, or None if nothing changed."""
    zone, sev = report.get("zone"), report.get("severity")
    if not zone or not sev:
        return None
    existing = next((z for z in evac_zones if z["zone"] == zone), None)
    before = existing["priority"] if existing else None
    if _RANK[sev] <= _RANK[before]:
        return None
    reason = f"field report ({report['need']}, urgency " \
             f"{report['urgency']:.1f}/2): \"{report['text'][:60]}\""
    if existing:
        evac_zones.remove(existing)
        existing["priority"] = sev
        existing["reason"] = reason + "; physics: " + existing["reason"]
    else:
        existing = {"zone": zone, "priority": sev, "reason": reason}
    # front of its priority band, so the viewer's top-6 list never hides it
    evac_zones.insert(0, existing)
    evac_zones.sort(key=lambda z: -_RANK[z["priority"]])
    return {"zone": zone, "from": before, "to": sev, "reason": reason}
