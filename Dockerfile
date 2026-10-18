# The backend service: the FastAPI API with only the files it reads. The React app is its own service (frontend/Dockerfile).

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY data/reference/ data/reference/
COPY data/aggregated/ data/aggregated/
COPY data/fleet/ data/fleet/
COPY evals/results/ evals/results/
RUN useradd --create-home --uid 10001 app
USER app
CMD exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT}
