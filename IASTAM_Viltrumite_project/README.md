# Resilient LEO Satellite Network Routing
**Team Viltrumite — IASTAM 6.0 Technical Challenge, Track 4 (Problem 8)**

Adaptive routing for Low Earth Orbit mega-constellations combining Contact
Graph Routing (CGR), DTN store-and-forward, and a reliability-driven hybrid
controller — validated on a realistic, SGP4-propagated orbital simulation.

## What's in this repo

```
.
├── demo/                     # standalone static web demo (no build step, no dependencies)
│   ├── index.html
│   ├── assets/               # styles.css, app.js
│   ├── data/                 # demo-data.js (recorded trace), results-data.js (30-seed results)
│   └── vercel.json
├── src/
│   ├── tle_generator.py      # valid, checksummed NORAD TLEs for a Walker-Delta constellation
│   ├── orbital_network.py    # real SGP4 propagation (Skyfield) + genuine Earth-occlusion geometry
│   ├── routing.py            # the 4 routing strategies + all metrics
│   ├── run_multiseed.py      # primary evaluation: 30 seeds, mean and std
│   ├── run_experiments.py    # earlier single-run version
│   └── export_demo_data.py   # records the single routing trace replayed in the demo
├── scripts/
│   └── build_demo_data.py    # regenerates demo/data/*.js from results/
├── tests/test_orbital_network.py   # 5-case sanity suite
├── results/                  # JSON results, figures, recorded demo trace
├── report/                   # final technical report (PDF + LaTeX source)
├── vercel.json               # lets Vercel deploy ./demo even from the repository root
├── requirements.txt
└── README.md
```

## Live demo

**https://YOUR-PROJECT.vercel.app** &nbsp;← replace with your Vercel URL after the first deployment (see *Deploy the demo to Vercel* below).

The demo is a plain static website hosted on Vercel; it does not depend on any AI platform. It replays one recorded routing trace
(CGR-lite vs. the hybrid controller during an outage) and shows the 30-seed statistics. The animation is a single example, not
statistics; the table and chart are the statistics.

### Run the demo locally

No installation is needed beyond Python or Node:

```bash
python3 -m http.server 8000 --directory demo     # then open http://localhost:8000
# or:  npx serve demo
```

## Why synthetic-but-valid TLEs instead of live Celestrak/Space-Track data

Live TLE feeds (Celestrak, Space-Track) were not reachable from our development
environment (robots.txt / auth-gated). Instead, `tle_generator.py` constructs **physically valid**
TLEs (correct NORAD field widths and checksums) for a Walker-Delta
constellation with realistic LEO parameters (550 km altitude, 53° inclination
— a Starlink-shell-1 analog). These are propagated by the **real SGP4
propagator** (via Skyfield), so all orbital dynamics — precession, J2
oblateness effects, drag — are physically accurate. Only the "tracking one
specific, currently-flying satellite" aspect is synthetic; the orbital
mechanics and the resulting dynamic-topology behavior are real. This is a
standard approach in LEO network research when routing behavior, not exact
live tracking, is the object of study. Swapping in a real TLE file (e.g. a
`celestrak_active.txt` downloaded on a machine with network access) only
requires replacing the call to `walker_constellation()` in
`orbital_network.py` with `Skyfield`'s `load.tle_file()`.

## Setup

```bash
pip install -r requirements.txt
```

## Reproducing the results

```bash
cd src
python3 run_experiments.py
```

This builds the 32-satellite / 3-ground-station constellation, runs the
baseline comparison, the disruption-robustness sweep, and the
recovery-time experiment, and writes `results/realistic_results.json` and
`results/realistic_comparison.png`.

## Statistical evaluation (30 seeds)

`src/run_multiseed.py` is the primary evaluation: 30 independent seeds, a paired design (all four strategies
receive identical traffic and failure draws within a seed) and a fixed orbital epoch (2026-10-01 00:00 UTC) so results are exactly
reproducible. It writes `results/multiseed_results.json` (mean and std) and `results/multiseed_comparison.png`.
`run_experiments.py` is the earlier single-run version and `export_demo_data.py` records the single trace shown in the live demo.
`results/multiseed_extended.json` holds the 0-100% sweep (11 levels, used by the paper figure and the demo); `multiseed_results.json` is the first 0-40% run. The 50-100% range was added after seeing the 0-40% results.
Findings: up to 40% extra failures CGR-lite and the hybrid are statistically indistinguishable; at 50-70% the hybrid is clearly worse (theta = 0.5 switches to flooding too early); equal at 80%; the hybrid is better only at 90% (40.0% vs 27.4%); at 100% nothing is delivered. Epidemic and Naive are below CGR-lite up to 80%.

## Running the tests

```bash
python3 tests/test_orbital_network.py
```

5 sanity checks: TLE validity/checksums, SGP4 propagation accuracy, dynamic
contact-graph behavior, genuine Earth-occlusion geometry, and end-to-end
execution of all 4 routing strategies.

## The 4 routing strategies (`src/routing.py`)

| Strategy | Type | Description |
|---|---|---|
| `run_naive` | baseline | Shortest-path, immediate packet drop (terrestrial-IP analog) |
| `run_cgr` | predictive | Contact Graph Routing-lite: earliest-arrival path over the predicted contact schedule |
| `run_epidemic` | reactive | Bounded store-and-forward flooding (DTN Bundle-Protocol style) |
| `run_hybrid` | **ours** | Reliability-driven controller that switches between CGR and epidemic per message, based on a locally-estimated measure of how trustworthy the contact plan currently is |

## Key finding from the realistic model (vs. the mid-review toy model)

The mid-review report used a simplified, sparse circular-orbit model in
which CGR degraded sharply under disruption, motivating a fairly aggressive
switch-to-epidemic threshold (θ = 0.85). On the realistic, denser Walker
constellation built here, CGR's abundant redundant paths make it far more
robust on its own — so θ had to be **recalibrated down to 0.5** to avoid the
hybrid controller abandoning CGR mode when it didn't actually need to. This
recalibration is itself a validated outcome of the Phase-3 "threshold
learning" item from the interim report's roadmap.

See `results/realistic_results.json` for full numeric results and
`results/realistic_comparison.png` for the delivery-rate / resource-usage
plots across the disruption sweep.

## Project status — honestly assessed

Of the five Phase-3 items committed to at the mid-review stage:

| Item | Status |
|---|---|
| Realistic orbital dynamics (SGP4 + Earth occlusion) | ✅ Delivered |
| Larger-scale validation (14 → 35 nodes) | 🟡 Partial — not yet Starlink-scale (hundreds of satellites); the pairwise occlusion check is O(n²) and untested at that size |
| Threshold learning (online/continuous) | ❌ Not delivered — threshold was recalibrated manually (0.85 → 0.5), not learned |
| Hardware-aware evaluation (energy/storage) | ❌ Not delivered |
| Cross-validation vs ns-3/OMNeT++ | ❌ Not delivered |

Full discussion in `report/paper_final.pdf`, Section IV-G.

## Performance indicators (per the official Problem 8 evaluation criteria)

- **Delivery rate** — `run_experiments.py`, baseline + sweep
- **Latency** — `avg_latency_s` in every result dict
- **Network utilization** — fraction of total available contact
  opportunities actually used (`network_utilization` field)
- **Recovery after disruption** — `recovery_time()` in `routing.py`:
  average delay, after a severe localized outage ends, before bundles that
  were in flight during the outage are finally delivered
- **Robustness** — the 0–40% unpredicted-failure sweep

## Deploy the demo to Vercel

The demo is static, so Vercel needs no build step.

1. Push this repository to GitHub.
2. On [vercel.com](https://vercel.com) choose **Add New → Project** and import the repository.
3. Set **Framework Preset = Other** and **Root Directory = `demo`**. Leave Build Command, Install Command and Output Directory empty.
   (If you keep the repository root, the root `vercel.json` already points Vercel to `demo/`.)
4. Click **Deploy**. Vercel gives you a public URL such as `https://<project-name>.vercel.app`.
5. Put that URL in the *Live demo* section above and commit.

CLI alternative: `npm i -g vercel`, then `cd demo && vercel --prod`.

Check that the site opens in a private browser window. If Vercel asks visitors to log in, open
*Project → Settings → Deployment Protection* and make sure the production deployment is public.

To regenerate the demo data after changing the results: `python3 scripts/build_demo_data.py`.

## Team

Team Viltrumite — Mohamed Abdelmoughith Rouis, Amrou Boukhacham, Majd Lamouchi
(IASTAM 6.0 Technical Challenge, Tunisia Section Chapter).
