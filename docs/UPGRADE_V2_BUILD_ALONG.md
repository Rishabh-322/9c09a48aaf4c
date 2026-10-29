# WindScope v2 — Product Engineering Upgrade (Ubuntu)

**Goal:** evolve the existing functioning demo into a technically defensible UK wind-forecast analysis product. This is a code-along and interview preparation guide, not a claim that live API integration is verified. The full assignment recommends **at most 16 hours**; spend that time on validity, reliability and communication, not cosmetic features.

## 0. Before you write more code

Original reference: `REint Full Stack SWE challenge v4 Shared.docx`.

**Business question:** A UK power supplier is deciding day-ahead procurement in January 2026. It needs to inspect wind forecasts *that were available when the procurement decision was made* and quantify how good those forecasts turned out to be. The supplied data scope is *only* Elexon `WINDFOR` forecasts and `FUELHH` actuals, `fuelType=WIND`. Demand, prices and other generation aren't in scope; no defensible net purchase amount can be calculated from these two feeds alone.

**A subtle but high-impact modelling issue:** WINDFOR wind forecasts are hourly while FUELHH outturn is half-hourly. Comparing them on 48 half-hour target times leaves valid half-hours unmatched and understates estimated forecast energy when the hourly MW value is incorrectly multiplied by 0.5. v2 aligns `F_hour` to `(A_hour:00 + A_hour:30)/2` and requires both actual readings. Forecast energy uses `forecast_MW * 1h`. The dashboard keeps the raw actuals visible for independent audit.

**Two views of January scope:** decision dates 1–31 Jan 2026 imply delivery days 2 Jan–1 Feb 2026. Always be precise about which you mean.

## 1. Backup the Ubuntu project and apply v2

Open a **new terminal**; the v1 Docker container can continue to run on port 8001 while you inspect this.

```bash
cd ~/Projects
cp -a windscope windscope-v1-backup
# Move the downloaded v2 ZIP to ~/Downloads and extract it into ~/Projects:
unzip -o ~/Downloads/WindScope_Product_Engineering_v2.zip -d ~/Projects
cd ~/Projects/windscope
```

If your ZIP filename differs, replace it with the actual downloaded name. Do not discard local edits without a backup.

`git diff` (if you initialized Git previously) shows exactly what changed. The key edited files are:

- `backend/app/domain.py` — measurement alignment + cutoff comparison pure functions.
- `backend/app/sample.py` — realistic hourly synthetic forecast points alongside 48 synthetic half-hour actuals; still marked **demo**.
- `backend/app/main.py` — new `/api/compare` route and expanded CSV lineage.
- `backend/app/elexon.py` — smaller one-day publication windows for upstream requests.
- `frontend/src/{App.tsx,types.ts,styles.css}` — corrected labels, raw half-hour columns and scenario UI.
- `scripts/validate_january.py` — offline CSV-quality audit for real-data snapshots only.

## 2. Rebuild the single production container

Your earlier port 8000 conflict only affected the **host binding**, not the Docker image. Keep using host port 8001:

```bash
cd ~/Projects/windscope
docker build -t windscope:v2 .
docker run --rm -p 8001:8000 \
  -e WINDSCOPE_DATA_MODE=demo \
  windscope:v2
```

If the previous v1 container still occupies port 8001, stop it with `Ctrl+C` in its terminal first (or choose `-p 8002:8000` and browse port 8002). Avoid `docker system prune` during development.

Open `http://localhost:8001`. Under **Overview** you should see a section **“Would a later forecast change the picture?”** Click **Compare decision cut-offs**. In the **Forecast explorer**, you should see separate `ACTUAL :00` and `ACTUAL :30` columns, plus the complete-hour mean.

### Test the backend directly

```bash
curl -sS 'http://localhost:8001/api/health' | python3 -m json.tool
curl -sS 'http://localhost:8001/api/analysis?delivery_date=2026-01-16&cutoff=12:00' \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["source"], len(p["periods"]), p["statistics"]["coverage_pct"], p["statistics"]["period_minutes"])'
curl -sS 'http://localhost:8001/api/compare?delivery_date=2026-01-16&early=09:00&late=18:00' \
  | python3 -m json.tool | head -n 55
```

**Expected in demo mode:** source contains `DEMO`, `/api/analysis` has **24** hourly periods and `period_minutes=60`, and `/api/compare` returns both scenario metrics. These are synthetic analytics checks, not evidence of January Elexon correctness.

## 3. Understand the analytics code with one worked example

Imagine an hour from 15:00 to 16:00 UK time. The only permitted information at decision time was a forecast of **1,100 MW**, published at 09:00 the prior day. The realised FUELHH values were:

- 15:00–15:30 → 900 MW
- 15:30–16:00 → 1,000 MW

The comparable observed power is `(900+1000)/2 = 950 MW`. The signed forecast error is `1100-950 = +150 MW`, meaning over-forecasting. The **actual energy** in that hour was `900×0.5 + 1000×0.5 = 950 MWh` and **forecast energy** was `1100×1 = 1100 MWh`.

`choose_forecasts(rows, cutoff_utc)` enforces `publishTime <= cutoff` and picks the latest eligible publication **for each target hour**, not one global forecast revision. `choose_actuals(rows)` filters to `fuelType=WIND` and prefers the most recently published actual revision. `analyse_day(...)` then matches each forecast hour to both actual half-hours.

**Why not just fill every missing half-hour with the hourly forecast?** That would be a modelling transformation requiring assumptions. v2 instead aggregates observed data to the published forecast's cadence. It never invents missing actuals and records `incomplete-actual` if only one source reading exists.

**Code exercise:** In `backend/tests/test_domain.py`, find `test_partial_actual_hour_is_not_filled_in`. Remove the `:30` actual from another test case, rerun the test suite, and see why missing measurements reduce coverage rather than silently changing the error.

## 4. Build the decision-time scenario comparison

Why? A trader acting at 09:00 and one acting at 18:00 might have different forecasts for the same delivery day. Historical MAE can show whether those updates were more accurate *in hindsight*. It does **not** prove that waiting is possible under real exchange deadlines or would have reduced trading costs.

- `backend/app/domain.py` → `compare_cutoffs(...)` runs **the same input rows** through the as-of filter twice. This eliminates differences caused by pulling different datasets.
- `backend/app/main.py` → `GET /api/compare?delivery_date=2026-01-16&early=09:00&late=18:00` validates time order, fetches data once, delegates to the domain layer.
- `frontend/src/App.tsx` → `loadComparison()` retrieves the result on demand; the scenario section compares MAE, coverage, revised forecast hours and the net change in forecast energy on hours available in both scenarios.

The sum of hourly forecast changes is meaningful in **MWh** because each hour is one hour long. Changes on non-overlapping hours are excluded and counted separately via `comparable_forecast_hours`.

**Potential interview prompt:** “Did you optimize the purchasing strategy?” Answer: “No. I quantified sensitivity to the information cut-off and forecast errors; actual cost optimization would require demand, traded positions, prices and market rules outside the allowed data scope.”

## 5. Test, intentionally break, and recover

Inside the repository:

```bash
cd ~/Projects/windscope
source .venv/bin/activate  # only if your virtual environment is here
cd backend
python -m pytest -q
```

If `.venv` isn't in the repository root, set up a new one:

```bash
cd ~/Projects/windscope
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
```

Expected v2 baseline: **15 passing Python tests**. They cover as-of selection, 24-hour alignment, incomplete realisations, energy arithmetic, scenario comparison, input validation, API output, snapshot loading and source filtering.

Other manual tests:

1. Request `/api/compare?early=18:00&late=09:00` → **HTTP 422**, not a server crash.
2. Request `/api/analysis?delivery_date=2026-03-01` → **HTTP 422**.
3. Switch delivery date → dashboard, table and CSV must change together.
4. Use the browser's mobile view → summary cards remain readable and table scrolls horizontally.
5. Download CSV → confirm raw half-hour outturns, hourly aligned actual, and `forecast_published_at_utc` appear together.

**Frontend build check** is part of `docker build`, but for local development you can also run `cd frontend && npm install && npm run build` with Node.js installed.

## 6. Verify *real* January data — the acceptance gate

Do **not** submit the synthetic demo dataset and claim historical analysis. Live integration requires internet connectivity and an API schema/data-coverage smoke test **on your Ubuntu computer**:

```bash
# Stop the demo container first, then:
docker run --rm -p 8001:8000 \
  -e WINDSCOPE_DATA_MODE=live \
  windscope:v2
```

Inspect several dates with `curl` or the UI. Ensure that the `source` field says Elexon BMRS, `forecast_periods` and `actual_periods` are positive, the forecast publication timestamps are earlier than the cut-off, hourly matches exist, and 24 expected hourly periods appear. If coverage is unexpectedly low, investigate the Elexon response schema, date filters and source cadence. Don't hide it with interpolation.

For a reproducible monthly run, follow the README's *genuine snapshot* workflow:

```bash
cd ~/Projects/windscope
source .venv/bin/activate
python scripts/snapshot_january.py
python scripts/validate_january.py
```

`snapshot_january.py` downloads only genuine Elexon responses and refuses empty sources; `validate_january.py` creates `january_data_audit.csv` and exits nonzero if any day has no complete matched hour. **Check and record daily coverage**, not just a 200 response from the API. The snapshot data is only eligible for public distribution after you check source licensing/attribution.

If upstream retrieval fails, preserve the honest “live data unavailable” UI. Do not switch a public demo to synthetic mode without labeling it.

## 7. Product-level release checklist

P0 (must-have): real-data correctness on representative days; 31-day data coverage report; January decision scope; 24-hour time alignment; as-of cutoffs and no look-ahead bias; automated tests; functional Docker release; browser accessibility; explicit demo-vs-live mode.

P1 (high value): cut-off sensitivity; raw-source lineage; polished loading/error/empty states; source provenance; CI green; one-command install; deployed HTTPS site and incognito verification; honest limits.

P2 (only if P0 and P1 are stable and assessment time remains): trend distribution, risk percentile from historical comparable hours, guided onboarding, screenshot tests or more sophisticated caching. Avoid unrelated logins, a database that isn't necessary, machine learning, or external demand/pricing sources outside the challenge scope.

## 8. Your technical-review explanation

> “I treated the problem as a retrospective as-of forecasting problem rather than a time-series charting task. React provides an interactive decision workspace, FastAPI owns data validation and endpoints, and a pure Python domain layer guarantees that only forecasts published before the scenario cut-off are eligible. Since Elexon WINDFOR forecasts are hourly but FUELHH wind actuals are half-hourly, I convert two complete actual MW readings to their hourly mean before calculating forecast error. I preserve both raw readings and each forecast publication timestamp for audit. The product compares hypothetical decision cut-offs to show how forecast revisions affect retrospective accuracy. The analysis intentionally does not estimate trading volumes or costs because demand and market prices are outside the assignment scope. Docker's multi-stage build produces one deployable image, and synthetic-data tests validate the business rules independently of external APIs.”

Practice opening the following code locations in order when giving this explanation:

1. `domain.py`: `choose_forecasts()` → as-of filter.
2. `domain.py`: `analyse_day()` → hourly alignment + error metrics.
3. `domain.py`: `compare_cutoffs()` → scenario design.
4. `elexon.py`: request adapter, bounded concurrency, retry/cache.
5. `main.py`: REST endpoints and HTTP 422/502 error contracts.
6. `App.tsx`: controls, asynchronous fetch, visible data-source mode.
7. `backend/tests/`: the exact cases that would otherwise produce incorrect results.
8. `Dockerfile` and `.github/workflows/ci.yml`: deployment reproducibility and CI.

**Do not say “production-proven” yet:** full npm build and real Elexon responses were not executable in the restricted authoring environment. Your Ubuntu build/test and live review are release gates.

### Automated one-day live smoke check

Once the container is running with `WINDSCOPE_DATA_MODE=live`:

```bash
python scripts/verify_live.py --url http://localhost:8001 --date 2026-01-16
```

This script **fails closed**: it rejects synthetic/demo mode, missing matched hours, incorrect hourly record count, forecast publication timestamps after the selected cut-off, and partial FUELHH actuals erroneously marked as matched. A passing day is a useful gate, **not** a substitute for a whole-month audit or browser QA.
