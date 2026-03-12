FROM python:3.12-slim

WORKDIR /app

# Copy and install Python dependencies
COPY pyproject.toml .
COPY growthpal/ growthpal/
COPY worker/ worker/
COPY configs/ configs/

# Install the growthpal package + worker dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir fastapi uvicorn

# Railway sets PORT env var
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "worker.main"]
