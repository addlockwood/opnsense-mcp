FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS source
ARG OPNSENSE_MCP_BUILD_VERSION=0.0.0+local
ENV OPNSENSE_MCP_BUILD_VERSION=${OPNSENSE_MCP_BUILD_VERSION}

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY tests ./tests

RUN python - <<'PY'
import os
from pathlib import Path

build_version = os.environ["OPNSENSE_MCP_BUILD_VERSION"]

pyproject = Path("pyproject.toml")
pyproject.write_text(
    pyproject.read_text(encoding="utf-8").replace('version = "0.0.0"', f'version = "{build_version}"'),
    encoding="utf-8",
)

init_file = Path("src/opnsense_mcp/__init__.py")
init_file.write_text(
    init_file.read_text(encoding="utf-8").replace('__version__ = "0.0.0"', f'__version__ = "{build_version}"'),
    encoding="utf-8",
)
PY

FROM source AS dev

RUN pip install --no-cache-dir '.[dev]'

CMD ["pytest"]

FROM base AS runtime
ARG OPNSENSE_MCP_BUILD_VERSION=0.0.0+local
ENV OPNSENSE_MCP_BUILD_VERSION=${OPNSENSE_MCP_BUILD_VERSION}

COPY --from=source /app/pyproject.toml /app/README.md /app/LICENSE ./
COPY --from=source /app/src ./src

RUN pip install --no-cache-dir . \
    && groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /workspace \
    && chown -R app:app /workspace /home/app

ENV HOME=/home/app

USER app

ENTRYPOINT ["opnsense-mcp"]
