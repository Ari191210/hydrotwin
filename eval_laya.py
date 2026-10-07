"""Hand-labelled check of the Laya field-report triage.

    .venv/Scripts/python eval_laya.py

Each case is (report, expected need, expected severity, expected POI).
Prints every miss and the hit rates, so claims about the layer stay honest.
"""

import time

import laya_layer

POIS = [
    {"name": "AIIMS Hospital", "type": "hospital", "zone": "D3"},
    {"name": "Yamuna Bridge", "type": "road", "zone": "C2"},
    {"name": "Sarvodaya School", "type": "school", "zone": "B4"},
]

CASES = [
    ("Water is up to the second floor, 6 of us stuck on the roof near Yamuna Bridge, send a boat",
     "rescue", "immediate", "Yamuna Bridge"),
    ("My grandmother needs her insulin and the road to AIIMS Hospital is under water",
     "medical", "immediate", "AIIMS Hospital"),
    ("Water level near the ghat is about knee deep, nobody in danger yet",
     "observation", None, None),
    ("We have had no drinking water or food for two days at Sarvodaya School shelter",
     "supplies", "high", "Sarvodaya School"),
    ("The bridge railing collapsed and cars cannot cross",
     "infrastructure", "high", None),
    ("Who won the cricket match yesterday?",
     "irrelevant", None, None),
    ("पानी तेजी से बढ़ रहा है, हमारे घर में बच्चे फंसे हुए हैं, नाव भेजिए",
     "rescue", "immediate", None),
    ("गर्भवती महिला को तुरंत अस्पताल ले जाना है, सड़क पर पानी भरा है",
     "medical", "immediate", None),
    ("Bhai paani ghar mein ghus raha hai, budhe papa chal nahi sakte, help karo",
     "rescue", "immediate", None),
    ("Nước đang dâng rất nhanh, gia đình tôi mắc kẹt trên mái nhà, cần thuyền cứu hộ",
     "rescue", "immediate", None),
    ("Đường bị ngập, cầu bị hỏng, xe không đi qua được",
     "infrastructure", "high", None),
    ("Mưa nhỏ, nước sông vẫn bình thường",
     "observation", None, None),
]


def main():
    laya_layer.start_loading()
    while laya_layer.status()["state"] == "loading":
        time.sleep(1)
    print(laya_layer.status())

    need_ok = sev_ok = sev_close = place_ok = 0
    ranks = {None: 0, "monitor": 1, "high": 2, "immediate": 3}
    for text, need, sev, poi in CASES:
        r = laya_layer.triage(text, POIS)
        n, s, p = r["need"] == need, r["severity"] == sev, r["poi"] == poi
        need_ok += n
        sev_ok += s
        sev_close += abs(ranks[r["severity"]] - ranks[sev]) <= 1
        place_ok += p
        mark = "ok " if (n and s and p) else "MISS"
        print(f"{mark} [{r['model']:12s} {r['ms']:4d} ms] need={r['need']}"
              f"({r['need_confidence']}) want {need} | sev={r['severity']} "
              f"want {sev} | urg={r['urgency']} flags={r['flags']} | "
              f"poi={r['poi']} (suggest {r['suggested_poi']}) want {poi}\n     {text[:70]}")
    k = len(CASES)
    print(f"\nneed {need_ok}/{k}  severity exact {sev_ok}/{k}  "
          f"severity within one level {sev_close}/{k}  place {place_ok}/{k}")


if __name__ == "__main__":
    main()
