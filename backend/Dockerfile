FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT_MODE=export \
    NEXT_PUBLIC_API_BASE_URL=same-origin \
    NEXT_PUBLIC_RUNTIME_CONFIG=true
RUN npx next build --webpack

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app --no-create-home app

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY --from=frontend-builder /frontend/out /frontend/out
RUN pip install --no-cache-dir .

USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
