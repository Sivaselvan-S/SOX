# ─── GriffSOX Production Dockerfile ─────────────────────────────────────────
FROM python:3.12-slim

# Install curl for healthcheck (lighter than httpx)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Security: run as non-root
RUN addgroup --system griffsox && adduser --system --group griffsox

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Copy application source
COPY app/ ./app/

# Copy declarative config files (action guardrails, RBAC policy)
COPY action_rules.yaml ./
COPY rbac_policy.json* ./

# Copy SQLite seed data directory (create directory if empty)
RUN mkdir -p ./data
COPY data* ./data/

# Switch to non-root user
USER griffsox

# Expose FastAPI port
EXPOSE 8000

# Health check using curl (no Python import needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn — 2 workers for production throughput
# (safe for in-memory state; scale out via ECS tasks, not in-process workers)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
