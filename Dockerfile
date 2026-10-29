# Frontend build stage
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Single process serves API and compiled React assets (Heroku-compatible).
FROM python:3.12-slim AS runtime
ARG VCS_REF=local
ENV WINDSCOPE_BUILD_COMMIT=$VCS_REF
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /service
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
# Restore and verify the archived Elexon dataset
COPY data_snapshot/january-2026-elexon.tar.gz /tmp/january-2026-elexon.tar.gz
COPY data_snapshot/SHA256SUMS /tmp/SHA256SUMS

RUN mkdir -p /service/app/data \
    && tar -xzf /tmp/january-2026-elexon.tar.gz -C /service/app/data \
    && cd /service/app/data \
    && sha256sum -c /tmp/SHA256SUMS \
    && rm /tmp/january-2026-elexon.tar.gz /tmp/SHA256SUMS
COPY --from=frontend-builder /build/frontend/dist ./app/static
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
