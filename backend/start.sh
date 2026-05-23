#!/bin/bash
set -e
echo "Starting PRD Agent API..."
echo "ENVIRONMENT: ${ENVIRONMENT:-not set}"
cd /app
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
