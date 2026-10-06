# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv VISA_PROJECT_ROOT=/app
WORKDIR /app

FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable
RUN /opt/venv/bin/python -c "from visa_agent.documents import ocr_engine; ocr_engine()"

FROM base AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Visa Agent" \
      org.opencontainers.image.source="https://github.com/Sanssssssssssssssss/Visa-Agent" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision=$VCS_REF
RUN useradd --create-home --uid 10001 agent \
    && mkdir /data /backups && chown agent:agent /data /backups
COPY --from=build /opt/venv /opt/venv
COPY src ./src
COPY scripts ./scripts
COPY datasets ./datasets
COPY pyproject.toml uv.lock LICENSE THIRD_PARTY_NOTICES.md ./
ENV PATH="/opt/venv/bin:$PATH" VISA_DATA_DIR=/data VISA_QQ_DATA_DIR=/data
USER agent
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD ["python", "scripts/container_healthcheck.py"]
ENTRYPOINT ["python", "scripts/container_entrypoint.py"]
CMD ["mail"]

FROM build AS test
COPY tests ./tests
COPY scripts ./scripts
COPY datasets ./datasets
COPY docs ./docs
COPY examples ./examples
COPY README.md README.zh-CN.md TESTING.md CONTRIBUTING.md SECURITY.md LICENSE THIRD_PARTY_NOTICES.md .env.example ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-editable
ENV PATH="/opt/venv/bin:$PATH"
CMD ["pytest", "-q"]
