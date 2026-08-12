FROM python:3.11-slim

WORKDIR /app

# build context is the repo root so we can reuse the shared requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY serving/app.py .

ENV MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
    MODEL_NAME=customer_churn_model \
    MODEL_STAGE=Production \
    FALLBACK_MODEL_PATH=/app/model

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
