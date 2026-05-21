FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/chroma_data

# Expose port
EXPOSE 8001

# Ensure HOME is set (ChromaDB needs it for ONNX model cache)
ENV HOME=/root

# Start server
CMD uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --log-level debug
