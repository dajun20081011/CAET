FROM python:3.12-slim AS runtime

ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/cabinlingo

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system cabinlingo && adduser --system --ingroup cabinlingo cabinlingo
WORKDIR /srv/cabinlingo

COPY requirements.txt ./requirements.txt
RUN python -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --retries 10 \
    --timeout 120 \
    --index-url "${PIP_INDEX_URL}" \
    --requirement requirements.txt

COPY app ./app
COPY migrations ./migrations
RUN mkdir -p /uploads/audio && chown -R cabinlingo:cabinlingo /srv/cabinlingo /uploads

USER cabinlingo
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/core/health',timeout=3)" || exit 1

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips=*"]
