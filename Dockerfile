FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RIDE_RADAR_DB=/data/ride_radar.db \n    RIDE_RADAR_MEDIA=/data/media

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY static ./static
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 radar && mkdir -p /data && chown radar /data
USER radar
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# One worker: the rate limiter and SQLite writer are per process. Put a TLS proxy in front.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
