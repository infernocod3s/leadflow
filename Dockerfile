FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
COPY leadflow/ leadflow/
COPY worker/ worker/
COPY configs/ configs/

# Install the leadflow package + worker dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir fastapi uvicorn

# Railway sets PORT env var
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "worker.main"]
