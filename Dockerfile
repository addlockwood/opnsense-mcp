FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS source

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY tests ./tests

FROM source AS dev

RUN pip install --no-cache-dir '.[dev]'

CMD ["pytest"]

FROM base AS runtime

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /workspace \
    && chown -R app:app /workspace /home/app

ENV HOME=/home/app

USER app

ENTRYPOINT ["opnsense-mcp"]
