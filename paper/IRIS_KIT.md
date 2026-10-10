# IRIS submission kit

Deadline: **13 October 2026, 11:59 pm**, at register.irisnationalfair.org.
Prepared 2026-10-10. Every number here is reproduced by a script in this
repository; the script is named next to it.

## Read this first

- **The words must be yours.** The drafts below are a starting point.
  Rewrite them in your own voice and make sure you can explain every step
  without notes, because finalists are interviewed.
- **Say how the work was done.** Much of the code was written with an AI
  coding assistant (Claude). Check the IRIS rules on AI assistance and
  state it plainly in the acknowledgement. A draft line is included.
- **Do not claim more than the tables show.** The honest result is
  modest and that is fine. Reviewers reward stated limits.
- **What IRIS rejects:** display-only models with no research under
  them. Lead with the question and the data, not the 3D viewer.

## What to submit

| Item | Limit | Status |
|---|---|---|
| Title, category | | options below |
| Abstract | about 250 words, hard cap 300 | draft below (289 words; trim towards 250) |
| Research synopsis (PDF) | 650 to 1,250 words, six sections | draft below |
| Research paper (PDF) | about 10 to 15 pages | outline + all numbers below |
| YouTube video | 90 seconds max, unlisted or public | script below |

Suggested category: **Earth and Environmental Sciences**. Alternative:
Systems Software.

Title options:
1. From a river level to a doorstep: testing a street-scale flood lookup
   against Delhi's 2023 Yamuna flood
2. Why Delhi's flood warnings under-called 2023, and a level-based
   alternative
3. Does barrage release predict Delhi's floods? A test, and a tool built
   on the answer

## The research in five lines

1. **Question.** Delhi's warning stages are triggered by the barrage
   release. Does release predict the flood level at Delhi?
2. **Finding 1.** Not in 2023. The trend of eight earlier floods
   under-predicts the 2023 record by 2.53 m.
3. **Design.** So key the tool to the river level at the Old Railway
   Bridge, and use a 2D flood model to turn a level into a depth map.
4. **Finding 2.** Tested by rules fixed in advance on 17 localities: the
   model beats the simplest alternative (CSI 0.56 against 0.45).
5. **Finding 3.** Three errors found in my own model along the way, each
   corrected and documented.

## Results (all numbers)

### A. Release against level (`make_figures.py`, figure 1)

Peak Hathnikund release and peak level at the Old Railway Bridge.
Source: SANDRP, 16 July 2023.

| Flood | Release (cusecs) | Release (m³/s) | Level (m) |
|---|---|---|---|
| 1978 | 7,09,000 | 20,077 | 207.49 |
| 1988 | 5,77,522 | 16,354 | 206.92 |
| 1995 | 5,36,188 | 15,183 | 206.93 |
| 2008 | 4,09,576 | 11,598 | 206.00 |
| 2010 | 7,44,507 | 21,082 | 207.11 |
| 2013 | 8,06,464 | 22,836 | 207.32 |
| 2018 | 5,03,925 | 14,270 | 206.05 |
| 2019 | 8,28,000 | 23,446 | 206.60 |
| 2023 | 3,59,760 | 10,187 | 208.66 |

- Eight floods before 2023: correlation r = 0.67.
- All nine: r = -0.06.
- Straight-line fit to the eight, applied to the 2023 release:
  206.13 m. Observed: 208.66 m. Under-prediction: **2.53 m**.
- Caveat to state: nine points, one source, peak release only. Duration
  of release, rain along the way and changes to the floodplain are not
  in this table.

### B. The level-indexed library (`stagelib.py`, figure 2)

- Model: Landlab OverlandFlow (2D shallow water), 150 x 150 cells of
  67 m, about 10 km of the Yamuna through Delhi.
- Runs: steady state, river only, no rain. 17 river flows on SRTM
  terrain (250 to 21,000 m³/s), 20 on FABDEM. All reached steady state.
- Flow the model needs to reach 208.66 m at the bridge: about
  **7,970 m³/s** on SRTM, about **23,170 m³/s** on FABDEM. The real 2023
  peak release upstream was about 10,190 m³/s, so the FABDEM figure is
  not physically credible.
- Physics check (`check_inflow.py`): steady flow in a test channel
  settles at 0.709 m against 0.710 m from Manning's formula.

### C. Locality test (`score_localities.py`, figures 3 and 4)

Rules fixed in `PREREG_LOCALITIES.md` and committed before scoring
(commits 27f504d, 8d6f91a; scoring commit fbf9895).

| Terrain | Method | Caught (of 7) | False alarms (of 10) | CSI |
|---|---|---|---|---|
| SRTM (primary) | Hydraulic model | 5 | 2 | 0.56 |
| SRTM | Bathtub rule | 5 | 4 | 0.45 |
| FABDEM | Hydraulic model | 7 | 4 | 0.64 |
| FABDEM | Bathtub rule | 6 | 5 | 0.50 |

CSI = hits / (hits + misses + false alarms).

SRTM, place by place:

| Locality | 2023 | Model | Depth (m) |
|---|---|---|---|
| Yamuna Bazar | flooded | flooded | 3.53 |
| Nigam Bodh Ghat | flooded | flooded | 6.07 |
| Vijay Ghat | flooded | flooded | 4.64 |
| Usmanpur | flooded | flooded | 6.28 |
| Bela Road, Civil Lines | flooded | flooded | 4.25 |
| Majnu ka Tilla | flooded | **missed** | 0.00 |
| Kashmere Gate ISBT | flooded | **missed** | 0.00 |
| Geeta Colony | no report | **false alarm** | 1.54 |
| Seelampur | no report | **false alarm** | 3.55 |
| Laxmi Nagar, Gandhi Nagar, Chandni Chowk, Daryaganj, Connaught Place, Kamla Nagar, DU North Campus, Paharganj | no report | dry | 0.00 to 0.26 |
| Raj Ghat, ITO, Hakikat Nagar (drain flooding, not scored) | flooded | dry | 0.00 |

What to say about it:
- The two misses are where the terrain data reads rooftops. The lowest
  ground near Majnu ka Tilla in the data is 215.3 m.
- The two false alarms are east-bank colonies behind embankments that a
  67 m grid cannot see. Both risks were written down before scoring.
- The model keeps Raj Ghat and ITO dry, which is right for a river-only
  model: they flooded through a failed drain gate.
- The gap between model and bathtub is two localities. Seventeen is a
  small sample. "No report" is the absence of a report, not proof.
- Only one flood level has been tested.

### D. Errors found in my own model (BACKTEST_PREREG.md, commit log)

| What went wrong | How it was found | What was done |
|---|---|---|
| The river ponded like a bathtub: at 96 m³/s, 16.6 Mm³ entered in 48 h and none left | Mass balance printed by every run | Carved a continuous river bed; outflow then reached 95.6 of 96 m³/s |
| "Hits" at four sites were rain pooling in dips | A rain-only control run gave the same depths | Withdrew the claim; the new test is river only |
| The global forecast (GloFAS) rated 2023 as an ordinary year: 907 m³/s on the peak day, below its own median annual maximum of 1,433 | Pulled the historical series | Stopped using it as the flood trigger |
| The instant-preview model was drawn mirrored north to south | Reproduced the page's calculation against held-out runs: 0.08 overlap as shipped, 0.96 flipped | Fixed the export; added the check |
| A first neural network scored below "predict the average map" (0.54 against 0.73) | Compared against that baseline | Replaced with a per-pixel interpolation model, 0.96 on held-out runs |

### E. What was built

- `outputs/doorstep.html`: set the forecast level, see which
  neighbourhoods get water and how deep, copy a message in Hindi.
- `outputs/delhi/flood_3d.html`: 3D view, today's forecast, the July
  2023 replay, an instant what-if preview.
- `outputs/print/`: three STL files for a 120 mm printed tile of the
  river at Old Delhi, vertical scale exaggerated 25 times.

## Abstract (draft, 289 words: under the 300 cap, trim towards 250)

Delhi's flood warnings are triggered by how much water an upstream
barrage releases. I tested whether that number predicts the flood. In
official records of nine large Yamuna floods since 1978, a larger
release went with a higher river level at Delhi across the first eight
(r = 0.67), but that trend under-predicts the July 2023 record by 2.53 m:
the highest level on record came from the smallest release. A warning
keyed to release would have under-called the worst flood.

I therefore built a tool keyed to the river level at the Old Railway
Bridge, the figure official forecasts give. A two-dimensional
shallow-water model (Landlab OverlandFlow) over satellite-derived terrain
was run to steady state at 17 river flows, giving a library that maps any
bridge level to a depth map. Before scoring, I fixed in writing the
method, 17 localities and the pass rule. At the 2023 level the model
flagged 5 of 7 localities recorded as submerged, with 2 false alarms
among 10 with no flood report (critical success index 0.56). A simpler
rule, flooding everything below the water level, scored 0.45. With
bare-earth terrain the model caught 7 of 7 with 4 false alarms, but only
at an implausible river flow, so I report it as a caution.

Earlier tests exposed errors in my own model, which I corrected and
document: the river ponded in the terrain data, rain pooled where real
drains exist, and a global forecast rated 2023 as an ordinary year. The
result is a web page that turns one forecast number into a
neighbourhood-level message in Hindi, and a 3D-printed terrain model for
explaining it. It has been tested at one flood level in one city and is
not an official warning.

## Synopsis (draft, six sections)

**Abstract.** Use the abstract above.

**Introduction (100 to 150 words).** In July 2023 the Yamuna at Delhi
reached 208.66 m, the highest level recorded, and about 35,000 people
were rescued. Authorities had roughly two days of notice: Delhi's Flood
Control Order raises warnings when the Hathnikund barrage, about 200 km
upstream, releases more than 1 lakh and then 3 lakh cusecs. An official
review of the flood lists, among its challenges, that people in flooded
areas were unwilling to leave despite announcements. A warning stated as
a barrage release or a river level in metres does not tell a family
whether water will reach their lane. This project asks two questions.
Does the release actually predict the flood level at Delhi? And can a
forecast river level be turned into a neighbourhood-level statement that
holds up against what happened in 2023?

**Innovation (50 to 100 words).** Existing public tools report the river
level and the warning stage. This project maps a forecast level to
named neighbourhoods and expected depth, in Hindi. Its test was
pre-registered: the localities, method and pass rule were committed to a
public repository before any result was seen, and the model is compared
against a simple baseline. Errors found in the model are reported, not
hidden.

**Methodology (150 to 250 words).** (1) Release against level: peak
releases and peak Delhi levels for nine floods, 1978 to 2023; a
straight-line fit to the first eight was applied to 2023. (2) Model:
Landlab OverlandFlow, a two-dimensional shallow-water solver, on a
150 x 150 grid of 67 m cells covering about 10 km of the river. Terrain:
SRTM, with the river bed made continuous along a least-climb path after
a mass-balance check showed water ponding in the channel. The inflow
term was checked against Manning's normal depth (0.709 m against
0.710 m). (3) Library: the model was run to steady state, river only,
at 17 flows from 250 to 21,000 m³/s. Each run gives a level at the Old
Railway Bridge and a depth map; a forecast level is answered by
interpolating between runs. (4) Test: 7 localities recorded as
submerged in 2023 and 10 with no flood report, located with
OpenStreetMap. A locality counts as flooded if depth reaches 0.30 m
within 250 m, outside the mapped river. Baseline: a "bathtub" rule that
floods any ground below the water level. The test was repeated on
bare-earth terrain (FABDEM).

**Results (100 to 150 words).** The eight-flood trend (r = 0.67) predicts
206.13 m for the 2023 release; the observed peak was 208.66 m, 2.53 m
higher. At 208.66 m the model flagged 5 of 7 submerged localities with
2 false alarms among 10 (CSI 0.56); the bathtub rule gave 5 of 7 with 4
false alarms (CSI 0.45). The two misses are where the terrain data reads
rooftops; the two false alarms are colonies behind embankments narrower
than a grid cell. On bare-earth terrain the model caught 7 of 7 with 4
false alarms (CSI 0.64), but needed about 23,000 m³/s to reach the
level, more than twice the real release. A rain-only control showed that
earlier apparent hits were rain pooling, and they were withdrawn.

**Acknowledgement and references (50 to 100 words).** Code was written
with the help of an AI coding assistant (Claude, Anthropic); I directed
the work, reviewed the results and am responsible for the conclusions.
[Add your teacher or mentor.] Data: SANDRP (2023), "July 2023 Delhi
Floods"; NIDM (2024), proceedings on Yamuna urban floods in Delhi;
Central Water Commission; Open-Meteo Flood API (Copernicus GloFAS);
SRTM via AWS Terrain Tiles; FABDEM V1-2 (Hawker et al., 2022);
OpenStreetMap contributors; Landlab (Hobley et al., 2017; Adams et al.,
2017); Esri World Imagery.

## Research paper outline (10 to 15 pages)

1. **Introduction.** The 2023 flood; how warnings work; the last-mile
   problem (cite the NIDM proceedings). The two questions.
2. **Background.** Hathnikund to Delhi, 36 to 72 hours. Warning stages.
   What public tools show today. Shallow-water models in one paragraph.
3. **Does release predict level?** Table A, figure 1, the 2.53 m miss,
   and the caveats.
4. **The model.** Grid, terrain, river-bed conditioning, the Manning
   check, the mass-balance check. Figure 2.
5. **The level-indexed library.** Why river only and steady state.
6. **Pre-registered test.** Localities, rule, baseline. Table C, figures
   3 and 4. Both terrains.
7. **What went wrong and how I found it.** Table D. This section is a
   strength; do not shorten it.
8. **The tool.** Doorstep page, Hindi message, printed tile. Screenshots.
9. **Limitations.** One city, one level, 17 localities; no drains, no
   embankments; rooftop terrain; labels from reports; the model's level
   scale is unreliable at low levels; not an official warning.
10. **Next steps.** Radar satellite flood extent as ground truth;
    embankments from OpenStreetMap; a second flood (2019 or 2025); a
    conversation with residents or a district office.
11. **Acknowledgements, references.**

Figures are in `paper/figures/`. Screenshots: open the pages and capture
them yourself.

## Video script (90 seconds)

- 0:00 to 0:12. "In July 2023 the Yamuna hit a record in Delhi. The
  city had two days' warning, and 35,000 people still had to be
  rescued." (Show figure 1.)
- 0:12 to 0:30. "Warnings are triggered by how much water a barrage
  releases. I checked nine floods. 2023 had the smallest release and the
  highest flood, 2.5 metres above the trend."
- 0:30 to 0:55. "So I built a tool that starts from the river level
  instead. A physics model turns that one number into a map."
  (Screen-record the doorstep page: drag the slider, tap Yamuna Bazar,
  show the Hindi message.)
- 0:55 to 1:15. "I wrote down the test before running it. At the 2023
  level it caught 5 of 7 flooded places with 2 false alarms, better than
  the simple rule. It misses two, and I can show why." (Figure 3.)
- 1:15 to 1:30. "It is tested at one level in one city. Next is satellite
  data and a second flood." (Show the printed tile if it is ready.)

## Your to-do list before the 13th

1. Open `outputs/doorstep.html` and the Delhi page; check them on your
   own screen. Read the Hindi message aloud and fix any wording.
2. Rewrite the abstract and synopsis in your own words. Check the word
   counts.
3. Write the paper from the outline. Paste in the tables and figures.
4. Record the video. Upload as unlisted.
5. Print the tile if there is time (`outputs/print/README.txt`).
6. Check the IRIS rules on AI assistance and team size.
7. Submit a day early.
