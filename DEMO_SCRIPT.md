# HydroTwin demo script, about 3 minutes

Rewritten 2026-10-09 after the backtest controls. The earlier version
claimed "2 of 3 sites from physics alone" and three "bonus" hits. The
rain-only control showed that is not true, so those lines are gone. Every
number below is in BACKTEST_PREREG.md, BACKTEST_FABDEM.md or the commit
log.

Audience: judges. User we pitch: district disaster officers.

## What we can honestly claim

1. **The physics is checked.** Steady flow down a test channel settles at
   0.709 m against 0.710 m from Manning's formula.
2. **Given the river's flow, it shows where the water goes.** In the July
   2023 replay the model floods Yamuna Bazar from the river, which is
   what happened.
3. **It does not cry wolf.** On a normal day the Delhi page says no flood.
   Force the river to twice its ordinary yearly high and it raises
   top-priority zones.
4. **Nothing invented is shown as real.** What-ifs, replays and fallbacks
   are labelled on screen.
5. **The instant preview matches the physics.** 96% overlap with held-out
   physics runs outside the river.

## What we must not claim

- That it "predicted" or "would have predicted" the 2023 flood. The river
  inflow in the replay was tuned so the level at the Old Railway Bridge
  matches the record.
- "2 of 3 sites". By the rule we fixed in advance the table reads 2 of 3,
  but only Yamuna Bazar is flooded by the river. The other wet sites are
  rain pooling in terrain dips and stay just as wet with the river off.
- That the global forecast feed is enough. GloFAS put 13 July 2023 at
  907 m3/s, below its own ordinary yearly high. The real barrage release
  was about 10,190 m3/s. Fed by GloFAS alone, this would not have flagged
  that flood.
- Any accuracy number for the Laya field-report triage.

## Before the judges arrive

- Run `.venv\Scripts\python run.py` that morning (rain and river numbers
  are fetched live at build time). Takes a few minutes.
- Open `outputs/delhi/flood_3d.html`. Turn Auto-rotate off.
- If showing the live server: start `server.py` at least 2 minutes early
  (the field-report model takes about 95 s to load).
- Do not leave both ML sliders at zero on screen.

## 0. Opening (15 s)

"On 11 July 2023 a barrage 200 km upstream of Delhi released its biggest
flow of the year. The Yamuna peaked in Delhi about 55 hours later, at a
record 208.66 metres. HydroTwin is a physics model that takes a river
flow like that and shows, street by street, where the water goes."

## 1. Today, on the real map (40 s)

- Delhi page, Forecast selected. Point at the satellite terrain: "This is
  the real Yamuna and the real city."
- Point at the alert: "Today it says no flood. The river is running above
  its seasonal normal, inside its banks, and the model knows the
  difference." (Read the actual numbers off the discharge panel.)
- Point at the Data sources list: "Every number says where it came from."

## 2. The July 2023 replay (60 s) - the centre of the demo

- Click "July 2023". Read the yellow banner out loud: it is a replay, the
  inflow was calibrated to the bridge record, rain is from the archive.
- Scrub to the peak (around 11 July). "The river leaves its banks here."
- Open the results block and say it straight:
  - "We picked nine places before running anything."
  - "Yamuna Bazar: flooded by the river in the model, and it flooded in
    2023."
  - "Majnu ka Tilla: we miss it. Our elevation data reads rooftops, and
    it puts that ground too high."
  - "Four other places show water, but it is rain pooling in dips because
    we do not model drains. We do not count those as hits."
  - "One false alarm, Connaught Place, for the same reason."
- "So: one clear river hit, one clear miss, and we can tell you exactly
  why for each. We wrote the rules down before the run. That file is in
  the repository with its date."

## 3. What-if, instantly (30 s)

- Switch back to Forecast. Toggle "ML instant preview" on.
- Drag the river slider up past about 1,300 m3/s: "That is the river
  going over its banks. This is not a rerun of the physics. It is a small
  model fitted to 234 physics runs, and it matches runs it never saw 96%
  of the time outside the river."
- Toggle it off before moving on.

## 4. Field reports, only if time (20 s)

- Live server tab. Submit one report. "A report from the ground can raise
  a zone's priority. It only pins itself to the map when it names a known
  place exactly. Otherwise it is logged, not guessed."
- No accuracy claims here.

## 5. Close (15 s)

"The model needs one thing it cannot make up: the real river flow. The
barrage release is announced two days before the water reaches Delhi.
Give an officer that number and this shows which streets to clear. That
is the product."

## Questions to expect, with honest answers

- **"So did it predict 2023?"** "No. We tuned the inflow to the bridge
  record, then checked where the water went. One site right, one missed,
  the rest inconclusive."
- **"Why not use the global forecast?"** "We tried. It rated 2023 as an
  ordinary year at Delhi. That is why the input has to be the barrage
  release."
- **"Why did you change the terrain after the test?"** "The first version
  ponded water in the channel and raised a false alarm on a normal day.
  We fixed the channel, reran the test, and report both. The site
  outcomes did not change."
- **"How is this different from Google Flood Hub?"** "Flood Hub tells you
  the river will be high. This shows which streets, with the reasons, and
  it runs on a number a district office already receives."
- **"Would you let it order an evacuation?"** "No. It drafts zones and an
  alert. An officer decides."
- **"What about drains?"** "Not modelled. It is why ITO is dry in our
  replay and why rain pools in dips over long runs."
- **"Only one city tested?"** "Yes. Delhi is the one with a recorded
  flood we could check against."

## If something breaks

1. No internet or server down: use `outputs/index.html`. It is fully
   offline.
2. A yellow banner appears that you did not expect: read it out. That is
   the design working.
3. Field-report model not loaded: skip step 4.

## Optional, only if asked about better data

BACKTEST_FABDEM.md repeats the test on bare-earth elevation data. Kashmere
Gate becomes a genuine river hit there at modest flows, but matching the
bridge record needs an inflow 2.4 times the real barrage release, so we do
not present its 3 of 3 as a result. That data is licensed for
non-commercial use only.
