# Race Lens — single-container deploy (HF Spaces / any Docker host).
# Stage 1: build the frontend; Stage 2: slim Python serving API + statics.
FROM node:22-slim AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend[api]
COPY --from=web /app/dist ./frontend/dist
ENV RACELENS_FIXTURES=/app/backend/fixtures \
    RACELENS_DIST=/app/frontend/dist \
    RACELENS_READONLY=1
RUN useradd --create-home racelens && chown -R racelens:racelens /app
USER racelens
EXPOSE 7860
CMD ["uvicorn", "racelens.api:app", "--host", "0.0.0.0", "--port", "7860"]
