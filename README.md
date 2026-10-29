
# WindScope — UK Wind Procurement Intelligence

**A decision-support pilot for evaluating UK wind-generation forecasts at historical day-ahead purchasing decision times.**

[Live Application](https://9c09a48aaf4c.vercel.app) | [GitHub Repository](https://github.com/Rishabh-322/9c09a48aaf4c) | [Elexon BMRS API](https://bmrs.elexon.co.uk/api-documentation)

**Tech Stack:** React · TypeScript · Vite · Recharts · Python · FastAPI · httpx · Docker · GitHub Actions · Vercel

> **Release v2.2 — October 2026**
>
> WindScope is deployed on Vercel and has passed its production HTTP acceptance tests using archived Elexon data. It is an analytical pilot, not an automated electricity trading or purchasing system.

---

## 1. Project Overview

Electricity suppliers in the UK must anticipate how much electricity their consumers will need and procure sufficient power from the wholesale market.

Part of this supply comes from renewable sources such as wind. However, wind generation is weather-dependent and difficult to predict accurately.

This creates two important challenges for electricity procurement teams:

1. **Forecast visibility:** What was the latest wind-generation forecast available when a day-ahead purchasing decision was made?
2. **Forecast accuracy:** How reliable were those forecasts, and how much uncertainty should the procurement team consider?

WindScope addresses these questions through an interactive web application that reconstructs historical wind-generation forecasts, compares them against actual generation, and provides quantitative error analysis.

The application uses publicly available data from the Elexon Balancing Mechanism Reporting Service (BMRS).

### Assessment Scope

| Parameter | Description |
|---|---|
| Decision period | 1–31 January 2026 |
| Delivery period | 2 January–1 February 2026 |
| Forecast dataset | Elexon WINDFOR |
| Actual generation dataset | Elexon FUELHH, filtered to WIND |
| Default decision cut-off | 12:00 UK time on the preceding day |
| Forecast granularity | Hourly |
| Actual generation granularity | Half-hourly |
| Technology | React frontend, Python backend, Docker |

**Important:** The 12:00 cut-off is a configurable analytical assumption. It is not a claim about the actual gate-closure time of a particular electricity exchange.

WindScope deliberately focuses on wind-generation forecast analysis. It does not calculate actual purchasing quantities because consumer demand, contracted supply, pricing and other energy sources are outside the assignment's permitted data scope.

---

## 2. Key Features

### 2.1 Overview Dashboard

The Overview provides an interactive view of historical wind-generation performance.

Users can:

- Select a delivery date.
- Configure a hypothetical decision cut-off.
- Compare forecasted and actual wind generation.
- Inspect forecast accuracy metrics.
- Identify periods of significant forecasting error.
- Review available source-data coverage.

### 2.2 Analyst Decision Brief

The Analyst Decision Brief translates raw forecast statistics into a concise business-oriented summary.

It includes:

- Net matched-hour forecast energy error.
- Largest hourly forecast miss.
- Latest eligible forecast publication timestamp.
- Data completeness and coverage status.
- A clear explanation of analysis limitations.

The brief helps analysts understand historical forecasting performance without interpreting the results as direct trading recommendations.

### 2.3 Decision Cut-off Comparison

Wind forecasts are revised as updated weather information becomes available.

WindScope allows analysts to compare forecasts available at two different hypothetical purchasing decision times, such as 09:00 and 18:00.

The comparison includes:

- Forecast MAE at each cut-off.
- Forecast bias at each cut-off.
- Number of revised forecast hours.
- Net forecast energy revision.
- Forecast coverage.
- Paired forecast accuracy on identical matched hours.

This reveals whether a later forecast was more or less accurate.

A newer forecast is not automatically assumed to be better.

### 2.4 Forecast Explorer

The Forecast Explorer provides a detailed, auditable view of individual hourly records.

For each period, the application displays:

- Forecast target timestamp.
- Forecasted generation in MW.
- Actual generation in MW.
- Both underlying half-hourly actual measurements.
- Forecast error.
- Forecast publication timestamp.
- Data matching status.

Missing data is displayed explicitly rather than silently filled or interpolated.

### 2.5 Accuracy & Risk Analysis

The application supports historical accuracy analysis across the complete January decision period.

It provides:

- Daily forecast accuracy.
- Monthly aggregate metrics.
- MAE and RMSE.
- Forecast bias.
- Mean Absolute Percentage Error.
- Data coverage.
- Historical performance comparisons.

### 2.6 CSV Export

Users can export daily analysis results in CSV format.

Exports preserve relevant timestamps, source values and matching information to support independent review.

---

## 3. Core Analytical Methodology

### 3.1 Preventing Look-Ahead Bias

One of the most important engineering challenges is ensuring that historical analysis only uses information available when the purchasing decision was made.

For delivery date `D`, WindScope constructs the decision timestamp using the selected cut-off on day `D - 1`.

For each forecast target timestamp:

1. Retrieve historical forecast publications.
2. Parse publication and target timestamps.
3. Exclude forecasts published after the decision cut-off.
4. Select the most recently published eligible forecast.
5. Match the forecast against actual generation for the same target period.
6. Calculate accuracy metrics using valid forecast–actual pairs.

A forecast published after the purchasing decision cannot be used in the historical decision reconstruction, even if it later proves more accurate.

This prevents **look-ahead bias**.

### 3.2 Aligning Different Time Resolutions

The two Elexon datasets use different time intervals:

- WINDFOR provides hourly wind-generation forecasts.
- FUELHH provides half-hourly actual generation.

WindScope aligns them by calculating the mean of the two half-hourly actual power readings corresponding to each forecast hour.

```text
Hourly actual MW =
    (First half-hour actual MW + Second half-hour actual MW) / 2
```

For example:

```text
Forecast for 10:00–11:00 = 8,000 MW

Actual at 10:00 = 7,600 MW
Actual at 10:30 = 7,800 MW

Hourly actual = (7,600 + 7,800) / 2
              = 7,700 MW

Forecast error = 8,000 - 7,700
               = +300 MW
```

A positive error means the forecast overestimated generation.

A negative error means the forecast underestimated generation.

If either half-hourly actual record is missing, the corresponding hourly comparison is marked incomplete.

This averaging is an explicit alignment convention and does not prove that WINDFOR and FUELHH use identical underlying measurement definitions.

### 3.3 Forecast Accuracy Metrics

**Mean Absolute Error (MAE)**

```text
MAE = Σ |Forecast - Actual| / N
```

MAE describes the average absolute forecasting error.

**Root Mean Squared Error (RMSE)**

```text
RMSE = sqrt(Σ (Forecast - Actual)² / N)
```

RMSE penalizes larger errors more strongly than MAE.

**Forecast Bias**

```text
Bias = Σ (Forecast - Actual) / N
```

Positive bias indicates average over-forecasting.

Negative bias indicates average under-forecasting.

**Mean Absolute Percentage Error (MAPE)**

```text
MAPE = mean(|Forecast - Actual| / |Actual|) × 100
```

MAPE is calculated only where the actual generation is nonzero.

**Coverage**

```text
Coverage = Matched periods / Total requested periods × 100
```

Coverage measures data completeness, not forecast accuracy.

### 3.4 Energy Accounting

WindScope converts hourly average power values into energy using:

```text
Energy (MWh) = Average power (MW) × Duration (hours)
```

For an hourly interval, duration is one hour.

Forecast and actual energy totals are calculated over identical matched periods.

This prevents misleading comparisons when some hours have missing forecasts or actual measurements.

The API identifies this approach using:

```text
energy_basis = matched_hours_only
```

### 3.5 Fair Decision Comparisons

When comparing two decision cut-offs, WindScope calculates paired MAE using only hours available in both scenarios.

This ensures a scenario with incomplete data is not unfairly compared against one with complete data.

---

## 4. Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | React | Interactive dashboard |
| Language | TypeScript | Type-safe frontend development |
| Build tool | Vite | Frontend development and production builds |
| Visualization | Recharts | Forecast and accuracy charts |
| Backend | Python | Business logic and data processing |
| API framework | FastAPI | REST endpoints and validation |
| HTTP client | httpx | External Elexon API requests |
| Testing | pytest | Backend unit and API testing |
| Containerization | Docker | Reproducible runtime packaging |
| Local orchestration | Docker Compose | Frontend and backend development services |
| CI | GitHub Actions | Automated validation |
| Hosting | Vercel Container Runtime | Public HTTPS deployment |

---

## 5. System Architecture

```text
                    +----------------------+
                    |   React Frontend     |
                    |   TypeScript + Vite  |
                    |   Charts and Filters |
                    +----------+-----------+
                               |
                               | HTTP /api/*
                               |
                               v
                    +----------------------+
                    |    FastAPI Backend   |
                    |                      |
                    | Request Validation   |
                    | API Endpoints        |
                    | Response Handling    |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |   Analytics Engine   |
                    |                      |
                    | As-of Forecasts      |
                    | Timestamp Alignment  |
                    | Error Calculations   |
                    | Coverage Analysis    |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |   Elexon Adapter     |
                    |                      |
                    | HTTP Requests        |
                    | Retries and Caching  |
                    | Historical Snapshots |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |    Elexon BMRS API   |
                    |                      |
                    | WINDFOR              |
                    | FUELHH (WIND)        |
                    +----------------------+
```

### Architectural Decisions

**Separation of concerns**

The frontend handles presentation and interaction, while the backend owns data processing and accuracy calculations.

**Independent domain logic**

The analytics engine is separated from HTTP requests and UI rendering, allowing calculations to be tested independently.

**External API abstraction**

Elexon integration is isolated so changes in the upstream API do not require rewriting the analytical engine.

**Multi-stage Docker build**

The frontend is compiled in a Node.js build stage, then its generated assets are included in the Python runtime image.

This allows the complete production application to run as a single container.

---

## 6. Running Locally on Ubuntu

### Prerequisites

- Ubuntu 22.04 or newer
- Git
- Docker Engine
- Docker Compose v2
- Node.js and npm for local frontend development
- Python 3 for local backend development

### Clone the Repository

```bash
git clone https://github.com/Rishabh-322/9c09a48aaf4c.git

cd 9c09a48aaf4c
```

### Configure Environment Variables

```bash
cp .env.example .env
```

The application supports two modes:

```text
WINDSCOPE_DATA_MODE=live
```

Uses genuine Elexon data from local snapshots or the external API.

```text
WINDSCOPE_DATA_MODE=demo
```

Uses clearly labeled synthetic data for offline exploration and development.

### Start with Docker Compose

```bash
docker compose up --build
```

Open:

- React dashboard: http://localhost:5173
- FastAPI documentation: http://localhost:8000/docs
- Health endpoint: http://localhost:8000/api/health

Stop the application:

```bash
docker compose down
```

### Production-Style Docker Build

```bash
docker build -t windscope:local .
```

Run:

```bash
docker run --rm \
  -p 8001:8000 \
  -e WINDSCOPE_DATA_MODE=live \
  windscope:local
```

Open:

http://localhost:8001

This runs the compiled React application and FastAPI backend inside one production container.

---

## 7. Running Without Docker

### Backend

```bash
cd backend

python3 -m venv .venv

source .venv/bin/activate

pip install -r requirements-dev.txt

WINDSCOPE_DATA_MODE=live \
uvicorn app.main:app --reload --port 8000
```

### Frontend

In another terminal:

```bash
cd frontend

npm ci

npm run dev
```

When running Vite directly on the host, verify that its development API proxy points to `http://localhost:8000` rather than the Docker Compose service hostname.

---

## 8. Historical Elexon Data

### Data Sources

WindScope uses:

- WINDFOR: historical wind-generation forecasts.
- FUELHH: actual generation, filtered to WIND.

### Download Historical Data

The project provides a script for downloading the January historical dataset.

From the repository root:

```bash
python3 -m venv .venv

source .venv/bin/activate

pip install -r backend/requirements-dev.txt

python scripts/snapshot_january.py
```

This creates daily JSON snapshots in:

```text
backend/app/data/
```

The assessment's 31 decision dates correspond to delivery dates from:

```text
2026-01-02
through
2026-02-01
```

### Validate the Data

Run:

```bash
python scripts/validate_january.py
```

Then:

```bash
python scripts/deep_audit_january.py
```

### Verified January Audit Results

The following results were obtained from the archived Elexon data on the Ubuntu development machine.

| Validation | Result |
|---|---|
| Daily snapshots checked | 31/31 |
| Distinct daily actual profiles | 31 |
| Distinct daily forecast profiles | 31 |
| Matched hourly periods | 744/744 |
| Reported hourly coverage | 100% |
| Backend tests | 20 passed |

These results validate consistency under the application's matching rules.

They do not independently certify upstream Elexon data authenticity or identical measurement coverage between the datasets.

### Deployment Data Reproducibility

The initial Vercel production release was uploaded from the Ubuntu development workspace with the 31 locally validated historical snapshots included.

The GitHub repository excludes the raw daily snapshot files.

Consequently, a fresh GitHub-triggered deployment may request data directly from Elexon instead of using the identical audited archive.

A versioned, checksum-verified historical snapshot artifact is planned to make automated cloud builds independently reproducible.

Until that workflow is verified, the initial snapshot-backed deployment and a fresh source-only build should not be described as identical.

---

## 9. Testing and Quality Assurance

### Backend Tests

From the repository root:

```bash
python -m pip install -r backend/requirements-dev.txt

python -m pytest backend/tests -q
```

The v2.2 release candidate passed 20 Python tests.

Tests cover:

- Historical publication cut-offs.
- Prevention of look-ahead bias.
- Forecast revision selection.
- Timestamp alignment.
- Missing-data behavior.
- Error metric calculations.
- Matched-hour energy accounting.
- API request validation.
- CSV exports.
- Decision comparison correctness.
- Snapshot isolation.

### Frontend Production Build

```bash
cd frontend

npm ci

npm run build
```

The frontend production build was successfully verified on Ubuntu using TypeScript and Vite.

### GitHub Actions

The repository includes a GitHub Actions workflow for automated checks.

[View CI Workflow Results](https://github.com/Rishabh-322/9c09a48aaf4c/actions)

The CI pipeline checks backend tests, frontend build correctness and container-related acceptance behavior.

### Production Smoke Tests

The project includes an HTTP smoke test that validates critical application workflows against a running deployment.

```bash
python scripts/smoke_release.py \
  --url https://9c09a48aaf4c.vercel.app \
  --mode live \
  --expect-origin local_snapshot \
  --full-coverage
```

### Verified Production Results

On 29 October 2026, the production deployment passed:

```text
PASS health: version=2.2.0 mode=live commit=local

PASS daily: local_snapshot 24/24 matched;
net forecast error 9519.0 MWh

PASS decision comparison:
24 common hours; later_worse

PASS monthly:
31 days, 744/744 hours

PASS CSV:
24 hourly data rows plus header

PASS invalid date:
HTTP 422

RELEASE SMOKE CHECK: PASSED
```

These checks confirm that the deployed application responds correctly to its essential HTTP workflows.

They do not constitute a formal security review or guarantee every external API failure scenario has been tested.

---

## 10. REST API Reference

| Endpoint | Parameters | Purpose |
|---|---|---|
| `GET /api/health` | None | Application health, mode and version |
| `GET /api/meta` | None | Application scope and metadata |
| `GET /api/analysis` | `delivery_date`, `cutoff` | Daily wind forecast analysis |
| `GET /api/compare` | `delivery_date`, `early`, `late` | Compare decision cut-offs |
| `GET /api/month` | `cutoff` | Monthly historical analysis |
| `GET /api/export` | `delivery_date`, `cutoff` | Export hourly results to CSV |

### Example Request

```bash
curl 'https://9c09a48aaf4c.vercel.app/api/analysis?delivery_date=2026-01-16&cutoff=12:00'
```

### Example Response Fields

```json
{
  "delivery_date": "2026-01-16",
  "decision_date": "2026-01-15",
  "cutoff_uk": "12:00",
  "source": "Elexon BMRS · WINDFOR + FUELHH",
  "statistics": {
    "mae": 858.7,
    "rmse": 1084.8,
    "bias": 396.6,
    "coverage_pct": 100.0,
    "matched_periods": 24,
    "period_minutes": 60
  }
}
```

This is an abbreviated example showing selected response fields.

The production API returns additional metadata, the Analyst Decision Brief, and the hourly data.

---

## 11. Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── domain.py
│   │   ├── elexon.py
│   │   ├── sample.py
│   │   └── data/
│   ├── tests/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── Dockerfile.dev
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── styles.css
│   │   ├── types.ts
│   │   └── main.tsx
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.ts
│
├── scripts/
│   ├── snapshot_january.py
│   ├── validate_january.py
│   ├── deep_audit_january.py
│   ├── verify_live.py
│   ├── smoke_release.py
│   └── setup_ubuntu.sh
│
├── docs/
│   ├── BUILD_AND_LEARN.md
│   ├── UBUNTU_BUILD_ALONG_GUIDE.md
│   ├── UPGRADE_V2_BUILD_ALONG.md
│   ├── INTEGRITY_UPGRADE.md
│   └── RELEASE_CANDIDATE_V2_2.md
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 12. Deployment — Vercel

### Live Application

**Production URL:**

https://9c09a48aaf4c.vercel.app

**GitHub Repository:**

https://github.com/Rishabh-322/9c09a48aaf4c

The application is hosted using Vercel's Container framework.

The production Dockerfile uses a multi-stage build:

1. Node.js installs dependencies and builds the React frontend.
2. Python installs backend dependencies.
3. The compiled React assets are copied into the Python runtime image.
4. FastAPI serves the API and production frontend through the same origin.

### Vercel Environment Variables

```text
WINDSCOPE_DATA_MODE=live
PORT=8000
```

The `PORT` value is configured for the container deployment environment.

### Deployment Commands

From a prepared local checkout:

```bash
npm install -g vercel

vercel login

vercel link

vercel --prod
```

A fresh Git-triggered build additionally requires the historical dataset to be made available if the exact archived-data release is to be reproduced.

### Public Accessibility

Before assessment submission, the live URL, GitHub repository and unlisted demonstration video should be checked in a private/incognito browser window.

The evaluator should not need a developer account or deployment-protection token to access the final deliverables.

---

## 13. Engineering Decisions

### Why React and FastAPI?

React provides a component-based interface for interactive analysis, while FastAPI offers a lightweight Python environment for data processing and REST APIs.

### Why keep analytics on the backend?

Centralizing calculations in Python avoids duplicating business logic across frontend components and makes the calculations independently testable.

### Why historical forecast selection?

Using the latest available forecast without accounting for publication time would introduce future information into historical analysis.

### Why preserve raw measurements?

Keeping source publication timestamps and underlying half-hourly measurements improves auditability and makes debugging easier.

### Why Docker?

Docker provides a reproducible application environment and reduces differences between local development and cloud deployment.

### Why automated tests?

Testing critical domain logic reduces the risk of incorrect forecasts, misleading accuracy calculations and regressions during development.

### Why use local historical snapshots?

Historical snapshots reduce reliance on repeated upstream API requests and support repeatable analysis of a defined historical period.

---

## 14. Known Limitations and Future Improvements

WindScope is a product-level analytical pilot rather than a complete enterprise trading platform.

Current limitations include:

- No automatic electricity purchasing or market execution.
- No customer demand data or other generation sources.
- No electricity price or commercial exposure modeling.
- No user authentication or role-based access control.
- No persistent enterprise database.
- No automated production ingestion scheduler.
- No full observability or alerting stack.
- No formal security review.
- No statistically calibrated forecast confidence intervals.
- A limited historical publication lookback.
- Historical data snapshot reproducibility still being hardened for Git-based cloud deployments.

Potential future improvements include managed historical storage, scheduled ingestion, audit logging, monitoring, broader forecast-history coverage, and better operational resilience.

---

## 15. Development Process and AI Disclosure

The project was implemented iteratively:

1. Understanding the business requirements and Elexon datasets.
2. Designing the React and FastAPI architecture.
3. Building the Elexon data integration.
4. Implementing point-in-time forecast selection.
5. Aligning hourly forecasts with half-hourly actuals.
6. Implementing forecast accuracy calculations.
7. Creating the interactive dashboard.
8. Adding decision cut-off sensitivity analysis.
9. Validating historical January data.
10. Improving test isolation and data integrity.
11. Adding analyst-focused UI features.
12. Containerizing the application.
13. Implementing automated tests and CI.
14. Deploying and validating the application on Vercel.

### AI Tools Disclosure

AI tools were used to assist with:

- Interface design.
- React and FastAPI implementation.
- Analytics logic.
- Test development.
- Debugging.
- Technical documentation.

The assessment explicitly permits AI-assisted development.

The submitter remains responsible for validating the application, reviewing source-data assumptions, verifying calculations and ensuring deployment correctness.

---

## 16. Data Sources and Attribution

WindScope uses public datasets from Elexon BMRS.

**Data sources:**

- [Elexon WINDFOR Forecast API](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Elexon FUELHH Actual Generation API](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon Insights API Developer Portal](https://developer.data.elexon.co.uk/)
- [BMRS Data Copyright Licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/)

**Contains BMRS data © Elexon Limited copyright and database right 2026.**

Elexon does not endorse or certify this application.

The analysis is provided for retrospective evaluation and demonstration purposes.
