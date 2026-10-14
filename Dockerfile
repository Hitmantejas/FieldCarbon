# One Cloud Run service: the FastAPI backend also serves the built React app.
# Stage 1 builds the frontend; stage 2 is the Python runtime with only the files the API reads.

FROM node:24-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY data/reference/ data/reference/
COPY data/aggregated/ data/aggregated/
COPY data/fleet/ data/fleet/
COPY --from=ui /ui/dist/ frontend/dist/
RUN useradd --create-home --uid 10001 app
USER app
CMD exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT}
