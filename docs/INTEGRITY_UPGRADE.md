# WindScope v2.1 — build-along: integrity and reproducibility

This is a small engineering patch to **v2**, not a new project. Keep your 31 genuine snapshots under `backend/app/data`.

## What was wrong?

In v2, `forecast_energy_mwh` summed all hours with forecasts; `actual_energy_mwh` summed all fully observed actual hours. When different hours were missing from each source, comparing these totals was invalid. In v2.1, both totals use **only identical hours with a valid forecast and a complete actual**. The response declares `energy_basis: matched_hours_only`. The frontend relabels the number accordingly.

### Tiny example

Hour 00 has 1,200 MW forecast and 900 MW actual; hour 01 has 3,000 MW forecast but no complete actual; hour 02 has 500 MW actual but no forecast. v2 incorrectly displayed 4,200 MWh forecast versus 1,400 MWh actual, although only one hour can be compared. v2.1 displays **1,200 MWh versus 900 MWh**. The 300 MWh matched-hour difference corresponds to the one hour of 300 MW signed error.

## Independent archive integrity audit

`python scripts/deep_audit_january.py` verifies:

- 31 date-specific files and their metadata.
- For each date, 48 distinct WIND half-hour timestamps, 24 comparable hours and no selected forecast publication after the cut-off.
- Distinct daily *values*, not merely distinct file names or date stamps.
- Row counts and SHA256 snapshot fingerprints saved in `january_deep_audit.csv`.

The check is deliberately separate from the original coverage audit. It validates local consistency, **not** the external upstream license, market gate closure, or whether the two Elexon datasets have identical generating-asset populations. It does not independently fetch source data to prove the archive has not been altered.

## Apply patch to your Ubuntu v2 repository

From `~/Projects/windscope`, preserve your own source changes, then extract the **patch ZIP only** from the project root:

```bash
cp -a backend/app/domain.py /tmp/windscope-domain-v2.py
cp -a backend/app/main.py /tmp/windscope-main-v2.py
unzip -o ~/Downloads/WindScope_v2_1_Integrity_Patch.zip -d .
```

Patch ZIP contains only source/docs/test changes—**not** your downloaded snapshots.

```bash
source .venv/bin/activate
python -m pytest backend/tests -q
python scripts/deep_audit_january.py
```

Build a production container *after* the snapshots exist, so the image can include them:

```bash
docker build -t windscope:v2.1 --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo local)" .
docker run -d --name windscope-v21 -p 8003:8000 -e WINDSCOPE_DATA_MODE=live windscope:v2.1
curl -fsS http://localhost:8003/api/health
curl -fsS 'http://localhost:8003/api/analysis?delivery_date=2026-01-16&cutoff=12:00' | python -m json.tool | head -n 32
```

The health response now returns `version: 2.1.0` and `build_commit` (`local` if not supplied). To verify snapshot availability inside the image: `docker exec windscope-v21 ls /service/app/data | head`.

## Explain this in an interview

"I found that coverage alone didn't prove archive independence, and totals built from differently missing hours were not comparable. I added an independent per-day fingerprint audit and made energy aggregation use only matched intervals. I tested the edge case with incomplete actuals and added version identification to deployment health checks."

## Before submitting

Run both snapshot audits. Inspect Elexon's dataset scope and redistribution terms before publishing raw snapshots. Test that monthly analytics works offline from archived records. Keep the synthetic demo labeled distinctly from real-data mode. Don't claim to predict actual procurement volumes: demand, contracts and prices are outside this assessment's dataset scope.
