# WindScope — UK Wind Procurement Intelligence

**React + TypeScript · Python/FastAPI · Elexon BMRS · Docker**

WindScope is a pilot decision-support application for a UK electricity procurement team. It helps analysts view historical wind-generation forecasts **as they existed when day-ahead purchase decisions were made**, compare those forecasts against actual wind generation, measure forecast errors, and audit the source data.

> **Assessment scope:** Decisions made **1–31 January 2026**, resulting in delivery days **2 January–1 February 2026**. This day-ahead convention is an explicit modeling choice. The UI defaults to a *hypothetical* 12:00 UK local time decision cut-off, which users can change. It must **not** be interpreted as the actual contractual gate closure of any UK exchange.

> **Data integrity:** Live mode requests the specified `WINDFOR` (forecast) and `FUELHH` (actual, `fuelType=WIND`) Elexon datasets. Demo mode is independently generated **synthetic data and visibly labeled as such**. No sample values are passed off as genuine Elexon data. The January archive was validated on an Ubuntu host (31 distinct daily profiles and 744/744 matched hourly intervals); that check does not certify the upstream measurement definitions or source authenticity. Run the release smoke test again after deployment.

## Screens and features

| Page | Capabilities |
| --- | --- |
| Overview | Select delivery date and decision cut-off; see forecast/actual chart, daily MAE, bias, RMSE, coverage, energy summary and largest misses |
| Forecast explorer | Inspect 24 hourly comparison slots (with both raw half-hour actuals) with target time, forecast, actual, error, source publication timestamp and match status; filter gaps |
| Accuracy & risk | On-demand 31-day backtest (31 decision dates), weighted aggregate metrics, daily errors and drill-down |
| Methodology | Source definitions, look-ahead-bias prevention, formulas, data-quality limitations, operational caveats |
| Export | Auditable per-day CSV from the same backend analysis used on screen |

### How we prevent look-ahead bias

For a delivery day `D` and selected UK cut-off `HH:MM`, the decision timestamp is `D-1 HH:MM Europe/London`. For **each individual forecast target `startTime`**, select the row whose `publishTime` is the latest not later than that decision timestamp. Later revisions never enter this analysis, even if they would have been more accurate.

1. Obtain source rows and parse timezone-aware UTC timestamps.
2. Deduplicate/choose the latest forecast as of cut-off per target `startTime`.
3. Keep the latest available `FUELHH` revision for the matching WIND target time.
4. Build hourly actual means from the two half-hour FUELHH records starting at the forecast hour, then compare **on exact target UTC timestamps**.
5. Display missing values as gaps and compute metrics **only over matched pairs**.

WINDFOR forecasts are hourly while FUELHH reports half-hourly outturn. We compare each forecast with the arithmetic mean of both constituent actual readings; if either reading is absent, the hour is not matched. Both source readings remain visible and exportable. We never interpolate missing values. This is an *alignment assumption* for comparing MW, not a claim that the two datasets have identical sampling methodology.

## Quick start on Ubuntu (recommended)

Requirements: Ubuntu 22.04+; Docker Engine with Compose v2; Git. Internet access is needed in live mode.

```bash
# From the extracted repository root (folder containing docker-compose.yml)
cp .env.example .env
# Default .env uses LIVE Elexon data.
docker compose up --build
```

- Open **http://localhost:5173** for the React dashboard.
- Open **http://localhost:8000/docs** for interactive FastAPI documentation.
- Open **http://localhost:8000/api/health** for a small API status JSON.
- For offline UI exploration only: change `.env` to `WINDSCOPE_DATA_MODE=demo`, then run `docker compose up -d --force-recreate`.
- To stop: `Ctrl+C` or `docker compose down` from another terminal. `docker compose down -v` additionally removes cached API data and frontend dependencies.

**Important:** Elexon historical requests can take time, and a whole-month backtest performs many network calls. Backend requests have retry logic and a 24-hour local JSON cache. The cache is a convenience; it is not a durable production database.

### Recommended before cloud deployment: reproducible genuine data snapshot

For a reliable demo, save actual Elexon responses into verified, date-specific JSON snapshots. This is **opt-in**: the ZIP does **not** contain an invented or unverified January dataset. The downloader fails if Elexon responds with missing forecasts or actuals, so it will not silently create a fake snapshot. After checking the results, the files are read locally instead of requiring repeated upstream requests on every Heroku boot.

```bash
# From repository root; requires backend Python dependencies and internet
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
python scripts/snapshot_january.py
# Creates backend/app/data/2026-01-02.json ... 2026-02-01.json
# Inspect quality and source timestamps after this completes.
```

Then run `python scripts/validate_january.py` to write a day-by-day CSV audit. **Do not claim a validated real-data backtest until its results have been reviewed.**

Run this **before** building the final production image to include snapshots in the Docker build context. The BMRS open-data licence allows reuse and redistribution subject to its attribution and other terms; preserve the exact required attribution (see Sources). Snapshots remain ignored by Git by default, so a clean cloud checkout will not include them unless you explicitly provide the archives through an approved deployment process. Snapshots contain public upstream records, never demo data. To force fresh API requests when diagnosing a snapshot, set `WINDSCOPE_IGNORE_ARCHIVE=1`.

### Production-style single-container local run

```bash
docker build -t windscope:local .
docker run --rm -p 8000:8000 -e WINDSCOPE_DATA_MODE=live windscope:local
# Browse http://localhost:8000
```

This image builds Vite assets in a Node stage and serves React and FastAPI from the **same Python application** in the final image, avoiding any same-origin or CORS issues in production.

### Without Docker (development only)

Backend terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
WINDSCOPE_DATA_MODE=live uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend terminal:

```bash
cd frontend
npm install
# Set backend proxy destination if outside Docker. By default vite.config.ts uses the
# Docker Compose service hostname "backend". Locally change it to http://localhost:8000.
npm run dev
```

## Verification and tests

```bash
# Python unit + FastAPI integration tests, using synthetic data only
cd backend
pip install -r requirements-dev.txt
python -m pytest -q

# Frontend type-check and build
cd ../frontend
npm install
npm run build
```

Automated tests cover preventing future publications, per-target latest forecast selection, half-hour time matching, exclusion of non-wind fuels, zero-denominator MAPE, scope validation, month weighting, CSV, and API responses. The GitHub Actions workflow runs tests and a frontend build on pushes and PRs. The decision-cutoff comparison and completeness tests are included.

Live smoke test on a network-connected Ubuntu host:

```bash
curl -fsS 'http://localhost:8000/api/health'
curl -fsS 'http://localhost:8000/api/analysis?delivery_date=2026-01-16&cutoff=12:00' \
  | python3 -m json.tool | head -n 45
```

Verify `source` is **Elexon BMRS**, and inspect the `matched_periods`, forecast publication timestamps and missing-data statuses. A 200 response with empty matches should be investigated, not treated as a successful data integration. Inspect Elexon's current docs if upstream query arguments or field names change. The API client is isolated in `backend/app/elexon.py` so changes remain local.

## Architecture

```text
                         Browser (React + TypeScript)
                                      │
             dashboard / filters / drill-down / CSV download
                                      │ HTTP /api/*
                                      ▼
                          FastAPI (Python REST API)
                  /analysis  /month  /export  /health  /meta
                                      │
                           Pure analytics module
               (latest as-of + join + metrics + quality)
                                      │
                     Elexon API adapter (httpx client)
                  retry / bounded concurrency / JSON cache
                                      │
                     Public Elexon BMRS Insights API
                       WINDFOR      FUELHH (WIND)
```

## Repository structure

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI routes + React static asset serving
│   │   ├── domain.py            # Pure time selection, matching and metrics
│   │   ├── elexon.py            # Elexon HTTP client, retry and cache
│   │   └── sample.py            # Explicit synthetic offline fixture generator
│   ├── tests/                   # Analytics and API tests
│   ├── requirements.txt         # Production Python dependencies
│   ├── requirements-dev.txt     # Testing dependencies
│   └── Dockerfile.dev           # Development API container
├── frontend/
│   ├── src/App.tsx              # UI screens, controls, visualizations
│   ├── src/styles.css           # Design system + responsive layouts
│   ├── src/types.ts             # Typed API responses
│   ├── src/main.tsx             # React entrypoint
│   ├── index.html
│   ├── public/favicon.svg
│   ├── vite.config.ts           # Development API proxy
│   └── package.json
├── scripts/validate_january.py # Audit real snapshot coverage before submission
├── scripts/deep_audit_january.py # Audit distinct daily actual and forecast records
├── scripts/smoke_release.py # Production HTTP acceptance suite
├── docs/UPGRADE_V2_BUILD_ALONG.md # Data-alignment and scenario build tutorial
├── docs/RELEASE_CANDIDATE_V2_2.md # Hands-on release candidate build guide
├── .github/workflows/ci.yml     # Continuous integration
├── scripts/setup_ubuntu.sh     # Ubuntu environment preflight
├── scripts/snapshot_january.py  # Download genuine January archive (optional)
├── docs/BUILD_AND_LEARN.md     # Beginner-to-intermediate explanation
├── Dockerfile                  # Production multi-stage build
├── docker-compose.yml          # Local React + API services
├── .env.example
└── README.md
```

## REST contract

| Endpoint | Query parameters | Purpose |
| --- | --- | --- |
| `GET /api/health` | — | Service health + source mode |
| `GET /api/meta` | — | Delivery scope, timezone and cut-off caveat |
| `GET /api/analysis` | `delivery_date=2026-01-16&cutoff=12:00` | One delivery day with points + metrics |
| `GET /api/compare` | `delivery_date=2026-01-16&early=09:00&late=18:00` | Compare two hypothetical procurement decision times using identical source data |
| `GET /api/month` | `cutoff=12:00` | 31 delivery days and weighted aggregate |
| `GET /api/export` | `delivery_date=2026-01-16&cutoff=12:00` | CSV source trail |

The API validates dates: only **2026-01-02 through 2026-02-01** may be requested. Cut-offs use `HH:MM` in **Europe/London** time. Error sign is `forecast − actual`. MAE/RMSE/bias are in MW. Hourly forecast energy is `hourly MW × 1 hour` (MWh); raw FUELHH half-hour energy is `MW × 0.5 hour` (MWh).

## Deployment: Heroku, using Docker

The challenge allows Vercel or Heroku. **Heroku container deployment is the straightforward path for this React + Python monorepo**, using the production Dockerfile. Do not publish until the live dataset is verified; Heroku may require a paid plan.

1. Create your anonymous public GitHub repository and push the source. Do not put your name in the repo slug or make promises about live availability before verification.
2. Install [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) and sign in (`heroku login`).
3. Run in the repository root:

```bash
heroku create YOUR-ANONYMOUS-APP-NAME --stack container
heroku config:set WINDSCOPE_DATA_MODE=live -a YOUR-ANONYMOUS-APP-NAME
heroku container:login
heroku container:push web -a YOUR-ANONYMOUS-APP-NAME
heroku container:release web -a YOUR-ANONYMOUS-APP-NAME
heroku open -a YOUR-ANONYMOUS-APP-NAME
```

4. In the final submission README, replace this placeholder with the actual verified deployment URL:

**Deployed URL:** `TO_BE_ADDED_AFTER_SUCCESSFUL_LIVE_DEPLOYMENT`

5. Check `/api/health`, `/api/analysis`, CSV export and `/api/month` **in an incognito browser**. The assignment also asks that the YouTube demo and anonymous public GitHub repository be externally accessible before submission.

Heroku container filesystems are ephemeral; JSON cache is not permanent between restarts. For a durable commercial system, migrate raw source history and processed metrics to managed object storage and PostgreSQL and precompute daily snapshots.

## Design choices, safeguards and honest limitations

- **Time-zone handling:** source timestamps are UTC; the cut-off is anchored to the previous `Europe/London` local date. January 2026 is UTC+00:00. Using the named zone makes the rule explicit for future extension.
- **No misleading completeness:** missing forecast periods are `null`. No filling, interpolation or fabricated source data. Metrics use actual forecast matches, and coverage is visible.
- **Revision history:** selection is done per target timestamp, not by taking the final published revision of the day.
- **No unlicensed price/demand assertions:** requirement expressly forbids datasets beyond FUELHH and WINDFOR. The app cannot determine how much extra power a utility must buy without demand, contracted generation and other supply.
- **No confidence intervals inferred from tiny samples:** MAE/RMSE/bias are historical diagnostics, not 95% prediction intervals. A risk reserve would need empirical calibration and additional analysis.
- **API availability:** upstream requests can time out, throttle or return schema changes. Errors are surfaced, never silently replaced by mock data.
- **Known scope limitation:** the pilot fetches forecast publications from the decision day and **one preceding calendar day**. If a forecast was last published even earlier, it will not appear; a production archive should use a wider, documented as-of lookback and record its data completeness.
- **Source interpretation:** The requested Elexon sources represent their own definitions of national actual and forecast generation. They are not a full representation of all wind generation or all electricity purchased by a supplier.
- **Data precision:** published wind forecasts can have non-half-hour cadence. The dashboard compares hourly WINDFOR to complete-hour averages of FUELHH without inventing either forecast or actual values.
- **Production hardening pending:** no user authentication, durable warehouse, automated ingestion scheduler, request throttling, observability, API version pinning, error budget or security review. This is a polished pilot, not a live trading platform.

## AI tools disclosure

**AI tools were used to assist in designing the interface, drafting React/FastAPI implementation, analytical logic, tests, and documentation.** This is allowed by the assessment and is explicitly disclosed. The submitter remains responsible for testing and independently validating all calculations, data-source semantics and deployment behavior.

## Sources

- [Elexon FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Elexon Insights API developer portal](https://developer.data.elexon.co.uk/)
- [Elexon BMRS open-data copyright licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/) (required attribution: **Contains BMRS data © Elexon Limited copyright and database right 2026**).


## Release candidate v2.2 improvements

- **Analyst brief:** retrospective net energy error (MWh) and peak hourly miss based only on matched periods, with source publication provenance and an explicit no-trading-recommendation caveat.
- **Defensible decision comparison:** in addition to separate cut-off MAEs, the dashboard reports *paired MAE on the same matched hours* and the signed difference (later minus earlier). Incomplete coverage at one cut-off cannot falsely skew a conclusion.
- **Data source provenance:** the API labels synthetic fixtures, local historical Elexon snapshots, and Elexon API-or-cache retrievals separately; the frontend does not claim an API fetch is fresh when a local archive was used.
- **Frontend consistency:** cancel stale monthly/comparison requests and refuse to show a previous date's report under new selection controls. Failed monthly requests can be retried from the empty state.
- **Production quality:** 20 Python tests, a Docker HTTP acceptance script for `/api/*`, and a dedicated clean-checkout Docker smoke job in GitHub Actions. These are *not* substitutes for validating the real-data deploy.
- **Licensing:** the application displays the required BMRS attribution and links to Elexon's licence.

```bash
python -m pytest backend/tests -q
python scripts/smoke_release.py --url http://localhost:8004 --mode live --expect-origin local_snapshot --full-coverage
```

The standalone release patch is documented step-by-step in `docs/RELEASE_CANDIDATE_V2_2.md`. A clean public CI job runs in demo mode; archived data is not distributed through Git automatically.

## Assessment-focused v2 improvements

- **Correct hourly comparison:** align 24 hourly WINDFOR predictions to the mean of two complete FUELHH half-hour readings. Never pair one 30-minute actual with a 60-minute forecast or multiply forecast energy by 0.5.
- **Decision cut-off sensitivity:** compare 09:00 and 18:00 UK hypothetical decisions for the same delivery day; report changed forecast hours and comparable forecast-energy movement without claiming a trading result.
- **Auditable source trail:** display and export both raw FUELHH half-hour values and selected WINDFOR publication timestamp.
- **QA evidence:** run `python scripts/validate_january.py` on actual downloaded snapshots to create `january_data_audit.csv`; report any missing days or unmatched hours truthfully.
- **Validation status:** a real January snapshot on the Ubuntu development machine passed the distinct-profile audit (31/31) and hourly matching audit (744/744). The **v2.2 frontend production build has not been verified in this isolated environment** and must be run on Ubuntu before the public deployment.

For a detailed build-along walkthrough see `docs/UPGRADE_V2_BUILD_ALONG.md`.

Quick live release smoke test against an already running `WINDSCOPE_DATA_MODE=live` application:

```bash
python scripts/verify_live.py --url http://localhost:8001 --date 2026-01-16
```

A pass checks source mode, as-of timestamps, raw-actual completeness, and matched hourly coverage for one date; it does not claim all 31 decision days were verified.

## v2.1 integrity hardening

The reported `forecast_energy_mwh` and `actual_energy_mwh` always sum **identical matched hourly intervals** (`energy_basis=matched_hours_only`). With incomplete coverage, unmatched forecast-only or actual-only energy is excluded rather than compared against dissimilar periods. The `scripts/deep_audit_january.py` offline audit independently checks per-day profiles, publication cutoffs and half-hour completeness; see `docs/INTEGRITY_UPGRADE.md`. Health includes deployment `version` and optional build commit.
