FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_SYSTEM_PYTHON=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/README.md apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/src ./src
COPY fixtures ./fixtures
RUN uv pip install --no-cache ".[postgres,s3]"
ENV BEARCASE_FIXTURES_DIR=/app/fixtures/northstar-hvac
EXPOSE 8000
CMD ["bearcase", "serve", "--host", "0.0.0.0"]
