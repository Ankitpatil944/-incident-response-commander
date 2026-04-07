FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ENABLE_WEB_INTERFACE=true

WORKDIR /app

COPY pyproject.toml README.md openenv.yaml ./
COPY incident_env ./incident_env
COPY server ./server
COPY inference.py ./inference.py

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r incident_env/server/requirements.txt && \
    pip install --no-cache-dir -e .

EXPOSE 7860

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
