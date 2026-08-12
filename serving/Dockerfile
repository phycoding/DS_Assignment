FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
# Optional: a locally exported model dir used as an offline fallback if the
# MLflow tracking server is unreachable from inside the container.
COPY model/ ./model/

ENV MLFLOW_TRACKING_URI=http://host.docker.internal:5000 \
    MODEL_NAME=customer_churn_model \
    MODEL_STAGE=Production \
    FALLBACK_MODEL_PATH=/app/model

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
