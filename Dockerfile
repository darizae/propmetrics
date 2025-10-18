FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for DuckDB spatial and shapefile extraction path (not used at runtime in demo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App
COPY app ./app
COPY actions ./actions
COPY scripts ./scripts
COPY sources ./sources
COPY Makefile ./
COPY .env.example ./

# Demo data location (bind or copy into /app/demo at runtime)
ENV DATA_DIR=/app/demo
ENV REDIS_URL=fakeredis://
ENV SERVER_URL=http://0.0.0.0:8000
ENV RATE_QPS=0
ENV LLM_MOCK=1

EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
