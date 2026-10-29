> **Important v2 update (read first):** This original tutorial was written for the first implementation, which compared 48 half-hourly points. The current product now correctly uses **24 hourly WINDFOR forecasts** aligned to the mean of **two complete FUELHH half-hour actuals**, with no interpolation. Any older 48-slot tests, coverage calculations, code listings, or half-hourly forecast instructions in this tutorial are historical teaching examples, **not current build instructions**. Follow `docs/UPGRADE_V2_BUILD_ALONG.md` for the corrected pipeline.

# WindScope: build, learn and explain it

**Purpose:** teach the exact engineering behind this submission from beginner to intermediate level, so that you can operate, troubleshoot and defend the solution. This guide is for development, not your final video script.

## 1. The business problem in plain English

A UK energy company must obtain enough electricity to meet its customers' demand. Wind generation is variable: if wind generation is less than expected, the company may have to arrange more electricity from other sources. A buyer therefore needs forecasts before the purchase decision.

The critical issue is that a *historical* database knows things the buyer **did not know at the time**. The job of the product is to reconstruct the information actually available before a configured day-ahead decision and measure how it performed afterward.

This pilot covers **wind only**. It does not know actual customer demand, contractual positions, prices or generation from other sources, so it **cannot** calculate a safe purchase quantity. That restraint is an important sign of correct product reasoning.

## 2. The two feeds

| Field | FUELHH actuals | WINDFOR forecasts |
| --- | --- | --- |
| `startTime` | Target/measurement interval | Forecast target time |
| `generation` | Actual national generation (MW) | Predicted generation (MW) |
| `fuelType` | Must be `WIND` | WINDFOR is already wind-specific |
| `publishTime` | When revision was published, when supplied | **Critical**: when a forecast became known |

**MW** is power: rate of producing energy. **MWh** is energy: power × time. For one half-hour interval at 10,000 MW, energy is `10,000 × 0.5 = 5,000 MWh`. Do not call 10,000 MW "10,000 MWh".

**Target vs publication time:** A forecast can target Jan 16 at 09:00 but have been published Jan 15 at 08:30. The *target* joins actuals; the *publication* governs whether it was usable before the buying decision.

## 3. What is the technology stack?

- **React:** A JavaScript UI library that composes reusable components, such as the metric cards, charts and data table. It manages user interactions and local state.
- **TypeScript:** JavaScript with static type checking. Our `Report`, `Period` and `Stats` types make accidental data-shape mismatches easier to catch.
- **Vite:** Frontend development server and production asset bundler.
- **FastAPI:** Python web framework exposing REST endpoints; automatically provides Swagger at `/docs`. It validates `delivery_date` and returns structured JSON.
- **httpx:** Async HTTP client. It queries Elexon's upstream API, with timeouts and retries.
- **Docker:** Runs the app in repeatable Linux containers; Compose runs frontend and backend as services; the production Dockerfile creates one compact self-hosted service.
- **Recharts:** React charts using charting primitives that consume an array of domain records.

The interaction path is:

```text
User chooses a delivery date
    ↓
React updates selected date state
    ↓
Browser GET /api/analysis?delivery_date=2026-01-16&cutoff=12:00
    ↓
FastAPI validates input
    ↓
Elexon client downloads WINDFOR and FUELHH (cache if available)
    ↓
Analytics filters forecasts to publications known by the cut-off
    ↓
Join on the exact interval startTime and calculate errors
    ↓
FastAPI sends JSON, React renders cards/chart/table
```

## 4. Why not just display Elexon's latest forecasts?

Imagine the buyer made a decision at noon on January 15:

| Forecast publication | Target Jan 16 09:00 | Eligible? |
| --- | --- | --- |
| Jan 15 08:30 | 8,900 MW | Yes |
| Jan 15 10:30 | 9,100 MW | Yes; **chosen** |
| Jan 15 16:30 | 9,900 MW | No: published after decision |
| Jan 16 03:30 | 10,400 MW | No: published after decision |

The winning forecast is **9,100 MW**. If actual wind later turns out to be 9,700 MW, signed error is `9,100 − 9,700 = −600 MW` and absolute error is `600 MW`.

Why choose the latest eligible publication for each *target*? Because different future target times can be revised at different moments. Choosing one latest whole-document timestamp could lose the most recent known value for individual targets.

This is a miniature example of **point-in-time data correctness**, sometimes called an *as-of join*. The same concept matters in finance (what a trader knew when placing an order), fraud detection (what was observed before a claim), and machine learning (avoiding future information leakage).

## 5. Error metrics, step by step

Let three matched periods have errors `+100`, `−200`, `+300` MW.

**MAE — Mean Absolute Error** = `(100 + 200 + 300) / 3 = 200 MW`. It measures typical absolute miss.

**Bias** = `(100 − 200 + 300) / 3 = +66.7 MW`. Positive means the forecast tended to **overestimate** wind production. A near-zero bias can still coexist with very large positive and negative misses.

**RMSE — Root Mean Squared Error** = `sqrt((100² + (−200)² + 300²)/3) ≈ 216.0 MW`. Bigger mistakes matter disproportionately.

**MAPE — Mean Absolute Percentage Error** = `mean(|forecast − actual| / actual) × 100%`. This is unstable for near-zero actuals. This implementation **excludes actual=0** from that denominator and shows no MAPE when none are valid.

**Coverage** = `matched forecast/actual intervals / total expected intervals`. For 36 matches out of 48 half-hour slots: `75%`. Never interpret a low-coverage MAE as a complete picture of the day.

### A common mistake: averaging daily MAEs

Suppose day 1 has 2 matched errors of 100 MW, and day 2 has 20 matched errors of 500 MW. A simple average of the day MAEs, `(100+500)/2 = 300`, is **wrong** for the month. Aggregate all 22 individual errors: `(2×100 + 20×500)/22 ≈ 463.6 MW`. WindScope's monthly rollup uses matched errors, not unweighted daily averages.

## 6. Date semantics and time zones

The requirement says **purchase decisions made in January 2026**. A day-ahead decision on Jan 31 means the delivery is **Feb 1**. The selectable delivery range is therefore Jan 2–Feb 1.

Use `Europe/London` and properly parse ISO timestamps. In January 2026 the UK is on GMT (UTC+0). In summer it would be on British Summer Time (UTC+1), which is why hardcoding an offset is dangerous for future use. Actual/forecast times are aligned in UTC, then labeled using UK local time.

The 12:00 cut-off is a configurable *hypothetical decision time* for this assignment. **Do not tell interviewers that 12:00 is the guaranteed market cut-off.** Actual day-ahead auction schedules vary with market, provider and product.

## 7. Source code tour

Start with `backend/app/domain.py`. The functions are intentionally pure: when supplied with the same rows and dates, they return the same results without network calls. This makes correctness easy to unit test.

- `decision_cutoff()` determines yesterday's UK local cut-off.
- `choose_forecasts()` excludes future publications and chooses the latest eligible version per target time.
- `choose_actuals()` filters WIND fuel and picks the latest published revision per target.
- `analyse_day()` creates **48** standard half-hour slots, joins exact timestamps, reports missingness, and calculates daily metrics.
- `summarise_month()` aggregates matched errors across all 31 decision days.

Then read `backend/app/elexon.py`. It knows the API URLs, query arguments, retries, concurrency limits and disk cache. It does **not** know how MAE works: this separation is a design principle called **separation of concerns**.

Then read `backend/app/main.py`. Routes receive HTTP requests, validate inputs, run analytics and send JSON. Finally read `frontend/src/App.tsx`, the React view layer that transforms API results into charts and user controls.

## 8. Docker from zero

A **Docker image** is the packaged filesystem + instructions to run an app. A **container** is a running instance of that image.

The development `docker-compose.yml` declares two services:

- `backend` — Python FastAPI server on local port `8000`.
- `frontend` — Node/Vite dev server on local port `5173`, proxying `/api` to `backend:8000` inside Docker's network.

The production `Dockerfile` is multi-stage: the first stage uses Node to compile the React bundle, the second uses Python and serves static React files with the API. In a deployment this means one Docker container instead of separate frontend and backend infrastructure.

Check install:

```bash
docker --version
docker compose version
docker info
```

Build and run:

```bash
cp .env.example .env
docker compose up --build
```

See logs and inspect:

```bash
docker compose ps
docker compose logs --tail=60 backend
curl -i http://localhost:8000/api/health
```

Stop:

```bash
docker compose down
```

If Docker prints `permission denied` on `/var/run/docker.sock`, you can use `sudo docker compose ...` temporarily. To fix it properly, add yourself to the docker group (`sudo usermod -aG docker "$USER"`), log out and back in, and be aware that this membership is root-equivalent.

## 9. Practical debugging sequence on Ubuntu

**Case: webpage does not load** — run `docker compose ps` and check frontend logs. Test `http://localhost:5173` locally. If port 5173 is already used, shut down the other process or change the published Compose port.

**Case: chart says Elexon unavailable** — test `/api/health`, then `/api/analysis`; inspect HTTP error and backend logs. Check network/DNS and upstream Elexon status. Never quietly switch to demo values for a submitted result.

**Case: data appears but accuracy is empty** — inspect `forecast_periods`, `actual_periods`, `matched_periods`, and the raw publication times. It can be a genuinely sparse forecast, empty upstream response, a timestamp mismatch or an upstream API/schema change. Separate these possibilities before drawing conclusions.

**Case: month backtest is slow** — it needs up to 62 upstream daily requests (31 decisions × 2 feeds). A local cache cuts repeat requests. For a stable pilot deployment, run `python scripts/snapshot_january.py` with network access first, inspect the genuine records, then package the immutable archive in the production Docker build. A commercial product would use a proper data pipeline.

**Case: frontend renders but /api returns HTML** — check Vite proxy and backend availability. Locally the proxy must use `http://localhost:8000` instead of the `backend` Docker hostname.

## 10. Interview questions you should be able to answer

**Why FastAPI?** It is Python-first, strongly typed with Pydantic, makes data functions easy to test, and automatically provides API docs.

**Why isolate domain logic?** To test the correctness of forecast selection and error metrics without requiring internet access, credentials or a running web server.

**Why no database?** This pilot has a fixed small historical scope. A cached HTTP adapter makes delivery fast within assessment time. A production system should use a durable store for source version history and scheduled ingestion.

**Why report bias as well as MAE?** MAE quantifies miss size; bias captures directional over/under-estimation that can matter differently to procurement teams.

**How is future information leakage prevented?** Every candidate's `publishTime` is compared to the previous day's configured cut-off before selection for its individual `startTime`. This is verified with tests.

**How would you scale it?** Background ingest and immutable object-store archives, validated transformation jobs, precomputed analytics, PostgreSQL for indexed historical queries, Redis caching, auth/roles, monitoring/alerts, and CI/CD.

**What is the biggest limitation?** Two specified datasets cannot answer the entire procurement optimization problem. They only quantify the forecast/actual wind component; purchase volumes also require demand, contracts, constraints, generation elsewhere and market conditions.

**Where was AI used?** The README explicitly discloses AI assistance in implementation and documentation. Never pretend this code was entirely authored manually; focus on demonstrating your understanding and independently verifying its behavior.

## 11. Final pre-submission checklist

- [ ] Tests pass and the frontend builds on Ubuntu.
- [ ] Live mode returns actual Elexon source labels and non-empty expected data; compare sample records manually with Elexon.
- [ ] Confirm the upstream WINDFOR and FUELHH query parameter semantics against the current official docs.
- [ ] Compare a manually calculated sample (two or three timestamps) to app's daily errors.
- [ ] Confirm the configured hypothetical cut-off does not imply exchange gate closure.
- [ ] Test partial/missing data presentation and downloaded CSV.
- [ ] Test desktop and mobile layout.
- [ ] Deploy the **live** Docker image to Heroku and verify URLs in an incognito window.
- [ ] Use an anonymous GitHub repo slug and include README + deployment URL.
- [ ] Record a total ≤10-minute unlisted YouTube demo **after** product verification.
