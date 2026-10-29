#!/usr/bin/env bash
set -euo pipefail
printf '\nWindScope Ubuntu preflight\n========================\n'
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker is missing. Install Docker Engine + Docker Compose plugin:'
  echo 'https://docs.docker.com/engine/install/ubuntu/'
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo 'Docker Compose v2 is missing. Install docker-compose-plugin.'
  exit 1
fi
docker --version
docker compose version
if ! docker info >/dev/null 2>&1; then
  echo 'Docker daemon is unavailable to this user. Check systemctl status docker and user permissions.'
  exit 1
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo 'Created .env with LIVE Elexon mode.'
fi
echo 'Ready. Run: docker compose up --build'
