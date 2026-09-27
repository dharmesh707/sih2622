FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /src/frontend-react
COPY frontend-react/package*.json ./
RUN npm ci
COPY frontend-react/ ./
RUN npm run build

FROM python:3.13-slim AS python-builder
WORKDIR /src
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY ml_artifacts/ ml_artifacts/
COPY scripts/ scripts/
ENV PYTHONPATH=/src
ENV PROGRESSSYNC_MODEL_PATH=/opt/progresssync-model
RUN PYTHONPATH=/install/lib/python3.13/site-packages:/src python scripts/provision_model.py

FROM python:3.13-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PROGRESSSYNC_MODEL_PATH=/opt/progresssync-model
COPY --from=python-builder /install /usr/local
COPY --from=python-builder /opt/progresssync-model /opt/progresssync-model
COPY backend/ backend/
COPY data/ data/
COPY ml_artifacts/ ml_artifacts/
COPY --from=frontend-builder /src/frontend-react/dist frontend-react/dist
RUN useradd --create-home --uid 10001 progresssync \
    && mkdir -p /app/data \
    && chown -R progresssync:progresssync /app /opt/progresssync-model
USER progresssync
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]