# DEMO / lightweight Runtime image only.
# Full product path: host Runtime + host Agent CLIs (docs/DEPLOY.md).
# Optional engines (SoVITS): docker compose --profile engines up -d
#
#   docker compose -f docker-compose.runtime-demo.yml up -d --build

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AGENTDOCK_HOME=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY runtime ./runtime
COPY catalog ./catalog
COPY examples ./examples
COPY config.yaml ./
COPY assets/brand ./assets/brand
COPY assets/pets/README.md ./assets/pets/README.md
COPY assets/voices/README.md ./assets/voices/README.md

RUN pip install --no-cache-dir .

EXPOSE 8765 8766

CMD ["python", "-m", "runtime"]
