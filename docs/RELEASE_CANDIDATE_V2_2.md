# WindScope v2.2 — Product Experience & Release Candidate Build-Along

**Learning goal:** be able to show an analyst a useful historical decision brief, explain *why* the two cut-off scenarios use the same comparison sample, and prove that a production Docker image serves the right version.

**Scope:** The only business datasets remain Elexon `WINDFOR` and `FUELHH` (`fuelType=WIND`). **There is no demand, market price, trading recommendation, or energy-purchase optimizer.** The product is a historical analytical pilot.

## 0. Preserve your working v2.1 and your 31 downloaded snapshots

You should have: a working container on `localhost:8003`, archived data in `backend/app/data/`, and the v2.1 source at `~/Projects/windscope`.

```bash
cd ~/Projects
cp -a windscope windscope-v21-backup
cd windscope
find backend/app/data -maxdepth 1 -name '*.json' | wc -l
```

Expect `31`. **Don't delete this folder** or run an unnecessary new download.

Place `WindScope_v2_2_Release_Patch.zip` in `~/Downloads` and overlay the changed source files:

```bash
cd ~/Projects/windscope
unzip -o ~/Downloads/WindScope_v2_2_Release_Patch.zip -d .
```

The patch deliberately includes **no downloaded Elexon JSON snapshots** and **no `.env`**; these remain yours. It contains modified source, additional tests, this document and the release HTTP smoke script.

## 1. Explore the new analytics logic

Open `backend/app/domain.py`.

### Net error in energy (MWh)

For hourly matched forecast/actual pairs, the forecast error is:

```
error MW = forecast MW - hourly mean actual MW
net energy error (MWh) = Σ(error MW × 1 hour)
```

For example: at 00:00, forecast 1,200 MW and actual 900 MW means +300 MW, i.e. **+300 MWh over that hour**. If a later hour has a forecast but only one of the two required FUELHH half-hours, that hour does **not** contribute to either energy total or the net error.

The new `decision_brief` field returns the net matched-hours error, hour of the largest absolute miss, number of distinct selected forecast publication timestamps and the latest selected publication timestamp. It has a clearly stated caveat: this is **not the quantity a utility should buy**.

### Compare the SAME hours at two decision cut-offs

A naive comparison might say “09:00 MAE = 800 MW, 18:00 MAE = 700 MW, so 18:00 is better.” But if 09:00 has 12 matched hours and 18:00 has 24, you're comparing different samples.

The new `common_comparison` pairs only hours where **both** scenarios have forecast/actual matches. It computes:

```
paired early MAE = mean(abs(early error)) on common hours
paired late MAE  = mean(abs(late error)) on those same hours
Δ paired MAE = late MAE - early MAE
```

Positive Δ means the later forecast was worse on the same matched hours. Negative means it was better. It is a retrospective forecast comparison, not a trading outcome.

**Explain to an interviewer:** “I noticed that two headline accuracy metrics can use different denominators. I added a paired comparison so the cut-off experiment measures revision quality rather than a coverage difference.”

## 2. Explore the product features

Open `frontend/src/App.tsx`, `types.ts`, and `styles.css`.

- `DecisionBrief` turns verified metrics into a quick-scanning analyst summary. It is **deterministic**, calculated from backend results; there is no generative AI or invented inference involved.
- `data_origin` distinguishes `synthetic`, `local_snapshot`, and `api_or_cache`, so a historical snapshot is never marketed as a fresh API call.
- An `AbortController` cancels obsolete month and comparison requests. `cachedReport` is displayed only when its date and cut-off equal the currently selected controls.
- The “Retry monthly analysis” button remains available after a failure.
- The decision-comparison panel presents paired MAE and explains the sign of `late - early`.
- The footer links to Elexon's BMRS licence and carries the required source attribution.

**Explain to an interviewer:** “State management is not just UI convenience. A React view showing a previous query's result under a new set of filters would be a data-correctness incident. We invalidate stale results and cancel obsolete requests.”

## 3. Run unit and API tests

```bash
cd ~/Projects/windscope
source .venv/bin/activate
python -m pytest backend/tests -q
```

**Expected:** `20 passed` (a dependency deprecation warning may still appear). Tests cover the as-of rule, hourly measurement matching, missing source data, paired denominators, retrospective net energy, data provenance and isolated upstream mocking.

If you see an archive-interference failure in `test_elexon.py`, inspect that test's `tmp_path` fixture. It must monkeypatch `elexon.ARCHIVE_DIR` to an empty temporary directory so local snapshots cannot bypass `_request`.

Then re-run the independent archive audit:

```bash
python scripts/deep_audit_january.py
```

On the existing downloaded data it previously returned 31 distinct forecast and actual daily profiles and 744/744 matched hours. Don't claim that result for a different dataset unless you run the audit again.

## 4. Build the React bundle locally

```bash
cd ~/Projects/windscope/frontend
npm install --no-audit --no-fund
npm run build
cd ..
```

This runs TypeScript checking and Vite compilation. If you get a TS error, share the complete output rather than blindly reinstalling packages. The full production frontend build could **not** be independently completed in the isolated artifact-authoring environment; your Ubuntu validation is the release gate.

## 5. Build the production image WITHOUT disturbing v2.1

```bash
cd ~/Projects/windscope
docker build -t windscope:v2.2 \
  --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo local)" .

docker run -d \
  --name windscope-v22 \
  -p 8004:8000 \
  -e WINDSCOPE_DATA_MODE=live \
  windscope:v2.2
```

If the container name already exists, **inspect it** with `docker ps -a --filter name=windscope-v22` before removing anything. Your previous containers on 8001/8002/8003 are left alone.

```bash
curl -fsS http://localhost:8004/api/health | python -m json.tool
docker exec windscope-v22 python -c \
  "from pathlib import Path; print('Snapshots:', len(list(Path('/service/app/data').glob('*.json'))))"
```

**Expected:** version `2.2.0`, mode `live`, and `31` snapshots. The snapshot count confirms files were placed in the image, not that their source authenticity is independently certified.

## 6. Run HTTP release acceptance tests

```bash
python scripts/smoke_release.py \
  --url http://localhost:8004 \
  --mode live \
  --expect-origin local_snapshot \
  --full-coverage
```

This test suite checks:

1. Health response is for version 2.2 and live mode.
2. Day report contains 24 hourly rows and uses archived Elexon data.
3. Selected publications precede the decision timestamp; paired forecast/actual errors reconcile with the reported net MWh error.
4. Early-vs-late comparison returns a nonnegative number of common hours and consistent MAE delta.
5. Month view has 31 days and 744 expected hourly slots (with `--full-coverage` requiring all 744 matched).
6. CSV export has one header and 24 data rows.
7. Out-of-scope dates receive HTTP 422.

You should see `RELEASE SMOKE CHECK: PASSED`. This tests the **deployed HTTP surface**, not just isolated functions.

## 7. Browser acceptance walkthrough (desktop and narrow viewport)

Open `http://localhost:8004` and verify each of these scenarios:

- Overview shows the dark analyst briefing, actual Elexon snapshot provenance, all 24 hours, and the correct matched energy error for 16 January.
- Change the delivery day rapidly. The chart/brief must **not** retain the previous day's report under the newly selected date.
- Change cut-off from 09:00 to 18:00. The day report must match the selected cut-off.
- Select “Compare decision cut-offs.” Check early and late MAEs and the distinct **paired** delta. A positive delta says later forecast had a higher paired MAE.
- Accuracy & Risk → calculate month → change cutoff while it is loading. An old request must not show its result as the new cutoff's result.
- Forecast explorer displays the publication timestamps and both raw half-hourly actuals. CSV downloads in the browser.
- Try a narrow window (approximately 390 px). Check chart, briefing and table scrolling; the data explorer intentionally scrolls horizontally.
- Methodology and footer clearly state the limits: no actual market gate closure, no procurement recommendation, only specified wind datasets.

**Do not submit if a visible screen displays demo measurements while claiming they're genuine Elexon values.**

## 8. CI and cloud deployment — the next gate

`.github/workflows/ci.yml` now includes a clean-checkout production-image build and an HTTP smoke test in **demo mode**, in addition to Python and TypeScript checks. The demo CI job does not need private snapshot files and never implies they are genuine records.

For the public Heroku deployment, decide how to supply the January archives to the release build. The default `.gitignore` excludes `backend/app/data/*.json`: **a GitHub checkout will not contain your laptop's Elexon snapshots**. A fresh cloud container can still use the Elexon API, but month-scale historical requests could be slow and unreliable. A separately published, attributed, verified archive or build-time ingestion strategy is preferable for the evaluator's demo.

Elexon's [BMRS open-data licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/) allows redistribution with the stated conditions. Required source attribution:

> Contains BMRS data © Elexon Limited copyright and database right 2026.

Retain the link and avoid implying Elexon endorses WindScope. The README already discloses AI-assistance, as the assessment requires.

## Three common interview questions

**1. Why didn't you calculate procurement requirements?** The assessment limits us to forecasts and actual national wind generation. Without the utility's demand, contracted supplies and other generation, computing actual purchases would be fabricated. The product instead quantifies forecast uncertainty.

**2. Why compare paired MAEs rather than the two overall MAEs?** Different cut-offs may have different coverage. A paired sample ensures a fair revision-quality comparison on the exact same delivery hours.

**3. Why serve React from FastAPI in production?** One multi-stage image compiles frontend assets in Node, then serves the static result and API from a Python process on `$PORT`. This is a simple deployable pilot topology, not a claim that a commercial application would necessarily keep a single service.
