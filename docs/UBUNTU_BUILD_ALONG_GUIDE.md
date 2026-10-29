> **Important v2 update (read first):** This original tutorial was written for the first implementation, which compared 48 half-hourly points. The current product now correctly uses **24 hourly WINDFOR forecasts** aligned to the mean of **two complete FUELHH half-hour actuals**, with no interpolation. Any older 48-slot tests, coverage calculations, code listings, or half-hourly forecast instructions in this tutorial are historical teaching examples, **not current build instructions**. Follow `docs/UPGRADE_V2_BUILD_ALONG.md` for the corrected pipeline.

# WindScope — Ubuntu build-along guide

**Goal:** Build, run, test, understand, and defend the React + Python WindScope submission. This guide follows the **actual files in the WindScope source package**, not a hypothetical template. The complete project is included as a starter codebase; the exercises below are how you learn to implement and verify it yourself.

**Recommended sequence:** Business problem → setup → Python API → Elexon connection → analytical correctness → React → Docker → tests → deployment. Keep to the assessment's **16-hour** development budget. Prepare the presentation/video only **after** the live product is verified.

## Acceptance checklist from the assessment

- UK national-level wind only: `WINDFOR` forecast and `FUELHH` actual generation, `fuelType=WIND`.
- Decisions made **1–31 January 2026**, translating to deliveries **2 January–1 February 2026** for the preceding-day scenario.
- Configurable decision cut-off, clear warning that default 12:00 UK is an *illustrative decision assumption*, not a proven trading gate closure.
- Inspect actual versus eligible forecast, error metrics, missing data, provenance.
- React frontend, Python backend, Docker, public anonymous GitHub repository, Heroku/Vercel deployment.
- Explicitly disclose use of AI in README. Before submission verify production, repo, and eventually unlisted video in incognito mode.

## 0. Sketch your mental model

```text
Browser / React + TypeScript
  GET /api/analysis?delivery_date=2026-01-16&cutoff=12:00
        ↓
FastAPI (backend/app/main.py)
        ↓
Analytics (backend/app/domain.py) ← raw datasets ← Elexon client (backend/app/elexon.py)
        ↓
JSON with matched half-hour periods and MAE, RMSE, bias, coverage
        ↓
React chart / table / cards
```

**Interview-ready statement:** “I separated the API transport layer, deterministic business logic, and UI presentation. That made the time-series logic independently testable and allowed the React application to consume a stable JSON contract.”

## 1. Ubuntu preflight (15–30 minutes)

```bash
sudo apt update
sudo apt install -y git unzip curl python3 python3-pip python3-venv
python3 --version
git --version
node --version         # optional for all-Docker workflow, required to run Vite locally
npm --version
docker --version
docker compose version
docker info
```

For Docker installation: https://docs.docker.com/engine/install/ubuntu/ . Do not blindly mix `docker.io` and Docker's upstream packages. If you get a Docker socket permission error, use `sudo docker compose ...` temporarily; `sudo usermod -aG docker "$USER"` followed by a new login changes access and **the Docker group grants root-equivalent privileges**.

Download the ZIP from ChatGPT, then:

```bash
mkdir -p ~/projects
unzip ~/Downloads/WindScope_UK_Wind_Procurement_FullStack.zip -d ~/projects
cd ~/projects/windscope
pwd
find . -maxdepth 3 -type f | sort
code .                    # only if VS Code's 'code' CLI is installed
```

Open `.env.example`, `docker-compose.yml`, `frontend/package.json`, `backend/requirements.txt`. Point to one reason each exists.

**Checkpoint:** Can you explain the difference between Python packages in `requirements.txt`, Node packages in `package.json`, and OS/container dependencies in Docker?

## 2. Establish a reproducible baseline (20 minutes)

```bash
cd ~/projects/windscope
cp .env.example .env
sed -i 's/WINDSCOPE_DATA_MODE=live/WINDSCOPE_DATA_MODE=demo/' .env
docker compose up --build
```

Open **http://localhost:5173** and **http://localhost:8000/docs**. In a second terminal:

```bash
curl -fsS http://localhost:8000/api/health | python3 -m json.tool
curl -fsS 'http://localhost:8000/api/analysis?delivery_date=2026-01-16&cutoff=12:00' | python3 -m json.tool | head -60
docker compose ps
```

**Expect:** two containers running; health shows `mode: demo`; the API returns 48 half-hour `periods`; the UI clearly identifies demo values as synthetic. Use `Ctrl+C`, then `docker compose down` to stop.

**Explain:** Docker Compose declares two *services*: Vite frontend on `5173` and FastAPI backend on `8000`. The frontend proxy in `frontend/vite.config.ts` forwards browser `/api` requests to `http://backend:8000` *inside the Docker network*. Browsers do not resolve the hostname `backend` directly; they access `localhost:5173`.

## 3. Understand and extend FastAPI (30–60 minutes)

Read `backend/app/main.py` from top to bottom. The important definitions are:

- `app = FastAPI(...)`: creates the API service.
- `@app.get('/api/health')`: route decorator registering a GET path.
- `@app.get('/api/meta')`: supported scope and cut-off assumption.
- `@app.get('/api/analysis')`: one day of analytics.
- `@app.get('/api/month')`: January decision-month aggregation.
- `@app.get('/api/export')`: downloadable CSV.
- `validate(...)`: enforces supported dates and cut-off.
- `day_report(...)`: orchestrates data fetching and deterministic analysis.

**Small safe coding exercise:** Add a new route immediately below `health()`:

```python
@app.get('/api/about')
def about():
    return {'product': 'WindScope', 'purpose': 'Point-in-time wind forecast verification'}
```

Run the application, then test `curl http://localhost:8000/api/about` and explore `/docs`. Remove `/api/about` after the exercise if you want the original API surface.

**Explain:** “FastAPI turns Python functions into HTTP endpoints. Query parameters are validated, and responses are serialized as JSON. `/docs` is auto-generated OpenAPI documentation.”

**Practice questions:** What is GET? What is an HTTP 200 vs 422 vs 502? Why do we use Python `async def` when making HTTP requests? Why does the API return `null` for missing measurements?

## 4. Learn the real data contract, *before trusting the dashboard* (45–90 minutes)

Read `backend/app/elexon.py`, then the official dataset docs:

- https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream
- https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream

The client requests `https://data.elexon.co.uk/bmrs/api/v1/datasets/.../stream` with `httpx` asynchronously. It caches successful JSON, retries transient errors, and rejects unexpected data shapes. The stream API is public; Elexon's developer portal states no API key is required.

Test the raw forecast URL from Ubuntu (requires Internet):

```bash
curl -fsSG 'https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream' \
  --data-urlencode 'publishDateTimeFrom=2026-01-15T00:00:00Z' \
  --data-urlencode 'publishDateTimeTo=2026-01-16T00:00:00Z' \
  -o /tmp/windscope-windfor.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/windscope-windfor.json'))
rows=p if isinstance(p,list) else p.get('data',[])
print('rows:',len(rows))
for row in rows[:2]: print({k:row.get(k) for k in ('startTime','publishTime','generation')})
PY
```

**Important:** A successful HTTP response does **not** guarantee enough forecasts to perform the historical analysis. Confirm there are records **targeting the selected delivery day** and **published before the configured cut-off**. If the API rejects parameters or responds with zero records, verify Elexon's current parameter names/schema and investigate; do not patch around it by silently substituting demo data. Do the same for FUELHH using the query shape in `backend/app/elexon.py`, and inspect `fuelType`, `startTime`, `generation`.

Use `WINDSCOPE_DATA_MODE=live` only once the live sample checks pass:

```bash
sed -i 's/WINDSCOPE_DATA_MODE=demo/WINDSCOPE_DATA_MODE=live/' .env
docker compose up -d --force-recreate
curl -fsS 'http://localhost:8000/api/analysis?delivery_date=2026-01-16&cutoff=12:00' | python3 -m json.tool | head -55
```

**Explain:** A data adapter isolates upstream API specifics from the product's calculations. Retries cover transient upstream failures; bounded concurrency avoids spamming public infrastructure. Cache results improve repeat performance but are not a permanent historical data warehouse.

## 5. Implement the key algorithm in your own words (60–120 minutes)

Read `backend/app/domain.py`. Do not skip its functions:

1. `parse_timestamp`: parses ISO timestamps with timezone into UTC.
2. `decision_cutoff`: converts delivery date into **the previous UK calendar day's cut-off**.
3. `choose_forecasts`: for each target `startTime`, select the latest `publishTime <= decision_cutoff`. Disallow publications after the target itself.
4. `choose_actuals`: filter `fuelType='WIND'`; select the latest revision if multiple exist.
5. `analyse_day`: construct all 48 January half-hour slots, join by precise timestamp, compute metrics and missingness.
6. `summarise_month`: calculate metrics across all matched intervals, not a naïve average of daily scores.

**Walk through an example on paper:** Buyer makes decision **15 Jan at 12:00 UK** for delivery **16 Jan**. Three forecasts target 16 Jan 09:00: published 15 Jan 08:30 at 8,900 MW; 15 Jan 10:30 at 9,100 MW; 15 Jan 16:30 at 9,900 MW. Correct selected forecast: **9,100 MW**. If actual is 9,700 MW, error `forecast-actual = -600 MW`.

**Mini exercise (no HTTP needed):**

```bash
cd ~/projects/windscope/backend
python3 - <<'PY'
from datetime import date, time
from app.domain import analyse_day
f = [
 {'startTime':'2026-01-16T09:00:00Z','publishTime':'2026-01-15T10:30:00Z','generation':9100},
 {'startTime':'2026-01-16T09:00:00Z','publishTime':'2026-01-15T16:30:00Z','generation':9900},
]
a = [{'startTime':'2026-01-16T09:00:00Z','fuelType':'WIND','generation':9700}]
r = analyse_day(date(2026,1,16),time(12,0),f,a,'learning exercise')
print('matched:',r['statistics']['matched_periods'])
print('bias:',r['statistics']['bias'])
print('MAE:',r['statistics']['mae'])
print('coverage:',r['statistics']['coverage_pct'])
PY
```

**Expect:** one matched period, `bias = -600`, `MAE = 600`, `coverage ≈ 2.1%`. Coverage is only 1/48 because the exercise supplied one matched interval.

**Explain:** “I used an as-of join: publication time determines eligibility, and target time determines matching. This avoids look-ahead bias. My metrics report coverage so missing observations don't masquerade as perfect forecasts.”

### Know these metrics

For signed errors `[100,-200,300]` MW:

- `MAE = (100+200+300)/3 = 200 MW` — typical absolute miss.
- `Bias = (100-200+300)/3 = +66.7 MW` — average directional error; positive means forecast too high.
- `RMSE = sqrt((100²+(-200)²+300²)/3) ≈ 216.0 MW` — penalizes large misses.
- `MAPE = mean(|error|/actual)*100%` — percentage error; exclude actual=0.
- `Coverage = matched periods / expected periods*100%` — confidence in sample completeness.

**MW vs MWh:** MW is power; 10,000 MW sustained for a 30-minute period corresponds to 5,000 MWh.

## 6. Understand the React frontend (60–120 minutes)

Read in this order:

1. `frontend/package.json`: React, Recharts, Vite, TypeScript, Lucide icons.
2. `frontend/src/types.ts`: describes the backend JSON contract (`Report`, `Period`, `Stats`, `Month`).
3. `frontend/src/main.tsx`: mounts React.
4. `frontend/src/App.tsx`: `useState` for selections; `useEffect` for data fetching; charts and tables.
5. `frontend/src/styles.css`: responsive layout, components and visual consistency.
6. `frontend/vite.config.ts`: development HTTP proxy (`/api` → `backend:8000`).

**Trace a user interaction:** change date → `setDay()` → effect runs → browser requests `/api/analysis` → FastAPI returns a `Report` → React updates `report` state → Recharts and table render.

**Exercise:** Change the descriptive text of one metric card in `App.tsx` and observe the browser auto-update; then change its back. Next, use browser DevTools → Network to inspect the `/api/analysis` response.

To type-check and build without Docker (needs Node installed):

```bash
cd ~/projects/windscope/frontend
npm install
npm run build
```

If you run Vite **outside Docker** while the backend is local, change `frontend/vite.config.ts` proxy from `http://backend:8000` to `http://localhost:8000` (the `backend` hostname resolves only within Compose). For the Compose workflow, retain the original setting.

**Explain:** “React doesn't calculate the forecast metrics. The backend owns the business rules; React manages interaction and presentation. TypeScript checks API response shapes at build time, and the charts preserve missing values as gaps.”

## 7. Dockerize development and production (30–60 minutes)

Read `docker-compose.yml` and `backend/Dockerfile.dev`: two services, port mappings, volumes, Python dependencies, Vite dev server. Then read the root production `Dockerfile`: first stage compiles frontend in Node; second stage copies its compiled assets into the Python image. FastAPI serves both the API and compiled React single-page app.

```bash
cd ~/projects/windscope
docker compose config
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 backend
curl -fsS http://localhost:8000/api/health
```

**Practice questions:** What is an image vs container? What is a Docker layer? What is a multi-stage build? Why is `localhost` different from a Docker service hostname? What happens to cache data when a Heroku container restarts?

Build the production image locally:

```bash
docker compose down
docker build -t windscope:local .
docker run --rm -p 8000:8000 -e WINDSCOPE_DATA_MODE=demo windscope:local
# Browse http://localhost:8000
```

**Explain:** “I used a multi-stage image to exclude Node tooling from the final Python runtime, while making the frontend and API available from one origin in production.”

## 8. Tests and acceptance (60–90 minutes)

```bash
cd ~/projects/windscope
python3 -m venv /tmp/windscope-test-venv
source /tmp/windscope-test-venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
```

Source-package baseline: **12 automated Python tests passed** where the project was prepared. That is not a promise that your machine/network is already verified.

Test cases live in `backend/tests/test_domain.py`, `test_api.py`, `test_elexon.py`, and `test_snapshot.py`. Be ready to explain **unit tests** (pure function), **integration/API tests** (HTTP response), and **live smoke tests** (real upstream Elexon + complete UI).

Acceptance checks:

- API in live mode identifies **Elexon**, never demo values.
- A chosen delivery date returns a valid number of actual/forecast/matched intervals; investigate zero-coverage days.
- Forecast publication is **at or before** configured cut-off.
- Only `WIND` from FUELHH is used.
- `null` periods remain gaps, not zero measurements.
- All displayed MW/MWh units are correct.
- A later decision cut-off can change the chosen forecast, by design.
- `/api/month` uses all matched errors, weighted by observations.
- CSV export has timestamps, selected forecast publication and status.
- UI supports narrow/mobile viewport without broken charts or clipping.
- Invalid dates return HTTP **422**; upstream failures surface as **502** rather than synthetic success.
- Tests and `npm run build` pass.

**Important live caveat:** The source client currently looks back from the decision day by **one preceding calendar day** for forecast publications. An earlier forecast can be missing even when valid. This is a documented pilot limitation; don't claim perfect archival completeness without extending and validating the lookback.

## 9. Real January snapshot, reproducibility and release (60–120 minutes)

For stable historical responses, after proving one live delivery date works:

```bash
cd ~/projects/windscope
# From an Ubuntu shell with Python dependencies installed and Internet access:
python scripts/snapshot_january.py
# Creates real source snapshots in backend/app/data/
```

Read the script before running it: it fetches many daily datasets and will take network time. Inspect sample JSON and data coverage. The files are genuine only if they were actually fetched from Elexon and their sources verified. Follow the source's licensing and attribution terms if republishing raw records.

`backend/app/data` is included in the final image when built; local API cache under `/tmp` or a Compose named volume is not a permanent database. The app must show data availability honestly.

### Git and automated builds

```bash
cd ~/projects/windscope
git init
git add .
git status
git commit -m 'Build WindScope wind procurement analytics pilot'
```

Create an **anonymously named** public GitHub repo as the assessment requires. Then follow the *actual* remote URL GitHub gives you; do not paste someone else's sample URL:

```bash
git branch -M main
git remote add origin <YOUR_REPO_URL>
git push -u origin main
```

The file `.github/workflows/ci.yml` defines GitHub Actions checks: Python tests and React production build. After pushing, open the repo's **Actions** tab and fix any failures before submitting.

### Deployment

The project README provides Heroku container deployment commands and the final production Dockerfile. Do **not** claim deployment has succeeded until you've checked the public URL. Verify `GET /api/health`, a real-date `/api/analysis`, monthly aggregation, CSV export, all screens, mobile layout, and anonymous/incognito access. Update README with the real deployed URL.

## Debugging map

| Symptom | First check | Likely cause / next action |
|---|---|---|
| `docker: command not found` | `docker --version` | Install Docker Engine and Compose |
| Docker socket permission denied | `docker info` | User permission/daemon; don't mix Docker installs |
| Frontend blank | `docker compose ps`; frontend logs | Startup, port, build or JS console error |
| API works but UI fetch fails | Browser Network tab; `vite.config.ts` | Bad proxy to `backend:8000` vs localhost |
| 502 from `/api/analysis` | `docker compose logs backend` | Elexon timeout/rate limit/schema or invalid parameters |
| 200 with zero matched periods | inspect `startTime`, `publishTime`, expected interval cadence | Sparse data, wrong date bounds, insufficient publication lookback |
| Data looks too perfect | `GET /api/health`; `source` field | Still running synthetic demo mode |
| `npm run build` fails | TypeScript terminal output | Fix first type or JSX error before more changes |
| Tests fail | name of failing test and traceback | Fix precise cause; do not disable the test |

## Short interview answers to rehearse

**What is the product?** “WindScope is a historical wind generation forecast analysis pilot for UK day-ahead procurement analysts. It shows what wind generation was forecast at a given decision time and how those forecasts compared with actual outturns.”

**Why is `publishTime` more than metadata?** “It is a causal boundary. A forecast published after the decision is information the buyer couldn't have used, so including it would cause hindsight bias.”

**Why Python?** “It lets us implement and unit-test time-series selection and statistical calculations as isolated functions, while FastAPI exposes those results through a validated REST interface.”

**Why React?** “The user needs to change dates, inspect discrepancies, drill down into half-hour periods and export evidence. React maps application state and API responses into reusable UI components.”

**Why Docker?** “To reproduce the full environment and ship a consistent application. Multi-stage builds keep Node out of the final Python runtime.”

**Is this a full electricity procurement optimizer?** “No. The assessment restricts us to wind forecasts and wind actuals, so there is no demand, price, contract position or other source data. Claiming the exact MW to purchase would be misleading. The tool supports decisions by quantifying forecast reliability.”

**What would you improve if productizing?** “Wider and verified as-of history, durable storage, scheduled ingestion, data quality alerts, access control, tracing/monitoring and a clearly documented trading calendar.”

## Your practice loop

For **each** milestone: (1) open the relevant file; (2) restate it in everyday language; (3) run its test/endpoint; (4) change one small thing safely; (5) observe the effect; (6) revert or commit; (7) explain the architectural reason in 30–60 seconds.

**Suggested next action:** Do steps 1–2, then send the terminal output of `docker compose ps` and the JSON from `/api/health`. We'll inspect and debug the actual Ubuntu setup before moving into source-by-source implementation.
